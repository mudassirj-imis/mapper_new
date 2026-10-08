"""Store call logs pushed by external producers (e.g. the CRM gateway helper).

The CRM's ``gatewayhelper`` forwards business requests to the legacy mapper
and wants its per-call audit trail stored by *this* application instead.
This module normalises whatever shape the caller sends into the canonical
``log_data`` dictionary understood by
:func:`backend.services.log_writer.write_call_log`, resolves the owning
endpoint so the dashboard (which joins logs to ``api_endpoint``) can display
the row, and persists it through the exact same redaction + audit-mirror
pipeline used by the gateway itself.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.schema_probe import probe as schema_probe
from backend.models import ApiEndpoint
from backend.schemas.log import CallLogIngestRequest, CallLogIngestResponse
from backend.services.log_writer import write_call_log

logger = logging.getLogger(__name__)

__all__ = [
    "check_ingest_token",
    "normalise_log_payload",
    "resolve_endpoint_id",
    "store_ingested_log",
]


# Canonical key -> every alias a caller may reasonably use (checked in order,
# first non-None value wins). Covers this app's own log_data keys, the legacy
# engine's MongoDB document fields, and camelCase variants.
_ALIASES: dict[str, tuple[str, ...]] = {
    "request_id": (
        "request_id",
        "requestId",
        "transaction_id",
        "correlation_id",
    ),
    "endpoint_id": ("endpoint_id", "endpointId"),
    "method": ("method", "http_method", "httpMethod", "source_method"),
    "path": ("path", "request_path", "requestPath", "route", "url", "source_url"),
    "request_headers": (
        "request_headers",
        "requestHeaders",
        "internal_request_headers",
        "source_request_headers",
        "headers",
    ),
    "response_headers": (
        "response_headers",
        "responseHeaders",
        "internal_response_headers",
        "source_response_headers",
    ),
    "external_request_headers": (
        "external_request_headers",
        "externalRequestHeaders",
        "target_request_headers",
    ),
    "external_response_headers": (
        "external_response_headers",
        "externalResponseHeaders",
        "target_response_headers",
    ),
    "external_query_params": (
        "external_query_params",
        "externalQueryParams",
        "query_params",
        "queryParams",
        "params",
    ),
    "internal_request_body": (
        "internal_request_body",
        "internalRequestBody",
        "request_body",
        "requestBody",
        "request_data",
        "requestData",
        "body",
    ),
    "data": (
        "data",
        "response",
        "response_body",
        "responseBody",
        "upstream_response",
        "internal_api_client_response",
        "source_response",
        "sourceResponse",
    ),
    "external_request_body": (
        "external_request_body",
        "externalRequestBody",
        "target_request_body",
    ),
    "external_status_code": (
        "external_status_code",
        "externalStatusCode",
        "upstream_status_code",
        "target_status_code",
    ),
    "status_code": (
        "status_code",
        "statusCode",
        "client_status_code",
        "internal_api_client_status",
        "internalApiClientStatus",
    ),
    "error": ("error", "error_message", "errorMessage", "failure"),
    "external_response_time_ms": (
        "external_response_time_ms",
        "externalResponseTimeMs",
    ),
    "total_time_ms": (
        "total_time_ms",
        "totalTimeMs",
        "response_time_ms",
        "responseTimeMs",
        "duration_ms",
        "elapsed_ms",
    ),
    "full_log": ("full_log", "fullLog", "captured_logs", "logs"),
    "timeout_configured": ("timeout_configured", "timeoutConfigured"),
    "external_request_url": ("external_request_url", "externalRequestUrl"),
    "external_request_method": (
        "external_request_method",
        "externalRequestMethod",
    ),
    "success": ("success",),
    "status": ("status",),
}

_INT_KEYS = (
    "status_code",
    "external_status_code",
    "external_response_time_ms",
    "total_time_ms",
    "timeout_configured",
)

_TRUE_TEXT = {"1", "true", "t", "yes", "y", "on"}
_FALSE_TEXT = {"0", "false", "f", "no", "n", "off"}

_SUCCESS_STATUS = {"SUCCESS", "SUCCEEDED", "OK", "PROCESSED", "UP", "PASSED"}
_FAILURE_STATUS = {"FAILED", "FAILURE", "ERROR", "DOWN", "TIMEOUT", "EXCEPTION"}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_TEXT:
            return True
        if text in _FALSE_TEXT:
            return False
    return None


def _infer_success(log_data: Mapping[str, Any]) -> bool:
    """Decide the outcome from whatever the caller actually provided."""
    explicit = _as_bool(log_data.get("success"))
    if explicit is not None:
        return explicit

    status_text = str(log_data.get("status") or "").strip().upper()
    if status_text in _SUCCESS_STATUS:
        return True
    if status_text in _FAILURE_STATUS:
        return False

    for key in ("status_code", "external_status_code"):
        code = _as_int(log_data.get(key))
        if code is not None:
            return 200 <= code < 400

    return False


def normalise_log_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Fold an inbound payload's aliases into the canonical ``log_data`` keys."""
    log_data: dict[str, Any] = {}

    for canonical, names in _ALIASES.items():
        for name in names:
            value = raw.get(name)
            if value is not None:
                log_data[canonical] = value
                break

    for key in _INT_KEYS:
        if key in log_data:
            coerced = _as_int(log_data[key])
            if coerced is not None:
                log_data[key] = coerced

    if "method" in log_data and log_data["method"] is not None:
        log_data["method"] = str(log_data["method"]).strip().upper()

    log_data["success"] = _infer_success(log_data)

    if not log_data.get("status"):
        log_data["status"] = "SUCCESS" if log_data["success"] else "FAILED"

    if not log_data.get("request_id"):
        log_data["request_id"] = str(uuid4())

    return log_data


