"""Pydantic schemas for request/response validation.

Re-exports the public schema objects so routers and services can import
everything from ``backend.schemas`` directly.
"""

from backend.schemas.auth import LoginRequest, LoginResponse, TokenData, UserResponse
from backend.schemas.common import PaginatedResponse, SuccessResponse
from backend.schemas.endpoint import (
    CompleteMappingRequest,
    CompleteMappingResponse,
    EndpointCreate,
    EndpointResponse,
    EndpointUpdate,
    MappingItem,
)
from backend.schemas.gateway import MapAndCallRequest, MapAndCallResponse
from backend.schemas.log import CallLogListResponse, CallLogResponse, CallLogSummary
from backend.schemas.parameter import (
    ParameterBulkCreate,
    ParameterCreate,
    ParameterResponse,
)

__all__ = [
    # auth
    "LoginRequest",
    "LoginResponse",
    "TokenData",
    "UserResponse",
    # common
    "PaginatedResponse",
    "SuccessResponse",
    # endpoint
    "CompleteMappingRequest",
    "CompleteMappingResponse",
    "EndpointCreate",
    "EndpointResponse",
    "EndpointUpdate",
    "MappingItem",
    # gateway
    "MapAndCallRequest",
    "MapAndCallResponse",
    # log
    "CallLogListResponse",
    "CallLogResponse",
    "CallLogSummary",
    # parameter
    "ParameterBulkCreate",
    "ParameterCreate",
    "ParameterResponse",
]
