"""
FinTech Agent — Schema Catalog and Verification Engine
Inspects and compares schema.json against the actual MongoDB collections.
Uses centralized path resolution and read-only database connections.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.app.config import settings
from backend.app.db.mongo_client import mongo_manager

SCHEMA_PATH = Path(settings.SCHEMA_SOURCE_PATH)


def load_schema_json() -> Optional[Dict[str, Any]]:
    """Loads schema.json using centralized path resolution."""
    if not SCHEMA_PATH.exists():
        return None
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_schema_against_db(db_name: Optional[str] = None) -> Dict[str, Any]:
    """Compares schema.json against actual collections and sampled documents in MongoDB."""
    schema = load_schema_json()
    if not schema:
        return {"error": "schema.json not found"}

    target_db = db_name or settings.MONGO_BANKING_DB
    if target_db == settings.MONGO_BANKING_DB:
        db = mongo_manager.get_banking_db(enforce_proxy=True)
    else:
        client = mongo_manager.get_metadata_client()
        db = client[target_db]

    db_collections = set(db.list_collection_names())
    schema_collections = set(schema.get("collections", {}).keys())
    missing_in_db = list(schema_collections - db_collections)
    extra_in_db = list(db_collections - schema_collections)

    field_audits = {}
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }

    special_warning_fields = {
        "loans": ["days_past_due", "overdue_amount"]
    }
    special_fields_found = {}

    for col in schema_collections:
        if col not in db_collections:
            continue

        sample_docs = list(db[col].find({}, {"_id": 0}).limit(100))
        documented_fields = set(schema["collections"][col].get("fields", {}).keys())

        observed_fields = set()
        observed_types = {}
        for doc in sample_docs:
            for k, v in doc.items():
                observed_fields.add(k)
                if v is not None:
                    t_name = type_map.get(type(v), type(v).__name__)
                    observed_types.setdefault(k, set()).add(t_name)

        # Check special warning fields
        if col in special_warning_fields:
            for wf in special_warning_fields[col]:
                special_fields_found[f"{col}.{wf}"] = wf in observed_fields

        missing_fields = list(documented_fields - observed_fields)
        undocumented_fields = list(observed_fields - documented_fields)

        field_audits[col] = {
            "documented_fields_count": len(documented_fields),
            "observed_fields_count": len(observed_fields),
            "sample_size": len(sample_docs),
            "missing_in_samples": missing_fields,
            "undocumented_observed": undocumented_fields,
        }

    return {
        "database": target_db,
        "schema_version": schema.get("schema_version"),
        "collections_in_schema": len(schema_collections),
        "collections_in_db": len(db_collections),
        "missing_collections_in_db": missing_in_db,
        "extra_collections_in_db": extra_in_db,
        "special_warning_fields_verification": special_fields_found,
        "field_audits": field_audits,
        "relationships_documented": len(schema.get("relationships", [])),
    }
