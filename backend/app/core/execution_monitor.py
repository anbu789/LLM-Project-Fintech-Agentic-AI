"""
FinTech Agent — Local Execution Monitor Event Infrastructure
Non-blocking, bounded-queue, rotating JSONL execution telemetry with strict PII/secret redaction,
per-request state tracking, Windows-safe log rotation, and backend restart detection.
"""

from __future__ import annotations

import atexit
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
import uuid

from backend.app.config import settings
from backend.app.core.logging import REDACT_RULES, sanitize_error_message

MONITOR_NODES: Tuple[str, ...] = (
    "input_guardrail",
    "request_intent_router",
    "schema_retriever",
    "query_synthesizer",
    "mql_policy_validator",
    "query_executor",
    "result_verifier",
    "response_composer",
    "schedule_planner",
)

GRAPH_TO_MONITOR_NODE: Dict[str, str] = {
    "input_guardrail": "input_guardrail",
    "intent_router": "request_intent_router",
    "request_intent_router": "request_intent_router",
    "schema_retriever": "schema_retriever",
    "query_synthesizer": "query_synthesizer",
    "mql_policy_validator": "mql_policy_validator",
    "query_executor": "query_executor",
    "result_verifier": "result_verifier",
    "response_composer": "response_composer",
    "schedule_planner": "schedule_planner",
}

SENSITIVE_KEY_MARKERS: Tuple[str, ...] = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "x-goog-api-key",
    "mongo_uri",
    "connection_string",
    "raw_results",
    "verified_results",
    "dry_run_results",
    "result_rows",
    "documents",
    "records",
    "prompt",
    "system_prompt",
    "conversation_history",
    "messages",
)

EXTRA_REDACT_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AIza[0-9A-Za-z\-_]{12,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"x-goog-api-key['\"\s:=]+[^\s'\",;}{]+", re.IGNORECASE), "x-goog-api-key=[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){11,19}\b"), "[REDACTED_NUMBER]"),
)

_DROP_SENTINEL = object()


def resolve_monitor_node_name(graph_node_name: str) -> str:
    """Maps a LangGraph node key to the canonical 9-node monitor identifier."""
    return GRAPH_TO_MONITOR_NODE.get(graph_node_name, graph_node_name)


def sanitize_monitor_text(value: str, max_len: int = 300) -> str:
    """Redacts API keys, URIs, JWTs, emails, and account/card numbers from text."""
    text = sanitize_error_message(str(value))
    for pattern, _ in REDACT_RULES:
        text = pattern.sub("[REDACTED]", text)
    for pattern, replacement in EXTRA_REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def summarize_query_safely(query: Optional[str]) -> Dict[str, Any]:
    """Produces a privacy-safe query summary honoring MONITORING_LOG_FULL_QUERY."""
    raw = str(query or "")
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:12] if raw else ""
    if not raw:
        return {"query_summary": "", "query_length": 0, "query_sha256_12": ""}
    if settings.MONITORING_LOG_FULL_QUERY:
        return {
            "query_summary": sanitize_monitor_text(raw, max_len=240),
            "query_length": len(raw),
            "query_sha256_12": digest,
        }
    redacted_preview = sanitize_monitor_text(raw, max_len=72)
    return {
        "query_summary": redacted_preview,
        "query_length": len(raw),
        "query_sha256_12": digest,
    }


def _is_sensitive_key(key: str) -> bool:
    low = key.lower().strip()
    if low in SENSITIVE_KEY_MARKERS:
        return True
    return any(
        marker in low
        for marker in (
            "password",
            "secret",
            "api_key",
            "apikey",
            "token",
            "authorization",
            "mongo_uri",
            "raw_results",
            "verified_results",
            "dry_run_results",
            "prompt",
        )
    )


