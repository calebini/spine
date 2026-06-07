"""Work generation and eligibility services."""

from __future__ import annotations

import sqlite3

from spine.core import SpineValidationError
from spine.ledger import (
    CreatedWorkInstance,
    UpdatedWorkInstance,
    assert_work_instance_not_stale,
    cancel_work_instance,
    create_work_instance,
    fail_work_instance,
    get_work_instance,
    retry_work_instance,
    start_work_instance,
    succeed_work_instance,
)


def generate_notification_reminder_work(
    connection: sqlite3.Connection,
    *,
    notification_policy_id: str,
    eligible_at_utc: str,
    created_at_utc: str,
    work_instance_id: str | None = None,
) -> CreatedWorkInstance:
    """Generate durable reminder work from a notification policy without delivery."""

    policy = _get_notification_policy(connection, notification_policy_id)
    return create_work_instance(
        connection,
        work_instance_id=work_instance_id,
        item_id=policy["item_id"],
        item_version=policy["version"],
        notification_policy_id=policy["policy_id"],
        notification_policy_item_version=policy["version"],
        generation_source_kind="notification_policy",
        generation_source_ref=policy["policy_id"],
        work_subject_ref=policy["recipient_subject_id"],
        policy_basis_ref=policy["policy_id"],
        eligible_at_utc=eligible_at_utc,
        created_at_utc=created_at_utc,
    )


def list_eligible_work(connection: sqlite3.Connection, *, now_utc: str, limit: int | None = None) -> list[dict[str, object]]:
    """Return eligible, non-stale work rows ordered by eligibility time."""

    sql = """
        SELECT w.*
        FROM work_instances AS w
        JOIN coordination_items AS i ON i.item_id = w.item_id
        WHERE w.status = 'eligible'
          AND w.eligible_at_utc <= ?
          AND (w.next_attempt_at_utc IS NULL OR w.next_attempt_at_utc <= ?)
          AND i.current_version = w.item_version
        ORDER BY w.eligible_at_utc, w.work_instance_id
    """
    params: tuple[object, ...]
    if limit is not None:
        sql += " LIMIT ?"
        params = (now_utc, now_utc, limit)
    else:
        params = (now_utc, now_utc)
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def require_processable_work(connection: sqlite3.Connection, work_instance_id: str) -> dict[str, object]:
    """Return a work row only after stale-work safety has passed."""

    assert_work_instance_not_stale(connection, work_instance_id)
    return get_work_instance(connection, work_instance_id)


def start_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    started_at_utc: str,
    reason_code: str | None = None,
) -> UpdatedWorkInstance:
    """Mark eligible work in progress after stale-work safety passes."""

    return start_work_instance(
        connection,
        work_instance_id=work_instance_id,
        started_at_utc=started_at_utc,
        reason_code=reason_code,
    )


def succeed_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    succeeded_at_utc: str,
    reason_code: str | None = None,
) -> UpdatedWorkInstance:
    """Mark in-progress work succeeded."""

    return succeed_work_instance(
        connection,
        work_instance_id=work_instance_id,
        succeeded_at_utc=succeeded_at_utc,
        reason_code=reason_code,
    )


def fail_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    failed_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Mark eligible or in-progress work failed."""

    return fail_work_instance(
        connection,
        work_instance_id=work_instance_id,
        failed_at_utc=failed_at_utc,
        reason_code=reason_code,
    )


def retry_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    next_attempt_at_utc: str,
    updated_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Return in-progress work to eligible state for a later retry."""

    return retry_work_instance(
        connection,
        work_instance_id=work_instance_id,
        next_attempt_at_utc=next_attempt_at_utc,
        updated_at_utc=updated_at_utc,
        reason_code=reason_code,
    )


def cancel_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    cancelled_at_utc: str,
    reason_code: str,
) -> UpdatedWorkInstance:
    """Cancel eligible or in-progress work."""

    return cancel_work_instance(
        connection,
        work_instance_id=work_instance_id,
        cancelled_at_utc=cancelled_at_utc,
        reason_code=reason_code,
    )


def _get_notification_policy(connection: sqlite3.Connection, policy_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM notification_policies WHERE policy_id = ?",
        (policy_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("notification_policy_not_found", f"notification policy not found: {policy_id}")
    return dict(row)
