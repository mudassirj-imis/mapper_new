import unittest

from backend.schemas.log import CallLogResponse
from backend.services import audit_enrichment
from backend.services.log_writer import (
    MASK,
    _client_response,
    _headers,
    _query_params,
    redact,
)


class RedactionTests(unittest.TestCase):
    def test_required_keys_are_masked_and_kept(self):

        payload = {
            "user": "example-user",
            "pass": "example-pass",
            "password": "example-password",
            "authorization": "Bearer example-token",
            "token": "example-token-value",
            "api_key": "example-api-key",
        }
        masked = redact(payload)

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

        self.assertNotIn("resCode", body["data"])
        self.assertNotIn("status_code", body["data"])
        self.assertEqual(body["message"], "ok")
        self.assertEqual(body["data"], {"1": {"Date": "x"}})

        self.assertNotIn("error_code", body)

    def test_no_content_status_is_mirrored(self):
        body = _client_response({"success": True, "status_code": 204, "data": None})
        self.assertEqual(body["resCode"], 204)
        self.assertEqual(body["status_code"], 204)
        self.assertEqual(body["data"], {})

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

    def test_bare_payload_is_not_dropped(self):
        """An upstream with no ``data`` key still gets recorded, not blanked."""
        body = _client_response(
            {"success": True, "status_code": 200, "data": {"total": 42}}
        )
        self.assertEqual(body["data"], {"total": 42})
        self.assertEqual(body["message"], "Success")


class InternalVsExternalResponseTests(unittest.TestCase):
    UPSTREAM = {
        "data": {"1": {"Date": "2026-09-24"}},
        "message": "Records retrieved successfully.",
        "success": True,
        "error_code": 0,
    }

    def _both(self, **overrides):
        log_data = {"success": True, "status_code": 200, "data": self.UPSTREAM}
        log_data.update(overrides)
        internal = _client_response(log_data)
        external = redact(log_data.get("data") or {})
        return internal, external

    def test_passthrough_call_keeps_the_two_apart(self):
        internal, external = self._both()
        self.assertNotEqual(internal, external)

        self.assertEqual(external, self.UPSTREAM)
        self.assertIn("error_code", external)

        self.assertEqual(internal["resCode"], 200)
        self.assertEqual(internal["status_code"], 200)
        self.assertEqual(internal["data"], self.UPSTREAM["data"])

    def test_neither_field_is_null(self):
        for overrides in (
            {},
            {"data": None},
            {"success": False, "error": "boom"},
        ):
            internal, external = self._both(**overrides)
            self.assertIsNotNone(internal, overrides)
            self.assertIsNotNone(external, overrides)
            self.assertNotEqual(internal, external, overrides)

    def test_failure_envelope_reports_the_upstream_status(self):
        internal, external = self._both(
            success=False, status_code=502, error="Bad Gateway", data=None
        )
        self.assertEqual(internal["resCode"], 502)
        self.assertEqual(internal["status_code"], 502)
        self.assertIsNone(internal["data"])
        self.assertEqual(external, {})


class QueryParamCaptureTests(unittest.TestCase):
    def test_empty_and_missing_capture_stay_null(self):
        self.assertIsNone(_query_params(None))
        self.assertIsNone(_query_params({}))

    def test_scalar_values_are_stringified(self):
        self.assertEqual(
            _query_params({"page": 2, "size": 10}),
            {"page": "2", "size": "10"},
        )

    def test_repeated_params_collapse_to_one_readable_row(self):

        self.assertEqual(
            _query_params({"date": ["20260924", "20260925"]}),
            {"date": "20260924, 20260925"},
        )

    def test_credentials_in_the_query_string_are_masked(self):
        masked = _query_params({"user": "example-user", "page": "1"})
        self.assertEqual(masked["user"], MASK)
        self.assertEqual(masked["page"], "1")


class DetailPayloadContractTests(unittest.TestCase):
    REQUIRED = (
        "internal_request_headers",
        "internal_request_body",
        "external_request_headers",
        "external_query_params",
        "external_response",
        "path",
    )

    def test_audit_fields_are_all_declared(self):
        declared = set(CallLogResponse.model_fields)
        missing = [name for name in self.REQUIRED if name not in declared]
        self.assertEqual(missing, [], f"undeclared, dropped on serialise: {missing}")

    def test_values_passed_in_are_not_silently_dropped(self):
        payload = {name: {} for name in self.REQUIRED if name != "path"}
        payload["path"] = "/gateway/v1/call"
        dumped = CallLogResponse(id=1, request_id="1", **payload).model_dump()
        for name in self.REQUIRED:
            self.assertIn(name, dumped)


class AuditEnrichmentTests(unittest.TestCase):
    DOCUMENT = {
        "external_request_headers": {"accept": "*/*"},
        "external_request_body": {"user": "example-user"},
        "external_query_params": {"page": "2"},
        "external_response": {"ok": True},
        "full_log": "STEP 1 ... STEP 4",
    }

    def test_gaps_are_filled_from_the_document(self):
        merged = audit_enrichment.apply(
            {"external_query_params": None, "full_log": None},
            {"external_query_params": {"page": "2"}, "full_log": "log"},
        )
        self.assertEqual(merged["external_query_params"], {"page": "2"})
        self.assertEqual(merged["full_log"], "log")

    def test_mysql_values_are_never_overwritten(self):
        """MySQL is authoritative: a stored value must survive the merge."""
        merged = audit_enrichment.apply(
            {"external_response": {"from": "mysql"}},
            {"external_response": {"from": "mongo"}},
        )
        self.assertEqual(merged["external_response"], {"from": "mysql"})

    def test_empty_mysql_values_do_count_as_gaps(self):

        for empty in ({}, "", []):
            merged = audit_enrichment.apply(
                {"external_response": empty},
                {"external_response": {"server": "Apache"}},
            )
            self.assertEqual(merged["external_response"], {"server": "Apache"})

    def test_missing_supplement_is_a_no_op(self):
        current = {"external_response": {"kept": True}}
        self.assertEqual(audit_enrichment.apply(current, None), current)
        self.assertEqual(audit_enrichment.apply(current, {}), current)

    def test_project_masks_credentials_in_the_document(self):
        """Documents are re-redacted: pre-masking rows must not leak."""
        projected = audit_enrichment._project(
            {"internal_request_body": {"user": "example-user", "page": "1"}}
        )
        self.assertEqual(projected["internal_request_body"]["user"], MASK)
        self.assertEqual(projected["internal_request_body"]["page"], "1")

    def test_project_drops_blank_fields(self):
        projected = audit_enrichment._project(
            {
                "external_query_params": {},
                "full_log": "   ",
                "external_response": {"a": 1},
            }
        )
        self.assertNotIn("external_query_params", projected)
        self.assertNotIn("full_log", projected)
        self.assertEqual(projected["external_response"], {"a": 1})

    def test_field_map_targets_declared_response_fields(self):
        """Every mapped target must exist on the API schema, or it is dropped."""
        declared = set(CallLogResponse.model_fields)
        unknown = sorted(
            target
            for target in audit_enrichment.MONGO_FIELD_MAP.values()
            if target not in declared
        )
        self.assertEqual(unknown, [], f"mapped fields absent from schema: {unknown}")


if __name__ == "__main__":
    unittest.main()
