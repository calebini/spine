"""Bounded, read-only assembly snapshots for the pending v2 read adapter.

Nothing yielded here is release-authorized: a later service layer must perform the
fresh authorization/source fence before serializing a public response.
"""

from __future__ import annotations

import copy
import sqlite3
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from math import gcd
from pathlib import Path
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.transactions import LedgerConnection
from spine.web.errors import WebError
from spine.web.read_authorization import ReadPermissions
from spine.web.read_contracts import ReadContracts, read_error, utc_datetime
from spine.web.read_proof import SourceFacts
from spine.web.service import WebConfig


class OptionalReadUnavailable(Exception):
    """Only a separately bounded optional computation may catch this signal."""


class ReadBudget:
    def __init__(
        self, contracts: ReadContracts, *, clock: Callable[[], float] = time.monotonic, sql_steps: int = 100_000,
    ) -> None:
        self.bounds, self.clock = contracts.bounds, clock
        self.deadline = clock() + self.bounds["request_milliseconds"] / 1000
        self.steps = {"core": 0, "optional": 0}
        self.maximum_steps = min(sql_steps, self.bounds["core_sql_vm_steps"] + self.bounds["optional_sql_vm_steps"])
        self.quantum = gcd(100, self.maximum_steps, self.bounds["core_sql_vm_steps"], self.bounds["optional_sql_vm_steps"])
        self.bytes = {"core": 0, "optional": 0}
        self.phase = "core"
        self.section_bytes = self.section_rows = 0
        self.lines = 0
        self.interrupted = False
        self.interruption: Exception | None = None

    def check(self) -> None:
        if self.clock() >= self.deadline or sum(self.steps.values()) >= self.maximum_steps:
            raise read_error("capacity_exceeded")
        if self.steps["core"] >= self.bounds["core_sql_vm_steps"]:
            raise read_error("capacity_exceeded")
        if self.phase == "optional" and self.steps["optional"] >= self.bounds["optional_sql_vm_steps"]:
            raise OptionalReadUnavailable

    def progress(self) -> int:
        self.steps[self.phase] += self.quantum
        try:
            self.check()
        except (OptionalReadUnavailable, WebError) as exc:
            # SQLite callbacks may not propagate exceptions; check() maps it outside.
            self.interrupted = True
            self.interruption = exc
            return 1
        return 0

    def trace(self, frame: Any, event: str, arg: Any) -> Any:
        self.lines += 1
        if not self.interrupted and self.lines % 1024 == 0 and self.clock() >= self.deadline:
            raise read_error("capacity_exceeded")
        return self.trace

    @contextmanager
    def active(self, db: sqlite3.Connection) -> Iterator[None]:
        previous = sys.gettrace()
        db.set_progress_handler(self.progress, self.quantum)
        sys.settrace(self.trace)
        try:
            yield
            self.check()
        except sqlite3.OperationalError as exc:
            if self.interruption is not None:
                raise self.interruption from exc
            raise read_error("capacity_exceeded" if "locked" in str(exc) else "admission_unavailable") from exc
        finally:
            sys.settrace(previous)
            db.set_progress_handler(None, 0)

    @contextmanager
    def optional(self) -> Iterator[None]:
        if self.phase != "core":
            raise RuntimeError("optional read budgets cannot nest")
        self.phase = "optional"
        self.section_bytes = self.section_rows = 0
        try:
            self.check()
            yield
            self.check()
        except sqlite3.OperationalError as exc:
            if self.interruption is not None:
                raise self.interruption from exc
            raise
        finally:
            self.phase = "core"
            self.interrupted = False
            self.interruption = None

    def charge(self, value: Any, *, authorized_rows: int = 0) -> None:
        """Account only already-authorized projected bytes/rows, never hidden rows."""
        self.check()
        size = len(canonical_json_bytes(value))
        self.bytes[self.phase] += size
        if self.phase == "core":
            if self.bytes["core"] > self.bounds["core_reserved_bytes"]:
                raise read_error("capacity_exceeded")
        else:
            self.section_bytes += size
            self.section_rows += authorized_rows
            if (self.bytes["optional"] > self.bounds["optional_total_bytes"]
                    or self.section_bytes > self.bounds["section_bytes"]
                    or self.section_rows > self.bounds["optional_authorized_rows_per_section"]):
                raise OptionalReadUnavailable

    def check_response(self, value: Any) -> None:
        self.check()
        if len(canonical_json_bytes(value)) > self.bounds["response_bytes"]:
            raise read_error("capacity_exceeded")


