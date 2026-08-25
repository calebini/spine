from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine.adapters.tickerd import SpineTickerdWorkAdapter, WorkProcessingOutcome
from spine.runtime.compatibility import (
    TickerdCompatibilityError,
    compatibility_contract,
    resolve_tickerd_compatibility,
)
from spine.runtime.storage_safety import (
    LedgerDurabilityLatchedError,
    SpineStorageSafetyGate,
    StorageSafetyLatch,
    StorageSafetyPolicy,
)

ROOT = Path(__file__).parents[1]

try:
    import tickerd  # noqa: F401

    TICKERD_IMPORTABLE = True
except ImportError:
    TICKERD_IMPORTABLE = False

try:
    metadata.version("tickerd")
    TICKERD_INSTALLED = True
except metadata.PackageNotFoundError:
    TICKERD_INSTALLED = False


class TickerdRuntimeCompatibilityTests(unittest.TestCase):
    def test_packaged_contract_matches_repository_contract(self) -> None:
        source_path = ROOT / "contracts" / "spine-tickerd-compatibility.v1.json"
        packaged_path = ROOT / "src" / "spine" / "contracts" / "spine-tickerd-compatibility.v1.json"
        self.assertEqual(packaged_path.read_bytes(), source_path.read_bytes())
        source = json.loads(source_path.read_text(encoding="utf-8"))
        self.assertEqual(compatibility_contract(), source)

    def test_version_mismatch_fails_closed_with_sorted_diagnostic(self) -> None:
        with (
            patch("spine.runtime.compatibility.metadata.version", return_value="0.1.0"),
            self.assertRaises(TickerdCompatibilityError) as raised,
        ):
            resolve_tickerd_compatibility()
        diagnostic = raised.exception.diagnostic
        self.assertEqual(diagnostic["event"], "ledger_runtime_preflight_failed")
        self.assertEqual(diagnostic["reason"], "runtime_dependency_mismatch")
        self.assertIn("package_version", diagnostic["mismatch_fields"])
        self.assertEqual(diagnostic["mismatch_fields"], sorted(set(diagnostic["mismatch_fields"])))

    @unittest.skipUnless(TICKERD_IMPORTABLE and TICKERD_INSTALLED, "exact Tickerd distribution is not installed")
    def test_installed_tickerd_passes_exact_runtime_admission(self) -> None:
        info = resolve_tickerd_compatibility()
        self.assertEqual(info.package_version, "0.2.0")
        self.assertEqual(info.capability_id, "tickerd.runtime-capabilities.v1")


class StorageSafetyTests(unittest.TestCase):
    def test_latch_is_monotonic_and_recognizes_sqlite_full(self) -> None:
        latch = StorageSafetyLatch()
        error = sqlite3.OperationalError("database or disk is full")
        self.assertTrue(latch.observe_sqlite_error(error))
        self.assertTrue(latch.is_latched)
        first = latch.latched_at_utc
        latch.latch()
        self.assertEqual(latch.latched_at_utc, first)
        with self.assertRaises(LedgerDurabilityLatchedError):
            latch.require_safe()

    def test_adapter_refuses_work_after_durability_latch(self) -> None:
        latch = StorageSafetyLatch()
        latch.latch()
        adapter = SpineTickerdWorkAdapter(sqlite3.connect(":memory:"), storage_safety_latch=latch)
        try:
            with self.assertRaises(LedgerDurabilityLatchedError):
                adapter.list_work_items(
                    SimpleNamespace(actual_start_ts=datetime.now(UTC)),
                    1,
                )
        finally:
            adapter.connection.close()

    @unittest.skipUnless(TICKERD_IMPORTABLE, "Tickerd is not importable")
    def test_adapter_latches_sqlite_full_from_work_discovery(self) -> None:
        latch = StorageSafetyLatch()
        adapter = SpineTickerdWorkAdapter(sqlite3.connect(":memory:"), storage_safety_latch=latch)
        try:
            with (
                patch(
                    "spine.adapters.tickerd.list_eligible_work",
                    side_effect=sqlite3.OperationalError("database or disk is full"),
                ),
                self.assertRaisesRegex(sqlite3.OperationalError, "disk is full"),
            ):
                adapter.list_work_items(SimpleNamespace(actual_start_ts=datetime.now(UTC)), 1)
            self.assertTrue(latch.is_latched)
            with self.assertRaises(LedgerDurabilityLatchedError):
                adapter.list_work_items(SimpleNamespace(actual_start_ts=datetime.now(UTC)), 1)
        finally:
            adapter.connection.close()

    @unittest.skipUnless(TICKERD_IMPORTABLE, "Tickerd is not importable")
    def test_adapter_latches_sqlite_full_from_outcome_persistence(self) -> None:
        latch = StorageSafetyLatch()
        adapter = SpineTickerdWorkAdapter(
            sqlite3.connect(":memory:"),
            processor=lambda connection, work, envelope: WorkProcessingOutcome.succeeded(),
            storage_safety_latch=latch,
        )
        envelope = SimpleNamespace(actual_start_ts=datetime.now(UTC))
        try:
            with (
                patch("spine.adapters.tickerd.require_processable_work", return_value={"status": "started"}),
                patch("spine.adapters.tickerd.start_work"),
                patch(
                    "spine.adapters.tickerd._apply_work_processing_outcome",
                    side_effect=sqlite3.OperationalError("database or disk is full"),
                ),
                patch("spine.adapters.tickerd.fail_work") as fail_work,
                self.assertRaisesRegex(sqlite3.OperationalError, "disk is full"),
            ):
                adapter.process_work_item(
                    SimpleNamespace(item_id="work-1"),
                    envelope,
                    side_effects_allowed=True,
                )
            self.assertTrue(latch.is_latched)
            fail_work.assert_not_called()
        finally:
            adapter.connection.close()

    @unittest.skipUnless(TICKERD_IMPORTABLE, "Tickerd is not importable")
    def test_critical_pressure_maps_to_bounded_tickerd_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.sqlite"
            ledger.touch()
            free = shutil.disk_usage(root).free
            gate = SpineStorageSafetyGate(
                ledger_path=ledger,
                worker_state_path=root,
                policy=StorageSafetyPolicy(
                    warning_free_bytes=free + 2,
                    critical_free_bytes=free + 1,
                    reserve_bytes=1,
                    critical_storage_action="exit_nonzero",
                ),
                latch=StorageSafetyLatch(),
            )
            context = SimpleNamespace(actual_start_ts=datetime.now(UTC))
            decision = gate.evaluate(context)
        self.assertEqual(decision.action.value, "terminate_nonzero")
        self.assertEqual(decision.reason, "storage_safety_stop")
        self.assertEqual(decision.facts["primary_reason"], "critical_storage_pressure")
        schema = json.loads((ROOT / "contracts" / "schemas" / "storage-safety-facts.schema.json").read_text())
        Draft202012Validator(schema).validate(decision.facts)


if __name__ == "__main__":
    unittest.main()