def check_ingest_token(headers: Mapping[str, str]) -> bool:
    """Validate the optional shared secret for the ingest endpoint.

    Open (``True``) until ``LOG_INGEST_TOKEN`` is configured; afterwards the
    caller must present the value via ``X-Log-Ingest-Token`` or a Bearer
    token.
    """
    expected = str(getattr(settings, "LOG_INGEST_TOKEN", "") or "").strip()
    if not expected:
        return True

    provided = ""
    for key, value in headers.items():
        lowered = str(key).lower()
        if lowered == "x-log-ingest-token":
            provided = str(value).strip()
        elif lowered == "authorization" and not provided:
            text = str(value).strip()
            if text.lower().startswith("bearer "):
                text = text[7:].strip()
            provided = text

    return bool(provided) and secrets.compare_digest(provided, expected)


def _clean_path(path: Any) -> str:
    """Reduce whatever the caller sent to a plain path for the suffix match.

    Drops query/fragment, any scheme+host (callers often log the full URL)
    and a trailing slash.
    """
    text = str(path or "").strip()
    text = text.split("#", 1)[0].split("?", 1)[0]
    if "://" in text:
        after_scheme = text.split("://", 1)[1]
        slash = after_scheme.find("/")
        text = after_scheme[slash:] if slash >= 0 else "/"
    if len(text) > 1:
        text = text.rstrip("/")
    return text


async def _match_endpoint(
    db: AsyncSession,
    column: Any,
    path: str,
    method: str,
) -> int | None:
    """Newest endpoint whose ``column`` ends with ``path``.

    Mirrors ``GatewayEngine._find_endpoint_by_target_url`` (same LIKE-suffix
    predicate, method prefilter, ``created_at`` ordering) but prefers active
    rows via ``ORDER BY`` instead of filtering them out, so an inactive
    mapping can still anchor its historical logs.
    """
    statement = select(ApiEndpoint.id).where(column.like(f"%{path}"))

    if method:
        statement = statement.where(func.upper(ApiEndpoint.method) == method)

    statement = statement.order_by(
        ApiEndpoint.is_active.desc(),
        ApiEndpoint.created_at.desc(),
    ).limit(1)

    result = await db.execute(statement)
    return _as_int(result.scalar())


async def resolve_endpoint_id(
    db: AsyncSession,
    endpoint_id: Any = None,
    path: Any = None,
    method: Any = None,
) -> int | None:
    """Anchor a log entry to its ``api_endpoint`` row.

    An explicit id wins when the row exists; otherwise the source path is
    matched against ``target_api_url`` (the incoming route, matching this
    app's own resolver) and then ``source_api_url`` (the legacy convention
    used by the CRM helper), each with and without a method prefilter.
    """
    identifier = _as_int(endpoint_id)
    if identifier is not None:
        existing = await db.execute(
            select(ApiEndpoint.id).where(ApiEndpoint.id == identifier)
        )
        if _as_int(existing.scalar()) is not None:
            return identifier

    cleaned = _clean_path(path)
    if not cleaned:
        return None

    method_text = str(method).strip().upper() if method else ""

    for column in (ApiEndpoint.target_api_url, ApiEndpoint.source_api_url):
        for candidate_method in ((method_text, "") if method_text else ("",)):
            matched = await _match_endpoint(db, column, cleaned, candidate_method)
            if matched is not None:
                return matched

    logger.info(
        "Log ingest: no endpoint matched path=%r method=%r; storing unlinked",
        cleaned,
        method_text or None,
    )
    return None


async def store_ingested_log(
    db: AsyncSession,
    payload: CallLogIngestRequest,
) -> CallLogIngestResponse:
    """Normalise, link and persist one externally produced log entry."""
    log_data = normalise_log_payload(payload.model_dump())

    await schema_probe.ensure(db)

    endpoint_id = await resolve_endpoint_id(
        db,
        endpoint_id=log_data.get("endpoint_id"),
        path=log_data.get("path"),
        method=log_data.get("method"),
    )
    log_data["endpoint_id"] = endpoint_id

    log_id = await write_call_log(db, log_data)

    if log_id is None:
        logger.warning(
            "Log ingest: failed to store request_id=%s path=%s",
            log_data.get("request_id"),
            log_data.get("path"),
        )
        return CallLogIngestResponse(
            success=False,
            message="Call log could not be stored",
            endpoint_id=endpoint_id,
        )

    logger.info(
        "Log ingest stored: log_id=%s endpoint=%s path=%s status=%s",
        log_id,
        endpoint_id,
        log_data.get("path"),
        log_data.get("status"),
    )
    return CallLogIngestResponse(
        success=True,
        message="Call log stored",
        log_id=log_id,
        endpoint_id=endpoint_id,
    )
