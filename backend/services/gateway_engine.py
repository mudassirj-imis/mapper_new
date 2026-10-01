import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApiEndpoint, CallStatusEnum, ParameterMapping
from backend.services import mock_service, parameter_service
from backend.services.upstream_auth import apply_upstream_auth

logger = logging.getLogger(__name__)

__all__ = [
    "GatewayEngine",
    "EndpointSnapshot",
    "MappingSnapshot",
    "ExecutionOutcome",
    "FailureKind",
    "ExecutionSource",
]

FailureKind = (
    Literal[
        "not_found",
        "configuration",
        "upstream_http",
        "upstream_timeout",
        "transport",
        "local_pool_timeout",
        "internal",
    ]
    | None
)
ExecutionSource = Literal["live", "mock", "cache", "policy"]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EndpointSnapshot:
    """Detached gateway configuration."""

    id: int
    endpoint_code: str | None
    source_api_url: str
    target_api_url: str
    method: str | None
    is_active: bool | None
    tenant_id: str | None = None
    rate_limit_rpm: int | None = None
    mock_enabled: bool = False
    updated_at: datetime | None = None

    _mock_response: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_mock_response", _freeze(self._mock_response))

    @property
    def mock_response(self) -> Any:
        return _thaw(self._mock_response)


@dataclass(frozen=True, slots=True)
class MappingSnapshot:
    source_parameter: str
    target_parameter: str
    parameter_type: str | None
    data_type: str | None


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """Immutable internal result; ``to_result`` recreates the legacy envelope."""

    result: Mapping[str, Any]
    failure_kind: FailureKind = None
    source: ExecutionSource = "live"
    upstream_attempted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", _freeze(self.result))

    @property
    def success(self) -> bool:
        return bool(self.result.get("success"))

    @property
    def upstream_status(self) -> int | None:
        return self.result.get("external_status_code")

    @property
    def upstream_audit(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                **{
                    key: value
                    for key, value in self.result.items()
                    if key.startswith("external_")
                },
                "external_response": self.result.get("data")
                if self.upstream_attempted
                else None,
            }
        )

    def to_result(self) -> dict[str, Any]:
        return _thaw(self.result)


_ENDPOINT_COLUMNS = (
    "id",
    "endpoint_code",
    "source_api_url",
    "target_api_url",
    "method",
    "is_active",
    "updated_at",
)


def _endpoint_snapshot(row):
    if row is None:
        return None

    values = dict(row)

    return EndpointSnapshot(
        id=int(values["id"]),
        endpoint_code=values.get("endpoint_code"),
        source_api_url=values.get("source_api_url") or "",
        target_api_url=values.get("target_api_url") or "",
        method=values.get("method"),
        is_active=values.get("is_active"),
        tenant_id=None,
        rate_limit_rpm=None,
        mock_enabled=False,
        updated_at=values.get("updated_at"),
        _mock_response=None,
    )


def _http_failure(status: int) -> FailureKind:
    if status in (408, 504):
        return "upstream_timeout"
    return None if 200 <= status < 400 else "upstream_http"


_STATIC_PREFIX = "static:"


_DEFAULT_CONTENT_TYPE = "application/json"


_CONNECT_TIMEOUT_SECONDS = 10.0


def _as_int(value: object) -> int | None:
    """Best-effort conversion of ``value`` to the integer endpoint id."""
    if isinstance(value, int):
        return value
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _elapsed_ms(started: float) -> int:
    """Milliseconds elapsed since ``started`` (a ``perf_counter`` mark)."""
    return int((time.perf_counter() - started) * 1000)


_LOG_ONLY_MESSAGE = "Log-only endpoint, no external call made"


def _log_only_result(
    *,
    request_id: str,
    endpoint_id: int,
    tenant_id: str | None,
    method: str,
    url: str,
    headers: dict[str, Any] | None,
    timeout: int,
) -> dict[str, Any]:
    """Result envelope for a log-only endpoint (scheme-less ``source_api_url``)."""
    return {
        "request_id": request_id,
        "endpoint_id": endpoint_id,
        "tenant_id": tenant_id,
        "method": method,
        "path": url,
        "request_headers": dict(headers or {}),
        "success": True,
        "data": {"message": _LOG_ONLY_MESSAGE},
        "status_code": 200,
        "response_time_ms": 0,
        "response_headers": {"Content-Type": "application/json"},
        "error": None,
        "failure_kind": None,
        "upstream_attempted": False,
        "source": "policy",
        "external_request_url": None,
        "external_request_method": None,
        "external_request_headers": None,
        "external_request_body": None,
        "external_query_params": None,
        "external_response_headers": None,
        "external_status_code": None,
        "external_response_time_ms": None,
        "total_time_ms": 0,
        "status": CallStatusEnum.SUCCESS.value,
        "timeout_configured": timeout,
    }


