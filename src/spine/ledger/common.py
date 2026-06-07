"""Shared helpers for SQLite ledger workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from spine.core import SpineValidationError
from spine.models.enums import TemporalAnchorKind


@dataclass(frozen=True)
class TemporalAnchorInput:
    """Input row for a temporal anchor created with a ledger workflow."""

    anchor_kind: TemporalAnchorKind | str
    anchor_id: str | None = None
    local_date: str | None = None
    local_time: str | None = None
    timezone: str | None = None
    utc_instant: str | None = None
    window_start_utc: str | None = None
    window_end_utc: str | None = None
    recurrence_rule: str | None = None
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
    require_non_empty("anchor.created_at_utc", created_at_utc)
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, local_time, timezone, utc_instant,
          window_start_utc, window_end_utc, recurrence_rule, source, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            anchor_id,
            enum_value(anchor.anchor_kind),
            anchor.local_date,
            anchor.local_time,
            anchor.timezone,
            anchor.utc_instant,
            anchor.window_start_utc,
            anchor.window_end_utc,
            anchor.recurrence_rule,
            anchor.source,
            created_at_utc,
        ),
    )


def require_non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) == 0:
        raise SpineValidationError("invalid_item_create_input", f"{name} must be a non-empty string")


def enum_value(value: StrEnum | str) -> str:
    return value.value if isinstance(value, StrEnum) else value


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def copy_id(row_id: str, version: int) -> str:
    return f"{row_id}-v{version}"
