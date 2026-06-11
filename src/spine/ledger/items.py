"""Atomic coordination item creation workflows."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.ledger.common import (
    TemporalAnchorInput,
    enum_value,
    insert_temporal_anchor,
    new_id,
    require_non_empty,
)
from spine.ledger.item_drafts import EventDraft, ItemVersionDraft, TaskDraft, _UNSET
from spine.ledger.supporting import (
    ItemLocationInput,
    ItemSubjectRoleInput,
    NotificationPolicyInput,
    copy_forward_supporting_sets,
    current_locations,
    current_notification_policies,
    current_subject_roles,
    insert_supporting_sets,
)
from spine.models.enums import EventStatus, ItemStatus, ItemType, TaskStatus
from spine.ledger.sqlite import assert_ledger_invariants


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

def create_event_from_draft(connection: sqlite3.Connection, draft: EventDraft) -> CreatedItem:
    """Create a brand-new event item from an input bundle."""

    item_id = draft.item_id or new_id("item")
    audit_id = draft.audit_id or new_id("audit")
    require_non_empty("item_id", item_id)
    require_non_empty("audit_id", audit_id)
    _require_common_create_inputs(draft.created_at_utc, draft.created_by_subject_id, draft.title)

    start_anchor_id = draft.start_anchor.anchor_id or new_id("anchor")
    end_anchor_id = draft.end_anchor.anchor_id if draft.end_anchor is not None else None
    if draft.end_anchor is not None and end_anchor_id is None:
        end_anchor_id = new_id("anchor")

    def insert_anchors(connection: sqlite3.Connection) -> None:
        insert_temporal_anchor(
            connection,
            anchor=draft.start_anchor,
            anchor_id=start_anchor_id,
            default_created_at_utc=draft.created_at_utc,
        )
        if draft.end_anchor is not None:
            insert_temporal_anchor(
                connection,
                anchor=draft.end_anchor,
                anchor_id=end_anchor_id,
                default_created_at_utc=draft.created_at_utc,
            )

    def insert_detail(connection: sqlite3.Connection) -> None:
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
                enum_value(draft.event_status),
                int(draft.all_day),
                start_anchor_id,
                end_anchor_id,
                draft.visibility,
                draft.attendance_policy_ref,
            ),
        )

    return _create_item_v1(
        connection,
        item_id=item_id,
        audit_id=audit_id,
        item_type=ItemType.EVENT,
        created_at_utc=draft.created_at_utc,
        created_by_subject_id=draft.created_by_subject_id,
        title=draft.title,
        summary=draft.summary,
        source_ref=draft.source_ref,
        item_locations=draft.item_locations,
        subject_roles=draft.subject_roles,
        notification_policies=draft.notification_policies,
        insert_anchors=insert_anchors,
        insert_detail=insert_detail,
    )


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
    item_locations: tuple[ItemLocationInput, ...] = (),
    subject_roles: tuple[ItemSubjectRoleInput, ...] = (),
    notification_policies: tuple[NotificationPolicyInput, ...] = (),
) -> CreatedItem:
    """Create a brand-new event item and its v1 facts in one transaction."""

    return create_event_from_draft(
        connection,
        EventDraft(
            item_id=item_id,
            audit_id=audit_id,
            created_at_utc=created_at_utc,
            created_by_subject_id=created_by_subject_id,
            title=title,
            summary=summary,
            source_ref=source_ref,
            event_status=event_status,
            all_day=all_day,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            visibility=visibility,
            attendance_policy_ref=attendance_policy_ref,
            item_locations=item_locations,
            subject_roles=subject_roles,
            notification_policies=notification_policies,
        ),
    )


def create_task_from_draft(connection: sqlite3.Connection, draft: TaskDraft) -> CreatedItem:
    """Create a brand-new task item from an input bundle."""

    item_id = draft.item_id or new_id("item")
    audit_id = draft.audit_id or new_id("audit")
    require_non_empty("item_id", item_id)
    require_non_empty("audit_id", audit_id)
    _require_common_create_inputs(draft.created_at_utc, draft.created_by_subject_id, draft.title)

    due_anchor_id = draft.due_anchor.anchor_id if draft.due_anchor is not None else None
    if draft.due_anchor is not None and due_anchor_id is None:
        due_anchor_id = new_id("anchor")
    defer_until_anchor_id = draft.defer_until_anchor.anchor_id if draft.defer_until_anchor is not None else None
    if draft.defer_until_anchor is not None and defer_until_anchor_id is None:
        defer_until_anchor_id = new_id("anchor")

    def insert_anchors(connection: sqlite3.Connection) -> None:
        if draft.due_anchor is not None:
            insert_temporal_anchor(
                connection,
                anchor=draft.due_anchor,
                anchor_id=due_anchor_id,
                default_created_at_utc=draft.created_at_utc,
            )
        if draft.defer_until_anchor is not None:
            insert_temporal_anchor(
                connection,
                anchor=draft.defer_until_anchor,
                anchor_id=defer_until_anchor_id,
                default_created_at_utc=draft.created_at_utc,
            )

    def insert_detail(connection: sqlite3.Connection) -> None:
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
                enum_value(draft.task_status),
                draft.completion_state,
                draft.priority,
                due_anchor_id,
                defer_until_anchor_id,
                draft.completed_at_utc,
                draft.completed_by_subject_id,
            ),
        )

    return _create_item_v1(
        connection,
        item_id=item_id,
        audit_id=audit_id,
        item_type=ItemType.TASK,
        created_at_utc=draft.created_at_utc,
        created_by_subject_id=draft.created_by_subject_id,
        title=draft.title,
        summary=draft.summary,
        source_ref=draft.source_ref,
        item_locations=draft.item_locations,
        subject_roles=draft.subject_roles,
        notification_policies=draft.notification_policies,
        insert_anchors=insert_anchors,
        insert_detail=insert_detail,
    )


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
    item_locations: tuple[ItemLocationInput, ...] = (),
    subject_roles: tuple[ItemSubjectRoleInput, ...] = (),
    notification_policies: tuple[NotificationPolicyInput, ...] = (),
) -> CreatedItem:
    """Create a brand-new task item and its v1 facts in one transaction."""

    return create_task_from_draft(
        connection,
        TaskDraft(
            item_id=item_id,
            audit_id=audit_id,
            created_at_utc=created_at_utc,
            created_by_subject_id=created_by_subject_id,
            title=title,
            summary=summary,
            source_ref=source_ref,
            task_status=task_status,
            completion_state=completion_state,
            priority=priority,
            due_anchor=due_anchor,
            defer_until_anchor=defer_until_anchor,
            completed_at_utc=completed_at_utc,
            completed_by_subject_id=completed_by_subject_id,
            item_locations=item_locations,
            subject_roles=subject_roles,
            notification_policies=notification_policies,
        ),
    )


def create_item_version_from_draft(connection: sqlite3.Connection, draft: ItemVersionDraft) -> MutatedItem:
    """Create the next immutable item version from an input bundle."""

    audit_id = draft.audit_id or new_id("audit")
    require_non_empty("item_id", draft.item_id)
    require_non_empty("audit_id", audit_id)
    require_non_empty("created_at_utc", draft.created_at_utc)
    require_non_empty("created_by_subject_id", draft.created_by_subject_id)
    if draft.target_version < 1:
        raise SpineValidationError("stale_item_version", "target_version must be greater than or equal to 1")

    try:
        with connection:
            current = _load_current_row(connection, item_id=draft.item_id)
            if current["current_version"] != draft.target_version:
                raise SpineValidationError(
                    "stale_item_version",
                    f"target version {draft.target_version} is not current version {current['current_version']}",
                )
            next_version = draft.target_version + 1
            next_title = draft.title if draft.title is not None else current["title"]
            require_non_empty("title", next_title)
            next_summary = current["summary"] if draft.summary is _UNSET else draft.summary
            next_source_ref = current["source_ref"] if draft.source_ref is _UNSET else draft.source_ref

            _insert_item_version(
                connection,
                item_id=draft.item_id,
                version=next_version,
                title=next_title,
                summary=next_summary,
                source_ref=next_source_ref,
                created_at_utc=draft.created_at_utc,
                created_by_subject_id=draft.created_by_subject_id,
            )
            _insert_next_detail(
                connection,
                item_id=draft.item_id,
                item_type=current["item_type"],
                previous_version=draft.target_version,
                next_version=next_version,
                event_detail=draft.event_detail,
                task_detail=draft.task_detail,
            )
            copy_forward_supporting_sets(
                connection,
                item_id=draft.item_id,
                previous_version=draft.target_version,
                next_version=next_version,
                created_at_utc=draft.created_at_utc,
            )
            cursor = connection.execute(
                """
                UPDATE coordination_items
                SET current_version = ?, updated_at_utc = ?
                WHERE item_id = ? AND current_version = ?
                """,
                (next_version, draft.created_at_utc, draft.item_id, draft.target_version),
            )
            if cursor.rowcount != 1:
                raise SpineValidationError("stale_item_version", "current item pointer was not updated")
            _insert_mutation_audit(
                connection,
                audit_id=audit_id,
                item_id=draft.item_id,
                item_type=current["item_type"],
                previous_version=draft.target_version,
                version=next_version,
                action=draft.audit_action,
                reason_code=draft.reason_code,
                actor_ref=draft.created_by_subject_id,
                created_at_utc=draft.created_at_utc,
            )
            assert_ledger_invariants(connection, item_id=draft.item_id)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_mutation_rejected", str(exc)) from exc

    return MutatedItem(
        item_id=draft.item_id,
        previous_version=draft.target_version,
        version=draft.target_version + 1,
        audit_id=audit_id,
    )


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

    return create_item_version_from_draft(
        connection,
        ItemVersionDraft(
            item_id=item_id,
            target_version=target_version,
            created_at_utc=created_at_utc,
            created_by_subject_id=created_by_subject_id,
            audit_id=audit_id,
            title=title,
            summary=summary,
            source_ref=source_ref,
            event_detail=event_detail,
            task_detail=task_detail,
            audit_action=audit_action,
            reason_code=reason_code,
        ),
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

    audit_id = audit_id or new_id("audit")
    require_non_empty("item_id", item_id)
    require_non_empty("audit_id", audit_id)
    require_non_empty("archived_at_utc", archived_at_utc)
    require_non_empty("archived_by_subject_id", archived_by_subject_id)
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
            assert_ledger_invariants(connection, item_id=item_id)
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
        "locations": current_locations(connection, item_id=item_id, version=row["current_version"]),
        "subject_roles": current_subject_roles(connection, item_id=item_id, version=row["current_version"]),
        "notification_policies": current_notification_policies(
            connection,
            item_id=item_id,
            version=row["current_version"],
        ),
    }


def creation_audit_payload(*, item_id: str, item_type: ItemType | str, version: int) -> dict[str, object]:
    """Return the canonical payload hashed for item creation audit rows."""

    return {
        "action": "created",
        "item_id": item_id,
        "item_type": enum_value(item_type),
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
        "item_type": enum_value(item_type),
        "previous_version": str(previous_version),
        "version": str(version),
    }


def _create_item_v1(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    audit_id: str,
    item_type: ItemType,
    created_at_utc: str,
    created_by_subject_id: str,
    title: str,
    summary: str | None,
    source_ref: str | None,
    item_locations: tuple[ItemLocationInput, ...],
    subject_roles: tuple[ItemSubjectRoleInput, ...],
    notification_policies: tuple[NotificationPolicyInput, ...],
    insert_anchors: Callable[[sqlite3.Connection], None],
    insert_detail: Callable[[sqlite3.Connection], None],
) -> CreatedItem:
    try:
        with connection:
            insert_anchors(connection)
            _insert_item_shell(
                connection,
                item_id=item_id,
                item_type=item_type,
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
            insert_detail(connection)
            insert_supporting_sets(
                connection,
                item_id=item_id,
                version=1,
                default_created_at_utc=created_at_utc,
                item_locations=item_locations,
                subject_roles=subject_roles,
                notification_policies=notification_policies,
            )
            _insert_creation_audit(
                connection,
                audit_id=audit_id,
                item_id=item_id,
                item_type=item_type,
                created_by_subject_id=created_by_subject_id,
                created_at_utc=created_at_utc,
            )
            assert_ledger_invariants(connection, item_id=item_id)
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_create_rejected", str(exc)) from exc
    return CreatedItem(item_id=item_id, version=1, audit_id=audit_id)


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


def current_locations(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
          il.item_location_id, il.item_id, il.version, il.location_id, il.role,
          il.created_at_utc,
          l.label, l.kind, l.address_text, l.latitude, l.longitude, l.timezone,
          l.provider_ref, l.metadata_json
        FROM item_locations AS il
        JOIN locations AS l ON l.location_id = il.location_id
        WHERE il.item_id = ? AND il.version = ?
        ORDER BY il.item_location_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def current_subject_roles(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT *
        FROM item_subject_roles
        WHERE item_id = ? AND version = ?
        ORDER BY item_subject_role_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def current_notification_policies(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT *
        FROM notification_policies
        WHERE item_id = ? AND version = ?
        ORDER BY policy_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


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
    require_non_empty("created_at_utc", created_at_utc)
    require_non_empty("created_by_subject_id", created_by_subject_id)
    require_non_empty("title", title)
