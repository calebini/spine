"""Read-only bounded selection of an assignment's still-pending adoption."""

from typing import Any

from spine.ledger.recurring_task_catalog import pending_adoption
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.recurring_tasks import read_record, row
from spine.ledger.transactions import LedgerConnection


def selected(db: LedgerConnection, rule_id: str, assignment: dict[str, Any], *, budget: ProofBudget) -> dict[str, Any] | None:
    intent = pending_adoption(db, rule_id)
    if intent is None or assignment["assignment_seq"] > int(intent["assignment_high_water"]):
        return None
    prior = row(db, "related_task_intent_outcomes", intent["intent_id"], assignment["assignment_id"])
    if prior is None:
        return intent
    if prior["outcome"] == "conflict" and not resolved(db, assignment, intent, budget=budget):
        return intent
    return None


def resolved(db: LedgerConnection, assignment: dict[str, Any], intent: dict[str, Any], *, budget: ProofBudget) -> bool:
    """Follow exact immutable predecessors, charging each read; never scan history."""
    identity = assignment["current_assignment_revision_id"]
    while identity is not None:
        budget.spend()
        revision = read_record(db, "related_task_assignment_revisions", identity)
        state = revision["state_json"]
        if state.get("pending_intent_id") != intent["intent_id"]:
            return False
        if (
            state["adopted_rule_revision_id"] == intent["configuration_revision_id"]
            or state["restoration_veto"]
            or state["disposition"] == "source_cancelled"
            or state["reason"] == "due_not_future"
        ):
            return True
        identity = revision["prior_assignment_revision_id"]
    return False
