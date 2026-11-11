"""Shared schedule-policy preparation; no writes, dispatch or authority inference.

Family adapters retain request admission and receipt ownership. The existing
_UNSET identity continues to distinguish copy-forward from an explicit empty set.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.notifications import NormalizedNotificationPolicy, normalize_notification_policy, revise_notification_policy
from spine.core.request_values import exact_fields, object_value, required_string
from spine.ledger.item_drafts import _UNSET


def normalize_policies(
    value: object,
    *,
    item_id: str,
    item_type: str,
    recurring: bool,
    command_id: str,
    created_at_utc: str,
    delivery: Mapping[str, Any],
) -> tuple[tuple[str, NormalizedNotificationPolicy], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError(
            "invalid_request:notification_plan.custom_additions",
            "custom_additions must be an array",
        )
    if not 1 <= len(value) <= 32:
        raise SpineValidationError(
            "invalid_request:notification_plan.custom_additions",
            "custom_additions must contain 1 through 32 policies",
        )
    keyed: list[tuple[str, int, Mapping[str, Any]]] = []
    seen_keys: set[str] = set()
    for index, raw in enumerate(value):
        field = f"notification_plan.custom_additions[{index}]"
        reminder: Mapping[str, Any] = object_value(raw, field)
        exact_fields(reminder, {"policy_key", "schedule", "late_handling"}, field)
        policy_key = required_string(reminder, "policy_key", f"{field}.policy_key")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", policy_key) is None:
            raise SpineValidationError(
                f"invalid_request:{field}.policy_key",
                "policy_key has an invalid format",
            )
        if policy_key in seen_keys:
            raise SpineValidationError(
                f"semantic_conflict:{field}.policy_key",
                "policy_key must be unique",
            )
        seen_keys.add(policy_key)
        keyed.append((policy_key, index, reminder))
    result: list[tuple[str, NormalizedNotificationPolicy]] = []
    seen_schedules: set[str] = set()
    for policy_key, index, reminder in sorted(keyed, key=lambda entry: entry[0]):
        normalized = normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {
                    "anchor_role": "event_start" if item_type == "event" else "task_due",
                    "application_scope": "each_occurrence" if recurring else "item",
                },
                "schedule": reminder.get("schedule"),
                "late_handling": reminder.get("late_handling"),
            },
            item_id=item_id,
            item_version="1",
            command_id=f"{command_id}:{policy_key}",
            created_at_utc=created_at_utc,
            recipient_kind=str(delivery["recipient_kind"]),
            recipient_id=str(delivery["recipient_id"]),
            channel=str(delivery["channel"]),
            delivery_target_id=str(delivery["delivery_target_id"]),
        )
        schedule_hash = str(normalized.value["normalized_notification_schedule_hash"])
        if schedule_hash in seen_schedules:
            raise SpineValidationError(
                f"semantic_conflict:notification_plan.custom_additions[{index}]",
                "reminder duplicates another normalized policy",
            )
        seen_schedules.add(schedule_hash)
        result.append((policy_key, normalized))
    return tuple(result)


def update_policies(
    current: Sequence[Mapping[str, object]],
    *,
    desired: object,
    delivery: Mapping[str, Any] | None,
    item: Mapping[str, Any],
    next_version: int,
    command_id: str,
    updated_at: str,
    policy_keys: Mapping[str, str],
    established_policy_intents: set[str],
    recurring: bool,
) -> tuple[tuple[tuple[str, NormalizedNotificationPolicy], ...], dict[str, str], list[str]]:
    by_intent = {str(value["notification_intent_id"]): value for value in current}
    keyed: list[tuple[str, Mapping[str, Any] | None, Mapping[str, object] | None]] = []
    if desired is _UNSET:
        for prior in current:
            keyed.append((policy_keys[str(prior["notification_intent_id"])], None, prior))
    else:
        if not isinstance(desired, Sequence) or isinstance(desired, (str, bytes, bytearray)) or len(desired) > 32:
            raise SpineValidationError(
                "invalid_request:patch.notification_plan.custom_additions",
                "custom_additions must contain zero through 32 entries",
            )
        seen_keys: set[str] = set()
        seen_intents: set[str] = set()
        for index, raw in enumerate(desired):
            field = f"patch.notification_plan.custom_additions[{index}]"
            submitted = object_value(raw, field)
            exact_fields(
                submitted,
                {"policy_key", "notification_intent_id", "notification_policy_id", "schedule", "late_handling"},
                field,
            )
            key = required_string(submitted, "policy_key", f"{field}.policy_key")
            if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key) is None or key in seen_keys:
                raise SpineValidationError(f"semantic_conflict:{field}.policy_key", "policy_key is invalid or duplicated")
            seen_keys.add(key)
            intent_id = submitted.get("notification_intent_id")
            policy_id = submitted.get("notification_policy_id")
            if (intent_id is None) != (policy_id is None):
                missing = "notification_intent_id" if intent_id is None else "notification_policy_id"
                raise SpineValidationError(f"invalid_request:{field}.{missing}", "both reminder identities are required")
            prior = None
            if intent_id is not None:
                if not isinstance(intent_id, str) or not isinstance(policy_id, str):
                    raise SpineValidationError(f"invalid_request:{field}", "reminder identities must be strings")
                prior = by_intent.get(intent_id)
                if prior is None or prior["notification_policy_id"] != policy_id:
                    raise SpineValidationError(
                        f"semantic_conflict:{field}.notification_policy_id",
                        "policy is not current",
                    )
                if intent_id in seen_intents:
                    raise SpineValidationError(f"semantic_conflict:{field}.notification_intent_id", "intent is duplicated")
                seen_intents.add(intent_id)
                established = policy_keys.get(intent_id)
                if intent_id in established_policy_intents and established is not None and established != key:
                    raise SpineValidationError(
                        f"semantic_conflict:{field}.policy_key",
                        "policy_key is bound to another intent",
                    )
            elif delivery is None:
                raise SpineValidationError("missing_patch.delivery", "new reminders require patch.delivery")
            keyed.append((key, submitted, prior))
    result: list[tuple[str, NormalizedNotificationPolicy]] = []
    effects: dict[str, str] = {}
    schedule_hashes: set[str] = set()
    for key, entry, prior in sorted(keyed, key=lambda value: value[0]):
        if prior is not None:
            route = policy_route(prior, delivery)
            normalized = revise_notification_policy(
                prior,
                item_version=str(next_version),
                command_id=command_id,
                changed_at_utc=updated_at,
                recipient_kind=route["recipient_kind"],
                recipient_id=route["recipient_id"],
                channel=route["channel"],
                delivery_target_id=route["delivery_target_id"],
                target=prior["target"],
                schedule=entry["schedule"] if entry is not None else prior["schedule"],
                late_handling=entry["late_handling"] if entry is not None else prior["late_handling"],
            )
            changed = (
                normalized.value["normalized_notification_schedule_hash"] != prior["normalized_notification_schedule_hash"]
                or normalized.value["delivery_target_id"] != prior["delivery_target_id"]
                or normalized.value["recipient_kind"] != prior["recipient_kind"]
                or normalized.value["channel"] != prior["channel"]
            )
            effects[str(prior["notification_intent_id"])] = "updated" if changed else "retained"
        else:
            assert entry is not None and delivery is not None
            normalized = normalize_notification_policy(
                {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {
                        "anchor_role": "event_start" if item["item_type"] == "event" else "task_due",
                        "application_scope": "each_occurrence" if recurring else "item",
                    },
                    "schedule": entry["schedule"],
                    "late_handling": entry["late_handling"],
                },
                item_id=str(item["item_id"]),
                item_version=str(next_version),
                command_id=f"{command_id}:{key}",
                created_at_utc=updated_at,
                recipient_kind=str(delivery["recipient_kind"]),
                recipient_id=str(delivery["recipient_id"]),
                channel=str(delivery["channel"]),
                delivery_target_id=str(delivery["delivery_target_id"]),
            )
            effects[str(normalized.value["notification_intent_id"])] = "created"
        schedule_hash = str(normalized.value["normalized_notification_schedule_hash"])
        if schedule_hash in schedule_hashes:
            raise SpineValidationError("semantic_conflict:patch.notification_plan", "two reminders normalize to the same policy")
        schedule_hashes.add(schedule_hash)
        result.append((key, normalized))
    resulting_intents = {str(value.value["notification_intent_id"]) for _, value in result}
    disabled = sorted(set(by_intent) - resulting_intents)
    return tuple(result), effects, disabled


def disabled_policy(
    prior: Mapping[str, object],
    *,
    item_version: int,
    command_id: str,
    updated_at: str,
) -> NormalizedNotificationPolicy:
    route = policy_route(prior, None)
    return revise_notification_policy(
        prior,
        item_version=str(item_version),
        command_id=command_id,
        changed_at_utc=updated_at,
        recipient_kind=route["recipient_kind"],
        recipient_id=route["recipient_id"],
        channel=route["channel"],
        delivery_target_id=route["delivery_target_id"],
        target=prior["target"],
        schedule=prior["schedule"],
        late_handling=prior["late_handling"],
        status="disabled",
        disabled_at_utc=updated_at,
    )


def policy_route(policy: Mapping[str, object], delivery: Mapping[str, Any] | None) -> dict[str, str]:
    if delivery is not None:
        return {
            "recipient_kind": str(delivery["recipient_kind"]),
            "recipient_id": str(delivery["recipient_id"]),
            "channel": str(delivery["channel"]),
            "delivery_target_id": str(delivery["delivery_target_id"]),
        }
    recipient_kind = str(policy["recipient_kind"])
    recipient_field = "recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"
    return {
        "recipient_kind": recipient_kind,
        "recipient_id": str(policy[recipient_field]),
        "channel": str(policy["channel"]),
        "delivery_target_id": str(policy["delivery_target_id"]),
    }
