"""Offline bootstrap wire/finite-model witnesses, not runtime or SQL evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urldefrag, urljoin

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands.receipts import command_derived_id
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.canonical_json import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "https://cortext.local/spine/contracts/schemas/"
SCHEMAS = "contracts/schemas/local-ownership-bootstrap/"
FIXTURES = "tests/fixtures/local_ownership_bootstrap/"
INSTANCE = "ledger_instance_" + "1" * 64
MAXIMUM = 9223372036854775807


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def references(node):
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for value in node.values():
            yield from references(value)
    elif isinstance(node, list):
        for value in node:
            yield from references(value)


def canonical_oracle(value):
    """Independent canonical encoding for this ASCII-only fixture corpus."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if not raw.isascii():
        raise AssertionError("Expand the independent encoder before adding Unicode vectors")
    return raw.encode("utf-8")


def epoch_witness(vector):
    """Finite declared branch oracle; no SQL, command dispatch or mutable ledger."""
    before = copy.deepcopy(vector["before"])
    state, consumed, stack, error = copy.deepcopy(before), False, [], None
    for event in vector["events"]:
        if event == "savepoint":
            stack.append((copy.deepcopy(state), consumed))
        elif event == "rollback_to_savepoint":
            state, consumed = copy.deepcopy(stack[-1])
        elif event == "release_savepoint":
            stack.pop()
        elif event == "outer_rollback":
            state, consumed = copy.deepcopy(before), False
            break
        elif event == "owner" and not consumed:
            if state is None:
                state = dict(singleton_id="1", ledger_id=INSTANCE, realm_id=None, mode="trusted_local",
                             identity_mode=None, access_epoch="1", recovery_epoch="1")
            elif int(state["access_epoch"]) == MAXIMUM:
                state, error = copy.deepcopy(before), "epoch_overflow"
                break
            else:
                state["access_epoch"] = str(int(state["access_epoch"]) + 1)
            consumed = True
        else:
            if event not in {"owner", "read", "replay", "no_op"}:
                raise AssertionError(event)
    if vector["dry_run"]:
        state = before
    return state, error


class LocalOwnershipBootstrapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.descriptor = read("contracts/local-ownership-bootstrap.v1.json")
        cls.manifest = read(cls.descriptor["fixture_manifest"])
        cls.schemas = {}
        pending = list(cls.descriptor["schemas"]) + ["contracts/schemas/trusted-web-error.schema.json"]
        while pending:
            path = pending.pop()
            schema = read(path)
            uri = schema["$id"]
            if uri in cls.schemas:
                continue
            cls.schemas[uri] = schema
            for reference in references(schema):
                target, _ = urldefrag(urljoin(uri, reference))
                if not target.startswith(PREFIX):
                    raise AssertionError("No network schema fallback: " + target)
                target_path = "contracts/schemas/" + target.removeprefix(PREFIX)
                if target not in cls.schemas:
                    pending.append(target_path)
        cls.registry = Registry().with_resources((uri, Resource.from_contents(s)) for uri, s in cls.schemas.items())

    def validator(self, path):
        schema = read(path)
        return Draft202012Validator(schema, registry=self.registry, format_checker=FormatChecker())

    def test_schema_closure_and_all_fixture_polarities(self):
        for uri, schema in self.schemas.items():
            Draft202012Validator.check_schema(schema)
            for reference in references(schema):
                target, fragment = urldefrag(urljoin(uri, reference))
                at = self.schemas[target]
                for part in fragment.split("/")[1:]:
                    part = part.replace("~1", "/").replace("~0", "~")
                    at = at[int(part)] if isinstance(at, list) else at[part]
        paths, identities = [], []
        for fixture in self.manifest["fixtures"]:
            with self.subTest(fixture=fixture["fixture_id"]):
                errors = list(self.validator(fixture["schema"]).iter_errors(read(fixture["fixture"])))
                self.assertEqual(not errors, fixture["valid"], [e.message for e in errors])
                paths.append(ROOT / fixture["fixture"])
                identities.append(fixture["fixture_id"])
        self.assertEqual(len(set(identities)), len(identities))
        self.assertEqual(set(paths), set((ROOT / FIXTURES).glob("*.json")))

    def test_epoch_and_savepoint_finite_witnesses(self):
        vectors = read(FIXTURES + "transition_vectors.json")["vectors"]
        self.assertEqual(len(vectors), len({v["case_id"] for v in vectors}))
        for vector in vectors:
            with self.subTest(case=vector["case_id"]):
                self.assertEqual(epoch_witness(vector), (vector["expected"], vector["error"]))

    def test_positive_epoch_exact_boundaries_and_null_postures(self):
        validator = self.validator(SCHEMAS + "state.schema.json")
        sample = read(FIXTURES + "state_local.json")
        for value in ("1", "9", "10", "9223372036854775806", str(MAXIMUM)):
            candidate = copy.deepcopy(sample)
            candidate["state"]["access_epoch"] = value
            self.assertTrue(validator.is_valid(candidate), value)
        for value in ("0", "-1", "+1", "01", "1\n", "1.0", "1e1", str(MAXIMUM + 1), True, 1):
            candidate = copy.deepcopy(sample)
            candidate["state"]["access_epoch"] = value
            self.assertFalse(validator.is_valid(candidate), value)
        configured = read(FIXTURES + "state_configured.json")
        for field in ("realm_id", "identity_mode"):
            candidate = copy.deepcopy(configured)
            candidate["state"][field] = None
            self.assertFalse(validator.is_valid(candidate))

    def test_plan_digest_exact_preimage_and_stale_witness(self):
        for row in self.manifest["computed_plan_digests"] + self.manifest["computed_apply_digests"]:
            preimage = read(row["fixture"])
            encoded = canonical_oracle(preimage)
            self.assertEqual(encoded, canonical_json_bytes(preimage))
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), row["sha256"])
        for name in ("absent", "local", "configured", "no_operator"):
            response = read(FIXTURES + "response_plan_" + name + ".json")
            preimage = {key: response[key] for key in self.descriptor["plan_hash_fields"] if key != "contract_version"}
            preimage["contract_version"] = response["contract_version"]
            self.assertEqual(hashlib.sha256(canonical_oracle(preimage)).hexdigest(), response["plan_hash"])
        original = read(FIXTURES + "preimage_plan_local.json")
        digest = hashlib.sha256(canonical_oracle(original)).hexdigest()
        for field, value in (("access_epoch", "2"), ("recovery_epoch", "2"), ("ledger_id", INSTANCE[:-1] + "2")):
            altered = copy.deepcopy(original)
            altered["access_state_before"][field] = value
            self.assertNotEqual(hashlib.sha256(canonical_oracle(altered)).hexdigest(), digest)
        altered = copy.deepcopy(original)
        altered["normalized_plan"]["realm_id"] = "different-realm"
        self.assertNotEqual(hashlib.sha256(canonical_oracle(altered)).hexdigest(), digest)

    def test_existing_row_id_derivation_and_replay_projection(self):
        request = read(FIXTURES + "request_apply_local.json")
        response = read(FIXTURES + "response_apply_local.json")
        replay = read(FIXTURES + "response_apply_replay.json")
        self.assertEqual(replay, {**response, "replayed": True})
        preimage = {key: request[key] for key in ("contract_version", "actor_subject_id", "action_timestamp_utc",
                                                "expected_access_epoch")}
        preimage.update(normalized_plan=request["plan"]["normalized_plan"], plan_hash=request["plan"]["plan_hash"],
                        realm_id=request["plan"]["normalized_plan"]["realm_id"])
        self.assertEqual(preimage, read(FIXTURES + "preimage_apply_local.json"))
        self.assertEqual(set(preimage), set(self.descriptor["apply_semantic_hash_fields"]))
        for field, role, path in (("command_receipt_id", "command_receipt", "/"), ("audit_id", "access_audit", "/audit")):
            self.assertEqual(response[field], command_derived_id(prefix=role, command="web_access.apply",
                             command_id=request["command_id"], row_role=role, request_path=path))

    def test_successors_are_not_runtime_or_frozen_web_activation(self):
        self.assertEqual(IMPLEMENTED_LEDGER_SCHEMA_VERSION, 19)
        self.assertTrue(set(self.descriptor["proposed_contract_versions"]).isdisjoint(IMPLEMENTED_CONTRACT_VERSIONS))
        self.assertNotIn("ownership.bootstrap", COMMAND_RUNTIME_CONTRACT_REGISTRY)
        packaged = ROOT / "src/spine/contracts/web/schemas/local-ownership-bootstrap"
        self.assertFalse(packaged.exists())
        for name in ("plan", "apply"):
            self.assertNotIn("spine.trusted-web-provisioning.v3",
                             COMMAND_RUNTIME_CONTRACT_REGISTRY["web_access." + name].required_contract_versions)
        v2 = self.validator("contracts/schemas/trusted-web-provisioning-plan-request.v2.schema.json")
        request = read(FIXTURES + "request_plan_local.json")
        self.assertFalse(v2.is_valid(request))
        request["contract_version"] = "spine.trusted-web-provisioning.v2"
        self.assertFalse(v2.is_valid(request))  # explicit realm is not a v2 extension map

    def test_migration_contract_is_definition_only_with_fk_and_null_guards(self):
        migration = read(self.descriptor["migration_contract"])
        self.assertIsNone(migration["target_schema"])
        self.assertFalse(migration["runtime_verified"])
        self.assertEqual(migration["preserve_fk_targets"][0]["references_table"], "ledger_access_state")
        self.assertEqual(migration["temporarily_drop_and_recreate_verbatim_triggers"],
                         ["web_group_status_changed", "web_route_security_changed", "web_subject_status_changed"])
        self.assertEqual(migration["column_order"], ["singleton_id", "ledger_id", "realm_id", "mode",
                                                     "identity_mode", "access_epoch", "recovery_epoch"])
        ddl = migration["changed_objects"][0]["target_definition_sql"]
        self.assertIn("typeof(identity_mode) = 'text'", ddl)  # NULL must not make SQL CHECK UNKNOWN pass
        self.assertIn("realm_id IS NULL AND identity_mode IS NULL", ddl)
        self.assertNotIn("CREATE TABLE ledger_access_state_bootstrap_new", ddl)
        self.assertTrue(all(o["status"] == "pending_runtime" for o in self.descriptor["runtime_obligations"]))
        self.assertFalse(self.manifest["runtime_verified"])

    def test_specification_local_links_resolve(self):
        path = ROOT / self.descriptor["specification"]
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" not in target:
                self.assertTrue((path.parent / target.split("#")[0]).is_file(), target)


if __name__ == "__main__":
    unittest.main()
