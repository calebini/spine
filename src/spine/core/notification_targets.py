"""Deterministic target and source-range calculations for schedule materialization."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.request_values import exact_fields, object_value, required_string
from spine.core.schedule import parse_scheduled_fact, resolve_local_instant, system_timezone_database_version
from spine.timezones import timezone_for_version


def recurrence_source_range(
    recurrence: Mapping[str, object],
    *,
    policies: list[dict[str, object]],
    eligibility_start: datetime,
    eligibility_end: datetime,
) -> tuple[str, str]:
    minimum_offset = 0
    maximum_offset = 0
    for policy in policies:
        target = object_value(policy.get("target"), "notification policy target")
        if target.get("application_scope") == "item":
            continue
        offsets = policy_offsets(policy)
        minimum_offset = min(minimum_offset, *offsets)
        maximum_offset = max(maximum_offset, *offsets)
    conservative = timedelta(days=2)
    target_start = eligibility_start - timedelta(seconds=maximum_offset) - conservative
    target_end = eligibility_end - timedelta(seconds=minimum_offset) + conservative
    basis = str(recurrence["time_basis"])
    if basis == "instant_utc":
        return utc_text(target_start), utc_text(target_end)
    zone = timezone_for_version(str(recurrence["timezone"]), str(recurrence["timezone_database_version"]))
    local_start = target_start.astimezone(zone)
    local_end = target_end.astimezone(zone)
    if basis == "local_date":
        return local_start.date().isoformat(), (local_end.date() + timedelta(days=1)).isoformat()
    return (
        local_start.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S"),
        (local_end.replace(tzinfo=None) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def policy_offsets(policy: Mapping[str, object]) -> list[int]:
    schedule = object_value(policy.get("schedule"), "notification policy schedule")
    kind = schedule.get("kind")
    if kind == "once":
        boundaries = [object_value(schedule.get("at"), "notification schedule boundary")]
    elif kind == "offsets":
        raw_boundaries = schedule.get("at")
        if not isinstance(raw_boundaries, Sequence) or isinstance(raw_boundaries, (str, bytes, bytearray)):
            raise SpineValidationError("invalid_request:reminders", "notification offsets must be an array")
        boundaries = [object_value(entry, "notification schedule boundary") for entry in raw_boundaries]
    else:
        boundaries = [
            object_value(schedule.get("start"), "notification schedule start"),
            object_value(schedule.get("stop"), "notification schedule stop"),
        ]
    values = [0]
    for boundary in boundaries:
        if boundary.get("kind") != "target_offset":
            continue
        if boundary.get("offset_basis") == "elapsed":
            values.append(int(str(boundary["offset_seconds"])))
        else:
            values.append(int(str(boundary["offset_days"])) * 86_400)
    return values


def parse_utc_datetime(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SpineValidationError("invalid_request:timestamp", "timestamp must be canonical UTC with trailing Z") from exc


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def target_from_anchor(anchor: Mapping[str, Any]) -> dict[str, object]:
    kind = str(anchor["anchor_kind"])
    if kind == "instant_utc":
        value = str(anchor["utc_instant"])
        return {"target_scheduled_fact": value, "target_utc_instant": value, "lifecycle": "scheduled", "actionable": True}
    timezone = str(anchor["timezone"])
    timezone_version = str(anchor.get("timezone_database_version") or system_timezone_database_version())
    local_date_value = str(anchor["local_date"])
    result: dict[str, object] = {
        "target_scheduled_fact": local_date_value,
        "target_local_date": local_date_value,
        "timezone": timezone,
        "timezone_database_version": timezone_version,
        "lifecycle": "scheduled",
        "actionable": True,
    }
    if kind == "local_instant":
        local_time = str(anchor["local_time"])
        if len(local_time) == 5:
            local_time += ":00"
        scheduled = f"{local_date_value}T{local_time}"
        resolution = resolve_local_instant(
            scheduled,
            timezone=timezone,
            timezone_database_version=timezone_version,
        )
        if resolution is None:
            raise SpineValidationError("semantic_conflict", "notification target is a nonexistent local instant")
        result["target_scheduled_fact"] = scheduled
        result["target_utc_instant"] = resolution.utc_instant
    return result


def resolve_initial_time(value: Mapping[str, Any]) -> dict[str, str]:
    exact_fields(
        value,
        {"time_basis", "local_date", "local_time", "timezone", "timezone_database_version", "recurrence"},
        "scheduled_time",
    )
    if value.get("time_basis") != "local_instant":
        raise SpineValidationError("invalid_request:scheduled_time.time_basis", "scheduled_time.time_basis must be local_instant")
    local_date = required_string(value, "local_date", "scheduled_time.local_date")
    local_time = required_string(value, "local_time", "scheduled_time.local_time")
    timezone = required_string(value, "timezone", "scheduled_time.timezone")
    local_datetime = f"{local_date}T{local_time}"
    try:
        parse_scheduled_fact(local_datetime, time_basis="local_instant", field="scheduled_time.local_time")
    except SpineValidationError as exc:
        if len(local_date) != 10 or local_datetime[:10] != local_date:
            raise SpineValidationError("invalid_request:scheduled_time.local_date", "scheduled_time.local_date is invalid") from exc
        raise
    directive = object_value(value.get("timezone_database_version"), "scheduled_time.timezone_database_version")
    kind = directive.get("kind")
    if kind == "explicit":
        exact_fields(directive, {"kind", "version"}, "scheduled_time.timezone_database_version")
        version = required_string(directive, "version", "scheduled_time.timezone_database_version.version")
    elif kind == "system_current":
        exact_fields(directive, {"kind"}, "scheduled_time.timezone_database_version")
        version = system_timezone_database_version()
    else:
        raise SpineValidationError(
            "invalid_request:scheduled_time.timezone_database_version.kind",
            "timezone_database_version.kind must be explicit or system_current",
        )
    try:
        resolution = resolve_local_instant(local_datetime, timezone=timezone, timezone_database_version=version)
    except SpineValidationError as exc:
        if exc.code == "invalid_request:timezone":
            raise SpineValidationError("invalid_request:scheduled_time.timezone", exc.message) from exc
        if exc.code == "environment_failure:timezone_database_version":
            raise SpineValidationError("environment_failure:scheduled_time.timezone_database_version", exc.message) from exc
        raise
    if resolution is None:
        raise SpineValidationError(
            "invalid_request:scheduled_time.local_time",
            "initial local time does not exist in the pinned timezone data",
        )
    if resolution.resolution_kind != "unambiguous":
        raise SpineValidationError(
            "invalid_request:scheduled_time.local_time",
            "initial local time is ambiguous in the pinned timezone data",
        )
    return {
        "local_date": local_date,
        "local_time": local_time,
        "timezone": timezone,
        "timezone_database_version": version,
        "utc_instant": resolution.utc_instant,
        "offset_seconds": resolution.offset_seconds,
    }
