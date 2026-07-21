"""Generated work-instance workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import enum_value, new_id, require_non_empty, require_optional_utc_z, require_utc_z
from spine.models.enums import (
    EventStatus,
    GenerationSourceKind,
    ItemStatus,
    ItemType,
    NotificationPolicyStatus,
    TaskStatus,
    WorkKind,
    WorkStatus,
)


@dataclass(frozen=True)
class CreatedWorkInstance:
    """Result of creating a generated work row."""

    work_instance_id: str
    item_id: str
    item_version: int


@dataclass(frozen=True)
class UpdatedWorkInstance:
    """Result of changing generated work lifecycle state."""

    work_instance_id: str
    status: str
    attempt_count: int


def create_work_instance(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_version: int,
    eligible_at_utc: str,
    created_at_utc: str,
    work_instance_id: str | None = None,
    notification_policy_id: str | None = None,
    notification_policy_item_version: int | None = None,
    delivery_target_id: str | None = None,
    source_work_instance_id: str | None = None,
    generation_source_kind: GenerationSourceKind | str | None = None,
    generation_source_ref: str | None = None,
    work_subject_ref: str | None = None,
    work_kind: WorkKind | str = WorkKind.NOTIFICATION_REMINDER,
    purpose_detail_ref: str | None = None,
    policy_basis_ref: str | None = None,
    status: WorkStatus | str = WorkStatus.ELIGIBLE,
    attempt_count: int = 0,
    next_attempt_at_utc: str | None = None,
    reason_code: str | None = None,
    updated_at_utc: str | None = None,
) -> CreatedWorkInstance:
    """Create a durable generated work row without executing side effects."""

    work_instance_id = work_instance_id or new_id("work")
    require_non_empty("work_instance_id", work_instance_id)
    require_non_empty("item_id", item_id)
    require_utc_z("eligible_at_utc", eligible_at_utc)
    require_utc_z("created_at_utc", created_at_utc)
    require_optional_utc_z("next_attempt_at_utc", next_attempt_at_utc)
    if updated_at_utc is not None:
        require_utc_z("updated_at_utc", updated_at_utc)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO work_instances (
                  work_instance_id, item_id, item_version, notification_policy_id,
                  notification_policy_item_version, delivery_target_id, source_work_instance_id,
                  generation_source_kind, generation_source_ref, work_subject_ref,
                  work_kind, purpose_detail_ref, policy_basis_ref, eligible_at_utc,
                  status, attempt_count, next_attempt_at_utc, reason_code, created_at_utc,
                  updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_instance_id,
                    item_id,
                    item_version,
                    notification_policy_id,
                    notification_policy_item_version,
                    delivery_target_id,
                    source_work_instance_id,
                    enum_value(generation_source_kind) if generation_source_kind is not None else None,
                    generation_source_ref,
                    work_subject_ref,
                    enum_value(work_kind),
                    purpose_detail_ref,
                    policy_basis_ref,
                    eligible_at_utc,
                    enum_value(status),
                    attempt_count,
                    next_attempt_at_utc,
                    reason_code,
                    created_at_utc,
                    updated_at_utc or created_at_utc,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("work_instance_rejected", str(exc)) from exc
    return CreatedWorkInstance(work_instance_id=work_instance_id, item_id=item_id, item_version=item_version)


def start_work_instance(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    started_at_utc: str,
    reason_code: str | None = None,
) -> UpdatedWorkInstance:
    """Mark eligible work in progress and count one processing attempt."""

    require_utc_z("started_at_utc", started_at_utc)
    row = _get_work_for_outcome(connection, work_instance_id)
    if row["status"] != WorkStatus.ELIGIBLE.value:
        raise SpineValidationError("work_outcome_rejected", f"work is not eligible: {work_instance_id}")
    with connection:
        connection.execute(
            """
            UPDATE work_instances
            SET status = 'in_progress',
                attempt_count = attempt_count + 1,
                next_attempt_at_utc = NULL,
                reason_code = ?,
                updated_at_utc = ?
            WHERE work_instance_id = ?
            """,
            (reason_code, started_at_utc, work_instance_id),
        )
    updated = get_work_instance(connection, work_instance_id)
    return _updated_work_result(updated)


def succeed_work_instance(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    succeeded_at_utc: str,
    reason_code: str | None = None,
) -> UpdatedWorkInstance:
    """Mark in-progress work succeeded."""

    require_utc_z("succeeded_at_utc", succeeded_at_utc)
    row = _get_work_for_outcome(connection, work_instance_id)
    if row["status"] != WorkStatus.IN_PROGRESS.value:
        raise SpineValidationError("work_outcome_rejected", f"work is not in progress: {work_instance_id}")
    return _set_work_outcome(
        connection,
        work_instance_id=work_instance_id,
        status=WorkStatus.SUCCEEDED,
        updated_at_utc=succeeded_at_utc,
        reason_code=reason_code,
        next_attempt_at_utc=None,
    )


def fail_work_instance(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    failed_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Mark eligible or in-progress work failed with a durable reason."""

    require_utc_z("failed_at_utc", failed_at_utc)
    _require_reason(reason_code)
    row = _get_work_for_outcome(connection, work_instance_id)
    if row["status"] not in {WorkStatus.ELIGIBLE.value, WorkStatus.IN_PROGRESS.value}:
        raise SpineValidationError("work_outcome_rejected", f"work cannot fail from status {row['status']}")
    return _set_work_outcome(
        connection,
        work_instance_id=work_instance_id,
        status=WorkStatus.FAILED,
        updated_at_utc=failed_at_utc,
        reason_code=reason_code,
        next_attempt_at_utc=None,
    )


