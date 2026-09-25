"""Async query service for the ``api_call_log`` audit trail."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, ApiEndpoint, CallStatusEnum
from backend.schemas.log import CallLogSummary, CallLogResponse

__all__ = ["get_log", "list_logs"]

_MAX_PER_PAGE = 200

_VALID_STATUS = {member.value for member in CallStatusEnum}


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value

    if value in (None, ""):
        return None

    try:
        return int(str(value))
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
    endpoint_id: int | str | None = None,
    status: str | None = None,
    date_from=None,
    date_to=None,
    method: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[int, list[CallLogSummary], int, int]:
    """Return ``(total, items, page, per_page)``; page is 1-based."""

    conditions = []

    endpoint_int = _as_int(endpoint_id) if endpoint_id is not None else None

    if endpoint_int is not None:
        conditions.append(ApiCallLog.endpoint_id == endpoint_int)

    if status:
        value = str(status).strip().upper()

        if value in _VALID_STATUS:
            conditions.append(ApiCallLog.status == value)

    if method:
        conditions.append(func.upper(ApiEndpoint.method) == str(method).strip().upper())

    start = _as_datetime(date_from)

    if start is not None:
        conditions.append(ApiCallLog.created_at >= start)

    end = _as_datetime(date_to)

    if end is not None:
        conditions.append(ApiCallLog.created_at <= end)

    page = max(1, int(page))
    per_page = max(1, min(int(per_page), _MAX_PER_PAGE))

    count_stmt = (
        select(func.count())
        .select_from(ApiCallLog)
        .join(
            ApiEndpoint,
            ApiCallLog.endpoint_id == ApiEndpoint.id,
        )
        .where(*conditions)
    )

    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar() or 0)

    stmt = (
        select(ApiCallLog, ApiEndpoint)
        .join(
            ApiEndpoint,
            ApiCallLog.endpoint_id == ApiEndpoint.id,
        )
        .where(*conditions)
        .order_by(ApiCallLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(stmt)

    rows = result.all()

    items = [
        CallLogSummary(
            id=log.id,
            endpoint_id=log.endpoint_id,
            request_id=str(log.id),
            method=endpoint.method,
            path=endpoint.source_api_url,
            status=log.status,
            overall_status=(
                True
                if log.status == "SUCCESS"
                else False
                if log.status is not None
                else None
            ),
            internal_request_headers=None,
            internal_request_body=log.source_request_payload,
            internal_api_client_response=log.source_response,
            internal_api_client_status=None,
            external_request_url=endpoint.target_api_url,
            external_request_method=endpoint.method,
            external_request_headers=None,
            external_request_body=log.target_request_payload,
            external_query_params=None,
            external_response=log.target_response,
            external_response_headers=None,
            external_response_time_ms=log.response_time_ms,
            external_status_code=None,
            total_time_ms=log.response_time_ms,
            created_at=log.created_at,
        )
        for log, endpoint in rows
    ]

    return total, items, page, per_page


async def get_log(
    db: AsyncSession,
    log_id: int | str,
) -> CallLogResponse | None:
    """Return one call log with endpoint data for the frontend."""

    identifier = _as_int(log_id)

    if identifier is None:
        return None

    result = await db.execute(
        select(ApiCallLog, ApiEndpoint)
        .join(
            ApiEndpoint,
            ApiCallLog.endpoint_id == ApiEndpoint.id,
        )
        .where(ApiCallLog.id == identifier)
    )

    row = result.first()

    if row is None:
        return None

    log, endpoint = row

    return CallLogResponse(
        id=log.id,
        endpoint_id=log.endpoint_id,
        request_id=str(log.id),
        method=endpoint.method,
        path=endpoint.source_api_url,
        status=log.status,
        error_message=log.error_message,
        overall_status=(
            True
            if log.status == "SUCCESS"
            else False
            if log.status is not None
            else None
        ),
        internal_request_headers=None,
        internal_request_body=log.source_request_payload,
        internal_api_client_response=log.source_response,
        internal_api_client_status=None,
        external_request_url=endpoint.target_api_url,
        external_request_method=endpoint.method,
        external_request_headers=None,
        external_request_body=log.target_request_payload,
        external_query_params=None,
        external_response=log.target_response,
        external_response_headers=None,
        external_response_time_ms=log.response_time_ms,
        total_time_ms=log.response_time_ms,
        external_status_code=None,
        full_log=None,
        timeout_configured=None,
        tenant_id=None,
        created_at=log.created_at,
    )
