"""Atomic coordination item creation workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from spine.core import SpineValidationError
from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.models.enums import EventStatus, ItemStatus, ItemType, TaskStatus, TemporalAnchorKind
from spine.ledger.sqlite import assert_ledger_invariants


@dataclass(frozen=True)
class TemporalAnchorInput:
    """Input row for a temporal anchor created with an item workflow."""

    anchor_kind: TemporalAnchorKind | str
    anchor_id: str | None = None
    local_date: str | None = None
    local_time: str | None = None
    timezone: str | None = None
    utc_instant: str | None = None
    window_start_utc: str | None = None
    window_end_utc: str | None = None
    recurrence_rule: str | None = None
    source: str | None = None
    created_at_utc: str | None = None


@dataclass(frozen=True)
class CreatedItem:
    """Result of an atomic item creation workflow."""

    item_id: str
    version: int
    audit_id: str


def create_event_v1(
    connection: sqlite3.Connection,
    *,
    created_at_utc: str,
    created_by_subject_id: str,
    title: str,
    all_day: bool,
    start_anchor: TemporalAnchorInput,
    item_id: str | None = None,
    audit_id: str | None = None,
    summary: str | None = None,
    source_ref: str | None = None,
    event_status: EventStatus | str = EventStatus.SCHEDULED,
    end_anchor: TemporalAnchorInput | None = None,
    visibility: str | None = None,
    attendance_policy_ref: str | None = None,
) -> CreatedItem:
    """Create a brand-new event item and its v1 facts in one transaction."""

    item_id = item_id or _new_id("item")
    audit_id = audit_id or _new_id("audit")
    _require_non_empty("item_id", item_id)
    _require_non_empty("audit_id", audit_id)
    _require_common_create_inputs(created_at_utc, created_by_subject_id, title)

    start_anchor_id = start_anchor.anchor_id or _new_id("anchor")
    end_anchor_id = end_anchor.anchor_id if end_anchor is not None else None
    if end_anchor is not None and end_anchor_id is None:
        end_anchor_id = _new_id("anchor")

    try:
        with connection:
            _insert_temporal_anchor(
                connection,
                anchor=start_anchor,
                anchor_id=start_anchor_id,
                default_created_at_utc=created_at_utc,
            )
            if end_anchor is not None:
                _insert_temporal_anchor(
                    connection,
                    anchor=end_anchor,
                    anchor_id=end_anchor_id,
                    default_created_at_utc=created_at_utc,
                )
            _insert_item_shell(
                connection,
                item_id=item_id,
                item_type=ItemType.EVENT,
                created_at_utc=created_at_utc,
            )
            _insert_item_version(
                connection,
                item_id=item_id,
                title=title,
                summary=summary,
                source_ref=source_ref,
                created_at_utc=created_at_utc,
                created_by_subject_id=created_by_subject_id,
            )
            connection.execute(
                """
                INSERT INTO event_details (
                  item_id, version, event_status, all_day, start_anchor_id, end_anchor_id,
                  visibility, attendance_policy_ref
                )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    _enum_value(event_status),
                    int(all_day),
                    start_anchor_id,
                    end_anchor_id,
                    visibility,
                    attendance_policy_ref,
                ),
            )
            _insert_creation_audit(
                connection,
                audit_id=audit_id,
                item_id=item_id,
                item_type=ItemType.EVENT,
                created_by_subject_id=created_by_subject_id,
                created_at_utc=created_at_utc,
            )
            assert_ledger_invariants(connection)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_create_rejected", str(exc)) from exc

    return CreatedItem(item_id=item_id, version=1, audit_id=audit_id)


