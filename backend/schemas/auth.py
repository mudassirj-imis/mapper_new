"""Authentication and user schemas."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Credentials posted to the login endpoint."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Login result — ``token`` is only present on success."""

    success: bool
    message: str
    token: str | None = None
    email: str | None = None


class TokenData(BaseModel):
    """Claims carried inside an issued JWT."""

    user_id: int
    email: str
    roles: list[str] = Field(default_factory=list)


class UserResponse(BaseModel):
    """A user account as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_name: str
    email: str | None = None
    is_active: bool | None = None
    roles: list[str] = Field(default_factory=list)
