"""Tickerd adapter for Spine work instances."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from spine.core import SpineValidationError
from spine.ledger.common import utc_z_from_datetime
from spine.protocols import (
    TickerdCycleEnvelope,
    TickerdProcessResult,
    TickerdProcessResultFactory,
    TickerdPublicTypes,
    TickerdReconcileResult,
    TickerdReconcileResultFactory,
    TickerdRuntimeMode,
    TickerdRuntimeModeFactory,
    TickerdWorkItem,
    TickerdWorkItemFactory,
)
from spine.runtime.storage_safety import StorageSafetyLatch
from spine.services import (
    cancel_work,
    fail_work,
    list_eligible_work,
    materialize_notification_horizon,
    require_processable_work,
    retry_work,
    start_work,
    succeed_work,
)

SIDE_EFFECTS_BLOCKED = "SIDE_EFFECTS_BLOCKED"
NO_PROCESSOR_CONFIGURED = "NO_PROCESSOR_CONFIGURED"
STALE_WORK_BLOCKED = "STALE_WORK_INSTANCE"
INVALID_WORK_OUTCOME = "INVALID_WORK_OUTCOME"

WorkProcessor = Callable[[sqlite3.Connection, Mapping[str, object], TickerdCycleEnvelope], "WorkProcessingOutcome"]


@dataclass(frozen=True)
class WorkProcessingOutcome:
    """A Spine work outcome returned by an active Tickerd work processor."""

    status: str
    reason_code: str | None = None
    next_attempt_at_utc: str | None = None

    @classmethod
    def succeeded(cls, reason_code: str | None = None) -> WorkProcessingOutcome:
        return cls("succeeded", reason_code=reason_code)

    @classmethod
    def failed(cls, reason_code: str) -> WorkProcessingOutcome:
        return cls("failed", reason_code=reason_code)

    @classmethod
    def retry(cls, *, reason_code: str, next_attempt_at_utc: str) -> WorkProcessingOutcome:
        return cls("retry", reason_code=reason_code, next_attempt_at_utc=next_attempt_at_utc)

    @classmethod
    def cancelled(cls, reason_code: str) -> WorkProcessingOutcome:
        return cls("cancelled", reason_code=reason_code)


@dataclass(frozen=True)
class SpineTickerdWorkAdapter:
    """Expose Spine eligible work through Tickerd's adapter protocols."""

    connection: sqlite3.Connection
    runtime_mode: str = "observe_only"
    processor: WorkProcessor | None = None
    scheduler_actor_subject_id: str | None = None
    materialization_horizon_seconds: int = 86_400
    storage_safety_latch: StorageSafetyLatch | None = None

    def read_mode(self) -> TickerdRuntimeMode:
        """Return Tickerd's runtime mode without making Tickerd a hard import."""

        tickerd_types = _tickerd_public_types()
        return tickerd_types.runtime_mode(self.runtime_mode)

    def list_work_items(self, envelope: TickerdCycleEnvelope, limit: int) -> Sequence[TickerdWorkItem]:
        """Map eligible, non-stale Spine work instances into Tickerd work items."""

        self._require_storage_safe()
        try:
            tickerd_types = _tickerd_public_types()
            rows = list_eligible_work(self.connection, now_utc=_utc_z(envelope.actual_start_ts), limit=limit)
            return tuple(
                tickerd_types.work_item(
                    item_id=str(row["work_instance_id"]),
                    payload=build_work_item_payload(row),
                )
                for row in rows
            )
        except sqlite3.Error as exc:
            self._observe_sqlite_error(exc)
            raise

    def process_work_item(
        self,
        item: TickerdWorkItem,
        envelope: TickerdCycleEnvelope,
        *,
        side_effects_allowed: bool,
    ) -> TickerdProcessResult:
        """Validate work freshness and delegate active processing only when configured."""

        self._require_storage_safe()
        try:
            return self._process_work_item(item, envelope, side_effects_allowed=side_effects_allowed)
        except sqlite3.Error as exc:
            self._observe_sqlite_error(exc)
            raise

    def _process_work_item(
        self,
        item: TickerdWorkItem,
        envelope: TickerdCycleEnvelope,
        *,
        side_effects_allowed: bool,
    ) -> TickerdProcessResult:

        tickerd_types = _tickerd_public_types()
        try:
            require_processable_work(self.connection, item.item_id)
        except SpineValidationError as exc:
            if exc.code in {"stale_work_instance", "work_instance_not_found"}:
                return tickerd_types.process_result.blocked(STALE_WORK_BLOCKED)
            raise

        if not side_effects_allowed:
            return tickerd_types.process_result.blocked(SIDE_EFFECTS_BLOCKED)
        if self.processor is None:
            return tickerd_types.process_result.blocked(NO_PROCESSOR_CONFIGURED)
        start_work(
            self.connection,
            work_instance_id=item.item_id,
            started_at_utc=_utc_z(envelope.actual_start_ts),
            reason_code="tickerd_processor_started",
        )
        started_work_row = require_processable_work(self.connection, item.item_id)
        try:
            outcome = self.processor(self.connection, started_work_row, envelope)
            _apply_work_processing_outcome(
                self.connection,
                work_instance_id=item.item_id,
                outcome=outcome,
                outcome_at_utc=_utc_z(envelope.actual_start_ts),
            )
        except sqlite3.Error:
            raise
        except Exception:
            fail_work(
                self.connection,
                work_instance_id=item.item_id,
                failed_at_utc=_utc_z(envelope.actual_start_ts),
                reason_code="processor_exception",
            )
            return tickerd_types.process_result.failed("PROCESSOR_EXCEPTION")
        return tickerd_types.process_result.processed()

    def reconcile(self, envelope: TickerdCycleEnvelope, *, max_batches: int) -> TickerdReconcileResult:
        """Materialize the next bounded notification horizon before work selection."""

        self._require_storage_safe()
        try:
            tickerd_types = _tickerd_public_types()
            result = materialize_notification_horizon(
                self.connection,
                evaluated_at_utc=_utc_z(envelope.actual_start_ts),
                horizon_seconds=self.materialization_horizon_seconds,
                max_items=max(1, max_batches) * 100,
                actor_subject_id=self.scheduler_actor_subject_id,
            )
            return tickerd_types.reconcile_result(
                ok=not result.failures,
                items_scanned=result.items_scanned,
                items_repaired=result.items_repaired,
            )
        except sqlite3.Error as exc:
            self._observe_sqlite_error(exc)
            raise

    def _require_storage_safe(self) -> None:
        if self.storage_safety_latch is not None:
            self.storage_safety_latch.require_safe()

    def _observe_sqlite_error(self, exc: sqlite3.Error) -> None:
        if self.storage_safety_latch is not None:
            self.storage_safety_latch.observe_sqlite_error(exc)


