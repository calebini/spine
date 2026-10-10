"""SPINE-053: local release, exact readback, migration/restore and wire isolation."""

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine import IMPLEMENTED_CONTRACT_VERSIONS, __version__
from spine.commands import CommandContext, handle
from spine.commands.cli import main
from spine.core.errors import SpineValidationError
from spine.ledger import connect
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.rendering_definitions import verify_deep
from spine.ledger.rendering_migration import install_rendering_storage
from tests import test_trusted_web_runtime as web_helpers
from tests.facet_storage_support import NOW, all_rows
from tests.test_rendering_delivery import RenderingDeliveryTests
from tests.test_schedule_operations_command import ScheduleOperationsCommandTests


class RenderingReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RenderingDeliveryTests.setUpClass()

    def setUp(self):
        self.h = RenderingDeliveryTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def show(self, event, **kwargs):
        result = handle(
            "schedule.show",
            {
                "contract_version": "spine.schedule-show.v2",
                "item_id": event["item_id"],
                "include": ["policies", "work", "attempts", "notification_profile"],
                **kwargs,
            },
            self.h.context,
        )
        self.assertTrue(result["ok"], result)
        Draft202012Validator(
            {"$ref": "https://cortext.local/spine/contracts/schemas/schedule-show-response-v2.schema.json"}, registry=self.h.registry
        ).validate(result)
        return result

    def test_v1_v2_attempts_are_stored_history_not_current_rendering(self):
        selected, grant = self.h.event()
        message = self.h.message(self.h.work(selected, start=True))
        self.h.prepare(message)
        original = self.h.fixture.event_request
        with patch.object(self.h.fixture, "event_request", side_effect=lambda *a, **kw: original(*a, **kw) | {"command_id": "plain-event"}):
            ordinary, _ = self.h.event(selected=False)
        plain = self.h.message(self.h.work(ordinary, start=True))
        self.h.prepare(plain)
        first = self.show(selected)
        v2 = first["side_effect_attempts"][0]["notification_rendering"]
        self.assertEqual(v2["rendering_contract"], "spine.notification-rendering.v2")
        self.assertIn("AC872", v2["body_text"])
        v1 = self.show(ordinary)["side_effect_attempts"][0]["notification_rendering"]
        self.assertEqual(v1["rendering_contract"], "spine.notification-rendering.v1")
        self.h.facet(selected, {"flight": "CHANGED"})
        self.h.revoke(grant)
        later = self.show(selected)
        self.assertEqual(v2, later["side_effect_attempts"][0]["notification_rendering"])
        self.assertIsNone(later["notification_profile"]["application"])
        old = handle("schedule.show", {"item_id": selected["item_id"], "include": ["attempts"]}, self.h.context)
        self.assertEqual(old["error"]["code"], "unsupported_contract_version")

    def test_profile_application_and_readback_have_exact_successor_schema(self):
        profile, _, _ = self.h.profile(pinned=False)
        request = self.h.fixture.event_request("readback-profile", materialize=False)
        request["contract_version"] = "spine.schedule-create.v3"
        request["notification_plan"] = {
            "mode": "explicit",
            "notification_profile_id": profile["notification_profile_id"],
            "revision_resolution": "exact",
            "notification_profile_revision_id": profile["notification_profile_revision_id"],
        }
        event = handle("schedule.create", request, self.h.context)
        self.assertTrue(event["ok"], event)
        result = self.show(event)
        self.assertEqual(result["notification_profile"]["application"]["application_contract"], "spine.notification-profile-application.v2")
        self.assertEqual(result["notification_policies"][0]["presentation"]["kind"], "ordinary")
        old = handle("schedule.show", {"item_id": event["item_id"], "include": ["notification_profile"]}, self.h.context)
        self.assertEqual(old["error"]["code"], "unsupported_contract_version")
        old_profile = handle(
            "notification_profile.show",
            {"contract_version": "spine.notification-profiles.v1", "notification_profile_id": profile["notification_profile_id"]},
            self.h.context,
        )
        self.assertEqual(old_profile["error"]["code"], "unsupported_contract_version")

    def cli(self, path, command, request, *flags):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request))), redirect_stdout(output):
            code = main(["--db", str(path), "--input", "-", *flags, *command.split(".")])
        return code, json.loads(output.getvalue())

    def test_frozen_web_summary_does_not_load_or_release_v2_rendering(self):
        from spine.web.read_context import read_snapshot
        from spine.web.read_contracts import ReadContracts
        from spine.web.read_sections import assemble_sections
        from spine.web.service import WebConfig

        event, _ = self.h.event()
        self.h.prepare(self.h.message(self.h.work(event, start=True)))
        helper = web_helpers.TrustedWebRuntimeTests()
        helper.db = self.h.db
        helper.provision(
            operators=[
                {"operation": "create", "subject_id": "owner", "display_name": "Owner", "activation_basis": "trusted_local_approval"}
            ]
        )
        account = self.h.db.execute("SELECT account_id FROM account_subject_bindings WHERE subject_id='owner'").fetchone()[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            target = sqlite3.connect(path)
            self.h.db.backup(target)
            target.close()
            traced = []
            with read_snapshot(WebConfig(str(path), "test-ledger"), ReadContracts(Path(__file__).parents[1] / "contracts"),
                               account, evaluated_at_utc=NOW) as snapshot:
                snapshot.db.set_trace_callback(traced.append)
                sections = assemble_sections(snapshot, event["item_id"], ["policies", "attempts", "notification_profiles"])
                output = {k: v.complete_value() for k, v in sections.items()}
            self.assertEqual(len(output["attempts"]["entries"]), 1)
            for private in ("AC872", "details_evidence", "presentation_hash", "disclosure_authorization_id"):
                self.assertNotIn(private, json.dumps(output))
            self.assertNotIn("notification_renderings", " ".join(traced).lower())

    def test_v2_readback_preserves_v1_profile_revision_without_rehashing(self):
        profile, request, _ = self.h.profile(pinned=False, key="source-for-old")
        request["contract_version"] = "spine.notification-profiles.v1"
        request["command_id"] = "old-profile"
        request["profile_key"] = "old-profile"
        for template in request["revision"]["templates"]:
            template.pop("rendering")
        old_profile = handle("notification_profile.create", request, self.h.context)
        self.assertTrue(old_profile["ok"], old_profile)
        event_request = self.h.fixture.event_request("old-profile-event", materialize=False)
        event_request["notification_plan"] = {
            "mode": "explicit",
            "revision_resolution": "exact",
            "notification_profile_id": old_profile["notification_profile_id"],
            "notification_profile_revision_id": old_profile["notification_profile_revision_id"],
        }
        event = handle("schedule.create", event_request, self.h.context)
        self.assertTrue(event["ok"], event)
        result = self.show(event)
        self.assertEqual(
            result["notification_profile"]["pinned_notification_profile_revision_id"], old_profile["notification_profile_revision_id"]
        )
        self.assertNotEqual(
            result["notification_profile"]["pinned_notification_profile_revision_id"], profile["notification_profile_revision_id"]
        )

    def test_public_cli_readback_compact_and_catalog_dry_run(self):
        event, _ = self.h.event()
        self.h.prepare(self.h.message(self.h.work(event, start=True)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            target = sqlite3.connect(path)
            self.h.db.backup(target)
            target.close()
            code, full = self.cli(path, "schedule.show", {"contract_version": "spine.schedule-show.v2", "item_id": event["item_id"]})
            self.assertEqual(code, 0, full)
            self.assertEqual(full["response_contract"], "spine.schedule-show.v2")
            code, compact = self.cli(path, "schedule.show", {"item_id": event["item_id"]}, "--compact")
            self.assertEqual(code, 0, compact)
            self.assertNotIn("AC872", json.dumps(compact))
            self.assertEqual(compact["projection_contract"], "spine.schedule-compact.v1")
            request = self.h.request(
                "notification_rendering_definition.create", owner=self.h.scope, definition_key="cli-preview", revision=self.h.revision
            )
            code, preview = self.cli(path, "notification_rendering_definition.create", request, "--dry-run")
            self.assertEqual(code, 0, preview)
            self.assertTrue(preview["dry_run"])
            check = connect(path)
            self.addCleanup(check.close)
            self.assertIsNone(
                check.execute("SELECT 1 FROM notification_rendering_definitions WHERE definition_key='cli-preview'").fetchone()
            )
            with patch.dict("os.environ", {"SPINE_RENDERING_CURSOR_CONFIG": ""}):
                code, error = self.cli(
                    path,
                    "notification_rendering_definition.list",
                    self.h.request("notification_rendering_definition.list", owner=self.h.scope, status="active", limit="1"),
                )
            self.assertNotEqual(code, 0)
            self.assertEqual(error["error"]["field"], "cursor_config")

    def test_registry_and_bounded_preflight_have_no_domain_scan(self):
        self.assertEqual(__version__, "0.9.1")
        self.assertIn("spine.notification-rendering-integration.v1", IMPLEMENTED_CONTRACT_VERSIONS)
        traced = []
        self.h.db.set_trace_callback(traced.append)
        try:
            self.assertEqual(verify_runtime_schema(self.h.db).schema_version, 19)
        finally:
            self.h.db.set_trace_callback(None)
        sql = " ".join(traced).lower()
        for prohibited in ("integrity_check", "quick_check", "foreign_key_check", "from notification_policies", "from item_facet_entries"):
            self.assertNotIn(prohibited, sql)
        before = self.h.db.total_changes
        self.show(self.h.event(selected=False, materialize=False)[0])
        # Ordinary creation is a write; subsequent readback must not be.
        before = self.h.db.total_changes
        event = {"item_id": self.h.db.execute("SELECT item_id FROM coordination_items LIMIT 1").fetchone()[0]}
        self.show(event)
        self.assertEqual(before, self.h.db.total_changes)

    def test_populated_migration_faults_and_backup_restore(self):
        for stage in ("preflight", "ddl", "backfill", "verified", "activation", None):
            with self.subTest(stage=stage):
                h = ScheduleOperationsCommandTests()
                with patch("spine.ledger.rendering_migration.install_rendering_storage"):
                    h.setUp()
                try:
                    with patch("spine.commands.core.IMPLEMENTED_LEDGER_SCHEMA_VERSION", 18):
                        event = handle(
                            "schedule.create", h.event_request("old-ledger", materialize=True), CommandContext(ledger=h.connection)
                        )
                    self.assertTrue(event["ok"], event)
                    before = all_rows(h.connection)
                    objects = [tuple(r) for r in h.connection.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY name")]
                    backup = sqlite3.connect(":memory:")
                    try:
                        h.connection.backup(backup)
                        if stage:

                            def fault(current, stage=stage):
                                if current == stage:
                                    raise RuntimeError("interrupted")

                            with self.assertRaises(RuntimeError):
                                install_rendering_storage(h.connection, applied_at_utc=NOW, fault=fault)
                            self.assertEqual(before, all_rows(h.connection))
                            self.assertEqual(
                                objects, [tuple(r) for r in h.connection.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY name")]
                            )
                            self.assertEqual(h.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                        else:
                            self.assertEqual(migrate_schema(h.connection).applied_versions, (19,))
                            self.assertEqual(verify_schema(h.connection).schema_version, 19)
                            for table, rows in before.items():
                                if table != "ledger_schema":
                                    self.assertEqual(rows, all_rows(h.connection)[table], table)
                            verify_deep(h.connection)
                            with self.assertRaises(SpineValidationError):
                                verify_runtime_schema(h.connection, expected_version=18)
                            backup.row_factory = sqlite3.Row
                            self.assertEqual(verify_runtime_schema(backup, expected_version=18).schema_version, 18)
                            self.assertEqual(migrate_schema(h.connection).applied_versions, ())
                    finally:
                        backup.close()
                finally:
                    h.tearDown()


if __name__ == "__main__":
    unittest.main()
