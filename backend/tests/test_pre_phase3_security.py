"""
FinTech Agent — Pre-Phase 3 Security, Timeout & Hardening Test Suite
Verifies:
1. Banking read-only proxy enforcement and zero-write guarantee.
2. Interception of write aggregation stages ($out, $merge) and mutating commands.
3. Metadata database isolation and independent read/write capability.
4. MongoDB server-side authentication configuration and safe failure on missing credentials.
5. Least-privilege credential separation (rejection of identical usernames).
6. Query timeout enforcement (maxTimeMS injection and DatabaseTimeoutError translation).
7. RequestDeadline tracking, stage deadline checking, and retry eligibility.
8. Non-retryable error classification vs retryable transient errors.
9. Configuration bounds validation (timeouts, retry counts, dev auth flags).
"""

import time
import pytest
import pymongo
from pymongo.errors import AutoReconnect

from backend.app.config import Settings, settings
from backend.app.core.deadline import RequestDeadline
from backend.app.core.exceptions import (
    DatabaseCredentialsError,
    DatabaseTimeoutError,
    DatabaseWriteProhibitedError,
    FinTechAgentException,
    InvalidRequestError,
    MissingAPIKeyError,
    NonRetryableError,
    ProviderAuthenticationError,
    RequestTimeoutError,
)
from backend.app.db.mongo_client import (
    ReadOnlyCollectionProxy,
    ReadOnlyDatabaseProxy,
    ReadOnlyCursorProxy,
    mongo_manager,
    check_mongo_connection,
)


# ==============================================================================
# 1. Read-Only Banking DB & Write Prohibitions
# ==============================================================================

def test_banking_db_reads_succeed():
    """Verify that legitimate read operations on banking collections succeed."""
    banking_db = mongo_manager.get_banking_db(enforce_proxy=True)
    assert isinstance(banking_db, ReadOnlyDatabaseProxy)

    # find_one
    customer = banking_db["customers"].find_one({}, {"_id": 0, "customer_id": 1})
    assert customer is not None
    assert "customer_id" in customer

    # find with limit
    docs = list(banking_db["accounts"].find({}, {"_id": 0, "account_id": 1}).limit(5))
    assert len(docs) == 5

    # count_documents
    total_txns = banking_db["transactions"].count_documents({})
    assert total_txns == 10000

    # aggregate
    agg_res = list(banking_db["branches"].aggregate([
        {"$project": {"_id": 0, "branch_id": 1, "branch_name": 1}},
        {"$limit": 3}
    ]))
    assert len(agg_res) == 3


def test_banking_collection_write_operations_strictly_prohibited():
    """Verify that all mutating operations on ReadOnlyCollectionProxy raise DatabaseWriteProhibitedError."""
    banking_db = mongo_manager.get_banking_db(enforce_proxy=True)
    accounts = banking_db["accounts"]

    mutating_calls = [
        lambda: accounts.insert_one({"account_id": "HACK_001"}),
        lambda: accounts.insert_many([{"account_id": "HACK_002"}]),
        lambda: accounts.update_one({"account_id": "ACC000001"}, {"$set": {"balance": 999999}}),
        lambda: accounts.update_many({}, {"$set": {"status": "FROZEN"}}),
        lambda: accounts.replace_one({"account_id": "ACC000001"}, {"account_id": "ACC000001"}),
        lambda: accounts.delete_one({"account_id": "ACC000001"}),
        lambda: accounts.delete_many({"account_id": "ACC000001"}),
        lambda: accounts.find_one_and_delete({"account_id": "ACC000001"}),
        lambda: accounts.find_one_and_replace({"account_id": "ACC000001"}, {"account_id": "ACC000001"}),
        lambda: accounts.find_one_and_update({"account_id": "ACC000001"}, {"$set": {"balance": 0}}),
        lambda: accounts.drop(),
        lambda: accounts.rename("accounts_renamed"),
        lambda: accounts.create_index([("account_id", 1)]),
        lambda: accounts.drop_index("account_id_1"),
        lambda: accounts.bulk_write([]),
    ]

    for call in mutating_calls:
        with pytest.raises(DatabaseWriteProhibitedError) as exc_info:
            call()
        assert "strictly prohibited" in str(exc_info.value)
        # Also verify backward compatibility: must be an instance of PermissionError
        assert isinstance(exc_info.value, PermissionError)
        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "BANKING_WRITE_PROHIBITED"


def test_banking_aggregation_write_stages_prohibited():
    """Verify that $out and $merge aggregation stages are intercepted and blocked."""
    banking_db = mongo_manager.get_banking_db(enforce_proxy=True)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_out:
        banking_db["accounts"].aggregate([
            {"$match": {"status": "ACTIVE"}},
            {"$out": "unauthorized_export"}
        ])
    assert "$out" in str(exc_out.value)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_merge:
        banking_db["customers"].aggregate([
            {"$match": {"risk_category": "HIGH"}},
            {"$merge": {"into": "target_col"}}
        ])
    assert "$merge" in str(exc_merge.value)


