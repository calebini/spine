"""Run a bounded fake-OpenClaw active Tickerd smoke."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
    OpenClawOutboundMessage,
)
from spine.adapters import SpineTickerdWorkAdapter
from spine.ledger import connect, initialize_schema
from spine.runtime.seed_demo import seed_demo_ledger
from spine.runtime.tickerd_runner import SpineRunnerPaths, _tickerd_runner_types


@dataclass(frozen=True)
class OpenClawSmokePaths:
    """Filesystem paths written by the fake-OpenClaw smoke."""

    runner: SpineRunnerPaths
    sends_path: Path

    @classmethod
    def from_state_dir(cls, state_dir: Path | str) -> "OpenClawSmokePaths":
        runner_paths = SpineRunnerPaths.from_state_dir(state_dir)
        return cls(runner=runner_paths, sends_path=runner_paths.state_dir / "openclaw_sends.jsonl")


@dataclass(frozen=True)
class FakeOpenClawSender:
    """File-backed fake OpenClaw sender for operator smoke tests."""

    sends_path: Path
    result: str = "delivered"

    def __call__(self, message: OpenClawOutboundMessage) -> NormalizedOpenClawResult:
        if self.result == "binding_error":
            raise OpenClawBindingError("fake OpenClaw binding unavailable")
        if self.result == "send_exception":
            raise RuntimeError("fake OpenClaw sender exception")

        provider_ref = f"fake-openclaw:{message.delivery_id}:{message.attempt_id}"
        self._write_send(message, provider_ref)
        if self.result == "delivered":
            return NormalizedOpenClawResult.delivered(provider_ref=provider_ref)
        if self.result == "transient":
            return NormalizedOpenClawResult.transient_failure(
                reason_code="openclaw_fake_transient",
                next_attempt_at_utc="2026-06-07T10:30:00Z",
            )
        if self.result == "permanent":
            return NormalizedOpenClawResult.permanent_failure(
                reason_code="openclaw_fake_permanent",
                provider_ref=provider_ref,
            )
        if self.result == "blocked":
            return NormalizedOpenClawResult.blocked(reason_code="openclaw_fake_blocked")
        raise ValueError(f"unknown fake OpenClaw result: {self.result}")

    def _write_send(self, message: OpenClawOutboundMessage, provider_ref: str) -> None:
        self.sends_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": "openclaw_fake_send",
            "fake_result": self.result,
            "provider_ref": provider_ref,
            **message.request_envelope(),
        }
        with self.sends_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


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

    (
        TickerdConfig,
        RuntimeKernel,
        FileLockBackend,
        JsonFileHealthSink,
        JsonlFileEventSink,
        ForegroundRunner,
    ) = _tickerd_runner_types()
    paths = OpenClawSmokePaths.from_state_dir(state_dir)
    paths.runner.state_dir.mkdir(parents=True, exist_ok=True)
    if sender_mode == "gateway":
        sender = OpenClawGatewaySender(OpenClawGatewayConfig.from_env())
    elif sender_mode == "fake":
        sender = FakeOpenClawSender(paths.sends_path, result=fake_result)
    else:
        raise ValueError(f"unknown OpenClaw smoke sender mode: {sender_mode}")
    processor = OpenClawNotificationProcessor(sender=sender)
    adapter = SpineTickerdWorkAdapter(connection, runtime_mode="active", processor=processor)
    config = TickerdConfig(
        tick_interval_ms=tick_interval_ms,
        reconcile_interval_ms=reconcile_interval_ms,
        max_work_items_per_tick=max_work_items_per_tick,
    )
    events = JsonlFileEventSink(paths.runner.events_path)
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
        lock_backend=FileLockBackend(paths.runner.lock_path, paths.runner.owner_path),
        health_sink=JsonFileHealthSink(paths.runner.health_path),
        event_sink=events,
        install_signal_handlers=install_signal_handlers,
    )
    return runner.run(max_cycles=max_cycles)


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
        choices=("fake", "gateway"),
        default="fake",
        help="OpenClaw sender binding to use. Gateway mode can perform a real external send.",
    )
    parser.add_argument("--allow-real-send", action="store_true", help="Required with --sender gateway.")
    parser.add_argument(
        "--fake-result",
        choices=("delivered", "transient", "permanent", "blocked", "binding_error", "send_exception"),
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
