"""Source-only contracts and reference oracles; not a runtime feature test."""

from __future__ import annotations

import copy
import json
import re
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.hashing import command_derived_id, hash_canonical_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/notification_rendering_definitions/contracts"
PREFIX = "notification-rendering-definition-"
TYPES = PREFIX + "types.schema.json"
COMMANDS = PREFIX + "commands.schema.json"
RESPONSES = PREFIX + "responses.schema.json"
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=ValueError)
def canonical_utc_timestamp(value):
    if not isinstance(value, str):
        return True
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return True


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_text(value):
    result = re.sub(r"\s+", " ", value.strip())
    if not result or any(unicodedata.category(char).startswith("C") for char in result):
        raise ValueError("invalid_text")
    return result


def reference_render(case):
    """Apply Section 4 only, after the fixture's simulated resolver decisions."""
    outcomes, suffix = [], ""
    for field in case["fields"]:
        outcome = None
        if not field["selected"]:
            outcome = "not_selected"
        elif case["authorization_state"] != "active":
            outcome = "disclosure_unavailable"
        elif "unavailable" in field:
            outcome = field["unavailable"]
        else:
            value = field["value"]
            if field["field_type"] == "boolean":
                value = "true" if value else "false"
            try:
                value = normalized_text(value)
            except ValueError:
                outcome = "invalid_text"
            if outcome is None:
                if len(value) > 120:
                    outcome = "value_too_long"
                else:
                    outcome = "included"
                    suffix += f" · {field['label']}: {value}"
        outcomes.append({"selection_key": field["selection_key"], "outcome": outcome})
    kind = "details_included" if suffix else "ordinary_only"
    if len(case["base_body"] + suffix) > 1024:
        suffix, kind = "", "suffix_overflow"
        for outcome in outcomes:
            if outcome["outcome"] == "included":
                outcome["outcome"] = "suffix_overflow"
    return {"body_text": case["base_body"] + suffix, "outcome": kind, "selection_outcomes": outcomes}


def reference_disclosure(case):
    """Check all requested details, not permissions or live ledger eligibility."""
    scope, facts = case["scope"], case["facts"]
    origin = facts["origin"]
    use = (
        {"kind": "profile", "notification_profile_id": origin["notification_profile_id"]}
        if origin["kind"] in ("profile_template", "profile_replacement")
        else {"kind": "direct_policy"}
    )
    return (
        case["authorization_state"] == "active"
        and all(scope[key] == facts[key] for key in ("item_owner", "definition", "destination"))
        and scope["use_scope"] == use
        and set(facts["effective_selection_keys"]) <= set(scope["approved_selection_keys"])
        and set(facts["location_ids"]) <= set(scope["permitted_location_ids"])
    )


class RenderingDefinitionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {p.name: load(p) for p in (ROOT / "contracts/schemas").glob("*.schema.json")}
        cls.resources = Registry().with_resources(
            (value["$id"], Resource.from_contents(value)) for value in cls.schemas.values()
        )
        cls.manifest = load(ROOT / "contracts/notification-rendering-definition-fixture-manifest.json")
        cls.registry = load(ROOT / "contracts/notification-rendering-definition-contract-registry.v1.json")
        cls.vectors = load(FIXTURES / "reference_vectors.json")

    def validator(self, name, definition=None):
        schema = self.schemas[name]
        if definition:
            schema = {"$ref": schema["$id"] + "#/$defs/" + definition}
        return Draft202012Validator(schema, registry=self.resources, format_checker=FORMATS)

    def test_schemas_manifest_and_all_fixtures(self):
        for name, schema in self.schemas.items():
            if name.startswith(PREFIX):
                Draft202012Validator.check_schema(schema)
        self.assertEqual(self.manifest["status"], "implemented_local")
        ids, paths = [], set()
        for entry in self.manifest["fixtures"]:
            with self.subTest(fixture=entry["fixture_id"]):
                ids.append(entry["fixture_id"])
                paths.add(ROOT / entry["fixture"])
                definition = entry.get("schema_ref", "").removeprefix("#/$defs/") or None
                self.validator(Path(entry["schema"]).name, definition).validate(load(ROOT / entry["fixture"]))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(paths, set(FIXTURES.glob("*.json")))

    def test_registry_has_exact_command_shapes_and_local_runtime_mapping(self):
        self.assertEqual(self.registry["status"], "implemented_local")
        commands = self.schemas[COMMANDS]["$defs"]
        self.assertEqual(set(commands), set(self.registry["commands"]))
        self.assertEqual(len(commands), 9)
        for name, value in self.registry["commands"].items():
            self.assertEqual(value["exposure"], "trusted_local")
            self.assertEqual(commands[name]["properties"]["contract_version"]["const"], value["contract_version"])
            for field in ("request_schema", "response_schema"):
                path, fragment = value[field].split("#/$defs/")
                self.assertIn(fragment, load(ROOT / path)["$defs"])
        runtime_registry = (ROOT / "src/spine/commands/registry.py").read_text()
        for name in commands:
            self.assertIn(f'"{name}"', runtime_registry)
        self.assertTrue(self.registry["implementation_gates"])

    def test_closed_command_shapes_and_bounds(self):
        request = load(FIXTURES / "request_definition_create.json")
        validator = self.validator(COMMANDS, "notification_rendering_definition.create")
        for name, change in (
            ("unknown_field", lambda r: r.update(script="eval")),
            ("context_flag_in_request", lambda r: r.update(dry_run=True)),
            ("wrong_version", lambda r: r.update(contract_version="spine.notification-profiles.v1")),
            ("too_many_fields", lambda r: r["revision"].update(selections=r["revision"]["selections"] * 3)),
            ("long_label", lambda r: r["revision"]["selections"][0].update(label="x" * 41)),
            ("subject_reference", lambda r: r["revision"]["selections"][0].update(projection="subject_name")),
            ("wildcard", lambda r: r["revision"]["selections"][0].update(field_key="*")),
            ("invalid_date", lambda r: r.update(action_timestamp_utc="2026-02-31T00:00:00Z")),
        ):
            with self.subTest(case=name):
                changed = copy.deepcopy(request)
                change(changed)
                self.assertFalse(validator.is_valid(changed))
        scope = load(FIXTURES / "request_disclosure_provision.json")["scope"]
        for field in ("use_scope", "permitted_location_ids", "destination"):
            changed = copy.deepcopy(scope)
            del changed[field]
            self.assertFalse(self.validator(TYPES, "disclosureScope").is_valid(changed))
        changed = copy.deepcopy(scope)
        changed["use_scope"]["notification_profile_revision_id"] = "not-a-match-key"
        self.assertFalse(self.validator(TYPES, "disclosureScope").is_valid(changed))
        changed = copy.deepcopy(scope)
        changed["permitted_location_ids"] = [f"place-{i}" for i in range(65)]
        self.assertFalse(self.validator(TYPES, "disclosureScope").is_valid(changed))

    def test_normalization_and_semantic_selector_uniqueness(self):
        revision = load(FIXTURES / "request_definition_create.json")["revision"]
        selections = revision["selections"]
        self.assertEqual(len(selections), len({v["selection_key"] for v in selections}))
        tuples = [(s["facet_key"], s["facet_schema_revision_id"], s["field_key"]) for s in selections]
        self.assertEqual(len(tuples), len(set(tuples)))
        duplicate = copy.deepcopy(selections[0])
        duplicate["selection_key"] = "renamed"
        tuples.append((duplicate["facet_key"], duplicate["facet_schema_revision_id"], duplicate["field_key"]))
        self.assertNotEqual(len(tuples), len(set(tuples)))
        preimage = self.vectors["hashes"][0]["preimage"]
        reordered = copy.deepcopy(preimage)
        reordered["revision"]["selections"].reverse()
        self.assertNotEqual(hash_canonical_json(preimage), hash_canonical_json(reordered))
        self.assertEqual(normalized_text(" Flight\t details  "), "Flight details")

    def test_reference_text_vectors(self):
        for case in self.vectors["rendering"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(reference_render(case), case["expected"])
                self.assertLessEqual(len(case["expected"]["body_text"]), 1024)
        # Scalar count, not UTF-8 bytes; no splitting/truncation of Unicode values.
        case = copy.deepcopy(self.vectors["rendering"][0])
        case["fields"] = [{"selection_key": "flight", "label": "Flight", "field_type": "text", "value": "✈" * 120, "selected": True}]
        self.assertEqual(reference_render(case)["outcome"], "details_included")
        case["fields"][0]["value"] += "✈"
        self.assertEqual(reference_render(case)["selection_outcomes"][0]["outcome"], "value_too_long")

    def test_reference_disclosure_vectors(self):
        for case in self.vectors["disclosure"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(reference_disclosure(case), case["expected_all_details_authorized"])

    def test_exact_preimage_bytes_and_digests(self):
        for case in self.vectors["hashes"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(canonical_json_text(case["preimage"]), case["canonical_json"])
                self.assertEqual(hash_canonical_json(case["preimage"]), case["sha256"])
        cases = {v["case_id"]: v for v in self.vectors["hashes"]}
        record = load(FIXTURES / "response_definition_create.json")["record"]
        self.assertEqual(record["definition_hash"], cases["definition_content"]["sha256"])
        for role in ("notification_rendering_definition", "notification_rendering_definition_revision"):
            pre = cases[role]["preimage"]
            expected = command_derived_id(prefix=role, **{k: v for k, v in pre.items() if k != "derivation_version"})
            self.assertEqual(record[role + "_id"], expected)
        evidence = load(FIXTURES / "evidence_flight_details.json")
        self.assertEqual(evidence["input_hash"], cases["evidence_input"]["sha256"])
        self.assertEqual(evidence["content_hash"], cases["evidence_content"]["sha256"])
        self.assertEqual(evidence["disclosure_scope_hash"], cases["disclosure_scope"]["sha256"])
        self.assertEqual(evidence["body_text"], self.vectors["rendering"][0]["expected"]["body_text"])
        self.assertLessEqual(len(canonical_json_bytes(record["revision"])), self.registry["limits"]["max_definition_bytes"])
        self.assertLessEqual(len(canonical_json_bytes(evidence)), self.registry["limits"]["max_evidence_extension_bytes"])
        for name in ("response_definition_create", "response_definition_create_replay",
                     "response_definition_create_dry_run", "response_definition_publish_noop"):
            response = load(FIXTURES / f"{name}.json")
            for role, path in (("audit", "/audit"), ("command_receipt", "/")):
                expected = command_derived_id(
                    prefix=role, command=response["command"], command_id=response["command_id"],
                    row_role=role, request_path=path,
                )
                self.assertEqual(response[role + "_id"], expected)

    def test_omission_evidence_forbids_private_values_and_raw_reference_fallback(self):
        validator = self.validator(PREFIX + "evidence.schema.json", "selectionOutcome")
        omitted = {"selection_key": "departure", "outcome": "reference_unavailable"}
        self.assertTrue(validator.is_valid(omitted))
        for key, value in (("value", "private home"), ("source", {"location_id": "private-id"})):
            self.assertFalse(validator.is_valid({**omitted, key: value}))
        invalid = {"selection_key": "departure", "outcome": "invented_reason"}
        self.assertFalse(validator.is_valid(invalid))
        evidence = load(FIXTURES / "evidence_flight_details.json")
        evidence["authorization_state"] = "revoked"
        self.assertFalse(self.validator(PREFIX + "evidence.schema.json").is_valid(evidence))
        evidence["outcome"] = "ordinary_only"
        self.assertFalse(self.validator(PREFIX + "evidence.schema.json").is_valid(evidence))

    def test_receipt_and_pagination_shapes_prevent_false_evidence(self):
        result = load(FIXTURES / "response_definition_create.json")
        validator = self.validator(RESPONSES, "notification_rendering_definition.create")
        result["dry_run"] = True
        self.assertTrue(validator.is_valid(result))
        result["replayed"] = True
        self.assertFalse(validator.is_valid(result))
        result["changed"] = False
        self.assertTrue(validator.is_valid(result))
        result["command_receipt_id"] = None
        self.assertFalse(validator.is_valid(result))
        page = load(FIXTURES / "response_definition_list_empty.json")
        validator = self.validator(RESPONSES, "notification_rendering_definition.list")
        page["has_more"] = True
        self.assertFalse(validator.is_valid(page))
        page["next_cursor"] = "opaque-cursor"
        self.assertTrue(validator.is_valid(page))

    def test_every_response_uses_shared_dry_run_marker(self):
        definition = load(FIXTURES / "response_definition_create.json")
        disclosure = load(FIXTURES / "response_disclosure_show.json")
        failure = load(FIXTURES / "response_disclosure_scope_mismatch.json")
        for command, registration in self.registry["commands"].items():
            record = (definition if command.startswith("notification_rendering_definition.") else disclosure)["record"]
            response = {
                "ok": True, "contract_version": registration["contract_version"],
                "command": command,
            }
            if command.endswith(".list"):
                response.update(records=[record], limit="1", has_more=False, next_cursor=None)
            else:
                response["record"] = record
            if registration["mutates"]:
                response.update(
                    command_id="preview-test", changed=True, replayed=False,
                    effect=self.registry["effects"][command][0],
                    command_receipt_id="would-be-receipt", audit_id="would-be-audit",
                )
            cases = [(command, response), ("failure", {**failure, "command": command})]
            if registration["mutates"]:
                cases.append((command, {**response, "replayed": True, "changed": False}))
                for effect in self.registry["effects"][command][1:]:
                    cases.append((command, {**response, "effect": effect, "changed": False}))
            for schema_key, example in cases:
                with self.subTest(command=command, schema=schema_key, effect=example.get("effect")):
                    validator = self.validator(RESPONSES, schema_key)
                    self.assertNotIn("dry_run", example)
                    self.assertTrue(validator.is_valid(example))
                    self.assertTrue(validator.is_valid({**example, "dry_run": True}))
                    self.assertFalse(validator.is_valid({**example, "dry_run": False}))

    def test_list_limit_echo_and_semantic_record_bound(self):
        # Schema validates the wire domain; the count comparison is a separate oracle.
        for family in ("definition", "disclosure"):
            command = f"notification_rendering_{family}.list"
            page = load(FIXTURES / f"response_{family}_list_dry_run.json")
            request = load(FIXTURES / f"request_{family}_list.json")
            validator = self.validator(RESPONSES, command)
            request_validator = self.validator(COMMANDS, command)
            self.assertEqual(page["limit"], request["limit"])
            self.assertLessEqual(len(page["records"]), int(page["limit"]))
            missing = {key: value for key, value in page.items() if key != "limit"}
            self.assertFalse(validator.is_valid(missing))
            for valid in range(1, 101):
                with self.subTest(command=command, limit=str(valid)):
                    self.assertTrue(validator.is_valid({**page, "limit": str(valid)}))
                    self.assertTrue(request_validator.is_valid({**request, "limit": str(valid)}))
            for invalid in (
                0, 1, "0", "01", "101", "-1", None,
                "20\n", "20\r\n", "20\r", "20 ", "20\t", " 20", "\n20", "20\n1",
            ):
                with self.subTest(command=command, limit=invalid):
                    self.assertFalse(validator.is_valid({**page, "limit": invalid}))
                    self.assertFalse(request_validator.is_valid({**request, "limit": invalid}))
            source = "response_definition_create" if family == "definition" else "response_disclosure_show"
            record = load(FIXTURES / f"{source}.json")["record"]
            too_many = {**page, "limit": "1", "records": [record, record]}
            self.assertTrue(validator.is_valid(too_many))
            self.assertFalse(len(too_many["records"]) <= int(too_many["limit"]))

    def test_stateful_obligations_are_not_misreported_as_runtime_proofs(self):
        data = load(FIXTURES / "stateful_obligations.json")
        self.assertFalse(data["runtime_verified"])
        names = [v["scenario_id"] for v in data["scenarios"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"presentation_only_work_continuity", "revocation_serialization",
                         "attempt_persistence_failure", "facet_only_location_freeze"} <= set(names))
        self.assertIn("facet_referenced_location_freeze_migration_and_fs14", self.registry["implementation_gates"])


if __name__ == "__main__":
    unittest.main()
