"""External runtime and side-effect adapter boundaries."""

from spine.adapters.tickerd import (
    NO_PROCESSOR_CONFIGURED,
    SIDE_EFFECTS_BLOCKED,
    STALE_WORK_BLOCKED,
    SpineTickerdWorkAdapter,
    build_work_item_payload,
)

__all__ = [
    "NO_PROCESSOR_CONFIGURED",
    "SIDE_EFFECTS_BLOCKED",
    "STALE_WORK_BLOCKED",
    "SpineTickerdWorkAdapter",
    "build_work_item_payload",
]
