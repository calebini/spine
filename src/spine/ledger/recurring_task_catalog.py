"""Recurring catalog persistence and exact stored read projections.

These helpers retain family-specific history decoding and errors, not admission.
Catalog advancement joins the caller transaction; no commits or receipts are made.
"""

from __future__ import annotations

from typing import Any

from spine.core.recurring_task_runtime import fail
from spine.ledger.recurrence import load_current_recurrence_header
from spine.ledger.recurring_tasks import read_record


def catalog(db: Any) -> str:
    return str(db.execute("SELECT catalog_generation FROM related_task_catalog_state WHERE singleton_id=1").fetchone()[0])


def advance_catalog(db: Any) -> None:
    if db.mutation_state.recurring.catalog_advanced:
        return
    db.execute("UPDATE related_task_catalog_state SET catalog_generation=catalog_generation+1 WHERE singleton_id=1")
    db.mutation_state.recurring.catalog_advanced = True


def lookup(db: Any, table: str, key: str, field: str) -> dict[str, Any]:
    from spine.ledger.recurring_tasks import row

    value = row(db, table, key)
    if value is None:
        fail("referenced_row_not_found", field)
    return read_record(db, table, key)


def source_snapshot(db: Any, root: dict[str, Any]) -> dict[str, Any]:
    item = db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (root["source_item_id"],)).fetchone()
    header = load_current_recurrence_header(db, item_id=root["source_item_id"])
    if item is None or header is None:
        fail("environment_failure", "source")
    return {
        "source_item_id": root["source_item_id"],
        "source_item_version": str(item[0]),
        "recurrence_set_id": header["recurrence_set_id"],
        "recurrence_revision_id": header["recurrence_revision_id"],
        "normalized_recurrence_set_hash": header["normalized_recurrence_set_hash"],
    }


def intent_view(db: Any, identity: str | None) -> dict[str, Any] | None:
    if identity is None:
        return None
    value = read_record(db, "related_task_intents", identity)
    payload = value["intent_json"]
    return {
        "intent_id": identity,
        "status": value["status"],
        "kind": value["intent_kind"],
        "assignment_high_water": payload["assignment_high_water"],
        "scope": payload.get("scope"),
        "disposition": payload.get("disposition"),
        "configuration_revision_id": payload.get("configuration_revision_id"),
    }


def pending_adoption(db: Any, root_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT intent_id FROM related_task_intents WHERE related_task_rule_id=? AND intent_kind='adopt' AND status='pending'", (root_id,)
    ).fetchone()
    return intent_view(db, row[0]) if row else None


def stored_projection(db: Any, table: str, identity: str) -> dict[str, Any]:
    value = read_record(db, table, identity)
    return {k: str(v) if type(v) is int else v for k, v in value.items()}


def rule_view(db: Any, root: dict[str, Any], *, summary: bool = False) -> dict[str, Any]:
    config = read_record(db, "related_task_rule_revisions", root["current_revision_id"])
    retired = intent_view(db, root["retirement_intent_id"])
    progress = db.execute(
        "SELECT 1 FROM related_task_rule_progress WHERE related_task_rule_id=?", (root["related_task_rule_id"],)
    ).fetchone()
    progress = stored_projection(db, "related_task_rule_progress", root["related_task_rule_id"]) if progress else None
    if progress:
        progress.pop("related_task_rule_id")
    result = {
        "related_task_rule_id": root["related_task_rule_id"],
        "owner": root["owner_key"],
        "rule_key": root["rule_key"],
        "source_item_id": root["source_item_id"],
        "recurrence_set_id": root["recurrence_set_id"],
        "status": root["status"],
        "rule_revision_id": root["current_revision_id"],
        "change_version": str(root["change_version"]),
        "adoption_intent": pending_adoption(db, root["related_task_rule_id"]),
        "retirement_intent": retired,
        "progress": progress,
    }
    if not summary:
        result.update(
            source_snapshot=source_snapshot(db, root),
            revision_index=str(config["revision_index"]),
            configuration=config["configuration_json"],
            configuration_hash=config["configuration_hash"],
            catalog_generation=catalog(db),
            enrollment=root["enrollment_json"],
            enrolled_at_utc=root["enrolled_at_utc"],
            retirement_disposition=retired["disposition"] if retired else None,
        )
    return result
