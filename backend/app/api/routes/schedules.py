"""
FinTech Agent — Scheduled Queries and Jobs API Routes (Phase 7)
Provides endpoints for explicit schedule preview approval, job lifecycle
management (list, inspect, pause, resume, cancel), and execution history.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from backend.app.core.auth import (
    AuthenticatedUser,
    get_current_authenticated_user,
)
from backend.app.core.logging import logger, sanitize_error_message
from backend.app.schemas.schedule import (
    JobRun,
    ScheduleApprovalRequest,
    ScheduleApprovalResponse,
    ScheduledJob,
)
from backend.app.services.schedule_service import (
    ScheduleOwnershipError,
    SchedulePreviewNotFoundError,
    ScheduleServiceError,
    schedule_service,
)

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post(
    "/approve",
    response_model=ScheduleApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a pending schedule preview",
)
async def approve_schedule(
    request: ScheduleApprovalRequest,
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Explicitly approves a pending schedule preview, activating the job."""
    owner_id = current_user.user_id
    try:
        job = schedule_service.approve_preview(
            preview_id=request.preview_id,
            owner_id=owner_id,
            idempotency_key=request.idempotency_key,
        )
        return ScheduleApprovalResponse(
            success=True,
            job_id=job.job_id,
            status=job.status,
            next_run_time=job.next_run_at,
            message=f"Schedule '{job.job_id}' successfully approved and activated.",
        )
    except SchedulePreviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScheduleServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Unexpected error approving schedule preview: {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get(
    "",
    response_model=List[ScheduledJob],
    summary="List all scheduled jobs owned by the user",
)
async def list_schedules(current_user: AuthenticatedUser = Depends(get_current_authenticated_user)):
    """Retrieves all scheduled jobs belonging strictly to the requesting user."""
    owner_id = current_user.user_id
    try:
        return schedule_service.list_jobs(owner_id=owner_id)
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error listing schedules for user '{owner_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not list schedules")


@router.get(
    "/{job_id}",
    response_model=ScheduledJob,
    summary="Retrieve details of a specific scheduled job",
)
async def get_schedule(
    job_id: str,
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Retrieves details of a scheduled job after validating ownership."""
    owner_id = current_user.user_id
    try:
        job = schedule_service.get_job(job_id=job_id, owner_id=owner_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled job '{job_id}' not found.",
            )
        return job
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error retrieving schedule '{job_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve schedule")


@router.post(
    "/{job_id}/pause",
    response_model=ScheduledJob,
    summary="Pause an active scheduled job",
)
async def pause_schedule(
    job_id: str,
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Pauses future executions of an active scheduled job."""
    owner_id = current_user.user_id
    try:
        return schedule_service.pause_job(job_id=job_id, owner_id=owner_id)
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScheduleServiceError as exc:
        status_c = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_c, detail=str(exc))
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error pausing schedule '{job_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not pause schedule")


@router.post(
    "/{job_id}/resume",
    response_model=ScheduledJob,
    summary="Resume a paused scheduled job",
)
async def resume_schedule(
    job_id: str,
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Resumes a paused scheduled job following deterministic pipeline revalidation."""
    owner_id = current_user.user_id
    try:
        return schedule_service.resume_job(job_id=job_id, owner_id=owner_id)
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScheduleServiceError as exc:
        status_c = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_c, detail=str(exc))
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error resuming schedule '{job_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not resume schedule")


@router.post(
    "/{job_id}/cancel",
    response_model=ScheduledJob,
    summary="Cancel a scheduled job",
)
async def cancel_schedule(
    job_id: str,
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Permanently cancels a scheduled job."""
    owner_id = current_user.user_id
    try:
        return schedule_service.cancel_job(job_id=job_id, owner_id=owner_id)
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScheduleServiceError as exc:
        status_c = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_c, detail=str(exc))
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error cancelling schedule '{job_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not cancel schedule")


@router.get(
    "/{job_id}/runs",
    response_model=List[JobRun],
    summary="Get execution history for a scheduled job",
)
async def get_schedule_runs(
    job_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_authenticated_user),
):
    """Retrieves durable execution run history from agent_metadata_db.job_runs."""
    owner_id = current_user.user_id
    try:
        return schedule_service.get_job_runs(job_id=job_id, owner_id=owner_id, limit=limit)
    except ScheduleOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScheduleServiceError as exc:
        status_c = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_c, detail=str(exc))
    except Exception as exc:
        safe_msg = sanitize_error_message(str(exc))
        logger.error(f"Error retrieving runs for schedule '{job_id}': {safe_msg}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve schedule runs")
