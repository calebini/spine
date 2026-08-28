from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.adapters import build_openclaw_side_effect_request
from spine.commands import CommandContext, handle
from spine.commands.cli import main as cli_main
from spine.ledger import connect, get_work_instance, initialize_schema
from spine.services.attempts import prepare_work_attempt, record_attempt_success
from spine.services.work import start_work, succeed_work


class ScheduleShowCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_dir = Path(__file__).parents[1] / "contracts" / "schemas"
        schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(schema_dir.glob("*.schema.json"))}
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
        cls.response_validator = Draft202012Validator(
            schemas["schedule-show-response.schema.json"],
            registry=registry,
        )

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self._bootstrap(self.context)

    def tearDown(self) -> None:
        self.connection.close()

    def test_readback_returns_current_schedule_policy_work_route_and_lifecycle(self) -> None:
        created = handle("schedule.create", self._schedule_request(), self.context)
        self.assertTrue(created["ok"], created)
        counts_before = self._evidence_counts()

        shown = handle("schedule.show", {"item_id": created["item_id"]}, self.context)

        self.assertTrue(shown["ok"], shown)
        self.response_validator.validate(shown)
        self.assertEqual(self._evidence_counts(), counts_before)
        self.assertEqual(shown["item"]["event_detail"]["event_status"], "scheduled")
        self.assertEqual(shown["scheduled_times"][0]["anchor_role"], "event_start")
        self.assertEqual(shown["scheduled_times"][0]["utc_instant"], created["scheduled_time"]["utc_instant"])
        self.assertEqual(shown["scheduled_times"][0]["resolution_source"], "authoring_receipt")
        self.assertEqual(shown["lifecycle"]["authored"]["state"], "committed")
        self.assertEqual(shown["lifecycle"]["opportunities"], {"state": "expanded", "count": "6"})
        self.assertEqual(shown["lifecycle"]["work"]["state"], "materialized")
        self.assertEqual(shown["lifecycle"]["work"]["status_counts"]["eligible"], "6")
        self.assertEqual(shown["lifecycle"]["delivery"]["attempt_state"], "not_attempted")
        self.assertEqual(len(shown["notification_policies"]), 1)
        self.assertEqual(len(shown["work_instances"]), 6)
        self.assertEqual(shown["side_effect_attempts"], [])
        self.assertEqual(shown["authoring_receipt"]["command_id"], created["command_id"])
        target = shown["delivery_targets"][0]
        self.assertTrue(target["routing_facts_match_authored"])
        self.assertEqual(target["authored_snapshot"]["delivery_state"], "not_attempted_by_command")
        self.assertEqual(target["current_snapshot"]["target_ref"], "owner@example")

    def test_readback_separates_delivery_attempt_from_terminal_outcome(self) -> None:
        created = handle("schedule.create", self._schedule_request(command_id="schedule-show-delivery"), self.context)
        work_id = created["materialization"]["work_instance_ids"][0]
        start_work(
            self.connection,
            work_instance_id=work_id,
            started_at_utc="2026-08-14T11:59:00Z",
        )
        gate = prepare_work_attempt(
            self.connection,
            work_instance_id=work_id,
            adapter_name="openclaw",
            idempotency_key="schedule-show-delivery-attempt",
            request_envelope={"body": "Reminder"},
            attempted_at_utc="2026-08-14T11:59:01Z",
            attempt_id="attempt_schedule_show_delivery",
        )

        pending = handle("schedule.show", {"item_id": created["item_id"]}, self.context)
        self.assertEqual(pending["lifecycle"]["delivery"]["attempt_state"], "attempted")
        self.assertEqual(pending["lifecycle"]["delivery"]["outcome_state"], "pending")

        record_attempt_success(
            self.connection,
            attempt_id=gate.attempt.attempt_id,
            completed_at_utc="2026-08-14T11:59:02Z",
            provider_ref="fake-provider-ref",
        )
        succeed_work(
            self.connection,
            work_instance_id=work_id,
            succeeded_at_utc="2026-08-14T11:59:03Z",
            reason_code="delivered",
        )
        shown = handle("schedule.show", {"item_id": created["item_id"]}, self.context)

        self.response_validator.validate(shown)
        self.assertEqual(shown["lifecycle"]["delivery"]["outcome_state"], "succeeded")
        self.assertEqual(shown["lifecycle"]["delivery"]["status_counts"]["succeeded"], "1")
        self.assertEqual(shown["lifecycle"]["work"]["status_counts"]["succeeded"], "1")
        self.assertEqual(shown["side_effect_attempts"][0]["attempt_status"], "succeeded")
        self.assertEqual(shown["side_effect_attempts"][0]["provider_ref"], "fake-provider-ref")

    def test_include_and_limits_bound_detail_without_hiding_summary_counts(self) -> None:
        created = handle("schedule.create", self._schedule_request(command_id="schedule-show-bounds"), self.context)
        shown = handle(
            "schedule.show",
            {
                "item_id": created["item_id"],
                "include": ["work"],
                "work_instances_limit": "2",
            },
            self.context,
        )

        self.response_validator.validate(shown)
        self.assertEqual(shown["included"], ["work"])
        self.assertEqual(len(shown["work_instances"]), 2)
        self.assertEqual(shown["work_instances_count"], "6")
        self.assertTrue(shown["work_instances_truncated"])
        self.assertEqual(shown["lifecycle"]["work"]["count"], "6")
        self.assertNotIn("notification_policies", shown)
        self.assertNotIn("side_effect_attempts", shown)

    def test_attempt_readback_nests_immutable_notification_rendering(self) -> None:
        request = self._schedule_request(command_id="schedule-show-rendering")
        request["item"]["primary_location"] = {
            "mode": "create",
            "label": "Downtown clinic",
            "kind": "place",
        }
        created = handle("schedule.create", request, self.context)
        work_id = created["materialization"]["work_instance_ids"][0]
        start_work(self.connection, work_instance_id=work_id, started_at_utc="2026-08-14T11:59:00Z")
        request = build_openclaw_side_effect_request(
            self.connection,
            work_row=get_work_instance(self.connection, work_id),
            envelope=SimpleNamespace(
                trace_id="trace-rendering",
                causation_id="cause-rendering",
                actual_start_ts=datetime(2026, 8, 14, 11, 59, 1, tzinfo=UTC),
            ),
        )
        prepare_work_attempt(
            self.connection,
            attempt_id=request.attempt_id,
            work_instance_id=request.work_instance_id,
            adapter_name="openclaw",
            idempotency_key=request.idempotency_key,
            request_envelope=request.request_envelope,
            attempted_at_utc=request.attempted_at_utc,
            notification_rendering=request.notification_rendering,
        )

        shown = handle("schedule.show", {"item_id": created["item_id"], "include": ["attempts"]}, self.context)
        self.response_validator.validate(shown)
        evidence = shown["side_effect_attempts"][0]["notification_rendering"]
        self.assertEqual(evidence["body_text"], request.message.body_text)
        self.assertEqual(evidence["notification_rendering_id"], request.notification_rendering.notification_rendering_id)
        self.assertEqual(evidence["primary_location"]["location_label"], "Downtown clinic")
        self.assertIn("@ Downtown clinic", evidence["body_text"])

    def test_cli_item_id_and_include_flags_supply_a_complete_read_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spine.sqlite"
            connection = connect(path)
            initialize_schema(connection)
            context = CommandContext(ledger=connection)
            self._bootstrap(context)
            created = handle("schedule.create", self._schedule_request(command_id="schedule-show-cli"), context)
            connection.close()
            output = StringIO()
            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "--db",
                        str(path),
                        "--item-id",
                        created["item_id"],
                        "--include",
                        "policies,work,attempts",
                        "schedule",
                        "show",
                    ]
                )

        response = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.response_validator.validate(response)
        self.assertEqual(response["item"]["item_id"], created["item_id"])

    def _bootstrap(self, context: CommandContext) -> None:
        subject = handle(
            "subject.upsert",
            {
                "command_id": "schedule-show-bootstrap-owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": "2026-08-13T10:00:00Z",
            },
            context,
        )
        self.assertTrue(subject["ok"], subject)
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": "schedule-show-bootstrap-route",
                "actor_subject_id": "owner",
                "delivery_target_id": "whatsapp-owner",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "owner@example",
                "updated_at_utc": "2026-08-13T10:01:00Z",
            },
            context,
        )
        self.assertTrue(route["ok"], route)

    def _schedule_request(self, *, command_id: str = "schedule-show-created") -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v2",
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
            "materialization": {
                "mode": "bounded",
                "evaluated_at_utc": "2026-08-13T12:00:00Z",
                "range": {"kind": "item_relative", "start_offset_seconds": "-7200", "end_offset_seconds": "1"},
                "limit": "100",
            },
        }

    def _evidence_counts(self) -> tuple[int, ...]:
        return tuple(
            self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "coordination_items",
                "notification_policies",
                "work_instances",
                "side_effect_attempts",
                "audit_log",
                "command_receipts",
            )
        )


if __name__ == "__main__":
    unittest.main()
