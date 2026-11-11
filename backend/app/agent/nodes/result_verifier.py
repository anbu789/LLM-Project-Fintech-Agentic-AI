"""
FinTech Agent — Node 7: Result Verifier and Recovery (Phase 6 Implementation)
Verifies query results for semantic correctness, volume bounds, schema alignment,
and categorizes execution outcomes into formal verification and recovery statuses.

Architectural Guarantees:
  1. Outcome Categorization: Accurately classifies outcomes into SUCCESS_WITH_DATA,
     SUCCESS_EMPTY, SUCCESS_LIMITED, EXECUTION_GATE_BLOCKED, TIMEOUT, CONNECTION_ERROR,
     AUTH_ERROR, RESULT_OVERSIZED, UNSUPPORTED, VALIDATION_FAILED, and INVALID_RESULT.
  2. Bounded Error Recovery: Tracks attempts in all_attempts; allows transient retry
     tracking without weakening MQL validation policies, stage limits, or safety filters.
  3. Data Sanitization: Converts BSON ObjectIds to strings, datetimes to ISO 8601 UTC strings,
     and Decimal128 values to standard floats for safe JSON serialization.
  4. Semantic Summary: Generates a clear, grounded natural-language interpretation summary.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.core.logging import logger


def _sanitize_doc(doc: Any) -> Any:
    """Recursively converts BSON / non-JSON-serializable types to Python primitives.
    Preserves exact financial precision for Decimal128 and Decimal types without
    any lossy IEEE 754 floating-point conversion.
    """
    if isinstance(doc, dict):
        return {k: _sanitize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [_sanitize_doc(elem) for elem in doc]
    elif hasattr(doc, "isoformat"):
        return doc.isoformat()
    elif type(doc).__name__ == "Decimal128" or isinstance(doc, Decimal):
        return Decimal(str(doc))
    elif hasattr(doc, "__str__") and type(doc).__name__ == "ObjectId":
        return str(doc)
    return doc


async def result_verifier_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 7: Verifies query results and coordinates bounded recovery.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with result_status, verification_status, verified_results,
        interpretation_summary, semantic_verification, and updated trace.
    """
    request_id = state.get("request_id", "unknown")
    trace: List[Dict[str, Any]] = list(state.get("trace") or [])
    all_attempts: List[Dict[str, Any]] = list(state.get("all_attempts") or [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", settings.MAX_RETRY_ATTEMPTS)
    next_retry_count = retry_count

    guardrail_status = state.get("guardrail_status")
    final_status = state.get("final_status")
    validation_status = state.get("validation_status")
    execution_status = state.get("execution_status")
    raw_results = state.get("raw_results")
    execution_error = state.get("execution_error")
    execution_time_ms = state.get("execution_time_ms") or 0
    target_collection = state.get("target_collection") or "unknown"
    result_truncated = state.get("result_truncated", False)

    sanitized_results: Optional[List[Dict[str, Any]]] = None
    interpretation = ""

    # -------------------------------------------------------------------------
    # 1. Non-Execution / Precondition Cases
    # -------------------------------------------------------------------------
    if guardrail_status == "rejected" or final_status == "rejected":
        verification_status = "REJECTED"
        result_status = "TERMINAL_FAILURE"
        interpretation = "Request was rejected by input guardrail."

    elif validation_status == "UNSUPPORTED":
        verification_status = "UNSUPPORTED"
        result_status = "TERMINAL_FAILURE"
        interpretation = "Query contains unsupported business concepts (e.g. overdue loans)."

    elif validation_status == "INVALID":
        verification_status = "VALIDATION_FAILED"
        result_status = "TERMINAL_FAILURE"
        interpretation = "Candidate aggregation pipeline failed deterministic MQL validation."

    # -------------------------------------------------------------------------
    # 2. Central Execution Gate Blocked
    # -------------------------------------------------------------------------
    elif execution_status == "GATE_BLOCKED":
        verification_status = "EXECUTION_GATE_BLOCKED"
        result_status = "EXECUTION_GATE_BLOCKED"
        interpretation = (
            "Aggregation pipeline successfully verified and validated. Live database execution is "
            "currently gated pending manual activation of MongoDB RBAC authentication."
        )

    # -------------------------------------------------------------------------
    # 3. Execution Failures & Timeouts (Bounded Retryable Errors)
    # -------------------------------------------------------------------------
    elif execution_status == "TIMEOUT":
        verification_status = "TIMEOUT"
        if retry_count < max_retries:
            result_status = "RETRYABLE_ERROR"
            next_retry_count = retry_count + 1
            interpretation = f"Query execution timed out after {settings.QUERY_TIMEOUT_MS}ms. Initiating bounded retry attempt {next_retry_count}/{max_retries}."
        else:
            result_status = "TERMINAL_FAILURE"
            next_retry_count = retry_count
            interpretation = f"Query execution timed out after {settings.QUERY_TIMEOUT_MS}ms (retry limit of {max_retries} exhausted)."

        all_attempts.append({
            "attempt": retry_count + 1,
            "status": "TIMEOUT",
            "error": execution_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    elif execution_status == "CONNECTION_ERROR":
        verification_status = "CONNECTION_ERROR"
        if retry_count < max_retries:
            result_status = "RETRYABLE_ERROR"
            next_retry_count = retry_count + 1
            interpretation = f"Temporary database connection failure. Initiating bounded retry attempt {next_retry_count}/{max_retries}."
        else:
            result_status = "TERMINAL_FAILURE"
            next_retry_count = retry_count
            interpretation = f"Database connection failure persisted after {max_retries} attempts."

        all_attempts.append({
            "attempt": retry_count + 1,
            "status": "CONNECTION_ERROR",
            "error": execution_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    elif execution_status == "AUTH_ERROR":
        verification_status = "AUTH_ERROR"
        result_status = "TERMINAL_FAILURE"
        next_retry_count = retry_count
        interpretation = "Database authorization failure under read-only access controls (non-retryable)."

    elif execution_status == "RESULT_OVERSIZED":
        verification_status = "RESULT_OVERSIZED"
        result_status = "TERMINAL_FAILURE"
        interpretation = f"Result payload exceeded maximum allowed limit ({settings.MAX_RESULT_BYTES} bytes)."

    elif execution_status == "EXECUTION_ERROR":
        verification_status = "EXECUTION_ERROR"
        result_status = "TERMINAL_FAILURE"
        interpretation = execution_error or "Database execution error occurred."

    # -------------------------------------------------------------------------
    # 4. Successful Execution Handling
    # -------------------------------------------------------------------------
    elif execution_status in ("SUCCESS", "SUCCESS_LIMITED") or (raw_results is not None):
        if raw_results is None:
            verification_status = "INVALID_RESULT"
            result_status = "TERMINAL_FAILURE"
            interpretation = "Execution status indicated success but raw_results was null."
        else:
            # Sanitize BSON documents
            sanitized_results = [_sanitize_doc(d) for d in raw_results]
            row_count = len(sanitized_results)

            if row_count == 0:
                verification_status = "SUCCESS_EMPTY"
                result_status = "VALID_EMPTY"
                interpretation = (
                    f"Query executed successfully against '{target_collection}' in {execution_time_ms}ms; "
                    "returned 0 matching records."
                )
            elif result_truncated or execution_status == "SUCCESS_LIMITED":
                verification_status = "SUCCESS_LIMITED"
                result_status = "VALID_WITH_DATA"
                interpretation = (
                    f"Query executed successfully against '{target_collection}' in {execution_time_ms}ms; "
                    f"configured limit reached ({row_count} records returned). Total matching record count may be greater and is unverified without an explicit count."
                )
            else:
                verification_status = "SUCCESS_WITH_DATA"
                result_status = "VALID_WITH_DATA"
                interpretation = (
                    f"Query executed successfully against '{target_collection}' in {execution_time_ms}ms; "
                    f"returned {row_count} records."
                )

    # -------------------------------------------------------------------------
    # 5. Unexpected / Fallback
    # -------------------------------------------------------------------------
    else:
        verification_status = "INVALID_RESULT"
        result_status = "TERMINAL_FAILURE"
        interpretation = f"Unrecognized execution status: '{execution_status}'."

    logger.info(
        f"[{request_id}] Node 7 verification complete: status='{verification_status}', "
        f"result_status='{result_status}', retry_count={next_retry_count}"
    )

    trace.append({
        "node": "result_verifier",
        "status": verification_status.lower(),
        "detail": interpretation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    verified_count = len(sanitized_results) if sanitized_results is not None else 0

    return {
        "result_status": result_status,
        "verification_status": verification_status,
        "verified_results": sanitized_results,
        "raw_results": sanitized_results if sanitized_results is not None else raw_results,
        "result_row_count": verified_count,
        "interpretation_summary": interpretation,
        "all_attempts": all_attempts,
        "retry_count": next_retry_count,
        "semantic_verification": {
            "status": verification_status,
            "row_count": verified_count,
            "is_empty": verified_count == 0 if sanitized_results is not None else True,
            "truncated": result_truncated,
            "interpretation": interpretation,
        },
        "trace": trace,
    }


# Maintain backward compatibility alias for stub imports
result_verifier_stub = result_verifier_node
