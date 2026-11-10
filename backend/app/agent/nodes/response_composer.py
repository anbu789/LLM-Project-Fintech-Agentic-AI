"""
FinTech Agent — Node 8: Response Composer (Phase 4, Basic Implementation)
Assembles the final user-facing message from agent state.

Phase 4 scope: Composes appropriate responses for all RequestMode outcomes.
  - QUERY_ONLY → Confirms intent, explains Phase 5 pipeline generation is pending.
  - QUERY_AND_SCHEDULE → Confirms dual intent, explains both Phase 5 and scheduling pending.
  - SCHEDULE_ONLY → Confirms scheduling intent, explains future phase pending.
  - CLARIFICATION_REQUIRED → Forwards the clarification_question to the user.
  - OUT_OF_SCOPE → Explains system scope and suggests valid queries.

Phase 5+ will replace QUERY_ONLY/QUERY_AND_SCHEDULE/SCHEDULE_ONLY responses with
actual data results once pipeline generation and execution are implemented.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.services.llm_service import llm_service

# ---------------------------------------------------------------------------
# Phase 4 response templates
# ---------------------------------------------------------------------------

_QUERY_ONLY_TEMPLATE = """\
✅ **Query Understood** (Phase 4 — Intent Confirmed)

I've identified your request as a **data query**:

> {query_description}

**Current system status:** Pipeline generation (Phase 5) is not yet implemented. \
In Phase 5, I will generate a sandboxed MongoDB aggregation pipeline and return \
real data from the banking database.

*Intent confidence: {intent_reason}*
"""

_QUERY_AND_SCHEDULE_TEMPLATE = """\
✅ **Query + Schedule Request Understood** (Phase 4 — Intent Confirmed)

I've identified your request as: **retrieve data now AND schedule recurring delivery**.

> {query_description}

**Current system status:**
- Pipeline generation and execution (Phase 5) is not yet implemented.
- Recurring scheduling and job registration (future phase) is not yet implemented.

Both will be available in upcoming phases.

*Intent confidence: {intent_reason}*
"""

_SCHEDULE_ONLY_TEMPLATE = """\
✅ **Schedule Request Understood** (Phase 4 — Intent Confirmed)

I've identified your request as: **set up a recurring scheduled report**.

> {query_description}

**Current system status:** Scheduled job registration is planned for a future phase \
after pipeline generation and execution are implemented.

*Intent confidence: {intent_reason}*
"""

_CLARIFICATION_TEMPLATE = """\
🤔 **Clarification Needed**

{clarification_question}

Please provide more details so I can generate the right banking data query for you. \
For example:
- "Show me active loans above ₹10 lakhs in the last 30 days"
- "List customers with high credit risk score in Mumbai branch"
- "Total outstanding amount by loan product category"
"""

_OUT_OF_SCOPE_TEMPLATE = """\
ℹ️ **Outside System Scope**

{intent_reason}

**FinTech Agent** is designed for banking data analytics queries. Here are some \
things I can help with:

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

An unexpected error occurred while processing your request (status: {final_status}). \
Please try again or contact support if the problem persists.
"""


# ---------------------------------------------------------------------------
# Node 8 — Response Composer
# ---------------------------------------------------------------------------

async def response_composer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 8: Assembles the final user-facing response from AgentState.

    Reads request_mode, intent fields, and guardrail results to compose an
    appropriate message.  In Phase 4 this is primarily informational — real
    data results will be incorporated in Phase 5+.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with graph_response and formatted_response set.
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

    # -- Check for mock provider explanations (e.g. definitions of NPA, KYC in tests)
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

    # -- Case 1: Guardrail already rejected (should not reach here, but be safe)
    if guardrail_status == "rejected" or final_status == "rejected":
        msg = _REJECTED_TEMPLATE.format(
            rejection_reason=rejection_reason or "Request did not pass safety checks."
        )

    # -- Case 2: Mode-based composition
    elif request_mode == "QUERY_ONLY":
        msg = mock_preamble + _QUERY_ONLY_TEMPLATE.format(
            query_description=query_description,
            intent_reason=intent_reason,
        )
    elif request_mode == "QUERY_AND_SCHEDULE":
        msg = mock_preamble + _QUERY_AND_SCHEDULE_TEMPLATE.format(
            query_description=query_description,
            intent_reason=intent_reason,
        )
    elif request_mode == "SCHEDULE_ONLY":
        msg = mock_preamble + _SCHEDULE_ONLY_TEMPLATE.format(
            query_description=query_description,
            intent_reason=intent_reason,
        )
    elif request_mode == "CLARIFICATION_REQUIRED":
        msg = (
            mock_preamble
            + _CLARIFICATION_TEMPLATE.format(
                clarification_question=clarification_question
                or "Could you describe what banking data you need in more detail?",
            )
        )
    elif request_mode == "OUT_OF_SCOPE":
        msg = mock_preamble + _OUT_OF_SCOPE_TEMPLATE.format(intent_reason=intent_reason)

    # -- Case 3: Unexpected state
    else:
        logger.warning(
            f"[{request_id}] Response composer received unexpected state: "
            f"request_mode='{request_mode}', final_status='{final_status}'"
        )
        msg = _UNKNOWN_TEMPLATE.format(final_status=final_status or "unknown")

    logger.info(f"[{request_id}] Response composer — mode='{request_mode}', len={len(msg)}")
    trace.append({
        "node": "response_composer",
        "status": "composed",
        "detail": f"Composed response for mode='{request_mode}'",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "graph_response": msg.strip(),
        "formatted_response": msg.strip(),
        "final_status": final_status or "complete",
        "trace": trace,
    }
