"""Async query service for the ``api_call_logs`` audit trail.

``list_logs`` applies the supported filters (endpoint, status, date range,
method), counts the total and returns one page (newest first). ``get_log``
fetches a single record with every JSON audit column for the full-detail view.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, CallStatusEnum

__all__ = ["get_log", "list_logs"]

#: Hard cap on per_page so a hostile caller cannot request a giant page.
_MAX_PER_PAGE = 200

_VALID_STATUS = {member.value for member in CallStatusEnum}


def _as_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def list_logs(
    db: AsyncSession,
    *,
    endpoint_id: str | UUID | None = None,
    status: str | None = None,
    date_from=None,
    date_to=None,
    method: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[int, list[ApiCallLog], int, int]:
    """Return ``(total, items, page, per_page)``; page is 1-based."""
    conditions = []

    endpoint_uuid = _as_uuid(endpoint_id) if endpoint_id is not None else None
    if endpoint_uuid is not None:
        conditions.append(ApiCallLog.endpoint_id == endpoint_uuid)

    if status:
        value = str(status).strip().upper()
        if value in _VALID_STATUS:
            conditions.append(ApiCallLog.status == value)

    if method:
        conditions.append(func.upper(ApiCallLog.method) == str(method).strip().upper())

    start = _as_datetime(date_from)
    if start is not None:
        conditions.append(ApiCallLog.created_at >= start)
    end = _as_datetime(date_to)
    if end is not None:
        conditions.append(ApiCallLog.created_at <= end)

    page = max(1, int(page))
    per_page = max(1, min(int(per_page), _MAX_PER_PAGE))

    count_result = await db.execute(
        select(func.count()).select_from(ApiCallLog).where(*conditions)
    )
    total = int(count_result.scalar() or 0)

    stmt = (
        select(ApiCallLog)
        .where(*conditions)
        .order_by(ApiCallLog.created_at.desc(), ApiCallLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return total, list(result.scalars().all()), page, per_page


async def get_log(db: AsyncSession, log_id: str | UUID) -> ApiCallLog | None:
    """Return one call log (full detail) or ``None`` when missing."""
    identifier = _as_uuid(log_id)
    if identifier is None:
        return None
    result = await db.execute(
        select(ApiCallLog).where(ApiCallLog.id == identifier)
    )
    return result.scalar_one_or_none()