"""Private, immutable mutation facts; neither wire dimensions nor durable events.

RF3 covers the inventoried item, policy, binding, relation, recurrence and initial
item-owner producers. Categories describe proven facts, not every version bump.
"""

import json
from dataclasses import dataclass
from enum import Enum


class ChangeCategory(Enum):
    BINDING = "binding"
    TIME = "time"
    OWNERSHIP = "ownership"
    RELATION = "relation"
    RECURRENCE = "recurrence"
    ITEM = "item"
    LIFECYCLE = "lifecycle"
    POLICIES = "policies"
    PEOPLE = "people"
    FACETS = "facets"
    PRESENTATIONS = "presentations"


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
class ItemSnapshot:
    item_id: str
    item_type: str
    version: int
    status: str
    title: str
    summary: str | None
    source_ref: str | None
    detail_bytes: bytes


@dataclass(frozen=True)
class ItemMutation:
    before: ItemSnapshot | None
    after: ItemSnapshot
    audit_id: str
    # None on both sides explicitly means unaffected/not inspected (shell archive).
    before_people: tuple[tuple[str, str, str], ...] | None = None
    after_people: tuple[tuple[str, str, str], ...] | None = None
    before_facets: bytes | None = None
    after_facets: bytes | None = None

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        result = {ChangeCategory.ITEM}
        before = {} if self.before is None else json.loads(self.before.detail_bytes)
        after = json.loads(self.after.detail_bytes)
        lifecycle = ("event_status", "task_status", "completion_state", "completed_at_utc", "completed_by_subject_id")
        if (self.before is None or self.before.status != self.after.status
                or any(before.get(k) != after.get(k) for k in lifecycle)):
            result.add(ChangeCategory.LIFECYCLE)
        # Exact temporal-reference changes, not an inference from allocation.
        temporal = ("all_day", "start_anchor_id", "end_anchor_id", "due_anchor_id", "defer_until_anchor_id")
        if any(before.get(k) != after.get(k) for k in temporal):
            result.add(ChangeCategory.TIME)
        if self.before_people != self.after_people:
            result.add(ChangeCategory.PEOPLE)
        if self.before_facets != self.after_facets:
            result.add(ChangeCategory.FACETS)
        return frozenset(result)


@dataclass(frozen=True)
class PolicyMutation:
    item_id: str
    item_version: int
    policy_id: str
    source_policy_id: str | None
    definition_bytes: bytes
    before_presentation: bytes | None = None
    after_presentation: bytes | None = None

    @property
    def categories(self) -> frozenset[ChangeCategory]:
        # This is an exact policy-row write, not proof of semantic schedule change.
        result = {ChangeCategory.POLICIES}
        if self.before_presentation != self.after_presentation:
            result.add(ChangeCategory.PRESENTATIONS)
        return frozenset(result)


@dataclass(frozen=True)
class MutationEffects:
    bindings: tuple[BindingMutation, ...] = ()
    owners: tuple[OwnerMutation, ...] = ()
    ownership_epoch: OwnershipPropagationResult | None = None
    relations: tuple[RelationMutation, ...] = ()
    recurrences: tuple[RecurrenceMutation, ...] = ()
    items: tuple[ItemMutation, ...] = ()
    policies: tuple[PolicyMutation, ...] = ()
