"""Private, immutable mutation facts; neither wire dimensions nor durable events.

RF3 covers binding, relation, recurrence and initial item-owner producers. Other kinds must be
introduced with their writer inventory, not guessed from an item-version bump.
"""

from dataclasses import dataclass
from enum import Enum


class ChangeCategory(Enum):
    BINDING = "binding"
    TIME = "time"
    OWNERSHIP = "ownership"
    RELATION = "relation"
    RECURRENCE = "recurrence"


@dataclass(frozen=True)
class BindingSnapshot:
    binding_id: str
    source_item_id: str
    target_item_id: str
    relationship_id: str
    status: str
    revision_id: str | None = None
    revision_index: int | None = None
    source_item_version: int | None = None
    target_item_version: int | None = None
    source_recurrence_revision_id: str | None = None
    source_occurrence_key: str | None = None
    source_anchor_id: str | None = None
    target_anchor_id: str | None = None
    resolved_source_utc: str | None = None
    resolved_target_utc: str | None = None
    offset_seconds: int | None = None
    target_local_date: str | None = None
    target_local_time: str | None = None
    target_timezone: str | None = None
    target_timezone_database_version: str | None = None

    @property
    def time_facts(self) -> tuple[object, ...]:
        return (self.resolved_source_utc, self.resolved_target_utc, self.offset_seconds,
                self.target_local_date, self.target_local_time, self.target_timezone,
                self.target_timezone_database_version)


@dataclass(frozen=True)
class BindingMutation:
    before: BindingSnapshot | None
    after: BindingSnapshot

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        result = {ChangeCategory.BINDING}
        if self.before is None or self.before.time_facts != self.after.time_facts:
            result.add(ChangeCategory.TIME)
        return frozenset(result)


@dataclass(frozen=True)
class OwnerSnapshot:
    item_id: str
    owner_id: str
    revision: int
    owner_kind: str
    owner_subject_id: str | None
    owner_group_id: str | None
    creator_subject_id: str | None
    command_id: str


@dataclass(frozen=True)
class OwnerHistory:
    actor: str
    at: str
    receipt_id: str


@dataclass(frozen=True)
class OwnerMutation:
    after: OwnerSnapshot
    history: OwnerHistory | None = None
    before: OwnerSnapshot | None = None

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        return frozenset({ChangeCategory.OWNERSHIP})


@dataclass(frozen=True)
class LocalOwnerPropagation:
    owner_id: str


@dataclass(frozen=True)
class ConfiguredOwnerPropagation:
    owner_id: str
    expected_epoch: int


@dataclass(frozen=True)
class ProvisionedOwnerPropagation:
    owner_ids: tuple[str, ...]
    before_epoch: int
    after_epoch: int


@dataclass(frozen=True)
class OwnershipPropagationResult:
    before_epoch: int
    after_epoch: int


@dataclass(frozen=True)
class RelationSnapshot:
    relation_id: str
    source_item_id: str
    target_item_id: str
    relation_type: str
    relation_status: str
    created_at_utc: str
    created_by_subject_id: str
    metadata_json: str | None


@dataclass(frozen=True)
class RelationMutation:
    after: RelationSnapshot
    before: RelationSnapshot | None = None

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        return frozenset({ChangeCategory.RELATION})


@dataclass(frozen=True)
class RecurrenceSnapshot:
    recurrence_set_id: str
    recurrence_revision_id: str
    revision_number: int
    source_item_id: str
    source_item_version: int
    normalized_recurrence_set_hash: str
    prior_recurrence_revision_id: str | None
    command_id: str
    created_at_utc: str


@dataclass(frozen=True)
class RecurrenceLineage:
    lineage_id: str
    command_id: str
    recurrence_set_id: str
    prior_recurrence_revision_id: str
    new_recurrence_revision_id: str
    lineage_role: str
    prior_segment_id: str | None
    new_segment_id: str | None
    prior_child_id: str | None
    new_child_id: str | None
    effect: str
    lineage_index: int
    payload_hash: str


@dataclass(frozen=True)
class RecurrenceMutation:
    before: RecurrenceSnapshot | None
    after: RecurrenceSnapshot
    definition_bytes: bytes
    lineage: tuple[RecurrenceLineage, ...] = ()

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        # A new revision/hash is not proof that time, lifecycle or people changed.
        return frozenset({ChangeCategory.RECURRENCE})


@dataclass(frozen=True)
class MutationEffects:
    bindings: tuple[BindingMutation, ...] = ()
    owners: tuple[OwnerMutation, ...] = ()
    ownership_epoch: OwnershipPropagationResult | None = None
    relations: tuple[RelationMutation, ...] = ()
    recurrences: tuple[RecurrenceMutation, ...] = ()
