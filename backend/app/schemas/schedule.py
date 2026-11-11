"""
FinTech Agent — Phase 7 Schedule Schemas and Data Models
Defines structured contracts for schedule specifications, previews,
approval workflows, durable job representations, and run history.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import uuid
import zoneinfo
from pydantic import BaseModel, Field, field_validator

ScheduleFrequency = Literal["daily", "weekly", "monthly", "cron"]

JobStatus = Literal[
    "PENDING_APPROVAL",
    "ACTIVE",
    "PAUSED",
    "CANCELLED",
    "COMPLETED",
    "AUTO_PAUSED",
    "FAILED_CONFIGURATION",
]

RunStatus = Literal["SUCCESS", "FAILED", "SKIPPED"]


class ScheduleSpec(BaseModel):
    """Normalized specification for a recurring banking query schedule."""
    frequency: ScheduleFrequency = Field(..., description="Schedule frequency (daily, weekly, monthly, cron)")
    recurrence_expression: str = Field(..., description="Human-readable description or cron string")
    timezone: str = Field(default="Asia/Kolkata", description="Valid IANA timezone identifier")
    start_at: Optional[datetime] = Field(default=None, description="Optional start datetime (UTC)")
    end_at: Optional[datetime] = Field(default=None, description="Optional end datetime (UTC)")
    hour: Optional[int] = Field(default=9, ge=0, le=23, description="Hour of day (0-23)")
    minute: Optional[int] = Field(default=0, ge=0, le=59, description="Minute of hour (0-59)")
    day_of_week: Optional[List[str]] = Field(default=None, description="Days of week for weekly schedule (e.g. ['mon'])")
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31, description="Day of month for monthly schedule (1-31)")
    cron_expression: Optional[str] = Field(default=None, description="Standard 5-field cron expression")
    enabled: bool = Field(default=True, description="Whether the schedule is active")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        clean = (v or "").strip()
        if not clean:
            return "Asia/Kolkata"
        try:
            zoneinfo.ZoneInfo(clean)
        except Exception:
            raise ValueError(f"Invalid IANA timezone identifier: '{clean}'.")
        return clean

    @field_validator("end_at")
    @classmethod
    def validate_dates(cls, end_at: Optional[datetime], info) -> Optional[datetime]:
        start_at = info.data.get("start_at")
        if start_at and end_at and end_at <= start_at:
            raise ValueError("end_at must be strictly after start_at.")
        return end_at


class SchedulePreview(BaseModel):
    """Immutable preview generated before explicit user approval."""
    preview_id: str = Field(default_factory=lambda: f"prev_{uuid.uuid4().hex[:12]}")
    owner_id: str = Field(..., description="Authenticated user ID who owns the schedule")
    report_name: str = Field(..., description="Human-readable report name")
    natural_language_query: str = Field(..., description="Original user prompt")
    target_collection: str = Field(..., description="Target banking collection")
    pipeline_explanation: str = Field(..., description="Explanation of validated query pipeline")
    approved_pipeline: List[Dict[str, Any]] = Field(..., description="Deterministic validated MQL pipeline")
    pipeline_hash: str = Field(..., description="SHA-256 hash of approved pipeline for tamper verification")
    schedule_spec: ScheduleSpec = Field(..., description="Structured schedule specification")
    next_run_times: List[str] = Field(..., description="Next 3 run timestamps in ISO UTC format")
    dry_run_status: str = Field(default="NOT_PERMITTED", description="Status of bounded dry run (SUCCESS, GATE_BLOCKED, etc.)")
    dry_run_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="Up to 10 sample preview documents")
    warning: Optional[str] = Field(default=None, description="Any limit or data truncation warnings")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = Field(..., description="Timestamp after which preview cannot be approved")
    status: JobStatus = Field(default="PENDING_APPROVAL")


class ScheduleApprovalRequest(BaseModel):
    """Request payload to approve a pending schedule preview."""
    preview_id: str = Field(..., description="Server-issued preview identifier")
    idempotency_key: Optional[str] = Field(default=None, description="Client-provided idempotency key")


class ScheduleApprovalResponse(BaseModel):
    """Response payload returned upon approving a schedule."""
    success: bool
    job_id: str
    status: JobStatus
    next_run_time: Optional[str] = None
    message: str


class ScheduledJob(BaseModel):
    """Durable document stored in agent_metadata_db.scheduled_jobs."""
    job_id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    owner_id: str = Field(..., description="Authenticated user ID")
    report_name: str
    natural_language_query: str
    target_collection: str
    pipeline_template: List[Dict[str, Any]]
    pipeline_hash: str
    schedule_spec: ScheduleSpec
    timezone: str
    status: JobStatus = Field(default="ACTIVE")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    consecutive_failures: int = Field(default=0)
    failure_threshold: int = Field(default=3)
    idempotency_key: Optional[str] = None
    preview_id: Optional[str] = None
    notification_config: Optional[Dict[str, Any]] = None


class JobRun(BaseModel):
    """Durable execution record stored in agent_metadata_db.job_runs."""
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    job_id: str
    owner_id: str
    start_time: str
    end_time: str
    duration_ms: int
    status: RunStatus
    pipeline_hash: str
    query_execution_status: str
    result_row_count: int = 0
    result_truncated: bool = False
    summary: str
    error_message: Optional[str] = None
    notification_status: Optional[str] = None
