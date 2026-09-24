"""Draft wire-contract tests, not facet runtime/ledger integration tests.

The small pure oracles below test published vectors. They are deliberately not
importable application validators, command handlers, or substitutes for the open
work-freshness, authorization, cursor-security and query-plan acceptance gates.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
import unittest
from datetime import date, datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.core.canonical_json import canonical_json_bytes, canonical_json_text

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures/archetype_facets"
SCHEMAS = ROOT / "contracts/schemas"
PREFIX = "https://cortext.local/spine/contracts/schemas/"
SCHEMA_FILES = (
    "archetype-facet-commands.schema.json",
    "archetype-facet-failure.schema.json",
    "archetype-facet-fixture-manifest.schema.json",
    "archetype-facet-responses.schema.json",
    "archetype-facet-types.schema.json",
    "notification-profile-types.schema.json",
    "notification-types.schema.json",
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def nfc(value):
    if isinstance(value, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("surrogate")
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [nfc(v) for v in value]
    if isinstance(value, dict):
        return {k: nfc(v) for k, v in value.items()}
    return value


def integer(value):
    if not isinstance(value, str) or not re.fullmatch(r"0|-?[1-9][0-9]*", value):
        raise ValueError("integer encoding")
    result = int(value)
    if not -(2**63) <= result < 2**63:
        raise ValueError("integer range")
    return result


class ArchetypeFacetContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exact facet schema bundle plus its two transitive reference dependencies.
        # Runtime/web non-advertisement is checked separately in the declaration tests.
        cls.schemas = {name: load(SCHEMAS / name) for name in SCHEMA_FILES}
        cls.resources = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in cls.schemas.values())
        cls.manifest = load(ROOT / "contracts/archetype-facet-fixture-manifest.json")
        cls.contract = load(ROOT / "contracts/archetype-facet-contract-registry.v1.json")

    def validator(self, name, fragment=None):
        uri = PREFIX + name + ("#/$defs/" + fragment if fragment else "")
        return Draft202012Validator({"$ref": uri}, registry=self.resources)

    def assertWire(self, name, fragment, value, valid=True):
        errors = list(self.validator(name, fragment).iter_errors(value))
        self.assertEqual(not errors, valid, "\n".join(e.message for e in errors))

    def definition(self, value):
        result = nfc(copy.deepcopy(value))
        self.validator("archetype-facet-types.schema.json", "definition").validate(result)
        keys = [f["key"] for f in result["fields"]]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate field")
        for field in result["fields"]:
            field.setdefault("queryable", False)
            if field["type"] == "enum":
                if len(set(field["choices"])) != len(field["choices"]):
                    raise ValueError("duplicate enum")
                field["choices"].sort()
            if field["type"] == "integer" and integer(field["min"]) > integer(field["max"]):
                raise ValueError("inverted bounds")
        result["fields"].sort(key=lambda f: f["key"])
        result["compatible_item_types"].sort()
        if len(canonical_json_bytes(result)) > 32768:
            raise ValueError("definition capacity")
        return result

    def scalar(self, field, value, references):
        value = nfc(value)
        kind = field["type"]
        if kind == "boolean":
            if type(value) is not bool:
                raise ValueError("boolean")
            return value
        if not isinstance(value, str):
            raise ValueError("string scalar")
        if kind == "text":
            if not 1 <= len(value) <= int(field["max_length"]):
                raise ValueError("text length")
            if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
                raise ValueError("text controls")
        elif kind == "enum":
            if value not in field["choices"]:
                raise ValueError("enum choice")
        elif kind == "integer":
            if not integer(field["min"]) <= integer(value) <= integer(field["max"]):
                raise ValueError("integer bounds")
        elif kind == "date":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError("date encoding")
            date.fromisoformat(value)
        elif kind == "reference":
            target = references.get(value)
            if (
                not target or target.get("target_kind") != field["target_kind"]
                or target.get("readable") is not True
                or (field["target_kind"] == "subject" and target.get("active") is not True)
            ):
                raise ValueError("facet_reference_unavailable")
        else:
            raise ValueError("type")
        return value

    def values(self, definition, values, references):
        self.validator("archetype-facet-types.schema.json", "values").validate(values)
        fields = {f["key"]: f for f in definition["fields"]}
        if set(values) - set(fields):
            raise ValueError("unknown field")
        if any(f["required"] and k not in values for k, f in fields.items()):
            raise ValueError("missing required field")
        normalized = {k: self.scalar(fields[k], v, references) for k, v in values.items()}
        if len(canonical_json_bytes(normalized)) > 16384:
            raise ValueError("values capacity")
        return normalized

    def test_schema_and_manifest_integrity(self):
        for name, schema in self.schemas.items():
            if name.startswith("archetype-facet-"):
                Draft202012Validator.check_schema(schema)
        self.validator("archetype-facet-fixture-manifest.schema.json").validate(self.manifest)
        ids, paths = set(), set()
        for row in self.manifest["fixtures"]:
            with self.subTest(fixture=row["fixture_id"]):
                self.assertNotIn(row["fixture_id"], ids)
                self.assertNotIn(row["fixture"], paths)
                ids.add(row["fixture_id"])
                paths.add(row["fixture"])
                name = Path(row["schema"]).name
                fragment = row.get("schema_ref", "").removeprefix("#/$defs/") or None
                self.assertWire(name, fragment, load(ROOT / row["fixture"]), row["valid"])
        self.assertEqual(paths, {str(p.relative_to(ROOT)) for p in (FIXTURES / "contracts").glob("*.json")})
        self.assertEqual(
            {v["path"] for v in self.manifest["vectors"]},
            {str(p.relative_to(ROOT)) for p in (FIXTURES / "vectors").glob("*.json")},
        )

    def test_query_item_owners_are_distinct_from_catalog_owners(self):
        query = load(FIXTURES / "contracts/request_item_facets_query.json")
        create = load(FIXTURES / "contracts/request_facet_schema_create.json")
        listing = load(FIXTURES / "contracts/request_facet_schema_list.json")
        for scope in (
            {"owner_kind": "subject", "owner_subject_id": "person"},
            {"owner_kind": "subject_group", "owner_group_id": "group"},
            {"owner_kind": "system"},
        ):
            with self.subTest(scope=scope):
                query["owner"] = scope
                self.assertWire("archetype-facet-commands.schema.json", "item.facets.query", query,
                                valid=scope["owner_kind"] != "system")
                for command, request in (("facet_schema.create", create), ("facet_schema.list", listing)):
                    request["owner"] = scope
                    self.assertWire("archetype-facet-commands.schema.json", command, request)

    def test_reference_readback_distinguishes_subject_lifecycle_from_locations(self):
        for kind in ("subject", "location"):
            for status in ("active", "inactive"):
                with self.subTest(kind=kind, status=status):
                    self.assertWire("archetype-facet-types.schema.json", "referenceState", {
                        "field": "reference", "target_kind": kind, "target_id": "target", "status": status,
                    }, valid=kind == "subject" or status == "active")

    def test_schema_resources_have_explicit_dependency_closure(self):
        self.assertEqual(len(SCHEMA_FILES), 7)
        self.assertEqual(set(self.schemas), set(SCHEMA_FILES))
        references = set()

        def visit(value):
            if isinstance(value, dict):
                reference = value.get("$ref", "").split("#")[0]
                if reference:
                    self.assertNotIn("://", reference)
                    references.add(reference)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        for schema in self.schemas.values():
            visit(schema)
        self.assertTrue(references <= set(SCHEMA_FILES))
        self.assertEqual(
            {name for name in references if not name.startswith("archetype-facet-")},
            {"notification-profile-types.schema.json", "notification-types.schema.json"},
        )

    def test_command_coverage_and_draft_status(self):
        expected = {
            "facet_schema.create",
            "facet_schema.publish",
            "facet_schema.retire",
            "facet_schema.show",
            "facet_schema.list",
            "item_archetype.facet_binding.set",
            "item_archetype.facet_binding.remove",
            "item_archetype.facet_binding.list",
            "item.facets.update",
            "item.facets.show",
            "item.facets.query",
        }
        self.assertEqual(set(self.contract["commands"]), expected)
        self.assertEqual(self.contract["status"], "draft_not_implemented")
        for kind in ("commands", "responses"):
            schema = self.schemas[f"archetype-facet-{kind}.schema.json"]
            self.assertEqual(set(schema["$defs"]), expected)
            for command in expected:
                self.assertTrue(
                    any(
                        f["schema"] == f"contracts/schemas/archetype-facet-{kind}.schema.json"
                        and f.get("schema_ref") == "#/$defs/" + command
                        and f["valid"]
                        for f in self.manifest["fixtures"]
                    )
                )
        for command, entry in self.contract["commands"].items():
            for kind in ("request", "response"):
                path, fragment = entry[kind + "_schema"].split("#/$defs/")
                self.assertEqual(fragment, command)
                self.assertIn(fragment, load(ROOT / path)["$defs"])

    def test_envelopes_are_closed_and_version_pinned(self):
        for command, entry in self.contract["commands"].items():
            request = load(FIXTURES / "contracts" / ("request_" + command.replace(".", "_") + ".json"))
            with self.subTest(command=command):
                self.assertWire("archetype-facet-commands.schema.json", command, {**request, "extra": True}, False)
                self.assertWire("archetype-facet-commands.schema.json", command, {**request, "contract_version": "future"}, False)
                if entry["mutates"]:
                    datetime.strptime(request["action_timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ")
                    for field in ("command_id", "actor_subject_id", "action_timestamp_utc"):
                        missing = dict(request)
                        del missing[field]
                        self.assertWire("archetype-facet-commands.schema.json", command, missing, False)
                else:
                    self.assertWire("archetype-facet-commands.schema.json", command, {**request, "command_id": "forbidden"}, False)

    def test_normalization_hash_and_field_order_vector(self):
        vector = load(FIXTURES / "vectors/definition_normalization.json")
        for definition in (vector["input"], vector["equivalent_input"]):
            normalized = self.definition(definition)
            self.assertEqual(normalized, vector["normalized_definition"])
            preimage = {"derivation_version": "spine.facet-definition.v1", "definition": normalized}
            self.assertEqual(preimage, vector["preimage"])
            self.assertEqual(canonical_json_text(preimage), vector["canonical_preimage"])
            self.assertEqual(hashlib.sha256(canonical_json_bytes(preimage)).hexdigest(), vector["sha256"])

    def test_identity_vectors_cover_exact_registry(self):
        vectors = load(FIXTURES / "vectors/identity.json")["vectors"]
        actual = []
        for vector in vectors:
            row = {k: vector[k] for k in ("command", "row_role", "prefix", "request_path")}
            actual.append(row)
            expected = {
                "derivation_version": "spine.command-id.v1",
                "command": row["command"],
                "command_id": "fixture-" + row["command"],
                "row_role": row["row_role"],
                "request_path": row["request_path"],
            }
            self.assertEqual(vector["preimage"], expected)
            self.assertEqual(canonical_json_text(expected), vector["canonical_preimage"])
            digest = hashlib.sha256(canonical_json_bytes(expected)).hexdigest()
            self.assertEqual(vector["sha256"], digest)
            self.assertEqual(vector["expected_id"], row["prefix"] + "_" + digest)
        self.assertEqual(actual, self.contract["identity_registry"])
        # Independent literal mapping from the audited Section 3.1 table.
        expected_roles = {
            ("facet_schema.create", "facet_schema", "/facet_schema"),
            ("facet_schema.create", "facet_schema_revision", "/facet_schema/revision"),
            ("facet_schema.publish", "facet_schema_revision", "/facet_schema/revision"),
            ("item_archetype.facet_binding.set", "archetype_facet_binding", "/facet_binding"),
        }
        for command, meta in self.contract["commands"].items():
            if meta["mutates"]:
                expected_roles.update({(command, "audit", "/audit"), (command, "command_receipt", "/")})
        self.assertEqual({(r["command"], r["row_role"], r["request_path"]) for r in actual}, expected_roles)
        self.assertTrue(all(r["prefix"] == r["row_role"] for r in actual))
        self.assertEqual(len({v["expected_id"] for v in vectors}), len(vectors))
        for command, meta in self.contract["commands"].items():
            roles = {v["row_role"] for v in vectors if v["command"] == command}
            if meta["mutates"]:
                self.assertTrue({"audit", "command_receipt"} <= roles)
            else:
                self.assertEqual(roles, set())
        self.assertFalse(any(v["row_role"] in {"facet_value", "facet_snapshot", "tombstone"} for v in vectors))

    def test_typed_value_vectors(self):
        corpus = load(FIXTURES / "vectors/typed_values.json")
        for vector in corpus["cases"]:
            with self.subTest(case=vector["case_id"]):
                if vector["valid"]:
                    self.assertEqual(self.scalar(vector["field"], vector["input"], corpus["reference_context"]), vector["expected"])
                else:
                    with self.assertRaises(ValueError):
                        self.scalar(vector["field"], vector["input"], corpus["reference_context"])

    def test_definition_semantic_rejections(self):
        definition = load(FIXTURES / "vectors/definition_normalization.json")["input"]
        duplicate = copy.deepcopy(definition)
        duplicate["fields"].append({**duplicate["fields"][0], "queryable": False})
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            self.definition(duplicate)
        for low, high in (("2", "1"), ("-9223372036854775809", "1")):
            invalid = {**definition, "fields": [{"key": "count", "type": "integer", "required": True, "min": low, "max": high}]}
            with self.assertRaises(ValueError):
                self.definition(invalid)
        duplicate_enum = {**definition, "fields": [{"key": "kind", "type": "enum", "required": True, "choices": ["café", "cafe\u0301"]}]}
        self.assertFalse(self.validator("archetype-facet-types.schema.json", "definition").is_valid(nfc(duplicate_enum)))
        enum = {**definition, "fields": [{"key": "kind", "type": "enum", "required": True, "choices": ["Z", "A"]}]}
        self.assertEqual(self.definition(enum)["fields"][0]["choices"], ["A", "Z"])

    def test_closed_field_types_and_scalar_envelopes(self):
        validator = self.validator("archetype-facet-types.schema.json", "field")
        for kind in ("object", "array", "computed", "float", "json_schema"):
            self.assertFalse(validator.is_valid({"key": "data", "required": True, "type": kind}))
        for value in (None, 1, 1.5, [], {}, ["x"]):
            self.assertFalse(self.validator("archetype-facet-types.schema.json", "values").is_valid({"value": value}))
        for value in ("-0", "+1", "01", "١", "1\n"):
            # Semantic full-match additionally rejects final-newline regex behavior.
            with self.assertRaises(ValueError):
                integer(value)
        with self.assertRaisesRegex(ValueError, "surrogate"):
            nfc("\ud800")

    def test_required_unknown_and_empty_values(self):
        definition = self.definition(load(FIXTURES / "vectors/definition_normalization.json")["input"])
        request = load(FIXTURES / "contracts/request_item_facets_update.json")
        values = request["changes"][0]["values"]
        references = {v: {"target_kind": "location", "readable": True} for v in ("airport-origin", "airport-destination")}
        self.assertEqual(self.values(definition, values, references), values)
        for bad in ({}, {**values, "unknown": "extra"}):
            with self.assertRaises(ValueError):
                self.values(definition, bad, references)
        optional = {**definition, "fields": [{"key": "note", "type": "text", "required": False, "max_length": "10"}]}
        self.assertEqual(self.values(optional, {}, {}), {})

    def test_byte_limits_are_utf8_not_character_counts(self):
        definition = {
            "display_name": "Large",
            "description": None,
            "compatible_item_types": ["event"],
            "fields": [{"key": f"f{i}", "type": "text", "required": False, "max_length": "1024"} for i in range(32)],
        }
        normalized = self.definition(definition)
        values = {f"f{i}": "🛫" * 1024 for i in range(5)}
        self.assertLess(sum(len(v) for v in values.values()), 16384)
        with self.assertRaisesRegex(ValueError, "values capacity"):
            self.values(normalized, values, {})
        large = copy.deepcopy(definition)
        large["fields"] = [
            {"key": f"f{i}", "type": "enum", "required": False, "choices": [str(j) + "🛫" * 120 for j in range(64)]} for i in range(2)
        ]
        with self.assertRaisesRegex(ValueError, "definition capacity"):
            self.definition(large)
        valid_values = {f"f{i}": "🛫" * 1000 for i in range(3)}
        self.values(normalized, valid_values, {})
        snapshot = {f"facet{i}": valid_values for i in range(6)}
        self.assertLessEqual(len(snapshot), 8)
        self.assertGreater(len(canonical_json_bytes(snapshot)), self.contract["limits"]["snapshot_values_bytes"])

    def test_receipt_branch_semantics(self):
        for row in self.manifest["fixtures"]:
            if "responses" not in row["schema"] or not row["valid"]:
                continue
            response = load(ROOT / row["fixture"])
            if "changed" not in response:
                continue
            command = response["command"]
            original_changed = not response["effect"].endswith("_noop")
            self.assertEqual("audit_id" in response, original_changed)
            self.assertEqual(response["changed"], original_changed and not response["replayed"])
            if command == "item.facets.update":
                prior = int(response["prior_item_version"])
                self.assertEqual(int(response["item_version"]), prior + int(original_changed))
                self.assertEqual(response["changed_facet_keys"], sorted(set(response["changed_facet_keys"])))
                if not response["changed"]:
                    self.assertEqual(response["changed_facet_keys"], [])
                    self.assertFalse(response["reconciliation_performed"])
            if command == "item_archetype.facet_binding.remove":
                self.assertEqual(response["facet_binding_id"], response["prior_binding_id"])
            corrupt = {**response, "effect": "invented"}
            self.assertWire("archetype-facet-responses.schema.json", command, corrupt, False)

    def test_readback_pin_hash_and_reference_state(self):
        response = load(FIXTURES / "contracts/response_item_facets_show.json")
        entries = response["entries"]
        self.assertEqual([v["facet_key"] for v in entries], sorted({v["facet_key"] for v in entries}))
        for entry in entries:
            revision = entry["schema_revision"]
            self.assertEqual(entry["facet_schema_revision_id"], revision["facet_schema_revision_id"])
            self.assertEqual(self.definition(revision["definition"]), revision["definition"])
            preimage = {"derivation_version": "spine.facet-definition.v1", "definition": revision["definition"]}
            self.assertEqual(hashlib.sha256(canonical_json_bytes(preimage)).hexdigest(), revision["definition_hash"])
            expected_refs = {
                f["key"]: f for f in revision["definition"]["fields"] if f["type"] == "reference" and f["key"] in entry["values"]
            }
            self.assertEqual([r["field"] for r in entry["references"]], sorted(expected_refs))
            for ref in entry["references"]:
                self.assertEqual(ref["target_kind"], expected_refs[ref["field"]]["target_kind"])
                self.assertEqual(ref["target_id"], entry["values"][ref["field"]])
        self.assertWire("archetype-facet-responses.schema.json", "item.facets.show", {**response, "entries": []})

    def test_replay_pairs_preserve_identity_without_reporting_new_activity(self):
        covered = set()
        for row in self.manifest["fixtures"]:
            if not row["fixture_id"].endswith("_replay"):
                continue
            replay = load(ROOT / row["fixture"])
            original_path = Path(row["fixture"].removesuffix("_replay.json") + ".json")
            original = load(ROOT / original_path)
            command = original["command"]
            covered.add((command, original["effect"]))
            expected = {**original, "changed": False, "replayed": True}
            if command == "item.facets.update":
                expected.update(changed_facet_keys=[], reconciliation_performed=False)
            self.assertEqual(replay, expected)
            self.assertFalse(original["replayed"])
            for malformed in ({**replay, "changed": True}, {k: v for k, v in replay.items() if k != "replayed"}):
                self.assertWire("archetype-facet-responses.schema.json", command, malformed, False)
            wrong_audit = dict(replay)
            if "audit_id" in original:
                del wrong_audit["audit_id"]
            else:
                wrong_audit["audit_id"] = "invented-audit"
            self.assertWire("archetype-facet-responses.schema.json", command, wrong_audit, False)
            if command == "item.facets.update":
                self.assertWire("archetype-facet-responses.schema.json", command, {**replay, "reconciliation_performed": True}, False)
                self.assertWire(
                    "archetype-facet-responses.schema.json", command, {**replay, "changed_facet_keys": ["flight_details"]}, False
                )
        expected = {
            (command, branch["properties"]["effect"]["const"])
            for command, schema in self.schemas["archetype-facet-responses.schema.json"]["$defs"].items()
            for branch in schema.get("oneOf", [])
        }
        self.assertEqual(covered, expected)
        self.assertEqual(len(covered), 11)

    def test_pagination_envelope_and_bounds(self):
        for command, collection, sort_key in (
            ("facet_schema.list", "schemas", "facet_schema_id"),
            ("item_archetype.facet_binding.list", "bindings", "facet_key"),
            ("item.facets.query", "items", "item_id"),
        ):
            response = load(FIXTURES / "contracts" / ("response_" + command.replace(".", "_") + ".json"))
            self.assertLessEqual(len(response[collection]), int(response["limit"]))
            keys = [v[sort_key] for v in response[collection]]
            self.assertEqual(keys, sorted(set(keys)))
            for facts in ({"has_more": True, "next_cursor": None}, {"has_more": False, "next_cursor": "opaque"}):
                self.assertWire("archetype-facet-responses.schema.json", command, {**response, **facts}, False)
        for limit in ("0", "101", "01", 25, "-1"):
            self.assertFalse(self.validator("archetype-facet-types.schema.json", "limit").is_valid(limit))

    def test_failure_code_mapping_and_no_evidence_payload(self):
        codes = self.schemas["archetype-facet-failure.schema.json"]["properties"]["error"]["properties"]["code"]["enum"]
        self.assertEqual(set(codes), set(self.contract["handler_error_exit_codes"]))
        for row in self.manifest["fixtures"]:
            if row["fixture_id"].startswith("failure_"):
                response = load(ROOT / row["fixture"])
                self.assertNotIn("command_receipt_id", response)
                self.assertNotIn("value", response["error"])
                self.assertWire(
                    "archetype-facet-failure.schema.json",
                    None,
                    {**response, "error": {**response["error"], "private_value": "secret"}},
                    False,
                )

    def test_change_and_snapshot_semantic_bounds(self):
        request = load(FIXTURES / "contracts/request_item_facets_update.json")
        changes = request["changes"]
        # Envelope validation cannot enforce uniqueness by a selected property.
        duplicate = [*changes, {"op": "remove", "facet_key": "flight_details"}]

        def normalize_changes(changes):
            self.validator("archetype-facet-commands.schema.json", "item.facets.update").validate({**request, "changes": changes})
            keys = [op["facet_key"] for op in changes]
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate change")
            return sorted(nfc(changes), key=lambda op: op["facet_key"])

        with self.assertRaisesRegex(ValueError, "duplicate change"):
            normalize_changes(duplicate)
        pair = [*changes, {"op": "remove", "facet_key": "another_facet"}]
        self.assertEqual(normalize_changes(pair), normalize_changes(list(reversed(pair))))
        response = load(FIXTURES / "contracts/response_item_facets_show.json")
        self.assertWire(
            "archetype-facet-responses.schema.json", "item.facets.show", {**response, "entries": response["entries"] * 9}, False
        )
        definition = load(FIXTURES / "vectors/definition_normalization.json")["input"]
        self.assertWire("archetype-facet-types.schema.json", "definition", {**definition, "fields": definition["fields"] * 9}, False)

    def test_success_effect_coverage_and_normalized_readback_schema(self):
        responses = self.schemas["archetype-facet-responses.schema.json"]["$defs"]
        for command, schema in responses.items():
            if "oneOf" not in schema:
                continue
            expected = {b["properties"]["effect"]["const"] for b in schema["oneOf"]}
            observed = set()
            for row in self.manifest["fixtures"]:
                if row.get("schema_ref") == "#/$defs/" + command and "responses" in row["schema"]:
                    observed.add(load(ROOT / row["fixture"])["effect"])
            self.assertEqual(expected, observed)
        revision = load(FIXTURES / "contracts/response_facet_schema_show.json")["revision"]
        del revision["definition"]["fields"][0]["queryable"]
        self.assertWire("archetype-facet-types.schema.json", "revision", revision, False)


if __name__ == "__main__":
    unittest.main()
