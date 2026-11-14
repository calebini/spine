"""Three-way managed-field comparison and immutable bounded intent outcomes."""

from __future__ import annotations

import copy
from typing import Any

from spine.ledger.notification_profiles import current_assignment
from spine.ledger.recurring_task_intent_reads import resolved as resolved
from spine.ledger.recurring_task_intent_reads import selected as selected
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.recurring_tasks import insert_record, read_record, row
from spine.ledger.rendering_definitions import load_presentation
from spine.ledger.transactions import LedgerConnection
from spine.services import recurring_task_children as children
from spine.services.primary_locations import canonical_location_facts
from spine.services.recurring_task_operations import ChildInvocation


def fields(config: dict[str, Any]) -> dict[str, Any]:
    item = config["task_template"]["item"]
    return {
        **{k: item[k] for k in ("title", "summary", "source_ref", "archetype", "primary_location")},
        "priority": item["task_detail"]["priority"],
        "assignees": config["task_template"]["people"]["assignees"],
        "offset_seconds": config["offset_seconds"],
        "materialization": config["materialization"],
        "reminders": [config["notification_plan"], config["delivery"]],
    }


def policy_matches(db: Any, current: dict[str, Any], generation: dict[str, Any], config: dict[str, Any]) -> bool:
    expected = {e["policy_key"]: e for e in (config["notification_plan"] or {}).get("resolved", {}).get("effective_templates", [])}
    actual = children.mappings(db, "comparison-only", generation, config)
    if {p["policy_key"] for p in actual} != set(expected):
        return False
    policies = {p["notification_policy_id"]: p for p in current["notification_policies"]}
    route = (config["delivery"] or {}).get("resolved", {})
    for mapping in actual:
        policy, selected = policies[mapping["notification_policy_id"]], expected[mapping["policy_key"]]
        if (
            policy["schedule"] != selected["template"]["schedule"]
            or policy["late_handling"] != selected["template"]["late_handling"]
            or policy["delivery_target_id"] != route["delivery_target_id"]
            or load_presentation(db, policy["notification_policy_id"]) != selected["presentation"]
        ):
            return False
    return True


def comparison(
    db: LedgerConnection,
    generation: dict[str, Any],
    state: dict[str, Any],
    current: dict[str, Any],
    binding: dict[str, Any],
    desired: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """D=B first is deliberate: an unrelated update preserves individual exceptions."""
    base = fields(state["managed_baseline"])
    wanted = fields(desired)
    observed = {
        **{k: current["version"][k] for k in ("title", "summary", "source_ref")},
        "priority": current["detail"]["priority"],
        "assignees": sorted({r["subject_id"] for r in current["subject_roles"] if r["role"] == "assignee" and r["status"] == "active"}),
        "offset_seconds": binding["latest_revision"]["offset_seconds"],
        "materialization": base["materialization"],
    }
    archetype = current_assignment(db, item_id=generation["task_item_id"], item_version=int(current["current_version"]))
    observed["archetype"] = (
        None
        if archetype is None
        else {
            "item_archetype_id": archetype["item_archetype_id"],
            "item_archetype_revision_id": archetype["item_archetype_revision_id"],
            "revision_resolution": "exact",
            "selection_source": archetype["selection_source"],
            **({"source_ref": archetype["source_ref"]} if archetype["source_ref"] is not None else {}),
        }
    )
    location = next((v for v in current["locations"] if v["role"] == "primary"), None)
    observed["primary_location"] = None if location is None else {"mode": "reference", "location_id": location["location_id"]}
    for expected in (base["primary_location"], wanted["primary_location"]):
        if expected is not None and expected["mode"] == "create" and location is not None:
            normalized = {"mode": "create", **canonical_location_facts(location)}
            if normalized == expected:
                observed["primary_location"] = copy.deepcopy(expected)
    observed["reminders"] = (
        base["reminders"]
        if policy_matches(db, current, generation, state["managed_baseline"])
        else (wanted["reminders"] if policy_matches(db, current, generation, desired) else {"independent_change": True})
    )
    patch = {}
    for key, value in wanted.items():
        if value == base[key]:
            continue
        if observed[key] != base[key] and observed[key] != value:
            return {}, True
        if observed[key] != value:
            patch[key] = copy.deepcopy(value)
    return patch, False


def outcome(db: LedgerConnection, invocation: ChildInvocation, intent: dict[str, Any], assignment_id: str,
            state_id: str, result: str, reason: str) -> bool:
    """Retain the first conflict fact; subsequent resolution is current-state evidence."""
    invocation.require_transaction(db)
    if row(db, "related_task_intent_outcomes", intent["intent_id"], assignment_id) is None:
        insert_record(
            db,
            "related_task_intent_outcomes",
            {
                "intent_id": intent["intent_id"],
                "assignment_id": assignment_id,
                "assignment_revision_id": state_id,
                "outcome": result,
                "reason": reason,
                "command_id": invocation.command_id,
                "created_at_utc": invocation.now,
            },
        )
        return True
    return False


def missing_outcomes(db: LedgerConnection, rule_id: str, intent: dict[str, Any]) -> bool:
    """Indexed existence seek; do not count the root or infer completion from totals."""
    return db.execute(
        "SELECT 1 FROM related_task_assignments a LEFT JOIN related_task_intent_outcomes o "
        "ON o.assignment_id=a.assignment_id AND o.intent_id=? WHERE a.related_task_rule_id=? AND a.assignment_seq<=? "
        "AND o.assignment_id IS NULL LIMIT 1",
        (intent["intent_id"], rule_id, int(intent["assignment_high_water"])),
    ).fetchone() is not None


def coverage_status(db: LedgerConnection, rule_id: str, intent: dict[str, Any] | None) -> str:
    """Called after bounded completion proof; pending conflicts are not more rows."""
    if intent is None:
        return "not_applicable"
    if intent["status"] == "complete":
        return "complete"
    return "partial" if missing_outcomes(db, rule_id, intent) else "decision_required"


def complete(db: LedgerConnection, invocation: ChildInvocation, *, rule_id: str,
             budget: ProofBudget, intent: dict[str, Any]) -> bool:
    """Indexed missing-outcome seek, then bounded conflict-resolution evidence."""
    invocation.require_transaction(db)
    if not can_complete(db, rule_id, intent, budget):
        return False
    db.execute("UPDATE related_task_intents SET status='complete' WHERE intent_id=? AND status='pending'", (intent["intent_id"],))
    return True


def can_complete(db: LedgerConnection, rule_id: str, intent: dict[str, Any], budget: ProofBudget) -> bool:
    if missing_outcomes(db, rule_id, intent):
        return False
    conflicts = db.execute(
        "SELECT assignment_id FROM related_task_intent_outcomes WHERE intent_id=? AND outcome='conflict' LIMIT ?",
        (intent["intent_id"], budget.steps + 1),
    ).fetchall()
    budget.spend(len(conflicts))
    for conflict in conflicts:
        assignment = read_record(db, "related_task_assignments", conflict["assignment_id"])
        if not resolved(db, assignment, intent, budget=budget):
            return False
    return True
