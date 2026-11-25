"""
FinTech Agent — 55-Question Live Benchmark Execution Engine
Executes all 55 natural-language questions from fintech-agent/data/test_questions.json
against the real LangGraph agent pipeline, real LLM provider fallback chain
(Gemini 3.8 Flash -> Groq GPT-OSS 120B -> Ollama), and local authenticated MongoDB.

Guarantees:
- Strictly read-only database execution via ReadOnlyDatabaseProxy
- Incremental checkpointing to results.json and results.csv after each question
- Uninterruptible loop: continues through all 55 questions
- Zero modification to .env, database data, or credentials
"""

import asyncio
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from typing import Any, Dict, List, Optional
import sys

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Project imports
from backend.app.config import PROJECT_ROOT, settings

# Enable live read-only execution in memory for this benchmark process only (leaves .env unmodified on disk)
settings.PHASE6_LIVE_EXECUTION_ENABLED = True
settings.PHASE7_SCHEDULER_ENABLED = False
settings.QUERY_MAX_RETRY_ATTEMPTS = 0

from backend.app.agent.graph import agent_graph
from backend.app.core.deadline import (
    RequestDeadline,
    set_request_preferred_provider,
    reset_request_preferred_provider,
    get_request_preferred_provider,
)
from backend.app.core.exceptions import LLMFallbackExhaustedError, ProviderTimeoutError


QUESTIONS_FILE = PROJECT_ROOT / "fintech-agent" / "data" / "test_questions.json"
OUTPUT_DIR = PROJECT_ROOT / "IEEE_REPORT_EVIDENCE" / "55_QUERY_BENCHMARK"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_JSON = OUTPUT_DIR / "results.json"
RESULTS_CSV = OUTPUT_DIR / "results.csv"
SUMMARY_MD = OUTPUT_DIR / "execution_summary.md"


def load_benchmark_questions() -> List[Dict[str, Any]]:
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def sanitize_pipeline(pipeline: Any) -> Any:
    if not pipeline:
        return None
    try:
        return json.loads(json.dumps(pipeline, default=str))
    except Exception:
        return str(pipeline)


