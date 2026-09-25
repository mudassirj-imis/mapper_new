"""Model for the ``api_call_log`` table.

Stores the audit trail for requests proxied through the API gateway.
This model matches the existing MySQL ``api_call_log`` table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ApiCallLog(Base):
    """One proxied request/response pair recorded for auditing."""

    __tablename__ = "api_call_log"

    __table_args__ = (
        Index(
            "idx_api_call_logs_recent",
            "endpoint_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    endpoint_id: Mapped[int | None] = mapped_column(
        "endpoint_id",
        Integer,
        ForeignKey(
            "api_endpoint.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    source_request_payload: Mapped[dict[str, Any] | None] = mapped_column(
        "source_request_payload",
        JSON,
        nullable=True,
    )

    source_response: Mapped[dict[str, Any] | None] = mapped_column(
        "source_response",
        JSON,
        nullable=True,
    )

    target_request_payload: Mapped[dict[str, Any] | None] = mapped_column(
        "target_request_payload",
        JSON,
        nullable=True,
    )

    target_response: Mapped[dict[str, Any] | None] = mapped_column(
        "target_response",
        JSON,
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        "status",
        String(20),
        nullable=True,
    )

    response_time_ms: Mapped[int | None] = mapped_column(
        "response_time_ms",
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        "error_message",
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime | None] = mapped_column(
        "created_at",
        DateTime,
        server_default=func.now(),
        nullable=True,
    )
