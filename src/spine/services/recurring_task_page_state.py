"""Rollbackable recurring-page outputs and retained whole-unit checkpoints.

Execution dependencies, proof/hop budgets, elapsed time and per-trial rejection
signals are deliberately not page state. SQLite/trigger state remains owned by
LedgerConnection.command_unit; this owner pairs it with the corresponding outputs.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from spine.ledger.transactions import LedgerConnection

type ExceptionInfo = tuple[type[BaseException] | None, BaseException | None, TracebackType | None]


class PageBoundary(Exception):
    """Reject a tentative whole unit or final response projection."""


@dataclass(frozen=True, slots=True)
class PageCheckpoint:
    root: dict[str, Any]
    runtime: dict[str, Any]
    work: dict[str, list[str]]
    mappings: list[dict[str, Any]]
    changed: bool
    owners: bool
    mutations: int
    result_count: int
    position: dict[str, Any]
    lane: str


@dataclass(frozen=True, slots=True)
class PageUnit:
    scope: AbstractContextManager[None]
    checkpoint: PageCheckpoint


@dataclass(slots=True)
class PageState:
    root: dict[str, Any]
    runtime: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    work: dict[str, list[str]] = field(default_factory=lambda: {
        key: [] for key in ("created", "retained", "cancelled", "protected_stale")
    })
    mappings: list[dict[str, Any]] = field(default_factory=list)
    changed: bool = False
    owners: bool = False
    mutations: int = 0
    position: dict[str, Any] = field(default_factory=dict)
    lane: str = "assignments"
    _units: list[PageUnit] = field(default_factory=list, init=False, repr=False)

    @property
    def has_units(self) -> bool:
        return bool(self._units)

    def checkpoint(self) -> PageCheckpoint:
        # Accepted result entries are append-only. Save the suffix boundary rather
        # than repeatedly copying all earlier results at every retained unit.
        return PageCheckpoint(
            deepcopy(self.root), deepcopy(self.runtime), deepcopy(self.work), deepcopy(self.mappings),
            self.changed, self.owners, self.mutations, len(self.results), deepcopy(self.position), self.lane,
        )

    def restore(self, checkpoint: PageCheckpoint) -> None:
        for current, saved in ((self.root, checkpoint.root), (self.runtime, checkpoint.runtime),
                               (self.work, checkpoint.work), (self.position, checkpoint.position)):
            current.clear()
            current.update(deepcopy(saved))
        self.mappings[:] = deepcopy(checkpoint.mappings)
        self.changed, self.owners, self.mutations = checkpoint.changed, checkpoint.owners, checkpoint.mutations
        del self.results[checkpoint.result_count:]
        self.lane = checkpoint.lane

    def begin_unit(self, db: LedgerConnection) -> PageUnit:
        checkpoint = self.checkpoint()
        scope = db.command_unit(nested=True)
        scope.__enter__()
        unit = PageUnit(scope, checkpoint)
        # Register before invoking any child/reference lookup so an exception can
        # never strand an entered SQL savepoint outside the retained stack.
        self._units.append(unit)
        return unit

    def _close(self, unit: PageUnit, error: ExceptionInfo) -> None:
        if not self._units or self._units[-1] is not unit:
            raise RuntimeError("page units must close in LIFO order")
        self._units.pop()
        try:
            unit.scope.__exit__(*error)
        except BaseException:
            self.restore(unit.checkpoint)
            raise
        if error[0] is not None:
            self.restore(unit.checkpoint)

    def rollback(self, unit: PageUnit, error: ExceptionInfo) -> None:
        if error[0] is None:
            raise ValueError("page rollback requires an error")
        self._close(unit, error)

    def rollback_last(self) -> str:
        unit = self._units[-1]
        self.rollback(unit, (PageBoundary, PageBoundary(), None))
        return unit.checkpoint.lane

    @contextmanager
    def trial(self, db: LedgerConnection) -> Iterator[None]:
        """A non-retained final projection joins the same SQL/Python checkpoint."""
        unit = self.begin_unit(db)
        try:
            yield
        except BaseException:
            self.rollback(unit, sys.exc_info())
            raise
        else:
            self._close(unit, (None, None, None))

    def close(self, error: ExceptionInfo) -> None:
        """Release successful units or unwind a failed invocation in reverse order."""
        try:
            while self._units:
                self._close(self._units[-1], error)
        except BaseException:
            failure = sys.exc_info()
            while self._units:
                self._close(self._units[-1], failure)
            raise
