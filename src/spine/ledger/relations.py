"""Coordination item relation workflows."""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext

from spine.core import SpineValidationError
from spine.ledger.common import enum_value, new_id, require_non_empty, require_utc_z
from spine.models.enums import RelationStatus, RelationType


def create_item_relation(
    connection: sqlite3.Connection,
    *,
    relation_id: str | None = None,
    source_item_id: str,
    target_item_id: str,
    relation_type: RelationType | str,
    created_at_utc: str,
    created_by_subject_id: str,
    relation_status: RelationStatus | str = RelationStatus.ACTIVE,
    metadata_json: str | None = None,
    manage_transaction: bool = True,
) -> str:
    """Create a stored MVP item relation."""

    relation_id = relation_id or new_id("relation")
    require_non_empty("relation_id", relation_id)
    require_non_empty("source_item_id", source_item_id)
    require_non_empty("target_item_id", target_item_id)
    require_utc_z("created_at_utc", created_at_utc)
    require_non_empty("created_by_subject_id", created_by_subject_id)
    relation_type_value = enum_value(relation_type)
    if relation_type_value in {"blocks", "contains"}:
        raise SpineValidationError("reserved_relation_type", f"relation_type is query-only: {relation_type_value}")
    try:
        with connection if manage_transaction else nullcontext():
            connection.execute(
                """
                INSERT INTO coordination_item_relations (
                  relation_id, source_item_id, target_item_id, relation_type, relation_status,
                  created_at_utc, created_by_subject_id, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relation_id,
                    source_item_id,
                    target_item_id,
                    relation_type_value,
                    enum_value(relation_status),
                    created_at_utc,
                    created_by_subject_id,
                    metadata_json,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("item_relation_rejected", str(exc)) from exc
    return relation_id


def get_active_relations(
    connection: sqlite3.Connection,
    *,
    source_item_id: str,
    relation_type: RelationType | str | None = None,
) -> list[dict[str, object]]:
    """Return active stored relations from an item."""

    if relation_type is None:
        rows = connection.execute(
            """
            SELECT *
            FROM coordination_item_relations
            WHERE source_item_id = ? AND relation_status = 'active'
            ORDER BY relation_id
            """,
            (source_item_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT *
            FROM coordination_item_relations
            WHERE source_item_id = ? AND relation_status = 'active' AND relation_type = ?
            ORDER BY relation_id
            """,
            (source_item_id, enum_value(relation_type)),
        ).fetchall()
    return [dict(row) for row in rows]


def get_derived_relations(
    connection: sqlite3.Connection,
    *,
    source_item_id: str,
    relation_type: str,
) -> list[dict[str, object]]:
    """Return derived query-only relation aliases for an item."""

    if relation_type == "blocks":
        stored_type = RelationType.DEPENDS_ON.value
    elif relation_type == "contains":
        stored_type = RelationType.PART_OF.value
    else:
        raise SpineValidationError("unsupported_derived_relation", f"unsupported derived relation: {relation_type}")
    rows = connection.execute(
        """
        SELECT *
        FROM coordination_item_relations
        WHERE target_item_id = ? AND relation_status = 'active' AND relation_type = ?
        ORDER BY relation_id
        """,
        (source_item_id, stored_type),
    ).fetchall()
    return [
        {
            "source_item_id": source_item_id,
            "target_item_id": row["source_item_id"],
            "relation_type": relation_type,
            "stored_relation_id": row["relation_id"],
            "stored_relation_type": row["relation_type"],
        }
        for row in rows
    ]
