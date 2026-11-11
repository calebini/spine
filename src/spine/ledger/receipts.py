"""Keyed command-receipt reads and immutable historical row decoding.

No receipt authoring, command admission or transaction ownership lives here.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any


def get_command_receipt(connection: sqlite3.Connection, command_id: str) -> dict[str, Any] | None:
    """Return a persisted command receipt by global command ID."""

    row = connection.execute(
        """
        SELECT *
        FROM command_receipts
        WHERE command_id = ?
        """,
        (command_id,),
    ).fetchone()
    if row is None:
        return None
    return receipt_from_row(row)


def receipt_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a stored receipt row into the public receipt dictionary shape."""

    item_id = row["item_id"]
    target_version = row["target_version"]
    receipt = {
        "command_receipt_id": row["command_receipt_id"],
        "command": row["command"],
        "command_id": row["command_id"],
        "actor_subject_id": row["actor_subject_id"],
        "action_timestamp_utc": row["action_timestamp_utc"],
        "effect": row["effect"],
        "result_identity_facts": json.loads(row["result_identity_facts_json"]),
        "semantic_facts_hash": row["semantic_facts_hash"],
        "semantic_facts": json.loads(row["semantic_facts_json"]),
        "created_at_utc": row["created_at_utc"],
    }
    if item_id is not None:
        receipt["item_id"] = item_id
    if target_version is not None:
        receipt["target_version"] = target_version
    return receipt
