"""Bounded scheduler orchestration used by Tickerd reconciliation cycles."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from spine.commands import CommandContext, handle
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notifications import expand_notification_policy
from spine.core.occurrences import expand_recurrence_set
from spine.core.schedule import resolve_local_instant
from spine.ledger.notifications import (
    load_current_notification_policies,
    notification_policy_actionability,
    notification_work_stale_reason,
)
from spine.ledger.recurrence import load_current_recurrence_set

_SCHEDULER_SCAN_MINIMUM = 100
_SCHEDULER_SCAN_MULTIPLIER = 10
_SCHEDULER_SCAN_MAXIMUM = 10_000
_SCHEDULER_ROTATION_SECONDS = 60
_CANDIDATE_ITEMS_CTE = """
    WITH candidate_items AS (
      SELECT p.item_id
      FROM notification_policies AS p
      JOIN coordination_items AS i
        ON i.item_id = p.item_id AND i.current_version = p.version
      WHERE p.status = 'active'
      UNION
      SELECT w.item_id
      FROM work_instances AS w
      WHERE w.work_kind = 'notification_reminder'
        AND w.status = 'eligible'
        AND w.attempt_count = 0
        AND NOT EXISTS (
          SELECT 1 FROM side_effect_attempts AS attempt
          WHERE attempt.work_instance_id = w.work_instance_id
        )
    )
