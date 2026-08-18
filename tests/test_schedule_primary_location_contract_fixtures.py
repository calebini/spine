from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST_PATH = ROOT / "contracts" / "schedule-primary-location-fixture-manifest.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "schedule_primary_location" / "contracts"


class SchedulePrimaryLocationContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )

    def test_manifest_is_complete_and_every_fixture_validates(self) -> None:
        manifest = _load(MANIFEST_PATH)
        self.assertEqual(
            manifest["schema_version"],
            "spine.schedule-primary-location-contract-fixtures.v1",
        )
        fixture_ids: list[str] = []
        fixture_paths: list[str] = []

        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            fixture_paths.append(entry["fixture"])
            fixture = _load(ROOT / entry["fixture"])
            schema = _load(ROOT / entry["schema"])
            schema_ref = entry.get("schema_ref")
            if schema_ref:
                schema = {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": f'{schema["$id"]}{schema_ref}',
                }
            Draft202012Validator(schema, registry=self.registry).validate(fixture)

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in FIXTURE_DIR.glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_authoring_forms_are_closed_paired_and_coordinate_bounded(self) -> None:
        validator = self._validator_for_ref(
            "schedule-primary-location-types.schema.json", "#/$defs/authoring"
        )
        inline = _load(FIXTURE_DIR / "authoring_inline_place.json")
        reference = _load(FIXTURE_DIR / "authoring_reference.json")
        self.assertTrue(validator.is_valid(inline))
        self.assertTrue(validator.is_valid(reference))

        for invalid in (
            {**inline, "location_id": "caller_forbidden"},
            {**reference, "label": "Forbidden on reference"},
            {**inline, "longitude": None},
            {**inline, "latitude": "91"},
            {**inline, "longitude": "181"},
            {**inline, "latitude": "4.37e1"},
            {**inline, "latitude": 43.7},
            {**inline, "label": "   "},
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(validator.is_valid(invalid))

        unpaired = copy.deepcopy(inline)
        del unpaired["longitude"]
        self.assertFalse(validator.is_valid(unpaired))

    def test_legacy_requests_remain_valid_when_location_is_absent(self) -> None:
        cases = (
            (
                "schedule-create-request.schema.json",
                ROOT / "tests/fixtures/schedule_create/contracts/request_event_repeat_window_materialized.json",
            ),
            (
                "schedule-update-request.schema.json",
                ROOT / "tests/fixtures/schedule_operations/contracts/request_update_recurring_event.json",
            ),
            (
                "schedule-agenda-request.schema.json",
                ROOT / "tests/fixtures/schedule_operations/contracts/request_agenda_local_day.json",
            ),
            (
                "schedule-countdown-builder-request.schema.json",
                ROOT / "tests/fixtures/schedule_operator/countdown_builder_request.json",
            ),
        )
        for schema_name, fixture_path in cases:
            with self.subTest(schema=schema_name):
                self.assertTrue(self._validator(schema_name).is_valid(_load(fixture_path)))

    def test_update_response_location_change_is_closed_and_ordered(self) -> None:
        response = _load(
            ROOT
            / "tests/fixtures/schedule_operations/contracts/response_update_title_with_work_classifications.json"
        )
        location = _load(FIXTURE_DIR / "view_primary_location.json")
        response["changed_dimensions"] = ["item", "primary_location"]
        response["primary_location_change"] = {
            "effect": "created",
            "requested_mode": "reference",
            "previous_location_id": None,
            "current": location,
        }
        self.assertTrue(self._validator("schedule-update-response.schema.json").is_valid(response))
        self.assertTrue(_changed_dimensions_are_canonical(response["changed_dimensions"]))

        out_of_order = copy.deepcopy(response)
        out_of_order["changed_dimensions"] = ["primary_location", "item"]
        # JSON Schema closes membership and uniqueness but cannot economically encode
        # every ordered subset. The explicit semantic oracle rejects divergent order.
        self.assertTrue(
            self._validator("schedule-update-response.schema.json").is_valid(out_of_order)
        )
        self.assertFalse(
            _changed_dimensions_are_canonical(out_of_order["changed_dimensions"])
        )

        impossible = copy.deepcopy(response)
        impossible["primary_location_change"]["effect"] = "cleared"
        self.assertFalse(self._validator("schedule-update-response.schema.json").is_valid(impossible))

    def test_agenda_primary_location_is_required_exactly_when_included(self) -> None:
        validator = self._validator("schedule-agenda-response.schema.json")
        response = _load(
            ROOT / "tests/fixtures/schedule_operations/contracts/response_agenda_local_day.json"
        )
        self.assertTrue(validator.is_valid(response))

        response["included"].append("primary_location")
        self.assertFalse(validator.is_valid(response))
        for entry in response["entries"]:
            entry["primary_location"] = None
        response["entries"][0]["primary_location"] = _load(
            FIXTURE_DIR / "view_primary_location.json"
        )
        self.assertTrue(validator.is_valid(response))

        response["included"].remove("primary_location")
        self.assertFalse(validator.is_valid(response))

    def test_missing_reference_failure_is_phase_seven_and_writes_nothing(self) -> None:
        scenario = _load(FIXTURE_DIR / "failure_update_missing_reference.json")
        self.assertTrue(
            self._validator("schedule-operation-failure-scenario.schema.json").is_valid(scenario)
        )
        self.assertEqual(
            _semantic_failure(scenario),
            {
                "phase": "7",
                "code": "referenced_row_not_found",
                "field": "patch.primary_location.location_id",
            },
        )
        self.assertEqual(scenario["mutation"], "none")
        self.assertFalse(scenario["command_receipt_written"])

    def _validator(self, schema_name: str) -> Draft202012Validator:
        return Draft202012Validator(self.schemas[schema_name], registry=self.registry)

    def _validator_for_ref(self, schema_name: str, fragment: str) -> Draft202012Validator:
        schema = self.schemas[schema_name]
        return Draft202012Validator(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": f'{schema["$id"]}{fragment}',
            },
            registry=self.registry,
        )


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _changed_dimensions_are_canonical(values: list[str]) -> bool:
    order = {
        "item": 0,
        "primary_location": 1,
        "scheduled_time": 2,
        "recurrence": 3,
        "delivery": 4,
        "reminders": 5,
    }
    return values == sorted(values, key=order.__getitem__)


def _semantic_failure(scenario: dict[str, object]) -> dict[str, str]:
    context = scenario["ledger_context"]
    request = scenario["request"]
    assert isinstance(context, dict)
    assert isinstance(request, dict)
    patch = request.get("patch")
    if (
        scenario.get("command") == "schedule.update"
        and isinstance(patch, dict)
        and isinstance(patch.get("primary_location"), dict)
        and patch["primary_location"].get("mode") == "reference"
        and context.get("referenced_location_exists") is False
    ):
        return {
            "phase": "7",
            "code": "referenced_row_not_found",
            "field": "patch.primary_location.location_id",
        }
    raise AssertionError("scenario is not covered by the primary-location failure oracle")


if __name__ == "__main__":
    unittest.main()
