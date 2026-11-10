"""
FinTech Agent — Schema Catalog Builder
Builds a unified, structured, and validated representation of the banking database
by combining schema.json, MongoDB collection metadata, and BANKING_GLOSSARY.md.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.db.mongo_client import mongo_manager
from backend.app.schema.fingerprint import compute_schema_fingerprint
from backend.app.schema.glossary_mapper import load_glossary_entries
from backend.app.schema.models import (
    CollectionMetadata,
    FieldMetadata,
    GlossaryEntry,
    RelationshipMetadata,
    SchemaCatalog,
)

SCHEMA_JSON_PATH = Path("fintech-agent/data/schema.json")
DEFAULT_CATALOG_OUTPUT_PATH = Path(settings.SCHEMA_CATALOG_PATH)


class SchemaCatalogBuilder:
    """Builds a rich, grounded schema catalog without modifying any underlying data."""

    def __init__(self, schema_json_path: Path = SCHEMA_JSON_PATH):
        self.schema_json_path = schema_json_path

    def _load_schema_json(self) -> Dict[str, Any]:
        """Loads original schema.json in read-only mode."""
        if not self.schema_json_path.exists():
            raise FileNotFoundError(f"Source schema file not found at '{self.schema_json_path}'")
        with open(self.schema_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _fetch_collection_counts(self) -> Dict[str, int]:
        """Reads document counts safely using read-only banking DB."""
        counts = {}
        try:
            banking_db = mongo_manager.get_banking_db(enforce_proxy=True)
            for col_name in banking_db.list_collection_names():
                counts[col_name] = banking_db[col_name].count_documents({})
        except Exception as exc:
            logger.warning(f"Could not fetch live document counts: {exc}")
        return counts

    def build_catalog(self, include_live_counts: bool = True) -> SchemaCatalog:
        """Constructs the complete SchemaCatalog instance."""
        raw_schema = self._load_schema_json()
        doc_counts = self._fetch_collection_counts() if include_live_counts else {}
        glossary_entries = load_glossary_entries()

        # Build term index for fast field annotation
        term_map: Dict[str, List[str]] = {}
        for entry in glossary_entries:
            for field_ref in entry.mapped_fields:
                term_map.setdefault(field_ref, []).append(entry.term)
                term_map[field_ref].extend(entry.synonyms)

        # 1. Parse Relationships
        all_relationships: List[RelationshipMetadata] = []
        relationships_by_collection: Dict[str, List[RelationshipMetadata]] = {}

        for rel in raw_schema.get("relationships", []):
            from_part = rel.get("from", "")
            to_part = rel.get("to", "")
            if "." not in from_part or "." not in to_part:
                continue

            from_col, from_field = from_part.split(".", 1)
            to_col, to_field = to_part.split(".", 1)

            is_denorm = "denormalised" in rel.get("note", "").lower() or "denormalized" in rel.get("note", "").lower()

            rel_meta = RelationshipMetadata(
                from_collection=from_col,
                from_field=from_field,
                to_collection=to_col,
                to_field=to_field,
                relationship_type=rel.get("type", "many-to-one"),
                description=rel.get("note", f"Join {from_col}.{from_field} to {to_col}.{to_field}"),
                is_denormalized=is_denorm,
                integrity_rule=rel.get("note") if "integrity" in rel.get("note", "").lower() else None
            )
            all_relationships.append(rel_meta)
            relationships_by_collection.setdefault(from_col, []).append(rel_meta)

        # 2. Parse Collections & Fields
        collections_map: Dict[str, CollectionMetadata] = {}

        for col_name, col_data in raw_schema.get("collections", {}).items():
            pk = col_data.get("primary_key", "")
            raw_fields = col_data.get("fields", {})

            field_metas: Dict[str, FieldMetadata] = {}
            col_business_terms: set = set()

            for f_name, f_info in raw_fields.items():
                f_key = f"{col_name}.{f_name}"
                terms = sorted(list(set(term_map.get(f_key, []))))
                col_business_terms.update(terms)

                # Determine related collections for foreign keys
                related = []
                for rel in relationships_by_collection.get(col_name, []):
                    if rel.from_field == f_name:
                        related.append(rel.to_collection)

                # Find incoming relationships targeting this field
                for rel in all_relationships:
                    if rel.to_collection == col_name and rel.to_field == f_name:
                        related.append(rel.from_collection)

                field_meta = FieldMetadata(
                    collection=col_name,
                    field=f_name,
                    data_type=f_info.get("type", "unknown"),
                    description=f_info.get("description", ""),
                    is_primary_key=(f_name == pk),
                    references=f_info.get("references"),
                    allowed_values=f_info.get("allowed_values"),
                    business_terms=terms,
                    related_collections=sorted(list(set(related))),
                    note=f_info.get("note")
                )
                field_metas[f_name] = field_meta

            col_meta = CollectionMetadata(
                name=col_name,
                description=col_data.get("description", ""),
                primary_key=pk,
                document_count=doc_counts.get(col_name),
                fields=field_metas,
                relationships=relationships_by_collection.get(col_name, []),
                business_terms=sorted(list(col_business_terms))
            )
            collections_map[col_name] = col_meta

        # Compute deterministic fingerprint
        temp_dict = {
            "database": raw_schema.get("database", "fintech_agent_db"),
            "collections": {k: v.model_dump() for k, v in collections_map.items()},
            "relationships": [r.model_dump() for r in all_relationships]
        }
        fingerprint = compute_schema_fingerprint(temp_dict)

        catalog = SchemaCatalog(
            database=raw_schema.get("database", "fintech_agent_db"),
            schema_version=str(raw_schema.get("schema_version", "2")),
            catalog_fingerprint=fingerprint,
            generated_at=datetime.now(timezone.utc).isoformat(),
            source=str(self.schema_json_path),
            collections=collections_map,
            relationships=all_relationships,
            glossary=glossary_entries
        )
        return catalog

    def save_catalog(self, catalog: SchemaCatalog, output_path: Optional[Path] = None) -> Path:
        """Saves catalog JSON to the dedicated generated-artifact directory."""
        target = output_path or DEFAULT_CATALOG_OUTPUT_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2)
        logger.info(f"Schema catalog saved to '{target}' (fingerprint={catalog.catalog_fingerprint[:12]}...)")
        return target

    @classmethod
    def load_catalog(cls, path: Optional[Path] = None) -> SchemaCatalog:
        """Loads cached schema catalog from disk or builds fresh if missing."""
        target = path or DEFAULT_CATALOG_OUTPUT_PATH
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SchemaCatalog(**data)
        builder = cls()
        cat = builder.build_catalog()
        builder.save_catalog(cat, target)
        return cat


schema_catalog_builder = SchemaCatalogBuilder()
