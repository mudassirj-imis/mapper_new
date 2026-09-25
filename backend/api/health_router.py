"""Health, uptime and system diagnostics.

``GET /api/health`` performs a real ``SELECT 1`` against the database so the
reported status reflects current DB connectivity, not just process liveness.
Public by design — no auth, so load balancers and orchestrators can probe it.
"""

from __future__ import annotations

import platform
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db

__all__ = ["router"]

VERSION = "1.0.0"

router = APIRouter(tags=["Health"])

_STARTED = time.monotonic()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    """Liveness plus a database connectivity probe."""
    db_connected = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_connected = False

    return {
        "status": "ok" if db_connected else "degraded",
        "database": "connected" if db_connected else "unavailable",
        "uptime_seconds": round(time.monotonic() - _STARTED, 3),
        "version": VERSION,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
