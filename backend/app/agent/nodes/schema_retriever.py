"""
FinTech Agent — Node 3: Schema Retriever — STUB (Phase 5 implementation)
Retrieves relevant ChromaDB schema context for the identified query intent.

PHASE 4 STATUS: STUB — returns a placeholder indicating Phase 5 is pending.
This stub performs NO database queries and NO ChromaDB lookups.
Full implementation planned for Phase 5.
"""

from datetime import datetime, timezone
from typing import Any, Dict


async def schema_retriever_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 3 stub: Schema retrieval placeholder.

    In Phase 5 this node will:
    - Use the query_description from Node 2 to build an embedding query.
    - Retrieve relevant schema chunks from ChromaDB (fintech_schema_catalog_cosine).
    - Populate schema_context, collections_identified, and schema_version.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with stub schema_context.
    """
    trace: list = list(state.get("trace") or [])
    trace.append({
        "node": "schema_retriever",
        "status": "stub",
        "detail": "Phase 5 not yet implemented — schema retrieval skipped.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "schema_context": {
            "phase": "stub",
            "note": "Schema retrieval will be implemented in Phase 5.",
        },
        "collections_identified": [],
        "trace": trace,
    }
