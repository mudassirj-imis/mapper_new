import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from backend.schemas.log import CallLogIngestRequest
from backend.services import log_ingest


def _result(scalar_value):
    """A finished ``db.execute`` result exposing ``scalar()``."""
    result = Mock()
    result.scalar.return_value = scalar_value
    return result


class NormalisationTests(unittest.TestCase):
    def test_canonical_gateway_keys_pass_through(self):
        raw = {
            "request_id": "abc",
            "method": "post",
            "path": "/x",
            "success": True,
            "status": "SUCCESS",
            "status_code": 200,
            "data": {"message": "ok"},
            "internal_request_body": {"a": 1},
            "request_headers": {"Accept": "*/*"},
            "total_time_ms": 12,
        }
        out = log_ingest.normalise_log_payload(raw)

        self.assertEqual(out["request_id"], "abc")
        self.assertEqual(out["method"], "POST")
        self.assertEqual(out["path"], "/x")
        self.assertTrue(out["success"])
        self.assertEqual(out["data"], {"message": "ok"})
        self.assertEqual(out["internal_request_body"], {"a": 1})
        self.assertEqual(out["request_headers"], {"Accept": "*/*"})
        self.assertEqual(out["total_time_ms"], 12)

    def test_alias_keys_map_to_canonical(self):
        """CRM-style key names land on the fields write_call_log reads."""
        out = log_ingest.normalise_log_payload(
            {
                "headers": {"X": "1"},
                "body": {"cnic": "123"},
                "response": {"message": "created"},
                "client_status_code": "201",
                "response_time_ms": "412",
                "error_message": None,
            }
        )

        self.assertEqual(out["request_headers"], {"X": "1"})
        self.assertEqual(out["internal_request_body"], {"cnic": "123"})
        self.assertEqual(out["data"], {"message": "created"})
        self.assertEqual(out["status_code"], 201)
        self.assertEqual(out["total_time_ms"], 412)
        self.assertNotIn("error", out)

    def test_camel_case_keys_are_accepted(self):
        out = log_ingest.normalise_log_payload(
            {"statusCode": "503", "requestData": {"a": 1}}
        )

        self.assertEqual(out["status_code"], 503)
        self.assertEqual(out["internal_request_body"], {"a": 1})
        self.assertFalse(out["success"])
        self.assertEqual(out["status"], "FAILED")

    def test_success_is_inferred_from_status_code(self):
        self.assertFalse(
            log_ingest.normalise_log_payload({"status_code": 500})["success"]
        )
        self.assertTrue(
            log_ingest.normalise_log_payload({"status_code": 204})["success"]
        )

    def test_success_is_inferred_from_status_text(self):
        self.assertFalse(log_ingest.normalise_log_payload({"status": "FAILED"})["success"])
        self.assertTrue(log_ingest.normalise_log_payload({"status": "SUCCESS"})["success"])

    def test_explicit_success_beats_status_text(self):
        out = log_ingest.normalise_log_payload({"status": "FAILED", "success": "true"})
        self.assertTrue(out["success"])

    def test_request_id_is_generated_when_absent(self):
        out = log_ingest.normalise_log_payload({"path": "/x"})
        self.assertTrue(out["request_id"])

    def test_no_signal_defaults_to_failed(self):
        out = log_ingest.normalise_log_payload({"path": "/x"})
        self.assertFalse(out["success"])
        self.assertEqual(out["status"], "FAILED")


class EndpointResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_existing_id_wins_without_path_lookup(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_result(294))

        resolved = await log_ingest.resolve_endpoint_id(
            db, endpoint_id=294, path="/x", method="GET"
        )

        self.assertEqual(resolved, 294)
        self.assertEqual(db.execute.await_count, 1)

    async def test_unknown_explicit_id_falls_back_to_target_url_match(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_result(None), _result(277)])

        resolved = await log_ingest.resolve_endpoint_id(
            db, endpoint_id=99999, path="/v1/integration/cc/create-ticket"
        )

        self.assertEqual(resolved, 277)
        self.assertEqual(db.execute.await_count, 2)

        statement = str(db.execute.call_args_list[1].args[0])
        self.assertIn("target_api_url", statement)
        self.assertIn("is_active", statement)

    async def test_method_mismatch_retries_without_method(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_result(None), _result(275)])

        resolved = await log_ingest.resolve_endpoint_id(
            db, path="/v1/channels", method="GET"
        )

        self.assertEqual(resolved, 275)
        self.assertEqual(db.execute.await_count, 2)

    async def test_source_url_is_the_fallback_convention(self):
        """Legacy rows (CRM convention) keep the route in source_api_url."""
        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[_result(None), _result(None), _result(284)]
        )

        resolved = await log_ingest.resolve_endpoint_id(
            db, path="/getCallByDate2.php", method="GET"
        )

        self.assertEqual(resolved, 284)
        self.assertEqual(db.execute.await_count, 3)
        self.assertIn("source_api_url", str(db.execute.call_args_list[2].args[0]))

    async def test_no_path_returns_none_without_touching_the_db(self):
        db = MagicMock()
        db.execute = AsyncMock()

        resolved = await log_ingest.resolve_endpoint_id(db, path=None)

        self.assertIsNone(resolved)
        db.execute.assert_not_awaited()

    async def test_query_string_is_stripped_before_matching(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_result(None))

        await log_ingest.resolve_endpoint_id(db, path="/health?x=1", method="GET")

        statement = db.execute.call_args_list[0].args[0]
        values = list(statement.compile().params.values())
        self.assertIn("%/health", values)
        self.assertNotIn("%/health?x=1", values)

    async def test_full_url_and_trailing_slash_are_normalised(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_result(None))

        await log_ingest.resolve_endpoint_id(
            db, path="https://host:8443/v1/integration/cc/create-ticket/", method="POST"
        )

        statement = db.execute.call_args_list[0].args[0]
        values = list(statement.compile().params.values())
        self.assertIn("%/v1/integration/cc/create-ticket", values)


