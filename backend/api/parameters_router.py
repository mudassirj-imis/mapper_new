from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.models import DataTypeEnum, ParamTypeEnum
from backend.services.central_auth import CentralUser

# Protected routes receive the centralized identity, not the local ORM user.
User = CentralUser
from backend.schemas.common import SuccessResponse
from backend.schemas.parameter import ParameterBulkCreate, ParameterResponse
from backend.services import endpoint_service, parameter_service

__all__ = ["ParameterUpdate", "router"]

router = APIRouter(tags=["Parameter Mappings"])


class ParameterUpdate(BaseModel):
    """Partial update payload for a single parameter mapping."""

    source_parameter: str | None = None
    target_parameter: str | None = None
    data_type: DataTypeEnum | None = None
    parameter_type: ParamTypeEnum | None = None
    is_active: bool | None = None


@router.get(
    "/api-endpoints/{endpoint_id}/parameters",
    response_model=list[ParameterResponse],
)
async def list_endpoint_parameters(
    endpoint_id: int,
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
    endpoint_id: int,
    payload: ParameterBulkCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> list[ParameterResponse]:
    """Insert many parameter mappings for an endpoint in one batch."""
    endpoint = await endpoint_service.get_endpoint(db, endpoint_id)

    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )

    return await parameter_service.bulk_create_parameters(
        db, endpoint_id, payload.parameters
    )


@router.put("/parameters/{param_id}", response_model=ParameterResponse)
async def update_parameter(
    param_id: int,
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
    param_id: int,
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

    return SuccessResponse(
        success=True,
        message="Parameter mapping deleted",
    )