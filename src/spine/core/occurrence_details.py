"""Shared pure occurrence detail projection and scheduled-fact helpers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from spine.core.schedule import parse_scheduled_fact


def decorate_occurrence(
    item: Mapping[str, Any],
    recurrence: Mapping[str, Any],
    occurrence: dict[str, Any],
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    detail = item["detail"]
    time_basis = str(recurrence["time_basis"])
    expressed = str(occurrence["expressed_scheduled_fact"])
    lifecycle = str(occurrence["lifecycle"])
    scheduled_anchor = value_anchor_from_scheduled_fact(
        expressed,
        time_basis=time_basis,
        timezone=recurrence.get("timezone"),
    )
    event_patch = occurrence.pop("event_detail_patch", None)
    task_patch = occurrence.pop("task_detail_patch", None)
    occurrence.pop("common_detail_patch", None)
    if not include_internal:
        occurrence.pop("target_occurrence_selector", None)
    if item["item_type"] == "event":
        event_status = "cancelled" if detail["event_status"] == "cancelled" or lifecycle == "cancelled" else "scheduled"
        all_day = bool(detail["all_day"])
        if isinstance(event_patch, Mapping) and "all_day" in event_patch:
            all_day = bool(event_patch["all_day"])
        result_detail: dict[str, Any] = {
            "event_status": event_status,
            "all_day": all_day,
            "start_anchor": scheduled_anchor,
        }
        if isinstance(event_patch, Mapping) and "end_scheduled_fact" in event_patch:
            if event_patch["end_scheduled_fact"] is not None:
                result_detail["end_anchor"] = value_anchor_from_scheduled_fact(
                    str(event_patch["end_scheduled_fact"]),
                    time_basis=time_basis,
                    timezone=recurrence.get("timezone"),
                )
        elif detail.get("end_anchor") is not None:
            result_detail["end_anchor"] = shift_value_anchor(
                detail["end_anchor"],
                seed_anchor=detail["start_anchor"],
                new_seed_fact=expressed,
                time_basis=time_basis,
            )
        occurrence["occurrence_event_detail"] = result_detail
        actionable = item["status"] == "active" and detail["event_status"] == "scheduled" and lifecycle != "cancelled"
    else:
        if detail["task_status"] in {"done", "cancelled"}:
            task_status = detail["task_status"]
        elif lifecycle == "completed":
            task_status = "done"
        elif lifecycle == "cancelled":
            task_status = "cancelled"
        else:
            task_status = "open"
        result_detail = {"task_status": task_status, "due_anchor": scheduled_anchor}
        if isinstance(task_patch, Mapping) and "priority" in task_patch:
            result_detail["priority"] = task_patch["priority"]
        elif "priority" in detail:
            result_detail["priority"] = detail["priority"]
        if isinstance(task_patch, Mapping) and "defer_until_scheduled_fact" in task_patch:
            if task_patch["defer_until_scheduled_fact"] is not None:
                result_detail["defer_until_anchor"] = value_anchor_from_scheduled_fact(
                    str(task_patch["defer_until_scheduled_fact"]),
                    time_basis=time_basis,
                    timezone=recurrence.get("timezone"),
                )
        elif detail.get("defer_until_anchor") is not None:
            result_detail["defer_until_anchor"] = shift_value_anchor(
                detail["defer_until_anchor"],
                seed_anchor=detail["due_anchor"],
                new_seed_fact=expressed,
                time_basis=time_basis,
            )
        occurrence["occurrence_task_detail"] = result_detail
        actionable = item["status"] == "active" and detail["task_status"] == "open" and lifecycle == "active"
    occurrence["actionable"] = actionable
    return occurrence


def value_anchor_from_scheduled_fact(value: str, *, time_basis: str, timezone: object) -> dict[str, Any]:
    parse_scheduled_fact(value, time_basis=time_basis, field="scheduled_fact")
    if time_basis == "local_date":
        return {"anchor_kind": "local_date", "local_date": value, "timezone": timezone}
    if time_basis == "local_instant":
        local_date, local_time = value.split("T", 1)
        return {
            "anchor_kind": "local_instant",
            "local_date": local_date,
            "local_time": local_time,
            "timezone": timezone,
        }
    return {"anchor_kind": "instant_utc", "utc_instant": value}


def shift_value_anchor(
    anchor: Mapping[str, Any],
    *,
    seed_anchor: Mapping[str, Any],
    new_seed_fact: str,
    time_basis: str,
) -> dict[str, Any]:
    anchor_fact = scheduled_fact_from_anchor(anchor, time_basis=time_basis)
    seed_fact = scheduled_fact_from_anchor(seed_anchor, time_basis=time_basis)
    parsed_anchor = parse_scheduled_fact(anchor_fact, time_basis=time_basis, field="anchor")
    parsed_seed = parse_scheduled_fact(seed_fact, time_basis=time_basis, field="seed_anchor")
    parsed_new = parse_scheduled_fact(new_seed_fact, time_basis=time_basis, field="new_seed")
    shifted = parsed_new + (parsed_anchor - parsed_seed)
    shifted_fact = format_scheduled_fact(shifted, time_basis=time_basis)
    return value_anchor_from_scheduled_fact(
        shifted_fact,
        time_basis=time_basis,
        timezone=anchor.get("timezone"),
    )


def scheduled_fact_from_anchor(anchor: Mapping[str, Any], *, time_basis: str) -> str:
    if time_basis == "local_date":
        return str(anchor["local_date"])
    if time_basis == "local_instant":
        return f"{anchor['local_date']}T{anchor['local_time']}"
    return str(anchor["utc_instant"])


def format_scheduled_fact(value: date | datetime, *, time_basis: str) -> str:
    if time_basis == "local_date":
        assert isinstance(value, date) and not isinstance(value, datetime)
        return value.isoformat()
    assert isinstance(value, datetime)
    if time_basis == "local_instant":
        return value.isoformat(timespec="seconds")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_scheduled_fact(value: str, *, time_basis: str) -> str:
    parsed = parse_scheduled_fact(value, time_basis=time_basis, field="scheduled_fact")
    if time_basis == "local_date":
        assert isinstance(parsed, date) and not isinstance(parsed, datetime)
        return (parsed + timedelta(days=1)).isoformat()
    assert isinstance(parsed, datetime)
    advanced = parsed + timedelta(seconds=1)
    return format_scheduled_fact(advanced, time_basis=time_basis)
