"""Assignment-aware admission for the ordinary direct/automatic binding path.

The legacy command may maintain work for an exactly current governed child, or
honour explicit manual independence. It cannot perform recurring lifecycle work
without the assignment/cause/intent witnesses owned by recurring reconciliation.
"""

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core.errors import SpineValidationError
from spine.ledger.mutation_effects import require_transaction
from spine.ledger.recurring_task_catalog import intent_view, source_snapshot
from spine.ledger.recurring_task_sources import ProofBudget, verify_proof
from spine.ledger.recurring_tasks import read_record
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_adoption import selected
from spine.services.recurring_task_proofs import payload


def guard_binding_reconcile(
    db: sqlite3.Connection | None, binding: Mapping[str, Any], *, state: str, operator: str | None,
    source: Mapping[str, Any], target: Mapping[str, Any],
) -> None:
    if not isinstance(db, LedgerConnection) or not getattr(db, "_recurring_tasks_enabled", False):
        return
    require_transaction(db)
    generation_row = db.execute("SELECT * FROM related_task_generations WHERE temporal_binding_id=?",
                                (binding["temporal_binding_id"],)).fetchone()
    if generation_row is None:
        return

    def reject() -> None:
        raise SpineValidationError(
            "semantic_conflict:temporal_binding_id",
            "generated binding requires related-task rule reconciliation before ordinary binding maintenance",
        )

    generation = dict(generation_row)
    assignment = read_record(db, "related_task_assignments", generation["assignment_id"])
    if assignment["current_generation_id"] != generation["generation_id"]:
        reject()
    # Existing v1 validation still decides which explicit resolutions are legal.
    # Propagation records the resulting invalidation atomically; current truth
    # then prevents any restoration even before the assignment observer runs.
    if operator in {"detach_at_current_target", "cancel_target"}:
        return
    root = read_record(db, "related_task_rules", assignment["related_task_rule_id"])
    witness = read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
    retirement = intent_view(db, root["retirement_intent_id"])
    owner = db.execute("SELECT item_access_owner_id,current_revision FROM item_access_owners WHERE item_id=?",
                       (generation["task_item_id"],)).fetchone()
    if (
        state != "current" or witness["disposition"] != "governed" or witness["restoration_veto"]
        or source["status"] != "active" or source["detail"]["event_status"] != "scheduled"
        or target["status"] != "active" or target["detail"]["task_status"] != "open"
        or witness["task_item_version"] != str(target["current_version"])
        or witness["temporal_binding_revision_id"] != binding["latest_revision"]["temporal_binding_revision_id"]
        or owner is None or owner[0] != generation["item_access_owner_id"] or owner[1] != 1
        or (root["status"] != "active" and (retirement is None or retirement["disposition"] != "keep_following"))
    ):
        reject()
    budget = ProofBudget()
    snapshot = source_snapshot(db, root)
    if any(witness[key] != snapshot[key] for key in ("source_item_version", "recurrence_revision_id")):
        reject()
    try:
        if selected(db, root["related_task_rule_id"], assignment, budget=budget) is not None:
            reject()
        # Fresh positive membership, not an unbounded history scan and never
        # an inference from absence. v1 current-state resolution also checked
        # current actionability, relation and resolved due/anchor equality.
        verify_proof(db, root, "identity", payload(snapshot, witness["selector"]), budget)
    except SpineValidationError:
        reject()