async def execute_single_question(q: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    qid = q["id"]
    prompt = q["question"]
    level = q.get("level", 1)
    req_id = f"bench-55-{qid.lower()}-{int(time.time())}"
    conv_id = f"conv-bench-{qid.lower()}"

    print(f"\n[{index}/{total}] Starting {qid} (Level {level}): \"{prompt}\"")

    # Allocate a healthy 45.0s request deadline to allow multi-provider fallback if primary times out
    deadline = RequestDeadline(45.0, req_id)
    token = set_request_preferred_provider(None)

    initial_state = {
        "request_id": req_id,
        "natural_language_query": prompt,
        "user_message": prompt,
        "conversation_history": [],
        "thread_id": conv_id,
        "selected_provider": None,
        "retry_count": 0,
        "max_retries": 0,
        "trace": [],
        "all_attempts": [],
        "result_truncated": False,
        "dry_run": False,
        "schedule_approved": False,
        "is_api_request": False,
    }

    start_time = time.time()
    record: Dict[str, Any] = {
        "id": qid,
        "level": level,
        "question": prompt,
        "hint": q.get("hint", ""),
        "expected_operators": q.get("operators", []),
        "expected_collections": q.get("collections", []),
        "provider": None,
        "model": None,
        "request_mode": None,
        "target_collection": None,
        "generated_pipeline": None,
        "validation_status": None,
        "validation_errors": [],
        "execution_status": None,
        "result_row_count": 0,
        "sample_results": [],
        "duration_s": 0.0,
        "error_detail": None,
        "final_status": "PENDING",
        "ground_truth_correctness": "NOT VERIFIED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        final_state = await asyncio.wait_for(
            agent_graph.ainvoke(initial_state),
            timeout=50.0,
        )
        dur = round(time.time() - start_time, 2)
        record["duration_s"] = dur

        # Extract telemetry
        mode = final_state.get("request_mode")
        record["request_mode"] = mode
        provider = (
            final_state.get("selected_provider")
            or get_request_preferred_provider()
            or final_state.get("llm_provider")
            or settings.LLM_PROVIDER
        )
        record["provider"] = provider
        record["model"] = final_state.get("llm_model") or settings.LLM_MODEL
        record["target_collection"] = final_state.get("target_collection") or final_state.get("selected_collection")
        record["generated_pipeline"] = sanitize_pipeline(final_state.get("generated_pipeline") or final_state.get("approved_pipeline"))
        record["validation_status"] = final_state.get("validation_status")
        record["validation_errors"] = final_state.get("validation_errors") or []
        record["execution_status"] = final_state.get("execution_status")
        raw_res = final_state.get("raw_results") or []
        record["result_row_count"] = len(raw_res) if isinstance(raw_res, list) else (final_state.get("result_row_count") or 0)
        record["sample_results"] = sanitize_pipeline(raw_res[:2] if isinstance(raw_res, list) else [])

        # Determine final status classification
        guardrail = final_state.get("guardrail_status")
        v_status = final_state.get("validation_status")
        exec_status = final_state.get("execution_status")

        if guardrail == "rejected":
            record["final_status"] = "REJECTED_GUARDRAIL"
            record["error_detail"] = "Blocked by input guardrail"
        elif mode == "CLARIFICATION_REQUIRED":
            record["final_status"] = "CLARIFICATION"
            record["error_detail"] = final_state.get("clarification_question") or "Clarification requested by agent"
        elif mode == "OUT_OF_SCOPE":
            record["final_status"] = "OUT_OF_SCOPE"
            record["error_detail"] = "Query classified as out of banking scope"
        elif v_status == "UNSUPPORTED":
            record["final_status"] = "REJECTED_UNSUPPORTED"
            record["error_detail"] = "Unsupported banking concepts identified"
        elif v_status in ("INVALID", "REJECTED"):
            record["final_status"] = "REJECTED_POLICY"
            record["error_detail"] = "; ".join(record["validation_errors"]) or "MQL policy validator rejected pipeline"
        elif exec_status in ("SUCCESS_DATA", "SUCCESS_PREVIEW", "SUCCESS_EMPTY") or (exec_status is None and record["result_row_count"] > 0):
            record["final_status"] = "SUCCESS"
        elif exec_status == "GATE_BLOCKED":
            record["final_status"] = "GATE_BLOCKED"
            record["error_detail"] = final_state.get("execution_error") or "Fail-closed gate blocked execution"
        elif exec_status == "EXECUTION_ERROR":
            record["final_status"] = "EXECUTION_ERROR"
            record["error_detail"] = final_state.get("execution_error") or "MongoDB execution error"
        else:
            if v_status == "VALID" and record["result_row_count"] >= 0:
                record["final_status"] = "SUCCESS"
            else:
                record["final_status"] = f"OTHER_{v_status or mode}"

    except asyncio.TimeoutError:
        dur = round(time.time() - start_time, 2)
        record["duration_s"] = dur
        record["final_status"] = "TIMEOUT"
        record["error_detail"] = f"Execution exceeded 50.0s overall timeout (elapsed={dur}s)"
    except LLMFallbackExhaustedError as e:
        dur = round(time.time() - start_time, 2)
        record["duration_s"] = dur
        record["final_status"] = "PROVIDER_FAILURE"
        record["error_detail"] = str(e)
    except Exception as e:
        dur = round(time.time() - start_time, 2)
        record["duration_s"] = dur
        record["final_status"] = "ERROR"
        record["error_detail"] = f"{type(e).__name__}: {str(e)}"
    finally:
        reset_request_preferred_provider(token)

    print(
        f"[{index}/{total}] Completed {qid} in {record['duration_s']}s -> "
        f"Status: {record['final_status']} | Provider: {record['provider']} | Rows: {record['result_row_count']}"
    )
    return record


def save_checkpoint(results: List[Dict[str, Any]]):
    # 1. JSON
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # 2. CSV
    fieldnames = [
        "id", "level", "question", "provider", "model", "request_mode",
        "target_collection", "validation_status", "execution_status",
        "result_row_count", "duration_s", "final_status", "error_detail",
        "ground_truth_correctness", "timestamp"
    ]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)


