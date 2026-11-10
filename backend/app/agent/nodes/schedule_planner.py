"""
FinTech Agent — Node 9: Schedule Planner and Registrar — STUB (Future phase)
Registers validated pipelines as APScheduler recurring jobs.

PHASE 4 STATUS: STUB — performs NO scheduler registration and NO cron validation.
Full implementation is planned for a future phase after query execution is complete.
"""

from datetime import datetime, timezone
from typing import Any, Dict


async def schedule_planner_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 9 stub: Schedule planning and registration placeholder.

    In a future phase this node will:
    - Parse cron_expression and timezone from request context.
    - Register or update APScheduler jobs persisted in agent_metadata_db.
    - Populate schedule_job_id, schedule_approved, next_run_times.
    - Support delivery_spec (email/webhook) configuration.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with stub schedule fields.
    """
    trace: list = list(state.get("trace") or [])
    trace.append({
        "node": "schedule_planner",
        "status": "stub",
        "detail": "Future phase — schedule planning not yet implemented.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "schedule_approved": False,
        "schedule_job_id": None,
        "trace": trace,
    }
