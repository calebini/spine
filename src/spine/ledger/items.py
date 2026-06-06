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


@dataclass(frozen=True)
class MutatedItem:
    """Result of an atomic item version mutation workflow."""

    item_id: str
    previous_version: int
    version: int
    audit_id: str


_UNSET = object()


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
                version=1,
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
                version=1,
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


def create_next_item_version(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    target_version: int,
    created_at_utc: str,
    created_by_subject_id: str,
    audit_id: str | None = None,
    title: str | None = None,
    summary: str | None | object = _UNSET,
    source_ref: str | None | object = _UNSET,
    event_detail: dict[str, object] | None = None,
    task_detail: dict[str, object] | None = None,
    audit_action: str = "version_created",
    reason_code: str = "item_version_created",
) -> MutatedItem:
    """Create the next immutable item version from the current version."""

    audit_id = audit_id or _new_id("audit")
    _require_non_empty("item_id", item_id)
    _require_non_empty("audit_id", audit_id)
    _require_non_empty("created_at_utc", created_at_utc)
    _require_non_empty("created_by_subject_id", created_by_subject_id)
    if target_version < 1:
        raise SpineValidationError("stale_item_version", "target_version must be greater than or equal to 1")

    try:
        with connection:
            current = _load_current_row(connection, item_id=item_id)
            if current["current_version"] != target_version:
                raise SpineValidationError(
                    "stale_item_version",
                    f"target version {target_version} is not current version {current['current_version']}",
                )
            next_version = target_version + 1
            next_title = title if title is not None else current["title"]
            _require_non_empty("title", next_title)
            next_summary = current["summary"] if summary is _UNSET else summary
            next_source_ref = current["source_ref"] if source_ref is _UNSET else source_ref

            _insert_item_version(
                connection,
                item_id=item_id,
                version=next_version,
                title=next_title,
                summary=next_summary,
                source_ref=next_source_ref,
                created_at_utc=created_at_utc,
                created_by_subject_id=created_by_subject_id,
            )
            _insert_next_detail(
                connection,
                item_id=item_id,
                item_type=current["item_type"],
                previous_version=target_version,
                next_version=next_version,
                event_detail=event_detail,
                task_detail=task_detail,
            )
            cursor = connection.execute(
                """
                UPDATE coordination_items
                SET current_version = ?, updated_at_utc = ?
                WHERE item_id = ? AND current_version = ?
                """,
                (next_version, created_at_utc, item_id, target_version),
            )
            if cursor.rowcount != 1:
                raise SpineValidationError("stale_item_version", "current item pointer was not updated")
            _insert_mutation_audit(
                connection,
                audit_id=audit_id,
                item_id=item_id,
                item_type=current["item_type"],
                previous_version=target_version,
                version=next_version,
                action=audit_action,
                reason_code=reason_code,
                actor_ref=created_by_subject_id,
                created_at_utc=created_at_utc,
            )
            assert_ledger_invariants(connection)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_mutation_rejected", str(exc)) from exc

    return MutatedItem(
        item_id=item_id,
        previous_version=target_version,
        version=target_version + 1,
        audit_id=audit_id,
    )


def cancel_event(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    target_version: int,
    cancelled_at_utc: str,
    cancelled_by_subject_id: str,
    audit_id: str | None = None,
) -> MutatedItem:
    """Transition an event from scheduled to cancelled by creating a new version."""

    current = get_current_item(connection, item_id)
    _require_item_type(current, ItemType.EVENT)
    if current["detail"]["event_status"] != EventStatus.SCHEDULED.value:
        raise SpineValidationError("invalid_event_transition", "only scheduled events can be cancelled")

    return create_next_item_version(
        connection,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=cancelled_at_utc,
        created_by_subject_id=cancelled_by_subject_id,
        audit_id=audit_id,
        event_detail={"event_status": EventStatus.CANCELLED.value},
        audit_action="event_cancelled",
        reason_code="event_cancelled",
    )


