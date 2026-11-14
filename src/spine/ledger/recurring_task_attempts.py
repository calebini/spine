"""Current-truth admission at the durable attempt boundary, never outcome recording."""

import sqlite3
from typing import Any, cast

from spine.core.errors import SpineValidationError
from spine.ledger.mutation_effects import require_transaction
from spine.ledger.recurring_task_catalog import intent_view, source_snapshot
from spine.ledger.recurring_task_intent_reads import selected
from spine.ledger.recurring_task_sources import ProofBudget, verify_proof
from spine.ledger.recurring_tasks import read_record
from spine.ledger.temporal_bindings import load_temporal_binding
from spine.ledger.transactions import LedgerConnection


def assert_attempt_current(db: sqlite3.Connection, work_instance_id: str) -> None:
    """An old queued/leased/retry row is not authority to send a generated task.

    All reads join the caller's attempt INSERT transaction. No repair, queue
    acknowledgement, policy mutation, cancellation or history rewrite occurs.
    """
    if not isinstance(db, LedgerConnection) or not getattr(db, "_recurring_tasks_enabled", False):
        return
    require_transaction(db)
    generation_row = db.execute(
        "SELECT g.* FROM work_instances w JOIN related_task_generations g ON g.task_item_id=w.item_id "
        "WHERE w.work_instance_id=?", (work_instance_id,),
    ).fetchone()
    if generation_row is None:
        return

    def reject() -> None:
        raise SpineValidationError("stale_work_instance", "generated task requires current recurring assignment evidence")

    generation = dict(generation_row)
    assignment = read_record(db, "related_task_assignments", generation["assignment_id"])
    state = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
    if assignment["current_generation_id"] != generation["generation_id"]:
        reject()
    binding = load_temporal_binding(db, generation["temporal_binding_id"])
    revision = cast(dict[str, Any], binding["latest_revision"])
    # Only an observed, explicitly independent child leaves family governance.
    # Ordinary work/policy freshness is still checked below, not bypassed.
    independent = state["disposition"] == "detached" and state["restoration_veto"] and binding["binding_status"] == "retired"
    if not independent:
        root = read_record(db, "related_task_rules", assignment["related_task_rule_id"])
        retirement = intent_view(db, root["retirement_intent_id"])
        owner = db.execute("SELECT item_access_owner_id,current_revision FROM item_access_owners WHERE item_id=?",
                           (generation["task_item_id"],)).fetchone()
        target = db.execute(
            "SELECT i.current_version,i.status,t.task_status,t.due_anchor_id FROM coordination_items i "
            "JOIN task_details t ON t.item_id=i.item_id AND t.version=i.current_version WHERE i.item_id=?",
            (generation["task_item_id"],),
        ).fetchone()
        relation = db.execute(
            "SELECT relation_status,relation_type,source_item_id,target_item_id FROM coordination_item_relations WHERE relation_id=?",
            (generation["relationship_id"],),
        ).fetchone()
        source = db.execute(
            "SELECT i.status,e.event_status FROM coordination_items i JOIN event_details e "
            "ON e.item_id=i.item_id AND e.version=i.current_version WHERE i.item_id=?", (root["source_item_id"],),
        ).fetchone()
        if (
            state["disposition"] != "governed" or state["restoration_veto"]
            or binding["binding_status"] != "active" or binding["binding_mode"] != "follow_source"
            or revision["temporal_binding_revision_id"] != state["temporal_binding_revision_id"]
            or target is None or target["status"] != "active" or target["task_status"] != "open"
            or str(target["current_version"]) != state["task_item_version"]
            or target["due_anchor_id"] != revision["target_anchor_id"]
            or owner is None or owner[0] != generation["item_access_owner_id"] or owner[1] != 1
            or relation is None or tuple(relation) != ("active", "part_of", generation["task_item_id"], root["source_item_id"])
            or source is None or tuple(source) != ("active", "scheduled")
            or (root["status"] != "active" and (retirement is None or retirement["disposition"] != "keep_following"))
        ):
            reject()
        try:
            budget = ProofBudget()
            snapshot = source_snapshot(db, root)
            if any(state[k] != snapshot[k] for k in ("source_item_version", "recurrence_revision_id")):
                reject()
            if selected(db, root["related_task_rule_id"], assignment, budget=budget) is not None:
                reject()
            verify_proof(db, root, "identity", {
                **snapshot, "lineage_ids": [], "selector": state["selector"], "occurrence_key": state["occurrence_key"],
            }, budget)
            # Membership and actionability are separate. Both are required.
            for table, condition in (("recurrence_exdates", ""), ("recurrence_overrides", " AND lifecycle='cancelled'")):
                if db.execute(
                    f"SELECT 1 FROM {table} WHERE recurrence_revision_id=? "
                    f"AND target_occurrence_key=? AND status='active'{condition} LIMIT 1",
                    (snapshot["recurrence_revision_id"], state["occurrence_key"]),
                ).fetchone():
                    reject()
        except SpineValidationError:
            reject()
    from spine.ledger.work import assert_work_instance_not_stale

    assert_work_instance_not_stale(db, work_instance_id)
