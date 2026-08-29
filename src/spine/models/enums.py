"""MVP enum names for the first Spine model layer."""

from enum import StrEnum


class ItemType(StrEnum):
    EVENT = "event"
    TASK = "task"
    PROJECT = "project"
    COLLECTION = "collection"


class ItemStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SubjectKind(StrEnum):
    PERSON = "person"
    AGENT = "agent"


class SubjectStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SubjectMembershipRole(StrEnum):
    MEMBER = "member"
    OWNER = "owner"


class SubjectMembershipStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TemporalAnchorKind(StrEnum):
    INSTANT_UTC = "instant_utc"
    LOCAL_INSTANT = "local_instant"
    LOCAL_DATE = "local_date"
    UTC_WINDOW = "utc_window"
    LOCAL_WINDOW = "local_window"


class RelationType(StrEnum):
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"


class RelationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class LocationKind(StrEnum):
    ADDRESS = "address"
    PLACE = "place"
    VIRTUAL = "virtual"
    RELATIVE = "relative"
    UNKNOWN = "unknown"


class ItemLocationRole(StrEnum):
    PRIMARY = "primary"
    PICKUP = "pickup"
    DROPOFF = "dropoff"
    MEETING_LINK = "meeting_link"
    CONTEXT = "context"


class ItemSubjectRole(StrEnum):
    PARTICIPANT = "participant"
    ASSIGNEE = "assignee"
    WATCHER = "watcher"
    OWNER = "owner"
    RECIPIENT = "recipient"


class NotificationPolicyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DeliveryTargetOwnerKind(StrEnum):
    SUBJECT = "subject"
    SUBJECT_GROUP = "subject_group"


class DeliveryTargetStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class GenerationSourceKind(StrEnum):
    WORK_INSTANCE = "work_instance"
    NOTIFICATION_POLICY = "notification_policy"
    SCHEDULE_TICK = "schedule_tick"
    USER_ACTION = "user_action"
    ITEM_VERSION = "item_version"


class WorkKind(StrEnum):
    NOTIFICATION_REMINDER = "notification_reminder"


class WorkStatus(StrEnum):
    ELIGIBLE = "eligible"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateActionKind(StrEnum):
    DELIVER_NOTIFICATION = "deliver_notification"
    SYNC_PROJECTION = "sync_projection"
    REQUEST_USER_DECISION = "request_user_decision"


class CandidateActionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ProjectionStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    FAILED = "failed"
