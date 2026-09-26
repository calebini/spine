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
