"""Version-scoped supporting-set workflows for ledger items."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import (
    copy_id,
    enum_value,
    new_id,
    require_non_empty,
    require_utc_z,
)
from spine.models.enums import (
    DeliveryTargetOwnerKind,
    DeliveryTargetStatus,
    ItemLocationRole,
    ItemSubjectRole,
    LocationKind,
    SubjectGroupKind,
)


@dataclass(frozen=True)
class LocationInput:
    """Input row for a first-class location."""

    label: str
    kind: LocationKind | str
    location_id: str | None = None
    address_text: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    timezone: str | None = None
    provider_ref: str | None = None
    metadata_json: str | None = None
    created_at_utc: str | None = None
    updated_at_utc: str | None = None


@dataclass(frozen=True)
class ItemLocationInput:
    """Input row for an item-version location role."""

    role: ItemLocationRole | str
    location: LocationInput | None = None
    location_id: str | None = None
    item_location_id: str | None = None
    created_at_utc: str | None = None


@dataclass(frozen=True)
class ItemSubjectRoleInput:
    """Input row for an item-version subject role."""

    subject_id: str
    role: ItemSubjectRole | str
    item_subject_role_id: str | None = None
    status: str = "active"
    created_at_utc: str | None = None


@dataclass(frozen=True)
class SubjectGroupInput:
    """Input row for a first-class subject group."""

    group_id: str
    group_kind: SubjectGroupKind | str
    display_name: str
    status: str = "active"
    created_at_utc: str | None = None
    updated_at_utc: str | None = None


@dataclass(frozen=True)
class DeliveryTargetInput:
    """Input row for a subject- or group-owned delivery endpoint."""

    delivery_target_id: str
    owner_kind: DeliveryTargetOwnerKind | str
    channel: str
    adapter_name: str
    target_ref: str
    owner_subject_id: str | None = None
    owner_group_id: str | None = None
    account_id: str | None = None
    display_name: str | None = None
    status: DeliveryTargetStatus | str = DeliveryTargetStatus.ACTIVE
    created_at_utc: str | None = None
    updated_at_utc: str | None = None


def insert_supporting_sets(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    default_created_at_utc: str,
    item_locations: tuple[ItemLocationInput, ...],
    subject_roles: tuple[ItemSubjectRoleInput, ...],
) -> None:
    require_utc_z("default_created_at_utc", default_created_at_utc)
    for item_location in item_locations:
        insert_item_location(
            connection,
            item_id=item_id,
            version=version,
            item_location=item_location,
            default_created_at_utc=default_created_at_utc,
        )
    for subject_role in subject_roles:
        insert_item_subject_role(
            connection,
            item_id=item_id,
            version=version,
            subject_role=subject_role,
            default_created_at_utc=default_created_at_utc,
        )

def copy_forward_supporting_sets(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    previous_version: int,
    next_version: int,
    created_at_utc: str,
    created_by_command_id: str,
) -> None:
    require_utc_z("created_at_utc", created_at_utc)
    for row in connection.execute(
        """
        SELECT item_location_id, location_id, role
        FROM item_locations
        WHERE item_id = ? AND version = ?
        ORDER BY item_location_id
        """,
        (item_id, previous_version),
    ):
        connection.execute(
            """
            INSERT INTO item_locations (
              item_location_id, item_id, version, location_id, role, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                copy_id(row["item_location_id"], next_version),
                item_id,
                next_version,
                row["location_id"],
                row["role"],
                created_at_utc,
            ),
        )

    for row in connection.execute(
        """
        SELECT item_subject_role_id, subject_id, role, status
        FROM item_subject_roles
        WHERE item_id = ? AND version = ?
        ORDER BY item_subject_role_id
        """,
        (item_id, previous_version),
    ):
        connection.execute(
            """
            INSERT INTO item_subject_roles (
              item_subject_role_id, item_id, version, subject_id, role, status, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                copy_id(row["item_subject_role_id"], next_version),
                item_id,
                next_version,
                row["subject_id"],
                row["role"],
                row["status"],
                created_at_utc,
            ),
        )

    from spine.ledger.notifications import copy_forward_notification_policies

    copy_forward_notification_policies(
        connection,
        item_id=item_id,
        previous_version=previous_version,
        next_version=next_version,
        created_at_utc=created_at_utc,
        created_by_command_id=created_by_command_id,
    )


def current_locations(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
          il.item_location_id, il.item_id, il.version, il.location_id, il.role,
          il.created_at_utc,
          l.label, l.kind, l.address_text, l.latitude, l.longitude, l.timezone,
          l.provider_ref, l.metadata_json,
          l.created_at_utc AS location_created_at_utc,
          l.updated_at_utc AS location_updated_at_utc
        FROM item_locations AS il
        JOIN locations AS l ON l.location_id = il.location_id
        WHERE il.item_id = ? AND il.version = ?
        ORDER BY il.item_location_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_subject_group(
    connection: sqlite3.Connection,
    *,
    group: SubjectGroupInput,
    default_created_at_utc: str,
) -> None:
    require_non_empty("group.group_id", group.group_id)
    require_non_empty("group.display_name", group.display_name)
    created_at_utc = group.created_at_utc or default_created_at_utc
    updated_at_utc = group.updated_at_utc or created_at_utc
    require_utc_z("group.created_at_utc", created_at_utc)
    require_utc_z("group.updated_at_utc", updated_at_utc)
    connection.execute(
        """
        INSERT INTO subject_groups (
          group_id, group_kind, display_name, status, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            group.group_id,
            enum_value(group.group_kind),
            group.display_name,
            enum_value(group.status),
            created_at_utc,
            updated_at_utc,
        ),
    )


