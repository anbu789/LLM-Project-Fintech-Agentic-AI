"""
FinTech Agent — Node 3: Schema Retriever (Phase 5, Full Implementation)
Retrieves semantic schema context from ChromaDB and the canonical schema catalog
for the identified natural-language banking query intent.

Responsibilities:
  1. Extract search query from query_description (Node 2) or natural_language_query.
  2. Invoke SchemaRetriever to perform vector search over schema chunks.
  3. Extract relevant collections, fields, relationships, and unsupported concepts.
  4. Build a bounded, verified schema context dictionary from the canonical catalog.
  5. Populate schema_context, collections_identified, schema_version, and embedding_model.
  6. Record structured audit trace.

THIS NODE PERFORMS ZERO MONGODB DATABASE QUERIES.
All metadata is retrieved from the ChromaDB vector store and generated schema catalog.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.agent.state import AgentState
from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.rag.retriever import schema_retriever


def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def schema_retriever_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 3: Retrieve relevant schema context for the banking inquiry.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with schema_context, collections_identified,
        schema_version, and embedding_model populated.
    """
    request_id = state.get("request_id", "unknown")
    trace: list = list(state.get("trace") or [])

    # Prefer restated query description from Node 2; fallback to original query
    query: str = (
        state.get("query_description")
        or state.get("natural_language_query")
        or ""
    ).strip()

    logger.info(
        f"[{request_id}] Node 3 (Schema Retriever) executing for query: '{query[:80]}...'"
    )

    try:
        # 1. Execute semantic retrieval via ChromaDB and schema catalog
        result = schema_retriever.retrieve(
            query=query,
            top_k=settings.RETRIEVAL_TOP_K
        )

        catalog = schema_retriever.catalog
        schema_version = catalog.schema_version
        collections_identified: List[str] = list(result.relevant_collections)

        # 2. Build structured collection definitions from canonical catalog
        collections_detail: Dict[str, Any] = {}
        for col_name in collections_identified:
            if col_name in catalog.collections:
                col_meta = catalog.collections[col_name]
                fields_map: Dict[str, Any] = {}
                for f_name, f_meta in col_meta.fields.items():
                    fields_map[f_name] = {
                        "data_type": f_meta.data_type,
                        "description": f_meta.description,
                        "is_primary_key": f_meta.is_primary_key,
                        "references": f_meta.references,
                        "allowed_values": f_meta.allowed_values,
                    }

                collections_detail[col_name] = {
                    "name": col_name,
                    "description": col_meta.description,
                    "primary_key": col_meta.primary_key,
                    "fields": fields_map,
                }

        # 3. Assemble complete bounded schema context
        schema_context: Dict[str, Any] = {
            "status": result.status,
            "query": query,
            "relevant_collections": collections_identified,
            "collections": collections_detail,
            "relevant_fields": result.relevant_fields,
            "relevant_relationships": result.relevant_relationships,
            "unsupported_concepts": result.unsupported_concepts,
            "retrieved_documents": [
                {
                    "id": doc.id,
                    "doc_type": doc.doc_type,
                    "collection": doc.collection,
                    "field": doc.field,
                    "similarity": doc.similarity,
                    "content": doc.content,
                }
                for doc in result.retrieved_documents
            ],
            "total_hits": result.total_hits,
            "schema_version": schema_version,
        }

        trace.append(
            _trace_entry(
                "schema_retriever",
                "success",
                f"Retrieved {len(collections_identified)} collections, "
                f"{len(result.relevant_relationships)} relationships, "
                f"{len(result.unsupported_concepts)} unsupported warnings.",
            )
        )

        logger.info(
            f"[{request_id}] Node 3 completed successfully: "
            f"collections={collections_identified}, hits={result.total_hits}"
        )

        return {
            "schema_context": schema_context,
            "collections_identified": collections_identified,
            "schema_version": schema_version,
            "embedding_model": settings.EMBEDDING_MODEL,
            "trace": trace,
        }

    except Exception as exc:
        safe_err = str(exc)[:200]
        logger.warning(f"[{request_id}] Schema retriever exception: {safe_err}")
        trace.append(
            _trace_entry(
                "schema_retriever",
                "fallback",
                f"Retrieval error: {safe_err}. Returning empty schema context.",
            )
        )
        return {
            "schema_context": {
                "status": "error",
                "error": safe_err,
                "relevant_collections": [],
                "collections": {},
                "relevant_relationships": [],
                "unsupported_concepts": [],
                "retrieved_documents": [],
                "total_hits": 0,
            },
            "collections_identified": [],
            "schema_version": "unknown",
            "embedding_model": settings.EMBEDDING_MODEL,
            "trace": trace,
        }


# Backwards compatibility stub for Phase 4 regression test
async def schema_retriever_stub(state: AgentState) -> dict:
    """Legacy stub function preserved for Phase 4 backwards-compatibility tests."""
    trace = list(state.get("trace", []))
    trace.append({
        "node": "schema_retriever",
        "status": "stub",
        "detail": "Phase 4 stub invoked directly",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "collections_identified": [],
        "schema_context": {
            "phase": "stub",
            "collections": {},
            "relationships": [],
            "unsupported_concepts": [],
        },
        "trace": trace,
    }
