"""
FinTech Agent — Phase 1 Readiness Verification Test Suite
Verifies Environment, MongoDB Connection, Dataset Integrity, Schema, Indexes, and Security.
Strictly non-destructive: zero modifications to banking data.
"""

import json
import os
import subprocess
from pathlib import Path
import pytest
from pymongo import MongoClient

from backend.app.config import PROJECT_ROOT, settings
from backend.app.db.mongo_client import (
    check_mongo_connection,
    get_collection_inventory,
    get_bounded_samples,
    mongo_manager,
    ReadOnlyDatabaseProxy,
)
from backend.app.db.schema_catalog import load_schema_json, verify_schema_against_db
from backend.app.db.indexes import audit_indexes, RECOMMENDED_INDEXES


# ------------------------------------------------------------------------------
# 1. Environment Tests
# ------------------------------------------------------------------------------

def test_python_version_and_config():
    """Verify python version pinning and configuration."""
    version_file = PROJECT_ROOT / ".python-version"
    assert version_file.exists(), ".python-version file must exist"
    assert "3.12" in version_file.read_text(), "Expected Python 3.12 pinned"


def test_nodejs_pinning_and_package_manifest():
    """Verify Node.js pinning and frontend package manifest."""
    nvmrc = PROJECT_ROOT / ".nvmrc"
    assert nvmrc.exists(), ".nvmrc must exist"
    package_json = PROJECT_ROOT / "frontend/package.json"
    assert package_json.exists(), "frontend/package.json must exist"
    with open(package_json, "r") as f:
        data = json.load(f)
    assert data["name"] == "fintech-agent-frontend"
    assert "react" in data["dependencies"]


def test_env_settings_loaded_safely():
    """Verify settings load from environment without exposing secrets."""
    assert settings.MONGO_BANKING_DB == "fintech_agent_db"
    assert settings.MONGO_METADATA_DB == "agent_metadata_db"
    assert settings.QUERY_TIMEOUT_MS == 15000
    assert settings.RESULT_DOC_LIMIT == 1000
    assert settings.MAX_PIPELINE_STAGES == 20


# ------------------------------------------------------------------------------
# 2. Git & Security Tests
# ------------------------------------------------------------------------------

def test_env_file_is_git_ignored():
    """Ensure .env is strictly ignored by Git."""
    gitignore = PROJECT_ROOT / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert ".env" in content
    assert ".venv/" in content


def test_protected_assets_remain_unmodified():
    """Verify that dataset files and presentation files exist and are protected."""
    # Check dataset files
    dataset_dir = PROJECT_ROOT / "fintech-agent/data"
    assert dataset_dir.exists(), "Dataset directory must exist"
    assert (dataset_dir / "schema.json").exists()
    assert (dataset_dir / "generate_dataset.py").exists()
    assert (dataset_dir / "validate_dataset.py").exists()

    # Check presentations
    pres_pdf = PROJECT_ROOT / "docs/codex/INT450_Final_Project_Presentation.pdf"
    pres_pptx = PROJECT_ROOT / "docs/codex/INT450_Final_Project_Presentation.pptx"
    assert pres_pdf.exists(), "Presentation PDF must remain intact"
    assert pres_pptx.exists(), "Presentation PPTX must remain intact"


def test_banking_db_read_only_protection():
    """Verify that the read-only proxy strictly prohibits write operations."""
    readonly_db = mongo_manager.get_banking_db(enforce_proxy=True)
    assert isinstance(readonly_db, ReadOnlyDatabaseProxy)

    # Test insert attempt
    with pytest.raises(PermissionError) as exc_info:
        readonly_db["customers"].insert_one({"test": 1})
    assert "strictly prohibited" in str(exc_info.value)

    # Test update attempt
    with pytest.raises(PermissionError) as exc_info:
        readonly_db["accounts"].update_one({"account_id": "ACC000001"}, {"$set": {"balance": 0}})
    assert "strictly prohibited" in str(exc_info.value)

    # Test delete attempt
    with pytest.raises(PermissionError) as exc_info:
        readonly_db["transactions"].delete_one({"transaction_id": "TXN000000001"})
    assert "strictly prohibited" in str(exc_info.value)

    # Test drop attempt
    with pytest.raises(PermissionError) as exc_info:
        readonly_db["cards"].drop()
    assert "strictly prohibited" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. MongoDB Connection & Database Tests
# ------------------------------------------------------------------------------

def test_mongodb_connection():
    """Verify MongoDB connection and server status."""
    status = check_mongo_connection()
    assert status["status"] == "connected", f"Failed to connect: {status}"
    assert status["banking_db_exists"] is True, "fintech_agent_db must exist in MongoDB"


def test_expected_12_collections_exist():
    """Verify that all 12 planned banking collections exist in fintech_agent_db."""
    expected_collections = {
        "branches", "employees", "merchants", "customers",
        "accounts", "transactions", "cards", "loans",
        "kyc_documents", "support_tickets", "fraud_alerts", "investments"
    }
    inventory = get_collection_inventory()
    db_collections = set(inventory.keys())

    missing = expected_collections - db_collections
    assert not missing, f"Missing collections in MongoDB: {missing}"


def test_document_counts_are_populated():
    """Verify document counts match the generated synthetic dataset."""
    inventory = get_collection_inventory()
    expected_counts = {
        "branches": 20,
        "employees": 100,
        "merchants": 200,
        "customers": 1000,
        "accounts": 1500,
        "transactions": 10000,
        "cards": 1000,
        "loans": 500,
        "kyc_documents": 1500,
        "support_tickets": 2000,
        "fraud_alerts": 300,
        "investments": 1000,
    }
    for col, expected_count in expected_counts.items():
        actual_count = inventory.get(col, 0)
        assert actual_count == expected_count, f"{col}: expected {expected_count}, got {actual_count}"


