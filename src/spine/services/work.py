"""Work generation and eligibility services."""

from __future__ import annotations

import sqlite3

from spine.core import SpineValidationError
from spine.ledger import (
    UpdatedWorkInstance,
    assert_work_instance_not_stale,
    cancel_work_instance,
    fail_work_instance,
    get_work_instance,
    retry_work_instance,
    start_work_instance,
    succeed_work_instance,
)
from spine.ledger.common import require_utc_z


def list_eligible_work(connection: sqlite3.Connection, *, now_utc: str, limit: int | None = None) -> list[dict[str, object]]:
    """Return eligible, processable work rows ordered by eligibility time."""

    require_utc_z("now_utc", now_utc)
    if limit == 0:
        return []
    rows = connection.execute(
        """
        SELECT w.*
        FROM work_instances AS w
        WHERE w.status = 'eligible'
          AND w.eligible_at_utc <= ?
          AND (w.next_attempt_at_utc IS NULL OR w.next_attempt_at_utc <= ?)
        ORDER BY w.eligible_at_utc, w.work_instance_id
        """,
        (now_utc, now_utc),
    ).fetchall()
    processable: list[dict[str, object]] = []
    for row in rows:
        try:
            assert_work_instance_not_stale(connection, str(row["work_instance_id"]))
        except SpineValidationError as exc:
            if exc.code == "stale_work_instance":
                continue
            raise
        processable.append(dict(row))
        if limit is not None and limit >= 0 and len(processable) >= limit:
            break
    return processable


def require_processable_work(connection: sqlite3.Connection, work_instance_id: str) -> dict[str, object]:
    """Return a work row only after work processability safety has passed."""

    assert_work_instance_not_stale(connection, work_instance_id)
    return get_work_instance(connection, work_instance_id)


def start_work(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    started_at_utc: str,
    reason_code: str | None = None,
) -> UpdatedWorkInstance:
    """Mark eligible work in progress after processability safety passes."""

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