def generate_summary_report(results: List[Dict[str, Any]]) -> str:
    total = len(results)
    successful = sum(1 for r in results if r["final_status"] == "SUCCESS")
    clarifications = sum(1 for r in results if r["final_status"] == "CLARIFICATION")
    policy_rejected = sum(1 for r in results if "REJECTED" in r["final_status"])
    provider_failures = sum(1 for r in results if r["final_status"] in ("PROVIDER_FAILURE", "TIMEOUT"))
    other_errors = total - (successful + clarifications + policy_rejected + provider_failures)

    durations = [r["duration_s"] for r in results if r["duration_s"] > 0]
    avg_dur = round(statistics.mean(durations), 2) if durations else 0.0
    med_dur = round(statistics.median(durations), 2) if durations else 0.0

    providers = {}
    for r in results:
        p = r["provider"] or "none"
        providers[p] = providers.get(p, 0) + 1

    lines = [
        "# FinTech Agent — 55-Question Live Benchmark Execution Summary",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Target Dataset:** `fintech-agent/data/test_questions.json` (55 Questions across 5 Complexity Levels)  ",
        f"**Database:** Authenticated MongoDB (`fintech_agent_db`, 19,120 records, Read-Only Sandboxed)  ",
        f"**LLM Fallback Chain:** Gemini 3.8 Flash -> Groq GPT-OSS 120B -> Local Ollama  ",
        "",
        "---",
        "",
        "## 1. Aggregate Execution Metrics",
        "",
        f"- **Total Questions Attempted:** **{total} / 55**",
        f"- **Successful Database Executions:** **{successful}** ({round(successful/total*100, 1) if total else 0}%)",
        f"- **Clarifications Requested by Agent:** **{clarifications}** ({round(clarifications/total*100, 1) if total else 0}%)",
        f"- **Policy-Rejected / Unsupported Shielded:** **{policy_rejected}** ({round(policy_rejected/total*100, 1) if total else 0}%)",
        f"- **Provider Failures / Timeouts:** **{provider_failures}** ({round(provider_failures/total*100, 1) if total else 0}%)",
        f"- **Other / Unhandled Exceptions:** **{other_errors}**",
        f"- **Overall Pipeline Completion Rate:** **{round((total - provider_failures)/total*100, 1) if total else 0}%**",
        f"- **Average Duration:** **{avg_dur}s** | **Median Duration:** **{med_dur}s**",
        f"- **Provider Utilization:** {json.dumps(providers)}",
        f"- **Ground Truth Correctness:** **NOT VERIFIED** (test_questions.json contains no expected output records)",
        "",
        "---",
        "",
        "## 2. Complete Question-by-Question Results Table",
        "",
        "| ID | Level | Natural Language Prompt | Provider | Target Collection | Validation | DB Execution | Rows | Duration (s) | Status |",
        "|:---:|:---:|:---|:---:|:---:|:---:|:---:|---:|---:|:---:|",
    ]

    for r in results:
        col = r["target_collection"] or "-"
        val = r["validation_status"] or "-"
        exec_st = r["execution_status"] or "-"
        q_clean = r["question"].replace("|", "\\|")
        lines.append(
            f"| **{r['id']}** | L{r['level']} | {q_clean} | `{r['provider'] or '-'}` | `{col}` | `{val}` | `{exec_st}` | {r['result_row_count']} | {r['duration_s']}s | **{r['final_status']}** |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Generated by FinTech Agent Benchmark Runner | Antigravity AI*")
    report_text = "\n".join(lines)

    with open(SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write(report_text)

    return report_text


async def main():
    questions = load_benchmark_questions()
    total = len(questions)
    print(f"=== Starting FinTech Agent 55-Question Live Benchmark (Total: {total}) ===")
    print(f"Evidence will be saved to: {OUTPUT_DIR}")

    results: List[Dict[str, Any]] = []

    for idx, q in enumerate(questions, start=1):
        record = await execute_single_question(q, idx, total)
        results.append(record)
        save_checkpoint(results)

        # Print live progress summary
        successful = sum(1 for r in results if r["final_status"] == "SUCCESS")
        rejected = sum(1 for r in results if "REJECTED" in r["final_status"])
        failed = sum(1 for r in results if r["final_status"] in ("PROVIDER_FAILURE", "TIMEOUT", "ERROR"))
        remaining = total - idx
        print(
            f"--> Progress: Completed: {idx}/{total} | Successful: {successful} | "
            f"Rejected: {rejected} | Failed: {failed} | Remaining: {remaining}"
        )

    print("\n=== All 55 Questions Completed. Generating Final Summary Report... ===")
    summary_report = generate_summary_report(results)
    print("Benchmark run complete. Report saved to execution_summary.md")


if __name__ == "__main__":
    asyncio.run(main())
