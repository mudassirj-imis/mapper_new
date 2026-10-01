from __future__ import annotations

import asyncio
import hashlib
import json
import time

from backend.core.config import settings

__all__ = ["DedupCache", "dedup_cache"]


class DedupCache:
    """TTL cache keyed by ``(endpoint_id, canonical request_data)``."""

    def __init__(
        self, ttl_seconds: float | None = None, max_entries: int | None = None
    ) -> None:
        self._ttl = (
            float(ttl_seconds)
            if ttl_seconds is not None
            else float(settings.DEDUP_TTL_SECONDS)
        )
        self._max_entries = (
            int(max_entries)
            if max_entries is not None
            else int(settings.DEDUP_MAX_ENTRIES)
        )

        self._store: dict[str, tuple[float, dict]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _canonical(request_data: dict | None) -> str:
        """Deterministic, sorted-key JSON for hashing purposes."""
        return json.dumps(
            request_data if request_data is not None else {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @classmethod
    def _key(cls, endpoint_id, request_data: dict | None) -> str:
        payload = f"{endpoint_id}:{cls._canonical(request_data)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def get(self, endpoint_id, request_data: dict | None) -> dict | None:
        """Return the cached result dict for an identical request, if fresh."""
        async with self._lock:
            key = self._key(endpoint_id, request_data)
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, result = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return result

    async def set(self, endpoint_id, request_data: dict | None, result: dict) -> None:
        """Store a result (only cache when the caller deems it cacheable)."""
        async with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict()
                if len(self._store) >= self._max_entries:
                    self._store.pop(next(iter(self._store)))
            key = self._key(endpoint_id, request_data)
            self._store[key] = (time.monotonic() + self._ttl, dict(result))

    def _evict(self) -> None:
        """Drop already-expired entries to make room for new ones."""
        now = time.monotonic()
        expired = [
            key for key, (expires_at, _) in self._store.items() if now >= expires_at
        ]
        for key in expired:
            del self._store[key]

    def size(self) -> int:
        return len(self._store)


dedup_cache = DedupCache()