def test_banking_database_level_mutations_prohibited():
    """Verify database-level mutations (drop_collection, create_collection, command) are blocked."""
    banking_db = mongo_manager.get_banking_db(enforce_proxy=True)

    with pytest.raises(DatabaseWriteProhibitedError):
        banking_db.drop_collection("accounts")

    with pytest.raises(DatabaseWriteProhibitedError):
        banking_db.create_collection("malicious_col")

    with pytest.raises(DatabaseWriteProhibitedError):
        banking_db.command("dropDatabase")

    with pytest.raises(DatabaseWriteProhibitedError):
        banking_db.command({"drop": "accounts"})


# ==============================================================================
# 2. Metadata Database Isolation & Read/Write Capability
# ==============================================================================

def test_metadata_database_isolation_and_write_capability():
    """Verify agent_metadata_db operates independently and allows necessary writes."""
    metadata_db = mongo_manager.get_metadata_db()
    assert metadata_db.name == settings.MONGO_METADATA_DB

    # Test collection for verification
    test_col = metadata_db["_test_pre_phase3_audit"]

    # Write operation must succeed on metadata DB
    insert_res = test_col.insert_one({
        "audit_id": "audit-001",
        "action": "test_verification",
        "timestamp": time.time()
    })
    assert insert_res.inserted_id is not None

    # Read back document
    found = test_col.find_one({"audit_id": "audit-001"})
    assert found is not None
    assert found["action"] == "test_verification"

    # Cleanup test record
    delete_res = test_col.delete_one({"audit_id": "audit-001"})
    assert delete_res.deleted_count == 1

    # Drop test collection
    test_col.drop()


def test_banking_db_cannot_be_mutated_via_banking_manager():
    """Verify that get_banking_db never returns a writeable database handle."""
    banking_db = mongo_manager.get_banking_db()
    assert isinstance(banking_db, ReadOnlyDatabaseProxy)
    with pytest.raises(DatabaseWriteProhibitedError):
        banking_db["cards"].insert_one({"test": "value"})


# ==============================================================================
# 3. Security Configuration & Credential Validation
# ==============================================================================

def test_auth_enabled_requires_both_credentials():
    """Verify that MONGO_AUTH_ENABLED=True fails if credentials are missing."""
    with pytest.raises(ValueError) as exc:
        Settings(
            MONGO_AUTH_ENABLED=True,
            MONGO_READONLY_USERNAME=None,
            MONGO_READONLY_PASSWORD=None,
            MONGO_METADATA_USERNAME=None,
            MONGO_METADATA_PASSWORD=None,
        )
    assert "MONGO_READONLY_USERNAME or MONGO_READONLY_PASSWORD is not configured" in str(exc.value)


def test_auth_enabled_rejects_identical_credentials():
    """Verify that MONGO_AUTH_ENABLED=True rejects identical usernames (least privilege violation)."""
    with pytest.raises(ValueError) as exc:
        Settings(
            MONGO_AUTH_ENABLED=True,
            MONGO_READONLY_USERNAME="shared_admin",
            MONGO_READONLY_PASSWORD="password123",
            MONGO_METADATA_USERNAME="shared_admin",
            MONGO_METADATA_PASSWORD="password123",
        )
    assert "Least-privilege violation" in str(exc.value)


def test_disallowing_unauthenticated_dev_fails_without_auth():
    """Verify that setting ALLOW_UNAUTHENTICATED_DEV=False without auth enabled raises error."""
    with pytest.raises(ValueError) as exc:
        Settings(
            MONGO_AUTH_ENABLED=False,
            ALLOW_UNAUTHENTICATED_DEV=False,
        )
    assert "Unauthenticated MongoDB access is disallowed" in str(exc.value)


def test_authenticated_uri_generation():
    """Verify proper URI formatting with authentication credentials and authSource."""
    custom_settings = Settings(
        MONGO_AUTH_ENABLED=True,
        MONGO_READONLY_USERNAME="fintech_reader",
        MONGO_READONLY_PASSWORD="ReadPassword!123",
        MONGO_METADATA_USERNAME="agent_metadata_writer",
        MONGO_METADATA_PASSWORD="WritePassword!456",
        MONGO_AUTH_SOURCE="admin"
    )

    ro_uri = custom_settings.get_banking_uri()
    assert "fintech_reader:ReadPassword%21123@" in ro_uri
    assert "/fintech_agent_db?authSource=admin" in ro_uri

    rw_uri = custom_settings.get_metadata_uri()
    assert "agent_metadata_writer:WritePassword%21456@" in rw_uri
    assert "/agent_metadata_db?authSource=admin" in rw_uri


# ==============================================================================
# 4. Timeout Enforcement & Translation
# ==============================================================================

