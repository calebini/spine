"""Keyed catalog reads shared by command validation and scheduling operations."""

from __future__ import annotations

import sqlite3
from typing import Any

from spine.core.errors import SpineValidationError


def subject_exists(connection: sqlite3.Connection, subject_id: str) -> bool:
    return connection.execute("SELECT 1 FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone() is not None


def subject_group_exists(connection: sqlite3.Connection, group_id: str) -> bool:
    return connection.execute("SELECT 1 FROM subject_groups WHERE group_id = ?", (group_id,)).fetchone() is not None


def delivery_target(connection: sqlite3.Connection, delivery_target_id: str, *, required: bool = True) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM delivery_targets WHERE delivery_target_id = ?", (delivery_target_id,)).fetchone()
    if row is None:
        if required:
            raise SpineValidationError("delivery_target_not_found", f"delivery target not found: {delivery_target_id}")
        return None
    return dict(row)
