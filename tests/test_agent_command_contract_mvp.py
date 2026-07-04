import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from spine.commands import CommandContext, handle
from spine.commands.cli import _generated_command_id, main as cli_main
from spine.core.hashing import hash_canonical_json
from spine.ledger import connect, initialize_schema

MVP_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "command_responses" / "mvp"
CONTRACT_MANIFEST = Path(__file__).parents[1] / "contracts" / "command-fixture-manifest.json"
COMMAND_RESPONSE_SCHEMA = Path(__file__).parents[1] / "contracts" / "schemas" / "command-response.schema.json"


OPENCLAW = {"openclaw": {"binding_name": "openclaw", "channel": "whatsapp", "configured": True}}


class AgentCommandContractMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self.bootstrap_subject("agent")

    def tearDown(self) -> None:
        self.connection.close()

    def test_all_mvp_commands_dispatch_without_unsupported_command(self) -> None:
        commands = [
            "subject.upsert",
            "item.show",
            "item.list",
            "item.archive",
            "event.create",
            "event.update",
            "event.reschedule",
            "event.cancel",
            "task.create",
            "task.update",
            "task.complete",
            "task.cancel",
            "relation.create",
            "relation.list",
            "reminder.create",
        ]

        for command in commands:
            with self.subTest(command=command):
                response = handle(command, {}, self.context)
                self.assertNotEqual(response.get("error", {}).get("code"), "unsupported_command")

    def test_item_list_rejects_status_with_include_archived(self) -> None:
        response = handle("item.list", {"status": "active", "include_archived": False}, self.context)

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertEqual(response["error"]["field"], "include_archived")

        archived_only = handle("item.list", {"status": "archived"}, self.context)
        invalid_item_type = handle("item.list", {"item_type": "note"}, self.context)
        invalid_status = handle("item.list", {"status": "done"}, self.context)

        self.assertTrue(archived_only["ok"])
        self.assertEqual(invalid_item_type["error"]["code"], "unsupported_field")
        self.assertEqual(invalid_item_type["error"]["field"], "item_type")
        self.assertEqual(invalid_status["error"]["code"], "unsupported_field")
        self.assertEqual(invalid_status["error"]["field"], "status")

    def test_create_supporting_set_inputs_are_deferred_unsupported_fields(self) -> None:
        event_response = handle(
            "event.create",
            {**event_request("cmd-deferred-supporting-event"), "locations": []},
            self.context,
        )
        task_response = handle(
            "task.create",
            {**task_request("cmd-deferred-supporting-task"), "subject_roles": []},
            self.context,
        )

        self.assertFalse(event_response["ok"])
        self.assertEqual(event_response["error"]["code"], "unsupported_field")
        self.assertEqual(event_response["error"]["field"], "locations")
        self.assertFalse(task_response["ok"])
        self.assertEqual(task_response["error"]["code"], "unsupported_field")
        self.assertEqual(task_response["error"]["field"], "subject_roles")

    def test_missing_required_field_uses_public_error_code(self) -> None:
        response = handle("event.create", {key: value for key, value in event_request("cmd-missing-field").items() if key != "command_id"}, self.context)

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "missing_required_field")
        self.assertEqual(response["error"]["field"], "command_id")

    def test_update_patch_is_required(self) -> None:
        event = handle("event.create", event_request("cmd-missing-patch-event"), self.context)
        response = handle(
            "event.update",
            {
                "command_id": "cmd-missing-patch-update",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 1,
                "updated_at_utc": "2026-06-06T10:10:00Z",
            },
            self.context,
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "missing_required_field")
        self.assertEqual(response["error"]["field"], "patch")

    def test_temporal_anchor_kind_shape_validation(self) -> None:
        cases = [
            ("instant_utc_missing", {"anchor_kind": "instant_utc"}, "missing_required_field", "start_anchor.utc_instant"),
            (
                "instant_utc_forbidden",
                {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T12:00:00Z", "local_date": "2026-06-06"},
                "unsupported_field",
                "start_anchor.local_date",
            ),
            (
                "local_instant_missing",
                {"anchor_kind": "local_instant", "local_date": "2026-06-06", "timezone": "Europe/Paris"},
                "missing_required_field",
                "start_anchor.local_time",
            ),
            (
                "local_instant_forbidden",
                {
                    "anchor_kind": "local_instant",
                    "local_date": "2026-06-06",
                    "local_time": "09:00",
                    "timezone": "Europe/Paris",
                    "utc_instant": "2026-06-06T07:00:00Z",
                },
                "unsupported_field",
                "start_anchor.utc_instant",
            ),
            ("local_date_missing", {"anchor_kind": "local_date", "local_date": "2026-06-06"}, "missing_required_field", "start_anchor.timezone"),
            (
                "local_date_forbidden",
                {"anchor_kind": "local_date", "local_date": "2026-06-06", "timezone": "Europe/Paris", "local_time": "09:00"},
                "unsupported_field",
                "start_anchor.local_time",
            ),
            ("utc_window_missing", {"anchor_kind": "utc_window", "window_start_utc": "2026-06-06T07:00:00Z"}, "missing_required_field", "start_anchor.window_end_utc"),
            (
                "utc_window_forbidden",
                {
                    "anchor_kind": "utc_window",
                    "window_start_utc": "2026-06-06T07:00:00Z",
                    "window_end_utc": "2026-06-06T08:00:00Z",
                    "timezone": "Europe/Paris",
                },
                "unsupported_field",
                "start_anchor.timezone",
            ),
            ("local_window_missing", {"anchor_kind": "local_window", "local_date": "2026-06-06"}, "missing_required_field", "start_anchor.timezone"),
            (
                "local_window_forbidden",
                {"anchor_kind": "local_window", "local_date": "2026-06-06", "timezone": "Europe/Paris", "utc_instant": "2026-06-06T07:00:00Z"},
                "unsupported_field",
                "start_anchor.utc_instant",
            ),
        ]

        for name, anchor, code, field in cases:
            with self.subTest(name=name):
                response = handle(
                    "event.create",
                    {**event_request(f"cmd-anchor-{name}"), "start_anchor": anchor},
                    self.context,
                )
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], code)
                self.assertEqual(response["error"]["field"], field)

    def test_subject_upsert_receipt_replay_conflict_and_cross_command_reuse(self) -> None:
        request = {
            "command_id": "cmd-subject-2",
            "actor_subject_id": "agent",
            "subject_id": "person-1",
            "subject_kind": "person",
            "display_name": "Person One",
            "status": "active",
            "updated_at_utc": "2026-06-06T10:05:00Z",
        }

        created = handle("subject.upsert", request, self.context)
        replay = handle("subject.upsert", request, self.context)
        incompatible = handle("subject.upsert", {**request, "display_name": "Changed"}, self.context)
        cross = handle("event.create", {**event_request("cmd-subject-2"), "title": "Other"}, self.context)

        self.assertTrue(created["created"])
        self.assertFalse(replay["created"])
        self.assertEqual(replay["command_receipt_id"], created["command_receipt_id"])
        self.assertEqual(incompatible["error"]["code"], "semantic_conflict")
        self.assertEqual(cross["error"]["code"], "semantic_conflict")

    def test_event_and_task_create_show_list_update_and_replay(self) -> None:
        event = handle("event.create", event_request("cmd-event-create"), self.context)
        task = handle("task.create", task_request("cmd-task-create"), self.context)
        shown = handle("item.show", {"item_id": event["item_id"]}, self.context)
        listed = handle("item.list", {"item_type": "event"}, self.context)
        update_request = {
            "command_id": "cmd-event-update",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T10:10:00Z",
            "patch": {"summary": "Bring forms"},
        }
        updated = handle("event.update", update_request, self.context)
        replay = handle("event.update", update_request, self.context)
        stale = handle("event.update", {**update_request, "command_id": "cmd-event-stale"}, self.context)
        wrong_type = handle(
            "task.update",
            {
                "command_id": "cmd-task-wrong-type",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 2,
                "updated_at_utc": "2026-06-06T10:11:00Z",
                "patch": {"title": "Wrong"},
            },
            self.context,
        )

        self.assertTrue(event["created"])
        self.assertTrue(task["created"])
        self.assertIn("start_anchor", shown["event_detail"])
        self.assertEqual(listed["items"][0]["item_id"], event["item_id"])
        self.assertTrue(updated["updated"])
        self.assertFalse(replay["updated"])
        self.assertEqual(stale["error"]["code"], "stale_version")
        self.assertEqual(wrong_type["error"]["code"], "wrong_item_type")

    def test_item_show_missing_referenced_anchor_reports_anchor_field(self) -> None:
        event = handle("event.create", event_request("cmd-missing-anchor-event"), self.context)
        self.connection.execute("PRAGMA foreign_keys=OFF")
        self.connection.execute(
            "UPDATE event_details SET start_anchor_id = ? WHERE item_id = ? AND version = ?",
            ("anchor_missing_for_test", event["item_id"], 1),
        )
        response = handle("item.show", {"item_id": event["item_id"]}, self.context)
        self.connection.execute("PRAGMA foreign_keys=ON")

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "referenced_row_not_found")
        self.assertEqual(response["error"]["field"], "start_anchor_id")

    def test_update_replay_returns_stored_result_after_later_mutation(self) -> None:
        event = handle("event.create", event_request("cmd-replay-history-event"), self.context)
        update_request = {
            "command_id": "cmd-replay-history-update",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T10:10:00Z",
            "patch": {"title": "Replay history title"},
        }
        updated = handle("event.update", update_request, self.context)
        rescheduled = handle(
            "event.reschedule",
            {
                "command_id": "cmd-replay-history-reschedule",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 2,
                "rescheduled_at_utc": "2026-06-06T10:20:00Z",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T13:00:00Z"},
            },
            self.context,
        )
        replay = handle("event.update", update_request, self.context)

        self.assertTrue(updated["updated"])
        self.assertTrue(rescheduled["rescheduled"])
        self.assertFalse(replay["updated"])
        self.assertEqual(replay["version"], "2")
        self.assertEqual(replay["current_version"], "2")
        self.assertEqual(replay["current_common"]["version"], "2")
        self.assertEqual(replay["event_detail"]["start_anchor"]["utc_instant"], "2026-06-06T12:00:00Z")

    def test_event_reschedule_and_lifecycle_archive_immutability(self) -> None:
        event = handle("event.create", event_request("cmd-event-lifecycle"), self.context)
        rescheduled = handle(
            "event.reschedule",
            {
                "command_id": "cmd-event-reschedule",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 1,
                "rescheduled_at_utc": "2026-06-06T11:00:00Z",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T13:00:00Z"},
            },
            self.context,
        )
        cancelled = handle(
            "event.cancel",
            {
                "command_id": "cmd-event-cancel",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 2,
                "cancelled_at_utc": "2026-06-06T12:00:00Z",
            },
            self.context,
        )
        cancelled_reschedule = handle(
            "event.reschedule",
            {
                "command_id": "cmd-event-reschedule-cancelled",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 3,
                "rescheduled_at_utc": "2026-06-06T12:30:00Z",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T14:00:00Z"},
            },
            self.context,
        )
        archive = handle(
            "item.archive",
            {
                "command_id": "cmd-archive",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 3,
                "archived_at_utc": "2026-06-06T13:00:00Z",
            },
            self.context,
        )
        post_archive = handle(
            "event.update",
            {
                "command_id": "cmd-post-archive",
                "actor_subject_id": "agent",
                "item_id": event["item_id"],
                "target_version": 3,
                "updated_at_utc": "2026-06-06T14:00:00Z",
                "patch": {"title": "Nope"},
            },
            self.context,
        )

        self.assertTrue(rescheduled["rescheduled"])
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(cancelled_reschedule["error"]["code"], "invalid_state_transition")
        self.assertEqual(cancelled_reschedule["error"]["field"], "event_status")
        self.assertTrue(archive["archived"])
        self.assertEqual(archive["version"], archive["current_version"])
        self.assertEqual(post_archive["error"]["code"], "invalid_state_transition")

    def test_task_complete_cancel_duplicate_and_dry_run_no_persistence(self) -> None:
        task = handle("task.create", task_request("cmd-task-dry"), self.context)
        dry_run = handle(
            "task.update",
            {
                "command_id": "cmd-task-dry-update",
                "actor_subject_id": "agent",
                "item_id": task["item_id"],
                "target_version": 1,
                "updated_at_utc": "2026-06-06T10:20:00Z",
                "patch": {"title": "Previewed"},
            },
            CommandContext(ledger=self.connection, dry_run=True),
        )
        unchanged = handle("item.show", {"item_id": task["item_id"]}, self.context)
        completed = handle(
            "task.complete",
            {
                "command_id": "cmd-task-complete",
                "actor_subject_id": "agent",
                "item_id": task["item_id"],
                "target_version": 1,
                "completed_at_utc": "2026-06-06T10:25:00Z",
            },
            self.context,
        )
        duplicate = handle(
            "task.cancel",
            {
                "command_id": "cmd-task-cancel-terminal",
                "actor_subject_id": "agent",
                "item_id": task["item_id"],
                "target_version": 1,
                "cancelled_at_utc": "2026-06-06T10:30:00Z",
            },
            self.context,
        )

        self.assertTrue(dry_run["dry_run"])
        self.assertTrue(dry_run["updated"])
        self.assertEqual(unchanged["current_common"]["title"], "File paperwork")
        self.assertTrue(completed["completed"])
        self.assertEqual(duplicate["error"]["code"], "invalid_state_transition")

    def test_dry_run_failure_is_structured_and_persists_nothing(self) -> None:
        before_receipts = self.connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]

        response = handle(
            "event.create",
            {
                "command_id": "cmd-dry-run-invalid",
                "actor_subject_id": "agent",
                "created_at_utc": "2026-06-06T10:01:00Z",
                "title": "Invalid dry run",
                "all_day": False,
            },
            CommandContext(ledger=self.connection, dry_run=True),
        )
        after_receipts = self.connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]

        self.assertFalse(response["ok"])
        self.assertTrue(response["dry_run"])
        self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertEqual(before_receipts, after_receipts)

    def test_item_show_nested_limits_and_relation_direction_validation(self) -> None:
        event = handle("event.create", event_request("cmd-limit-event"), self.context)
        task = handle("task.create", task_request("cmd-limit-task"), self.context)
        relation_request = {
            "command_id": "cmd-limit-relation",
            "actor_subject_id": "agent",
            "source_item_id": task["item_id"],
            "source_target_version": 1,
            "target_item_id": event["item_id"],
            "target_target_version": 1,
            "relation_type": "depends_on",
            "created_at_utc": "2026-06-06T10:40:00Z",
        }
        handle("relation.create", relation_request, self.context)

        shown = handle(
            "item.show",
            {"item_id": event["item_id"], "include_relations": True, "relations_limit": 0},
            self.context,
        )
        invalid = handle(
            "relation.list",
            {"source_item_id": task["item_id"], "direction": "source", "bounded": True},
            self.context,
        )

        self.assertEqual(shown["relations"], [])
        self.assertEqual(shown["relations_limit"], "0")
        self.assertTrue(shown["relations_truncated"])
        self.assertEqual(invalid["error"]["code"], "invalid_request")
        self.assertEqual(invalid["error"]["field"], "direction")

    def test_successful_writes_create_exactly_one_receipt_per_command(self) -> None:
        writes: list[tuple[str, dict[str, object], CommandContext]] = [
            (
                "subject.upsert",
                {
                    "command_id": "cmd-receipt-subject",
                    "actor_subject_id": "agent",
                    "subject_id": "receipt-person",
                    "subject_kind": "person",
                    "display_name": "Receipt Person",
                    "status": "active",
                    "updated_at_utc": "2026-06-06T10:01:00Z",
                },
                self.context,
            ),
            ("event.create", event_request("cmd-receipt-event"), self.context),
            ("task.create", task_request("cmd-receipt-task"), self.context),
        ]
        event = handle("event.create", event_request("cmd-receipt-event-target"), self.context)
        task = handle("task.create", task_request("cmd-receipt-task-target"), self.context)
        writes.extend(
            [
                (
                    "event.update",
                    {
                        "command_id": "cmd-receipt-event-update",
                        "actor_subject_id": "agent",
                        "item_id": event["item_id"],
                        "target_version": 1,
                        "updated_at_utc": "2026-06-06T10:10:00Z",
                        "patch": {"summary": "Receipt"},
                    },
                    self.context,
                ),
                (
                    "task.update",
                    {
                        "command_id": "cmd-receipt-task-update",
                        "actor_subject_id": "agent",
                        "item_id": task["item_id"],
                        "target_version": 1,
                        "updated_at_utc": "2026-06-06T10:11:00Z",
                        "patch": {"summary": "Receipt"},
                    },
                    self.context,
                ),
                (
                    "event.reschedule",
                    {
                        "command_id": "cmd-receipt-event-reschedule",
                        "actor_subject_id": "agent",
                        "item_id": event["item_id"],
                        "target_version": 2,
                        "rescheduled_at_utc": "2026-06-06T10:12:00Z",
                        "all_day": False,
                        "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T13:00:00Z"},
                    },
                    self.context,
                ),
                (
                    "event.cancel",
                    {
                        "command_id": "cmd-receipt-event-cancel",
                        "actor_subject_id": "agent",
                        "item_id": event["item_id"],
                        "target_version": 3,
                        "cancelled_at_utc": "2026-06-06T10:13:00Z",
                    },
                    self.context,
                ),
                (
                    "task.complete",
                    {
                        "command_id": "cmd-receipt-task-complete",
                        "actor_subject_id": "agent",
                        "item_id": task["item_id"],
                        "target_version": 2,
                        "completed_at_utc": "2026-06-06T10:14:00Z",
                    },
                    self.context,
                ),
            ]
        )
        task_for_cancel = handle("task.create", task_request("cmd-receipt-task-cancel-target"), self.context)
        relation_source = handle("task.create", task_request("cmd-receipt-relation-source"), self.context)
        relation_target = handle("event.create", event_request("cmd-receipt-relation-target"), self.context)
        reminder_target = handle("task.create", task_request("cmd-receipt-reminder-target"), self.context)
        self.bootstrap_subject("receipt-recipient")
        writes.extend(
            [
                (
                    "task.cancel",
                    {
                        "command_id": "cmd-receipt-task-cancel",
                        "actor_subject_id": "agent",
                        "item_id": task_for_cancel["item_id"],
                        "target_version": 1,
                        "cancelled_at_utc": "2026-06-06T10:15:00Z",
                    },
                    self.context,
                ),
                (
                    "item.archive",
                    {
                        "command_id": "cmd-receipt-archive",
                        "actor_subject_id": "agent",
                        "item_id": relation_target["item_id"],
                        "target_version": 1,
                        "archived_at_utc": "2026-06-06T10:16:00Z",
                    },
                    self.context,
                ),
                (
                    "relation.create",
                    {
                        "command_id": "cmd-receipt-relation",
                        "actor_subject_id": "agent",
                        "source_item_id": relation_source["item_id"],
                        "source_target_version": 1,
                        "target_item_id": task_for_cancel["item_id"],
                        "target_target_version": 2,
                        "relation_type": "depends_on",
                        "created_at_utc": "2026-06-06T10:17:00Z",
                    },
                    self.context,
                ),
                (
                    "reminder.create",
                    {
                        "command_id": "cmd-receipt-reminder",
                        "actor_subject_id": "agent",
                        "item_id": reminder_target["item_id"],
                        "target_version": 1,
                        "created_at_utc": "2026-06-06T10:18:00Z",
                        "work_subject_ref": "receipt-recipient",
                        "channel": "whatsapp",
                        "eligible_at_utc": "2026-06-06T11:18:00Z",
                    },
                    CommandContext(ledger=self.connection, adapter_bindings=OPENCLAW),
                ),
            ]
        )

        for command, request, context in writes:
            with self.subTest(command=command):
                response = handle(command, request, context)
                self.assertTrue(response["ok"], response)
                count = self.connection.execute(
                    "SELECT COUNT(*) FROM command_receipts WHERE command_id = ?",
                    (request["command_id"],),
                ).fetchone()[0]
                self.assertEqual(count, 1)

    def test_noop_update_creates_receipt_without_new_version(self) -> None:
        task = handle("task.create", task_request("cmd-noop-task"), self.context)

        response = handle(
            "task.update",
            {
                "command_id": "cmd-noop-task-update",
                "actor_subject_id": "agent",
                "item_id": task["item_id"],
                "target_version": 1,
                "updated_at_utc": "2026-06-06T10:20:00Z",
                "patch": {"title": "File paperwork"},
            },
            self.context,
        )
        receipt_count = self.connection.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE command_id = 'cmd-noop-task-update'"
        ).fetchone()[0]
        version_count = self.connection.execute(
            "SELECT COUNT(*) FROM coordination_item_versions WHERE item_id = ?",
            (task["item_id"],),
        ).fetchone()[0]

        self.assertTrue(response["ok"])
        self.assertFalse(response["updated"])
        self.assertEqual(receipt_count, 1)
        self.assertEqual(version_count, 1)

    def test_relation_create_list_alias_and_duplicate_conflict(self) -> None:
        event = handle("event.create", event_request("cmd-relation-event"), self.context)
        task = handle("task.create", task_request("cmd-relation-task"), self.context)
        request = {
            "command_id": "cmd-relation-create",
            "actor_subject_id": "agent",
            "source_item_id": task["item_id"],
            "source_target_version": 1,
            "target_item_id": event["item_id"],
            "target_target_version": 1,
            "relation_type": "depends_on",
            "created_at_utc": "2026-06-06T10:40:00Z",
        }

        created = handle("relation.create", request, self.context)
        metadata = handle("relation.create", {**request, "command_id": "cmd-relation-metadata", "metadata_json": "{}"}, self.context)
        duplicate = handle("relation.create", {**request, "command_id": "cmd-relation-dup"}, self.context)
        listed = handle("relation.list", {"item_id": event["item_id"], "include_derived_aliases": True}, self.context)
        blocks = handle("relation.list", {"item_id": event["item_id"], "relation_type": "blocks", "include_derived_aliases": True}, self.context)

        self.assertTrue(created["created"])
        self.assertFalse(metadata["ok"])
        self.assertEqual(metadata["error"]["code"], "unsupported_field")
        self.assertEqual(metadata["error"]["field"], "metadata_json")
        self.assertEqual(duplicate["error"]["code"], "semantic_conflict")
        self.assertIn("blocks", {relation["relation_type"] for relation in listed["relations"]})
        self.assertEqual([relation["relation_type"] for relation in blocks["relations"]], ["blocks"])
        self.assertEqual(blocks["relations"][0]["source_item_id"], event["item_id"])
        self.assertEqual(blocks["relations"][0]["target_item_id"], task["item_id"])
        self.assertEqual(blocks["relations"][0]["result_kind"], "derived_alias")

    def test_reminder_create_is_durable_only_duplicate_safe_and_never_sends(self) -> None:
        event = handle("event.create", event_request("cmd-reminder-event"), self.context)
        self.bootstrap_subject("recipient")
        request = {
            "command_id": "cmd-reminder",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 1,
            "created_at_utc": "2026-06-06T11:00:00Z",
            "work_subject_ref": "recipient",
            "channel": "whatsapp",
            "eligible_at_utc": "2026-06-06T12:00:00Z",
        }

        missing_binding = handle("reminder.create", request, self.context)
        created = handle("reminder.create", request, CommandContext(ledger=self.connection, adapter_bindings=OPENCLAW))
        duplicate = handle(
            "reminder.create",
            {**request, "command_id": "cmd-reminder-if-absent", "if_absent": True},
            CommandContext(ledger=self.connection, adapter_bindings=OPENCLAW),
        )
        stale_duplicate = handle(
            "reminder.create",
            {**request, "command_id": "cmd-reminder-stale-duplicate"},
            CommandContext(ledger=self.connection, adapter_bindings=OPENCLAW),
        )
        attempts = self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0]

        self.assertEqual(missing_binding["error"]["code"], "environment_failure")
        self.assertTrue(created["created"])
        self.assertFalse(duplicate["created"])
        self.assertEqual(stale_duplicate["error"]["code"], "stale_version")
        self.assertEqual(stale_duplicate["error"]["field"], "target_version")
        self.assertEqual(created["predicted_delivery"]["send_boundary"], "no_external_send_from_authoring_command")
        self.assertEqual(attempts, 0)

    def test_cli_returns_one_json_response_and_normative_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "spine.sqlite"
            connection = connect(db_path)
            initialize_schema(connection)
            connection.close()
            request = json.dumps(
                {
                    "command_id": "cmd-cli-subject",
                    "actor_subject_id": "cli-agent",
                    "subject_id": "cli-agent",
                    "subject_kind": "agent",
                    "display_name": "CLI Agent",
                    "status": "active",
                    "updated_at_utc": "2026-06-06T10:00:00Z",
                }
            )
            stdout = io.StringIO()
            stdin = io.StringIO(request)
            original_stdin = sys.stdin
            try:
                sys.stdin = stdin
                with contextlib.redirect_stdout(stdout):
                    exit_code = cli_main(["--db", str(db_path), "subject", "upsert"])
            finally:
                sys.stdin = original_stdin

            lines = stdout.getvalue().splitlines()
            payload = json.loads(lines[0])
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(lines), 1)
            self.assertTrue(payload["ok"])

    def test_cli_missing_db_is_structured_preflight_failure(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli_main(["item", "list"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["field"], "db")

    def test_cli_input_file_pretty_dry_run_and_generated_command_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "spine.sqlite"
            connection = connect(db_path)
            initialize_schema(connection)
            context = CommandContext(ledger=connection)
            self.bootstrap_subject_in_context(context, "agent")
            baseline_receipt_count = connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
            connection.close()
            input_path = Path(tmpdir) / "event.json"
            input_path.write_text(
                json.dumps(
                    {
                        "actor_subject_id": "agent",
                        "created_at_utc": "2026-06-06T10:01:00Z",
                        "title": "Generated ID event",
                        "all_day": False,
                        "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T12:00:00Z"},
                    }
                ),
                encoding="utf-8",
            )

            first_exit, first_payload, first_stdout = self.run_cli(
                "--db",
                str(db_path),
                "--input",
                str(input_path),
                "--pretty",
                "--dry-run",
                "--generate-command-id",
                "event",
                "create",
            )
            second_exit, second_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "--input",
                str(input_path),
                "--dry-run",
                "--generate-command-id",
                "event",
                "create",
            )
            connection = connect(db_path)
            try:
                item_count = connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0]
                receipt_count = connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            self.assertTrue(first_payload["dry_run"])
            self.assertTrue(first_payload["created"])
            self.assertEqual(first_payload["command_receipt_id"], second_payload["command_receipt_id"])
            self.assertGreater(len(first_stdout.splitlines()), 1)
            self.assertEqual(item_count, 0)
            self.assertEqual(receipt_count, baseline_receipt_count)

    def test_cli_generated_command_id_uses_normative_payload_and_lexical_db_path(self) -> None:
        request = {
            "actor_subject_id": "agent",
            "created_at_utc": "2026-06-06T10:01:00Z",
            "title": "Generated ID event",
            "all_day": False,
            "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T12:00:00Z"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                expected_path = os.path.normpath(os.path.join(os.getcwd(), "nested", "spine.sqlite"))
                expected = "cmd_" + hash_canonical_json(
                    {
                        "derivation_version": "spine.cli-command-id.v1",
                        "command": "event.create",
                        "db_path": expected_path,
                        "request": request,
                    }
                )

                self.assertEqual(_generated_command_id("event.create", request, "nested/./spine.sqlite"), expected)
                self.assertEqual(
                    _generated_command_id(
                        "event.create",
                        request,
                        os.path.join(os.getcwd(), "nested", "..", "nested", "spine.sqlite"),
                    ),
                    expected,
                )

                symlink_path = Path(tmpdir) / "db-link"
                target_path = Path(tmpdir) / "db-target"
                try:
                    target_path.mkdir()
                    symlink_path.symlink_to(target_path, target_is_directory=True)
                except OSError:
                    self.skipTest("symlink creation unavailable")
                linked_id = _generated_command_id("event.create", request, str(symlink_path / "spine.sqlite"))
                target_id = _generated_command_id("event.create", request, str(target_path / "spine.sqlite"))
                self.assertNotEqual(linked_id, target_id)
            finally:
                os.chdir(previous_cwd)

    def test_cli_normative_exit_code_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "spine.sqlite"
            connection = connect(db_path)
            initialize_schema(connection)
            context = CommandContext(ledger=connection)
            self.bootstrap_subject_in_context(context, "agent")
            self.bootstrap_subject_in_context(context, "recipient")
            event = handle("event.create", event_request("cmd-cli-exit-event"), context)
            task = handle("task.create", task_request("cmd-cli-exit-task"), context)
            handle(
                "relation.create",
                {
                    "command_id": "cmd-cli-exit-relation",
                    "actor_subject_id": "agent",
                    "source_item_id": task["item_id"],
                    "source_target_version": 1,
                    "target_item_id": event["item_id"],
                    "target_target_version": 1,
                    "relation_type": "depends_on",
                    "created_at_utc": "2026-06-06T10:40:00Z",
                },
                context,
            )
            handle(
                "task.update",
                {
                    "command_id": "cmd-cli-exit-task-update",
                    "actor_subject_id": "agent",
                    "item_id": task["item_id"],
                    "target_version": 1,
                    "updated_at_utc": "2026-06-06T10:45:00Z",
                    "patch": {"summary": "advance version"},
                },
                context,
            )
            connection.close()

            stale_exit, stale_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "task",
                "update",
                stdin_payload={
                    "command_id": "cmd-cli-stale",
                    "actor_subject_id": "agent",
                    "item_id": task["item_id"],
                    "target_version": 1,
                    "updated_at_utc": "2026-06-06T10:50:00Z",
                    "patch": {"title": "stale"},
                },
            )
            conflict_exit, conflict_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "relation",
                "create",
                stdin_payload={
                    "command_id": "cmd-cli-duplicate",
                    "actor_subject_id": "agent",
                    "source_item_id": task["item_id"],
                    "source_target_version": 2,
                    "target_item_id": event["item_id"],
                    "target_target_version": 1,
                    "relation_type": "depends_on",
                    "created_at_utc": "2026-06-06T10:41:00Z",
                },
            )
            env_exit, env_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "reminder",
                "create",
                stdin_payload={
                    "command_id": "cmd-cli-env",
                    "actor_subject_id": "agent",
                    "item_id": event["item_id"],
                    "target_version": 1,
                    "created_at_utc": "2026-06-06T11:00:00Z",
                    "work_subject_ref": "recipient",
                    "channel": "whatsapp",
                    "eligible_at_utc": "2026-06-06T12:00:00Z",
                },
            )
            invalid_json_exit, invalid_json_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "item",
                "list",
                stdin_text="{",
            )
            unsupported_exit, unsupported_payload, _ = self.run_cli("--db", str(db_path), "not", "real")
            unsupported_if_absent_exit, unsupported_if_absent_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "--if-absent",
                "event",
                "create",
            )
            generated_overwrite_exit, generated_overwrite_payload, _ = self.run_cli(
                "--db",
                str(db_path),
                "--generate-command-id",
                "event",
                "create",
                stdin_payload=event_request("cmd-cli-supplied-id"),
            )

            self.assertEqual(stale_exit, 5)
            self.assertEqual(stale_payload["error"]["code"], "stale_version")
            self.assertEqual(conflict_exit, 6)
            self.assertEqual(conflict_payload["error"]["code"], "semantic_conflict")
            self.assertEqual(env_exit, 7)
            self.assertEqual(env_payload["error"]["code"], "environment_failure")
            self.assertEqual(invalid_json_exit, 3)
            self.assertEqual(invalid_json_payload["command"], "item.list")
            self.assertEqual(invalid_json_payload["error"]["field"], "input")
            self.assertEqual(unsupported_exit, 2)
            self.assertEqual(unsupported_payload["command"], "not.real")
            self.assertEqual(unsupported_payload["error"]["code"], "unsupported_command")
            self.assertEqual(unsupported_if_absent_exit, 2)
            self.assertEqual(unsupported_if_absent_payload["command"], "event.create")
            self.assertEqual(unsupported_if_absent_payload["error"]["code"], "unsupported_field")
            self.assertEqual(unsupported_if_absent_payload["error"]["field"], "if_absent")
            self.assertEqual(generated_overwrite_exit, 2)
            self.assertEqual(generated_overwrite_payload["command"], "event.create")
            self.assertEqual(generated_overwrite_payload["error"]["code"], "invalid_request")
            self.assertEqual(generated_overwrite_payload["error"]["field"], "command_id")

    def test_mvp_golden_command_response_fixtures_are_stable(self) -> None:
        responses = build_mvp_fixture_responses()

        self.assertEqual(
            sorted(path.name for path in MVP_FIXTURE_DIR.glob("*.json")),
            sorted(responses),
        )
        for name, response in responses.items():
            with self.subTest(name=name):
                self.assertEqual(json.loads((MVP_FIXTURE_DIR / name).read_text()), response)

    def test_contract_manifest_and_response_schema_cover_fixtures(self) -> None:
        manifest = json.loads(CONTRACT_MANIFEST.read_text())
        schema = json.loads(COMMAND_RESPONSE_SCHEMA.read_text())

        self.assertEqual(manifest["schema_version"], "spine.agent-command-fixtures.v1")
        self.assertEqual(schema["title"], "Spine Agent Command Response")
        for entry in manifest["fixtures"]:
            with self.subTest(fixture=entry["fixture"]):
                payload = json.loads((Path(__file__).parents[1] / entry["fixture"]).read_text())
                self.assertEqual(entry["schema"], "contracts/schemas/command-response.schema.json")
                assert_matches_command_response_schema(payload, schema)
                self.assertIn(entry["command"], payload.get("command", entry["command"]))
                self.assertIsInstance(payload["ok"], bool)
                if payload["ok"]:
                    self.assertEqual(payload["command"], entry["command"])
                    self.assertNotIn("error", payload)
                    self.assertEqual(entry["expected_exit_code"], 0)
                    if entry["command"] == "reminder.create":
                        self.assertIn("work_instance_id", payload)
                        self.assertIn("notification_policy_id", payload)
                        self.assertIn("notification_policy_item_version", payload)
                else:
                    self.assertIn("error", payload)
                    self.assertIn("code", payload["error"])
                    self.assertIn("message", payload["error"])
                    self.assertGreater(entry["expected_exit_code"], 0)

    def bootstrap_subject(self, subject_id: str) -> None:
        self.bootstrap_subject_in_context(self.context, subject_id)

    def bootstrap_subject_in_context(self, context: CommandContext, subject_id: str) -> None:
        request = {
            "command_id": f"cmd-bootstrap-{subject_id}",
            "actor_subject_id": subject_id if subject_id == "agent" else "agent",
            "subject_id": subject_id,
            "subject_kind": "agent" if subject_id == "agent" else "person",
            "display_name": subject_id.title(),
            "status": "active",
            "updated_at_utc": "2026-06-06T10:00:00Z",
        }
        response = handle("subject.upsert", request, context)
        self.assertTrue(response["ok"])

    def run_cli(
        self,
        *argv: str,
        stdin_payload: dict[str, object] | None = None,
        stdin_text: str | None = None,
    ) -> tuple[int, dict[str, object], str]:
        text = stdin_text if stdin_text is not None else json.dumps(stdin_payload or {})
        stdout = io.StringIO()
        original_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(text)
            with contextlib.redirect_stdout(stdout):
                exit_code = cli_main(list(argv))
        finally:
            sys.stdin = original_stdin
        output = stdout.getvalue()
        return exit_code, json.loads(output), output


