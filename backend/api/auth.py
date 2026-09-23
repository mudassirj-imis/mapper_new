"""Authentication router: login, token validation, logout and profile.

Mounted under ``/api`` in ``backend.main`` so the effective paths are
``/api/auth/login``, ``/api/auth/validate``, ``/api/auth/logout`` and
``/api/auth/me``. Tokens are stateless JWTs — logout is a client-side
operation and intentionally a no-op server-side.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_user, get_db
from backend.models.user import User
from backend.schemas.auth import LoginRequest, LoginResponse, UserResponse
from backend.services.auth_service import (
    create_access_token,
    verify_password,
)

__all__ = ["router"]

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _roles_of(user: User) -> list[str]:
    """Role names attached to ``user`` (relationships must be eager-loaded)."""
    return [role.role_name for role in user.roles]


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse | JSONResponse:
    """Exchange email + password for a signed access token."""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    # Same generic message for unknown email and wrong password so the
    # response cannot be used to enumerate accounts.
    if user is None or not verify_password(request.password, user.password_hash):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=LoginResponse(
                success=False, message="Invalid credentials"
            ).model_dump(),
        )

    if not user.is_active:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=LoginResponse(
                success=False, message="Account is inactive", email=user.email
            ).model_dump(),
        )

    token = create_access_token(
        {"user_id": user.id, "email": user.email, "roles": _roles_of(user)}
    )
    return LoginResponse(
        success=True,
        message="Login successful",
        token=token,
        email=user.email,
    )


@router.post("/validate")
async def validate_token(current_user: User = Depends(get_current_user)) -> dict:
    """Confirm the bearer token is valid and return the caller's identity."""
    return {
        "success": True,
        "valid": True,
        "user_id": current_user.id,
        "email": current_user.email,
        "user_name": current_user.user_name,
        "roles": _roles_of(current_user),
    }


@router.post("/logout")
async def logout() -> dict[str, str | bool]:
    """Stateless JWT logout — nothing to revoke server-side."""
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Full profile of the authenticated user."""
    return UserResponse(
        id=current_user.id,
        user_name=current_user.user_name,
        email=current_user.email,
        is_active=current_user.is_active,
        roles=_roles_of(current_user),
    )
