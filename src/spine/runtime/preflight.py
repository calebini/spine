"""Worker admission helpers shared by Spine runtime entrypoints."""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import missing_worker_runtime_contract_versions
from spine.core import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema
from spine.runtime.compatibility import TickerdCompatibilityError, resolve_tickerd_compatibility

WORKER_PREFLIGHT_EVENT = "ledger_runtime_preflight_failed"


@dataclass(frozen=True)
class WorkerPreflightFailureResult:
    exit_code: int = 3
    reason: str = WORKER_PREFLIGHT_EVENT
    cycles_completed: int = 0


@dataclass(frozen=True)
class WorkerBootstrapConfig:
    max_health_age_ms: int = 5000
    health_fail_mode: str = "strict"
    event_log_max_bytes: int = 10 * 1024 * 1024
    event_log_backup_count: int = 5


@dataclass(frozen=True)
class _BootstrapHealthSnapshot:
    snapshot_ts_utc: datetime
    max_health_age_ms: int
    health_fail_mode: str

    def as_record(self) -> dict[str, Any]:
        return {
            "state": "DOWN",
            "is_ready": False,
            "snapshot_ts_utc": self.snapshot_ts_utc.astimezone(UTC).isoformat(),
            "max_health_age_ms": self.max_health_age_ms,
            "health_fail_mode": self.health_fail_mode,
            "last_successful_cycle_id": None,
            "last_failure_reason": WORKER_PREFLIGHT_EVENT,
            "health_age_ms": 0,
        }


class BootstrapHealthSink:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def write(self, snapshot: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(snapshot.as_record(), sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)


class BootstrapEventSink:
    def __init__(self, path: Path | str, *, max_bytes: int, backup_count: int) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count

    def emit(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True) + "\n"
        incoming = len(line.encode("utf-8"))
        if incoming > self.max_bytes:
            raise ValueError("preflight diagnostic exceeds event-log bound")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size + incoming > self.max_bytes:
            oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
            if oldest.exists():
                oldest.unlink()
            for index in range(self.backup_count - 1, 0, -1):
                source = self.path.with_name(f"{self.path.name}.{index}")
                if source.exists():
                    source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
            self.path.replace(self.path.with_name(f"{self.path.name}.1"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def admit_worker(
    connection: sqlite3.Connection,
    *,
    config: Any,
    health_sink: Any,
    event_sink: Any,
    implemented_versions: frozenset[str] | None = None,
    dependency_resolver: Any = None,
) -> WorkerPreflightFailureResult | None:
    """Run bounded worker admission before any adapter or Tickerd kernel exists."""

    try:
        verify_runtime_schema(connection)
    except SpineValidationError as exc:
        if exc.code.startswith("ledger_schema_object_") or exc.code.startswith("ledger_schema_missing_"):
            object_type, object_name = _schema_object_identity(exc.message)
            return emit_worker_preflight_failure(
                config=config,
                health_sink=health_sink,
                event_sink=event_sink,
                reason="schema_object_mismatch",
                object_type=object_type,
                object_name=object_name,
            )
        return emit_worker_preflight_failure(
            config=config,
            health_sink=health_sink,
            event_sink=event_sink,
            reason="schema_version_mismatch",
        )
    except sqlite3.Error:
        return emit_worker_preflight_failure(
            config=config,
            health_sink=health_sink,
            event_sink=event_sink,
            reason="database_unavailable",
        )
    versions = IMPLEMENTED_CONTRACT_VERSIONS if implemented_versions is None else implemented_versions
    missing = missing_worker_runtime_contract_versions(versions)
    if missing:
        return emit_worker_preflight_failure(
            config=config,
            health_sink=health_sink,
            event_sink=event_sink,
            reason="runtime_contract_mismatch",
            required_contract_versions=missing,
        )
    resolver = resolve_tickerd_compatibility if dependency_resolver is None else dependency_resolver
    try:
        resolver()
    except TickerdCompatibilityError as exc:
        return emit_worker_preflight_failure(
            config=config,
            health_sink=health_sink,
            event_sink=event_sink,
            reason="runtime_dependency_mismatch",
            dependency_diagnostic=exc.diagnostic,
        )
    return None


def _schema_object_identity(message: str) -> tuple[str, str]:
    words = message.split()
    for object_type in ("table", "index", "trigger"):
        if object_type in words:
            position = words.index(object_type)
            if position + 1 < len(words):
                return object_type, words[position + 1]
    return "unknown", "unknown"


def emit_worker_preflight_failure(
    *,
    config: Any,
    health_sink: Any,
    event_sink: Any,
    reason: str,
    object_type: str | None = None,
    object_name: str | None = None,
    required_contract_versions: tuple[str, ...] = (),
    dependency_diagnostic: dict[str, Any] | None = None,
) -> WorkerPreflightFailureResult:
    """Persist DOWN/not-ready health and exactly one startup diagnostic."""

    with suppress(Exception):
        health_sink.write(
            _BootstrapHealthSnapshot(
                snapshot_ts_utc=datetime.now(UTC),
                max_health_age_ms=config.max_health_age_ms,
                health_fail_mode=getattr(config.health_fail_mode, "value", config.health_fail_mode),
            )
        )
    diagnostic: dict[str, Any] = {"event": WORKER_PREFLIGHT_EVENT, "reason": reason}
    if dependency_diagnostic is not None:
        diagnostic = dict(dependency_diagnostic)
    if object_type is not None and object_name is not None:
        diagnostic.update({"object_type": object_type, "object_name": object_name})
    if required_contract_versions:
        diagnostic["required_contract_versions"] = sorted(set(required_contract_versions))
    try:
        event_sink.emit(diagnostic)
    except Exception:
        sys.stderr.write(json.dumps(diagnostic, sort_keys=True) + "\n")
    return WorkerPreflightFailureResult()
