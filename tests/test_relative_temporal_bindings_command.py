from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema
from spine.services.scheduling import materialize_notification_horizon
from spine.services.work import require_processable_work


class RelativeTemporalBindingCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_dir = Path(__file__).parents[1] / "contracts" / "schemas"
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(schema_dir.glob("*.schema.json"))
        }
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
        )
        cls.create_response_validator = Draft202012Validator(
            schemas["schedule-related-task-create-response.schema.json"], registry=registry
        )
        cls.list_response_validator = Draft202012Validator(
            schemas["schedule-binding-list-response.schema.json"], registry=registry
        )
        cls.reconcile_response_validator = Draft202012Validator(
            schemas["schedule-binding-reconcile-response.schema.json"], registry=registry
        )
        cls.agenda_response_validator = Draft202012Validator(
            schemas["schedule-agenda-response.schema.json"], registry=registry
        )
        cls.show_response_validator = Draft202012Validator(
            schemas["schedule-show-response.schema.json"], registry=registry
        )

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self.assertTrue(
            handle(
                "subject.upsert",
                {
                    "command_id": "binding-bootstrap-owner",
                    "actor_subject_id": "owner",
                    "subject_id": "owner",
                    "subject_kind": "person",
                    "display_name": "Owner",
                    "updated_at_utc": "2026-08-17T10:00:00Z",
                },
                self.context,
            )["ok"]
        )
        self.assertTrue(
            handle(
                "delivery_target.upsert",
                {
                    "command_id": "binding-bootstrap-route",
                    "actor_subject_id": "owner",
                    "delivery_target_id": "whatsapp-owner",
                    "owner_kind": "subject",
                    "owner_subject_id": "owner",
                    "channel": "whatsapp",
                    "adapter_name": "openclaw",
                    "target_ref": "owner@example",
                    "updated_at_utc": "2026-08-17T10:01:00Z",
                },
                self.context,
            )["ok"]
        )
        self.event = handle("schedule.create", self._event_request(), self.context)
        self.assertTrue(self.event["ok"], self.event)

    def tearDown(self) -> None:
        self.connection.close()

    def test_snapshot_composite_is_atomic_replayable_and_readable(self) -> None:
        request = self._related_request("snapshot")
        created = handle("schedule.related_task.create", request, self.context)

        self.assertTrue(created["ok"], created)
        self.create_response_validator.validate(created)
        self.assertEqual(created["effect"], "related_task_schedule_created")
        self.assertEqual(created["temporal_binding"]["binding_state"], "snapshot_resolved")
        self.assertEqual(created["scheduled_time"]["utc_instant"], "2026-08-22T13:00:00Z")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM relative_temporal_bindings").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_item_relations").fetchone()[0], 1)

        replay = handle("schedule.related_task.create", request, self.context)
        self.assertEqual(replay["effect"], "related_task_schedule_create_replay")
        self.assertEqual(replay["command_receipt_id"], created["command_receipt_id"])

        shown = handle(
            "schedule.show",
            {"item_id": created["task"]["item_id"], "include": ["relations", "temporal_bindings"]},
            self.context,
        )
        self.assertTrue(shown["ok"], shown)
        self.show_response_validator.validate(shown)
        self.assertEqual(shown["temporal_bindings"][0]["binding_state"], "snapshot_resolved")
        self.assertEqual(shown["relations"][0]["relation_type"], "part_of")
        self.assertEqual(shown["scheduled_times"][0]["resolution_source"], "authoring_receipt")
        self.assertEqual(shown["lifecycle"]["opportunities"]["state"], "not_requested")

    def test_follow_source_blocks_delivery_then_reconciles_target(self) -> None:
        created = handle("schedule.related_task.create", self._related_request("follow_source", with_reminder=True), self.context)
        self.assertTrue(created["ok"], created)
        work_id = created["work_instance_ids"][0]

        moved = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v1",
                "command_id": "move-source-event",
                "actor_subject_id": "owner",
                "item_id": self.event["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-17T12:00:00Z",
                "patch": {
                    "scheduled_time": {
                        "time_basis": "local_instant",
                        "local_date": "2026-08-23",
                        "local_time": "10:00:00",
                        "timezone": "America/Toronto",
                        "timezone_database_version": {"kind": "explicit", "version": system_timezone_database_version()},
                    }
                },
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(moved["ok"], moved)
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            require_processable_work(self.connection, work_id)

        listed = handle(
            "schedule.binding.list",
            {
                "contract_version": "spine.schedule-binding-list.v1",
                "target_item_id": created["task"]["item_id"],
                "binding_mode": "follow_source",
                "limit": "10",
            },
            self.context,
        )
        self.assertTrue(listed["ok"], listed)
        self.list_response_validator.validate(listed)
        binding = listed["bindings"][0]
        self.assertEqual(binding["binding_state"], "stale")
        agenda = handle(
            "agenda.show",
            {
                "contract_version": "spine.schedule-agenda.v1",
                "evaluated_at_utc": "2026-08-17T12:00:00Z",
                "range_start_local": "2026-08-22T00:00:00",
                "range_end_local": "2026-08-23T00:00:00",
                "timezone": "America/Toronto",
                "timezone_database_version": {"kind": "system_current"},
                "item_ids": [created["task"]["item_id"]],
                "limit": "10",
            },
            self.context,
        )
        self.assertTrue(agenda["ok"], agenda)
        self.agenda_response_validator.validate(agenda)
        self.assertTrue(agenda["entries"][0]["actionable"])
        self.assertFalse(agenda["entries"][0]["schedule_actionable"])
        self.assertEqual(agenda["entries"][0]["temporal_binding"]["binding_state"], "stale")
        reconciled = handle(
            "schedule.binding.reconcile",
            {
                "contract_version": "spine.schedule-binding-reconcile.v1",
                "command_id": "reconcile-moved-source",
                "actor_subject_id": "owner",
                "reconciled_at_utc": "2026-08-17T12:01:00Z",
                **binding["reconcile_inputs"],
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(reconciled["ok"], reconciled)
        self.reconcile_response_validator.validate(reconciled)
        self.assertEqual(reconciled["resolution_outcome"], "target_rescheduled")
        self.assertEqual(reconciled["target_item_version"], "2")
        self.assertEqual(
            self.connection.execute("SELECT reason_code FROM work_instances WHERE work_instance_id = ?", (work_id,)).fetchone()[0],
            "notification_target_changed",
        )

    def test_follow_binding_rejects_direct_due_replacement(self) -> None:
        created = handle("schedule.related_task.create", self._related_request("follow_source"), self.context)
        self.assertTrue(created["ok"], created)
        response = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v1",
                "command_id": "direct-bound-task-move",
                "actor_subject_id": "owner",
                "item_id": created["task"]["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-17T12:00:00Z",
                "patch": {
                    "scheduled_time": {
                        "time_basis": "local_instant",
                        "local_date": "2026-08-25",
                        "local_time": "09:00:00",
                        "timezone": "America/Toronto",
                        "timezone_database_version": {"kind": "explicit", "version": system_timezone_database_version()},
                    }
                },
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertEqual(response["error"]["code"], "semantic_conflict")
        self.assertEqual(response["error"]["field"], "temporal_binding_id")

    def test_selected_recurring_occurrence_persists_provenance_and_reconciles(self) -> None:
        recurring_request = self._event_request()
        recurring_request["command_id"] = "binding-recurring-source-event"
        recurring_request["scheduled_time"]["recurrence"] = {  # type: ignore[index]
            "rules": [
                {
                    "frequency": "DAILY",
                    "interval": "1",
                    "seed": "2026-08-22T10:00:00",
                    "start_bound": "2026-08-22T10:00:00",
                    "end_condition": {"kind": "count", "count": "3"},
                }
            ]
        }
        recurring = handle("schedule.create", recurring_request, self.context)
        self.assertTrue(recurring["ok"], recurring)
        occurrences = handle(
            "item.occurrences",
            {
                "item_id": recurring["item_id"],
                "range_start": "2026-08-22T00:00:00",
                "range_end": "2026-08-23T00:00:00",
                "limit": "10",
            },
            self.context,
        )
        occurrence = occurrences["occurrences"][0]
        encoded = occurrence["occurrence_key"].split(".", 1)[0]
        selector = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))[
            "target_occurrence_selector"
        ]
        request = self._related_request("follow_source")
        request["command_id"] = "related-task-selected-occurrence"
        request["source"] = {
            "item_id": recurring["item_id"],
            "target_version": "1",
            "anchor_role": "event_start",
            "scope": "selected_occurrence",
            "source_recurrence_revision_id": recurring["recurrence"]["recurrence_revision_id"],
            "target_occurrence_key": occurrence["occurrence_key"],
            "target_occurrence_selector": selector,
        }

        created = handle("schedule.related_task.create", request, self.context)

        self.assertTrue(created["ok"], created)
        revision = created["temporal_binding"]["latest_revision"]
        self.assertEqual(revision["source_scope"], "selected_occurrence")
        self.assertIsNotNone(revision["source_occurrence_provenance_id"])
        provenance = self.connection.execute(
            "SELECT consumer, producer, management_status FROM occurrence_provenance WHERE occurrence_provenance_id = ?",
            (revision["source_occurrence_provenance_id"],),
        ).fetchone()
        self.assertEqual(tuple(provenance), ("temporal_binding", "schedule.related_task.create", "active"))

    def test_source_only_change_refreshes_binding_without_versioning_task(self) -> None:
        created = handle("schedule.related_task.create", self._related_request("follow_source"), self.context)
        updated = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v1",
                "command_id": "retitle-source-event",
                "actor_subject_id": "owner",
                "item_id": self.event["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-17T12:00:00Z",
                "patch": {"item": {"title": "Golf trip with Alex"}},
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(updated["ok"], updated)
        binding = self._binding_for(created["task"]["item_id"])
        self.assertEqual(binding["binding_state"], "stale")

        reconciled = handle(
            "schedule.binding.reconcile",
            {
                "contract_version": "spine.schedule-binding-reconcile.v1",
                "command_id": "refresh-source-only-change",
                "actor_subject_id": "owner",
                "reconciled_at_utc": "2026-08-17T12:01:00Z",
                **binding["reconcile_inputs"],
                "materialization": {"mode": "none"},
            },
            self.context,
        )

        self.assertTrue(reconciled["ok"], reconciled)
        self.assertEqual(reconciled["resolution_outcome"], "source_refreshed")
        self.assertEqual(reconciled["target_item_version"], "1")
        self.assertNotEqual(
            reconciled["prior_temporal_binding_revision_id"],
            reconciled["current_temporal_binding_revision_id"],
        )

    def test_snapshot_remains_non_governing_after_source_and_target_move(self) -> None:
        created = handle("schedule.related_task.create", self._related_request("snapshot"), self.context)
        self._move_item(self.event["item_id"], "1", "2026-08-23", "move-snapshot-source")
        self.assertEqual(self._binding_for(created["task"]["item_id"])["binding_state"], "snapshot_resolved")

        moved_target = self._move_item(created["task"]["item_id"], "1", "2026-08-25", "move-snapshot-target")
        self.assertTrue(moved_target["ok"], moved_target)
        self.assertEqual(self._binding_for(created["task"]["item_id"])["binding_state"], "snapshot_diverged")

    def test_cancel_source_behavior_is_reconciled_by_scheduler(self) -> None:
        request = self._related_request("follow_source")
        request["temporal_binding"]["source_terminal_behavior"] = "cancel_target"  # type: ignore[index]
        created = handle("schedule.related_task.create", request, self.context)
        cancelled = handle(
            "schedule.cancel",
            {
                "contract_version": "spine.schedule-cancel.v1",
                "command_id": "cancel-binding-source",
                "actor_subject_id": "owner",
                "item_id": self.event["item_id"],
                "target_version": "1",
                "cancelled_at_utc": "2026-08-17T12:00:00Z",
                "reason_code": "trip_cancelled",
            },
            self.context,
        )
        self.assertTrue(cancelled["ok"], cancelled)

        cycle = materialize_notification_horizon(
            self.connection,
            evaluated_at_utc="2026-08-17T12:01:00Z",
            horizon_seconds=86400,
            max_items=10,
            actor_subject_id="owner",
        )

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertGreaterEqual(cycle.items_repaired, 1)
        shown = handle("item.show", {"item_id": created["task"]["item_id"]}, self.context)
        self.assertEqual(shown["task_detail"]["task_status"], "cancelled")
        self.assertEqual(self._binding_for(created["task"]["item_id"], status="retired")["binding_state"], "retired")

    def test_create_dry_run_and_injected_failures_leave_no_partial_bundle(self) -> None:
        request = self._related_request("snapshot")
        preview = handle(
            "schedule.related_task.create",
            request,
            CommandContext(ledger=self.connection, dry_run=True),
        )
        self.assertTrue(preview["ok"], preview)
        self.create_response_validator.validate(preview)
        self.assertTrue(preview["dry_run"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM relative_temporal_bindings").fetchone()[0], 0)

        baseline = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "coordination_items",
                "coordination_item_relations",
                "relative_temporal_bindings",
                "relative_temporal_binding_revisions",
                "command_receipts",
            )
        }
        for phase in ("item", "provenance", "relation", "binding", "policies", "work", "receipt"):
            failed_request = self._related_request("snapshot")
            failed_request["command_id"] = f"related-task-failure-{phase}"
            failed = handle(
                "schedule.related_task.create",
                failed_request,
                CommandContext(
                    ledger=self.connection,
                    transport_metadata={"related_task_create_fail_after": phase},
                ),
            )
            self.assertFalse(failed["ok"], (phase, failed))
            self.assertEqual(failed["error"]["code"], "runtime_failure")
            for table, count in baseline.items():
                self.assertEqual(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count, (phase, table))

    def test_create_replay_precedes_later_source_freshness(self) -> None:
        request = self._related_request("follow_source")
        created = handle("schedule.related_task.create", request, self.context)
        self._move_item(self.event["item_id"], "1", "2026-08-23", "move-before-create-replay")

        replay = handle("schedule.related_task.create", request, self.context)

        self.assertTrue(replay["ok"], replay)
        self.assertEqual(replay["effect"], "related_task_schedule_create_replay")
        self.assertEqual(replay["command_receipt_id"], created["command_receipt_id"])

    def test_binding_list_paginates_and_rejects_cursor_after_catalog_change(self) -> None:
        first_request = self._related_request("follow_source")
        first_request["command_id"] = "binding-page-first"
        second_request = self._related_request("follow_source")
        second_request["command_id"] = "binding-page-second"
        self.assertTrue(handle("schedule.related_task.create", first_request, self.context)["ok"])
        self.assertTrue(handle("schedule.related_task.create", second_request, self.context)["ok"])
        query = {
            "contract_version": "spine.schedule-binding-list.v1",
            "source_item_id": self.event["item_id"],
            "binding_mode": "follow_source",
            "limit": "1",
        }
        first_page = handle("schedule.binding.list", query, self.context)
        self.assertTrue(first_page["has_more"])
        cursor = first_page["next_cursor"]
        second_page = handle("schedule.binding.list", {**query, "cursor": cursor}, self.context)
        self.assertTrue(second_page["ok"], second_page)
        self.assertFalse(second_page["has_more"])
        self.assertNotEqual(
            first_page["bindings"][0]["temporal_binding_id"],
            second_page["bindings"][0]["temporal_binding_id"],
        )

        self._move_item(self.event["item_id"], "1", "2026-08-23", "move-after-binding-page")
        stale = handle("schedule.binding.list", {**query, "cursor": cursor}, self.context)
        self.assertEqual(stale["error"]["code"], "stale_cursor")
        self.assertEqual(stale["error"]["field"], "cursor")

    def _binding_for(self, target_item_id: str, *, status: str = "active") -> dict[str, object]:
        listed = handle(
            "schedule.binding.list",
            {
                "contract_version": "spine.schedule-binding-list.v1",
                "target_item_id": target_item_id,
                "binding_status": status,
                "limit": "10",
            },
            self.context,
        )
        self.assertTrue(listed["ok"], listed)
        self.assertEqual(len(listed["bindings"]), 1)
        return listed["bindings"][0]

    def _move_item(self, item_id: str, version: str, local_date: str, command_id: str) -> dict[str, object]:
        return handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v1",
                "command_id": command_id,
                "actor_subject_id": "owner",
                "item_id": item_id,
                "target_version": version,
                "updated_at_utc": "2026-08-17T12:00:00Z",
                "patch": {
                    "scheduled_time": {
                        "time_basis": "local_instant",
                        "local_date": local_date,
                        "local_time": "10:00:00",
                        "timezone": "America/Toronto",
                        "timezone_database_version": {
                            "kind": "explicit",
                            "version": system_timezone_database_version(),
                        },
                    }
                },
                "materialization": {"mode": "none"},
            },
            self.context,
        )

    def _event_request(self) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v1",
            "command_id": "binding-source-event",
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-17T11:00:00Z",
            "item": {"item_type": "event", "title": "Golf trip", "event_detail": {"all_day": False}},
            "scheduled_time": {
                "time_basis": "local_instant",
                "local_date": "2026-08-22",
                "local_time": "10:00:00",
                "timezone": "America/Toronto",
                "timezone_database_version": {"kind": "explicit", "version": system_timezone_database_version()},
            },
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            },
            "reminders": [
                {
                    "policy_key": "source_notice",
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
                    "late_handling": {"kind": "skip"},
                }
            ],
            "materialization": {"mode": "none"},
        }

    def _related_request(self, mode: str, *, with_reminder: bool = False) -> dict[str, object]:
        request: dict[str, object] = {
            "contract_version": "spine.schedule-related-task-create.v1",
            "command_id": f"related-task-{mode}-{'reminder' if with_reminder else 'plain'}",
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-17T11:30:00Z",
            "source": {"item_id": self.event["item_id"], "target_version": "1", "anchor_role": "event_start", "scope": "item"},
            "task": {"title": "Pack golf bag", "priority": "high", "subject_roles": [{"subject_id": "owner", "role": "assignee"}]},
            "relationship": {"relation_type": "part_of"},
            "temporal_binding": {"binding_mode": mode, "offset_basis": "elapsed", "offset_seconds": "-3600"},
            "reminders": [],
            "materialization": {"mode": "none"},
        }
        if mode == "follow_source":
            request["temporal_binding"]["source_terminal_behavior"] = "detach_at_last_value"  # type: ignore[index]
        if with_reminder:
            request["delivery"] = {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            }
            request["reminders"] = [
                {
                    "policy_key": "task_notice",
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-1800"}},
                    "late_handling": {"kind": "skip"},
                }
            ]
            request["materialization"] = {
                "mode": "bounded",
                "evaluated_at_utc": "2026-08-17T11:30:00Z",
                "range": {"kind": "item_relative", "start_offset_seconds": "-3600", "end_offset_seconds": "1"},
                "limit": "10",
            }
        return request


if __name__ == "__main__":
    unittest.main()
