"""Spine-owned storage policy mapped into Tickerd's generic safety gate."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class StorageSafetyPolicy:
    warning_free_bytes: int = 1_073_741_824
    critical_free_bytes: int = 536_870_912
    reserve_bytes: int = 268_435_456
    critical_storage_action: str = "exit_nonzero"

    def __post_init__(self) -> None:
        if not self.warning_free_bytes > self.critical_free_bytes >= self.reserve_bytes > 0:
            raise ValueError("storage thresholds must satisfy warning > critical >= reserve > 0")
        if self.critical_storage_action not in {"suspend", "exit_nonzero"}:
            raise ValueError("critical_storage_action must be suspend|exit_nonzero")


class LedgerDurabilityLatchedError(RuntimeError):
    pass


class StorageSafetyLatch:
    """Process-local monotonic latch; recovery requires a new process."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._latched_at_utc: str | None = None

    @property
    def is_latched(self) -> bool:
        return self._latched_at_utc is not None

    @property
    def latched_at_utc(self) -> str | None:
        return self._latched_at_utc

    def latch(self) -> None:
        with self._lock:
            if self._latched_at_utc is None:
                self._latched_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def require_safe(self) -> None:
        if self.is_latched:
            raise LedgerDurabilityLatchedError("ledger durability failure is latched")

    def observe_sqlite_error(self, exc: sqlite3.Error) -> bool:
        code = getattr(exc, "sqlite_errorcode", None)
        message = str(exc).lower()
        durability_failure = code in {sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR} or any(
            token in message for token in ("database or disk is full", "disk i/o error", "failed commit", "failed fsync")
        )
        if durability_failure:
            self.latch()
        return durability_failure


@dataclass(frozen=True)
class _Measurement:
    filesystem_id: str
    free_bytes: int
    roles: tuple[str, ...]


class SpineStorageSafetyGate:
    def __init__(
        self,
        *,
        ledger_path: Path | str,
        worker_state_path: Path | str,
        policy: StorageSafetyPolicy,
        latch: StorageSafetyLatch,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.worker_state_path = Path(worker_state_path)
        self.policy = policy
        self.latch = latch

    def evaluate(self, context: Any) -> Any:
        from tickerd import SafetyDecision

        measured_at = context.actual_start_ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            measurements = self._measure()
        except OSError as exc:
            facts = self._facts(
                primary_reason="storage_measurement_failure",
                pressure_state="unknown",
                measured_at_utc=measured_at,
                measurements=(),
                measurement_error_category=_measurement_error_category(exc),
            )
            return SafetyDecision.terminate_nonzero("storage_measurement_failed", facts)

        if self.latch.is_latched:
            facts = self._facts(
                primary_reason="ledger_durability_failure",
                pressure_state=self._pressure_state(measurements),
                measured_at_utc=measured_at,
                measurements=measurements,
            )
            return self._stop_decision(SafetyDecision, facts)

        if self._pressure_state(measurements) == "critical":
            facts = self._facts(
                primary_reason="critical_storage_pressure",
                pressure_state="critical",
                measured_at_utc=measured_at,
                measurements=measurements,
            )
            return self._stop_decision(SafetyDecision, facts)
        return SafetyDecision.allow()

    def _stop_decision(self, decision_type: Any, facts: dict[str, Any]) -> Any:
        if self.policy.critical_storage_action == "suspend":
            return decision_type.suspend("storage_safety_stop", facts)
        return decision_type.terminate_nonzero("storage_safety_stop", facts)

    def _measure(self) -> tuple[_Measurement, ...]:
        grouped: dict[str, dict[str, Any]] = {}
        for role, configured in (("ledger", self.ledger_path), ("worker_state", self.worker_state_path)):
            target = configured if configured.exists() else configured.parent
            stat = os.stat(target)
            filesystem = os.statvfs(target)
            identity = str(stat.st_dev)
            free_bytes = int(filesystem.f_bavail * filesystem.f_frsize)
            entry = grouped.setdefault(identity, {"free_bytes": free_bytes, "roles": []})
            entry["free_bytes"] = min(int(entry["free_bytes"]), free_bytes)
            entry["roles"].append(role)
        return tuple(
            _Measurement(identity, int(entry["free_bytes"]), tuple(sorted(set(entry["roles"]))))
            for identity, entry in sorted(grouped.items(), key=lambda item: item[0])
        )

    def _pressure_state(self, measurements: tuple[_Measurement, ...]) -> str:
        minimum = min(item.free_bytes for item in measurements)
        if minimum <= self.policy.critical_free_bytes:
            return "critical"
        if minimum <= self.policy.warning_free_bytes:
            return "warning"
        return "normal"

    def _facts(
        self,
        *,
        primary_reason: str,
        pressure_state: str,
        measured_at_utc: str,
        measurements: tuple[_Measurement, ...],
        measurement_error_category: str | None = None,
    ) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "reason_facts_contract": "spine.storage-safety-facts.v1",
            "primary_reason": primary_reason,
            "pressure_state": pressure_state,
            "critical_storage_action": self.policy.critical_storage_action,
            "measured_at_utc": measured_at_utc,
            "measurements": [
                {
                    "roles": list(item.roles),
                    "filesystem_id": item.filesystem_id,
                    "free_bytes": str(item.free_bytes),
                    "warning_free_bytes": str(self.policy.warning_free_bytes),
                    "critical_free_bytes": str(self.policy.critical_free_bytes),
                    "reserve_bytes": str(self.policy.reserve_bytes),
                }
                for item in measurements
            ],
        }
        if measurement_error_category is not None:
            facts["measurement_error_category"] = measurement_error_category
        return facts


def _measurement_error_category(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "path_unavailable"
    return "stat_failed"