class TokenTests(unittest.TestCase):
    def test_open_when_no_token_is_configured(self):
        with patch.object(log_ingest.settings, "LOG_INGEST_TOKEN", None):
            self.assertTrue(log_ingest.check_ingest_token({}))

    def test_matching_header_is_accepted(self):
        with patch.object(log_ingest.settings, "LOG_INGEST_TOKEN", "s3cret"):
            self.assertTrue(
                log_ingest.check_ingest_token({"X-Log-Ingest-Token": "s3cret"})
            )

    def test_matching_bearer_is_accepted(self):
        with patch.object(log_ingest.settings, "LOG_INGEST_TOKEN", "s3cret"):
            self.assertTrue(
                log_ingest.check_ingest_token(
                    {"Authorization": "Bearer s3cret"}
                )
            )

    def test_missing_or_wrong_token_is_rejected(self):
        with patch.object(log_ingest.settings, "LOG_INGEST_TOKEN", "s3cret"):
            self.assertFalse(log_ingest.check_ingest_token({}))
            self.assertFalse(
                log_ingest.check_ingest_token({"X-Log-Ingest-Token": "wrong"})
            )


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_stores_links_and_acknowledges(self):
        db = MagicMock()
        with (
            patch.object(
                log_ingest, "write_call_log", AsyncMock(return_value=51)
            ) as write,
            patch.object(
                log_ingest, "resolve_endpoint_id", AsyncMock(return_value=277)
            ) as resolve,
            patch.object(
                log_ingest.schema_probe, "ensure", AsyncMock()
            ) as ensure,
        ):
            payload = CallLogIngestRequest(
                method="POST", path="/v1/integration/cc/create-ticket", status_code=200
            )
            response = await log_ingest.store_ingested_log(db, payload)

        self.assertTrue(response.success)
        self.assertEqual(response.log_id, 51)
        self.assertEqual(response.endpoint_id, 277)
        ensure.assert_awaited_once()
        resolve.assert_awaited_once()

        log_data = write.call_args.args[1]
        self.assertEqual(log_data["endpoint_id"], 277)
        self.assertEqual(log_data["path"], "/v1/integration/cc/create-ticket")
        self.assertTrue(log_data["success"])

    async def test_unlinked_entry_is_still_stored(self):
        db = MagicMock()
        with (
            patch.object(
                log_ingest, "write_call_log", AsyncMock(return_value=52)
            ) as write,
            patch.object(
                log_ingest, "resolve_endpoint_id", AsyncMock(return_value=None)
            ),
            patch.object(log_ingest.schema_probe, "ensure", AsyncMock()),
        ):
            payload = CallLogIngestRequest(path="/no/such/route", success=True)
            response = await log_ingest.store_ingested_log(db, payload)

        self.assertTrue(response.success)
        self.assertIsNone(response.endpoint_id)
        self.assertIsNone(write.call_args.args[1]["endpoint_id"])

    async def test_persistence_failure_is_reported(self):
        db = MagicMock()
        with (
            patch.object(
                log_ingest, "write_call_log", AsyncMock(return_value=None)
            ),
            patch.object(
                log_ingest, "resolve_endpoint_id", AsyncMock(return_value=1)
            ),
            patch.object(log_ingest.schema_probe, "ensure", AsyncMock()),
        ):
            payload = CallLogIngestRequest(path="/x", success=True)
            response = await log_ingest.store_ingested_log(db, payload)

        self.assertFalse(response.success)
        self.assertIsNone(response.log_id)
        self.assertEqual(response.endpoint_id, 1)
