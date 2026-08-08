"""Bounded scheduler orchestration used by Tickerd reconciliation cycles."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from spine.commands import CommandContext, handle
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.ledger.notifications import load_current_notification_policies
from spine.ledger.recurrence import load_current_recurrence_set


@dataclass(frozen=True)
class SchedulingCycleResult:
    items_scanned: int
    items_repaired: int
    failures: tuple[dict[str, object], ...]


def materialize_notification_horizon(
    connection: sqlite3.Connection,
    *,
    evaluated_at_utc: str,
    horizon_seconds: int,
    max_items: int,
    actor_subject_id: str | None = None,
) -> SchedulingCycleResult:
    """Regenerate required recurrence provenance and materialize one UTC horizon."""

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
    rows = connection.execute(
        """
        SELECT DISTINCT i.item_id, i.current_version
        FROM coordination_items AS i
        JOIN notification_policies AS p
          ON p.item_id = i.item_id AND p.version = i.current_version
        WHERE p.status = 'active'
        ORDER BY i.item_id
        LIMIT ?
        """,
        (max_items,),
    ).fetchall()
    repaired = 0
    failures: list[dict[str, object]] = []
    context = CommandContext(ledger=connection)
    for row in rows:
        item_id = str(row["item_id"])
        version = str(row["current_version"])
        policies = load_current_notification_policies(connection, item_id=item_id)
        recurrence = load_current_recurrence_set(connection, item_id=item_id)
        grace_lookback = 0
        for policy in policies:
            late_handling = _mapping(policy.get("late_handling"), "notification policy late_handling")
            if late_handling.get("kind") == "deliver_within":
                grace_lookback = max(grace_lookback, int(str(late_handling.get("grace_seconds", "0"))))
        eligibility_start = evaluated - timedelta(seconds=grace_lookback)
        if recurrence is not None and any(
            _mapping(value.get("target"), "notification policy target").get("application_scope") != "item" for value in policies
        ):
            source_start, source_end = _recurrence_source_range(
                recurrence,
                policies=policies,
                eligibility_start=eligibility_start,
                eligibility_end=end,
            )
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
        range_start = _utc_text(eligibility_start)
        range_end = _utc_text(end)
        materialize = handle(
            "notification_work.materialize",
            {
                "command_id": _cycle_command_id(
                    "notification_work.materialize",
                    item_id,
                    version,
                    evaluated_at_utc,
                    range_start,
                    range_end,
                ),
                "actor_subject_id": actor,
                "item_id": item_id,
                "target_version": version,
                "materialized_at_utc": evaluated_at_utc,
                "range_start_utc": range_start,
                "range_end_utc": range_end,
                "limit": "1000",
            },
            context,
        )
        if not materialize["ok"]:
            failures.append({"item_id": item_id, "operation": "materialize", "error": materialize["error"]})
            continue
        if materialize["changed"]:
            repaired += 1
    return SchedulingCycleResult(
        items_scanned=len(rows),
        items_repaired=repaired,
        failures=tuple(failures),
    )


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
