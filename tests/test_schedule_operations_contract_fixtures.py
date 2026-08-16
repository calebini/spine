from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST_PATH = ROOT / "contracts" / "schedule-operations-fixture-manifest.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "schedule_operations" / "contracts"


class ScheduleOperationsContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )

    def test_manifest_is_complete_and_all_structural_fixtures_validate(self) -> None:
        manifest = _load(MANIFEST_PATH)
        self.assertEqual(manifest["schema_version"], "spine.schedule-operations-contract-fixtures.v1")
        self.assertEqual(manifest["fixture_scope"], "structural_examples")

        fixture_ids: list[str] = []
        fixture_paths: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            fixture_paths.append(entry["fixture"])
            schema = _load(ROOT / entry["schema"])
            fixture = _load(ROOT / entry["fixture"])
            Draft202012Validator(schema, registry=self.registry).validate(fixture)

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in FIXTURE_DIR.glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_update_schema_rejects_partial_intent_identity_and_hidden_fields(self) -> None:
        schema = self.schemas["schedule-update-request.schema.json"]
        request = _load(FIXTURE_DIR / "request_update_recurring_event.json")

        partial_identity = copy.deepcopy(request)
        del partial_identity["patch"]["reminders"][0]["notification_policy_id"]
        self.assertFalse(_valid(schema, partial_identity, self.registry))

        hidden_route = copy.deepcopy(request)
        hidden_route["patch"]["delivery"]["target"]["target_ref"] = "not-canonical"
        self.assertFalse(_valid(schema, hidden_route, self.registry))

        cross_type = copy.deepcopy(request)
        cross_type["patch"]["item"]["event_detail"] = {"visibility": "private"}
        cross_type["patch"]["item"]["task_detail"] = {"priority": "high"}
        self.assertFalse(_valid(schema, cross_type, self.registry))

    def test_agenda_and_cancel_schemas_are_closed(self) -> None:
        agenda_schema = self.schemas["schedule-agenda-request.schema.json"]
        agenda = _load(FIXTURE_DIR / "request_agenda_local_day.json")
        agenda["raw_sql"] = "SELECT *"
        self.assertFalse(_valid(agenda_schema, agenda, self.registry))

        cancel_schema = self.schemas["schedule-cancel-request.schema.json"]
        cancel = _load(FIXTURE_DIR / "request_cancel_event.json")
        cancel["deliver"] = True
        self.assertFalse(_valid(cancel_schema, cancel, self.registry))

    def test_proposed_contracts_are_not_declared_as_implemented(self) -> None:
        proposed = {
            "spine.schedule-operations-normalization.v1",
            "spine.schedule-agenda.v1",
            "spine.schedule-agenda-response.v1",
            "spine.schedule-update.v1",
            "spine.schedule-update-response.v1",
            "spine.schedule-update-receipt.v1",
            "spine.schedule-cancel.v1",
            "spine.schedule-cancel-response.v1",
            "spine.schedule-cancel-receipt.v1",
        }
        self.assertTrue(proposed.isdisjoint(IMPLEMENTED_CONTRACT_VERSIONS))


def _valid(schema: dict[str, object], value: dict[str, object], registry: Registry) -> bool:
    return not list(Draft202012Validator(schema, registry=registry).iter_errors(value))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
