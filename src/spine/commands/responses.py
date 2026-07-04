"""Public JSON response builders for the agent command contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def item_show_response(
    item: Mapping[str, Any],
    *,
    include_relations: bool = False,
    relations: Sequence[Mapping[str, Any]] = (),
    locations_limit: str = "50",
    locations_truncated: bool = False,
    subject_roles_limit: str = "50",
    subject_roles_truncated: bool = False,
    notification_policies_limit: str = "50",
    notification_policies_truncated: bool = False,
    relations_limit: str = "50",
    relations_truncated: bool = False,
) -> dict[str, Any]:
    """Return the catalogued ``item.show`` success shape."""

    response = {
        "ok": True,
        "command": "item.show",
        **_item_shell(item),
        "current_common": _common_version(item["current_version"], _mapping(item.get("version"))),
        "locations": [_location_element(row) for row in _sequence(item.get("locations"))],
        "subject_roles": [_subject_role_element(row) for row in _sequence(item.get("subject_roles"))],
        "notification_policies": [_notification_policy_element(row) for row in _sequence(item.get("notification_policies"))],
        "locations_limit": locations_limit,
        "locations_truncated": locations_truncated,
        "subject_roles_limit": subject_roles_limit,
        "subject_roles_truncated": subject_roles_truncated,
        "notification_policies_limit": notification_policies_limit,
        "notification_policies_truncated": notification_policies_truncated,
    }
    detail = _mapping(item.get("detail"))
    if item.get("item_type") == "event":
        response["event_detail"] = _event_detail(detail)
    elif item.get("item_type") == "task":
        response["task_detail"] = _task_detail(detail)
    if include_relations:
        response["relations"] = [dict(row) for row in relations]
        response["relations_limit"] = relations_limit
        response["relations_truncated"] = relations_truncated
    return _omit_none(response)


def item_list_response(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: str = "50",
    truncated: bool = False,
) -> dict[str, Any]:
    """Return the catalogued ``item.list`` success shape."""

    return {
        "ok": True,
        "command": "item.list",
        "items": [_item_list_element(item) for item in items],
        "limit": limit,
        "truncated": truncated,
    }


def event_update_response(
    *,
    updated: bool,
    item: Mapping[str, Any],
    target_version: str,
    audit_id: str | None,
    command_receipt_id: str,
) -> dict[str, Any]:
    """Return the catalogued ``event.update`` success shape."""

    return _mutation_response(
        command="event.update",
        effect_field="updated",
        effect_value=updated,
        item_type="event",
        item=item,
        target_version=target_version,
        detail_key="event_detail",
        detail=_event_detail(_mapping(item.get("detail"))),
        audit_id=audit_id,
        command_receipt_id=command_receipt_id,
    )


def event_reschedule_response(
    *,
    rescheduled: bool,
    item: Mapping[str, Any],
    target_version: str,
    audit_id: str | None,
    command_receipt_id: str,
) -> dict[str, Any]:
    """Return the catalogued ``event.reschedule`` success shape."""

    return _mutation_response(
        command="event.reschedule",
        effect_field="rescheduled",
        effect_value=rescheduled,
        item_type="event",
        item=item,
        target_version=target_version,
        detail_key="event_detail",
        detail=_event_detail(_mapping(item.get("detail"))),
        audit_id=audit_id,
        command_receipt_id=command_receipt_id,
    )


def task_update_response(
    *,
    updated: bool,
    item: Mapping[str, Any],
    target_version: str,
    audit_id: str | None,
    command_receipt_id: str,
) -> dict[str, Any]:
    """Return the catalogued ``task.update`` success shape."""

    return _mutation_response(
        command="task.update",
        effect_field="updated",
        effect_value=updated,
        item_type="task",
        item=item,
        target_version=target_version,
        detail_key="task_detail",
        detail=_task_detail(_mapping(item.get("detail"))),
        audit_id=audit_id,
        command_receipt_id=command_receipt_id,
    )


def _mutation_response(
    *,
    command: str,
    effect_field: str,
    effect_value: bool,
    item_type: str,
    item: Mapping[str, Any],
    target_version: str,
    detail_key: str,
    detail: Mapping[str, Any],
    audit_id: str | None,
    command_receipt_id: str,
) -> dict[str, Any]:
    current_version = _string(item["current_version"])
    response = {
        "ok": True,
        "command": command,
        effect_field: effect_value,
        "item_id": item["item_id"],
        "item_type": item_type,
        "target_version": target_version,
        "version": current_version,
        "current_version": current_version,
        "updated_at_utc": item["updated_at_utc"],
        "current_common": _common_version(current_version, _mapping(item.get("version"))),
        detail_key: detail,
        "audit_id": audit_id,
        "command_receipt_id": command_receipt_id,
    }
    return _omit_none(response)


def _item_list_element(item: Mapping[str, Any]) -> dict[str, Any]:
    element = {
        **_item_shell(item),
        "current_common": _common_version(item["current_version"], _mapping(item.get("version"))),
    }
    detail = _mapping(item.get("detail"))
    if item.get("item_type") == "event":
        element["detail_status"] = detail.get("event_status")
    elif item.get("item_type") == "task":
        element["detail_status"] = detail.get("task_status")
    return _omit_none(element)


def _item_shell(item: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "item_id": item["item_id"],
            "item_type": item["item_type"],
            "current_version": _string(item["current_version"]),
            "status": item["status"],
            "created_at_utc": item["created_at_utc"],
            "updated_at_utc": item["updated_at_utc"],
            "archived_at_utc": item.get("archived_at_utc"),
        }
    )


def _common_version(version: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "version": _string(version),
            "title": row["title"],
            "summary": row.get("summary"),
            "source_ref": row.get("source_ref"),
            "intent_hash": row["intent_hash"],
            "normalized_fields_hash": row["normalized_fields_hash"],
            "created_at_utc": row["created_at_utc"],
            "created_by_subject_id": row["created_by_subject_id"],
        }
    )


def _event_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "event_status": detail["event_status"],
            "all_day": _bool(detail["all_day"]),
            "start_anchor_id": detail["start_anchor_id"],
            "start_anchor": detail.get("start_anchor"),
            "end_anchor_id": detail.get("end_anchor_id"),
            "end_anchor": detail.get("end_anchor"),
            "visibility": detail.get("visibility"),
            "attendance_policy_ref": detail.get("attendance_policy_ref"),
        }
    )


def _task_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "task_status": detail["task_status"],
            "due_anchor_id": detail.get("due_anchor_id"),
            "due_anchor": detail.get("due_anchor"),
            "defer_until_anchor_id": detail.get("defer_until_anchor_id"),
            "defer_until_anchor": detail.get("defer_until_anchor"),
            "completed_at_utc": detail.get("completed_at_utc"),
            "completed_by_subject_id": detail.get("completed_by_subject_id"),
            "completion_state": detail.get("completion_state"),
            "priority": detail.get("priority"),
        }
    )


def _location_element(row: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "location_id": row["location_id"],
            "item_location_id": row["item_location_id"],
            "role": row["role"],
            "item_locations.created_at_utc": row["created_at_utc"],
            "label": row["label"],
            "kind": row["kind"],
            "address_text": row.get("address_text"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "timezone": row.get("timezone"),
            "provider_ref": row.get("provider_ref"),
            "metadata_json": row.get("metadata_json"),
            "locations.created_at_utc": row.get("location_created_at_utc"),
            "locations.updated_at_utc": row.get("location_updated_at_utc"),
        }
    )


def _subject_role_element(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "item_subject_role_id": row["item_subject_role_id"],
        "subject_id": row["subject_id"],
        "role": row["role"],
        "status": row["status"],
        "created_at_utc": row["created_at_utc"],
    }


def _notification_policy_element(row: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            "notification_policy_id": row.get("notification_policy_id", row.get("policy_id")),
            "recipient_subject_id": row["recipient_subject_id"],
            "channel_preference_ref": row.get("channel_preference_ref"),
            "trigger_anchor_id": row["trigger_anchor_id"],
            "trigger_anchor": row.get("trigger_anchor"),
            "status": row["status"],
            "created_at_utc": row["created_at_utc"],
        }
    )


def _omit_none(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError("expected mapping")


def _sequence(value: Any) -> Sequence[Mapping[str, Any]]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    raise TypeError("expected sequence")


def _string(value: Any) -> str:
    return str(value)


def _bool(value: Any) -> bool:
    return bool(value)
