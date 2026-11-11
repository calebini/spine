"""Append-only assignment witnesses; the caller owns the transaction and receipt."""

from __future__ import annotations

import copy
from typing import Any

from spine.core.hashing import hash_canonical_json
from spine.core.recurring_task_runtime import fail
from spine.core.recurring_tasks import derive, payload_hash
from spine.ledger.recurring_tasks import compare_and_swap, insert_record, read_record, row


def append_state(db: Any, assignment: dict[str, Any], state: dict[str, Any], request: dict[str, Any], now: str) -> str:
    """Append exactly the next state, retaining the current generation unless changed."""
    version = assignment["change_version"] + 1
    digest = payload_hash("state", state)[0]
    identity = derive(
        "assignment_revision",
        {
            "assignment_id": assignment["assignment_id"],
            "change_version": str(version),
            "prior_assignment_revision_id": assignment["current_assignment_revision_id"],
            "state_hash": digest,
        },
    )[0]
    columns = {
        key: int(state[key]) if key in {"task_item_version", "source_item_version"} else state[key]
        for key in (
            "source_item_version",
            "recurrence_revision_id",
            "task_item_id",
            "task_item_version",
            "adopted_rule_revision_id",
            "generation_id",
            "temporal_binding_revision_id",
            "proof_id",
        )
    }
    insert_record(
        db,
        "related_task_assignment_revisions",
        {
            "assignment_revision_id": identity,
            "assignment_id": assignment["assignment_id"],
            "change_version": version,
            "prior_assignment_revision_id": assignment["current_assignment_revision_id"],
            "state_json": state,
            "state_hash": digest,
            "selector_ref": "recurrence_target_selector_" + hash_canonical_json(state["selector"]),
            **columns,
            "command_id": request["command_id"],
            "created_at_utc": now,
        },
    )
    compare_and_swap(
        db,
        "related_task_assignments",
        assignment["assignment_id"],
        assignment["change_version"],
        {
            "current_assignment_revision_id": identity,
            "current_generation_id": state["generation_id"],
        },
    )
    return identity


def suppress(db: Any, request: dict[str, Any], root: dict[str, Any], now: str) -> tuple[dict[str, Any], str, bool]:
    from spine.ledger.recurring_task_catalog import advance_catalog, lookup
    from spine.services.recurring_task_reads import assignment_view

    assignment = lookup(db, "related_task_assignments", request["assignment_id"], "assignment_id")
    if assignment["related_task_rule_id"] != root["related_task_rule_id"]:
        fail("referenced_row_not_found", "assignment_id")
    for field, actual in (
        ("assignment_change_version", str(assignment["change_version"])),
        ("target_generation_id", assignment["current_generation_id"]),
    ):
        given = request["expected"][field] if field == "assignment_change_version" else request[field]
        if given != actual:
            fail("stale_version", "expected." + field if field == "assignment_change_version" else field)
    generation = read_record(db, "related_task_generations", assignment["current_generation_id"])
    if request["target_task_item_id"] != generation["task_item_id"]:
        fail("stale_version", "target_task_item_id")
    task = db.execute(
        "SELECT i.current_version,d.task_status FROM coordination_items i JOIN task_details d "
        "ON d.item_id=i.item_id AND d.version=i.current_version WHERE i.item_id=?",
        (generation["task_item_id"],),
    ).fetchone()
    cause = row(db, "related_task_source_cancellations", generation["generation_id"])
    successor = db.execute(
        "SELECT 1 FROM related_task_generations WHERE predecessor_generation_id=?", (generation["generation_id"],)
    ).fetchone()
    if (
        cause is None
        or successor
        or task is None
        or task["task_status"] != "cancelled"
        or task["current_version"] != cause["cancelled_task_version"]
    ):
        fail("semantic_conflict", "target_generation_id", "suppression requires the latest solely source-cancelled task")
    identity = derive("suppression", {"assignment_id": assignment["assignment_id"], "target_generation_id": generation["generation_id"]})[0]
    existing = row(db, "related_task_restoration_suppressions", identity)
    if existing is None:
        state = copy.deepcopy(
            read_record(db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
        )
        if state["restoration_veto"] or state["disposition"] != "source_cancelled":
            fail("semantic_conflict", "target_generation_id")
        insert_record(
            db,
            "related_task_restoration_suppressions",
            {
                "suppression_id": identity,
                "assignment_id": assignment["assignment_id"],
                "target_generation_id": generation["generation_id"],
                "actor_subject_id": request["actor_subject_id"],
                "command_id": request["command_id"],
                "suppressed_at_utc": now,
            },
        )
        state.update(disposition="suppressed", restoration_veto=True, reason="restoration_suppressed")
        append_state(db, assignment, state, request, now)
        compare_and_swap(
            db,
            "related_task_rules",
            root["related_task_rule_id"],
            root["change_version"],
            {"current_revision_id": root["current_revision_id"]},
        )
        advance_catalog(db)
    projection = assignment_view(db, read_record(db, "related_task_assignments", assignment["assignment_id"]), root)
    return (
        {
            "assignment": projection,
            "suppression": projection["suppression"],
            "successor_generation_id": None,
            "delivery": "not_attempted_by_command",
        },
        "assignment_restoration_suppressed" if existing is None else "assignment_suppress_noop",
        existing is None,
    )
