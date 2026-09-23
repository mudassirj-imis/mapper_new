"""Parameter-mapping routes: listing, bulk creation, update and delete.

Mounted under ``/api`` in :mod:`backend.main`, so the effective paths are
``/api/api-endpoints/{endpoint_id}/parameters`` and
``/api/parameters/{param_id}``. Every route requires an authenticated, active
user.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.models import DataTypeEnum, ParamTypeEnum
from backend.models.user import User
from backend.schemas.common import SuccessResponse
from backend.schemas.parameter import ParameterBulkCreate, ParameterResponse
from backend.services import endpoint_service, parameter_service

__all__ = ["ParameterUpdate", "router"]

router = APIRouter(tags=["Parameter Mappings"])


class ParameterUpdate(BaseModel):
    """Partial update payload for a single parameter mapping.

    Lives here (not in ``backend.schemas.parameter``) because it is the only
    place that needs it: the bulk save contract uses ``ParameterCreate``.
    """

    source_parameter: str | None = None
    target_parameter: str | None = None
    data_type: DataTypeEnum | None = None
    parameter_type: ParamTypeEnum | None = None
    is_active: bool | None = None


@router.get(
    "/api-endpoints/{endpoint_id}/parameters", response_model=list[ParameterResponse]
)
async def list_endpoint_parameters(
    endpoint_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> list[ParameterResponse]:
    """List the active parameter mappings of an endpoint."""
    return await parameter_service.list_parameters(db, endpoint_id)


@router.post(
    "/api-endpoints/{endpoint_id}/parameters",
    response_model=list[ParameterResponse],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_endpoint_parameters(
    endpoint_id: UUID,
    payload: ParameterBulkCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> list[ParameterResponse]:
    """Insert many parameter mappings for an endpoint in one batch."""
    endpoint = await endpoint_service.get_endpoint(db, endpoint_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found"
        )
    return await parameter_service.bulk_create_parameters(
        db, endpoint_id, payload.parameters
    )


@router.put("/parameters/{param_id}", response_model=ParameterResponse)
async def update_parameter(
    param_id: UUID,
    payload: ParameterUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> ParameterResponse:
    """Partially update a single parameter mapping."""
    parameter = await parameter_service.update_parameter(
        db, param_id, payload.model_dump(exclude_unset=True)
    )
    if parameter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parameter mapping not found",
        )
    return parameter


@router.delete("/parameters/{param_id}", response_model=SuccessResponse)
async def delete_parameter(
    param_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> SuccessResponse:
    """Delete a single parameter mapping."""
    deleted = await parameter_service.delete_parameter(db, param_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parameter mapping not found",
        )
    return SuccessResponse(success=True, message="Parameter mapping deleted")