def sanitize_event_value(value: Any, key_hint: str = "", depth: int = 0) -> Any:
    """Recursively strips sensitive keys, full result rows, and PII from event metadata."""
    if key_hint and _is_sensitive_key(key_hint):
        return "[REDACTED]"
    if depth > 4:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_monitor_text(value, max_len=300)
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 40:
                cleaned["_truncated_keys"] = len(value) - 40
                break
            k_str = str(k)
            if _is_sensitive_key(k_str):
                cleaned[k_str] = "[REDACTED]"
            else:
                cleaned[k_str] = sanitize_event_value(v, key_hint=k_str, depth=depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        capped = [sanitize_event_value(item, depth=depth + 1) for item in seq[:15]]
        if len(seq) > 15:
            capped.append(f"...(+{len(seq) - 15} more)")
        return capped
    return sanitize_monitor_text(repr(value), max_len=200)


class ExecutionMonitorWriter:
    """Non-blocking bounded-queue rotating JSONL writer for execution telemetry."""

    def __init__(
        self,
        log_path: Optional[str] = None,
        queue_maxsize: Optional[int] = None,
        max_bytes: Optional[int] = None,
        backup_count: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        self._lock = threading.Lock()
        self._boot_id = f"boot-{uuid.uuid4().hex[:12]}"
        self._pid = os.getpid()
        self._dropped_events = 0
        self._written_events = 0
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: queue.Queue[Any] = queue.Queue(
            maxsize=int(queue_maxsize or settings.MONITORING_QUEUE_MAX_SIZE)
        )
        self._enabled = settings.MONITORING_ENABLED if enabled is None else bool(enabled)
        self._log_path = Path(log_path or settings.MONITORING_LOG_PATH)
        self._max_bytes = int(max_bytes or settings.MONITORING_LOG_MAX_BYTES)
        self._backup_count = int(backup_count or settings.MONITORING_LOG_BACKUP_COUNT)
        self._atexit_registered = False

    @property
    def boot_id(self) -> str:
        return self._boot_id

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def log_path(self) -> Path:
        return self._log_path

    @property
    def dropped_events(self) -> int:
        with self._lock:
            return self._dropped_events

    @property
    def written_events(self) -> int:
        with self._lock:
            return self._written_events

    def reconfigure(
        self,
        log_path: Optional[str] = None,
        queue_maxsize: Optional[int] = None,
        max_bytes: Optional[int] = None,
        backup_count: Optional[int] = None,
        enabled: Optional[bool] = None,
        new_boot_id: bool = False,
    ) -> None:
        """Stops any active writer cleanly and updates configuration (used cleanly in tests)."""
        self.shutdown(timeout=1.0)
        with self._lock:
            if log_path is not None:
                self._log_path = Path(log_path)
            if queue_maxsize is not None:
                self._queue = queue.Queue(maxsize=max(1, int(queue_maxsize)))
            else:
                self._queue = queue.Queue(maxsize=int(settings.MONITORING_QUEUE_MAX_SIZE))
            if max_bytes is not None:
                self._max_bytes = int(max_bytes)
            if backup_count is not None:
                self._backup_count = int(backup_count)
            if enabled is not None:
                self._enabled = bool(enabled)
            if new_boot_id:
                self._boot_id = f"boot-{uuid.uuid4().hex[:12]}"
            self._dropped_events = 0
            self._written_events = 0

    def _ensure_worker_started(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            t = threading.Thread(
                target=self._writer_loop,
                name="ExecutionMonitorWriter",
                daemon=True,
            )
            t.start()
            self._worker_thread = t
            if not self._atexit_registered:
                atexit.register(self.shutdown)
                self._atexit_registered = True

    def start(self) -> None:
        """Starts background writer thread and ensures target directory exists."""
        if not self._enabled:
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._ensure_worker_started()

    def shutdown(self, timeout: float = 2.0) -> None:
        """Flushes pending events and stops the background writer thread cleanly."""
        thread_to_join: Optional[threading.Thread] = None
        with self._lock:
            t = self._worker_thread
            if t is not None and t.is_alive():
                self._stop_event.set()
                try:
                    self._queue.put_nowait(_DROP_SENTINEL)
                except queue.Full:
                    pass
                thread_to_join = t
        if thread_to_join is not None and threading.current_thread() is not thread_to_join:
            thread_to_join.join(timeout=timeout)
        with self._lock:
            if self._worker_thread is thread_to_join and (thread_to_join is None or not thread_to_join.is_alive()):
                self._worker_thread = None

    def flush(self, timeout: float = 2.0) -> bool:
        """Waits until currently queued monitoring events are persisted to disk."""
        if not self._enabled:
            return True
        deadline = time.monotonic() + timeout
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        # Allow writer thread a brief moment to finish writing the last popped line
        if hasattr(self._queue, "unfinished_tasks"):
            while self._queue.unfinished_tasks > 0 and time.monotonic() < deadline:
                time.sleep(0.01)
        return self._queue.empty()

    def build_event(
        self,
        event_type: str,
        *,
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        node_name: Optional[str] = None,
        status: Optional[str] = None,
        elapsed_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Constructs a sanitized JSON-serializable execution monitor event record."""
        canonical_node = resolve_monitor_node_name(node_name) if node_name else None
        event: Dict[str, Any] = {
            "schema_version": 1,
            "event_id": f"evt-{uuid.uuid4().hex[:16]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boot_id": self._boot_id,
            "pid": self._pid,
            "event_type": event_type,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "node_name": canonical_node,
            "status": status,
            "elapsed_ms": round(float(elapsed_ms), 2) if elapsed_ms is not None else None,
            "details": sanitize_event_value(details or {}),
        }
        return event

    def emit(
        self,
        event_type: str,
        *,
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        node_name: Optional[str] = None,
        status: Optional[str] = None,
        elapsed_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        start_worker: bool = True,
    ) -> Optional[str]:
        """Enqueues a sanitized event without ever blocking or failing callers."""
        if not self._enabled:
            return None
        try:
            if start_worker:
                self._ensure_worker_started()
            event = self.build_event(
                event_type,
                request_id=request_id,
                conversation_id=conversation_id,
                node_name=node_name,
                status=status,
                elapsed_ms=elapsed_ms,
                details=details,
            )
            line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
            try:
                self._queue.put_nowait(line)
                return event["event_id"]
            except queue.Full:
                with self._lock:
                    self._dropped_events += 1
                return None
        except Exception:
            return None

    def _rotate_if_needed(self, next_bytes: int) -> None:
        if not self._log_path.exists():
            return
        try:
            current_size = self._log_path.stat().st_size
        except OSError:
            return
        if current_size + next_bytes <= self._max_bytes:
            return

        # Windows-safe rotation with copy-truncate fallback if reader briefly touches file
        try:
            for idx in range(self._backup_count, 0, -1):
                cur = self._log_path.with_name(f"{self._log_path.name}.{idx}")
                if idx == self._backup_count:
                    if cur.exists():
                        try:
                            cur.unlink()
                        except OSError:
                            pass
                else:
                    nxt = self._log_path.with_name(f"{self._log_path.name}.{idx + 1}")
                    if cur.exists():
                        if nxt.exists():
                            try:
                                nxt.unlink()
                            except OSError:
                                pass
                        os.replace(cur, nxt)

            backup_one = self._log_path.with_name(f"{self._log_path.name}.1")
            if backup_one.exists():
                try:
                    backup_one.unlink()
                except OSError:
                    pass
            os.replace(self._log_path, backup_one)
        except PermissionError:
            # Windows fallback when external reader holds handle briefly: copy then truncate in-place
            try:
                backup_one = self._log_path.with_name(f"{self._log_path.name}.1")
                shutil.copy2(self._log_path, backup_one)
                with open(self._log_path, "w", encoding="utf-8") as fh:
                    fh.truncate(0)
            except OSError:
                pass
        except OSError:
            pass

    def _write_line(self, line: str) -> None:
        encoded_len = len(line.encode("utf-8"))
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed(encoded_len)
        with open(self._log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
        with self._lock:
            self._written_events += 1

    def _writer_loop(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                if self._stop_event.is_set() and self._queue.empty():
                    break
                continue
            try:
                if item is _DROP_SENTINEL:
                    self._queue.task_done()
                    # Drain any remaining items before exiting
                    while True:
                        try:
                            rem = self._queue.get_nowait()
                        except queue.Empty:
                            return
                        try:
                            if rem is not _DROP_SENTINEL:
                                self._write_line(rem)
                        finally:
                            self._queue.task_done()
                self._write_line(item)
            except Exception:
                # Never allow monitoring I/O failures to propagate
                pass
            finally:
                if item is not _DROP_SENTINEL:
                    self._queue.task_done()


@dataclass
class NodeExecutionRecord:
    """Tracks per-node lifecycle status for one request."""

    node_name: str
    status: str = "PENDING"  # PENDING | RUNNING | COMPLETED | SKIPPED | FAILED
    elapsed_ms: Optional[float] = None
    skip_reason: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    attempts_seen: int = 0


@dataclass
class RequestExecutionState:
    """Isolated per-request execution summary tracked by MonitorStateTracker."""

    request_id: str
    conversation_id: Optional[str] = None
    boot_id: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "RUNNING"  # RUNNING | COMPLETED | FAILED | TIMEOUT | CANCELLED | INTERRUPTED
    provider: Optional[str] = None
    model: Optional[str] = None
    query_summary: str = ""
    http_status: Optional[int] = None
    total_elapsed_ms: Optional[float] = None
    final_error_code: Optional[str] = None
    final_error_message: Optional[str] = None
    current_node: Optional[str] = None
    nodes: Dict[str, NodeExecutionRecord] = field(default_factory=dict)
    gemini_events: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nodes:
            self.nodes = {n: NodeExecutionRecord(node_name=n) for n in MONITOR_NODES}

    def progress_metrics(self) -> Dict[str, Any]:
        completed = sum(1 for r in self.nodes.values() if r.status == "COMPLETED")
        skipped = sum(1 for r in self.nodes.values() if r.status == "SKIPPED")
        failed = sum(1 for r in self.nodes.values() if r.status == "FAILED")
        running = sum(1 for r in self.nodes.values() if r.status == "RUNNING")
        pending = len(MONITOR_NODES) - (completed + skipped + failed + running)
        terminal = completed + skipped + failed
        total = len(MONITOR_NODES)
        return {
            "total": total,
            "terminal": terminal,
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "running": running,
            "pending": max(0, pending),
            "summary_text": (
                f"{terminal}/{total} nodes reached a terminal state — "
                f"{completed} completed, {skipped} skipped, {failed} failed."
            ),
        }


class MonitorStateTracker:
    """
    Stateful event aggregator for execution monitor CLI/TUI and tests.
    Guarantees idempotent deduplication, concurrent request isolation, accurate
    9-node progress tracking, and restart interruption detection.
    """

    def __init__(self, max_requests: int = 50, max_seen_event_ids: int = 20000):
        self._max_requests = max_requests
        self._max_seen_event_ids = max_seen_event_ids
        self._seen_event_ids: OrderedDict[str, None] = OrderedDict()
        self.requests: OrderedDict[str, RequestExecutionState] = OrderedDict()
        self.recent_feed: List[Dict[str, Any]] = []
        self.active_boot_id: Optional[str] = None
        self.backend_status: str = "WAITING"
        self.backend_meta: Dict[str, Any] = {}

    def _mark_seen(self, event_id: Optional[str]) -> bool:
        if not event_id:
            return False
        if event_id in self._seen_event_ids:
            return True
        self._seen_event_ids[event_id] = None
        if len(self._seen_event_ids) > self._max_seen_event_ids:
            self._seen_event_ids.popitem(last=False)
        return False

    def _get_or_create_request(
        self,
        request_id: str,
        conversation_id: Optional[str] = None,
        boot_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> RequestExecutionState:
        req = self.requests.get(request_id)
        if req is None:
            req = RequestExecutionState(
                request_id=request_id,
                conversation_id=conversation_id,
                boot_id=boot_id,
                started_at=timestamp,
                updated_at=timestamp,
            )
            self.requests[request_id] = req
            while len(self.requests) > self._max_requests:
                # Prefer removing the oldest non-running request if possible
                victim_key = next(
                    (k for k, v in self.requests.items() if v.status != "RUNNING"),
                    next(iter(self.requests)),
                )
                del self.requests[victim_key]
        else:
            if conversation_id and not req.conversation_id:
                req.conversation_id = conversation_id
            if boot_id and not req.boot_id:
                req.boot_id = boot_id
            if timestamp:
                req.updated_at = timestamp
        return req

    def ingest_event(self, event: Dict[str, Any]) -> bool:
        """Processes a single JSONL event dict; returns True if newly accepted."""
        if not isinstance(event, dict):
            return False
        event_id = event.get("event_id")
        if self._mark_seen(event_id):
            return False

        ev_type = event.get("event_type", "")
        ts = event.get("timestamp")
        boot_id = event.get("boot_id")
        req_id = event.get("request_id")
        conv_id = event.get("conversation_id")
        node_name = event.get("node_name")
        elapsed_ms = event.get("elapsed_ms")
        details = event.get("details") or {}

        self.recent_feed.append(event)
        if len(self.recent_feed) > 200:
            self.recent_feed = self.recent_feed[-200:]

        if ev_type == "BACKEND_STARTED":
            if boot_id and boot_id != self.active_boot_id:
                for req in self.requests.values():
                    if req.status == "RUNNING" and req.boot_id != boot_id:
                        req.status = "INTERRUPTED"
                        req.finished_at = ts
                        req.current_node = None
                        req.final_error_code = "BACKEND_RESTARTED"
                        req.final_error_message = "Backend restarted or reloaded before request completion."
            self.active_boot_id = boot_id
            self.backend_status = "ONLINE"
            self.backend_meta = dict(details)
            return True

        if ev_type == "BACKEND_SHUTDOWN":
            for req in self.requests.values():
                if req.status == "RUNNING" and (boot_id is None or req.boot_id == boot_id):
                    req.status = "INTERRUPTED"
                    req.finished_at = ts
                    req.current_node = None
                    req.final_error_code = "BACKEND_SHUTDOWN"
                    req.final_error_message = "Backend shut down before request completion."
            self.backend_status = "OFFLINE"
            return True

        if not req_id:
            return True

        # Detect missed BACKEND_STARTED marker if a new boot_id appears mid-stream
        if boot_id and self.active_boot_id and boot_id != self.active_boot_id:
            for req in self.requests.values():
                if req.status == "RUNNING" and req.boot_id == self.active_boot_id:
                    req.status = "INTERRUPTED"
                    req.finished_at = ts
                    req.current_node = None
                    req.final_error_code = "BACKEND_RESTARTED"
                    req.final_error_message = "Backend restarted before request completion."
            self.active_boot_id = boot_id
        elif boot_id and self.active_boot_id is None:
            self.active_boot_id = boot_id

        req = self._get_or_create_request(req_id, conversation_id=conv_id, boot_id=boot_id, timestamp=ts)
        req.events.append(event)
        if len(req.events) > 100:
            req.events = req.events[-100:]

        if ev_type == "REQUEST_STARTED":
            req.status = "RUNNING"
            req.started_at = ts or req.started_at
            req.provider = details.get("provider", req.provider)
            req.model = details.get("model", req.model)
            req.query_summary = details.get("query_summary", req.query_summary)
            return True

        if ev_type in ("REQUEST_COMPLETED", "REQUEST_FAILED", "REQUEST_TIMEOUT", "REQUEST_CANCELLED"):
            status_map = {
                "REQUEST_COMPLETED": "COMPLETED",
                "REQUEST_FAILED": "FAILED",
                "REQUEST_TIMEOUT": "TIMEOUT",
                "REQUEST_CANCELLED": "CANCELLED",
            }
            req.status = status_map[ev_type]
            req.finished_at = ts
            req.current_node = None
            if elapsed_ms is not None:
                req.total_elapsed_ms = float(elapsed_ms)
            req.http_status = details.get("http_status", req.http_status)
            req.provider = details.get("provider", req.provider)
            req.model = details.get("model", req.model)
            req.final_error_code = details.get("error_code")
            req.final_error_message = details.get("error_message")
            return True

        if ev_type.startswith("PROVIDER_"):
            req.gemini_events.append(event)
            if len(req.gemini_events) > 40:
                req.gemini_events = req.gemini_events[-40:]
            if details.get("provider"):
                req.provider = details["provider"]
            if details.get("model"):
                req.model = details["model"]
            return True

        if node_name:
            canonical = resolve_monitor_node_name(node_name)
            rec = req.nodes.get(canonical)
            if rec is None:
                rec = NodeExecutionRecord(node_name=canonical)
                req.nodes[canonical] = rec

            if ev_type == "NODE_STARTED":
                # Only update to RUNNING if not already permanently completed unless genuinely re-entered
                rec.status = "RUNNING"
                rec.started_at = ts
                rec.attempts_seen += 1
                req.current_node = canonical
                if details:
                    rec.details.update(details)
            elif ev_type == "NODE_COMPLETED":
                rec.status = "COMPLETED"
                rec.finished_at = ts
                if elapsed_ms is not None:
                    rec.elapsed_ms = float(elapsed_ms)
                if details:
                    rec.details.update(details)
                if req.current_node == canonical:
                    req.current_node = None
            elif ev_type == "NODE_FAILED":
                rec.status = "FAILED"
                rec.finished_at = ts
                if elapsed_ms is not None:
                    rec.elapsed_ms = float(elapsed_ms)
                rec.error = details.get("error_message") or details.get("error_code") or "Node failed"
                if details:
                    rec.details.update(details)
                if req.current_node == canonical:
                    req.current_node = None
            elif ev_type == "NODE_SKIPPED":
                # Never overwrite an actually completed or failed node with skipped
                if rec.status in ("PENDING", "RUNNING"):
                    rec.status = "SKIPPED"
                    rec.finished_at = ts
                    rec.skip_reason = details.get("skip_reason") or details.get("reason")
                    if details:
                        rec.details.update(details)
                    if req.current_node == canonical:
                        req.current_node = None
            return True

        return True


execution_monitor = ExecutionMonitorWriter()
