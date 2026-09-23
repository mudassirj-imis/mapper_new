"""Per-endpoint circuit breaker with a CLOSED -> OPEN -> HALF_OPEN state machine.

Failures are counted in memory inside a trailing window; when the count for a
key reaches the configured threshold the circuit trips OPEN and callers are
rejected (503) without hitting the downstream. After the recovery timeout
elapses the next check reopens the circuit to HALF_OPEN and lets a single trial
request through — a success closes it again, a failure re-trips it.

State is process-local and threaded-safe via an ``asyncio.Lock``.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum

from backend.core.config import settings

__all__ = ["CircuitState", "CircuitBreaker", "circuit_breaker"]


class CircuitState(str, Enum):
    """Lifecycle of a per-key circuit."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class _KeyState:
    state: CircuitState = CircuitState.CLOSED
    failures: deque[float] = field(default_factory=deque)
    trip_at: float = 0.0


class CircuitBreaker:
    """Breaker keyed by ``endpoint_id``; thresholds come from config."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        window_seconds: float | None = None,
        recovery_timeout: float | None = None,
    ) -> None:
        self._threshold = (
            failure_threshold
            if failure_threshold is not None
            else int(settings.CIRCUIT_FAILURE_THRESHOLD)
        )
        self._window = (
            float(window_seconds)
            if window_seconds is not None
            else float(settings.CIRCUIT_WINDOW_SECONDS)
        )
        self._recovery = (
            float(recovery_timeout)
            if recovery_timeout is not None
            else float(settings.CIRCUIT_RECOVERY_TIMEOUT_SECONDS)
        )
        self._states: dict[str, _KeyState] = defaultdict(_KeyState)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        """Whether a request for ``key`` may proceed now.

        An OPEN circuit rejects until the recovery timeout elapses, then the
        next call reopens to HALF_OPEN and grants a single trial request.
        """
        async with self._lock:
            state = self._states[key]
            now = time.monotonic()
            self._prune(state, now)
            if state.state == CircuitState.OPEN:
                if now - state.trip_at >= self._recovery:
                    state.state = CircuitState.HALF_OPEN
                    return True
                return False
            return True

    async def record_success(self, key: str) -> None:
        """Close the circuit after a successful trial / steady success."""
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                return
            if state.state == CircuitState.HALF_OPEN:
                state.state = CircuitState.CLOSED
                state.failures.clear()
                state.trip_at = 0.0

    async def record_failure(self, key: str) -> None:
        """Count one upstream failure; tripping OPEN at the threshold."""
        async with self._lock:
            state = self._states[key]
            now = time.monotonic()
            self._prune(state, now)
            state.failures.append(now)
            if state.state == CircuitState.HALF_OPEN or len(state.failures) >= self._threshold:
                state.state = CircuitState.OPEN
                state.trip_at = now

    def state(self, key: str) -> CircuitState:
        """Current (unlocked, best-effort) state for a key, for diagnostics."""
        state = self._states.get(key)
        if state is None:
            return CircuitState.CLOSED
        self._prune(state, time.monotonic())
        return state.state

    def _prune(self, state: _KeyState, now: float) -> None:
        while state.failures and now - state.failures[0] >= self._window:
            state.failures.popleft()


#: Process-wide instance shared by the gateway router.
circuit_breaker = CircuitBreaker()