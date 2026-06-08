"""Provider-agnostic Spine service workflows."""

from spine.services.attempts import (
    AttemptGate,
    prepare_candidate_action_attempt,
    prepare_projection_attempt,
    prepare_work_attempt,
    record_attempt_failure,
    record_attempt_rejection,
    record_attempt_success,
)
from spine.services.items import create_event, create_task, get_current
from spine.services.projections import plan_projection_sync
from spine.services.work import (
    cancel_work,
    fail_work,
    generate_notification_reminder_work,
    list_eligible_work,
    require_processable_work,
    retry_work,
    start_work,
    succeed_work,
)

__all__ = [
    "AttemptGate",
    "cancel_work",
    "create_event",
    "create_task",
    "fail_work",
    "generate_notification_reminder_work",
    "get_current",
    "list_eligible_work",
    "plan_projection_sync",
    "prepare_candidate_action_attempt",
    "prepare_projection_attempt",
    "prepare_work_attempt",
    "record_attempt_failure",
    "record_attempt_rejection",
    "record_attempt_success",
    "require_processable_work",
    "retry_work",
    "start_work",
    "succeed_work",
]
