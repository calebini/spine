"""Emit deterministic source-only recurring-task fixtures; never write files.

Run with PYTHONPATH=src. Default stdout is a path -> JSON artifact bundle for
review/apply_patch. --check compares it to retained artifacts. No ledger, command
dispatcher, worker, wall clock, network, or adapter is used. These are offline
wire/hash examples, not evidence that the proposed runtime exists.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin

from spine.core.canonical_json import canonical_json_bytes
from spine.core.notification_profiles import compose_notification_plan
from spine.core.notifications import expand_notification_policy, normalize_notification_policy, revise_notification_policy

if __package__ in (None, ""):
    from recurring_related_task_fixture_sources import selector_for, source_witnesses
else:
    from scripts.recurring_related_task_fixture_sources import selector_for, source_witnesses

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = "contracts/schemas/recurring-related-tasks/"
FIXTURES = "tests/fixtures/recurring_related_tasks/"
FAMILY = "spine.recurring-related-tasks.v1"
CANONICAL = "spine.canonical-json.v1"
RESPONSE = "spine.recurring-related-tasks-response.v1"
CURSOR = "spine.recurring-related-tasks.cursor.v1"
BASE = "schedule.related_task_rule."
NOW = "2026-11-08T10:00:00Z"
END = "2027-01-03T10:00:00Z"
DELIVERY = "not_attempted_by_command"
LEDGER = "ledger_instance_disposable_fixture_only"
TEST_KEY = "0123456789abcdef" * 4


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def schema_closure():
    """Return only recursively required resources, with exact local source hashes."""
    resources = {}
    for path in (ROOT / "contracts/schemas").rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in value:
            resources[value["$id"]] = (path, value)
    queue = [read(str(p.relative_to(ROOT)))["$id"] for p in (ROOT / SCHEMAS).glob("*.json")]
    # Complete normalized values in the offline source corpus use this existing
    # schema owner; no installed runtime closure is changed.
    queue.append(read("contracts/schemas/recurrence-set.schema.json")["$id"])
    seen = set()
    while queue:
        uri = queue.pop()
        if uri in seen:
            continue
        seen.add(uri)
        _, value = resources[uri]  # Missing resources are fatal, never fetched.

        def walk(node, uri=uri):
            if isinstance(node, dict):
                if "$ref" in node:
                    target, fragment = urldefrag(urljoin(uri, node["$ref"]))
                    at = resources[target][1]
                    for part in fragment.split("/")[1:]:
                        key = part.replace("~1", "/").replace("~0", "~")
                        at = at[int(key)] if isinstance(at, list) else at[key]
                    queue.append(target)
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
    return {
        "contract_version": "spine.recurring-related-task-schema-closure.v1",
        "status": "ratified_source_only",
        "resources": [
            {
                "uri": uri,
                "path": str(resources[uri][0].relative_to(ROOT)),
                "sha256": hashlib.sha256(resources[uri][0].read_bytes()).hexdigest(),
            }
            for uri in sorted(seen)
        ],
    }


def decision_witnesses():
    """Hand-declared finite decisions, NOT results of a second task engine."""
    cases = []

    def add(name, family, facts, expected):
        cases.append({"case_id": name, "family": family, "facts": facts, "expected": expected})

    cutoff = {
        "exists": False,
        "source_actionable": True,
        "enrolled": True,
        "evaluation": "2026-11-14T12:00:00Z",
        "commit": "2026-11-14T12:00:01Z",
        "due": "2026-11-14T13:00:00Z",
    }
    for name, change, result in [
        ("class_started_due_future", {}, "create"),
        ("due_equal_evaluation", {"due": cutoff["evaluation"]}, "skip"),
        ("due_equal_commit", {"due": cutoff["commit"]}, "stale_evaluation"),
        ("commit_crossed_due", {"commit": "2026-11-14T13:00:01Z"}, "stale_evaluation"),
        ("clock_backwards", {"commit": "2026-11-14T11:59:59Z"}, "environment_failure"),
        ("existing_overdue_kept", {"exists": True, "due": "2026-11-14T11:00:00Z"}, "retain"),
        ("not_enrolled", {"enrolled": False}, "skip"),
        ("source_not_actionable", {"source_actionable": False}, "skip"),
    ]:
        add(name, "cutoff", {**cutoff, **change}, result)
    restore = {
        "active_rule": True,
        "one_to_one_proof": True,
        "source_restored": True,
        "latest_source_cancelled": True,
        "successor_exists": False,
        "veto": False,
        "future_due": True,
        "task_done": False,
        "manual_exception": False,
    }
    for name, change, result in [
        ("source_only_restoration", {}, "new_successor"),
        ("repeat_restoration", {"successor_exists": True}, "retain"),
        ("suppression_wins", {"veto": True}, "retain"),
        ("completed_consumes_slot", {"task_done": True}, "retain"),
        ("manual_cancel_never_restored", {"manual_exception": True}, "retain"),
        ("retirement_stops_restoration", {"active_rule": False}, "retain"),
        ("overdue_restore_skipped", {"future_due": False}, "retain"),
        ("unresolved_not_cancellation", {"one_to_one_proof": False}, "decision_required"),
        ("source_still_excluded", {"source_restored": False}, "retain"),
    ]:
        add(name, "restore", {**restore, **change}, result)
    for name, facts, expected in [
        ("untouched_adopt", {"baseline": "B", "current": "B", "desired": "D", "eligible": True}, "adopt"),
        ("already_desired", {"baseline": "B", "current": "D", "desired": "D", "eligible": True}, "adopt_witness"),
        ("individual_exception", {"baseline": "B", "current": "C", "desired": "D", "eligible": True}, "conflict"),
        ("unchanged_desired_preserves_exception", {"baseline": "B", "current": "C", "desired": "B", "eligible": True}, "preserve_current"),
        ("all_equal_preserved", {"baseline": "B", "current": "B", "desired": "B", "eligible": True}, "preserve_current"),
        ("terminal_or_overdue_adoption", {"baseline": "B", "current": "B", "desired": "D", "eligible": False}, "skip"),
    ]:
        add(name, "adoption", facts, expected)
    for disposition in ["keep_following", "detach_open", "cancel_open"]:
        add(
            "retire_" + disposition,
            "retirement",
            {"disposition": disposition, "open_governed": True},
            {"keep_following": "follow", "detach_open": "detach", "cancel_open": "cancel"}[disposition],
        )
        add("retire_terminal_" + disposition, "retirement", {"disposition": disposition, "open_governed": False}, "preserve")
    for name, facts, expected in [
        ("exact_selector", {"exact": True, "positive_lineage": False, "matches": "1", "range_absent": False}, "same_assignment"),
        ("proved_move", {"exact": False, "positive_lineage": True, "matches": "1", "range_absent": False}, "same_assignment"),
        ("union_many_to_one", {"exact": False, "positive_lineage": True, "matches": "2", "range_absent": False}, "decision_required"),
        (
            "no_nearest_time_pairing",
            {"exact": False, "positive_lineage": False, "matches": "1", "range_absent": False},
            "decision_required",
        ),
        ("absence_not_exclusion", {"exact": False, "positive_lineage": False, "matches": "0", "range_absent": True}, "decision_required"),
    ]:
        add(name, "continuity", facts, expected)
    for name, facts, expected in [
        ("whole_unit_fits", {"used": "1", "unit": "2", "limit": "3", "hard": "4"}, "process"),
        ("stop_between_units", {"used": "2", "unit": "2", "limit": "3", "hard": "4"}, "continue"),
        ("unit_exceeds_request", {"used": "0", "unit": "4", "limit": "3", "hard": "4"}, "capacity_exceeded"),
        ("unit_exceeds_hard_cap", {"used": "0", "unit": "5", "limit": "4", "hard": "4"}, "capacity_exceeded"),
    ]:
        add(name, "budget", facts, expected)
    for name, facts, expected in [
        ("idle_clock_only", {"domain_change": False, "semantic_progress": False, "clock_only": True}, "no_dispatch"),
        ("new_candidate", {"domain_change": True, "semantic_progress": False, "clock_only": False}, "dispatch"),
        ("real_cleanup_progress", {"domain_change": False, "semantic_progress": True, "clock_only": False}, "dispatch"),
    ]:
        add(name, "scheduler", facts, expected)
    return {
        "contract_version": "spine.recurring-related-task-decision-witnesses.v1",
        "status": "offline_model_only",
        "runtime_verified": False,
        "cases": cases,
    }


def cursor_witnesses(vectors):
    """Retain exact synthetic invalid/stale/precedence cases, not a validator."""
    baseline = next(v for v in vectors if v["purpose"] == "reconcile")
    payload = baseline["payload"]
    freshness = {
        k: payload[k]
        for k in [
            "catalog_generation",
            "rule_change_version",
            "rule_revision_id",
            "source_item_id",
            "source_item_version",
            "recurrence_set_id",
            "recurrence_revision_id",
            "normalized_recurrence_set_hash",
        ]
    }
    context = {
        "keys": {payload["key_id"]: TEST_KEY},
        "purpose": "reconcile",
        "query": payload["query"],
        "now": "2026-11-08T10:00:10Z",
        "freshness": freshness,
        "expected_mismatch": False,
    }
    cases = []

    def signed(value=None, raw=None, domain=CURSOR):
        raw = raw if raw is not None else canonical_json_bytes(value if value is not None else payload)
        tag = hmac.new(bytes.fromhex(TEST_KEY), domain.encode() + b"\0" + raw, hashlib.sha256).digest()
        return b64(raw) + "." + b64(tag)

    def add(name, expected, *, wire=None, change_context=None, value=None, raw=None, domain=CURSOR):
        current = copy.deepcopy(context)
        if change_context:
            change_context(current)
        cases.append(
            {"case_id": name, "wire": wire or signed(value=value, raw=raw, domain=domain), "context": current, "expected": expected}
        )

    add("accepted", "accepted")
    add("one_second_before_expiry", "accepted", change_context=lambda c: c.update(now="2026-11-08T10:59:59Z"))
    add("expiry_equality", "stale_cursor", change_context=lambda c: c.update(now="2026-11-08T11:00:00Z"))
    add("expired", "stale_cursor", change_context=lambda c: c.update(now="2026-11-08T11:00:01Z"))
    add("different_query_limit", "invalid_request", change_context=lambda c: c["query"]["limits"].update(assignments="2"))
    add("wrong_ledger", "invalid_request", change_context=lambda c: c["query"].update(ledger_instance_id="ledger_instance_other_fixture"))
    add("wrong_purpose", "invalid_request", change_context=lambda c: c.update(purpose="list"))
    bad_tag = baseline["wire"].split(".")[0] + "." + b64(bytes(32))
    add("bad_tag", "invalid_request", wire=bad_tag)
    add("wrong_hmac_domain", "invalid_request", domain="spine.other.cursor.v1")
    add("padded_encoding", "invalid_request", wire=baseline["wire"].replace(".", "=."))
    add("noncanonical_json_whitespace", "invalid_request", raw=json.dumps(payload, indent=2).encode())
    duplicate = '{"catalog_generation":"2",' + canonical_json_bytes(payload).decode()[1:]
    add("duplicate_json_key", "invalid_request", raw=duplicate.encode())
    add("malformed_json", "invalid_request", raw=b"{")
    add("unknown_verification_key", "invalid_request", value={**payload, "key_id": "retired_fixture_key"})
    add("unknown_payload_field", "invalid_request", value={**payload, "force": True})
    add("overflow_counter", "invalid_request", value={**payload, "catalog_generation": "9223372036854775808"})
    add("json_number_counter", "invalid_request", raw=json.dumps({**payload, "catalog_generation": 2}).encode())
    add("invalid_unicode", "invalid_request", raw=json.dumps({**payload, "key_id": "\ud800"}).encode())
    add("wrong_lifetime", "invalid_request", value={**payload, "expires_at_utc": "2026-11-08T11:00:01Z"})
    for key, value in [
        ("catalog_generation", "3"),
        ("rule_change_version", "3"),
        ("rule_revision_id", "related_task_rule_revision_" + "a" * 64),
        ("source_item_version", "2"),
        ("recurrence_revision_id", "recurrence_revision_other"),
        ("normalized_recurrence_set_hash", "a" * 64),
    ]:
        add("stale_" + key, "stale_cursor", change_context=lambda c, k=key, v=value: c["freshness"].update({k: v}))
    add("expected_mismatch_only", "stale_version", change_context=lambda c: c.update(expected_mismatch=True))
    add("bad_tag_before_expected", "invalid_request", wire=bad_tag, change_context=lambda c: c.update(expected_mismatch=True))
    add("expiry_before_expected", "stale_cursor", change_context=lambda c: c.update(now="2026-11-08T11:00:00Z", expected_mismatch=True))
    add(
        "query_before_stale_and_expected",
        "invalid_request",
        change_context=lambda c: (
            c["query"]["limits"].update(assignments="2"),
            c["freshness"].update(catalog_generation="3"),
            c.update(expected_mismatch=True),
        ),
    )
    return cases


def build():
    bundle, fixtures, vectors = {}, [], []
    descriptor = read("contracts/recurring-related-tasks.v1.json")
    types = read(SCHEMAS + "types.schema.json")["$defs"]
    limits = {key: str(value[0]) for key, value in descriptor["limits"]["page"].items()}
    owner = {"owner_kind": "subject_group", "owner_group_id": "fixture_kinflow"}
    sources = source_witnesses()
    source_values = {s["case_id"]: s["value"] for s in sources["snapshots"]}
    source_pairs = {p["case_id"]: p for p in sources["pairs"]}
    initial_source = source_values["main"]
    source = {
        "source_item_id": initial_source["source_item_id"],
        "source_item_version": "1",
        "recurrence_set_id": initial_source["recurrence_set_id"],
        "recurrence_revision_id": initial_source["recurrence_revision_id"],
        "normalized_recurrence_set_hash": initial_source["normalized_recurrence_set_hash"],
    }
    write = {
        "contract_version": FAMILY,
        "command_id": "fixture_author_rule",
        "actor_subject_id": "fixture_operator",
        "requested_at_utc": NOW,
    }
    source_rule = {k: v for k, v in initial_source["rules"][0].items() if k not in {"rule_id", "segment_id"}}

    def selector(fact):
        return selector_for(initial_source, fact)

    selected = selector("2026-11-14T11:30:00")

    def vector(case_id, artifact, prefix, preimage):
        encoded = canonical_json_bytes(preimage)
        sha = hashlib.sha256(encoded).hexdigest()
        value = prefix + "_" + sha if prefix else sha
        if artifact == "occurrence_key":
            value = b64(encoded) + "." + sha
        row = {
            "case_id": case_id,
            "artifact": artifact,
            "prefix": prefix,
            "preimage": copy.deepcopy(preimage),
            "canonical_json": encoded.decode("utf-8"),
            "sha256": sha,
            "value": value,
        }
        existing = next((v for v in vectors if v["case_id"] == case_id), None)
        if existing is None:
            vectors.append(row)
        elif existing != row:
            raise ValueError("Conflicting vector case " + case_id)
        return value

    def identity(artifact, fields, case=None):
        hash_versions = {
            "configuration_hash": "spine.related-task-rule-configuration.v1",
            "state_hash": "spine.related-task-assignment-state.v1",
        }
        prefix = None if artifact in hash_versions else artifact
        preimage = {
            "contract_version": FAMILY,
            "canonical_json_version": CANONICAL,
            "derivation_version": hash_versions.get(artifact, "spine." + artifact.replace("_", "-") + "-id.v1"),
            **fields,
        }
        return vector(case or artifact, artifact, prefix, preimage)

    def child(prefix, role, path, seed, case):
        return vector(
            case,
            "command_derived",
            prefix,
            {
                "derivation_version": "spine.command-id.v1",
                "command": BASE + "reconcile",
                "command_id": seed,
                "row_role": role,
                "request_path": path,
            },
        )

    def fixture(name, value, schema, valid=True):
        path = FIXTURES + "contracts/" + name + ".json"
        bundle[path] = copy.deepcopy(value)
        fixtures.append({"fixture_id": name, "fixture": path, "schema": SCHEMAS + schema + ".schema.json", "valid": valid})

    def occurrence(sel, name):
        return vector(
            name,
            "occurrence_key",
            None,
            {
                "derivation_version": "spine.recurrence-occurrence-key.v2",
                "contract_version": "spine.recurrence.contract.v1",
                "normalization_version": "spine.recurrence.normalization.v1",
                "canonical_json_version": CANONICAL,
                "target_occurrence_selector": sel,
            },
        )

    occurrence_key = occurrence(selected, "first_occurrence_key")
    selector_ref = vector("first_selector_ref", "selector_ref", "recurrence_target_selector", selected)
    custom = {
        "policy_key": "pickup_ten_minutes",
        "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
        "late_handling": {"kind": "deliver_within", "grace_seconds": "300"},
    }
    plan = {"mode": "none", "custom_additions": [custom]}
    delivery = {
        "recipient_kind": "subject_group",
        "recipient_group_id": "fixture_kinflow",
        "channel": "fixture_channel",
        "target": {"resolution": "explicit", "delivery_target_id": "delivery_target_fixture"},
    }
    configuration = {
        "task_owner": owner,
        "task_template": {
            "item": {"item_type": "task", "title": "Pick up Joe", "task_detail": {}},
            "people": {"assignees": ["fixture_parent"]},
        },
        "offset_basis": "elapsed",
        "offset_seconds": "5400",
        "notification_plan": plan,
        "delivery": delivery,
        "materialization": {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "4838400", "opportunity_limit": "100"},
    }
    normalized = copy.deepcopy(configuration)
    normalized["generation_horizon_seconds"] = "4838400"
    normalized["task_template"]["item"].update(summary=None, source_ref=None, primary_location=None, archetype=None)
    normalized["task_template"]["item"]["task_detail"] = {"priority": None}
    normalized["notification_plan"] = {
        "requested": plan,
        "resolved": {
            "selection_mode": "none",
            "profile": None,
            "notification_profile_binding_id": None,
            "scope_chain": [],
            "effective_templates": [
                {
                    "policy_origin": "custom_addition",
                    "source_key": custom["policy_key"],
                    "policy_key": custom["policy_key"],
                    "template": {
                        "template_key": custom["policy_key"],
                        "schedule": custom["schedule"],
                        "late_handling": custom["late_handling"],
                        "rendering": {"kind": "ordinary"},
                    },
                    "presentation": {"kind": "ordinary"},
                }
            ],
        },
    }
    normalized["delivery"] = {
        "requested": delivery,
        "resolved": {
            "delivery_target_id": "delivery_target_fixture",
            "resolution_source": "explicit",
            "recipient_kind": "subject_group",
            "recipient_group_id": "fixture_kinflow",
            "channel": "fixture_channel",
            "adapter_name": "test_capture",
            "target_ref": "fixture://no-send/pickup",
        },
    }
    root_id = identity("related_task_rule", {"owner": owner, "rule_key": "science_pickup"})
    config_hash = identity("configuration_hash", {"configuration": normalized})
    revision = identity(
        "related_task_rule_revision", {"related_task_rule_id": root_id, "revision_index": "1", "configuration_hash": config_hash}
    )
    baseline = {
        k: normalized[k] for k in ("task_template", "offset_basis", "offset_seconds", "notification_plan", "delivery", "materialization")
    }
    assignment_id = identity("related_task_assignment", {"related_task_rule_id": root_id, "initial_selector": selected})
    generation = identity("related_task_generation", {"assignment_id": assignment_id, "generation_index": "1"})
    successor = identity("related_task_generation", {"assignment_id": assignment_id, "generation_index": "2"}, "restoration_generation")
    second_selector = selector("2026-11-21T11:30:00")
    identity("related_task_assignment", {"related_task_rule_id": root_id, "initial_selector": second_selector}, "next_week_assignment")
    occurrence(second_selector, "next_week_occurrence_key")
    children = {}
    paths = [
        ("task_item_id", "item", "item", "/task"),
        ("due_anchor_id", "anchor", "due_anchor", "/temporal_binding/resolved_target"),
        ("relationship_id", "relation", "relation", "/relationship"),
        ("temporal_binding_id", "temporal_binding", "temporal_binding", "/temporal_binding"),
        ("temporal_binding_revision_id", "temporal_binding_revision", "temporal_binding_revision", "/temporal_binding/revisions/0"),
        ("item_access_owner_id", "item_access_owner", "item_access_owner", "/task_owner"),
    ]
    for field, prefix, role, path in paths:
        children[field] = child(prefix, role, path, generation, "initial_" + field)
        child(prefix, role, path, successor, "restored_" + field)
    outer = "fixture_reconcile_page_1"
    receipt = child("command_receipt", "command_receipt", "/command_receipt", outer, "page_receipt")
    child("audit", "audit", "/audit", outer, "root_audit")
    child("audit", "audit", "/assignments/" + assignment_id + "/audit", outer, "child_audit")

    proof_payload = {
        **source,
        "selector": selected,
        "occurrence_key": occurrence_key,
        "lineage_ids": [],
        "enrolled_recurrence_revision_id": source["recurrence_revision_id"],
    }
    proof_id = identity("related_task_proof", {"related_task_rule_id": root_id, "proof_kind": "enrollment", "proof_payload": proof_payload})
    proof = {
        "proof_id": proof_id,
        "related_task_rule_id": root_id,
        "proof_kind": "enrollment",
        "source_item_version": "1",
        "recurrence_revision_id": source["recurrence_revision_id"],
        "prior_recurrence_revision_id": None,
        "proof_json": proof_payload,
        "proof_hash": proof_id.rsplit("_", 1)[1],
        "created_by_command_id": outer,
        "created_at_utc": NOW,
    }
    state = {
        "generation_id": generation,
        "selector": selected,
        "occurrence_key": occurrence_key,
        "source_item_version": "1",
        "recurrence_revision_id": source["recurrence_revision_id"],
        "proof_id": proof_id,
        "task_item_id": children["task_item_id"],
        "task_item_version": "1",
        "temporal_binding_revision_id": children["temporal_binding_revision_id"],
        "adopted_rule_revision_id": revision,
        "managed_baseline": baseline,
        "disposition": "governed",
        "restoration_veto": False,
        "reason": "new_source_slot",
    }
    state_hash = identity("state_hash", {"state": state})
    state_id = identity(
        "related_task_assignment_revision", {"assignment_id": assignment_id, "change_version": "1", "state_hash": state_hash}
    )
    state_record = {
        "assignment_revision_id": state_id,
        "assignment_id": assignment_id,
        "change_version": "1",
        "prior_assignment_revision_id": None,
        "state_json": state,
        "state_hash": state_hash,
        **{
            k: state[k]
            for k in (
                "source_item_version",
                "recurrence_revision_id",
                "task_item_id",
                "task_item_version",
                "adopted_rule_revision_id",
                "generation_id",
                "temporal_binding_revision_id",
                "proof_id",
            )
        },
        "selector_ref": selector_ref,
        "command_id": outer,
        "created_at_utc": NOW,
    }
    generation_record = {
        "generation_id": generation,
        "assignment_id": assignment_id,
        "generation_index": "1",
        "predecessor_generation_id": None,
        "task_item_id": children["task_item_id"],
        "created_task_version": "1",
        **{k: children[k] for k in ("relationship_id", "temporal_binding_id", "item_access_owner_id")},
        "created_rule_revision_id": revision,
        "creation_proof_id": proof_id,
        "created_by_command_id": outer,
        "created_at_utc": NOW,
    }
    owner_header = {
        "item_id": children["task_item_id"],
        "item_access_owner_id": children["item_access_owner_id"],
        "current_revision": "1",
        "owner_kind": "subject_group",
        "owner_subject_id": None,
        "owner_group_id": owner["owner_group_id"],
        "creator_entitlement_subject_id": None,
        "created_by_command_id": outer,
    }
    owner_revision = {k: v for k, v in owner_header.items() if k != "current_revision"}
    owner_revision.update(revision="1", changed_at_utc=NOW, changed_by_subject_id="fixture_operator", command_receipt_id=receipt)
    expected = {
        "rule_change_version": "1",
        "rule_revision_id": revision,
        "source_item_version": "1",
        "recurrence_revision_id": source["recurrence_revision_id"],
        "catalog_generation": "1",
    }
    rule = {
        "related_task_rule_id": root_id,
        "owner": owner,
        "rule_key": "science_pickup",
        "source_item_id": source["source_item_id"],
        "recurrence_set_id": source["recurrence_set_id"],
        "source_snapshot": source,
        "status": "active",
        "rule_revision_id": revision,
        "revision_index": "1",
        "configuration": normalized,
        "configuration_hash": config_hash,
        "change_version": "1",
        "catalog_generation": "1",
        "enrollment": {"kind": "upcoming"},
        "enrolled_at_utc": NOW,
        "retirement_disposition": None,
        "retirement_intent": None,
        "adoption_intent": None,
        "progress": None,
    }
    assignment = {
        "assignment_id": assignment_id,
        "assignment_seq": "1",
        "change_version": "1",
        "assignment_revision_id": state_id,
        "initial_selector": selected,
        "current_selector": selected,
        "occurrence_key": occurrence_key,
        "generation_id": generation,
        "generation_index": "1",
        "task_item_id": children["task_item_id"],
        "task_item_version": "1",
        "task_status": "open",
        **{k: children[k] for k in ("temporal_binding_id", "temporal_binding_revision_id", "relationship_id", "item_access_owner_id")},
        "task_owner": owner,
        "item_access_owner_revision": "1",
        "adopted_rule_revision_id": revision,
        "desired_rule_revision_id": None,
        "disposition": "governed",
        "reason": "new_source_slot",
        "restoration_veto": False,
        "suppression": None,
        "source_proof_id": proof_id,
        "source_snapshot": source,
        "predecessor_generation_id": None,
        "successor_generation_id": None,
        "source_cancellation": None,
        "freshness": "current",
        "observed_source_item_version": "1",
        "observed_recurrence_revision_id": source["recurrence_revision_id"],
        "observed_task_item_version": "1",
    }
    child_refs = {k: assignment[k] for k in read(SCHEMAS + "responses.schema.json")["$defs"]["childRefs"]["required"]}
    create = {
        **write,
        "owner": owner,
        "rule_key": "science_pickup",
        "source": {
            "item_id": source["source_item_id"],
            "item_version": "1",
            "recurrence_set_id": source["recurrence_set_id"],
            "recurrence_revision_id": source["recurrence_revision_id"],
        },
        "enrollment": {"kind": "upcoming"},
        "configuration": configuration,
    }
    fixture("request_create_pickup", create, "create-request")
    duplicate_people = copy.deepcopy(create)
    duplicate_people["configuration"]["task_template"]["people"]["assignees"] = ["fixture_parent", "fixture_parent"]
    fixture("request_create_duplicate_assignees", duplicate_people, "create-request")
    explicit = copy.deepcopy(create)
    explicit["enrollment"] = {"kind": "selected_occurrence", "occurrence_key": occurrence_key}
    fixture("request_create_selected", explicit, "create-request")
    bare_key = copy.deepcopy(explicit)
    bare_key["enrollment"]["occurrence_key"] = occurrence_key.split(".")[-1]
    fixture("invalid_create_bare_occurrence_key", bare_key, "create-request", False)
    no_reminders = copy.deepcopy(create)
    no_reminders["configuration"].update(notification_plan=None, delivery=None, materialization={"mode": "none"})
    fixture("request_create_without_reminders", no_reminders, "create-request")
    two_reminders = copy.deepcopy(create)
    earlier = copy.deepcopy(custom)
    earlier["policy_key"] = "pickup_one_hour"
    earlier["schedule"]["at"]["offset_seconds"] = "-3600"
    two_reminders["configuration"]["notification_plan"]["custom_additions"] = [earlier, custom]
    fixture("request_create_two_reminders", two_reminders, "create-request")
    explicit_profile = copy.deepcopy(create)
    explicit_profile["configuration"]["notification_plan"] = {
        "mode": "explicit",
        "notification_profile_id": "notification_profile_fixture_pickup",
        "revision_resolution": "exact",
        "notification_profile_revision_id": "notification_profile_revision_fixture_pickup_1",
    }
    fixture("request_create_exact_profile", explicit_profile, "create-request")
    default_profile = copy.deepcopy(create)
    default_profile["configuration"]["task_template"]["item"]["archetype"] = {
        "item_archetype_id": "item_archetype_fixture_pickup",
        "revision_resolution": "current",
        "selection_source": "operator_explicit",
    }
    default_profile["configuration"]["notification_plan"] = {
        "mode": "archetype_default",
        "scope_chain": [owner],
        "on_no_match": "fail",
    }
    fixture("request_create_archetype_default", default_profile, "create-request")
    for name, value in [
        ("system_child_owner", {"owner_kind": "system"}),
        ("wrong_group_field", {"owner_kind": "subject_group", "owner_subject_id": "fixture_parent"}),
    ]:
        invalid = copy.deepcopy(create)
        invalid["configuration"]["task_owner"] = value
        fixture("invalid_create_" + name, invalid, "create-request", False)
    invalid = copy.deepcopy(create)
    invalid["configuration"]["task_template"]["item"]["task_detail"]["subject_roles"] = []
    fixture("invalid_create_embedded_roles", invalid, "create-request", False)
    base_write = {**write, "related_task_rule_id": root_id, "expected": expected}
    full_config = {**configuration, "generation_horizon_seconds": "4838400"}
    fixture("request_update_upcoming", {**base_write, "configuration": full_config, "adoption_scope": "upcoming_open"}, "update-request")
    fixture(
        "request_update_new_only", {**base_write, "configuration": full_config, "adoption_scope": "new_assignments_only"}, "update-request"
    )
    for disposition in types["disposition"]["enum"]:
        fixture("request_retire_" + disposition, {**base_write, "disposition": disposition}, "retire-request")
    suppress_request = {
        **base_write,
        "expected": {**expected, "assignment_change_version": "2"},
        "assignment_id": assignment_id,
        "target_generation_id": generation,
        "target_task_item_id": children["task_item_id"],
    }
    fixture("request_suppress", suppress_request, "suppress-request")
    fixture("request_reconcile_defaults", {**base_write, "limits": {}}, "reconcile-request")
    fixture("request_list_defaults", {"contract_version": FAMILY}, "list-request")
    fixture("request_show_default", {"contract_version": FAMILY, "related_task_rule_id": root_id}, "show-request")

    # All delegated policy preimages are produced by the existing pure normalizer.
    policies, mappings, work_ids, opportunity_rows = [], [], [], []
    for suffix, seed, item in [
        ("initial", generation, children["task_item_id"]),
        ("restored", successor, next(v["value"] for v in vectors if v["case_id"] == "restored_task_item_id")),
    ]:
        token = seed + ":" + custom["policy_key"]
        policy = normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "task_due", "application_scope": "item"},
                "schedule": custom["schedule"],
                "late_handling": custom["late_handling"],
            },
            item_id=item,
            item_version="1",
            command_id=token,
            created_at_utc=NOW,
            recipient_kind="subject_group",
            recipient_id="fixture_kinflow",
            channel="fixture_channel",
            delivery_target_id="delivery_target_fixture",
        )
        for artifact, prefix, preimage in [
            ("notification_intent", "notification_intent", policy.intent_id_preimage),
            ("normalized_notification_schedule_hash", None, policy.schedule_hash_preimage),
            ("notification_schedule", "notification_schedule", policy.schedule_id_preimage),
            ("notification_policy", "notification_policy", policy.policy_id_preimage),
        ]:
            vector(suffix + "_" + artifact, artifact, prefix, preimage)
        policies.append(policy.value)
        expanded = expand_notification_policy(
            policy.value,
            targets=[
                {
                    "target_utc_instant": "2026-11-14T13:00:00Z",
                    "target_scheduled_fact": "2026-11-14T13:00:00",
                    "timezone": "Etc/UTC",
                    "timezone_database_version": "2026c",
                }
            ],
            evaluated_at_utc=NOW,
            range_start_utc=NOW,
            range_end_utc=END,
        )
        opportunity = expanded.opportunities[0]
        slot_fields = {"schedule_kind": "once", "slot_descriptor": custom["schedule"]["at"]}
        constants = {
            "contract_version": "spine.notification-schedule.contract.v1",
            "normalization_version": "spine.notification-schedule.normalization.v1",
            "canonical_json_version": CANONICAL,
        }
        slot_key = vector(
            suffix + "_slot",
            "notification_schedule_slot",
            "notification_schedule_slot",
            {**constants, "derivation_version": "spine.notification-schedule-slot-key.v1", **slot_fields},
        )
        opportunity_preimage = {
            **constants,
            "derivation_version": "spine.notification-opportunity-id.v1",
            "notification_intent_id": policy.value["notification_intent_id"],
            "normalized_notification_schedule_hash": policy.value["normalized_notification_schedule_hash"],
            "target_binding": {"anchor_role": "task_due", "application_scope": "item", "item_target_scheduled_fact": "2026-11-14T13:00:00"},
            "notification_schedule_slot_key": slot_key,
            "eligible_at_utc": "2026-11-14T12:50:00Z",
        }
        opportunity_id = vector(suffix + "_opportunity", "notification_opportunity", "notification_opportunity", opportunity_preimage)
        assert opportunity_id == opportunity["notification_opportunity_id"]
        work_id = vector(
            suffix + "_work",
            "work_instance",
            "work_instance",
            {
                **constants,
                "derivation_version": "spine.notification-work-instance-id.v1",
                "notification_opportunity_id": opportunity_id,
                "delivery_target_id": "delivery_target_fixture",
            },
        )
        work_ids.append(work_id)
        opportunity_rows.append(opportunity)
        mappings.append(
            {
                "assignment_id": assignment_id,
                "generation_id": seed,
                "task_item_id": item,
                "policy_key": custom["policy_key"],
                "creation_token": token,
                "notification_intent_id": policy.value["notification_intent_id"],
                "notification_policy_id": policy.value["notification_policy_id"],
            }
        )

    # Retain the composition boundary itself, not only isolated distinct tokens.
    templates = [
        {
            "template_key": key,
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": offset}},
            "late_handling": {"kind": "skip"},
        }
        for key, offset in [("one_hour", "-3600"), ("ten_minutes", "-600")]
    ]
    replacements = [
        {
            "template_key": "ten_minutes",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-1200"}},
            "late_handling": {"kind": "skip"},
        }
    ]
    composed_initial = compose_notification_plan(templates, suppress_template_keys=["one_hour"], replacements=[], custom_additions=[custom])
    composed_reordered = compose_notification_plan(
        list(reversed(templates)), suppress_template_keys=["one_hour"], replacements=[], custom_additions=[custom]
    )
    composed_replaced = compose_notification_plan(
        templates, suppress_template_keys=["one_hour"], replacements=replacements, custom_additions=[custom]
    )
    multi_initial, multi_revised, multi_maps_initial, multi_maps_revised = [], [], [], []
    for reminder in composed_initial.reminders:
        key = reminder["policy_key"]
        token = generation + ":" + key
        initial = normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "task_due", "application_scope": "item"},
                "schedule": reminder["schedule"],
                "late_handling": reminder["late_handling"],
            },
            item_id=children["task_item_id"],
            item_version="1",
            command_id=token,
            created_at_utc=NOW,
            recipient_kind="subject_group",
            recipient_id="fixture_kinflow",
            channel="fixture_channel",
            delivery_target_id="delivery_target_fixture",
        )
        changed = next(r for r in composed_replaced.reminders if r["policy_key"] == key)
        revised = revise_notification_policy(
            initial.value,
            item_version="2",
            command_id="fixture_multi_adoption",
            changed_at_utc="2026-11-08T10:01:00Z",
            recipient_kind="subject_group",
            recipient_id="fixture_kinflow",
            channel="fixture_channel",
            delivery_target_id="delivery_target_fixture",
            target=initial.value["target"],
            schedule=changed["schedule"],
            late_handling=changed["late_handling"],
        )
        for phase, normalized_policy in [("initial", initial), ("revised", revised)]:
            for artifact, prefix, preimage in [
                ("notification_intent", "notification_intent", normalized_policy.intent_id_preimage or initial.intent_id_preimage),
                ("normalized_notification_schedule_hash", None, normalized_policy.schedule_hash_preimage),
                ("notification_schedule", "notification_schedule", normalized_policy.schedule_id_preimage),
                ("notification_policy", "notification_policy", normalized_policy.policy_id_preimage),
            ]:
                vector("composed_" + phase + "_" + key + "_" + artifact, artifact, prefix, preimage)
        multi_initial.append(initial.value)
        multi_revised.append(revised.value)
        for policy, target in [(initial.value, multi_maps_initial), (revised.value, multi_maps_revised)]:
            target.append(
                {
                    "assignment_id": assignment_id,
                    "generation_id": generation,
                    "task_item_id": children["task_item_id"],
                    "policy_key": key,
                    "creation_token": token,
                    "notification_intent_id": policy["notification_intent_id"],
                    "notification_policy_id": policy["notification_policy_id"],
                }
            )
    bundle[FIXTURES + "composed-policies.json"] = {
        "status": "offline_model_only",
        "runtime_verified": False,
        "scenario_semantics": "alternative_configuration_not_extra_main_policies",
        "templates": templates,
        "suppress_template_keys": ["one_hour"],
        "custom_additions": [custom],
        "replacements": replacements,
        "initial_reminders": list(composed_initial.reminders),
        "reordered_reminders": list(composed_reordered.reminders),
        "replacement_reminders": list(composed_replaced.reminders),
        "initial_origins": list(composed_initial.origins),
        "replacement_origins": list(composed_replaced.origins),
        "initial_policies": multi_initial,
        "revised_policies": multi_revised,
        "initial_mappings": multi_maps_initial,
        "revised_mappings": multi_maps_revised,
        "real_outer_command_id": "fixture_multi_adoption",
    }

    # Success bodies and cursor vectors bind concrete IDs, not fabricated hash literals.
    def success(name, result, effect, changed=True, command_id=None):
        value = {
            "ok": True,
            "response_contract": RESPONSE,
            "command": BASE + ("assignment.suppress" if name == "suppress" else name),
            "changed": changed,
            "effect": effect,
            "evaluated_at_utc": NOW,
            "result": result,
        }
        if name in {"show", "list"}:
            value["commit_cutoff_recheck_required"] = True
        else:
            actual = command_id or outer
            cmd = value["command"]
            rcpt = vector(
                "receipt_" + name + "_" + effect + "_" + actual,
                "command_derived",
                "command_receipt",
                {
                    "derivation_version": "spine.command-id.v1",
                    "command": cmd,
                    "command_id": actual,
                    "row_role": "command_receipt",
                    "request_path": "/command_receipt",
                },
            )
            audit_id = (
                vector(
                    "audit_" + name + "_" + effect + "_" + actual,
                    "command_derived",
                    "audit",
                    {
                        "derivation_version": "spine.command-id.v1",
                        "command": cmd,
                        "command_id": actual,
                        "row_role": "audit",
                        "request_path": "/audit",
                    },
                )
                if changed
                else None
            )
            value.update(command_id=actual, command_receipt_id=rcpt, audit_ids=[audit_id] if audit_id else [], replayed=False)
        return value

    create_response = success(
        "create",
        {"rule": rule, "generation_started": False, "materialized_work_count": "0", "delivery": DELIVERY},
        "rule_created",
        command_id=write["command_id"],
    )
    fixture("response_create", create_response, "create-response")
    replay = copy.deepcopy(create_response)
    replay["replayed"] = True
    fixture("response_create_replay", replay, "create-response")
    preview = copy.deepcopy(create_response)
    preview.update(command_receipt_id=None, audit_ids=[], replayed=False, dry_run=True, commit_cutoff_recheck_required=True)
    fixture("response_create_preview", preview, "create-response")

    cursor_vectors = []
    queries = {
        "list": {
            "contract_version": FAMILY,
            "ledger_instance_id": LEDGER,
            "owner": None,
            "source_item_id": None,
            "status": "active",
            "limit": "50",
        },
        "assignments": {
            "contract_version": FAMILY,
            "ledger_instance_id": LEDGER,
            "related_task_rule_id": root_id,
            "view": "assignments",
            "limit": "50",
        },
        "generations": {
            "contract_version": FAMILY,
            "ledger_instance_id": LEDGER,
            "related_task_rule_id": root_id,
            "view": "generations",
            "assignment_id": assignment_id,
            "limit": "50",
        },
        "states": {
            "contract_version": FAMILY,
            "ledger_instance_id": LEDGER,
            "related_task_rule_id": root_id,
            "view": "states",
            "assignment_id": assignment_id,
            "limit": "50",
        },
        "reconcile": {"contract_version": FAMILY, "ledger_instance_id": LEDGER, "related_task_rule_id": root_id, "limits": limits},
    }
    lane_start = {"assignment_after_seq": "0", "source_after": None}
    lane_end = {"assignment_after_seq": "1", "source_after": {"scheduled_fact": selected["scheduled_fact"], "selector": selected}}
    for purpose in queries:
        payload = {
            "cursor_version": CURSOR,
            "canonical_json_version": CANONICAL,
            "key_id": "public_fixture_key",
            "catalog_generation": "2",
            "issued_at_utc": NOW,
            "expires_at_utc": "2026-11-08T11:00:00Z",
            "purpose": purpose,
            "query": queries[purpose],
            "after": root_id if purpose == "list" else lane_end if purpose == "reconcile" else "1",
        }
        if purpose == "reconcile":
            payload.update(
                rule_change_version="2", rule_revision_id=revision, **source, evaluation_at_utc=NOW, range_start_utc=NOW, range_end_utc=END
            )
        encoded = canonical_json_bytes(payload)
        signed = CURSOR.encode() + b"\x00" + encoded
        tag = hmac.new(bytes.fromhex(TEST_KEY), signed, hashlib.sha256).digest()
        cursor_vectors.append(
            {
                "purpose": purpose,
                "key_hex": TEST_KEY,
                "payload": payload,
                "canonical_json": encoded.decode(),
                "hmac_input_hex": signed.hex(),
                "hmac_sha256": tag.hex(),
                "wire": b64(encoded) + "." + b64(tag),
            }
        )
    cursor_wire = {v["purpose"]: v["wire"] for v in cursor_vectors}
    fixture(
        "request_reconcile_cursor",
        {
            **base_write,
            "expected": {**expected, "rule_change_version": "2", "catalog_generation": "2"},
            "limits": limits,
            "cursor": cursor_wire["reconcile"],
        },
        "reconcile-request",
    )
    fixture("request_list_cursor", {"contract_version": FAMILY, "cursor": cursor_wire["list"]}, "list-request")
    fixture(
        "response_show_rule",
        success("show", {"rule": rule, "read_at_utc": NOW, "delivery": DELIVERY}, "rule_shown", False),
        "show-response",
    )
    fixture(
        "response_show_assignment",
        success("show", {"assignment": assignment, "read_at_utc": NOW, "delivery": DELIVERY}, "rule_shown", False),
        "show-response",
    )
    fixture(
        "response_show_proof",
        success("show", {"proof": proof, "read_at_utc": NOW, "delivery": DELIVERY}, "rule_shown", False),
        "show-response",
    )
    summary = {k: rule[k] for k in read(SCHEMAS + "responses.schema.json")["$defs"]["ruleSummary"]["required"]}
    fixture(
        "response_list",
        success(
            "list",
            {
                "rows": [summary],
                "query": queries["list"],
                "catalog_generation": "1",
                "has_more": False,
                "next_cursor": None,
                "read_at_utc": NOW,
                "delivery": DELIVERY,
            },
            "rules_listed",
            False,
        ),
        "list-response",
    )
    for view, rows, effect in [
        ("assignments", [assignment], "rule_shown"),
        ("generations", [generation_record], "rule_shown"),
        ("states", [state_record], "rule_shown"),
    ]:
        request = {"contract_version": FAMILY, "related_task_rule_id": root_id, "view": view, "limit": "50"}
        if view != "assignments":
            request["assignment_id"] = assignment_id
        fixture("request_show_" + view, request, "show-request")
        fixture(
            "response_show_" + view,
            success(
                "show",
                {
                    "rows": rows,
                    "query": queries[view],
                    "catalog_generation": "2",
                    "has_more": False,
                    "next_cursor": None,
                    "read_at_utc": NOW,
                    "delivery": DELIVERY,
                },
                effect,
                False,
            ),
            "show-response",
        )
    for view, extra in [("assignment", {"assignment_id": assignment_id}), ("proof", {"proof_id": proof_id})]:
        fixture(
            "request_show_" + view, {"contract_version": FAMILY, "related_task_rule_id": root_id, "view": view, **extra}, "show-request"
        )
    coverage = {
        k: {
            "status": "complete" if k in {"generation", "assignments"} else "not_applicable",
            "processed_count": "1" if k == "generation" else "0",
            "remaining_known_count": "0",
        }
        for k in ["generation", "assignments", "adoption", "retirement"]
    }
    page_rule = {**rule, "change_version": "2", "catalog_generation": "2"}
    page = {
        "rule": page_rule,
        "source_snapshot": source,
        "selection": {
            "evaluation_at_utc": NOW,
            "execution_at_utc": NOW,
            "limits": limits,
            "lane_start": lane_start,
            "lane_end": lane_end,
            "intent_id": None,
            "assignment_high_water": None,
        },
        "results": [
            {
                "outcome": "created",
                "reason": "new_source_slot",
                "selector": selected,
                "occurrence_key": occurrence_key,
                "assignment_id": assignment_id,
                "generation_id": generation,
                "actions": sorted(["assignment_created", "alias_reserved", "task_created"]),
                "before": None,
                "after": child_refs,
                "proof_ids": [proof_id],
            }
        ],
        "policy_mappings": [mappings[0]],
        "work": {"created": [work_ids[0]], "retained": [], "cancelled": [], "protected_stale": []},
        "coverage": coverage,
        "future_generation": "waiting",
        "has_more": False,
        "next_cursor": None,
        "delivery": DELIVERY,
    }
    fixture("response_reconcile_created", success("reconcile", page, "rule_page_applied"), "reconcile-response")
    partial = copy.deepcopy(page)
    partial.update(has_more=True, next_cursor=cursor_wire["reconcile"])
    partial["coverage"]["generation"].update(status="partial", remaining_known_count=None)
    fixture("response_reconcile_partial", success("reconcile", partial, "rule_page_applied"), "reconcile-response")
    noop = copy.deepcopy(page)
    noop.update(results=[], policy_mappings=[], work={k: [] for k in page["work"]})
    noop["selection"]["lane_start"] = lane_end
    noop["coverage"] = {
        k: {
            "status": "complete" if k in {"generation", "assignments"} else "not_applicable",
            "processed_count": "0",
            "remaining_known_count": "0",
        }
        for k in coverage
    }
    fixture("response_reconcile_noop", success("reconcile", noop, "rule_page_noop", False), "reconcile-response")
    progress_only = copy.deepcopy(noop)
    progress_only["selection"].update(lane_start=lane_start, lane_end=lane_end)
    fixture("response_reconcile_progress", success("reconcile", progress_only, "rule_progress_advanced"), "reconcile-response")
    blocked = copy.deepcopy(noop)
    blocked["results"] = [
        {
            "outcome": "decision_required",
            "reason": "source_continuity_unresolved",
            "selector": selected,
            "occurrence_key": occurrence_key,
            "assignment_id": assignment_id,
            "generation_id": generation,
            "actions": [],
            "before": child_refs,
            "after": child_refs,
            "proof_ids": [],
        }
    ]
    blocked["coverage"]["assignments"].update(status="decision_required", processed_count="1", remaining_known_count="1")
    blocked["future_generation"] = "blocked"
    blocked["policy_mappings"] = [mappings[0]]
    blocked["selection"].update(lane_start=lane_start, lane_end={"assignment_after_seq": "1", "source_after": None})
    fixture(
        "response_reconcile_decision_required", success("reconcile", blocked, "rule_page_decision_required", False), "reconcile-response"
    )
    # Source evidence now refers to retained normalized snapshots and actual
    # registered lineage facts, not fixture-label hashes or dangling IDs.
    proofs = [proof]
    prior = {"prior_proof_id": proof_id, "prior_selector": selected}

    def add_proof(kind, snapshot_name, extras, case, *, fact=None, use_rdate=False):
        current = source_values[snapshot_name]
        payload = {k: current[k] for k in source}
        payload["lineage_ids"] = sorted(f["row"]["lineage_id"] for f in source_pairs.get(snapshot_name, {}).get("lineage", []))
        if kind != "source_cancelled":
            sel = selector_for(current, fact or selected["scheduled_fact"], rules=not use_rdate, rdates=use_rdate)
            payload.update(selector=sel, occurrence_key=occurrence(sel, case + "_key"))
        payload.update(extras)
        pid = identity("related_task_proof", {"related_task_rule_id": root_id, "proof_kind": kind, "proof_payload": payload}, case)
        record = {
            **proof,
            "proof_id": pid,
            "proof_kind": kind,
            "proof_json": payload,
            "proof_hash": pid.rsplit("_", 1)[1],
            "source_item_version": payload["source_item_version"],
            "recurrence_revision_id": payload["recurrence_revision_id"],
            "prior_recurrence_revision_id": source["recurrence_revision_id"] if snapshot_name != "main" else None,
        }
        proofs.append(record)
        return record

    add_proof("identity", "main", {}, "proof_identity")
    copied = source_values["copied"]
    copied_selector = selector_for(copied, selected["scheduled_fact"])
    copy_ids = sorted(f["row"]["lineage_id"] for f in source_pairs["copied"]["lineage"])
    hop = {
        "prior_revision_id": source["recurrence_revision_id"],
        "new_revision_id": copied["recurrence_revision_id"],
        "prior_selector": selected,
        "selector": copied_selector,
        "lineage_ids": copy_ids,
    }
    add_proof("carry_forward", "copied", {**prior, "hops": [hop]}, "proof_carry_forward")
    add_proof(
        "component_candidate",
        "main",
        {
            "basis_revision_id": source["recurrence_revision_id"],
            "component_selector": {"source_kind": "rule", "selector": source_rule},
            "hops": [],
        },
        "proof_component_candidate",
    )
    added = source_values["added"]
    add_proof(
        "new_rdate",
        "added",
        {
            "rdate_id": added["rdates"][0]["rdate_id"],
            "prior_recurrence_revision_id": source["recurrence_revision_id"],
        },
        "proof_new_rdate",
        fact="2026-11-15T11:30:00",
        use_rdate=True,
    )
    for kind, snapshot_name, extras in [
        (
            "excluded",
            "excluded",
            {"exdate_id": source_values["excluded"]["exdates"][0]["exdate_id"], "exclusion_active": True, "actionable": False},
        ),
        (
            "occurrence_cancelled",
            "occurrence_cancelled",
            {
                "override_id": source_values["occurrence_cancelled"]["overrides"][0]["override_id"],
                "lifecycle": "cancelled",
                "actionable": False,
            },
        ),
    ]:
        current_identity = add_proof("identity", snapshot_name, prior, "proof_identity_before_" + kind)
        add_proof(
            kind,
            snapshot_name,
            {
                **extras,
                "prior_proof_id": current_identity["proof_id"],
                "prior_selector": current_identity["proof_json"]["selector"],
            },
            "proof_" + kind,
        )
    add_proof(
        "source_cancelled",
        "source_cancelled",
        {
            "lineage_ids": [],
            "cancelled_event_version": "2",
            "event_status": "cancelled",
        },
        "proof_source_cancelled",
    )
    excluded_proof = next(p for p in proofs if p["proof_kind"] == "excluded")
    cancelled_state = {
        **state,
        "task_item_version": "2",
        "proof_id": excluded_proof["proof_id"],
        "source_item_version": "2",
        "recurrence_revision_id": excluded_proof["recurrence_revision_id"],
        "disposition": "source_cancelled",
        "reason": "source_excluded",
    }
    cancelled_hash = identity("state_hash", {"state": cancelled_state}, "cancelled_state_hash")
    cancelled_state_id = identity(
        "related_task_assignment_revision",
        {"assignment_id": assignment_id, "change_version": "2", "prior_assignment_revision_id": state_id, "state_hash": cancelled_hash},
        "cancelled_assignment_revision",
    )
    cancelled_record = {
        **state_record,
        "assignment_revision_id": cancelled_state_id,
        "change_version": "2",
        "prior_assignment_revision_id": state_id,
        "state_json": cancelled_state,
        "state_hash": cancelled_hash,
        "task_item_version": "2",
        "source_item_version": "2",
        "recurrence_revision_id": excluded_proof["recurrence_revision_id"],
        "proof_id": cancelled_state["proof_id"],
    }
    cancellation = {
        "generation_id": generation,
        "cancelled_task_version": "2",
        "proof_id": cancelled_state["proof_id"],
        "assignment_revision_id": cancelled_state_id,
        "command_id": outer,
        "cancelled_at_utc": NOW,
    }
    suppression_id = identity("related_task_suppression", {"assignment_id": assignment_id, "target_generation_id": generation})
    suppression_receipt = "command_receipt_" + digest(
        {
            "derivation_version": "spine.command-id.v1",
            "command": BASE + "assignment.suppress",
            "command_id": "fixture_suppress",
            "row_role": "command_receipt",
            "request_path": "/command_receipt",
        }
    )
    suppression = {
        "suppression_id": suppression_id,
        "assignment_id": assignment_id,
        "target_generation_id": generation,
        "actor_subject_id": "fixture_operator",
        "command_id": "fixture_suppress",
        "command_receipt_id": suppression_receipt,
        "suppressed_at_utc": NOW,
    }
    suppressed_state = {**cancelled_state, "disposition": "suppressed", "reason": "restoration_suppressed", "restoration_veto": True}
    suppressed_hash = identity("state_hash", {"state": suppressed_state}, "suppressed_state_hash")
    suppressed_state_id = identity(
        "related_task_assignment_revision",
        {
            "assignment_id": assignment_id,
            "change_version": "3",
            "prior_assignment_revision_id": cancelled_state_id,
            "state_hash": suppressed_hash,
        },
        "suppressed_assignment_revision",
    )
    suppressed_record = {
        **cancelled_record,
        "assignment_revision_id": suppressed_state_id,
        "change_version": "3",
        "prior_assignment_revision_id": cancelled_state_id,
        "state_json": suppressed_state,
        "state_hash": suppressed_hash,
        "command_id": "fixture_suppress",
    }
    suppressed = copy.deepcopy(assignment)
    suppressed.update(
        change_version="3",
        assignment_revision_id=suppressed_state_id,
        task_item_version="2",
        task_status="cancelled",
        disposition="suppressed",
        reason="restoration_suppressed",
        restoration_veto=True,
        suppression=suppression,
        source_cancellation=cancellation,
        observed_task_item_version="2",
    )
    suppressed["source_snapshot"] = {k: excluded_proof["proof_json"][k] for k in source}
    suppressed.update(
        source_proof_id=excluded_proof["proof_id"],
        observed_source_item_version="2",
        observed_recurrence_revision_id=excluded_proof["recurrence_revision_id"],
    )
    fixture(
        "response_suppress",
        success(
            "suppress",
            {"assignment": suppressed, "suppression": suppression, "successor_generation_id": None, "delivery": DELIVERY},
            "assignment_restoration_suppressed",
            command_id="fixture_suppress",
        ),
        "suppress-response",
    )
    fixture(
        "response_suppress_noop",
        success(
            "suppress",
            {"assignment": suppressed, "suppression": suppression, "successor_generation_id": None, "delivery": DELIVERY},
            "assignment_suppress_noop",
            False,
            "fixture_suppress_noop",
        ),
        "suppress-response",
    )
    # A changed configuration, adoption intent, and all retirement dispositions.
    updated_config = copy.deepcopy(normalized)
    updated_config["offset_seconds"] = "6000"
    new_hash = identity("configuration_hash", {"configuration": updated_config}, "updated_configuration_hash")
    new_revision = identity(
        "related_task_rule_revision",
        {"related_task_rule_id": root_id, "revision_index": "2", "prior_revision_id": revision, "configuration_hash": new_hash},
        "updated_rule_revision",
    )
    adopt_payload = {"configuration_revision_id": new_revision, "assignment_high_water": "1", "scope": "upcoming_open"}
    adopt_id = identity(
        "related_task_intent",
        {"related_task_rule_id": root_id, "rule_change_version": "3", "intent_kind": "adopt", "intent_payload": adopt_payload},
        "adoption_intent",
    )
    adopt_summary = {
        "intent_id": adopt_id,
        "status": "pending",
        "kind": "adopt",
        "assignment_high_water": "1",
        "scope": "upcoming_open",
        "disposition": None,
        "configuration_revision_id": new_revision,
    }
    updated_rule = {
        **page_rule,
        "configuration": updated_config,
        "configuration_hash": new_hash,
        "rule_revision_id": new_revision,
        "revision_index": "2",
        "change_version": "3",
        "catalog_generation": "3",
        "adoption_intent": adopt_summary,
    }
    update_result = {
        "rule": updated_rule,
        "prior_rule_revision_id": revision,
        "new_rule_revision_id": new_revision,
        "adoption_scope": "upcoming_open",
        "intent_id": adopt_id,
        "assignment_high_water": "1",
        "delivery": DELIVERY,
    }
    fixture(
        "response_update", success("update", update_result, "rule_configuration_updated", command_id="fixture_update"), "update-response"
    )
    noop_update = {**update_result, "prior_rule_revision_id": new_revision, "new_rule_revision_id": new_revision}
    fixture("response_update_noop", success("update", noop_update, "rule_update_noop", False, "fixture_update_noop"), "update-response")
    same_root_adoption = {**update_result, "prior_rule_revision_id": new_revision}
    fixture(
        "response_update_adoption_only",
        success("update", same_root_adoption, "rule_adoption_requested", command_id="fixture_adoption_only"),
        "update-response",
    )
    intents = [
        {
            "intent_id": adopt_id,
            "related_task_rule_id": root_id,
            "rule_change_version": "3",
            "intent_kind": "adopt",
            "intent_json": adopt_payload,
            "status": "pending",
            "created_by_command_id": "fixture_update",
            "created_at_utc": NOW,
        }
    ]
    for disposition in types["disposition"]["enum"]:
        payload = {"disposition": disposition, "assignment_high_water": "1"}
        if disposition != "keep_following":
            payload["superseded_adoption_intent_id"] = adopt_id
        retire_id = identity(
            "related_task_intent",
            {"related_task_rule_id": root_id, "rule_change_version": "4", "intent_kind": "retire", "intent_payload": payload},
            "retirement_" + disposition,
        )
        intent_summary = {
            "intent_id": retire_id,
            "status": "pending",
            "kind": "retire",
            "assignment_high_water": "1",
            "scope": None,
            "disposition": disposition,
            "configuration_revision_id": None,
        }
        retired = {
            **updated_rule,
            "status": "retired",
            "change_version": "4",
            "catalog_generation": "4",
            "retirement_disposition": disposition,
            "retirement_intent": intent_summary,
            "adoption_intent": adopt_summary if disposition == "keep_following" else {**adopt_summary, "status": "superseded"},
        }
        result = {
            "rule": retired,
            "generation_stopped": True,
            "cleanup_status": "pending",
            "retirement_intent_id": retire_id,
            "assignment_high_water": "1",
            "disposition": disposition,
            "delivery": DELIVERY,
        }
        fixture(
            "response_retire_" + disposition,
            success("retire", result, "rule_retired", command_id="fixture_retire_" + disposition),
            "retire-response",
        )
        if disposition == "keep_following":
            fixture("response_retire_noop", success("retire", result, "rule_retire_noop", False, "fixture_retire_noop"), "retire-response")
        intents.append(
            {
                "intent_id": retire_id,
                "related_task_rule_id": root_id,
                "rule_change_version": "4",
                "intent_kind": "retire",
                "intent_json": payload,
                "status": "pending",
                "created_by_command_id": "fixture_retire_" + disposition,
                "created_at_utc": NOW,
            }
        )
    unicode_config = copy.deepcopy(normalized)
    unicode_config["task_template"]["item"]["title"] = 'Pick up Zoë — 科学 🧪\n"entrance"\t'
    identity("configuration_hash", {"configuration": unicode_config}, "unicode_control_configuration")
    # Every closed error code has a representative public failure; precedence
    # itself also has explicit offline model witnesses below.
    for code in types["errorCode"]["enum"]:
        failure_field = {
            "environment_failure": "schema_version",
            "unsupported_command": "command",
            "unsupported_contract_version": "contract_version",
            "invalid_request": "limits.assignments",
            "unsupported_field": "force",
            "command_id_conflict": "command_id",
            "referenced_row_not_found": "related_task_rule_id",
            "stale_cursor": "cursor",
            "stale_version": "expected.rule_change_version",
            "semantic_conflict": "configuration.task_owner",
            "rendering_disclosure_unavailable": "configuration.notification_plan",
            "capacity_exceeded": "limits.work_rows",
            "stale_evaluation": "evaluated_at_utc",
        }[code]
        failure_command, failure_message = {
            "semantic_conflict": ("update", "Synthetic update branch: configuration.task_owner changes the rule's immutable child owner."),
            "rendering_disclosure_unavailable": (
                "update",
                "Synthetic update branch: configuration.notification_plan selects unavailable detail disclosure.",
            ),
        }.get(code, ("reconcile", "Synthetic branch-specific offline " + code))
        fixture(
            "failure_" + code,
            {
                "ok": False,
                "response_contract": RESPONSE,
                "command": BASE + failure_command,
                "changed": False,
                "error": {
                    "code": code,
                    "field": failure_field,
                    "message": failure_message,
                },
            },
            "failure",
        )
    for name, original, mutate, schema in [
        ("unknown_force", {**base_write, "limits": {}}, lambda x: x.update(force=True), "reconcile-request"),
        ("numeric_limit", {**base_write, "limits": {}}, lambda x: x["limits"].update(assignments=32), "reconcile-request"),
        ("over_limit", {**base_write, "limits": {}}, lambda x: x["limits"].update(assignments="129"), "reconcile-request"),
        ("negative_zero", create, lambda x: x["configuration"].update(offset_seconds="-0"), "create-request"),
        ("fractional_time", create, lambda x: x.update(requested_at_utc="2026-11-08T10:00:00.1Z"), "create-request"),
        ("false_delivery_claim", create_response, lambda x: x["result"].update(delivery="delivered"), "create-response"),
        (
            "read_receipt",
            success("show", {"rule": rule, "read_at_utc": NOW, "delivery": DELIVERY}, "rule_shown", False),
            lambda x: x.update(command_receipt_id=receipt),
            "show-response",
        ),
        ("preview_receipt", preview, lambda x: x.update(command_receipt_id=receipt), "create-response"),
    ]:
        invalid = copy.deepcopy(original)
        mutate(invalid)
        fixture("invalid_" + name, invalid, schema, False)
    bundle[FIXTURES + "computed.json"] = {
        "vector_version": "spine.recurring-related-task-computed.v1",
        "status": "offline_model_only",
        "runtime_verified": False,
        "vectors": vectors,
    }
    bundle[FIXTURES + "cursors.json"] = {
        "vector_version": "spine.recurring-related-task-cursors.v1",
        "status": "offline_model_only",
        "runtime_verified": False,
        "vectors": cursor_vectors,
        "cases": cursor_witnesses(cursor_vectors),
    }
    bundle[FIXTURES + "decisions.json"] = decision_witnesses()
    bundle[FIXTURES + "source-proofs.json"] = sources
    bundle[FIXTURES + "evidence.json"] = {
        "status": "offline_model_only",
        "runtime_verified": False,
        "scenario_semantics": "alternative_branch_examples_not_one_ledger_snapshot",
        "proofs": proofs,
        "states": [state_record, cancelled_record, suppressed_record],
        "generations": [generation_record],
        "intents": intents,
        "source_cancellations": [cancellation],
        "owners": [{"header": owner_header, "revision": owner_revision}],
        "suppressions": [suppression],
        "policies": policies,
        "opportunities": opportunity_rows,
        "schedule_example": {
            "source_timezone": "Etc/UTC",
            "timezone_database_version": "2026c",
            "expressed_start_utc": "2026-11-14T11:30:00Z",
            "offset_seconds": "5400",
            "task_due_utc": "2026-11-14T13:00:00Z",
            "reminder_offset_seconds": "-600",
            "eligible_at_utc": "2026-11-14T12:50:00Z",
        },
    }
    closure_path = "contracts/recurring-related-task-schema-closure.v1.json"
    bundle[closure_path] = schema_closure()
    bundle["contracts/recurring-related-task-fixture-manifest.json"] = {
        "contract_version": "spine.recurring-related-task-fixtures.v1",
        "status": "ratified_source_only",
        "runtime_verified": False,
        "registry": "contracts/recurring-related-tasks.v1.json",
        "schema_closure": closure_path,
        "builder": "scripts/build_recurring_related_task_contract_fixtures.py",
        "fixtures": sorted(fixtures, key=lambda f: f["fixture_id"]),
        "computed": FIXTURES + "computed.json",
        "cursors": FIXTURES + "cursors.json",
        "evidence": FIXTURES + "evidence.json",
        "decisions": FIXTURES + "decisions.json",
        "source_proofs": FIXTURES + "source-proofs.json",
        "composed_policies": FIXTURES + "composed-policies.json",
        "source_snapshot_schema": "contracts/schemas/recurrence-set.schema.json",
        "builder_helpers": ["scripts/recurring_related_task_fixture_sources.py"],
        "test_oracle_helpers": ["tests/recurring_related_task_oracles.py"],
        "runtime_obligations": [row["id"] for row in descriptor["runtime_obligations"]],
    }
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read/compare retained artifacts; never write them")
    args = parser.parse_args()
    bundle = build()
    if args.check:
        drift = [path for path, value in bundle.items() if not (ROOT / path).is_file() or read(path) != value]
        if drift:
            raise SystemExit("Fixture drift: " + ", ".join(drift))
        print(f"Verified {len(bundle)} deterministic source-only artifacts; runtime pending")
    else:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
