"""Offline draft wire/model checks; no handler, ledger or runtime qualification."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scripts.sync_web_contracts import SOURCE_ONLY_SCHEMAS
from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.canonical_json import canonical_json_bytes

ROOT = Path(__file__).parents[1]
COMMAND = "facet_schema.revision.show"
CONTRACT = "spine.facet-schema-revision-readback.v1"
FIXTURES = ROOT / "tests/fixtures/facet_schema_revision_readback"
SCHEMA_FILES = (
    "facet-schema-revision-show-request.schema.json",
    "facet-schema-revision-show-response.schema.json",
    "facet-schema-revision-show-failure.schema.json",
    "archetype-facet-types.schema.json",
    "notification-profile-types.schema.json",
    "notification-types.schema.json",
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def definition_hash(definition):
    return hashlib.sha256(canonical_json_bytes({"derivation_version": "spine.facet-definition.v1", "definition": definition})).hexdigest()


def historical_lookup_model(state, request, exemplar_failures):
    """Pure witness oracle, not an application validator or client workaround.

    The state is a small declared subset of catalog facts, not a real database.
    Runtime transaction, authorization, decoder/projection parity and budget proofs
    remain RR implementation gates; this model cannot establish those properties.
    """
    selected = next((r for r in state["revisions"] if r["facet_schema_revision_id"] == request["facet_schema_revision_id"]), None)
    if selected is None:
        return copy.deepcopy(exemplar_failures["failure_revision_missing"])
    root = next((r for r in state["roots"] if r["facet_schema_id"] == selected["facet_schema_id"]), None)
    if root is None or selected["definition_hash"] != definition_hash(selected["definition"]):
        return copy.deepcopy(exemplar_failures["failure_corrupt_evidence"])
    return {"ok": True, "command": COMMAND, "response_contract": CONTRACT, "root": copy.deepcopy(root), "revision": copy.deepcopy(selected)}


class FacetSchemaRevisionReadbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {name: load(ROOT / "contracts/schemas" / name) for name in SCHEMA_FILES}
        cls.resources = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in cls.schemas.values())
        cls.manifest = load(ROOT / "contracts/facet-schema-revision-readback-fixture-manifest.json")
        cls.contract = load(ROOT / cls.manifest["registry"])
        cls.witness = load(ROOT / cls.manifest["model_witness"])

    def validator(self, name):
        return Draft202012Validator(self.schemas[name], registry=self.resources)

    def test_meta_schemas_and_complete_fixture_inventory(self):
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)
        self.assertEqual(self.manifest["schema_version"], "spine.facet-schema-revision-readback-fixtures.v1")
        self.assertEqual(self.manifest["status"], "draft_contract_only")
        self.assertFalse(self.manifest["runtime_verified"])
        ids, paths = set(), set()
        for row in self.manifest["fixtures"]:
            with self.subTest(fixture=row["fixture_id"]):
                self.assertEqual(set(row), {"fixture_id", "fixture", "schema", "valid"})
                self.assertIs(type(row["valid"]), bool)
                self.assertNotIn(row["fixture_id"], ids)
                self.assertNotIn(row["fixture"], paths)
                ids.add(row["fixture_id"])
                paths.add(row["fixture"])
                value = load(ROOT / row["fixture"])
                errors = list(self.validator(Path(row["schema"]).name).iter_errors(value))
                self.assertEqual(not errors, row["valid"], "\n".join(e.message for e in errors))
        self.assertEqual(paths, {str(p.relative_to(ROOT)) for p in (FIXTURES / "contracts").glob("*.json")})

    def test_draft_surface_is_not_runtime_or_http_advertisement(self):
        self.assertEqual(self.contract["contract_version"], CONTRACT)
        self.assertEqual(self.contract["status"], "draft_contract_only")
        self.assertEqual(self.contract["exposure"], "trusted_local_only")
        self.assertFalse(self.contract["runtime_implemented"])
        self.assertFalse(self.contract["inspected_baseline"]["implements_command"])
        self.assertEqual(set(self.contract["commands"]), {COMMAND})
        self.assertNotIn(CONTRACT, IMPLEMENTED_CONTRACT_VERSIONS)
        self.assertNotIn(COMMAND, COMMAND_RUNTIME_CONTRACT_REGISTRY)
        for path in (
            "contracts/spine.trusted-web-command-registry.v1.json",
            "contracts/spine.trusted-web-facet-registry.v1.json",
            "src/spine/contracts/web/spine.trusted-web-command-registry.v1.json",
            "src/spine/contracts/web/spine.trusted-web-facet-registry.v1.json",
        ):
            self.assertNotIn(COMMAND, {entry["command"] for entry in load(ROOT / path)["commands"]})
        self.assertNotIn(COMMAND, load(ROOT / "contracts/archetype-facet-contract-registry.v1.json")["commands"])
        for uri in ("contracts/schemas/trusted-web-facet-request.schema.json", "contracts/schemas/archetype-facet-commands.schema.json"):
            self.assertNotIn(COMMAND, load(ROOT / uri)["$defs"])
        pins = load(ROOT / "contracts/trusted-web-facet-pins.v1.json")["files"]
        for name in SCHEMA_FILES[:3]:
            self.assertIn(name, SOURCE_ONLY_SCHEMAS)
            self.assertNotIn("schemas/" + name, pins)
            self.assertFalse((ROOT / "src/spine/contracts/web/schemas" / name).exists())

    def test_complete_planned_command_requirements_and_bounds(self):
        entry = self.contract["commands"][COMMAND]
        self.assertFalse(entry["mutates"])
        self.assertEqual(entry["contract_version"], CONTRACT)
        self.assertEqual(
            entry["required_contract_versions"],
            sorted(
                {
                    CONTRACT,
                    "spine.canonical-json.v1",
                    "spine.facet-schemas.v1",
                    "spine.notification-rendering-integration.v1",
                }
            ),
        )
        for key in ("request_schema", "response_schema", "failure_schema"):
            self.assertTrue((ROOT / entry[key]).is_file())
        self.assertEqual(
            self.contract["limits"],
            {
                "request_bytes": 1048576,
                "response_bytes": 4194304,
                "definition_bytes": 32768,
                "max_fields": 32,
                "resolved_resources": 100,
                "sqlite_vm_steps": 100000,
                "operation_seconds": 5,
            },
        )
        self.assertEqual([row["id"] for row in self.contract["runtime_obligations"]], [f"RR-{i:02}" for i in range(1, 12)])
        self.assertEqual({row["status"] for row in self.contract["runtime_obligations"]}, {"pending_runtime_verification"})

    def test_response_fixture_hashes_and_identity_semantics(self):
        request = load(FIXTURES / "contracts/request_historical.json")
        for name in ("response_historical_active", "response_historical_retired", "response_historical_dry_run", "response_current"):
            with self.subTest(name=name):
                value = load(FIXTURES / "contracts" / (name + ".json"))
                selected = value["revision"]
                self.assertEqual(value["root"]["facet_schema_id"], selected["facet_schema_id"])
                self.assertEqual(selected["definition_hash"], definition_hash(selected["definition"]))
                self.assertLessEqual(len(canonical_json_bytes(selected["definition"])), 32768)
                self.assertLessEqual(len(canonical_json_bytes(value)), 4194304)
                self.assertTrue(all("queryable" in field for field in selected["definition"]["fields"]))
                if name != "response_current":
                    self.assertEqual(selected["facet_schema_revision_id"], request["facet_schema_revision_id"])
        historical = load(FIXTURES / "contracts/response_historical_active.json")
        retired = load(FIXTURES / "contracts/response_historical_retired.json")
        self.assertEqual(historical["revision"], retired["revision"])
        self.assertNotEqual(historical["root"]["current_revision_id"], historical["revision"]["facet_schema_revision_id"])

    def test_cross_root_historical_witness_and_failure_model(self):
        self.assertEqual(self.witness["status"], "offline_model_only")
        self.assertFalse(self.witness["runtime_verified"])
        failures = {
            name: load(FIXTURES / "contracts" / (name + ".json"))
            for name in (
                "failure_revision_missing",
                "failure_corrupt_evidence",
            )
        }
        request_validator = self.validator("facet-schema-revision-show-request.schema.json")
        for scenario in self.witness["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                request_validator.validate(scenario["request"])
                before = copy.deepcopy(scenario["state"])
                expected = scenario["expected"]
                self.validator("facet-schema-revision-show-" + ("response" if expected["ok"] else "failure") + ".schema.json").validate(
                    expected
                )
                self.assertEqual(historical_lookup_model(scenario["state"], scenario["request"], failures), expected)
                self.assertEqual(scenario["state"], before)
                for root in before["roots"]:
                    Draft202012Validator(
                        {"$ref": self.schemas["archetype-facet-types.schema.json"]["$id"] + "#/$defs/root"}, registry=self.resources
                    ).validate(root)
                for revision in before["revisions"]:
                    Draft202012Validator(
                        {"$ref": self.schemas["archetype-facet-types.schema.json"]["$id"] + "#/$defs/revision"}, registry=self.resources
                    ).validate(revision)
        historical = next(s for s in self.witness["scenarios"] if s["id"] == "cross_root_historical_pin")
        context = historical["context"]
        self.assertNotEqual(context["desired_facet_schema_id"], historical["expected"]["root"]["facet_schema_id"])
        self.assertEqual(context["existing_binding"]["facet_schema_revision_id"], historical["request"]["facet_schema_revision_id"])
        self.assertEqual(context["rendering_selection"]["facet_schema_revision_id"], historical["request"]["facet_schema_revision_id"])
        self.assertNotIn(
            historical["request"]["facet_schema_revision_id"], {r["current_revision_id"] for r in historical["state"]["roots"]}
        )

    def test_failure_fields_are_closed_and_do_not_release_evidence(self):
        validator = self.validator("facet-schema-revision-show-failure.schema.json")
        for row in self.manifest["fixtures"]:
            if not row["fixture_id"].startswith("failure_"):
                continue
            value = load(ROOT / row["fixture"])
            self.assertEqual(set(value), {"ok", "command", "error"})
            validator.validate(value)
            unsafe = value | {"root": {"facet_schema_id": "private"}}
            self.assertFalse(validator.is_valid(unsafe))
            for private in ("facet_schema_A", "facet_schema_B", "example-owner-group"):
                self.assertNotIn(private, value["error"]["message"])
        missing = load(FIXTURES / "contracts/failure_revision_missing.json")
        missing["error"]["field"] = "facet_schema_id"
        self.assertFalse(validator.is_valid(missing))
        self.assertEqual(self.contract["handler_error_exit_codes"]["referenced_row_not_found"], 4)
        self.assertEqual(self.contract["handler_error_exit_codes"]["environment_failure"], 7)

    def test_shared_references_form_a_complete_offline_closure(self):
        known = {s["$id"] for s in self.schemas.values()}
        for schema in self.schemas.values():

            def walk(value, schema_id=schema["$id"]):
                if isinstance(value, dict):
                    if "$ref" in value:
                        uri = value["$ref"].split("#")[0]
                        if uri:
                            resolved = uri if uri.startswith("https://") else schema_id.rsplit("/", 1)[0] + "/" + uri
                            self.assertIn(resolved, known)
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)

            walk(schema)

    def test_leaf_spec_marks_fixture_and_implementation_limits(self):
        spec = (ROOT / "specs/facet-schema-revision-readback.md").read_text()
        self.assertIn("not implemented", spec)
        self.assertIn("trusted-local only", spec)
        self.assertIn("not** completed runtime", spec)
        for row in self.contract["runtime_obligations"]:
            self.assertIn(row["id"], spec)
