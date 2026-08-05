import json
import re
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "contracts" / "recurrence-fixture-manifest.json"
SCHEMA_DIR = ROOT / "contracts" / "schemas"


class RecurrenceContractFixtureTests(unittest.TestCase):
    def test_manifest_is_complete_and_every_fixture_matches_its_schema(self) -> None:
        manifest = _load_json(MANIFEST_PATH)
        schemas = {
            path.name: _load_json(path)
            for path in sorted(SCHEMA_DIR.glob("recurrence-*.schema.json"))
        }

        self.assertEqual(manifest["schema_version"], "spine.recurrence-contract-fixtures.v1")
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
            schema = schemas[schema_path.name]
            fixture = _load_json(fixture_path)
            _validate(fixture, schema, schema, schemas, path="$fixture")

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in (ROOT / "tests/fixtures/recurrence/contracts").glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_schema_family_has_stable_ids_and_resolvable_file_references(self) -> None:
        schemas = {
            path.name: _load_json(path)
            for path in sorted(SCHEMA_DIR.glob("recurrence-*.schema.json"))
        }
        self.assertEqual(
            set(schemas),
            {
                "recurrence-authoring.schema.json",
                "recurrence-command.schema.json",
                "recurrence-occurrence-response.schema.json",
                "recurrence-set.schema.json",
                "recurrence-types.schema.json",
            },
        )
        schema_ids = [schema["$id"] for schema in schemas.values()]
        self.assertEqual(len(schema_ids), len(set(schema_ids)))
        for name, schema in schemas.items():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIsInstance(schema["title"], str)
            for ref in _collect_refs(schema):
                if ref.startswith("#"):
                    _resolve_pointer(schema, ref[1:])
                    continue
                file_name, _, fragment = ref.partition("#")
                self.assertIn(file_name, schemas, f"{name}: {ref}")
                if fragment:
                    _resolve_pointer(schemas[file_name], fragment)

    def test_initial_fixtures_cover_flexible_authoring_and_all_recurrence_commands(self) -> None:
        manifest = _load_json(MANIFEST_PATH)
        fixtures = {
            entry["fixture_id"]: _load_json(ROOT / entry["fixture"])
            for entry in manifest["fixtures"]
        }
        authoring = [payload for key, payload in fixtures.items() if key.startswith("authoring.")]
        self.assertEqual({payload["time_basis"] for payload in authoring}, {"local_date", "local_instant", "instant_utc"})
        self.assertTrue(any(rule["frequency"] == "WEEKLY" for payload in authoring for rule in payload["rules"]))
        self.assertTrue(any(rule["frequency"] == "MONTHLY" for payload in authoring for rule in payload["rules"]))
        every_three_days = fixtures["authoring.every_three_days_0800"]
        self.assertEqual(every_three_days["rules"][0]["interval"], "3")
        self.assertEqual(every_three_days["rules"][0]["seed"], "2026-08-03T08:00:00")

        command_fixtures = {
            payload["command"]
            for key, payload in fixtures.items()
            if key.startswith("command.")
        }
        self.assertEqual(
            command_fixtures,
            {
                "recurrence.instance.add",
                "recurrence.instance.remove",
                "recurrence.instance.override",
                "recurrence.series.edit",
                "occurrence_provenance.regenerate",
            },
        )

        response = fixtures["response.every_three_days_page"]
        self.assertEqual(response["response_contract"], "spine.item-occurrences.recurrence.v1")
        normalized = fixtures["normalized.every_three_days_0800"]
        normalized_segment_ids = {segment["segment_id"] for segment in normalized["segments"]}
        self.assertTrue(
            all(
                occurrence["segment_id"] in normalized_segment_ids
                for occurrence in response["occurrences"]
            )
        )
        self.assertNotIn("recurrence_rule", response)
        self.assertNotIn("recurrence_field", response)
        self.assertNotIn("truncated", response)
        self.assertTrue(all("ordinal" not in occurrence for occurrence in response["occurrences"]))

    def test_closed_schema_rules_reject_cross_frequency_and_scope_leakage(self) -> None:
        schemas = {
            path.name: _load_json(path)
            for path in sorted(SCHEMA_DIR.glob("recurrence-*.schema.json"))
        }
        manifest = _load_json(MANIFEST_PATH)
        fixtures = {
            entry["fixture_id"]: _load_json(ROOT / entry["fixture"])
            for entry in manifest["fixtures"]
        }

        invalid_daily = deepcopy(fixtures["authoring.every_three_days_0800"])
        invalid_daily["rules"][0]["by_weekday"] = ["MO"]
        self.assertFalse(
            _is_valid(
                invalid_daily,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$invalid_daily",
            )
        )

        invalid_utc = deepcopy(fixtures["authoring.daily_fixed_utc"])
        invalid_utc["timezone"] = "UTC"
        self.assertFalse(
            _is_valid(
                invalid_utc,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$invalid_utc",
            )
        )

        invalid_whole_series = deepcopy(fixtures["command.series_edit"])
        invalid_whole_series["request"]["edit_scope"] = "whole_series"
        del invalid_whole_series["request"]["target_occurrence_key"]
        self.assertFalse(
            _is_valid(
                invalid_whole_series,
                schemas["recurrence-command.schema.json"],
                schemas["recurrence-command.schema.json"],
                schemas,
                "$invalid_whole_series",
            )
        )

        invalid_following_segment = deepcopy(fixtures["command.series_edit"])
        invalid_following_segment["request"]["recurrence_patch"]["rules"][0]["segment_id"] = "segment_not_caller_selectable"
        self.assertFalse(
            _is_valid(
                invalid_following_segment,
                schemas["recurrence-command.schema.json"],
                schemas["recurrence-command.schema.json"],
                schemas,
                "$invalid_following_segment",
            )
        )

    def test_audit_alignment_rules_are_executable(self) -> None:
        schemas = {
            path.name: _load_json(path)
            for path in sorted(SCHEMA_DIR.glob("recurrence-*.schema.json"))
        }
        manifest = _load_json(MANIFEST_PATH)
        fixtures = {
            entry["fixture_id"]: _load_json(ROOT / entry["fixture"])
            for entry in manifest["fixtures"]
        }

        response_schema = schemas["recurrence-occurrence-response.schema.json"]
        response = fixtures["response.every_three_days_page"]
        required_occurrence_fields = {
            "recurrence_set_id",
            "segment_id",
            "origin_kind",
            "range_basis",
            "lifecycle",
        }
        for occurrence in response["occurrences"]:
            self.assertTrue(required_occurrence_fields <= occurrence.keys())
            self.assertEqual(
                set(occurrence["timezone_resolution"]),
                {
                    "timezone",
                    "timezone_database_version",
                    "resolution_kind",
                    "local_datetime",
                    "utc_instant",
                    "offset_seconds",
                },
            )

        missing_occurrence_fact = deepcopy(response)
        del missing_occurrence_fact["occurrences"][0]["segment_id"]
        self.assertFalse(
            _is_valid(
                missing_occurrence_fact,
                response_schema,
                response_schema,
                schemas,
                "$missing_occurrence_fact",
            )
        )

        invalid_diagnostic = deepcopy(response)
        invalid_diagnostic["diagnostics"] = [
            {
                "severity": "error",
                "diagnostic_code": "implementation_note",
                "field": "runtime",
            }
        ]
        self.assertFalse(
            _is_valid(
                invalid_diagnostic,
                response_schema,
                response_schema,
                schemas,
                "$invalid_diagnostic",
            )
        )

        valid_dst_diagnostic = deepcopy(response)
        valid_dst_diagnostic["diagnostics"] = [
            {
                "severity": "warning",
                "diagnostic_code": "dst_nonexistent_omitted",
                "field": "timezone_resolution",
                "scheduled_fact": "2026-03-08T02:30:00",
                "source_id": "recurrence_rule_dst_example",
                "timezone_resolution": {
                    "timezone": "America/Denver",
                    "timezone_database_version": "2026a",
                    "resolution_kind": "nonexistent_omitted",
                    "local_datetime": "2026-03-08T02:30:00",
                },
            }
        ]
        self.assertTrue(
            _is_valid(
                valid_dst_diagnostic,
                response_schema,
                response_schema,
                schemas,
                "$valid_dst_diagnostic",
            )
        )

        override_command = fixtures["command.instance_override"]
        self.assertNotIn("override", override_command["request"])
        self.assertIn("expressed_scheduled_fact", override_command["request"])
        nested_override = deepcopy(override_command)
        request = nested_override["request"]
        request["override"] = {
            "expressed_scheduled_fact": request.pop("expressed_scheduled_fact"),
            "common_detail_patch": request.pop("common_detail_patch"),
        }
        self.assertFalse(
            _is_valid(
                nested_override,
                schemas["recurrence-command.schema.json"],
                schemas["recurrence-command.schema.json"],
                schemas,
                "$nested_override",
            )
        )

        mixed_monthly = deepcopy(fixtures["authoring.monthly_last_day"])
        mixed_monthly["rules"][0]["by_weekday"] = ["MO"]
        self.assertFalse(
            _is_valid(
                mixed_monthly,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$mixed_monthly",
            )
        )

        positional_without_weekday = deepcopy(fixtures["authoring.monthly_last_day"])
        del positional_without_weekday["rules"][0]["by_month_day"]
        positional_without_weekday["rules"][0]["by_set_position"] = ["-1"]
        self.assertFalse(
            _is_valid(
                positional_without_weekday,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$positional_without_weekday",
            )
        )

        unsegmented_with_label = deepcopy(fixtures["authoring.every_three_days_0800"])
        unsegmented_with_label["rules"][0]["segment_label"] = "primary"
        self.assertFalse(
            _is_valid(
                unsegmented_with_label,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$unsegmented_with_label",
            )
        )

        segmented_without_label = deepcopy(fixtures["authoring.every_three_days_0800"])
        segmented_without_label["segments"] = [
            {"segment_label": "primary", "active_start": "2026-08-03T08:00:00"}
        ]
        self.assertFalse(
            _is_valid(
                segmented_without_label,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$segmented_without_label",
            )
        )
        segmented_without_label["rules"][0]["segment_label"] = "primary"
        self.assertTrue(
            _is_valid(
                segmented_without_label,
                schemas["recurrence-authoring.schema.json"],
                schemas["recurrence-authoring.schema.json"],
                schemas,
                "$segmented_with_label",
            )
        )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _collect_refs(value: Any) -> list[str]:
    if isinstance(value, dict):
        refs = [value["$ref"]] if "$ref" in value else []
        for child in value.values():
            refs.extend(_collect_refs(child))
        return refs
    if isinstance(value, list):
        refs: list[str] = []
        for child in value:
            refs.extend(_collect_refs(child))
        return refs
    return []


