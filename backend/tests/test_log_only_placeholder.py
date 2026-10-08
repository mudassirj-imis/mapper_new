"""The log views must return a placeholder when no external response exists."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from backend.services import audit_enrichment, log_service

PLACEHOLDER = "Log only endpoint"


def _log_row(**overrides):
    """A ``(log, endpoint)`` pair shaped like the list/detail query rows."""
    log = SimpleNamespace(
        id=9,
        endpoint_id=1,
        status="SUCCESS",
        source_request_headers=None,
        source_request_payload=None,
        source_response=None,
        client_status_code=None,
        target_request_headers=None,
        target_request_payload=None,
        target_query_params=None,
        target_response=None,
        response_time_ms=5,
        upstream_status_code=None,
        error_message=None,
        created_at=datetime(2026, 1, 1),
    )
    for name, value in overrides.items():
        setattr(log, name, value)
    endpoint = SimpleNamespace(
        method="POST",
        source_api_url="https://source.test",
        target_api_url="https://target.test",
    )
    return log, endpoint


def _db(*results):
    """A session whose ``execute`` replays ``results`` in order."""
    db = MagicMock()
    pending = iter(results)

    async def execute(_statement):
        return next(pending)

    db.execute = AsyncMock(side_effect=execute)
    return db


def _probe():
    probe = MagicMock()
    probe.ensure = AsyncMock()
    probe.load_options = Mock(return_value=[])
    probe.apply_defaults = Mock()
    return probe


class PlaceholderHelperTests(unittest.TestCase):
    def test_nullish_values_become_the_placeholder(self):
        for value in (None, {}, [], "", "   "):
            with self.subTest(value=value):
                self.assertEqual(
                    log_service._external_response_or_placeholder(value),
                    PLACEHOLDER,
                )

    def test_captured_responses_pass_through(self):
        captured = {"message": "upstream ok"}
        for value in (captured, ["chunk"], "raw body"):
            with self.subTest(value=value):
                self.assertEqual(
                    log_service._external_response_or_placeholder(value), value
                )


class LogServicePlaceholderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.object(log_service, "schema_probe", _probe())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_detail_null_external_response_returns_placeholder(self):
        result = Mock()
        result.first.return_value = _log_row()

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            detail = await log_service.get_log(_db(result), 9)

        self.assertEqual(detail.external_response, PLACEHOLDER)

    async def test_detail_empty_ingested_response_returns_placeholder(self):
        """Ingest stores ``{}`` when the caller supplied no response body."""
        result = Mock()
        result.first.return_value = _log_row(target_response={})

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            detail = await log_service.get_log(_db(result), 9)

        self.assertEqual(detail.external_response, PLACEHOLDER)

    async def test_detail_captured_response_is_untouched(self):
        captured = {"message": "upstream ok"}
        result = Mock()
        result.first.return_value = _log_row(target_response=captured)

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            detail = await log_service.get_log(_db(result), 9)

        self.assertEqual(detail.external_response, captured)

    async def test_detail_mongo_response_wins_over_placeholder(self):
        """Enrichment runs first: a real captured body is never masked."""
        result = Mock()
        result.first.return_value = _log_row(target_response=None)

        with patch.object(
            audit_enrichment,
            "enrich_rows",
            return_value={9: {"external_response": {"from": "mongo"}}},
        ):
            detail = await log_service.get_log(_db(result), 9)

        self.assertEqual(detail.external_response, {"from": "mongo"})

    async def test_list_rows_get_the_placeholder(self):
        count = Mock()
        count.scalar.return_value = 1
        page = Mock()
        page.all.return_value = [_log_row(target_response={})]

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            _total, items, _page, _per = await log_service.list_logs(
                _db(count, page)
            )

        self.assertEqual(items[0].external_response, PLACEHOLDER)

    async def test_list_rows_keep_captured_responses(self):
        captured = {"message": "upstream ok"}
        count = Mock()
        count.scalar.return_value = 1
        page = Mock()
        page.all.return_value = [_log_row(target_response=captured)]

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            _total, items, _page, _per = await log_service.list_logs(
                _db(count, page)
            )

        self.assertEqual(items[0].external_response, captured)


if __name__ == "__main__":
    unittest.main()
