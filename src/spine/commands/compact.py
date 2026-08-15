"""Compact, deterministic operator projections for schedule commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from spine.core.errors import SpineValidationError

COMPACT_CONTRACT_VERSION = "spine.schedule-compact.v1"


def compact_schedule_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Project a successful canonical schedule response without reading the ledger."""

    command = response.get("command")
    if response.get("ok") is not True:
        return dict(response)
    if command == "schedule.create":
        return _compact_create(response)
    if command == "schedule.show":
        return _compact_show(response)
    raise SpineValidationError("unsupported_field:compact", "compact output is only supported for schedule.create and schedule.show")


def _compact_create(response: Mapping[str, Any]) -> dict[str, Any]:
    policies = _mapping_sequence(response.get("policies"))
    materialization = _mapping(response.get("materialization"), "materialization")
    scheduled = _mapping(response.get("scheduled_time"), "scheduled_time")
    delivery = _mapping(response.get("delivery"), "delivery")
    phases = _mapping(response.get("phases"), "phases")
    work_ids = _string_sequence(materialization.get("work_instance_ids"), "materialization.work_instance_ids")
    dry_run = bool(response.get("dry_run", False))
    return {
        "ok": True,
        "command": "schedule.create",
        "projection_contract": COMPACT_CONTRACT_VERSION,
        "action": "schedule.create",
        "effect": str(response["effect"]),
        "dry_run": dry_run,
        "item_id": str(response["item_id"]),
        "item_type": str(response["item_type"]),
        "status": "active",
        "command_id": str(response["command_id"]),
        "command_receipt_id": str(response["command_receipt_id"]),
        "scheduled_times": [{"anchor_role": "event_start" if response["item_type"] == "event" else "task_due", **dict(scheduled)}],
        "timezone": scheduled.get("timezone"),
        "timezone_database_version": scheduled.get("timezone_database_version"),
        "notification_intent_ids": [str(policy["notification_intent_id"]) for policy in policies],
        "notification_policy_ids": [str(policy["notification_policy_id"]) for policy in policies],
        "notification_policy_count": str(len(policies)),
        "notification_policy_ids_truncated": False,
        "work": {
            "state": str(materialization["state"]),
            "count": str(materialization["work_instance_count"]),
            "work_instance_ids": work_ids,
            "work_instance_ids_truncated": False,
        },
        "lifecycle": {
            "authored": "preview" if dry_run else "committed",
            "opportunities": str(phases["opportunities"]),
            "work": str(phases["work"]),
            "delivery_attempt": "not_attempted",
            "delivery_outcome": "none",
        },
        "delivery_targets": [_compact_create_delivery(delivery)],
    }


def _compact_show(response: Mapping[str, Any]) -> dict[str, Any]:
    item = _mapping(response.get("item"), "item")
    scheduled_times = _mapping_sequence(response.get("scheduled_times"))
    lifecycle = _mapping(response.get("lifecycle"), "lifecycle")
    authored = _mapping(lifecycle.get("authored"), "lifecycle.authored")
    opportunities = _mapping(lifecycle.get("opportunities"), "lifecycle.opportunities")
    work_lifecycle = _mapping(lifecycle.get("work"), "lifecycle.work")
    delivery_lifecycle = _mapping(lifecycle.get("delivery"), "lifecycle.delivery")
    authoring_receipt = response.get("authoring_receipt")
    receipt = dict(authoring_receipt) if isinstance(authoring_receipt, Mapping) else {}
    policies = _mapping_sequence(response.get("notification_policies"))
    work_rows = _mapping_sequence(response.get("work_instances"))
    primary = next(
        (value for value in scheduled_times if value.get("anchor_role") in {"event_start", "task_due"}),
        scheduled_times[0] if scheduled_times else {},
    )
    return {
        "ok": True,
        "command": "schedule.show",
        "projection_contract": COMPACT_CONTRACT_VERSION,
        "action": "schedule.show",
        "effect": "readback",
        "dry_run": False,
        "item_id": str(item["item_id"]),
        "item_type": str(item["item_type"]),
        "status": str(item["status"]),
        "command_id": receipt.get("command_id"),
        "command_receipt_id": receipt.get("command_receipt_id"),
        "scheduled_times": [dict(value) for value in scheduled_times],
        "timezone": primary.get("timezone"),
        "timezone_database_version": primary.get("timezone_database_version"),
        "notification_intent_ids": [str(policy["notification_intent_id"]) for policy in policies],
        "notification_policy_ids": [str(policy["notification_policy_id"]) for policy in policies],
        "notification_policy_count": str(response.get("notification_policies_count", len(policies))),
        "notification_policy_ids_truncated": bool(response.get("notification_policies_truncated", False)),
        "work": {
            "state": str(work_lifecycle["state"]),
            "count": str(work_lifecycle["count"]),
            "work_instance_ids": [str(row["work_instance_id"]) for row in work_rows],
            "work_instance_ids_truncated": bool(response.get("work_instances_truncated", False)),
        },
        "lifecycle": {
            "authored": str(authored["state"]),
            "opportunities": str(opportunities["state"]),
            "work": str(work_lifecycle["state"]),
            "delivery_attempt": str(delivery_lifecycle["attempt_state"]),
            "delivery_outcome": str(delivery_lifecycle["outcome_state"]),
        },
        "delivery_targets": [_compact_show_delivery(value) for value in _mapping_sequence(response.get("delivery_targets"))],
    }


def _compact_create_delivery(delivery: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "delivery_target_id": str(delivery["delivery_target_id"]),
        "channel": str(delivery["channel"]),
        "destination_source_ref": str(delivery["adapter_name"]),
        "destination_target_ref": str(delivery["target_ref"]),
        "state": str(delivery["delivery_state"]),
    }


def _compact_show_delivery(value: Mapping[str, Any]) -> dict[str, Any]:
    current = _mapping(value.get("current_snapshot"), "delivery_targets.current_snapshot")
    return {
        "delivery_target_id": str(value["delivery_target_id"]),
        "channel": str(current["channel"]),
        "destination_source_ref": str(current["adapter_name"]),
        "destination_target_ref": str(current["target_ref"]),
        "state": str(current["status"]),
    }


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError("runtime_failure:compact", f"canonical response is missing {field}")
    return dict(value)


def _mapping_sequence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError("runtime_failure:compact", "canonical response contains an invalid collection")
    if not all(isinstance(entry, Mapping) for entry in value):
        raise SpineValidationError("runtime_failure:compact", "canonical response contains an invalid collection entry")
    return [dict(entry) for entry in value]


def _string_sequence(value: object, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not all(isinstance(entry, str) for entry in value):
        raise SpineValidationError("runtime_failure:compact", f"canonical response contains invalid {field}")
    return list(value)
