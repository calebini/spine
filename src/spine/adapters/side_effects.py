"""Generic attempt-backed side-effect processor helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, Mapping, TypeVar

from spine.adapters.tickerd import WorkProcessingOutcome
from spine.services import (
    prepare_work_attempt,
    record_attempt_failure,
    record_attempt_rejection,
    record_attempt_success,
)

TMessage = TypeVar("TMessage")

SideEffectResultStatus = Literal["succeeded", "retry", "failed", "rejected", "cancelled"]
SideEffectSender = Callable[[TMessage], "NormalizedSideEffectResult"]
SideEffectRequestBuilder = Callable[
    [sqlite3.Connection, Mapping[str, object], Any],
    "AttemptBackedSideEffectRequest[TMessage]",
]


class SideEffectBindingError(RuntimeError):
    """Raised when a side-effect sender binding cannot be invoked."""


@dataclass(frozen=True)
class AttemptBackedSideEffectRequest(Generic[TMessage]):
    """Prepared side-effect message plus the attempt identity needed before send."""

    message: TMessage
    attempt_id: str
    work_instance_id: str
    idempotency_key: str
    request_envelope: Mapping[str, object]
    attempted_at_utc: str


@dataclass(frozen=True)
class NormalizedSideEffectResult:
    """Provider-neutral side-effect result that can update attempts and work."""

    status: SideEffectResultStatus
    reason_code: str
    provider_ref: str | None = None
    next_attempt_at_utc: str | None = None

    @classmethod
    def succeeded(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedSideEffectResult":
        return cls("succeeded", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def retry(
        cls,
        *,
        reason_code: str,
        next_attempt_at_utc: str,
        provider_ref: str | None = None,
    ) -> "NormalizedSideEffectResult":
        return cls(
            "retry",
            reason_code=reason_code,
            provider_ref=provider_ref,
            next_attempt_at_utc=next_attempt_at_utc,
        )

    @classmethod
    def failed(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedSideEffectResult":
        return cls("failed", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def rejected(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedSideEffectResult":
        return cls("rejected", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def cancelled(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedSideEffectResult":
        return cls("cancelled", reason_code=reason_code, provider_ref=provider_ref)


@dataclass(frozen=True)
class AttemptBackedSideEffectProcessor(Generic[TMessage]):
    """Tickerd work processor wrapper for any attempt-backed side effect."""

    adapter_name: str
    build_request: SideEffectRequestBuilder[TMessage]
    sender: SideEffectSender[TMessage]
    binding_error_type: type[Exception] = SideEffectBindingError
    binding_failure_reason_code: str = "side_effect_binding_failed"
    send_exception_reason_code: str = "side_effect_send_exception"
    missing_retry_reason_code: str = "side_effect_missing_retry_at"

    def __call__(self, connection: sqlite3.Connection, work_row: Mapping[str, object], envelope: Any) -> WorkProcessingOutcome:
        request = self.build_request(connection, work_row, envelope)
        gate = prepare_work_attempt(
            connection,
            attempt_id=request.attempt_id,
            work_instance_id=request.work_instance_id,
            adapter_name=self.adapter_name,
            idempotency_key=request.idempotency_key,
            request_envelope=request.request_envelope,
            attempted_at_utc=request.attempted_at_utc,
        )
        try:
            result = self.sender(request.message)
        except self.binding_error_type:
            record_attempt_rejection(
                connection,
                attempt_id=gate.attempt.attempt_id,
                completed_at_utc=request.attempted_at_utc,
                reason_code=self.binding_failure_reason_code,
            )
            return WorkProcessingOutcome.failed(self.binding_failure_reason_code)
        except Exception:
            record_attempt_failure(
                connection,
                attempt_id=gate.attempt.attempt_id,
                completed_at_utc=request.attempted_at_utc,
                reason_code=self.send_exception_reason_code,
            )
            return WorkProcessingOutcome.failed(self.send_exception_reason_code)

        return record_side_effect_result(
            connection,
            attempt_id=gate.attempt.attempt_id,
            result=result,
            completed_at_utc=request.attempted_at_utc,
            missing_retry_reason_code=self.missing_retry_reason_code,
        )


def record_side_effect_result(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    result: NormalizedSideEffectResult,
    completed_at_utc: str,
    missing_retry_reason_code: str = "side_effect_missing_retry_at",
) -> WorkProcessingOutcome:
    """Persist a normalized side-effect result and return the matching work outcome."""

    if result.status == "succeeded":
        record_attempt_success(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.succeeded(result.reason_code)
    if result.status == "retry":
        if not result.next_attempt_at_utc:
            record_attempt_failure(
                connection,
                attempt_id=attempt_id,
                completed_at_utc=completed_at_utc,
                provider_ref=result.provider_ref,
                reason_code=missing_retry_reason_code,
            )
            return WorkProcessingOutcome.failed(missing_retry_reason_code)
        record_attempt_failure(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.retry(
            reason_code=result.reason_code,
            next_attempt_at_utc=result.next_attempt_at_utc,
        )
    if result.status == "failed":
        record_attempt_failure(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.failed(result.reason_code)
    if result.status == "rejected":
        record_attempt_rejection(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.failed(result.reason_code)
    if result.status == "cancelled":
        record_attempt_rejection(
            connection,
            attempt_id=attempt_id,
            completed_at_utc=completed_at_utc,
            provider_ref=result.provider_ref,
            reason_code=result.reason_code,
        )
        return WorkProcessingOutcome.cancelled(result.reason_code)
    raise ValueError(f"unknown side-effect result status: {result.status}")
