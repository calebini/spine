"""Relational persistence for canonical notification policies and schedules."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notifications import (
    NormalizedNotificationPolicy,
    revise_notification_policy,
)
from spine.ledger.recurrence import (
    load_target_occurrence_selector,
    persist_target_occurrence_selector,
)


def notification_policy_actionability(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    policy: Mapping[str, object],
) -> tuple[bool, str | None]:
    """Return canonical policy-level actionability and its first failure reason."""

    if policy["status"] != "active":
        return False, "notification_policy_disabled"
    if item["status"] != "active":
        return False, "item_inactive"
    detail = item["detail"]
    if item["item_type"] == "event" and detail["event_status"] != "scheduled":
        return False, "event_not_scheduled"
    if item["item_type"] == "task" and detail["task_status"] != "open":
        return False, "task_not_open"
    target = connection.execute(
        "SELECT * FROM delivery_targets WHERE delivery_target_id = ?",
        (policy["delivery_target_id"],),
    ).fetchone()
    recipient_id = policy.get("recipient_subject_id") or policy.get("recipient_group_id")
    owner_id = None if target is None else target["owner_subject_id"] or target["owner_group_id"]
    if (
        target is None
        or target["status"] != "active"
        or target["channel"] != policy["channel"]
        or target["owner_kind"] != policy["recipient_kind"]
        or owner_id != recipient_id
    ):
        return False, "delivery_target_unavailable"
    return True, None


def notification_work_stale_reason(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    work: sqlite3.Row,
    policy: Mapping[str, object] | None,
    valid_targets: Mapping[str, set[tuple[object, ...]]],
) -> str | None:
    """Return the canonical first stale reason for one notification work row."""

    if policy is not None and work["normalized_notification_schedule_hash"] != policy["normalized_notification_schedule_hash"]:
        return "notification_schedule_superseded"
    target_snapshot = (
        work["target_anchor_role"],
        work["application_scope"],
        work["target_scheduled_fact"],
        work["target_at_utc"],
        work["occurrence_key"],
    )
    if policy is not None and target_snapshot not in valid_targets.get(str(work["notification_intent_id"]), set()):
        return "notification_target_changed"
    if work["occurrence_provenance_id"] is not None:
        active = connection.execute(
            """
            SELECT 1 FROM occurrence_provenance
            WHERE occurrence_provenance_id = ? AND management_status = 'active'
              AND actionable = 1
            """,
            (work["occurrence_provenance_id"],),
        ).fetchone()
        if active is None:
            return "notification_occurrence_stale"
    if item["item_type"] == "task":
        from spine.ledger.temporal_bindings import active_follow_binding_current

        if not active_follow_binding_current(connection, item_id=str(item["item_id"])):
            return "notification_temporal_binding_stale"
    if policy is not None and work["delivery_target_id"] != policy["delivery_target_id"]:
        return "notification_routing_changed"
    if policy is None or policy["status"] != "active":
        return "notification_policy_disabled"
    detail = item["detail"]
    terminal = item["status"] != "active"
    terminal = terminal or (item["item_type"] == "event" and detail["event_status"] != "scheduled")
    terminal = terminal or (item["item_type"] == "task" and detail["task_status"] != "open")
    if terminal:
        return "parent_lifecycle_terminal"
    return None


def insert_notification_schedule_policy(connection: sqlite3.Connection, *, normalized: NormalizedNotificationPolicy) -> None:
    value = normalized.value
    target = _object(value["target"], "target")
    late = _object(value["late_handling"], "late_handling")
    recipient_kind = str(value["recipient_kind"])
    connection.execute(
        """
        INSERT INTO notification_policies (
          policy_id, notification_intent_id, intent_created_item_version,
          intent_created_by_command_id, item_id, version, recipient_kind,
          recipient_subject_id, recipient_group_id, channel, delivery_target_id,
          schedule_id, target_anchor_role, application_scope,
          target_occurrence_key, target_occurrence_selector_ref,
          normalized_notification_schedule_hash, late_handling_kind,
          late_grace_seconds, status, created_at_utc, created_by_command_id,
          source_notification_policy_id, disabled_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["notification_policy_id"],
            value["notification_intent_id"],
            int(str(value["intent_created_item_version"])),
            value["intent_created_by_command_id"],
            value["item_id"],
            int(str(value["item_version"])),
            recipient_kind,
            value.get("recipient_subject_id"),
            value.get("recipient_group_id"),
            value["channel"],
            value["delivery_target_id"],
            value["notification_schedule_id"],
            target["anchor_role"],
            target["application_scope"],
            target.get("target_occurrence_key"),
            target.get("target_occurrence_selector_ref"),
            value["normalized_notification_schedule_hash"],
            late["kind"],
            int(str(late["grace_seconds"])) if "grace_seconds" in late else None,
            value["status"],
            value["created_at_utc"],
            value["created_by_command_id"],
            value.get("source_notification_policy_id"),
            value.get("disabled_at_utc"),
        ),
    )
    _insert_schedule(connection, value)


