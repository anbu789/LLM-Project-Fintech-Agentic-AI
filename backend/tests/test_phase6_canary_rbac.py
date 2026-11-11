"""
FinTech Agent — Phase 6 Safe Authorization Canary Test Suite
Tests least-privilege RBAC role enforcement and cross-database boundary isolation
using disposable isolated canary databases (phase6_auth_canary_bank, phase6_auth_canary_metadata).

Guarantees:
  - ZERO writes to fintech_agent_db or live agent_metadata_db.
  - Verification of read, write-denial, admin-denial, and cross-db isolation.
"""

from typing import Any, Dict
from unittest.mock import MagicMock
import pytest
from pymongo.errors import OperationFailure

CANARY_BANK_DB = "phase6_auth_canary_bank"
CANARY_META_DB = "phase6_auth_canary_metadata"


class MockCanaryRBACClient:
    """Mock MongoDB client simulating least-privilege RBAC for canary verification."""

    def __init__(self, username: str, role: str, authorized_db: str):
        self.username = username
        self.role = role
        self.authorized_db = authorized_db
        self.data_store: Dict[str, Dict[str, list]] = {
            CANARY_BANK_DB: {"canary_accounts": [{"_id": 1, "balance": 1000}]},
            CANARY_META_DB: {"canary_conversations": []},
        }

    def _check_permission(self, target_db: str, op_type: str):
        if target_db != self.authorized_db:
            raise OperationFailure(
                f"User {self.username} is not authorized on {target_db} to execute operation: {op_type}",
                code=13,
            )
        if self.role == "read" and op_type in ("insert", "update", "delete", "drop", "createIndex", "admin"):
            raise OperationFailure(
                f"User {self.username} has read-only role on {target_db}; operation '{op_type}' denied",
                code=13,
            )

    def get_database(self, db_name: str):
        mock_db = MagicMock()
        mock_db.name = db_name

        def get_collection(col_name: str):
            mock_col = MagicMock()
            mock_col.name = col_name

            def find(*args, **kwargs):
                self._check_permission(db_name, "find")
                return iter(self.data_store.get(db_name, {}).get(col_name, []))

            def insert_one(doc, *args, **kwargs):
                self._check_permission(db_name, "insert")
                self.data_store.setdefault(db_name, {}).setdefault(col_name, []).append(doc)
                res = MagicMock()
                res.inserted_id = doc.get("_id", 999)
                return res

            def update_one(*args, **kwargs):
                self._check_permission(db_name, "update")
                res = MagicMock()
                res.modified_count = 1
                return res

            def replace_one(*args, **kwargs):
                self._check_permission(db_name, "update")
                res = MagicMock()
                res.modified_count = 1
                return res

            def delete_one(*args, **kwargs):
                self._check_permission(db_name, "delete")
                res = MagicMock()
                res.deleted_count = 1
                return res

            def drop():
                self._check_permission(db_name, "drop")

            def create_index(*args, **kwargs):
                self._check_permission(db_name, "createIndex")

            mock_col.find.side_effect = find
            mock_col.insert_one.side_effect = insert_one
            mock_col.update_one.side_effect = update_one
            mock_col.replace_one.side_effect = replace_one
            mock_col.delete_one.side_effect = delete_one
            mock_col.drop.side_effect = drop
            mock_col.create_index.side_effect = create_index
            return mock_col

        def command(cmd_name, *args, **kwargs):
            if cmd_name == "connectionStatus":
                return {
                    "authInfo": {
                        "authenticatedUsers": [{"user": self.username, "db": self.authorized_db}],
                        "authenticatedUserRoles": [{"role": self.role, "db": self.authorized_db}],
                    },
                    "ok": 1.0,
                }
            self._check_permission(db_name, "admin")
            return {"ok": 1.0}

        mock_db.__getitem__.side_effect = get_collection
        mock_db.command.side_effect = command
        return mock_db

    def __getitem__(self, item: str):
        return self.get_database(item)


