"""Global rate-limit middleware for the ``/api`` surface.

Complements the per-endpoint limiter applied to the gateway engine: this is a
coarse per-client-IP guard with a generous default budget, so a single noisy
client cannot monopolise the whole service while legitimate per-endpoint
budgets still govern individual mappings. Returns ``429`` with a ``Retry-After``
header when the budget is exceeded.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.core.config import settings
from backend.services.rate_limiter import RateLimiter

__all__ = ["RateLimitMiddleware"]

#: Paths exempt from the global guard (health probes called by operators/load balancers).
_EXEMPT_PATHS = ("/api/health",)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce a per-client-IP request budget on ``/api/*`` paths."""

    def __init__(
        self,
        app,
        rpm: int | None = None,
        window_seconds: float = 60.0,
    ) -> None:
        super().__init__(app)
        self._rpm = rpm if rpm is not None else int(settings.GLOBAL_RATE_LIMIT_RPM)
        self._limiter = RateLimiter(window_seconds=window_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.startswith("/api") and not path.startswith(_EXEMPT_PATHS):
            client = request.client.host if request.client else "unknown"
            decision = await self._limiter.check(f"global:{client}", self._rpm)
            if not decision.allowed:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(decision.retry_after)},
                    content={
                        "success": False,
                        "error": "Global rate limit exceeded",
                        "status_code": 429,
                        "retry_after": decision.retry_after,
                    },
                )
        return await call_next(request)