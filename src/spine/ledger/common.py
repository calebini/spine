"""Shared helpers for SQLite ledger workflows."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from spine.core import SpineValidationError
from spine.models.enums import TemporalAnchorKind

UTC_Z_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class TemporalAnchorInput:
    """Input row for a temporal anchor created with a ledger workflow."""

    anchor_kind: TemporalAnchorKind | str
    anchor_id: str | None = None
    local_date: str | None = None
    local_time: str | None = None
    timezone: str | None = None
    timezone_database_version: str | None = None
    utc_instant: str | None = None
    window_start_utc: str | None = None
    window_end_utc: str | None = None
    source: str | None = None
    created_at_utc: str | None = None


def insert_temporal_anchor(
    connection: sqlite3.Connection,
    *,
    anchor: TemporalAnchorInput,
    anchor_id: str,
    default_created_at_utc: str,
) -> None:
    require_non_empty("anchor_id", anchor_id)
    created_at_utc = anchor.created_at_utc or default_created_at_utc
    require_utc_z("anchor.created_at_utc", created_at_utc)
    require_optional_utc_z("anchor.utc_instant", anchor.utc_instant)
    require_optional_utc_z("anchor.window_start_utc", anchor.window_start_utc)
    require_optional_utc_z("anchor.window_end_utc", anchor.window_end_utc)
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, local_time, timezone, timezone_database_version, utc_instant,
          window_start_utc, window_end_utc, source, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            anchor_id,
            enum_value(anchor.anchor_kind),
            anchor.local_date,
            anchor.local_time,
            anchor.timezone,
            anchor.timezone_database_version,
            anchor.utc_instant,
            anchor.window_start_utc,
            anchor.window_end_utc,
            anchor.source,
            created_at_utc,
        ),
    )


def require_non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) == 0:
        raise SpineValidationError("invalid_item_create_input", f"{name} must be a non-empty string")


def require_utc_z(name: str, value: str) -> str:
    """Require Spine's canonical lexicographically sortable UTC timestamp string."""

    require_non_empty(name, value)
    if _UTC_Z_PATTERN.fullmatch(value) is None:
        raise SpineValidationError(
            "invalid_utc_timestamp",
            f"{name} must be formatted as YYYY-MM-DDTHH:MM:SSZ",
        )
    try:
        datetime.strptime(value, UTC_Z_FORMAT)
    except ValueError as exc:
        raise SpineValidationError(
            "invalid_utc_timestamp",
            f"{name} must be a valid UTC timestamp formatted as YYYY-MM-DDTHH:MM:SSZ",
        ) from exc
    return value


def require_optional_utc_z(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return require_utc_z(name, value)


def utc_z_from_datetime(value: datetime) -> str:
    """Convert an aware datetime to Spine's canonical second-precision UTC timestamp."""

    if value.tzinfo is None:
        raise SpineValidationError("invalid_utc_timestamp", "datetime value must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None, microsecond=0).strftime(UTC_Z_FORMAT)


def enum_value(value: StrEnum | str) -> str:
    return value.value if isinstance(value, StrEnum) else value


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def copy_id(row_id: str, version: int) -> str:
    return f"{row_id}-v{version}"
