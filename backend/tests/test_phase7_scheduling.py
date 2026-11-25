"""
FinTech Agent — Phase 7 Scheduled Queries & Automated Reports Test Suite
Comprehensive testing for:
  - Recurrence parsing and IANA timezone validation
  - APScheduler next run time calculations (strictly ascending future timestamps)
  - Node 9 Schedule Planner & Registrar (immutable preview creation, bounded dry run)
  - Explicit schedule approval workflow, tamper-proof SHA-256 hash checks, and idempotency
  - Metadata persistence (CRUD lifecycle, pause/resume/cancel, run history)
  - Distributed scheduler lease management and reconciliation
  - Pre-execution runtime MQL revalidation (drift detection -> FAILED_CONFIGURATION)
  - Dynamic relative date token resolution ($$DAYS_AGO_30, $$TODAY_START)
  - Failure tracking and consecutive failure auto-pause
  - FastAPI schedules management endpoints with strict ownership boundaries
  - End-to-end LangGraph query and schedule pipeline flow
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.graph import agent_graph
from backend.app.agent.nodes.schedule_planner import schedule_planner_node
from backend.app.config import settings
from backend.app.core.auth import auth_manager
from backend.app.core.logging import logger
from backend.app.main import app
from backend.app.schemas.schedule import (
    JobRun,
    ScheduleApprovalRequest,
    SchedulePreview,
    ScheduleSpec,
    ScheduledJob,
)
from backend.app.services.recurrence_parser import (
    calculate_next_run_times,
    parse_recurrence,
    validate_iana_timezone,
)
from backend.app.services.schedule_service import (
    ScheduleOwnershipError,
    SchedulePreviewNotFoundError,
    ScheduleService,
    ScheduleServiceError,
    schedule_service,
)
from backend.app.services.scheduler_runner import SchedulerRunner


# ==============================================================================
# In-Memory Metadata DB Mock Fixture for Complete Test Isolation
# ==============================================================================

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

    def find_one(self, query: Dict[str, Any]):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: Dict[str, Any] = None):
        res = []
        for doc in self.docs:
            if not query or self._matches(doc, query):
                res.append(dict(doc))

        class Cursor:
            def __init__(self, items):
                self._items = items

            def sort(self, key, direction=1):
                return self

            def limit(self, count):
                self._items = self._items[:count]
                return self

            def __iter__(self):
                return iter(self._items)

        return Cursor(res)

    def find_one_and_update(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False, return_document: bool = False):
        matched_doc = None
        for doc in self.docs:
            if self._matches(doc, filter):
                matched_doc = doc
                break

        if matched_doc is not None:
            if "$set" in update:
                matched_doc.update(update["$set"])
            return dict(matched_doc)
        elif upsert:
            new_doc = {}
            if "$set" in update:
                new_doc.update(update["$set"])
            if "_id" not in new_doc:
                new_doc["_id"] = str(len(self.docs) + 1)
            self.docs.append(new_doc)
            return dict(new_doc)
        return None

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        found = False
        for doc in self.docs:
            if self._matches(doc, query):
                found = True
                if "$set" in update:
                    doc.update(update["$set"])
                res = MagicMock()
                res.modified_count = 1
                return res
        if not found and upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "_id" not in new_doc:
                new_doc["_id"] = str(len(self.docs) + 1)
            self.docs.append(new_doc)
            res = MagicMock()
            res.upserted_id = "new_id"
            return res
        res = MagicMock()
        res.modified_count = 0
        return res

    def delete_one(self, query: Dict[str, Any]):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[i]
                res = MagicMock()
                res.deleted_count = 1
                return res
        res = MagicMock()
        res.deleted_count = 0
        return res


class MockMetadataDB:
    def __init__(self):
        self.schedule_previews = InMemoryCollection()
        self.scheduled_jobs = InMemoryCollection()
        self.job_runs = InMemoryCollection()
        self.scheduler_leases = InMemoryCollection()
        self.conversations = InMemoryCollection()
        self._collections = {}

    def __getitem__(self, item):
        if hasattr(self, item):
            return getattr(self, item)
        if item not in self._collections:
            self._collections[item] = InMemoryCollection()
        return self._collections[item]


@pytest.fixture(autouse=True)
def ensure_mock_provider_for_graph_tests():
    orig = settings.LLM_PROVIDER
    settings.LLM_PROVIDER = "mock"
    yield
    settings.LLM_PROVIDER = orig


@pytest.fixture
def mock_meta_db():
    db = MockMetadataDB()
    with patch("backend.app.db.mongo_client.mongo_manager.get_metadata_db", return_value=db):
        orig_custom = schedule_service._custom_db
        schedule_service._custom_db = db
        yield db
        schedule_service._custom_db = orig_custom


# ==============================================================================
# SECTION 1: RECURRENCE PARSING & TIMEZONE VALIDATION
# ==============================================================================

def test_parse_recurrence_daily():
    spec = parse_recurrence("daily at 8:00 AM", timezone_name="Asia/Kolkata")
    assert spec.frequency == "daily"
    assert spec.hour == 8
    assert spec.minute == 0
    assert spec.cron_expression == "0 8 * * *"
    assert spec.timezone == "Asia/Kolkata"


def test_parse_recurrence_weekly():
    spec = parse_recurrence("every Monday at 9:00 AM", timezone_name="UTC")
    assert spec.frequency == "weekly"
    assert spec.day_of_week == ["mon"]
    assert spec.hour == 9
    assert spec.minute == 0
    assert spec.cron_expression == "0 9 * * mon"
    assert spec.timezone == "UTC"


def test_parse_recurrence_monthly():
    spec = parse_recurrence("monthly on the 1st at 10:30 AM", timezone_name="Asia/Kolkata")
    assert spec.frequency == "monthly"
    assert spec.day_of_month == 1
    assert spec.hour == 10
    assert spec.minute == 30
    assert spec.cron_expression == "30 10 1 * *"


def test_parse_recurrence_standard_cron():
    spec = parse_recurrence("0 9 * * 1", timezone_name="Asia/Kolkata")
    assert spec.frequency == "cron"
    assert spec.cron_expression == "0 9 * * 1"


def test_parse_recurrence_minute_and_hour_intervals():
    # 1 minute
    spec1 = parse_recurrence("every 1 minute", timezone_name="Asia/Kolkata")
    assert spec1.frequency == "cron"
    assert spec1.cron_expression == "* * * * *"

    # 2 minutes
    spec2 = parse_recurrence("every 2 minutes", timezone_name="Asia/Kolkata")
    assert spec2.frequency == "cron"
    assert spec2.cron_expression == "*/2 * * * *"

    # 15 mins in query text
    spec15 = parse_recurrence("schedule accounts report every 15 mins", timezone_name="Asia/Kolkata")
    assert spec15.frequency == "cron"
    assert spec15.cron_expression == "*/15 * * * *"

    # Hourly interval
    spec_hr = parse_recurrence("every 2 hours", timezone_name="Asia/Kolkata")
    assert spec_hr.frequency == "cron"
    assert spec_hr.cron_expression == "0 */2 * * *"


def test_parse_recurrence_invalid_cron_raises():
    with pytest.raises(ValueError, match="Invalid 5-field cron"):
        parse_recurrence("99 99 * * *", timezone_name="Asia/Kolkata")


def test_parse_recurrence_invalid_timezone_raises():
    with pytest.raises(ValueError, match="Invalid IANA timezone"):
        validate_iana_timezone("Invalid/Timezone_Not_Real")


def test_parse_recurrence_ambiguous_text_raises():
    with pytest.raises(ValueError, match="Could not extract recurrence pattern"):
        parse_recurrence("summarize transactions randomly sometime")


def test_calculate_next_run_times_strictly_ascending():
    spec = ScheduleSpec(
        frequency="weekly",
        recurrence_expression="every Monday at 9:00 AM",
        cron_expression="0 9 * * mon",
        timezone="Asia/Kolkata",
    )
    runs = calculate_next_run_times(spec, count=3)
    assert len(runs) == 3
    dt1 = datetime.fromisoformat(runs[0])
    dt2 = datetime.fromisoformat(runs[1])
    dt3 = datetime.fromisoformat(runs[2])
    assert dt1 < dt2 < dt3
    assert dt1 > datetime.now(timezone.utc)


# ==============================================================================
# SECTION 2: NODE 9 SCHEDULE PLANNER & IMMUTABLE PREVIEWS
# ==============================================================================

@pytest.mark.asyncio
async def test_node9_schedule_planner_bypass_for_non_scheduling():
    state = {
        "request_id": "req-test-1",
        "request_mode": "QUERY_ONLY",
        "natural_language_query": "Show active customers",
    }
    result = await schedule_planner_node(state)
    assert result["schedule_approved"] is False
    assert result["schedule_preview"] is None
    assert result["preview_id"] is None


@pytest.mark.asyncio
async def test_node9_schedule_planner_generates_preview(mock_meta_db):
    state = {
        "request_id": "req-test-2",
        "user_id": "analyst_1",
        "request_mode": "SCHEDULE_ONLY",
        "natural_language_query": "Send me loan delinquency report every Monday at 9:00 AM",
        "target_collection": "loans",
        "pipeline_explanation": "Aggregate defaulted loans.",
        "generated_pipeline": [
            {"$match": {"loan_status": "DEFAULT"}},
            {"$limit": 10},
        ],
        "temporal_spec": {"recurrence_expression": "every Monday at 9:00 AM"},
    }
    result = await schedule_planner_node(state)
    assert result["schedule_approved"] is False
    preview = result["schedule_preview"]
    assert preview is not None
    assert preview["owner_id"] == "analyst_1"
    assert preview["target_collection"] == "loans"
    assert preview["status"] == "PENDING_APPROVAL"
    assert len(preview["next_run_times"]) == 3
    assert preview["pipeline_hash"] != ""
    assert result["preview_id"] == preview["preview_id"]


@pytest.mark.asyncio
async def test_node9_dry_run_bounded_to_limit(mock_meta_db):
    large_results = [{"doc_id": i} for i in range(50)]
    state = {
        "request_id": "req-test-3",
        "user_id": "analyst_1",
        "request_mode": "SCHEDULE_ONLY",
        "natural_language_query": "Send me account report daily at 8:00 AM",
        "target_collection": "accounts",
        "generated_pipeline": [{"$limit": 10}],
        "raw_results": large_results,
    }
    result = await schedule_planner_node(state)
    preview = result["schedule_preview"]
    assert preview is not None
    assert len(preview["dry_run_results"]) <= 10


# ==============================================================================
# SECTION 3: EXPLICIT APPROVAL WORKFLOW & TAMPER RESISTANCE
# ==============================================================================

def test_schedule_service_preview_and_approval_flow(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(
        frequency="daily",
        recurrence_expression="daily at 9:00 AM",
        cron_expression="0 9 * * *",
        timezone="Asia/Kolkata",
    )
    pipeline = [{"$match": {"status": "active"}}, {"$limit": 10}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Daily Active Accounts",
        natural_language_query="Show active accounts daily at 9am",
        target_collection="accounts",
        pipeline_explanation="Filter active accounts.",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z", "2026-11-13T09:00:00Z"],
    )

    # Preview exists in metadata db
    stored = svc.get_preview(preview.preview_id)
    assert stored is not None
    assert stored["status"] == "PENDING_APPROVAL"

    # Explicit approval
    job = svc.approve_preview(preview.preview_id, owner_id="user_bank_1")
    assert job.job_id.startswith("job_")
    assert job.status == "ACTIVE"
    assert job.target_collection == "accounts"
    assert job.next_run_at == "2026-11-12T09:00:00Z"


def test_approve_expired_preview_raises(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
        ttl_minutes=-5,  # immediately expired
    )
    with pytest.raises(ScheduleServiceError, match="expired"):
        svc.approve_preview(preview.preview_id, owner_id="user_bank_1")


def test_approve_ownership_mismatch_raises(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_alice",
        report_name="Alice Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    with pytest.raises(ScheduleOwnershipError, match="not authorized"):
        svc.approve_preview(preview.preview_id, owner_id="user_bob")


def test_approve_tampered_pipeline_hash_raises(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    # Tamper with stored pipeline in metadata DB
    mock_meta_db.schedule_previews.update_one(
        {"preview_id": preview.preview_id},
        {"$set": {"approved_pipeline": [{"$match": {"tampered": True}}, {"$limit": 5}]}},
    )
    with pytest.raises(ScheduleServiceError, match="hash mismatch"):
        svc.approve_preview(preview.preview_id, owner_id="user_bank_1")


def test_approval_idempotency_returns_same_job(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job1 = svc.approve_preview(preview.preview_id, owner_id="user_bank_1", idempotency_key="idemp_123")
    job2 = svc.approve_preview(preview.preview_id, owner_id="user_bank_1", idempotency_key="idemp_123")
    assert job1.job_id == job2.job_id


# ==============================================================================
# SECTION 4: METADATA PERSISTENCE & JOB LIFECYCLE
# ==============================================================================

def test_schedule_service_lifecycle_pause_resume_cancel(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = svc.approve_preview(preview.preview_id, owner_id="user_bank_1")
    assert job.status == "ACTIVE"

    # Pause
    paused = svc.pause_job(job.job_id, owner_id="user_bank_1")
    assert paused.status == "PAUSED"

    # Resume
    resumed = svc.resume_job(job.job_id, owner_id="user_bank_1")
    assert resumed.status == "ACTIVE"

    # Cancel
    cancelled = svc.cancel_job(job.job_id, owner_id="user_bank_1")
    assert cancelled.status == "CANCELLED"
    assert cancelled.next_run_at is None


def test_resume_revalidates_and_blocks_invalid_pipeline(mock_meta_db):
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="user_bank_1",
        report_name="Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = svc.approve_preview(preview.preview_id, owner_id="user_bank_1")
    svc.pause_job(job.job_id, owner_id="user_bank_1")

    # Tamper job pipeline to include prohibited operator ($out)
    mock_meta_db.scheduled_jobs.update_one(
        {"job_id": job.job_id},
        {"$set": {"pipeline_template": [{"$out": "hacked_collection"}]}},
    )

    with pytest.raises(ScheduleServiceError, match="revalidation"):
        svc.resume_job(job.job_id, owner_id="user_bank_1")


# ==============================================================================
# SECTION 5: SCHEDULER RUNNER, REVALIDATION, DYNAMIC DATES, LEASES
# ==============================================================================

def test_scheduler_runner_dynamic_date_resolution():
    pipeline = [
        {"$match": {"created_at": {"$gte": "$$DAYS_AGO_30"}}},
        {"$limit": 10},
    ]
    resolved = SchedulerRunner.resolve_dynamic_dates(pipeline)
    assert resolved[0]["$match"]["created_at"]["$gte"] != "$$DAYS_AGO_30"
    # Ensure it parsed to a valid ISO datetime
    val = resolved[0]["$match"]["created_at"]["$gte"]
    assert "T" in val


def test_scheduler_runner_lease_acquisition(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    acquired = runner.acquire_lease()
    assert acquired is True
    # Second acquisition by same instance ID succeeds (renewal)
    assert runner.acquire_lease() is True
    # Another runner cannot acquire while lease is fresh
    runner2 = SchedulerRunner(db=mock_meta_db)
    assert runner2.acquire_lease() is False


@pytest.mark.asyncio
async def test_scheduler_runner_execute_job_drift_detection(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    job = ScheduledJob(
        job_id="job_drift_test",
        owner_id="user_bank_1",
        report_name="Drift Test",
        natural_language_query="test",
        target_collection="accounts",
        pipeline_template=[{"$match": {"illegal_eval": True}}, {"$limit": 5}],
        pipeline_hash="fake_hash",
        schedule_spec=ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *"),
        timezone="Asia/Kolkata",
    )
    mock_meta_db.scheduled_jobs.insert_one(job.model_dump())

    # Execute run
    await runner.execute_job("job_drift_test")

    # Verify job status was flipped to FAILED_CONFIGURATION
    updated = mock_meta_db.scheduled_jobs.find_one({"job_id": "job_drift_test"})
    assert updated["status"] == "FAILED_CONFIGURATION"

    # Verify run record in job_runs
    runs = mock_meta_db.job_runs.find({"job_id": "job_drift_test"})
    runs_list = list(runs)
    assert len(runs_list) == 1
    assert runs_list[0]["status"] == "FAILED"
    assert "MQL validation failed" in runs_list[0]["error_message"]


@pytest.mark.asyncio
async def test_scheduler_runner_auto_pause_after_consecutive_failures(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    job = ScheduledJob(
        job_id="job_fail_test",
        owner_id="user_bank_1",
        report_name="Fail Test",
        natural_language_query="test",
        target_collection="accounts",
        pipeline_template=[{"$limit": 5}],
        pipeline_hash=schedule_service.compute_pipeline_hash([{"$limit": 5}]),
        schedule_spec=ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *"),
        timezone="Asia/Kolkata",
        consecutive_failures=2,
        failure_threshold=3,
    )
    mock_meta_db.scheduled_jobs.insert_one(job.model_dump())

    # Mock query_executor_node to simulate runtime failure
    with patch(
        "backend.app.agent.nodes.query_executor.query_executor_node",
        new=AsyncMock(return_value={"verification_status": "TIMEOUT", "execution_error": "DB Timeout"}),
    ):
        await runner.execute_job("job_fail_test")

    updated = mock_meta_db.scheduled_jobs.find_one({"job_id": "job_fail_test"})
    assert updated["consecutive_failures"] == 3
    assert updated["status"] == "AUTO_PAUSED"


# ==============================================================================
# SECTION 6: FASTAPI SCHEDULE MANAGEMENT ROUTES
# ==============================================================================

def _auth_headers(user_id: str) -> Dict[str, str]:
    token = auth_manager.create_access_token(user_id=user_id)
    return {"Authorization": f"Bearer {token}", "X-User-ID": user_id}


def test_fastapi_schedules_approve_route(mock_meta_db):
    client = TestClient(app)
    svc = schedule_service
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily at 9:00 AM", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = svc.create_preview(
        owner_id="test_client_user",
        report_name="API Preview Test",
        natural_language_query="q",
        target_collection="customers",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )

    resp = client.post(
        "/api/v1/schedules/approve",
        headers=_auth_headers("test_client_user"),
        json={"preview_id": preview.preview_id, "idempotency_key": "api_key_1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["job_id"].startswith("job_")
    assert data["status"] == "ACTIVE"


def test_fastapi_schedules_list_and_get(mock_meta_db):
    client = TestClient(app)
    # List empty initially
    resp = client.get("/api/v1/schedules", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    assert resp.json() == []

    # Insert a job for alice
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = schedule_service.create_preview(
        owner_id="alice",
        report_name="Alice Report",
        natural_language_query="q",
        target_collection="customers",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = schedule_service.approve_preview(preview.preview_id, owner_id="alice")

    # List now returns 1 job
    resp = client.get("/api/v1/schedules", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Get single job
    resp_get = client.get(f"/api/v1/schedules/{job.job_id}", headers=_auth_headers("alice"))
    assert resp_get.status_code == 200
    assert resp_get.json()["job_id"] == job.job_id

    # Bob cannot access Alice's job
    resp_bob = client.get(f"/api/v1/schedules/{job.job_id}", headers=_auth_headers("bob"))
    assert resp_bob.status_code == 403


def test_fastapi_schedules_lifecycle_routes(mock_meta_db):
    client = TestClient(app)
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = schedule_service.create_preview(
        owner_id="charlie",
        report_name="Charlie Report",
        natural_language_query="q",
        target_collection="customers",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = schedule_service.approve_preview(preview.preview_id, owner_id="charlie")

    # Pause
    resp_pause = client.post(f"/api/v1/schedules/{job.job_id}/pause", headers=_auth_headers("charlie"))
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "PAUSED"

    # Resume
    resp_resume = client.post(f"/api/v1/schedules/{job.job_id}/resume", headers=_auth_headers("charlie"))
    assert resp_resume.status_code == 200
    assert resp_resume.json()["status"] == "ACTIVE"

    # Cancel
    resp_cancel = client.post(f"/api/v1/schedules/{job.job_id}/cancel", headers=_auth_headers("charlie"))
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "CANCELLED"


def test_fastapi_schedules_runs_route(mock_meta_db):
    client = TestClient(app)
    spec = ScheduleSpec(frequency="daily", recurrence_expression="daily", cron_expression="0 9 * * *")
    pipeline = [{"$limit": 5}]
    preview = schedule_service.create_preview(
        owner_id="dave",
        report_name="Dave Report",
        natural_language_query="q",
        target_collection="customers",
        pipeline_explanation="exp",
        approved_pipeline=pipeline,
        schedule_spec=spec,
        next_run_times=["2026-11-12T09:00:00Z"],
    )
    job = schedule_service.approve_preview(preview.preview_id, owner_id="dave")

    # Record a run
    run = JobRun(
        job_id=job.job_id,
        owner_id="dave",
        start_time="2026-11-11T10:00:00Z",
        end_time="2026-11-11T10:00:01Z",
        duration_ms=1000,
        status="SUCCESS",
        pipeline_hash=job.pipeline_hash,
        query_execution_status="SUCCESS",
        result_row_count=5,
        summary="Successful execution.",
    )
    schedule_service.record_job_run(run)

    resp_runs = client.get(f"/api/v1/schedules/{job.job_id}/runs", headers=_auth_headers("dave"))
    assert resp_runs.status_code == 200
    runs_data = resp_runs.json()
    assert len(runs_data) == 1
    assert runs_data[0]["status"] == "SUCCESS"
    assert runs_data[0]["result_row_count"] == 5


# ==============================================================================
# SECTION 7: END-TO-END LANGGRAPH PIPELINE INTEGRATION
# ==============================================================================

@pytest.mark.asyncio
async def test_graph_end_to_end_query_and_schedule_flow(mock_meta_db):
    initial_state = {
        "request_id": "req-e2e-sched-1",
        "user_id": "analyst_e2e",
        "natural_language_query": "Send me active accounts every Monday at 9:00 AM",
        "conversation_history": [],
        "thread_id": "conv-e2e-1",
        "request_started_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": 0,
        "max_retries": 3,
        "trace": [],
        "all_attempts": [],
        "result_truncated": False,
        "dry_run": False,
        "schedule_approved": False,
        "is_api_request": True,
    }

    final_state = await agent_graph.ainvoke(initial_state)

    # Verify traversal through schedule planner and response composer
    trace_nodes = [t.get("node") for t in final_state.get("trace", [])]
    assert "input_guardrail" in trace_nodes
    assert "intent_router" in trace_nodes
    assert "schema_retriever" in trace_nodes
    assert "query_synthesizer" in trace_nodes
    assert "mql_policy_validator" in trace_nodes
    assert "schedule_planner" in trace_nodes
    assert "response_composer" in trace_nodes

    # Verify preview was generated and explicitly pending approval
    assert final_state.get("schedule_approved") is False
    assert final_state.get("preview_id") is not None
    assert final_state.get("schedule_preview") is not None

    # Verify formatted response contains approval callout
    final_resp = final_state.get("graph_response") or ""
    assert "Scheduled Report Preview" in final_resp
    assert "approve" in final_resp.lower()


def test_parse_recurrence_natural_interval_and_timezone_abbreviations():
    # 2-minute interval with IST
    spec1 = parse_recurrence("run accounts report with a 2-minute interval at 10:39 PM IST")
    assert spec1.frequency in ("cron", "interval")
    assert spec1.cron_expression == "*/2 * * * *"
    assert spec1.timezone == "Asia/Kolkata"

    # interval of 5 minutes
    spec2 = parse_recurrence("schedule this to run at interval of 5 minutes")
    assert spec2.frequency in ("cron", "interval")
    assert spec2.cron_expression == "*/5 * * * *"

    # Weekday schedule
    spec3 = parse_recurrence("send daily summary every weekday at 9am")
    assert spec3.frequency == "weekly"
    assert spec3.cron_expression == "0 9 * * mon-fri"
    assert spec3.day_of_week == ["mon", "tue", "wed", "thu", "fri"]

    # Timezone abbreviation UTC
    spec4 = parse_recurrence("daily at 8:00 AM UTC")
    assert spec4.timezone == "UTC"


def test_parse_recurrence_markdown_and_complex_prompt():
    prompt = (
        "Schedule the same accounts aggregation query to run **2 times**, "
        "starting today at **10:39 PM IST**, with a **2-minute interval** (10:39 PM and 10:45 PM). "
        "Keep it read-only, do not run it immediately, and stop after the second execution."
    )
    spec = parse_recurrence(prompt)
    assert spec.frequency in ("cron", "interval")
    assert spec.cron_expression == "*/2 * * * *"
    assert spec.timezone == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_graph_e2e_complex_schedule_prompt_generates_preview(mock_meta_db):
    prompt = (
        "Schedule the same accounts aggregation query to run **2 times**, "
        "starting today at **10:39 PM IST**, with a **2-minute interval** (10:39 PM and 10:45 PM). "
        "Keep it read-only, do not run it immediately, and stop after the second execution."
    )
    initial_state = {
        "request_id": "req-e2e-user-sched",
        "user_id": "operator_1",
        "natural_language_query": prompt,
        "conversation_history": [],
        "thread_id": "conv-user-1",
        "retry_count": 0,
        "max_retries": 3,
        "trace": [],
        "all_attempts": [],
        "result_truncated": False,
        "dry_run": False,
        "schedule_approved": False,
        "is_api_request": True,
    }

    final_state = await agent_graph.ainvoke(initial_state)

    assert final_state.get("schedule_approved") is False
    assert final_state.get("preview_id") is not None
    assert final_state.get("schedule_preview") is not None

    final_resp = final_state.get("graph_response") or ""
    assert "Scheduled Report Preview" in final_resp
    assert "Query Executed Successfully" not in final_resp
    assert "approve" in final_resp.lower()


# ==============================================================================
# SECTION 8: FINITE SCHEDULES, ONE-TIME JOBS & EXECUTION LIMITS TESTS
# ==============================================================================

def test_parse_recurrence_one_time_scheduled_job():
    spec = parse_recurrence("Schedule a loan delinquency report to run once today at 10:30 PM IST")
    assert spec.frequency == "once"
    assert spec.max_executions == 1
    assert spec.timezone == "Asia/Kolkata"
    assert spec.start_at is not None

    # Calculate run times: one-time job must return exactly 1 timestamp
    runs = calculate_next_run_times(spec, count=3)
    assert len(runs) == 1
    assert "T" in runs[0]


def test_calculate_next_run_times_two_executions_at_interval():
    prompt = (
        "Schedule accounts aggregation to run 2 times, "
        "starting today at 10:39 PM IST, with a 2-minute interval."
    )
    spec = parse_recurrence(prompt)
    assert spec.frequency == "interval"
    assert spec.interval_minutes == 2
    assert spec.max_executions == 2

    # Calculate next run times: must return exactly 2 timestamps (capped at max_executions)
    runs = calculate_next_run_times(spec, count=3)
    assert len(runs) == 2
    dt1 = datetime.fromisoformat(runs[0])
    dt2 = datetime.fromisoformat(runs[1])

    # Must be strictly ascending
    assert dt1 < dt2
    # Spacing must be exactly 2 minutes
    diff_seconds = (dt2 - dt1).total_seconds()
    assert diff_seconds == 120


@pytest.mark.asyncio
async def test_scheduler_runner_auto_completion_at_max_executions(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    spec = ScheduleSpec(
        frequency="interval",
        recurrence_expression="Run 2 times at 2-minute intervals",
        timezone="Asia/Kolkata",
        interval_minutes=2,
        max_executions=2,
    )
    job = ScheduledJob(
        job_id="job_max_exec_test",
        owner_id="bank_user_1",
        report_name="Finite Report",
        natural_language_query="q",
        target_collection="accounts",
        pipeline_template=[{"$limit": 5}],
        pipeline_hash=schedule_service.compute_pipeline_hash([{"$limit": 5}]),
        schedule_spec=spec,
        timezone="Asia/Kolkata",
        status="ACTIVE",
        max_executions=2,
        execution_count=0,
    )
    mock_meta_db.scheduled_jobs.insert_one(job.model_dump())

    # Mock query_executor_node and result_verifier_node to succeed without live DB
    with patch(
        "backend.app.services.scheduler_runner.query_executor_node",
        new=AsyncMock(return_value={"execution_status": "SUCCESS_WITH_DATA", "raw_results": [{"acc_id": 1}], "result_row_count": 1}),
    ), patch(
        "backend.app.services.scheduler_runner.result_verifier_node",
        new=AsyncMock(return_value={"verification_status": "SUCCESS_WITH_DATA", "interpretation_summary": "Success"}),
    ):
        # Execution 1
        await runner.execute_job("job_max_exec_test")
        doc1 = mock_meta_db.scheduled_jobs.find_one({"job_id": "job_max_exec_test"})
        assert doc1["execution_count"] == 1
        assert doc1["status"] == "ACTIVE"

        # Execution 2 (Final execution)
        await runner.execute_job("job_max_exec_test")
        doc2 = mock_meta_db.scheduled_jobs.find_one({"job_id": "job_max_exec_test"})
        assert doc2["execution_count"] == 2
        assert doc2["status"] == "COMPLETED"
        assert doc2["next_run_at"] is None


@pytest.mark.asyncio
async def test_scheduler_runner_one_time_job_auto_completion(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    spec = ScheduleSpec(
        frequency="once",
        recurrence_expression="Run once at 10:30 PM",
        timezone="Asia/Kolkata",
        hour=22,
        minute=30,
        max_executions=1,
    )
    job = ScheduledJob(
        job_id="job_once_test",
        owner_id="bank_user_2",
        report_name="One Time Report",
        natural_language_query="q",
        target_collection="customers",
        pipeline_template=[{"$limit": 5}],
        pipeline_hash=schedule_service.compute_pipeline_hash([{"$limit": 5}]),
        schedule_spec=spec,
        timezone="Asia/Kolkata",
        status="ACTIVE",
        max_executions=1,
        execution_count=0,
    )
    mock_meta_db.scheduled_jobs.insert_one(job.model_dump())

    with patch(
        "backend.app.services.scheduler_runner.query_executor_node",
        new=AsyncMock(return_value={"execution_status": "SUCCESS_WITH_DATA", "raw_results": [{"cid": "c1"}], "result_row_count": 1}),
    ), patch(
        "backend.app.services.scheduler_runner.result_verifier_node",
        new=AsyncMock(return_value={"verification_status": "SUCCESS_WITH_DATA", "interpretation_summary": "Success"}),
    ):
        await runner.execute_job("job_once_test")
        doc = mock_meta_db.scheduled_jobs.find_one({"job_id": "job_once_test"})
        assert doc["execution_count"] == 1
        assert doc["status"] == "COMPLETED"
        assert doc["next_run_at"] is None


def test_scheduler_runner_reconcile_jobs_triggers(mock_meta_db):
    runner = SchedulerRunner(db=mock_meta_db)
    runner._has_lease = True

    # 1. Once job
    job1 = ScheduledJob(
        job_id="job_rec_once",
        owner_id="u1",
        report_name="r1",
        natural_language_query="q",
        target_collection="loans",
        pipeline_template=[{"$limit": 1}],
        pipeline_hash="h1",
        schedule_spec=ScheduleSpec(frequency="once", recurrence_expression="once", timezone="Asia/Kolkata", start_at=datetime.now(timezone.utc) + timedelta(hours=1)),
        timezone="Asia/Kolkata",
        status="ACTIVE",
    )
    # 2. Interval job
    job2 = ScheduledJob(
        job_id="job_rec_interval",
        owner_id="u1",
        report_name="r2",
        natural_language_query="q",
        target_collection="loans",
        pipeline_template=[{"$limit": 1}],
        pipeline_hash="h2",
        schedule_spec=ScheduleSpec(frequency="interval", interval_minutes=2, recurrence_expression="int", timezone="Asia/Kolkata", max_executions=2),
        timezone="Asia/Kolkata",
        status="ACTIVE",
    )
    mock_meta_db.scheduled_jobs.insert_one(job1.model_dump())
    mock_meta_db.scheduled_jobs.insert_one(job2.model_dump())

    synced = runner.reconcile_jobs()
    assert synced == 2
    aps_jobs = runner.scheduler.get_jobs()
    aps_job_ids = {j.id for j in aps_jobs}
    assert "job_rec_once" in aps_job_ids
    assert "job_rec_interval" in aps_job_ids


@pytest.mark.asyncio
async def test_schedule_planner_node_error_reporting(mock_meta_db):
    # Invalid timezone should report scheduling_error and NOT create preview
    state = {
        "request_id": "req-err-1",
        "user_id": "analyst_err",
        "request_mode": "SCHEDULE_ONLY",
        "natural_language_query": "Send report daily at 9am",
        "timezone": "Invalid/Timezone",
        "target_collection": "customers",
        "generated_pipeline": [{"$limit": 10}],
    }
    result = await schedule_planner_node(state)
    assert result["schedule_approved"] is False
    assert result["schedule_preview"] is None
    assert result["preview_id"] is None
    assert result.get("scheduling_error") is not None

    # Node 8 response composer should render error template, NOT success
    comp_state = {**state, **result}
    from backend.app.agent.nodes.response_composer import response_composer_node
    comp_result = await response_composer_node(comp_state)
    resp = comp_result.get("graph_response", "")
    assert "Schedule Registration Failed" in resp
    assert "✅" not in resp


@pytest.mark.asyncio
async def test_schedule_only_never_executes_query_immediately(mock_meta_db):
    from backend.app.agent.nodes.query_executor import query_executor_node
    state = {
        "request_id": "req-sched-only-guard",
        "request_mode": "SCHEDULE_ONLY",
        "target_collection": "transactions",
        "approved_pipeline": [{"$limit": 10}],
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SKIPPED"
    assert res["raw_results"] is None
    assert res["result_row_count"] == 0
