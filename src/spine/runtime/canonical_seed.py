"""Deterministic canonical notification seed used by demos and canaries."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from spine.commands import CommandContext, handle
from spine.core.errors import SpineValidationError


def seed_canonical_notification_work(
    connection: sqlite3.Connection,
    *,
    prefix: str,
    actor_subject_id: str,
    title: str,
    delivery_target_id: str,
    channel: str,
    recipient_kind: str,
    recipient_id: str,
    now_utc: str,
    eligible_at_utc: str,
) -> dict[str, object]:
    """Create a scheduled task, policy, opportunity, and durable work instance."""

    context = CommandContext(ledger=connection)
    eligible = datetime.strptime(eligible_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    due_at = (eligible + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    task = handle(
        "task.create",
        {
            "command_id": f"{prefix}-task-create",
            "actor_subject_id": actor_subject_id,
            "created_at_utc": now_utc,
            "title": title,
            "summary": "Controlled canonical Spine notification seed.",
            "due_anchor": {"anchor_kind": "instant_utc", "utc_instant": due_at},
        },
        context,
    )
    _require_ok(task)
    recipient_field = (
        "recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"
    )
    reminder = handle(
        "reminder.create",
        {
            "command_id": f"{prefix}-reminder-create",
            "actor_subject_id": actor_subject_id,
            "item_id": task["item_id"],
            "target_version": "1",
            "created_at_utc": now_utc,
            "recipient_kind": recipient_kind,
            recipient_field: recipient_id,
            "delivery_target_id": delivery_target_id,
            "channel": channel,
            "notification": {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "task_due", "application_scope": "item"},
                "schedule": {
                    "kind": "once",
                    "at": {"kind": "absolute_utc", "at_utc": eligible_at_utc},
                },
                "late_handling": {"kind": "deliver_within", "grace_seconds": "86400"},
            },
        },
        context,
    )
    _require_ok(reminder)
    range_start = (eligible - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    range_end = (eligible + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    materialized = handle(
        "notification_work.materialize",
        {
            "command_id": f"{prefix}-materialize",
            "actor_subject_id": actor_subject_id,
            "item_id": task["item_id"],
            "target_version": reminder["current_version"],
            "materialized_at_utc": now_utc,
            "range_start_utc": range_start,
            "range_end_utc": range_end,
            "limit": "10",
        },
        context,
    )
    _require_ok(materialized)
    work_ids = materialized["created_work_instance_ids"]
    if len(work_ids) != 1:
        raise SpineValidationError(
            "canonical_seed_failed", "canonical notification seed did not create exactly one work row"
        )
    return {
        "item_id": task["item_id"],
        "notification_intent_id": reminder["notification_intent_id"],
        "notification_policy_id": reminder["notification_policy_id"],
        "work_instance_id": work_ids[0],
        "eligible_at_utc": eligible_at_utc,
    }


def _require_ok(response: dict[str, object]) -> None:
    if not response.get("ok"):
        raise SpineValidationError("canonical_seed_failed", str(response.get("error")))
