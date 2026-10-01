"""What the ``api_call_log`` table actually looks like on this server.

The audit model maps more columns than every deployment has. Some hosts -- like
the production box this was reported from -- run a MySQL account that cannot
``ALTER TABLE``, so the header columns added by
:mod:`backend.migrations.add_call_log_headers` were never created there. The
ORM does not know that: it emits every mapped column, and MySQL answers 1054
(``Unknown column 'api_call_log.source_request_headers' in 'field list'``) for
*every* log read, taking the whole log view down over a schema mismatch.

The detail itself is not lost. The legacy ``mapper-engine`` gateway writes a
full-detail document to MongoDB for each call, which
:mod:`backend.services.audit_enrichment` already merges over the empty columns.
So the fix is to stop asking MySQL for columns it does not have and let MongoDB
supply them, rather than to demand a migration this process cannot perform.

This module introspects the table once per process and caches the answer:

* :meth:`SchemaProbe.load_options` narrows a ``SELECT`` to the columns that
  exist, via SQLAlchemy's ``load_only``. The absent attributes then need
  :meth:`SchemaProbe.apply_defaults`, because touching an unloaded column would
  lazy-load it and re-issue the very query MySQL just rejected.
* :meth:`SchemaProbe.writable` drops absent columns from an ``INSERT``.

Introspection is best-effort and never fatal. If the table cannot be inspected
the model is assumed complete, which reproduces today's behaviour, so a
permissions problem degrades to the status quo rather than to silent data loss.
"""

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
    """Which of a table's mapped columns the connected server really has.

    The result is cached for the life of the process. A column cannot appear or
    vanish under a running service without an ``ALTER``, and re-inspecting on
    every log page would add a round trip to the hot path to learn nothing new.
    :meth:`invalidate` exists for tests and for a deliberate re-check.
    """

    def __init__(self) -> None:
        #: ``None`` means "not inspected yet", which is read as "assume complete"
        #: so the very first query behaves exactly as it did before this module
        #: existed.
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
            # An unreadable schema is not a reason to fail the request: keep the
            # model's full column list and let the database decide.
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
        """``SELECT``-narrowing options for the columns that exist.

        Returns an empty tuple when the table is complete, so the common
        deployment compiles exactly the statement it always did.
        """
        if self.complete:
            return ()

        kept = tuple(
            getattr(ApiCallLog, column.key)
            for column in ApiCallLog.__table__.columns
            if column.key not in self.missing
        )
        return (load_only(*kept),)

    def apply_defaults(self, *instances: Any) -> None:
        """Give every loaded row a value for each absent column.

        Without this, reading an attribute the query did not load raises:
        SQLAlchemy would try to lazy-load it, emitting a second ``SELECT`` that
        names the column MySQL just rejected.
        :func:`set_committed_value` writes it straight into the instance
        without marking the row dirty, so a read-only request can never try to
        ``UPDATE`` a column that is not there.

        A value already present is left alone. The check reads the instance
        ``__dict__`` rather than the attribute, because touching an unloaded
        column is exactly the lazy load this exists to prevent.
        """
        if self.complete:
            return

        for instance in instances:
            # Only mapped rows need it; a caller may hand over a plain stand-in.
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
            name: value
            for name, value in values.items()
            if name not in self.missing
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


#: Process-wide probe. One database, one schema, one answer.
probe = SchemaProbe()


async def warm() -> None:
    """Inspect the schema at startup so the first request pays nothing.

    Failures are swallowed: an unreachable database here would otherwise stop
    the process from booting, and the first request would have surfaced it
    anyway.
    """
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
