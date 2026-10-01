"""Idempotent additive migration for ``api_call_log``.

The main application database is MySQL and is not created by this process --
there is no ``create_all`` for it, so new columns have to be added explicitly.
This script only ever *adds* nullable columns, so it is safe to re-run and does
not rewrite or drop existing audit rows.

Usage::

    python -m backend.migrations.add_call_log_headers

It is a no-op once the columns exist, so it can be wired into a deploy step
without special-casing.
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
    added = await ensure_columns()
    if added:
        print(f"api_call_log: added {', '.join(added)}")
    else:
        print("api_call_log: already up to date")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
