"""Populated candidate migration and complete existing writer regression coverage."""

import importlib
import json
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle, rendering_catalog
from spine.core.errors import SpineValidationError
from spine.ledger.rendering_definitions import verify_deep
from spine.ledger.rendering_migration import install_candidate, verify_candidate_schema
from tests import test_facet_writers as facet_writers
from tests import test_notification_commands as notifications
from tests import test_notification_policy_lineage as lineage
from tests import test_notification_profile_commands as profiles
from tests import test_openclaw_adapter as adapters
from tests import test_relative_temporal_bindings_command as bindings
from tests import test_schedule_create_command as creation
from tests import test_schedule_operations_command as operations
from tests.test_rendering_authoring_foundation import RenderingFoundationTests

ROOT = Path(__file__).parents[1]


class CandidateWriters:
    def setUp(self):
        super().setUp()
        install_candidate(self.connection, disposable_test_ledger=True)

    def tearDown(self):
        verify_deep(self.connection)
        super().tearDown()


class ExistingNotificationWriters(CandidateWriters, notifications.NotificationCommandTests):
    pass


class ExistingProfileWriters(CandidateWriters, profiles.NotificationProfileCommandTests):
    pass


class ExistingScheduleCreateWriters(CandidateWriters, creation.ScheduleCreateCommandTests):
    pass


class ExistingScheduleOperationWriters(CandidateWriters, operations.ScheduleOperationsCommandTests):
    pass


class ExistingBindingWriters(CandidateWriters, bindings.RelativeTemporalBindingCommandTests):
    pass


