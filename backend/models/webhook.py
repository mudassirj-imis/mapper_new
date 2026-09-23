"""Webhook subscription persistence; delivery is owned by a separate service."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class WebhookEvent(str, Enum):
    CALL_SUCCESS = "call_success"
    CALL_FAILURE = "call_failure"
    CALL_TIMEOUT = "call_timeout"
    ENDPOINT_CREATED = "endpoint_created"


class Webhook(Base):
    """Null endpoint is global; deletion removes endpoint-scoped subscriptions."""

    __tablename__ = "webhooks"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(events) = 'array' AND "
            "jsonb_array_length(events) BETWEEN 1 AND 4 AND "
            "events <@ '[\"call_success\",\"call_failure\",\"call_timeout\","
            "\"endpoint_created\"]'::jsonb",
            name="ck_webhooks_events",
        ),
        Index("idx_webhooks_endpoint", "endpoint_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    endpoint_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
