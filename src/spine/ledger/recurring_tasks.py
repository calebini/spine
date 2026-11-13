"""Internal R1 repository: immutable records, reservations and checked pointers.

Helpers never commit. The existing outer transaction owns atomicity. Only rows
touched in that transaction are finalized; full verification is explicit.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurring_tasks import (
    closed,
    decode,
    derive,
    integer,
    invariant,
    occurrence_key,
    payload_hash,
    validate_proof,
    validate_state,
)
from spine.ledger.recurrence import load_target_occurrence_selector, persist_target_occurrence_selector
from spine.ledger.recurring_task_sources import ProofBudget, require_candidate, verify_proof

TABLE_KEYS = {
    "related_task_rules": ("related_task_rule_id",),
    "related_task_rule_revisions": ("related_task_rule_revision_id",),
    "related_task_assignments": ("assignment_id",),
    "related_task_source_proofs": ("proof_id",),
    "related_task_proof_lineage": ("proof_id", "lineage_id"),
    "related_task_selector_reservations": ("related_task_rule_id", "selector_ref"),
    "related_task_generations": ("generation_id",),
    "related_task_assignment_revisions": ("assignment_revision_id",),
    "related_task_source_cancellations": ("generation_id",),
    "related_task_restoration_suppressions": ("suppression_id",),
    "related_task_intents": ("intent_id",),
    "related_task_intent_outcomes": ("intent_id", "assignment_id"),
    "related_task_rule_progress": ("related_task_rule_id",),
    "related_task_catalog_state": ("singleton_id",),
    "related_task_dirty_rules": ("related_task_rule_id",),
}


def row(db: sqlite3.Connection, table: str, first: object, second: object | None = None) -> dict[str, Any] | None:
    invariant(table in TABLE_KEYS, "unknown recurring-task table")
    keys = TABLE_KEYS[table]
    where = " AND ".join(f"{key}=?" for key in keys)
    found = db.execute(f"SELECT * FROM {table} WHERE {where}", (first,) if len(keys) == 1 else (first, second)).fetchone()
    return dict(found) if found is not None else None


def required(db: sqlite3.Connection, table: str, first: object, second: object | None = None) -> dict[str, Any]:
    value = row(db, table, first, second)
    invariant(value is not None, "missing recurring-task reference: " + table)
    assert value is not None
    return value


def insert_record(db: sqlite3.Connection, table: str, value: Mapping[str, object]) -> None:
    invariant(db.in_transaction and getattr(db, "_recurring_tasks_enabled", False), "owning recurring-task transaction required")
    invariant(table in TABLE_KEYS)
    columns = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
    invariant(value.keys() <= columns, "unknown recurring-task column")
    keys = list(value)
    values = [canonical_json_bytes(v).decode() if isinstance(v, dict) else v for v in value.values()]
    db.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", values)


def compare_and_swap(db: sqlite3.Connection, table: str, identity: str, expected: int, changes: Mapping[str, object]) -> None:
    invariant(db.in_transaction and getattr(db, "_recurring_tasks_enabled", False))
    allowed = {
        "related_task_rules": ("change_version", {"current_revision_id", "next_assignment_seq", "status", "retirement_intent_id"}),
        "related_task_assignments": ("change_version", {"current_assignment_revision_id", "current_generation_id"}),
        "related_task_rule_progress": (
            "progress_version",
            {"source_scan_version", "recurrence_revision_id", "coverage_json", "assignment_after_seq", "pending_intent_id"},
        ),
    }
    invariant(table in allowed)
    counter, fields = allowed[table]
    invariant(bool(changes) and changes.keys() <= fields and 0 <= expected < 9223372036854775807)
    values = [canonical_json_bytes(v).decode() if isinstance(v, dict) else v for v in changes.values()]
    result = db.execute(
        f"UPDATE {table} SET "
        + ",".join(f"{key}=?" for key in changes)
        + f",{counter}={counter}+1 "
        + f"WHERE {TABLE_KEYS[table][0]}=? AND {counter}=?",
        (*values, identity, expected),
    )
    if result.rowcount != 1:
        raise SpineValidationError("stale_version", "recurring-task compare-and-swap failed")


def validate_selector(db: sqlite3.Connection, selector_ref: str, selector: dict[str, Any], key: str, set_id: str) -> None:
    invariant(
        selector_ref == "recurrence_target_selector_" + hash_canonical_json(selector)
        and selector["recurrence_set_id"] == set_id
        and occurrence_key(selector) == key,
        "selector identity mismatch",
    )
    stored = db.execute(
        "SELECT occurrence_key,recurrence_set_id FROM recurrence_target_occurrence_selectors WHERE target_occurrence_selector_ref=?",
        (selector_ref,),
    ).fetchone()
    invariant(stored is not None and stored["occurrence_key"] == key and stored["recurrence_set_id"] == set_id, "selector header mismatch")
    invariant(load_target_occurrence_selector(db, selector_ref=selector_ref) == selector, "selector child/preimage mismatch")


def ensure_selector(db: sqlite3.Connection, *, revision_id: str, selector: dict[str, Any], budget: ProofBudget) -> str:
    """Prove actual children before the existing INSERT OR IGNORE producer."""
    invariant(db.in_transaction)
    require_candidate(db, revision_id, selector, budget)
    key = occurrence_key(selector)
    reference = "recurrence_target_selector_" + hash_canonical_json(selector)
    existing = db.execute(
        "SELECT 1 FROM recurrence_target_occurrence_selectors WHERE target_occurrence_selector_ref=? OR occurrence_key=?", (reference, key)
    ).fetchone()
    if existing is not None:
        validate_selector(db, reference, selector, key, selector["recurrence_set_id"])
        return reference
    actual = persist_target_occurrence_selector(db, selector=selector, occurrence_key=key)
    invariant(actual == reference)
    validate_selector(db, reference, selector, key, selector["recurrence_set_id"])
    return reference


def reserve_selector(
    db: sqlite3.Connection,
    *,
    rule_id: str,
    assignment_id: str,
    proof_id: str,
    selector: dict[str, Any],
    revision_id: str,
    budget: ProofBudget,
) -> None:
    reference = ensure_selector(db, revision_id=revision_id, selector=selector, budget=budget)
    existing = row(db, "related_task_selector_reservations", rule_id, reference)
    if existing is not None:
        invariant(
            existing["assignment_id"] == assignment_id and decode(existing["selector_json"]) == selector,
            "selector reservation cannot transfer assignments",
        )
        return
    insert_record(
        db,
        "related_task_selector_reservations",
        {
            "related_task_rule_id": rule_id,
            "selector_ref": reference,
            "selector_json": selector,
            "occurrence_key": occurrence_key(selector),
            "assignment_id": assignment_id,
            "proof_id": proof_id,
        },
    )


def _owner(value: dict[str, Any]) -> dict[str, Any]:
    result = {"owner_kind": value["owner_kind"]}
    for key in ("owner_subject_id", "owner_group_id"):
        if value[key] is not None:
            result[key] = value[key]
    return result


def _id(kind: str, value: dict[str, Any], column: str, fields: dict[str, Any]) -> None:
    invariant(derive(kind, fields)[0] == value[column], "recurring-task identity/preimage mismatch: " + kind)


def _rule_root(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    owner = _owner(value)
    invariant(decode(value["owner_key"]) == owner, "rule owner snapshot mismatch")
    _id("rule", value, "related_task_rule_id", {"owner": owner, "rule_key": value["rule_key"]})
    source = db.execute(
        "SELECT s.source_item_id,r.source_item_version,i.item_type FROM recurrence_sets s "
        "JOIN recurrence_revisions r USING(recurrence_set_id) JOIN coordination_items i ON i.item_id=s.source_item_id "
        "WHERE s.recurrence_set_id=? AND r.recurrence_revision_id=?",
        (value["recurrence_set_id"], value["enrolled_recurrence_revision_id"]),
    ).fetchone()
    invariant(
        source is not None and source["source_item_id"] == value["source_item_id"] and source["item_type"] == "event",
        "rule source mismatch",
    )
    revision = required(db, "related_task_rule_revisions", value["current_revision_id"])
    invariant(revision["related_task_rule_id"] == value["related_task_rule_id"] and revision["revision_index"] <= value["change_version"])
    latest = db.execute(
        "SELECT related_task_rule_revision_id FROM related_task_rule_revisions "
        "WHERE related_task_rule_id=? ORDER BY revision_index DESC LIMIT 1",
        (value["related_task_rule_id"],),
    ).fetchone()
    invariant(latest is not None and latest[0] == value["current_revision_id"], "rule pointer is not its latest configuration")
    enrollment = decode(value["enrollment_json"])
    if enrollment.get("kind") == "upcoming":
        closed(enrollment, {"kind"})
    else:
        closed(enrollment, {"kind", "occurrence_key", "selector", "recurrence_revision_id"})
        invariant(
            enrollment["kind"] == "selected_occurrence" and enrollment["recurrence_revision_id"] == value["enrolled_recurrence_revision_id"]
        )
        invariant(occurrence_key(enrollment["selector"]) == enrollment["occurrence_key"])
    if value["retirement_intent_id"] is not None:
        intent = required(db, "related_task_intents", value["retirement_intent_id"])
        invariant(intent["related_task_rule_id"] == value["related_task_rule_id"] and intent["intent_kind"] == "retire")


def _configuration(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    config = decode(value["configuration_json"])
    closed(
        config,
        {
            "task_owner",
            "task_template",
            "offset_basis",
            "offset_seconds",
            "notification_plan",
            "delivery",
            "materialization",
            "generation_horizon_seconds",
        },
    )
    owner = config["task_owner"]
    invariant(isinstance(owner, dict) and owner.get("owner_kind") in {"subject", "subject_group"}, "system is not a child owner")
    field = "owner_subject_id" if owner["owner_kind"] == "subject" else "owner_group_id"
    closed(owner, {"owner_kind", field})
    invariant(integer(config["generation_horizon_seconds"], minimum=1) <= 31622400, "generation horizon out of bounds")
    offset = config["offset_seconds"]
    invariant(isinstance(offset, str), "offset must be a canonical decimal string")
    absolute = integer(offset[1:] if offset.startswith("-") else offset)
    invariant(absolute <= 31622400 and offset != "-0", "offset out of bounds")
    invariant(config["offset_basis"] == "elapsed" and payload_hash("configuration", config)[0] == value["configuration_hash"])
    fields = {
        "related_task_rule_id": value["related_task_rule_id"],
        "revision_index": str(value["revision_index"]),
        "configuration_hash": value["configuration_hash"],
    }
    if value["prior_revision_id"] is not None:
        fields["prior_revision_id"] = value["prior_revision_id"]
        prior = required(db, "related_task_rule_revisions", value["prior_revision_id"])
        invariant(prior["related_task_rule_id"] == value["related_task_rule_id"] and prior["revision_index"] + 1 == value["revision_index"])
        invariant(decode(prior["configuration_json"])["task_owner"] == owner, "immutable child owner changed")
    _id("rule_revision", value, "related_task_rule_revision_id", fields)
    root = required(db, "related_task_rules", value["related_task_rule_id"])
    current = required(db, "related_task_rule_revisions", root["current_revision_id"])
    invariant(current["revision_index"] >= value["revision_index"], "unpublished rule revision")


def _assignment(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    root = required(db, "related_task_rules", value["related_task_rule_id"])
    selector = decode(value["initial_selector_json"])
    _id("assignment", value, "assignment_id", {"related_task_rule_id": value["related_task_rule_id"], "initial_selector": selector})
    validate_selector(db, value["initial_selector_ref"], selector, value["initial_occurrence_key"], root["recurrence_set_id"])
    invariant(root["next_assignment_seq"] > value["assignment_seq"], "assignment sequence was not allocated")
    current = required(db, "related_task_assignment_revisions", value["current_assignment_revision_id"])
    invariant(
        current["assignment_id"] == value["assignment_id"]
        and current["change_version"] == value["change_version"]
        and current["generation_id"] == value["current_generation_id"],
        "assignment pointer mismatch",
    )
    generation = required(db, "related_task_generations", value["current_generation_id"])
    successor = db.execute(
        "SELECT 1 FROM related_task_generations WHERE predecessor_generation_id=?", (generation["generation_id"],)
    ).fetchone()
    invariant(successor is None, "assignment points to a superseded generation")


def _proof(db: sqlite3.Connection, value: dict[str, Any], budget: ProofBudget) -> None:
    payload = decode(value["proof_json"])
    root = required(db, "related_task_rules", value["related_task_rule_id"])
    _id(
        "proof",
        value,
        "proof_id",
        {"related_task_rule_id": value["related_task_rule_id"], "proof_kind": value["proof_kind"], "proof_payload": payload},
    )
    invariant(value["proof_hash"] == value["proof_id"].rsplit("_", 1)[1])
    invariant(
        payload["source_item_version"] == str(value["source_item_version"])
        and payload["recurrence_revision_id"] == value["recurrence_revision_id"]
    )
    source_revision = db.execute(
        "SELECT prior_recurrence_revision_id FROM recurrence_revisions WHERE recurrence_revision_id=?",
        (value["recurrence_revision_id"],),
    ).fetchone()
    invariant(
        source_revision is not None and source_revision[0] == value["prior_recurrence_revision_id"], "proof predecessor snapshot mismatch"
    )
    actual = [
        r[0]
        for r in db.execute("SELECT lineage_id FROM related_task_proof_lineage WHERE proof_id=? ORDER BY lineage_id", (value["proof_id"],))
    ]
    invariant(actual == payload["lineage_ids"], "incomplete proof lineage references")
    verify_proof(db, root, value["proof_kind"], payload, budget)


def _generation(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    assignment = required(db, "related_task_assignments", value["assignment_id"])
    root = required(db, "related_task_rules", assignment["related_task_rule_id"])
    _id("generation", value, "generation_id", {"assignment_id": value["assignment_id"], "generation_index": str(value["generation_index"])})
    restored_offset = None
    if value["predecessor_generation_id"] is not None:
        prior = required(db, "related_task_generations", value["predecessor_generation_id"])
        invariant(prior["assignment_id"] == value["assignment_id"] and prior["generation_index"] + 1 == value["generation_index"])
        cancellation = row(db, "related_task_source_cancellations", prior["generation_id"])
        invariant(cancellation is not None, "restoration lacks source-only cancellation")
        assert cancellation is not None
        cancelled_state = required(db, "related_task_assignment_revisions", cancellation["assignment_revision_id"])
        cancelled_binding = db.execute(
            "SELECT * FROM relative_temporal_binding_revisions WHERE temporal_binding_revision_id=?",
            (cancelled_state["temporal_binding_revision_id"],),
        ).fetchone()
        invariant(
            cancelled_binding is not None
            and cancelled_binding["temporal_binding_id"] == prior["temporal_binding_id"]
            and cancelled_state["generation_id"] == prior["generation_id"]
            and cancelled_binding["target_item_version"] == cancellation["cancelled_task_version"],
            "restoration cancellation binding mismatch",
        )
        # Restoration preserves the actual individual choice at cancellation,
        # not the rule default or a mutable latest binding pointer.
        restored_offset = str(cancelled_binding["offset_seconds"])
    proof = required(db, "related_task_source_proofs", value["creation_proof_id"])
    config = required(db, "related_task_rule_revisions", value["created_rule_revision_id"])
    invariant(proof["related_task_rule_id"] == root["related_task_rule_id"] == config["related_task_rule_id"])
    task = db.execute("SELECT item_type FROM coordination_items WHERE item_id=?", (value["task_item_id"],)).fetchone()
    detail = db.execute(
        "SELECT rs.recurrence_set_id FROM task_details d "
        "LEFT JOIN recurrence_sets rs ON rs.seed_anchor_id=d.due_anchor_id "
        "WHERE d.item_id=? AND d.version=?",
        (value["task_item_id"], value["created_task_version"]),
    ).fetchone()
    invariant(task is not None and task[0] == "task" and detail is not None and detail[0] is None, "generation must be an ordinary task")
    relation = db.execute("SELECT * FROM coordination_item_relations WHERE relation_id=?", (value["relationship_id"],)).fetchone()
    binding = db.execute("SELECT * FROM relative_temporal_bindings WHERE temporal_binding_id=?", (value["temporal_binding_id"],)).fetchone()
    invariant(
        relation is not None
        and relation["source_item_id"] == value["task_item_id"]
        and relation["target_item_id"] == root["source_item_id"]
        and relation["relation_type"] == "part_of",
        "generation relation mismatch",
    )
    invariant(
        binding is not None
        and binding["target_item_id"] == value["task_item_id"]
        and binding["source_item_id"] == root["source_item_id"]
        and binding["relationship_id"] == value["relationship_id"]
        and binding["binding_mode"] == "follow_source"
        and binding["source_anchor_role"] == "event_start"
        and binding["target_anchor_role"] == "task_due"
        and binding["source_terminal_behavior"] == "require_decision",
        "generation binding mismatch",
    )
    initial = db.execute(
        "SELECT * FROM relative_temporal_binding_revisions WHERE temporal_binding_id=? AND revision_index=1",
        (value["temporal_binding_id"],),
    ).fetchone()
    creation = decode(proof["proof_json"])
    configuration = decode(config["configuration_json"])
    invariant(
        initial is not None
        and initial["source_scope"] == "selected_occurrence"
        and initial["source_occurrence_key"] == creation.get("occurrence_key")
        and initial["source_recurrence_revision_id"] == proof["recurrence_revision_id"]
        and str(initial["source_target_version"]) == creation["source_item_version"]
        and initial["target_item_version"] == value["created_task_version"]
        and initial["offset_basis"] == configuration["offset_basis"]
        and str(initial["offset_seconds"]) == (restored_offset if restored_offset is not None else configuration["offset_seconds"]),
        "generation creation binding mismatch",
    )
    owner = db.execute(
        "SELECT * FROM item_access_owner_revisions WHERE item_access_owner_id=? AND revision=1", (value["item_access_owner_id"],)
    ).fetchone()
    invariant(
        owner is not None
        and owner["item_id"] == value["task_item_id"]
        and _owner(dict(owner)) == decode(config["configuration_json"])["task_owner"]
        and owner["creator_entitlement_subject_id"] is None,
        "generation ownership history mismatch",
    )


def _state(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    state = decode(value["state_json"])
    validate_state(state)
    invariant(payload_hash("state", state)[0] == value["state_hash"], "assignment state hash mismatch")
    fields = {"assignment_id": value["assignment_id"], "change_version": str(value["change_version"]), "state_hash": value["state_hash"]}
    if value["prior_assignment_revision_id"] is not None:
        fields["prior_assignment_revision_id"] = value["prior_assignment_revision_id"]
        previous = required(db, "related_task_assignment_revisions", value["prior_assignment_revision_id"])
        invariant(previous["assignment_id"] == value["assignment_id"] and previous["change_version"] + 1 == value["change_version"])
        invariant(not decode(previous["state_json"])["restoration_veto"] or state["restoration_veto"], "restoration veto cannot be cleared")
    _id("assignment_revision", value, "assignment_revision_id", fields)
    for column in (
        "source_item_version",
        "recurrence_revision_id",
        "task_item_id",
        "task_item_version",
        "generation_id",
        "proof_id",
        "temporal_binding_revision_id",
    ):
        invariant(str(value[column]) == state[column], "extracted state column differs from payload: " + column)
    invariant(value["adopted_rule_revision_id"] == state["adopted_rule_revision_id"])
    assignment = required(db, "related_task_assignments", value["assignment_id"])
    root = required(db, "related_task_rules", assignment["related_task_rule_id"])
    validate_selector(db, value["selector_ref"], state["selector"], state["occurrence_key"], root["recurrence_set_id"])
    proof = required(db, "related_task_source_proofs", value["proof_id"])
    invariant(
        proof["related_task_rule_id"] == root["related_task_rule_id"] and proof["recurrence_revision_id"] == value["recurrence_revision_id"]
    )
    invariant(proof["source_item_version"] == value["source_item_version"], "state source version differs from proof")
    proof_payload = decode(proof["proof_json"])
    if "selector" in proof_payload:
        invariant(proof_payload["selector"] == state["selector"], "state selector differs from proof")
    configuration = required(db, "related_task_rule_revisions", value["adopted_rule_revision_id"])
    invariant(configuration["related_task_rule_id"] == root["related_task_rule_id"], "foreign adopted configuration")
    if "pending_intent_id" in state:
        intent = required(db, "related_task_intents", state["pending_intent_id"])
        invariant(intent["related_task_rule_id"] == root["related_task_rule_id"], "foreign pending state intent")
    gen = required(db, "related_task_generations", value["generation_id"])
    invariant(gen["assignment_id"] == value["assignment_id"] and gen["task_item_id"] == value["task_item_id"])
    binding = db.execute(
        "SELECT * FROM relative_temporal_binding_revisions WHERE temporal_binding_revision_id=?", (value["temporal_binding_revision_id"],)
    ).fetchone()
    invariant(
        binding is not None
        and binding["temporal_binding_id"] == gen["temporal_binding_id"]
        and binding["source_scope"] == "selected_occurrence"
        and binding["offset_basis"] == "elapsed"
        and binding["source_occurrence_key"] == state["occurrence_key"]
        and binding["source_occurrence_selector_ref"] == value["selector_ref"]
        and binding["target_item_version"] == value["task_item_version"],
        "assignment binding witness mismatch",
    )


def _intent(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    payload = decode(value["intent_json"])
    if value["intent_kind"] == "adopt":
        closed(payload, {"configuration_revision_id", "assignment_high_water", "scope"})
        invariant(payload["scope"] == "upcoming_open")
        revision = required(db, "related_task_rule_revisions", payload["configuration_revision_id"])
        invariant(revision["related_task_rule_id"] == value["related_task_rule_id"])
    else:
        closed(payload, {"disposition", "assignment_high_water"}, {"superseded_adoption_intent_id"})
        invariant(payload["disposition"] in {"keep_following", "detach_open", "cancel_open"})
    integer(payload["assignment_high_water"])
    _id(
        "intent",
        value,
        "intent_id",
        {
            "related_task_rule_id": value["related_task_rule_id"],
            "rule_change_version": str(value["rule_change_version"]),
            "intent_kind": value["intent_kind"],
            "intent_payload": payload,
        },
    )


def validate_record(db: sqlite3.Connection, table: str, value: dict[str, Any], budget: ProofBudget) -> None:
    if table == "related_task_rules":
        _rule_root(db, value)
    elif table == "related_task_rule_revisions":
        _configuration(db, value)
    elif table == "related_task_assignments":
        _assignment(db, value)
    elif table == "related_task_source_proofs":
        _proof(db, value, budget)
    elif table == "related_task_generations":
        _generation(db, value)
    elif table == "related_task_assignment_revisions":
        _state(db, value)
    elif table == "related_task_intents":
        _intent(db, value)
    elif table == "related_task_proof_lineage":
        proof = required(db, "related_task_source_proofs", value["proof_id"])
        invariant(value["lineage_id"] in decode(proof["proof_json"])["lineage_ids"])
    elif table == "related_task_selector_reservations":
        root = required(db, "related_task_rules", value["related_task_rule_id"])
        validate_selector(db, value["selector_ref"], decode(value["selector_json"]), value["occurrence_key"], root["recurrence_set_id"])
        proof = required(db, "related_task_source_proofs", value["proof_id"])
        invariant(decode(proof["proof_json"])["selector"] == decode(value["selector_json"]), "reservation proof mismatch")
    elif table == "related_task_source_cancellations":
        gen = required(db, "related_task_generations", value["generation_id"])
        state = required(db, "related_task_assignment_revisions", value["assignment_revision_id"])
        proof = required(db, "related_task_source_proofs", value["proof_id"])
        detail = db.execute(
            "SELECT task_status FROM task_details WHERE item_id=? AND version=?", (gen["task_item_id"], value["cancelled_task_version"])
        ).fetchone()
        invariant(
            detail is not None
            and detail[0] == "cancelled"
            and proof["proof_kind"] in {"excluded", "occurrence_cancelled", "source_cancelled"}
        )
        invariant(
            state["generation_id"] == value["generation_id"]
            and state["proof_id"] == value["proof_id"]
            and state["task_item_version"] == value["cancelled_task_version"]
            and decode(state["state_json"])["disposition"] == "source_cancelled"
        )
    elif table == "related_task_restoration_suppressions":
        _id(
            "suppression",
            value,
            "suppression_id",
            {"assignment_id": value["assignment_id"], "target_generation_id": value["target_generation_id"]},
        )
        assignment = required(db, "related_task_assignments", value["assignment_id"])
        invariant(
            assignment["current_generation_id"] == value["target_generation_id"]
            and row(db, "related_task_source_cancellations", value["target_generation_id"]) is not None,
            "suppression target is not current source-cancelled generation",
        )
    elif table == "related_task_intent_outcomes":
        intent = required(db, "related_task_intents", value["intent_id"])
        assignment = required(db, "related_task_assignments", value["assignment_id"])
        state = required(db, "related_task_assignment_revisions", value["assignment_revision_id"])
        invariant(
            intent["related_task_rule_id"] == assignment["related_task_rule_id"] and state["assignment_id"] == assignment["assignment_id"]
        )
        invariant(assignment["assignment_seq"] <= integer(decode(intent["intent_json"])["assignment_high_water"]))
    elif table == "related_task_rule_progress":
        coverage = decode(value["coverage_json"])
        closed(coverage, {"range_start_utc", "range_end_utc", "source_after", "complete"})
        invariant(type(coverage["complete"]) is bool and coverage["range_start_utc"] < coverage["range_end_utc"])
        root = required(db, "related_task_rules", value["related_task_rule_id"])
        rev = db.execute(
            "SELECT recurrence_set_id FROM recurrence_revisions WHERE recurrence_revision_id=?", (value["recurrence_revision_id"],)
        ).fetchone()
        invariant(rev is not None and rev[0] == root["recurrence_set_id"])
        source = db.execute(
            "SELECT 1 FROM coordination_item_versions WHERE item_id=? AND version=?", (root["source_item_id"], value["source_scan_version"])
        ).fetchone()
        invariant(source is not None, "progress source version is missing")
        if value["pending_intent_id"] is not None:
            invariant(
                required(db, "related_task_intents", value["pending_intent_id"])["related_task_rule_id"] == root["related_task_rule_id"]
            )


def finalize(db: sqlite3.Connection, touched: frozenset[tuple[str, str, str | None]]) -> None:
    budget = ProofBudget(50000, 256)
    for table, first, second in sorted(touched, key=lambda t: (t[0], t[1], t[2] or "")):
        value = row(db, table, first, second)
        if value is not None:
            validate_record(db, table, value, budget)


def read_record(db: sqlite3.Connection, table: str, first: str, second: str | None = None) -> dict[str, Any]:
    value = required(db, table, first, second)
    # Historical decoding is independent of mutable live catalog pointers. Check
    # immutable bytes/hashes without treating old evidence as present actionability.
    for key, item in list(value.items()):
        if key.endswith("_json") or key == "owner_key":
            value[key] = decode(item)
    if table == "related_task_rules":
        invariant(value["owner_key"] == _owner(value), "rule owner snapshot mismatch")
        _id("rule", value, "related_task_rule_id", {"owner": value["owner_key"], "rule_key": value["rule_key"]})
    if table == "related_task_assignments":
        selector = value["initial_selector_json"]
        _id("assignment", value, "assignment_id", {"related_task_rule_id": value["related_task_rule_id"], "initial_selector": selector})
        invariant(
            occurrence_key(selector) == value["initial_occurrence_key"]
            and value["initial_selector_ref"] == "recurrence_target_selector_" + hash_canonical_json(selector)
        )
    if table == "related_task_rule_revisions":
        invariant(payload_hash("configuration", value["configuration_json"])[0] == value["configuration_hash"])
        fields = {
            "related_task_rule_id": value["related_task_rule_id"],
            "revision_index": str(value["revision_index"]),
            "configuration_hash": value["configuration_hash"],
        }
        if value["prior_revision_id"] is not None:
            fields["prior_revision_id"] = value["prior_revision_id"]
        _id("rule_revision", value, "related_task_rule_revision_id", fields)
    if table == "related_task_assignment_revisions":
        validate_state(value["state_json"])
        invariant(payload_hash("state", value["state_json"])[0] == value["state_hash"])
        fields = {
            "assignment_id": value["assignment_id"],
            "change_version": str(value["change_version"]),
            "state_hash": value["state_hash"],
        }
        if value["prior_assignment_revision_id"] is not None:
            fields["prior_assignment_revision_id"] = value["prior_assignment_revision_id"]
        _id("assignment_revision", value, "assignment_revision_id", fields)
    if table == "related_task_source_proofs":
        validate_proof(value["proof_kind"], value["proof_json"])
        _id(
            "proof",
            value,
            "proof_id",
            {
                "related_task_rule_id": value["related_task_rule_id"],
                "proof_kind": value["proof_kind"],
                "proof_payload": value["proof_json"],
            },
        )
        invariant(value["proof_hash"] == value["proof_id"].rsplit("_", 1)[1])
    if table == "related_task_generations":
        _id(
            "generation",
            value,
            "generation_id",
            {"assignment_id": value["assignment_id"], "generation_index": str(value["generation_index"])},
        )
    if table == "related_task_intents":
        _id(
            "intent",
            value,
            "intent_id",
            {
                "related_task_rule_id": value["related_task_rule_id"],
                "rule_change_version": str(value["rule_change_version"]),
                "intent_kind": value["intent_kind"],
                "intent_payload": value["intent_json"],
            },
        )
    return value


def verify_deep(db: sqlite3.Connection) -> None:
    """Explicit candidate/operator verification only; not routine preflight."""
    for table, keys in TABLE_KEYS.items():
        for record in db.execute(f"SELECT * FROM {table} ORDER BY {','.join(keys)}").fetchall():
            validate_record(db, table, dict(record), ProofBudget(50000, 256))
