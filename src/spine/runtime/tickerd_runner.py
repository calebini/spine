"""Foreground Tickerd runner for Spine."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spine.adapters import SpineTickerdWorkAdapter
from spine.ledger import connect, initialize_schema
from spine.runtime.preflight import (
    BootstrapEventSink,
    BootstrapHealthSink,
    WorkerBootstrapConfig,
    admit_worker,
    emit_worker_preflight_failure,
)
from spine.runtime.storage_safety import SpineStorageSafetyGate, StorageSafetyLatch, StorageSafetyPolicy
from spine.runtime.tickerd_observe import RUNTIME_MODES


@dataclass(frozen=True)
class SpineRunnerPaths:
    """Filesystem paths used by the Spine Tickerd foreground runner."""

    state_dir: Path
    lock_path: Path
    owner_path: Path
    health_path: Path
    events_path: Path

    @classmethod
    def from_state_dir(cls, state_dir: Path | str) -> SpineRunnerPaths:
        root = Path(state_dir)
        return cls(
            state_dir=root,
            lock_path=root / "tickerd.lock",
            owner_path=root / "owner.json",
            health_path=root / "health.json",
            events_path=root / "events.jsonl",
        )


def run_foreground(
    connection: sqlite3.Connection,
    *,
    state_dir: Path | str,
    runtime_mode: str = "observe_only",
    trace_id: str = "spine-tickerd-runner",
    max_cycles: int | None = None,
    tick_interval_ms: int = 1000,
    reconcile_interval_ms: int = 5000,
    max_work_items_per_tick: int = 100,
    install_signal_handlers: bool = True,
    scheduler_actor_subject_id: str | None = None,
    materialization_horizon_seconds: int = 86_400,
    event_log_max_bytes: int = 10 * 1024 * 1024,
    event_log_backup_count: int = 5,
    storage_warning_free_bytes: int = 1_073_741_824,
    storage_critical_free_bytes: int = 536_870_912,
    storage_reserve_bytes: int = 268_435_456,
    critical_storage_action: str = "exit_nonzero",
) -> Any:
    """Run Spine work through Tickerd's foreground runner."""

    paths = SpineRunnerPaths.from_state_dir(state_dir)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_config = WorkerBootstrapConfig(
        event_log_max_bytes=event_log_max_bytes,
        event_log_backup_count=event_log_backup_count,
    )
    preflight_failure = admit_worker(
        connection,
        config=bootstrap_config,
        health_sink=BootstrapHealthSink(paths.health_path),
        event_sink=BootstrapEventSink(
            paths.events_path,
            max_bytes=bootstrap_config.event_log_max_bytes,
            backup_count=bootstrap_config.event_log_backup_count,
        ),
    )
    if preflight_failure is not None:
        return preflight_failure
    (
        TickerdConfig,
        RuntimeKernel,
        FileLockBackend,
        JsonFileHealthSink,
        JsonlFileEventSink,
        ForegroundRunner,
    ) = _tickerd_runner_types()
    config = TickerdConfig(
        tick_interval_ms=tick_interval_ms,
        reconcile_interval_ms=reconcile_interval_ms,
        max_work_items_per_tick=max_work_items_per_tick,
        event_log_max_bytes=event_log_max_bytes,
        event_log_backup_count=event_log_backup_count,
    )
    health = JsonFileHealthSink(paths.health_path)
    events = JsonlFileEventSink.bounded(
        paths.events_path,
        max_bytes=config.event_log_max_bytes,
        backup_count=config.event_log_backup_count,
    )
    latch = StorageSafetyLatch()
    policy = StorageSafetyPolicy(
        warning_free_bytes=storage_warning_free_bytes,
        critical_free_bytes=storage_critical_free_bytes,
        reserve_bytes=storage_reserve_bytes,
        critical_storage_action=critical_storage_action,
    )
    safety_gate = SpineStorageSafetyGate(
        ledger_path=_ledger_path(connection, paths.state_dir),
        worker_state_path=paths.state_dir,
        policy=policy,
        latch=latch,
    )
    adapter = SpineTickerdWorkAdapter(
        connection,
        runtime_mode=runtime_mode,
        scheduler_actor_subject_id=scheduler_actor_subject_id,
        materialization_horizon_seconds=materialization_horizon_seconds,
        storage_safety_latch=latch,
    )
    kernel = RuntimeKernel(
        config,
        mode_reader=adapter,
        work_source=adapter,
        processor=adapter,
        reconciler=adapter,
        event_sink=events,
        trace_id=trace_id,
    )
    runner = ForegroundRunner(
        config,
        kernel=kernel,
        lock_backend=FileLockBackend(paths.lock_path, paths.owner_path),
        health_sink=health,
        event_sink=events,
        install_signal_handlers=install_signal_handlers,
        safety_gate=safety_gate,
    )
    return runner.run(max_cycles=max_cycles)


