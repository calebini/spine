"""Private bounded role readback, not a public or permission-enforcing surface."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core.errors import SpineValidationError
from spine.core.people import MAX_ROLE_ROWS, RoleAssociation, managed_role, people_id


@dataclass(frozen=True)
class PeopleSnapshot:
    item_id: str
    item_type: str
    item_version: int
    current_version: int
    associations: tuple[RoleAssociation, ...]


def read_people_snapshot(connection: sqlite3.Connection, *, item_id: str, version: int | None = None) -> PeopleSnapshot:
    """One statement binds current metadata and exact-version roles without writes.

    The caller must supply admitted identity/item access and a request budget.
    No subject labels, membership resolution, lifecycle write checks or permission
    decision is provided by this primitive. Read at most one over-limit sentinel;
    never silently truncate a managed set or ignore excess unmanaged rows.
    """
    people_id(item_id)
    if version is not None and (type(version) is not int or not 1 <= version <= 9223372036854775807):
        raise SpineValidationError("invalid_request:version", "Invalid people version.")
    rows = connection.execute(
        """SELECT i.item_id, i.item_type, i.current_version, v.version,
                  r.item_subject_role_id, r.subject_id, r.role, r.status
           FROM coordination_items AS i
           JOIN coordination_item_versions AS v
             ON v.item_id = i.item_id AND v.version = COALESCE(?, i.current_version)
           LEFT JOIN item_subject_roles AS r ON r.item_id = v.item_id AND r.version = v.version
           WHERE i.item_id = ?
           ORDER BY r.role COLLATE BINARY, r.subject_id COLLATE BINARY
           LIMIT ?""",
        (version, item_id, MAX_ROLE_ROWS + 1),
    ).fetchall()
    if not rows:
        raise SpineValidationError("referenced_row_not_found:item_id", "People version unavailable.")
    role = managed_role(rows[0]["item_type"])
    if len(rows) > MAX_ROLE_ROWS:
        raise SpineValidationError("capacity_exceeded:people", "People role set exceeds its limit.")
    associations = tuple(RoleAssociation(
        item_subject_role_id=row["item_subject_role_id"], subject_id=row["subject_id"],
        role=row["role"], status=row["status"],
    ) for row in rows if row["role"] == role)
    return PeopleSnapshot(item_id=rows[0]["item_id"], item_type=rows[0]["item_type"],
        item_version=rows[0]["version"], current_version=rows[0]["current_version"], associations=associations)
