"""Immutable recurrence-write evidence; no current-pointer or application dependency."""

import sqlite3
from dataclasses import astuple, replace
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import RecurrenceLineage, RecurrenceMutation, RecurrenceSnapshot
from spine.ledger.mutation_effects import require_transaction


def definition_bytes(value: dict[str, Any]) -> bytes:
    # The existing decoder omits the predecessor header and orders independent
    # children by SQL keys. Preserve selector order and nested null patch values.
    projected = {k: v for k, v in value.items() if k != "prior_recurrence_revision_id"}
    for key in ("segments", "rules", "rdates", "exdates", "overrides"):
        projected[key] = sorted(projected[key], key=canonical_json_bytes)
    return canonical_json_bytes(projected)


def recurrence_snapshot(db: sqlite3.Connection, revision_id: str) -> RecurrenceSnapshot | None:
    row = db.execute(
        "SELECT r.recurrence_set_id,r.recurrence_revision_id,r.revision_number,s.source_item_id,"
        "r.source_item_version,r.normalized_recurrence_set_hash,r.prior_recurrence_revision_id,r.command_id,r.created_at_utc "
        "FROM recurrence_revisions r JOIN recurrence_sets s ON s.recurrence_set_id=r.recurrence_set_id "
        "WHERE r.recurrence_revision_id=?", (revision_id,),
    ).fetchone()
    return None if row is None else RecurrenceSnapshot(*row)


def header_snapshot(row: dict[str, Any]) -> RecurrenceSnapshot:
    return RecurrenceSnapshot(*(row[key] for key in RecurrenceSnapshot.__dataclass_fields__))


def record_recurrence(db: sqlite3.Connection, value: dict[str, object], command_id: str, at: str) -> None:
    pending = require_transaction(db).mutation_state.propagation.recurrences
    prior = value.get("prior_recurrence_revision_id")
    prior_id = None if prior is None else str(prior)
    before = None if prior_id is None else recurrence_snapshot(db, prior_id)
    if prior_id is not None and before is None:
        raise SpineValidationError("environment_failure:propagation", "recurrence predecessor missing")
    after = RecurrenceSnapshot(str(value["recurrence_set_id"]), str(value["recurrence_revision_id"]),
        int(str(value["revision_number"])), str(value["source_item_id"]), int(str(value["source_item_version"])),
        str(value["normalized_recurrence_set_hash"]), prior_id, command_id, at)
    if after.recurrence_revision_id in pending:
        raise SpineValidationError("environment_failure:propagation", "duplicate recurrence mutation")
    pending[after.recurrence_revision_id] = RecurrenceMutation(before, after, definition_bytes(value))


def record_lineage(db: sqlite3.Connection, value: dict[str, object]) -> None:
    pending = require_transaction(db).mutation_state.propagation.recurrences
    revision = str(value["new_recurrence_revision_id"])
    effect = pending.get(revision)
    if effect is None:
        raise SpineValidationError("environment_failure:propagation", "lineage requires pending recurrence mutation")

    def optional(key: str) -> str | None:
        return None if value.get(key) is None else str(value[key])

    line = RecurrenceLineage(str(value["lineage_id"]), str(value["command_id"]), str(value["recurrence_set_id"]),
        str(value["prior_recurrence_revision_id"]), revision, str(value["lineage_role"]), optional("prior_segment_id"),
        optional("new_segment_id"), optional("prior_child_id"), optional("new_child_id"), str(value["effect"]),
        int(str(value["lineage_index"])), str(value["payload_hash"]))
    if (line.recurrence_set_id, line.prior_recurrence_revision_id, line.command_id) != (
        effect.after.recurrence_set_id, effect.after.prior_recurrence_revision_id, effect.after.command_id,
    ):
        raise SpineValidationError("environment_failure:propagation", "lineage identity differs from recurrence mutation")
    pending[revision] = replace(effect, lineage=(*effect.lineage, line))


def verify_recurrence(db: sqlite3.Connection, effect: RecurrenceMutation) -> None:
    from spine.ledger.recurrence import load_recurrence_revision

    stored = load_recurrence_revision(db, revision_id=effect.after.recurrence_revision_id)
    if stored is None or stored[0] != effect.after or definition_bytes(stored[1]) != effect.definition_bytes:
        raise SpineValidationError("environment_failure:propagation", "recurrence aggregate incomplete or changed")
    if effect.before is not None and not effect.lineage:
        raise SpineValidationError("environment_failure:propagation", "recurrence successor lineage missing")
    for line in effect.lineage:
        row = db.execute("SELECT * FROM recurrence_lineage WHERE lineage_id=?", (line.lineage_id,)).fetchone()
        if row is None or tuple(row) != astuple(line):
            raise SpineValidationError("environment_failure:propagation", "recurrence lineage incomplete or changed")
