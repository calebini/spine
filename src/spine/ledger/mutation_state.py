"""Closed, transaction-local obligations shared by SQL triggers and finalizers.

Connection configuration and allocation/commit guards deliberately live elsewhere.
The component tuple below is fixed, not a runtime registration/plugin interface.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import BindingMutation, OwnerMutation, RecurrenceMutation, RelationMutation

if TYPE_CHECKING:
    from spine.ledger.transactions import LedgerConnection


@dataclass(slots=True)
class _Component:
    def restore(self, checkpoint: _Component) -> None:
        """Restore declared obligations, retaining component/container references."""
        if type(self) is not type(checkpoint):
            raise TypeError("mutation checkpoint component differs")
        for member in fields(self):
            current = getattr(self, member.name)
            saved = deepcopy(getattr(checkpoint, member.name))
            if isinstance(current, (dict, set)):
                current.clear()
                current.update(saved)
            else:
                setattr(self, member.name, saved)

    def finalize(self, db: LedgerConnection) -> None:
        """Ownership epoch consumption has no additional finalization proof."""


@dataclass(slots=True)
class OwnershipMutationState(_Component):
    epoch_consumed: bool = False
    epoch_before: int | None = None
    epoch_after: int | None = None


@dataclass(slots=True)
class PropagationMutationState(_Component):
    bindings: dict[str, BindingMutation] = field(default_factory=dict)
    owners: dict[str, OwnerMutation] = field(default_factory=dict)
    relations: dict[str, RelationMutation] = field(default_factory=dict)
    recurrences: dict[str, RecurrenceMutation] = field(default_factory=dict)

    def finalize(self, db: LedgerConnection) -> None:
        if self.bindings:
            raise SpineValidationError("environment_failure:propagation", "unpropagated binding mutation")
        if self.owners:
            raise SpineValidationError("environment_failure:propagation", "unpropagated ownership mutation")
        if self.relations:
            raise SpineValidationError("environment_failure:propagation", "unpropagated relation mutation")
        if self.recurrences:
            raise SpineValidationError("environment_failure:propagation", "unpropagated recurrence mutation")


@dataclass(slots=True)
class RecurringMutationState(_Component):
    rows: set[tuple[str, str, str | None]] = field(default_factory=set)

    def finalize(self, db: LedgerConnection) -> None:
        if getattr(db, "_recurring_tasks_enabled", False):
            from spine.ledger.recurring_tasks import finalize

            finalize(db, frozenset(self.rows))


@dataclass(slots=True)
class RenderingMutationState(_Component):
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: set[tuple[str, int]] = field(default_factory=set)
    catalog: set[tuple[str, str]] = field(default_factory=set)
    profiles: set[str] = field(default_factory=set)
    attempts: set[str] = field(default_factory=set)

    def finalize(self, db: LedgerConnection) -> None:
        if getattr(db, "_renderings_enabled", False):
            from spine.ledger.rendering_definitions import finalize

            finalize(db)


@dataclass(slots=True)
class FacetMutationState(_Component):
    versions: set[tuple[str, int]] = field(default_factory=set)
    allocations: set[tuple[str, int]] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)
    items: set[str] = field(default_factory=set)
    bindings: set[str] = field(default_factory=set)
    definitions: set[str] = field(default_factory=set)

    def finalize(self, db: LedgerConnection) -> None:
        if getattr(db, "_facets_enabled", False):
            from spine.ledger.facets import finalize

            if not self.allocations <= self.versions:
                raise SpineValidationError("environment_failure:facets", "unfinalized item version")
            expected = (
                frozenset(self.versions), frozenset(self.items), frozenset(self.roots),
                frozenset(self.bindings), frozenset(self.definitions),
            )
            if finalize(db, *expected) != expected:
                raise SpineValidationError("environment_failure:facets", "facet finalization incomplete")


@dataclass(slots=True)
class TransactionMutationState:
    ownership: OwnershipMutationState = field(default_factory=OwnershipMutationState)
    propagation: PropagationMutationState = field(default_factory=PropagationMutationState)
    recurring: RecurringMutationState = field(default_factory=RecurringMutationState)
    renderings: RenderingMutationState = field(default_factory=RenderingMutationState)
    facets: FacetMutationState = field(default_factory=FacetMutationState)

    def _components(self) -> tuple[
        OwnershipMutationState, PropagationMutationState, RecurringMutationState, RenderingMutationState, FacetMutationState
    ]:
        # Single closed registration point: checkpoint/restore/reset/finalize use
        # this same order. Rendering may add facts needed by facet finalization.
        return self.ownership, self.propagation, self.recurring, self.renderings, self.facets

    def checkpoint(self) -> TransactionMutationState:
        checkpoint = TransactionMutationState()
        checkpoint.restore(self)
        return checkpoint

    def restore(self, checkpoint: TransactionMutationState) -> None:
        for component, saved in zip(self._components(), checkpoint._components(), strict=True):
            component.restore(saved)

    def reset(self) -> None:
        self.restore(TransactionMutationState())

    def finalize(self, db: LedgerConnection) -> None:
        for component in self._components():
            component.finalize(db)
