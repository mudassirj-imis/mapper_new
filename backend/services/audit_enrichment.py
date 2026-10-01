"""MongoDB-backed enrichment for call-log rows.

Every gateway call produces two records: a compact MySQL row in
``api_call_log`` (what the list view pages over) and a full-detail MongoDB
document written by the legacy ``mapper-engine`` gateway. That document holds
everything the detail view renders -- both sides' headers and bodies, the
query string, the status codes and the captured console log.

Rows this backend writes already carry the detail in MySQL. Rows written by
the legacy gateway cannot: its model has no header columns, so MySQL is null
and the UI blocks render empty even though the data exists in MongoDB.

This module bridges the two. It pairs a row to its document by write time --
both records are produced by the same in-process call, so they land within
milliseconds of each other -- and returns the document's fields for the caller
to merge over the NULL columns.

Mongo is a *supplement*, never a dependency: every failure path degrades to
"no enrichment" so the log views keep working when Mongo is down.
"""

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

#: MongoDB document field -> the ``CallLogResponse`` field it satisfies.
#: The names are identical in both systems; the mapping is kept explicit so the
#: API contract lives in one place and a rename cannot drift silently.
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
    """Return the audit collection, or ``None`` when Mongo is unusable.

    The client is built once per process and reused so it pools connections
    and reconnects on its own. A failed attempt is remembered, so a down Mongo
    costs one timeout per process rather than one per log-view request.
    """
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
    """Build the Mongo projection for the API fields the caller needs.

    Documents average ~47 KB because ``full_log`` holds the captured console
    trace. The list view never renders it, so fetching it would move megabytes
    per page only for the payload to be discarded on arrival. Callers pass
    their schema's fields and Mongo returns just those.
    """
    wanted = set(MONGO_FIELD_MAP) if fields is None else set(fields)

    projection: dict[str, int] = {"_id": 0, "timestamp": 1, "log_id": 1}
    for mongo_field, api_field in MONGO_FIELD_MAP.items():
        if api_field in wanted:
            projection[mongo_field] = 1
    # Aliases are only worth fetching for a field the caller will actually use,
    # for the same reason: the projection is the cheap half of this query.
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
    """Copy the fields we care about, re-redacting on the way out.

    The legacy engine masks before writing, but documents are re-redacted here
    for the same reason MySQL rows are: anything written before masking existed
    must never surface a plaintext credential.

    ``allowed`` narrows the copy to the API fields the caller asked for, so a
    field Mongo returned but the target schema cannot use is dropped here
    rather than carried through the merge.
    """
    projected: dict[str, Any] = {}

    for mongo_field, api_field in MONGO_FIELD_MAP.items():
        if allowed is not None and api_field not in allowed:
            continue
        # The canonical name first, then any alias the legacy engine may have
        # used for the same value.
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
    """Pair ``(log_id, created_at)`` rows to their MongoDB documents.

    Two pairing strategies, in order of trust. A document written by this
    backend carries the row's own ``log_id``, which is an exact match; a
    document written by the legacy engine does not, so its rows fall back to
    write-time proximity.

    One range query covers the whole page, so a 25-row view costs the same
    round trip as one row. Proximity matching is greedy on absolute time
    distance, which stops two calls landing in the same second from stealing
    each other's document.

    ``fields`` narrows both the projection and the result to the API fields the
    caller will actually use -- the list schema does not carry ``full_log``,
    and asking Mongo for it would pull tens of kilobytes per row for nothing.

    Returns ``{log_id: {field: value}}`` for rows that matched. Failures yield
    an empty mapping rather than raising: the log views must not break because
    the audit store is unavailable.
    """
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

    # Exact pairing first: a document that names its row can never be matched
    # to the wrong call, however close another one was written.
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
    """Merge a document's fields over a row, never displacing stored data.

    MySQL stays authoritative: a field it already holds is left alone, so the
    detail view shows what this backend recorded rather than a legacy snapshot
    describing a different call.
    """
    merged = dict(current)
    if not supplement:
        return merged

    for key, value in supplement.items():
        if _is_empty(merged.get(key)):
            merged[key] = value

    return merged


#: ``api_call_log`` column -> the audit document field carrying the same value.
#: The inverse of :data:`MONGO_FIELD_MAP`, used when a row is written to a
#: database that cannot store the detail and it has to go to Mongo instead.
#: ``source_response_headers``/``target_response_headers`` are absent on
#: purpose: the API schema has nowhere to render them, so writing them would
#: only grow the document.
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

#: Document field -> extra names the legacy engine may have used. The client
#: status is the one value the engine is known to spell more than one way, so
#: the alternatives are listed in preference order and the first non-empty hit
#: wins.
MONGO_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "internal_api_client_status": (
        "internal_api_client_status",
        "client_status_code",
        "status_code",
    ),
}


def should_mirror() -> bool:
    """Whether this process should also write its own calls to MongoDB.

    Automatic by default: only when ``api_call_log`` is missing the columns that
    would hold the detail, so a migrated database pays nothing and an
    un-migratable one still gets a complete audit view. ``AUDIT_MONGO_MIRROR``
    forces the decision either way.
    """
    if not settings.AUDIT_MONGO_ENABLED:
        return False
    if settings.AUDIT_MONGO_MIRROR is not None:
        return bool(settings.AUDIT_MONGO_MIRROR)
    return bool(schema_probe.missing)


#: Document fields written whenever the gateway produced them, even when the
#: value is an empty body. A GET with no request body records ``{}``, which is a
#: fact about the call -- unlike an absent header block, which means "not
#: captured" and should stay out of the document.
_ALWAYS_WRITTEN = frozenset(
    {
        "internal_request_body",
        "internal_api_client_response",
        "external_request_body",
        "external_response",
    }
)


async def mirror_call(log_id: int | None, log_data: dict[str, Any]) -> bool:
    """Write one gateway call to the audit collection as a document.

    Used when the row in MySQL cannot hold the detail, so the enrichment pass
    can still serve it. The document is stamped with the row's own ``id``,
    which lets :func:`enrich_rows` pair the two exactly instead of by write
    time.

    Returns whether a document was written. Every failure is swallowed and
    reported as ``False``: a missing audit document must never fail a call that
    was already proxied and already recorded in MySQL.
    """
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
            "target_query_params": _query_params(
                log_data.get("external_query_params")
            ),
            "target_response": redact(log_data.get("data") or {}),
            "upstream_status_code": log_data.get("external_status_code"),
            "response_time_ms": (
                log_data.get("external_response_time_ms")
                or log_data.get("total_time_ms")
                or 0
            ),
        }

        document: dict[str, Any] = {
            # Our addition to the engine's shape: it lets
            # :func:`enrich_rows` pair a document to its row exactly instead of
            # by write time, and is ignored by every other reader.
            "log_id": int(log_id),
            # The rest mirrors the legacy engine's document field for field, so
            # both writers produce the same shape and existing queries keep
            # working over a mixed collection.
            "request_id": log_data.get("request_id"),
            "timestamp": datetime.now(),
            "method": log_data.get("method"),
            "path": log_data.get("path"),
            "status": log_data.get("status"),
            "overall_status": bool(log_data.get("success")),
            "external_request_url": log_data.get("external_request_url"),
            "external_request_method": log_data.get("external_request_method"),
            "total_time_ms": log_data.get("total_time_ms"),
            # The engine's console trace. This backend has no equivalent, so it
            # writes an empty string rather than omitting the key, matching what
            # the engine writes for a call with nothing captured.
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


