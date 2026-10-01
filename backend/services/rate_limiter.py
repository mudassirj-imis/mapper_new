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
    retry_after: int = 0


class RateLimiter:
    """Sliding-window rate limiter keyed by an arbitrary ``key`` string."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = float(window_seconds)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, rpm: int | None) -> RateLimitDecision:

        if rpm is None or rpm < 0:
            rpm = settings.RATE_LIMIT_DEFAULT_RPM
        if rpm <= 0:
            return RateLimitDecision(False, retry_after=int(self._window))

        budget = int(rpm)
        async with self._lock:
            now = time.monotonic()
            stamps = self._requests[key]

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


rate_limiter = RateLimiter()
