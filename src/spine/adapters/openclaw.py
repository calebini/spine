"""OpenClaw-style notification adapter skeleton."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Mapping

from spine.adapters.side_effects import (
    AttemptBackedSideEffectProcessor,
    AttemptBackedSideEffectRequest,
    NormalizedSideEffectResult,
    SideEffectBindingError,
    record_side_effect_result,
)
from spine.adapters.tickerd import WorkProcessingOutcome
from spine.services import get_current

OPENCLAW_ADAPTER_NAME = "openclaw"

OpenClawResultStatus = Literal["delivered", "failed_transient", "failed_permanent", "blocked"]
OpenClawSender = Callable[["OpenClawOutboundMessage"], "NormalizedOpenClawResult"]


class OpenClawBindingError(SideEffectBindingError):
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
        processor: AttemptBackedSideEffectProcessor[OpenClawOutboundMessage] = AttemptBackedSideEffectProcessor(
            adapter_name=OPENCLAW_ADAPTER_NAME,
            build_request=lambda request_connection, request_work_row, request_envelope: build_openclaw_side_effect_request(
                request_connection,
                work_row=request_work_row,
                envelope=request_envelope,
                channel_hint=self.channel_hint,
            ),
            sender=lambda outbound: normalize_openclaw_result(self.sender(outbound)),
            binding_error_type=OpenClawBindingError,
            binding_failure_reason_code="openclaw_binding_failed",
            send_exception_reason_code="openclaw_send_exception",
            missing_retry_reason_code="openclaw_missing_retry_at",
        )
        return processor(connection, work_row, envelope)


def build_openclaw_side_effect_request(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    envelope: Any,
    channel_hint: str = "openclaw_auto",
) -> AttemptBackedSideEffectRequest[OpenClawOutboundMessage]:
    """Build the generic attempt-backed request for an OpenClaw outbound message."""

    outbound = build_openclaw_outbound_message(
        connection,
        work_row=work_row,
        trace_id=str(envelope.trace_id),
        causation_id=str(envelope.causation_id),
        created_at_utc=_utc_z(envelope.actual_start_ts),
        channel_hint=channel_hint,
    )
    return AttemptBackedSideEffectRequest(
        message=outbound,
        attempt_id=outbound.attempt_id,
        work_instance_id=outbound.delivery_id,
        idempotency_key=outbound.dedupe_key,
        request_envelope=outbound.request_envelope(),
        attempted_at_utc=outbound.created_at_utc,
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

    return record_side_effect_result(
        connection,
        attempt_id=attempt_id,
        result=normalize_openclaw_result(result),
        completed_at_utc=completed_at_utc,
        missing_retry_reason_code="openclaw_missing_retry_at",
    )


def normalize_openclaw_result(result: NormalizedOpenClawResult) -> NormalizedSideEffectResult:
    """Translate OpenClaw-shaped outcomes into provider-neutral side-effect outcomes."""

    if result.status == "delivered":
        return NormalizedSideEffectResult.succeeded(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    if result.status == "failed_transient":
        return NormalizedSideEffectResult.retry(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
            next_attempt_at_utc=result.next_attempt_at_utc or "",
        )
    if result.status == "failed_permanent":
        return NormalizedSideEffectResult.failed(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    if result.status == "blocked":
        return NormalizedSideEffectResult.cancelled(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    raise ValueError(f"unknown OpenClaw result status: {result.status}")


def _utc_z(value: datetime) -> str:
    return f"{value.astimezone(UTC).replace(tzinfo=None).isoformat()}Z"
