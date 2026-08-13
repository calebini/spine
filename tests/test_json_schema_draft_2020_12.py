from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"


class Draft202012ContractValidationTests(unittest.TestCase):
    def test_every_public_schema_and_manifest_fixture_validates_with_reference_tooling(self) -> None:
        schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)

        for manifest_name in (
            "command-fixture-manifest.json",
            "recurrence-fixture-manifest.json",
            "notification-fixture-manifest.json",
            "schedule-create-fixture-manifest.json",
        ):
            manifest = _load(ROOT / "contracts" / manifest_name)
            for entry in manifest["fixtures"]:
                schema = _load(ROOT / entry["schema"])
                fixture = _load(ROOT / entry["fixture"])
                Draft202012Validator(schema, registry=registry).validate(fixture)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