def complete_task(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    target_version: int,
    completed_at_utc: str,
    completed_by_subject_id: str,
    audit_id: str | None = None,
    completion_state: str | None = None,
) -> MutatedItem:
    """Transition an open task to done by creating a new version."""

    current = get_current_item(connection, item_id)
    _require_item_type(current, ItemType.TASK)
    if current["detail"]["task_status"] != TaskStatus.OPEN.value:
        raise SpineValidationError("invalid_task_transition", "only open tasks can be completed")

    return create_next_item_version(
        connection,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=completed_at_utc,
        created_by_subject_id=completed_by_subject_id,
        audit_id=audit_id,
        task_detail={
            "task_status": TaskStatus.DONE.value,
            "completion_state": completion_state,
            "completed_at_utc": completed_at_utc,
            "completed_by_subject_id": completed_by_subject_id,
        },
        audit_action="task_completed",
        reason_code="task_completed",
    )


def cancel_task(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    target_version: int,
    cancelled_at_utc: str,
    cancelled_by_subject_id: str,
    audit_id: str | None = None,
) -> MutatedItem:
    """Transition an open task to cancelled by creating a new version."""

    current = get_current_item(connection, item_id)
    _require_item_type(current, ItemType.TASK)
    if current["detail"]["task_status"] != TaskStatus.OPEN.value:
        raise SpineValidationError("invalid_task_transition", "only open tasks can be cancelled")

    return create_next_item_version(
        connection,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=cancelled_at_utc,
        created_by_subject_id=cancelled_by_subject_id,
        audit_id=audit_id,
        task_detail={"task_status": TaskStatus.CANCELLED.value},
        audit_action="task_cancelled",
        reason_code="task_cancelled",
    )


def archive_item(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    target_version: int,
    archived_at_utc: str,
    archived_by_subject_id: str,
    audit_id: str | None = None,
) -> str:
    """Archive an item shell without creating a new item version."""

    audit_id = audit_id or _new_id("audit")
    _require_non_empty("item_id", item_id)
    _require_non_empty("audit_id", audit_id)
    _require_non_empty("archived_at_utc", archived_at_utc)
    _require_non_empty("archived_by_subject_id", archived_by_subject_id)
    try:
        with connection:
            current = _load_current_row(connection, item_id=item_id)
            if current["current_version"] != target_version:
                raise SpineValidationError(
                    "stale_item_version",
                    f"target version {target_version} is not current version {current['current_version']}",
                )
            if current["status"] == ItemStatus.ARCHIVED.value:
                raise SpineValidationError("item_already_archived", f"item is already archived: {item_id}")
            cursor = connection.execute(
                """
                UPDATE coordination_items
                SET status = 'archived', archived_at_utc = ?, updated_at_utc = ?
                WHERE item_id = ? AND current_version = ? AND status = 'active'
                """,
                (archived_at_utc, archived_at_utc, item_id, target_version),
            )
            if cursor.rowcount != 1:
                raise SpineValidationError("item_archive_rejected", "item shell was not archived")
            _insert_mutation_audit(
                connection,
                audit_id=audit_id,
                item_id=item_id,
                item_type=current["item_type"],
                previous_version=target_version,
                version=target_version,
                action="item_archived",
                reason_code="item_archived",
                actor_ref=archived_by_subject_id,
                created_at_utc=archived_at_utc,
            )
            assert_ledger_invariants(connection)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_archive_rejected", str(exc)) from exc
    return audit_id


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