def retry_work_instance(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    next_attempt_at_utc: str,
    updated_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Return in-progress work to eligible state for a later retry."""

    require_utc_z("next_attempt_at_utc", next_attempt_at_utc)
    require_utc_z("updated_at_utc", updated_at_utc)
    _require_reason(reason_code)
    row = _get_work_for_outcome(connection, work_instance_id)
    if row["status"] != WorkStatus.IN_PROGRESS.value:
        raise SpineValidationError("work_outcome_rejected", f"work is not in progress: {work_instance_id}")
    return _set_work_outcome(
        connection,
        work_instance_id=work_instance_id,
        status=WorkStatus.ELIGIBLE,
        updated_at_utc=updated_at_utc,
        reason_code=reason_code,
        next_attempt_at_utc=next_attempt_at_utc,
    )


def cancel_work_instance(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    cancelled_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Cancel eligible or in-progress work with a durable reason."""

    require_utc_z("cancelled_at_utc", cancelled_at_utc)
    _require_reason(reason_code)
    row = _get_work_for_outcome(connection, work_instance_id)
    if row["status"] not in {WorkStatus.ELIGIBLE.value, WorkStatus.IN_PROGRESS.value}:
        raise SpineValidationError("work_outcome_rejected", f"work cannot be cancelled from status {row['status']}")
    return _set_work_outcome(
        connection,
        work_instance_id=work_instance_id,
        status=WorkStatus.CANCELLED,
        updated_at_utc=cancelled_at_utc,
        reason_code=reason_code,
        next_attempt_at_utc=None,
    )


def assert_work_instance_not_stale(connection: sqlite3.Connection, work_instance_id: str) -> None:
    row = connection.execute(
        """
        SELECT w.item_version, w.work_kind, w.notification_policy_id,
               i.current_version, i.status AS item_status, i.item_type,
               p.status AS notification_policy_status,
               ed.event_status, td.task_status
        FROM work_instances AS w
        JOIN coordination_items AS i ON i.item_id = w.item_id
        LEFT JOIN notification_policies AS p
          ON p.policy_id = w.notification_policy_id
         AND p.item_id = w.item_id
         AND p.version = w.notification_policy_item_version
        LEFT JOIN event_details AS ed
          ON i.item_type = 'event'
         AND ed.item_id = i.item_id
         AND ed.version = i.current_version
        LEFT JOIN task_details AS td
          ON i.item_type = 'task'
         AND td.item_id = i.item_id
         AND td.version = i.current_version
        WHERE w.work_instance_id = ?
        """,
        (work_instance_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("work_instance_not_found", f"work instance not found: {work_instance_id}")

    is_policy_reminder = (
        row["work_kind"] == WorkKind.NOTIFICATION_REMINDER.value
        and row["notification_policy_id"] is not None
    )
    if is_policy_reminder:
        if row["item_status"] != ItemStatus.ACTIVE.value:
            _raise_stale_work(work_instance_id, "item is not active")
        if row["notification_policy_status"] != NotificationPolicyStatus.ACTIVE.value:
            _raise_stale_work(work_instance_id, "notification policy is not active")
        if row["item_type"] == ItemType.EVENT.value and row["event_status"] != EventStatus.SCHEDULED.value:
            _raise_stale_work(work_instance_id, "event is not scheduled")
        if row["item_type"] == ItemType.TASK.value and row["task_status"] != TaskStatus.OPEN.value:
            _raise_stale_work(work_instance_id, "task is not open")
        return

    if row["item_version"] != row["current_version"]:
        _raise_stale_work(work_instance_id, "bound item version is not current")


def get_work_instance(connection: sqlite3.Connection, work_instance_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM work_instances WHERE work_instance_id = ?",
        (work_instance_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("work_instance_not_found", f"work instance not found: {work_instance_id}")
    return dict(row)


def _get_work_for_outcome(connection: sqlite3.Connection, work_instance_id: str) -> dict[str, object]:
    assert_work_instance_not_stale(connection, work_instance_id)
    return get_work_instance(connection, work_instance_id)


def _set_work_outcome(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    status: WorkStatus,
    updated_at_utc: str,
    reason_code: str | None,
    next_attempt_at_utc: str | None,
) -> UpdatedWorkInstance:
    with connection:
        connection.execute(
            """
            UPDATE work_instances
            SET status = ?,
                next_attempt_at_utc = ?,
                reason_code = ?,
                updated_at_utc = ?
            WHERE work_instance_id = ?
            """,
            (status.value, next_attempt_at_utc, reason_code, updated_at_utc, work_instance_id),
        )
    updated = get_work_instance(connection, work_instance_id)
    return _updated_work_result(updated)


def _updated_work_result(row: dict[str, object]) -> UpdatedWorkInstance:
    attempt_count = row["attempt_count"]
    if not isinstance(attempt_count, int):
        raise SpineValidationError("work_instance_rejected", "attempt_count must be an integer")
    return UpdatedWorkInstance(
        work_instance_id=str(row["work_instance_id"]),
        status=str(row["status"]),
        attempt_count=attempt_count,
    )


def _require_reason(reason_code: str) -> None:
    if not isinstance(reason_code, str) or len(reason_code) == 0:
        raise SpineValidationError("work_outcome_rejected", "reason_code must be a non-empty string")


def _raise_stale_work(work_instance_id: str, reason: str) -> None:
    raise SpineValidationError(
        "stale_work_instance",
        f"work instance is not processable ({reason}): {work_instance_id}",
    )
