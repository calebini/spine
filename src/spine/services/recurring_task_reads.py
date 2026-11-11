"""Read-only stored witnesses separated from observed item/source truth."""

from __future__ import annotations

from typing import Any

from spine.core.hashing import command_derived_id
from spine.ledger.recurring_tasks import read_record


def assignment_view(db: Any, assignment: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    from spine.ledger.recurring_task_catalog import pending_adoption, source_snapshot, stored_projection

    state_row = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])
    state = state_row["state_json"]
    gen = read_record(db, "related_task_generations", assignment["current_generation_id"])
    observed = db.execute(
        "SELECT i.current_version,d.task_status FROM coordination_items i "
        "JOIN task_details d ON d.item_id=i.item_id AND d.version=i.current_version WHERE i.item_id=?",
        (gen["task_item_id"],),
    ).fetchone()
    source = source_snapshot(db, root)
    owner = db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (gen["task_item_id"],)).fetchone()
    if owner is None or observed is None:
        from spine.core.recurring_task_runtime import fail

        fail("environment_failure", "assignment")
    successor = db.execute(
        "SELECT generation_id FROM related_task_generations WHERE predecessor_generation_id=?", (gen["generation_id"],)
    ).fetchone()
    cancellation = db.execute(
        "SELECT generation_id FROM related_task_source_cancellations WHERE generation_id=?", (gen["generation_id"],)
    ).fetchone()
    cancellation = stored_projection(db, "related_task_source_cancellations", gen["generation_id"]) if cancellation else None
    suppression = db.execute(
        "SELECT suppression_id FROM related_task_restoration_suppressions WHERE assignment_id=?", (assignment["assignment_id"],)
    ).fetchone()
    if suppression:
        suppression = stored_projection(db, "related_task_restoration_suppressions", suppression[0])
        suppression["command_receipt_id"] = command_derived_id(
            prefix="command_receipt",
            command="schedule.related_task_rule.assignment.suppress",
            command_id=suppression["command_id"],
            row_role="command_receipt",
            request_path="/command_receipt",
        )
    else:
        suppression = None
    proof = read_record(db, "related_task_source_proofs", state["proof_id"])
    proof_snapshot = {
        k: proof["proof_json"][k]
        for k in ("source_item_id", "source_item_version", "recurrence_set_id", "recurrence_revision_id", "normalized_recurrence_set_hash")
    }
    adoption = pending_adoption(db, root["related_task_rule_id"])
    desired = (
        adoption["configuration_revision_id"]
        if adoption and assignment["assignment_seq"] <= int(adoption["assignment_high_water"])
        else None
    )
    freshness = "decision_required" if state["disposition"] == "decision_required" else "current"
    if freshness == "current" and (source != proof_snapshot or observed["current_version"] != int(state["task_item_version"])):
        freshness = "needs_reconcile"
    if freshness == "current" and desired is not None and desired != state["adopted_rule_revision_id"]:
        freshness = "needs_reconcile"
    return {
        "assignment_id": assignment["assignment_id"],
        "assignment_seq": str(assignment["assignment_seq"]),
        "change_version": str(assignment["change_version"]),
        "assignment_revision_id": state_row["assignment_revision_id"],
        "initial_selector": assignment["initial_selector_json"],
        "current_selector": state["selector"],
        "occurrence_key": state["occurrence_key"],
        "generation_id": gen["generation_id"],
        "generation_index": str(gen["generation_index"]),
        "task_item_id": gen["task_item_id"],
        "task_item_version": state["task_item_version"],
        "task_status": observed["task_status"],
        "temporal_binding_id": gen["temporal_binding_id"],
        "temporal_binding_revision_id": state["temporal_binding_revision_id"],
        "relationship_id": gen["relationship_id"],
        "task_owner": {k: owner[k] for k in ("owner_kind", "owner_subject_id", "owner_group_id") if owner[k] is not None},
        "item_access_owner_id": owner["item_access_owner_id"],
        "item_access_owner_revision": str(owner["current_revision"]),
        "adopted_rule_revision_id": state["adopted_rule_revision_id"],
        "desired_rule_revision_id": desired,
        "disposition": state["disposition"],
        "reason": state["reason"],
        "restoration_veto": state["restoration_veto"],
        "suppression": suppression,
        "source_proof_id": state["proof_id"],
        "source_snapshot": proof_snapshot,
        "predecessor_generation_id": gen["predecessor_generation_id"],
        "successor_generation_id": successor[0] if successor else None,
        "source_cancellation": cancellation,
        "freshness": freshness,
        "observed_source_item_version": source["source_item_version"],
        "observed_recurrence_revision_id": source["recurrence_revision_id"],
        "observed_task_item_version": str(observed["current_version"]),
    }
