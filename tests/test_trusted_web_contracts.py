"""Static trusted-web contracts, not HTTP/security/runtime acceptance tests."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.receipts import command_derived_id
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.hashing import hash_canonical_json

ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "contracts/schemas"
FIXTURES = ROOT / "tests/fixtures/trusted_web/contracts"
COMMANDS = {
    "schedule.build", "schedule.create", "schedule.show", "schedule.update",
    "schedule.cancel", "task.complete", "item.occurrences", "item_archetype.list",
    "item_archetype.show", "notification_profile.list", "notification_profile.show",
    "notification_profile.binding.list", "notification_profile.resolve",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class TrustedWebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {p.name: load(p) for p in SCHEMAS.glob("*.schema.json")}
        cls.references = Registry().with_resources(
            (s["$id"], Resource.from_contents(s)) for s in cls.schemas.values()
        )
        cls.entries = load(ROOT / "contracts/spine.trusted-web-command-registry.v1.json")["commands"]

    def validator(self, filename: str, fragment: str = "") -> Draft202012Validator:
        return Draft202012Validator(
            {"$ref": self.schemas[filename]["$id"] + fragment},
            registry=self.references, format_checker=FormatChecker(),
        )

    def request_validator(self, command: str) -> Draft202012Validator:
        return self.validator("trusted-web-command-request.schema.json", f"#/$defs/{command}")

    def test_schemas_and_positive_negative_fixtures(self) -> None:
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)
        manifest = load(ROOT / "contracts/trusted-web-fixture-manifest.json")
        self.assertEqual(manifest["runtime_acceptance"], "pending")
        ids = []
        for entry in manifest["fixtures"]:
            with self.subTest(fixture=entry["fixture_id"]):
                ids.append(entry["fixture_id"])
                validator = self.validator(Path(entry["schema"]).name, entry.get("schema_ref", ""))
                errors = list(validator.iter_errors(load(ROOT / entry["fixture"])))
                self.assertEqual(not errors, entry["valid"], [e.message for e in errors])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            {ROOT / e["fixture"] for e in manifest["fixtures"]}, set(FIXTURES.glob("*.json"))
        )

    def test_registry_is_closed_and_matches_runtime_dependencies(self) -> None:
        artifact = load(ROOT / "contracts/spine.trusted-web-command-registry.v1.json")
        self.validator("trusted-web-command-registry.schema.json").validate(artifact)
        names = [e["command"] for e in self.entries]
        self.assertEqual(names, sorted(COMMANDS))
        for e in self.entries:
            current = COMMAND_RUNTIME_CONTRACT_REGISTRY[e["command"]]
            self.assertEqual(e["required_contract_versions"], list(current.required_contract_versions))
            self.assertTrue(set(e["required_contract_versions"]) <= IMPLEMENTED_CONTRACT_VERSIONS)
            self.assertEqual(e["access_mode"], current.access_mode)
            self.assertEqual(e["requires_expected_access_epoch"], current.access_mode == "write")
        self.assertFalse({"web_access.plan", "web_access.apply", "system.info"} & set(names))

    def test_no_unimplemented_runtime_advertisement(self) -> None:
        self.assertFalse(any(v.startswith("spine.trusted-web") for v in IMPLEMENTED_CONTRACT_VERSIONS))
        self.assertNotIn("web_access.apply", COMMAND_RUNTIME_CONTRACT_REGISTRY)

    def test_transitive_inner_schema_pins(self) -> None:
        pins = load(ROOT / "contracts/trusted-web-schema-pins.v1.json")["files"]
        visited = set()

        def walk(value: object) -> None:
            if isinstance(value, dict):
                if "$ref" in value:
                    visit(value["$ref"].split("#")[0])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        def visit(name: str) -> None:
            if not name or name in visited:
                return
            visited.add(name)
            walk(self.schemas[name])

        for e in self.entries:
            visit(e["request_schema"].split("#")[0])
            visit(e["response_schema"].split("#")[0])
        self.assertEqual(visited, set(pins))
        for name, expected in pins.items():
            self.assertEqual(hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest(), expected, name)

    def test_every_command_has_request_fixture_and_strict_outer_shape(self) -> None:
        for e in self.entries:
            command = e["command"]
            payload = load(FIXTURES / f"request_{command.replace('.', '_')}.json")
            v = self.request_validator(command)
            v.validate(payload)
            for field, value in [("access_mode", "single_operator"), ("actor_subject_id", "admin"),
                                 ("db", "/private.sqlite"), ("access_revision", "1")]:
                self.assertFalse(v.is_valid({**payload, field: value}))
            bad_version = copy.deepcopy(payload)
            bad_version["contract_version"] = "spine.trusted-web-api.v999"
            self.assertFalse(v.is_valid(bad_version))
            if e["request_version_field"]:
                bad_inner = copy.deepcopy(payload)
                bad_inner["request"][e["request_version_field"]] = "unknown.v999"
                self.assertFalse(v.is_valid(bad_inner))

    def test_create_owner_and_epoch_placement(self) -> None:
        for e in self.entries:
            command = e["command"]
            payload = load(FIXTURES / f"request_{command.replace('.', '_')}.json")
            v = self.request_validator(command)
            if e["requires_create_owner_scope"]:
                missing = copy.deepcopy(payload)
                del missing["create_owner_scope"]
                self.assertFalse(v.is_valid(missing))
                payload["create_owner_scope"] = {"owner_kind": "system"}
                self.assertFalse(v.is_valid(payload))
            else:
                self.assertFalse(v.is_valid({**payload, "create_owner_scope": {"owner_kind": "subject", "owner_subject_id": "a"}}))
            original = load(FIXTURES / f"request_{command.replace('.', '_')}.json")
            original["expected_access_epoch"] = "01"
            self.assertFalse(v.is_valid(original))

    def test_provisioning_plan_digest_and_command_derived_ids(self) -> None:
        response = load(FIXTURES / "response_provisioning_plan.json")
        preimage = {k: response[k] for k in ("normalized_plan", "references")}
        self.assertEqual(hash_canonical_json(preimage), response["plan_hash"])
        altered = copy.deepcopy(preimage)
        altered["normalized_plan"]["operators"][0]["subject_id"] = "another-subject"
        self.assertNotEqual(hash_canonical_json(altered), response["plan_hash"])
        vectors = load(ROOT / "contracts/trusted-web-id-vectors.v1.json")
        for v in vectors["vectors"]:
            self.assertEqual(command_derived_id(
                command=vectors["command"], command_id=vectors["command_id"],
                prefix=v["row_role"], row_role=v["row_role"], request_path=v["request_path"],
            ), v["expected_id"])

    def test_grants_cannot_mix_families_or_omit_read(self) -> None:
        request = load(FIXTURES / "failure_admin_grant.json")
        v = self.validator("trusted-web-provisioning-plan-request.schema.json")
        for operations, valid in [(["item.read", "item.edit"], True), (["item.edit"], False),
                                  (["catalog.read"], False), (["item.read", "catalog.use"], False)]:
            request["grants"][0]["operations"] = operations
            self.assertEqual(v.is_valid(request), valid)

    def test_pagination_pair_and_budget(self) -> None:
        response = load(FIXTURES / "response_items.json")
        v = self.validator("trusted-web-items-response.schema.json")
        response["has_more"] = True
        self.assertFalse(v.is_valid(response))
        response["next_cursor"] = "opaque-cursor"
        v.validate(response)
        response["entries"] *= 101
        self.assertFalse(v.is_valid(response))

    def test_task_completion_response_cannot_claim_work_cancelled(self) -> None:
        result = {"ok": True, "command": "task.complete", "completed": True, "item_id": "task-a",
                  "item_type": "task", "target_version": "1", "version": "2", "current_version": "2",
                  "updated_at_utc": "2026-09-06T09:00:00Z", "audit_id": "audit-a", "command_receipt_id": "receipt-a"}
        response = {"contract_version": "spine.trusted-web-api.v1", "ok": True,
                    "identity_basis": "self_selected", "account_id": "a", "subject_id": "s", "selection_id": "selection",
                    "access_epoch": "1", "result_contract": "spine.trusted-web-task-complete-result.v1", "result": result,
                    "work_reconciliation": "not_performed_by_this_command"}
        v = self.validator("trusted-web-command-response.schema.json", "#/$defs/task.complete")
        v.validate(response)
        response["work_reconciliation"] = "all_cancelled"
        self.assertFalse(v.is_valid(response))

    def test_failure_shape_cannot_carry_resource_or_sql_details(self) -> None:
        response = load(FIXTURES / "response_denied.json")
        response["error"]["sql"] = "SELECT private_data"
        self.assertFalse(self.validator("trusted-web-error.schema.json").is_valid(response))

    def test_all_future_oracles_are_explicitly_pending(self) -> None:
        acceptance = load(ROOT / "contracts/trusted-web-acceptance.v1.json")
        self.assertEqual(acceptance["status"], "runtime_oracles_pending")
        self.assertEqual(
            [s["id"] for s in acceptance["scenarios"]],
            [f"WEB-{i:02}" for i in range(1, 16)],
        )
        for scenario in acceptance["scenarios"]:
            self.assertEqual(scenario["verification"], "pending_backend")
            self.assertTrue(scenario["given"])
            self.assertTrue(scenario["when"])
            self.assertTrue(scenario["then"])

    def test_private_create_fixture_has_consistent_actor_owner_and_route(self) -> None:
        fixture = load(FIXTURES / "request_schedule_create.json")
        self.assertEqual(fixture["create_owner_scope"]["owner_kind"], "subject")
        subject = fixture["create_owner_scope"]["owner_subject_id"]
        self.assertEqual(fixture["request"]["actor_subject_id"], subject)
        self.assertEqual(fixture["request"]["delivery"]["recipient_subject_id"], subject)


if __name__ == "__main__":
    unittest.main()
