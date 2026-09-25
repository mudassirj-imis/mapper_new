"""Parameter mapping request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import DataTypeEnum, ParamTypeEnum


class ParameterCreate(BaseModel):
    """A single source -> target parameter transformation to persist."""

    source_parameter: str
    target_parameter: str
    data_type: DataTypeEnum = DataTypeEnum.STRING
    parameter_type: ParamTypeEnum = ParamTypeEnum.BODY
    is_active: bool = True


class ParameterResponse(BaseModel):
    """Stored parameter mapping (read model)."""

    model_config = ConfigDict(from_attributes=True)

    # ``api_endpoint_parameter_mapping`` uses INT auto-increment keys (see
    # ``ParameterMapping``); declaring these as UUID rejected every real row.
    id: int
    api_endpoint_id: int
    source_parameter: str
    target_parameter: str
    data_type: str | None = None
    parameter_type: str | None = None
    is_active: bool | None = None
    created_at: datetime | None = None


class ParameterBulkCreate(BaseModel):
    """Bulk payload used when saving every mapping of an endpoint at once."""

    parameters: list[ParameterCreate] = Field(default_factory=list)
