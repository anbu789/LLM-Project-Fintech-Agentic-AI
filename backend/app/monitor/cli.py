"""
FinTech Agent — Terminal Execution Monitor (Terminal 2)
Tails the local rotating JSONL execution event stream independently of the frontend
and renders live multi-request progress, 9-node LangGraph lifecycle states, Gemini retry
telemetry, and security/execution details using Rich with automatic plain-text fallback.
"""

from __future__ import annotations

import argparse
from io import StringIO
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backend.app.config import settings
from backend.app.core.execution_monitor import (
    MONITOR_NODES,
    MonitorStateTracker,
    RequestExecutionState,
)


def _short_ts(iso_ts: Optional[str]) -> str:
    if not iso_ts:
        return "--:--:--"
    if "T" in iso_ts:
        tail = iso_ts.split("T", 1)[1]
        return tail[:8]
    return str(iso_ts)[:8]


def _fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    if ms >= 1000.0:
        return f"{ms / 1000.0:.2f}s"
    return f"{ms:.1f}ms"


def format_provider_event_line(event: Dict[str, Any]) -> str:
    """Formats a provider lifecycle JSONL event into a crisp diagnostic line."""
    ts = _short_ts(event.get("timestamp"))
    ev_type = event.get("event_type", "")
    details = event.get("details") or {}
    prov = str(details.get("provider") or "LLM").upper()
    attempt = details.get("attempt") or details.get("attempts_used")
    max_att = details.get("max_attempts")
    elapsed_ms = event.get("elapsed_ms")
    elapsed_str = f" ({_fmt_ms(elapsed_ms)})" if elapsed_ms is not None else ""

    if ev_type == "PROVIDER_REQUEST_STARTED":
        att_lbl = f"Attempt {attempt}/{max_att} " if attempt and max_att else ""
        t_cfg = details.get("attempt_timeout_seconds")
        t_str = f" (timeout {t_cfg}s)" if t_cfg is not None else ""
        return f"{ts} [{prov}] {att_lbl}STARTED{t_str}"

    if ev_type == "PROVIDER_RESPONSE_RECEIVED":
        att_lbl = f"Attempt {attempt}/{max_att} " if attempt and max_att else ""
        code = details.get("http_status", 200)
        return f"{ts} [{prov}] {att_lbl}HTTP {code}{elapsed_str}"

    if ev_type == "PROVIDER_RETRYABLE_ERROR":
        att_lbl = f"Attempt {attempt}/{max_att} " if attempt and max_att else ""
        err_type = details.get("error_type") or event.get("status") or "ERROR"
        if str(err_type).startswith("HTTP_"):
            err_label = f"HTTP {err_type.split('_', 1)[1]}"
        else:
            err_label = str(err_type)
        return f"{ts} [{prov}] {att_lbl}{err_label}{elapsed_str}"

    if ev_type == "PROVIDER_RETRY_SCHEDULED":
        delay = details.get("delay_seconds", "-")
        reason = details.get("reason", "")
        nxt = details.get("next_attempt")
        nxt_str = f" -> Attempt {nxt}/{max_att}" if nxt and max_att else ""
        r_str = f" [{reason}]" if reason else ""
        return f"{ts} [{prov}] Retry scheduled — delay {delay}s{nxt_str}{r_str}"

    if ev_type == "PROVIDER_SUCCESS":
        used = details.get("attempts_used")
        u_str = f" ({used} attempt{'s' if used != 1 else ''})" if used is not None else ""
        return f"{ts} [{prov}] FINAL SUCCESS{u_str}{elapsed_str}"

    if ev_type == "PROVIDER_FAILURE":
        code = details.get("error_code") or event.get("status") or "FAILED"
        return f"{ts} [{prov}] FINAL FAILURE — {code}{elapsed_str}"

    if ev_type == "PROVIDER_FALLBACK_STARTED":
        from_p = str(details.get("from_provider") or "").upper()
        to_p = str(details.get("to_provider") or "").upper()
        reason = details.get("reason", "")
        rem = details.get("remaining_budget_seconds")
        rem_str = f" [rem {rem:.1f}s]" if rem is not None else ""
        return f"{ts} [FALLBACK] {from_p} -> {to_p} ({reason}){rem_str}"

    if ev_type == "PROVIDER_FALLBACK_SKIPPED":
        p = str(details.get("provider") or "").upper()
        reason = details.get("reason", "")
        return f"{ts} [FALLBACK] Skipped {p} ({reason})"

    if ev_type == "PROVIDER_CHAIN_EXHAUSTED":
        att = ",".join(details.get("attempted_providers") or [])
        return f"{ts} [FALLBACK] Chain exhausted: attempted [{att}]{elapsed_str}"

    if ev_type == "PROVIDER_ATTEMPT_COMPLETED":
        p = str(details.get("provider") or prov).upper()
        fb = " (fallback)" if details.get("is_fallback") else ""
        return f"{ts} [{p}] Attempt completed{fb}{elapsed_str}"

    if ev_type == "PROVIDER_ATTEMPT_FAILED":
        p = str(details.get("provider") or prov).upper()
        rec = "recoverable" if details.get("recoverable") else "non-recoverable"
        err = details.get("error", "")
        err_str = f" - {err[:40]}" if err else ""
        return f"{ts} [{p}] Attempt failed ({rec}){err_str}{elapsed_str}"

    return f"{ts} [{prov}] {ev_type}{elapsed_str}"


