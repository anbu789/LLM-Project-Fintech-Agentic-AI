"""
FinTech Agent — Node 8: Response Composer (Phase 5, Full Implementation)
Assembles the final user-facing response from AgentState.

Phase 5 responsibilities:
  - Formats validated MongoDB aggregation pipelines and plain-language explanations.
  - Explains validation errors when candidate pipelines fail MQL security policy.
  - Highlights unsupported business concepts (e.g. loans.overdue_amount, days_past_due).
  - Explicitly states that database query execution has NOT occurred (Phase 6 scope).
  - Preserves legacy Phase 2/4 response contracts for greetings, clarifications,
    out-of-scope guidance, and mock terminology explanations.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict

from backend.app.config import settings
from backend.app.core.logging import logger, make_ascii_safe
from backend.app.services.llm_service import llm_service

# ---------------------------------------------------------------------------
# Phase 5 & Phase 6 Response Templates
# ---------------------------------------------------------------------------

_VALIDATED_PIPELINE_TEMPLATE = """\
✅ **Query Understood & Validated** (Phase 5 — Read-only query execution plan validated)

**Target Collection:** `{target_collection}`  
**Explanation:** {pipeline_explanation}

```json
{formatted_pipeline}
```

**MQL Security Validation Summary:**
- Validation Status: `{validation_status}`
- Stage Count: {stage_count} ({stages_used})
- Policy: Deterministically verified against canonical schema. Zero unsafe operators.

> 🔒 **Execution Gate Status:** Database query execution has not occurred. Live database execution is currently gated pending administrative authorization.
"""

_EXECUTION_SUCCESS_WITH_DATA_TEMPLATE = """\
✅ **Query Executed Successfully** (Database query executed successfully)

**Target Collection:** `{target_collection}`
**Execution Metrics:** {row_count} records returned in {execution_time_ms} ms.
**Explanation:** {pipeline_explanation}

**Results Preview:**
```json
{formatted_results}
```
"""

_EXECUTION_SUCCESS_EMPTY_TEMPLATE = """\
✅ **Query Executed Successfully** (Database query executed successfully)

**Target Collection:** `{target_collection}`
**Execution Metrics:** 0 records returned in {execution_time_ms} ms.
**Explanation:** {pipeline_explanation}

> ℹ️ **Result:** The query completed successfully against the database, but no records matched the specified criteria.
"""

_EXECUTION_SUCCESS_LIMITED_TEMPLATE = """\
⚠️ **Query Executed (Results Capped)** (Read-only query execution)

**Target Collection:** `{target_collection}`
**Execution Metrics:** {row_count} records returned in {execution_time_ms} ms (capped at limit of {result_limit}).
**Explanation:** {pipeline_explanation}

**Results Preview:**
```json
{formatted_results}
```

> ⚠️ **Notice:** Result set reached the maximum allowed limit of {result_limit} documents and was truncated.
"""

_EXECUTION_ERROR_TEMPLATE = """\
❌ **Query Execution Failed** (Read-only query execution)

**Target Collection:** `{target_collection}`
**Status:** `{verification_status}`
**Detail:** {error_detail}

The query passed deterministic validation, but an error occurred during execution against the database.
"""

_INVALID_PIPELINE_TEMPLATE = """\
❌ **Query Validation Failed** (Phase 5)

The generated query plan for collection `{target_collection}` could not pass deterministic security validation.

**Validation Errors:**
{formatted_errors}

Please refine your query or ensure that only canonical banking fields and relationships are requested.
"""

_UNSUPPORTED_CONCEPT_TEMPLATE = """\
[UNSUPPORTED] **Unsupported Banking Concept**

{unsupported_explanations}

**Canonical Schema Guidance:**
- `loans.outstanding_amount` exists and represents remaining principal balance.
- `loans.overdue_amount` and `loans.days_past_due` do NOT exist in the banking dataset.
- In commercial banking, total remaining principal on a defaulted loan is fundamentally distinct from overdue installments, interest arrears, or late penalties.
- To analyze defaulted loans, please submit a separate query such as:
  - "Show defaulted loans"
  - "Calculate total outstanding principal of defaulted loans"
"""

_QUERY_AND_SCHEDULE_TEMPLATE = """\
✅ **Query Understood & Validated (Schedule Request Pending)** (Phase 5)

**Target Collection:** `{target_collection}`
**Explanation:** {pipeline_explanation}

```json
{formatted_pipeline}
```

> ℹ️ **Scheduling Status:** Query pipeline validated. Recurring scheduling and job registration are planned for a future phase after query execution (Phase 6) is established.
"""

_SCHEDULE_PREVIEW_TEMPLATE = """\
📋 **Scheduled Report Preview** (Phase 7 — Awaiting Explicit Approval)