class GatewayEngine:
    """Execute one map-and-call cycle against a registered endpoint."""

    def __init__(
        self,
        db: AsyncSession,
        http_client: httpx.AsyncClient,
        timeout: int = 60,
    ) -> None:
        self.db = db
        self.http_client = http_client
        self.timeout = timeout

        self._request_timeout = httpx.Timeout(
            float(timeout), connect=min(_CONNECT_TIMEOUT_SECONDS, float(timeout))
        )

    async def process_request(
        self,
        endpoint_id: int | str | None,
        request_data: dict[str, Any] | None,
        headers: dict[str, Any] | None = None,
        target_url: str | None = None,
        target_method: str | None = None,
    ) -> dict[str, Any]:
        """Run the full pipeline and return an audit-complete result dict."""
        started = time.perf_counter()
        method = str(target_method or "").strip().upper()
        url = str(target_url or "").strip()
        result = self._new_result(headers, url, method)
        try:
            endpoint = await self.resolve_endpoint(endpoint_id, url, method)
            if endpoint is None:
                result["status_code"] = 404
                result["error"] = await self._not_found_message(method, url)
            else:
                outcome = await self.execute_resolved(
                    endpoint, request_data, headers, url, method
                )
                result = outcome.to_result()
        except Exception as exc:
            logger.exception(
                "Gateway call %s: unexpected pipeline failure", result["request_id"]
            )
            result["status_code"] = result["status_code"] or 500
            result["error"] = f"Gateway encountered an internal error: {exc}"
        finally:
            result["total_time_ms"] = _elapsed_ms(started)
        return result

    def _new_result(
        self, headers: dict[str, Any] | None, url: str, method: str
    ) -> dict[str, Any]:
        client_headers = dict(headers or {})
        return {
            "request_id": str(uuid4()),
            "endpoint_id": None,
            "tenant_id": None,
            "method": method,
            "path": url,
            "request_headers": client_headers,
            "success": False,
            "data": None,
            "status_code": None,
            "response_time_ms": None,
            "total_time_ms": None,
            "response_headers": None,
            "error": None,
            "external_request_url": None,
            "external_request_method": None,
            "external_request_headers": None,
            "external_request_body": None,
            "external_query_params": None,
            "external_response_headers": None,
            "external_status_code": None,
            "external_response_time_ms": None,
            "status": CallStatusEnum.FAILED.value,
            "timeout_configured": self.timeout,
        }

    async def execute_resolved(
        self,
        endpoint: EndpointSnapshot,
        request_data: dict[str, Any] | None,
        headers: dict[str, Any] | None = None,
        target_url: str | None = None,
        target_method: str | None = None,
        *,
        mappings: Sequence[MappingSnapshot] | None = None,
    ) -> ExecutionOutcome:
        """Live execution only; supplied snapshots skip all mapping queries."""
        started = time.perf_counter()
        method = str(target_method or "").strip().upper()
        url = str(target_url or "").strip()
        result = self._new_result(headers, url, method)
        result["endpoint_id"] = endpoint.id
        result["tenant_id"] = endpoint.tenant_id
        failure_kind: FailureKind = None
        upstream_attempted = False

        if endpoint.mock_enabled:
            result.update(
                mock_service.build_mock_result(
                    endpoint,
                    request_id=result["request_id"],
                    method=method,
                    url=url,
                    headers=headers,
                )
            )
            result["total_time_ms"] = _elapsed_ms(started)
            return ExecutionOutcome(result, None, "mock", upstream_attempted)

        try:
            if mappings is None:
                mappings = await self.load_mappings(endpoint)
            else:
                await self._finish_read()
            body_params, header_params, query_params = self._transform_parameters(
                dict(request_data or {}), mappings, dict(headers or {})
            )

            upstream_url = str(endpoint.source_api_url or "").strip()
            upstream_method = str(endpoint.method or "POST").strip().upper()
            if not upstream_url:
                result["status_code"] = 500
                result["error"] = "Endpoint has no source (upstream) URL configured"
                logger.error(
                    "Gateway call %s: endpoint %s has no source_api_url",
                    result["request_id"],
                    endpoint.id,
                )
                result["total_time_ms"] = _elapsed_ms(started)
                return ExecutionOutcome(result, failure_kind="configuration")

            if not upstream_url.lower().startswith(("http://", "https://")):
                result.update(
                    _log_only_result(
                        request_id=result["request_id"],
                        endpoint_id=endpoint.id,
                        tenant_id=endpoint.tenant_id,
                        method=method,
                        url=url,
                        headers=headers,
                        timeout=self.timeout,
                    )
                )
                logger.info(
                    "Gateway call %s: endpoint %s source URL %r has no scheme "
                    "— log-only, no upstream call",
                    result["request_id"],
                    endpoint.id,
                    upstream_url,
                )
                return ExecutionOutcome(result, None, "policy", False)

            logger.info(
                "Gateway call %s: %s %s -> %s %s (body=%d header=%d query=%d)",
                result["request_id"],
                method,
                url,
                upstream_method,
                upstream_url,
                len(body_params),
                len(header_params),
                len(query_params),
            )

            call = await self._call_upstream(
                upstream_method, upstream_url, body_params, header_params, query_params
            )
            failure_kind = call.pop("failure_kind")
            upstream_attempted = call.pop("upstream_attempted")
            result.update(call)
            result["status"] = (
                CallStatusEnum.SUCCESS.value
                if result["success"]
                else CallStatusEnum.FAILED.value
            )
            if not result["success"]:
                logger.warning(
                    "Gateway call %s: upstream HTTP %s (%s)",
                    result["request_id"],
                    result["status_code"],
                    result["error"],
                )
        except Exception as exc:
            failure_kind = "internal"
            logger.exception(
                "Gateway call %s: unexpected pipeline failure", result["request_id"]
            )
            result["status_code"] = result["status_code"] or 500
            result["error"] = f"Gateway encountered an internal error: {exc}"
            result["status"] = CallStatusEnum.FAILED.value
        finally:
            result["total_time_ms"] = _elapsed_ms(started)

        return ExecutionOutcome(result, failure_kind, "live", upstream_attempted)

    def _ensure_read_only(self) -> None:
        if self.db.new or self.db.dirty or self.db.deleted:
            raise RuntimeError("Gateway reads require a session without pending writes")

    async def _finish_read(self) -> None:
        self._ensure_read_only()
        if self.db.in_transaction():
            await self.db.rollback()

    async def resolve_endpoint(
        self,
        endpoint_id: int | str | None,
        target_url: str | None = None,
        target_method: str | None = None,
    ) -> EndpointSnapshot | None:
        """Config-only resolution; no mapping load, credentials, or open read tx."""
        self._ensure_read_only()
        try:
            return await self._resolve_endpoint(
                endpoint_id,
                str(target_url or "").strip(),
                str(target_method or "").strip().upper(),
            )
        finally:
            await self._finish_read()

    async def load_mappings(
        self, endpoint: EndpointSnapshot
    ) -> tuple[MappingSnapshot, ...]:
        """One active-mapping query, detached before ending the read tx."""
        self._ensure_read_only()
        try:
            rows = await parameter_service.list_parameters(
                self.db, endpoint.id, active_only=True
            )
            return tuple(
                MappingSnapshot(
                    row.source_parameter,
                    row.target_parameter,
                    row.parameter_type,
                    row.data_type,
                )
                for row in rows
            )
        finally:
            await self._finish_read()

    async def _resolve_endpoint(
        self, endpoint_id: int | str | None, target_url: str, target_method: str
    ) -> EndpointSnapshot | None:
        """Explicit id first; fall back to matching the target URL + method."""
        identifier = _as_int(endpoint_id)
        if identifier is not None:
            result = await self.db.execute(
                select(
                    *(getattr(ApiEndpoint, name) for name in _ENDPOINT_COLUMNS)
                ).where(ApiEndpoint.id == identifier)
            )
            endpoint = _endpoint_snapshot(result.mappings().first())
            if endpoint is not None:
                return endpoint

        if not target_url:
            return None
        return await self._find_endpoint_by_target_url(target_url, target_method)

    async def _find_endpoint_by_target_url(
        self, target_url: str, target_method: str
    ) -> EndpointSnapshot | None:
        """Active endpoint whose ``target_api_url`` ends with ``target_url``."""
        statement = select(
            *(getattr(ApiEndpoint, name) for name in _ENDPOINT_COLUMNS)
        ).where(
            ApiEndpoint.is_active == True,
            ApiEndpoint.target_api_url.like(f"%{target_url}"),
        )
        if target_method:
            statement = statement.where(func.upper(ApiEndpoint.method) == target_method)
        statement = statement.order_by(ApiEndpoint.created_at.desc()).limit(1)

        result = await self.db.execute(statement)
        return _endpoint_snapshot(result.mappings().first())

    async def _not_found_message(self, target_method: str, target_url: str) -> str:
        """Actionable not-found error, listing similar active endpoints."""
        message = f"Endpoint not found: {target_method} {target_url}".strip()
        self._ensure_read_only()
        try:
            similar = await self._similar_endpoints(target_method)
        finally:
            await self._finish_read()
        if similar:
            preview = ", ".join(
                f"{item['endpoint_code'] or item['id']} ({item['target_api_url']})"
                for item in similar
            )
            message += f". Similar active endpoints: {preview}"
        return message

    async def _similar_endpoints(
        self, target_method: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Active endpoints on the same method, for error hints."""
        statement = select(
            ApiEndpoint.id, ApiEndpoint.endpoint_code, ApiEndpoint.target_api_url
        ).where(ApiEndpoint.is_active == True)
        if target_method:
            statement = statement.where(func.upper(ApiEndpoint.method) == target_method)
        statement = statement.order_by(ApiEndpoint.created_at.desc()).limit(limit)

        result = await self.db.execute(statement)
        return [
            {
                "id": str(endpoint.id),
                "endpoint_code": endpoint.endpoint_code,
                "target_api_url": endpoint.target_api_url,
            }
            for endpoint in result.all()
        ]

    @staticmethod
    def _transform_parameters(
        request_data: dict[str, Any],
        mappings: Sequence[MappingSnapshot | ParameterMapping],
        client_headers: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Split mappings into ``(body, header, query)`` upstream parameters."""

        if not mappings:
            return (
                dict(request_data),
                {
                    str(name): value
                    for name, value in client_headers.items()
                    if str(name).lower() != "host"
                },
                {},
            )

        body_params: dict[str, Any] = {}
        header_params: dict[str, Any] = {
            str(name): value
            for name, value in client_headers.items()
            if str(name).lower() != "host"
        }
        query_params: dict[str, Any] = {}
        header_mappings: list[MappingSnapshot | ParameterMapping] = []

        for mapping in mappings:
            param_type = str(mapping.parameter_type or "BODY").strip().upper()
            if param_type == "HEADER":
                header_mappings.append(mapping)
                continue

            value = request_data.get(str(mapping.target_parameter))
            if value is None:
                continue
            source = str(mapping.source_parameter)
            if param_type == "QUERY":
                query_params[source] = value
            else:
                body_params[source] = value

        client_lower = {
            str(name).lower(): value for name, value in client_headers.items()
        }
        for mapping in header_mappings:
            target = str(mapping.target_parameter)
            source = str(mapping.source_parameter)
            if target.lower().startswith(_STATIC_PREFIX):
                header_params[source] = target[len(_STATIC_PREFIX) :]
            elif target.lower() in client_lower:
                header_params[source] = client_lower[target.lower()]
            else:
                fallback = request_data.get(target)
                if fallback is not None:
                    header_params[source] = fallback

        if body_params and not any(
            str(name).lower() == "content-type" for name in header_params
        ):
            header_params["Content-Type"] = _DEFAULT_CONTENT_TYPE

        return body_params, header_params, query_params

    async def _call_upstream(
        self,
        method: str,
        url: str,
        body_params: dict[str, Any],
        header_params: dict[str, Any],
        query_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform the upstream call; every failure mode returns a dict."""
        outcome: dict[str, Any] = {
            "failure_kind": None,
            "upstream_attempted": False,
            "success": False,
            "data": None,
            "status_code": None,
            "response_time_ms": None,
            "response_headers": None,
            "external_request_url": url,
            "external_request_method": method,
            "external_request_headers": dict(header_params),
            "external_request_body": dict(body_params),
            "external_query_params": dict(query_params),
            "external_response_headers": None,
            "external_status_code": None,
            "external_response_time_ms": None,
            "error": None,
        }

        started = time.perf_counter()
        try:
            await apply_upstream_auth(header_params, self.http_client, url)

            request = self.http_client.build_request(
                method=method,
                url=url,
                json=body_params if body_params else None,
                headers=header_params or None,
                params=query_params if query_params else None,
                timeout=self._request_timeout,
            )

            outcome["external_request_headers"] = dict(request.headers)
            outcome["external_request_url"] = str(request.url)
            outcome["external_request_method"] = str(request.method)
            outcome["external_query_params"] = dict(request.url.params)

            outcome["upstream_attempted"] = True
            response = await self.http_client.send(request)
            elapsed = _elapsed_ms(started)
            data = self._parse_response_body(response)
            response_headers = dict(response.headers)

            outcome.update(
                {
                    "success": 200 <= response.status_code < 400,
                    "failure_kind": _http_failure(response.status_code),
                    "data": data,
                    "status_code": response.status_code,
                    "response_time_ms": elapsed,
                    "response_headers": response_headers,
                    "external_response_headers": response_headers,
                    "external_status_code": response.status_code,
                    "external_response_time_ms": elapsed,
                    "error": self._extract_error_message(response.status_code, data),
                }
            )
            return outcome
        except httpx.PoolTimeout:
            elapsed = _elapsed_ms(started)
            outcome.update(
                {
                    "failure_kind": "local_pool_timeout",
                    "upstream_attempted": False,
                    "status_code": 408,
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Request timeout after {self.timeout} seconds",
                }
            )
            return outcome
        except httpx.TimeoutException:
            elapsed = _elapsed_ms(started)
            outcome.update(
                {
                    "status_code": 408,
                    "failure_kind": "upstream_timeout",
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Request timeout after {self.timeout} seconds",
                }
            )
            logger.warning("Upstream timeout after %sms: %s %s", elapsed, method, url)
            return outcome
        except httpx.ConnectError as exc:
            elapsed = _elapsed_ms(started)
            outcome.update(
                {
                    "status_code": 503,
                    "failure_kind": "transport",
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Could not connect to {url}: {str(exc) or 'connection failed'}",
                }
            )
            logger.warning("Upstream connection error: %s %s — %s", method, url, exc)
            return outcome
        except httpx.HTTPStatusError as exc:
            elapsed = _elapsed_ms(started)
            status_code = exc.response.status_code if exc.response is not None else 502
            outcome.update(
                {
                    "success": False,
                    "failure_kind": _http_failure(status_code),
                    "external_status_code": status_code
                    if exc.response is not None
                    else None,
                    "status_code": status_code,
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Upstream HTTP error: {exc}",
                }
            )
            return outcome
        except httpx.RequestError as exc:
            elapsed = _elapsed_ms(started)
            outcome.update(
                {
                    "status_code": 502,
                    "failure_kind": "transport",
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Upstream request failed: {exc}",
                }
            )
            logger.warning("Upstream request error: %s %s — %s", method, url, exc)
            return outcome
        except Exception as exc:
            elapsed = _elapsed_ms(started)
            outcome.update(
                {
                    "status_code": 500,
                    "failure_kind": "internal",
                    "response_time_ms": elapsed,
                    "external_response_time_ms": elapsed,
                    "error": f"Unexpected error calling {url}: {exc}",
                }
            )
            logger.exception("Unexpected upstream error: %s %s", method, url)
            return outcome

    @staticmethod
    def _parse_response_body(response: httpx.Response) -> Any:
        """Parsed JSON when possible, an envelope with the raw text otherwise."""
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"raw_response": response.text}

    @staticmethod
    def _extract_error_message(status_code: int, data: Any) -> str | None:
        """Human-readable message for a non-2xx/3xx upstream response."""
        if 200 <= status_code < 400:
            return None
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, list):
                errors: list[str] = []
                for item in detail:
                    if isinstance(item, dict) and "msg" in item:
                        location = item.get("loc") or []
                        field = " -> ".join(str(part) for part in location)
                        errors.append(
                            f"{field}: {item['msg']}" if field else str(item["msg"])
                        )
                    else:
                        errors.append(str(item))
                if errors:
                    return "; ".join(errors)
            elif detail is not None:
                return str(detail)
            for key in ("message", "error", "error_description"):
                if data.get(key):
                    return str(data[key])
        return f"External API returned HTTP {status_code}"
