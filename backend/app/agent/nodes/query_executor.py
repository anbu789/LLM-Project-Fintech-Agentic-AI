"""
FinTech Agent — Node 6: Read-only Query Executor — STUB (Phase 6 implementation)
Executes validated MongoDB aggregation pipelines against fintech_agent_db.

PHASE 4 STATUS: STUB — performs NO database queries whatsoever.
This stub does not connect to MongoDB, does not read banking data, and returns
no results.  Full implementation planned for Phase 6.
"""

from datetime import datetime, timezone
from typing import Any, Dict


async def query_executor_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 6 stub: Query execution placeholder.

    In Phase 6 this node will:
    - Execute validated pipelines against fintech_agent_db using the read-only
      MongoDB client (pymongo, maxTimeMS enforcement, result capping).
    - Populate raw_results, execution_time_ms, result_row_count.
    - Respect dry_run flag for schedule validation.

    THIS STUB DOES NOT ACCESS MONGODB.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with stub raw_results.
    """
    trace: list = list(state.get("trace") or [])
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
