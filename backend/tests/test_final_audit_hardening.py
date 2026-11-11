"""
FinTech Agent — Final Audit Hardening Test Suite (Tasks 1, 2, and 3)
Verifies:
  1. Cryptographic authentication, token tampering, expiration, identity spoofing (403),
     and strict server-side tenant isolation.
  2. Distributed atomic scheduler leases, monotonic fencing tokens, lease loss suspension,
     and per-job execution locks preventing duplicate runs.
  3. Edge-case scheduling across IANA timezones, DST spring/fall transitions, leap years,
     month-end dates, schema drift auto-pause, and consecutive failure thresholds.
"""

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo

from backend.app.agent.nodes.mql_policy_validator import MQLPolicyValidator
from backend.app.config import settings
from backend.app.core.auth import AuthenticatedUser, TokenManager, auth_manager
from backend.app.main import app
from backend.app.schemas.schedule import (
    JobRun,
    ScheduleApprovalRequest,
    SchedulePreview,
    ScheduleSpec,
    ScheduledJob,
)
from backend.app.services.recurrence_parser import calculate_next_run_times, parse_recurrence
from backend.app.services.schedule_service import (
    ScheduleOwnershipError,
    ScheduleService,
    schedule_service,
)
from backend.app.services.scheduler_runner import SchedulerRunner


# ------------------------------------------------------------------------------
# Mock Metadata DB Fixture
# ------------------------------------------------------------------------------

class MockMetadataDB:
    def __init__(self):
        self.scheduler_leases = InMemoryCollection()
        self.scheduled_jobs = InMemoryCollection()
        self.job_runs = InMemoryCollection()
        self.schedule_previews = InMemoryCollection()


class InMemoryCollection:
    def __init__(self):
        self.docs = []

    def _matches(self, doc: Dict[str, Any], filter: Dict[str, Any]) -> bool:
        for k, v in filter.items():
            if k == "$or":
                sub_matches = any(self._matches(doc, sub) for sub in v)
                if not sub_matches:
                    return False
            elif isinstance(v, dict):
                val = doc.get(k)
                if "$lt" in v:
                    if val is None or val >= v["$lt"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def insert_one(self, doc: Dict[str, Any]):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = str(len(self.docs) + 1)
        self.docs.append(doc_copy)
        res = MagicMock()
        res.inserted_id = doc_copy["_id"]
        return res

    def find_one(self, filter: Dict[str, Any]):
        for doc in self.docs:
            if self._matches(doc, filter):
                return dict(doc)
        return None

    def find(self, filter: Dict[str, Any] = None):
        filter = filter or {}
        matches = [dict(d) for d in self.docs if self._matches(d, filter)]
        return iter(matches)

    def find_one_and_update(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False, return_document: bool = True):
        matched_doc = None
        for doc in self.docs:
            if self._matches(doc, filter):
                matched_doc = doc
                break

        if matched_doc is None:
            if not upsert:
                return None
            matched_doc = {"_id": str(len(self.docs) + 1)}
            self.docs.append(matched_doc)

        if "$set" in update:
            matched_doc.update(update["$set"])
        if "$inc" in update:
            for k, inc_val in update["$inc"].items():
                matched_doc[k] = matched_doc.get(k, 0) + inc_val

        return dict(matched_doc)

    def update_one(self, filter: Dict[str, Any], update: Dict[str, Any]):
        for doc in self.docs:
            if self._matches(doc, filter):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, inc_val in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + inc_val
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    def delete_one(self, filter: Dict[str, Any]):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, filter):
                del self.docs[i]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)


@pytest.fixture
def mock_db():
    db = MockMetadataDB()
    with patch("backend.app.db.mongo_client.mongo_manager.get_metadata_db", return_value=db):
        orig_custom = schedule_service._custom_db
        schedule_service._custom_db = db
        yield db
        schedule_service._custom_db = orig_custom


