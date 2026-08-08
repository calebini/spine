"""Production-shaped Spine worker runtime."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spine.adapters import (
    DEFAULT_OPENCLAW_CHANNEL,
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
    OpenClawOutboundMessage,
    SpineTickerdWorkAdapter,
)
from spine.ledger import connect, initialize_schema
from spine.runtime.tickerd_observe import RUNTIME_MODES
from spine.runtime.tickerd_runner import SpineRunnerPaths, _tickerd_runner_types

FAKE_OPENCLAW_RESULTS = ("delivered", "transient", "permanent", "blocked", "binding_error", "send_exception")
OPENCLAW_SENDERS = ("fake", "gateway")
WORKER_BINDINGS = ("openclaw",)


@dataclass(frozen=True)
class SpineWorkerPaths:
    """Filesystem paths written by the Spine worker."""

    runner: SpineRunnerPaths
    sends_path: Path

    @classmethod
    def from_state_dir(cls, state_dir: Path | str) -> SpineWorkerPaths:
        runner_paths = SpineRunnerPaths.from_state_dir(state_dir)
        return cls(runner=runner_paths, sends_path=runner_paths.state_dir / "openclaw_sends.jsonl")


@dataclass(frozen=True)
class FakeOpenClawSender:
    """File-backed fake OpenClaw sender for deployment dry runs."""

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


def run_spine_worker(
    connection: sqlite3.Connection,
    *,
    state_dir: Path | str,
    runtime_mode: str = "active",
    trace_id: str = "spine-worker",
    max_cycles: int | None = None,
    tick_interval_ms: int = 1000,
    reconcile_interval_ms: int = 5000,
    max_work_items_per_tick: int = 100,
    bindings: Sequence[str] = WORKER_BINDINGS,
    openclaw_channel: str = DEFAULT_OPENCLAW_CHANNEL,
    openclaw_sender_mode: str = "fake",
    openclaw_fake_result: str = "delivered",
    install_signal_handlers: bool = True,
) -> Any:
    """Run Spine work through Tickerd with the configured worker bindings."""

    (
        TickerdConfig,
        RuntimeKernel,
        FileLockBackend,
        JsonFileHealthSink,
        JsonlFileEventSink,
        ForegroundRunner,
    ) = _tickerd_runner_types()
    paths = SpineWorkerPaths.from_state_dir(state_dir)
    paths.runner.state_dir.mkdir(parents=True, exist_ok=True)
    processor = _worker_processor(
        paths=paths,
        bindings=bindings,
        openclaw_channel=openclaw_channel,
        openclaw_sender_mode=openclaw_sender_mode,
        openclaw_fake_result=openclaw_fake_result,
    )
    adapter = SpineTickerdWorkAdapter(connection, runtime_mode=runtime_mode, processor=processor)
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
    _validate_args(args)

    db_path = Path(args.db)
    if not db_path.exists() and not args.initialize_schema:
        raise SystemExit(f"database does not exist: {db_path}; pass --initialize-schema to create it")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    try:
        if args.initialize_schema:
            initialize_schema(connection)
        bindings = _parse_bindings(args.bindings)
        result = run_spine_worker(
            connection,
            state_dir=args.state_dir,
            runtime_mode=args.mode,
            trace_id=args.trace_id,
            max_cycles=args.max_cycles,
            tick_interval_ms=args.tick_interval_ms,
            reconcile_interval_ms=args.reconcile_interval_ms,
            max_work_items_per_tick=args.max_work_items,
            bindings=bindings,
            openclaw_channel=args.openclaw_channel,
            openclaw_sender_mode=args.openclaw_sender,
            openclaw_fake_result=args.openclaw_fake_result,
            install_signal_handlers=True,
        )
    finally:
        connection.close()

    paths = SpineWorkerPaths.from_state_dir(args.state_dir)
    payload = {
        "database": str(db_path),
        "state_dir": str(paths.runner.state_dir),
        "bindings": args.bindings,
        "openclaw_sends": str(paths.sends_path),
        "openclaw_fake_result": args.openclaw_fake_result,
        "openclaw_channel": args.openclaw_channel,
        "openclaw_sender": args.openclaw_sender,
        "runtime_mode": args.mode,
        "exit_code": result.exit_code,
        "reason": result.reason,
        "cycles_completed": result.cycles_completed,
    }
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


def _worker_processor(
    *,
    paths: SpineWorkerPaths,
    bindings: Sequence[str],
    openclaw_channel: str,
    openclaw_sender_mode: str,
    openclaw_fake_result: str,
) -> Any:
    if tuple(bindings) == ("openclaw",):
        sender = _openclaw_sender(paths=paths, sender_mode=openclaw_sender_mode, fake_result=openclaw_fake_result)
        return OpenClawNotificationProcessor(sender=sender, channel_hint=openclaw_channel)
    raise ValueError(f"unsupported worker bindings: {','.join(bindings)}")


def _openclaw_sender(*, paths: SpineWorkerPaths, sender_mode: str, fake_result: str) -> Any:
    if sender_mode == "gateway":
        return OpenClawGatewaySender(OpenClawGatewayConfig.from_env())
    if sender_mode == "fake":
        return FakeOpenClawSender(paths.sends_path, result=fake_result)
    raise ValueError(f"unknown OpenClaw sender mode: {sender_mode}")


def _validate_args(args: argparse.Namespace) -> None:
    if args.max_cycles is not None and args.max_cycles < 1:
        raise SystemExit("--max-cycles must be at least 1 when provided")
    if args.max_work_items < 1:
        raise SystemExit("--max-work-items must be at least 1")
    _parse_bindings(args.bindings)
    _require_non_empty("--openclaw-channel", args.openclaw_channel)
    if args.openclaw_sender == "gateway" and not args.allow_real_send:
        raise SystemExit("--openclaw-sender gateway requires --allow-real-send")


def _parse_bindings(raw: str) -> tuple[str, ...]:
    bindings = tuple(binding.strip() for binding in raw.split(",") if binding.strip())
    if not bindings:
        raise SystemExit("--bindings must include at least one binding")
    unsupported = tuple(binding for binding in bindings if binding not in WORKER_BINDINGS)
    if unsupported:
        raise SystemExit(f"unsupported worker binding(s): {','.join(unsupported)}")
    if bindings != ("openclaw",):
        raise SystemExit("only --bindings openclaw is supported in this release")
    return bindings


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise SystemExit(f"{name} must be non-empty")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Spine's Tickerd-backed worker.")
    parser.add_argument("--db", required=True, help="Path to a Spine SQLite ledger database.")
    parser.add_argument("--state-dir", required=True, help="Directory for lock, owner, health, Tickerd events, and fake sends.")
    parser.add_argument("--initialize-schema", action="store_true", help="Initialize the Spine schema before running.")
    parser.add_argument("--mode", choices=RUNTIME_MODES, default="active", help="Tickerd runtime mode.")
    parser.add_argument(
        "--bindings",
        default="openclaw",
        help="Comma-separated worker bindings to attach. Currently supports: openclaw.",
    )
    parser.add_argument(
        "--openclaw-sender",
        choices=OPENCLAW_SENDERS,
        default="fake",
        help="OpenClaw sender binding to use. Gateway mode can perform a real external send.",
    )
    parser.add_argument(
        "--openclaw-channel",
        default=DEFAULT_OPENCLAW_CHANNEL,
        help="OpenClaw gateway channel value (default: whatsapp).",
    )
    parser.add_argument("--allow-real-send", action="store_true", help="Required with --openclaw-sender gateway.")
    parser.add_argument(
        "--openclaw-fake-result",
        choices=FAKE_OPENCLAW_RESULTS,
        default="delivered",
        help="Fake OpenClaw sender result to return.",
    )
    parser.add_argument("--max-cycles", type=int, help="Stop after this many cycles. Omit for a long-running service.")
    parser.add_argument("--trace-id", default="spine-worker", help="Trace id for emitted Tickerd records.")
    parser.add_argument("--tick-interval-ms", type=int, default=1000, help="Tickerd tick interval.")
    parser.add_argument("--reconcile-interval-ms", type=int, default=5000, help="Tickerd reconcile cadence.")
    parser.add_argument("--max-work-items", type=int, default=100, help="Maximum work items to process per cycle.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
