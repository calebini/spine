from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST = ROOT / "contracts" / "owner-scope-discovery-fixture-manifest.json"


class OwnerScopeContractFixtureTests(unittest.TestCase):
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

    def test_schemas_and_manifest_fixtures_validate(self) -> None:
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)
        manifest = _load(MANIFEST)
        self.assertEqual(
            manifest["schema_version"],
            "spine.owner-scope-discovery-contract-fixtures.v1",
        )
        fixture_ids: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            schema = _load(ROOT / entry["schema"])
            Draft202012Validator(
                schema, registry=self.registry
            ).validate(_load(ROOT / entry["fixture"]))
        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))

    def test_request_is_closed_and_scoped_filters_require_their_owner_kind(self) -> None:
        request = _load(
            ROOT / "tests/fixtures/owner_scope/contracts/request_default_active.json"
        )
        schema = self.schemas["owner-scope-list-request.schema.json"]

        unknown = copy.deepcopy(request)
        unknown["actor_subject_id"] = "anchor"
        self.assertFalse(_valid(schema, unknown, self.registry))

        mismatched = copy.deepcopy(request)
        mismatched["owner_kinds"] = ["system"]
        mismatched["subject_kinds"] = ["person"]
        self.assertFalse(_valid(schema, mismatched, self.registry))

        numeric_limit = copy.deepcopy(request)
        numeric_limit["limit"] = 50
        self.assertFalse(_valid(schema, numeric_limit, self.registry))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid(schema: dict[str, object], value: object, registry: Registry) -> bool:
    return not list(
        Draft202012Validator(schema, registry=registry).iter_errors(value)
    )


if __name__ == "__main__":
    unittest.main()
