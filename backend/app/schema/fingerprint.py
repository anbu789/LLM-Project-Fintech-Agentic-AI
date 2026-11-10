"""
FinTech Agent — Schema Fingerprint Calculator
Produces deterministic SHA-256 hash representing database schema version
to enable incremental indexing, change detection, and ChromaDB consistency.
"""

import hashlib
import json
from typing import Any, Dict


def compute_schema_fingerprint(schema_dict: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of the schema structure.
    Ignores non-structural runtime metadata (timestamps, document counts)
    to ensure identical schemas produce identical fingerprints across runs.
    """
    canonical_repr: Dict[str, Any] = {
        "database": schema_dict.get("database", "fintech_agent_db"),
        "collections": {},
        "relationships": []
    }

    # Normalize collections and fields
    collections = schema_dict.get("collections", {})
    for col_name in sorted(collections.keys()):
        col_data = collections[col_name]
        fields = col_data.get("fields", {})
        canonical_fields = {}
        for f_name in sorted(fields.keys()):
            f_meta = fields[f_name]
            # Handle both dict and FieldMetadata model
            if hasattr(f_meta, "model_dump"):
                f_meta = f_meta.model_dump()
            canonical_fields[f_name] = {
                "type": f_meta.get("data_type") or f_meta.get("type", "unknown"),
                "references": f_meta.get("references"),
                "allowed_values": sorted(f_meta.get("allowed_values") or [])
            }
        canonical_repr["collections"][col_name] = {
            "primary_key": col_data.get("primary_key", ""),
            "fields": canonical_fields
        }

    # Normalize relationships
    rels = schema_dict.get("relationships", [])
    for rel in rels:
        if hasattr(rel, "model_dump"):
            rel = rel.model_dump()
        from_col = rel.get("from_collection") or (rel.get("from", "").split(".")[0] if "." in rel.get("from", "") else "")
        from_field = rel.get("from_field") or (rel.get("from", "").split(".")[1] if "." in rel.get("from", "") else "")
        to_col = rel.get("to_collection") or (rel.get("to", "").split(".")[0] if "." in rel.get("to", "") else "")
        to_field = rel.get("to_field") or (rel.get("to", "").split(".")[1] if "." in rel.get("to", "") else "")

        canonical_repr["relationships"].append({
            "from": f"{from_col}.{from_field}",
            "to": f"{to_col}.{to_field}",
            "type": rel.get("relationship_type") or rel.get("type", "many-to-one")
        })

    # Sort relationships deterministically
    canonical_repr["relationships"].sort(key=lambda r: (r["from"], r["to"]))

    # Canonical JSON string
    serialized = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
