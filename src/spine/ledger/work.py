"""Generated work-instance workflows."""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from dataclasses import dataclass
from typing import NoReturn

from spine.core import SpineValidationError
from spine.core.schedule import resolve_local_instant
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
    notification_intent_id: str | None = None,
    notification_opportunity_id: str | None = None,
    normalized_notification_schedule_hash: str | None = None,
    occurrence_provenance_id: str | None = None,
    target_anchor_role: str | None = None,
    application_scope: str | None = None,
    target_scheduled_fact: str | None = None,
    target_at_utc: str | None = None,
    occurrence_key: str | None = None,
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
    manage_transaction: bool = True,
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
        with connection if manage_transaction else nullcontext():
            connection.execute(
                """
                INSERT INTO work_instances (
                  work_instance_id, item_id, item_version, notification_policy_id,
                  notification_policy_item_version, notification_intent_id,
                  notification_opportunity_id, normalized_notification_schedule_hash,
                  occurrence_provenance_id, target_anchor_role, application_scope,
                  target_scheduled_fact, target_at_utc, occurrence_key,
                  delivery_target_id, source_work_instance_id,
                  generation_source_kind, generation_source_ref, work_subject_ref,
                  work_kind, purpose_detail_ref, policy_basis_ref, eligible_at_utc,
                  status, attempt_count, next_attempt_at_utc, reason_code, created_at_utc,
                  updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_instance_id,
                    item_id,
                    item_version,
                    notification_policy_id,
                    notification_policy_item_version,
                    notification_intent_id,
                    notification_opportunity_id,
                    normalized_notification_schedule_hash,
                    occurrence_provenance_id,
                    target_anchor_role,
                    application_scope,
                    target_scheduled_fact,
                    target_at_utc,
                    occurrence_key,
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
    require_fresh: bool = True,
) -> UpdatedWorkInstance:
    """Cancel eligible or in-progress work with a durable reason."""

    require_utc_z("cancelled_at_utc", cancelled_at_utc)
    _require_reason(reason_code)
    row = _get_work_for_outcome(connection, work_instance_id) if require_fresh else get_work_instance(connection, work_instance_id)
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
        SELECT w.*, i.current_version, i.status AS item_status, i.item_type,
               ed.event_status, td.task_status
        FROM work_instances AS w
        JOIN coordination_items AS i ON i.item_id = w.item_id
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

    is_scheduled_notification = row["notification_opportunity_id"] is not None
    if is_scheduled_notification:
        if row["item_status"] != ItemStatus.ACTIVE.value:
            _raise_stale_work(work_instance_id, "item is not active")
        if row["item_type"] == ItemType.EVENT.value and row["event_status"] != EventStatus.SCHEDULED.value:
            _raise_stale_work(work_instance_id, "event is not scheduled")
        if row["item_type"] == ItemType.TASK.value and row["task_status"] != TaskStatus.OPEN.value:
            _raise_stale_work(work_instance_id, "task is not open")
        policy = connection.execute(
            """
            SELECT p.*, dt.status AS delivery_target_status,
                   dt.channel AS delivery_target_channel,
                   dt.owner_kind AS delivery_target_owner_kind,
                   dt.owner_subject_id AS delivery_target_owner_subject_id,
                   dt.owner_group_id AS delivery_target_owner_group_id
            FROM notification_policies AS p
            JOIN delivery_targets AS dt ON dt.delivery_target_id = p.delivery_target_id
            WHERE p.item_id = ? AND p.version = ?
              AND (p.policy_id = ? OR p.source_notification_policy_id = ?)
            ORDER BY CASE WHEN p.policy_id = ? THEN 0 ELSE 1 END
            """,
            (
                row["item_id"],
                row["current_version"],
                row["notification_policy_id"],
                row["notification_policy_id"],
                row["notification_policy_id"],
            ),
        ).fetchone()
        if policy is None or policy["status"] != NotificationPolicyStatus.ACTIVE.value:
            _raise_stale_work(work_instance_id, "current notification intent is not active")
        if policy["normalized_notification_schedule_hash"] != row["normalized_notification_schedule_hash"]:
            _raise_stale_work(work_instance_id, "notification schedule changed")
        if (
            policy["delivery_target_id"] != row["delivery_target_id"]
            or policy["delivery_target_status"] != "active"
            or policy["channel"] != policy["delivery_target_channel"]
        ):
            _raise_stale_work(work_instance_id, "notification route changed or became inactive")
        if (
            policy["target_anchor_role"] != row["target_anchor_role"]
            or policy["application_scope"] != row["application_scope"]
        ):
            _raise_stale_work(work_instance_id, "notification target binding changed")
        if policy["recipient_kind"] == "subject":
            owner_matches = (
                policy["delivery_target_owner_kind"] == "subject"
                and policy["recipient_subject_id"] == policy["delivery_target_owner_subject_id"]
            )
        else:
            owner_matches = (
                policy["delivery_target_owner_kind"] == "subject_group"
                and policy["recipient_group_id"] == policy["delivery_target_owner_group_id"]
            )
        if not owner_matches:
            _raise_stale_work(work_instance_id, "notification recipient route ownership changed")

        if row["application_scope"] == "item":
            scheduled_fact, target_at_utc = _current_item_target_snapshot(connection, row)
            if (
                row["target_scheduled_fact"] != scheduled_fact
                or row["target_at_utc"] != target_at_utc
                or row["occurrence_key"] is not None
                or row["occurrence_provenance_id"] is not None
            ):
                _raise_stale_work(work_instance_id, "item target changed")
        else:
            provenance = connection.execute(
                """
                SELECT op.*, rr.source_item_version AS revision_item_version
                FROM occurrence_provenance AS op
                JOIN recurrence_revisions AS rr
                  ON rr.recurrence_revision_id = op.recurrence_revision_id
                WHERE op.occurrence_provenance_id = ?
                """,
                (row["occurrence_provenance_id"],),
            ).fetchone()
            latest = connection.execute(
                """
                SELECT rr.recurrence_revision_id, rr.normalized_recurrence_set_hash
                FROM recurrence_sets AS rs
                JOIN recurrence_revisions AS rr ON rr.recurrence_set_id = rs.recurrence_set_id
                WHERE rs.source_item_id = ? AND rr.source_item_version <= ?
                ORDER BY rr.source_item_version DESC, rr.revision_number DESC LIMIT 1
                """,
                (row["item_id"], row["current_version"]),
            ).fetchone()
            if (
                provenance is None
                or latest is None
                or provenance["management_status"] != "active"
                or provenance["actionable"] != 1
                or provenance["recurrence_revision_id"] != latest["recurrence_revision_id"]
                or provenance["normalized_recurrence_set_hash"] != latest["normalized_recurrence_set_hash"]
                or provenance["occurrence_key"] != row["occurrence_key"]
                or provenance["expressed_scheduled_fact"] != row["target_scheduled_fact"]
                or (provenance["timezone_utc_instant"] or (
                    provenance["expressed_scheduled_fact"]
                    if str(provenance["expressed_scheduled_fact"]).endswith("Z") else None
                )) != row["target_at_utc"]
            ):
                _raise_stale_work(work_instance_id, "recurrence occurrence changed or is not actionable")
        if row["item_type"] == ItemType.TASK.value:
            from spine.ledger.temporal_bindings import active_follow_binding_current

            if not active_follow_binding_current(connection, item_id=str(row["item_id"])):
                _raise_stale_work(work_instance_id, "active follow-source temporal binding is not current")
        return

    if row["item_version"] != row["current_version"]:
        _raise_stale_work(work_instance_id, "bound item version is not current")


def _current_item_target_snapshot(
    connection: sqlite3.Connection, work: sqlite3.Row
) -> tuple[str, str | None]:
    detail_table, anchor_column = (
        ("event_details", "start_anchor_id")
        if work["target_anchor_role"] == "event_start"
        else ("task_details", "due_anchor_id")
    )
    anchor = connection.execute(
        f"""
        SELECT a.* FROM {detail_table} AS d
        JOIN temporal_anchors AS a ON a.anchor_id = d.{anchor_column}
        WHERE d.item_id = ? AND d.version = ?
        """,
        (work["item_id"], work["current_version"]),
    ).fetchone()
    if anchor is None:
        _raise_stale_work(str(work["work_instance_id"]), "notification target anchor is unavailable")
    if anchor["anchor_kind"] == "instant_utc":
        return str(anchor["utc_instant"]), str(anchor["utc_instant"])
    if anchor["anchor_kind"] == "local_date":
        return str(anchor["local_date"]), None
    scheduled_fact = f"{anchor['local_date']}T{anchor['local_time']}"
    resolution = resolve_local_instant(
        scheduled_fact,
        timezone=str(anchor["timezone"]),
        timezone_database_version=str(anchor["timezone_database_version"]),
    )
    if resolution is None:
        _raise_stale_work(str(work["work_instance_id"]), "notification target local instant no longer resolves")
    return scheduled_fact, resolution.utc_instant


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


def _raise_stale_work(work_instance_id: str, reason: str) -> NoReturn:
    raise SpineValidationError(
        "stale_work_instance",
        f"work instance is not processable ({reason}): {work_instance_id}",
    )
