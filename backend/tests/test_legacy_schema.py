"""Behaviour of the audit tables on a host that cannot be migrated.

Some deployments run a MySQL account without ``ALTER`` privilege, so
``api_call_log`` never got the header columns this model maps. The log views
used to die with error 1054 on every read. These tests pin the contract that
replaced it: query and write only the columns that exist, take the detail from
MongoDB, and never let the audit store break a request.

Everything is mocked -- no database, network or secret files, matching
:mod:`test_foundations`.
"""

import asyncio
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from pydantic_settings import DotEnvSettingsSource
from sqlalchemy import select

with (
    # ``Settings`` requires the audit-store values and this module must not
    # depend on a developer's ``.env`` to find them. Nothing here connects: the
    # collection is always stubbed or the store disabled.
    patch.dict(
        os.environ,
        {
            "JWT_SECRET": "legacy-schema-test-only",
            "ENCRYPTION_KEY": "legacy-schema-test-only",
            "AUTH_BASE_URL": "https://auth.test",
            "AUDIT_MONGO_URI": "mongodb://audit-store.invalid:27017/",
            "AUDIT_MONGO_DATABASE": "audit_test_db",
            "AUDIT_MONGO_COLLECTION": "audit_test_collection",
        },
        clear=True,
    ),
    patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}),
):
    from backend.db.schema_probe import SchemaProbe, _mapped_columns
    from backend.models import ApiCallLog
    from backend.services import audit_enrichment, log_service, log_writer

#: The columns the header migration adds; a host that cannot ALTER is missing
#: exactly these.
MIGRATED = (
    "source_request_headers",
    "source_response_headers",
    "target_request_headers",
    "target_response_headers",
    "target_query_params",
    "client_status_code",
    "upstream_status_code",
)


#: Field names of a real ``mapper-engine`` audit document. The mirror written by
#: this backend must use exactly these, so one collection holds two writers
#: speaking the same language and the reader needs no special case per origin.
ENGINE_DOCUMENT_FIELDS = (
    "request_id",
    "timestamp",
    "method",
    "path",
    "status",
    "overall_status",
    "internal_request_headers",
    "internal_request_body",
    "internal_api_client_response",
    "internal_api_client_status",
    "external_request_url",
    "external_request_method",
    "external_request_headers",
    "external_request_body",
    "external_query_params",
    "external_response",
    "external_response_time_ms",
    "external_status_code",
    "total_time_ms",
    "full_log",
    "timeout_configured",
)


def _legacy_probe() -> SchemaProbe:
    """A probe that has seen a table without the migrated columns."""
    found = SchemaProbe()
    found._present = _mapped_columns() - set(MIGRATED)
    return found


def _log_row(**overrides) -> SimpleNamespace:
    """An ``(ApiCallLog, ApiEndpoint)`` pair with the columns a legacy table has.

    Absent columns are present as ``None`` because the service stamps them
    itself; a row that lacked them would raise on attribute access instead of
    proving the merge works.
    """
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


def _endpoint() -> SimpleNamespace:
    return SimpleNamespace(
        method="POST",
        source_api_url="https://source.test",
        target_api_url="https://target.test",
    )


def asyncio_run(coro):
    """Drive a coroutine to completion.

    The tests here mix plain and ``IsolatedAsyncio`` cases, and the functions
    under test are coroutines either way, so each test runs its own loop rather
    than depending on the case type it happens to live in.
    """
    return asyncio.run(coro)


def _select_with(probe: SchemaProbe):
    """The list view's own query, narrowed the way ``log_service`` narrows it."""
    return (
        select(ApiCallLog)
        .options(*probe.load_options())
    )


