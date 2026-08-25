from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import CommandContext, handle
from spine.commands.cli import _schedule_show_include
from spine.commands.compact import compact_schedule_response
from spine.ledger import LocationInput, connect, initialize_schema
from spine.ledger.supporting import insert_location
from spine.runtime.compatibility import TickerdCompatibilityInfo


class SchedulePrimaryLocationCommandTests(unittest.TestCase):
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
            name: Draft202012Validator(schemas[name], registry=registry)
            for name in (
                "schedule-create-response.schema.json",
                "schedule-update-response.schema.json",
                "schedule-show-response.schema.json",
                "schedule-agenda-response.schema.json",
                "schedule-countdown-builder-request.schema.json",
                "schedule-countdown-builder-response.schema.json",
            )
        }

    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self.assertTrue(
            handle(
                "subject.upsert",
                {
                    "command_id": "location-bootstrap-owner",
                    "actor_subject_id": "owner",
                    "subject_id": "owner",
                    "subject_kind": "person",
                    "display_name": "Owner",
                    "updated_at_utc": "2026-08-18T12:00:00Z",
                },
                self.context,
            )["ok"]
        )
        self.assertTrue(
            handle(
                "delivery_target.upsert",
                {
                    "command_id": "location-bootstrap-route",
                    "actor_subject_id": "owner",
                    "delivery_target_id": "whatsapp-owner",
                    "owner_kind": "subject",
                    "owner_subject_id": "owner",
                    "channel": "whatsapp",
                    "adapter_name": "openclaw",
                    "target_ref": "owner@example",
                    "updated_at_utc": "2026-08-18T12:01:00Z",
                },
                self.context,
            )["ok"]
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_inline_create_readback_agenda_compact_and_replay(self) -> None:
        request = self.event_request("location-inline-create", materialize=True)
        request["item"]["primary_location"] = self.inline_location()

        created = handle("schedule.create", request, self.context)

        self.assertTrue(created["ok"], created)
        self.validators["schedule-create-response.schema.json"].validate(created)
        location = created["primary_location"]
        self.assertEqual(location["role"], "primary")
        self.assertEqual(location["label"], "Lakeside Golf Club")
        self.assertEqual(location["timezone"], "America/Vancouver")
        self.assertEqual(created["scheduled_time"]["timezone"], "America/Toronto")
        self.assertEqual(self._count("locations"), 1)
        self.assertEqual(self._count("item_locations"), 1)

        omitted = handle("schedule.show", {"item_id": created["item_id"]}, self.context)
        self.assertNotIn("primary_location", omitted)
        shown = handle(
            "schedule.show",
            {"item_id": created["item_id"], "include": ["policies", "primary_location", "work"]},
            self.context,
        )
        self.validators["schedule-show-response.schema.json"].validate(shown)
        self.assertEqual(shown["primary_location"], location)
        self.assertEqual(compact_schedule_response(created)["primary_location"], location)
        self.assertEqual(compact_schedule_response(shown)["primary_location"], location)

        agenda = handle("agenda.show", self.agenda_request(), self.context)
        self.assertTrue(agenda["ok"], agenda)
        self.validators["schedule-agenda-response.schema.json"].validate(agenda)
        self.assertEqual(agenda["entries"][0]["primary_location"], location)

        replay = handle("schedule.create", copy.deepcopy(request), self.context)
        self.assertEqual(replay["effect"], "schedule_create_replay")
        self.assertEqual(replay["primary_location"], location)
        self.assertEqual(self._count("locations"), 1)
        self.assertEqual(self._count("item_locations"), 1)

    def test_reference_create_and_replay_use_the_authored_snapshot(self) -> None:
        self.seed_location("location_shared", label="Shared Venue")
        request = self.event_request("location-reference-create")
        request["item"]["primary_location"] = {
            "mode": "reference",
            "location_id": "location_shared",
        }

        created = handle("schedule.create", request, self.context)

        self.assertTrue(created["ok"], created)
        self.assertEqual(created["primary_location"]["location_id"], "location_shared")
        self.assertEqual(self._count("locations"), 1)
        self.connection.execute(
            "UPDATE locations SET metadata_json = ?, updated_at_utc = ? WHERE location_id = ?",
            ('{"source":"refreshed"}', "2026-08-18T13:00:00Z", "location_shared"),
        )
        self.connection.commit()

        replay = handle("schedule.create", copy.deepcopy(request), self.context)

        self.assertTrue(replay["ok"], replay)
        self.assertEqual(replay["effect"], "schedule_create_replay")
        self.assertEqual(replay["primary_location"], created["primary_location"])

    def test_missing_reference_and_injected_failures_leave_no_partial_location_bundle(self) -> None:
        missing = self.event_request("location-missing-reference")
        missing["item"]["primary_location"] = {
            "mode": "reference",
            "location_id": "location_missing",
        }
        failed = handle("schedule.create", missing, self.context)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"]["code"], "referenced_row_not_found")
        self.assertEqual(failed["error"]["field"], "item.primary_location.location_id")
        self.assertEqual(self._count("coordination_items"), 0)

        injected = self.event_request("location-injected-create")
        injected["item"]["primary_location"] = self.inline_location()
        response = handle(
            "schedule.create",
            injected,
            CommandContext(
                ledger=self.connection,
                transport_metadata={"schedule_create_fail_after": "policies"},
            ),
        )
        self.assertFalse(response["ok"])
        self.assertEqual(self._count("coordination_items"), 0)
        self.assertEqual(self._count("locations"), 0)
        self.assertEqual(self._count("item_locations"), 0)

    def test_location_only_replace_retains_work_and_clear_preserves_history(self) -> None:
        create_request = self.event_request("location-update-source", materialize=True)
        create_request["item"]["primary_location"] = self.inline_location()
        created = handle("schedule.create", create_request, self.context)
        self.assertTrue(created["ok"], created)
        old_location_id = created["primary_location"]["location_id"]
        work_before = self._work_rows(created["item_id"])

        replacement = self.update_request(
            "location-update-replace",
            created["item_id"],
            "1",
            {"primary_location": {"mode": "create", "label": "City Club", "kind": "place"}},
        )
        updated = handle("schedule.update", replacement, self.context)

        self.assertTrue(updated["ok"], updated)
        self.validators["schedule-update-response.schema.json"].validate(updated)
        self.assertEqual(updated["changed_dimensions"], ["primary_location"])
        self.assertTrue(updated["truth_changed"])
        self.assertFalse(updated["work_changed"])
        self.assertEqual(updated["phases"]["provenance"], "not_applicable")
        self.assertEqual(updated["primary_location_change"]["effect"], "replaced")
        self.assertNotEqual(updated["primary_location_change"]["current"]["location_id"], old_location_id)
        self.assertEqual(self._work_rows(created["item_id"]), work_before)
        self.assertEqual(self._count("locations"), 2)

        cleared = handle(
            "schedule.update",
            self.update_request(
                "location-update-clear",
                created["item_id"],
                "2",
                {"primary_location": None},
                updated_at="2026-08-18T14:00:00Z",
            ),
            self.context,
        )
        self.assertTrue(cleared["ok"], cleared)
        self.validators["schedule-update-response.schema.json"].validate(cleared)
        self.assertEqual(cleared["primary_location_change"]["effect"], "cleared")
        self.assertIsNone(cleared["primary_location_change"]["current"])
        self.assertEqual(self._count("locations"), 2)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM item_locations WHERE item_id = ? AND version = 3",
                (created["item_id"],),
            ).fetchone()[0],
            0,
        )

    def test_semantic_noop_and_copy_forward_have_distinct_version_behavior(self) -> None:
        request = self.event_request("location-noop-source")
        request["item"]["primary_location"] = self.inline_location()
        created = handle("schedule.create", request, self.context)
        initial = created["primary_location"]
        audits_before = self._count("audit_log")

        noop = handle(
            "schedule.update",
            self.update_request(
                "location-exact-noop",
                created["item_id"],
                "1",
                {"primary_location": self.inline_location()},
            ),
            self.context,
        )
        self.assertTrue(noop["ok"], noop)
        self.assertEqual(noop["effect"], "schedule_update_noop")
        self.assertEqual(noop["primary_location_change"]["effect"], "retained")
        self.assertEqual(noop["current_version"], "1")
        self.assertEqual(self._count("locations"), 1)
        self.assertEqual(self._count("audit_log"), audits_before)

        copied = handle(
            "schedule.update",
            self.update_request(
                "location-copy-forward",
                created["item_id"],
                "1",
                {
                    "item": {"title": "Golf outing changed"},
                    "primary_location": self.inline_location(),
                },
            ),
            self.context,
        )
        self.assertTrue(copied["ok"], copied)
        self.assertEqual(copied["changed_dimensions"], ["item"])
        self.assertEqual(copied["primary_location_change"]["effect"], "retained")
        current = copied["primary_location_change"]["current"]
        self.assertEqual(current["location_id"], initial["location_id"])
        self.assertNotEqual(current["item_location_id"], initial["item_location_id"])
        self.assertEqual(self._count("locations"), 1)
        self.assertEqual(self._count("item_locations"), 2)

    def test_builder_passes_public_authoring_shape_and_dry_run_writes_nothing(self) -> None:
        builder = {
            "contract_version": "spine.schedule-countdown-builder.v1",
            "command_id": "location-builder",
            "actor_subject_id": "owner",
            "reference_time_utc": "2026-08-18T12:00:00Z",
            "title": "Golf outing",
            "event_detail": {"all_day": False},
            "primary_location": self.inline_location(),
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "system_current"},
            "event_delay_seconds": "7200",
            "reminder_interval_seconds": "1800",
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "whatsapp-owner"},
            },
        }
        self.validators["schedule-countdown-builder-request.schema.json"].validate(builder)

        built = handle("schedule.build", builder, self.context)

        self.assertTrue(built["ok"], built)
        self.validators["schedule-countdown-builder-response.schema.json"].validate(built)
        self.assertEqual(
            built["schedule_create_request"]["item"]["primary_location"],
            self.inline_location(),
        )
        preview = handle(
            "schedule.create",
            built["schedule_create_request"],
            CommandContext(ledger=self.connection, dry_run=True),
        )
        self.assertTrue(preview["ok"], preview)
        self.validators["schedule-create-response.schema.json"].validate(preview)
        self.assertTrue(preview["dry_run"])
        self.assertIn("primary_location", preview)
        self.assertEqual(self._count("coordination_items"), 0)
        self.assertEqual(self._count("locations"), 0)

    def test_reference_update_validation_and_transaction_failure_are_atomic(self) -> None:
        request = self.event_request("location-reference-update-source")
        request["item"]["primary_location"] = self.inline_location()
        created = handle("schedule.create", request, self.context)
        self.seed_location("location_replacement", label="Replacement Venue")
        locations_before = self._count("locations")
        roles_before = self._count("item_locations")

        missing = handle(
            "schedule.update",
            self.update_request(
                "location-reference-update-missing",
                created["item_id"],
                "1",
                {
                    "primary_location": {
                        "mode": "reference",
                        "location_id": "location_missing",
                    }
                },
            ),
            self.context,
        )
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "referenced_row_not_found")
        self.assertEqual(missing["error"]["field"], "patch.primary_location.location_id")
        self.assertEqual(self._current_version(created["item_id"]), 1)

        injected = handle(
            "schedule.update",
            self.update_request(
                "location-reference-update-rollback",
                created["item_id"],
                "1",
                {
                    "primary_location": {
                        "mode": "reference",
                        "location_id": "location_replacement",
                    }
                },
            ),
            CommandContext(
                ledger=self.connection,
                transport_metadata={"schedule_operations_fail_after": "truth"},
            ),
        )
        self.assertFalse(injected["ok"])
        self.assertEqual(injected["error"]["code"], "runtime_failure")
        self.assertEqual(self._current_version(created["item_id"]), 1)
        self.assertEqual(self._count("locations"), locations_before)
        self.assertEqual(self._count("item_locations"), roles_before)

        updated = handle(
            "schedule.update",
            self.update_request(
                "location-reference-update-success",
                created["item_id"],
                "1",
                {
                    "primary_location": {
                        "mode": "reference",
                        "location_id": "location_replacement",
                    }
                },
            ),
            self.context,
        )
        self.assertTrue(updated["ok"], updated)
        self.validators["schedule-update-response.schema.json"].validate(updated)
        self.assertEqual(updated["primary_location_change"]["effect"], "replaced")
        self.assertEqual(
            updated["primary_location_change"]["current"]["location_id"],
            "location_replacement",
        )
        self.assertEqual(self._count("locations"), locations_before)

    def test_runtime_advertises_the_complete_location_contract_family(self) -> None:
        expected = {
            "spine.schedule-primary-location.v1",
            "spine.schedule-primary-location-authoring.v1",
            "spine.schedule-primary-location-view.v1",
            "spine.schedule-primary-location-normalization.v1",
        }
        self.assertTrue(expected.issubset(IMPLEMENTED_CONTRACT_VERSIONS))
        tickerd_info = TickerdCompatibilityInfo(
            package_version="0.2.0",
            capability_id="tickerd.runtime-capabilities.v1",
            descriptor_sha256="215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b",
        )
        with patch("spine.runtime.compatibility.resolve_tickerd_compatibility", return_value=tickerd_info):
            info = handle("system.info", {}, self.context)
        self.assertTrue(expected.issubset(set(info["implemented_contract_versions"])))

    def test_cli_include_parser_accepts_primary_location(self) -> None:
        self.assertEqual(
            _schedule_show_include("policies,primary_location,work"),
            ["policies", "primary_location", "work"],
        )

    def inline_location(self) -> dict[str, object]:
        return {
            "mode": "create",
            "label": "Lakeside Golf Club",
            "kind": "place",
            "address_text": "123 Fairway Road",
            "latitude": "43.7001",
            "longitude": "-79.4163",
            "timezone": "America/Vancouver",
            "provider_ref": "maps:place:lakeside",
        }

    def event_request(self, command_id: str, *, materialize: bool = False) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-create.v1",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "created_at_utc": "2026-08-18T12:10:00Z",
            "item": {
                "item_type": "event",
                "title": "Golf outing",
                "event_detail": {"all_day": False},
            },
            "scheduled_time": {
                "time_basis": "local_instant",
                "local_date": "2026-08-19",
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
                        "start": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-3600",
                        },
                        "stop": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "0",
                        },
                        "stop_inclusive": False,
                        "cadence": {"kind": "fixed_elapsed", "interval_seconds": "1200"},
                    },
                    "late_handling": {"kind": "skip"},
                }
            ],
            "materialization": (
                {
                    "mode": "bounded",
                    "evaluated_at_utc": "2026-08-18T12:10:00Z",
                    "range": {
                        "kind": "item_relative",
                        "start_offset_seconds": "-3600",
                        "end_offset_seconds": "1",
                    },
                    "limit": "100",
                }
                if materialize
                else {"mode": "none"}
            ),
        }

    def update_request(
        self,
        command_id: str,
        item_id: str,
        target_version: str,
        patch: dict[str, object],
        *,
        updated_at: str = "2026-08-18T13:00:00Z",
    ) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-update.v1",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "item_id": item_id,
            "target_version": target_version,
            "updated_at_utc": updated_at,
            "patch": patch,
            "materialization": {"mode": "none"},
        }

    def agenda_request(self) -> dict[str, object]:
        return {
            "contract_version": "spine.schedule-agenda.v1",
            "evaluated_at_utc": "2026-08-18T12:10:00Z",
            "range_start_local": "2026-08-19T00:00:00",
            "range_end_local": "2026-08-20T00:00:00",
            "timezone": "America/Toronto",
            "timezone_database_version": {"kind": "system_current"},
            "include": ["primary_location"],
            "limit": "100",
        }

    def seed_location(self, location_id: str, *, label: str) -> None:
        with self.connection:
            insert_location(
                self.connection,
                location=LocationInput(
                    label=label,
                    kind="place",
                    address_text="1 Shared Street",
                    created_at_utc="2026-08-18T12:02:00Z",
                    updated_at_utc="2026-08-18T12:02:00Z",
                ),
                location_id=location_id,
                default_created_at_utc="2026-08-18T12:02:00Z",
            )

    def _count(self, table: str) -> int:
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _work_rows(self, item_id: str) -> list[tuple[object, ...]]:
        return [
            tuple(row)
            for row in self.connection.execute(
                """
                SELECT work_instance_id, status, reason_code, item_version
                FROM work_instances
                WHERE item_id = ?
                ORDER BY work_instance_id
                """,
                (item_id,),
            ).fetchall()
        ]

    def _current_version(self, item_id: str) -> int:
        return int(
            self.connection.execute(
                "SELECT current_version FROM coordination_items WHERE item_id = ?",
                (item_id,),
            ).fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()
