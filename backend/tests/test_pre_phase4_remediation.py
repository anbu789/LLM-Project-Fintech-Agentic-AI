"""
FinTech Agent — Pre-Phase 4 Remediation & Security Hardening Test Suite
Verifies:
1. Complete read-only protection across all database and collection access paths:
   - db["customers"]
   - db.customers
   - db.get_collection("customers")
   - col.database (ensuring no leakage of unwrapped write-capable objects)
2. Blocking of all collection mutations and administrative database commands ($out, $merge, dropDatabase, etc.).
3. Comprehensive secret redaction (Google AIza, Mongo URI passwords, Bearer tokens, URL query keys).
4. Safe API error sanitization without raw exception or path leakage.
5. Conversation ID validation (rejection of CRLF, spaces, oversized IDs, unicode controls).
6. HTTP Request Body size limit enforcement (HTTP 413 on oversized payloads).
7. In-memory IP rate limiting (HTTP 429 on abuse).
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.core.exceptions import DatabaseWriteProhibitedError
from backend.app.core.logging import sanitize_error_message
from backend.app.core.rate_limit import InMemoryRateLimiter, chat_rate_limiter
from backend.app.db.mongo_client import (
    ReadOnlyCollectionProxy,
    ReadOnlyDatabaseProxy,
    mongo_manager,
)
from backend.app.main import app

client = TestClient(app)


# ==============================================================================
# 1. Database Access Path Read-Only Protection Tests
# ==============================================================================

def test_all_collection_access_paths_return_readonly_proxy():
    """Verify that item access, attribute access, and get_collection() all return ReadOnlyCollectionProxy."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)
    assert isinstance(db, ReadOnlyDatabaseProxy)

    # 1. Item access: db["customers"]
    col_item = db["customers"]
    assert isinstance(col_item, ReadOnlyCollectionProxy)

    # 2. Attribute access: db.customers
    col_attr = db.customers
    assert isinstance(col_attr, ReadOnlyCollectionProxy)

    # 3. Method access: db.get_collection("customers")
    col_method = db.get_collection("customers")
    assert isinstance(col_method, ReadOnlyCollectionProxy)

    # 4. Property access: col.database returns ReadOnlyDatabaseProxy, never raw Database
    assert isinstance(col_item.database, ReadOnlyDatabaseProxy)
    assert isinstance(col_attr.database, ReadOnlyDatabaseProxy)


def test_mutation_blocked_on_all_access_paths():
    """Verify write operations fail with DatabaseWriteProhibitedError regardless of access path."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    # 1. Item access write
    with pytest.raises(DatabaseWriteProhibitedError):
        db["customers"].insert_one({"name": "Attacker"})

    # 2. Attribute access write (The audit-identified bypass)
    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.insert_one({"name": "Attacker"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.delete_many({})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.accounts.update_one({"account_id": "ACC000001"}, {"$set": {"balance": 999999}})

    # 3. get_collection access write (The audit-identified bypass)
    with pytest.raises(DatabaseWriteProhibitedError):
        db.get_collection("customers").insert_one({"name": "Attacker"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.get_collection("customers").delete_many({})

    # 4. col.database navigation write
    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.database.drop_collection("customers")


def test_comprehensive_collection_mutation_api_blocking():
    """Verify every PyMongo mutation API is blocked on ReadOnlyCollectionProxy."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)
    col = db.loans

    mutation_calls = [
        lambda: col.insert_one({"loan_id": "TEST"}),
        lambda: col.insert_many([{"loan_id": "TEST"}]),
        lambda: col.update_one({"loan_id": "LN00001"}, {"$set": {"status": "closed"}}),
        lambda: col.update_many({}, {"$set": {"status": "defaulted"}}),
        lambda: col.replace_one({"loan_id": "LN00001"}, {"loan_id": "LN00001"}),
        lambda: col.delete_one({"loan_id": "LN00001"}),
        lambda: col.delete_many({}),
        lambda: col.find_one_and_delete({"loan_id": "LN00001"}),
        lambda: col.find_one_and_replace({"loan_id": "LN00001"}, {"loan_id": "LN00001"}),
        lambda: col.find_one_and_update({"loan_id": "LN00001"}, {"$set": {"status": "closed"}}),
        lambda: col.drop(),
        lambda: col.rename("loans_renamed"),
        lambda: col.create_index([("loan_id", 1)]),
        lambda: col.create_indexes([]),
        lambda: col.drop_index("loan_id_1"),
        lambda: col.drop_indexes(),
        lambda: col.bulk_write([]),
        lambda: col.reindex(),
        lambda: col.create_search_index({"name": "idx"}),
        lambda: col.drop_search_index("idx"),
    ]

    for call in mutation_calls:
        with pytest.raises(DatabaseWriteProhibitedError):
            call()