class RenderingStorageTests(RenderingFoundationTests):
    def test_migration_preserves_v1_profile_hashes_and_stored_attempt_bytes(self):
        profile_case = profiles.NotificationProfileCommandTests()
        profile_case.setUp()
        try:
            profile_case._create_profile()
            before = {
                t: [tuple(r) for r in profile_case.connection.execute(f"SELECT * FROM {t}")]
                for t in ("notification_profiles", "notification_profile_revisions", "notification_profile_templates", "command_receipts")
            }
            install_candidate(profile_case.connection, disposable_test_ledger=True)
            for table, rows in before.items():
                self.assertEqual(rows, [tuple(r) for r in profile_case.connection.execute(f"SELECT * FROM {table}")])
            verify_deep(profile_case.connection)
        finally:
            profile_case.tearDown()
        attempt_case = adapters.OpenClawAdapterTests()
        attempt_case.setUp()
        try:
            # This helper persists/replays a prepared attempt but invokes no
            # processor, adapter, transport, provider or real recipient.
            attempt_case.test_compatible_attempt_replay_reuses_rendering_and_suppresses_transport()
            from spine.ledger.notification_renderings import get_notification_rendering

            attempt = attempt_case.connection.execute("SELECT attempt_id FROM side_effect_attempts").fetchone()[0]
            before = get_notification_rendering(attempt_case.connection, attempt_id=attempt)
            attempts = [tuple(r) for r in attempt_case.connection.execute("SELECT * FROM side_effect_attempts")]
            install_candidate(attempt_case.connection, disposable_test_ledger=True)
            self.assertEqual(before, get_notification_rendering(attempt_case.connection, attempt_id=attempt))
            self.assertEqual(attempts, [tuple(r) for r in attempt_case.connection.execute("SELECT * FROM side_effect_attempts")])
            verify_deep(attempt_case.connection)
        finally:
            attempt_case.tearDown()

    def test_schema_manifest_and_writer_inventory_are_compiled_and_complete(self):
        verify_candidate_schema(self.db)
        inventory = json.loads((ROOT / "src/spine/ledger/rendering_writer_inventory.v1.json").read_text())
        writers = [
            str(p.relative_to(ROOT)) for p in (ROOT / "src/spine").rglob("*.py") if "insert_notification_schedule_policy(" in p.read_text()
        ]
        self.assertEqual(sorted(writers), inventory["policy_callers"])
        sql_writers = [
            str(p.relative_to(ROOT)) for p in (ROOT / "src/spine").rglob("*.py") if "INSERT INTO notification_policies" in p.read_text()
        ]
        self.assertEqual(sql_writers, ["src/spine/ledger/notifications.py"])
        with self.db.atomic_command():
            self.db.execute("CREATE INDEX noncolliding_extra_index ON notification_rendering_definitions(status)")
        verify_candidate_schema(self.db)
        with self.db.atomic_command():
            self.db.execute(
                "DROP INDEX notification_rendering_definitions_owner_kind_owner_subject_id_"
                "owner_group_id_status_notification_rendering_definition_id_idx"
            )
        with self.assertRaises(SpineValidationError):
            verify_candidate_schema(self.db)

    def test_catalog_release_fence_rejects_a_changed_snapshot(self):
        self.create()
        original = rendering_catalog.cursor_facts
        calls = 0

        def changed(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls >= 3:
                result["catalog_generation"] = str(int(result["catalog_generation"]) + 1)
            return result

        with patch.object(rendering_catalog, "cursor_facts", changed):
            result = rendering_catalog.execute(
                "notification_rendering_definition.list",
                self.request("notification_rendering_definition.list", owner=self.scope, status="active", limit="1"),
                self.context,
                cursor_config=self.config,
            )
        self.assertEqual(result["error"]["code"], "environment_failure")

    def test_populated_v1_history_preserved_and_disabled_backfilled(self):
        fixture = notifications.NotificationCommandTests()
        fixture.setUp()
        try:
            # Exercise its real multi-policy/edit/disable paths before installing
            # the candidate, preserving nonempty historical policy/receipt rows.
            fixture.test_notification_persistence_failure_rolls_back_item_version_and_policy()
            event = handle("schedule.create", self.fixture.event_request("history", materialize=False), fixture.context)
            self.assertTrue(event["ok"], event)
            intent, policy = fixture.connection.execute("SELECT notification_intent_id,policy_id FROM notification_policies").fetchone()
            disabled = handle(
                "reminder.disable",
                {
                    "command_id": "history-disable",
                    "actor_subject_id": "owner",
                    "item_id": event["item_id"],
                    "target_version": "1",
                    "notification_policy_id": policy,
                    "notification_intent_id": intent,
                    "disabled_at_utc": "2035-01-01T00:00:00Z",
                },
                fixture.context,
            )
            self.assertTrue(disabled["ok"], disabled)
            tables = ("notification_policies", "command_receipts", "audit_log", "work_instances", "notification_profile_revisions")
            before = {t: [tuple(r) for r in fixture.connection.execute(f"SELECT * FROM {t}")] for t in tables}
            install_candidate(fixture.connection, disposable_test_ledger=True)
            for table in tables:
                self.assertEqual(before[table], [tuple(r) for r in fixture.connection.execute(f"SELECT * FROM {table}")])
            self.assertEqual(
                fixture.connection.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0],
                fixture.connection.execute("SELECT COUNT(*) FROM notification_policy_presentations").fetchone()[0],
            )
            verify_candidate_schema(fixture.connection)
            verify_deep(fixture.connection)
        finally:
            fixture.tearDown()

    def test_every_item_version_producer_runs_the_shared_finalizer(self):
        for module, cls, method in facet_writers.CASES:
            with self.subTest(producer=method):
                case = getattr(importlib.import_module(f"tests.{module}"), cls)(method)
                try:
                    type(case).setUpClass()
                    case.setUp()
                    install_candidate(case.connection, disposable_test_ledger=True)
                    getattr(case, method)()
                    verify_deep(case.connection)
                finally:
                    case.tearDown()

    def test_shared_intent_exact_predecessors_survive_three_copies(self):
        case = lineage.NotificationPolicyLineageTests("test_three_facet_copy_forwards_preserve_both_siblings_and_noop_planning")
        try:
            case.setUp()
            install_candidate(case.db, disposable_test_ledger=True)
            case.test_three_facet_copy_forwards_preserve_both_siblings_and_noop_planning()
            verify_deep(case.db)
        finally:
            case.doCleanups()
