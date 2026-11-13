"""Bounded capture/debt for selected native binding writers; no application calls."""

import sqlite3
from collections.abc import Mapping
from dataclasses import replace

from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import BindingMutation, BindingSnapshot
from spine.ledger.transactions import LedgerConnection


def require_transaction(db: sqlite3.Connection) -> LedgerConnection:
    if not isinstance(db, LedgerConnection) or not db.in_transaction:
        raise SpineValidationError("environment_failure:propagation", "binding propagation requires an owned transaction")
    return db


def binding_snapshot(db: sqlite3.Connection, binding_id: str) -> BindingSnapshot | None:
    row = db.execute(
        "SELECT b.temporal_binding_id AS binding_id,b.source_item_id,b.target_item_id,b.relationship_id,"
        "b.binding_status AS status,r.temporal_binding_revision_id AS revision_id,r.revision_index,"
        "r.source_target_version AS source_item_version,r.target_item_version,r.source_recurrence_revision_id,"
        "r.source_occurrence_key,r.source_anchor_id,r.target_anchor_id,r.resolved_source_utc,r.resolved_target_utc,"
        "r.offset_seconds,r.target_local_date,r.target_local_time,r.target_timezone,r.target_timezone_database_version "
        "FROM relative_temporal_bindings b LEFT JOIN relative_temporal_binding_revisions r "
        "ON r.temporal_binding_id=b.temporal_binding_id WHERE b.temporal_binding_id=? "
        "ORDER BY r.revision_index DESC LIMIT 1", (binding_id,),
    ).fetchone()
    return None if row is None else BindingSnapshot(**dict(row))


def binding_before(db: sqlite3.Connection, binding_id: str) -> BindingSnapshot | None:
    pending = require_transaction(db).mutation_state.propagation.bindings.get(binding_id)
    return pending.after if pending is not None else binding_snapshot(db, binding_id)


def binding_revision(before: BindingSnapshot, value: Mapping[str, object]) -> BindingSnapshot:
    """Project the successful native INSERT; propagation verifies it against SQL.

    Avoid rereading each intermediate header/revision in a bounded child page.
    SQLite's integer affinity is reflected explicitly in the typed snapshot.
    """
    def optional(key: str) -> str | None:
        return None if value.get(key) is None else str(value[key])

    return replace(
        before, revision_id=str(value["temporal_binding_revision_id"]),
        revision_index=int(str(value["revision_index"])),
        source_item_version=int(str(value["source_target_version"])),
        target_item_version=int(str(value["target_item_version"])),
        source_recurrence_revision_id=optional("source_recurrence_revision_id"),
        source_occurrence_key=optional("source_occurrence_key"), source_anchor_id=optional("source_anchor_id"),
        target_anchor_id=str(value["target_anchor_id"]), resolved_source_utc=str(value["resolved_source_utc"]),
        resolved_target_utc=str(value["resolved_target_utc"]), offset_seconds=int(str(value["offset_seconds"])),
        target_local_date=str(value["target_local_date"]), target_local_time=str(value["target_local_time"]),
        target_timezone=str(value["target_timezone"]),
        target_timezone_database_version=str(value["target_timezone_database_version"]),
    )


def record_binding(db: sqlite3.Connection, binding_id: str, before: BindingSnapshot | None, after: BindingSnapshot) -> None:
    connection = require_transaction(db)
    if after.binding_id != binding_id or before == after:
        raise SpineValidationError("environment_failure:propagation", "binding writer produced no exact change")
    pending = connection.mutation_state.propagation.bindings
    previous = pending.get(binding_id)
    if previous is not None and previous.after != before:
        raise SpineValidationError("environment_failure:propagation", "binding effects are out of order")
    pending[binding_id] = BindingMutation(previous.before if previous else before, after)
