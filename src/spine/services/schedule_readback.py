"""Canonical aggregate readback for scheduled items and notification evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.commands.receipts import receipt_from_row
from spine.core.errors import SpineValidationError
from spine.core.schedule import resolve_local_instant
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.temporal_bindings import binding_view

WORK_STATUSES = ("eligible", "in_progress", "succeeded", "failed", "cancelled")
ATTEMPT_STATUSES = ("started", "succeeded", "failed", "rejected")


def build_schedule_readback(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    item_view: Mapping[str, Any],
    include: frozenset[str],
    policies_limit: int,
    work_limit: int,
    attempts_limit: int,
) -> dict[str, Any]:
    """Build one bounded, deterministic view of schedule and delivery evidence."""

    item_id = str(item["item_id"])
    authoring_receipt = _authoring_receipt(connection, item_id)
    schedule_create_facts = _schedule_create_facts(authoring_receipt)
    all_policies = _sequence(item.get("notification_policies"))
    policy_page, policies_truncated = _page(all_policies, policies_limit)

    work_page, work_truncated = _work_rows(connection, item_id, work_limit)
    attempt_page, attempts_truncated = _attempt_rows(connection, item_id, attempts_limit)

    work_counts = _status_counts_query(connection, "work_instances", "status", item_id, WORK_STATUSES)
    attempt_counts = _status_counts_query(
        connection,
        "side_effect_attempts",
        "attempt_status",
        item_id,
        ATTEMPT_STATUSES,
    )
    distinct_opportunity_count = connection.execute(
        """
        SELECT COUNT(DISTINCT notification_opportunity_id)
        FROM work_instances
        WHERE item_id = ? AND notification_opportunity_id IS NOT NULL
        """,
        (item_id,),
    ).fetchone()[0]
    materialization = schedule_create_facts.get("materialization") if schedule_create_facts is not None else None
    lifecycle = _lifecycle(
        item=item,
        policy_count=len(all_policies),
        work_counts=work_counts,
        attempt_counts=attempt_counts,
        distinct_opportunity_count=distinct_opportunity_count,
        materialization=materialization if isinstance(materialization, Mapping) else None,
    )

    result: dict[str, Any] = {
        "ok": True,
        "command": "schedule.show",
        "response_contract": "spine.schedule-show.v1",
        "item": dict(item_view),
        "scheduled_times": _scheduled_times(item, schedule_create_facts),
        "lifecycle": lifecycle,
        "delivery_targets": _delivery_target_views(
            connection,
            item_id=item_id,
            policies=all_policies,
            schedule_create_facts=schedule_create_facts,
        ),
        "included": sorted(include),
    }
    recurrence = load_current_recurrence_set(connection, item_id=item_id)
    if recurrence is not None:
        result["recurrence"] = recurrence
    if authoring_receipt is not None:
        result["authoring_receipt"] = {
            "command_receipt_id": authoring_receipt["command_receipt_id"],
            "command_id": authoring_receipt["command_id"],
            "command": authoring_receipt["command"],
            "effect": authoring_receipt["effect"],
            "semantic_facts_hash": authoring_receipt["semantic_facts_hash"],
            "created_at_utc": authoring_receipt["created_at_utc"],
        }
    if "policies" in include:
        result.update(
            {
                "notification_policies": policy_page,
                "notification_policies_count": str(len(all_policies)),
                "notification_policies_limit": str(policies_limit),
                "notification_policies_truncated": policies_truncated,
            }
        )
    if "work" in include:
        result.update(
            {
                "work_instances": [_work_view(row) for row in work_page],
                "work_instances_count": str(sum(work_counts.values())),
                "work_instances_limit": str(work_limit),
                "work_instances_truncated": work_truncated,
            }
        )
    if "attempts" in include:
        result.update(
            {
                "side_effect_attempts": [_attempt_view(row) for row in attempt_page],
                "side_effect_attempts_count": str(sum(attempt_counts.values())),
                "side_effect_attempts_limit": str(attempts_limit),
                "side_effect_attempts_truncated": attempts_truncated,
            }
        )
    if "relations" in include:
        result["relations"] = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM coordination_item_relations
                WHERE source_item_id = ? OR target_item_id = ?
                ORDER BY relation_type, relation_id
                """,
                (item_id, item_id),
            )
        ]
    if "temporal_bindings" in include:
        binding_rows = connection.execute(
            """
            SELECT temporal_binding_id FROM relative_temporal_bindings
            WHERE source_item_id = ? OR target_item_id = ?
            ORDER BY temporal_binding_id
            """,
            (item_id, item_id),
        ).fetchall()
        result["temporal_bindings"] = [binding_view(connection, str(row["temporal_binding_id"])) for row in binding_rows]
    return result


