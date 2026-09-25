"""Call log schemas — full audit view plus a trimmed list summary."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import PaginatedResponse


class CallLogResponse(BaseModel):
    """Complete stored call log.

    The response deliberately carries two views of the same record:

    * the raw stored columns (``source_*`` / ``target_*``) for API consumers
      that read the table directly, and
    * the frontend audit contract (``internal_*`` / ``external_*``, ``method``,
      ``path``, ``overall_status`` …) which mirrors :class:`CallLogSummary`.

    ``log_service.get_log`` populates the second set from the first with the
    endpoint join. Every one of those fields must stay declared here: FastAPI
    serialises through ``response_model``, so an undeclared field is silently
    dropped from the payload and the detail view renders empty.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint_id: int | None = None

    source_request_payload: dict[str, Any] | None = None
    source_response: dict[str, Any] | None = None
    target_request_payload: dict[str, Any] | None = None
    target_response: dict[str, Any] | None = None

    status: str | None = None
    response_time_ms: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    # --- Frontend audit contract -------------------------------------------
    request_id: str | None = None
    method: str | None = None
    #: Endpoint path the caller targeted (``api_endpoint.source_api_url``).
    path: str | None = None

    overall_status: bool | None = None
    tenant_id: str | None = None

    # Timing
    external_status_code: int | None = None
    total_time_ms: int | None = None

    # Internal audit data (caller -> gateway)
    internal_request_headers: dict[str, Any] | None = None
    internal_request_body: dict[str, Any] | None = None
    internal_api_client_response: dict[str, Any] | None = None
    internal_api_client_status: str | None = None

    # External audit data (gateway -> upstream)
    external_request_url: str | None = None
    external_request_method: str | None = None
    external_request_headers: dict[str, Any] | None = None
    external_request_body: dict[str, Any] | None = None
    external_query_params: dict[str, Any] | None = None
    external_response: Any | None = None
    external_response_headers: dict[str, Any] | None = None
    external_response_time_ms: int | None = None

    # Failure diagnostics
    full_log: str | None = None
    timeout_configured: int | None = None


class CallLogSummary(BaseModel):
    """Trimmed log row for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint_id: int | None = None

    request_id: str
    method: str | None = None
    path: str | None = None

    status: str | None = None
    overall_status: bool | None = None

    # Timing
    external_status_code: int | None = None
    total_time_ms: int | None = None
    created_at: datetime | None = None

    # Audit data
    internal_request_headers: dict[str, Any] | None = None
    internal_request_body: dict[str, Any] | None = None
    internal_api_client_response: dict[str, Any] | None = None
    internal_api_client_status: str | None = None

    external_request_url: str | None = None
    external_request_method: str | None = None
    external_request_headers: dict[str, Any] | None = None
    external_request_body: dict[str, Any] | None = None
    external_query_params: dict[str, Any] | None = None
    external_response: Any | None = None
    external_response_headers: dict[str, Any] | None = None
    external_response_time_ms: int | None = None

class CallLogListResponse(PaginatedResponse):
    """Paginated envelope of CallLogSummary rows."""

    items: list[CallLogSummary] = Field(default_factory=list)