def build_work_item_payload(row: Mapping[str, object]) -> dict[str, object]:
    """Build a deterministic, JSON-friendly Tickerd payload for a Spine work row."""

    payload = {
        "payload_version": "spine.tickerd.work_item.v1",
        "work_instance_id": row["work_instance_id"],
        "item_id": row["item_id"],
        "item_version": row["item_version"],
        "work_kind": row["work_kind"],
        "eligible_at_utc": row["eligible_at_utc"],
        "notification_policy_id": row.get("notification_policy_id"),
        "notification_policy_item_version": row.get("notification_policy_item_version"),
        "notification_intent_id": row.get("notification_intent_id"),
        "notification_opportunity_id": row.get("notification_opportunity_id"),
        "normalized_notification_schedule_hash": row.get("normalized_notification_schedule_hash"),
        "occurrence_provenance_id": row.get("occurrence_provenance_id"),
        "target_anchor_role": row.get("target_anchor_role"),
        "application_scope": row.get("application_scope"),
        "target_scheduled_fact": row.get("target_scheduled_fact"),
        "target_at_utc": row.get("target_at_utc"),
        "occurrence_key": row.get("occurrence_key"),
        "delivery_target_id": row.get("delivery_target_id"),
        "generation_source_kind": row.get("generation_source_kind"),
        "generation_source_ref": row.get("generation_source_ref"),
        "work_subject_ref": row.get("work_subject_ref"),
        "policy_basis_ref": row.get("policy_basis_ref"),
        "attempt_count": row.get("attempt_count"),
        "next_attempt_at_utc": row.get("next_attempt_at_utc"),
        "reason_code": row.get("reason_code"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _apply_work_processing_outcome(
    connection: sqlite3.Connection,
    *,
    work_instance_id: str,
    outcome: WorkProcessingOutcome,
    outcome_at_utc: str,
) -> None:
    if not isinstance(outcome, WorkProcessingOutcome):
        raise SpineValidationError(INVALID_WORK_OUTCOME.lower(), "processor must return WorkProcessingOutcome")
    if outcome.status == "succeeded":
        succeed_work(
            connection,
            work_instance_id=work_instance_id,
            succeeded_at_utc=outcome_at_utc,
            reason_code=outcome.reason_code,
        )
    elif outcome.status == "failed":
        fail_work(
            connection,
            work_instance_id=work_instance_id,
            failed_at_utc=outcome_at_utc,
            reason_code=outcome.reason_code or "",
        )
    elif outcome.status == "retry":
        retry_work(
            connection,
            work_instance_id=work_instance_id,
            next_attempt_at_utc=outcome.next_attempt_at_utc or "",
            updated_at_utc=outcome_at_utc,
            reason_code=outcome.reason_code or "",
        )
    elif outcome.status == "cancelled":
        cancel_work(
            connection,
            work_instance_id=work_instance_id,
            cancelled_at_utc=outcome_at_utc,
            reason_code=outcome.reason_code or "",
        )
    else:
        raise SpineValidationError(INVALID_WORK_OUTCOME.lower(), f"unknown work outcome: {outcome.status}")


def _tickerd_public_types() -> TickerdPublicTypes:
    try:
        from tickerd import ProcessResult, RuntimeMode, WorkItem
        from tickerd.types import ReconcileResult
    except ImportError as exc:
        raise RuntimeError(
            "Tickerd is required for SpineTickerdWorkAdapter; install tickerd or put Tickerd's src directory on PYTHONPATH."
        ) from exc
    return TickerdPublicTypes(
        work_item=cast(TickerdWorkItemFactory, WorkItem),
        process_result=cast(TickerdProcessResultFactory, ProcessResult),
        reconcile_result=cast(TickerdReconcileResultFactory, ReconcileResult),
        runtime_mode=cast(TickerdRuntimeModeFactory, RuntimeMode),
    )


def _utc_z(value: datetime) -> str:
    return str(utc_z_from_datetime(value))
