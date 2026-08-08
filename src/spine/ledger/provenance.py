"""Persistence operations for occurrence provenance snapshots."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import cast

from spine.core.provenance import DerivedOccurrenceProvenance
from spine.core.recurrence_set import generated_id
from spine.ledger.recurrence import persist_target_occurrence_selector


def active_provenance_for_slot(connection: sqlite3.Connection, *, slot_key: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            """
        SELECT * FROM occurrence_provenance
        WHERE occurrence_provenance_slot_key = ? AND management_status = 'active'
        """,
            (slot_key,),
        ).fetchone(),
    )


def insert_occurrence_provenance(connection: sqlite3.Connection, *, derived: DerivedOccurrenceProvenance) -> None:
    value = derived.value
    selector = value["target_occurrence_selector"]
    assert isinstance(selector, dict)
    selector_ref = persist_target_occurrence_selector(
        connection,
        occurrence_key=str(value["occurrence_key"]),
        selector=selector,
    )
    connection.execute(
        """
        INSERT INTO occurrence_provenance (
          occurrence_provenance_id, occurrence_provenance_slot_key, producer,
          consumer, item_id, source_item_version, shell_status, archived_at_utc,
          recurrence_set_id, recurrence_revision_id, normalized_recurrence_set_hash,
          target_occurrence_selector_ref, occurrence_id, occurrence_key,
          range_basis, range_start, range_end, original_scheduled_fact,
          expressed_scheduled_fact, timezone, timezone_database_version,
          timezone_resolution_kind, timezone_utc_instant, timezone_offset_seconds,
          override_id, lifecycle, actionable, content_hash, contract_version,
          normalization_version, canonical_json_version, management_status,
          created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["occurrence_provenance_id"],
            value["occurrence_provenance_slot_key"],
            value.get("producer"),
            value["consumer"],
            value["item_id"],
            int(str(value["source_item_version"])),
            value["shell_status"],
            value.get("archived_at_utc"),
            value["recurrence_set_id"],
            value["recurrence_revision_id"],
            value["normalized_recurrence_set_hash"],
            selector_ref,
            value["occurrence_id"],
            value["occurrence_key"],
            value["range_basis"],
            value["range_start"],
            value["range_end"],
            value["original_scheduled_fact"],
            value["expressed_scheduled_fact"],
            value.get("timezone"),
            value.get("timezone_database_version"),
            value.get("timezone_resolution_kind"),
            value.get("timezone_utc_instant"),
            int(str(value["timezone_offset_seconds"])) if value.get("timezone_offset_seconds") is not None else None,
            value.get("override_id"),
            value["lifecycle"],
            int(bool(value["actionable"])),
            value["content_hash"],
            value["contract_version"],
            value["normalization_version"],
            value["canonical_json_version"],
            value["management_status"],
            value["created_at_utc"],
        ),
    )
    rule_index = 0
    rdate_index = 0
    entries = value["source_entries"]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, Mapping)
        if entry["source_kind"] == "rule":
            connection.execute(
                """
                INSERT INTO occurrence_provenance_rule_sources (
                  occurrence_provenance_id, source_index, rule_id, rule_local_index
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    value["occurrence_provenance_id"],
                    rule_index,
                    entry["source_id"],
                    int(str(entry["rule_local_index"])),
                ),
            )
            rule_index += 1
        else:
            connection.execute(
                """
                INSERT INTO occurrence_provenance_rdate_sources (
                  occurrence_provenance_id, source_index, rdate_id
                ) VALUES (?, ?, ?)
                """,
                (value["occurrence_provenance_id"], rdate_index, entry["source_id"]),
            )
            rdate_index += 1


def supersede_occurrence_provenance(
    connection: sqlite3.Connection,
    *,
    occurrence_provenance_id: str,
    command_id: str,
    superseded_at_utc: str,
    replacement_occurrence_provenance_id: str | None,
) -> None:
    connection.execute(
        """
        UPDATE occurrence_provenance
        SET management_status = 'superseded', superseded_by_command_id = ?,
            superseded_at_utc = ?, replacement_occurrence_provenance_id = ?
        WHERE occurrence_provenance_id = ? AND management_status = 'active'
        """,
        (
            command_id,
            superseded_at_utc,
            replacement_occurrence_provenance_id,
            occurrence_provenance_id,
        ),
    )


def active_provenance_for_range(
    connection: sqlite3.Connection,
    *,
    consumer: str,
    item_id: str,
    recurrence_set_id: str,
    range_basis: str,
    range_start: str,
    range_end: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM occurrence_provenance
        WHERE consumer = ? AND item_id = ? AND recurrence_set_id = ?
          AND range_basis = ? AND range_start = ? AND range_end = ?
          AND management_status = 'active'
        ORDER BY original_scheduled_fact, occurrence_provenance_slot_key
        """,
        (consumer, item_id, recurrence_set_id, range_basis, range_start, range_end),
    ).fetchall()


