"""Spine coordination ledger package and implemented public declarations."""

__all__ = ["IMPLEMENTED_CONTRACT_VERSIONS", "IMPLEMENTED_LEDGER_SCHEMA_VERSION", "__version__"]

__version__ = "0.1.0"

IMPLEMENTED_LEDGER_SCHEMA_VERSION = 7
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
        "spine.system-info.v1",
    }
)
