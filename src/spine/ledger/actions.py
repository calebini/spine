"""Candidate action workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.ledger.common import enum_value, new_id, require_non_empty, require_optional_utc_z, require_utc_z
from spine.models.enums import CandidateActionKind, CandidateActionStatus


@dataclass(frozen=True)
class CreatedCandidateAction:
    """Result of creating a candidate action row."""

    candidate_action_id: str
    item_id: str
    item_version: int


def create_candidate_action(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_version: int,
    action_kind: CandidateActionKind | str,
    requires_approval: bool,
    created_at_utc: str,
    candidate_action_id: str | None = None,
    urgency: str | None = None,
    status: CandidateActionStatus | str = CandidateActionStatus.OPEN,
    evidence_ref: str | None = None,
    resolved_at_utc: str | None = None,
) -> CreatedCandidateAction:
    """Create proposed action pressure bound to an item version."""

    candidate_action_id = candidate_action_id or new_id("candidate-action")
    require_non_empty("candidate_action_id", candidate_action_id)
    require_non_empty("item_id", item_id)
    require_utc_z("created_at_utc", created_at_utc)
    require_optional_utc_z("resolved_at_utc", resolved_at_utc)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO candidate_actions (
                  candidate_action_id, item_id, item_version, action_kind, urgency,
                  status, evidence_ref, requires_approval, created_at_utc, resolved_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_action_id,
                    item_id,
                    item_version,
                    enum_value(action_kind),
                    urgency,
                    enum_value(status),
                    evidence_ref,
                    int(requires_approval),
                    created_at_utc,
                    resolved_at_utc,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("candidate_action_rejected", str(exc)) from exc
    return CreatedCandidateAction(candidate_action_id=candidate_action_id, item_id=item_id, item_version=item_version)


def assert_candidate_action_not_stale(connection: sqlite3.Connection, candidate_action_id: str) -> None:
    row = connection.execute(
        """
        SELECT c.item_version, i.current_version
        FROM candidate_actions AS c
        JOIN coordination_items AS i ON i.item_id = c.item_id
        WHERE c.candidate_action_id = ?
        """,
        (candidate_action_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("candidate_action_not_found", f"candidate action not found: {candidate_action_id}")
    if row["item_version"] != row["current_version"]:
        raise SpineValidationError("stale_candidate_action", f"candidate action is stale: {candidate_action_id}")


def get_candidate_action(connection: sqlite3.Connection, candidate_action_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM candidate_actions WHERE candidate_action_id = ?",
        (candidate_action_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("candidate_action_not_found", f"candidate action not found: {candidate_action_id}")
    return dict(row)
