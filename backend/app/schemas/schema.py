"""
FinTech Agent — Schema API Request and Response Schemas
Pydantic v2 models for schema search, health inspection, and indexing endpoints.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SchemaSearchRequest(BaseModel):
    """Request payload for semantic schema retrieval endpoint."""
    query: str = Field(..., description="Natural language banking question", min_length=1, max_length=1000)
    top_k: Optional[int] = Field(default=5, description="Number of results to return", gt=0, le=20)
    doc_types: Optional[List[str]] = Field(default=None, description="Optional filter by document types ('collection', 'field', 'relationship', 'glossary')")
    collection_filter: Optional[str] = Field(default=None, description="Optional filter by target collection name")

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty or contain only whitespace.")
        return cleaned


class SchemaIndexRequest(BaseModel):
    """Request payload to trigger controlled schema indexing."""
    force: bool = Field(default=False, description="Whether to force re-indexing even if schema fingerprint matches")


class SchemaHealthResponse(BaseModel):
    """Health and index status for ChromaDB schema store."""
    status: str
    collection_name: str
    persist_directory: str
    document_count: int
    schema_version: str
    schema_fingerprint: Optional[str] = None
    embedding_provider: str
    embedding_model: str
    embedding_dimension: Optional[int] = None
