"""Source-only RRT wire, identity and finite model witnesses; no runtime claims.

Nothing here opens a ledger, dispatches a command or starts a worker. Actual SQL,
migration, locking, freshness/attempt races and scheduler behavior are verified
separately by the named R4 runtime inventory, never by these pure wire examples.
"""

import base64
import copy
import hashlib
import hmac
import json
import os
import subprocess
import sys
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
from spine.core.notification_profiles import compose_notification_plan
from spine.core.notifications import normalize_notification_policy, revise_notification_policy
from spine.core.recurrence_mutations import build_successor_recurrence_revision
from tests.recurring_related_task_oracles import candidate, check_snapshot, check_snapshot_hashes, cursor_case, source_case

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
        if f["desired"] == f["baseline"]:
            return "preserve_current"
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
        cls.sources = read(cls.manifest["source_proofs"])
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
        source_uri = self.schemas[self.manifest["source_snapshot_schema"]]["$id"]
        visited.add(source_uri)
        walk(by_uri[source_uri], source_uri)
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

    def test_trusted_local_runtime_boundary_and_exact_existing_prerequisites(self):
        self.assertTrue(self.descriptor["runtime_implemented"])
        self.assertFalse(self.manifest["runtime_verified"])
        self.assertEqual(self.descriptor["status"], "ratified_machine_contract")
        self.assertEqual(self.manifest["status"], "ratified_source_only")
        self.assertEqual(read("contracts/recurring-related-task-schema-closure.v1.json")["status"], "ratified_source_only")
        self.assertEqual(self.descriptor["exposure"], "trusted_local_only")
        self.assertEqual(self.descriptor["ledger_schema_version"], "20")
        proposed = self.descriptor["proposed_contract_versions"]
        self.assertLessEqual(set(proposed), set(IMPLEMENTED_CONTRACT_VERSIONS))
        self.assertLessEqual(set(self.descriptor["commands"]), set(COMMAND_RUNTIME_CONTRACT_REGISTRY))
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
        self.assertTrue(all(r["status"] == "runtime_verified" for r in self.descriptor["runtime_obligations"]))
        self.assertEqual(self.manifest["builder_helpers"], ["scripts/recurring_related_task_fixture_sources.py"])
        self.assertEqual(self.manifest["test_oracle_helpers"], ["tests/recurring_related_task_oracles.py"])

    def test_builder_standalone_check_entrypoint(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_recurring_related_task_contract_fixtures.py", "--check"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("deterministic source-only artifacts; runtime evidence is separate", result.stdout)

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
        # Independent branch-specific expectations: not copied from the builder.
        for code, (command, field) in {
            "environment_failure": ("reconcile", "schema_version"),
            "unsupported_command": ("reconcile", "command"),
            "unsupported_contract_version": ("reconcile", "contract_version"),
            "invalid_request": ("reconcile", "limits.assignments"),
            "unsupported_field": ("reconcile", "force"),
            "command_id_conflict": ("reconcile", "command_id"),
            "referenced_row_not_found": ("reconcile", "related_task_rule_id"),
            "stale_cursor": ("reconcile", "cursor"),
            "stale_evaluation": ("reconcile", "evaluated_at_utc"),
            "capacity_exceeded": ("reconcile", "limits.work_rows"),
            "stale_version": ("reconcile", "expected.rule_change_version"),
            "semantic_conflict": ("update", "configuration.task_owner"),
            "rendering_disclosure_unavailable": ("update", "configuration.notification_plan"),
        }.items():
            row = self.fixtures["failure_" + code]
            self.assertEqual(
                (row["command"], row["error"]["code"], row["error"]["field"]), ("schedule.related_task_rule." + command, code, field)
            )
        for name in ("create", "update", "retire", "suppress", "reconcile", "show", "list"):
            envelope = self.schemas[SCHEMAS + "responses.schema.json"]["$defs"][name]
            effects = self.descriptor["effects"][name]
            self.assertEqual(set(envelope["properties"]["effect"]["enum"]), set(effects[0] + effects[1]))
            command = "schedule.related_task_rule." + ("assignment.suppress" if name == "suppress" else name)
            observed = {
                value["effect"] for key, value in self.fixtures.items() if key.startswith("response_") and value["command"] == command
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
                if row["artifact"] == "occurrence_key":
                    payload, digest = row["value"].split(".")
                    self.assertEqual(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)), expected_bytes)
                    self.assertEqual(digest, hashlib.sha256(expected_bytes).hexdigest())
                    self.assertEqual(payload, base64.urlsafe_b64encode(expected_bytes).rstrip(b"=").decode())
                    self.assertNotEqual(row["value"], row["sha256"])
                else:
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

    def test_adoption_preserves_individual_value_when_rule_field_unchanged(self):
        for baseline, current in [("B", "C"), (None, "C"), (["one"], ["two"]), ({"reminders": ["a"]}, {"reminders": ["b"]})]:
            self.assertEqual(
                decision_model(
                    "adoption", {"baseline": baseline, "current": current, "desired": copy.deepcopy(baseline), "eligible": True}
                ),
                "preserve_current",
            )
        row = next(c for c in read(self.manifest["decisions"])["cases"] if c["case_id"] == "unchanged_desired_preserves_exception")
        self.assertEqual(row["expected"], "preserve_current")

    def test_raw_duplicate_assignees_normalize_to_unique_bounded_stored_set(self):
        request = self.fixtures["request_create_duplicate_assignees"]
        self.validator(SCHEMAS + "create-request.schema.json").validate(request)
        raw = request["configuration"]["task_template"]["people"]["assignees"]
        self.assertEqual(
            sorted(set(raw)), self.fixtures["response_create"]["result"]["rule"]["configuration"]["task_template"]["people"]["assignees"]
        )
        self.assertFalse(self.validator(SCHEMAS + "types.schema.json", "normalizedPeople").is_valid({"assignees": raw}))
        self.assertFalse(self.validator(SCHEMAS + "types.schema.json", "people").is_valid({"assignees": ["same"] * 101}))

    def test_complete_normalized_source_snapshots_and_hash_preimages(self):
        self.assertFalse(self.sources["runtime_verified"])
        for record in self.sources["snapshots"]:
            with self.subTest(snapshot=record["case_id"]):
                value = check_snapshot(record, oracle_canonical)
                # The existing value schema owns domain rows; successor ancestry
                # is separately checked against the exact revision preimage.
                projection = {k: v for k, v in value.items() if k != "prior_recurrence_revision_id"}
                self.validator(self.manifest["source_snapshot_schema"]).validate(projection)
        bad = copy.deepcopy(self.sources["snapshots"][0])
        bad["value"]["normalized_recurrence_set_hash"] = "a" * 64
        with self.assertRaises(ValueError):
            check_snapshot(bad, oracle_canonical)
        bad = copy.deepcopy(self.sources["snapshots"][0])
        bad["value"]["rules"][0]["interval"] = "2"
        with self.assertRaises(ValueError):
            check_snapshot(bad, oracle_canonical)

    def test_successor_segment_ancestry_rejects_self_consistently_hashed_wrong_sources(self):
        initial = next(s for s in self.sources["snapshots"] if s["case_id"] == "main")
        current = next(s for s in self.sources["snapshots"] if s["case_id"] == "copied")
        unrelated = next(s["value"]["recurrence_revision_id"] for s in self.sources["snapshots"] if s["case_id"] == "union")
        self.assertEqual(check_snapshot(initial, oracle_canonical), initial["value"])
        self.assertEqual(check_snapshot(current, oracle_canonical), current["value"])
        for wrong_source in ["initial", unrelated]:
            with self.subTest(source_revision_id=wrong_source):
                # Deliberately construct a mathematically self-consistent invalid
                # successor. The independent identity-only checker accepts its
                # hashes; the ancestry check must reject it for the right reason.
                malformed = build_successor_recurrence_revision(
                    initial["value"],
                    source_item_version="2",
                    command_id="fixture_invalid_ancestry",
                    segments=[{**s, "source_revision_id": wrong_source} for s in initial["value"]["segments"]],
                )
                bad = {
                    "value": malformed.value,
                    "recurrence_set_id_preimage": initial["recurrence_set_id_preimage"],
                    "normalized_hash_preimage": malformed.normalized_hash_preimage,
                    "recurrence_revision_id_preimage": malformed.recurrence_revision_id_preimage,
                    "segment_id_preimages": list(malformed.segment_id_preimages),
                    "rule_id_preimages": list(malformed.rule_id_preimages),
                    "rdate_id_preimages": list(malformed.rdate_id_preimages),
                }
                self.assertEqual(check_snapshot_hashes(bad, oracle_canonical), malformed.value)
                with self.assertRaisesRegex(ValueError, "segment ancestry mismatch"):
                    check_snapshot(bad, oracle_canonical)

    def test_positive_copy_count_union_retarget_and_novelty_oracles(self):
        for case in self.sources["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(source_case(self.sources, case, oracle_canonical), case["expected"])
        by_revision = {s["value"]["recurrence_revision_id"]: s["value"] for s in self.sources["snapshots"]}
        for proof in self.evidence["proofs"]:
            value = by_revision[proof["recurrence_revision_id"]]
            payload = proof["proof_json"]
            self.assertEqual(payload["normalized_recurrence_set_hash"], value["normalized_recurrence_set_hash"])
            if proof["proof_kind"] == "source_cancelled":
                detail = next(e for e in self.sources["event_details"] if e["snapshot"] == "source_cancelled")
                self.assertEqual(detail["item_version"], payload["cancelled_event_version"])
                self.assertEqual(detail["status"], "cancelled")
                continue
            found = candidate(value, payload["selector"]["scheduled_fact"], oracle_canonical)
            self.assertIsNotNone(found)
            self.assertEqual(found[0], payload["selector"])
            if proof["proof_kind"] == "new_rdate":
                self.assertTrue(payload["lineage_ids"])
                self.assertIn(payload["rdate_id"], {r["rdate_id"] for r in value["rdates"]})
            if proof["proof_kind"] == "excluded":
                self.assertIn(payload["exdate_id"], {r["exdate_id"] for r in value["exdates"]})
            if proof["proof_kind"] == "occurrence_cancelled":
                self.assertIn(payload["override_id"], {r["override_id"] for r in value["overrides"]})
        published_lineage = {f["row"]["lineage_id"] for pair in self.sources["pairs"] for f in pair["lineage"]}
        for proof in self.evidence["proofs"]:
            self.assertLessEqual(set(proof["proof_json"]["lineage_ids"]), published_lineage)

    def test_source_proofs_reject_missing_lineage_wrong_count_union_and_retarget(self):
        def evaluate(case_id, mutate):
            corpus = copy.deepcopy(self.sources)
            case = next(c for c in corpus["cases"] if c["case_id"] == case_id)
            pair = next(p for p in corpus["pairs"] if p["case_id"] == case["pair"])
            mutate(corpus, pair, case)
            return source_case(corpus, case, oracle_canonical)

        self.assertEqual(evaluate("unchanged_copy", lambda c, p, t: p.update(lineage=[])), "decision_required")
        self.assertEqual(
            evaluate(
                "count_split",
                lambda c, p, t: next(x for x in p["copy_facts"] if "count_subtraction" in x)["count_subtraction"].update(
                    produced_before_split="1"
                ),
            ),
            "decision_required",
        )
        self.assertEqual(evaluate("all_union_contributors", lambda c, p, t: p["copy_facts"].pop()), "decision_required")
        self.assertEqual(
            evaluate("exact_retarget", lambda c, p, t: p["retarget_facts"].append(copy.deepcopy(p["retarget_facts"][0]))),
            "decision_required",
        )
        self.assertEqual(evaluate("genuinely_added_rdate", lambda c, p, t: p.update(lineage=[])), "decision_required")

        def reserve(corpus, pair, case):
            value = next(s["value"] for s in corpus["snapshots"] if s["case_id"] == pair["snapshot"])
            case["reserved_selectors"] = [candidate(value, case["fact"], oracle_canonical)[0]]

        self.assertEqual(evaluate("genuinely_added_rdate", reserve), "not_novel")

    def test_retained_profile_composition_reordering_and_replacement_intents(self):
        corpus = read(self.manifest["composed_policies"])
        self.assertFalse(corpus["runtime_verified"])
        self.assertEqual(corpus["initial_reminders"], corpus["reordered_reminders"])
        self.assertEqual([r["policy_key"] for r in corpus["initial_reminders"]], ["pickup_ten_minutes", "profile_ten_minutes"])
        reordered = compose_notification_plan(
            list(reversed(corpus["templates"])),
            suppress_template_keys=corpus["suppress_template_keys"],
            replacements=[],
            custom_additions=list(reversed(corpus["custom_additions"])),
        )
        self.assertEqual(list(reordered.reminders), corpus["initial_reminders"])
        self.assertEqual({r["policy_origin"] for r in corpus["replacement_origins"]}, {"profile_replacement", "custom_addition"})
        self.assertEqual(len({p["notification_intent_id"] for p in corpus["initial_policies"]}), 2)
        for initial, revised, mapping in zip(
            corpus["initial_policies"], corpus["revised_policies"], corpus["initial_mappings"], strict=True
        ):
            self.assertEqual(mapping["creation_token"], mapping["generation_id"] + ":" + mapping["policy_key"])
            self.assertEqual(initial["notification_intent_id"], revised["notification_intent_id"])
            self.assertEqual(initial["intent_created_by_command_id"], revised["intent_created_by_command_id"])
            self.assertEqual(initial["intent_created_by_command_id"], mapping["creation_token"])
            self.assertEqual(revised["created_by_command_id"], corpus["real_outer_command_id"])
        self.assertEqual(
            {m["notification_policy_id"] for m in corpus["initial_mappings"]},
            {p["notification_policy_id"] for p in corpus["initial_policies"]},
        )
        self.assertEqual(
            {m["notification_policy_id"] for m in corpus["revised_mappings"]},
            {p["notification_policy_id"] for p in corpus["revised_policies"]},
        )

    def test_cursor_rejection_expiry_and_validation_precedence_oracles(self):
        corpus = read(self.manifest["cursors"])
        validator = self.validator(SCHEMAS + "cursor.schema.json", "reconcilePayload")
        seen = {}
        for case in corpus["cases"]:
            with self.subTest(case=case["case_id"]):
                outcome = cursor_case(case["wire"], case["context"], oracle_canonical, validator.is_valid)
                self.assertEqual(outcome, case["expected"])
                seen[case["case_id"]] = outcome
        for key, expected in {
            "expiry_equality": "stale_cursor",
            "different_query_limit": "invalid_request",
            "wrong_ledger": "invalid_request",
            "wrong_purpose": "invalid_request",
            "noncanonical_json_whitespace": "invalid_request",
            "expected_mismatch_only": "stale_version",
            "bad_tag_before_expected": "invalid_request",
            "expiry_before_expected": "stale_cursor",
            "query_before_stale_and_expected": "invalid_request",
        }.items():
            self.assertEqual(seen[key], expected)
        self.assertGreaterEqual(len(seen), 25)

    def test_cross_surface_catalog_watermarks_and_blocked_policy_completeness(self):
        creation = self.fixtures["response_reconcile_created"]["result"]
        for view in ["assignments", "generations", "states"]:
            readback = self.fixtures["response_show_" + view]["result"]
            self.assertTrue(readback["rows"])
            self.assertGreaterEqual(int(readback["catalog_generation"]), int(creation["rule"]["catalog_generation"]))

        def check_mapping(page):
            processed = {(e["after"]["task_item_id"], e["after"]["task_item_version"]) for e in page["results"] if e["after"] is not None}
            expected = {
                p["notification_policy_id"]
                for p in self.evidence["policies"]
                if (p["item_id"], p["item_version"]) in processed and p["status"] == "active"
            }
            if {m["notification_policy_id"] for m in page["policy_mappings"]} != expected:
                raise ValueError("incomplete current family policy mapping")

        check_mapping(creation)
        blocked = self.fixtures["response_reconcile_decision_required"]["result"]
        check_mapping(blocked)
        bad = copy.deepcopy(blocked)
        bad["policy_mappings"] = []
        with self.assertRaises(ValueError):
            check_mapping(bad)
        self.assertLess(
            int(blocked["selection"]["lane_start"]["assignment_after_seq"]), int(blocked["selection"]["lane_end"]["assignment_after_seq"])
        )
        self.assertEqual(blocked["coverage"]["assignments"]["status"], "decision_required")
        self.assertFalse(self.fixtures["response_reconcile_decision_required"]["changed"])
        for name, value in self.fixtures.items():
            if name.startswith("failure_"):
                self.assertNotIn("result", value)  # Failed whole pages cannot return committed lane advancement.


if __name__ == "__main__":
    unittest.main()
