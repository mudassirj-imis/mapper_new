from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_scheduler_path = Path(settings.SCHEDULER_DATABASE_PATH).expanduser()
if not _scheduler_path.is_absolute():
    _scheduler_path = PROJECT_ROOT / _scheduler_path

SCHEDULER_DATABASE_PATH = str(_scheduler_path)
SCHEDULER_ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{SCHEDULER_DATABASE_PATH}"
SCHEDULER_SYNC_DATABASE_URL = f"sqlite:///{SCHEDULER_DATABASE_PATH}"

scheduler_engine = create_async_engine(
    SCHEDULER_ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SchedulerSessionLocal = async_sessionmaker(
    bind=scheduler_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_scheduler_db() -> AsyncGenerator[AsyncSession, None]:
    async with SchedulerSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("scheduled_jobs", "headers", "TEXT"),
    ("scheduled_jobs", "body", "TEXT"),
    ("scheduled_job_runs", "request_headers", "TEXT"),
    ("scheduled_job_runs", "response_headers", "TEXT"),
    ("scheduled_job_runs", "response_body", "TEXT"),
    (
        "scheduled_job_runs",
        "response_body_truncated",
        "BOOLEAN NOT NULL DEFAULT 0",
    ),
    ("scheduled_job_runs", "response_size", "INTEGER"),
)


def _add_missing_scheduler_columns(connection) -> None:
    """Add post-release scheduler columns to a pre-existing database."""
    inspector = sa_inspect(connection)
    for table, column, ddl_type in _ADDED_COLUMNS:
        if not inspector.has_table(table):
            continue
        if column in {item["name"] for item in inspector.get_columns(table)}:
            continue
        connection.exec_driver_sql(
            f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"
        )


async def create_scheduler_tables() -> None:
    from backend.models.scheduled_job import (
        ScheduledJob,
        ScheduledJobRun,
        SchedulerBase,
    )

    _scheduler_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with scheduler_engine.begin() as connection:
            await connection.run_sync(
                SchedulerBase.metadata.create_all,
                tables=[ScheduledJob.__table__, ScheduledJobRun.__table__],
            )
            await connection.run_sync(_add_missing_scheduler_columns)
    except Exception:
        await scheduler_engine.dispose()
        raise


async def dispose_scheduler_engine() -> None:
    await scheduler_engine.dispose()