@dataclass
class ReadSnapshot:
    db: sqlite3.Connection
    permissions: ReadPermissions
    contracts: ReadContracts
    budget: ReadBudget
    evaluated_at_utc: str
    proof: SourceFacts | None = None


class _OptionalPermissions(ReadPermissions):
    """Reuse v1 predicates, with capacity failures confined to optional evidence."""

    def touch(self, kind: str, resource: str, operation: str) -> None:
        try:
            super().touch(kind, resource, operation)
        except WebError as exc:
            if exc.code == "capacity_exceeded":
                raise OptionalReadUnavailable from exc
            raise

    def grant(self, kind: str, resource: str, revision: int, operation: str) -> bool:
        try:
            return super().grant(kind, resource, revision, operation)
        except WebError as exc:
            if exc.code == "capacity_exceeded":
                raise OptionalReadUnavailable from exc
            raise


@contextmanager
def optional_snapshot(snapshot: ReadSnapshot) -> Iterator[ReadSnapshot]:
    # Reuse the frozen admitted identity, but optional permission traversal cannot
    # spend the root's resource reserve. Retain all successful checks for the later
    # release service; do not treat this merge as a release authorization fence.
    permissions = object.__new__(_OptionalPermissions)
    permissions.__dict__ = copy.copy(snapshot.permissions.__dict__)
    permissions.visited, permissions.checked, permissions.matched_grants = set(), set(), set()
    permissions.release_scopes = {}
    permissions.probes = {}
    permissions.core_probe_keys = set()
    permissions.optional = True
    proof = copy.deepcopy(snapshot.proof)
    with snapshot.budget.optional():
        yield replace(snapshot, permissions=permissions, proof=proof)
    if snapshot.proof is not None and proof is not None:
        snapshot.proof.values.update(proof.values)
        snapshot.proof.cores.update(proof.cores)
    # Discard checks/proof fragments for unavailable sections; they disclose no rows.
    snapshot.permissions.checked.update(permissions.checked)
    snapshot.permissions.matched_grants.update(permissions.matched_grants)
    snapshot.permissions.release_scopes.update(permissions.release_scopes)
    snapshot.permissions.probes.update(permissions.probes)
    snapshot.permissions.discovery |= permissions.discovery
    if permissions.discovered is not None:
        snapshot.permissions.discovered = permissions.discovered


@contextmanager
def read_snapshot(
    config: WebConfig, contracts: ReadContracts, account_id: str, *, evaluated_at_utc: str,
    clock: Callable[[], float] = time.monotonic,
    budget: ReadBudget | None = None, collect_proof: bool = False,
) -> Iterator[ReadSnapshot]:
    """Open a private assembly snapshot, never a public response/release boundary.

    Evaluation time comes from the service clock, not the request's agenda timestamp.
    A dedicated read-only connection avoids writes and nested transaction ownership.
    """
    try:
        if not utc_datetime(evaluated_at_utc) or not isinstance(evaluated_at_utc, str):
            raise ValueError("invalid service clock")
    except ValueError as exc:
        raise read_error("admission_unavailable") from exc
    path = Path(config.database).resolve()
    if not path.is_file():
        raise read_error("admission_unavailable")
    if budget is None:
        budget = ReadBudget(contracts, clock=clock, sql_steps=config.sql_steps)
        budget.deadline = min(budget.deadline, clock() + config.request_seconds)
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, factory=LedgerConnection)
    except sqlite3.Error as exc:
        raise read_error("admission_unavailable") from exc
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA query_only=ON")
        db.execute(f"PRAGMA busy_timeout={config.busy_milliseconds}")
        with budget.active(db), db.atomic_command(write=False):
            verify_runtime_schema(db)
            state = db.execute("SELECT * FROM ledger_access_state WHERE singleton_id=1").fetchone()
            if (state is None or state["ledger_id"] != config.ledger_id or state["realm_id"] != config.realm_id
                    or state["mode"] != "multi_user" or state["identity_mode"] != "trusted_identity"):
                raise read_error("admission_unavailable")
            permissions = ReadPermissions(db, account_id, evaluated_at_utc)
            yield ReadSnapshot(db, permissions, contracts, budget, evaluated_at_utc, SourceFacts() if collect_proof else None)
    except WebError as exc:
        # Reused v1 permission helpers must not leak v1's 429 capacity mapping or details.
        raise read_error(exc.code) from exc
    except SpineValidationError as exc:
        raise read_error("admission_unavailable") from exc
    finally:
        db.close()
