"""Generated work-instance workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import enum_value, new_id, require_non_empty
from spine.models.enums import GenerationSourceKind, WorkKind, WorkStatus


@dataclass(frozen=True)
class CreatedWorkInstance:
    """Result of creating a generated work row."""

    work_instance_id: str
    item_id: str
    item_version: int


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
    require_non_empty("eligible_at_utc", eligible_at_utc)
    require_non_empty("created_at_utc", created_at_utc)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO work_instances (
                  work_instance_id, item_id, item_version, notification_policy_id,
                  notification_policy_item_version, source_work_instance_id,
                  generation_source_kind, generation_source_ref, work_subject_ref,
                  work_kind, purpose_detail_ref, policy_basis_ref, eligible_at_utc,
                  status, attempt_count, next_attempt_at_utc, reason_code, created_at_utc,
                  updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_instance_id,
                    item_id,
                    item_version,
                    notification_policy_id,
                    notification_policy_item_version,
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


def assert_work_instance_not_stale(connection: sqlite3.Connection, work_instance_id: str) -> None:
    row = connection.execute(
        """
        SELECT w.item_version, i.current_version
        FROM work_instances AS w
        JOIN coordination_items AS i ON i.item_id = w.item_id
        WHERE w.work_instance_id = ?
        """,
        (work_instance_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("work_instance_not_found", f"work instance not found: {work_instance_id}")
    if row["item_version"] != row["current_version"]:
        raise SpineValidationError("stale_work_instance", f"work instance is stale: {work_instance_id}")


def get_work_instance(connection: sqlite3.Connection, work_instance_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM work_instances WHERE work_instance_id = ?",
        (work_instance_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("work_instance_not_found", f"work instance not found: {work_instance_id}")
    return dict(row)
