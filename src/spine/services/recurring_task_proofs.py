"""Construct positive source evidence from stored recurrence facts, never range absence."""

from __future__ import annotations

from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.recurring_tasks import derive, occurrence_key
from spine.ledger.recurring_task_sources import ProofBudget, candidate, continuity, revision, verify_proof
from spine.ledger.recurring_tasks import insert_record, row


def hops(db: Any, before: str, after: str, selector: dict[str, Any], budget: ProofBudget) -> list[dict[str, Any]]:
    path, current = [], after
    while current != before:
        budget.spend(hop=True)
        header = revision(db, current, budget)
        path.append(header)
        current = header["prior_recurrence_revision_id"]
        if current is None:
            raise SpineValidationError("source_continuity_unresolved", "enrollment is not an ancestor")
    result, current_selector = [], selector
    for header in reversed(path):
        matched = candidate(db, header["recurrence_revision_id"], selector["scheduled_fact"], budget)
        if matched is None:
            raise SpineValidationError("source_continuity_unresolved", "original slot has no proved successor")
        lines = db.execute(
            "SELECT lineage_id FROM recurrence_lineage WHERE new_recurrence_revision_id=? "
            "AND prior_recurrence_revision_id=? ORDER BY lineage_id LIMIT ?",
            (header["recurrence_revision_id"], header["prior_recurrence_revision_id"], budget.steps + 1),
        ).fetchall()
        budget.spend(len(lines))
        hop = {
            "prior_revision_id": header["prior_recurrence_revision_id"],
            "new_revision_id": header["recurrence_revision_id"],
            "prior_selector": current_selector,
            "selector": matched["selector"],
            "lineage_ids": [r[0] for r in lines],
        }
        continuity(db, hop["prior_revision_id"], current_selector, [hop], budget)
        result.append(hop)
        current_selector = matched["selector"]
    return result


def payload(snapshot: dict[str, Any], selector: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    result = {**snapshot, "lineage_ids": []}
    if selector is not None:
        result.update(selector=selector, occurrence_key=occurrence_key(selector))
    result.update(extra)
    return result


def persist(db: Any, root: dict[str, Any], kind: str, value: dict[str, Any], request: dict[str, Any], now: str, budget: ProofBudget) -> str:
    verify_proof(db, root, kind, value, budget)
    identity = derive("proof", {"related_task_rule_id": root["related_task_rule_id"], "proof_kind": kind, "proof_payload": value})[0]
    existing = row(db, "related_task_source_proofs", identity)
    if existing is None:
        header = revision(db, value["recurrence_revision_id"], budget)
        insert_record(
            db,
            "related_task_source_proofs",
            {
                "proof_id": identity,
                "related_task_rule_id": root["related_task_rule_id"],
                "proof_kind": kind,
                "source_item_version": int(value["source_item_version"]),
                "recurrence_revision_id": value["recurrence_revision_id"],
                "prior_recurrence_revision_id": header["prior_recurrence_revision_id"],
                "proof_json": value,
                "proof_hash": identity.rsplit("_", 1)[1],
                "created_by_command_id": request["command_id"],
                "created_at_utc": now,
            },
        )
        for line in value["lineage_ids"]:
            insert_record(db, "related_task_proof_lineage", {"proof_id": identity, "lineage_id": line})
    return identity


def initial(
    db: Any, root: dict[str, Any], snapshot: dict[str, Any], selector: dict[str, Any], budget: ProofBudget
) -> tuple[str, dict[str, Any]]:
    if snapshot["recurrence_revision_id"] == root["enrolled_recurrence_revision_id"]:
        return "enrollment", payload(snapshot, selector, enrolled_recurrence_revision_id=root["enrolled_recurrence_revision_id"])
    basis = candidate(db, root["enrolled_recurrence_revision_id"], selector["scheduled_fact"], budget)
    if basis is not None:
        path = hops(db, root["enrolled_recurrence_revision_id"], snapshot["recurrence_revision_id"], basis["selector"], budget)
        if not path or path[-1]["selector"] != selector:
            raise SpineValidationError("source_continuity_unresolved", "candidate differs from verified lineage")
        source_kind = "rule" if basis["rules"] else "rdate"
        component = basis["selector"]["source_rule_selectors" if source_kind == "rule" else "source_rdate_selectors"][0]
        return "component_candidate", payload(
            snapshot,
            selector,
            basis_revision_id=root["enrolled_recurrence_revision_id"],
            component_selector={"source_kind": source_kind, "selector": component},
            hops=path,
            lineage_ids=sorted({line for hop in path for line in hop["lineage_ids"]}),
        )
    current = candidate(db, snapshot["recurrence_revision_id"], selector["scheduled_fact"], budget)
    if current is not None and current["rdates"] and not current["rules"]:
        header = current["header"]
        ids = db.execute(
            "SELECT lineage_id FROM recurrence_lineage WHERE new_recurrence_revision_id=? AND new_child_id=? ORDER BY lineage_id LIMIT ?",
            (header["recurrence_revision_id"], current["rdates"][0][0]["rdate_id"], budget.steps + 1),
        ).fetchall()
        budget.spend(len(ids))
        return "new_rdate", payload(
            snapshot,
            selector,
            rdate_id=current["rdates"][0][0]["rdate_id"],
            prior_recurrence_revision_id=header["prior_recurrence_revision_id"],
            lineage_ids=[r[0] for r in ids],
        )
    raise SpineValidationError("source_continuity_unresolved", "candidate novelty is not proved")


def existing(
    db: Any, root: dict[str, Any], snapshot: dict[str, Any], state: dict[str, Any], budget: ProofBudget
) -> tuple[str, dict[str, Any]]:
    current = candidate(db, snapshot["recurrence_revision_id"], state["selector"]["scheduled_fact"], budget)
    if current is not None and current["selector"] == state["selector"]:
        return "identity", payload(snapshot, current["selector"])
    path = hops(db, state["recurrence_revision_id"], snapshot["recurrence_revision_id"], state["selector"], budget)
    if not path:
        raise SpineValidationError("source_continuity_unresolved", "no current membership")
    return "carry_forward", payload(
        snapshot,
        path[-1]["selector"],
        prior_proof_id=state["proof_id"],
        prior_selector=state["selector"],
        hops=path,
        lineage_ids=sorted({line for hop in path for line in hop["lineage_ids"]}),
    )