def close_recoverable_provenance_reports(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    consumer: str,
    recurrence_set_id: str,
    command_id: str,
    closed_at_utc: str,
    range_basis: str,
    range_start: str,
    range_end: str,
) -> tuple[list[str], list[dict[str, object]]]:
    """Close open reports proven recoverable by an explicit canonical regeneration."""

    rows = connection.execute(
        """
        SELECT report.*, stale.management_status AS stale_management_status,
               replacement.occurrence_provenance_id AS resulting_id
        FROM recurrence_provenance_block_reports AS report
        LEFT JOIN occurrence_provenance AS stale
          ON stale.occurrence_provenance_id = report.stale_occurrence_provenance_id
        LEFT JOIN occurrence_provenance AS replacement
          ON replacement.occurrence_provenance_slot_key = report.occurrence_provenance_slot_key
         AND replacement.management_status = 'active'
        WHERE report.item_id = ? AND report.consumer = ?
          AND report.recurrence_set_id = ? AND report.status = 'open'
        ORDER BY report.block_report_id
        """,
        (item_id, consumer, recurrence_set_id),
    ).fetchall()
    closed: list[str] = []
    unresolved: list[dict[str, object]] = []
    for row in rows:
        exact_range = row["range_basis"] is None or (
            row["range_basis"] == range_basis and row["range_start"] == range_start and row["range_end"] == range_end
        )
        stale_cleared = row["stale_occurrence_provenance_id"] is None or row["stale_management_status"] == "superseded"
        if exact_range and stale_cleared:
            closure_kind = "canonical_range_derived_no_stale_provenance" if row["resulting_id"] is None else "canonical_range_derived"
            connection.execute(
                """
                UPDATE recurrence_provenance_block_reports
                SET status = 'resolved', resolved_by_command_id = ?, closed_at_utc = ?,
                    closure_kind = ?, range_basis = COALESCE(range_basis, ?),
                    range_start = COALESCE(range_start, ?), range_end = COALESCE(range_end, ?),
                    resulting_occurrence_provenance_id = ?
                WHERE block_report_id = ? AND status = 'open'
                """,
                (
                    command_id,
                    closed_at_utc,
                    closure_kind,
                    range_basis,
                    range_start,
                    range_end,
                    row["resulting_id"],
                    row["block_report_id"],
                ),
            )
            closed.append(str(row["block_report_id"]))
        else:
            unresolved.append(
                {
                    "block_report_id": row["block_report_id"],
                    "reason_code": row["reason_code"],
                    **({"range_basis": row["range_basis"]} if row["range_basis"] is not None else {}),
                    **({"range_start": row["range_start"]} if row["range_start"] is not None else {}),
                    **({"range_end": row["range_end"]} if row["range_end"] is not None else {}),
                    "recurrence_revision_id": row["recurrence_revision_id"],
                    "normalized_recurrence_set_hash": row["normalized_recurrence_set_hash"],
                }
            )
    return closed, unresolved


