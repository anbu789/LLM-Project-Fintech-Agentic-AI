"""
FinTech Agent — Schema Retrieval and Indexing API Routes
Exposes semantic schema retrieval, health inspection, and controlled indexing endpoints.
"""

from fastapi import APIRouter, HTTPException, status

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.rag.chroma_store import chroma_store
from backend.app.rag.indexer import schema_indexer
from backend.app.rag.retriever import RetrievalResult, schema_retriever
from backend.app.schemas.schema import (
    SchemaHealthResponse,
    SchemaIndexRequest,
    SchemaSearchRequest,
)

router = APIRouter(prefix="/schema", tags=["Schema Retrieval"])


@router.get(
    "/health",
    response_model=SchemaHealthResponse,
    summary="Inspect Schema Vector Store Health",
    description="Returns current ChromaDB persistence state, indexed document counts, and schema fingerprint."
)
async def schema_health_endpoint():
    """Returns vector database status and active schema fingerprint."""
    stats = chroma_store.get_stats()
    cat = schema_retriever.catalog

    return SchemaHealthResponse(
        status=stats.get("status", "ready"),
        collection_name=chroma_store.collection_name,
        persist_directory=str(chroma_store.persist_dir),
        document_count=stats.get("document_count", 0),
        schema_version=cat.schema_version,
        schema_fingerprint=stats.get("schema_fingerprint") or cat.catalog_fingerprint,
        embedding_provider=settings.EMBEDDING_PROVIDER,
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dimension=stats.get("embedding_dimension") or settings.EMBEDDING_DIMENSION
    )


@router.post(
    "/search",
    response_model=RetrievalResult,
    summary="Semantic Schema Search",
    description="Searches ChromaDB vector store for relevant banking collections, fields, and relationships."
)
async def schema_search_endpoint(request: SchemaSearchRequest):
    """Executes semantic retrieval for a natural-language banking inquiry."""
    try:
        result = schema_retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            doc_types=request.doc_types,
            collection_filter=request.collection_filter
        )
        return result
    except Exception as exc:
        logger.error(f"Schema retrieval error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error_code": "RETRIEVAL_ERROR",
                "message": f"Failed to retrieve schema information: {str(exc)}"
            }
        )


@router.post(
    "/index",
    summary="Trigger Controlled Schema Indexing",
    description="Re-indexes the schema catalog into ChromaDB. Skips embedding generation if fingerprint matches unless force=True."
)
async def schema_index_endpoint(request: SchemaIndexRequest):
    """Triggers controlled schema catalog indexing."""
    try:
        summary = schema_indexer.index_schema(force=request.force)
        return {
            "success": True,
            "data": summary
        }
    except Exception as exc:
        logger.error(f"Schema indexing failure: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error_code": "INDEXING_ERROR",
                "message": f"Failed to index schema: {str(exc)}"
            }
        )
