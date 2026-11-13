"""Native item/policy write evidence; application acknowledgement is separate.

Capture uses already-read predecessor facts and successful native writes. Existing
allocator invariants and rendering/facet finalizers retain their SQL proof ownership.
No duplicate supporting-set/history scans are introduced here.
"""

import sqlite3
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ItemMutation, ItemSnapshot, PolicyMutation
from spine.ledger.mutation_effects import require_transaction


def snapshot(item: dict[str, Any], detail: dict[str, Any]) -> ItemSnapshot:
    return ItemSnapshot(item["item_id"], item["item_type"], int(item["current_version"]), item["status"],
                        item["title"], item["summary"], item["source_ref"],
                        canonical_json_bytes({k: str(v) if type(v) is int else v for k, v in detail.items()}))


def record_item(
    db: sqlite3.Connection, before: ItemSnapshot | None, after: ItemSnapshot, audit_id: str,
    *, before_people: tuple[tuple[str, str, str], ...] | None = None, after_people: tuple[tuple[str, str, str], ...] | None = None,
    before_facets: bytes | None = None, after_facets: bytes | None = None,
) -> None:
    pending = require_transaction(db).mutation_state.propagation.items
    if after.item_id in pending:
        raise SpineValidationError("environment_failure:propagation", "unacknowledged prior item mutation")
    pending[after.item_id] = ItemMutation(before, after, audit_id, before_people, after_people, before_facets, after_facets)


def record_policy(db: sqlite3.Connection, value: dict[str, Any]) -> None:
    # Legacy standalone helpers retain their original local behavior.
    if not getattr(db, "_command_transaction", False):
        return
    connection = require_transaction(db)
    pending = connection.mutation_state.propagation.policies
    identity = str(value["notification_policy_id"])
    if identity in pending:
        raise SpineValidationError("environment_failure:propagation", "duplicate policy mutation")
    if getattr(db, "_renderings_enabled", False) and identity not in connection.mutation_state.renderings.pending:
        raise SpineValidationError("environment_failure:rendering", "unregistered policy writer or missing presentation")
    presentation = (canonical_json_bytes(connection.mutation_state.renderings.pending[identity])
                    if getattr(db, "_renderings_enabled", False) else None)
    pending[identity] = PolicyMutation(str(value["item_id"]), int(value["item_version"]), identity,
        value.get("source_notification_policy_id"), canonical_json_bytes(value), presentation, presentation)


def discard_copied_policy(db: sqlite3.Connection, identity: str) -> None:
    if not getattr(db, "_command_transaction", False):
        return
    pending = require_transaction(db).mutation_state.propagation.policies
    if identity not in pending:
        raise SpineValidationError("environment_failure:propagation", "removed policy is not a pending successor")
    del pending[identity]