def record_stale_work_provenance_report(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    operation: str,
    blocked_at_utc: str,
) -> str | None:
    """Persist the canonical recovery handoff when recurrence-bound work is stale."""

    row = connection.execute(
        """
        SELECT w.item_id, w.occurrence_provenance_id, op.consumer,
               op.recurrence_set_id, op.range_basis, op.range_start, op.range_end,
               op.occurrence_provenance_slot_key,
               rr.recurrence_revision_id, rr.source_item_version,
               rr.normalized_recurrence_set_hash,
               rs.contract_version, rs.normalization_version, rs.canonical_json_version
        FROM work_instances AS w
        JOIN occurrence_provenance AS op
          ON op.occurrence_provenance_id = w.occurrence_provenance_id
        JOIN recurrence_sets AS rs ON rs.source_item_id = w.item_id
        JOIN recurrence_revisions AS rr ON rr.recurrence_set_id = rs.recurrence_set_id
        JOIN coordination_items AS item ON item.item_id = w.item_id
        WHERE w.work_instance_id = ?
          AND rr.source_item_version <= item.current_version
        ORDER BY rr.source_item_version DESC, rr.revision_number DESC
        LIMIT 1
        """,
        (work_instance_id,),
    ).fetchone()
    if row is None:
        return None
    identity = {
        "report_version": "spine.recurrence.provenance-block.v1",
        "item_id": row["item_id"],
        "consumer": row["consumer"],
        "operation": operation,
        "recurrence_set_id": row["recurrence_set_id"],
        "range_basis": row["range_basis"],
        "range_start": row["range_start"],
        "range_end": row["range_end"],
        "stale_occurrence_provenance_id": row["occurrence_provenance_id"],
        "occurrence_provenance_slot_key": row["occurrence_provenance_slot_key"],
        "source_item_version": str(row["source_item_version"]),
        "contract_version": row["contract_version"],
        "normalization_version": row["normalization_version"],
        "canonical_json_version": row["canonical_json_version"],
        "recurrence_revision_id": row["recurrence_revision_id"],
        "normalized_recurrence_set_hash": row["normalized_recurrence_set_hash"],
    }
    report_id, _ = generated_id(
        "recurrence_provenance_block",
        "spine.recurrence-provenance-block-id.v1",
        identity,
    )
    connection.execute(
        """
        INSERT INTO recurrence_provenance_block_reports (
          block_report_id, report_version, item_id, consumer, operation,
          recurrence_set_id, range_basis, range_start, range_end,
          stale_occurrence_provenance_id, occurrence_provenance_slot_key,
          source_item_version, contract_version, normalization_version,
          canonical_json_version, recurrence_revision_id,
          normalized_recurrence_set_hash, reason_code, handoff, status,
          block_count, first_blocked_at_utc, last_blocked_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  'stale_occurrence_provenance', 'occurrence_provenance.regenerate',
                  'open', 1, ?, ?)
        ON CONFLICT(block_report_id) DO UPDATE SET
          block_count = block_count + 1,
          last_blocked_at_utc = excluded.last_blocked_at_utc
        WHERE status = 'open'
        """,
        (
            report_id,
            identity["report_version"],
            identity["item_id"],
            identity["consumer"],
            identity["operation"],
            identity["recurrence_set_id"],
            identity["range_basis"],
            identity["range_start"],
            identity["range_end"],
            identity["stale_occurrence_provenance_id"],
            identity["occurrence_provenance_slot_key"],
            int(str(identity["source_item_version"])),
            identity["contract_version"],
            identity["normalization_version"],
            identity["canonical_json_version"],
            identity["recurrence_revision_id"],
            identity["normalized_recurrence_set_hash"],
            blocked_at_utc,
            blocked_at_utc,
        ),
    )
    return report_id
