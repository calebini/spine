"""OpenClaw-style notification adapter skeleton."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Mapping

from spine.adapters.tickerd import WorkProcessingOutcome
from spine.services import (
    get_current,
    prepare_work_attempt,
    record_attempt_failure,
    record_attempt_rejection,
    record_attempt_success,
)

OPENCLAW_ADAPTER_NAME = "openclaw"

OpenClawResultStatus = Literal["delivered", "failed_transient", "failed_permanent", "blocked"]
OpenClawSender = Callable[["OpenClawOutboundMessage"], "NormalizedOpenClawResult"]


class OpenClawBindingError(RuntimeError):
    """Raised when the configured OpenClaw sender cannot be invoked."""


@dataclass(frozen=True)
class OpenClawOutboundMessage:
    """Spine outbound message envelope for the OpenClaw replacement path."""

    delivery_id: str
    attempt_id: str
    trace_id: str
    causation_id: str
    channel_hint: str
    target_ref: str
    body_text: str
    dedupe_key: str
    created_at_utc: str

    def request_envelope(self) -> dict[str, str]:
        return {
            "payload_version": "spine.openclaw.outbound.v1",
            "delivery_id": self.delivery_id,
            "attempt_id": self.attempt_id,
            "trace_id": self.trace_id,
            "causation_id": self.causation_id,
            "channel_hint": self.channel_hint,
            "target_ref": self.target_ref,
            "body_text": self.body_text,
            "dedupe_key": self.dedupe_key,
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True)
class NormalizedOpenClawResult:
    """Normalized OpenClaw send result used before a real host binding exists."""

    status: OpenClawResultStatus
    reason_code: str
    provider_ref: str | None = None
    next_attempt_at_utc: str | None = None

    @classmethod
    def delivered(cls, *, provider_ref: str, reason_code: str = "openclaw_delivered") -> "NormalizedOpenClawResult":
        return cls("delivered", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def transient_failure(cls, *, reason_code: str, next_attempt_at_utc: str) -> "NormalizedOpenClawResult":
        return cls("failed_transient", reason_code=reason_code, next_attempt_at_utc=next_attempt_at_utc)

    @classmethod
    def permanent_failure(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedOpenClawResult":
        return cls("failed_permanent", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def blocked(cls, *, reason_code: str) -> "NormalizedOpenClawResult":
        return cls("blocked", reason_code=reason_code)


@dataclass(frozen=True)
class OpenClawNotificationProcessor:
    """Active Tickerd processor that sends reminder work through an OpenClaw-style sender."""

    sender: OpenClawSender
    channel_hint: str = "openclaw_auto"

    def __call__(self, connection: sqlite3.Connection, work_row: Mapping[str, object], envelope: Any) -> WorkProcessingOutcome:
        outbound = build_openclaw_outbound_message(
            connection,
            work_row=work_row,
            trace_id=str(envelope.trace_id),
            causation_id=str(envelope.causation_id),
            created_at_utc=_utc_z(envelope.actual_start_ts),
            channel_hint=self.channel_hint,
        )
        gate = prepare_work_attempt(
            connection,
            attempt_id=outbound.attempt_id,
            work_instance_id=outbound.delivery_id,
            adapter_name=OPENCLAW_ADAPTER_NAME,
            idempotency_key=outbound.dedupe_key,
            request_envelope=outbound.request_envelope(),
            attempted_at_utc=outbound.created_at_utc,
        )
        try:
            result = self.sender(outbound)
        except OpenClawBindingError:
            record_attempt_rejection(
                connection,
                attempt_id=gate.attempt.attempt_id,
                completed_at_utc=outbound.created_at_utc,
                reason_code="openclaw_binding_failed",
            )
            return WorkProcessingOutcome.failed("openclaw_binding_failed")
        except Exception:
            record_attempt_failure(
                connection,
                attempt_id=gate.attempt.attempt_id,
                completed_at_utc=outbound.created_at_utc,
                reason_code="openclaw_send_exception",
            )
            return WorkProcessingOutcome.failed("openclaw_send_exception")

        return record_openclaw_result(
            connection,
            attempt_id=gate.attempt.attempt_id,
            result=result,
            completed_at_utc=outbound.created_at_utc,
        )


def build_openclaw_outbound_message(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    trace_id: str,
    causation_id: str,
    created_at_utc: str,
    channel_hint: str = "openclaw_auto",
) -> OpenClawOutboundMessage:
    """Map Spine reminder work into an OpenClaw-style outbound message."""

    item = get_current(connection, str(work_row["item_id"]))
    work_instance_id = str(work_row["work_instance_id"])
    attempt_count = str(work_row["attempt_count"])
    target_ref = str(work_row.get("work_subject_ref") or "")
    title = str(item["version"]["title"])  # type: ignore[index]
    return OpenClawOutboundMessage(
        delivery_id=work_instance_id,
        attempt_id=f"openclaw-attempt-{work_instance_id}-{attempt_count}",
        trace_id=trace_id,
        causation_id=causation_id,
        channel_hint=channel_hint,
        target_ref=target_ref,
        body_text=f"Reminder: {title}",
        dedupe_key=f"openclaw:{work_instance_id}:{attempt_count}",
        created_at_utc=created_at_utc,
    )


def record_openclaw_result(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    result: NormalizedOpenClawResult,
    completed_at_utc: str,
) -> WorkProcessingOutcome:
    """Persist normalized OpenClaw result and return the matching Spine work outcome."""

    if result.status == "delivered":
        record_attempt_success(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.succeeded(result.reason_code)
    if result.status == "failed_transient":
        if not result.next_attempt_at_utc:
            record_attempt_failure(
                connection,
                attempt_id=attempt_id,
                completed_at_utc=completed_at_utc,
                provider_ref=result.provider_ref,
                reason_code="openclaw_missing_retry_at",
            )
            return WorkProcessingOutcome.failed("openclaw_missing_retry_at")
        record_attempt_failure(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.retry(
            reason_code=result.reason_code,
            next_attempt_at_utc=result.next_attempt_at_utc or "",
        )
    if result.status == "failed_permanent":
        record_attempt_failure(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.failed(result.reason_code)
    if result.status == "blocked":
        record_attempt_rejection(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.cancelled(result.reason_code)
    raise ValueError(f"unknown OpenClaw result status: {result.status}")


def _utc_z(value: datetime) -> str:
    return f"{value.astimezone(UTC).replace(tzinfo=None).isoformat()}Z"
