"""
export_dataset.py
=================
Exports all 12 collections from fintech_agent_db to:
  - data/exports/json/<collection>.json (clean JSON with ISO date strings)
  - data/exports/csv/<collection>.csv   (tabular CSV with headers)
"""

import os
import csv
import json
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "fintech_agent_db"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
JSON_DIR = os.path.join(EXPORTS_DIR, "json")
CSV_DIR = os.path.join(EXPORTS_DIR, "csv")

os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)

COLLECTIONS = [
    "branches",
    "employees",
    "merchants",
    "customers",
    "accounts",
    "transactions",
    "cards",
    "loans",
    "kyc_documents",
    "support_tickets",
    "fraud_alerts",
    "investments"
]


def json_serializer(obj):
    """Custom JSON serializer for ObjectId and datetime objects."""
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def export_collection(db, coll_name):
    print(f"Exporting '{coll_name}'...")
    cursor = db[coll_name].find({})
    docs = list(cursor)

    if not docs:
        print(f"  Warning: '{coll_name}' is empty.")
        return

    # Clean documents for export (exclude MongoDB internal `_id` for cleaner output, or keep it stringified)
    clean_docs = []
    fieldnames_set = set()

    for doc in docs:
        cleaned = {}
        for k, v in doc.items():
            if k == "_id":
                continue  # Skip MongoDB internal ObjectId to keep domain keys clean
            if isinstance(v, datetime):
                cleaned[k] = v.isoformat()
            elif isinstance(v, ObjectId):
                cleaned[k] = str(v)
            else:
                cleaned[k] = v
            fieldnames_set.add(k)
        clean_docs.append(cleaned)

    # 1. Export JSON
    json_path = os.path.join(JSON_DIR, f"{coll_name}.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(clean_docs, jf, indent=2, default=json_serializer)

    # 2. Export CSV
    # Ensure stable field ordering (primary key first if present)
    fieldnames = list(clean_docs[0].keys())
    # Add any extra fields from subsequent docs if schema is slightly polymorphic
    for f in fieldnames_set:
        if f not in fieldnames:
            fieldnames.append(f)

    csv_path = os.path.join(CSV_DIR, f"{coll_name}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for doc in clean_docs:
            # Replace None with empty string for CSV cleanliness
            row = {k: ("" if v is None else v) for k, v in doc.items()}
            writer.writerow(row)

    print(f"  ok  {coll_name}: {len(clean_docs):,} records -> JSON ({os.path.getsize(json_path):,} bytes) & CSV ({os.path.getsize(csv_path):,} bytes)")


def main():
    print("=" * 60)
    print(f"  Exporting fintech_agent_db Collections")
    print(f"  Target: {EXPORTS_DIR}")
    print("=" * 60)

    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]

    for coll in COLLECTIONS:
        export_collection(db, coll)

    print("\n" + "=" * 60)
    print("  All collections exported successfully!")
    print(f"  JSON Files: {JSON_DIR}")
    print(f"  CSV Files : {CSV_DIR}")
    print("=" * 60)
    client.close()


if __name__ == "__main__":
    main()