def _node_style_tag(status: str, details: Dict[str, Any]) -> tuple[str, str]:
    """Maps node execution status to Rich style and status indicator."""
    if status == "COMPLETED":
        if details.get("execution_status") == "GATE_BLOCKED" or details.get("allowed") is False:
            return "yellow", "COMPLETED (GATED/BLOCKED)"
        return "green", "COMPLETED"
    if status == "RUNNING":
        return "yellow", "RUNNING"
    if status == "FAILED":
        return "red", "FAILED"
    if status == "SKIPPED":
        return "bright_black", "SKIPPED"
    return "bright_black", "PENDING"


def _request_style(status: str) -> str:
    if status in ("COMPLETED", "success"):
        return "green"
    if status in ("RUNNING", "INTERRUPTED"):
        return "yellow"
    if status in ("FAILED", "TIMEOUT", "CANCELLED"):
        return "red"
    return "bright_black"


def _ascii_progress_bar(metrics: Dict[str, Any], width: int = 18) -> str:
    """Renders event-driven discrete progress bar strictly from terminal node counts."""
    total = max(1, metrics["total"])
    c_len = round((metrics["completed"] / total) * width)
    s_len = round((metrics["skipped"] / total) * width)
    f_len = round((metrics["failed"] / total) * width)
    used = c_len + s_len + f_len
    if used > width:
        overflow = used - width
        s_len = max(0, s_len - overflow)
    rem = max(0, width - (c_len + s_len + f_len))
    return "[" + ("#" * c_len) + ("s" * s_len) + ("!" * f_len) + ("." * rem) + "]"


def _rich_progress_text(metrics: Dict[str, Any]) -> Text:
    total = metrics["total"]
    c = metrics["completed"]
    s = metrics["skipped"]
    f = metrics["failed"]
    p = metrics["pending"] + metrics["running"]
    t = Text()
    t.append("[")
    if c:
        t.append("#" * (c * 2), style="green")
    if s:
        t.append("s" * (s * 2), style="bright_black")
    if f:
        t.append("!" * (f * 2), style="red")
    if metrics["running"]:
        t.append(">" * (metrics["running"] * 2), style="yellow")
    rem = max(0, total - c - s - f - metrics["running"])
    if rem:
        t.append("." * (rem * 2), style="bright_black")
    t.append(f"] {metrics['summary_text']}  ", style="white")
    t.append("#=ok ", style="green")
    t.append("s=skip ", style="bright_black")
    t.append("!=fail", style="red")
    return t


def _select_focus_request(tracker: MonitorStateTracker) -> Optional[RequestExecutionState]:
    if not tracker.requests:
        return None
    running = [r for r in tracker.requests.values() if r.status == "RUNNING"]
    if running:
        return running[-1]
    all_reqs = list(tracker.requests.values())
    return all_reqs[-1]


