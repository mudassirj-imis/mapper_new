"""The legacy dynamic gateway route must behave like the old engine."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response

from backend.api import gateway_proxy_router
from backend.services.gateway_engine import GatewayEngine, MappingSnapshot


def _request(method="GET", query="", body=b"", headers=None):
    """A minimal ASGI request the handler can read like a real one."""
    items = list(headers) if headers is not None else [("Host", "mapper.test")]
    items.append(("X-Trace", "abc"))
    if body:
        items.append(("Content-Length", str(len(body))))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/probe",
        "raw_path": b"/probe",
        "root_path": "",
        "query_string": query.encode(),
        "headers": [(name.lower().encode(), value.encode()) for name, value in items],
        "client": ("10.0.0.1", 1234),
        "server": ("mapper.test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _result(**overrides):
    base = {
        "request_id": "req-1",
        "endpoint_id": 284,
        "method": "GET",
        "path": "/getCallByDate2.php",
        "request_headers": {},
        "success": True,
        "data": {"rows": []},
        "status_code": 200,
        "error": None,
        "status": "SUCCESS",
    }
    base.update(overrides)
    return base


class GatewayProxyHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, request, path, result, app_root=""):
        background = BackgroundTasks()
        engine = MagicMock()
        engine.process_request = AsyncMock(return_value=result)
        db = MagicMock()
        write = AsyncMock()

        with (
            patch.object(gateway_proxy_router, "GatewayEngine", return_value=engine),
            patch.object(gateway_proxy_router, "write_call_log", write),
            patch.object(gateway_proxy_router.settings, "APP_ROOT_PATH", app_root),
        ):
            response = await gateway_proxy_router.gateway_proxy(
                request, path, background, db=db, http_client=MagicMock()
            )

        return response, background, engine, write, db

    async def test_get_forwards_the_query_string_as_request_data(self):
        """Legacy contract: on GET the query string IS the request payload."""
        response, _bg, engine, _write, _db = await self._invoke(
            _request(method="GET", query="date=20241213&user=cmsAlpha&pass=x"),
            "getCallByDate2.php",
            _result(),
        )

        args = engine.process_request.call_args.args
        self.assertIsNone(args[0])
        self.assertEqual(args[1], {"date": "20241213", "user": "cmsAlpha", "pass": "x"})
        self.assertEqual(args[3], "/getCallByDate2.php")
        self.assertEqual(args[4], "GET")
        self.assertEqual(response.status_code, 200)

    async def test_post_forwards_the_json_body(self):
        _response, _bg, engine, _write, _db = await self._invoke(
            _request(
                method="POST",
                body=b'{"ticket_id": 7}',
                headers=[("Content-Type", "application/json")],
            ),
            "v1/integration/cc/create-ticket",
            _result(method="POST", endpoint_id=277),
        )

        args = engine.process_request.call_args.args
        self.assertEqual(args[1], {"ticket_id": 7})
        self.assertEqual(args[3], "/v1/integration/cc/create-ticket")
        self.assertEqual(args[4], "POST")

    async def test_non_json_body_becomes_an_empty_payload(self):
        _response, _bg, engine, _write, _db = await self._invoke(
            _request(method="POST", body=b"<html>"),
            "something",
            _result(),
        )

        self.assertEqual(engine.process_request.call_args.args[1], {})

    async def test_hop_by_hop_headers_are_not_forwarded(self):
        _response, _bg, engine, _write, _db = await self._invoke(
            _request(
                method="POST",
                body=b"{}",
                headers=[("Content-Type", "application/json")],
            ),
            "something",
            _result(),
        )

        forwarded = engine.process_request.call_args.args[2]
        self.assertIn("x-trace", forwarded)
        self.assertNotIn("host", forwarded)
        self.assertNotIn("content-length", forwarded)

    async def test_matched_endpoint_schedules_the_log_write(self):
        response, background, _engine, write, db = await self._invoke(
            _request(
                method="POST",
                body=b'{"a": 1}',
                headers=[("Content-Type", "application/json")],
            ),
            "something",
            _result(status_code=201),
        )

        self.assertEqual(len(background.tasks), 1)
        await background()

        write.assert_awaited_once()
        written_db, log_data = write.await_args.args
        self.assertIs(written_db, db)
        self.assertEqual(log_data["internal_request_body"], {"a": 1})
        self.assertEqual(log_data["path"], "/getCallByDate2.php")
        self.assertEqual(response.status_code, 201)

    async def test_unresolved_endpoint_is_not_logged(self):
        """Probe traffic (404, no endpoint) must not flood api_call_log."""
        response, background, _engine, write, _db = await self._invoke(
            _request(method="GET", query="x=1"),
            "no/such/route",
            _result(
                endpoint_id=None,
                success=False,
                status_code=404,
                data=None,
                error="Endpoint not found: GET /no/such/route",
            ),
        )

        self.assertEqual(len(background.tasks), 0)
        await background()
        write.assert_not_awaited()
        self.assertEqual(response.status_code, 404)
        payload = json.loads(response.body)
        self.assertNotIn("status_code", payload)
        self.assertIn("Endpoint not found", payload["error"])

    async def test_204_returns_an_empty_response(self):
        response, _bg, _engine, _write, _db = await self._invoke(
            _request(
                method="POST",
                body=b"{}",
                headers=[("Content-Type", "application/json")],
            ),
            "something",
            _result(status_code=204, data=None),
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.body, b"")
        self.assertIsInstance(response, Response)

    async def test_missing_status_defaults_from_success(self):
        ok, _bg, _engine, _write, _db = await self._invoke(
            _request(), "something", _result(status_code=None, success=True)
        )
        failed, _bg2, _engine2, _write2, _db2 = await self._invoke(
            _request(), "something", _result(status_code=None, success=False)
        )

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(failed.status_code, 500)

    async def test_app_root_path_prefix_is_stripped(self):
        _response, _bg, engine, _write, _db = await self._invoke(
            _request(method="GET", query="date=1"),
            "mapper-new/getCallByDate2.php",
            _result(),
            app_root="/mapper-new",
        )

        self.assertEqual(
            engine.process_request.call_args.args[3], "/getCallByDate2.php"
        )

    async def test_response_body_mirrors_the_legacy_envelope(self):
        response, _bg, _engine, _write, _db = await self._invoke(
            _request(),
            "something",
            _result(status_code=502, success=False, error="Upstream HTTP error"),
        )

        self.assertIsInstance(response, JSONResponse)
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("status_code", payload)
        self.assertEqual(payload["data"], {"rows": []})
        self.assertEqual(payload["error"], "Upstream HTTP error")


class QueryStringMappingTests(unittest.TestCase):
    """Legacy rows spell query mappings ``QUERYSTRING``; they must reach the URL."""

    def test_querystring_mappings_land_in_the_query_not_the_body(self):
        mappings = [
            MappingSnapshot("date", "date", "QUERYSTRING", "STRING"),
            MappingSnapshot("user", "login", "QUERYSTRING", "STRING"),
            MappingSnapshot("title", "subject", "BODY", "STRING"),
        ]
        body, _headers, query = GatewayEngine._transform_parameters(
            {"date": "20241213", "login": "cmsAlpha", "subject": "hi"},
            mappings,
            {},
        )

        self.assertEqual(query, {"date": "20241213", "user": "cmsAlpha"})
        self.assertEqual(body, {"title": "hi"})

    def test_modern_query_spelling_still_works(self):
        mappings = [MappingSnapshot("page", "page", "QUERY", "NUMBER")]
        body, _headers, query = GatewayEngine._transform_parameters(
            {"page": "2"}, mappings, {}
        )

        self.assertEqual(query, {"page": "2"})
        self.assertEqual(body, {})

    def test_falsy_query_values_still_travel(self):
        mappings = [
            MappingSnapshot("page", "page", "QUERYSTRING", "NUMBER"),
            MappingSnapshot("flag", "enabled", "QUERY_STRING", "BOOLEAN"),
        ]
        _body, _headers, query = GatewayEngine._transform_parameters(
            {"page": 0, "enabled": False}, mappings, {}
        )

        self.assertEqual(query, {"page": 0, "flag": False})