**Report Name:** {report_name}
**Target Collection:** `{target_collection}`
**Recurrence:** {recurrence_expression} (`{cron_expression}`)
**Timezone:** `{timezone_name}`
**Query Intent:** {pipeline_explanation}

**Upcoming Run Times (Next 3):**
{formatted_run_times}

**Aggregation Pipeline:**
```json
{formatted_pipeline}
```

{dry_run_section}

---
⚠️ **Explicit Approval Required:**
- **Preview ID:** `{preview_id}`
- **Expires At:** `{expires_at}`
- **Status:** `PENDING_APPROVAL` (No automated jobs are scheduled until approved)

👉 *To activate this automated schedule, click **Approve Schedule** or submit:*
```
approve {preview_id}
```
"""

_SCHEDULE_ACTIVATED_TEMPLATE = """\
✅ **Scheduled Report Activated** (Phase 7)

**Job ID:** `{job_id}`
**Report Name:** {report_name}
**Target Collection:** `{target_collection}`
**Recurrence:** {recurrence_expression} (`{cron_expression}`)
**Timezone:** `{timezone_name}`
**Status:** `ACTIVE`

**Next Scheduled Run:** `{next_run_at}`

Your scheduled report is now registered in `agent_metadata_db.scheduled_jobs` and will execute automatically at the configured intervals.
"""

_SCHEDULE_ONLY_TEMPLATE = """\
✅ **Schedule Request Understood** (Phase 5/7)

I've identified your request as: **set up a recurring scheduled report**.

> {query_description}

**Current system status:** Recurrence parsed and awaiting pipeline generation or clarification.
"""

_CLARIFICATION_TEMPLATE = """\
🤔 **Clarification Needed**

{clarification_question}

Please provide more details so I can generate the right banking data query for you. For example:
- "Show me active loans above ₹10 lakhs in the last 30 days"
- "List customers with high credit risk score in Mumbai branch"
- "Total outstanding amount by loan product category"
"""

_OUT_OF_SCOPE_TEMPLATE = """\
ℹ️ **Outside System Scope**

{intent_reason}

**FinTech Agent** is designed for banking data analytics queries. Here are some things I can help with:
- Loan portfolio analysis (outstanding amounts, delinquency rates, NPA classification)
- Customer risk profiling and credit score distributions
- Transaction monitoring and AML/fraud alert summaries
- Branch performance comparisons
- KYC compliance status across customer segments

Please try a banking data query to get started.
"""

_REJECTED_TEMPLATE = """\
🚫 **Request Blocked**

{rejection_reason}

For assistance with banking data queries, please submit a valid request such as:
- "Show active loans above ₹5 lakhs"
- "How many customers are flagged for AML review?"
"""

_UNKNOWN_TEMPLATE = """\
⚠️ **Processing Error**

