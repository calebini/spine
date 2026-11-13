"""Private, immutable mutation facts; neither wire dimensions nor durable events.

RF3's first increment covers binding producers only. Other effect kinds must be
introduced with their writer inventory, not guessed from an item-version bump.
"""

from dataclasses import dataclass
from enum import Enum


class ChangeCategory(Enum):
    BINDING = "binding"
    TIME = "time"


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
class MutationEffects:
    bindings: tuple[BindingMutation, ...]
