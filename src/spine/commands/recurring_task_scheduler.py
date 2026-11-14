"""Process-local command orchestration for the candidate recurring-task reconciler.

Alternate a round-robin fresh visit with a deep visit. The latter has its own
round-robin position and holds at most one signed continuation, regardless of
catalog size. No remembered position is authority to mutate or acknowledge.
"""

import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from spine.commands import recurring_task_automatic as automatic
from spine.commands.context import CommandContext
from spine.commands.recurring_task_runtime import RecurringTaskContracts
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurring_task_runtime import cursor_config, fail, wire
from spine.core.recurring_tasks import CONTRACT
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.recurring_task_catalog import catalog, source_snapshot
from spine.ledger.recurring_tasks import read_record
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_planning import DiscoveryLimits, discover


@dataclass(frozen=True)
class Visit:
    rule_id: str | None
    status: str
    reasons: tuple[str, ...] = ()
    outcomes: tuple[tuple[str, int], ...] = ()

    @property
    def failed(self) -> bool:
        return self.status == "failed"


def _now() -> str:
    return wire(datetime.now(UTC))


def _require_actor(db: LedgerConnection, actor: str) -> None:
    if not db.execute("SELECT 1 FROM subjects WHERE subject_id=? AND status='active'", (actor,)).fetchone():
        fail("environment_failure", "scheduler_actor")


@dataclass
class RecurringTaskSweep:
    """Private dependency of one worker, bound to its connection and explicit actor."""

    context: CommandContext
    contracts: RecurringTaskContracts
    actor: str
    clock: Callable[[], str] = _now
    _after: str | None = field(default=None, init=False)
    _deep_after: str | None = field(default=None, init=False)
    _cursor: str | None = field(default=None, init=False, repr=False)
    _deep_next: bool = field(default=False, init=False)
    last_visit: Visit | None = field(default=None, init=False)

    def run(self, db: LedgerConnection, evaluated: str, require_safe: Callable[[], None]) -> Visit:
        require_safe()
        if (db is not self.context.ledger or db.in_transaction or not getattr(db, "_recurring_tasks_enabled", False)
                or self.context.dry_run or self.context.transport_metadata):
            fail("environment_failure", "scheduler_admission")
        ledger_id = read_ledger_instance_id(db)
        cursor_config(self.context.facet_cursor_config, ledger_id)
        _require_actor(db, self.actor)
        deep = self._deep_next
        self._deep_next = not deep
        candidate = None
        if deep and self._cursor:
            identity = self._deep_after
        else:
            cycle = discover(db, evaluated_at_utc=evaluated, after_root=self._deep_after if deep else self._after,
                             limits=DiscoveryLimits(roots=1, assignments=2, source_candidates=2))
            if deep:
                self._deep_after = cycle.next_root_after
            else:
                self._after = cycle.next_root_after
            candidate = cycle.roots[0] if cycle.roots else None
            identity = candidate.rule_id if candidate else None

        if identity is None:
            visit = Visit(None, "idle")
        else:
            # A fresh visit to the currently deep-walking root helps its chain
            # instead of needlessly invalidating it by restarting at the head.
            remember = deep or (identity == self._deep_after and self._cursor is not None) or self._deep_after is None
            token = self._cursor if identity == self._deep_after else None
            if (candidate and not token and not candidate.check_existing and not candidate.occurrence_keys
                    and not candidate.diagnostic):
                visit, next_token = Visit(identity, "observed"), None
            else:
                try:
                    visit, next_token = self._page(db, identity, evaluated, ledger_id, token, require_safe)
                except SpineValidationError as exc:
                    code = exc.code.partition(":")[0]
                    visit = Visit(identity, "stale_plan" if code in {"stale_cursor", "stale_version"} else "failed", (exc.code,))
                    next_token = None
                except sqlite3.OperationalError as exc:
                    # A bounded VM timeout or competing writer belongs to this
                    # visit. Do not strand the deep slot; do not swallow IO errors.
                    primary = (getattr(exc, "sqlite_errorcode", 0) or 0) & 0xff
                    if primary not in (sqlite3.SQLITE_INTERRUPT, sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                        raise
                    reason = "capacity_exceeded" if primary == sqlite3.SQLITE_INTERRUPT else "writer_busy"
                    visit, next_token = Visit(identity, "failed", (reason,)), None
            if candidate and candidate.diagnostic:
                visit = Visit(identity, "failed" if visit.status == "observed" else visit.status,
                              tuple(sorted({*visit.reasons, candidate.diagnostic})), visit.outcomes)
            if remember:
                self._deep_after, self._cursor = identity, next_token
        self.last_visit = visit
        return visit

    def _page(self, db: LedgerConnection, identity: str, evaluated: str, ledger_id: str, token: str | None,
              require_safe: Callable[[], None]) -> tuple[Visit, str | None]:
        with db.atomic_command(write=False):
            root = read_record(db, "related_task_rules", identity)
            source = source_snapshot(db, root)
            expected = {"rule_change_version": str(root["change_version"]), "rule_revision_id": root["current_revision_id"],
                        "source_item_version": source["source_item_version"], "recurrence_revision_id": source["recurrence_revision_id"],
                        "catalog_generation": catalog(db)}
        request: dict[str, Any] = {"contract_version": CONTRACT, "related_task_rule_id": identity, "actor_subject_id": self.actor,
                                   "expected": expected, "requested_at_utc": evaluated,
                                   "limits": {"assignments": "2", "source_candidates": "2"}}
        if token:
            request["cursor"] = token
        request["command_id"] = "scheduler_rrt_" + hash_canonical_json({"ledger": ledger_id, "request": request})
        prior = automatic.plan(request, self.context, contracts=self.contracts, now=self.clock())
        reasons = tuple(sorted({u.reason for u in prior.units if u.reason and u.action == "decision_required"}))
        if not prior.dispatchable:
            outcomes = tuple(sorted(Counter(u.action for u in prior.units).items()))
            return Visit(identity, "blocked" if reasons else "observed", reasons, outcomes), prior.observed_cursor

        def safe_clock() -> str:
            # Called under BEGIN IMMEDIATE and by the page's finalizer.
            require_safe()
            _require_actor(db, self.actor)
            return self.clock()

        outcome = automatic.dispatch(prior, request, self.context, contracts=self.contracts, clock=safe_clock)
        response = outcome.response or {}
        if outcome.status == "failed":
            error = response["error"]
            code = error["code"]
            transient = code in {"stale_cursor", "stale_version", "stale_evaluation"}
            return Visit(identity, "stale_plan" if transient else "failed", (code + ":" + error["field"],)), None
        if outcome.status != "applied":
            # Replays describe an older publication, not a fresh page position.
            if outcome.status == "no_semantic_change":
                # The byte-limited writer could not retain the planned effect.
                # Never skip the unproved suffix or report a successful repair.
                return Visit(identity, "failed", ("no_semantic_change",)), None
            return Visit(identity, outcome.status), None
        units = response["result"]["results"]
        committed_reasons = tuple(sorted({u["reason"] for u in units if u["outcome"] == "decision_required"}))
        return (Visit(identity, "applied", committed_reasons, tuple(sorted(Counter(u["outcome"] for u in units).items()))),
                response["result"]["next_cursor"])
