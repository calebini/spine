"""Command receipt helpers for deterministic replay fixtures."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core.canonical_json import canonical_json_text
from spine.core.hashing import hash_canonical_json


def command_derived_id(
    *,
    prefix: str,
    command: str,
    command_id: str,
    row_role: str,
    request_path: str,
) -> str:
    """Return the MVP command-derived row identity."""

    digest = hash_canonical_json(
        {
            "command": command,
            "command_id": command_id,
            "derivation_version": "spine.command-id.v1",
            "request_path": request_path,
            "row_role": row_role,
        }
    )
    return f"{prefix}_{digest}"


def command_receipt(
    *,
    command: str,
    command_id: str,
    actor_subject_id: str,
    action_timestamp_utc: str,
    effect: str,
    semantic_facts: Mapping[str, Any],
    result_identity_facts: Mapping[str, Any],
    item_id: str | None = None,
    target_version: str | None = None,
    command_receipt_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Return a command receipt row shape with a canonical semantic hash."""

    receipt_id = command_receipt_id or command_derived_id(
        prefix="command_receipt",
        command=command,
        command_id=command_id,
        row_role="command_receipt",
        request_path="/",
    )
    receipt: dict[str, Any] = {
        "command_receipt_id": receipt_id,
        "command": command,
        "command_id": command_id,
        "actor_subject_id": actor_subject_id,
        "action_timestamp_utc": action_timestamp_utc,
        "effect": effect,
        "result_identity_facts": dict(result_identity_facts),
        "semantic_facts_hash": hash_canonical_json(dict(semantic_facts)),
        "semantic_facts": dict(semantic_facts),
        "created_at_utc": created_at_utc or action_timestamp_utc,
    }
    if item_id is not None:
        receipt["item_id"] = item_id
    if target_version is not None:
        receipt["target_version"] = target_version
    return receipt


def insert_command_receipt(connection: sqlite3.Connection, receipt: Mapping[str, Any]) -> None:
    """Persist a command receipt produced by :func:`command_receipt`."""

    semantic_facts = dict(_mapping(receipt["semantic_facts"]))
    result_identity_facts = dict(_mapping(receipt["result_identity_facts"]))
    connection.execute(
        """
        INSERT INTO command_receipts (
          command_receipt_id, command_id, command, actor_subject_id, action_timestamp_utc,
          effect, item_id, target_version, result_identity_facts_json, semantic_facts_hash,
          semantic_facts_json, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt["command_receipt_id"],
            receipt["command_id"],
            receipt["command"],
            receipt["actor_subject_id"],
            receipt["action_timestamp_utc"],
            receipt["effect"],
            receipt.get("item_id"),
            receipt.get("target_version"),
            canonical_json_text(result_identity_facts),
            receipt["semantic_facts_hash"],
            canonical_json_text(semantic_facts),
            receipt["created_at_utc"],
        ),
    )


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


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("receipt field must be a mapping")
    return value
