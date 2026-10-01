from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.db.session import get_db
from backend.services.central_auth import (
    CentralAuthError,
    CentralAuthRejected,
    CentralAuthUnavailable,
    CentralUser,
    validate_access_token,
)
from backend.services.http_client import get_http_client

__all__ = [
    "bearer_scheme",
    "get_db",
    "get_current_active_user",
    "get_current_user",
    "require_roles",
]


bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Centralized SSPA/IMIS access token",
)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    http_client=Depends(get_http_client),
) -> CentralUser:
    """Validate the central access token and return its current identity."""
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_ERROR

    try:
        return await validate_access_token(http_client, credentials.credentials)
    except CentralAuthRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message or "Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except CentralAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    except CentralAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        ) from exc


async def get_current_active_user(
    current_user: CentralUser = Depends(get_current_user),
) -> CentralUser:
    """Reject a central identity that is no longer active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user


def require_roles(*roles: str):
    """Dependency factory gating an endpoint on central role names."""

    async def _require_roles(
        current_user: CentralUser = Depends(get_current_active_user),
    ) -> CentralUser:
        if not set(current_user.roles).intersection(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _require_roles
