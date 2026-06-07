"""Internal item command service wrappers."""

from __future__ import annotations

import sqlite3
from typing import Any

from spine.ledger import create_event_v1, create_task_v1, get_current_item


def create_event(connection: sqlite3.Connection, **kwargs: Any):
    """Create an event through the stable service surface."""

    return create_event_v1(connection, **kwargs)


def create_task(connection: sqlite3.Connection, **kwargs: Any):
    """Create a task through the stable service surface."""

    return create_task_v1(connection, **kwargs)


def get_current(connection: sqlite3.Connection, item_id: str) -> dict[str, object]:
    """Read current item truth through the stable service surface."""

    return get_current_item(connection, item_id)