def _build_node_summary_detail(node_name: str, rec) -> str:
    d = rec.details or {}
    if rec.status == "SKIPPED":
        return f"Skip reason: {rec.skip_reason or 'Conditionally bypassed'}"
    if rec.status == "FAILED":
        return f"Error: {rec.error or 'Execution failed'}"
    if rec.status == "PENDING":
        return "Not executed"
    if rec.status == "RUNNING":
        return "Executing..."

    if node_name == "input_guardrail":
        return f"result={d.get('guardrail_result', 'allowed')}" + (
            f" ({d['rejection_reason']})" if d.get("rejection_reason") else ""
        )
    if node_name == "request_intent_router":
        return f"intent={d.get('intent_classification', '-')} | route={d.get('selected_route', '-')}"
    if node_name == "schema_retriever":
        cols = ", ".join(d.get("selected_collections") or []) or "-"
        return f"status={d.get('retrieval_status', 'ok')} | collections=[{cols}] | entries={d.get('retrieved_entries_count', 0)}"
    if node_name == "query_synthesizer":
        col = d.get("target_collection") or "-"
        stages = d.get("pipeline_stage_count", 0)
        return f"provider={d.get('provider', '-')}/{d.get('model', '-')} | status={d.get('synthesis_status', '-')} | col={col} | stages={stages} (unvalidated)"
    if node_name == "mql_policy_validator":
        res = d.get("validation_result", "-")
        gate = d.get("execution_gate_status", "-")
        if d.get("allowed"):
            return f"result={res} | gate={gate} | executable={d.get('is_executable', False)}"
        return f"result={res} | category={d.get('policy_category', '-')} | reason={d.get('rejection_reason', '-')}"
    if node_name == "query_executor":
        if d.get("execution_status") == "GATE_BLOCKED":
            return f"gate=BLOCKED | db_executed=False | {d.get('skipped_or_blocked_reason', 'Gate disabled')}"
        return (
            f"status={d.get('execution_status', '-')} | gate_ok={d.get('execution_gate_permitted')} | "
            f"db_ms={d.get('db_execution_duration_ms', '-')} | rows={d.get('result_count', 0)} | "
            f"truncated={d.get('result_truncated', False)}"
        )
    if node_name == "result_verifier":
        return f"verification={d.get('verification_status', '-')} | accepted={d.get('accepted', False)} | {d.get('recovery_or_failure_reason', '')}"
    if node_name == "response_composer":
        return f"final_status={d.get('final_status', '-')} | response_chars={d.get('response_length', 0)}"
    if node_name == "schedule_planner":
        return f"preview={d.get('preview_id', '-')} | dry_run={d.get('dry_run_status', '-')} | live_reg={d.get('phase7_live_registration_enabled', False)}"
    return "-"