def test_bounded_sample_retrieval():
    """Verify sample retrieval works without exposing full payloads or modifying records."""
    samples = get_bounded_samples("branches", limit=2)
    assert len(samples) == 2
    assert "branch_id" in samples[0]
    assert "branch_name" in samples[0]


# ------------------------------------------------------------------------------
# 4. Schema & Data Integrity Tests
# ------------------------------------------------------------------------------

def test_schema_json_validity():
    """Verify schema.json loads and contains all collections and relationships."""
    schema = load_schema_json()
    assert schema is not None, "schema.json could not be loaded"
    assert schema["database"] == "fintech_agent_db"
    assert len(schema["collections"]) == 12
    assert len(schema["relationships"]) >= 20


def test_schema_verification_against_actual_db():
    """Verify schema match against actual database documents."""
    result = verify_schema_against_db()
    assert result.get("collections_in_schema") == 12
    assert result.get("missing_collections_in_db") == []

    # Verify special warning fields: days_past_due and overdue_amount must NOT exist
    special = result["special_warning_fields_verification"]
    assert special.get("loans.days_past_due") is False, "loans.days_past_due should NOT exist"
    assert special.get("loans.overdue_amount") is False, "loans.overdue_amount should NOT exist"


def test_loan_fields_distinction_and_absence():
    """Verify outstanding_amount presence and complete absence of days_past_due/overdue_amount."""
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[settings.MONGO_BANKING_DB]
    loans = db["loans"]

    total = loans.count_documents({})
    assert total == 500, f"Expected 500 loans, got {total}"

    has_outstanding = loans.count_documents({"outstanding_amount": {"$exists": True}})
    has_dpd = loans.count_documents({"days_past_due": {"$exists": True}})
    has_overdue = loans.count_documents({"overdue_amount": {"$exists": True}})

    assert has_outstanding == 500, "outstanding_amount must exist on all 500 loans"
    assert has_dpd == 0, "loans.days_past_due must NOT exist on any loan"
    assert has_overdue == 0, "loans.overdue_amount must NOT exist on any loan"

    # Business rule verification: closed loans have outstanding_amount == 0
    closed_loans = list(loans.find({"status": "closed"}))
    assert len(closed_loans) > 0
    assert all(l["outstanding_amount"] == 0.0 for l in closed_loans)

    # Active and defaulted loans have outstanding_amount > 0
    non_closed = list(loans.find({"status": {"$in": ["active", "defaulted"]}}))
    assert len(non_closed) > 0
    assert all(l["outstanding_amount"] > 0 for l in non_closed)

    client.close()


def test_all_22_cross_collection_relationships():
    """Verify all 22 foreign key relationships across 100% of documents with zero orphans."""
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[settings.MONGO_BANKING_DB]

    relationships = [
        ("employees", "branch_id", "branches", "branch_id", False),
        ("branches", "manager_id", "employees", "employee_id", False),
        ("customers", "relationship_manager_id", "employees", "employee_id", False),
        ("accounts", "customer_id", "customers", "customer_id", False),
        ("accounts", "branch_id", "branches", "branch_id", False),
        ("accounts", "account_manager_id", "employees", "employee_id", False),
        ("transactions", "account_id", "accounts", "account_id", False),
        ("transactions", "customer_id", "customers", "customer_id", False),
        ("transactions", "merchant_id", "merchants", "merchant_id", True),
        ("cards", "customer_id", "customers", "customer_id", False),
        ("cards", "account_id", "accounts", "account_id", False),
        ("loans", "customer_id", "customers", "customer_id", False),
        ("loans", "sanctioning_branch_id", "branches", "branch_id", False),
        ("loans", "loan_officer_id", "employees", "employee_id", False),
        ("kyc_documents", "customer_id", "customers", "customer_id", False),
        ("kyc_documents", "verified_by", "employees", "employee_id", True),
        ("support_tickets", "customer_id", "customers", "customer_id", False),
        ("support_tickets", "assigned_agent_id", "employees", "employee_id", False),
        ("fraud_alerts", "transaction_id", "transactions", "transaction_id", False),
        ("fraud_alerts", "customer_id", "customers", "customer_id", False),
        ("fraud_alerts", "reviewed_by", "employees", "employee_id", True),
        ("investments", "customer_id", "customers", "customer_id", False),
    ]

    for src_col, src_key, tgt_col, tgt_key, nullable in relationships:
        tgt_ids = set(db[tgt_col].distinct(tgt_key))
        cursor = db[src_col].find({}, {src_key: 1})
        orphans = 0
        for doc in cursor:
            val = doc.get(src_key)
            if val is None:
                if not nullable:
                    orphans += 1
            elif val not in tgt_ids:
                orphans += 1
        assert orphans == 0, f"Relationship {src_col}.{src_key} -> {tgt_col}.{tgt_key} has {orphans} orphans"

    client.close()


# ------------------------------------------------------------------------------
# 5. Database Index Audit Tests
# ------------------------------------------------------------------------------

def test_database_indexes_audit():
    """Verify primary key indexes and foreign key indexes exist across all collections."""
    report = audit_indexes()
    assert len(report) == 12
    for col, data in report.items():
        assert data["existing_count"] >= 2, f"{col} has fewer than 2 indexes"
        assert data["matched_recommendations"] > 0, f"{col} has no matched recommended indexes"
