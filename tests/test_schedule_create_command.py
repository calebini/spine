from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema
from spine.services import list_eligible_work


class ScheduleCreateCommandTests(unittest.TestCase):
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
        cls.response_validator = Draft202012Validator(
            schemas["schedule-create-response.schema.json"],
            registry=registry,
        )

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(
            ledger=self.connection,
            delivery_target_defaults={"owner_whatsapp": "whatsapp-owner"},
        )
        self.assertTrue(
            handle(
                "subject.upsert",
                {
                    "command_id": "bootstrap-owner",
                    "actor_subject_id": "owner",
                    "subject_id": "owner",
                    "subject_kind": "person",
                    "display_name": "Owner",
                    "updated_at_utc": "2026-08-13T10:00:00Z",
                },
                self.context,
            )["ok"]
        )
        self.assertTrue(
            handle(
                "delivery_target.upsert",
                {
                    "command_id": "bootstrap-route",
                    "actor_subject_id": "owner",
                    "delivery_target_id": "whatsapp-owner",
                    "owner_kind": "subject",
                    "owner_subject_id": "owner",
                    "channel": "whatsapp",
                    "adapter_name": "openclaw",
                    "target_ref": "owner@example",
                    "updated_at_utc": "2026-08-13T10:01:00Z",
                },
                self.context,
            )["ok"]
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_event_repeat_window_is_created_and_materialized_atomically(self) -> None:
        response = handle("schedule.create", self.event_request(), self.context)

        self.assertTrue(response["ok"], response)
        self.response_validator.validate(response)
        self.assertEqual(response["effect"], "schedule_created")
        self.assertEqual(response["scheduled_time"]["utc_instant"], "2026-08-14T14:00:00Z")
        self.assertEqual(response["materialization"]["work_instance_count"], "6")
        self.assertEqual(response["phases"]["delivery"], "not_attempted")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 6)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        audit = self.connection.execute("SELECT action, reason_code FROM audit_log WHERE item_id = ?", (response["item_id"],)).fetchall()
        self.assertEqual([(row["action"], row["reason_code"]) for row in audit], [("schedule_created", "schedule_created")])

    def test_recurring_task_policy_only_uses_context_route_and_persists_recurrence(self) -> None:
        request = self.task_request()
        response = handle("schedule.create", request, self.context)

        self.assertTrue(response["ok"], response)
        self.response_validator.validate(response)
        self.assertEqual(response["delivery"]["resolution_source"], "context_default")
        self.assertEqual(response["delivery"]["default_key"], "owner_whatsapp")
        self.assertEqual(response["phases"]["provenance"], "not_requested")
        self.assertEqual(response["materialization"]["state"], "not_requested")
        self.assertIn("recurrence", response)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM recurrence_sets").fetchone()[0], 1)
        role = self.connection.execute("SELECT subject_id, role, status FROM item_subject_roles").fetchone()
        self.assertEqual((role["subject_id"], role["role"], role["status"]), ("owner", "assignee", "active"))

    def test_recurring_bounded_materialization_builds_provenance_before_work(self) -> None:
        request = self.task_request(command_id="schedule-recurring-materialized")
        request["materialization"] = {
            "mode": "bounded",
            "evaluated_at_utc": "2026-08-13T12:00:00Z",
            "range": {"kind": "item_relative", "start_offset_seconds": "-3600", "end_offset_seconds": "1"},
            "limit": "100",
        }

        response = handle("schedule.create", request, self.context)

        self.assertTrue(response["ok"], response)
        self.response_validator.validate(response)
        self.assertEqual(response["phases"]["provenance"], "regenerated")
        self.assertEqual(response["materialization"]["work_instance_count"], "1")
        self.assertGreater(self.connection.execute("SELECT COUNT(*) FROM occurrence_provenance").fetchone()[0], 0)
        work = self.connection.execute("SELECT occurrence_provenance_id FROM work_instances").fetchone()
        self.assertIsNotNone(work["occurrence_provenance_id"])

    def test_replay_returns_snapshotted_evidence_without_reresolving_environment(self) -> None:
        request = self.event_request()
        created = handle("schedule.create", request, self.context)
        self.connection.execute("UPDATE delivery_targets SET status = 'inactive' WHERE delivery_target_id = 'whatsapp-owner'")
        replay_context = CommandContext(ledger=self.connection, delivery_target_defaults={})

        replay = handle("schedule.create", request, replay_context)

        self.assertTrue(replay["ok"], replay)
        self.response_validator.validate(replay)
        self.assertEqual(replay["effect"], "schedule_create_replay")
        self.assertEqual(replay["receipt"], created["receipt"])
        self.assertEqual(replay["delivery"], created["delivery"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM command_receipts WHERE command = 'schedule.create'").fetchone()[0],
            1,
        )

    def test_policy_order_is_nonsemantic_for_replay(self) -> None:
        request = self.event_request(command_id="schedule-policy-order")
        request["materialization"] = {"mode": "none"}
        request["reminders"].append(
            {
                "policy_key": "one_day_before",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-86400"},
                },
                "late_handling": {"kind": "skip"},
            }
        )
        created = handle("schedule.create", request, self.context)
        reordered = copy.deepcopy(request)
        reordered["reminders"].reverse()

        replay = handle("schedule.create", reordered, self.context)

        self.assertTrue(created["ok"], created)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(replay["effect"], "schedule_create_replay")
        self.assertEqual(replay["policies"], created["policies"])

    def test_multiple_once_reminders_with_shared_intent_remain_processable(self) -> None:
        request = self.event_request(command_id="schedule-multi-once")
        request["reminders"] = [
            {
                "policy_key": "ninety_minutes",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-9000"},
                },
                "late_handling": {"kind": "skip"},
            },
            {
                "policy_key": "seventy_minutes",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-7800"},
                },
                "late_handling": {"kind": "skip"},
            },
            {
                "policy_key": "thirty_minutes",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-1800"},
                },
                "late_handling": {"kind": "skip"},
            },
            {
                "policy_key": "fifteen_minutes",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-900"},
                },
                "late_handling": {"kind": "skip"},
            },
        ]
        request["materialization"]["range"] = {
            "kind": "item_relative",
            "start_offset_seconds": "-9000",
            "end_offset_seconds": "1",
        }

        created = handle("schedule.create", request, self.context)

        self.assertTrue(created["ok"], created)
        self.assertEqual(len(created["policies"]), 4)
        self.assertEqual(len({policy["notification_intent_id"] for policy in created["policies"]}), 1)
        self.assertEqual(len({policy["notification_policy_id"] for policy in created["policies"]}), 4)

        reconciled = handle(
            "notification_work.materialize",
            {
                "command_id": "schedule-multi-once-reconcile",
                "actor_subject_id": "owner",
                "item_id": created["item_id"],
                "target_version": created["current_version"],
                "materialized_at_utc": "2026-08-13T12:01:00Z",
                "range_start_utc": "2026-08-14T11:00:00Z",
                "range_end_utc": "2026-08-14T14:01:00Z",
                "limit": "100",
            },
            self.context,
        )

        self.assertTrue(reconciled["ok"], reconciled)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM work_instances WHERE status = 'cancelled'").fetchone()[0],
            0,
        )
        eligible = list_eligible_work(self.connection, now_utc="2026-08-14T14:00:00Z")
        self.assertEqual(len(eligible), 4)

    def test_dry_run_returns_same_identities_and_persists_nothing(self) -> None:
        request = self.event_request()
        preview = handle(
            "schedule.create",
            request,
            CommandContext(
                ledger=self.connection,
                dry_run=True,
                delivery_target_defaults=self.context.delivery_target_defaults,
            ),
        )
        self.assertTrue(preview["ok"], preview)
        self.response_validator.validate(preview)
        self.assertTrue(preview["dry_run"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 0)

        created = handle("schedule.create", request, self.context)
        for field in ("item_id", "audit_id", "command_receipt_id", "policies", "materialization"):
            self.assertEqual(preview[field], created[field])

    def test_every_injected_phase_failure_rolls_back_the_complete_bundle(self) -> None:
        for phase in ("item", "policies", "provenance", "work", "receipt"):
            with self.subTest(phase=phase):
                request = self.event_request(command_id=f"schedule-failure-{phase}")
                response = handle(
                    "schedule.create",
                    request,
                    CommandContext(
                        ledger=self.connection,
                        delivery_target_defaults=self.context.delivery_target_defaults,
                        transport_metadata={"schedule_create_fail_after": phase},
                    ),
                )
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "runtime_failure")
                for table in (
                    "coordination_items",
                    "notification_policies",
                    "work_instances",
                    "command_receipts",
                    "audit_log",
                ):
                    count = self.connection.execute(f"SELECT COUNT(*) FROM {table} WHERE 1 = 1").fetchone()[0]
                    expected = 2 if table == "command_receipts" else 0
                    self.assertEqual(count, expected, (phase, table))

    def test_ambiguous_time_and_duplicate_task_role_fail_before_mutation(self) -> None:
        ambiguous = self.event_request(command_id="schedule-ambiguous")
        ambiguous["scheduled_time"]["local_date"] = "2026-11-01"
        ambiguous["scheduled_time"]["local_time"] = "01:30:00"
        ambiguous_response = handle("schedule.create", ambiguous, self.context)
        self.assertEqual(ambiguous_response["error"]["code"], "invalid_request")
        self.assertEqual(ambiguous_response["error"]["field"], "scheduled_time.local_time")

        duplicate = self.task_request(command_id="schedule-duplicate-role")
        duplicate["item"]["task_detail"]["subject_roles"].append(
            {"subject_id": "owner", "role": "assignee", "status": "inactive"}
        )
        duplicate_response = handle("schedule.create", duplicate, self.context)
        self.assertEqual(duplicate_response["error"]["code"], "invalid_request")
        self.assertEqual(duplicate_response["error"]["field"], "item.task_detail.subject_roles")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 0)

    def event_request(self, *, command_id: str = "schedule-event") -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v1",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-13T12:00:00Z",
            "item": {
                "item_type": "event",
                "title": "Dentist appointment",
                "event_detail": {"all_day": False, "visibility": "private"},
            },
            "scheduled_time": {
                "time_basis": "local_instant",
                "local_date": "2026-08-14",
                "local_time": "10:00:00",
                "timezone": "America/Toronto",
                "timezone_database_version": {"kind": "system_current"},
            },
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            },
            "reminders": [
                {
                    "policy_key": "countdown",
                    "schedule": {
                        "kind": "repeat_window",
                        "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-7200"},
                        "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
                        "stop_inclusive": False,
                        "cadence": {"kind": "fixed_elapsed", "interval_seconds": "1200"},
                    },
                    "late_handling": {"kind": "skip"},
                }
            ],
            "materialization": {
                "mode": "bounded",
                "evaluated_at_utc": "2026-08-13T12:00:00Z",
                "range": {"kind": "item_relative", "start_offset_seconds": "-7200", "end_offset_seconds": "1"},
                "limit": "100",
            },
        }

    def task_request(self, *, command_id: str = "schedule-task") -> dict[str, object]:
        request = self.event_request(command_id=command_id)
        request["item"] = {
            "item_type": "task",
            "title": "Review household plan",
            "task_detail": {
                "priority": "normal",
                "subject_roles": [{"subject_id": "owner", "role": "assignee"}],
            },
        }
        request["scheduled_time"] = {
            "time_basis": "local_instant",
            "local_date": "2026-08-14",
            "local_time": "08:00:00",
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "explicit", "version": system_timezone_database_version()},
            "recurrence": {
                "rules": [
                    {
                        "frequency": "DAILY",
                        "interval": "3",
                        "seed": "2026-08-14T08:00:00",
                        "start_bound": "2026-08-14T08:00:00",
                        "end_condition": {"kind": "unbounded"},
                    }
                ]
            },
        }
        request["delivery"]["target"] = {"resolution": "context_default", "default_key": "owner_whatsapp"}
        request["reminders"] = [
            {
                "policy_key": "one_hour_before",
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                },
                "late_handling": {"kind": "deliver_within", "grace_seconds": "900"},
            }
        ]
        request["materialization"] = {"mode": "none"}
        return copy.deepcopy(request)


if __name__ == "__main__":
    unittest.main()
