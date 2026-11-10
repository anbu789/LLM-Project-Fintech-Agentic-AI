"""
FinTech Agent — Schema Catalog and RAG Document Models
Pydantic v2 schemas representing structured metadata for collections,
fields, relationships, banking glossary entries, and RAG documents.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FieldMetadata(BaseModel):
    """Metadata for an individual collection field."""
    collection: str = Field(..., description="Parent collection name")
    field: str = Field(..., description="Field name in MongoDB")
    data_type: str = Field(..., description="Data type (string, number, integer, boolean, date, object, array)")
    description: str = Field(default="", description="Field description and semantics")
    is_primary_key: bool = Field(default=False, description="Whether this field is the entity primary key")
    references: Optional[str] = Field(default=None, description="Foreign key reference (e.g., 'employees.employee_id')")
    allowed_values: Optional[List[str]] = Field(default=None, description="Enumerated values for categorical fields")
    business_terms: List[str] = Field(default_factory=list, description="Synonyms and banking domain terms")
    related_collections: List[str] = Field(default_factory=list, description="Collections related via this field")
    note: Optional[str] = Field(default=None, description="Implementation or integrity notes")


class RelationshipMetadata(BaseModel):
    """Metadata describing a directional relationship between two collections."""
    from_collection: str = Field(..., description="Source collection containing foreign key")
    from_field: str = Field(..., description="Source foreign key field name")
    to_collection: str = Field(..., description="Target collection containing referenced primary key")
    to_field: str = Field(..., description="Target primary key field name")
    relationship_type: str = Field(default="many-to-one", description="Cardinality type")
    description: str = Field(default="", description="Human-readable business explanation of join")
    is_denormalized: bool = Field(default=False, description="Whether this key is stored for denormalization efficiency")
    integrity_rule: Optional[str] = Field(default=None, description="Referenced cross-collection integrity constraint")


class GlossaryEntry(BaseModel):
    """Mapped banking term from BANKING_GLOSSARY.md."""
    term: str = Field(..., description="Banking business terminology")
    category: str = Field(..., description="Glossary category (e.g. 'Customer and Identity Terms')")
    meaning: str = Field(..., description="Business definition in project context")
    implementation_guidance: str = Field(default="", description="Guidance on schema mappings and pitfalls")
    mapped_collections: List[str] = Field(default_factory=list, description="Relevant MongoDB collections")
    mapped_fields: List[str] = Field(default_factory=list, description="Relevant MongoDB fields")
    synonyms: List[str] = Field(default_factory=list, description="Natural-language variants and synonyms")


class CollectionMetadata(BaseModel):
    """Metadata for a complete MongoDB collection."""
    name: str = Field(..., description="Collection name")
    description: str = Field(..., description="Purpose and contents summary")
    primary_key: str = Field(..., description="Domain primary key field")
    document_count: Optional[int] = Field(default=None, description="Verified document count in database")
    fields: Dict[str, FieldMetadata] = Field(default_factory=dict, description="Field definitions map")
    relationships: List[RelationshipMetadata] = Field(default_factory=list, description="Outgoing relationships")
    business_terms: List[str] = Field(default_factory=list, description="Associated banking terms")


class SchemaCatalog(BaseModel):
    """Comprehensive, versioned catalog of all collections, fields, and relationships."""
    database: str = Field(..., description="Database name (fintech_agent_db)")
    schema_version: str = Field(..., description="Schema revision number")
    catalog_fingerprint: str = Field(..., description="Deterministic SHA-256 hash of schema structure")
    source_fingerprint: Optional[str] = Field(default=None, description="SHA-256 hash of raw schema.json file for cache invalidation")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    source: str = Field(default="schema.json + mongodb_inspection + banking_glossary", description="Source of catalog")
    collections: Dict[str, CollectionMetadata] = Field(default_factory=dict, description="Collections map")
    relationships: List[RelationshipMetadata] = Field(default_factory=list, description="All cross-collection relationships")
    glossary: List[GlossaryEntry] = Field(default_factory=list, description="All mapped glossary entries")


class RAGDocument(BaseModel):
    """A logically separated, deterministic document for ChromaDB embedding and retrieval."""
    id: str = Field(..., description="Deterministic document ID (e.g., 'coll:accounts', 'field:loans.outstanding_amount')")
    doc_type: str = Field(..., description="Document type ('collection', 'field', 'relationship', 'glossary')")
    title: str = Field(..., description="Concise document title")
    content: str = Field(..., description="Human-readable text content for embedding")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="ChromaDB filter metadata")
