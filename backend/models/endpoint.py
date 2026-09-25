from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.types import YesNoBoolean

if TYPE_CHECKING:
    from backend.models.parameter import ParameterMapping


def _now() -> datetime:
    """Naive local timestamp for the ``DATETIME`` audit columns.

    ``api_endpoint.created_at`` and ``updated_at`` are ``NOT NULL`` with no
    database default, so the ORM must always supply a value — a missing one
    makes every insert fail with MySQL 1048
    (``Column 'created_at' cannot be null``).

    The app and the MySQL server share a clock and timezone (both report
    UTC+5), so this stays consistent with ``server_default=func.now()`` on
    ``api_call_log`` and with the ``datetime.now()`` stamps the routers embed
    in endpoint descriptions.
    """
    return datetime.now()


class ApiEndpoint(Base):
    """A source -> target mapping managed by the mapper API."""

    __tablename__ = "api_endpoint"

    __table_args__ = (
        Index(
            "idx_api_endpoints_routing",
            "target_api_url",
            "method",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    endpoint_code: Mapped[str | None] = mapped_column(
        "endpoint_code",
        String(255),
        unique=True,
        nullable=True,
    )

    source_api_url: Mapped[str] = mapped_column(
        "source_api_url",
        Text,
        nullable=False,
    )

    target_api_url: Mapped[str] = mapped_column(
        "target_api_url",
        Text,
        nullable=False,
    )

    method: Mapped[str | None] = mapped_column(
        "method",
        String(10),
        nullable=True,
    )

    request_content_type: Mapped[str | None] = mapped_column(
        "request_content_type",
        String(20),
        nullable=True,
    )

    require_authentication: Mapped[bool | None] = mapped_column(
        "require_authentication",
        YesNoBoolean(),
        nullable=True,
    )

    require_correlation_id: Mapped[bool | None] = mapped_column(
        "require_correlation_id",
        YesNoBoolean(),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        "description",
        Text,
        nullable=True,
    )

    is_active: Mapped[bool | None] = mapped_column(
        "is_active",
        YesNoBoolean(),
        nullable=True,
    )

    is_hidden: Mapped[bool | None] = mapped_column(
        "is_hidden",
        YesNoBoolean(),
        nullable=True,
    )

    created_by: Mapped[int | None] = mapped_column(
        "created_by",
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        "created_at",
        DateTime,
        default=_now,
        nullable=False,
    )

    updated_by: Mapped[int | None] = mapped_column(
        "updated_by",
        Integer,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime,
        default=_now,
        nullable=False,
    )

    api_id: Mapped[str | None] = mapped_column(
        "api_id",
        Text,
        nullable=True,
    )

    api_password: Mapped[str | None] = mapped_column(
        "api_password",
        Text,
        nullable=True,
    )

    api_auth_url: Mapped[str | None] = mapped_column(
        "api_auth_url",
        Text,
        nullable=True,
    )

    protocol: Mapped[str | None] = mapped_column(
        "protocol",
        String(10),
        nullable=True,
    )

    sftp_host: Mapped[str | None] = mapped_column(
        "sftp_host",
        Text,
        nullable=True,
    )

    sftp_port: Mapped[int | None] = mapped_column(
        "sftp_port",
        Integer,
        nullable=True,
    )

    sftp_username: Mapped[str | None] = mapped_column(
        "sftp_username",
        Text,
        nullable=True,
    )

    sftp_password: Mapped[str | None] = mapped_column(
        "sftp_password",
        Text,
        nullable=True,
    )

    sftp_private_key_path: Mapped[str | None] = mapped_column(
        "sftp_private_key_path",
        Text,
        nullable=True,
    )

    sftp_remote_path: Mapped[str | None] = mapped_column(
        "sftp_remote_path",
        Text,
        nullable=True,
    )

    dynamic_filename_pattern: Mapped[str | None] = mapped_column(
        "dynamic_filename_pattern",
        String(255),
        nullable=True,
    )

    parameters: Mapped[list["ParameterMapping"]] = relationship(
        back_populates="endpoint",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
