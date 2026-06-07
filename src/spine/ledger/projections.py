"""External projection record workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import enum_value, new_id, require_non_empty
from spine.models.enums import ProjectionStatus


@dataclass(frozen=True)
class CreatedProjection:
    """Result of creating an external projection record."""

    projection_id: str
    item_id: str


def create_external_projection(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    adapter_name: str,
    external_ref: str,
    projection_status: ProjectionStatus | str,
    updated_at_utc: str,
    projection_id: str | None = None,
    last_projected_version: int | None = None,
    last_attempt_id: str | None = None,
    stale_reason: str | None = None,
) -> CreatedProjection:
    """Create an external mirror-state record without invoking an adapter."""

    projection_id = projection_id or new_id("projection")
    require_non_empty("projection_id", projection_id)
    require_non_empty("item_id", item_id)
    require_non_empty("adapter_name", adapter_name)
    require_non_empty("external_ref", external_ref)
    require_non_empty("updated_at_utc", updated_at_utc)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO external_projections (
                  projection_id, item_id, adapter_name, external_ref, projection_status,
                  last_projected_version, last_attempt_id, stale_reason, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    item_id,
                    adapter_name,
                    external_ref,
                    enum_value(projection_status),
                    last_projected_version,
                    last_attempt_id,
                    stale_reason,
                    updated_at_utc,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("external_projection_rejected", str(exc)) from exc
    return CreatedProjection(projection_id=projection_id, item_id=item_id)


def get_external_projection(connection: sqlite3.Connection, projection_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM external_projections WHERE projection_id = ?",
        (projection_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("external_projection_not_found", f"projection not found: {projection_id}")
    return dict(row)
