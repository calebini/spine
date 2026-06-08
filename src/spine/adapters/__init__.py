"""External runtime and side-effect adapter boundaries."""

from spine.adapters.openclaw import (
    OPENCLAW_ADAPTER_NAME,
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawNotificationProcessor,
    OpenClawOutboundMessage,
    build_openclaw_outbound_message,
    record_openclaw_result,
)
from spine.adapters.tickerd import (
    NO_PROCESSOR_CONFIGURED,
    SIDE_EFFECTS_BLOCKED,
    STALE_WORK_BLOCKED,
    SpineTickerdWorkAdapter,
    WorkProcessingOutcome,
    build_work_item_payload,
)

__all__ = [
    "OPENCLAW_ADAPTER_NAME",
    "NO_PROCESSOR_CONFIGURED",
    "NormalizedOpenClawResult",
    "OpenClawBindingError",
    "OpenClawNotificationProcessor",
    "OpenClawOutboundMessage",
    "SIDE_EFFECTS_BLOCKED",
    "STALE_WORK_BLOCKED",
    "SpineTickerdWorkAdapter",
    "WorkProcessingOutcome",
    "build_openclaw_outbound_message",
    "build_work_item_payload",
    "record_openclaw_result",
]