def report_database_unavailable(
    *,
    state_dir: Path | str,
    tick_interval_ms: int,
    reconcile_interval_ms: int,
    max_work_items_per_tick: int,
) -> Any:
    """Emit the required failed-admission state when the ledger cannot be opened."""

    paths = SpineRunnerPaths.from_state_dir(state_dir)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    config = WorkerBootstrapConfig()
    events = BootstrapEventSink(
        paths.events_path,
        max_bytes=config.event_log_max_bytes,
        backup_count=config.event_log_backup_count,
    )
    return emit_worker_preflight_failure(
        config=config,
        health_sink=BootstrapHealthSink(paths.health_path),
        event_sink=events,
        reason="database_unavailable",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.max_cycles is not None and args.max_cycles < 1:
        raise SystemExit("--max-cycles must be at least 1 when provided")
    if args.max_work_items < 1:
        raise SystemExit("--max-work-items must be at least 1")
    if args.materialization_horizon_seconds < 1 or args.materialization_horizon_seconds > 31_622_400:
        raise SystemExit("--materialization-horizon-seconds must be between 1 and 31622400")

    db_path = Path(args.db)
    if not db_path.exists() and not args.initialize_schema:
        result = report_database_unavailable(
            state_dir=args.state_dir,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
        )
        return int(result.exit_code)

    try:
        connection = connect(db_path)
    except (OSError, sqlite3.Error):
        result = report_database_unavailable(
            state_dir=args.state_dir,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
        )
        return int(result.exit_code)
    try:
        if args.initialize_schema:
            initialize_schema(connection)
        result = run_foreground(
            connection,
            state_dir=args.state_dir,
            runtime_mode=args.mode,
            trace_id=args.trace_id,
            max_cycles=args.max_cycles,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
            install_signal_handlers=True,
            scheduler_actor_subject_id=args.scheduler_actor_subject_id,
            materialization_horizon_seconds=args.materialization_horizon_seconds,
            event_log_max_bytes=args.event_log_max_bytes,
            event_log_backup_count=args.event_log_backup_count,
            storage_warning_free_bytes=args.storage_warning_free_bytes,
            storage_critical_free_bytes=args.storage_critical_free_bytes,
            storage_reserve_bytes=args.storage_reserve_bytes,
            critical_storage_action=args.critical_storage_action,
        )
    finally:
        connection.close()
    return int(result.exit_code)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Spine's foreground Tickerd worker.")
    parser.add_argument("--db", required=True, help="Path to a Spine SQLite ledger database.")
    parser.add_argument("--state-dir", required=True, help="Directory for lock, owner, health, and event files.")
    parser.add_argument("--initialize-schema", action="store_true", help="Initialize the Spine schema before running.")
    parser.add_argument("--mode", choices=RUNTIME_MODES, default="observe_only", help="Tickerd runtime mode.")
    parser.add_argument("--max-cycles", type=int, help="Stop after this many cycles.")
    parser.add_argument("--trace-id", default="spine-tickerd-runner", help="Trace id for emitted Tickerd records.")
    parser.add_argument("--tick-interval-ms", type=int, default=1000, help="Tickerd tick interval.")
    parser.add_argument("--reconcile-interval-ms", type=int, default=5000, help="Tickerd reconcile cadence.")
    parser.add_argument("--max-work-items", type=int, default=100, help="Maximum work items to process per cycle.")
    parser.add_argument("--scheduler-actor-subject-id", help="Existing subject used for deterministic scheduler receipts.")
    parser.add_argument(
        "--materialization-horizon-seconds", type=int, default=86400, help="Bounded future notification horizon per reconcile cycle."
    )
    parser.add_argument("--event-log-max-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--event-log-backup-count", type=int, default=5)
    parser.add_argument("--storage-warning-free-bytes", type=int, default=1_073_741_824)
    parser.add_argument("--storage-critical-free-bytes", type=int, default=536_870_912)
    parser.add_argument("--storage-reserve-bytes", type=int, default=268_435_456)
    parser.add_argument("--critical-storage-action", choices=("suspend", "exit_nonzero"), default="exit_nonzero")
    return parser.parse_args(argv)


def _ledger_path(connection: sqlite3.Connection, fallback_root: Path) -> Path:
    row = connection.execute("PRAGMA database_list").fetchone()
    raw = "" if row is None else str(row[2])
    return Path(raw) if raw else fallback_root / "in-memory-ledger.sqlite"


def _tickerd_runner_types() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from tickerd import RuntimeKernel, TickerdConfig
        from tickerd.events import JsonlFileEventSink
        from tickerd.locks import FileLockBackend
        from tickerd.runner import ForegroundRunner
        from tickerd.sinks import JsonFileHealthSink
    except ImportError as exc:
        raise RuntimeError("Tickerd is required for this runtime; install tickerd or put Tickerd's src directory on PYTHONPATH.") from exc
    return TickerdConfig, RuntimeKernel, FileLockBackend, JsonFileHealthSink, JsonlFileEventSink, ForegroundRunner


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
