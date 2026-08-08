import unittest
from pathlib import Path

from tests.test_recurrence_contract_fixtures import (
    _collect_refs,
    _is_valid,
    _load_json,
    _resolve_pointer,
    _validate,
)

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "contracts" / "notification-fixture-manifest.json"
SCHEMA_DIR = ROOT / "contracts" / "schemas"


class NotificationContractFixtureTests(unittest.TestCase):
    def test_manifest_is_complete_and_every_fixture_matches_its_schema(self) -> None:
        manifest = _load_json(MANIFEST_PATH)
        schemas = _schemas()

        self.assertEqual(manifest["schema_version"], "spine.notification-contract-fixtures.v1")
        self.assertEqual(manifest["fixture_scope"], "structural_examples")
        fixture_ids: list[str] = []
        fixture_paths: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            fixture_paths.append(entry["fixture"])
            schema_path = ROOT / entry["schema"]
            fixture_path = ROOT / entry["fixture"]
            self.assertTrue(schema_path.is_file(), entry)
            self.assertTrue(fixture_path.is_file(), entry)
            _validate(
                _load_json(fixture_path),
                schemas[schema_path.name],
                schemas[schema_path.name],
                schemas,
                path="$fixture",
            )

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in (ROOT / "tests/fixtures/notifications/contracts").glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_schema_family_has_stable_ids_and_resolvable_references(self) -> None:
        schemas = _schemas()
        self.assertEqual(
            set(schemas),
            {
                "notification-authoring.schema.json",
                "notification-command.schema.json",
                "notification-opportunity-response.schema.json",
                "notification-policy.schema.json",
                "notification-types.schema.json",
            },
        )
        schema_ids = [schema["$id"] for schema in schemas.values()]
        self.assertEqual(len(schema_ids), len(set(schema_ids)))
        for name, schema in schemas.items():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            for ref in _collect_refs(schema):
                if ref.startswith("#"):
                    _resolve_pointer(schema, ref[1:])
                    continue
                file_name, _, fragment = ref.partition("#")
                self.assertIn(file_name, schemas, f"{name}: {ref}")
                if fragment:
                    _resolve_pointer(schemas[file_name], fragment)

    def test_initial_fixtures_cover_schedule_forms_scopes_and_commands(self) -> None:
        manifest = _load_json(MANIFEST_PATH)
        fixtures = {
            entry["fixture_id"]: _load_json(ROOT / entry["fixture"])
            for entry in manifest["fixtures"]
        }
        authoring = [value for key, value in fixtures.items() if key.startswith("authoring.")]
        self.assertEqual({value["schedule"]["kind"] for value in authoring}, {"once", "offsets", "repeat_window"})
        self.assertEqual(
            {value["target"]["application_scope"] for value in authoring},
            {"item", "each_occurrence", "selected_occurrence"},
        )
        self.assertEqual(
            {fixtures[key]["command"] for key in fixtures if key.startswith("command.")},
            {
                "reminder.create",
                "reminder.edit",
                "reminder.disable",
                "notification.opportunities",
                "notification_work.materialize",
            },
        )
        response = fixtures["response.every_hour_six_hours_before"]
        self.assertEqual(len(response["opportunities"]), 6)
        self.assertEqual(
            [value["eligible_at_utc"] for value in response["opportunities"]],
            [
                "2026-08-08T12:00:00Z",
                "2026-08-08T13:00:00Z",
                "2026-08-08T14:00:00Z",
                "2026-08-08T15:00:00Z",
                "2026-08-08T16:00:00Z",
                "2026-08-08T17:00:00Z",
            ],
        )

    def test_structural_contract_rejects_ambiguous_or_incomplete_shapes(self) -> None:
        schemas = _schemas()
        authoring_schema = schemas["notification-authoring.schema.json"]
        policy_schema = schemas["notification-policy.schema.json"]
        response_schema = schemas["notification-opportunity-response.schema.json"]

        selected_without_key = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/authoring_each_occurrence_six_hours_before.json"
        )
        selected_without_key["target"]["application_scope"] = "selected_occurrence"
        self.assertFalse(_is_valid(selected_without_key, authoring_schema, authoring_schema, schemas, "$fixture"))

        unbounded_repeat = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/authoring_every_hour_six_hours_before.json"
        )
        del unbounded_repeat["schedule"]["stop"]
        self.assertFalse(_is_valid(unbounded_repeat, authoring_schema, authoring_schema, schemas, "$fixture"))

        illegal_daily_selector = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/authoring_every_day_0800_until_event.json"
        )
        illegal_daily_selector["schedule"]["cadence"]["by_weekday"] = ["MO"]
        self.assertFalse(_is_valid(illegal_daily_selector, authoring_schema, authoring_schema, schemas, "$fixture"))

        conflicting_recipient = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/policy_every_hour_six_hours_before.json"
        )
        conflicting_recipient["recipient_group_id"] = "group_example"
        self.assertFalse(_is_valid(conflicting_recipient, policy_schema, policy_schema, schemas, "$fixture"))

        partial_recipient_edit = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/command_reminder_edit.json"
        )
        partial_recipient_edit["request"]["patch"] = {"recipient_group_id": "group_example"}
        command_schema = schemas["notification-command.schema.json"]
        self.assertFalse(_is_valid(partial_recipient_edit, command_schema, command_schema, schemas, "$fixture"))

        non_actionable_without_reason = _load_json(
            ROOT / "tests/fixtures/notifications/contracts/response_every_hour_six_hours_before.json"
        )
        non_actionable_without_reason["opportunities"][0]["actionable"] = False
        self.assertFalse(_is_valid(non_actionable_without_reason, response_schema, response_schema, schemas, "$fixture"))


def _schemas() -> dict[str, dict[str, object]]:
    return {
        path.name: _load_json(path)
        for path in sorted(SCHEMA_DIR.glob("notification-*.schema.json"))
    }


if __name__ == "__main__":
    unittest.main()
