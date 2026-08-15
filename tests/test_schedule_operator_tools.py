from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.commands.cli import main as cli_main
from spine.commands.compact import compact_schedule_response
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema


class ScheduleOperatorToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema_dir = Path(__file__).parents[1] / "contracts" / "schemas"
        schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(schema_dir.glob("*.schema.json"))}
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
        cls.builder_request_validator = Draft202012Validator(schemas["schedule-countdown-builder-request.schema.json"], registry=registry)
        cls.builder_response_validator = Draft202012Validator(schemas["schedule-countdown-builder-response.schema.json"], registry=registry)
        cls.compact_validator = Draft202012Validator(schemas["schedule-compact-response.schema.json"], registry=registry)

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(
            ledger=self.connection,
            delivery_target_defaults={"owner_whatsapp": "whatsapp-owner"},
        )
        self._bootstrap(self.context)

    def tearDown(self) -> None:
        self.connection.close()

    def test_relative_countdown_builder_is_read_only_and_feeds_schedule_create(self) -> None:
        request = self.builder_request()
        self.builder_request_validator.validate(request)
        changes_before = self.connection.total_changes

        built = handle("schedule.build", request, self.context)

        self.assertTrue(built["ok"], built)
        self.builder_response_validator.validate(built)
        self.assertEqual(built["event_at_utc"], "2026-08-15T16:00:00Z")
        self.assertEqual(built["estimated_reminder_count"], "4")
        generated = built["schedule_create_request"]
        self.assertEqual(generated["scheduled_time"]["local_time"], "12:00:00")
        self.assertEqual(
            generated["scheduled_time"]["timezone_database_version"],
            {"kind": "explicit", "version": system_timezone_database_version()},
        )
        self.assertEqual(
            generated["delivery"]["target"],
            {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
        )
        self.assertEqual(self.connection.total_changes, changes_before)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 0)

        created = handle("schedule.create", generated, self.context)

        self.assertTrue(created["ok"], created)
        self.assertEqual(created["materialization"]["work_instance_count"], "4")
        self.assertEqual(created["phases"]["delivery"], "not_attempted")

    def test_builder_is_deterministic_and_rejects_ambiguous_resulting_local_time(self) -> None:
        first = handle("schedule.build", self.builder_request(), self.context)
        second = handle("schedule.build", self.builder_request(), self.context)
        self.assertEqual(first, second)

        ambiguous = self.builder_request()
        ambiguous["reference_time_utc"] = "2026-11-01T03:30:00Z"
        response = handle("schedule.build", ambiguous, self.context)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertEqual(response["error"]["field"], "scheduled_time.local_time")

    def test_builder_rejects_unbounded_or_already_started_countdowns(self) -> None:
        before_reference = self.builder_request()
        before_reference["reminder_start_before_seconds"] = "10800"
        response = handle("schedule.build", before_reference, self.context)
        self.assertEqual(response["error"]["field"], "reminder_start_before_seconds")

        too_small = self.builder_request()
        too_small["materialization_limit"] = "3"
        response = handle("schedule.build", too_small, self.context)
        self.assertEqual(response["error"]["field"], "materialization_limit")

        over_range = self.builder_request()
        over_range["event_delay_seconds"] = str(367 * 86_400)
        response = handle("schedule.build", over_range, self.context)
        self.assertEqual(response["error"]["field"], "reminder_start_before_seconds")

    def test_compact_dry_run_is_explicitly_a_preview(self) -> None:
        built = handle("schedule.build", self.builder_request(), self.context)
        preview = handle(
            "schedule.create",
            built["schedule_create_request"],
            CommandContext(
                ledger=self.connection,
                dry_run=True,
                delivery_target_defaults=self.context.delivery_target_defaults,
            ),
        )
        compact = compact_schedule_response(preview)

        self.compact_validator.validate(compact)
        self.assertTrue(compact["dry_run"])
        self.assertEqual(compact["lifecycle"]["authored"], "preview")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 0)

    def test_cli_compact_create_and_show_keep_required_audit_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "spine.sqlite"
            connection = connect(database)
            initialize_schema(connection)
            context = CommandContext(ledger=connection)
            self._bootstrap(context)
            connection.close()

            built_connection = connect(database)
            built = handle(
                "schedule.build",
                self.builder_request(explicit_delivery=True),
                CommandContext(ledger=built_connection),
            )
            built_connection.close()
            self.assertTrue(built["ok"], built)

            create_exit, create_output = self._cli(
                ["--db", str(database), "--compact", "schedule", "create"],
                built["schedule_create_request"],
            )
            self.assertEqual(create_exit, 0)
            self.compact_validator.validate(create_output)
            self.assertEqual(create_output["action"], "schedule.create")
            self.assertEqual(create_output["work"]["count"], "4")
            self.assertEqual(create_output["lifecycle"]["delivery_attempt"], "not_attempted")
            self.assertEqual(create_output["delivery_targets"][0]["destination_source_ref"], "openclaw")
            self.assertEqual(create_output["delivery_targets"][0]["destination_target_ref"], "owner@example")

            show_exit, show_output = self._cli(
                [
                    "--db",
                    str(database),
                    "--compact",
                    "--item-id",
                    create_output["item_id"],
                    "--include",
                    "attempts",
                    "schedule",
                    "show",
                ],
                None,
            )
            self.assertEqual(show_exit, 0)
            self.compact_validator.validate(show_output)
            self.assertEqual(show_output["action"], "schedule.show")
            self.assertEqual(show_output["effect"], "readback")
            self.assertEqual(show_output["command_id"], create_output["command_id"])
            self.assertEqual(show_output["notification_policy_ids"], create_output["notification_policy_ids"])
            self.assertEqual(show_output["work"]["work_instance_ids"], create_output["work"]["work_instance_ids"])
            self.assertEqual(show_output["lifecycle"]["delivery_outcome"], "none")

    def builder_request(self, *, explicit_delivery: bool = False) -> dict[str, object]:
        target = (
            {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"}
            if explicit_delivery
            else {"resolution": "context_default", "default_key": "owner_whatsapp"}
        )
        return {
            "contract_version": "spine.schedule-countdown-builder.v1",
            "command_id": "relative-event-countdown-001",
            "actor_subject_id": "owner",
            "reference_time_utc": "2026-08-15T14:00:00Z",
            "title": "Leave for appointment",
            "event_detail": {"all_day": False, "visibility": "private"},
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "system_current"},
            "event_delay_seconds": "7200",
            "reminder_interval_seconds": "1800",
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": target,
            },
        }

    def _bootstrap(self, context: CommandContext) -> None:
        subject = handle(
            "subject.upsert",
            {
                "command_id": "schedule-operator-bootstrap-owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": "2026-08-15T13:00:00Z",
            },
            context,
        )
        self.assertTrue(subject["ok"], subject)
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": "schedule-operator-bootstrap-route",
                "actor_subject_id": "owner",
                "delivery_target_id": "whatsapp-owner",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "owner@example",
                "updated_at_utc": "2026-08-15T13:01:00Z",
            },
            context,
        )
        self.assertTrue(route["ok"], route)

    def _cli(self, argv: list[str], payload: object | None) -> tuple[int, dict[str, object]]:
        original_stdin = sys.stdin
        output = io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(payload) if payload is not None else "")
            with redirect_stdout(output):
                exit_code = cli_main(argv)
        finally:
            sys.stdin = original_stdin
        return exit_code, json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
