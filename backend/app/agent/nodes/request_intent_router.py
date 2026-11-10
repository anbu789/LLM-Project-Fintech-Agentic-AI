"""
FinTech Agent — Node 2: Request Intent Router (Phase 4, Full Implementation)
LLM-based (or mock-deterministic) intent classification node.

Responsibilities:
  - Build a structured prompt using the query and conversation context.
  - Call the configured LLM provider for JSON-structured intent output.
  - Parse and validate the response with Pydantic (IntentClassification).
  - On parse failure: use a safe conservative fallback (CLARIFICATION_REQUIRED).
  - For mock provider: use deterministic keyword classification without LLM.

NEVER silently converts a failed classification into a banking data intent.
NEVER allows LLM output to override guardrail decisions or grant authorization
to execute destructive operations.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from backend.app.agent.prompts.intent_classification import (
    INTENT_CLASSIFICATION_SYSTEM_PROMPT,
    build_intent_classification_prompt,
    mock_classify_intent,
)
from backend.app.agent.state import RequestMode
from backend.app.config import settings
from backend.app.core.exceptions import FinTechAgentException
from backend.app.core.logging import logger
from backend.app.services.llm_service import llm_service


# ---------------------------------------------------------------------------
# Pydantic model for structured intent output validation
# ---------------------------------------------------------------------------

class IntentClassification(BaseModel):
    """Validated structured output from the intent classification LLM call."""

    request_mode: RequestMode
    intent_reason: str
    query_description: Optional[str] = None
    clarification_question: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _safe_fallback(reason: str) -> Dict[str, Any]:
    """Conservative fallback when classification fails — never defaults to data query."""
    return {
        "request_mode": "CLARIFICATION_REQUIRED",
        "intent_reason": f"Intent classification failed — {reason}. Requesting clarification.",
        "query_description": None,
        "clarification_question": (
            "I wasn't able to understand your request. "
            "Could you rephrase it? For example: 'Show me active loans above ₹10 lakhs' "
            "or 'How many customers have high credit risk?'"
        ),
    }


def _parse_llm_intent(raw_text: str) -> Optional[IntentClassification]:
    """Extract and validate JSON from LLM output.

    Handles: fenced code blocks, leading/trailing prose, partial JSON.

    Args:
        raw_text: Raw string returned by the LLM provider.

    Returns:
        A validated IntentClassification instance, or None on failure.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if "```" in text:
        lines = text.splitlines()
        inside = False
        json_lines: List[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines).strip()

    # Try to find the first JSON object boundary
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    candidate = text[start:end]
    try:
        data = json.loads(candidate)
        return IntentClassification(**data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Node 2 — Request Intent Router
# ---------------------------------------------------------------------------

async def intent_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 2: Classify natural-language query into a RequestMode.

    For mock provider:   uses deterministic keyword-based rules.
    For real providers:  calls LLM with structured JSON output instructions.

    On any failure (network, bad JSON, validation error):
      - Logs a warning.
      - Falls back to CLARIFICATION_REQUIRED (never to a data query mode).

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState dict with intent fields populated.
    """
    request_id = state.get("request_id", "unknown")
    query: str = state.get("natural_language_query", "")
    history: List[Dict[str, Any]] = state.get("conversation_history") or []
    trace: list = list(state.get("trace") or [])

    provider_name = (settings.LLM_PROVIDER or "mock").lower().strip()
    logger.info(
        f"[{request_id}] Intent router — provider='{provider_name}', "
        f"query_len={len(query)}, history_turns={len(history)}"
    )

    # -------------------------------------------------------------------
    # Path A: mock provider — deterministic keyword classification
    # -------------------------------------------------------------------
    if provider_name == "mock":
        result = mock_classify_intent(query, history)
        logger.info(
            f"[{request_id}] Mock intent classification → mode='{result['request_mode']}'"
        )
        trace.append(
            _trace_entry(
                "intent_router",
                "mock",
                f"Mock classification → {result['request_mode']}",
            )
        )
        return {**result, "trace": trace}

    # -------------------------------------------------------------------
    # Path B: real LLM provider — structured JSON output
    # -------------------------------------------------------------------
    user_prompt = build_intent_classification_prompt(query, history)

    try:
        raw_response = await llm_service.get_provider().generate_response(
            user_message=user_prompt,
            conversation_history=None,  # history is already embedded in the prompt
            system_prompt=INTENT_CLASSIFICATION_SYSTEM_PROMPT,
        )

        classification = _parse_llm_intent(raw_response)
        if classification is None:
            logger.warning(
                f"[{request_id}] Intent router: could not parse LLM output as IntentClassification. "
                f"Raw (first 200 chars): {raw_response[:200]!r}"
            )
            fallback = _safe_fallback("LLM returned unparseable or invalid JSON")
            trace.append(
                _trace_entry("intent_router", "parse_failure", fallback["intent_reason"])
            )
            return {**fallback, "trace": trace}

        logger.info(
            f"[{request_id}] LLM intent classification → mode='{classification.request_mode}'"
        )
        trace.append(
            _trace_entry(
                "intent_router",
                "success",
                f"LLM classification → {classification.request_mode}",
            )
        )
        return {
            "request_mode": classification.request_mode,
            "intent_reason": classification.intent_reason,
            "query_description": classification.query_description,
            "clarification_question": classification.clarification_question,
            "trace": trace,
        }

    except FinTechAgentException:
        # Re-raise application/provider authentication, configuration, and rate-limit errors
        # so they can be handled by API error-shielding middleware with proper HTTP status codes.
        raise
    except Exception as exc:
        safe_msg = str(exc)[:200]
        logger.warning(
            f"[{request_id}] Intent router: LLM call failed — {safe_msg}"
        )
        fallback = _safe_fallback(f"LLM provider error: {safe_msg}")
        trace.append(_trace_entry("intent_router", "error", fallback["intent_reason"]))
        return {**fallback, "trace": trace}
