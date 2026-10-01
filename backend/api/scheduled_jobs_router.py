"""Authenticated scheduler configuration and run-history routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user
from backend.db.scheduler_session import get_scheduler_db
from backend.models.scheduled_job import ScheduledJob
from backend.schemas.common import SuccessResponse
from backend.schemas.scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobResponse,
    ScheduledJobRunResponse,
    ScheduledJobRunSummary,
    ScheduledJobToggle,
)
from backend.services import scheduler_service
from backend.services.central_auth import CentralUser
from backend.services.scheduler_security import UnsafeDestinationError

__all__ = ["router"]
router = APIRouter(tags=["Scheduled Jobs"])
User = CentralUser


def _summary(run) -> ScheduledJobRunSummary:
    """History row for the list endpoints, without the captured payload."""
    return ScheduledJobRunSummary(
        id=run.id,
        job_id=run.job_id,
        url=run.url,
        method=run.method,
        status_code=run.status_code,
        success=run.success,
        duration_ms=run.duration_ms,
        error=run.error,
        ran_at=run.ran_at,
        response_size=run.response_size,
        has_response_body=bool(run.response_body),
    )


def _detail(run) -> ScheduledJobRunResponse:
    """Full run detail, including both header sets and the response body."""
    return ScheduledJobRunResponse(
        id=run.id,
        job_id=run.job_id,
        url=run.url,
        method=run.method,
        status_code=run.status_code,
        success=run.success,
        duration_ms=run.duration_ms,
        error=run.error,
        ran_at=run.ran_at,
        response_size=run.response_size,
        has_response_body=bool(run.response_body),
        request_headers=scheduler_service.load_headers(run.request_headers),
        response_headers=scheduler_service.load_headers(run.response_headers),
        response_body=run.response_body,
        response_body_truncated=run.response_body_truncated,
    )


async def _response(db: AsyncSession, row: ScheduledJob) -> ScheduledJobResponse:
    live_job = scheduler_service.get_job(row.job_id)
    latest_run = await scheduler_service.get_latest_run(db, row.job_id)
    return ScheduledJobResponse(
        job_id=row.job_id,
        name=row.name,
        url=row.url,
        method=row.method,
        headers=scheduler_service.load_headers(row.headers),
        body=row.body,
        cron=row.cron,
        interval_seconds=row.interval_seconds,
        enabled=row.enabled,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        next_run_time=live_job.next_run_time if live_job else None,
        last_run_at=latest_run.ran_at if latest_run else None,
        last_success=latest_run.success if latest_run else None,
    )


@router.get("/scheduled-jobs", response_model=list[ScheduledJobResponse])
async def list_scheduled_jobs(
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    rows = await scheduler_service.list_jobs(db)
    return [await _response(db, row) for row in rows]


@router.post(
    "/scheduled-jobs",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_job(
    payload: ScheduledJobCreate,
    db: AsyncSession = Depends(get_scheduler_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        row = await scheduler_service.create_job(db, payload, current_user.id)
    except scheduler_service.SchedulerConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except scheduler_service.SchedulerLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsafeDestinationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid schedule") from exc
    return await _response(db, row)


@router.patch("/scheduled-jobs/{job_id}", response_model=ScheduledJobResponse)
async def toggle_scheduled_job(
    job_id: str,
    payload: ScheduledJobToggle,
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    try:
        row = await scheduler_service.set_job_enabled(db, job_id, payload.enabled)
    except UnsafeDestinationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid schedule") from None
    except scheduler_service.SchedulerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _response(db, row)


@router.delete("/scheduled-jobs/{job_id}", response_model=SuccessResponse)
async def delete_scheduled_job(
    job_id: str,
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    if not await scheduler_service.delete_job(db, job_id):
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return SuccessResponse(success=True, message="Scheduled job deleted")


@router.get(
    "/scheduled-jobs/{job_id}/runs", response_model=list[ScheduledJobRunSummary]
)
async def get_scheduled_job_runs(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    runs = await scheduler_service.get_runs(db, job_id, limit)
    return [_summary(run) for run in runs]


@router.get("/scheduled-runs/{run_id}", response_model=ScheduledJobRunResponse)
async def get_scheduled_run_detail(
    run_id: int,
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    """Full detail for one execution, including request/response headers and body."""
    run = await scheduler_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scheduled job run not found")
    return _detail(run)


@router.post("/scheduled-jobs/{job_id}/run", response_model=ScheduledJobRunResponse)
async def run_scheduled_job_now(
    job_id: str,
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    try:
        run = await scheduler_service.run_job_now(db, job_id)
    except scheduler_service.SchedulerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _detail(run)


@router.get("/scheduled-runs", response_model=list[ScheduledJobRunSummary])
async def get_all_scheduled_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_scheduler_db),
    _current_user: User = Depends(get_current_active_user),
):
    runs = await scheduler_service.get_all_runs(db, limit)
    return [_summary(run) for run in runs]
