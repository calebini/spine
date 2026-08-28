from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.ledger import connect, initialize_schema
from spine.services.work import start_work


class ScheduleOperationsCommandTests(unittest.TestCase):
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
        cls.validators = {
            "agenda": Draft202012Validator(schemas["schedule-agenda-response.schema.json"], registry=registry),
            "update": Draft202012Validator(schemas["schedule-update-response.schema.json"], registry=registry),
            "cancel": Draft202012Validator(schemas["schedule-cancel-response.schema.json"], registry=registry),
        }

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self.assertTrue(
            handle(
                "subject.upsert",
                {
                    "command_id": "schedule-ops-bootstrap-owner",
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
                    "command_id": "schedule-ops-bootstrap-route",
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

    def test_agenda_combines_singleton_and_recurrence_and_invalidates_cursor(self) -> None:
        event = handle("schedule.create", self.event_request("agenda-event", title="Late event", hour="11"), self.context)
        task = handle("schedule.create", self.task_request("agenda-task"), self.context)
        self.assertTrue(event["ok"], event)
        self.assertTrue(task["ok"], task)
        request = self.agenda_request(limit="1")

        first = handle("agenda.show", request, self.context)

        self.assertTrue(first["ok"], first)
        self.validators["agenda"].validate(first)
        self.assertTrue(first["has_more"])
        self.assertIsNotNone(first["next_cursor"])
        self.assertEqual(first["entries"][0]["item_type"], "task")
        second = handle("agenda.show", {**request, "cursor": first["next_cursor"]}, self.context)
        self.validators["agenda"].validate(second)
        self.assertEqual(second["entries"][0]["item_type"], "event")

        changed = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "agenda-stale-source",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-13T13:00:00Z",
                "patch": {"item": {"title": "Changed title"}},
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(changed["ok"], changed)
        stale = handle("agenda.show", {**request, "cursor": first["next_cursor"]}, self.context)
        self.assertEqual(stale["error"]["code"], "stale_cursor")
        self.assertEqual(stale["error"]["field"], "cursor")

    def test_update_replaces_reminder_and_reconciles_then_materializes_atomically(self) -> None:
        created = handle("schedule.create", self.event_request("update-event", materialize=True), self.context)
        self.assertTrue(created["ok"], created)
        policy = created["policies"][0]
        request = {
            "contract_version": "spine.schedule-update.v2",
            "command_id": "schedule-update-reminder",
            "actor_subject_id": "owner",
            "item_id": created["item_id"],
            "target_version": "1",
            "updated_at_utc": "2026-08-13T13:00:00Z",
            "patch": {
                "item": {"title": "Updated appointment"},
                "notification_plan": {
                    "action": "clear",
                    "custom_additions": [{
                        "policy_key": "countdown",
                        "notification_intent_id": policy["notification_intent_id"],
                        "notification_policy_id": policy["notification_policy_id"],
                        "schedule": {
                            "kind": "repeat_window",
                            "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-7200"},
                            "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
                            "stop_inclusive": False,
                            "cadence": {"kind": "fixed_elapsed", "interval_seconds": "1800"},
                        },
                        "late_handling": {"kind": "skip"},
                    }],
                },
            },
            "materialization": self.materialization(),
        }

        updated = handle("schedule.update", request, self.context)

        self.assertTrue(updated["ok"], updated)
        self.validators["update"].validate(updated)
        self.assertEqual(updated["effect"], "schedule_updated_and_reconciled")
        self.assertEqual(updated["changed_dimensions"], ["item", "reminders"])
        self.assertEqual(len(updated["work_reconciliation"]["cancelled_work_instance_ids"]), 6)
        self.assertEqual(len(updated["work_reconciliation"]["created_work_instance_ids"]), 4)
        self.assertEqual(updated["materialization"]["opportunity_count"], "4")
        self.assertEqual(len(updated["materialization"]["opportunity_work"]), 4)
        self.assertEqual(
            {value["work_instance_id"] for value in updated["materialization"]["opportunity_work"]},
            set(updated["work_reconciliation"]["created_work_instance_ids"]),
        )
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        replay = handle("schedule.update", request, self.context)
        self.assertEqual(replay["effect"], "schedule_update_replay")
        self.assertEqual(replay["work_reconciliation"], updated["work_reconciliation"])

    def test_update_recurring_time_requires_replacement_and_bounded_path_regenerates_provenance(self) -> None:
        created = handle("schedule.create", self.task_request("update-recurring"), self.context)
        missing = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "schedule-update-missing-recurrence",
                "actor_subject_id": "owner",
                "item_id": created["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-13T13:00:00Z",
                "patch": {"scheduled_time": self.scheduled_time("2026-08-15", "08:00:00")},
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertEqual(missing["error"]["code"], "missing_required_field")
        self.assertEqual(missing["error"]["field"], "patch.recurrence")
        self.assertEqual(
            self.connection.execute(
                "SELECT current_version FROM coordination_items WHERE item_id = ?",
                (created["item_id"],),
            ).fetchone()[0],
            1,
        )
        replacement = copy.deepcopy(self.task_request("unused")["scheduled_time"]["recurrence"])
        replacement["mode"] = "replace"
        replacement["rules"][0]["seed"] = "2026-08-15T08:00:00"
        replacement["rules"][0]["start_bound"] = "2026-08-15T08:00:00"
        updated = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "schedule-update-recurring",
                "actor_subject_id": "owner",
                "item_id": created["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-13T13:01:00Z",
                "patch": {
                    "scheduled_time": self.scheduled_time("2026-08-15", "08:00:00"),
                    "recurrence": replacement,
                },
                "materialization": {
                    "mode": "bounded",
                    "evaluated_at_utc": "2026-08-13T12:00:00Z",
                    "range": {"kind": "item_relative", "start_offset_seconds": "-3600", "end_offset_seconds": "1"},
                    "limit": "100",
                },
            },
            self.context,
        )
        self.assertTrue(updated["ok"], updated)
        self.validators["update"].validate(updated)
        self.assertEqual(updated["phases"]["provenance"], "regenerated")
        self.assertEqual(updated["materialization"]["work_instance_count"], "1")
        evidence = updated["materialization"]["opportunity_work"][0]
        self.assertEqual(evidence["original_scheduled_fact"], "2026-08-15T08:00:00")
        self.assertEqual(evidence["expressed_scheduled_fact"], "2026-08-15T08:00:00")
        self.assertGreater(self.connection.execute("SELECT COUNT(*) FROM occurrence_provenance").fetchone()[0], 0)

    def test_cancel_terminalizes_item_and_cancels_only_never_started_work(self) -> None:
        created = handle("schedule.create", self.event_request("cancel-event", materialize=True), self.context)
        started_id = created["materialization"]["work_instance_ids"][0]
        start_work(self.connection, work_instance_id=started_id, started_at_utc="2026-08-14T11:00:00Z")
        request = {
            "contract_version": "spine.schedule-cancel.v1",
            "command_id": "schedule-cancel-event",
            "actor_subject_id": "owner",
            "item_id": created["item_id"],
            "target_version": "1",
            "cancelled_at_utc": "2026-08-13T14:00:00Z",
            "reason_code": "operator_cancelled",
        }

        cancelled = handle("schedule.cancel", request, self.context)

        self.assertTrue(cancelled["ok"], cancelled)
        self.validators["cancel"].validate(cancelled)
        self.assertEqual(cancelled["detail_status"], "cancelled")
        self.assertEqual(len(cancelled["cancelled_work_instance_ids"]), 5)
        self.assertEqual(cancelled["protected_stale_work_instance_ids"], [started_id])
        self.assertEqual(
            self.connection.execute("SELECT reason_code FROM work_instances WHERE status = 'cancelled' LIMIT 1").fetchone()[0],
            "parent_lifecycle_terminal",
        )
        replay = handle("schedule.cancel", request, self.context)
        self.assertEqual(replay["effect"], "schedule_cancel_replay")
        self.assertEqual(replay["cancelled_work_instance_ids"], cancelled["cancelled_work_instance_ids"])

    def test_update_dry_run_matches_identities_and_persists_nothing(self) -> None:
        created = handle("schedule.create", self.event_request("dry-run-event"), self.context)
        request = {
            "contract_version": "spine.schedule-update.v2",
            "command_id": "schedule-update-dry-run",
            "actor_subject_id": "owner",
            "item_id": created["item_id"],
            "target_version": "1",
            "updated_at_utc": "2026-08-13T13:00:00Z",
            "patch": {"item": {"title": "Preview title"}},
            "materialization": {"mode": "none"},
        }
        preview = handle("schedule.update", request, CommandContext(ledger=self.connection, dry_run=True))
        self.assertTrue(preview["dry_run"])
        self.assertEqual(
            self.connection.execute(
                "SELECT current_version FROM coordination_items WHERE item_id = ?",
                (created["item_id"],),
            ).fetchone()[0],
            1,
        )
        committed = handle("schedule.update", request, self.context)
        for field in ("command_receipt_id", "audit_id", "current_version", "policies"):
            self.assertEqual(preview[field], committed[field])

    def test_injected_update_phase_failure_rolls_back_truth_work_audit_and_receipt(self) -> None:
        for phase in ("truth", "work", "materialization", "receipt"):
            with self.subTest(phase=phase):
                created = handle(
                    "schedule.create",
                    self.event_request(f"rollback-create-{phase}", materialize=True),
                    self.context,
                )
                before_work = self.connection.execute(
                    "SELECT status, reason_code FROM work_instances WHERE item_id = ? ORDER BY work_instance_id",
                    (created["item_id"],),
                ).fetchall()
                response = handle(
                    "schedule.update",
                    {
                        "contract_version": "spine.schedule-update.v2",
                        "command_id": f"rollback-update-{phase}",
                        "actor_subject_id": "owner",
                        "item_id": created["item_id"],
                        "target_version": "1",
                        "updated_at_utc": "2026-08-13T13:00:00Z",
                        "patch": {"item": {"title": f"Rollback {phase}"}},
                        "materialization": self.materialization(),
                    },
                    CommandContext(
                        ledger=self.connection,
                        transport_metadata={"schedule_operations_fail_after": phase},
                    ),
                )
                self.assertEqual(response["error"]["code"], "runtime_failure")
                self.assertEqual(
                    self.connection.execute(
                        "SELECT current_version FROM coordination_items WHERE item_id = ?",
                        (created["item_id"],),
                    ).fetchone()[0],
                    1,
                )
                after_work = self.connection.execute(
                    "SELECT status, reason_code FROM work_instances WHERE item_id = ? ORDER BY work_instance_id",
                    (created["item_id"],),
                ).fetchall()
                self.assertEqual([tuple(row) for row in after_work], [tuple(row) for row in before_work])
                self.assertEqual(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM command_receipts WHERE command_id = ?",
                        (f"rollback-update-{phase}",),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE action = 'schedule_updated' AND item_id = ?",
                        (created["item_id"],),
                    ).fetchone()[0],
                    0,
                )

    def scheduled_time(self, local_date: str, local_time: str) -> dict[str, object]:
        return {
            "time_basis": "local_instant",
            "local_date": local_date,
            "local_time": local_time,
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "system_current"},
        }

    def materialization(self) -> dict[str, object]:
        return {
            "mode": "bounded",
            "evaluated_at_utc": "2026-08-13T12:00:00Z",
            "range": {"kind": "item_relative", "start_offset_seconds": "-7200", "end_offset_seconds": "1"},
            "limit": "100",
        }

    def event_request(
        self,
        command_id: str,
        *,
        title: str = "Dentist appointment",
        hour: str = "10",
        materialize: bool = False,
    ) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v2",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-13T12:00:00Z",
            "item": {"item_type": "event", "title": title, "event_detail": {"all_day": False}},
            "scheduled_time": self.scheduled_time("2026-08-14", f"{hour}:00:00"),
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            },
            "notification_plan": {
                "mode": "none",
                "custom_additions": [{
                    "policy_key": "countdown",
                    "schedule": {
                        "kind": "repeat_window",
                        "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-7200"},
                        "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
                        "stop_inclusive": False,
                        "cadence": {"kind": "fixed_elapsed", "interval_seconds": "1200"},
                    },
                    "late_handling": {"kind": "skip"},
                }],
            },
            "materialization": self.materialization() if materialize else {"mode": "none"},
        }

    def task_request(self, command_id: str) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v2",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-13T12:00:00Z",
            "item": {"item_type": "task", "title": "Review household plan", "task_detail": {}},
            "scheduled_time": {
                **self.scheduled_time("2026-08-14", "08:00:00"),
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
            },
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            },
            "notification_plan": {
                "mode": "none",
                "custom_additions": [{
                    "policy_key": "one_hour_before",
                    "schedule": {
                        "kind": "once",
                        "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                    },
                    "late_handling": {"kind": "skip"},
                }],
            },
            "materialization": {"mode": "none"},
        }

    def agenda_request(self, *, limit: str) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-agenda.v1",
            "evaluated_at_utc": "2026-08-13T12:00:00Z",
            "range_start_local": "2026-08-14T00:00:00",
            "range_end_local": "2026-08-15T00:00:00",
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "system_current"},
            "include": ["notification_summary", "work_summary"],
            "limit": limit,
        }


if __name__ == "__main__":
    unittest.main()
