"""Idempotent additive migration for ``api_call_log``.

The main application database is MySQL and is not created by this process --
there is no ``create_all`` for it, so new columns have to be added explicitly.
This script only ever *adds* nullable columns, so it is safe to re-run and does
not rewrite or drop existing audit rows.

Usage::

    python -m backend.migrations.add_call_log_headers

It is a no-op once the columns exist, so it can be wired into a deploy step
without special-casing.

Usage::

    python -m backend.migrations.add_call_log_headers            # add what is missing
    python -m backend.migrations.add_call_log_headers --check    # report only

On a host whose MySQL account cannot ``ALTER TABLE`` this cannot run, and that
is fine: the service adapts to the schema it finds rather than requiring it
(see :mod:`backend.db.schema_probe`). The detail is served from MongoDB there,
so running this later is an improvement -- MySQL becomes the authority again --
not a prerequisite for the log views working at all.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import inspect, text

from backend.db.session import engine

__all__ = ["ADDED_COLUMNS", "ensure_columns", "main"]

#: ``(column, DDL type)`` pairs added to ``api_call_log``.
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source_request_headers", "JSON"),
    ("source_response_headers", "JSON"),
    ("target_request_headers", "JSON"),
    ("target_response_headers", "JSON"),
    ("target_query_params", "JSON"),
    ("client_status_code", "INT"),
    ("upstream_status_code", "INT"),
)

_TABLE = "api_call_log"


async def _missing_columns() -> list[tuple[str, str]]:
    """The pairs above that the connected table does not have yet."""
    async with engine.connect() as connection:

        def _run(sync_connection) -> list[tuple[str, str]]:
            inspector = inspect(sync_connection)
            if not inspector.has_table(_TABLE):
                return []
            existing = {column["name"] for column in inspector.get_columns(_TABLE)}
            return [pair for pair in ADDED_COLUMNS if pair[0] not in existing]

        return await connection.run_sync(_run)


async def ensure_columns() -> list[str]:
    """Add any missing columns; returns the names actually added."""

    async with engine.begin() as connection:

        def _run(sync_connection) -> list[str]:
            inspector = inspect(sync_connection)
            if not inspector.has_table(_TABLE):
                return []
            existing = {column["name"] for column in inspector.get_columns(_TABLE)}
            added: list[str] = []
            for column, ddl_type in ADDED_COLUMNS:
                if column in existing:
                    continue
                # Identifier and type come from the constant above, never from
                # user input.
                sync_connection.execute(
                    text(f"ALTER TABLE {_TABLE} ADD COLUMN {column} {ddl_type}")
                )
                added.append(column)
            return added

        return await connection.run_sync(_run)


async def main() -> int:
    if "--check" in sys.argv[1:]:
        missing = await _missing_columns()
        if missing:
            print(
                f"{_TABLE}: missing {', '.join(column for column, _ in missing)}"
            )
        else:
            print(f"{_TABLE}: up to date")
    else:
        added = await ensure_columns()
        if added:
            print(f"{_TABLE}: added {', '.join(added)}")
        else:
            print(f"{_TABLE}: already up to date")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