def render_rich_dashboard(tracker: MonitorStateTracker, log_path: Path) -> Group:
    """Builds Rich renderables for the multi-request backend execution monitor."""
    # 1. Header Banner
    backend_color = "green" if tracker.backend_status == "ONLINE" else ("red" if tracker.backend_status == "OFFLINE" else "yellow")
    meta = tracker.backend_meta or {}
    header_text = Text()
    header_text.append("FinTech Agent Execution Monitor  ", style="bold cyan")
    header_text.append(f"[{tracker.backend_status}] ", style=f"bold {backend_color}")
    if tracker.active_boot_id:
        header_text.append(f"boot={tracker.active_boot_id} ", style="white")
    if meta:
        header_text.append(
            f"| port={meta.get('port', settings.APP_PORT)} | provider={meta.get('provider', settings.LLM_PROVIDER)} "
            f"| model={meta.get('model', settings.LLM_MODEL)} | gate_live={meta.get('phase6_live_execution_enabled', False)}",
            style="white",
        )
    header_text.append(f"\nStream: {log_path}", style="bright_black")
    header_panel = Panel(header_text, border_style="cyan", padding=(0, 1))

    # 2. Active & Bounded Recent Request History Table
    req_table = Table(title="Requests (Active & Recent History)", expand=True, show_lines=False)
    req_table.add_column("Request ID", style="cyan", no_wrap=True)
    req_table.add_column("Conversation", no_wrap=True)
    req_table.add_column("Status", no_wrap=True)
    req_table.add_column("Provider / Model")
    req_table.add_column("Current Node")
    req_table.add_column("Progress", no_wrap=True)
    req_table.add_column("HTTP", no_wrap=True)
    req_table.add_column("Elapsed", no_wrap=True)

    recent_reqs = list(tracker.requests.values())[-12:]
    if not recent_reqs:
        req_table.add_row("(waiting for incoming chat requests...)", "-", "-", "-", "-", "0/9", "-", "-")
    else:
        for r in reversed(recent_reqs):
            m = r.progress_metrics()
            st_color = _request_style(r.status)
            req_table.add_row(
                r.request_id,
                r.conversation_id or "-",
                Text(r.status, style=f"bold {st_color}"),
                f"{r.provider or '-'} / {r.model or '-'}",
                r.current_node or ("-" if r.status != "RUNNING" else "initializing"),
                f"{m['terminal']}/{m['total']} ({m['completed']} ok, {m['skipped']} skip, {m['failed']} fail)",
                str(r.http_status) if r.http_status else "-",
                _fmt_ms(r.total_elapsed_ms),
            )

    panels: List[Any] = [header_panel, req_table]

    # 3. Focused Request Inspector (9 Nodes + Details + Gemini Log)
    focus = _select_focus_request(tracker)
    if focus is not None:
        m = focus.progress_metrics()
        focus_color = _request_style(focus.status)
        meta_line = Text()
        meta_line.append(f"Request: {focus.request_id}  ", style="bold cyan")
        meta_line.append(f"Conv: {focus.conversation_id or '-'}  ", style="white")
        meta_line.append(f"Outcome: {focus.status}", style=f"bold {focus_color}")
        if focus.http_status:
            meta_line.append(f" (HTTP {focus.http_status})", style=focus_color)
        if focus.final_error_code:
            meta_line.append(f" [{focus.final_error_code}]", style="red")
        if focus.total_elapsed_ms is not None:
            meta_line.append(f" | Total: {_fmt_ms(focus.total_elapsed_ms)}", style="white")
        meta_line.append(f"\nQuery (safe summary): {focus.query_summary or '-'}\n", style="bright_black")
        meta_line.append_text(_rich_progress_text(m))

        node_table = Table(expand=True, show_lines=False)
        node_table.add_column("#", width=2)
        node_table.add_column("LangGraph Node", no_wrap=True)
        node_table.add_column("Status", no_wrap=True)
        node_table.add_column("Duration", no_wrap=True)
        node_table.add_column("Sanitized Stage Diagnostics")

        for idx, n_name in enumerate(MONITOR_NODES, start=1):
            rec = focus.nodes[n_name]
            style, label = _node_style_tag(rec.status, rec.details)
            node_table.add_row(
                str(idx),
                n_name,
                Text(label, style=f"bold {style}"),
                _fmt_ms(rec.elapsed_ms),
                _build_node_summary_detail(n_name, rec),
            )

        panels.append(Panel(Group(meta_line, node_table), title="Focused Execution Trace (9-Node Pipeline)", border_style=focus_color))

        # Gemini Attempt Activity
        if focus.gemini_events:
            gem_text = Text()
            for gev in focus.gemini_events[-10:]:
                line = format_provider_event_line(gev)
                ev_t = gev.get("event_type", "")
                line_style = "green" if "SUCCESS" in ev_t or "RECEIVED" in ev_t else ("red" if "FAILURE" in ev_t else "yellow")
                gem_text.append(line + "\n", style=line_style)
            panels.append(Panel(gem_text, title="Provider / Gemini Attempt Log", border_style="yellow"))

    # 4. Live Event Feed
    feed_text = Text()
    for ev in tracker.recent_feed[-10:]:
        ts = _short_ts(ev.get("timestamp"))
        et = ev.get("event_type", "")
        rid = ev.get("request_id") or "system"
        node = f"/{ev['node_name']}" if ev.get("node_name") else ""
        st = ev.get("status") or ""
        em = f" ({_fmt_ms(ev.get('elapsed_ms'))})" if ev.get("elapsed_ms") is not None else ""
        style = "green" if "COMPLETED" in et or "SUCCESS" in et or et == "BACKEND_STARTED" else ("red" if "FAIL" in et or "TIMEOUT" in et or "CANCEL" in et else ("bright_black" if "SKIPPED" in et else "yellow"))
        feed_text.append(f"{ts} [{rid}]{node} {et} status={st}{em}\n", style=style)
    if not tracker.recent_feed:
        feed_text.append("No events observed yet.", style="bright_black")
    panels.append(Panel(feed_text, title="Live Event Feed", border_style="blue"))

    return Group(*panels)


