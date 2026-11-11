"""Resolve a schedule destination without writes, receipts or dispatch.

The family adapter retains admission and replay ordering. Only its ledger and
configured route defaults cross this boundary; no command context is imported.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from typing import TypedDict

from spine.core import request_values
from spine.core.errors import SpineValidationError
from spine.ledger import catalog_reads


class ResolvedDelivery(TypedDict):
    recipient_kind: str
    recipient_id: str
    recipient_subject_id: str | None
    recipient_group_id: str | None
    channel: str
    delivery_target_id: str
    snapshot: dict[str, object]


def resolve_delivery(
    value: object, *, ledger: sqlite3.Connection, defaults: Mapping[str, object]
) -> ResolvedDelivery:
    delivery = request_values.object_value(value, "delivery")
    request_values.exact_fields(
        delivery,
        {"recipient_kind", "recipient_subject_id", "recipient_group_id", "channel", "target"},
        "delivery",
    )
    recipient_kind = request_values.enum_value(delivery.get("recipient_kind"), "delivery.recipient_kind", {"subject", "subject_group"})
    channel = request_values.required_string(delivery, "channel", "delivery.channel")
    subject_id = request_values.optional_string(delivery, "recipient_subject_id", "delivery.recipient_subject_id")
    group_id = request_values.optional_string(delivery, "recipient_group_id", "delivery.recipient_group_id")
    if recipient_kind == "subject":
        if subject_id is None or group_id is not None:
            raise SpineValidationError(
                "invalid_request:delivery.recipient_subject_id",
                "subject recipient requires recipient_subject_id only",
            )
        if not catalog_reads.subject_exists(ledger, subject_id):
            raise SpineValidationError("referenced_row_not_found:delivery.recipient_subject_id", "recipient subject not found")
        recipient_id = subject_id
    else:
        if group_id is None or subject_id is not None:
            raise SpineValidationError(
                "invalid_request:delivery.recipient_group_id",
                "subject_group recipient requires recipient_group_id only",
            )
        if not catalog_reads.subject_group_exists(ledger, group_id):
            raise SpineValidationError("referenced_row_not_found:delivery.recipient_group_id", "recipient group not found")
        recipient_id = group_id

    target_request = request_values.object_value(delivery.get("target"), "delivery.target")
    resolution_source = target_request.get("resolution")
    default_key: str | None = None
    if resolution_source == "explicit":
        request_values.exact_fields(target_request, {"resolution", "delivery_target_id"}, "delivery.target")
        delivery_target_id = request_values.required_string(
            target_request,
            "delivery_target_id",
            "delivery.target.delivery_target_id",
        )
    elif resolution_source == "context_default":
        request_values.exact_fields(target_request, {"resolution", "default_key"}, "delivery.target")
        default_key = request_values.required_string(target_request, "default_key", "delivery.target.default_key")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", default_key) is None:
            raise SpineValidationError("invalid_request:delivery.target.default_key", "default_key has an invalid format")
        default_value = defaults.get(default_key)
        if default_value is None:
            raise SpineValidationError("referenced_row_not_found:delivery.target.default_key", "delivery target default not found")
        if isinstance(default_value, str):
            delivery_target_id = default_value
        elif isinstance(default_value, Sequence) and not isinstance(default_value, (bytes, bytearray, str)):
            matches = [candidate for candidate in default_value if isinstance(candidate, str) and candidate]
            if len(matches) == 0:
                raise SpineValidationError("referenced_row_not_found:delivery.target.default_key", "delivery target default not found")
            if len(matches) != 1:
                raise SpineValidationError("semantic_conflict:delivery.target.default_key", "delivery target default is ambiguous")
            delivery_target_id = matches[0]
        else:
            raise SpineValidationError("semantic_conflict:delivery.target.default_key", "delivery target default is invalid")
    else:
        raise SpineValidationError(
            "invalid_request:delivery.target.resolution",
            "delivery.target.resolution must be explicit or context_default",
        )

    target = catalog_reads.delivery_target(ledger, delivery_target_id, required=False)
    missing_field = "delivery.target.delivery_target_id" if resolution_source == "explicit" else "delivery.target.default_key"
    if target is None:
        raise SpineValidationError(f"referenced_row_not_found:{missing_field}", "delivery target not found")
    if target["status"] != "active":
        raise SpineValidationError(f"semantic_conflict:{missing_field}", "delivery target is inactive")
    if target["channel"] != channel:
        raise SpineValidationError("semantic_conflict:delivery.channel", "delivery target channel does not match delivery.channel")
    expected_owner = target["owner_subject_id"] if recipient_kind == "subject" else target["owner_group_id"]
    if target["owner_kind"] != recipient_kind or expected_owner != recipient_id:
        raise SpineValidationError(
            f"semantic_conflict:delivery.{'recipient_subject_id' if recipient_kind == 'subject' else 'recipient_group_id'}",
            "delivery target owner does not match recipient",
        )
    snapshot: dict[str, object] = {
        "delivery_target_id": delivery_target_id,
        "resolution_source": resolution_source,
        "recipient_kind": recipient_kind,
        "channel": channel,
        "adapter_name": target["adapter_name"],
        "target_ref": target["target_ref"],
        "delivery_state": "not_attempted_by_command",
        ("recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"): recipient_id,
    }
    if default_key is not None:
        snapshot["default_key"] = default_key
    return {
        "recipient_kind": recipient_kind,
        "recipient_id": recipient_id,
        "recipient_subject_id": subject_id,
        "recipient_group_id": group_id,
        "channel": channel,
        "delivery_target_id": delivery_target_id,
        "snapshot": snapshot,
    }
