"""Deterministic builders for common high-level schedule.create requests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


def build_relative_event_countdown(
    *,
    command_id: str,
    actor_subject_id: str,
    reference_time: datetime,
    title: str,
    summary: str | None,
    source_ref: str | None,
    event_detail: Mapping[str, Any],
    timezone: str,
    timezone_database_version: str,
    event_delay_seconds: int,
    reminder_start_before_seconds: int,
    reminder_interval_seconds: int,
    policy_key: str,
    materialization_limit: int,
    delivery: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile relative intent into a fully pinned schedule.create request."""

    event_at = reference_time.astimezone(UTC) + timedelta(seconds=event_delay_seconds)
    local = event_at.astimezone(ZoneInfo(timezone))
    item: dict[str, Any] = {
        "item_type": "event",
        "title": title,
        "event_detail": dict(event_detail),
    }
    if summary is not None:
        item["summary"] = summary
    if source_ref is not None:
        item["source_ref"] = source_ref
    request = {
        "contract_version": "spine.schedule-create.v1",
        "command_id": command_id,
        "actor_subject_id": actor_subject_id,
        "created_at_utc": _utc_text(reference_time),
        "item": item,
        "scheduled_time": {
            "time_basis": "local_instant",
            "local_date": local.date().isoformat(),
            "local_time": local.replace(tzinfo=None).strftime("%H:%M:%S"),
            "timezone": timezone,
            "timezone_database_version": {
                "kind": "explicit",
                "version": timezone_database_version,
            },
        },
        "delivery": dict(delivery),
        "reminders": [
            {
                "policy_key": policy_key,
                "schedule": {
                    "kind": "repeat_window",
                    "start": {
                        "kind": "target_offset",
                        "offset_basis": "elapsed",
                        "offset_seconds": str(-reminder_start_before_seconds),
                    },
                    "stop": {
                        "kind": "target_offset",
                        "offset_basis": "elapsed",
                        "offset_seconds": "0",
                    },
                    "stop_inclusive": False,
                    "cadence": {
                        "kind": "fixed_elapsed",
                        "interval_seconds": str(reminder_interval_seconds),
                    },
                },
                "late_handling": {"kind": "skip"},
            }
        ],
        "materialization": {
            "mode": "bounded",
            "evaluated_at_utc": _utc_text(reference_time),
            "range": {
                "kind": "item_relative",
                "start_offset_seconds": str(-reminder_start_before_seconds),
                "end_offset_seconds": "0",
            },
            "limit": str(materialization_limit),
        },
    }
    return {
        "ok": True,
        "command": "schedule.build",
        "response_contract": "spine.schedule-countdown-builder-response.v1",
        "effect": "schedule_create_request_built",
        "reference_time_utc": _utc_text(reference_time),
        "event_at_utc": _utc_text(event_at),
        "timezone": timezone,
        "timezone_database_version": timezone_database_version,
        "estimated_reminder_count": str((reminder_start_before_seconds + reminder_interval_seconds - 1) // reminder_interval_seconds),
        "schedule_create_request": request,
    }


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
