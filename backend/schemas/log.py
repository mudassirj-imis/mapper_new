"""Call log schemas — full audit view plus a trimmed list summary."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.common import PaginatedResponse


def _coerce_status(value: Any) -> str | None:
    """Render ``internal_api_client_status`` as text, whatever it holds.

    The column is free-text for historical rows and an integer status code for
    new ones; the field stays a string so existing consumers are unaffected.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


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

    request_id: str | None = None
    method: str | None = None
    #: Client-facing path this call was made against. Declared here because
    #: ``log_service.get_log`` passes it and the detail view renders it; an
    #: undeclared field would be dropped by ``response_model`` serialisation.
    path: str | None = None

    overall_status: bool | None = None
    tenant_id: str | None = None

    external_status_code: int | None = None
    total_time_ms: int | None = None

    internal_request_headers: dict[str, Any] | None = None
    internal_request_body: dict[str, Any] | None = None
    internal_api_client_response: dict[str, Any] | None = None
    #: Historically free-text; now also carries the HTTP status returned to
    #: the client, so both forms are accepted and the value is stringified so
    #: existing consumers keep working.
    internal_api_client_status: str | None = None

    external_request_url: str | None = None
    external_request_method: str | None = None
    external_request_headers: dict[str, Any] | None = None
    external_request_body: dict[str, Any] | None = None
    external_query_params: dict[str, Any] | None = None
    external_response: Any | None = None
    external_response_time_ms: int | None = None

    full_log: str | None = None
    timeout_configured: int | None = None

    _status_to_text = field_validator("internal_api_client_status", mode="before")(
        _coerce_status
    )


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

    external_status_code: int | None = None
    total_time_ms: int | None = None
    created_at: datetime | None = None

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
    external_response_time_ms: int | None = None

    _status_to_text = field_validator("internal_api_client_status", mode="before")(
        _coerce_status
    )


class CallLogListResponse(PaginatedResponse):
    """Paginated envelope of CallLogSummary rows."""

    items: list[CallLogSummary] = Field(default_factory=list)