"""


@dataclass(frozen=True)
class SchedulingCycleResult:
    items_scanned: int
    items_repaired: int
    failures: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _NotificationWorkPlan:
    item_id: str
    version: str
    range_start: str
    range_end: str
    recurrence_source_range: tuple[str, str] | None
    needs_provenance: bool
    needs_materialization: bool

    @property
    def dispatchable(self) -> bool:
        return self.needs_provenance or self.needs_materialization


def materialize_notification_horizon(
    connection: sqlite3.Connection,
    *,
    evaluated_at_utc: str,
    horizon_seconds: int,
    max_items: int,
    actor_subject_id: str | None = None,
) -> SchedulingCycleResult:
    """Plan and apply required recurrence provenance and notification work."""

    if horizon_seconds < 1 or horizon_seconds > 31_622_400:
        raise SpineValidationError(
            "invalid_materialization_horizon_seconds",
            "materialization horizon must be between 1 second and 366 days",
        )
    if max_items < 1:
        raise SpineValidationError("invalid_scheduler_max_items", "scheduler max items must be at least 1")
    evaluated = _utc(evaluated_at_utc)
    end = evaluated + timedelta(seconds=horizon_seconds)
    actor = actor_subject_id or _scheduler_actor(connection)
    if actor is None:
        return SchedulingCycleResult(
            items_scanned=0,
            items_repaired=0,
            failures=({"reason_code": "scheduler_actor_unavailable"},),
        )
    binding_failures, bindings_repaired, bindings_scanned = _reconcile_temporal_bindings(
        connection,
        evaluated_at_utc=evaluated_at_utc,
        actor_subject_id=actor,
        max_bindings=max_items,
    )
    rows = _scheduler_candidate_rows(connection, evaluated=evaluated, max_items=max_items)
    repaired = bindings_repaired
    failures: list[dict[str, object]] = list(binding_failures)
    context = CommandContext(ledger=connection, transport_metadata={"automatic_scheduler": True})
    scanned = 0
    dispatched = 0
    for row in rows:
        if dispatched >= max_items:
            break
        scanned += 1
        item_id = str(row["item_id"])
        version = str(row["current_version"])
        try:
            plan = _plan_notification_work(
                connection,
                context=context,
                item_id=item_id,
                version=version,
                evaluated_at_utc=evaluated_at_utc,
                evaluated=evaluated,
                eligibility_end=end,
            )
        except SpineValidationError as exc:
            failures.append(
                {
                    "item_id": item_id,
                    "operation": "planning",
                    "error": {"code": exc.code, "message": exc.message},
                }
            )
            continue
        if not plan.dispatchable:
            continue
        dispatched += 1
        item_repaired = False
        if plan.needs_provenance:
            assert plan.recurrence_source_range is not None
            source_start, source_end = plan.recurrence_source_range
            recurrence = load_current_recurrence_set(connection, item_id=item_id)
            if recurrence is None:
                failures.append({"item_id": item_id, "operation": "provenance", "reason_code": "recurrence_not_configured"})
                continue
            provenance_request = {
                "command_id": _cycle_command_id(
                    "occurrence_provenance.regenerate",
                    item_id,
                    version,
                    evaluated_at_utc,
                    source_start,
                    source_end,
                ),
                "actor_subject_id": actor,
                "item_id": item_id,
                "target_version": version,
                "recurrence_set_id": recurrence["recurrence_set_id"],
                "recurrence_revision_id": recurrence["recurrence_revision_id"],
                "regenerated_at_utc": evaluated_at_utc,
                "consumer": "notification_schedule",
                "range_basis": "expressed_time",
                "range_start": source_start,
                "range_end": source_end,
            }
            provenance = handle("occurrence_provenance.regenerate", provenance_request, context)
            if not provenance["ok"]:
                failures.append({"item_id": item_id, "operation": "provenance", "error": provenance["error"]})
                continue
            item_repaired = bool(provenance["changed"])
            try:
                plan = _plan_notification_work(
                    connection,
                    context=context,
                    item_id=item_id,
                    version=version,
                    evaluated_at_utc=evaluated_at_utc,
                    evaluated=evaluated,
                    eligibility_end=end,
                )
            except SpineValidationError as exc:
                failures.append(
                    {
                        "item_id": item_id,
                        "operation": "planning_after_provenance",
                        "error": {"code": exc.code, "message": exc.message},
                    }
                )
                if item_repaired:
                    repaired += 1
                continue
        if not plan.needs_materialization:
            if item_repaired:
                repaired += 1
            continue
        materialize = handle(
            "notification_work.materialize",
            {
                "command_id": _cycle_command_id(
                    "notification_work.materialize",
                    item_id,
                    version,
                    evaluated_at_utc,
                    plan.range_start,
                    plan.range_end,
                ),
                "actor_subject_id": actor,
                "item_id": item_id,
                "target_version": version,
                "materialized_at_utc": evaluated_at_utc,
                "range_start_utc": plan.range_start,
                "range_end_utc": plan.range_end,
                "limit": "1000",
            },
            context,
        )
        if not materialize["ok"]:
            failures.append({"item_id": item_id, "operation": "materialize", "error": materialize["error"]})
            continue
        item_repaired = item_repaired or bool(materialize["changed"])
        if item_repaired:
            repaired += 1
    return SchedulingCycleResult(
        items_scanned=scanned + bindings_scanned,
        items_repaired=repaired,
        failures=tuple(failures),
    )


def _scheduler_candidate_rows(
    connection: sqlite3.Connection,
    *,
    evaluated: datetime,
    max_items: int,
) -> list[sqlite3.Row]:
    total = int(
        connection.execute(
            _CANDIDATE_ITEMS_CTE + "SELECT COUNT(*) FROM candidate_items",
        ).fetchone()[0]
    )
    if total == 0:
        return []
    scan_budget = min(
        total,
        max(
            _SCHEDULER_SCAN_MINIMUM,
            min(max_items * _SCHEDULER_SCAN_MULTIPLIER, _SCHEDULER_SCAN_MAXIMUM),
        ),
    )
    cycle_slot = int(evaluated.timestamp()) // _SCHEDULER_ROTATION_SECONDS
    offset = (cycle_slot * scan_budget) % total
    query = (
        _CANDIDATE_ITEMS_CTE
        + """
        SELECT i.item_id, i.current_version
        FROM candidate_items AS candidate
        JOIN coordination_items AS i ON i.item_id = candidate.item_id
        ORDER BY i.item_id
        LIMIT ? OFFSET ?
        """
    )
    rows = connection.execute(query, (scan_budget, offset)).fetchall()
    remaining = scan_budget - len(rows)
    if remaining:
        rows.extend(connection.execute(query, (remaining, 0)).fetchall())
    return rows


def _plan_notification_work(
    connection: sqlite3.Connection,
    *,
    context: CommandContext,
    item_id: str,
    version: str,
    evaluated_at_utc: str,
    evaluated: datetime,
    eligibility_end: datetime,
) -> _NotificationWorkPlan:
    policies = load_current_notification_policies(connection, item_id=item_id)
    active_policies = [value for value in policies if value.get("status") == "active"]
    grace_lookback = max((_policy_grace_seconds(value) for value in active_policies), default=0)
    eligibility_start = evaluated - timedelta(seconds=grace_lookback)
    range_start = _utc_text(eligibility_start)
    range_end = _utc_text(eligibility_end)
    item = _scheduler_item(context, item_id=item_id)
    recurrence = load_current_recurrence_set(connection, item_id=item_id)
    cancellable = _cancellable_notification_work(
        connection,
        item_id=item_id,
        range_start=range_start,
        range_end=range_end,
    )

    recurrence_policies = [
        value
        for value in active_policies
        if _mapping(value.get("target"), "notification policy target").get("application_scope") != "item"
    ]
    source_range: tuple[str, str] | None = None
    if recurrence_policies:
        if recurrence is None:
            raise SpineValidationError("recurrence_not_configured", "recurrence-bound notification has no recurrence set")
        source_range = _recurrence_source_range(
            recurrence,
            policies=recurrence_policies,
            eligibility_start=eligibility_start,
            eligibility_end=eligibility_end,
        )
        provisional, raw_keys = _provisional_recurrence_opportunities(
            connection,
            item=item,
            recurrence=recurrence,
            policies=recurrence_policies,
            evaluated_at_utc=evaluated_at_utc,
            range_start=range_start,
            range_end=range_end,
            source_range=source_range,
        )
        required_keys = {
            str(value["occurrence_key"])
            for value in provisional
            if value.get("actionable") and _opportunity_has_no_work(connection, value)
        }
        if cancellable:
            required_keys.update(raw_keys)
        if required_keys - _active_notification_provenance_keys(connection, item_id=item_id, recurrence=recurrence):
            return _NotificationWorkPlan(
                item_id=item_id,
                version=version,
                range_start=range_start,
                range_end=range_end,
                recurrence_source_range=source_range,
                needs_provenance=True,
                needs_materialization=False,
            )

    opportunities = _read_notification_opportunities(
        context,
        item_id=item_id,
        evaluated_at_utc=evaluated_at_utc,
        range_start=range_start,
        range_end=range_end,
    )
    missing_work = any(value.get("actionable") and _opportunity_has_no_work(connection, value) for value in opportunities)
    policies_by_policy_id: dict[str, Mapping[str, object]] = {}
    for value in policies:
        policies_by_policy_id[str(value["notification_policy_id"])] = value
        source_policy_id = value.get("source_notification_policy_id")
        if source_policy_id is not None:
            policies_by_policy_id[str(source_policy_id)] = value
    valid_targets = _scheduler_target_snapshots(connection, item=item, policies=policies, recurrence=recurrence)
    stale_work = any(
        notification_work_stale_reason(
            connection,
            item=item,
            work=work,
            policy=policies_by_policy_id.get(str(work["notification_policy_id"])),
            valid_targets=valid_targets,
        )
        is not None
        for work in cancellable
    )
    return _NotificationWorkPlan(
        item_id=item_id,
        version=version,
        range_start=range_start,
        range_end=range_end,
        recurrence_source_range=source_range,
        needs_provenance=False,
        needs_materialization=missing_work or stale_work,
    )


def _scheduler_item(context: CommandContext, *, item_id: str) -> dict[str, Any]:
    shown = handle("item.show", {"item_id": item_id}, context)
    if not shown.get("ok"):
        error = shown.get("error", {})
        raise SpineValidationError(str(error.get("code", "item_not_found")), str(error.get("message", "item is unavailable")))
    item_type = str(shown["item_type"])
    detail_key = "event_detail" if item_type == "event" else "task_detail"
    detail = shown.get(detail_key)
    if not isinstance(detail, Mapping):
        raise SpineValidationError("invalid_item_detail", "scheduled item detail is unavailable")
    return {
        "item_id": shown["item_id"],
        "item_type": item_type,
        "current_version": shown["current_version"],
        "status": shown["status"],
        "detail": dict(detail),
    }


def _policy_grace_seconds(policy: Mapping[str, object]) -> int:
    late = _mapping(policy.get("late_handling"), "notification policy late_handling")
    return int(str(late.get("grace_seconds", "0"))) if late.get("kind") == "deliver_within" else 0


def _cancellable_notification_work(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    range_start: str,
    range_end: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM work_instances AS work
        WHERE work.item_id = ?
          AND work.work_kind = 'notification_reminder'
          AND work.status = 'eligible'
          AND work.attempt_count = 0
          AND work.eligible_at_utc >= ? AND work.eligible_at_utc < ?
          AND NOT EXISTS (
            SELECT 1 FROM side_effect_attempts AS attempt
            WHERE attempt.work_instance_id = work.work_instance_id
          )
        ORDER BY work.work_instance_id
        """,
        (item_id, range_start, range_end),
    ).fetchall()