An unexpected error occurred while processing your request (status: {final_status}). Please try again or contact support if the problem persists.
"""


# ---------------------------------------------------------------------------
# Node 8 — Response Composer
# ---------------------------------------------------------------------------

async def response_composer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 8: Assembles final user-facing response from AgentState.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with graph_response and formatted_response populated.
    """
    request_id = state.get("request_id", "unknown")
    trace: list = list(state.get("trace") or [])

    guardrail_status = state.get("guardrail_status", "")
    final_status = state.get("final_status", "")
    request_mode = state.get("request_mode", "")
    intent_reason = state.get("intent_reason", "")
    query_description = state.get("query_description") or state.get("natural_language_query", "")
    clarification_question = state.get("clarification_question", "")
    rejection_reason = state.get("rejection_reason", "")

    # Phase 5 & 6 pipeline state
    validation_status = state.get("validation_status", "")
    validation_errors = state.get("validation_errors") or []
    generated_pipeline = state.get("generated_pipeline")
    target_collection = state.get("target_collection") or "unknown"
    pipeline_explanation = state.get("pipeline_explanation") or "Read-only aggregation pipeline."
    query_plan_summary = state.get("query_plan_summary") or {}
    query_parameters = state.get("query_parameters") or {}
    unsupported_concepts = query_parameters.get("unsupported_concepts") or []

    # Phase 6 execution & verification state
    verification_status = state.get("verification_status")
    verified_results = state.get("verified_results")
    raw_results = state.get("raw_results")
    execution_time_ms = state.get("execution_time_ms") or 0
    execution_error = state.get("execution_error") or ""
    results_to_show = verified_results if verified_results is not None else raw_results

    # Phase 7 scheduling state
    schedule_preview = state.get("schedule_preview")
    schedule_approved = state.get("schedule_approved", False)
    schedule_job_id = state.get("schedule_job_id")

    # Mock provider backward-compatibility preamble (e.g. definitions of NPA, KYC in tests)
    mock_preamble = ""
    if (settings.LLM_PROVIDER or "").lower().strip() == "mock" and guardrail_status != "rejected":
        try:
            raw_mock = await llm_service.get_provider().generate_response(
                user_message=state.get("natural_language_query", ""),
                conversation_history=state.get("conversation_history") or [],
            )
            if any(term in raw_mock for term in ("Non-Performing Asset", "Know Your Customer", "fraud alert")):
                mock_preamble = f"{raw_mock}\n\n"
        except Exception:
            pass

    # -- Case 1: Guardrail rejected
    if guardrail_status == "rejected" or final_status == "rejected":
        msg = _REJECTED_TEMPLATE.format(
            rejection_reason=rejection_reason or "Request did not pass safety checks."
        )

    # -- Case 2: Unsupported Concepts
    elif validation_status == "UNSUPPORTED" or (unsupported_concepts and not generated_pipeline):
        warn_lines = "\n".join(f"- Requested concept '{c}' is not present in schema." for c in unsupported_concepts)
        msg = mock_preamble + _UNSUPPORTED_CONCEPT_TEMPLATE.format(
            unsupported_explanations=warn_lines or "- Requested banking concepts are unsupported by canonical schema."
        )

    # -- Case 3: Pipeline Failed Validation
    elif request_mode in ("QUERY_ONLY", "QUERY_AND_SCHEDULE") and validation_status == "INVALID":
        err_lines = "\n".join(f"- {e}" for e in validation_errors) or "- General validation policy rejection."
        msg = mock_preamble + _INVALID_PIPELINE_TEMPLATE.format(
            target_collection=target_collection,
            formatted_errors=err_lines,
        )

    # -- Case 4: Phase 6 Executed with Data
    elif verification_status == "SUCCESS_WITH_DATA":
        preview = results_to_show[:10] if results_to_show else []
        formatted_results = json.dumps(preview, indent=2, default=str)
        msg = mock_preamble + _EXECUTION_SUCCESS_WITH_DATA_TEMPLATE.format(
            target_collection=target_collection,
            row_count=len(results_to_show or []),
            execution_time_ms=execution_time_ms,
            pipeline_explanation=pipeline_explanation,
            formatted_results=formatted_results,
        )

    # -- Case 5: Phase 6 Executed with Empty Results
    elif verification_status == "SUCCESS_EMPTY":
        msg = mock_preamble + _EXECUTION_SUCCESS_EMPTY_TEMPLATE.format(
            target_collection=target_collection,
            execution_time_ms=execution_time_ms,
            pipeline_explanation=pipeline_explanation,
        )

    # -- Case 6: Phase 6 Executed with Capped Results
    elif verification_status == "SUCCESS_LIMITED":
        preview = results_to_show[:10] if results_to_show else []
        formatted_results = json.dumps(preview, indent=2, default=str)
        msg = mock_preamble + _EXECUTION_SUCCESS_LIMITED_TEMPLATE.format(
            target_collection=target_collection,
            row_count=len(results_to_show or []),
            execution_time_ms=execution_time_ms,
            result_limit=settings.RESULT_DOC_LIMIT,
            pipeline_explanation=pipeline_explanation,
            formatted_results=formatted_results,
        )

    # -- Case 7: Phase 6 Execution Errors (Timeout, Connection, Auth, Oversized)
    elif verification_status in ("TIMEOUT", "CONNECTION_ERROR", "AUTH_ERROR", "RESULT_OVERSIZED", "EXECUTION_ERROR"):
        msg = mock_preamble + _EXECUTION_ERROR_TEMPLATE.format(
            target_collection=target_collection,
            verification_status=verification_status,
            error_detail=execution_error or state.get("interpretation_summary") or "Query execution failure.",
        )

    # -- Case 7.5: Phase 7 Schedule Activated
    elif schedule_approved and schedule_job_id:
        msg = mock_preamble + _SCHEDULE_ACTIVATED_TEMPLATE.format(
            job_id=schedule_job_id,
            report_name=state.get("report_name") or f"Recurring {target_collection.capitalize()} Report",
            target_collection=target_collection,
            recurrence_expression=state.get("recurrence_expression") or "Custom",
            cron_expression=state.get("cron_expression") or "N/A",
            timezone_name=state.get("timezone") or settings.SCHEDULER_TIMEZONE,
            next_run_at=state.get("next_run_at") or "Scheduled per cron trigger",
        )

    # -- Case 7.6: Phase 7 Schedule Preview Generated
    elif schedule_preview and isinstance(schedule_preview, dict) and schedule_preview.get("preview_id"):
        spec = schedule_preview.get("schedule_spec") or {}
        recurrence_expr = spec.get("recurrence_expression") or "Custom"
        cron_expr = spec.get("cron_expression") or "N/A"
        tz_name = spec.get("timezone") or settings.SCHEDULER_TIMEZONE
        preview_runs = schedule_preview.get("next_run_times") or state.get("next_run_times") or []
        formatted_runs = "\n".join(f"  {idx+1}. {r}" for idx, r in enumerate(preview_runs)) if preview_runs else "  - Not calculated"

        preview_pipeline = schedule_preview.get("approved_pipeline") or generated_pipeline or []
        formatted_pipe = json.dumps(preview_pipeline, indent=2, default=str)

        dry_results = schedule_preview.get("dry_run_results")
        dry_limit = getattr(settings, "PHASE7_DRY_RUN_RESULT_LIMIT", 10)
        if dry_results:
            sample_json = json.dumps(dry_results[:dry_limit], indent=2, default=str)
            dry_section = f"**Dry-Run Results Preview (First {len(dry_results[:dry_limit])} records):**\n```json\n{sample_json}\n```"
        else:
            dry_section = "> 🔒 **Dry-Run Notice:** Live database execution preview is gated (`PHASE6_LIVE_EXECUTION_ENABLED=False`). The pipeline has been deterministically verified against canonical schema."

        msg = mock_preamble + _SCHEDULE_PREVIEW_TEMPLATE.format(
            report_name=schedule_preview.get("report_name", "Recurring Banking Report"),
            target_collection=schedule_preview.get("target_collection", target_collection),
            recurrence_expression=recurrence_expr,
            cron_expression=cron_expr,
            timezone_name=tz_name,
            pipeline_explanation=schedule_preview.get("pipeline_explanation", pipeline_explanation),
            formatted_run_times=formatted_runs,
            formatted_pipeline=formatted_pipe,
            dry_run_section=dry_section,
            preview_id=schedule_preview.get("preview_id", "N/A"),
            expires_at=schedule_preview.get("expires_at", "within 15 minutes"),
        )

    # -- Case 8: Schedule Only
    elif request_mode == "SCHEDULE_ONLY":
        msg = mock_preamble + _SCHEDULE_ONLY_TEMPLATE.format(
            query_description=query_description,
            intent_reason=intent_reason,
        )

    # -- Case 9: Clarification Required
    elif request_mode == "CLARIFICATION_REQUIRED":
        msg = mock_preamble + _CLARIFICATION_TEMPLATE.format(
            clarification_question=clarification_question
            or "Could you describe what banking data you need in more detail?",
        )

    # -- Case 10: Out of Scope
    elif request_mode == "OUT_OF_SCOPE":
        msg = mock_preamble + _OUT_OF_SCOPE_TEMPLATE.format(intent_reason=intent_reason)

    # -- Case 11: Validated Pipeline (Execution Gate Blocked or Dry Run)
    elif request_mode in ("QUERY_ONLY", "QUERY_AND_SCHEDULE") and validation_status == "VALID":
        formatted_json = json.dumps(generated_pipeline or [], indent=2)
        stages_used = ", ".join(query_plan_summary.get("stages_used", []))
        stage_count = query_plan_summary.get("stage_count", len(generated_pipeline or []))

        if request_mode == "QUERY_AND_SCHEDULE":
            msg = mock_preamble + _QUERY_AND_SCHEDULE_TEMPLATE.format(
                target_collection=target_collection,
                pipeline_explanation=pipeline_explanation,
                formatted_pipeline=formatted_json,
            )
        else:
            msg = mock_preamble + _VALIDATED_PIPELINE_TEMPLATE.format(
                target_collection=target_collection,
                pipeline_explanation=pipeline_explanation,
                formatted_pipeline=formatted_json,
                validation_status=validation_status,
                stage_count=stage_count,
                stages_used=stages_used or "read-only",
            )

    # -- Case 8: Fallback / Unexpected
    else:
        logger.warning(
            f"[{request_id}] Response composer received unexpected state: "
            f"request_mode='{request_mode}', validation_status='{validation_status}', "
            f"final_status='{final_status}'"
        )
        msg = _UNKNOWN_TEMPLATE.format(final_status=final_status or "unknown")

    logger.info(f"[{request_id}] Response composer composed message length={len(msg)}")
    trace.append({
        "node": "response_composer",
        "status": "composed",
        "detail": f"Composed response for mode='{request_mode}', validation='{validation_status}'",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "graph_response": msg.strip(),
        "formatted_response": msg.strip(),
        "final_response": msg.strip(),
        "final_status": final_status or "complete",
        "schedule_preview": schedule_preview,
        "preview_id": schedule_preview.get("preview_id") if isinstance(schedule_preview, dict) else state.get("preview_id"),
        "selected_provider": state.get("selected_provider") or state.get("llm_provider"),
        "llm_provider": state.get("selected_provider") or state.get("llm_provider"),
        "llm_model": state.get("llm_model"),
        "trace": trace,
    }
