"""
FinTech Agent — Node 6: Read-Only Query Executor (Phase 6 Implementation)
Executes deterministically validated MongoDB aggregation pipelines under strict
read-only sandboxing, server-side timeout enforcement, and result-volume bounds.

Architectural Guarantees:
  1. Read-Only Execution: Only read operations are permitted. Any write or mutating
     stages ($out, $merge) were eliminated by Node 5 and are blocked by the database layer.
  2. Central Fail-Closed Gate: When PHASE6_LIVE_EXECUTION_ENABLED=False (default),
     all live execution against the original banking database (fintech_agent_db) is
     strictly prevented.
  3. Controlled Test Execution: Isolated test fixtures or mock databases may be executed
     only when explicitly provided via state['test_db'] or state['mock_db'].
  4. Server-Side Timeout: Enforces maxTimeMS=settings.QUERY_TIMEOUT_MS (15,000 ms).
  5. Capped Results: Results are strictly capped at settings.RESULT_DOC_LIMIT (1,000).
  6. Memory & Payload Bounds: Result payload serialized size is bounded to settings.MAX_RESULT_BYTES (5MB).
  7. Error Shielding: Database errors (timeouts, network, auth) are shielded so that raw
     connection strings, credentials, or internal stack traces are never leaked.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional, Tuple
import pymongo
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    ExecutionTimeout,
    NetworkTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.db.mongo_client import mongo_manager

CANONICAL_COLLECTIONS = {
    "accounts",
    "branches",
    "cards",
    "customers",
    "employees",
    "fraud_alerts",
    "investments",
    "kyc_documents",
    "loans",
    "merchants",
    "support_tickets",
    "transactions",
}


def check_live_execution_readiness() -> Tuple[bool, str]:
    """Evaluates strict preconditions required before live database execution can occur.
    Guarantees that PHASE6_LIVE_EXECUTION_ENABLED=True alone CANNOT authorize live execution.
    """
    if not getattr(settings, "PHASE6_LIVE_EXECUTION_ENABLED", False):
        return False, "Live database execution is gated (PHASE6_LIVE_EXECUTION_ENABLED=False)."

    # 1. Server-side auth must be enabled in settings
    if not getattr(settings, "MONGO_AUTH_ENABLED", False):
        return False, "Live execution prohibited: MONGO_AUTH_ENABLED is False (unauthenticated MongoDB)."

    # 2. Development unauthenticated fallback must be explicitly disabled
    if getattr(settings, "ALLOW_UNAUTHENTICATED_DEV", True):
        return False, "Live execution prohibited: ALLOW_UNAUTHENTICATED_DEV is True."

    # 3. Dedicated banking read-only credentials must be non-empty
    banking_user = getattr(settings, "MONGO_READONLY_USERNAME", None)
    banking_pass = getattr(settings, "MONGO_READONLY_PASSWORD", None)
    if not banking_user or not banking_pass:
        return False, "Live execution prohibited: Missing dedicated banking read-only credentials."

    # 4. Dedicated metadata credentials must be non-empty
    meta_user = getattr(settings, "MONGO_METADATA_USERNAME", None)
    meta_pass = getattr(settings, "MONGO_METADATA_PASSWORD", None)
    if not meta_user or not meta_pass:
        return False, "Live execution prohibited: Missing dedicated metadata credentials."

    # 5. Least-privilege credential separation
    if banking_user == meta_user or banking_pass == meta_pass:
        return False, "Live execution prohibited: Banking and metadata credentials must be separate and distinct."

    # 6. Explicit verified native authorization status
    # An environment variable alone is NOT treated as proof that MongoDB authorization is active
    native_auth_verified = getattr(settings, "MONGO_NATIVE_AUTH_VERIFIED", False)
    if not native_auth_verified:
        return False, "Live execution prohibited: Native MongoDB server-side authorization status is unverified."

    return True, "Authorized"


def _serialize_for_size_check(data: Any) -> bytes:
    """Serializes objects to UTF-8 bytes to check byte limits."""
    return json.dumps(data, default=str).encode("utf-8")


async def query_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 6: Executes validated read-only aggregation pipelines.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with raw_results, execution_time_ms, result_row_count,
        execution_error, execution_status, result_truncated, and updated trace.
    """
    request_id = state.get("request_id", "unknown")
    trace: List[Dict[str, Any]] = list(state.get("trace") or [])

    guardrail_status = state.get("guardrail_status")
    final_status = state.get("final_status")
    validation_status = state.get("validation_status")
    is_pipeline_valid = state.get("is_pipeline_valid", False)
    target_collection = state.get("target_collection") or state.get("selected_collection")
    pipeline = state.get("approved_pipeline") or state.get("generated_pipeline")

    # -------------------------------------------------------------------------
    # 1. Precondition Verification (Strict Fail-Safe Skip)
    # -------------------------------------------------------------------------
    if state.get("request_mode") == "SCHEDULE_ONLY":
        logger.info(f"[{request_id}] Node 6 skipping: SCHEDULE_ONLY request does not execute database query immediately.")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": "Skipped: SCHEDULE_ONLY request does not execute database query immediately.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": 0,
            "result_row_count": 0,
            "execution_error": None,
            "execution_status": "SKIPPED",
            "result_truncated": False,
            "trace": trace,
        }

    if guardrail_status == "rejected" or final_status == "rejected":
        logger.info(f"[{request_id}] Node 6 skipping: request was rejected by input guardrail.")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": "Skipped: request was rejected by guardrail.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": None,
            "result_row_count": None,
            "execution_error": None,
            "execution_status": "SKIPPED",
            "result_truncated": False,
            "trace": trace,
        }

    if validation_status == "UNSUPPORTED":
        logger.info(f"[{request_id}] Node 6 skipping: query requests unsupported banking concepts.")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": "Skipped: query requests unsupported banking concepts.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": None,
            "result_row_count": None,
            "execution_error": None,
            "execution_status": "UNSUPPORTED",
            "result_truncated": False,
            "trace": trace,
        }

    if not is_pipeline_valid or validation_status != "VALID":
        logger.warning(f"[{request_id}] Node 6 skipping: pipeline failed validation (status='{validation_status}').")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": f"Skipped: pipeline validation status is '{validation_status}'.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": None,
            "result_row_count": None,
            "execution_error": "Pipeline did not pass validation.",
            "execution_status": "VALIDATION_FAILED",
            "result_truncated": False,
            "trace": trace,
        }

    if not target_collection or target_collection not in CANONICAL_COLLECTIONS:
        logger.warning(f"[{request_id}] Node 6 skipping: invalid target collection '{target_collection}'.")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": f"Skipped: unauthorized target collection '{target_collection}'.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": None,
            "result_row_count": None,
            "execution_error": f"Unauthorized target collection '{target_collection}'.",
            "execution_status": "VALIDATION_FAILED",
            "result_truncated": False,
            "trace": trace,
        }

    if not pipeline or not isinstance(pipeline, list):
        logger.warning(f"[{request_id}] Node 6 skipping: empty or invalid pipeline specification.")
        trace.append({
            "node": "query_executor",
            "status": "skipped",
            "detail": "Skipped: empty pipeline specification.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": None,
            "result_row_count": None,
            "execution_error": "Empty pipeline specification.",
            "execution_status": "VALIDATION_FAILED",
            "result_truncated": False,
            "trace": trace,
        }

    # -------------------------------------------------------------------------
    # 2. Central Fail-Closed Execution Gate & At-Most-Once API Safeguard
    # -------------------------------------------------------------------------
    prior_attempts = state.get("all_attempts") or []
    if state.get("is_api_request") is True and len(prior_attempts) >= 1:
        logger.warning(f"[{request_id}] Node 6 blocked repeat query execution attempt for API chat request.")
        trace.append({
            "node": "query_executor",
            "status": "execution_error",
            "detail": "Duplicate execution prevented: validated query may execute at most once per chat request.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": 0,
            "result_row_count": 0,
            "execution_error": "Duplicate query execution prevented for single chat request.",
            "execution_status": "EXECUTION_ERROR",
            "result_truncated": False,
            "trace": trace,
        }

    test_db = state.get("test_db") or state.get("mock_db")

    # Defense-in-depth: untrusted external/API requests are strictly prohibited from injecting test_db or mock_db
    if test_db is not None and (state.get("is_api_request") is True or state.get("is_untrusted") is True):
        logger.warning(f"[{request_id}] Node 6 blocked untrusted test_db/mock_db injection attempt.")
        trace.append({
            "node": "query_executor",
            "status": "gate_blocked",
            "detail": "Blocked untrusted test_db injection attempt.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": 0,
            "result_row_count": 0,
            "execution_error": "Untrusted test_db or mock_db injection detected. Test databases are not permitted from API requests.",
            "execution_status": "GATE_BLOCKED",
            "result_truncated": False,
            "trace": trace,
        }

    # If no isolated test database is provided, evaluate strict live execution authorization
    if test_db is None:
        is_ready, reason = check_live_execution_readiness()
        if not is_ready:
            logger.info(f"[{request_id}] Node 6 execution gated: {reason}")
            trace.append({
                "node": "query_executor",
                "status": "gate_blocked",
                "detail": f"Execution gated: {reason}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "raw_results": None,
                "execution_time_ms": 0,
                "result_row_count": 0,
                "execution_error": reason,
                "execution_status": "GATE_BLOCKED",
                "result_truncated": False,
                "trace": trace,
            }
        # Live execution path (only reachable if ALL live readiness checks pass)
        db = mongo_manager.get_banking_db(enforce_proxy=True)
    else:
        # Isolated test database path
        db = test_db
        db_name = getattr(db, "name", "test_database")
        banking_db_name = getattr(settings, "MONGO_BANKING_DB", "fintech_agent_db")
        # Enforce that test_db cannot target the production banking DB if live gate is disabled
        if db_name == banking_db_name and not getattr(settings, "PHASE6_LIVE_EXECUTION_ENABLED", False):
            logger.error(f"[{request_id}] Node 6 blocked attempt to execute against '{db_name}' while live gate disabled.")
            trace.append({
                "node": "query_executor",
                "status": "gate_blocked",
                "detail": f"Blocked attempt to target protected database '{db_name}'.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "raw_results": None,
                "execution_time_ms": 0,
                "result_row_count": 0,
                "execution_error": f"Targeting database '{db_name}' is strictly prohibited while live execution gate is disabled.",
                "execution_status": "GATE_BLOCKED",
                "result_truncated": False,
                "trace": trace,
            }

    # -------------------------------------------------------------------------
    # 3. Read-Only Execution with Incremental Timeout & Volume Capping
    # -------------------------------------------------------------------------
    start_time = time.perf_counter()
    timeout_ms = settings.QUERY_TIMEOUT_MS
    doc_limit = settings.RESULT_DOC_LIMIT
    max_bytes = settings.MAX_RESULT_BYTES

    try:
        col = db[target_collection]

        # Execute aggregation with server-side maxTimeMS and allowDiskUse=False
        cursor = col.aggregate(
            pipeline,
            maxTimeMS=timeout_ms,
            allowDiskUse=False,
        )

        # Incremental materialization with strict byte and document bounds
        docs: List[Dict[str, Any]] = []
        is_oversized = False
        current_bytes = 2  # represents '[]' in UTF-8
        cursor_had_more = False

        for doc in cursor:
            # 1. Check document limit (1,000)
            if len(docs) >= doc_limit:
                cursor_had_more = True
                break

            # 2. Incremental byte-budget check before adding doc
            doc_serialized = json.dumps(doc, default=str).encode("utf-8")
            doc_len = len(doc_serialized)
            projected_bytes = (doc_len + 2) if not docs else (current_bytes + doc_len + 2)

            if projected_bytes > max_bytes:
                # Adding this document would exceed the remaining budget!
                is_oversized = True
                logger.warning(
                    f"[{request_id}] Node 6: Adding document ({doc_len} bytes) would exceed MAX_RESULT_BYTES "
                    f"({max_bytes} bytes). Projected: {projected_bytes} bytes after {len(docs)} docs."
                )
                break

            docs.append(doc)
            current_bytes = projected_bytes

        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))

        # Handle oversized payload: abort immediately, return no partial result as complete
        if is_oversized:
            trace.append({
                "node": "query_executor",
                "status": "result_oversized",
                "detail": f"Result size exceeded maximum {max_bytes} bytes during iteration after {len(docs)} documents.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "raw_results": None,
                "execution_time_ms": elapsed_ms,
                "result_row_count": 0,
                "result_byte_count": current_bytes,
                "execution_error": f"Result payload exceeded maximum allowed limit ({max_bytes} bytes) during materialization.",
                "execution_status": "RESULT_OVERSIZED",
                "result_truncated": True,
                "trace": trace,
            }

        # Honest limit determination:
        # If len(docs) == doc_limit (or cursor_had_more is True), the configured limit was reached.
        # The total matching count is unknown and unverified without an explicit count.
        is_capped = (len(docs) == doc_limit) or cursor_had_more
        exec_status = "SUCCESS_LIMITED" if is_capped else "SUCCESS"

        logger.info(
            f"[{request_id}] Node 6 completed successfully: col='{target_collection}', "
            f"rows={len(docs)}, elapsed={elapsed_ms}ms, capped={is_capped}, bytes={current_bytes}"
        )
        trace.append({
            "node": "query_executor",
            "status": "executed",
            "detail": f"Executed read-only aggregation: {len(docs)} rows in {elapsed_ms}ms (capped={is_capped}).",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "raw_results": docs,
            "execution_time_ms": elapsed_ms,
            "result_row_count": len(docs),
            "result_byte_count": current_bytes,
            "execution_error": None,
            "execution_status": exec_status,
            "result_truncated": is_capped,
            "trace": trace,
        }

    except (ExecutionTimeout, NetworkTimeout) as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(f"[{request_id}] Node 6 query timed out after {elapsed_ms}ms: {exc}")
        trace.append({
            "node": "query_executor",
            "status": "timeout",
            "detail": f"Query execution timed out after {timeout_ms}ms.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": elapsed_ms,
            "result_row_count": 0,
            "execution_error": f"Query execution timed out (maximum {timeout_ms}ms exceeded).",
            "execution_status": "TIMEOUT",
            "result_truncated": False,
            "trace": trace,
        }

    except OperationFailure as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        code = getattr(exc, "code", None)
        logger.error(f"[{request_id}] Node 6 OperationFailure (code={code}): {exc}")

        # Check for authentication or authorization error (e.g., MongoDB code 13)
        if code in (13, 18) or "unauthorized" in str(exc).lower():
            status = "AUTH_ERROR"
            safe_err = "Database authorization error: operation not permitted under read-only credentials."
        else:
            status = "EXECUTION_ERROR"
            safe_err = "Database operation failure occurred during aggregation execution."

        trace.append({
            "node": "query_executor",
            "status": status.lower(),
            "detail": safe_err,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": elapsed_ms,
            "result_row_count": 0,
            "execution_error": safe_err,
            "execution_status": status,
            "result_truncated": False,
            "trace": trace,
        }

    except (ConnectionFailure, ServerSelectionTimeoutError, AutoReconnect) as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"[{request_id}] Node 6 database connection error after {elapsed_ms}ms: {exc}")
        trace.append({
            "node": "query_executor",
            "status": "connection_error",
            "detail": "Failed to connect to database host.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": elapsed_ms,
            "result_row_count": 0,
            "execution_error": "Database connection error: unable to establish connection with database host.",
            "execution_status": "CONNECTION_ERROR",
            "result_truncated": False,
            "trace": trace,
        }

    except PyMongoError as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"[{request_id}] Node 6 general PyMongoError: {exc}")
        trace.append({
            "node": "query_executor",
            "status": "execution_error",
            "detail": "General database error occurred during aggregation execution.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": elapsed_ms,
            "result_row_count": 0,
            "execution_error": "General database error occurred during aggregation execution.",
            "execution_status": "EXECUTION_ERROR",
            "result_truncated": False,
            "trace": trace,
        }

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"[{request_id}] Node 6 unexpected execution error: {exc}")
        trace.append({
            "node": "query_executor",
            "status": "execution_error",
            "detail": "Unexpected system error during query execution.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "raw_results": None,
            "execution_time_ms": elapsed_ms,
            "result_row_count": 0,
            "execution_error": "Unexpected system error during query execution.",
            "execution_status": "EXECUTION_ERROR",
            "result_truncated": False,
            "trace": trace,
        }


async def query_executor_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 6 stub: Query execution placeholder."""
    trace: List[Dict[str, Any]] = list(state.get("trace") or [])
    trace.append({
        "node": "query_executor",
        "status": "stub",
        "detail": "Phase 6 not yet implemented — query execution skipped. No DB access.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "raw_results": None,
        "execution_time_ms": None,
        "result_row_count": None,
        "execution_error": None,
        "result_truncated": False,
        "trace": trace,
    }
