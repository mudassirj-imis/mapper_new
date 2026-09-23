"""In-memory rate limiter with a per-key sliding-window token bucket.

Tracks caller timestamps per key (``endpoint_id`` for the gateway path, a
``client:host`` key for the global middleware) in deques and only admits a new
request when the number of requests inside the trailing window is below the
configured ``rpm``. The window is a fixed 60 seconds by default.

State lives in memory for the lifetime of the process (reset on restart) — no
external store, no persistence. A simple ``asyncio.Lock`` serialises access so
the counters stay correct under concurrency.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from backend.core.config import settings

__all__ = ["RateLimitDecision", "RateLimiter", "rate_limiter"]


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a rate-limit check."""

    allowed: bool
    retry_after: int = 0  # seconds until the oldest token in the window expires


class RateLimiter:
    """Sliding-window rate limiter keyed by an arbitrary ``key`` string."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = float(window_seconds)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, rpm: int | None) -> RateLimitDecision:
        """Allow/deny one request for ``key`` under the ``rpm`` budget.

        ``rpm`` follows the ``api_endpoints.rate_limit_rpm`` convention: value
        ``0`` blocks every request, a negative/None value falls back to the
        configured default RPM.
        """
        if rpm is None or rpm < 0:
            rpm = settings.RATE_LIMIT_DEFAULT_RPM
        if rpm <= 0:
            # An explicit zero budget rejects everything (no window needed).
            return RateLimitDecision(False, retry_after=int(self._window))

        budget = int(rpm)
        async with self._lock:
            now = time.monotonic()
            stamps = self._requests[key]

            # Drop timestamps that fell out of the trailing window.
            while stamps and now - stamps[0] >= self._window:
                stamps.popleft()

            if len(stamps) >= budget:
                oldest = stamps[0]
                retry_after = max(1, int(round(self._window - (now - oldest))))
                return RateLimitDecision(False, retry_after)

            stamps.append(now)
            return RateLimitDecision(True)

    def size(self) -> int:
        """Number of distinct keys currently tracked (test/diagnostic aid)."""
        return len(self._requests)


#: Process-wide instance shared by the gateway router and the middleware.
rate_limiter = RateLimiter()