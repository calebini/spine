"""Pre-write side-effect attempt gate services."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spine.core.errors import SpineValidationError
from spine.core.notification_rendering import NotificationRendering
from spine.ledger import (
    CompletedAttempt,
    StartedAttempt,
    assert_candidate_action_not_stale,
    assert_work_instance_not_stale,
    complete_side_effect_attempt,
    create_started_attempt,
)
from spine.ledger.notification_renderings import get_notification_rendering, insert_notification_rendering
from spine.ledger.provenance import record_stale_work_provenance_report
from spine.models.enums import AttemptStatus


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
    notification_rendering: NotificationRendering | None = None,
) -> AttemptGate:
    """Persist a started attempt for processable work before any external write."""

    try:
        assert_work_instance_not_stale(connection, work_instance_id)
    except SpineValidationError as exc:
        if exc.code != "stale_work_instance":
            raise
        with connection:
            report_id = record_stale_work_provenance_report(
                connection,
                work_instance_id=work_instance_id,
                operation="side_effect_attempt.start",
                blocked_at_utc=attempted_at_utc,
            )
        if report_id is None:
            raise
        raise SpineValidationError(
            "stale_work_instance",
            f"{exc.message}; occurrence provenance recovery report: {report_id}",
        ) from exc
    if notification_rendering is None:
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

    if (
        attempt_id is None
        or notification_rendering.attempt_id != attempt_id
        or notification_rendering.work_instance_id != work_instance_id
        or notification_rendering.attempted_at_utc != attempted_at_utc
    ):
        raise SpineValidationError(
            "notification_rendering_persistence_conflict",
            "rendering identity does not match the prepared attempt",
        )
    from spine.services.notification_rendering import assert_rendering_matches_current

    if connection.in_transaction:
        raise SpineValidationError(
            "notification_rendering_persistence_conflict",
            "rendered attempt start requires an independent transaction boundary",
        )
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing_attempt = connection.execute(
            "SELECT * FROM side_effect_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if existing_attempt is not None:
            existing_rendering = get_notification_rendering(connection, attempt_id=attempt_id)
            _assert_compatible_rendered_attempt_replay(
                attempt=dict(existing_attempt),
                rendering=existing_rendering,
                expected=notification_rendering,
                adapter_name=adapter_name,
                idempotency_key=idempotency_key,
                request_envelope=request_envelope,
            )
            connection.commit()
            return AttemptGate(
                attempt=StartedAttempt(
                    attempt_id=attempt_id,
                    request_payload_hash=str(existing_attempt["request_payload_hash"]),
                    request_hash=str(existing_attempt["request_hash"]),
                ),
                may_start_external_write=False,
            )
        assert_work_instance_not_stale(connection, work_instance_id)
        work_row = connection.execute(
            "SELECT * FROM work_instances WHERE work_instance_id = ?",
            (work_instance_id,),
        ).fetchone()
        if work_row is None:
            raise SpineValidationError("notification_rendering_source_unresolved", "work instance is unavailable")
        assert_rendering_matches_current(
            connection,
            work_row=dict(work_row),
            rendering=notification_rendering,
        )
        attempt = create_started_attempt(
            connection,
            attempt_id=attempt_id,
            work_instance_id=work_instance_id,
            adapter_name=adapter_name,
            idempotency_key=idempotency_key,
            request_envelope=request_envelope,
            attempted_at_utc=attempted_at_utc,
            manage_transaction=False,
        )
        insert_notification_rendering(
            connection,
            rendering=notification_rendering,
            manage_transaction=False,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return AttemptGate(attempt=attempt)


def _assert_compatible_rendered_attempt_replay(
    *,
    attempt: dict[str, object],
    rendering: dict[str, object] | None,
    expected: NotificationRendering,
    adapter_name: str,
    idempotency_key: str,
    request_envelope: object,
) -> None:
    """Accept only byte-identical replay of an already persisted rendered attempt."""

    from spine.core.hashing import side_effect_request_payload_hash

    expected_payload_hash = side_effect_request_payload_hash(
        adapter_name=adapter_name,
        request_envelope=request_envelope,
    )
    compatible = (
        rendering is not None
        and attempt.get("work_instance_id") == expected.work_instance_id
        and attempt.get("adapter_name") == adapter_name
        and attempt.get("idempotency_key") == idempotency_key
        and attempt.get("request_payload_hash") == expected_payload_hash
        and rendering.get("notification_rendering_id") == expected.notification_rendering_id
        and rendering.get("rendering_input_hash") == expected.rendering_input_hash
        and rendering.get("rendered_content_hash") == expected.rendered_content_hash
        and rendering.get("body_text") == expected.body_text
    )
    if not compatible:
        raise SpineValidationError(
            "notification_rendering_persistence_conflict",
            "attempt replay does not match immutable rendering evidence",
        )


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


def record_attempt_success(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    completed_at_utc: str,
    provider_ref: str | None = None,
    reason_code: str | None = None,
) -> CompletedAttempt:
    """Record a successful terminal side-effect attempt outcome."""

    return complete_side_effect_attempt(
        connection,
        attempt_id=attempt_id,
        attempt_status=AttemptStatus.SUCCEEDED,
        completed_at_utc=completed_at_utc,
        provider_ref=provider_ref,
        reason_code=reason_code,
    )


def record_attempt_failure(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    completed_at_utc: str,
    reason_code: str,
    provider_ref: str | None = None,
) -> CompletedAttempt:
    """Record a failed terminal side-effect attempt outcome."""

    return complete_side_effect_attempt(
        connection,
        attempt_id=attempt_id,
        attempt_status=AttemptStatus.FAILED,
        completed_at_utc=completed_at_utc,
        provider_ref=provider_ref,
        reason_code=reason_code,
    )


def record_attempt_rejection(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    completed_at_utc: str,
    reason_code: str,
    provider_ref: str | None = None,
) -> CompletedAttempt:
    """Record a rejected terminal side-effect attempt outcome."""

    return complete_side_effect_attempt(
        connection,
        attempt_id=attempt_id,
        attempt_status=AttemptStatus.REJECTED,
        completed_at_utc=completed_at_utc,
        provider_ref=provider_ref,
        reason_code=reason_code,
    )
