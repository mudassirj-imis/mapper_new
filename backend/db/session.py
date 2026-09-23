"""Async SQLAlchemy engine and session factory.

The engine is created once per process; request handlers obtain sessions via
the :func:`get_db` FastAPI dependency. Everything here is strictly async —
no synchronous engine/session is used anywhere in this codebase.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
    connect_args={
        # Supabase's pooler (PgBouncer, transaction mode, port 6543) reuses
        # server connections across client connections. SQLAlchemy's asyncpg
        # dialect otherwise asks asyncpg for *named* statements
        # (``__asyncpg_stmt_N__``), which collide on reuse and raise
        # asyncpg.exceptions.DuplicatePreparedStatementError. Disable both
        # caches AND request unnamed statements so nothing is named server-side.
        "statement_cache_size": 0,              # asyncpg's own statement cache
        "prepared_statement_cache_size": 0,     # SQLAlchemy's prepared stmt cache
        "prepared_statement_name_func": lambda: "",  # "" -> unnamed statement
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session.

    Transactions are controlled explicitly by services/repositories; on an
    unhandled exception the session is rolled back before being closed.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
