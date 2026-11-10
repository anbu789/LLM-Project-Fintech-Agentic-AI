"""
FinTech Agent — RAG Schema Document Builder
Transforms the structured SchemaCatalog into logically separated, deterministic
documents for ChromaDB indexing across collections, fields, relationships, and glossary terms.
Strictly prohibits embedding raw banking records or customer PII.
"""

import re
from typing import List
from backend.app.schema.models import RAGDocument, SchemaCatalog


def _slugify(text: str) -> str:
    """Converts a phrase into a clean deterministic identifier slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


class SchemaDocumentBuilder:
    """Generates discrete RAG documents from a SchemaCatalog instance."""

    def build_documents(self, catalog: SchemaCatalog) -> List[RAGDocument]:
        """Constructs all collection, field, relationship, and glossary documents."""
        documents: List[RAGDocument] = []

        # 1. Collection-Level Documents (12 documents)
        for col_name, col_meta in catalog.collections.items():
            field_names = list(col_meta.fields.keys())
            key_f_list = [f"{f} ({col_meta.fields[f].data_type})" for f in field_names[:12]]
            syn_str = ", ".join(col_meta.business_terms[:8]) if col_meta.business_terms else "None"
            rel_str = ", ".join([f"references {r.to_collection}" for r in col_meta.relationships]) if col_meta.relationships else "None"

            count_str = f" Document count: {col_meta.document_count} records." if col_meta.document_count is not None else ""

            content = (
                f"Collection: {col_name}.\n"
                f"Purpose: {col_meta.description}{count_str}\n"
                f"Primary Key: '{col_meta.primary_key}'.\n"
                f"Total Fields: {len(col_meta.fields)}. Key fields: {', '.join(key_f_list)}.\n"
                f"Outgoing Joins / Relationships: {rel_str}.\n"
                f"Banking Domain Terms & Synonyms: {syn_str}.\n"
                f"Use this collection for natural-language questions related to {col_name}."
            )

            doc = RAGDocument(
                id=f"coll:{col_name}",
                doc_type="collection",
                title=f"Collection: {col_name}",
                content=content.strip(),
                metadata={
                    "doc_type": "collection",
                    "collection": col_name,
                    "field": "",
                    "primary_key": col_meta.primary_key,
                    "schema_version": catalog.schema_version,
                    "fingerprint": catalog.catalog_fingerprint
                }
            )
            documents.append(doc)

        # 2. Field-Level Documents (200 documents across 12 collections)
        for col_name, col_meta in catalog.collections.items():
            for f_name, f_meta in col_meta.fields.items():
                desc_str = f" Description: {f_meta.description}." if f_meta.description else ""
                enum_str = f" Allowed values: {', '.join(f_meta.allowed_values)}." if f_meta.allowed_values else ""
                ref_str = f" Foreign key reference: joins to '{f_meta.references}'." if f_meta.references else ""
                syn_str = f" Business terms & synonyms: {', '.join(f_meta.business_terms)}." if f_meta.business_terms else ""
                note_str = f" Note: {f_meta.note}." if f_meta.note else ""

                pk_tag = " (Primary Key)" if f_meta.is_primary_key else ""

                content = (
                    f"Field: '{col_name}.{f_name}'{pk_tag}.\n"
                    f"Collection: '{col_name}'. Data Type: {f_meta.data_type}.{desc_str}{enum_str}{ref_str}{syn_str}{note_str}"
                )

                doc = RAGDocument(
                    id=f"field:{col_name}.{f_name}",
                    doc_type="field",
                    title=f"Field: {col_name}.{f_name}",
                    content=content.strip(),
                    metadata={
                        "doc_type": "field",
                        "collection": col_name,
                        "field": f_name,
                        "data_type": f_meta.data_type,
                        "is_primary_key": f_meta.is_primary_key,
                        "is_foreign_key": bool(f_meta.references),
                        "schema_version": catalog.schema_version,
                        "fingerprint": catalog.catalog_fingerprint
                    }
                )
                documents.append(doc)

        # 3. Relationship-Level Documents (22 documents)
        for rel in catalog.relationships:
            denorm_str = " (Denormalized join key)" if rel.is_denormalized else ""
            rule_str = f" Integrity constraint: {rel.integrity_rule}." if rel.integrity_rule else ""

            content = (
                f"Relationship: '{rel.from_collection}.{rel.from_field}' -> '{rel.to_collection}.{rel.to_field}'{denorm_str}.\n"
                f"Source Collection: '{rel.from_collection}', Field: '{rel.from_field}'.\n"
                f"Target Collection: '{rel.to_collection}', Field: '{rel.to_field}'.\n"
                f"Cardinality: {rel.relationship_type}.\n"
                f"Business Description: {rel.description}.{rule_str}\n"
                f"Use this relationship to join {rel.from_collection} with {rel.to_collection} in MongoDB aggregation pipelines via $lookup."
            )

            doc = RAGDocument(
                id=f"rel:{rel.from_collection}.{rel.from_field}->{rel.to_collection}.{rel.to_field}",
                doc_type="relationship",
                title=f"Relationship: {rel.from_collection} to {rel.to_collection}",
                content=content.strip(),
                metadata={
                    "doc_type": "relationship",
                    "collection": rel.from_collection,
                    "target_collection": rel.to_collection,
                    "field": rel.from_field,
                    "target_field": rel.to_field,
                    "schema_version": catalog.schema_version,
                    "fingerprint": catalog.catalog_fingerprint
                }
            )
            documents.append(doc)

        # 4. Glossary-Level Documents (35 documents)
        for entry in catalog.glossary:
            slug = _slugify(entry.term)
            cols_str = ", ".join(entry.mapped_collections) if entry.mapped_collections else "None"
            fields_str = ", ".join(entry.mapped_fields) if entry.mapped_fields else "None"
            syn_str = ", ".join(entry.synonyms) if entry.synonyms else "None"

            content = (
                f"Banking Concept: '{entry.term}' ({entry.category}).\n"
                f"Meaning: {entry.meaning}\n"
                f"Implementation Guidance: {entry.implementation_guidance}\n"
                f"Mapped Collections: {cols_str}.\n"
                f"Mapped Fields: {fields_str}.\n"
                f"Natural Language Synonyms: {syn_str}.\n"
                f"Connects user questions using '{entry.term}' to the corresponding MongoDB collections and fields."
            )

            primary_col = entry.mapped_collections[0] if entry.mapped_collections else "general"

            doc = RAGDocument(
                id=f"glossary:{slug}",
                doc_type="glossary",
                title=f"Banking Glossary: {entry.term}",
                content=content.strip(),
                metadata={
                    "doc_type": "glossary",
                    "collection": primary_col,
                    "field": "",
                    "term": entry.term,
                    "schema_version": catalog.schema_version,
                    "fingerprint": catalog.catalog_fingerprint
                }
            )
            documents.append(doc)

        return documents


schema_document_builder = SchemaDocumentBuilder()