def create_task_v1(
    connection: sqlite3.Connection,
    *,
    created_at_utc: str,
    created_by_subject_id: str,
    title: str,
    item_id: str | None = None,
    audit_id: str | None = None,
    summary: str | None = None,
    source_ref: str | None = None,
    task_status: TaskStatus | str = TaskStatus.OPEN,
    completion_state: str | None = None,
    priority: str | None = None,
    due_anchor: TemporalAnchorInput | None = None,
    defer_until_anchor: TemporalAnchorInput | None = None,
    completed_at_utc: str | None = None,
    completed_by_subject_id: str | None = None,
) -> CreatedItem:
    """Create a brand-new task item and its v1 facts in one transaction."""

    item_id = item_id or _new_id("item")
    audit_id = audit_id or _new_id("audit")
    _require_non_empty("item_id", item_id)
    _require_non_empty("audit_id", audit_id)
    _require_common_create_inputs(created_at_utc, created_by_subject_id, title)

    due_anchor_id = due_anchor.anchor_id if due_anchor is not None else None
    if due_anchor is not None and due_anchor_id is None:
        due_anchor_id = _new_id("anchor")
    defer_until_anchor_id = defer_until_anchor.anchor_id if defer_until_anchor is not None else None
    if defer_until_anchor is not None and defer_until_anchor_id is None:
        defer_until_anchor_id = _new_id("anchor")

    try:
        with connection:
            if due_anchor is not None:
                _insert_temporal_anchor(
                    connection,
                    anchor=due_anchor,
                    anchor_id=due_anchor_id,
                    default_created_at_utc=created_at_utc,
                )
            if defer_until_anchor is not None:
                _insert_temporal_anchor(
                    connection,
                    anchor=defer_until_anchor,
                    anchor_id=defer_until_anchor_id,
                    default_created_at_utc=created_at_utc,
                )
            _insert_item_shell(
                connection,
                item_id=item_id,
                item_type=ItemType.TASK,
                created_at_utc=created_at_utc,
            )
            _insert_item_version(
                connection,
                item_id=item_id,
                title=title,
                summary=summary,
                source_ref=source_ref,
                created_at_utc=created_at_utc,
                created_by_subject_id=created_by_subject_id,
            )
            connection.execute(
                """
                INSERT INTO task_details (
                  item_id, version, task_status, completion_state, priority, due_anchor_id,
                  defer_until_anchor_id, completed_at_utc, completed_by_subject_id
                )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    _enum_value(task_status),
                    completion_state,
                    priority,
                    due_anchor_id,
                    defer_until_anchor_id,
                    completed_at_utc,
                    completed_by_subject_id,
                ),
            )
            _insert_creation_audit(
                connection,
                audit_id=audit_id,
                item_id=item_id,
                item_type=ItemType.TASK,
                created_by_subject_id=created_by_subject_id,
                created_at_utc=created_at_utc,
            )
            assert_ledger_invariants(connection)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_create_rejected", str(exc)) from exc

    return CreatedItem(item_id=item_id, version=1, audit_id=audit_id)


def get_current_item(connection: sqlite3.Connection, item_id: str) -> dict[str, object]:
    """Return current item/version/detail facts for an event or task."""

    row = connection.execute(
        """
        SELECT
          i.item_id, i.item_type, i.current_version, i.status, i.created_at_utc,
          i.updated_at_utc, i.archived_at_utc,
          v.title, v.summary, v.intent_hash, v.normalized_fields_hash, v.source_ref,
          v.created_at_utc AS version_created_at_utc,
          v.created_by_subject_id
        FROM coordination_items AS i
        JOIN coordination_item_versions AS v
          ON v.item_id = i.item_id
         AND v.version = i.current_version
        WHERE i.item_id = ?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("item_not_found", f"coordination item not found: {item_id}")

    detail = _current_detail(connection, item_id=item_id, item_type=row["item_type"], version=row["current_version"])
    return {
        "item_id": row["item_id"],
        "item_type": row["item_type"],
        "current_version": row["current_version"],
        "status": row["status"],
        "created_at_utc": row["created_at_utc"],
        "updated_at_utc": row["updated_at_utc"],
        "archived_at_utc": row["archived_at_utc"],
        "version": {
            "title": row["title"],
            "summary": row["summary"],
            "intent_hash": row["intent_hash"],
            "normalized_fields_hash": row["normalized_fields_hash"],
            "source_ref": row["source_ref"],
            "created_at_utc": row["version_created_at_utc"],
            "created_by_subject_id": row["created_by_subject_id"],
        },
        "detail": detail,
    }


def creation_audit_payload(*, item_id: str, item_type: ItemType | str, version: int) -> dict[str, object]:
    """Return the canonical payload hashed for item creation audit rows."""

    return {
        "action": "created",
        "item_id": item_id,
        "item_type": _enum_value(item_type),
        "version": str(version),
    }


def _insert_temporal_anchor(
    connection: sqlite3.Connection,
    *,
    anchor: TemporalAnchorInput,
    anchor_id: str,
    default_created_at_utc: str,
) -> None:
    _require_non_empty("anchor_id", anchor_id)
    created_at_utc = anchor.created_at_utc or default_created_at_utc
    _require_non_empty("anchor.created_at_utc", created_at_utc)
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, local_time, timezone, utc_instant,
          window_start_utc, window_end_utc, recurrence_rule, source, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            anchor_id,
            _enum_value(anchor.anchor_kind),
            anchor.local_date,
            anchor.local_time,
            anchor.timezone,
            anchor.utc_instant,
            anchor.window_start_utc,
            anchor.window_end_utc,
            anchor.recurrence_rule,
            anchor.source,
            created_at_utc,
        ),
    )


