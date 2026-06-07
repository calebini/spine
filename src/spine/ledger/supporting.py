"""Version-scoped supporting-set workflows for ledger items."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import (
    TemporalAnchorInput,
    copy_id,
    enum_value,
    insert_temporal_anchor,
    new_id,
    require_non_empty,
)
from spine.models.enums import (
    ItemLocationRole,
    ItemSubjectRole,
    LocationKind,
    NotificationPolicyStatus,
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
class NotificationPolicyInput:
    """Input row for inert durable notification intent."""

    recipient_subject_id: str
    trigger_anchor: TemporalAnchorInput | None = None
    trigger_anchor_id: str | None = None
    policy_id: str | None = None
    channel_preference_ref: str | None = None
    quiet_hours_policy_ref: str | None = None
    status: NotificationPolicyStatus | str = NotificationPolicyStatus.ACTIVE
    created_at_utc: str | None = None


def insert_supporting_sets(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    default_created_at_utc: str,
    item_locations: tuple[ItemLocationInput, ...],
    subject_roles: tuple[ItemSubjectRoleInput, ...],
    notification_policies: tuple[NotificationPolicyInput, ...],
) -> None:
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
    for policy in notification_policies:
        insert_notification_policy(
            connection,
            item_id=item_id,
            version=version,
            policy=policy,
            default_created_at_utc=default_created_at_utc,
        )


def copy_forward_supporting_sets(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    previous_version: int,
    next_version: int,
    created_at_utc: str,
) -> None:
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

    for row in connection.execute(
        """
        SELECT policy_id, recipient_subject_id, channel_preference_ref, trigger_anchor_id,
               quiet_hours_policy_ref, status
        FROM notification_policies
        WHERE item_id = ? AND version = ?
        ORDER BY policy_id
        """,
        (item_id, previous_version),
    ):
        connection.execute(
            """
            INSERT INTO notification_policies (
              policy_id, item_id, version, recipient_subject_id, channel_preference_ref,
              trigger_anchor_id, quiet_hours_policy_ref, status, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                copy_id(row["policy_id"], next_version),
                item_id,
                next_version,
                row["recipient_subject_id"],
                row["channel_preference_ref"],
                row["trigger_anchor_id"],
                row["quiet_hours_policy_ref"],
                row["status"],
                created_at_utc,
            ),
        )


def current_locations(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
          il.item_location_id, il.item_id, il.version, il.location_id, il.role,
          il.created_at_utc,
          l.label, l.kind, l.address_text, l.latitude, l.longitude, l.timezone,
          l.provider_ref, l.metadata_json
        FROM item_locations AS il
        JOIN locations AS l ON l.location_id = il.location_id
        WHERE il.item_id = ? AND il.version = ?
        ORDER BY il.item_location_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def current_subject_roles(connection: sqlite3.Connection, *, item_id: str, version: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT *
        FROM item_subject_roles
        WHERE item_id = ? AND version = ?
        ORDER BY item_subject_role_id
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
    rows = connection.execute(
        """
        SELECT *
        FROM notification_policies
        WHERE item_id = ? AND version = ?
        ORDER BY policy_id
        """,
        (item_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


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
            item_location.created_at_utc or default_created_at_utc,
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


def insert_notification_policy(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    version: int,
    policy: NotificationPolicyInput,
    default_created_at_utc: str,
) -> None:
    trigger_anchor_id = policy.trigger_anchor_id
    if policy.trigger_anchor is not None:
        trigger_anchor_id = policy.trigger_anchor.anchor_id or trigger_anchor_id or new_id("anchor")
        insert_temporal_anchor(
            connection,
            anchor=policy.trigger_anchor,
            anchor_id=trigger_anchor_id,
            default_created_at_utc=default_created_at_utc,
        )
    if trigger_anchor_id is None:
        raise SpineValidationError("invalid_notification_policy", "notification policy requires a trigger anchor")
    connection.execute(
        """
        INSERT INTO notification_policies (
          policy_id, item_id, version, recipient_subject_id, channel_preference_ref,
          trigger_anchor_id, quiet_hours_policy_ref, status, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy.policy_id or new_id("policy"),
            item_id,
            version,
            policy.recipient_subject_id,
            policy.channel_preference_ref,
            trigger_anchor_id,
            policy.quiet_hours_policy_ref,
            enum_value(policy.status),
            policy.created_at_utc or default_created_at_utc,
        ),
    )
