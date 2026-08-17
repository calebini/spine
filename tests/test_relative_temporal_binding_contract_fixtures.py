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
MANIFEST = ROOT / "contracts" / "relative-temporal-binding-fixture-manifest.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "relative_temporal_bindings" / "contracts"


class RelativeTemporalBindingContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )

    def test_manifest_is_complete_and_fixtures_validate(self) -> None:
        manifest = _load(MANIFEST)
        self.assertEqual(manifest["schema_version"], "spine.relative-temporal-binding-contract-fixtures.v1")
        paths: list[str] = []
        identities: list[str] = []
        for entry in manifest["fixtures"]:
            paths.append(entry["fixture"])
            identities.append(entry["fixture_id"])
            Draft202012Validator(
                _load(ROOT / entry["schema"]), registry=self.registry
            ).validate(_load(ROOT / entry["fixture"]))
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(
            sorted(path.as_posix() for path in FIXTURE_DIR.glob("*.json")),
            sorted((ROOT / path).as_posix() for path in paths),
        )

    def test_create_schema_enforces_explicit_binding_and_delivery_conditions(self) -> None:
        schema = self.schemas["schedule-related-task-create-request.schema.json"]
        snapshot = _load(FIXTURE_DIR / "request_create_snapshot_task.json")
        follow = _load(FIXTURE_DIR / "request_create_follow_selected_occurrence.json")

        missing_binding = copy.deepcopy(snapshot)
        del missing_binding["temporal_binding"]
        self.assertFalse(_valid(schema, missing_binding, self.registry))

        snapshot_terminal_behavior = copy.deepcopy(snapshot)
        snapshot_terminal_behavior["temporal_binding"]["source_terminal_behavior"] = "cancel_target"
        self.assertFalse(_valid(schema, snapshot_terminal_behavior, self.registry))

        missing_delivery = copy.deepcopy(follow)
        del missing_delivery["delivery"]
        self.assertFalse(_valid(schema, missing_delivery, self.registry))

        selected_without_selector = copy.deepcopy(follow)
        del selected_without_selector["source"]["target_occurrence_selector"]
        self.assertFalse(_valid(schema, selected_without_selector, self.registry))

    def test_list_requires_a_bounded_scope_and_terminal_cursor_is_null(self) -> None:
        request_schema = self.schemas["schedule-binding-list-request.schema.json"]
        self.assertFalse(_valid(request_schema, {"contract_version": "spine.schedule-binding-list.v1"}, self.registry))
        self.assertTrue(
            _valid(
                request_schema,
                {"contract_version": "spine.schedule-binding-list.v1", "bounded": True},
                self.registry,
            )
        )

        response_schema = self.schemas["schedule-binding-list-response.schema.json"]
        response = _load(FIXTURE_DIR / "response_binding_list_empty.json")
        response["has_more"] = True
        self.assertFalse(_valid(response_schema, response, self.registry))

    def test_complete_contract_family_is_advertised(self) -> None:
        required = {
            "spine.relative-temporal-binding.v1",
            "spine.relative-temporal-binding-normalization.v1",
            "spine.normalized-temporal-binding-revision-hash.v1",
            "spine.temporal-binding-catalog.v1",
            "spine.schedule-related-task-create.v1",
            "spine.schedule-related-task-create-response.v1",
            "spine.schedule-related-task-create-receipt.v1",
            "spine.schedule-binding-list.v1",
            "spine.schedule-binding-list-response.v1",
            "spine.schedule-binding-list-cursor.v1",
            "spine.schedule-binding-reconcile.v1",
            "spine.schedule-binding-reconcile-response.v1",
            "spine.schedule-binding-reconcile-receipt.v1",
        }
        self.assertTrue(required.issubset(IMPLEMENTED_CONTRACT_VERSIONS))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid(schema: dict[str, object], value: dict[str, object], registry: Registry) -> bool:
    return not list(Draft202012Validator(schema, registry=registry).iter_errors(value))


if __name__ == "__main__":
    unittest.main()
