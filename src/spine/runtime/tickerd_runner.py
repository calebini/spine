"""Foreground Tickerd runner for Spine."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from spine.adapters import SpineTickerdWorkAdapter
from spine.ledger import connect, initialize_schema
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
    def from_state_dir(cls, state_dir: Path | str) -> "SpineRunnerPaths":
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
) -> Any:
    """Run Spine work through Tickerd's foreground runner."""

    (
        TickerdConfig,
        RuntimeKernel,
        FileLockBackend,
        JsonFileHealthSink,
        JsonlFileEventSink,
        ForegroundRunner,
    ) = _tickerd_runner_types()
    paths = SpineRunnerPaths.from_state_dir(state_dir)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    config = TickerdConfig(
        tick_interval_ms=tick_interval_ms,
        reconcile_interval_ms=reconcile_interval_ms,
        max_work_items_per_tick=max_work_items_per_tick,
    )
    adapter = SpineTickerdWorkAdapter(connection, runtime_mode=runtime_mode)
    events = JsonlFileEventSink(paths.events_path)
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
        health_sink=JsonFileHealthSink(paths.health_path),
        event_sink=events,
        install_signal_handlers=install_signal_handlers,
    )
    return runner.run(max_cycles=max_cycles)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.max_cycles is not None and args.max_cycles < 1:
        raise SystemExit("--max-cycles must be at least 1 when provided")
    if args.max_work_items < 1:
        raise SystemExit("--max-work-items must be at least 1")

    db_path = Path(args.db)
    if not db_path.exists() and not args.initialize_schema:
        raise SystemExit(f"database does not exist: {db_path}; pass --initialize-schema to create it")

    connection = connect(db_path)
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
    return parser.parse_args(argv)


def _tickerd_runner_types() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from tickerd import RuntimeKernel, TickerdConfig
        from tickerd.events import JsonlFileEventSink
        from tickerd.locks import FileLockBackend
        from tickerd.runner import ForegroundRunner
        from tickerd.sinks import JsonFileHealthSink
    except ImportError as exc:
        raise RuntimeError(
            "Tickerd is required for this runtime; install tickerd or put Tickerd's src directory on PYTHONPATH."
        ) from exc
    return TickerdConfig, RuntimeKernel, FileLockBackend, JsonFileHealthSink, JsonlFileEventSink, ForegroundRunner


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
