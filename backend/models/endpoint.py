"""``api_endpoints`` — one row per mapped endpoint (HTTP proxy, SFTP, mock).

The schema mirrors ``supabase/migrations/001_initial_schema.sql``. Credential
columns (``sftp_password``, ``api_password``) store AES-256-GCM ciphertext
produced by :mod:`backend.core.crypto` — never plaintext.

Enum-like columns are plain ``String`` on purpose (portability), and every
timestamp uses ``server_default=func.now()`` so the database clock is the
single source of truth.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers
    from backend.models.parameter import ParameterMapping


class ApiEndpoint(Base):
    """A source -> target mapping managed by the mapper API."""

    __tablename__ = "api_endpoints"
    __table_args__ = (
        # Route lookups: resolve an active endpoint by target URL + method.
        Index("idx_api_endpoints_routing", "target_api_url", "method", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    endpoint_code: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    source_api_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_api_url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(
        String(10), server_default=text("'POST'")
    )
    is_active: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("true")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )
    protocol: Mapped[str | None] = mapped_column(
        String(10), server_default=text("'HTTP'")
    )

    # --- SFTP delivery mode -------------------------------------------------
    sftp_host: Mapped[str | None] = mapped_column(Text)
    sftp_port: Mapped[int | None] = mapped_column(Integer, server_default=text("22"))
    sftp_username: Mapped[str | None] = mapped_column(Text)
    sftp_password: Mapped[str | None] = mapped_column(Text)  # AES-GCM ciphertext
    sftp_private_key_path: Mapped[str | None] = mapped_column(Text)
    sftp_remote_path: Mapped[str | None] = mapped_column(Text)
    dynamic_filename_pattern: Mapped[str | None] = mapped_column(String(255))

    # --- Upstream authentication ---------------------------------------------
    api_id: Mapped[str | None] = mapped_column(Text)
    api_password: Mapped[str | None] = mapped_column(Text)  # AES-GCM ciphertext
    api_auth_url: Mapped[str | None] = mapped_column(Text)

    # --- Behavior flags ---------------------------------------------------------
    request_content_type: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'JSON'")
    )
    require_authentication: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )
    require_correlation_id: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("true")
    )
    description: Mapped[str | None] = mapped_column(Text)
    mock_response: Mapped[Any] = mapped_column(JSONB, nullable=True)
    mock_enabled: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )
    tenant_id: Mapped[str | None] = mapped_column(String(255))
    rate_limit_rpm: Mapped[int | None] = mapped_column(
        Integer, server_default=text("60")
    )
    is_hidden: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )
    created_by: Mapped[int | None] = mapped_column(Integer)
    updated_by: Mapped[int | None] = mapped_column(Integer)

    # --- Relationships ------------------------------------------------------------
    parameters: Mapped[list["ParameterMapping"]] = relationship(
        back_populates="endpoint",
        cascade="all, delete-orphan",
        passive_deletes=True,  # api_endpoints.id ON DELETE CASCADE covers the rest
    )