def load_current_notification_policies(
    connection: sqlite3.Connection, *, item_id: str, notification_intent_id: str | None = None
) -> list[dict[str, object]]:
    where = "AND p.notification_intent_id = ?" if notification_intent_id is not None else ""
    params: tuple[object, ...] = (item_id, notification_intent_id) if notification_intent_id else (item_id,)
    rows = connection.execute(
        f"""
        SELECT p.*
        FROM coordination_items AS item
        JOIN notification_policies AS p
          ON p.item_id = item.item_id AND p.version = item.current_version
        WHERE item.item_id = ? {where}
        ORDER BY p.notification_intent_id, p.policy_id
        """,
        params,
    ).fetchall()
    return [_load_policy(connection, row) for row in rows]


def remove_copied_notification_policy(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_version: int,
    notification_intent_id: str,
) -> None:
    """Remove one just-copied successor so an atomic edit can replace it."""

    row = connection.execute(
        """
        SELECT policy_id, schedule_id FROM notification_policies
        WHERE item_id = ? AND version = ? AND notification_intent_id = ?
        """,
        (item_id, item_version, notification_intent_id),
    ).fetchone()
    if row is None:
        raise SpineValidationError("referenced_row_not_found", "copied notification policy is missing")
    connection.execute("DELETE FROM notification_schedule_selectors WHERE schedule_id = ?", (row["schedule_id"],))
    connection.execute("DELETE FROM notification_schedule_offsets WHERE schedule_id = ?", (row["schedule_id"],))
    connection.execute("DELETE FROM notification_schedules WHERE schedule_id = ?", (row["schedule_id"],))
    connection.execute("DELETE FROM notification_policies WHERE policy_id = ?", (row["policy_id"],))


def copy_forward_notification_policies(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    previous_version: int,
    next_version: int,
    created_at_utc: str,
    created_by_command_id: str,
) -> None:
    """Materialize the complete immutable policy set for a successor item version."""

    rows = connection.execute(
        "SELECT * FROM notification_policies WHERE item_id = ? AND version = ? ORDER BY policy_id",
        (item_id, previous_version),
    ).fetchall()
    for row in rows:
        prior = _load_policy(connection, row)
        target = _object(prior["target"], "target")
        recipient_field = "recipient_subject_id" if prior["recipient_kind"] == "subject" else "recipient_group_id"
        authoring_target = {key: target[key] for key in ("anchor_role", "application_scope", "target_occurrence_key") if key in target}
        selector = target.get("target_occurrence_selector")
        normalized = revise_notification_policy(
            prior,
            item_version=str(next_version),
            command_id=created_by_command_id,
            changed_at_utc=created_at_utc,
            recipient_kind=str(prior["recipient_kind"]),
            recipient_id=str(prior[recipient_field]),
            channel=str(prior["channel"]),
            delivery_target_id=str(prior["delivery_target_id"]),
            target=authoring_target,
            schedule=prior["schedule"],
            late_handling=prior["late_handling"],
            status=str(prior["status"]),
            disabled_at_utc=(str(prior["disabled_at_utc"]) if prior.get("disabled_at_utc") is not None else None),
            resolved_target_occurrence_selector=(selector if isinstance(selector, dict) else None),
        )
        if isinstance(selector, dict):
            recurrence_ref = persist_target_occurrence_selector(
                connection,
                occurrence_key=str(target["target_occurrence_key"]),
                selector=selector,
            )
            target_ref = persist_notification_target_selector(
                connection,
                recurrence_selector_ref=recurrence_ref,
                occurrence_key=str(target["target_occurrence_key"]),
                selector=selector,
            )
            normalized.value["target"]["target_occurrence_selector_ref"] = target_ref  # type: ignore[index]
        insert_notification_schedule_policy(connection, normalized=normalized)


