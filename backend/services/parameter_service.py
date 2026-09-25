"""Async CRUD service for ``parameter_mappings`` rows.

Parameters belong to an endpoint (``api_endpoint_id`` FK, cascade delete).
Every function takes an :class:`~sqlalchemy.ext.asyncio.AsyncSession` and
commits its own writes so routers can serialize the returned ORM objects
directly. Explicit ``*_flush`` helpers leave commit/rollback to their caller.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ParameterMapping
from backend.schemas.parameter import ParameterCreate

__all__ = [
    "bulk_create_parameters",
    "bulk_create_parameters_flush",
    "create_parameter",
    "create_parameter_flush",
    "delete_all_parameters",
    "delete_parameter",
    "list_parameters",
    "update_parameter",
]


def _as_int(value: object) -> int | None:
    """Best-effort conversion of ``value`` to an integer id.

    Both ``api_endpoint.id`` and ``api_endpoint_parameter_mapping.id`` are
    ``INT`` auto-increment columns. The previous UUID coercion silently turned
    every id into a miss: ``_fetch_by_id`` reported "not found" and the
    endpoint/parameter list routes answered with an empty list.
    """
    if isinstance(value, int):
        return value
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _enum_value(value: object) -> object:
    """Return the plain value for enum members (any other value unchanged)."""
    return getattr(value, "value", value)


def _parameter_values(data: ParameterCreate) -> dict:
    """Map a :class:`ParameterCreate` payload onto ORM column values."""
    return {
        "source_parameter": data.source_parameter,
        "target_parameter": data.target_parameter,
        "data_type": _enum_value(data.data_type),
        "parameter_type": _enum_value(data.parameter_type),
        "is_active": data.is_active,
    }


async def _fetch_by_id(
    db: AsyncSession, parameter_id: int | str
) -> ParameterMapping | None:
    """Plain single-row fetch; ``None`` for unknown (or invalid) ids."""
    identifier = _as_int(parameter_id)
    if identifier is None:
        return None
    result = await db.execute(
        select(ParameterMapping).where(ParameterMapping.id == identifier)
    )
    return result.scalar_one_or_none()


async def list_parameters(
    db: AsyncSession, endpoint_id: int | str, active_only: bool = True
) -> list[ParameterMapping]:
    """List the endpoint's parameter mappings (alphabetical by source field)."""
    identifier = _as_int(endpoint_id)
    if identifier is None:
        return []

    statement = (
        select(ParameterMapping)
        .where(ParameterMapping.api_endpoint_id == identifier)
        .order_by(ParameterMapping.source_parameter.asc())
    )
    if active_only:
        statement = statement.where(ParameterMapping.is_active == True)

    result = await db.execute(statement)
    return list(result.scalars().all())


async def create_parameter_flush(
    db: AsyncSession, endpoint_id: int | str, data: ParameterCreate
) -> ParameterMapping:
    """Stage and flush one mapping; caller owns commit/rollback."""
    parameter = ParameterMapping(
        api_endpoint_id=_as_int(endpoint_id), **_parameter_values(data)
    )
    db.add(parameter)
    await db.flush()
    return parameter


async def create_parameter(
    db: AsyncSession, endpoint_id: int | str, data: ParameterCreate
) -> ParameterMapping:
    """Insert a single parameter mapping (caller ensures the endpoint exists)."""
    parameter = await create_parameter_flush(db, endpoint_id, data)
    await db.commit()
    await db.refresh(parameter)
    return parameter


async def bulk_create_parameters_flush(
    db: AsyncSession, endpoint_id: int | str, params: list[ParameterCreate]
) -> list[ParameterMapping]:
    """Stage and flush a batch, without committing or refreshing its rows.

    Caller owns atomic endpoint-plus-mapping groups and must roll back on
    any failure. Invalid endpoint IDs and empty batches retain the CRUD
    wrapper's empty-list behavior.
    """
    identifier = _as_int(endpoint_id)
    if identifier is None or not params:
        return []

    objects = [
        ParameterMapping(api_endpoint_id=identifier, **_parameter_values(item))
        for item in params
    ]
    db.add_all(objects)  # one batch INSERT on flush
    await db.flush()
    return objects


async def bulk_create_parameters(
    db: AsyncSession, endpoint_id: int | str, params: list[ParameterCreate]
) -> list[ParameterMapping]:
    """Insert every parameter in a single batch and return the persisted rows."""
    objects = await bulk_create_parameters_flush(db, endpoint_id, params)
    if not objects:
        return []
    await db.commit()
    for obj in objects:
        await db.refresh(obj)
    return objects


async def update_parameter(
    db: AsyncSession, param_id: int | str, data: dict
) -> ParameterMapping | None:
    """Apply a partial update; ``None`` when the row does not exist."""
    parameter = await _fetch_by_id(db, param_id)
    if parameter is None:
        return None

    for field, value in data.items():
        setattr(parameter, field, _enum_value(value))

    await db.commit()
    await db.refresh(parameter)
    return parameter


async def delete_parameter(db: AsyncSession, param_id: int | str) -> bool:
    """Hard-delete a single mapping; ``False`` when the row does not exist."""
    parameter = await _fetch_by_id(db, param_id)
    if parameter is None:
        return False

    await db.delete(parameter)
    await db.commit()
    return True


async def delete_all_parameters(db: AsyncSession, endpoint_id: int | str) -> int:
    """Hard-delete every mapping of an endpoint and return the row count."""
    identifier = _as_int(endpoint_id)
    if identifier is None:
        return 0

    result = await db.execute(
        delete(ParameterMapping).where(ParameterMapping.api_endpoint_id == identifier)
    )
    await db.commit()
    return result.rowcount or 0