def _insert_item_shell(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_type: ItemType,
    created_at_utc: str,
) -> None:
    connection.execute(
        """
        INSERT INTO coordination_items (
          item_id, item_type, current_version, status, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (item_id, item_type.value, ItemStatus.ACTIVE.value, created_at_utc, created_at_utc),
    )


def _insert_item_version(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    title: str,
    summary: str | None,
    source_ref: str | None,
    created_at_utc: str,
    created_by_subject_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO coordination_item_versions (
          item_id, version, title, summary, intent_hash, normalized_fields_hash,
          source_ref, created_at_utc, created_by_subject_id
        )
        VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            title,
            summary,
            coordination_item_version_intent_hash(
                title=title,
                summary=summary,
                source_ref=source_ref,
            ),
            coordination_item_version_normalized_fields_hash(title=title, summary=summary),
            source_ref,
            created_at_utc,
            created_by_subject_id,
        ),
    )


def _insert_creation_audit(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    item_id: str,
    item_type: ItemType,
    created_by_subject_id: str,
    created_at_utc: str,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log (
          audit_id, item_id, stage, action, reason_code, actor_ref, payload_hash, created_at_utc
        )
        VALUES (?, ?, 'item', 'created', 'item_created', ?, ?, ?)
        """,
        (
            audit_id,
            item_id,
            created_by_subject_id,
            audit_log_payload_hash(creation_audit_payload(item_id=item_id, item_type=item_type, version=1)),
            created_at_utc,
        ),
    )


def _current_detail(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_type: str,
    version: int,
) -> dict[str, object]:
    if item_type == ItemType.EVENT.value:
        row = connection.execute(
            """
            SELECT event_status, all_day, start_anchor_id, end_anchor_id, visibility,
                   attendance_policy_ref
            FROM event_details
            WHERE item_id = ? AND version = ?
            """,
            (item_id, version),
        ).fetchone()
    elif item_type == ItemType.TASK.value:
        row = connection.execute(
            """
            SELECT task_status, completion_state, priority, due_anchor_id, defer_until_anchor_id,
                   completed_at_utc, completed_by_subject_id
            FROM task_details
            WHERE item_id = ? AND version = ?
            """,
            (item_id, version),
        ).fetchone()
    else:
        return {}

    if row is None:
        raise SpineValidationError(
            "item_detail_not_found",
            f"current detail row not found for {item_id} version {version}",
        )
    return dict(row)


def _require_common_create_inputs(created_at_utc: str, created_by_subject_id: str, title: str) -> None:
    _require_non_empty("created_at_utc", created_at_utc)
    _require_non_empty("created_by_subject_id", created_by_subject_id)
    _require_non_empty("title", title)


def _require_non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) == 0:
        raise SpineValidationError("invalid_item_create_input", f"{name} must be a non-empty string")


def _enum_value(value: StrEnum | str) -> str:
    return value.value if isinstance(value, StrEnum) else value


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"