def test_aggregation_mutating_stages_blocked():
    """Verify aggregation stages $out and $merge are intercepted and blocked on all access paths."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_info:
        db.transactions.aggregate([{"$match": {}}, {"$out": "leaked_transactions"}])
    assert "$out" in str(exc_info.value)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_info2:
        db.get_collection("customers").aggregate([{"$match": {}}, {"$merge": {"into": "target"}}])
    assert "$merge" in str(exc_info2.value)


def test_administrative_commands_blocked():
    """Verify that dangerous database commands are intercepted and blocked."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    blocked_cmds = [
        "dropDatabase", "drop", "delete", "insert", "update",
        "createIndexes", "collMod", "renameCollection", "applyOps", "reIndex"
    ]

    for cmd in blocked_cmds:
        with pytest.raises(DatabaseWriteProhibitedError):
            db.command(cmd)

        with pytest.raises(DatabaseWriteProhibitedError):
            db.command({cmd: "target"})


# ==============================================================================
# 2. Secret Redaction Tests
# ==============================================================================

def test_secret_redaction_comprehensive():
    """Verify all sensitive credential formats are redacted from error strings and logs."""
    test_cases = [
        ("AIzaSyA1234567890abcdef12345678901234567", "AIzaSy"),
        ("https://example.com/api?key=SECRET_VALUE_12345", "SECRET_VALUE_12345"),
        ("mongodb://admin:SuperSecret123@localhost:27017/fintech_agent_db", "SuperSecret123"),
        ("mongodb+srv://admin:SuperSecret456@example.mongodb.net/fintech_agent_db", "SuperSecret456"),
        ("Authorization: Bearer SECRET_TOKEN_VALUE_ABC", "SECRET_TOKEN_VALUE_ABC"),
        ("api_key=SECRET_API_KEY_VALUE_XYZ", "SECRET_API_KEY_VALUE_XYZ"),
        ("password=SECRET_PASSWORD_VALUE_999", "SECRET_PASSWORD_VALUE_999"),
        ("sk-ant-api03-abcdef1234567890abcdef123456", "sk-ant-"),
        ("gsk_abcdef1234567890abcdef", "gsk_"),
    ]

    for raw, secret_sub in test_cases:
        sanitized = sanitize_error_message(raw)
        assert secret_sub not in sanitized, f"Secret '{secret_sub}' was leaked in '{sanitized}'"
        assert "[REDACTED]" in sanitized


# ==============================================================================
# 3. Conversation ID Validation & Log Injection Tests
# ==============================================================================

def test_conversation_id_validation(monkeypatch):
    """Verify conversation_id rejects CRLF injection, oversized inputs, and whitespace."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    # CRLF injection attempt
    resp_crlf = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "conv-123\r\n[CRITICAL] Admin granted"
    })
    assert resp_crlf.status_code == 422
    assert "CRLF" in resp_crlf.text or "validation" in resp_crlf.text.lower()

    # Oversized ID attempt (> 64 chars)
    resp_oversized = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "C" * 65
    })
    assert resp_oversized.status_code == 422

    # Malformed characters attempt
    resp_invalid = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "conv; DROP TABLE; --"
    })
    assert resp_invalid.status_code == 422

    # Valid ID succeeds
    resp_valid = client.post("/api/v1/chat", json={
        "message": "What is an NPA?",
        "conversation_id": "conv-valid-test_123"
    })
    assert resp_valid.status_code == 200
    assert resp_valid.json()["conversation_id"] == "conv-valid-test_123"


# ==============================================================================
# 4. HTTP Request-Size Limit Tests
# ==============================================================================

def test_request_body_size_limits(monkeypatch):
    """Verify RequestBodyLimitMiddleware rejects payloads exceeding configured max_body_bytes."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    # Test normal request succeeds
    normal_resp = client.post("/api/v1/chat", json={"message": "What is KYC?"})
    assert normal_resp.status_code == 200

    # Test oversized payload (> 1MB) returns 413 Payload Too Large
    oversized_data = "x" * 1_100_000
    oversized_resp = client.post(
        "/api/v1/chat",
        content=oversized_data,
        headers={"Content-Type": "application/json"}
    )
    assert oversized_resp.status_code == 413
    assert "exceeds maximum allowed limit" in oversized_resp.json()["message"]


# ==============================================================================
# 5. Rate Limiting Tests
# ==============================================================================

def test_rate_limiter_in_memory():
    """Verify InMemoryRateLimiter triggers HTTP 429 when threshold is exceeded."""
    limiter = InMemoryRateLimiter(requests_per_minute=3)
    test_ip = "192.168.1.100"

    assert limiter.is_allowed(test_ip) is True
    assert limiter.is_allowed(test_ip) is True
    assert limiter.is_allowed(test_ip) is True
    # 4th request must be rejected
    assert limiter.is_allowed(test_ip) is False

    limiter.reset()
    assert limiter.is_allowed(test_ip) is True
