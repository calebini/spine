"""Read-only stale-work classification shared by scheduling composers."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import cast

from spine.ledger.notifications import NotificationPolicyResolver


def reconcile_work_plan(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    active_policies: Sequence[Mapping[str, object]],
    target_changed: bool,
    recurrence_changed: bool,
    temporal_binding_stale: bool = False,
    parent_terminal: bool = False,
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    policy_resolver = NotificationPolicyResolver(connection, active_policies)
    rows = connection.execute(
        """
        SELECT w.*,
               EXISTS (
                 SELECT 1 FROM side_effect_attempts AS a
                 WHERE a.work_instance_id = w.work_instance_id
               ) AS has_attempt
        FROM work_instances AS w
        WHERE w.item_id = ?
        ORDER BY w.work_instance_id
        """,
        (item_id,),
    ).fetchall()
    cancelled: list[str] = []
    retained: list[str] = []
    protected: list[str] = []
    reasons: dict[str, str] = {}
    for row in rows:
        policy = policy_resolver.resolve(str(row["notification_policy_id"]))
        reason = None
        if policy is not None and row["normalized_notification_schedule_hash"] != policy["normalized_notification_schedule_hash"]:
            reason = "notification_schedule_superseded"
        elif target_changed:
            reason = "notification_target_changed"
        elif recurrence_changed:
            reason = "notification_occurrence_stale"
        elif temporal_binding_stale:
            reason = "notification_temporal_binding_stale"
        elif policy is not None and row["delivery_target_id"] != policy["delivery_target_id"]:
            reason = "notification_routing_changed"
        elif policy is None:
            reason = "notification_policy_disabled"
        elif parent_terminal:
            reason = "parent_lifecycle_terminal"
        work_id = str(row["work_instance_id"])
        if reason is None:
            retained.append(work_id)
        elif row["status"] == "eligible" and int(row["attempt_count"]) == 0 and not bool(row["has_attempt"]):
            cancelled.append(work_id)
            reasons[work_id] = reason
        else:
            protected.append(work_id)
    return cancelled, retained, protected, reasons


def provenance_exists(connection: sqlite3.Connection, provenance_id: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM occurrence_provenance WHERE occurrence_provenance_id = ?", (provenance_id,)
    ).fetchone() is not None


def work_exists(connection: sqlite3.Connection, work_id: str) -> bool:
    return connection.execute("SELECT 1 FROM work_instances WHERE work_instance_id = ?", (work_id,)).fetchone() is not None


def provenance_scheduled_facts(connection: sqlite3.Connection, provenance_id: str) -> sqlite3.Row | None:
    return cast(sqlite3.Row | None, connection.execute(
        "SELECT original_scheduled_fact, expressed_scheduled_fact FROM occurrence_provenance WHERE occurrence_provenance_id = ?",
        (provenance_id,),
    ).fetchone())
