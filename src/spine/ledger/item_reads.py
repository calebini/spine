"""Historical item and anchor hydration shared by commands and temporal bindings."""

from __future__ import annotations

import sqlite3
from typing import Any

from spine.core.errors import SpineValidationError
from spine.ledger.supporting import current_locations, current_notification_policies, current_subject_roles


def hydrated_item_at_version(connection: sqlite3.Connection, item_id: str, version: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
          i.item_id, i.item_type, i.status, i.created_at_utc, i.archived_at_utc,
          v.title, v.summary, v.intent_hash, v.normalized_fields_hash, v.source_ref,
          v.created_at_utc AS version_created_at_utc,
          v.created_by_subject_id
        FROM coordination_items AS i
        JOIN coordination_item_versions AS v
          ON v.item_id = i.item_id
         AND v.version = ?
        WHERE i.item_id = ?
        """,
        (version, item_id),
    ).fetchone()
    if row is None:
        raise SpineValidationError("item_not_found", f"coordination item version not found: {item_id} v{version}")
    detail = detail_at_version(connection, item_id=item_id, item_type=row["item_type"], version=version)
    for key in ("start_anchor_id", "end_anchor_id", "due_anchor_id", "defer_until_anchor_id"):
        if detail.get(key) is not None:
            detail[key.removesuffix("_id")] = anchor_row(connection, str(detail[key]), field=key)
    return {
        "item_id": row["item_id"],
        "item_type": row["item_type"],
        "current_version": version,
        "status": row["status"],
        "created_at_utc": row["created_at_utc"],
        "updated_at_utc": row["version_created_at_utc"],
        "archived_at_utc": row["archived_at_utc"],
        "version": {
            "version": str(version),
            "title": row["title"],
            "summary": row["summary"],
            "intent_hash": row["intent_hash"],
            "normalized_fields_hash": row["normalized_fields_hash"],
            "source_ref": row["source_ref"],
            "created_at_utc": row["version_created_at_utc"],
            "created_by_subject_id": row["created_by_subject_id"],
        },
        "detail": detail,
        "locations": current_locations(connection, item_id=item_id, version=version),
        "subject_roles": current_subject_roles(connection, item_id=item_id, version=version),
        "notification_policies": current_notification_policies(connection, item_id=item_id, version=version),
    }


def detail_at_version(connection: sqlite3.Connection, *, item_id: str, item_type: str, version: int) -> dict[str, Any]:
    if item_type == "event":
        row = connection.execute(
            """
            SELECT event_status, all_day, start_anchor_id, end_anchor_id, visibility,
                   attendance_policy_ref
            FROM event_details
            WHERE item_id = ? AND version = ?
            """,
            (item_id, version),
        ).fetchone()
    elif item_type == "task":
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
        raise SpineValidationError("item_not_found", f"coordination item detail not found: {item_id} v{version}")
    return dict(row)


def anchor_row(connection: sqlite3.Connection, anchor_id: str, *, field: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM temporal_anchors WHERE anchor_id = ?", (anchor_id,)).fetchone()
    if row is None:
        raise SpineValidationError(f"anchor_not_found:{field}", f"anchor not found: {anchor_id}")
    result = {"anchor_id": row["anchor_id"], "anchor_kind": row["anchor_kind"], "created_at_utc": row["created_at_utc"]}
    for key in (
        "local_date",
        "local_time",
        "timezone",
        "timezone_database_version",
        "utc_instant",
        "window_start_utc",
        "window_end_utc",
        "source",
    ):
        if row[key] is not None:
            result[key] = row[key]
    recurrence = connection.execute(
        "SELECT recurrence_set_id FROM recurrence_sets WHERE seed_anchor_id = ?",
        (anchor_id,),
    ).fetchone()
    if recurrence is not None:
        result["recurrence_set_id"] = recurrence["recurrence_set_id"]
    return result
