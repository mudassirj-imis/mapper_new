"""Declarative base shared by every ORM model (SQLAlchemy 2.0 style)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models in the API Mapper backend."""
