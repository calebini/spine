"""Spine coordination ledger package and implemented public declarations."""

__all__ = ["IMPLEMENTED_CONTRACT_VERSIONS", "IMPLEMENTED_LEDGER_SCHEMA_VERSION", "__version__"]

__version__ = "0.1.0"

IMPLEMENTED_LEDGER_SCHEMA_VERSION = 8
IMPLEMENTED_CONTRACT_VERSIONS = frozenset(
    {
        "spine.canonical-json.v1",
        "spine.recurrence-authoring.v1",
        "spine.recurrence.contract.v1",
        "spine.recurrence.normalization.v1",
        "spine.item-occurrences.recurrence.v1",
        "spine.notification-schedule-authoring.v1",
        "spine.notification-schedule.contract.v1",
        "spine.notification-schedule.normalization.v1",
        "spine.notification-opportunities.v1",
        "spine.schedule-create.v1",
        "spine.schedule-create-normalization.v1",
        "spine.schedule-create-response.v1",
        "spine.schedule-create-receipt.v1",
        "spine.schedule-compact.v1",
        "spine.schedule-countdown-builder.v1",
        "spine.schedule-countdown-builder-response.v1",
        "spine.schedule-show.v1",
        "spine.schedule-operations-normalization.v1",
        "spine.schedule-agenda.v1",
        "spine.schedule-agenda-response.v1",
        "spine.schedule-update.v1",
        "spine.schedule-update-response.v1",
        "spine.schedule-update-receipt.v1",
        "spine.schedule-cancel.v1",
        "spine.schedule-cancel-response.v1",
        "spine.schedule-cancel-receipt.v1",
        "spine.relative-temporal-binding.v1",
        "spine.relative-temporal-binding-normalization.v1",
        "spine.normalized-temporal-binding-revision-hash.v1",
        "spine.temporal-binding-catalog.v1",
        "spine.schedule-related-task-create.v1",
        "spine.schedule-related-task-create-response.v1",
        "spine.schedule-related-task-create-receipt.v1",
        "spine.schedule-binding-list.v1",
        "spine.schedule-binding-list-response.v1",
        "spine.schedule-binding-list-cursor.v1",
        "spine.schedule-binding-reconcile.v1",
        "spine.schedule-binding-reconcile-response.v1",
        "spine.schedule-binding-reconcile-receipt.v1",
        "spine.system-info.v1",
    }
)
