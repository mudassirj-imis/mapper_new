from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.types import YesNoBoolean


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(
        "user_id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_name: Mapped[str] = mapped_column(
        "user_name",
        String(255),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        "email",
        String(255),
        nullable=True,
    )

    password_hash: Mapped[str] = mapped_column(
        "password_hash",
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        "is_active",
        YesNoBoolean(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        "created_on",
        DateTime,
        nullable=False,
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_role",
        viewonly=True,
    )


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(
        "role_id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    role_name: Mapped[str] = mapped_column(
        "role_name",
        String(50),
        nullable=False,
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserRole(Base):
    __tablename__ = "user_role"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role_id",
            name="uq_user_roles_user_id_role_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        "user_role_id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        "user_id",
        ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    role_id: Mapped[int] = mapped_column(
        "role_id",
        ForeignKey("role.role_id", ondelete="CASCADE"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="user_roles",
    )

    role: Mapped["Role"] = relationship(
        back_populates="user_roles",
    )