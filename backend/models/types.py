"""Database value types shared by mapper models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, TypeDecorator
from sqlalchemy.engine import Dialect

__all__ = ["YesNoBoolean"]


class YesNoBoolean(TypeDecorator[bool]):
    """Map boolean API values to legacy MySQL ``ENUM('Y', 'N')`` values."""

    impl = String(1)
    cache_ok = True

    def process_bind_param(
        self,
        value: bool | str | int | None,
        dialect: Dialect,
    ) -> str | None:
        """Convert booleans and compatible strings to values accepted by MySQL."""
        if value is None:
            return None

        normalized = str(value).strip().lower()
        if value is True or normalized in {"1", "y", "yes", "true"}:
            return "Y"
        if value is False or normalized in {"0", "n", "no", "false"}:
            return "N"

        raise ValueError(f"Unsupported Y/N value: {value!r}")

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect,
    ) -> bool | None:
        """Convert stored ``Y``/``N`` values back to booleans."""
        if value is None:
            return None

        normalized = str(value).strip().upper()
        if normalized == "Y":
            return True
        if normalized == "N":
            return False

        raise ValueError(f"Unsupported Y/N value: {value!r}")
