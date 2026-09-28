"""Call-log querying routes.

``GET /api/call-logs`` returns a paginated summary list; ``GET /api/call-logs/{id}``
returns the full audit record including every request/response header and body.
Both require an authenticated, active user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.services.central_auth import CentralUser

User = CentralUser
from backend.schemas.log import CallLogListResponse, CallLogResponse
from backend.services import log_service

__all__ = ["router"]

router = APIRouter(tags=["Call Logs"])


@router.get("/call-logs", response_model=CallLogListResponse)
async def list_call_logs(
    endpoint_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    method: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=5000,
        description=(
            "Window over the newest N matching logs, composed with the "
            "pagination parameters: the result is at most "
            "`ceil(limit / per_page)` pages, and `page` selects the slice "
            "within it."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> CallLogListResponse:
    total, items, page, per_page = await log_service.list_logs(
        db,
        endpoint_id=endpoint_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        method=method,
        page=page,
        per_page=per_page,
        limit=limit,
    )

    pages = (total + per_page - 1) // per_page if total else 0

    return CallLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/call-logs/{log_id}", response_model=CallLogResponse)
async def get_call_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> CallLogResponse:
    row = await log_service.get_log(db, log_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call log not found",
        )

    return row
