from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from backend.core.config import settings
from backend.db.schema_probe import probe as schema_probe
from backend.services.log_writer import redact

logger = logging.getLogger(__name__)

__all__ = [
    "enrich_rows",
    "apply",
    "mirror_call",
    "should_mirror",
    "MONGO_FIELD_MAP",
    "MONGO_FIELD_ALIASES",
    "COLUMN_DOCUMENT_MAP",
]

_client: Any = None
_client_failed = False


MONGO_FIELD_MAP: dict[str, str] = {
    "internal_request_headers": "internal_request_headers",
    "internal_request_body": "internal_request_body",
    "internal_api_client_response": "internal_api_client_response",
    "internal_api_client_status": "internal_api_client_status",
    "external_request_url": "external_request_url",
    "external_request_method": "external_request_method",
    "external_request_headers": "external_request_headers",
    "external_request_body": "external_request_body",
    "external_query_params": "external_query_params",
    "external_response": "external_response",
    "external_response_time_ms": "external_response_time_ms",
    "external_status_code": "external_status_code",
    "full_log": "full_log",
    "timeout_configured": "timeout_configured",
}


def _collection() -> Any:

    global _client, _client_failed

    if not settings.AUDIT_MONGO_ENABLED or _client_failed:
        return None

    if _client is None:
        try:
            from pymongo import MongoClient

            _client = MongoClient(
                settings.AUDIT_MONGO_URI,
                serverSelectionTimeoutMS=settings.AUDIT_MONGO_TIMEOUT_MS,
                connectTimeoutMS=settings.AUDIT_MONGO_TIMEOUT_MS,
            )
        except Exception:
            logger.warning(
                "Audit enrichment disabled: cannot create the MongoDB client",
                exc_info=True,
            )
            _client_failed = True
            return None

    try:
        return _client[settings.AUDIT_MONGO_DATABASE][settings.AUDIT_MONGO_COLLECTION]
    except Exception:
        logger.warning("Audit enrichment disabled: MongoDB unreachable", exc_info=True)
        _client_failed = True
        return None


def _projection(fields: Iterable[str] | None = None) -> dict[str, int]:

    wanted = set(MONGO_FIELD_MAP) if fields is None else set(fields)

    projection: dict[str, int] = {"_id": 0, "timestamp": 1, "log_id": 1}
    for mongo_field, api_field in MONGO_FIELD_MAP.items():
        if api_field in wanted:
            projection[mongo_field] = 1

    for api_field, aliases in MONGO_FIELD_ALIASES.items():
        if api_field not in wanted:
            continue
        for mongo_field in aliases:
            projection.setdefault(mongo_field, 1)

    return projection


def _documents_in_range(
    start: datetime,
    end: datetime,
    fields: Iterable[str] | None = None,
) -> list[Mapping[str, Any]]:
    """Fetch audit documents written between ``start`` and ``end``."""
    collection = _collection()
    if collection is None:
        return []

    try:
        cursor = collection.find(
            {"timestamp": {"$gte": start, "$lte": end}},
            _projection(fields),
        )
        return list(cursor)
    except Exception:
        logger.warning("Audit enrichment lookup failed", exc_info=True)
        return []


def _is_empty(value: Any) -> bool:
    """Mirror the frontend's emptiness rule so we never fill with a blank."""
    if value is None:
        return True
    if isinstance(value, (str, bytes)):
        return not value.strip()
    if isinstance(value, (Mapping, list, tuple, set)):
        return len(value) == 0
    return False


def _project(
    document: Mapping[str, Any],
    allowed: set[str] | None = None,
) -> dict[str, Any]:

    projected: dict[str, Any] = {}

    for mongo_field, api_field in MONGO_FIELD_MAP.items():
        if allowed is not None and api_field not in allowed:
            continue

        names = (mongo_field, *MONGO_FIELD_ALIASES.get(api_field, ()))
        for name in names:
            if name not in document:
                continue
            value = document[name]
            if _is_empty(value):
                continue
            projected[api_field] = (
                redact(value) if isinstance(value, (dict, list)) else value
            )
            break

    return projected


