"""Tickerd adapter for Spine work instances."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING

from spine.core import SpineValidationError
from spine.services import list_eligible_work, require_processable_work

if TYPE_CHECKING:
    from tickerd import CycleEnvelope, WorkItem


SIDE_EFFECTS_BLOCKED = "SIDE_EFFECTS_BLOCKED"
NO_PROCESSOR_CONFIGURED = "NO_PROCESSOR_CONFIGURED"
STALE_WORK_BLOCKED = "STALE_WORK_INSTANCE"

WorkProcessor = Callable[[sqlite3.Connection, Mapping[str, object], Any], Any]


@dataclass(frozen=True)
class SpineTickerdWorkAdapter:
    """Expose Spine eligible work through Tickerd's adapter protocols."""

    connection: sqlite3.Connection
    runtime_mode: str = "observe_only"
    processor: WorkProcessor | None = None

    def read_mode(self) -> Any:
        """Return Tickerd's runtime mode without making Tickerd a hard import."""

        _, _, _, RuntimeMode = _tickerd_public_types()
        return RuntimeMode(self.runtime_mode)

    def list_work_items(self, envelope: CycleEnvelope, limit: int) -> Sequence[WorkItem]:
        """Map eligible, non-stale Spine work instances into Tickerd work items."""

        WorkItem, _, _, _ = _tickerd_public_types()
        rows = list_eligible_work(self.connection, now_utc=_utc_z(envelope.actual_start_ts), limit=limit)
        return tuple(WorkItem(item_id=str(row["work_instance_id"]), payload=build_work_item_payload(row)) for row in rows)

    def process_work_item(self, item: WorkItem, envelope: CycleEnvelope, *, side_effects_allowed: bool) -> Any:
        """Validate work freshness and delegate active processing only when configured."""

        _, ProcessResult, _, _ = _tickerd_public_types()
        try:
            work_row = require_processable_work(self.connection, item.item_id)
        except SpineValidationError as exc:
            if exc.code in {"stale_work_instance", "work_instance_not_found"}:
                return ProcessResult.blocked(STALE_WORK_BLOCKED)
            raise

        if not side_effects_allowed:
            return ProcessResult.blocked(SIDE_EFFECTS_BLOCKED)
        if self.processor is None:
            return ProcessResult.blocked(NO_PROCESSOR_CONFIGURED)
        return self.processor(self.connection, work_row, envelope)

    def reconcile(self, envelope: CycleEnvelope, *, max_batches: int) -> Any:
        """Provide a bounded no-op reconciliation hook for the first integration slice."""

        _, _, ReconcileResult, _ = _tickerd_public_types()
        return ReconcileResult(ok=True, items_scanned=0, items_repaired=0)


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
        "generation_source_kind": row.get("generation_source_kind"),
        "generation_source_ref": row.get("generation_source_ref"),
        "work_subject_ref": row.get("work_subject_ref"),
        "policy_basis_ref": row.get("policy_basis_ref"),
        "attempt_count": row.get("attempt_count"),
        "next_attempt_at_utc": row.get("next_attempt_at_utc"),
        "reason_code": row.get("reason_code"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _tickerd_public_types() -> tuple[Any, Any, Any, Any]:
    try:
        from tickerd import ProcessResult, RuntimeMode, WorkItem
        from tickerd.types import ReconcileResult
    except ImportError as exc:
        raise RuntimeError(
            "Tickerd is required for SpineTickerdWorkAdapter; install tickerd or run with ../tickerd/src on PYTHONPATH."
        ) from exc
    return WorkItem, ProcessResult, ReconcileResult, RuntimeMode


def _utc_z(value: datetime) -> str:
    utc_value = value.astimezone(UTC).replace(tzinfo=None)
    return f"{utc_value.isoformat()}Z"