def insert_delivery_target(
    connection: sqlite3.Connection,
    *,
    target: DeliveryTargetInput,
    default_created_at_utc: str,
) -> None:
    require_non_empty("target.delivery_target_id", target.delivery_target_id)
    require_non_empty("target.channel", target.channel)
    require_non_empty("target.adapter_name", target.adapter_name)
    require_non_empty("target.target_ref", target.target_ref)
    created_at_utc = target.created_at_utc or default_created_at_utc
    updated_at_utc = target.updated_at_utc or created_at_utc
    require_utc_z("target.created_at_utc", created_at_utc)
    require_utc_z("target.updated_at_utc", updated_at_utc)
    connection.execute(
        """
        INSERT INTO delivery_targets (
          delivery_target_id, owner_kind, owner_subject_id, owner_group_id, channel,
          adapter_name, account_id, target_ref, display_name, status, created_at_utc,
          updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target.delivery_target_id,
            enum_value(target.owner_kind),
            target.owner_subject_id,
            target.owner_group_id,
            target.channel,
            target.adapter_name,
            target.account_id,
            target.target_ref,
            target.display_name,
            enum_value(target.status),
            created_at_utc,
            updated_at_utc,
        ),
    )


def get_delivery_target(connection: sqlite3.Connection, delivery_target_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM delivery_targets WHERE delivery_target_id = ?",
        (delivery_target_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("delivery_target_not_found", f"delivery target not found: {delivery_target_id}")
    return dict(row)


def current_subject_roles(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT *
        FROM item_subject_roles
        WHERE item_id = ? AND version = ?
        ORDER BY role, created_at_utc, item_subject_role_id
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
    from spine.ledger.notifications import load_current_notification_policies

    current = connection.execute(
        "SELECT current_version FROM coordination_items WHERE item_id = ?", (item_id,)
    ).fetchone()
    if current is not None and current["current_version"] == version:
        return load_current_notification_policies(connection, item_id=item_id)
    return []


def insert_item_location(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    item_location: ItemLocationInput,
    default_created_at_utc: str,
) -> None:
    location_id = item_location.location_id
    if item_location.location is not None:
        location_id = item_location.location.location_id or location_id or new_id("location")
        insert_location(
            connection,
            location=item_location.location,
            location_id=location_id,
            default_created_at_utc=default_created_at_utc,
        )
    if location_id is None:
        raise SpineValidationError("invalid_item_location", "item location requires location or location_id")
    connection.execute(
        """
        INSERT INTO item_locations (
          item_location_id, item_id, version, location_id, role, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            item_location.item_location_id or new_id("item-location"),
            item_id,
            version,
            location_id,
            enum_value(item_location.role),
            require_utc_z("item_location.created_at_utc", item_location.created_at_utc or default_created_at_utc),
        ),
    )


def insert_location(
    connection: sqlite3.Connection,
    *,
    location: LocationInput,
    location_id: str,
    default_created_at_utc: str,
) -> None:
    require_non_empty("location.label", location.label)
    created_at_utc = location.created_at_utc or default_created_at_utc
    updated_at_utc = location.updated_at_utc or created_at_utc
    require_utc_z("location.created_at_utc", created_at_utc)
    require_utc_z("location.updated_at_utc", updated_at_utc)
    connection.execute(
        """
        INSERT INTO locations (
          location_id, label, kind, address_text, latitude, longitude, timezone,
          provider_ref, metadata_json, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            location_id,
            location.label,
            enum_value(location.kind),
            location.address_text,
            location.latitude,
            location.longitude,
            location.timezone,
            location.provider_ref,
            location.metadata_json,
            created_at_utc,
            updated_at_utc,
        ),
    )


def insert_item_subject_role(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    subject_role: ItemSubjectRoleInput,
    default_created_at_utc: str,
) -> None:
    require_non_empty("subject_role.subject_id", subject_role.subject_id)
    require_utc_z("subject_role.created_at_utc", subject_role.created_at_utc or default_created_at_utc)
    connection.execute(
        """
        INSERT INTO item_subject_roles (
          item_subject_role_id, item_id, version, subject_id, role, status, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subject_role.item_subject_role_id or new_id("item-subject-role"),
            item_id,
            version,
            subject_role.subject_id,
            enum_value(subject_role.role),
            enum_value(subject_role.status),
            subject_role.created_at_utc or default_created_at_utc,
        ),
    )


def replace_item_subject_roles(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    roles_to_replace: tuple[str, ...],
    subject_roles: tuple[ItemSubjectRoleInput, ...],
    default_created_at_utc: str,
) -> None:
    """Replace selected role kinds while preserving all other copied roles."""

    if not roles_to_replace:
        raise SpineValidationError("invalid_subject_roles", "roles_to_replace must not be empty")
    accepted_roles = {enum_value(role) for role in roles_to_replace}
    for subject_role in subject_roles:
        if enum_value(subject_role.role) not in accepted_roles:
            raise SpineValidationError(
                "invalid_subject_roles",
                "replacement subject role is outside roles_to_replace",
            )
    placeholders = ", ".join("?" for _ in accepted_roles)
    connection.execute(
        f"DELETE FROM item_subject_roles WHERE item_id = ? AND version = ? AND role IN ({placeholders})",
        (item_id, version, *sorted(accepted_roles)),
    )
    for subject_role in subject_roles:
        insert_item_subject_role(
            connection,
            item_id=item_id,
            version=version,
            subject_role=subject_role,
            default_created_at_utc=default_created_at_utc,
        )