def _naive(value: datetime) -> datetime:
    """Drop tzinfo so a tz-aware document cannot raise on comparison."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def enrich_rows(
    rows: Sequence[tuple[int, datetime | None]],
    fields: Iterable[str] | None = None,
) -> dict[int, dict[str, Any]]:

    if not rows:
        return {}

    window = settings.AUDIT_MATCH_WINDOW_SECONDS
    dated = [(log_id, created) for log_id, created in rows if created is not None]
    allowed = None if fields is None else set(fields)

    try:
        start = min(created for _, created in dated) - timedelta(seconds=window)
        end = max(created for _, created in dated) + timedelta(seconds=window)
        documents = _documents_in_range(start, end, fields)
    except Exception:
        logger.warning("Audit enrichment range lookup failed", exc_info=True)
        return {}

    if not documents:
        return {}

    claimed: set[int] = set()
    matched: dict[int, dict[str, Any]] = {}

    for index, document in enumerate(documents):
        log_id = document.get("log_id")
        if log_id is None:
            continue
        try:
            key = int(log_id)
        except (TypeError, ValueError):
            continue
        if key in matched or key not in {row_id for row_id, _ in rows}:
            continue
        claimed.add(index)
        matched[key] = _project(document, allowed)

    candidates: list[tuple[float, int, int, Mapping[str, Any]]] = []
    for log_id, created in dated:
        if log_id in matched:
            continue
        reference = _naive(created)
        for index, document in enumerate(documents):
            if index in claimed:
                continue
            stamped = document.get("timestamp")
            if stamped is None:
                continue
            distance = abs((reference - _naive(stamped)).total_seconds())
            candidates.append((distance, log_id, index, document))

    candidates.sort(key=lambda item: (item[0], item[1]))

    for distance, log_id, index, document in candidates:
        if distance > window or log_id in matched or index in claimed:
            continue
        claimed.add(index)
        matched[log_id] = _project(document, allowed)

    return matched


def apply(
    current: Mapping[str, Any],
    supplement: Mapping[str, Any] | None,
) -> dict[str, Any]:

    merged = dict(current)
    if not supplement:
        return merged

    for key, value in supplement.items():
        if _is_empty(merged.get(key)):
            merged[key] = value

    return merged


COLUMN_DOCUMENT_MAP: dict[str, str] = {
    "source_request_headers": "internal_request_headers",
    "source_request_payload": "internal_request_body",
    "source_response": "internal_api_client_response",
    "client_status_code": "internal_api_client_status",
    "target_request_headers": "external_request_headers",
    "target_request_payload": "external_request_body",
    "target_query_params": "external_query_params",
    "target_response": "external_response",
    "upstream_status_code": "external_status_code",
    "response_time_ms": "external_response_time_ms",
}


MONGO_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "internal_api_client_status": (
        "internal_api_client_status",
        "client_status_code",
        "status_code",
    ),
}


def should_mirror() -> bool:

    if not settings.AUDIT_MONGO_ENABLED:
        return False
    if settings.AUDIT_MONGO_MIRROR is not None:
        return bool(settings.AUDIT_MONGO_MIRROR)
    return bool(schema_probe.missing)


_ALWAYS_WRITTEN = frozenset(
    {
        "internal_request_body",
        "internal_api_client_response",
        "external_request_body",
        "external_response",
    }
)


async def mirror_call(log_id: int | None, log_data: dict[str, Any]) -> bool:

    if log_id is None or not should_mirror():
        return False

    try:
        from backend.services.log_writer import (
            _client_response,
            _headers,
            _query_params,
        )

        values: dict[str, Any] = {
            "source_request_headers": _headers(
                log_data.get("request_headers")
                or log_data.get("internal_request_headers")
            ),
            "source_request_payload": redact(
                log_data.get("internal_request_body")
                or log_data.get("request_body")
                or {}
            ),
            "source_response": _client_response(log_data),
            "client_status_code": log_data.get("status_code"),
            "target_request_headers": _headers(
                log_data.get("external_request_headers")
            ),
            "target_request_payload": redact(
                log_data.get("external_request_body") or {}
            ),
            "target_query_params": _query_params(log_data.get("external_query_params")),
            "target_response": redact(log_data.get("data") or {}),
            "upstream_status_code": log_data.get("external_status_code"),
            "response_time_ms": (
                log_data.get("external_response_time_ms")
                or log_data.get("total_time_ms")
                or 0
            ),
        }

        document: dict[str, Any] = {
            "log_id": int(log_id),
            "request_id": log_data.get("request_id"),
            "timestamp": datetime.now(),
            "method": log_data.get("method"),
            "path": log_data.get("path"),
            "status": log_data.get("status"),
            "overall_status": bool(log_data.get("success")),
            "external_request_url": log_data.get("external_request_url"),
            "external_request_method": log_data.get("external_request_method"),
            "total_time_ms": log_data.get("total_time_ms"),
            "full_log": log_data.get("full_log") or "",
            "timeout_configured": log_data.get("timeout_configured"),
        }
        for column, value in values.items():
            field = COLUMN_DOCUMENT_MAP.get(column)
            if field is None:
                continue
            if field in _ALWAYS_WRITTEN or not _is_empty(value):
                document[field] = value

        collection = _collection()
        if collection is None:
            return False

        collection.insert_one(document)
        return True

    except Exception:
        logger.warning("Audit mirror write failed for log %s", log_id, exc_info=True)
        return False
