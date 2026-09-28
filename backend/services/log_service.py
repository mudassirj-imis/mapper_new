"""Async query service for the ``api_call_log`` audit trail."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, ApiEndpoint, CallStatusEnum
from backend.schemas.log import CallLogSummary, CallLogResponse
from backend.services.log_writer import redact

__all__ = ["get_log", "list_logs"]

_MAX_PER_PAGE = 200
#: Ceiling for ``limit``, which skips pagination and returns the newest N rows.
_MAX_LIMIT = 5000

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
    limit: int | None = None,
) -> tuple[int, list[CallLogSummary], int, int]:
    """Return ``(total, items, page, per_page)``; page is 1-based.

    ``limit`` composes with the paging arguments instead of replacing them: it
    defines a window over the newest N matching rows, so the response is
    ``limit / per_page`` pages at most and ``page`` selects the slice within
    that window. For example ``limit=40, per_page=20, page=2`` returns the
    second of two pages -- twenty rows, ids 80..61 for a hundred matches.
    Passing ``limit`` alone therefore behaves like "give me the newest N".
    """

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

    offset = (page - 1) * per_page
    row_cap = per_page
    if limit is not None:
        # ``limit`` is a window over the newest N matches and composes with
        # paging: it caps the total (``total``/``pages`` below are derived from
        # it) and clips the rows a single page may return, so
        # ``limit=40&per_page=20`` is exactly two pages of twenty.
        limit = max(1, min(int(limit), _MAX_LIMIT))
        # A page that starts past the window has nothing left to return.
        row_cap = max(0, min(per_page, limit - offset))

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

    if limit is not None:
        # The window is the result set: the caller asked for the newest N, so
        # the count is capped rather than reporting matches they can never see.
        total = min(total, limit)

    stmt = (
        select(ApiCallLog, ApiEndpoint)
        .join(
            ApiEndpoint,
            ApiCallLog.endpoint_id == ApiEndpoint.id,
        )
        .where(*conditions)
        .order_by(ApiCallLog.id.desc())
        .offset(offset)
        .limit(row_cap)
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
            # Re-redacted on read as well as on write: rows written before
            # masking existed still hold plaintext credentials.
            internal_request_headers=redact(log.source_request_headers),
            internal_request_body=redact(log.source_request_payload),
            internal_api_client_response=redact(log.source_response),
            internal_api_client_status=log.client_status_code,
            external_request_url=endpoint.target_api_url,
            external_request_method=endpoint.method,
            external_request_headers=redact(log.target_request_headers),
            external_request_body=redact(log.target_request_payload),
            external_query_params=None,
            external_response=redact(log.target_response),
            external_response_headers=redact(log.target_response_headers),
            external_response_time_ms=log.response_time_ms,
            external_status_code=log.upstream_status_code,
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
        # Re-redacted on read as well as on write, so rows written before
        # masking existed never expose a plaintext credential.
        internal_request_headers=redact(log.source_request_headers),
        internal_request_body=redact(log.source_request_payload),
        internal_api_client_response=redact(log.source_response),
        internal_api_client_status=log.client_status_code,
        external_request_url=endpoint.target_api_url,
        external_request_method=endpoint.method,
        external_request_headers=redact(log.target_request_headers),
        external_request_body=redact(log.target_request_payload),
        external_query_params=None,
        external_response=redact(log.target_response),
        external_response_headers=redact(log.target_response_headers),
        external_response_time_ms=log.response_time_ms,
        total_time_ms=log.response_time_ms,
        external_status_code=log.upstream_status_code,
        full_log=None,
        timeout_configured=None,
        tenant_id=None,
        created_at=log.created_at,
    )
