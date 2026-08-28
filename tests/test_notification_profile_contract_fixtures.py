from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST = ROOT / "contracts" / "notification-profile-fixture-manifest.json"


class NotificationProfileContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {
            path.name: _load(path)
            for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
        }
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema))
            for schema in cls.schemas.values()
        )

    def test_all_schemas_are_valid_and_manifest_fixtures_validate(self) -> None:
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)
        manifest = _load(MANIFEST)
        self.assertEqual(
            manifest["schema_version"],
            "spine.notification-profile-contract-fixtures.v1",
        )
        fixture_ids: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            schema = _load(ROOT / entry["schema"])
            schema_ref = entry.get("schema_ref")
            if schema_ref is not None:
                schema = {"$ref": f"{schema['$id']}{schema_ref}"}
            Draft202012Validator(
                schema, registry=self.registry
            ).validate(_load(ROOT / entry["fixture"]))
        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))

    def test_v2_create_rejects_v1_reminders_and_default_without_archetype(self) -> None:
        request = _load(
            ROOT
            / "tests/fixtures/notification_profiles/contracts/request_schedule_create_profile_default.json"
        )
        schema = self.schemas["schedule-create-request.schema.json"]
        with_reminders = copy.deepcopy(request)
        with_reminders["reminders"] = []
        self.assertFalse(_valid(schema, with_reminders, self.registry))

        without_archetype = copy.deepcopy(request)
        del without_archetype["item"]["archetype"]
        self.assertFalse(_valid(schema, without_archetype, self.registry))

    def test_v2_update_actions_are_closed(self) -> None:
        request = _load(
            ROOT
            / "tests/fixtures/notification_profiles/contracts/request_schedule_update_profile_upgrade.json"
        )
        schema = self.schemas["schedule-update-request.schema.json"]
        self.assertTrue(_valid(schema, request, self.registry))

        hidden_follow = copy.deepcopy(request)
        hidden_follow["patch"]["notification_plan"]["follow_profile"] = True
        self.assertFalse(_valid(schema, hidden_follow, self.registry))

        v1_reminders = copy.deepcopy(request)
        v1_reminders["patch"]["reminders"] = []
        self.assertFalse(_valid(schema, v1_reminders, self.registry))

    def test_system_owned_management_creation_is_structural_but_runtime_forbidden(self) -> None:
        request = _load(
            ROOT
            / "tests/fixtures/notification_profiles/contracts/request_notification_profile_create.json"
        )
        request["owner"] = {"owner_kind": "system"}
        schema = {
            "$ref": (
                self.schemas["notification-profile-commands.schema.json"]["$id"]
                + "#/$defs/profileCreate"
            )
        }
        self.assertTrue(_valid(schema, request, self.registry))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid(
    schema: dict[str, object], value: object, registry: Registry
) -> bool:
    return not list(
        Draft202012Validator(schema, registry=registry).iter_errors(value)
    )


if __name__ == "__main__":
    unittest.main()