def persist_notification_target_selector(
    connection: sqlite3.Connection,
    *,
    recurrence_selector_ref: str,
    occurrence_key: str,
    selector: dict[str, object],
) -> str:
    """Bind notification targeting to an inspectable recurrence selector."""

    target_ref = "notification_target_selector_" + hash_canonical_json(selector)
    connection.execute(
        """
        INSERT OR IGNORE INTO notification_target_occurrence_selectors (
          target_occurrence_selector_ref, recurrence_target_occurrence_selector_ref,
          occurrence_key
        ) VALUES (?, ?, ?)
        """,
        (target_ref, recurrence_selector_ref, occurrence_key),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO notification_target_rule_sources (
          target_occurrence_selector_ref, source_index,
          recurrence_target_occurrence_selector_ref, recurrence_source_index
        )
        SELECT ?, source_index, target_occurrence_selector_ref, source_index
        FROM recurrence_target_rule_sources
        WHERE target_occurrence_selector_ref = ?
        """,
        (target_ref, recurrence_selector_ref),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO notification_target_rule_source_selectors (
          target_occurrence_selector_ref, source_index, selector_kind,
          selector_index, selector_value
        )
        SELECT ?, source_index, selector_kind, selector_index, selector_value
        FROM recurrence_target_rule_source_selectors
        WHERE target_occurrence_selector_ref = ?
        """,
        (target_ref, recurrence_selector_ref),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO notification_target_rdate_sources (
          target_occurrence_selector_ref, source_index,
          recurrence_target_occurrence_selector_ref, recurrence_source_index
        )
        SELECT ?, source_index, target_occurrence_selector_ref, source_index
        FROM recurrence_target_rdate_sources
        WHERE target_occurrence_selector_ref = ?
        """,
        (target_ref, recurrence_selector_ref),
    )
    return target_ref


def _insert_schedule(connection: sqlite3.Connection, policy: dict[str, object]) -> None:
    schedule = _object(policy["schedule"], "schedule")
    cadence = _object(schedule["cadence"], "cadence") if schedule["kind"] == "repeat_window" else None
    once = _object(schedule["at"], "schedule.at") if schedule["kind"] == "once" else None
    connection.execute(
        """
        INSERT INTO notification_schedules (
          schedule_id, policy_id, schedule_kind, once_boundary_kind, once_at_utc,
          stop_inclusive, cadence_kind, interval_seconds, frequency,
          interval_value, seed_local_date, local_time, timezone,
          timezone_database_version, week_start, normalized_notification_schedule_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy["notification_schedule_id"],
            policy["notification_policy_id"],
            schedule["kind"],
            once.get("kind") if once is not None else None,
            once.get("at_utc") if once is not None else None,
            int(bool(schedule["stop_inclusive"])) if "stop_inclusive" in schedule else None,
            cadence.get("kind") if cadence is not None else None,
            int(str(cadence["interval_seconds"])) if cadence is not None and "interval_seconds" in cadence else None,
            cadence.get("frequency") if cadence is not None else None,
            int(str(cadence["interval"])) if cadence is not None and "interval" in cadence else None,
            cadence.get("seed_local_date") if cadence is not None else None,
            cadence.get("local_time") if cadence is not None else None,
            cadence.get("timezone") if cadence is not None else None,
            cadence.get("timezone_database_version") if cadence is not None else None,
            cadence.get("week_start") if cadence is not None else None,
            policy["normalized_notification_schedule_hash"],
        ),
    )
    boundaries: list[tuple[str, dict[str, Any]]] = []
    if schedule["kind"] == "once" and once is not None and once["kind"] == "target_offset":
        boundaries.append(("at", once))
    elif schedule["kind"] == "offsets":
        boundaries.extend(("at", _object(value, "schedule.at")) for value in schedule["at"])
    elif schedule["kind"] == "repeat_window":
        boundaries.extend(
            (
                ("start", _object(schedule["start"], "schedule.start")),
                ("stop", _object(schedule["stop"], "schedule.stop")),
            )
        )
    role_indexes: dict[str, int] = {}
    for role, boundary in boundaries:
        index = role_indexes.get(role, 0)
        role_indexes[role] = index + 1
        connection.execute(
            """
            INSERT INTO notification_schedule_offsets (
              schedule_id, boundary_role, offset_index, boundary_kind, at_utc,
              offset_basis, offset_seconds, offset_days, local_time, timezone,
              timezone_database_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy["notification_schedule_id"],
                role,
                index,
                boundary["kind"],
                boundary.get("at_utc"),
                boundary.get("offset_basis"),
                int(str(boundary["offset_seconds"])) if "offset_seconds" in boundary else None,
                int(str(boundary["offset_days"])) if "offset_days" in boundary else None,
                boundary.get("local_time"),
                boundary.get("timezone"),
                boundary.get("timezone_database_version"),
            ),
        )
    if cadence is not None:
        for selector_kind in ("by_month", "by_month_day", "by_weekday", "by_set_position"):
            for selector_index, selector_value in enumerate(cadence.get(selector_kind, [])):
                connection.execute(
                    """
                    INSERT INTO notification_schedule_selectors (
                      schedule_id, selector_kind, selector_index, selector_value
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (policy["notification_schedule_id"], selector_kind, selector_index, selector_value),
                )


def _load_policy(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    schedule_row = connection.execute(
        "SELECT * FROM notification_schedules WHERE schedule_id = ?",
        (row["schedule_id"],),
    ).fetchone()
    if schedule_row is None:
        raise SpineValidationError("referenced_row_not_found", "notification schedule is missing")
    schedule = _load_schedule(connection, schedule_row)
    target: dict[str, object] = {
        "anchor_role": row["target_anchor_role"],
        "application_scope": row["application_scope"],
    }
    if row["target_occurrence_key"] is not None:
        target["target_occurrence_key"] = row["target_occurrence_key"]
        target["target_occurrence_selector_ref"] = row["target_occurrence_selector_ref"]
        recurrence_ref = connection.execute(
            """
            SELECT recurrence_target_occurrence_selector_ref
            FROM notification_target_occurrence_selectors
            WHERE target_occurrence_selector_ref = ?
            """,
            (row["target_occurrence_selector_ref"],),
        ).fetchone()
        if recurrence_ref is None:
            raise SpineValidationError("referenced_row_not_found", "notification occurrence selector is missing")
        target["target_occurrence_selector"] = load_target_occurrence_selector(
            connection,
            selector_ref=recurrence_ref["recurrence_target_occurrence_selector_ref"],
        )
    late: dict[str, object] = {"kind": row["late_handling_kind"]}
    if row["late_grace_seconds"] is not None:
        late["grace_seconds"] = str(row["late_grace_seconds"])
    result: dict[str, object] = {
        "contract_version": "spine.notification-schedule.contract.v1",
        "normalization_version": "spine.notification-schedule.normalization.v1",
        "canonical_json_version": "spine.canonical-json.v1",
        "notification_intent_id": row["notification_intent_id"],
        "notification_policy_id": row["policy_id"],
        "notification_schedule_id": row["schedule_id"],
        "item_id": row["item_id"],
        "item_version": str(row["version"]),
        "intent_created_item_version": str(row["intent_created_item_version"]),
        "intent_created_by_command_id": row["intent_created_by_command_id"],
        "recipient_kind": row["recipient_kind"],
        "channel": row["channel"],
        "delivery_target_id": row["delivery_target_id"],
        "target": target,
        "schedule": schedule,
        "normalized_notification_schedule_hash": row["normalized_notification_schedule_hash"],
        "late_handling": late,
        "status": row["status"],
        "created_at_utc": row["created_at_utc"],
        "created_by_command_id": row["created_by_command_id"],
    }
    result["recipient_subject_id" if row["recipient_kind"] == "subject" else "recipient_group_id"] = (
        row["recipient_subject_id"] if row["recipient_kind"] == "subject" else row["recipient_group_id"]
    )
    if row["source_notification_policy_id"] is not None:
        result["source_notification_policy_id"] = row["source_notification_policy_id"]
    if row["disabled_at_utc"] is not None:
        result["disabled_at_utc"] = row["disabled_at_utc"]
    return result


def _load_schedule(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    kind = row["schedule_kind"]
    boundaries = [
        dict(value)
        for value in connection.execute(
            "SELECT * FROM notification_schedule_offsets WHERE schedule_id = ? ORDER BY boundary_role, offset_index",
            (row["schedule_id"],),
        )
    ]
    by_role: dict[str, list[dict[str, object]]] = {}
    for boundary in boundaries:
        by_role.setdefault(str(boundary["boundary_role"]), []).append(_boundary_from_row(boundary))
    if kind == "once":
        at = {"kind": "absolute_utc", "at_utc": row["once_at_utc"]} if row["once_boundary_kind"] == "absolute_utc" else by_role["at"][0]
        return {"kind": "once", "at": at}
    if kind == "offsets":
        return {"kind": "offsets", "at": by_role.get("at", [])}
    cadence: dict[str, object] = {"kind": row["cadence_kind"]}
    if row["cadence_kind"] == "fixed_elapsed":
        cadence["interval_seconds"] = str(row["interval_seconds"])
    else:
        cadence.update(
            {
                "frequency": row["frequency"],
                "interval": str(row["interval_value"]),
                "seed_local_date": row["seed_local_date"],
                "local_time": row["local_time"],
                "timezone": row["timezone"],
                "timezone_database_version": row["timezone_database_version"],
            }
        )
        if row["week_start"] is not None:
            cadence["week_start"] = row["week_start"]
        for selector in connection.execute(
            """
            SELECT selector_kind, selector_value
            FROM notification_schedule_selectors
            WHERE schedule_id = ?
            ORDER BY selector_kind, selector_index
            """,
            (row["schedule_id"],),
        ):
            selector_values = cadence.setdefault(str(selector["selector_kind"]), [])
            assert isinstance(selector_values, list)
            selector_values.append(str(selector["selector_value"]))
    return {
        "kind": "repeat_window",
        "start": by_role["start"][0],
        "stop": by_role["stop"][0],
        "stop_inclusive": bool(row["stop_inclusive"]),
        "cadence": cadence,
    }


def _boundary_from_row(row: dict[str, Any]) -> dict[str, object]:
    if row["boundary_kind"] == "absolute_utc":
        return {"kind": "absolute_utc", "at_utc": row["at_utc"]}
    result: dict[str, object] = {"kind": "target_offset", "offset_basis": row["offset_basis"]}
    if row["offset_basis"] == "elapsed":
        result["offset_seconds"] = str(row["offset_seconds"])
    else:
        result.update({"offset_days": str(row["offset_days"]), "local_time": row["local_time"]})
        if row["timezone"] is not None:
            result["timezone"] = row["timezone"]
            result["timezone_database_version"] = row["timezone_database_version"]
    return result


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpineValidationError("invalid_notification_storage", f"{field} must be an object")
    return value
