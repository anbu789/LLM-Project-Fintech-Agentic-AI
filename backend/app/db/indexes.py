"""
FinTech Agent — Database Index Inspection and Audit Utility
Audits existing indexes against architecture recommendations without making modifications.
"""

from typing import Any, Dict, List
from pymongo import MongoClient
from backend.app.config import settings

# Key recommended indexes based on SYSTEM_ARCHITECTURE_UPDATED.md
RECOMMENDED_INDEXES: Dict[str, List[Dict[str, Any]]] = {
    "accounts": [
        {"fields": [("account_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
        {"fields": [("branch_id", 1)], "unique": False},
        {"fields": [("status", 1)], "unique": False},
    ],
    "branches": [
        {"fields": [("branch_id", 1)], "unique": True},
    ],
    "cards": [
        {"fields": [("card_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
        {"fields": [("account_id", 1)], "unique": False},
    ],
    "customers": [
        {"fields": [("customer_id", 1)], "unique": True},
        {"fields": [("status", 1)], "unique": False},
        {"fields": [("risk_category", 1)], "unique": False},
    ],
    "employees": [
        {"fields": [("employee_id", 1)], "unique": True},
        {"fields": [("branch_id", 1)], "unique": False},
    ],
    "fraud_alerts": [
        {"fields": [("alert_id", 1)], "unique": True},
        {"fields": [("transaction_id", 1)], "unique": False},
        {"fields": [("customer_id", 1)], "unique": False},
    ],
    "investments": [
        {"fields": [("investment_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
    ],
    "kyc_documents": [
        {"fields": [("kyc_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
    ],
    "loans": [
        {"fields": [("loan_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
        {"fields": [("sanctioning_branch_id", 1)], "unique": False},
        {"fields": [("status", 1)], "unique": False},
    ],
    "merchants": [
        {"fields": [("merchant_id", 1)], "unique": True},
    ],
    "support_tickets": [
        {"fields": [("ticket_id", 1)], "unique": True},
        {"fields": [("customer_id", 1)], "unique": False},
        {"fields": [("status", 1)], "unique": False},
    ],
    "transactions": [
        {"fields": [("transaction_id", 1)], "unique": True},
        {"fields": [("account_id", 1)], "unique": False},
        {"fields": [("customer_id", 1)], "unique": False},
        {"fields": [("transaction_date", 1)], "unique": False},
        {"fields": [("transaction_mode", 1)], "unique": False},
        {"fields": [("status", 1)], "unique": False},
        {"fields": [("is_flagged", 1)], "unique": False},
    ],
}


def audit_indexes(db_name: str = None) -> Dict[str, Any]:
    """Audits existing indexes against recommendations without altering indexes."""
    target_db = db_name or settings.MONGO_BANKING_DB
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[target_db]

    report = {}
    for col_name, rec_list in RECOMMENDED_INDEXES.items():
        existing = list(db[col_name].list_indexes()) if col_name in db.list_collection_names() else []
        existing_keys = [tuple(idx["key"].items()) for idx in existing]

        matched = []
        missing = []
        for rec in rec_list:
            rec_key = tuple(rec["fields"])
            if rec_key in existing_keys:
                matched.append(rec)
            else:
                missing.append(rec)

        report[col_name] = {
            "existing_count": len(existing),
            "existing_indexes": [
                {"name": idx["name"], "key": idx["key"], "unique": idx.get("unique", False)}
                for idx in existing
            ],
            "matched_recommendations": len(matched),
            "missing_recommendations": missing,
        }

    client.close()
    return report
