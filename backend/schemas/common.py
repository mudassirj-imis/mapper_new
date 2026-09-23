"""Shared response envelopes used across the API."""

from typing import Any

from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    """Generic single-operation result."""

    success: bool = True
    message: str = ""


class PaginatedResponse(BaseModel):
    """Generic pagination envelope for list endpoints."""

    items: list[Any] = Field(default_factory=list)
    total: int
    page: int
    per_page: int
    pages: int