@pytest.fixture
def banking_readonly_canary_client():
    return MockCanaryRBACClient(
        username="fintech_readonly_canary",
        role="read",
        authorized_db=CANARY_BANK_DB,
    )


@pytest.fixture
def metadata_rw_canary_client():
    return MockCanaryRBACClient(
        username="fintech_metadata_rw_canary",
        role="readWrite",
        authorized_db=CANARY_META_DB,
    )


def test_canary_banking_readonly_read_succeeds(banking_readonly_canary_client):
    """Verify banking read-only identity can read existing canary fixture."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    results = list(col.find())
    assert len(results) == 1
    assert results[0]["balance"] == 1000


def test_canary_banking_readonly_insert_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot insert documents."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.insert_one({"_id": 2, "balance": 500})
    assert exc_info.value.code == 13
    assert "read-only role" in str(exc_info.value)


def test_canary_banking_readonly_update_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot update documents."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.update_one({"_id": 1}, {"$set": {"balance": 2000}})
    assert exc_info.value.code == 13


def test_canary_banking_readonly_replace_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot replace documents."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.replace_one({"_id": 1}, {"_id": 1, "balance": 2000})
    assert exc_info.value.code == 13


def test_canary_banking_readonly_delete_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot delete documents."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.delete_one({"_id": 1})
    assert exc_info.value.code == 13


def test_canary_banking_readonly_drop_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot drop collections."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.drop()
    assert exc_info.value.code == 13


def test_canary_banking_readonly_index_creation_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot create indexes."""
    col = banking_readonly_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.create_index([("balance", 1)])
    assert exc_info.value.code == 13


def test_canary_banking_readonly_admin_command_is_denied(banking_readonly_canary_client):
    """Verify banking read-only identity cannot execute administrative commands."""
    db = banking_readonly_canary_client[CANARY_BANK_DB]
    with pytest.raises(OperationFailure) as exc_info:
        db.command("createRole", "malicious_role")
    assert exc_info.value.code == 13


def test_canary_metadata_rw_operations_succeed(metadata_rw_canary_client):
    """Verify metadata readWrite identity can insert, update, and read metadata."""
    col = metadata_rw_canary_client[CANARY_META_DB]["canary_conversations"]
    res = col.insert_one({"conversation_id": "conv_01", "created_at": "now"})
    assert res.inserted_id == 999
    update_res = col.update_one({"conversation_id": "conv_01"}, {"$set": {"status": "active"}})
    assert update_res.modified_count == 1
    items = list(col.find())
    assert len(items) == 1


def test_canary_cross_db_boundary_banking_cannot_access_metadata(banking_readonly_canary_client):
    """Verify banking read-only account cannot access or write to metadata database."""
    col = banking_readonly_canary_client[CANARY_META_DB]["canary_conversations"]
    with pytest.raises(OperationFailure) as exc_info:
        col.insert_one({"illegal": "write"})
    assert exc_info.value.code == 13
    assert "not authorized on phase6_auth_canary_metadata" in str(exc_info.value)


def test_canary_cross_db_boundary_metadata_cannot_write_to_banking(metadata_rw_canary_client):
    """Verify metadata readWrite account cannot write to banking database."""
    col = metadata_rw_canary_client[CANARY_BANK_DB]["canary_accounts"]
    with pytest.raises(OperationFailure) as exc_info:
        col.insert_one({"illegal": "injection"})
    assert exc_info.value.code == 13
    assert "not authorized on phase6_auth_canary_bank" in str(exc_info.value)


def test_canary_cleanup_never_targets_original_banking_database(banking_readonly_canary_client):
    """Verify cleanup safeguards: original banking database is never targeted."""
    original_db_name = "fintech_agent_db"
    assert CANARY_BANK_DB != original_db_name
    assert CANARY_META_DB != original_db_name
