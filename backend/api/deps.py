"""Shared FastAPI dependencies: DB session, current user, role guards.

``oauth2_scheme`` drives Swagger's Authorize button; the actual token is
issued by ``POST /api/auth/login`` (JSON credentials, not OAuth2 form data),
so the ``tokenUrl`` below is informational only.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.session import get_db
from backend.models.user import User
from backend.services.auth_service import decode_token

__all__ = [
    "get_db",
    "get_current_active_user",
    "get_current_user",
    "oauth2_scheme",
    "require_roles",
]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the JWT bearer token to an active ``User`` row.

    Roles are eagerly loaded (``selectinload``) so downstream dependencies
    and endpoints can read ``user.roles`` without triggering lazy I/O
    outside the async session context.
    """
    payload = decode_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise _CREDENTIALS_ERROR

    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise _CREDENTIALS_ERROR
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Defence-in-depth wrapper: reject accounts deactivated after issuance."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user


def require_roles(*roles: str):
    """Dependency factory gating an endpoint on at least one required role."""

    async def _require_roles(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        granted = {role.role_name for role in current_user.roles}
        if not granted.intersection(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _require_roles