class AuditStoreSettingsTests(unittest.TestCase):
    """The audit store's location is deployment config, never a code default.

    A hardcoded ``localhost`` fallback is the dangerous kind: the service would
    start cleanly, connect to the wrong place (or to nothing), and the log views
    would render empty with nothing to explain why. Requiring the values turns
    that silent failure into a startup error naming the missing setting.
    """

    BASE: dict[str, str] = {
        "JWT_SECRET": "test",
        "ENCRYPTION_KEY": "test",
        "AUTH_BASE_URL": "https://auth.test",
    }
    MONGO: dict[str, str] = {
        "AUDIT_MONGO_URI": "mongodb://audit-store.invalid:27017/",
        "AUDIT_MONGO_DATABASE": "audit_test_db",
        "AUDIT_MONGO_COLLECTION": "audit_test_collection",
    }

    def _settings(self, **overrides):
        from backend.core.config import Settings

        environment = {**self.BASE, **overrides}
        with patch.dict(os.environ, environment, clear=True):
            return Settings(_env_file=None)

    def test_the_three_settings_are_read_from_the_environment(self):
        settings = self._settings(**self.MONGO)
        self.assertEqual(settings.AUDIT_MONGO_URI, self.MONGO["AUDIT_MONGO_URI"])
        self.assertEqual(settings.AUDIT_MONGO_DATABASE, "audit_test_db")
        self.assertEqual(settings.AUDIT_MONGO_COLLECTION, "audit_test_collection")

    def test_a_missing_setting_fails_loudly_rather_than_defaulting(self):
        from pydantic import ValidationError

        for omitted in self.MONGO:
            with self.subTest(omitted=omitted), self.assertRaises(
                ValidationError
            ) as caught:
                self._settings(
                    **{k: v for k, v in self.MONGO.items() if k != omitted}
                )
            # The error must name the setting, or an operator cannot act on it.
            self.assertIn(omitted, str(caught.exception))

    def test_no_mongo_host_is_baked_into_the_source(self):
        """A stray default would reappear the moment someone relaxes a test."""
        import pathlib

        import backend.core.config as config_module

        text = pathlib.Path(config_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("mongodb://", text)


class SchemaProbeTests(unittest.IsolatedAsyncioTestCase):
    def test_migrated_columns_are_all_mapped(self):
        """A renamed or dropped mapping would silently stop being detected."""
        self.assertEqual(set(MIGRATED) - _mapped_columns(), set())

    def test_uninspected_schema_is_assumed_complete(self):
        """Before the first probe, queries must be exactly what they always were."""
        probe = SchemaProbe()
        self.assertTrue(probe.complete)
        self.assertEqual(probe.missing, frozenset())
        self.assertEqual(probe.load_options(), ())

    def test_absent_columns_are_reported(self):
        probe = _legacy_probe()
        self.assertFalse(probe.complete)
        self.assertEqual(probe.missing, frozenset(MIGRATED))

    def test_absent_columns_are_omitted_from_selects(self):
        compiled = str(_select_with(_legacy_probe()))
        # The query must not name a column the server would reject.
        for column in MIGRATED:
            self.assertNotIn(f"api_call_log.{column}", compiled)

    def test_kept_columns_still_load(self):
        """Narrowing must not cost the columns the log views actually need."""
        compiled = str(_select_with(_legacy_probe()))
        for column in ("id", "endpoint_id", "status", "created_at"):
            self.assertIn(f"api_call_log.{column}", compiled)

    def test_a_complete_table_changes_nothing(self):
        compiled = str(_select_with(SchemaProbe()))
        self.assertIn("api_call_log.source_request_headers", compiled)

    def test_absent_columns_are_defaulted_on_the_row(self):
        row = ApiCallLog(id=1, status="SUCCESS")
        _legacy_probe().apply_defaults(row)
        for column in MIGRATED:
            self.assertIsNone(getattr(row, column))

    def test_defaults_never_overwrite_a_value(self):
        from sqlalchemy.orm.attributes import set_committed_value

        row = ApiCallLog(id=1, status="SUCCESS")
        set_committed_value(row, "client_status_code", 201)
        _legacy_probe().apply_defaults(row)
        self.assertEqual(row.client_status_code, 201)

    def test_present_schema_writes_every_column(self):
        values = {"status": "SUCCESS", "source_request_headers": {"a": "b"}}
        self.assertEqual(SchemaProbe().writable(values), values)

    def test_absent_columns_are_dropped_from_writes(self):
        written = _legacy_probe().writable(
            {"status": "SUCCESS", "source_request_headers": {"a": "b"}}
        )
        self.assertEqual(written, {"status": "SUCCESS"})

    async def test_introspection_failure_does_not_hide_columns(self):
        """A permissions problem must degrade to today's behaviour, not to loss."""
        probe = SchemaProbe()
        db = MagicMock()
        db.connection = AsyncMock(side_effect=RuntimeError("denied"))
        self.assertEqual(await probe.refresh(db), _mapped_columns())
        self.assertTrue(probe.complete)

    async def test_schema_is_inspected_once_per_process(self):
        probe = SchemaProbe()
        probe._present = _mapped_columns()
        db = MagicMock()
        db.connection = AsyncMock(side_effect=AssertionError("re-inspected"))
        await probe.ensure(db)  # cached: must not touch the database
        db.connection.assert_not_awaited()




class LogServiceOnLegacySchemaTests(unittest.IsolatedAsyncioTestCase):
    """The log views must serve a table that is missing the header columns."""

    def setUp(self):
        self._original = log_service.schema_probe
        log_service.schema_probe = _legacy_probe()
        self.addCleanup(self._restore)

    def _restore(self):
        log_service.schema_probe = self._original

    @staticmethod
    def _db(*results):
        db = MagicMock()
        pending = iter(results)

        async def execute(_statement):
            return next(pending)

        db.execute = AsyncMock(side_effect=execute)
        return db

    async def test_list_logs_runs_against_a_partial_table(self):
        count = Mock()
        count.scalar.return_value = 1
        page = Mock()
        page.all.return_value = [_log_row()]
        db = self._db(count, page)

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            total, items, _page, _per = await log_service.list_logs(db)

        self.assertEqual(total, 1)
        self.assertEqual([item.id for item in items], [9])

    async def test_statements_never_name_an_absent_column(self):
        count = Mock()
        count.scalar.return_value = 0
        page = Mock()
        page.all.return_value = []
        db = self._db(count, page)

        with patch.object(audit_enrichment, "enrich_rows", return_value={}):
            await log_service.list_logs(db)

        for call in db.execute.call_args_list:
            compiled = str(call.args[0])
            for column in MIGRATED:
                self.assertNotIn(f"api_call_log.{column}", compiled)

    async def test_detail_is_filled_from_mongo_when_the_column_is_absent(self):
        """The whole point: the headers still render, sourced from MongoDB."""
        result = Mock()
        result.first.return_value = _log_row()

        supplement = {
            "internal_request_headers": {"Accept": "*/*"},
            "external_request_headers": {"X-Trace": "abc"},
            "internal_api_client_status": "200",
        }
        with patch.object(
            audit_enrichment, "enrich_rows", return_value={9: supplement}
        ):
            detail = await log_service.get_log(self._db(result), 9)

        self.assertEqual(detail.internal_request_headers, {"Accept": "*/*"})
        self.assertEqual(detail.external_request_headers, {"X-Trace": "abc"})
        self.assertEqual(detail.internal_api_client_status, "200")

    async def test_mysql_value_still_wins_over_mongo(self):
        """Absent columns must not weaken MySQL's authority where it has data."""
        result = Mock()
        result.first.return_value = _log_row(
            source_request_headers={"X-From-MySQL": "yes"}
        )

        with patch.object(
            audit_enrichment,
            "enrich_rows",
            return_value={9: {"internal_request_headers": {"X-From-Mongo": "yes"}}},
        ):
            detail = await log_service.get_log(self._db(result), 9)

        self.assertEqual(detail.internal_request_headers, {"X-From-MySQL": "yes"})



class MirrorTests(unittest.IsolatedAsyncioTestCase):
    """Rows this backend writes must still have a full-detail document."""

    LOG_DATA = {
        "request_id": "0e7beac9",
        "endpoint_id": 1,
        "method": "GET",
        "path": "/getLogsByCli.php",
        "status": "SUCCESS",
        "total_time_ms": 355,
        "timeout_configured": 120,
        "success": True,
        "status_code": 200,
        "request_headers": {"Accept": "*/*", "Authorization": "Bearer example"},
        "external_request_url": "http://upstream.test/getLogsByCli.php",
        "external_request_method": "GET",
        "external_request_headers": {"X-Trace": "abc"},
        "external_query_params": {"page": "2"},
        "external_request_body": {},
        "data": {"ok": True},
        "external_status_code": 201,
        "external_response_time_ms": 42,
    }

    def _mirrored(self, log_id=11, log_data=None):
        """Mirror one call into a stub collection; return the document."""
        collection = Mock()
        with patch.object(
            audit_enrichment, "_collection", return_value=collection
        ), patch.object(audit_enrichment.settings, "AUDIT_MONGO_MIRROR", True):
            written = asyncio_run(
                audit_enrichment.mirror_call(log_id, log_data or self.LOG_DATA)
            )
        self.assertTrue(written)
        return collection.insert_one.call_args.args[0]

    def test_mirroring_is_off_for_a_complete_schema(self):
        with patch.object(
            audit_enrichment.schema_probe, "_present", _mapped_columns()
        ):
            self.assertFalse(audit_enrichment.should_mirror())

    def test_mirroring_is_on_when_a_column_is_absent(self):
        with patch.object(
            audit_enrichment.schema_probe,
            "_present",
            _mapped_columns() - set(MIGRATED),
        ):
            self.assertTrue(audit_enrichment.should_mirror())

    def test_mirroring_respects_an_explicit_setting(self):
        with patch.object(
            audit_enrichment.schema_probe, "_present", _mapped_columns()
        ), patch.object(audit_enrichment.settings, "AUDIT_MONGO_MIRROR", True):
            self.assertTrue(audit_enrichment.should_mirror())

    def test_mirroring_stops_when_mongo_is_disabled(self):
        with patch.object(audit_enrichment.settings, "AUDIT_MONGO_ENABLED", False):
            self.assertFalse(audit_enrichment.should_mirror())

    def test_mirrored_document_is_paired_by_its_own_id(self):
        document = self._mirrored()
        self.assertEqual(document["log_id"], 11)
        self.assertIn("timestamp", document)

    def test_mirrored_document_carries_the_detail_the_row_cannot(self):
        document = self._mirrored()
        self.assertEqual(document["internal_request_headers"]["Accept"], "*/*")
        self.assertEqual(document["external_query_params"], {"page": "2"})
        self.assertEqual(document["external_status_code"], 201)
        self.assertEqual(document["internal_api_client_status"], 200)

    def test_mirrored_document_masks_credentials(self):
        document = self._mirrored(
            log_data={**self.LOG_DATA, "external_request_body": {"user": "example-user"}}
        )
        self.assertEqual(
            document["internal_request_headers"]["Authorization"], "********"
        )
        self.assertEqual(document["external_request_body"]["user"], "********")

    def test_mirror_failure_never_breaks_the_write(self):
        with patch.object(
            audit_enrichment, "_collection", return_value=None
        ), patch.object(audit_enrichment.settings, "AUDIT_MONGO_MIRROR", True):
            self.assertFalse(asyncio_run(audit_enrichment.mirror_call(11, self.LOG_DATA)))

    def test_mirrored_document_uses_the_engine_field_names(self):
        """Both writers must produce the same shape in a shared collection.

        Field names are copied from a real ``mapper-engine`` document. A rename
        here would leave this backend's documents unreadable by the same
        ``_project`` that reads the engine's, silently emptying the detail view.
        """
        document = self._mirrored()
        for field in ENGINE_DOCUMENT_FIELDS:
            self.assertIn(field, document, f"missing engine field: {field}")

    def test_mirrored_document_adds_only_log_id(self):
        """The one field we add is ``log_id``; nothing else may drift."""
        document = self._mirrored()
        self.assertEqual(
            set(document) - set(ENGINE_DOCUMENT_FIELDS) - {"_id"}, {"log_id"}
        )

    def test_mirrored_document_carries_the_envelope_fields(self):
        document = self._mirrored()
        self.assertEqual(document["method"], self.LOG_DATA["method"])
        self.assertEqual(document["path"], self.LOG_DATA["path"])
        self.assertEqual(document["request_id"], self.LOG_DATA["request_id"])
        self.assertTrue(document["overall_status"])

    def test_an_empty_request_body_is_still_recorded(self):
        """``{}`` means "this call had no body", which is worth keeping.

        The engine writes it, and the detail view distinguishes it from a body
        that was never captured.
        """
        document = self._mirrored()
        self.assertEqual(document["external_request_body"], {})

    def test_an_uncaptured_header_block_is_left_out(self):
        """No headers is "not captured", so the key is absent rather than ``{}``.

        The opposite of the body rule: a header block we never received must not
        be rendered as "the client sent no headers".
        """
        document = self._mirrored(
            log_data={**self.LOG_DATA, "external_request_headers": None}
        )
        self.assertNotIn("external_request_headers", document)

    def test_no_document_without_a_row_id(self):
        collection = Mock()
        with patch.object(
            audit_enrichment, "_collection", return_value=collection
        ), patch.object(audit_enrichment.settings, "AUDIT_MONGO_MIRROR", True):
            self.assertFalse(asyncio_run(audit_enrichment.mirror_call(None, self.LOG_DATA)))
        collection.insert_one.assert_not_called()

    @staticmethod
    def _write_db() -> MagicMock:
        """A session whose ``execute`` reports an inserted primary key."""
        db = MagicMock()
        result = Mock()
        result.inserted_primary_key = (11,)
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @staticmethod
    def _inserted_sql(db: MagicMock) -> str:
        """The INSERT ``write_call_log`` issued."""
        return str(db.execute.call_args_list[0].args[0])

    def test_written_row_omits_absent_columns(self):
        """The INSERT itself must not name a column the server does not have."""
        db = self._write_db()
        with patch.object(log_writer, "schema_probe", _legacy_probe()), patch.object(
            audit_enrichment, "mirror_call", AsyncMock(return_value=False)
        ):
            asyncio_run(log_writer.write_call_log(db, self.LOG_DATA))

        named = self._inserted_sql(db)
        for column in MIGRATED:
            self.assertNotIn(column, named)
        self.assertIn("status", named)

    def test_a_complete_table_still_records_headers_in_mysql(self):
        """The fix must not cost a migrated deployment its MySQL detail."""
        db = self._write_db()
        collection = Mock()
        with patch.object(log_writer, "schema_probe", SchemaProbe()), patch.object(
            audit_enrichment.schema_probe, "_present", _mapped_columns()
        ), patch.object(
            audit_enrichment, "_collection", return_value=collection
        ):
            asyncio_run(log_writer.write_call_log(db, self.LOG_DATA))

        statement = db.execute.call_args_list[0].args[0]
        self.assertIn("source_request_headers", self._inserted_sql(db))
        # The values are what the detail view later reads back out of MySQL.
        params = statement.compile().params
        self.assertEqual(params["source_request_headers"]["Accept"], "*/*")
        self.assertEqual(params["target_query_params"], {"page": "2"})
        # Nothing to mirror: MySQL already holds the whole detail.
        collection.insert_one.assert_not_called()

    def test_a_legacy_table_mirrors_what_it_cannot_store(self):
        """The compensating write: headers live in MongoDB instead."""
        db = self._write_db()
        collection = Mock()
        with patch.object(log_writer, "schema_probe", _legacy_probe()), patch.object(
            audit_enrichment.schema_probe,
            "_present",
            _mapped_columns() - set(MIGRATED),
        ), patch.object(
            audit_enrichment, "_collection", return_value=collection
        ):
            asyncio_run(log_writer.write_call_log(db, self.LOG_DATA))

        collection.insert_one.assert_called_once()
        document = collection.insert_one.call_args.args[0]
        self.assertEqual(document["log_id"], 11)
        self.assertEqual(document["internal_request_headers"]["Accept"], "*/*")


class AuditStoreOutageTests(unittest.IsolatedAsyncioTestCase):
    """The audit store is a supplement; losing it must never fail a read."""

    async def test_detail_view_survives_a_broken_audit_store(self):
        result = Mock()
        result.first.return_value = _log_row()
        db = MagicMock()

        async def execute(_statement):
            return result

        db.execute = AsyncMock(side_effect=execute)

        with patch.object(
            audit_enrichment, "enrich_rows", side_effect=RuntimeError("mongo down")
        ):
            detail = await log_service.get_log(db, 9)

        self.assertEqual(detail.id, 9)
        self.assertIsNone(detail.internal_request_headers)



if __name__ == "__main__":  # pragma: no cover
    unittest.main()