def render_plain_dashboard(tracker: MonitorStateTracker, log_path: Path) -> str:
    """ANSI-free readable plain-text dashboard fallback when Rich live colors are unavailable."""
    lines: List[str] = []
    meta = tracker.backend_meta or {}
    lines.append("=" * 88)
    lines.append(
        f"FINTECH AGENT EXECUTION MONITOR | backend={tracker.backend_status} "
        f"| boot={tracker.active_boot_id or '-'} | port={meta.get('port', settings.APP_PORT)} "
        f"| provider={meta.get('provider', settings.LLM_PROVIDER)}/{meta.get('model', settings.LLM_MODEL)}"
    )
    lines.append(f"Log Stream: {log_path}")
    lines.append("-" * 88)

    recent_reqs = list(tracker.requests.values())[-8:]
    if not recent_reqs:
        lines.append("Active/Recent Requests: (waiting for incoming requests...)")
    else:
        lines.append("Recent Requests:")
        for r in reversed(recent_reqs):
            m = r.progress_metrics()
            lines.append(
                f"  - {r.request_id} | conv={r.conversation_id or '-'} | status={r.status} "
                f"| node={r.current_node or '-'} | progress={m['terminal']}/{m['total']} "
                f"({m['completed']} ok, {m['skipped']} skip, {m['failed']} fail) "
                f"| http={r.http_status or '-'} | total={_fmt_ms(r.total_elapsed_ms)}"
            )

    focus = _select_focus_request(tracker)
    if focus is not None:
        m = focus.progress_metrics()
        lines.append("-" * 88)
        lines.append(
            f"Focused Request: {focus.request_id} (conv={focus.conversation_id or '-'}) | "
            f"status={focus.status} | http={focus.http_status or '-'} | elapsed={_fmt_ms(focus.total_elapsed_ms)}"
        )
        lines.append(f"Query (safe): {focus.query_summary or '-'}")
        lines.append(f"Progress: {_ascii_progress_bar(m)} {m['summary_text']}")
        lines.append("Nodes (9-Node Pipeline):")
        for idx, n_name in enumerate(MONITOR_NODES, start=1):
            rec = focus.nodes[n_name]
            lines.append(
                f"  {idx}. {n_name:<22} | {rec.status:<10} | {_fmt_ms(rec.elapsed_ms):<8} | "
                f"{_build_node_summary_detail(n_name, rec)}"
            )
        if focus.gemini_events:
            lines.append("Provider / Gemini Attempts:")
            for gev in focus.gemini_events[-10:]:
                lines.append(f"  {format_provider_event_line(gev)}")

    if tracker.recent_feed:
        lines.append("-" * 88)
        lines.append("Live Event Feed:")
        for ev in tracker.recent_feed[-8:]:
            ts = _short_ts(ev.get("timestamp"))
            et = ev.get("event_type", "")
            rid = ev.get("request_id") or "system"
            node = f"/{ev['node_name']}" if ev.get("node_name") else ""
            lines.append(f"  {ts} [{rid}]{node} {et} ({ev.get('status', '-')})")

    lines.append("=" * 88)
    return "\n".join(lines)


