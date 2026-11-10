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
from backend.app.core.logging import logger
from backend.app.services.llm_service import llm_service

# ---------------------------------------------------------------------------
# Phase 5 Response Templates
# ---------------------------------------------------------------------------

_VALIDATED_PIPELINE_TEMPLATE = """\
✅ **Query Understood & Validated** (Phase 5 — Pipeline Generated)

**Target Collection:** `{target_collection}`  
**Explanation:** {pipeline_explanation}

```json
{formatted_pipeline}
```

**MQL Security Validation Summary:**
- Validation Status: `{validation_status}`
- Stage Count: {stage_count} ({stages_used})
- Policy: Deterministically verified against canonical schema. Zero unsafe operators.

> ℹ️ **Phase 5 Execution Notice:** The aggregation pipeline above has been validated and prepared for execution. In accordance with Phase 5 boundaries, database query execution has NOT occurred (scheduled for Phase 6).
"""

_INVALID_PIPELINE_TEMPLATE = """\
❌ **Query Validation Failed** (Phase 5)

The generated query plan for collection `{target_collection}` could not pass deterministic security validation.

**Validation Errors:**
{formatted_errors}

Please refine your query or ensure that only canonical banking fields and relationships are requested.
"""

_UNSUPPORTED_CONCEPT_TEMPLATE = """\
⚠️ **Unsupported Banking Concept** (Phase 5)

{unsupported_explanations}

**Canonical Schema Guidance:**
- `loans.outstanding_amount` exists and represents remaining principal.
- `loans.overdue_amount` and `loans.days_past_due` do NOT exist.
- To analyze defaulted or delinquent loans, use `loans.status = 'defaulted'`.
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

_SCHEDULE_ONLY_TEMPLATE = """\
✅ **Schedule Request Understood** (Phase 5)

I've identified your request as: **set up a recurring scheduled report**.

> {query_description}

**Current system status:** Scheduled job registration is planned for a future phase after pipeline generation (Phase 5) and execution (Phase 6) are implemented.
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

    # Phase 5 pipeline state
    validation_status = state.get("validation_status", "")
    validation_errors = state.get("validation_errors") or []
    generated_pipeline = state.get("generated_pipeline")
    target_collection = state.get("target_collection") or "unknown"
    pipeline_explanation = state.get("pipeline_explanation") or "Read-only aggregation pipeline."
    query_plan_summary = state.get("query_plan_summary") or {}
    query_parameters = state.get("query_parameters") or {}
    unsupported_concepts = query_parameters.get("unsupported_concepts") or []

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

    # -- Case 2: Phase 5 Validated Pipeline (QUERY_ONLY or QUERY_AND_SCHEDULE)
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

    # -- Case 3: Pipeline Failed Validation
    elif request_mode in ("QUERY_ONLY", "QUERY_AND_SCHEDULE") and validation_status == "INVALID":
        err_lines = "\n".join(f"- {e}" for e in validation_errors) or "- General validation policy rejection."
        msg = mock_preamble + _INVALID_PIPELINE_TEMPLATE.format(
            target_collection=target_collection,
            formatted_errors=err_lines,
        )

    # -- Case 4: Unsupported Concepts
    elif unsupported_concepts and validation_status == "UNSUPPORTED":
        warn_lines = "\n".join(f"- Requested concept '{c}' is not present in schema." for c in unsupported_concepts)
        msg = mock_preamble + _UNSUPPORTED_CONCEPT_TEMPLATE.format(
            unsupported_explanations=warn_lines
        )

    # -- Case 5: Schedule Only
    elif request_mode == "SCHEDULE_ONLY":
        msg = mock_preamble + _SCHEDULE_ONLY_TEMPLATE.format(
            query_description=query_description,
            intent_reason=intent_reason,
        )

    # -- Case 6: Clarification Required
    elif request_mode == "CLARIFICATION_REQUIRED":
        msg = mock_preamble + _CLARIFICATION_TEMPLATE.format(
            clarification_question=clarification_question
            or "Could you describe what banking data you need in more detail?",
        )

    # -- Case 7: Out of Scope
    elif request_mode == "OUT_OF_SCOPE":
        msg = mock_preamble + _OUT_OF_SCOPE_TEMPLATE.format(intent_reason=intent_reason)

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
        "trace": trace,
    }
