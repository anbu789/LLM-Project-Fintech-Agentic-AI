"""
FinTech Agent — Node 9: Schedule Planner and Registrar (Phase 7 Implementation)
Parses recurrence patterns, validates IANA timezones, computes next run times using
real APScheduler triggers, prepares immutable schedule previews for explicit user approval,
and coordinates persistent job registration in agent_metadata_db.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from backend.app.agent.nodes.mql_policy_validator import MQLPolicyValidator
from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.schemas.schedule import SchedulePreview, ScheduleSpec
from backend.app.services.recurrence_parser import (
    calculate_next_run_times,
    parse_recurrence,
    validate_iana_timezone,
)
from backend.app.services.schedule_service import schedule_service


async def schedule_planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 9: Full schedule planning, recurrence parsing, and preview coordination.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with schedule_spec, schedule_preview, preview_id,
        next_run_times, schedule_approved, and updated trace.
    """
    request_id = state.get("request_id", "unknown")
    user_id = state.get("user_id") or state.get("owner_id") or "default_user"
    trace: List[Dict[str, Any]] = list(state.get("trace") or [])
    request_mode = state.get("request_mode", "QUERY_ONLY")
    query_text = state.get("natural_language_query", "")
    target_collection = state.get("target_collection") or state.get("selected_collection") or "customers"
    approved_pipeline = state.get("approved_pipeline") or state.get("generated_pipeline") or []
    pipeline_explanation = state.get("pipeline_explanation") or state.get("query_explanation") or "Automated recurring report."

    # 1. Non-scheduling requests pass through cleanly
    if request_mode not in ("SCHEDULE_ONLY", "QUERY_AND_SCHEDULE"):
        trace.append({
            "node": "schedule_planner",
            "status": "bypassed",
            "detail": f"Request mode is '{request_mode}'; recurring schedule planning skipped.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "schedule_approved": False,
            "schedule_job_id": None,
            "preview_id": None,
            "schedule_preview": None,
            "trace": trace,
        }

    # 2. Extract and parse recurrence specification
    temporal_spec = state.get("temporal_spec") or {}
    requested_tz = state.get("timezone") or temporal_spec.get("timezone") or settings.SCHEDULER_TIMEZONE
    try:
        valid_tz = validate_iana_timezone(requested_tz)
    except ValueError as e:
        logger.warning(f"[{request_id}] Node 9 invalid timezone: {e}")
        trace.append({
            "node": "schedule_planner",
            "status": "error",
            "detail": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "schedule_approved": False,
            "schedule_job_id": None,
            "preview_id": None,
            "schedule_preview": None,
            "clarification_question": str(e),
            "trace": trace,
        }

    # Attempt recurrence parsing
    recurrence_text = temporal_spec.get("recurrence_expression") or query_text
    try:
        schedule_spec = parse_recurrence(recurrence_text, timezone_name=valid_tz)
    except ValueError as e:
        logger.warning(f"[{request_id}] Node 9 recurrence parse error: {e}")
        trace.append({
            "node": "schedule_planner",
            "status": "clarification_required",
            "detail": f"Recurrence parsing requires clarification: {e}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "schedule_approved": False,
            "schedule_job_id": None,
            "preview_id": None,
            "schedule_preview": None,
            "clarification_question": f"Could you clarify the recurring schedule? {e}",
            "trace": trace,
        }

    # 3. Calculate next 3 run times using real APScheduler trigger
    next_run_times = calculate_next_run_times(schedule_spec, count=3)

    # 4. Handle dry run results for preview
    dry_run_results = None
    dry_run_status = state.get("verification_status") or "NOT_PERMITTED"
    raw_results = state.get("verified_results") or state.get("raw_results")

    if raw_results and request_mode == "SCHEDULE_ONLY":
        dry_run_limit = getattr(settings, "PHASE7_DRY_RUN_RESULT_LIMIT", 10)
        dry_run_results = raw_results[:dry_run_limit]
        dry_run_status = "SUCCESS_PREVIEW"

    # 5. Create immutable schedule preview for explicit user approval
    report_name = state.get("query_description") or f"Recurring {target_collection.capitalize()} Report"
    preview = schedule_service.create_preview(
        owner_id=user_id,
        report_name=report_name,
        natural_language_query=query_text,
        target_collection=target_collection,
        pipeline_explanation=pipeline_explanation,
        approved_pipeline=approved_pipeline,
        schedule_spec=schedule_spec,
        next_run_times=next_run_times,
        dry_run_status=dry_run_status,
        dry_run_results=dry_run_results,
        warning="Preview generated. Explicit approval is required to activate this schedule.",
    )

    trace.append({
        "node": "schedule_planner",
        "status": "preview_created",
        "detail": f"Generated schedule preview '{preview.preview_id}' ({schedule_spec.recurrence_expression}). Next run: {next_run_times[0] if next_run_times else 'N/A'}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "schedule_spec": schedule_spec.model_dump(),
        "schedule_preview": preview.model_dump(),
        "preview_id": preview.preview_id,
        "next_run_times": next_run_times,
        "schedule_approved": False,  # MUST remain False until explicit approval!
        "schedule_job_id": None,
        "trace": trace,
    }


async def schedule_planner_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Backward compatibility alias for tests targeting the stub."""
    return await schedule_planner_node(state)
