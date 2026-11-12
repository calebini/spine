"""Bounded all-target reminder-lead admission; no recurrence expansion or writes."""

from __future__ import annotations

from typing import Any

from spine.core.recurring_task_runtime import fail
from spine.timezones import system_timezone_database_version, timezone_offset_bounds


def validate_reminder_lead(config: dict[str, Any], source: dict[str, Any]) -> None:
    """Prove the horizon covers every enabled template under source time facts.

    Calendar bounds cover every task clock (including moved occurrences), all
    historical zone offsets and future footer offsets. They are conservative:
    short horizons or mixed windows without a proof fail instead of guessing.
    Gap omission and earliest-fold resolution remain notification-owned.
    """
    plan = config["notification_plan"]
    if plan is None:
        return
    cache: dict[tuple[str, str], tuple[int, int]] = {}

    def offsets(zone: str, version: str) -> tuple[int, int]:
        key = zone, version
        if key not in cache:
            cache[key] = timezone_offset_bounds(zone, version)
        return cache[key]

    def target_zone() -> tuple[str, str]:
        if source["time_basis"] == "instant_utc":
            return "UTC", system_timezone_database_version()
        if source["time_basis"] != "local_instant" or not isinstance(source.get("timezone"), str) or not isinstance(
            source.get("timezone_database_version"), str
        ):
            fail("semantic_conflict", "configuration.notification_plan", "calendar reminder target timezone cannot be proved")
        return source["timezone"], source["timezone_database_version"]

    def bounds(boundary: dict[str, Any]) -> tuple[int, int, tuple[str, str] | None, int]:
        if boundary["kind"] != "target_offset":
            fail("semantic_conflict", "configuration.notification_plan", "earliest source-relative reminder lead cannot be proved")
        if boundary["offset_basis"] == "elapsed":
            value = int(boundary["offset_seconds"])
            return value, value, None, value
        target = target_zone()
        reminder = (boundary.get("timezone", target[0]), boundary.get("timezone_database_version", target[1]))
        target_min, target_max = offsets(*target)
        reminder_min, reminder_max = offsets(*reminder)
        clock = sum(int(part) * scale for part, scale in zip(boundary["local_time"].split(":"), (3600, 60, 1), strict=True))
        wall = int(boundary["offset_days"]) * 86400 + clock
        # Notification resolution uses the task's local date even when the
        # reminder explicitly selects a different zone. R-T = wall-task_clock
        # + task_UTC_offset-reminder_UTC_offset, with clock in [0,86399].
        return wall - 86399 + target_min - reminder_max, wall + target_max - reminder_min, reminder, wall

    lead = 0
    for entry in plan["resolved"]["effective_templates"]:
        schedule = entry["template"]["schedule"]
        boundaries = schedule["at"] if schedule["kind"] == "offsets" else (
            [schedule["at"]] if schedule["kind"] == "once" else [schedule["start"], schedule["stop"]]
        )
        intervals = [bounds(boundary) for boundary in boundaries]
        if schedule["kind"] == "repeat_window":
            start, stop = intervals
            # Same-zone calendar labels share the task date, so their order is
            # exact despite wide independent all-clock intervals. Otherwise
            # require nonoverlapping UTC-offset bounds. Equal bounds retain the
            # existing R2 strict-window admission rule.
            ordered = start[3] < stop[3] if start[2] == stop[2] else start[1] < stop[0]
            if not ordered:
                fail("semantic_conflict", "configuration.notification_plan", "repeat window ordering cannot be proved")
        lead = max(lead, -int(config["offset_seconds"]) - min(value[0] for value in intervals))
    if int(config["generation_horizon_seconds"]) < lead:
        fail("semantic_conflict", "configuration.generation_horizon_seconds", "horizon does not cover the proved reminder lead")