def _read_notification_opportunities(
    context: CommandContext,
    *,
    item_id: str,
    evaluated_at_utc: str,
    range_start: str,
    range_end: str,
) -> list[dict[str, object]]:
    response = handle(
        "notification.opportunities",
        {
            "item_id": item_id,
            "evaluated_at_utc": evaluated_at_utc,
            "range_start_utc": range_start,
            "range_end_utc": range_end,
            "limit": "1000",
        },
        context,
    )
    if not response.get("ok"):
        error = response.get("error", {})
        raise SpineValidationError(
            str(error.get("code", "notification_opportunity_planning_failed")),
            str(error.get("message", "notification opportunities could not be planned")),
        )
    values = response.get("opportunities")
    if not isinstance(values, list):
        raise SpineValidationError("invalid_notification_opportunities", "notification opportunities must be an array")
    return [dict(value) for value in values if isinstance(value, Mapping)]


def _opportunity_has_no_work(connection: sqlite3.Connection, opportunity: Mapping[str, object]) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM work_instances
            WHERE notification_opportunity_id = ? AND delivery_target_id = ?
            """,
            (opportunity["notification_opportunity_id"], opportunity["delivery_target_id"]),
        ).fetchone()
        is None
    )


def _active_notification_provenance_keys(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    recurrence: Mapping[str, object],
) -> set[str]:
    return {
        str(row["occurrence_key"])
        for row in connection.execute(
            """
            SELECT DISTINCT occurrence_key
            FROM occurrence_provenance
            WHERE item_id = ? AND recurrence_revision_id = ?
              AND consumer = 'notification_schedule' AND management_status = 'active'
            """,
            (item_id, recurrence["recurrence_revision_id"]),
        )
    }


def _provisional_recurrence_opportunities(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    recurrence: Mapping[str, object],
    policies: Sequence[Mapping[str, object]],
    evaluated_at_utc: str,
    range_start: str,
    range_end: str,
    source_range: tuple[str, str],
) -> tuple[list[dict[str, object]], set[str]]:
    expanded = expand_recurrence_set(
        recurrence,
        range_start=source_range[0],
        range_end=source_range[1],
        range_basis="expressed_time",
    )
    all_targets = [_provisional_occurrence_target(item=item, recurrence=recurrence, occurrence=value) for value in expanded.occurrences]
    opportunities: list[dict[str, object]] = []
    raw_keys: set[str] = set()
    for policy in policies:
        target = _mapping(policy.get("target"), "notification policy target")
        selected = all_targets
        if target.get("application_scope") == "selected_occurrence":
            selected = [value for value in all_targets if value.get("occurrence_key") == target.get("target_occurrence_key")]
        raw_keys.update(str(value["occurrence_key"]) for value in selected)
        actionable, reason = notification_policy_actionability(connection, item=item, policy=policy)
        generated = expand_notification_policy(
            policy,
            targets=selected,
            evaluated_at_utc=evaluated_at_utc,
            range_start_utc=range_start,
            range_end_utc=range_end,
            policy_actionable=actionable,
            non_actionable_reason=reason,
            candidate_limit=1001,
        )
        opportunities.extend(dict(value) for value in generated.opportunities)
    return opportunities, raw_keys


def _provisional_occurrence_target(
    *,
    item: Mapping[str, Any],
    recurrence: Mapping[str, object],
    occurrence: Mapping[str, object],
) -> dict[str, object]:
    expressed = str(occurrence["expressed_scheduled_fact"])
    lifecycle = str(occurrence["lifecycle"])
    detail = _mapping(item.get("detail"), "item detail")
    actionable = item["status"] == "active" and lifecycle == "active"
    actionable = actionable and (
        (item["item_type"] == "event" and detail.get("event_status") == "scheduled")
        or (item["item_type"] == "task" and detail.get("task_status") == "open")
    )
    value: dict[str, object] = {
        "target_scheduled_fact": expressed,
        "target_occurrence_selector": occurrence["target_occurrence_selector"],
        "occurrence_id": occurrence["occurrence_id"],
        "occurrence_key": occurrence["occurrence_key"],
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "lifecycle": "scheduled" if lifecycle == "active" else lifecycle,
        "actionable": actionable,
    }
    basis = str(recurrence["time_basis"])
    if basis == "instant_utc":
        value["target_utc_instant"] = expressed
    elif basis == "local_instant":
        resolution = resolve_local_instant(
            expressed,
            timezone=str(recurrence["timezone"]),
            timezone_database_version=str(recurrence["timezone_database_version"]),
        )
        if resolution is not None:
            value["target_utc_instant"] = resolution.utc_instant
        else:
            value["actionable"] = False
    if recurrence.get("timezone") is not None:
        value["timezone"] = recurrence["timezone"]
        value["timezone_database_version"] = recurrence["timezone_database_version"]
        value["target_local_date"] = expressed.split("T", 1)[0]
    return value


def _scheduler_target_snapshots(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    policies: Sequence[Mapping[str, object]],
    recurrence: Mapping[str, object] | None,
) -> dict[str, set[tuple[object, ...]]]:
    result: dict[str, set[tuple[object, ...]]] = {}
    detail = _mapping(item.get("detail"), "item detail")
    for policy in policies:
        target = _mapping(policy.get("target"), "notification policy target")
        scope = str(target["application_scope"])
        snapshots: set[tuple[object, ...]] = set()
        if scope == "item":
            anchor = detail.get("start_anchor" if item["item_type"] == "event" else "due_anchor")
            if isinstance(anchor, Mapping):
                value = _scheduler_target_from_anchor(anchor)
                snapshots.add(
                    (
                        target["anchor_role"],
                        scope,
                        value["target_scheduled_fact"],
                        value.get("target_utc_instant"),
                        None,
                    )
                )
        elif recurrence is not None:
            params: list[object] = [item["item_id"], recurrence["recurrence_revision_id"]]
            selected = ""
            if scope == "selected_occurrence":
                selected = "AND occurrence_key = ?"
                params.append(target["target_occurrence_key"])
            for row in connection.execute(
                f"""
                SELECT expressed_scheduled_fact, timezone_utc_instant, occurrence_key
                FROM occurrence_provenance
                WHERE item_id = ? AND recurrence_revision_id = ?
                  AND consumer = 'notification_schedule' AND management_status = 'active'
                  {selected}
                """,
                tuple(params),
            ):
                target_at = row["timezone_utc_instant"]
                if target_at is None and recurrence["time_basis"] == "instant_utc":
                    target_at = row["expressed_scheduled_fact"]
                snapshots.add(
                    (
                        target["anchor_role"],
                        scope,
                        row["expressed_scheduled_fact"],
                        target_at,
                        row["occurrence_key"],
                    )
                )
        result[str(policy["notification_intent_id"])] = snapshots
    return result


def _scheduler_target_from_anchor(anchor: Mapping[str, object]) -> dict[str, object]:
    kind = str(anchor["anchor_kind"])
    if kind == "instant_utc":
        value = str(anchor["utc_instant"])
        return {"target_scheduled_fact": value, "target_utc_instant": value}
    local_date = str(anchor["local_date"])
    result: dict[str, object] = {"target_scheduled_fact": local_date}
    if kind == "local_instant":
        local_time = str(anchor["local_time"])
        if len(local_time) == 5:
            local_time += ":00"
        scheduled = f"{local_date}T{local_time}"
        resolution = resolve_local_instant(
            scheduled,
            timezone=str(anchor["timezone"]),
            timezone_database_version=str(anchor["timezone_database_version"]),
        )
        if resolution is None:
            raise SpineValidationError("semantic_conflict", "notification target is a nonexistent local instant")
        result["target_scheduled_fact"] = scheduled
        result["target_utc_instant"] = resolution.utc_instant
    return result


def _reconcile_temporal_bindings(
    connection: sqlite3.Connection,
    *,
    evaluated_at_utc: str,
    actor_subject_id: str,
    max_bindings: int,
) -> tuple[tuple[dict[str, object], ...], int, int]:
    context = CommandContext(ledger=connection)
    listed = handle(
        "schedule.binding.list",
        {
            "contract_version": "spine.schedule-binding-list.v1",
            "binding_mode": "follow_source",
            "binding_status": "active",
            "binding_states": [
                "stale",
                "source_terminal",
                "source_unresolved",
                "target_diverged",
                "target_terminal",
                "relationship_inactive",
            ],
            "limit": str(min(max_bindings, 1000)),
            "bounded": True,
        },
        context,
    )
    if not listed.get("ok"):
        return ({"operation": "binding_list", "error": listed.get("error", {})},), 0, 0
    failures: list[dict[str, object]] = []
    repaired = 0
    bindings = listed.get("bindings", [])
    if not isinstance(bindings, list):
        return ({"operation": "binding_list", "reason_code": "binding_list_rows_invalid"},), 0, 0
    for raw in bindings:
        if not isinstance(raw, Mapping) or not raw.get("automatic_reconcile_eligible"):
            continue
        inputs = raw.get("reconcile_inputs")
        if not isinstance(inputs, Mapping):
            failures.append({"operation": "binding_reconcile", "reason_code": "binding_reconcile_inputs_missing"})
            continue
        request = {
            "contract_version": "spine.schedule-binding-reconcile.v1",
            "command_id": "scheduler_binding_"
            + hash_canonical_json(
                {
                    "derivation_version": "spine.scheduler-binding-reconcile-command-id.v1",
                    "temporal_binding_id": inputs["temporal_binding_id"],
                    "target_temporal_binding_revision_id": inputs["target_temporal_binding_revision_id"],
                    "expected_binding_state": inputs["expected_binding_state"],
                    "evaluated_at_utc": evaluated_at_utc,
                }
            ),
            "actor_subject_id": actor_subject_id,
            "reconciled_at_utc": evaluated_at_utc,
            "materialization": {"mode": "none"},
            **dict(inputs),
        }
        result = handle("schedule.binding.reconcile", request, context)
        if not result.get("ok"):
            failures.append(
                {"temporal_binding_id": inputs["temporal_binding_id"], "operation": "binding_reconcile", "error": result.get("error", {})}
            )
        elif result.get("truth_changed") or result.get("work_changed"):
            repaired += 1
    return tuple(failures), repaired, len(bindings)


def _recurrence_source_range(
    recurrence: Mapping[str, object],
    *,
    policies: list[dict[str, object]],
    eligibility_start: datetime,
    eligibility_end: datetime,
) -> tuple[str, str]:
    minimum_offset = 0
    maximum_offset = 0
    for policy in policies:
        target = _mapping(policy.get("target"), "notification policy target")
        if target.get("application_scope") == "item":
            continue
        offsets = _policy_offsets(policy)
        minimum_offset = min(minimum_offset, *offsets)
        maximum_offset = max(maximum_offset, *offsets)
    conservative = timedelta(days=2)
    target_start = eligibility_start - timedelta(seconds=maximum_offset) - conservative
    target_end = eligibility_end - timedelta(seconds=minimum_offset) + conservative
    basis = str(recurrence["time_basis"])
    if basis == "instant_utc":
        return _utc_text(target_start), _utc_text(target_end)
    zone = ZoneInfo(str(recurrence["timezone"]))
    local_start = target_start.astimezone(zone)
    local_end = target_end.astimezone(zone)
    if basis == "local_date":
        return local_start.date().isoformat(), (local_end.date() + timedelta(days=1)).isoformat()
    return (
        local_start.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S"),
        (local_end.replace(tzinfo=None) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _policy_offsets(policy: Mapping[str, object]) -> list[int]:
    schedule = _mapping(policy.get("schedule"), "notification policy schedule")
    boundaries: list[Mapping[str, object]] = []
    if schedule["kind"] == "once":
        boundaries = [_mapping(schedule.get("at"), "notification schedule boundary")]
    elif schedule["kind"] == "offsets":
        raw_boundaries = schedule.get("at")
        if not isinstance(raw_boundaries, list):
            raise SpineValidationError("invalid_notification_policy_row", "notification offsets must be an array")
        boundaries = [_mapping(value, "notification schedule boundary") for value in raw_boundaries]
    else:
        boundaries = [
            _mapping(schedule.get("start"), "notification schedule start"),
            _mapping(schedule.get("stop"), "notification schedule stop"),
        ]
    values = [0]
    for boundary in boundaries:
        if boundary["kind"] != "target_offset":
            continue
        if boundary["offset_basis"] == "elapsed":
            values.append(int(str(boundary["offset_seconds"])))
        else:
            values.append(int(str(boundary["offset_days"])) * 86_400)
    return values


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SpineValidationError("invalid_notification_policy_row", f"{field} must be an object")
    return value


def _scheduler_actor(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT subject_id FROM subjects WHERE status = 'active' ORDER BY subject_kind = 'agent' DESC, subject_id LIMIT 1"
    ).fetchone()
    return None if row is None else str(row["subject_id"])


def _cycle_command_id(
    operation: str,
    item_id: str,
    version: str,
    evaluated_at_utc: str,
    range_start: str,
    range_end: str,
) -> str:
    return "scheduler_command_" + str(
        hash_canonical_json(
            {
                "derivation_version": "spine.scheduler-command-id.v1",
                "operation": operation,
                "item_id": item_id,
                "item_version": version,
                "evaluated_at_utc": evaluated_at_utc,
                "range_start": range_start,
                "range_end": range_end,
            }
        )
    )


def _utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
