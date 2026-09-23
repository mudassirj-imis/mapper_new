"""``users`` / ``roles`` / ``user_roles`` — authentication and authorization.

Integer surrogate keys (SERIAL on PostgreSQL) match the seeded data from
``supabase/migrations/001_initial_schema.sql`` (default admin user plus the
admin/user/viewer roles).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


class User(Base):
    """A login account. Passwords are stored as argon2id hashes."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_active: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("true")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    # Convenience many-to-many view: ``user.roles`` yields Role rows joined
    # through ``user_roles``. Read-only — mutate via ``user_roles`` instead.
    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", viewonly=True)


class Role(Base):
    """A named permission bucket (seeded: admin, user, viewer)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", passive_deletes=True
    )


class UserRole(Base):
    """Association row linking a user to a role."""

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")
