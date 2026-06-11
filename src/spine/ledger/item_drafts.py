"""Input bundles for ledger item workflows."""

from __future__ import annotations

from dataclasses import dataclass

from spine.ledger.common import TemporalAnchorInput
from spine.ledger.supporting import ItemLocationInput, ItemSubjectRoleInput, NotificationPolicyInput
from spine.models.enums import EventStatus, TaskStatus

_UNSET = object()


@dataclass(frozen=True)
class EventDraft:
    """Input bundle for creating an event item."""

    created_at_utc: str
    created_by_subject_id: str
    title: str
    all_day: bool
    start_anchor: TemporalAnchorInput
    item_id: str | None = None
    audit_id: str | None = None
    summary: str | None = None
    source_ref: str | None = None
    event_status: EventStatus | str = EventStatus.SCHEDULED
    end_anchor: TemporalAnchorInput | None = None
    visibility: str | None = None
    attendance_policy_ref: str | None = None
    item_locations: tuple[ItemLocationInput, ...] = ()
    subject_roles: tuple[ItemSubjectRoleInput, ...] = ()
    notification_policies: tuple[NotificationPolicyInput, ...] = ()


@dataclass(frozen=True)
class TaskDraft:
    """Input bundle for creating a task item."""

    created_at_utc: str
    created_by_subject_id: str
    title: str
    item_id: str | None = None
    audit_id: str | None = None
    summary: str | None = None
    source_ref: str | None = None
    task_status: TaskStatus | str = TaskStatus.OPEN
    completion_state: str | None = None
    priority: str | None = None
    due_anchor: TemporalAnchorInput | None = None
    defer_until_anchor: TemporalAnchorInput | None = None
    completed_at_utc: str | None = None
    completed_by_subject_id: str | None = None
    item_locations: tuple[ItemLocationInput, ...] = ()
    subject_roles: tuple[ItemSubjectRoleInput, ...] = ()
    notification_policies: tuple[NotificationPolicyInput, ...] = ()


@dataclass(frozen=True)
class ItemVersionDraft:
    """Input bundle for creating the next immutable item version."""

    item_id: str
    target_version: int
    created_at_utc: str
    created_by_subject_id: str
    audit_id: str | None = None
    title: str | None = None
    summary: str | None | object = _UNSET
    source_ref: str | None | object = _UNSET
    event_detail: dict[str, object] | None = None
    task_detail: dict[str, object] | None = None
    audit_action: str = "version_created"
    reason_code: str = "item_version_created"