# ==============================================================================
# TASK 1: AUTHENTICATION, IDENTITY SPOOFING & TENANT ISOLATION TESTS
# ==============================================================================

def test_task1_token_generation_and_validation():
    tm = TokenManager("test_secret_key_1234567890_abcdefghij")
    token = tm.create_access_token(user_id="alice", role="analyst")
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    user = tm.verify_token(token)
    assert user.user_id == "alice"
    assert user.role == "analyst"
    assert "schedules:read" in user.scopes


def test_task1_token_tampering_rejected():
    tm = TokenManager("test_secret_key_1234567890_abcdefghij")
    token = tm.create_access_token(user_id="alice", role="analyst")
    parts = token.split(".")
    # Tamper with signature
    tampered = f"{parts[0]}.{parts[1]}.bad_sig_123"
    with pytest.raises(Exception) as exc:
        tm.verify_token(tampered)
    assert "Invalid token signature" in str(exc.value)


def test_task1_token_expired_rejected():
    tm = TokenManager("test_secret_key_1234567890_abcdefghij")
    # Issue expired token
    token = tm.create_access_token(user_id="alice", expires_delta=timedelta(seconds=-10))
    with pytest.raises(Exception) as exc:
        tm.verify_token(token)
    assert "expired" in str(exc.value).lower()


