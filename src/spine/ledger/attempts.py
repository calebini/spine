"""Side-effect attempt ledger workflows."""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from dataclasses import dataclass

from spine.core import SpineValidationError
from spine.core.hashing import side_effect_request_hash, side_effect_request_payload_hash, side_effect_response_hash
from spine.ledger.common import enum_value, new_id, require_non_empty, require_utc_z
from spine.models.enums import AttemptStatus


@dataclass(frozen=True)
class StartedAttempt:
    """Result of persisting a pre-write side-effect attempt row."""

    attempt_id: str
    request_payload_hash: str
    request_hash: str


@dataclass(frozen=True)
class CompletedAttempt:
    """Result of terminally updating a side-effect attempt row."""

    attempt_id: str
    attempt_status: str
    response_hash: str


def create_started_attempt(
    connection: sqlite3.Connection,
    *,
    adapter_name: str,
    idempotency_key: str,
    request_envelope: object,
    attempted_at_utc: str,
    attempt_id: str | None = None,
    work_instance_id: str | None = None,
    candidate_action_id: str | None = None,
    projection_id: str | None = None,
    item_id: str | None = None,
    source_item_version: int | None = None,
    reason_code: str | None = None,
    manage_transaction: bool = True,
) -> StartedAttempt:
    """Persist the durable pre-write attempt row required before an external write."""

    attempt_id = attempt_id or new_id("attempt")
    require_non_empty("attempt_id", attempt_id)
    require_non_empty("adapter_name", adapter_name)
    require_non_empty("idempotency_key", idempotency_key)
    require_utc_z("attempted_at_utc", attempted_at_utc)
    item_id, source_item_version = _resolve_attempt_binding(
        connection,
        item_id=item_id,
        source_item_version=source_item_version,
        work_instance_id=work_instance_id,
        candidate_action_id=candidate_action_id,
        projection_id=projection_id,
    )
    request_payload_hash = side_effect_request_payload_hash(
        adapter_name=adapter_name,
        request_envelope=request_envelope,
    )
    request_hash = side_effect_request_hash(
        adapter_name=adapter_name,
        idempotency_key=idempotency_key,
        request_payload_hash=request_payload_hash,
        work_instance_id=work_instance_id,
        candidate_action_id=candidate_action_id,
        projection_id=projection_id,
    )
    try:
        with connection if manage_transaction else nullcontext():
            connection.execute(
                """
                INSERT INTO side_effect_attempts (
                  attempt_id, work_instance_id, candidate_action_id, item_id, adapter_name,
                  projection_id, source_item_version, idempotency_key, attempt_status,
                  request_payload_hash, request_hash, reason_code, attempted_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    work_instance_id,
                    candidate_action_id,
                    item_id,
                    adapter_name,
                    projection_id,
                    source_item_version,
                    idempotency_key,
                    AttemptStatus.STARTED.value,
                    request_payload_hash,
                    request_hash,
                    reason_code,
                    attempted_at_utc,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise SpineValidationError("side_effect_attempt_rejected", str(exc)) from exc
    return StartedAttempt(
        attempt_id=attempt_id,
        request_payload_hash=request_payload_hash,
        request_hash=request_hash,
    )


def complete_side_effect_attempt(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    attempt_status: AttemptStatus | str,
    completed_at_utc: str,
    provider_ref: str | None = None,
    reason_code: str | None = None,
) -> CompletedAttempt:
    """Terminally update a started side-effect attempt."""

    require_non_empty("attempt_id", attempt_id)
    require_utc_z("completed_at_utc", completed_at_utc)
    status = enum_value(attempt_status)
    if status == AttemptStatus.STARTED.value:
        raise SpineValidationError("side_effect_attempt_transition_rejected", "terminal status required")
    if status not in {
        AttemptStatus.SUCCEEDED.value,
        AttemptStatus.FAILED.value,
        AttemptStatus.REJECTED.value,
    }:
        raise SpineValidationError("side_effect_attempt_transition_rejected", f"unknown terminal status: {status}")
    row = get_side_effect_attempt(connection, attempt_id)
    if row["attempt_status"] != AttemptStatus.STARTED.value:
        raise SpineValidationError("side_effect_attempt_transition_rejected", f"attempt is terminal: {attempt_id}")
    response_hash = side_effect_response_hash(
        attempt_id=attempt_id,
        attempt_status=status,
        provider_ref=provider_ref,
    )
    with connection:
        connection.execute(
            """
            UPDATE side_effect_attempts
            SET attempt_status = ?,
                provider_ref = ?,
                response_hash = ?,
                reason_code = ?,
                completed_at_utc = ?
            WHERE attempt_id = ?
            """,
            (status, provider_ref, response_hash, reason_code, completed_at_utc, attempt_id),
        )
    return CompletedAttempt(attempt_id=attempt_id, attempt_status=status, response_hash=response_hash)


def get_side_effect_attempt(connection: sqlite3.Connection, attempt_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM side_effect_attempts WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("side_effect_attempt_not_found", f"attempt not found: {attempt_id}")
    return dict(row)


def _resolve_attempt_binding(
    connection: sqlite3.Connection,
    *,
    item_id: str | None,
    source_item_version: int | None,
    work_instance_id: str | None,
    candidate_action_id: str | None,
    projection_id: str | None,
) -> tuple[str | None, int | None]:
    if work_instance_id is not None and candidate_action_id is not None:
        return item_id, source_item_version
    if work_instance_id is not None:
        work = connection.execute(
            "SELECT item_id, item_version FROM work_instances WHERE work_instance_id = ?",
            (work_instance_id,),
        ).fetchone()
        if work is None:
            return item_id, source_item_version
        item_id = item_id or work["item_id"]
        if projection_id is not None:
            source_item_version = source_item_version or work["item_version"]
    if candidate_action_id is not None:
        action = connection.execute(
            "SELECT item_id, item_version FROM candidate_actions WHERE candidate_action_id = ?",
            (candidate_action_id,),
        ).fetchone()
        if action is None:
            return item_id, source_item_version
        item_id = item_id or action["item_id"]
        if projection_id is not None:
            source_item_version = source_item_version or action["item_version"]
    if projection_id is not None and item_id is None:
        projection = connection.execute(
            "SELECT item_id FROM external_projections WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        if projection is not None:
            item_id = projection["item_id"]
    return item_id, source_item_version
