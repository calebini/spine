"""Worker admission helpers shared by Spine runtime entrypoints."""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import missing_worker_runtime_contract_versions
from spine.core import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema

WORKER_PREFLIGHT_EVENT = "ledger_runtime_preflight_failed"


@dataclass(frozen=True)
class WorkerPreflightFailureResult:
    exit_code: int = 3
    reason: str = WORKER_PREFLIGHT_EVENT
    cycles_completed: int = 0


def admit_worker(
    connection: sqlite3.Connection,
    *,
    config: Any,
    health_sink: Any,
    event_sink: Any,
    implemented_versions: frozenset[str] | None = None,
) -> WorkerPreflightFailureResult | None:
    """Run bounded worker admission before any adapter or Tickerd kernel exists."""

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
) -> WorkerPreflightFailureResult:
    """Persist DOWN/not-ready health and exactly one startup diagnostic."""

    from tickerd.health import HealthSnapshot, HealthState

    health_sink.write(
        HealthSnapshot(
            state=HealthState.DOWN,
            is_ready=False,
            snapshot_ts_utc=datetime.now(UTC),
            max_health_age_ms=config.max_health_age_ms,
            health_fail_mode=config.health_fail_mode,
            last_failure_reason=WORKER_PREFLIGHT_EVENT,
        )
    )
    diagnostic: dict[str, Any] = {"event": WORKER_PREFLIGHT_EVENT, "reason": reason}
    if object_type is not None and object_name is not None:
        diagnostic.update({"object_type": object_type, "object_name": object_name})
    if required_contract_versions:
        diagnostic["required_contract_versions"] = sorted(set(required_contract_versions))
    try:
        event_sink.emit(diagnostic)
    except Exception:
        sys.stderr.write(json.dumps(diagnostic, sort_keys=True) + "\n")
    return WorkerPreflightFailureResult()