def _resolve_pointer(document: Any, pointer: str) -> Any:
    value = document
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise AssertionError(f"invalid JSON pointer: {pointer}")
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    return value


def _validate(
    instance: Any,
    schema: Any,
    root_schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    *,
    path: str,
) -> None:
    if schema is True:
        return
    if schema is False:
        raise AssertionError(f"{path}: rejected by false schema")
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#"):
            resolved = _resolve_pointer(root_schema, ref[1:])
            _validate(instance, resolved, root_schema, schemas, path=path)
            return
        file_name, _, fragment = ref.partition("#")
        external = schemas[file_name]
        resolved = _resolve_pointer(external, fragment) if fragment else external
        _validate(instance, resolved, external, schemas, path=path)
        return

    if "allOf" in schema:
        for child in schema["allOf"]:
            _validate(instance, child, root_schema, schemas, path=path)
    if "anyOf" in schema:
        if not any(_is_valid(instance, child, root_schema, schemas, path) for child in schema["anyOf"]):
            raise AssertionError(f"{path}: no anyOf branch matched")
    if "oneOf" in schema:
        matches = sum(_is_valid(instance, child, root_schema, schemas, path) for child in schema["oneOf"])
        if matches != 1:
            raise AssertionError(f"{path}: expected one oneOf match, got {matches}")
    if "not" in schema and _is_valid(instance, schema["not"], root_schema, schemas, path):
        raise AssertionError(f"{path}: matched forbidden schema")
    if "if" in schema:
        branch = "then" if _is_valid(instance, schema["if"], root_schema, schemas, path) else "else"
        if branch in schema:
            _validate(instance, schema[branch], root_schema, schemas, path=path)

    if "const" in schema and instance != schema["const"]:
        raise AssertionError(f"{path}: expected {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise AssertionError(f"{path}: {instance!r} not in enum")
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_has_type(instance, type_name) for type_name in allowed):
            raise AssertionError(f"{path}: expected type {allowed}, got {type(instance).__name__}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise AssertionError(f"{path}: string shorter than minLength")
        if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
            raise AssertionError(f"{path}: {instance!r} does not match {schema['pattern']!r}")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [field for field in required if field not in instance]
        if missing:
            raise AssertionError(f"{path}: missing required fields {missing}")
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            raise AssertionError(f"{path}: too few properties")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], root_schema, schemas, path=f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise AssertionError(f"{path}: unexpected property {key}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise AssertionError(f"{path}: too few items")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(value, sort_keys=True, separators=(",", ":")) for value in instance]
            if len(encoded) != len(set(encoded)):
                raise AssertionError(f"{path}: duplicate array items")
        if "items" in schema:
            for index, value in enumerate(instance):
                _validate(value, schema["items"], root_schema, schemas, path=f"{path}[{index}]")


def _is_valid(
    instance: Any,
    schema: Any,
    root_schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    path: str,
) -> bool:
    try:
        _validate(instance, schema, root_schema, schemas, path=path)
    except AssertionError:
        return False
    return True


def _has_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    raise AssertionError(f"unsupported schema type in fixture validator: {type_name}")


if __name__ == "__main__":
    unittest.main()
