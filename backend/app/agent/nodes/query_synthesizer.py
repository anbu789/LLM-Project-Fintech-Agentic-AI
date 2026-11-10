"""
FinTech Agent — Node 4: Query Synthesizer — STUB (Phase 5 implementation)
Generates a sandboxed MongoDB aggregation pipeline from schema context and query intent.

PHASE 4 STATUS: STUB — returns a placeholder indicating Phase 5 is pending.
This stub performs NO LLM calls and NO pipeline generation.
Full implementation planned for Phase 5.
"""

from datetime import datetime, timezone
from typing import Any, Dict


async def query_synthesizer_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 4 stub: Query synthesis placeholder.

    In Phase 5 this node will:
    - Use schema_context, query_description, and conversation history.
    - Prompt the LLM to generate a read-only MongoDB aggregation pipeline.
    - Populate generated_pipeline, target_collection, and query_parameters.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with stub generated_pipeline.
    """
    trace: list = list(state.get("trace") or [])
    trace.append({
        "node": "query_synthesizer",
        "status": "stub",
        "detail": "Phase 5 not yet implemented — pipeline generation skipped.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "generated_pipeline": None,
        "target_collection": None,
        "trace": trace,
    }
