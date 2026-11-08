"""Source-only RRT wire, identity and finite model witnesses; no runtime claims.

Nothing here opens a ledger, dispatches a command or starts a worker. Actual SQL,
migration, locking, freshness/attempt races and scheduler behavior remain the
manifest's pending runtime obligations.
"""

import base64
import copy
import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urljoin

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from scripts.build_recurring_related_task_contract_fixtures import build
from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.notifications import normalize_notification_policy, revise_notification_policy

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = "contracts/schemas/recurring-related-tasks/"
FIXTURES = "tests/fixtures/recurring_related_tasks/"
FAMILY = "spine.recurring-related-tasks.v1"
CURSOR = "spine.recurring-related-tasks.cursor.v1"
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def valid_date_time(value):
    # jsonschema's optional date-time plugin is not installed in every dev
    # environment. Never silently skip actual Gregorian date validation.
    if not isinstance(value, str):
        return True
    return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def oracle_canonical(value):
    """Small independent encoder from the normative rules, not production code."""
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("surrogate")
        escaped = "".join('\\"' if c == '"' else "\\\\" if c == "\\" else f"\\u{ord(c):04x}" if ord(c) < 32 else c for c in value)
        return '"' + escaped + '"'
    if isinstance(value, list):
        return "[" + ",".join(map(oracle_canonical, value)) + "]"
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return "{" + ",".join(oracle_canonical(k) + ":" + oracle_canonical(value[k]) for k in sorted(value)) + "}"
    raise ValueError("noncanonical value")


def oracle_digest(value):
    return hashlib.sha256(oracle_canonical(value).encode()).hexdigest()


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decision_model(family, f):
    """Finite declared branch oracle, not an executable task/recurrence engine."""
    if family == "cutoff":
        if instant(f["commit"]) < instant(f["evaluation"]):
            return "environment_failure"
        if f["exists"]:
            return "retain"
        if not f["source_actionable"] or not f["enrolled"] or instant(f["due"]) <= instant(f["evaluation"]):
            return "skip"
        return "create" if instant(f["due"]) > instant(f["commit"]) else "stale_evaluation"
    if family == "restore":
        if f["veto"] or f["task_done"] or f["manual_exception"] or f["successor_exists"] or not f["active_rule"]:
            return "retain"
        if not f["one_to_one_proof"]:
            return "decision_required"
        return "new_successor" if f["source_restored"] and f["latest_source_cancelled"] and f["future_due"] else "retain"
    if family == "adoption":
        if not f["eligible"]:
            return "skip"
        if f["current"] == f["desired"]:
            return "adopt_witness"
        return "adopt" if f["current"] == f["baseline"] else "conflict"
    if family == "retirement":
        if not f["open_governed"]:
            return "preserve"
        return {"keep_following": "follow", "detach_open": "detach", "cancel_open": "cancel"}[f["disposition"]]
    if family == "continuity":
        return "same_assignment" if (f["exact"] or f["positive_lineage"]) and f["matches"] == "1" else "decision_required"
    if family == "budget":
        if int(f["unit"]) > min(int(f["limit"]), int(f["hard"])):
            return "capacity_exceeded"
        return "process" if int(f["used"]) + int(f["unit"]) <= int(f["limit"]) else "continue"
    if family == "scheduler":
        return "dispatch" if f["domain_change"] or f["semantic_progress"] else "no_dispatch"
    raise AssertionError(family)


class RecurringRelatedTaskContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = read("contracts/recurring-related-task-fixture-manifest.json")
        cls.descriptor = read(cls.manifest["registry"])
        cls.closure = read(cls.manifest["schema_closure"])
        cls.schemas = {r["path"]: read(r["path"]) for r in cls.closure["resources"]}
        cls.registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in cls.schemas.values())
        cls.computed = read(cls.manifest["computed"])
        cls.by_case = {v["case_id"]: v for v in cls.computed["vectors"]}
        cls.evidence = read(cls.manifest["evidence"])
        cls.fixtures = {r["fixture_id"]: read(r["fixture"]) for r in cls.manifest["fixtures"]}

    def validator(self, path, fragment=None):
        schema = self.schemas[path]
        if fragment:
            schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": schema["$id"] + "#/$defs/" + fragment}
        return Draft202012Validator(schema, registry=self.registry, format_checker=FORMATS)

    def valid_def(self, resource, definition, value):
        self.validator(SCHEMAS + resource + ".schema.json", definition).validate(value)

    def test_schema_closure_exact_hashes_unique_ids_and_fragments(self):
        by_uri = {s["$id"]: s for s in self.schemas.values()}
        self.assertEqual(len(by_uri), len(self.schemas))
        visited = set()

        def walk(node, uri):
            if isinstance(node, dict):
                if "$ref" in node:
                    target, fragment = urldefrag(urljoin(uri, node["$ref"]))
                    self.assertIn(target, by_uri)  # No resolver network fallback.
                    at = by_uri[target]
                    for part in fragment.split("/")[1:]:
                        key = part.replace("~1", "/").replace("~0", "~")
                        at = at[int(key)] if isinstance(at, list) else at[key]
                    if target not in visited:
                        visited.add(target)
                        walk(by_uri[target], target)
                for value in node.values():
                    walk(value, uri)
            elif isinstance(node, list):
                for value in node:
                    walk(value, uri)

        for row in self.closure["resources"]:
            self.assertEqual(row["sha256"], hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest())
            self.assertEqual(row["uri"], self.schemas[row["path"]]["$id"])
            Draft202012Validator.check_schema(self.schemas[row["path"]])
            if row["path"].startswith(SCHEMAS):
                visited.add(row["uri"])
                walk(self.schemas[row["path"]], row["uri"])
        self.assertEqual(visited, set(by_uri))
        self.assertEqual(
            {str(p.relative_to(ROOT)) for p in (ROOT / SCHEMAS).glob("*.json")}, {p for p in self.schemas if p.startswith(SCHEMAS)}
        )

    def test_fixture_inventory_shapes_and_positive_negative_expectations(self):
        paths, ids = set(), set()
        for row in self.manifest["fixtures"]:
            with self.subTest(fixture=row["fixture_id"]):
                self.assertEqual(set(row), {"fixture_id", "fixture", "schema", "valid"})
                self.assertIs(type(row["valid"]), bool)
                self.assertNotIn(row["fixture"], paths)
                self.assertNotIn(row["fixture_id"], ids)
                paths.add(row["fixture"])
                ids.add(row["fixture_id"])
                errors = list(self.validator(row["schema"]).iter_errors(read(row["fixture"])))
                self.assertEqual(not errors, row["valid"], "\n".join(str(e.json_path) + ": " + e.message[:200] for e in errors[:4]))
        self.assertEqual(paths, {str(p.relative_to(ROOT)) for p in (ROOT / FIXTURES / "contracts").glob("*.json")})
        for name in ("create", "update", "retire", "suppress", "reconcile", "list", "show"):
            self.assertTrue(any(r["schema"] == SCHEMAS + name + "-request.schema.json" and r["valid"] for r in self.manifest["fixtures"]))
            self.assertTrue(any(r["schema"] == SCHEMAS + name + "-response.schema.json" and r["valid"] for r in self.manifest["fixtures"]))

    def test_source_only_boundary_and_exact_existing_prerequisites(self):
        self.assertFalse(self.descriptor["runtime_implemented"])
        self.assertFalse(self.manifest["runtime_verified"])
        self.assertEqual(self.descriptor["status"], "draft_machine_contract")
        self.assertEqual(self.descriptor["exposure"], "trusted_local_only")
        self.assertIsNone(self.descriptor["ledger_schema_version"])
        proposed = self.descriptor["proposed_contract_versions"]
        self.assertFalse(set(proposed) & set(IMPLEMENTED_CONTRACT_VERSIONS))
        self.assertFalse(set(self.descriptor["commands"]) & set(COMMAND_RUNTIME_CONTRACT_REGISTRY))
        deps = self.descriptor["required_existing_contract_versions"]
        self.assertEqual(deps, sorted(set(deps)))
        self.assertLessEqual(set(deps), set(IMPLEMENTED_CONTRACT_VERSIONS))
        for path in [
            "contracts/spine.trusted-web-command-registry.v1.json",
            "contracts/spine.trusted-web-facet-registry.v1.json",
            "contracts/spine.trusted-web-people-registry.v1.json",
        ]:
            if (ROOT / path).exists():
                self.assertFalse(set(self.descriptor["commands"]) & {r["command"] for r in read(path)["commands"]})
        self.assertFalse((ROOT / "src/spine/contracts/web/schemas/recurring-related-tasks").exists())
        self.assertEqual(set(self.manifest["runtime_obligations"]), {r["id"] for r in self.descriptor["runtime_obligations"]})
        self.assertTrue(all(r["status"] == "pending_runtime_verification" for r in self.descriptor["runtime_obligations"]))

    def test_deterministic_builder_matches_retained_artifacts(self):
        for path, expected in build().items():
            with self.subTest(path=path):
                self.assertEqual(read(path), expected)

    def test_numeric_timestamp_and_closed_input_boundaries(self):
        for field, (default, maximum) in self.descriptor["limits"]["page"].items():
            validator = self.validator(SCHEMAS + "types.schema.json", "limits")
            for good in ("1", str(default), str(maximum)):
                validator.validate({field: good})
            for bad in ("0", "01", "-1", str(maximum + 1), maximum, True, "1\n", "1.0", "1e2", "١"):
                with self.subTest(field=field, bad=bad):
                    self.assertFalse(validator.is_valid({field: bad}))
        for definition, good, bad in [
            ("positive", ["1", "9223372036854775807"], ["0", "9223372036854775808", "1\n", 1]),
            ("offset", ["-31622400", "0", "31622400"], ["-0", "+1", "01", "31622401", "-31622401"]),
            ("utc", ["2026-11-08T10:00:00Z"], ["2026-02-30T10:00:00Z", "2026-11-08T10:00:00.1Z", "2026-11-08T10:00:00+00:00"]),
        ]:
            validator = self.validator(SCHEMAS + "types.schema.json", definition)
            for value in good:
                validator.validate(value)
            for value in bad:
                self.assertFalse(validator.is_valid(value), (definition, value))
        update = copy.deepcopy(self.fixtures["request_update_upcoming"])
        del update["configuration"]["generation_horizon_seconds"]
        self.assertFalse(self.validator(SCHEMAS + "update-request.schema.json").is_valid(update))

    def test_closed_effects_errors_and_read_write_preview_replay(self):
        reasons = self.schemas[SCHEMAS + "types.schema.json"]["$defs"]["reason"]["enum"]
        self.assertEqual(len(reasons), len(set(reasons)))
        code_fixtures = {v["error"]["code"] for name, v in self.fixtures.items() if name.startswith("failure_")}
        self.assertEqual(code_fixtures, set(self.descriptor["error_codes"]))
        for name in ("create", "update", "retire", "suppress", "reconcile", "show", "list"):
            envelope = self.schemas[SCHEMAS + "responses.schema.json"]["$defs"][name]
            effects = self.descriptor["effects"][name]
            self.assertEqual(set(envelope["properties"]["effect"]["enum"]), set(effects[0] + effects[1]))
            command = "schedule.related_task_rule." + ("assignment.suppress" if name == "suppress" else name)
            observed = {
                value["effect"]
                for key, value in self.fixtures.items()
                if key.startswith("response_") and value["command"] == command
            }
            self.assertEqual(observed, set(effects[0] + effects[1]))
        original = self.fixtures["response_create"]
        replay = copy.deepcopy(self.fixtures["response_create_replay"])
        replay["replayed"] = False
        self.assertEqual(replay, original)
        preview = self.fixtures["response_create_preview"]
        self.assertIsNone(preview["command_receipt_id"])
        self.assertEqual(preview["audit_ids"], [])
        self.assertTrue(preview["commit_cutoff_recheck_required"])
        self.assertFalse(preview["replayed"])
        for name, value in self.fixtures.items():
            if name.startswith("response_"):
                self.assertEqual(value["result"]["delivery"], "not_attempted_by_command")
                if value["command"].endswith((".list", ".show")):
                    self.assertTrue(value["commit_cutoff_recheck_required"])
                    self.assertFalse({"command_id", "command_receipt_id", "audit_ids", "replayed"} & set(value))

    def test_computed_preimages_golden_bytes_hashes_and_prefixes(self):
        self.assertFalse(self.computed["runtime_verified"])
        self.assertEqual(len(self.by_case), len(self.computed["vectors"]))
        self.validator(SCHEMAS + "computed.schema.json").validate(self.computed)
        artifact_names = set()
        for row in self.computed["vectors"]:
            with self.subTest(vector=row["case_id"]):
                artifact_names.add(row["artifact"])
                expected_bytes = oracle_canonical(row["preimage"]).encode()
                self.assertEqual(row["canonical_json"].encode(), expected_bytes)
                self.assertEqual(canonical_json_bytes(row["preimage"]), expected_bytes)
                self.assertEqual(row["sha256"], hashlib.sha256(expected_bytes).hexdigest())
                self.assertEqual(row["value"], (row["prefix"] + "_" if row["prefix"] else "") + row["sha256"])
        self.assertEqual(artifact_names, set(self.schemas[SCHEMAS + "preimages.schema.json"]["$defs"]))
        unicode_row = self.by_case["unicode_control_configuration"]
        self.assertIn('Zoë — 科学 🧪\\u000a\\"entrance\\"\\u0009', unicode_row["canonical_json"])
        for value in (1, 1.0, {"a": "\ud800"}):
            with self.assertRaises((SpineValidationError, UnicodeEncodeError)):
                canonical_json_bytes(value)
        self.assertNotEqual(oracle_digest({"a": None}), oracle_digest({}))
        self.assertNotEqual(oracle_digest(["a", "b"]), oracle_digest(["b", "a"]))
        self.assertEqual(oracle_digest({"b": False, "a": None}), oracle_digest({"a": None, "b": False}))

    def test_selector_slot_identity_and_child_generation_independence(self):
        a = self.by_case["related_task_assignment"]
        self.assertNotIn("recurrence_revision_id", a["preimage"])
        self.assertNotIn("ordinal", a["preimage"])
        self.assertNotEqual(a["value"], self.by_case["next_week_assignment"]["value"])
        selector = a["preimage"]["initial_selector"]
        self.valid_def("types", "sourceSelector", selector)
        self.assertEqual(self.by_case["first_selector_ref"]["preimage"], selector)
        self.assertEqual(self.by_case["first_occurrence_key"]["preimage"]["target_occurrence_selector"], selector)
        for field in (
            "task_item_id",
            "due_anchor_id",
            "relationship_id",
            "temporal_binding_id",
            "temporal_binding_revision_id",
            "item_access_owner_id",
        ):
            initial, restored = self.by_case["initial_" + field], self.by_case["restored_" + field]
            self.assertNotEqual(initial["value"], restored["value"])
            self.assertEqual(initial["preimage"]["command_id"], self.by_case["related_task_generation"]["value"])
            self.assertEqual(restored["preimage"]["command_id"], self.by_case["restoration_generation"]["value"])
            self.assertEqual(initial["preimage"]["command"], "schedule.related_task_rule.reconcile")
            self.assertEqual(set(initial["preimage"]), {"derivation_version", "command", "command_id", "row_role", "request_path"})

    def test_policy_tokens_due_reminder_and_intent_preserving_copy(self):
        example = self.evidence["schedule_example"]
        self.assertEqual(
            instant(example["task_due_utc"]), instant(example["expressed_start_utc"]) + timedelta(seconds=int(example["offset_seconds"]))
        )
        self.assertEqual(
            instant(example["eligible_at_utc"]),
            instant(example["task_due_utc"]) + timedelta(seconds=int(example["reminder_offset_seconds"])),
        )
        policies = self.evidence["policies"]
        self.assertNotEqual(policies[0]["notification_intent_id"], policies[1]["notification_intent_id"])
        for suffix, policy in zip(("initial", "restored"), policies, strict=True):
            token = policy["intent_created_by_command_id"]
            generation = self.by_case["related_task_generation" if suffix == "initial" else "restoration_generation"]["value"]
            self.assertEqual(token, generation + ":pickup_ten_minutes")
            self.assertEqual(policy["created_by_command_id"], token)
            self.assertNotEqual(token, self.fixtures["response_reconcile_created"]["command_id"])
            revised = revise_notification_policy(
                policy,
                item_version="2",
                command_id="fixture_real_adoption",
                changed_at_utc="2026-11-08T10:01:00Z",
                recipient_kind="subject_group",
                recipient_id="fixture_kinflow",
                channel="fixture_channel",
                delivery_target_id="delivery_target_fixture",
                target=policy["target"],
                schedule=policy["schedule"],
                late_handling=policy["late_handling"],
            )
            self.assertEqual(revised.value["notification_intent_id"], policy["notification_intent_id"])
            self.assertEqual(revised.value["intent_created_by_command_id"], token)
        first = policies[0]
        other = normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": first["target"],
                "schedule": first["schedule"],
                "late_handling": first["late_handling"],
            },
            item_id=first["item_id"],
            item_version="1",
            command_id=self.by_case["related_task_generation"]["value"] + ":pickup_second_policy",
            created_at_utc=first["created_at_utc"],
            recipient_kind="subject_group",
            recipient_id="fixture_kinflow",
            channel="fixture_channel",
            delivery_target_id="delivery_target_fixture",
        )
        self.assertNotEqual(first["notification_intent_id"], other.value["notification_intent_id"])
        self.assertEqual({o["eligible_at_utc"] for o in self.evidence["opportunities"]}, {example["eligible_at_utc"]})

    def test_typed_proof_and_state_evidence_reference_equality(self):
        proofs = {p["proof_id"]: p for p in self.evidence["proofs"]}
        self.assertEqual(
            {p["proof_kind"] for p in proofs.values()},
            {
                "enrollment",
                "identity",
                "carry_forward",
                "component_candidate",
                "new_rdate",
                "excluded",
                "occurrence_cancelled",
                "source_cancelled",
            },
        )
        for proof in proofs.values():
            self.valid_def("evidence", "proofRecord", proof)
            payload = proof["proof_json"]
            self.assertEqual(proof["source_item_version"], payload["source_item_version"])
            self.assertEqual(proof["recurrence_revision_id"], payload["recurrence_revision_id"])
            self.assertEqual(payload["lineage_ids"], sorted(set(payload["lineage_ids"])))
            preimage = {
                "canonical_json_version": "spine.canonical-json.v1",
                "contract_version": FAMILY,
                "derivation_version": "spine.related-task-proof-id.v1",
                "related_task_rule_id": proof["related_task_rule_id"],
                "proof_kind": proof["proof_kind"],
                "proof_payload": payload,
            }
            self.assertEqual(proof["proof_hash"], oracle_digest(preimage))
            self.assertEqual(proof["proof_id"], "related_task_proof_" + proof["proof_hash"])
            if "prior_proof_id" in payload:
                self.assertIn(payload["prior_proof_id"], proofs)
            if proof["proof_kind"] == "source_cancelled":
                self.assertNotIn("selector", payload)
                self.assertNotIn("occurrence_key", payload)
                self.assertEqual(payload["lineage_ids"], [])
        previous = None
        for row in self.evidence["states"]:
            self.valid_def("evidence", "stateRecord", row)
            self.assertEqual(row["prior_assignment_revision_id"], previous)
            previous = row["assignment_revision_id"]
            for key in (
                "task_item_id",
                "task_item_version",
                "source_item_version",
                "recurrence_revision_id",
                "generation_id",
                "adopted_rule_revision_id",
                "temporal_binding_revision_id",
                "proof_id",
            ):
                self.assertEqual(row[key], row["state_json"][key])
            source_proof = proofs[row["proof_id"]]
            self.assertEqual(row["source_item_version"], source_proof["source_item_version"])
            self.assertEqual(row["recurrence_revision_id"], source_proof["recurrence_revision_id"])
        for resource, rows in [
            ("generationRecord", self.evidence["generations"]),
            ("intentRecord", self.evidence["intents"]),
            ("suppression", self.evidence["suppressions"]),
            ("cancellation", self.evidence["source_cancellations"]),
        ]:
            for row in rows:
                self.valid_def("evidence", resource, row)
        cancellation = self.evidence["source_cancellations"][0]
        self.assertEqual(cancellation["assignment_revision_id"], self.evidence["states"][1]["assignment_revision_id"])
        self.assertEqual(cancellation["proof_id"], self.evidence["states"][1]["proof_id"])
        suppressed = self.fixtures["response_suppress"]
        self.assertEqual(suppressed["command_receipt_id"], suppressed["result"]["suppression"]["command_receipt_id"])
        self.assertEqual(suppressed["result"]["assignment"]["assignment_revision_id"], self.evidence["states"][2]["assignment_revision_id"])

    def test_owner_header_history_and_page_work_projections(self):
        for row in self.evidence["owners"]:
            self.valid_def("evidence", "ownerHeader", row["header"])
            self.valid_def("evidence", "ownerRevision", row["revision"])
            self.assertIsNone(row["header"]["creator_entitlement_subject_id"])
            self.assertEqual(row["header"]["created_by_command_id"], self.fixtures["response_reconcile_created"]["command_id"])
            self.assertEqual(row["header"]["item_access_owner_id"], self.by_case["initial_item_access_owner_id"]["value"])
            self.assertEqual(
                row["header"]["owner_group_id"], self.fixtures["request_create_pickup"]["configuration"]["task_owner"]["owner_group_id"]
            )
        page = self.fixtures["response_reconcile_created"]["result"]
        seen = set()
        for rows in page["work"].values():
            self.assertEqual(rows, sorted(set(rows)))
            self.assertFalse(set(rows) & seen)
            seen.update(rows)
        for entry in page["results"]:
            self.assertEqual(entry["actions"], sorted(set(entry["actions"])))
            self.assertEqual(entry["proof_ids"], sorted(set(entry["proof_ids"])))
            self.assertEqual(entry["assignment_id"], entry["after"]["assignment_id"])
            self.assertEqual(entry["generation_id"], entry["after"]["generation_id"])
        for mapping in page["policy_mappings"]:
            self.valid_def("responses", "mapping", mapping)
            self.assertEqual(mapping["creation_token"], mapping["generation_id"] + ":" + mapping["policy_key"])
            self.assertEqual(mapping["task_item_id"], self.by_case["initial_task_item_id"]["value"])

    def test_cursor_exact_payload_hmac_domain_canonical_encoding_and_post_commit_facts(self):
        corpus = read(self.manifest["cursors"])
        self.assertFalse(corpus["runtime_verified"])
        self.assertEqual({v["purpose"] for v in corpus["vectors"]}, {"list", "assignments", "generations", "states", "reconcile"})
        for row in corpus["vectors"]:
            self.valid_def("cursor", row["purpose"] + "Payload", row["payload"])
            encoded = oracle_canonical(row["payload"]).encode()
            signed = CURSOR.encode() + b"\0" + encoded
            self.assertEqual(row["canonical_json"].encode(), encoded)
            self.assertEqual(row["hmac_input_hex"], signed.hex())
            tag = hmac.new(bytes.fromhex(row["key_hex"]), signed, hashlib.sha256).digest()
            self.assertEqual(row["hmac_sha256"], tag.hex())

            def encode(value):
                return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

            self.assertEqual(row["wire"], encode(encoded) + "." + encode(tag))
            self.assertNotIn("=", row["wire"])
            self.assertEqual(instant(row["payload"]["expires_at_utc"]) - instant(row["payload"]["issued_at_utc"]), timedelta(seconds=3600))
            self.assertFalse({"command_id", "actor_subject_id", "expected", "cursor"} & set(row["payload"]["query"]))
            self.assertNotEqual(tag, hmac.new(bytes.fromhex(row["key_hex"]), b"wrong-purpose\0" + encoded, hashlib.sha256).digest())
            if row["purpose"] == "reconcile":
                page = self.fixtures["response_reconcile_partial"]["result"]
                self.assertEqual(row["payload"]["catalog_generation"], page["rule"]["catalog_generation"])
                self.assertEqual(row["payload"]["rule_change_version"], page["rule"]["change_version"])
                self.assertEqual(row["payload"]["after"], page["selection"]["lane_end"])
                self.assertEqual(row["payload"]["evaluation_at_utc"], page["selection"]["evaluation_at_utc"])

    def test_schema_shaped_semantic_mutations_are_detectable_not_implicitly_valid(self):
        # A schema cannot compare cross-record equalities; the dedicated checks
        # must reject such witnesses even though their wire shapes are valid.
        row = copy.deepcopy(self.evidence["states"][0])
        row["task_item_version"] = "9"
        self.valid_def("evidence", "stateRecord", row)
        self.assertNotEqual(row["task_item_version"], row["state_json"]["task_item_version"])
        row = copy.deepcopy(self.fixtures["response_reconcile_created"])
        row["result"]["work"]["retained"] = row["result"]["work"]["created"][:]
        self.validator(SCHEMAS + "reconcile-response.schema.json").validate(row)
        self.assertTrue(set(row["result"]["work"]["created"]) & set(row["result"]["work"]["retained"]))

    def test_finite_decision_witnesses_preserve_approved_policy(self):
        corpus = read(self.manifest["decisions"])
        self.assertFalse(corpus["runtime_verified"])
        self.assertEqual(corpus["status"], "offline_model_only")
        seen = set()
        for row in corpus["cases"]:
            with self.subTest(case=row["case_id"]):
                self.assertEqual(set(row), {"case_id", "family", "facts", "expected"})
                self.assertNotIn(row["case_id"], seen)
                seen.add(row["case_id"])
                self.assertEqual(decision_model(row["family"], row["facts"]), row["expected"])
        self.assertEqual(
            {r["family"] for r in corpus["cases"]}, {"cutoff", "restore", "adoption", "retirement", "continuity", "budget", "scheduler"}
        )
        self.assertGreaterEqual(len(seen), 35)


if __name__ == "__main__":
    unittest.main()
