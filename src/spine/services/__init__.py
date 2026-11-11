"""Provider-agnostic Spine service workflows.

Services are reserved for orchestration that adds policy, freshness checks,
work generation, attempt gating, or adapter-facing outcome handling. Plain
ledger passthroughs should import from ``spine.ledger`` directly instead of
accumulating here.
"""

from typing import TYPE_CHECKING, Any

from spine.services.attempts import (
    AttemptGate,
    prepare_candidate_action_attempt,
    prepare_projection_attempt,
    prepare_work_attempt,
    record_attempt_failure,
    record_attempt_rejection,
    record_attempt_success,
)
from spine.services.notification_rendering import resolve_notification_rendering
from spine.services.projections import plan_projection_sync
from spine.services.work import (
    cancel_work,
    fail_work,
    list_eligible_work,
    require_processable_work,
    retry_work,
    start_work,
    succeed_work,
)

if TYPE_CHECKING:
    from spine.services.scheduling import SchedulingCycleResult, materialize_notification_horizon


def __getattr__(name: str) -> Any:
    # The scheduler is a command-invocation adapter, not a dependency of every
    # service operation. Preserve its exports without eagerly importing commands.
    if name in {"SchedulingCycleResult", "materialize_notification_horizon"}:
        from spine.services import scheduling

        return getattr(scheduling, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AttemptGate",
    "cancel_work",
    "fail_work",
    "list_eligible_work",
    "materialize_notification_horizon",
    "plan_projection_sync",
    "prepare_candidate_action_attempt",
    "prepare_projection_attempt",
    "prepare_work_attempt",
    "record_attempt_failure",
    "record_attempt_rejection",
    "record_attempt_success",
    "resolve_notification_rendering",
    "require_processable_work",
    "retry_work",
    "start_work",
    "succeed_work",
    "SchedulingCycleResult",
]
