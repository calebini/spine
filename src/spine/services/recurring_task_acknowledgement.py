"""Discharge only a proven contiguous dirty prefix inside the page transaction."""

from typing import Any

from spine.ledger.recurring_task_catalog import intent_view, pending_adoption
from spine.ledger.recurring_task_invalidation import acknowledge
from spine.ledger.recurring_tasks import read_record
from spine.ledger.transactions import LedgerConnection


def acknowledge_page(
    db: LedgerConnection, rule_id: str, dirty: dict[str, Any] | None, *,
    original: dict[str, Any], position: dict[str, Any], results: list[dict[str, Any]],
    processed_assignments: int, existing_more: bool, source_more: bool,
    source_prefix_unproved: bool,
) -> bool:
    """Never infer earlier-page success from a signed continuation alone.

    The queue's sequence certifies a contiguous successful assignment prefix.
    Blocked assignments stop that prefix; source gaps keep the root queued.
    A canonical mutation within this page leaves a newer invalidation intact.
    All writes join the receipt-sizing savepoint and outer command rollback.
    """
    action, prefix = coverage_action(db, rule_id, dirty, original=original, position=position, results=results,
                                     processed_assignments=processed_assignments, existing_more=existing_more,
                                     source_more=source_more, source_prefix_unproved=source_prefix_unproved)
    if not action or dirty is None:
        return False
    return acknowledge(db, rule_id, dirty["dirty_generation"], assignment_after_seq=prefix)


def coverage_action(
    db: LedgerConnection, rule_id: str, dirty: dict[str, Any] | None, *,
    original: dict[str, Any], position: dict[str, Any], results: list[dict[str, Any]],
    processed_assignments: int, existing_more: bool, source_more: bool, source_prefix_unproved: bool,
) -> tuple[bool, int | None]:
    if dirty is None or int(original["assignment_after_seq"]) > dirty["assignment_after_seq"]:
        return False, None
    prefix = int(original["assignment_after_seq"])
    for result in results[:processed_assignments]:
        if result["outcome"] == "decision_required":
            break
        prefix += 1
    blocked = any(result["outcome"] == "decision_required" for result in results)
    root = read_record(db, "related_task_rules", rule_id)
    retirement = intent_view(db, root["retirement_intent_id"])
    pending = pending_adoption(db, rule_id) is not None or (retirement is not None and retirement["status"] == "pending")
    complete = not (existing_more or source_more or blocked or source_prefix_unproved or pending)
    if complete and prefix == int(position["assignment_after_seq"]):
        return True, None
    return prefix > dirty["assignment_after_seq"], prefix