def event_request(command_id: str) -> dict[str, object]:
    return {
        "command_id": command_id,
        "actor_subject_id": "agent",
        "created_at_utc": "2026-06-06T10:01:00Z",
        "title": "Dentist",
        "all_day": False,
        "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T12:00:00Z"},
    }


def task_request(command_id: str) -> dict[str, object]:
    return {
        "command_id": command_id,
        "actor_subject_id": "agent",
        "created_at_utc": "2026-06-06T10:02:00Z",
        "title": "File paperwork",
    }


def assert_matches_command_response_schema(payload: dict[str, object], schema: dict[str, object]) -> None:
    test_case = unittest.TestCase()
    test_case.assertEqual(schema["required"], ["ok"])
    test_case.assertIsInstance(payload.get("ok"), bool)
    if payload.get("ok") is True:
        test_case.assertIn("command", payload)
        test_case.assertNotIn("error", payload)
    else:
        error = payload.get("error")
        test_case.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        test_case.assertIn("code", error)
        test_case.assertIn("message", error)
        test_case.assertLessEqual(set(error), {"code", "message", "field"})


def build_mvp_fixture_responses() -> dict[str, object]:
    connection = connect()
    initialize_schema(connection)
    context = CommandContext(ledger=connection)
    responses: dict[str, object] = {}

    def record(name: str, command: str, request: dict[str, object], command_context: CommandContext = context) -> dict[str, object]:
        response = handle(command, request, command_context)
        responses[name] = response
        return response

    def subject(subject_id: str = "agent", command_id: str | None = None) -> dict[str, object]:
        return {
            "command_id": command_id or f"cmd-fixture-subject-{subject_id}",
            "actor_subject_id": subject_id if subject_id == "agent" else "agent",
            "subject_id": subject_id,
            "subject_kind": "agent" if subject_id == "agent" else "person",
            "display_name": subject_id.title(),
            "status": "active",
            "updated_at_utc": "2026-06-06T10:00:00Z",
        }

    def fixture_event_request(command_id: str) -> dict[str, object]:
        return {
            "command_id": command_id,
            "actor_subject_id": "agent",
            "created_at_utc": "2026-06-06T10:01:00Z",
            "title": "Fixture event",
            "summary": "Bring forms",
            "all_day": False,
            "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T12:00:00Z"},
        }

    def fixture_task_request(command_id: str) -> dict[str, object]:
        return {
            "command_id": command_id,
            "actor_subject_id": "agent",
            "created_at_utc": "2026-06-06T10:02:00Z",
            "title": "Fixture task",
        }

    record("subject_upsert_created.json", "subject.upsert", subject())
    record("subject_upsert_replay.json", "subject.upsert", subject())
    record("subject_recipient.json", "subject.upsert", subject("recipient"))
    responses.pop("subject_recipient.json")
    event = record("event_create.json", "event.create", fixture_event_request("cmd-fixture-event-create"))
    task = record("task_create.json", "task.create", fixture_task_request("cmd-fixture-task-create"))
    record("item_show_event.json", "item.show", {"item_id": event["item_id"]})
    record("item_list_event.json", "item.list", {"item_type": "event"})
    record(
        "event_update.json",
        "event.update",
        {
            "command_id": "cmd-fixture-event-update",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T10:10:00Z",
            "patch": {"title": "Fixture event updated"},
        },
    )
    record(
        "event_reschedule.json",
        "event.reschedule",
        {
            "command_id": "cmd-fixture-event-reschedule",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 2,
            "rescheduled_at_utc": "2026-06-06T10:20:00Z",
            "all_day": False,
            "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T13:00:00Z"},
        },
    )
    record(
        "event_cancel.json",
        "event.cancel",
        {
            "command_id": "cmd-fixture-event-cancel",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 3,
            "cancelled_at_utc": "2026-06-06T10:30:00Z",
        },
    )
    record(
        "item_archive.json",
        "item.archive",
        {
            "command_id": "cmd-fixture-archive",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 4,
            "archived_at_utc": "2026-06-06T10:40:00Z",
        },
    )
    record(
        "task_update.json",
        "task.update",
        {
            "command_id": "cmd-fixture-task-update",
            "actor_subject_id": "agent",
            "item_id": task["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T10:15:00Z",
            "patch": {"summary": "Updated task"},
        },
    )
    record(
        "task_complete.json",
        "task.complete",
        {
            "command_id": "cmd-fixture-task-complete",
            "actor_subject_id": "agent",
            "item_id": task["item_id"],
            "target_version": 2,
            "completed_at_utc": "2026-06-06T10:25:00Z",
        },
    )
    task2 = record("task_cancel_source_create.json", "task.create", fixture_task_request("cmd-fixture-task-cancel-create"))
    responses.pop("task_cancel_source_create.json")
    record(
        "task_cancel.json",
        "task.cancel",
        {
            "command_id": "cmd-fixture-task-cancel",
            "actor_subject_id": "agent",
            "item_id": task2["item_id"],
            "target_version": 1,
            "cancelled_at_utc": "2026-06-06T10:26:00Z",
        },
    )
    record(
        "relation_create.json",
        "relation.create",
        {
            "command_id": "cmd-fixture-relation",
            "actor_subject_id": "agent",
            "source_item_id": task2["item_id"],
            "source_target_version": 2,
            "target_item_id": task["item_id"],
            "target_target_version": 3,
            "relation_type": "depends_on",
            "created_at_utc": "2026-06-06T10:50:00Z",
        },
    )
    record("relation_list.json", "relation.list", {"item_id": task["item_id"], "include_derived_aliases": True})
    record(
        "reminder_create.json",
        "reminder.create",
        {
            "command_id": "cmd-fixture-reminder",
            "actor_subject_id": "agent",
            "item_id": task2["item_id"],
            "target_version": 2,
            "created_at_utc": "2026-06-06T11:00:00Z",
            "work_subject_ref": "recipient",
            "channel": "whatsapp",
            "eligible_at_utc": "2026-06-06T12:00:00Z",
        },
        CommandContext(ledger=connection, adapter_bindings=OPENCLAW),
    )
    record(
        "dry_run_event_create.json",
        "event.create",
        fixture_event_request("cmd-fixture-dry-run-event"),
        CommandContext(ledger=connection, dry_run=True),
    )
    dry_run_noop_task = record("dry_run_noop_task_source_create.json", "task.create", fixture_task_request("cmd-fixture-dry-run-noop-task"))
    responses.pop("dry_run_noop_task_source_create.json")
    record(
        "dry_run_task_update_noop.json",
        "task.update",
        {
            "command_id": "cmd-fixture-dry-run-task-noop",
            "actor_subject_id": "agent",
            "item_id": dry_run_noop_task["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T12:00:00Z",
            "patch": {"title": "Fixture task"},
        },
        CommandContext(ledger=connection, dry_run=True),
    )
    record(
        "dry_run_failure.json",
        "event.create",
        {
            "command_id": "cmd-fixture-dry-run-failure",
            "actor_subject_id": "agent",
            "created_at_utc": "2026-06-06T12:01:00Z",
            "title": "Missing anchor",
            "all_day": False,
        },
        CommandContext(ledger=connection, dry_run=True),
    )
    record(
        "reminder_duplicate_if_absent.json",
        "reminder.create",
        {
            "command_id": "cmd-fixture-reminder-if-absent",
            "actor_subject_id": "agent",
            "item_id": task2["item_id"],
            "target_version": 2,
            "created_at_utc": "2026-06-06T11:30:00Z",
            "work_subject_ref": "recipient",
            "channel": "whatsapp",
            "eligible_at_utc": "2026-06-06T12:00:00Z",
            "if_absent": True,
        },
        CommandContext(ledger=connection, adapter_bindings=OPENCLAW),
    )
    record(
        "stale_version_failure.json",
        "task.update",
        {
            "command_id": "cmd-fixture-stale",
            "actor_subject_id": "agent",
            "item_id": task["item_id"],
            "target_version": 1,
            "updated_at_utc": "2026-06-06T12:30:00Z",
            "patch": {"title": "stale"},
        },
    )
    record(
        "wrong_type_failure.json",
        "event.update",
        {
            "command_id": "cmd-fixture-wrong-type",
            "actor_subject_id": "agent",
            "item_id": task["item_id"],
            "target_version": 3,
            "updated_at_utc": "2026-06-06T12:31:00Z",
            "patch": {"title": "wrong"},
        },
    )
    record(
        "archived_item_failure.json",
        "event.update",
        {
            "command_id": "cmd-fixture-archived-failure",
            "actor_subject_id": "agent",
            "item_id": event["item_id"],
            "target_version": 4,
            "updated_at_utc": "2026-06-06T12:32:00Z",
            "patch": {"title": "archived"},
        },
    )
    record(
        "duplicate_failure.json",
        "relation.create",
        {
            "command_id": "cmd-fixture-relation-dup",
            "actor_subject_id": "agent",
            "source_item_id": task2["item_id"],
            "source_target_version": 3,
            "target_item_id": task["item_id"],
            "target_target_version": 3,
            "relation_type": "depends_on",
            "created_at_utc": "2026-06-06T10:51:00Z",
        },
    )
    connection.close()
    return responses


if __name__ == "__main__":
    unittest.main()
