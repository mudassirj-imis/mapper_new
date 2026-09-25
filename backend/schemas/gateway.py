"""Gateway (proxy) execution schemas for the map-and-call test endpoint."""

from typing import Any

from pydantic import BaseModel


class MapAndCallRequest(BaseModel):
    """Test-run request: apply an endpoint's mappings and call the upstream.

    ``endpointId`` is the ``api_endpoint.id`` integer (as sent by the frontend),
    accepted as an ``int`` or a numeric string.
    """

    targetUrl: str
    targetMethod: str
    requestData: dict[str, Any]
    headers: dict[str, Any] | None = None
    endpointId: int | str


class MapAndCallResponse(BaseModel):
    """Result of a map-and-call execution, including header audit trails.

    The ``external_*`` / ``total_time_ms`` fields carry the wire-level audit
    trail the response inspector renders; all are optional so an attempt that
    never reached the upstream (endpoint missing, DNS failure, …) can answer
    with whatever was captured.
    """

    success: bool
    data: Any | None = None
    status_code: int | None = None
    response_time_ms: int | None = None
    request_headers: dict[str, Any] | None = None
    response_headers: dict[str, Any] | None = None
    external_request_headers: dict[str, Any] | None = None
    external_response_headers: dict[str, Any] | None = None
    error: str | None = None

    # --- Extended audit trail -------------------------------------------------
    request_id: str | None = None
    external_request_url: str | None = None
    external_request_method: str | None = None
    external_request_body: dict[str, Any] | None = None
    external_query_params: dict[str, Any] | None = None
    external_status_code: int | None = None
    external_response_time_ms: int | None = None
    total_time_ms: int | None = None