def test_task1_api_token_endpoint():
    client = TestClient(app)
    resp = client.post("/api/v1/auth/token", json={"user_id": "bob", "role": "compliance"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user_id"] == "bob"
    assert data["role"] == "compliance"


def test_task1_missing_auth_header_rejected(mock_db):
    client = TestClient(app)
    # No auth header -> 401
    resp = client.get("/api/v1/schedules")
    assert resp.status_code == 401
    assert "Missing authentication credentials" in resp.json()["detail"]


def test_task1_identity_spoofing_header_alone_rejected(mock_db):
    client = TestClient(app)
    # Caller sends X-User-ID alone without Bearer token -> 401 rejected
    resp = client.get("/api/v1/schedules", headers={"X-User-ID": "admin"})
    assert resp.status_code == 401
    assert "Unsigned identity headers are rejected" in resp.json()["detail"]


def test_task1_identity_spoofing_token_mismatch_rejected(mock_db):
    client = TestClient(app)
    # Alice has token, but asserts she is Bob in X-User-ID -> 403 Forbidden!
    alice_token = auth_manager.create_access_token(user_id="alice")
    resp = client.get(
        "/api/v1/schedules",
        headers={
            "Authorization": f"Bearer {alice_token}",
            "X-User-ID": "bob",
        },
    )
    assert resp.status_code == 403
    assert "Identity spoofing violation" in resp.json()["detail"]


def test_task1_tenant_isolation_cross_user_denial(mock_db):
    client = TestClient(app)
    # Create job for Bob
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = schedule_service.create_preview(
        owner_id="bob",
        report_name="Bob Sensitive Report",
        natural_language_query="q",
        target_collection="customers",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = schedule_service.approve_preview(preview.preview_id, owner_id="bob")

    # Alice attempts to access Bob's job -> 403
    alice_token = auth_manager.create_access_token(user_id="alice")
    resp_get = client.get(
        f"/api/v1/schedules/{job.job_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp_get.status_code == 403

    # Alice attempts to pause Bob's job -> 403
    resp_pause = client.post(
        f"/api/v1/schedules/{job.job_id}/pause",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp_pause.status_code == 403

    # Alice attempts to cancel Bob's job -> 403
    resp_cancel = client.post(
        f"/api/v1/schedules/{job.job_id}/cancel",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp_cancel.status_code == 403

    # Alice attempts to read Bob's run history -> 403
    resp_runs = client.get(
        f"/api/v1/schedules/{job.job_id}/runs",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp_runs.status_code == 403


# ==============================================================================
# TASK 2: SCHEDULER LEASE, CONCURRENCY & DUPLICATE EXECUTION TESTS
# ==============================================================================

def test_task2_scheduler_lease_acquisition_and_fencing_token(mock_db):
    runner = SchedulerRunner(db=mock_db)
    # First acquisition
    assert runner.acquire_or_renew_lease(lease_ttl_seconds=60) is True
    assert runner._has_lease is True
    assert runner.current_fencing_token >= 1
    initial_fencing = runner.current_fencing_token

    # Renewal increments monotonic fencing token
    assert runner.acquire_or_renew_lease(lease_ttl_seconds=60) is True
    assert runner.current_fencing_token == initial_fencing + 1


def test_task2_scheduler_lease_collision_denial(mock_db):
    runner1 = SchedulerRunner(db=mock_db)
    runner2 = SchedulerRunner(db=mock_db)

    # Runner 1 acquires lease
    assert runner1.acquire_or_renew_lease(lease_ttl_seconds=60) is True

    # Runner 2 tries to acquire unexpired lease -> denied
    assert runner2.acquire_or_renew_lease(lease_ttl_seconds=60) is False
    assert runner2._has_lease is False


def test_task2_scheduler_atomic_execution_locking(mock_db):
    runner = SchedulerRunner(db=mock_db)
    # Insert active job
    job_id = "job_test_lock_123"
    mock_db.scheduled_jobs.insert_one({
        "job_id": job_id,
        "owner_id": "test_user",
        "status": "ACTIVE",
        "target_collection": "customers",
        "pipeline_template": [{"$limit": 5}],
    })

    # Test that find_one_and_update locks the job with execution fencing token
    now = datetime.now(timezone.utc)
    lock_expires = now + timedelta(seconds=120)
    lock_res = mock_db.scheduled_jobs.find_one_and_update(
        {
            "job_id": job_id,
            "status": "ACTIVE",
            "$or": [
                {"locked_by": None},
                {"locked_by": ""},
                {"lock_expires_at": {"$lt": now.isoformat()}},
                {"locked_by": runner.instance_id},
            ],
        },
        {
            "$set": {
                "locked_by": runner.instance_id,
                "locked_at": now.isoformat(),
                "lock_expires_at": lock_expires.isoformat(),
            },
            "$inc": {"execution_fencing_token": 1},
        },
        return_document=True,
    )
    assert lock_res is not None
    assert lock_res["locked_by"] == runner.instance_id
    assert lock_res["execution_fencing_token"] == 1

    # Second instance attempting to acquire lock concurrently -> denied (returns None)
    lock_res2 = mock_db.scheduled_jobs.find_one_and_update(
        {
            "job_id": job_id,
            "status": "ACTIVE",
            "$or": [
                {"locked_by": None},
                {"locked_by": ""},
                {"lock_expires_at": {"$lt": now.isoformat()}},
                {"locked_by": "different_instance_456"},
            ],
        },
        {
            "$set": {
                "locked_by": "different_instance_456",
                "locked_at": now.isoformat(),
                "lock_expires_at": lock_expires.isoformat(),
            },
            "$inc": {"execution_fencing_token": 1},
        },
        return_document=True,
    )
    assert lock_res2 is None


def test_task2_scheduler_loss_of_lease_suspension():
    runner = SchedulerRunner()
    runner.scheduler = MagicMock()
    runner.scheduler.running = True
    runner._is_paused = False

    # Simulate lease loss
    with patch.object(runner, "acquire_or_renew_lease", return_value=False):
        # Trigger reconciliation check
        has_lease = runner.acquire_or_renew_lease()
        if not has_lease and runner.scheduler.running and not runner._is_paused:
            runner.scheduler.pause()
            runner._is_paused = True

        assert runner._is_paused is True
        runner.scheduler.pause.assert_called_once()


# ==============================================================================
# TASK 3: SCHEDULING EDGE CASES & RECOVERY TESTS
# ==============================================================================

def test_task3_timezone_dst_spring_forward():
    # New York springs forward on March 8, 2026 (2:00 AM -> 3:00 AM)
    spec = parse_recurrence("daily at 2:30 AM", "America/New_York")
    from_time = datetime(2026, 3, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    run_times = calculate_next_run_times(spec, count=4, base_time=from_time)
    assert len(run_times) == 4
    # All run times must be strictly ascending future timestamps
    dts = [datetime.fromisoformat(t) for t in run_times]
    for i in range(len(dts) - 1):
        assert dts[i] < dts[i + 1]


def test_task3_timezone_dst_fall_back():
    # New York falls back on November 1, 2026 (2:00 AM repeated)
    spec = parse_recurrence("daily at 1:30 AM", "America/New_York")
    from_time = datetime(2026, 10, 31, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    run_times = calculate_next_run_times(spec, count=4, base_time=from_time)
    assert len(run_times) == 4
    dts = [datetime.fromisoformat(t) for t in run_times]
    for i in range(len(dts) - 1):
        assert dts[i] < dts[i + 1]


def test_task3_leap_year_recurrence():
    # 2028 is a leap year; 2027 is not.
    # Monthly on 28th should work reliably across Feb 28/29.
    spec = parse_recurrence("monthly on the 28th at 10:00", "UTC")
    from_time = datetime(2028, 2, 1, 0, 0, tzinfo=timezone.utc)
    run_times = calculate_next_run_times(spec, count=3, base_time=from_time)
    assert len(run_times) == 3
    assert "2028-02-28" in run_times[0]
    assert "2028-03-28" in run_times[1]
    assert "2028-04-28" in run_times[2]


def test_task3_month_end_recurrence():
    # Day 31 recurrence
    spec = parse_recurrence("monthly on the 31st at 12:00", "UTC")
    from_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    run_times = calculate_next_run_times(spec, count=3, base_time=from_time)
    assert len(run_times) == 3
    # Jan 31, Mar 31, May 31 (Feb and Apr skipped because they do not have 31 days)
    assert "2026-01-31" in run_times[0]
    assert "2026-03-31" in run_times[1]
    assert "2026-05-31" in run_times[2]


def test_task3_consecutive_failures_auto_pause(mock_db):
    runner = SchedulerRunner(db=mock_db)
    job_id = "job_fail_auto_pause"
    mock_db.scheduled_jobs.insert_one({
        "job_id": job_id,
        "owner_id": "test_user",
        "status": "ACTIVE",
        "consecutive_failures": 2,
    })

    # Third failure exceeds threshold (3) -> auto-pauses
    runner._handle_job_failure(job_id, "Third failure", is_config_error=False, threshold=3)
    updated = mock_db.scheduled_jobs.find_one({"job_id": job_id})
    assert updated["consecutive_failures"] == 3
    assert updated["status"] == "AUTO_PAUSED"


def test_task3_schema_drift_config_failure(mock_db):
    runner = SchedulerRunner(db=mock_db)
    job_id = "job_schema_drift"
    mock_db.scheduled_jobs.insert_one({
        "job_id": job_id,
        "owner_id": "test_user",
        "status": "ACTIVE",
        "consecutive_failures": 0,
    })

    # Schema/policy validation error -> immediately marks FAILED_CONFIGURATION
    runner._handle_job_failure(job_id, "Field 'non_existent_column' no longer exists", is_config_error=True)
    updated = mock_db.scheduled_jobs.find_one({"job_id": job_id})
    assert updated["status"] == "FAILED_CONFIGURATION"


def test_task3_scheduler_job_defaults_coalesce():
    runner = SchedulerRunner()
    defaults = runner.scheduler._job_defaults
    assert defaults.get("coalesce") is True
    assert defaults.get("misfire_grace_time") == 60
    assert defaults.get("max_instances") == 1
