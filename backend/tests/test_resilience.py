"""Developer tests for Tasks 6-8: resilience, mock/webhook, and log querying.

No network, database or secret files - everything is mocked (mirrors the style of
:mod:`test_foundations`).
"""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic_settings import DotEnvSettingsSource

# Build the app settings with fixed test secrets and no dotenv reads.
with (
    patch.dict(os.environ, {"JWT_SECRET": "test", "ENCRYPTION_KEY": "test"}, clear=True),
    patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}),
):
    from backend.api.health_router import health
    from backend.middleware.rate_limit import RateLimitMiddleware
    from backend.services import log_service
    from backend.services.circuit_breaker import CircuitBreaker, CircuitState
    from backend.services.dedup import DedupCache
    from backend.services.gateway_engine import GatewayEngine
    from backend.services.mock_service import build_mock_result
    from backend.services.rate_limiter import RateLimiter
    from backend.services.webhook_service import event_for_result
    from test_foundations import (
        endpoint_snapshot,
        make_client,
        make_db,
    )


def _request(path: str) -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("10.0.0.5", 1234),
        "server": ("test.local", 80),
    })


class RateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_up_to_budget_then_rejects(self):
        limiter = RateLimiter(window_seconds=10)
        for _ in range(3):
            self.assertTrue((await limiter.check("ep", 3)).allowed)
        decision = await limiter.check("ep", 3)
        self.assertFalse(decision.allowed)
        self.assertGreater(decision.retry_after, 0)

    async def test_zero_budget_blocks_everything(self):
        limiter = RateLimiter()
        self.assertFalse((await limiter.check("ep", 0)).allowed)

    async def test_none_budget_falls_back_to_default(self):
        limiter = RateLimiter()
        self.assertTrue((await limiter.check("ep", None)).allowed)

    async def test_window_expires_and_allows_again(self):
        limiter = RateLimiter(window_seconds=0.05)
        await limiter.check("ep", 1)
        self.assertFalse((await limiter.check("ep", 1)).allowed)
        await asyncio.sleep(0.1)
        self.assertTrue((await limiter.check("ep", 1)).allowed)


class CircuitBreakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_opens_after_threshold_failures(self):
        breaker = CircuitBreaker(failure_threshold=3, window_seconds=60, recovery_timeout=0.1)
        for _ in range(3):
            self.assertTrue(await breaker.allow("ep"))
            await breaker.record_failure("ep")
        self.assertEqual(breaker.state("ep"), CircuitState.OPEN)
        self.assertFalse(await breaker.allow("ep"))

    async def test_recovers_to_half_open_then_closes_on_success(self):
        breaker = CircuitBreaker(failure_threshold=2, window_seconds=60, recovery_timeout=0.05)
        await breaker.record_failure("ep")
        await breaker.record_failure("ep")
        self.assertEqual(breaker.state("ep"), CircuitState.OPEN)
        self.assertFalse(await breaker.allow("ep"))
        await asyncio.sleep(0.1)
        self.assertTrue(await breaker.allow("ep"))  # single trial
        self.assertEqual(breaker.state("ep"), CircuitState.HALF_OPEN)
        await breaker.record_success("ep")
        self.assertEqual(breaker.state("ep"), CircuitState.CLOSED)
        self.assertTrue(await breaker.allow("ep"))

    async def test_failure_during_half_open_retrips(self):
        breaker = CircuitBreaker(failure_threshold=1, window_seconds=60, recovery_timeout=0.01)
        await breaker.record_failure("ep")
        await asyncio.sleep(0.02)
        self.assertTrue(await breaker.allow("ep"))
        await breaker.record_failure("ep")
        self.assertEqual(breaker.state("ep"), CircuitState.OPEN)
        self.assertFalse(await breaker.allow("ep"))


class DedupCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_request_replays_cached_result(self):
        cache = DedupCache(ttl_seconds=5, max_entries=100)
        self.assertIsNone(await cache.get("ep", {"a": 1}))
        await cache.set("ep", {"a": 1}, {"request_id": "x", "success": True})
        self.assertEqual((await cache.get("ep", {"a": 1}))["request_id"], "x")

    async def test_key_is_order_insensitive(self):
        cache = DedupCache(ttl_seconds=5)
        await cache.set("ep", {"a": 1, "b": 2}, {"request_id": "y"})
        self.assertEqual((await cache.get("ep", {"b": 2, "a": 1}))["request_id"], "y")

    async def test_expired_entries_are_dropped(self):
        cache = DedupCache(ttl_seconds=0.05, max_entries=10)
        await cache.set("ep", {"a": 1}, {"request_id": "z"})
        await asyncio.sleep(0.1)
        self.assertIsNone(await cache.get("ep", {"a": 1}))


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_healthy_report(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=None)
        body = await health(db=db)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "connected")
        self.assertIn("uptime_seconds", body)
        self.assertIn("platform", body)

    async def test_degraded_when_db_down(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        body = await health(db=db)
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["database"], "unavailable")


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_limit_returns_429(self):
        middleware = RateLimitMiddleware(FastAPI(), rpm=1)
        request = _request("/api/map-and-call")

        async def downstream(_request):
            return PlainTextResponse("ok")

        self.assertEqual((await middleware.dispatch(request, downstream)).status_code, 200)
        self.assertEqual((await middleware.dispatch(request, downstream)).status_code, 429)

    async def test_health_path_is_exempt(self):
        middleware = RateLimitMiddleware(FastAPI(), rpm=1)
        request = _request("/api/health")

        async def downstream(_request):
            return PlainTextResponse("ok")

        for _ in range(3):
            self.assertEqual((await middleware.dispatch(request, downstream)).status_code, 200)


class WebhookClassificationTests(unittest.TestCase):
    def test_call_outcome_classification(self):
        self.assertEqual(event_for_result({"success": True}), "call_success")
        self.assertEqual(
            event_for_result({"success": False, "failure_kind": "upstream_timeout"}),
            "call_timeout",
        )
        self.assertEqual(
            event_for_result({"success": False, "failure_kind": "upstream_http"}),
            "call_failure",
        )


class LogServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_logs_paginates_with_total(self):
        db = MagicMock()
        count = Mock()
        count.scalar.return_value = 7
        page = Mock()
        page.scalars.return_value.all.return_value = [Mock(), Mock()]
        results = iter([count, page])

        async def execute(_statement):
            return next(results)

        db.execute = AsyncMock(side_effect=execute)
        total, items, page_no, per = await log_service.list_logs(
            db, status="failed", page=2, per_page=2
        )
        self.assertEqual(total, 7)
        self.assertEqual(len(items), 2)
        self.assertEqual(page_no, 2)
        self.assertEqual(per, 2)

    async def test_get_log_invalid_id_returns_none_without_query(self):
        db = MagicMock()
        db.execute = AsyncMock()
        self.assertIsNone(await log_service.get_log(db, "not-a-uuid"))
        db.execute.assert_not_awaited()

    async def test_invalid_status_filter_is_ignored(self):
        db = MagicMock()
        count = Mock()
        count.scalar.return_value = 0
        page = Mock()
        page.scalars.return_value.all.return_value = []
        results = iter([count, page])

        async def execute(_statement):
            return next(results)

        db.execute = AsyncMock(side_effect=execute)
        total, items, *_ = await log_service.list_logs(db, status="bogus")
        self.assertEqual(total, 0)
        self.assertEqual(items, [])


class MockShortCircuitTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_returns_configured_response_without_upstream(self):
        endpoint = endpoint_snapshot(mock_enabled=True, mock_response={"hello": [1, 2, 3]})
        client = make_client()
        engine = GatewayEngine(make_db(), client)
        outcome = await engine.execute_resolved(endpoint, {"a": 1}, {}, "/v1/items", "POST")
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.source, "mock")
        self.assertEqual(outcome.to_result()["status_code"], 200)
        self.assertEqual(outcome.to_result()["data"], {"hello": [1, 2, 3]})
        client.send.assert_not_awaited()

    def test_build_mock_result_sets_success_audit_envelope(self):
        endpoint = endpoint_snapshot(mock_enabled=True, mock_response={"ok": True})
        result = build_mock_result(
            endpoint, request_id="rid", method="POST", url="/v1/items", headers={"X": "1"}
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["data"], {"ok": True})
        self.assertIn("external_request_url", result)


if __name__ == "__main__":
    unittest.main()