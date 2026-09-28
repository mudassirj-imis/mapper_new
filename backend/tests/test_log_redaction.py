"""Audit-log redaction and header-capture contract.

Guards the three guarantees the log output depends on:

* request headers are captured, never left null;
* credential values are masked everywhere they appear, on write *and* on read;
* ``resCode``/``status_code`` sit beside ``data``, never inside it.

Every fixture below uses obviously-fake placeholder values. Real credentials
must never appear in a test, not even as the input being masked -- the
repository keeps history, so a "harmless" fixture is a permanent secret.
"""

import unittest

from backend.services.log_writer import MASK, _client_response, _headers, redact


class RedactionTests(unittest.TestCase):
    def test_required_keys_are_masked_and_kept(self):
        # Placeholder values only. Real credentials must never be committed
        # here, not even as fixtures -- a test asserting that they get masked
        # still puts them in git history forever.
        payload = {
            "user": "example-user",
            "pass": "example-pass",
            "password": "example-password",
            "authorization": "Bearer example-token",
            "token": "example-token-value",
            "api_key": "example-api-key",
        }
        masked = redact(payload)
        # Keys survive so consumers still see *that* a credential was sent.
        self.assertEqual(set(masked), set(payload))
        for value in masked.values():
            self.assertEqual(value, MASK)

    def test_matching_is_case_and_format_insensitive(self):
        masked = redact({"User": "u", "PASS": "p", "X-Api-Key": "k", "API_KEY": "a"})
        self.assertEqual(set(masked.values()), {MASK})

    def test_nested_structures_are_walked(self):
        masked = redact({"a": {"password": "x", "ok": "fine"}, "l": [{"token": "t"}]})
        self.assertEqual(masked["a"]["password"], MASK)
        self.assertEqual(masked["a"]["ok"], "fine")
        self.assertEqual(masked["l"][0]["token"], MASK)

    def test_business_data_is_untouched(self):
        payload = {"Msisdn": "03033789086", "Date": "2026-09-24", "path": "/r/x.wav"}
        self.assertEqual(redact(payload), payload)

    def test_credential_shaped_values_are_masked_even_under_other_keys(self):
        masked = redact({"X-Custom": "Bearer abcdef123", "note": "eyJhbG.eyJzdWI.sig"})
        self.assertEqual(masked["X-Custom"], MASK)
        self.assertEqual(masked["note"], MASK)

    def test_headers_helper_normalises_and_redacts(self):
        self.assertIsNone(_headers(None))
        self.assertIsNone(_headers({}))
        self.assertEqual(
            _headers({"Accept": "*/*", "Authorization": "Bearer s3cret"}),
            {"Accept": "*/*", "Authorization": MASK},
        )

    def test_masks_every_value_it_is_given(self):
        """A value that survives masking means the key was missed."""
        payload = {
            "user": "example-user",
            "pass": "example-pass",
            "nested": {"api_key": "example-key"},
        }
        masked = redact(payload)
        self.assertEqual(masked["user"], MASK)
        self.assertEqual(masked["pass"], MASK)
        self.assertEqual(masked["nested"]["api_key"], MASK)


class ClientResponseTests(unittest.TestCase):
    def test_rescode_and_status_sit_beside_data(self):
        body = _client_response(
            {
                "success": True,
                "status_code": 200,
                "data": {
                    "data": {"1": {"Date": "x"}},
                    "message": "ok",
                    "success": True,
                    "error_code": 0,
                },
            }
        )
        self.assertEqual(body["resCode"], 200)
        self.assertEqual(body["status_code"], 200)
        # The upstream envelope is passed through untouched, and neither status
        # key is nested inside the payload it carries.
        self.assertNotIn("resCode", body["data"])
        self.assertNotIn("status_code", body["data"])
        self.assertEqual(body["message"], "ok")
        self.assertEqual(body["error_code"], 0)
        self.assertEqual(body["data"], {"1": {"Date": "x"}})

    def test_no_content_status_is_mirrored(self):
        body = _client_response({"success": True, "status_code": 204, "data": None})
        self.assertEqual(body["resCode"], 204)
        self.assertEqual(body["status_code"], 204)
        self.assertIsNone(body["data"])

    def test_upstream_cannot_shadow_the_status_keys(self):
        body = _client_response(
            {
                "success": True,
                "status_code": 502,
                "data": {"resCode": 999, "status_code": 999},
            }
        )
        self.assertEqual(body["resCode"], 502)
        self.assertEqual(body["status_code"], 502)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()