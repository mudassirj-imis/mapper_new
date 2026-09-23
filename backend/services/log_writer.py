"""Background persistence for gateway calls.

:func:`write_call_log` is scheduled as a FastAPI ``BackgroundTask`` right
after a map-and-call request is answered, so logging latency never leaks into
the caller's response. Failures are contained: a logging problem is recorded
in the application log but never surfaces as a gateway error.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, CallStatusEnum

logger = logging.getLogger(__name__)

__all__ = ["write_call_log"]


def _as_uuid(value: Any) -> UUID:
    """Coerce ``value`` to a UUID, minting a fresh one when unparseable."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return uuid4()


def _client_response(log_data: dict[str, Any]) -> dict[str, Any]:
    """Mirror of the payload the gateway returned to its caller."""
    data = log_data.get("data")
    if log_data.get("success"):
        return data if isinstance(data, dict) else {"data": data}
    return {
        "success": False,
        "error": log_data.get("error"),
        "status_code": log_data.get("status_code"),
    }


def _full_log(log_data: dict[str, Any]) -> str:
    """Compact human-readable summary stored beside the structured fields."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    lines = [
        f"[{stamp}] {log_data.get('method', '')} {log_data.get('path', '')}".rstrip(),
        f"status: {log_data.get('status', 'FAILED')} "
        f"(upstream HTTP {log_data.get('external_status_code')})",
        f"upstream: {log_data.get('external_request_method')} "
        f"{log_data.get('external_request_url')}",
        f"timing: total={log_data.get('total_time_ms')}ms "
        f"upstream={log_data.get('external_response_time_ms')}ms",
    ]
    if log_data.get("error"):
        lines.append(f"error: {log_data['error']}")
    return "\n".join(lines)


async def write_call_log(db: AsyncSession, log_data: dict[str, Any]) -> None:
    """Persist one ``api_call_logs`` row from a gateway result dict.

    ``log_data`` is the engine's result dict plus ``internal_request_body``
    (the raw payload the caller sent to the gateway).
    """
    try:
        succeeded = bool(log_data.get("success"))
        status = (
            CallStatusEnum.SUCCESS.value if succeeded else CallStatusEnum.FAILED.value
        )
        record = ApiCallLog(
            endpoint_id=log_data.get("endpoint_id"),
            request_id=_as_uuid(log_data.get("request_id")),
            method=str(log_data.get("method") or "UNKNOWN")[:10],
            path=str(log_data.get("path") or ""),
            status=status,
            overall_status=succeeded,
            # --- Internal side (caller -> gateway) --------------------------
            internal_request_headers=log_data.get("request_headers") or {},
            internal_request_body=log_data.get("internal_request_body") or {},
            internal_api_client_response=_client_response(log_data),
            internal_api_client_status=status,
            # --- External side (gateway -> upstream) ------------------------
            external_request_url=log_data.get("external_request_url"),
            external_request_method=log_data.get("external_request_method"),
            external_request_headers=log_data.get("external_request_headers") or {},
            external_request_body=log_data.get("external_request_body") or {},
            external_query_params=log_data.get("external_query_params") or {},
            external_response=log_data.get("data"),
            external_response_headers=log_data.get("external_response_headers") or {},
            external_response_time_ms=log_data.get("external_response_time_ms") or 0,
            external_status_code=log_data.get("external_status_code"),
            # --- Timing / diagnostics ---------------------------------------
            total_time_ms=log_data.get("total_time_ms") or 0,
            full_log=_full_log(log_data),
            timeout_configured=log_data.get("timeout_configured"),
            tenant_id=log_data.get("tenant_id"),
        )
        db.add(record)
        await db.commit()
        logger.info(
            "api_call_logs row written: %s %s %s -> HTTP %s (%s ms)",
            record.method,
            record.path,
            record.status,
            record.external_status_code,
            record.total_time_ms,
        )
    except Exception:
        logger.exception("Failed to persist the gateway call log")
        try:
            await db.rollback()
        except Exception:
            logger.exception("Rollback after a failed log write also failed")
