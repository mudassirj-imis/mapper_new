"""``parameter_mappings`` — source -> target parameter transformations.

One row per enabled mapping rule; rows are cascade-deleted when their
endpoint is removed (``ON DELETE CASCADE`` on ``api_endpoint_id``).
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers
    from backend.models.endpoint import ApiEndpoint


class ParameterMapping(Base):
    """One ``source_parameter -> target_parameter`` transformation rule."""

    __tablename__ = "parameter_mappings"
    __table_args__ = (
        # Mapping lookups: active rules per endpoint.
        Index("idx_parameter_mappings_lookup", "api_endpoint_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    api_endpoint_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    source_parameter: Mapped[str] = mapped_column(String(255), nullable=False)
    target_parameter: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'STRING'")
    )
    parameter_type: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'BODY'")
    )
    is_active: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("true")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )

    endpoint: Mapped["ApiEndpoint"] = relationship(back_populates="parameters")
