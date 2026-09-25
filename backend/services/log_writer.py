"""Background persistence for gateway calls."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, CallStatusEnum

logger = logging.getLogger(__name__)

__all__ = ["write_call_log"]


def _client_response(log_data: dict[str, Any]) -> dict[str, Any]:
    """Build a response payload from the gateway result."""
    data = log_data.get("data")

    if log_data.get("success"):
        return data if isinstance(data, dict) else {"data": data}

    return {
        "success": False,
        "error": log_data.get("error"),
        "status_code": log_data.get("status_code"),
    }


async def write_call_log(
    db: AsyncSession,
    log_data: dict[str, Any],
) -> None:
    """Persist one api_call_log row from a gateway result dict."""

    try:
        succeeded = bool(log_data.get("success"))

        status = (
            CallStatusEnum.SUCCESS.value
            if succeeded
            else CallStatusEnum.FAILED.value
        )

        record = ApiCallLog(
            endpoint_id=log_data.get("endpoint_id"),

            # Caller -> gateway
            source_request_payload=(
                log_data.get("internal_request_body")
                or log_data.get("request_body")
                or {}
            ),

            # Gateway response to caller
            source_response=_client_response(log_data),

            # Gateway -> upstream
            target_request_payload=(
                log_data.get("external_request_body")
                or {}
            ),

            # Upstream -> gateway
            target_response=log_data.get("data"),

            status=status,

            response_time_ms=(
                log_data.get("external_response_time_ms")
                or log_data.get("total_time_ms")
                or 0
            ),

            error_message=log_data.get("error"),
        )

        db.add(record)
        await db.commit()

        logger.info(
            "api_call_log row written: endpoint=%s status=%s HTTP=%s (%sms)",
            record.endpoint_id,
            record.status,
            log_data.get("external_status_code"),
            record.response_time_ms,
        )

    except Exception:
        logger.exception("Failed to persist the gateway call log")

        try:
            await db.rollback()
        except Exception:
            logger.exception("Rollback after a failed log write also failed")