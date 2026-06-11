"""Structural protocols for Spine's Tickerd integration boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class TickerdCycleEnvelope(Protocol):
    """Cycle metadata from Tickerd that Spine needs for deterministic work processing."""

    trace_id: str
    cycle_id: str
    causation_id: str
    scheduled_tick_ts: datetime
    actual_start_ts: datetime
    runtime_mode: object


@runtime_checkable
class TickerdWorkItem(Protocol):
    """A Tickerd work item carrying Spine work identity and a JSON-friendly payload."""

    item_id: str
    payload: Mapping[str, object]


class TickerdWorkItemFactory(Protocol):
    def __call__(self, *, item_id: str, payload: Mapping[str, object]) -> TickerdWorkItem: ...


@runtime_checkable
class TickerdRuntimeMode(Protocol):
    """Opaque runtime mode value returned to Tickerd."""


class TickerdRuntimeModeFactory(Protocol):
    def __call__(self, value: str) -> TickerdRuntimeMode: ...


@runtime_checkable
class TickerdProcessResult(Protocol):
    """Tickerd process result returned by Spine's work processor adapter."""

    status: object
    reason: str | None


class TickerdProcessResultFactory(Protocol):
    def blocked(self, reason: str = "SIDE_EFFECTS_BLOCKED") -> TickerdProcessResult: ...

    def failed(self, reason: str = "PROCESSING_FAILED") -> TickerdProcessResult: ...

    def processed(self) -> TickerdProcessResult: ...


@runtime_checkable
class TickerdReconcileResult(Protocol):
    """Tickerd reconciliation result returned by Spine's reconciler adapter."""

    ok: bool
    items_scanned: int
    items_repaired: int
    reason: str | None


class TickerdReconcileResultFactory(Protocol):
    def __call__(self, *, ok: bool, items_scanned: int, items_repaired: int) -> TickerdReconcileResult: ...


@dataclass(frozen=True)
class TickerdPublicTypes:
    """Runtime Tickerd constructors, typed structurally so Spine avoids importing Tickerd at import time."""

    work_item: TickerdWorkItemFactory
    process_result: TickerdProcessResultFactory
    reconcile_result: TickerdReconcileResultFactory
    runtime_mode: TickerdRuntimeModeFactory