def test_query_timeout_ms_native_enforcement():
    """Verify that a native MongoDB query exceeding maxTimeMS translates to DatabaseTimeoutError."""
    banking_db = mongo_manager.get_banking_db(enforce_proxy=True)

    # Use a correlated $lookup query on 10,000 transactions with maxTimeMS=5 to guarantee timeout
    with pytest.raises(DatabaseTimeoutError) as exc_info:
        list(banking_db["transactions"].aggregate([
            {"$match": {"amount": {"$gt": 0}}},
            {"$lookup": {
                "from": "transactions",
                "let": {"amt": "$amount"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$amount", "$$amt"]}}}
                ],
                "as": "matches"
            }}
        ], maxTimeMS=5))

    assert exc_info.value.status_code == 504
    assert exc_info.value.error_code == "DATABASE_TIMEOUT"
    assert "Database query timed out" in exc_info.value.message


def test_timeout_bounds_validation():
    """Verify Settings rejects invalid QUERY_TIMEOUT_MS and REQUEST_TIMEOUT_SECONDS."""
    with pytest.raises(ValueError):
        Settings(QUERY_TIMEOUT_MS=0)

    with pytest.raises(ValueError):
        Settings(QUERY_TIMEOUT_MS=150000)  # Exceeds max 120000

    with pytest.raises(ValueError):
        Settings(REQUEST_TIMEOUT_SECONDS=0)

    with pytest.raises(ValueError):
        Settings(REQUEST_TIMEOUT_SECONDS=600)  # Exceeds max 300

    with pytest.raises(ValueError):
        Settings(MAX_RETRY_ATTEMPTS=-1)

    with pytest.raises(ValueError):
        Settings(MAX_RETRY_ATTEMPTS=15)  # Exceeds max 10


# ==============================================================================
# 5. RequestDeadline & Retry Policy
# ==============================================================================

def test_request_deadline_tracking_and_expiry():
    """Verify RequestDeadline correctly calculates elapsed time and detects expiry."""
    deadline = RequestDeadline(timeout_seconds=0.1, request_id="req-test-01")
    assert deadline.timeout_seconds == 0.1
    assert deadline.request_id == "req-test-01"
    assert not deadline.is_expired()
    assert deadline.remaining_seconds() > 0

    # Let deadline expire
    time.sleep(0.12)
    assert deadline.is_expired()
    assert deadline.remaining_seconds() == 0.0

    with pytest.raises(RequestTimeoutError) as exc_info:
        deadline.check_deadline("llm_dispatch")

    assert exc_info.value.status_code == 504
    assert exc_info.value.error_code == "REQUEST_TIMEOUT"
    assert "llm_dispatch" in exc_info.value.message


def test_request_deadline_can_retry():
    """Verify can_retry logic respects minimum time needed for retries."""
    deadline = RequestDeadline(timeout_seconds=5.0)
    assert deadline.can_retry(min_needed_seconds=2.0) is True

    # Deadline with only 1.0s remaining cannot retry when 2.0s are needed
    tight_deadline = RequestDeadline(timeout_seconds=1.0)
    assert tight_deadline.can_retry(min_needed_seconds=2.0) is False


def test_error_retryability_classification():
    """Verify that deterministic errors are non-retryable and transient errors are retryable."""
    # Non-retryable errors
    non_retryables = [
        DatabaseWriteProhibitedError("insert_one"),
        DatabaseCredentialsError("Invalid credentials"),
        MissingAPIKeyError("anthropic"),
        ProviderAuthenticationError("openai"),
        InvalidRequestError("Payload invalid"),
        NonRetryableError("Syntax error in query"),
        PermissionError("Access denied"),
        ValueError("Invalid format"),
        TypeError("Unexpected type"),
    ]

    for err in non_retryables:
        assert RequestDeadline.is_retryable_error(err) is False, f"Expected {type(err).__name__} to be non-retryable"

    # Retryable transient errors
    retryables = [
        AutoReconnect("Connection reset by peer"),
        Exception("Temporary network glitch"),
    ]

    for err in retryables:
        assert RequestDeadline.is_retryable_error(err) is True, f"Expected {type(err).__name__} to be retryable"


# ==============================================================================
# 6. MongoDB Security Status Introspection
# ==============================================================================

def test_mongo_security_status_introspection():
    """Verify mongo_manager.get_security_status() returns complete posture metadata."""
    status = mongo_manager.get_security_status()
    expected_keys = {
        "auth_enabled", "allow_unauthenticated_dev", "banking_db", "metadata_db",
        "banking_user_configured", "metadata_user_configured", "credentials_isolated",
        "query_timeout_ms", "request_timeout_seconds", "max_retry_attempts",
        "read_only_proxy_enforced"
    }
    assert expected_keys.issubset(set(status.keys()))
    assert status["banking_db"] == "fintech_agent_db"
    assert status["metadata_db"] == "agent_metadata_db"
    assert status["read_only_proxy_enforced"] is True
    assert status["query_timeout_ms"] == 15000
    assert status["request_timeout_seconds"] == 30
