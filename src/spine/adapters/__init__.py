"""External runtime and side-effect adapter boundaries."""

from spine.adapters.openclaw import (
    DEFAULT_OPENCLAW_CHANNEL,
    OPENCLAW_ADAPTER_NAME,
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
    OpenClawOutboundMessage,
    build_openclaw_gateway_command,
    build_openclaw_outbound_message,
    build_openclaw_side_effect_request,
    normalize_openclaw_result,
    record_openclaw_result,
)
from spine.adapters.side_effects import (
    AttemptBackedSideEffectProcessor,
    AttemptBackedSideEffectRequest,
    NormalizedSideEffectResult,
    SideEffectBindingError,
    record_side_effect_result,
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
    "DEFAULT_OPENCLAW_CHANNEL",
    "OPENCLAW_ADAPTER_NAME",
    "AttemptBackedSideEffectProcessor",
    "AttemptBackedSideEffectRequest",
    "NO_PROCESSOR_CONFIGURED",
    "NormalizedOpenClawResult",
    "NormalizedSideEffectResult",
    "OpenClawBindingError",
    "OpenClawGatewayConfig",
    "OpenClawGatewaySender",
    "OpenClawNotificationProcessor",
    "OpenClawOutboundMessage",
    "SIDE_EFFECTS_BLOCKED",
    "STALE_WORK_BLOCKED",
    "SideEffectBindingError",
    "SpineTickerdWorkAdapter",
    "WorkProcessingOutcome",
    "build_openclaw_gateway_command",
    "build_openclaw_outbound_message",
    "build_openclaw_side_effect_request",
    "build_work_item_payload",
    "normalize_openclaw_result",
    "record_openclaw_result",
    "record_side_effect_result",
]
