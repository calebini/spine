"""Projection planning services."""

from __future__ import annotations

import sqlite3

from spine.ledger import CreatedCandidateAction, create_candidate_action, get_current_item


def plan_projection_sync(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    created_at_utc: str,
    candidate_action_id: str | None = None,
    evidence_ref: str | None = None,
    requires_approval: bool = False,
) -> CreatedCandidateAction:
    """Create candidate sync pressure for the current item version."""

    current = get_current_item(connection, item_id)
    return create_candidate_action(
        connection,
        candidate_action_id=candidate_action_id,
        item_id=item_id,
        item_version=current["current_version"],
        action_kind="sync_projection",
        requires_approval=requires_approval,
        created_at_utc=created_at_utc,
        evidence_ref=evidence_ref,
    )
