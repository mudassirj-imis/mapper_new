"""``api_call_logs`` — full audit trail of proxied calls.

``endpoint_id`` becomes NULL (instead of deleting history) when an endpoint
is removed (``ON DELETE SET NULL``). Every header/body column is JSONB and
defaults to an empty object at the database level.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

# Shared server default for JSONB columns: an empty JSON object.
_EMPTY_JSON = text("'{}'")


class ApiCallLog(Base):
    """One proxied request/response pair recorded for auditing."""

    __tablename__ = "api_call_logs"
    __table_args__ = (
        # Log listing: newest entries per endpoint.
        Index("idx_api_call_logs_recent", "endpoint_id", desc("created_at")),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    endpoint_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_status: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )

    # --- Internal side (client -> gateway) ------------------------------------
    internal_request_headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    internal_request_body: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    internal_api_client_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    internal_api_client_status: Mapped[str | None] = mapped_column(String(20))

    # --- External side (gateway -> upstream) ------------------------------------
    external_request_url: Mapped[str | None] = mapped_column(Text)
    external_request_method: Mapped[str | None] = mapped_column(String(10))
    external_request_headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    external_request_body: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    external_query_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    external_response: Mapped[Any] = mapped_column(JSONB, nullable=True)
    external_response_headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, server_default=_EMPTY_JSON
    )
    external_response_time_ms: Mapped[int | None] = mapped_column(
        Integer, server_default=text("0")
    )
    external_status_code: Mapped[int | None] = mapped_column(Integer)

    # --- Timing / diagnostics ------------------------------------------------------
    total_time_ms: Mapped[int | None] = mapped_column(
        Integer, server_default=text("0")
    )
    full_log: Mapped[str | None] = mapped_column(Text)
    timeout_configured: Mapped[int | None] = mapped_column(
        Integer, server_default=text("60")
    )
    tenant_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
