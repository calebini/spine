"""Opt-in composition over the ordinary OpenClaw builder and canonical attempt gate."""

import hashlib
import sqlite3
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from spine.adapters.contextual_experiment import dump
from spine.adapters.openclaw import OpenClawOutboundMessage, build_openclaw_side_effect_request
from spine.adapters.side_effects import AttemptBackedSideEffectRequest
from spine.core.errors import SpineValidationError
from spine.core.hashing import side_effect_request_payload_hash
from spine.services.enrichment import SCHEMA


@dataclass(frozen=True)
class EnrichedOutboundMessage(OpenClawOutboundMessage):
    enrichment_selection: str = ""

    def request_envelope(self) -> dict[str, str]:
        result = super().request_envelope()
        result["payload_version"] = "spine.openclaw.outbound.v3"
        result["ordinary_rendered_content_hash"] = result.pop("rendered_content_hash")
        result["enriched_content_sha256"] = hashlib.sha256(self.body_text.encode()).hexdigest()
        result["enrichment_selection"] = self.enrichment_selection
        Draft202012Validator(SCHEMA["$defs"]["outbound"]).validate(result)
        return result


def build_enriched_request(
    connection: sqlite3.Connection, work_row: Mapping[str, object], envelope: Any, channel_hint: str, enrichment: Any,
) -> AttemptBackedSideEffectRequest[OpenClawOutboundMessage]:
    ordinary = build_openclaw_side_effect_request(connection, work_row=work_row, envelope=envelope, channel_hint=channel_hint)
    choice = enrichment.content_choice(connection, ordinary.work_instance_id, ordinary.message.body_text)
    if choice is None:
        return ordinary
    try:
        message = EnrichedOutboundMessage(**{
            **vars(ordinary.message),
            "body_text": ordinary.message.body_text + "\n\n" + choice["addendum"],
            "enrichment_selection": dump(choice).decode(),
        })
        request = message.request_envelope()
        payload_hash = side_effect_request_payload_hash(adapter_name="openclaw", request_envelope=request)
        enrichment.store.prepare_receipt(message.attempt_id, request, payload_hash)
    except Exception:
        # A private-store/evidence failure cannot prevent ordinary delivery.
        with suppress(OSError, sqlite3.Error):
            enrichment.store.disable(ordinary.work_instance_id)
        return ordinary

    def check(db: sqlite3.Connection) -> None:
        try:
            if request != message.request_envelope() or enrichment.store.receipt(message.attempt_id) != (request, payload_hash):
                raise ValueError("prepared enrichment evidence changed")
            enrichment.check_choice(db, ordinary.work_instance_id, choice)
        except Exception as exc:
            raise SpineValidationError("notification_enrichment_stale", "enrichment changed before attempt") from exc

    return AttemptBackedSideEffectRequest(
        message=message, attempt_id=ordinary.attempt_id, work_instance_id=ordinary.work_instance_id,
        idempotency_key=ordinary.idempotency_key, request_envelope=request, attempted_at_utc=ordinary.attempted_at_utc,
        notification_rendering=ordinary.notification_rendering,
        pre_write_check=check,
    )
