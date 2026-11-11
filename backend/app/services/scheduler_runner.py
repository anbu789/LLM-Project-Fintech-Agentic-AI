"""
FinTech Agent — Phase 7 APScheduler Service and Reconciliation Runner
Runs the single background scheduling authority, manages database leases,
reconciles active jobs from agent_metadata_db, and executes scheduled reports with
runtime MQL revalidation, dynamic relative date resolution, and failure tracking.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import socket
import time
from typing import Any, Dict, List, Optional
import uuid
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_RE_DAYS_AGO = re.compile(r"\$\$DAYS_AGO_(\d+)")
_RE_DAYS_AHEAD = re.compile(r"\$\$DAYS_AHEAD_(\d+)")

from backend.app.agent.nodes.mql_policy_validator import MQLPolicyValidator
from backend.app.agent.nodes.query_executor import (
    check_live_execution_readiness,
    query_executor_node,
)
from backend.app.agent.nodes.result_verifier import result_verifier_node
from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.db.mongo_client import mongo_manager
from backend.app.schemas.schedule import JobRun, ScheduledJob


class SchedulerRunner:
    """Single APScheduler authority with database lease management and job reconciliation."""

    def __init__(self, db: Optional[Any] = None):
        self._custom_db = db
        self.scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": settings.SCHEDULER_MAX_INSTANCES or 1,
                "misfire_grace_time": 60,
            }
        )
        self.instance_id = f"sched_{socket.gethostname()}_{uuid.uuid4().hex[:8]}"
        self._is_running = False
        self._is_paused = False
        self._reconcile_task: Optional[asyncio.Task] = None
        self._has_lease = False
        self.current_fencing_token: int = 0

    def _get_db(self):
        if self._custom_db is not None:
            return self._custom_db
        return mongo_manager.get_metadata_db()

    # -------------------------------------------------------------------------
    # 1. Distributed Single-Process Lease Management
    # -------------------------------------------------------------------------
    def acquire_or_renew_lease(self, lease_ttl_seconds: int = 60) -> bool:
        """Acquires or renews the single scheduler lease in agent_metadata_db."""
        db = self._get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_ttl_seconds)

        try:
            existing = db.scheduler_leases.find_one({"lease_name": "primary_scheduler"})
            if existing:
                existing_instance = existing.get("instance_id")
                existing_expires = existing.get("expires_at")
                if existing_instance != self.instance_id:
                    if existing_expires and existing_expires > now.isoformat():
                        self._has_lease = False
                        return False

            # Atomic find_one_and_update to acquire expired or owned lease with monotonic fencing token
            res = db.scheduler_leases.find_one_and_update(
                {
                    "lease_name": "primary_scheduler",
                    "$or": [
                        {"instance_id": self.instance_id},
                        {"expires_at": {"$lt": now.isoformat()}},
                        {"expires_at": None},
                    ],
                },
                {
                    "$set": {
                        "lease_name": "primary_scheduler",
                        "instance_id": self.instance_id,
                        "acquired_at": now.isoformat(),
                        "expires_at": expires_at.isoformat(),
                    },
                    "$inc": {
                        "fencing_token": 1,
                    },
                },
                upsert=(existing is None),
                return_document=True,
            )
            self._has_lease = (res is not None and res.get("instance_id") == self.instance_id)
            if self._has_lease:
                self.current_fencing_token = res.get("fencing_token", 1)
            return self._has_lease
        except Exception as e:
            logger.warning(f"Failed to acquire/renew scheduler lease: {e}")
            self._has_lease = False
            return False

    acquire_lease = acquire_or_renew_lease

    def release_lease(self) -> None:
        """Releases the scheduler lease upon graceful shutdown."""
        try:
            db = self._get_db()
            db.scheduler_leases.delete_one({"lease_name": "primary_scheduler", "instance_id": self.instance_id})
            self._has_lease = False
            logger.info(f"Released scheduler lease for instance '{self.instance_id}'.")
        except Exception as e:
            logger.warning(f"Error releasing scheduler lease: {e}")

    # -------------------------------------------------------------------------
    # 2. Dynamic Relative Date Resolution
    # -------------------------------------------------------------------------
    @staticmethod
    def resolve_relative_dates(pipeline: List[Dict[str, Any]], execution_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Resolves relative date markers (e.g. $$DAYS_AGO_30) dynamically to execution time."""
        if execution_time is None:
            execution_time = datetime.now(timezone.utc)
        pipeline_str = json.dumps(pipeline, default=str)

        # Pattern for relative day substitution: $$DAYS_AGO_<N>
        def repl_days_ago(match):
            days = int(match.group(1))
            dt = execution_time - timedelta(days=days)
            return dt.isoformat()

        # Pattern for relative day ahead substitution: $$DAYS_AHEAD_<N>
        def repl_days_ahead(match):
            days = int(match.group(1))
            dt = execution_time + timedelta(days=days)
            return dt.isoformat()

        pipeline_str = _RE_DAYS_AGO.sub(repl_days_ago, pipeline_str)
        pipeline_str = _RE_DAYS_AHEAD.sub(repl_days_ahead, pipeline_str)
        pipeline_str = pipeline_str.replace("$$NOW", execution_time.isoformat())
        pipeline_str = pipeline_str.replace(
            "$$TODAY_START",
            execution_time.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        )

        return json.loads(pipeline_str)

    resolve_dynamic_dates = resolve_relative_dates

    # -------------------------------------------------------------------------
    # 3. Scheduled Job Execution & Runtime Revalidation
    # -------------------------------------------------------------------------
    async def execute_scheduled_job(self, job_id: str) -> None:
        """Executes a single scheduled report under full Phase 6/7 security controls."""
        start_time = datetime.now(timezone.utc)
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        logger.info(f"Starting scheduled run '{run_id}' for job '{job_id}'.")

        db = self._get_db()

        # Atomic per-job execution lock with fencing token to eliminate duplicate runs
        lock_expires = start_time + timedelta(seconds=120)
        lock_res = db.scheduled_jobs.find_one_and_update(
            {
                "job_id": job_id,
                "status": "ACTIVE",
                "$or": [
                    {"locked_by": None},
                    {"locked_by": ""},
                    {"lock_expires_at": {"$lt": start_time.isoformat()}},
                    {"locked_by": self.instance_id},
                ],
            },
            {
                "$set": {
                    "locked_by": self.instance_id,
                    "locked_at": start_time.isoformat(),
                    "lock_expires_at": lock_expires.isoformat(),
                },
                "$inc": {"execution_fencing_token": 1},
            },
            return_document=True,
        )

        if not lock_res:
            logger.info(f"Job '{job_id}' is locked by another instance or not ACTIVE; skipping duplicate execution.")
            return

        job_doc = lock_res
        owner_id = job_doc.get("owner_id", "unknown")
        target_col = job_doc.get("target_collection", "customers")
        stored_pipeline = job_doc.get("pipeline_template", [])
        failure_threshold = job_doc.get("failure_threshold", settings.PHASE7_FAILURE_THRESHOLD)

        try:
            # 1. Resolve relative dates dynamically
            resolved_pipeline = self.resolve_relative_dates(stored_pipeline, start_time)
            pipeline_hash = hashlib.sha256(json.dumps(resolved_pipeline, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            # 2. Runtime revalidation immediately before execution
            validator = MQLPolicyValidator()
            val_res = validator.validate_pipeline(target_col, resolved_pipeline, require_terminal_limit=True)

            if not val_res.is_valid:
                # Policy or schema changed; mark configuration failure
                err_msg = f"Runtime MQL validation failed: {val_res.errors}"
                logger.error(f"Job '{job_id}' failed runtime revalidation: {err_msg}")
                self._handle_job_failure(job_id, err_msg, is_config_error=True)
                self._record_run(
                    run_id=run_id,
                    job_id=job_id,
                    owner_id=owner_id,
                    start_time=start_time,
                    status="FAILED",
                    pipeline_hash=pipeline_hash,
                    query_status="VALIDATION_FAILED",
                    error_message=err_msg,
                )
                return

            # 3. Execute via Node 6 Query Executor
            state = {
                "request_id": run_id,
                "target_collection": target_col,
                "approved_pipeline": resolved_pipeline,
                "is_pipeline_valid": True,
                "validation_status": "VALID",
                "test_db": self._custom_db,
            }
            exec_res = await query_executor_node(state)

            # 4. Verify results via Node 7 Result Verifier
            verif_state = {**state, **exec_res}
            verif_res = await result_verifier_node(verif_state)

            end_time = datetime.now(timezone.utc)
            duration_ms = max(1, int((end_time - start_time).total_seconds() * 1000))
            exec_status = exec_res.get("execution_status")
            verif_status = verif_res.get("verification_status")

            # 5. Evaluate execution outcome
            if verif_status in ("SUCCESS_WITH_DATA", "SUCCESS_EMPTY", "SUCCESS_LIMITED"):
                # Successful run
                db.scheduled_jobs.update_one(
                    {"job_id": job_id},
                    {
                        "$set": {
                            "last_run_at": start_time.isoformat(),
                            "consecutive_failures": 0,
                            "updated_at": end_time.isoformat(),
                        }
                    },
                )
                self._record_run(
                    run_id=run_id,
                    job_id=job_id,
                    owner_id=owner_id,
                    start_time=start_time,
                    status="SUCCESS",
                    pipeline_hash=pipeline_hash,
                    query_status=verif_status,
                    row_count=exec_res.get("result_row_count", 0),
                    truncated=exec_res.get("result_truncated", False),
                    summary=verif_res.get("interpretation_summary", "Completed successfully."),
                )
                logger.info(f"Job '{job_id}' run '{run_id}' succeeded in {duration_ms}ms ({exec_res.get('result_row_count', 0)} rows).")

            elif exec_status == "GATE_BLOCKED":
                # Live execution gate blocked (development or unverified native auth)
                self._record_run(
                    run_id=run_id,
                    job_id=job_id,
                    owner_id=owner_id,
                    start_time=start_time,
                    status="SKIPPED",
                    pipeline_hash=pipeline_hash,
                    query_status="GATE_BLOCKED",
                    summary="Execution skipped: Live execution gate is closed.",
                )
                logger.info(f"Job '{job_id}' run '{run_id}' skipped by live execution gate.")

            else:
                # Transient or terminal execution error
                err_msg = exec_res.get("execution_error") or verif_res.get("interpretation_summary") or "Query execution failed."
                self._handle_job_failure(job_id, err_msg, is_config_error=False, threshold=failure_threshold)
                self._record_run(
                    run_id=run_id,
                    job_id=job_id,
                    owner_id=owner_id,
                    start_time=start_time,
                    status="FAILED",
                    pipeline_hash=pipeline_hash,
                    query_status=exec_status or "EXECUTION_ERROR",
                    error_message=err_msg,
                )
                logger.warning(f"Job '{job_id}' run '{run_id}' failed: {err_msg}")
        finally:
            try:
                db.scheduled_jobs.update_one(
                    {"job_id": job_id, "locked_by": self.instance_id},
                    {
                        "$set": {
                            "locked_by": None,
                            "lock_expires_at": None,
                        }
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to clear execution lock for job '{job_id}': {e}")

    execute_job = execute_scheduled_job

    def _handle_job_failure(self, job_id: str, err_msg: str, is_config_error: bool = False, threshold: int = 3) -> None:
        """Tracks consecutive failures and auto-pauses when threshold is exceeded."""
        db = self._get_db()
        job = db.scheduled_jobs.find_one({"job_id": job_id})
        if not job:
            return

        consecutive = job.get("consecutive_failures", 0) + 1
        new_status = job.get("status")

        if is_config_error:
            new_status = "FAILED_CONFIGURATION"
        elif consecutive >= threshold:
            new_status = "AUTO_PAUSED"
            logger.error(f"Job '{job_id}' reached failure threshold ({consecutive}/{threshold}). Auto-pausing job.")

        db.scheduled_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "consecutive_failures": consecutive,
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": err_msg,
                }
            },
        )

    def _record_run(
        self,
        run_id: str,
        job_id: str,
        owner_id: str,
        start_time: datetime,
        status: str,
        pipeline_hash: str,
        query_status: str,
        row_count: int = 0,
        truncated: bool = False,
        summary: str = "",
        error_message: Optional[str] = None,
    ) -> None:
        """Persists JobRun document to agent_metadata_db.job_runs."""
        end_time = datetime.now(timezone.utc)
        duration_ms = max(1, int((end_time - start_time).total_seconds() * 1000))
        run = JobRun(
            run_id=run_id,
            job_id=job_id,
            owner_id=owner_id,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_ms=duration_ms,
            status=status,
            pipeline_hash=pipeline_hash,
            query_execution_status=query_status,
            result_row_count=row_count,
            result_truncated=truncated,
            summary=summary,
            error_message=error_message,
        )
        db = self._get_db()
        db.job_runs.insert_one(run.model_dump())

    # -------------------------------------------------------------------------
    # 4. In-Memory Job Reconciliation from MongoDB
    # -------------------------------------------------------------------------
    def reconcile_jobs(self) -> int:
        """Reconciles in-memory APScheduler triggers with active jobs in scheduled_jobs."""
        if not self._has_lease:
            return 0

        db = self._get_db()
        active_cursor = db.scheduled_jobs.find({"status": "ACTIVE"})
        active_jobs = {doc["job_id"]: doc for doc in active_cursor}

        existing_aps_jobs = {job.id: job for job in self.scheduler.get_jobs()}
        synced_count = 0

        # Remove jobs from APScheduler that are no longer ACTIVE in MongoDB
        for aps_id in list(existing_aps_jobs.keys()):
            if aps_id not in active_jobs:
                self.scheduler.remove_job(aps_id)
                logger.info(f"Removed inactive/paused job '{aps_id}' from scheduler runner.")

        # Register or update active jobs
        for job_id, job_doc in active_jobs.items():
            spec_dict = job_doc.get("schedule_spec", {})
            tz_str = job_doc.get("timezone") or spec_dict.get("timezone", "Asia/Kolkata")
            tz = ZoneInfo(tz_str)

            freq = spec_dict.get("frequency")
            cron_expr = spec_dict.get("cron_expression")

            try:
                if freq == "cron" and cron_expr:
                    trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
                elif freq == "daily":
                    trigger = CronTrigger(hour=spec_dict.get("hour", 9), minute=spec_dict.get("minute", 0), timezone=tz)
                elif freq == "weekly":
                    dow = ",".join(spec_dict.get("day_of_week") or ["mon"])
                    trigger = CronTrigger(day_of_week=dow, hour=spec_dict.get("hour", 9), minute=spec_dict.get("minute", 0), timezone=tz)
                elif freq == "monthly":
                    trigger = CronTrigger(day=spec_dict.get("day_of_month", 1), hour=spec_dict.get("hour", 9), minute=spec_dict.get("minute", 0), timezone=tz)
                else:
                    trigger = CronTrigger(hour=9, minute=0, timezone=tz)

                if job_id in existing_aps_jobs:
                    self.scheduler.modify_job(job_id, trigger=trigger)
                else:
                    self.scheduler.add_job(
                        self.execute_scheduled_job,
                        trigger=trigger,
                        args=[job_id],
                        id=job_id,
                        replace_existing=True,
                    )
                synced_count += 1
            except Exception as e:
                logger.warning(f"Could not build trigger for job '{job_id}': {e}")

        return synced_count

    # -------------------------------------------------------------------------
    # 5. Lifecycle Management
    # -------------------------------------------------------------------------
    async def _reconcile_loop(self):
        """Periodic background reconciliation loop with loss-of-lease suspension."""
        interval = settings.SCHEDULER_RECONCILE_INTERVAL_SECONDS or 30
        while self._is_running:
            try:
                has_lease = self.acquire_or_renew_lease()
                if has_lease:
                    if self._is_paused and self.scheduler.running:
                        self.scheduler.resume()
                        self._is_paused = False
                        logger.info(f"Instance '{self.instance_id}' re-acquired lease (fencing token: {self.current_fencing_token}); resumed scheduler triggers.")
                    self.reconcile_jobs()
                else:
                    if not self._is_paused and self.scheduler.running:
                        self.scheduler.pause()
                        self._is_paused = True
                        logger.warning(f"Instance '{self.instance_id}' lost or failed to acquire lease; suspended local scheduler triggers.")
            except Exception as e:
                logger.warning(f"Error in scheduler reconcile loop: {e}")
            await asyncio.sleep(interval)

    def start(self) -> None:
        """Starts the APScheduler process and reconciliation loop if enabled."""
        if self._is_running:
            return
        if not getattr(settings, "PHASE7_SCHEDULER_ENABLED", False):
            logger.info("Phase 7 scheduler is disabled by configuration (PHASE7_SCHEDULER_ENABLED=False).")
            return

        self._is_running = True
        self.acquire_or_renew_lease()
        self.scheduler.start()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        logger.info(f"SchedulerRunner '{self.instance_id}' started.")

    def shutdown(self) -> None:
        """Gracefully shuts down the scheduler and releases leases."""
        self._is_running = False
        if self._reconcile_task:
            self._reconcile_task.cancel()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.release_lease()
        logger.info("SchedulerRunner shutdown complete.")


import re
re_days_ago = re.compile(r"\$\$DAYS_AGO_(\d+)")
re_days_ahead = re.compile(r"\$\$DAYS_AHEAD_(\d+)")

scheduler_runner = SchedulerRunner()