def mutation_audit_payload(
    *,
    action: str,
    item_id: str,
    item_type: ItemType | str,
    previous_version: int,
    version: int,
) -> dict[str, object]:
    """Return the canonical payload hashed for item mutation audit rows."""

    return {
        "action": action,
        "item_id": item_id,
        "item_type": _enum_value(item_type),
        "previous_version": str(previous_version),
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
    version: int,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            version,
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


def _insert_next_detail(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_type: str,
    previous_version: int,
    next_version: int,
    event_detail: dict[str, object] | None,
    task_detail: dict[str, object] | None,
) -> None:
    if item_type == ItemType.EVENT.value:
        if task_detail is not None:
            raise SpineValidationError("item_detail_mismatch", "task detail cannot be applied to an event")
        detail = _load_event_detail(connection, item_id=item_id, version=previous_version)
        previous_status = detail["event_status"]
        detail.update(event_detail or {})
        _validate_event_status_transition(previous_status, detail["event_status"])
        connection.execute(
            """
            INSERT INTO event_details (
              item_id, version, event_status, all_day, start_anchor_id, end_anchor_id,
              visibility, attendance_policy_ref
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                next_version,
                detail["event_status"],
                detail["all_day"],
                detail["start_anchor_id"],
                detail["end_anchor_id"],
                detail["visibility"],
                detail["attendance_policy_ref"],
            ),
        )
        return

    if item_type == ItemType.TASK.value:
        if event_detail is not None:
            raise SpineValidationError("item_detail_mismatch", "event detail cannot be applied to a task")
        detail = _load_task_detail(connection, item_id=item_id, version=previous_version)
        previous_status = detail["task_status"]
        detail.update(task_detail or {})
        _validate_task_status_transition(previous_status, detail["task_status"])
        connection.execute(
            """
            INSERT INTO task_details (
              item_id, version, task_status, completion_state, priority, due_anchor_id,
              defer_until_anchor_id, completed_at_utc, completed_by_subject_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                next_version,
                detail["task_status"],
                detail["completion_state"],
                detail["priority"],
                detail["due_anchor_id"],
                detail["defer_until_anchor_id"],
                detail["completed_at_utc"],
                detail["completed_by_subject_id"],
            ),
        )
        return

    if event_detail is not None or task_detail is not None:
        raise SpineValidationError("item_detail_mismatch", "detail override is not valid for this item type")


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


def _insert_mutation_audit(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    item_id: str,
    item_type: ItemType | str,
    previous_version: int,
    version: int,
    action: str,
    reason_code: str,
    actor_ref: str,
    created_at_utc: str,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log (
          audit_id, item_id, stage, action, reason_code, actor_ref, payload_hash, created_at_utc
        )
        VALUES (?, ?, 'item', ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            item_id,
            action,
            reason_code,
            actor_ref,
            audit_log_payload_hash(
                mutation_audit_payload(
                    action=action,
                    item_id=item_id,
                    item_type=item_type,
                    previous_version=previous_version,
                    version=version,
                )
            ),
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


def _load_current_row(connection: sqlite3.Connection, *, item_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT
          i.item_id, i.item_type, i.current_version, i.status,
          v.title, v.summary, v.source_ref
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
    return row


def _load_event_detail(connection: sqlite3.Connection, *, item_id: str, version: int) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT event_status, all_day, start_anchor_id, end_anchor_id, visibility,
               attendance_policy_ref
        FROM event_details
        WHERE item_id = ? AND version = ?
        """,
        (item_id, version),
    ).fetchone()
    if row is None:
        raise SpineValidationError("item_detail_not_found", f"event detail not found for {item_id} v{version}")
    return dict(row)


def _load_task_detail(connection: sqlite3.Connection, *, item_id: str, version: int) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT task_status, completion_state, priority, due_anchor_id, defer_until_anchor_id,
               completed_at_utc, completed_by_subject_id
        FROM task_details
        WHERE item_id = ? AND version = ?
        """,
        (item_id, version),
    ).fetchone()
    if row is None:
        raise SpineValidationError("item_detail_not_found", f"task detail not found for {item_id} v{version}")
    return dict(row)


def _require_item_type(item: dict[str, object], item_type: ItemType) -> None:
    if item["item_type"] != item_type.value:
        raise SpineValidationError("item_type_mismatch", f"item is not a {item_type.value}")


def _validate_event_status_transition(previous_status: object, next_status: object) -> None:
    if previous_status == next_status:
        return
    if previous_status == EventStatus.SCHEDULED.value and next_status == EventStatus.CANCELLED.value:
        return
    raise SpineValidationError(
        "invalid_event_transition",
        f"event status transition is not allowed: {previous_status} -> {next_status}",
    )


def _validate_task_status_transition(previous_status: object, next_status: object) -> None:
    if previous_status == next_status:
        return
    if previous_status == TaskStatus.OPEN.value and next_status in {
        TaskStatus.DONE.value,
        TaskStatus.CANCELLED.value,
    }:
        return
    raise SpineValidationError(
        "invalid_task_transition",
        f"task status transition is not allowed: {previous_status} -> {next_status}",
    )


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
