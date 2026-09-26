"""Test-only facet integration oracles; no handlers, ledger or permission runtime.

Golden bytes and decision tables do not prove deployed authorization, races,
notification retention, migration or query plans. Those remain implementation tests.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from spine.core.canonical_json import canonical_json_bytes

ROOT = Path(__file__).parents[1]
VECTORS = ROOT / "tests/fixtures/archetype_facets/vectors"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def unb64(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid_request")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if b64(raw) != value:
        raise ValueError("invalid_request")
    return raw


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_request")
        result[key] = value
    return result


class FacetIntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load(ROOT / "contracts/archetype-facet-integration.v1.json")
        cls.schema = load(ROOT / "contracts/schemas/archetype-facet-cursor.schema.json")
        cls.vector = load(VECTORS / "cursor.json")
        cls.key = cls.vector["public_test_key"].encode()

    def sign(self, raw):
        mac = hmac.digest(self.key, b"spine.facet-cursor.v1\0" + raw, "sha256")
        return "fc1." + b64(raw) + "." + b64(mac)

    def digest(self, domain, value):
        return hmac.digest(self.key, canonical_json_bytes({"contract_version": domain, "value": value}), "sha256").hex()

    def decode(self, token):
        # Independent test oracle for the published byte contract, not runtime code.
        if len(token) > 4096 or not token.isascii():
            raise ValueError("invalid_request")
        prefix, raw, signature = token.split(".")
        raw, signature = unb64(raw), unb64(signature)
        if prefix != "fc1" or not hmac.compare_digest(signature, hmac.digest(self.key, b"spine.facet-cursor.v1\0" + raw, "sha256")):
            raise ValueError("invalid_request")
        payload = json.loads(raw, object_pairs_hook=no_duplicate_keys)
        if canonical_json_bytes(payload) != raw:
            raise ValueError("invalid_request")
        if not Draft202012Validator(self.schema).is_valid(payload):
            raise ValueError("invalid_request")
        return payload

    def continue_page(self, payload, expected, now, keys):
        # Context inputs are supplied fixtures, not a substitute for DB revalidation.
        issued = datetime.fromisoformat(payload["issued_at_utc"])
        expires = datetime.fromisoformat(payload["expires_at_utc"])
        current = datetime.fromisoformat(now)
        if current < issued or expires != issued + timedelta(seconds=900):
            return "invalid_request"
        if any(payload[k] != expected[k] for k in ("command", "query_hash")):
            return "invalid_request"
        deadline = payload["authorization_valid_until_utc"]
        if current >= expires or (deadline is not None and current >= datetime.fromisoformat(deadline)):
            return "stale_cursor"
        if any(payload[k] != expected[k] for k in ("context_hash", "access_hash", "source_snapshot_hash")):
            return "stale_cursor"
        if payload["last_key"] not in keys:
            return "stale_cursor"
        return [key for key in keys if key > payload["last_key"]]

    def test_mapping_is_complete_without_runtime_advertisement(self):
        registry = load(ROOT / "contracts/archetype-facet-contract-registry.v1.json")
        self.assertEqual(self.contract["status"], "draft_not_implemented")
        self.assertEqual(set(self.contract["permission_resolvers"]), set(registry["commands"]))
        self.assertEqual(registry["integration_contract"], "contracts/archetype-facet-integration.v1.json")
        web = load(ROOT / "contracts/spine.trusted-web-command-registry.v1.json")
        self.assertFalse(set(registry["commands"]) & {c["command"] for c in web["commands"]})
        self.assertEqual(self.contract["work"]["current_policy_key"], ["item_id", "notification_intent_id"])
        self.assertEqual(self.contract["work"]["row_mutations"], [])

    def test_permission_decision_vectors(self):
        vectors = load(VECTORS / "permissions.json")
        for case in vectors["catalog_admin_cases"]:
            with self.subTest(case=case):
                allowed = (case["scope"] == "subject" and case["self"]) or (
                    case["scope"] == "subject_group" and case["role"] in {"admin", "owner"}
                )
                self.assertEqual(allowed, case["expected"])
        for case in vectors["reference_cases"]:
            with self.subTest(case=case):
                allowed = case["exists"] and (
                    case["mode"] == "trusted_local" or (case["kind"] == "subject" and case["self"])
                ) and (case["operation"] != "set" or case["kind"] != "subject" or case["active"])
                self.assertEqual(allowed, case["expected"])
        for case in vectors["update_cases"]:
            with self.subTest(case=case["id"]):
                allowed = case["item_edit"] and (
                    not case["fresh_set"] or (case["catalog_use"] and case["reference_read"])
                )
                self.assertEqual(allowed, case["expected"])

    def test_cursor_golden_preimages_and_bytes(self):
        Draft202012Validator.check_schema(self.schema)
        vector = self.vector
        payload = vector["payload"]
        for field, name in (("context_hash", "context"), ("access_hash", "access"), ("source_snapshot_hash", "source")):
            self.assertEqual(payload[field], self.digest(self.contract["cursor"][name + "_domain"], vector[name]))
        self.assertEqual(payload["query_hash"], hashlib.sha256(canonical_json_bytes(vector["query"])).hexdigest())
        self.assertEqual(canonical_json_bytes(payload).decode(), vector["canonical_payload"])
        self.assertEqual(self.sign(canonical_json_bytes(payload)), vector["token"])
        self.assertEqual(self.decode(vector["token"]), payload)
        for command in self.contract["cursor"]["orders"]:
            other = {**payload, "command": command, "last_key": "flight_details"}
            self.assertTrue(Draft202012Validator(self.schema).is_valid(other))

    def test_fresh_set_concrete_item_type_vectors(self):
        rules = self.contract["item_set_compatibility"]
        self.assertEqual(rules["required_membership"], [
            "pinned_assigned_archetype_revision.compatible_item_types",
            "pinned_facet_schema_revision.compatible_item_types",
        ])
        self.assertEqual(rules["applies_to"], "every_fresh_set_including_same_value_noop")
        failure = load(ROOT / "tests/fixtures/archetype_facets/contracts/failure_item_facets_update_incompatible_item_type.json")
        self.assertEqual(failure["error"]["code"], rules["failure"]["code"])
        self.assertEqual(failure["error"]["field"], "item_id")
        for case in load(VECTORS / "permissions.json")["item_type_cases"]:
            with self.subTest(case=case["id"]):
                # All bindings have a legal intersection; the concrete target still matters.
                self.assertTrue(set(case["archetype_types"]) & set(case["schema_types"]))
                compatible = all(case["item_type"] in case[key] for key in ("archetype_types", "schema_types"))
                if case["operation"] == "set":
                    result = "allowed" if compatible else "wrong_item_type"
                else:
                    self.assertIn(case["operation"], rules["skip_for"])
                    result = "allowed"
                self.assertEqual(result, case["expected"])

    def test_closed_replay_authority_vectors(self):
        vectors = load(VECTORS / "permissions.json")
        registry = load(ROOT / "contracts/archetype-facet-contract-registry.v1.json")
        writes = {name for name, entry in registry["commands"].items() if entry["mutates"]}
        mapping = self.contract["replay_permission_resolvers"]
        self.assertEqual(set(mapping), writes)
        self.assertEqual({case["command"] for case in vectors["replay_cases"]}, writes)
        rules = self.contract["replay"]
        self.assertFalse(rules["fresh_write_permissions_required"])
        self.assertFalse(rules["active_catalog_or_binding_required"])
        self.assertFalse(rules["durable_writes"])
        self.assertEqual(rules["permission_enforced_identity"], "same_initiating_account_and_subject")
        self.assertEqual(rules["precedence"], [
            "shape_bounds", "identity_operation_admission", "private_receipt_lookup",
            "initiating_identity", "receipt_disclosure_authority", "semantic_compatibility",
            "release_authority_recheck", "replay_projection",
        ])
        shared = vectors["replay_shared_facts"]
        self.assertTrue(shared["current_identity_eligible"] and shared["operation_registered"])
        for field in ("fresh_write_permission", "catalog_active", "binding_active",
                      "original_request_reference_visible", "current_snapshot_reference_visible",
                      "fresh_expected_version_matches", "fresh_expected_access_epoch_matches"):
            self.assertFalse(shared[field])
        for case in vectors["replay_cases"]:
            required = mapping[case["command"]]
            self.assertEqual(required, case["read_authorities"])
            outcomes = ["changed"] if case["command"] == "facet_schema.create" else shared["original_outcomes"]
            for outcome in outcomes:
                for scenario in vectors["replay_scenarios"]:
                    revoked = required if scenario["revoked_read"] else [None]
                    for denied in revoked:
                        with self.subTest(command=case["command"], outcome=outcome,
                                          scenario=scenario["id"], denied=denied):
                            # Receipt-only disclosure: fresh write/catalog/ref facts above
                            # deliberately cannot authorize or defeat a compatible replay.
                            authorities = {name: name != denied for name in required}
                            if not (scenario["same_account"] and scenario["same_subject"]):
                                result = "command_id_unavailable"
                            elif not all(authorities.values()):
                                result = "resource_unavailable"
                            elif not scenario["semantic_match"]:
                                result = "semantic_conflict"
                            elif not scenario["release_access"]:
                                result = "access_changed"
                            else:
                                result = "replay"
                            self.assertEqual(result, scenario["expected"])

    def test_bounded_page_release_race_vectors(self):
        rules = self.contract["cursor"]["release_revalidation"]
        self.assertEqual(rules["max_snapshot_constructions"], 1)
        self.assertEqual(rules["automatic_retries"], 0)
        self.assertFalse(rules["reset_budget"])
        self.assertFalse(rules["failure_result_or_cursor"])
        self.assertEqual(rules["precedence"], ["current_authority", "capacity", "source_comparison"])
        for case in self.vector["release_race_cases"]:
            with self.subTest(case=case["id"]):
                if case["authority"] != "allowed":
                    result = case["authority"]
                    if result == "access_changed" and not case["continuation"]:
                        result = rules["first_page_access_transition"]
                elif not case["within_budget"]:
                    result = "capacity"
                elif case["source_changed"]:
                    branch = "continuation_source_change" if case["continuation"] else "first_page_source_change"
                    result = rules[branch]
                else:
                    result = "page"
                self.assertEqual(result, case["expected"])
        self.assertEqual(self.contract["adapter_errors"]["first_page_source_changed"], {
            "cli": "environment_failure", "exit": 7, "web": "access_changed", "http": 409,
        })
        self.assertEqual(self.contract["adapter_errors"]["stale_cursor"], {
            "cli": "stale_cursor", "exit": 6, "web": "access_changed", "http": 409,
        })

    def test_cursor_rejects_authenticated_bad_encodings_and_payloads(self):
        payload = self.vector["payload"]
        raw = canonical_json_bytes(payload)
        duplicate = raw[:-1] + b',"command":"item.facets.query"}'
        malformed = [self.sign(duplicate), self.sign(b" " + raw), self.sign(canonical_json_bytes({**payload, "extra": True}))]
        parts = self.vector["token"].split(".")
        malformed += ["fc1." + parts[1] + "=." + parts[2], "fc1." + parts[1] + "." + b64(b"x" * 32), "x" * 4097]
        malformed += [self.sign(canonical_json_bytes({**payload, "command": "agenda"}))]
        for token in malformed:
            with self.subTest(token_prefix=token[:12]), self.assertRaisesRegex(ValueError, "invalid_request"):
                self.decode(token)

    def test_cursor_context_expiry_snapshot_and_order_vectors(self):
        expected = self.vector["payload"]
        now = self.vector["valid_now"]
        keys = ["flight-a", "flight-b"]
        self.assertEqual(self.continue_page(expected, expected, now, keys), ["flight-b"])
        for field in ("context_hash", "query_hash", "access_hash", "source_snapshot_hash"):
            with self.subTest(field=field):
                changed = {**expected, field: "0" * 64}
                code = "invalid_request" if field == "query_hash" else "stale_cursor"
                self.assertEqual(self.continue_page(changed, expected, now, keys), code)
        self.assertEqual(self.continue_page(expected, expected, expected["expires_at_utc"], keys), "stale_cursor")
        self.assertEqual(self.continue_page(expected, expected, "2026-09-26T09:59:59Z", keys), "invalid_request")
        self.assertEqual(self.continue_page({**expected, "authorization_valid_until_utc": now}, expected, now, keys), "stale_cursor")
        self.assertEqual(self.continue_page(expected, expected, now, ["flight-b"]), "stale_cursor")
        self.assertEqual(self.continue_page({**expected, "command": "facet_schema.list"}, expected, now, keys), "invalid_request")
        source = copy.deepcopy(self.vector["source"])
        source["facts"]["candidates"][1]["current_version"] = "2"
        self.assertNotEqual(self.digest(self.contract["cursor"]["source_domain"], source), expected["source_snapshot_hash"])

    def test_notification_continuity_decisions(self):
        vectors = load(VECTORS / "work_freshness.json")
        rule = self.contract["work"]
        fields = rule["comparison_policy_fields"]
        prior = vectors["before_policy"]
        successor = vectors["after_policy"]
        # Three copy-forwards: same stable intent, different row IDs, no one-hop link.
        self.assertNotEqual(prior["notification_policy_id"], successor["source_notification_policy_id"])
        self.assertEqual({k: prior.get(k) for k in fields}, {k: successor.get(k) for k in fields})
        for case in vectors["cases"]:
            with self.subTest(case=case["id"]):
                current = dict(successor)
                if case["semantic_change"]:
                    current[case["semantic_change"]] = "different"
                same = {k: prior.get(k) for k in fields} == {k: current.get(k) for k in fields}
                evaluated = False
                if case["replayed"] or not case["changed"]:
                    effect = "no_reconciliation"
                elif not same:
                    effect = "environment_failure"
                else:
                    evaluated = case["has_policy"] or case["has_work"]
                    effect = rule["states"][case["state"]]
                self.assertEqual(effect, case["expected"])
                self.assertEqual(evaluated, case["evaluated"])

    def test_existing_binding_version_boundary_is_not_weakened(self):
        vectors = load(VECTORS / "work_freshness.json")
        for case in vectors["binding_cases"]:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["target_due_unchanged"])
                state = "current" if case["bound_source_version"] == case["current_source_version"] else "stale"
                self.assertEqual(state, case["expected"])

    def test_pagination_budget_query_limit_and_child_expiry(self):
        rules = self.contract["cursor"]
        self.assertEqual(rules["max_candidates"], 100)
        self.assertEqual(rules["max_access_proof_rows"], 100)
        self.assertFalse(rules["durable_read_writes"])
        query = copy.deepcopy(self.vector["query"])
        query["request"]["limit"] = "2"
        self.assertNotEqual(hashlib.sha256(canonical_json_bytes(query)).hexdigest(), self.vector["payload"]["query_hash"])
        child = {**self.vector["payload"], "last_key": "flight-b"}
        decoded = self.decode(self.sign(canonical_json_bytes(child)))
        for field in self.vector["payload"]:
            if field != "last_key":
                self.assertEqual(decoded[field], self.vector["payload"][field])


if __name__ == "__main__":
    unittest.main()
