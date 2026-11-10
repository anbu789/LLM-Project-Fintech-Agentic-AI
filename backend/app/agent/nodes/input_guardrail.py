"""
FinTech Agent — Node 1: Input Guardrail (Phase 4, Full Implementation)
Deterministic, LLM-free safety gate that runs BEFORE any LLM call.

Checks (in priority order):
  1. Missing / empty / whitespace-only input
  2. Oversized input (> MAX_MESSAGE_LENGTH characters)
  3. Prompt injection patterns
  4. Secret / credential extraction attempts
  5. Destructive database operation intent

This node never calls an LLM.  All decisions are based on pure regex and
length checks, so they are fast, deterministic, and testable without mocks.

LLM classification CANNOT override a guardrail rejection — a rejected state
terminates the graph immediately via conditional routing in graph.py.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.config import settings
from backend.app.core.logging import logger

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Prompt injection — attempts to override system instructions
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(system|previous)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+|an\s+)?", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"forget\s+(your\s+|the\s+)?(instructions?|rules?|guidelines?)", re.IGNORECASE),
    re.compile(r"new\s+persona\b", re.IGNORECASE),
    re.compile(r"override\s+(the\s+|your\s+)?(system|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"developer\s+mode\s+enabled", re.IGNORECASE),
]

# Secret / credential extraction attempts
_SECRET_EXTRACTION_PATTERNS = [
    re.compile(
        r"(show|tell|reveal|print|output|display|give|provide|expose|leak).{0,30}"
        r"(api.?key|password|secret|credentials?|\.env|environment.?variable|config\.?|token|private.?key)",
        re.IGNORECASE,
    ),
    re.compile(r"what\s+is\s+(your|the)\s+(api.?key|password|token|secret)", re.IGNORECASE),
    re.compile(r"repeat\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(instructions?|system\s+prompt)", re.IGNORECASE),
    re.compile(r"output\s+(your|the)\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"what\s+are\s+your\s+instructions", re.IGNORECASE),
]

# Destructive MongoDB / database operation intent
_DESTRUCTIVE_DB_PATTERNS = [
    re.compile(
        r"(drop|delete|destroy|truncate|remove)\s*.{0,20}\s*(collection|database|db|table|index)",
        re.IGNORECASE,
    ),
    re.compile(r"\bdb\s*\.\s*(drop|delete|dropDatabase|dropCollection)\b", re.IGNORECASE),
    re.compile(r"\bdb\s*\..*?\.\s*(drop|delete|remove|insert|update)\b", re.IGNORECASE),
    re.compile(r"\b\w+\.(drop|deleteMany|deleteOne|remove|insert)\s*\(", re.IGNORECASE),
    re.compile(r"\binsert\s*.{0,20}\s*into\b", re.IGNORECASE),
    re.compile(r"\b(create|drop)\s*.{0,20}\s*index\b", re.IGNORECASE),
    re.compile(r"\b(update|set)\s*.{0,20}\s*(all\s+)?(records|documents|rows)\b", re.IGNORECASE),
    re.compile(r"\bdeleteMany\b", re.IGNORECASE),
    re.compile(r"\bdropDatabase\b", re.IGNORECASE),
    re.compile(r"\bundrop\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Helper — append a trace entry
# ---------------------------------------------------------------------------

def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Node 1 — Input Guardrail
# ---------------------------------------------------------------------------

async def input_guardrail_node(state: "dict[str, Any]") -> Dict[str, Any]:
    """Node 1: Deterministic safety gate.  No LLM calls.

    Args:
        state: Incoming AgentState dict (may have partial keys).

    Returns:
        A partial AgentState dict with guardrail_status set to 'allowed'
        or 'rejected'.  On rejection, final_status and graph_response are
        also set so the graph can terminate cleanly via END.
    """
    request_id = state.get("request_id", "unknown")
    query: str = state.get("natural_language_query") or ""
    trace: list = list(state.get("trace") or [])

    def _reject(reason: str, user_msg: str) -> Dict[str, Any]:
        logger.warning(f"[{request_id}] Guardrail REJECTED — {reason}")
        trace.append(_trace_entry("input_guardrail", "rejected", reason))
        return {
            "guardrail_status": "rejected",
            "rejection_reason": reason,
            "final_status": "rejected",
            "graph_response": user_msg,
            "trace": trace,
        }

    # -- Check 1: empty / missing input -------------------------------------
    if not query or not query.strip():
        return _reject(
            reason="Empty or whitespace-only input.",
            user_msg=(
                "Your message appears to be empty. "
                "Please type a banking query such as 'Show me active loans above ₹10 lakhs'."
            ),
        )

    # -- Check 2: oversized input -------------------------------------------
    max_len = settings.MAX_MESSAGE_LENGTH
    if len(query) > max_len:
        return _reject(
            reason=f"Input length {len(query)} exceeds maximum {max_len} characters.",
            user_msg=(
                f"Your message is too long ({len(query)} characters). "
                f"Please shorten it to {max_len} characters or fewer."
            ),
        )

    # -- Check 3: prompt injection ------------------------------------------
    for pat in _INJECTION_PATTERNS:
        if pat.search(query):
            matched = pat.pattern[:60]
            return _reject(
                reason=f"Prompt injection pattern detected: '{matched}'.",
                user_msg=(
                    "Your request contains content that cannot be processed by this system. "
                    "Please submit a valid banking data query."
                ),
            )

    # -- Check 4: secret / credential extraction ----------------------------
    for pat in _SECRET_EXTRACTION_PATTERNS:
        if pat.search(query):
            matched = pat.pattern[:60]
            return _reject(
                reason=f"Credential/secret extraction attempt detected: '{matched}'.",
                user_msg=(
                    "Requests for system credentials, API keys, or configuration data "
                    "are not permitted. Please submit a valid banking data query."
                ),
            )

    # -- Check 5: destructive database intent -------------------------------
    for pat in _DESTRUCTIVE_DB_PATTERNS:
        if pat.search(query):
            matched = pat.pattern[:60]
            return _reject(
                reason=f"Destructive database operation intent detected: '{matched}'.",
                user_msg=(
                    "This system is read-only and cannot modify, delete, or drop "
                    "database collections or records. Please submit a read-only banking query."
                ),
            )

    # -- All checks passed --------------------------------------------------
    logger.info(f"[{request_id}] Guardrail ALLOWED — query length={len(query)}")
    trace.append(_trace_entry("input_guardrail", "allowed", "All guardrail checks passed."))
    return {
        "guardrail_status": "allowed",
        "trace": trace,
    }
