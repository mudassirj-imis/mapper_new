"""Background persistence for gateway calls."""

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiCallLog, CallStatusEnum

logger = logging.getLogger(__name__)

__all__ = ["write_call_log", "redact", "MASK"]

#: Replacement written in place of any credential value.
MASK = "********"

#: Keys whose values must never reach the database or the log, matched
#: case-insensitively. ``user``/``pass`` are included because the upstream
#: endpoints in use authenticate with them in the query string or body.
_SENSITIVE_KEYS = frozenset(
    {
        "user",
        "username",
        "pass",
        "password",
        "pwd",
        "authorization",
        "auth",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "x-api-key",
        "x-api-token",
        "x-auth-token",
        "secret",
        "client_secret",
        "cookie",
        "set-cookie",
        "session",
    }
)

#: Values that look like a credential even under an unexpected key, e.g. a
#: JWT or a "Bearer ..." string captured in a free-form header.
_BEARER = re.compile(r"^\s*(bearer|basic|token)\s+\S", re.IGNORECASE)
_JWT = re.compile(r"^\s*ey[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _is_sensitive(key: str) -> bool:
    normalised = str(key).strip().lower().replace(" ", "_")
    if normalised in _SENSITIVE_KEYS:
        return True
    # Catch variants like "userPassword" or "api_key_value".
    return any(
        part in normalised for part in ("password", "secret", "api_key", "apikey")
    )


def _scrub_value(value: str) -> str:
    """Mask a value that is credential-shaped even if the key was unusual."""
    if _BEARER.match(value) or _JWT.match(value):
        return MASK
    return value


def redact(payload: Any) -> Any:
    """Return a copy of ``payload`` with every credential value masked.

    Keys are always preserved so consumers can still see *that* a credential
    was sent; only the value is replaced. Nested dicts and lists are walked.
    """
    if isinstance(payload, dict):
        masked: dict[Any, Any] = {}
        for key, value in payload.items():
            if _is_sensitive(key):
                masked[key] = MASK
            else:
                masked[key] = redact(value)
        return masked

    if isinstance(payload, list):
        return [redact(item) for item in payload]

    if isinstance(payload, tuple):
        return tuple(redact(item) for item in payload)

    if isinstance(payload, str):
        return _scrub_value(payload)

    return payload


def _headers(source: Any) -> dict[str, Any] | None:
    """Normalise a captured header mapping to a plain, redacted dict."""
    if not isinstance(source, dict) or not source:
        return None
    return {str(key): str(value) for key, value in redact(dict(source)).items()}


def _client_response(log_data: dict[str, Any]) -> dict[str, Any]:
    """Build a response payload from the gateway result.

    ``resCode``/``status_code`` sit alongside ``data`` -- never inside it -- so
    the stored envelope keeps mirroring the payload the client received.
    """
    data = log_data.get("data")
    status_code = log_data.get("status_code")

    if log_data.get("success"):
        body = dict(data) if isinstance(data, dict) else {"data": data}
    else:
        body = {
            "success": False,
            "error": log_data.get("error"),
            "status_code": status_code,
        }

    # Added last so neither can be clobbered by an upstream key of the same
    # name, and both stay outside ``data``.
    body["resCode"] = status_code
    body["status_code"] = status_code
    return body


async def write_call_log(
    db: AsyncSession,
    log_data: dict[str, Any],
) -> None:
    """Persist one api_call_log row from a gateway result dict."""

    try:
        succeeded = bool(log_data.get("success"))

        status = (
            CallStatusEnum.SUCCESS.value if succeeded else CallStatusEnum.FAILED.value
        )

        record = ApiCallLog(
            endpoint_id=log_data.get("endpoint_id"),
            # ``request_headers`` is what the client sent; the external
            # ``external_request_headers`` is what went out upstream, which
            # additionally carries any auth header the gateway injected.
            source_request_headers=_headers(
                log_data.get("request_headers")
                or log_data.get("internal_request_headers")
            ),
            source_response_headers=_headers(
                log_data.get("response_headers")
                or log_data.get("internal_response_headers")
            ),
            target_request_headers=_headers(log_data.get("external_request_headers")),
            target_response_headers=_headers(
                log_data.get("external_response_headers")
            ),
            client_status_code=log_data.get("status_code"),
            upstream_status_code=log_data.get("external_status_code"),
            source_request_payload=redact(
                log_data.get("internal_request_body")
                or log_data.get("request_body")
                or {}
            ),
            source_response=_client_response(log_data),
            target_request_payload=redact(log_data.get("external_request_body") or {}),
            target_response=(
                redact(log_data.get("data"))
                if log_data.get("data") is not None
                else None
            ),
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
