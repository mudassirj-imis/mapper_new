"""Call log schemas — full audit view plus a trimmed list summary."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import PaginatedResponse


class CallLogResponse(BaseModel):
    """Complete stored call log, including every JSON audit column."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID | None = None
    request_id: UUID
    method: str
    path: str
    status: str
    overall_status: bool | None = None

    # --- Internal side (client -> gateway) ------------------------------------
    internal_request_headers: dict[str, Any] | None = None
    internal_request_body: dict[str, Any] | None = None
    internal_api_client_response: dict[str, Any] | None = None
    internal_api_client_status: str | None = None

    # --- External side (gateway -> upstream) ------------------------------------
    external_request_url: str | None = None
    external_request_method: str | None = None
    external_request_headers: dict[str, Any] | None = None
    external_request_body: dict[str, Any] | None = None
    external_query_params: dict[str, Any] | None = None
    external_response: Any | None = None
    external_response_headers: dict[str, Any] | None = None
    external_response_time_ms: int | None = None
    external_status_code: int | None = None

    # --- Timing / diagnostics ------------------------------------------------------
    total_time_ms: int | None = None
    full_log: str | None = None
    timeout_configured: int | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None


class CallLogSummary(BaseModel):
    """Trimmed log row for list views (no JSON payload columns)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID | None = None
    request_id: UUID
    method: str
    path: str
    status: str
    overall_status: bool | None = None
    external_status_code: int | None = None
    total_time_ms: int | None = None
    created_at: datetime | None = None


class CallLogListResponse(PaginatedResponse):
    """Paginated envelope of :class:`CallLogSummary` rows."""

    items: list[CallLogSummary] = Field(default_factory=list)