def _authoring_receipt(connection: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM command_receipts
        WHERE item_id = ?
          AND command IN ('schedule.create', 'schedule.related_task.create', 'event.create', 'task.create')
        ORDER BY
          CASE command WHEN 'schedule.create' THEN 0 ELSE 1 END,
          created_at_utc,
          command_receipt_id
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    return receipt_from_row(row) if row is not None else None


def _schedule_create_facts(receipt: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if receipt is None or receipt.get("command") not in {"schedule.create", "schedule.related_task.create"}:
        return None
    facts = receipt.get("result_identity_facts")
    return facts if isinstance(facts, Mapping) else None


def _work_rows(connection: sqlite3.Connection, item_id: str, limit: int) -> tuple[list[dict[str, Any]], bool]:
    rows = connection.execute(
        """
        SELECT *
        FROM work_instances
        WHERE item_id = ?
        ORDER BY eligible_at_utc, work_instance_id
        LIMIT ?
        """,
        (item_id, limit + 1),
    ).fetchall()
    values = [dict(row) for row in rows]
    return values[:limit], len(values) > limit


def _attempt_rows(connection: sqlite3.Connection, item_id: str, limit: int) -> tuple[list[dict[str, Any]], bool]:
    rows = connection.execute(
        """
        SELECT *
        FROM side_effect_attempts
        WHERE item_id = ? AND work_instance_id IS NOT NULL
        ORDER BY attempted_at_utc, attempt_id
        LIMIT ?
        """,
        (item_id, limit + 1),
    ).fetchall()
    values = [dict(row) for row in rows]
    return values[:limit], len(values) > limit


def _scheduled_times(item: Mapping[str, Any], schedule_create_facts: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    detail = item.get("detail")
    if not isinstance(detail, Mapping):
        return []
    roles = (
        ("event_start", "start_anchor"),
        ("event_end", "end_anchor"),
        ("task_due", "due_anchor"),
        ("task_defer_until", "defer_until_anchor"),
    )
    snapshot = schedule_create_facts.get("scheduled_time") if schedule_create_facts is not None else None
    result: list[dict[str, Any]] = []
    for role, key in roles:
        anchor = detail.get(key)
        if not isinstance(anchor, Mapping):
            continue
        result.append(_scheduled_time_view(role, anchor, snapshot if isinstance(snapshot, Mapping) else None))
    return result


def _scheduled_time_view(role: str, anchor: Mapping[str, Any], snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    result = {"anchor_role": role, **_omit_none(dict(anchor))}
    anchor_id = str(anchor.get("anchor_id", ""))
    if snapshot is not None and snapshot.get("anchor_id") == anchor_id:
        result.update(
            _omit_none(
                {
                    "resolution_state": "resolved",
                    "resolution_source": "authoring_receipt",
                    "resolution_kind": snapshot.get("resolution_kind"),
                    "utc_instant": snapshot.get("utc_instant"),
                    "offset_seconds": snapshot.get("offset_seconds"),
                }
            )
        )
        return result
    if anchor.get("anchor_kind") == "instant_utc":
        result.update({"resolution_state": "resolved", "resolution_source": "stored_anchor"})
        return result
    if anchor.get("anchor_kind") != "local_instant":
        result["resolution_state"] = "not_applicable"
        return result
    local_date = anchor.get("local_date")
    local_time = anchor.get("local_time")
    timezone = anchor.get("timezone")
    timezone_version = anchor.get("timezone_database_version")
    if not all(isinstance(value, str) and value for value in (local_date, local_time, timezone, timezone_version)):
        raise SpineValidationError("invalid_schedule_readback", f"{role} local instant is incomplete")
    try:
        resolution = resolve_local_instant(
            f"{local_date}T{local_time}",
            timezone=str(timezone),
            timezone_database_version=str(timezone_version),
        )
    except SpineValidationError as exc:
        if exc.code != "environment_failure:timezone_database_version":
            raise
        result.update(
            {
                "resolution_state": "unavailable",
                "resolution_source": "pinned_timezone_database",
                "resolution_error_code": "timezone_database_version_unavailable",
            }
        )
        return result
    if resolution is None:
        result.update(
            {
                "resolution_state": "unavailable",
                "resolution_source": "pinned_timezone_database",
                "resolution_error_code": "nonexistent_local_time",
            }
        )
        return result
    result.update(
        {
            "resolution_state": "resolved",
            "resolution_source": "pinned_timezone_database",
            "resolution_kind": resolution.resolution_kind,
            "utc_instant": resolution.utc_instant,
            "offset_seconds": resolution.offset_seconds,
        }
    )
    return result


def _lifecycle(
    *,
    item: Mapping[str, Any],
    policy_count: int,
    work_counts: Mapping[str, int],
    attempt_counts: Mapping[str, int],
    distinct_opportunity_count: int,
    materialization: Mapping[str, Any] | None,
) -> dict[str, Any]:
    work_total = sum(work_counts.values())
    attempt_total = sum(attempt_counts.values())
    receipt_opportunity_count = _decimal_count(materialization, "opportunity_count")
    opportunity_count = max(distinct_opportunity_count, receipt_opportunity_count)
    materialization_state = materialization.get("state") if materialization is not None else None
    materialization_mode = materialization.get("mode") if materialization is not None else None
    if opportunity_count > 0:
        opportunity_state = "expanded"
    elif materialization_state == "completed_zero_selected":
        opportunity_state = "expanded_zero_selected"
    elif materialization_mode == "none":
        opportunity_state = "not_requested"
    else:
        opportunity_state = "evidence_not_persisted"
    if work_total > 0:
        work_state = "materialized"
    elif materialization_state == "completed_zero_selected":
        work_state = "completed_zero_selected"
    elif materialization_mode == "none":
        work_state = "not_requested"
    else:
        work_state = "none"
    return {
        "authored": {
            "state": "committed",
            "item_version": str(item["current_version"]),
            "policy_count": str(policy_count),
        },
        "opportunities": {"state": opportunity_state, "count": str(opportunity_count)},
        "work": {
            "state": work_state,
            "count": str(work_total),
            "status_counts": {key: str(value) for key, value in work_counts.items()},
        },
        "delivery": {
            "attempt_state": "attempted" if attempt_total else "not_attempted",
            "outcome_state": _delivery_outcome(attempt_counts),
            "attempt_count": str(attempt_total),
            "status_counts": {key: str(value) for key, value in attempt_counts.items()},
        },
    }


def _delivery_outcome(counts: Mapping[str, int]) -> str:
    populated = {status for status, count in counts.items() if count > 0}
    if not populated:
        return "none"
    if populated == {"started"}:
        return "pending"
    terminal = populated - {"started"}
    if "started" not in populated and len(terminal) == 1:
        return next(iter(terminal))
    return "mixed"


def _delivery_target_views(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    policies: Sequence[Mapping[str, Any]],
    schedule_create_facts: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    target_ids = {str(policy["delivery_target_id"]) for policy in policies if policy.get("delivery_target_id") is not None}
    target_ids.update(
        str(row["delivery_target_id"])
        for row in connection.execute(
            """
            SELECT DISTINCT delivery_target_id
            FROM work_instances
            WHERE item_id = ? AND delivery_target_id IS NOT NULL
            ORDER BY delivery_target_id
            """,
            (item_id,),
        )
    )
    authored = schedule_create_facts.get("delivery") if schedule_create_facts is not None else None
    result: list[dict[str, Any]] = []
    for target_id in sorted(target_ids):
        row = connection.execute(
            "SELECT * FROM delivery_targets WHERE delivery_target_id = ?",
            (target_id,),
        ).fetchone()
        if row is None:
            raise SpineValidationError("invalid_schedule_readback", f"delivery target is missing: {target_id}")
        current = _omit_none(dict(row))
        value: dict[str, Any] = {"delivery_target_id": target_id, "current_snapshot": current}
        if isinstance(authored, Mapping) and authored.get("delivery_target_id") == target_id:
            authored_snapshot = dict(authored)
            value["authored_snapshot"] = authored_snapshot
            comparable = ("delivery_target_id", "channel", "adapter_name", "target_ref")
            value["routing_facts_match_authored"] = all(current.get(key) == authored_snapshot.get(key) for key in comparable)
        result.append(value)
    return result


def _work_view(row: Mapping[str, Any]) -> dict[str, Any]:
    result = _omit_none(
        {
            key: row.get(key)
            for key in (
                "work_instance_id",
                "item_id",
                "notification_policy_id",
                "notification_intent_id",
                "notification_opportunity_id",
                "occurrence_provenance_id",
                "target_anchor_role",
                "application_scope",
                "target_scheduled_fact",
                "target_at_utc",
                "occurrence_key",
                "delivery_target_id",
                "work_kind",
                "eligible_at_utc",
                "status",
                "next_attempt_at_utc",
                "reason_code",
                "created_at_utc",
                "updated_at_utc",
            )
        }
    )
    result["item_version"] = str(row["item_version"])
    result["attempt_count"] = str(row["attempt_count"])
    if row.get("notification_policy_item_version") is not None:
        result["notification_policy_item_version"] = str(row["notification_policy_item_version"])
    return result


def _attempt_view(row: Mapping[str, Any]) -> dict[str, Any]:
    return _omit_none(
        {
            key: row.get(key)
            for key in (
                "attempt_id",
                "work_instance_id",
                "item_id",
                "adapter_name",
                "idempotency_key",
                "attempt_status",
                "provider_ref",
                "request_payload_hash",
                "request_hash",
                "response_hash",
                "reason_code",
                "attempted_at_utc",
                "completed_at_utc",
            )
        }
    )


def _status_counts_query(
    connection: sqlite3.Connection,
    table: str,
    field: str,
    item_id: str,
    statuses: Sequence[str],
) -> dict[str, int]:
    counts = {status: 0 for status in statuses}
    work_attempt_filter = " AND work_instance_id IS NOT NULL" if table == "side_effect_attempts" else ""
    rows = connection.execute(
        f"SELECT {field}, COUNT(*) AS row_count FROM {table} WHERE item_id = ?{work_attempt_filter} GROUP BY {field}",
        (item_id,),
    )
    for row in rows:
        status = str(row[field])
        if status not in counts:
            raise SpineValidationError("invalid_schedule_readback", f"unsupported {field}: {status}")
        counts[status] = int(row["row_count"])
    return counts


def _decimal_count(value: Mapping[str, Any] | None, field: str) -> int:
    if value is None or value.get(field) is None:
        return 0
    candidate = value[field]
    if not isinstance(candidate, str) or not candidate.isdigit():
        raise SpineValidationError("invalid_schedule_readback", f"stored {field} is invalid")
    return int(candidate)


def _page(values: Sequence[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    return list(values[:limit]), len(values) > limit


def _sequence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _omit_none(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
