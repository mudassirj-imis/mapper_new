"""Authentication primitives: JWT issuing/decoding and argon2 password hashing.

Replaces the legacy HMAC token scheme (timestamp + user-id digest, see the
old ``local_mapper`` backend) which was unauthenticated in payload terms and
forced a full table scan per request. Standard JWTs carry the user id, email
and role names as signed claims instead.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from passlib.hash import argon2

from backend.core.config import settings

__all__ = [
    "create_access_token",
    "decode_token",
    "hash_password",
    "verify_password",
]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Sign a JWT containing ``data`` plus ``exp``/``iat`` claims.

    ``data`` must include the user id, email and roles list; the lifetime
    defaults to ``settings.JWT_EXPIRE_HOURS`` (24 h).
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update(
        {
            "iat": now,
            "exp": now + (expires_delta or timedelta(hours=settings.JWT_EXPIRE_HOURS)),
        }
    )
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT; raise ``HTTPException`` (401) when invalid.

    Returns the full claims dictionary so callers can read ``user_id``,
    ``email`` and ``roles``.
    """
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except JWTError as exc:
        raise _CREDENTIALS_ERROR from exc


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check ``plain_password`` against an argon2 hash (False on bad hash)."""
    try:
        return argon2.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    """Hash ``password`` with argon2id (used for seeding / password changes)."""
    return argon2.hash(password)
