"""Observe eligible Spine work through Tickerd."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence, TextIO

from spine.adapters import SpineTickerdWorkAdapter
from spine.ledger import connect, initialize_schema

RUNTIME_MODES = ("active", "observe_only", "suspended")


def run_observe_cycles(
    connection: sqlite3.Connection,
    *,
    cycles: int = 1,
    runtime_mode: str = "observe_only",
    trace_id: str = "spine-tickerd-observe",
    stream: TextIO | None = None,
    start_at_utc: datetime | None = None,
    tick_interval_ms: int = 1000,
    reconcile_interval_ms: int = 5000,
    max_work_items_per_tick: int = 100,
) -> list[dict[str, Any]]:
    """Run a bounded Tickerd kernel loop against Spine eligible work."""

    TickerdConfig, JsonLineEventSink, RuntimeKernel = _tickerd_runtime_types()
    config = TickerdConfig(
        tick_interval_ms=tick_interval_ms,
        reconcile_interval_ms=reconcile_interval_ms,
        max_work_items_per_tick=max_work_items_per_tick,
    )
    events = JsonLineEventSink(stream)
    adapter = SpineTickerdWorkAdapter(connection, runtime_mode=runtime_mode)
    kernel = RuntimeKernel(
        config,
        mode_reader=adapter,
        work_source=adapter,
        processor=adapter,
        reconciler=adapter,
        event_sink=events,
        trace_id=trace_id,
    )
    start = (start_at_utc or datetime.now(UTC)).astimezone(UTC)
    summaries: list[dict[str, Any]] = []

    kernel.startup(start)
    for cycle_number in range(cycles):
        cycle_time = start + timedelta(milliseconds=tick_interval_ms * (cycle_number + 1))
        summaries.append(kernel.run_cycle(cycle_time, cycle_time))
    kernel.shutdown(start + timedelta(milliseconds=tick_interval_ms * (cycles + 1)), "max_cycles_reached")
    return summaries


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.cycles < 1:
        raise SystemExit("--cycles must be at least 1")
    if args.max_work_items < 1:
        raise SystemExit("--max-work-items must be at least 1")

    db_path = Path(args.db_path)
    if not db_path.exists() and not args.initialize_schema:
        raise SystemExit(f"database does not exist: {db_path}; pass --initialize-schema to create it")

    connection = connect(db_path)
    try:
        if args.initialize_schema:
            initialize_schema(connection)
        run_observe_cycles(
            connection,
            cycles=args.cycles,
            runtime_mode=args.mode,
            trace_id=args.trace_id,
            stream=sys.stdout,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
        )
    finally:
        connection.close()
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded Tickerd observe pass over Spine eligible work.")
    parser.add_argument("db_path", help="Path to a Spine SQLite ledger database.")
    parser.add_argument("--initialize-schema", action="store_true", help="Initialize the Spine schema before observing.")
    parser.add_argument("--mode", choices=RUNTIME_MODES, default="observe_only", help="Tickerd runtime mode.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of bounded cycles to run.")
    parser.add_argument("--trace-id", default="spine-tickerd-observe", help="Trace id for emitted Tickerd records.")
    parser.add_argument("--tick-interval-ms", type=int, default=1000, help="Synthetic interval between bounded cycles.")
    parser.add_argument("--reconcile-interval-ms", type=int, default=5000, help="Tickerd reconcile cadence.")
    parser.add_argument("--max-work-items", type=int, default=100, help="Maximum work items to observe per cycle.")
    return parser.parse_args(argv)


def _tickerd_runtime_types() -> tuple[Any, Any, Any]:
    try:
        from tickerd import RuntimeKernel, TickerdConfig
        from tickerd.events import JsonLineEventSink
    except ImportError as exc:
        raise RuntimeError(
            "Tickerd is required for this runtime; install tickerd or put Tickerd's src directory on PYTHONPATH."
        ) from exc
    return TickerdConfig, JsonLineEventSink, RuntimeKernel


if __name__ == "__main__":
    raise SystemExit(main())
