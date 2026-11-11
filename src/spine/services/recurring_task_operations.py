"""Private, typed inputs/evidence for complete recurring child operations.

These are not wire contracts or an authorization bypass. The admitted local
composer supplies authority; a child never reads it from request JSON. Mutable
page bookkeeping, response projection and outer receipts stay with the caller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict

from spine.core.errors import SpineValidationError
from spine.core.recurring_task_runtime import PREFIX, fail
from spine.core.recurring_tasks import CONTRACT
from spine.ledger.transactions import LedgerConnection

if TYPE_CHECKING:
    from spine.services.recurring_task_restoration import Restoration


class LocalAuthority(Enum):
    TRUSTED_LOCAL = "trusted_local"


@dataclass(frozen=True, kw_only=True)
class ChildInvocation:
    command: ClassVar[str] = PREFIX + "reconcile"
    contract_version: ClassVar[str] = CONTRACT
    authority: LocalAuthority
    command_id: str
    actor_subject_id: str
    now: str
    delivery_target_defaults: Mapping[str, Any]
    fault: Callable[[str], None]

    def require_transaction(self, db: LedgerConnection) -> None:
        # Never allow an allocator's standalone convenience transaction to turn
        # a child into a separately committed operation.
        if self.authority is not LocalAuthority.TRUSTED_LOCAL:
            fail("environment_failure", "authority")
        if not isinstance(db, LedgerConnection) or not db._command_transaction or not db.in_transaction:
            fail("environment_failure", "transaction")


@dataclass(frozen=True, kw_only=True)
class CreateChild:
    source_item_id: str
    configuration: dict[str, Any]
    assignment_id: str
    generation_id: str
    source: dict[str, Any]
    work_limit: int


@dataclass(frozen=True, kw_only=True)
class RestoreChild:
    creation: CreateChild
    predecessor: Restoration


class ChildDisposition(Enum):
    FOLLOW = "follow"
    CANCEL = "cancel"
    DETACH = "detach"


@dataclass(frozen=True, kw_only=True)
class ChangeChild:
    assignment_id: str
    generation: dict[str, Any]
    binding: dict[str, Any]
    current: dict[str, Any]
    source: dict[str, Any]
    configuration: dict[str, Any]
    work_limit: int
    disposition: ChildDisposition = ChildDisposition.FOLLOW
    target: dict[str, Any] | None = None
    managed: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ChildDisposition):
            raise ValueError("unknown child disposition")
        if self.disposition is not ChildDisposition.FOLLOW and (self.target is not None or self.managed):
            raise ValueError("terminal binding changes cannot also adopt or move")


class CreatedChild(TypedDict):
    task_item_id: str
    task_item_version: str
    temporal_binding_id: str
    temporal_binding_revision_id: str
    relationship_id: str
    item_access_owner_id: str
    audit_id: str
    due: str
    work: list[str]
    policy_mappings: list[dict[str, Any]]


@dataclass(frozen=True)
class WorkEvidence:
    created: tuple[str, ...] = ()
    cancelled: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()
    protected_stale: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.created or self.cancelled)


@dataclass(frozen=True)
class ChangedChild:
    task_item_version: str
    temporal_binding_revision_id: str
    audit_ids: tuple[str, ...]
    policy_mappings: tuple[dict[str, Any], ...]
    work: WorkEvidence


class ChildWorkOverflow(SpineValidationError):
    """One indivisible child exceeds the work bound, not a page suffix boundary."""

    def __init__(self) -> None:
        super().__init__("capacity_exceeded:limits.work_rows", "recurring-task request could not complete")
