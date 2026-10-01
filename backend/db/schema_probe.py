from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import set_committed_value

from backend.models.log import ApiCallLog

logger = logging.getLogger(__name__)


class SchemaProbe:
    """Which of a table's mapped columns the connected server really has."""

    def __init__(self) -> None:

        self._present: frozenset[str] | None = None

    def invalidate(self) -> None:
        """Force the next read to re-inspect the table."""
        self._present = None

    @property
    def present(self) -> frozenset[str] | None:
        """Column names found in the table, or ``None`` if never inspected."""
        return self._present

    @property
    def missing(self) -> frozenset[str]:
        """Mapped columns the table does not have; empty when it has them all."""
        if self._present is None:
            return frozenset()
        return _mapped_columns() - self._present

    @property
    def complete(self) -> bool:
        """True when every mapped column exists, so no query needs narrowing."""
        return not self.missing

    async def refresh(self, db: AsyncSession) -> frozenset[str]:
        """Introspect ``api_call_log`` and cache which columns it has."""
        try:
            connection = await db.connection()
            present = await connection.run_sync(_column_names)
        except Exception:
            logger.warning(
                "Could not inspect api_call_log; assuming the full column set",
                exc_info=True,
            )
            self._present = None
            return _mapped_columns()

        self._present = present

        absent = self.missing
        if absent:
            logger.warning(
                "api_call_log is missing %d column(s) this build expects (%s). "
                "Reads and writes will omit them and take the detail from "
                "MongoDB; run 'python -m backend.migrations."
                "add_call_log_headers' on a host that can ALTER TABLE to store "
                "it in MySQL as well.",
                len(absent),
                ", ".join(sorted(absent)),
            )
        else:
            logger.info("api_call_log carries every mapped audit column")

        return present

    async def ensure(self, db: AsyncSession) -> None:
        """Inspect once, then do nothing for the rest of the process's life."""
        if self._present is None:
            await self.refresh(db)

    def load_options(self) -> tuple[Any, ...]:

        if self.complete:
            return ()

        kept = tuple(
            getattr(ApiCallLog, column.key)
            for column in ApiCallLog.__table__.columns
            if column.key not in self.missing
        )
        return (load_only(*kept),)

    def apply_defaults(self, *instances: Any) -> None:

        if self.complete:
            return

        for instance in instances:
            if not isinstance(instance, ApiCallLog):
                continue
            for name in self.missing:
                if instance.__dict__.get(name) is not None:
                    continue
                set_committed_value(instance, name, None)

    def writable(self, values: dict[str, Any]) -> dict[str, Any]:
        """Drop absent columns from an ``INSERT``'s keyword arguments."""
        if self.complete:
            return values
        return {
            name: value for name, value in values.items() if name not in self.missing
        }


def _column_names(sync_connection: Any) -> frozenset[str]:
    """Physical column names of ``api_call_log``, for ``run_sync``."""
    return frozenset(
        column["name"]
        for column in inspect(sync_connection).get_columns("api_call_log")
    )


def _mapped_columns() -> frozenset[str]:
    """Every column the model maps, whether or not the table has it."""
    return frozenset(column.key for column in ApiCallLog.__table__.columns)


probe = SchemaProbe()


async def warm() -> None:

    from backend.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            await probe.ensure(session)
    except Exception:
        logger.warning("Startup schema check skipped", exc_info=True)


def _column_names(sync_connection: Any) -> frozenset[str]:
    """Physical column names of ``api_call_log``, for ``run_sync``."""
    return frozenset(
        column["name"]
        for column in inspect(sync_connection).get_columns("api_call_log")
    )


def _mapped_columns() -> frozenset[str]:
    return frozenset(column.key for column in ApiCallLog.__table__.columns)