class JsonlEventTailer:
    """
    Windows-safe incremental reader for rotating JSONL event logs.
    Opens and closes files concisely per poll so log rotation never encounters persistent reader locks.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.offset = 0
        self._remainder = ""
        self._head_fingerprint: Optional[str] = None

    def _read_head_fingerprint(self) -> Optional[str]:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as fh:
                first_line = fh.readline(512)
                return first_line.strip() or None
        except OSError:
            return None

    def _parse_lines(self, raw_chunk: str, tracker: MonitorStateTracker) -> int:
        if not raw_chunk:
            return 0
        text = self._remainder + raw_chunk
        if text.endswith("\n"):
            parts = text.splitlines()
            self._remainder = ""
        else:
            split = text.splitlines()
            if split:
                parts = split[:-1]
                self._remainder = split[-1]
            else:
                parts = []
                self._remainder = text

        accepted = 0
        for line in parts:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                ev = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if tracker.ingest_event(ev):
                accepted += 1
        return accepted

    def poll(self, tracker: MonitorStateTracker, *, initial_read: bool = False) -> int:
        """Reads newly appended JSON lines and recovers across single or multiple rotations seamlessly."""
        if not self.log_path.exists():
            return 0

        try:
            size = self.log_path.stat().st_size
        except OSError:
            return 0

        accepted = 0
        current_head = self._read_head_fingerprint() if size > 0 else None
        rotated_or_truncated = (
            size < self.offset
            or (
                self._head_fingerprint is not None
                and current_head is not None
                and current_head != self._head_fingerprint
            )
        )

        if rotated_or_truncated:
            # Drain rotated backups oldest -> newest; MonitorStateTracker deduplicates by event_id
            backup_files = sorted(
                self.log_path.parent.glob(f"{self.log_path.name}.*"),
                key=lambda p: int(p.name.rsplit(".", 1)[1]) if p.name.rsplit(".", 1)[-1].isdigit() else 0,
                reverse=True,
            )
            for bfile in backup_files:
                try:
                    with open(bfile, "r", encoding="utf-8", errors="replace") as bfh:
                        accepted += self._parse_lines(bfh.read(), tracker)
                except OSError:
                    pass
            self.offset = 0
            self._remainder = ""
            self._head_fingerprint = None

        if initial_read and self.offset == 0 and size > 2_097_152:
            # Start from last ~2MB on huge pre-existing logs, skipping to next complete line
            self.offset = size - 2_097_152

        if size == self.offset:
            return accepted

        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as fh:
                if self.offset > 0:
                    fh.seek(self.offset)
                    if initial_read and size > 2_097_152:
                        fh.readline()  # discard partial first line
                chunk = fh.read()
                self.offset = fh.tell()
            if chunk:
                accepted += self._parse_lines(chunk, tracker)
                if self._head_fingerprint is None:
                    self._head_fingerprint = self._read_head_fingerprint()
        except OSError:
            return accepted

        return accepted


def run_monitor(
    log_path: Optional[str] = None,
    *,
    plain: bool = False,
    once: bool = False,
    poll_interval: float = 0.2,
) -> int:
    """Runs the dedicated terminal execution monitor loop or single-shot snapshot."""
    target_path = Path(log_path or settings.MONITORING_LOG_PATH)
    tracker = MonitorStateTracker()
    tailer = JsonlEventTailer(target_path)
    tailer.poll(tracker, initial_read=True)

    use_plain = (
        plain
        or not sys.stdout.isatty()
        or bool(os.environ.get("NO_COLOR"))
    )

    if once:
        if use_plain:
            print(render_plain_dashboard(tracker, target_path))
        else:
            console = Console()
            console.print(render_rich_dashboard(tracker, target_path))
        return 0

    if use_plain:
        last_output = ""
        print(f"[FinTech Agent Monitor] Plain-text mode watching: {target_path} (Ctrl+C to exit)")
        try:
            while True:
                changed = tailer.poll(tracker)
                output = render_plain_dashboard(tracker, target_path)
                if changed or not last_output:
                    if last_output and sys.stdout.isatty():
                        os.system("cls" if os.name == "nt" else "clear")
                    print(output, flush=True)
                    last_output = output
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[FinTech Agent Monitor] Stopped.")
            return 0

    console = Console()
    try:
        with Live(
            render_rich_dashboard(tracker, target_path),
            console=console,
            refresh_per_second=4,
            screen=False,
        ) as live:
            while True:
                tailer.poll(tracker)
                live.update(render_rich_dashboard(tracker, target_path))
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        console.print("\n[cyan]FinTech Agent Execution Monitor stopped.[/cyan]")
        return 0
    except Exception:
        # Automatic plain-text fallback if Rich Live encounters restricted terminal capabilities
        print(render_plain_dashboard(tracker, target_path))
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.app.monitor",
        description="FinTech Agent dedicated real-time backend execution monitor (Terminal 2).",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Path to execution JSONL event file (defaults to settings.MONITORING_LOG_PATH).",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Force ANSI-free plain-text rendering instead of Rich live dashboard.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read available events, render one snapshot, and exit.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.2,
        help="Polling interval in seconds (default: 0.2).",
    )
    args = parser.parse_args(argv)
    return run_monitor(
        log_path=args.log_path,
        plain=args.plain,
        once=args.once,
        poll_interval=max(0.05, args.interval),
    )


if __name__ == "__main__":
    raise SystemExit(main())
