"""Run a bounded fake-OpenClaw active Tickerd smoke."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence

from spine.ledger import connect, initialize_schema
from spine.runtime.worker import (
    FAKE_OPENCLAW_RESULTS,
    OPENCLAW_SENDERS,
    SpineWorkerPaths,
    run_spine_worker,
)
from spine.runtime.seed_demo import seed_demo_ledger

OpenClawSmokePaths = SpineWorkerPaths


def run_openclaw_smoke(
    connection: sqlite3.Connection,
    *,
    state_dir: Path | str,
    trace_id: str = "spine-openclaw-smoke",
    max_cycles: int = 1,
    tick_interval_ms: int = 1,
    reconcile_interval_ms: int = 1,
    max_work_items_per_tick: int = 100,
    fake_result: str = "delivered",
    sender_mode: str = "fake",
    install_signal_handlers: bool = True,
) -> Any:
    """Run Tickerd active mode with a fake or explicitly enabled OpenClaw processor."""

    return run_spine_worker(
        connection,
        state_dir=state_dir,
        runtime_mode="active",
        trace_id=trace_id,
        max_cycles=max_cycles,
        tick_interval_ms=tick_interval_ms,
        reconcile_interval_ms=reconcile_interval_ms,
        max_work_items_per_tick=max_work_items_per_tick,
        bindings=("openclaw",),
        openclaw_sender_mode=sender_mode,
        openclaw_fake_result=fake_result,
        install_signal_handlers=install_signal_handlers,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.max_cycles < 1:
        raise SystemExit("--max-cycles must be at least 1")
    if args.max_work_items < 1:
        raise SystemExit("--max-work-items must be at least 1")
    if args.seed_demo and args.initialize_schema:
        raise SystemExit("--seed-demo already initializes the schema; do not pass --initialize-schema")
    if args.sender == "gateway" and not args.allow_real_send:
        raise SystemExit("--sender gateway requires --allow-real-send")

    db_path = Path(args.db)
    if db_path.exists() and args.seed_demo:
        raise SystemExit(f"database already exists: {db_path}; omit --seed-demo to reuse it")
    if not db_path.exists() and not (args.initialize_schema or args.seed_demo):
        raise SystemExit(f"database does not exist: {db_path}; pass --seed-demo or --initialize-schema to create it")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    seed_result: dict[str, object] | None = None
    try:
        if args.seed_demo:
            seed_result = seed_demo_ledger(connection)
        elif args.initialize_schema:
            initialize_schema(connection)
        result = run_openclaw_smoke(
            connection,
            state_dir=args.state_dir,
            trace_id=args.trace_id,
            max_cycles=args.max_cycles,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
            fake_result=args.fake_result,
            sender_mode=args.sender,
            install_signal_handlers=True,
        )
    finally:
        connection.close()

    paths = OpenClawSmokePaths.from_state_dir(args.state_dir)
    payload = {
        "database": str(db_path),
        "state_dir": str(paths.runner.state_dir),
        "openclaw_sends": str(paths.sends_path),
        "fake_result": args.fake_result,
        "sender": args.sender,
        "exit_code": result.exit_code,
        "reason": result.reason,
        "cycles_completed": result.cycles_completed,
    }
    if seed_result is not None:
        payload["seed"] = seed_result
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded fake-OpenClaw active Tickerd smoke.")
    parser.add_argument("--db", required=True, help="Path to a Spine SQLite ledger database.")
    parser.add_argument("--state-dir", required=True, help="Directory for lock, owner, health, Tickerd events, and fake sends.")
    parser.add_argument("--seed-demo", action="store_true", help="Create and seed the deterministic demo ledger first.")
    parser.add_argument("--initialize-schema", action="store_true", help="Initialize an empty Spine schema before running.")
    parser.add_argument(
        "--sender",
        choices=OPENCLAW_SENDERS,
        default="fake",
        help="OpenClaw sender binding to use. Gateway mode can perform a real external send.",
    )
    parser.add_argument("--allow-real-send", action="store_true", help="Required with --sender gateway.")
    parser.add_argument(
        "--fake-result",
        choices=FAKE_OPENCLAW_RESULTS,
        default="delivered",
        help="Fake OpenClaw sender result to return.",
    )
    parser.add_argument("--max-cycles", type=int, default=1, help="Stop after this many cycles.")
    parser.add_argument("--trace-id", default="spine-openclaw-smoke", help="Trace id for emitted Tickerd records.")
    parser.add_argument("--tick-interval-ms", type=int, default=1, help="Tickerd tick interval.")
    parser.add_argument("--reconcile-interval-ms", type=int, default=1, help="Tickerd reconcile cadence.")
    parser.add_argument("--max-work-items", type=int, default=100, help="Maximum work items to process per cycle.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
