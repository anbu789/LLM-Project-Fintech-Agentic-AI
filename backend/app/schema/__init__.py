"""
FinTech Agent — Schema Catalog and Documentation Module
"""

from backend.app.schema.models import (
    CollectionMetadata,
    FieldMetadata,
    GlossaryEntry,
    RAGDocument,
    RelationshipMetadata,
    SchemaCatalog,
)
from backend.app.schema.catalog_builder import SchemaCatalogBuilder, schema_catalog_builder
from backend.app.schema.document_builder import SchemaDocumentBuilder, schema_document_builder
from backend.app.schema.fingerprint import compute_schema_fingerprint
from backend.app.schema.glossary_mapper import load_glossary_entries, find_glossary_for_term

__all__ = [
    "FieldMetadata",
    "RelationshipMetadata",
    "GlossaryEntry",
    "CollectionMetadata",
    "SchemaCatalog",
    "RAGDocument",
    "SchemaCatalogBuilder",
    "schema_catalog_builder",
    "SchemaDocumentBuilder",
    "schema_document_builder",
    "compute_schema_fingerprint",
    "load_glossary_entries",
    "find_glossary_for_term",
]
