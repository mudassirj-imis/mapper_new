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


def _query_params(source: Any) -> dict[str, Any] | None:
    """Normalise a captured query mapping to a plain, redacted dict.

    Unlike :func:`_headers` this keeps repeated parameters readable: httpx
    models a key sent more than once as a list, which ``str()`` would render
    as ``['a', 'b']``. Those are joined here instead, so the audit view shows
    one row per parameter name.
    """
    if not isinstance(source, dict) or not source:
        return None

    flattened: dict[str, Any] = {}
    for key, value in redact(dict(source)).items():
        if isinstance(value, (list, tuple)):
            flattened[str(key)] = ", ".join(str(item) for item in value)
        else:
            flattened[str(key)] = str(value)

    return flattened


def _client_response(log_data: dict[str, Any]) -> dict[str, Any]:
    """Build the gateway's own response envelope for the client.

    This is deliberately *not* the upstream body -- that is stored separately
    in ``external_response``. Mirroring the legacy engine, the envelope is
    assembled here: the status codes, the message, and the payload under
    ``data``. Keeping the two apart means a passthrough call still records
    the upstream envelope verbatim in ``external_response``, while
    ``internal_api_client_response`` stays the shape the client was served.

    ``resCode``/``status_code`` sit alongside ``data`` -- never inside it.
    """
    data = log_data.get("data")
    status_code = log_data.get("status_code")

    if log_data.get("success"):
        message = (
            data.get("message", "Success") if isinstance(data, dict) else "Success"
        )
        # Fall back to the whole body when the upstream is not ``data``-shaped,
        # so nothing is dropped for APIs that return a bare payload.
        payload = data.get("data", data) if isinstance(data, dict) else data
        return {
            "success": True,
            "message": message,
            "resCode": status_code,
            "data": {} if payload is None else payload,
            "status_code": status_code,
        }

    return {
        "success": False,
        "error": log_data.get("error"),
        "message": log_data.get("error"),
        "resCode": status_code,
        "data": None,
        "status_code": status_code,
    }


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
            target_response_headers=_headers(log_data.get("external_response_headers")),
            # The query string the gateway actually dialled. The engine
            # rebuilds it on the final request URL, so it also covers params
            # already present on the target URL, not just mapped ones.
            target_query_params=_query_params(log_data.get("external_query_params")),
            client_status_code=log_data.get("status_code"),
            upstream_status_code=log_data.get("external_status_code"),
            source_request_payload=redact(
                log_data.get("internal_request_body")
                or log_data.get("request_body")
                or {}
            ),
            source_response=_client_response(log_data),
            target_request_payload=redact(log_data.get("external_request_body") or {}),
            # The raw upstream body, kept separately from the gateway envelope
            # above. Stored as ``{}`` rather than NULL so the audit trail never
            # has to distinguish "no upstream body" from "not recorded".
            target_response=redact(log_data.get("data") or {}),
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
