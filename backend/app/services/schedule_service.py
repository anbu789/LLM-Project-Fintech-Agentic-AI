"""
FinTech Agent — Schedule Management and Metadata Persistence Service
Manages schedule previews, explicit approval verification, durable scheduled_jobs,
and execution history in agent_metadata_db.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid

from backend.app.agent.nodes.mql_policy_validator import MQLPolicyValidator
from backend.app.config import settings
from backend.app.core.exceptions import FinTechAgentException
from backend.app.core.logging import logger
from backend.app.db.mongo_client import mongo_manager
from backend.app.schemas.schedule import (
    JobRun,
    JobStatus,
    SchedulePreview,
    ScheduledJob,
    ScheduleSpec,
)


class ScheduleServiceError(FinTechAgentException):
    """Base exception for schedule service errors."""
    pass


class SchedulePreviewNotFoundError(ScheduleServiceError):
    """Raised when preview ID is not found or has expired."""
    pass


class ScheduleOwnershipError(ScheduleServiceError):
    """Raised when an operation is attempted by a non-owner."""
    pass


class ScheduleService:
    """Service for managing schedule previews, approval workflows, and metadata jobs."""

    def __init__(self, db: Optional[Any] = None):
        self._custom_db = db
        # In-memory preview store fallback for testing or ephemeral previews
        self._ephemeral_previews: Dict[str, Dict[str, Any]] = {}

    def _get_db(self):
        if self._custom_db is not None:
            return self._custom_db
        return mongo_manager.get_metadata_db()

    @staticmethod
    def compute_pipeline_hash(pipeline: List[Dict[str, Any]]) -> str:
        """Computes deterministic SHA-256 hash of pipeline stages for tamper protection."""
        serialized = json.dumps(pipeline, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def create_preview(
        self,
        owner_id: str,
        report_name: str,
        natural_language_query: str,
        target_collection: str,
        pipeline_explanation: str,
        approved_pipeline: List[Dict[str, Any]],
        schedule_spec: ScheduleSpec,
        next_run_times: List[str],
        dry_run_status: str = "NOT_PERMITTED",
        dry_run_results: Optional[List[Dict[str, Any]]] = None,
        warning: Optional[str] = None,
        ttl_minutes: int = 15,
    ) -> SchedulePreview:
        """Constructs an immutable preview and registers it for explicit approval."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl_minutes)
        pipeline_hash = self.compute_pipeline_hash(approved_pipeline)

        preview = SchedulePreview(
            preview_id=f"prev_{uuid.uuid4().hex[:12]}",
            owner_id=owner_id,
            report_name=report_name,
            natural_language_query=natural_language_query,
            target_collection=target_collection,
            pipeline_explanation=pipeline_explanation,
            approved_pipeline=approved_pipeline,
            pipeline_hash=pipeline_hash,
            schedule_spec=schedule_spec,
            next_run_times=next_run_times,
            dry_run_status=dry_run_status,
            dry_run_results=dry_run_results,
            warning=warning,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="PENDING_APPROVAL",
        )

        doc = preview.model_dump()
        try:
            db = self._get_db()
            db.schedule_previews.insert_one(doc)
        except Exception as e:
            logger.warning(f"Could not persist preview to metadata DB (using memory fallback): {e}")
            self._ephemeral_previews[preview.preview_id] = doc

        return preview

    def get_preview(self, preview_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves preview from metadata DB or memory fallback."""
        try:
            db = self._get_db()
            doc = db.schedule_previews.find_one({"preview_id": preview_id})
            if doc:
                return doc
        except Exception:
            pass
        return self._ephemeral_previews.get(preview_id)

    def approve_preview(
        self,
        preview_id: str,
        owner_id: str,
        idempotency_key: Optional[str] = None,
    ) -> ScheduledJob:
        """Approves a pending schedule preview and activates the scheduled job."""
        preview_doc = self.get_preview(preview_id)
        if not preview_doc:
            raise SchedulePreviewNotFoundError(f"Schedule preview '{preview_id}' not found or expired.")

        # 1. Ownership check
        if preview_doc.get("owner_id") != owner_id:
            raise ScheduleOwnershipError(f"User '{owner_id}' is not authorized to approve preview '{preview_id}'.")

        # 2. Expiry check
        expires_at_str = preview_doc.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                raise ScheduleServiceError("Schedule preview has expired. Please submit a new query to generate a fresh preview.")

        # 3. Idempotency check: if job already exists for this idempotency key or preview_id
        db = self._get_db()
        if idempotency_key:
            existing = db.scheduled_jobs.find_one({"owner_id": owner_id, "idempotency_key": idempotency_key})
            if existing:
                return ScheduledJob(**existing)

        existing_prev = db.scheduled_jobs.find_one({"owner_id": owner_id, "preview_id": preview_id})
        if existing_prev:
            return ScheduledJob(**existing_prev)

        # 4. Pipeline hash integrity & deterministic revalidation
        pipeline = preview_doc.get("approved_pipeline", [])
        stored_hash = preview_doc.get("pipeline_hash")
        current_hash = self.compute_pipeline_hash(pipeline)
        if stored_hash != current_hash:
            raise ScheduleServiceError("Pipeline integrity verification failed: pipeline hash mismatch.")

        # Revalidate via Node 5 policy validator
        validator = MQLPolicyValidator()
        target_col = preview_doc.get("target_collection", "customers")
        val_res = validator.validate_pipeline(target_col, pipeline, require_terminal_limit=True)
        if not val_res.is_valid:
            raise ScheduleServiceError(f"Pipeline failed deterministic revalidation: {val_res.errors}")

        # 5. Create active scheduled job
        next_run_times = preview_doc.get("next_run_times", [])
        first_next_run = next_run_times[0] if next_run_times else None

        job = ScheduledJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            owner_id=owner_id,
            report_name=preview_doc.get("report_name", "Recurring Report"),
            natural_language_query=preview_doc.get("natural_language_query", ""),
            target_collection=target_col,
            pipeline_template=pipeline,
            pipeline_hash=current_hash,
            schedule_spec=ScheduleSpec(**preview_doc.get("schedule_spec")),
            timezone=preview_doc.get("schedule_spec", {}).get("timezone", "Asia/Kolkata"),
            status="ACTIVE",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            next_run_at=first_next_run,
            max_executions=preview_doc.get("schedule_spec", {}).get("max_executions"),
            execution_count=0,
            idempotency_key=idempotency_key,
            preview_id=preview_id,
        )

        db.scheduled_jobs.insert_one(job.model_dump())
        logger.info(f"Scheduled job '{job.job_id}' activated for user '{owner_id}'. Next run: {job.next_run_at}")
        return job

    def list_jobs(self, owner_id: str) -> List[ScheduledJob]:
        """Lists all scheduled jobs belonging strictly to the authenticated owner."""
        db = self._get_db()
        cursor = db.scheduled_jobs.find({"owner_id": owner_id}).sort("created_at", -1)
        return [ScheduledJob(**doc) for doc in cursor]

    def get_job(self, job_id: str, owner_id: str) -> Optional[ScheduledJob]:
        """Retrieves a scheduled job ensuring ownership matching."""
        db = self._get_db()
        doc = db.scheduled_jobs.find_one({"job_id": job_id})
        if not doc:
            return None
        if doc.get("owner_id") != owner_id:
            raise ScheduleOwnershipError(f"User '{owner_id}' is not authorized to access job '{job_id}'.")
        return ScheduledJob(**doc)

    def pause_job(self, job_id: str, owner_id: str) -> ScheduledJob:
        """Pauses an active scheduled job."""
        job = self.get_job(job_id, owner_id)
        if not job:
            raise ScheduleServiceError(f"Job '{job_id}' not found.")
        if job.status == "CANCELLED":
            raise ScheduleServiceError(f"Cannot pause cancelled job '{job_id}'.")

        db = self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.scheduled_jobs.update_one(
            {"job_id": job_id, "owner_id": owner_id},
            {"$set": {"status": "PAUSED", "updated_at": now}},
        )
        job.status = "PAUSED"
        job.updated_at = now
        return job

    def resume_job(self, job_id: str, owner_id: str) -> ScheduledJob:
        """Resumes a paused scheduled job after revalidating its pipeline."""
        job = self.get_job(job_id, owner_id)
        if not job:
            raise ScheduleServiceError(f"Job '{job_id}' not found.")
        if job.status == "CANCELLED":
            raise ScheduleServiceError(f"Cannot resume cancelled job '{job_id}'.")

        # Deterministic revalidation before resumption
        validator = MQLPolicyValidator()
        val_res = validator.validate_pipeline(job.target_collection, job.pipeline_template, require_terminal_limit=True)
        if not val_res.is_valid:
            db = self._get_db()
            db.scheduled_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"status": "FAILED_CONFIGURATION", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            raise ScheduleServiceError(f"Job resumption blocked: pipeline failed revalidation ({val_res.errors})")

        db = self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.scheduled_jobs.update_one(
            {"job_id": job_id, "owner_id": owner_id},
            {"$set": {"status": "ACTIVE", "updated_at": now}},
        )
        job.status = "ACTIVE"
        job.updated_at = now
        return job

    def cancel_job(self, job_id: str, owner_id: str) -> ScheduledJob:
        """Cancels a scheduled job, permanently stopping future executions."""
        job = self.get_job(job_id, owner_id)
        if not job:
            raise ScheduleServiceError(f"Job '{job_id}' not found.")

        db = self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.scheduled_jobs.update_one(
            {"job_id": job_id, "owner_id": owner_id},
            {"$set": {"status": "CANCELLED", "updated_at": now, "next_run_at": None}},
        )
        job.status = "CANCELLED"
        job.updated_at = now
        job.next_run_at = None
        return job

    def record_job_run(self, run: JobRun) -> None:
        """Appends execution outcome to agent_metadata_db.job_runs."""
        db = self._get_db()
        db.job_runs.insert_one(run.model_dump())

    def get_job_runs(self, job_id: str, owner_id: str, limit: int = 50) -> List[JobRun]:
        """Retrieves execution history for a job after verifying ownership."""
        job = self.get_job(job_id, owner_id)
        if not job:
            raise ScheduleServiceError(f"Job '{job_id}' not found.")
        db = self._get_db()
        cursor = db.job_runs.find({"job_id": job_id, "owner_id": owner_id}).sort("start_time", -1).limit(limit)
        from backend.app.agent.nodes.result_verifier import _sanitize_doc
        return [JobRun(**_sanitize_doc(doc)) for doc in cursor]


schedule_service = ScheduleService()
