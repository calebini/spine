import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from spine.protocols import (
    TickerdCycleEnvelope,
    TickerdProcessResult,
    TickerdPublicTypes,
    TickerdReconcileResult,
    TickerdWorkItem,
)


@dataclass(frozen=True)
class FakeWorkItem:
    item_id: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class FakeCycleEnvelope:
    trace_id: str
    cycle_id: str
    causation_id: str
    scheduled_tick_ts: datetime
    actual_start_ts: datetime
    runtime_mode: object


@dataclass(frozen=True)
class FakeProcessResult:
    status: str
    reason: str | None = None

    @classmethod
    def blocked(cls, reason: str = "SIDE_EFFECTS_BLOCKED") -> "FakeProcessResult":
        return cls("blocked", reason)

    @classmethod
    def failed(cls, reason: str = "PROCESSING_FAILED") -> "FakeProcessResult":
        return cls("failed", reason)

    @classmethod
    def processed(cls) -> "FakeProcessResult":
        return cls("processed")


@dataclass(frozen=True)
class FakeReconcileResult:
    ok: bool
    items_scanned: int
    items_repaired: int
    reason: str | None = None


class FakeRuntimeMode(str):
    pass


class TickerdProtocolTests(unittest.TestCase):
    def test_protocol_shapes_do_not_require_tickerd_imports(self) -> None:
        cycle = FakeCycleEnvelope(
            trace_id="trace-1",
            cycle_id="cycle-1",
            causation_id="ROOT:cycle-1",
            scheduled_tick_ts=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
            actual_start_ts=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
            runtime_mode=FakeRuntimeMode("observe_only"),
        )
        item = FakeWorkItem(item_id="work-1", payload={"item_id": "task-1"})

        self.assertIsInstance(cycle, TickerdCycleEnvelope)
        self.assertIsInstance(item, TickerdWorkItem)

    def test_public_type_bundle_exposes_structural_factories(self) -> None:
        public_types = TickerdPublicTypes(
            work_item=FakeWorkItem,
            process_result=FakeProcessResult,
            reconcile_result=FakeReconcileResult,
            runtime_mode=FakeRuntimeMode,
        )

        item = public_types.work_item(item_id="work-1", payload={"item_id": "task-1"})
        process_result = public_types.process_result.blocked("SIDE_EFFECTS_BLOCKED")
        reconcile_result = public_types.reconcile_result(ok=True, items_scanned=1, items_repaired=0)
        mode = public_types.runtime_mode("observe_only")

        self.assertEqual(item.item_id, "work-1")
        self.assertIsInstance(process_result, TickerdProcessResult)
        self.assertEqual(process_result.reason, "SIDE_EFFECTS_BLOCKED")
        self.assertIsInstance(reconcile_result, TickerdReconcileResult)
        self.assertEqual(reconcile_result.items_scanned, 1)
        self.assertEqual(mode, "observe_only")


if __name__ == "__main__":
    unittest.main()
