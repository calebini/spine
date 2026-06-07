"""Pre-write side-effect attempt gate services."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.ledger import (
    StartedAttempt,
    assert_candidate_action_not_stale,
    assert_work_instance_not_stale,
    create_started_attempt,
)


@dataclass(frozen=True)
class AttemptGate:
    """A durable pre-write attempt gate result."""

    attempt: StartedAttempt
    may_start_external_write: bool = True


def prepare_work_attempt(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    adapter_name: str,
    idempotency_key: str,
    request_envelope: object,
    attempted_at_utc: str,
    attempt_id: str | None = None,
) -> AttemptGate:
    """Persist a started attempt for processable work before any external write."""

    assert_work_instance_not_stale(connection, work_instance_id)
    attempt = create_started_attempt(
        connection,
        attempt_id=attempt_id,
        work_instance_id=work_instance_id,
        adapter_name=adapter_name,
        idempotency_key=idempotency_key,
        request_envelope=request_envelope,
        attempted_at_utc=attempted_at_utc,
    )
    return AttemptGate(attempt=attempt)


def prepare_candidate_action_attempt(
    connection: sqlite3.Connection,
    *,
    candidate_action_id: str,
    adapter_name: str,
    idempotency_key: str,
    request_envelope: object,
    attempted_at_utc: str,
    attempt_id: str | None = None,
) -> AttemptGate:
    """Persist a started attempt for a non-stale candidate action."""

    assert_candidate_action_not_stale(connection, candidate_action_id)
    attempt = create_started_attempt(
        connection,
        attempt_id=attempt_id,
        candidate_action_id=candidate_action_id,
        adapter_name=adapter_name,
        idempotency_key=idempotency_key,
        request_envelope=request_envelope,
        attempted_at_utc=attempted_at_utc,
    )
    return AttemptGate(attempt=attempt)


def prepare_projection_attempt(
    connection: sqlite3.Connection,
    *,
    projection_id: str,
    item_id: str,
    source_item_version: int,
    adapter_name: str,
    idempotency_key: str,
    request_envelope: object,
    attempted_at_utc: str,
    attempt_id: str | None = None,
    work_instance_id: str | None = None,
    candidate_action_id: str | None = None,
) -> AttemptGate:
    """Persist a started attempt for a projection write from current item truth."""

    if work_instance_id is not None:
        assert_work_instance_not_stale(connection, work_instance_id)
    if candidate_action_id is not None:
        assert_candidate_action_not_stale(connection, candidate_action_id)
    attempt = create_started_attempt(
        connection,
        attempt_id=attempt_id,
        work_instance_id=work_instance_id,
        candidate_action_id=candidate_action_id,
        projection_id=projection_id,
        item_id=item_id,
        source_item_version=source_item_version,
        adapter_name=adapter_name,
        idempotency_key=idempotency_key,
        request_envelope=request_envelope,
        attempted_at_utc=attempted_at_utc,
    )
    return AttemptGate(attempt=attempt)
