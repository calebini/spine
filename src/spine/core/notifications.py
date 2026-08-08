"""Canonical notification-policy normalization and bounded opportunity expansion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.schedule import (
    expand_rule,
    normalize_rule,
    parse_scheduled_fact,
    resolve_local_instant,
    validate_timezone_context,
)

NOTIFICATION_CONTRACT_VERSION = "spine.notification-schedule.contract.v1"
NOTIFICATION_NORMALIZATION_VERSION = "spine.notification-schedule.normalization.v1"
CANONICAL_JSON_VERSION = "spine.canonical-json.v1"
NOTIFICATION_AUTHORING_VERSION = "spine.notification-schedule-authoring.v1"


@dataclass(frozen=True)
class NormalizedNotificationPolicy:
    value: dict[str, object]
    intent_id_preimage: dict[str, object]
    schedule_hash_preimage: dict[str, object]
    schedule_id_preimage: dict[str, object]
    policy_id_preimage: dict[str, object]


@dataclass(frozen=True)
class ExpandedNotificationOpportunities:
    opportunities: tuple[dict[str, object], ...]
    diagnostics: tuple[dict[str, object], ...]


def notification_id(prefix: str, derivation_version: str, fields: dict[str, object]) -> tuple[str, dict[str, object]]:
    preimage = {
        "derivation_version": derivation_version,
        "contract_version": NOTIFICATION_CONTRACT_VERSION,
        "normalization_version": NOTIFICATION_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        **fields,
    }
    return f"{prefix}_{hash_canonical_json(preimage)}", preimage


def normalize_notification_policy(
    authoring: object,
    *,
    item_id: str,
    item_version: str,
    command_id: str,
    created_at_utc: str,
    recipient_kind: str,
    recipient_id: str,
    channel: str,
    delivery_target_id: str,
    resolved_target_occurrence_selector: dict[str, object] | None = None,
) -> NormalizedNotificationPolicy:
    root = _object(authoring, "notification")
    _exact_fields(root, {"authoring_contract", "target", "schedule", "late_handling"}, "notification")
    if root.get("authoring_contract") != NOTIFICATION_AUTHORING_VERSION:
        _invalid("notification.authoring_contract", "is unsupported")
    _positive(item_version, "item_version")
    for field, text_value in (
        ("item_id", item_id),
        ("command_id", command_id),
        ("recipient_id", recipient_id),
        ("channel", channel),
        ("delivery_target_id", delivery_target_id),
    ):
        _text(text_value, field)
    parse_scheduled_fact(created_at_utc, time_basis="instant_utc", field="created_at_utc")
    if recipient_kind not in {"subject", "subject_group"}:
        _invalid("recipient_kind", "must be subject or subject_group")

    target = _normalize_target(root.get("target"), resolved_target_occurrence_selector=resolved_target_occurrence_selector)
    schedule = _normalize_schedule(root.get("schedule"), application_scope=str(target["application_scope"]))
    late_handling = _normalize_late(root.get("late_handling"))

    intent_id, intent_preimage = notification_id(
        "notification_intent",
        "spine.notification-intent-id.v1",
        {
            "item_id": item_id,
            "intent_created_item_version": item_version,
            "intent_created_by_command_id": command_id,
        },
    )
    schedule_hash_preimage: dict[str, object] = {
        "derivation_version": "spine.normalized-notification-schedule-hash.v1",
        "contract_version": NOTIFICATION_CONTRACT_VERSION,
        "normalization_version": NOTIFICATION_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "target": _hash_target(target),
        "schedule": schedule,
        "late_handling": late_handling,
    }
    schedule_hash = hash_canonical_json(schedule_hash_preimage)
    schedule_id, schedule_id_preimage = notification_id(
        "notification_schedule",
        "spine.notification-schedule-id.v1",
        {
            "notification_intent_id": intent_id,
            "item_id": item_id,
            "item_version": item_version,
            "normalized_notification_schedule_hash": schedule_hash,
        },
    )
    policy_fields: dict[str, object] = {
        "notification_intent_id": intent_id,
        "intent_created_item_version": item_version,
        "intent_created_by_command_id": command_id,
        "item_id": item_id,
        "item_version": item_version,
        "notification_schedule_id": schedule_id,
        "recipient_kind": recipient_kind,
        "channel": channel,
        "delivery_target_id": delivery_target_id,
        "target": target,
        "normalized_notification_schedule_hash": schedule_hash,
        "status": "active",
        "created_at_utc": created_at_utc,
        "created_by_command_id": command_id,
    }
    policy_fields["recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"] = recipient_id
    policy_id, policy_id_preimage = notification_id("notification_policy", "spine.notification-policy-id.v1", policy_fields)
    value: dict[str, object] = {
        "contract_version": NOTIFICATION_CONTRACT_VERSION,
        "normalization_version": NOTIFICATION_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "notification_intent_id": intent_id,
        "notification_policy_id": policy_id,
        "notification_schedule_id": schedule_id,
        "item_id": item_id,
        "item_version": item_version,
        "intent_created_item_version": item_version,
        "intent_created_by_command_id": command_id,
        "recipient_kind": recipient_kind,
        "channel": channel,
        "delivery_target_id": delivery_target_id,
        "target": target,
        "schedule": schedule,
        "normalized_notification_schedule_hash": schedule_hash,
        "late_handling": late_handling,
        "status": "active",
        "created_at_utc": created_at_utc,
        "created_by_command_id": command_id,
        ("recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"): recipient_id,
    }
    return NormalizedNotificationPolicy(
        value=value,
        intent_id_preimage=intent_preimage,
        schedule_hash_preimage=schedule_hash_preimage,
        schedule_id_preimage=schedule_id_preimage,
        policy_id_preimage=policy_id_preimage,
    )


def revise_notification_policy(
    current: object,
    *,
    item_version: str,
    command_id: str,
    changed_at_utc: str,
    recipient_kind: str,
    recipient_id: str,
    channel: str,
    delivery_target_id: str,
    target: object,
    schedule: object,
    late_handling: object,
    status: str = "active",
    disabled_at_utc: str | None = None,
    resolved_target_occurrence_selector: dict[str, object] | None = None,
) -> NormalizedNotificationPolicy:
    """Normalize a successor row while retaining the logical intent identity."""

    prior = _object(current, "current_policy")
    _positive(item_version, "item_version")
    parse_scheduled_fact(changed_at_utc, time_basis="instant_utc", field="changed_at_utc")
    normalized_target = _normalize_target(target, resolved_target_occurrence_selector=resolved_target_occurrence_selector)
    normalized_schedule = _normalize_schedule(schedule, application_scope=str(normalized_target["application_scope"]))
    normalized_late = _normalize_late(late_handling)
    schedule_hash_preimage: dict[str, object] = {
        "derivation_version": "spine.normalized-notification-schedule-hash.v1",
        "contract_version": NOTIFICATION_CONTRACT_VERSION,
        "normalization_version": NOTIFICATION_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "target": _hash_target(normalized_target),
        "schedule": normalized_schedule,
        "late_handling": normalized_late,
    }
    schedule_hash = hash_canonical_json(schedule_hash_preimage)
    schedule_id, schedule_id_preimage = notification_id(
        "notification_schedule",
        "spine.notification-schedule-id.v1",
        {
            "notification_intent_id": prior["notification_intent_id"],
            "item_id": prior["item_id"],
            "item_version": item_version,
            "normalized_notification_schedule_hash": schedule_hash,
        },
    )
    if status not in {"active", "disabled"}:
        _invalid("status", "must be active or disabled")
    policy_fields: dict[str, object] = {
        "notification_intent_id": prior["notification_intent_id"],
        "intent_created_item_version": prior["intent_created_item_version"],
        "intent_created_by_command_id": prior["intent_created_by_command_id"],
        "item_id": prior["item_id"],
        "item_version": item_version,
        "notification_schedule_id": schedule_id,
        "recipient_kind": recipient_kind,
        "channel": channel,
        "delivery_target_id": delivery_target_id,
        "target": normalized_target,
        "normalized_notification_schedule_hash": schedule_hash,
        "status": status,
        "created_at_utc": changed_at_utc,
        "created_by_command_id": command_id,
        "source_notification_policy_id": prior["notification_policy_id"],
    }
    recipient_field = "recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"
    policy_fields[recipient_field] = recipient_id
    if status == "disabled":
        policy_fields["disabled_at_utc"] = disabled_at_utc or changed_at_utc
    policy_id, policy_id_preimage = notification_id("notification_policy", "spine.notification-policy-id.v1", policy_fields)
    value: dict[str, object] = {
        "contract_version": NOTIFICATION_CONTRACT_VERSION,
        "normalization_version": NOTIFICATION_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        **policy_fields,
        "notification_policy_id": policy_id,
        "notification_schedule_id": schedule_id,
        "schedule": normalized_schedule,
        "late_handling": normalized_late,
    }
    return NormalizedNotificationPolicy(
        value=value,
        intent_id_preimage={},
        schedule_hash_preimage=schedule_hash_preimage,
        schedule_id_preimage=schedule_id_preimage,
        policy_id_preimage=policy_id_preimage,
    )


def expand_notification_policy(
    policy: object,
    *,
    targets: list[dict[str, object]],
    evaluated_at_utc: str,
    range_start_utc: str,
    range_end_utc: str,
    policy_actionable: bool = True,
    non_actionable_reason: str | None = None,
    include_diagnostics: bool = False,
    candidate_limit: int = 1001,
) -> ExpandedNotificationOpportunities:
    root = _object(policy, "policy")
    evaluated = _utc(evaluated_at_utc, "evaluated_at_utc")
    range_start = _utc(range_start_utc, "range_start_utc")
    range_end = _utc(range_end_utc, "range_end_utc")
    if range_end <= range_start:
        _invalid("range_end_utc", "must be after range_start_utc")
    if range_end - range_start > timedelta(days=366):
        _invalid("range_end_utc", "range_too_large")
    schedule = _object(root.get("schedule"), "schedule")
    late = _object(root.get("late_handling"), "late_handling")
    opportunities: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for target in targets:
        candidates, omitted = _schedule_candidates(
            schedule,
            target,
            range_start=range_start,
            range_end=range_end,
            candidate_limit=candidate_limit,
        )
        if include_diagnostics:
            diagnostics.extend(omitted)
        for eligible, slot_descriptor in candidates:
            if not range_start <= eligible < range_end:
                continue
            late_allowed = _late_allowed(eligible, evaluated=evaluated, late=late)
            if not late_allowed:
                if include_diagnostics:
                    diagnostics.append(
                        {
                            "severity": "info",
                            "diagnostic_code": "late_slot_skipped",
                            "field": "late_handling",
                            "eligible_at_utc": _utc_text(eligible),
                        }
                    )
                continue
            slot_key, _ = notification_id(
                "notification_schedule_slot",
                "spine.notification-schedule-slot-key.v1",
                {
                    "schedule_kind": schedule["kind"],
                    "slot_descriptor": slot_descriptor,
                },
            )
            target_binding = _target_binding(root, target)
            opportunity_id, _ = notification_id(
                "notification_opportunity",
                "spine.notification-opportunity-id.v1",
                {
                    "notification_intent_id": root["notification_intent_id"],
                    "normalized_notification_schedule_hash": root["normalized_notification_schedule_hash"],
                    "target_binding": target_binding,
                    "notification_schedule_slot_key": slot_key,
                    "eligible_at_utc": _utc_text(eligible),
                },
            )
            dedupe = (str(target_binding), slot_key)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            target_actionable = bool(target.get("actionable", True))
            actionable = policy_actionable and target_actionable
            reason = non_actionable_reason if not policy_actionable else ("occurrence_non_actionable" if not target_actionable else None)
            opportunity: dict[str, object] = {
                "notification_opportunity_id": opportunity_id,
                "notification_schedule_slot_key": slot_key,
                "notification_intent_id": root["notification_intent_id"],
                "notification_policy_id": root["notification_policy_id"],
                "item_id": root["item_id"],
                "source_item_version": root["item_version"],
                "normalized_notification_schedule_hash": root["normalized_notification_schedule_hash"],
                "anchor_role": _object(root["target"], "target")["anchor_role"],
                "application_scope": _object(root["target"], "target")["application_scope"],
                "target_scheduled_fact": target["target_scheduled_fact"],
                "eligible_at_utc": _utc_text(eligible),
                "recipient_kind": root["recipient_kind"],
                "channel": root["channel"],
                "delivery_target_id": root["delivery_target_id"],
                "lifecycle": target.get("lifecycle", "active"),
                "actionable": actionable,
            }
            recipient_field = "recipient_subject_id" if root["recipient_kind"] == "subject" else "recipient_group_id"
            opportunity[recipient_field] = root[recipient_field]
            if target.get("target_utc_instant") is not None:
                opportunity["target_at_utc"] = target["target_utc_instant"]
            for field in (
                "occurrence_id",
                "occurrence_key",
                "occurrence_provenance_id",
                "recurrence_set_id",
                "recurrence_revision_id",
            ):
                if target.get(field) is not None:
                    opportunity[field] = target[field]
            if reason is not None:
                opportunity["reason_code"] = reason
            opportunities.append(opportunity)
    opportunities.sort(key=lambda row: (str(row["eligible_at_utc"]), str(row["notification_opportunity_id"])))
    diagnostics.sort(
        key=lambda row: (
            0 if row["severity"] == "warning" else 1,
            str(row["diagnostic_code"]),
            str(row["field"]),
            str(row.get("eligible_at_utc", "")),
            str(row.get("source_id", "")),
        )
    )
    return ExpandedNotificationOpportunities(tuple(opportunities), tuple(diagnostics))


def _normalize_target(value: object, *, resolved_target_occurrence_selector: dict[str, object] | None) -> dict[str, object]:
    target = _object(value, "target")
    allowed = {"anchor_role", "application_scope", "target_occurrence_key"}
    _exact_fields(target, allowed, "target")
    if target.get("anchor_role") not in {"event_start", "task_due"}:
        _invalid("target.anchor_role", "is invalid")
    scope = target.get("application_scope")
    if scope not in {"item", "each_occurrence", "selected_occurrence"}:
        _invalid("target.application_scope", "is invalid")
    result: dict[str, object] = {
        "anchor_role": target["anchor_role"],
        "application_scope": scope,
    }
    key = target.get("target_occurrence_key")
    if scope == "selected_occurrence":
        _text(key, "target.target_occurrence_key")
        if resolved_target_occurrence_selector is None:
            raise SpineValidationError("semantic_conflict", "target.target_occurrence_key did not resolve")
        result["target_occurrence_key"] = key
        result["target_occurrence_selector"] = resolved_target_occurrence_selector
    elif key is not None or resolved_target_occurrence_selector is not None:
        _invalid("target.target_occurrence_key", "is forbidden for this scope")
    return result


def _hash_target(target: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in target.items() if key != "target_occurrence_key"}


def _normalize_schedule(value: object, *, application_scope: str) -> dict[str, object]:
    schedule = _object(value, "schedule")
    kind = schedule.get("kind")
    if kind == "once":
        _exact_fields(schedule, {"kind", "at"}, "schedule")
        at = _normalize_boundary(schedule.get("at"), "schedule.at")
        if application_scope == "each_occurrence" and at["kind"] == "absolute_utc":
            _invalid("schedule.at", "must be target-relative for each_occurrence")
        return {"kind": "once", "at": at}
    if kind == "offsets":
        _exact_fields(schedule, {"kind", "at"}, "schedule")
        raw = schedule.get("at")
        if not isinstance(raw, list) or not raw:
            _invalid("schedule.at", "must be a non-empty array")
        values = [_normalize_boundary(entry, f"schedule.at[{index}]", target_only=True) for index, entry in enumerate(raw)]
        unique = {canonical_json_bytes(entry): entry for entry in values}
        return {"kind": "offsets", "at": [unique[key] for key in sorted(unique)]}
    if kind == "repeat_window":
        _exact_fields(schedule, {"kind", "start", "stop", "stop_inclusive", "cadence"}, "schedule")
        start = _normalize_boundary(schedule.get("start"), "schedule.start")
        stop = _normalize_boundary(schedule.get("stop"), "schedule.stop")
        if application_scope == "each_occurrence" and (start["kind"] == "absolute_utc" or stop["kind"] == "absolute_utc"):
            _invalid("schedule", "repeat boundaries must be target-relative for each_occurrence")
        inclusive = schedule.get("stop_inclusive")
        if not isinstance(inclusive, bool):
            _invalid("schedule.stop_inclusive", "must be boolean")
        cadence = _normalize_cadence(schedule.get("cadence"))
        return {
            "kind": "repeat_window",
            "start": start,
            "stop": stop,
            "stop_inclusive": inclusive,
            "cadence": cadence,
        }
    _invalid("schedule.kind", "must be once, offsets, or repeat_window")


def _normalize_boundary(value: object, field: str, *, target_only: bool = False) -> dict[str, object]:
    boundary = _object(value, field)
    kind = boundary.get("kind")
    if kind == "absolute_utc" and not target_only:
        _exact_fields(boundary, {"kind", "at_utc"}, field)
        at = _text(boundary.get("at_utc"), f"{field}.at_utc")
        _utc(at, f"{field}.at_utc")
        return {"kind": "absolute_utc", "at_utc": at}
    if kind != "target_offset":
        _invalid(f"{field}.kind", "must be target_offset")
    basis = boundary.get("offset_basis")
    if basis == "elapsed":
        _exact_fields(boundary, {"kind", "offset_basis", "offset_seconds"}, field)
        offset = _signed(boundary.get("offset_seconds"), f"{field}.offset_seconds", -315_576_000, 315_576_000)
        return {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": str(offset)}
    if basis == "calendar_days":
        allowed = {"kind", "offset_basis", "offset_days", "local_time", "timezone", "timezone_database_version"}
        _exact_fields(boundary, allowed, field)
        days = _signed(boundary.get("offset_days"), f"{field}.offset_days", -3660, 3660)
        local_time = _text(boundary.get("local_time"), f"{field}.local_time")
        _parse_local_time(local_time, f"{field}.local_time")
        result: dict[str, object] = {
            "kind": "target_offset",
            "offset_basis": "calendar_days",
            "offset_days": str(days),
            "local_time": local_time,
        }
        timezone = boundary.get("timezone")
        version = boundary.get("timezone_database_version")
        if (timezone is None) != (version is None):
            _invalid(field, "timezone and timezone_database_version must appear together")
        if timezone is not None:
            result["timezone"] = _text(timezone, f"{field}.timezone")
            result["timezone_database_version"] = _text(version, f"{field}.timezone_database_version")
            validate_timezone_context(
                time_basis="local_instant",
                timezone=str(result["timezone"]),
                timezone_database_version=str(result["timezone_database_version"]),
            )
        return result
    _invalid(f"{field}.offset_basis", "must be elapsed or calendar_days")


def _normalize_cadence(value: object) -> dict[str, object]:
    cadence = _object(value, "schedule.cadence")
    if cadence.get("kind") == "fixed_elapsed":
        _exact_fields(cadence, {"kind", "interval_seconds"}, "schedule.cadence")
        interval = _positive(cadence.get("interval_seconds"), "schedule.cadence.interval_seconds")
        if interval > 31_557_600:
            _invalid("schedule.cadence.interval_seconds", "is too large")
        return {"kind": "fixed_elapsed", "interval_seconds": str(interval)}
    if cadence.get("kind") != "local_calendar":
        _invalid("schedule.cadence.kind", "must be fixed_elapsed or local_calendar")
    allowed = {
        "kind",
        "frequency",
        "interval",
        "seed_local_date",
        "local_time",
        "timezone",
        "timezone_database_version",
        "by_month",
        "by_month_day",
        "by_weekday",
        "by_set_position",
        "week_start",
    }
    _exact_fields(cadence, allowed, "schedule.cadence")
    seed_date = _text(cadence.get("seed_local_date"), "schedule.cadence.seed_local_date")
    local_time = _text(cadence.get("local_time"), "schedule.cadence.local_time")
    parse_scheduled_fact(seed_date, time_basis="local_date", field="schedule.cadence.seed_local_date")
    _parse_local_time(local_time, "schedule.cadence.local_time")
    timezone = _text(cadence.get("timezone"), "schedule.cadence.timezone")
    version = _text(cadence.get("timezone_database_version"), "schedule.cadence.timezone_database_version")
    validate_timezone_context(
        time_basis="local_instant",
        timezone=timezone,
        timezone_database_version=version,
    )
    rule_input = {
        key: value
        for key, value in cadence.items()
        if key not in {"kind", "seed_local_date", "local_time", "timezone", "timezone_database_version"}
    }
    rule_input.update(
        {
            "seed": f"{seed_date}T{local_time}",
            "start_bound": f"{seed_date}T{local_time}",
            "end_condition": {"kind": "unbounded"},
        }
    )
    normalized_rule = normalize_rule(rule_input, time_basis="local_instant", field="schedule.cadence").as_contract()
    normalized_rule.pop("seed")
    normalized_rule.pop("start_bound")
    normalized_rule.pop("end_condition")
    return {
        "kind": "local_calendar",
        **normalized_rule,
        "seed_local_date": seed_date,
        "local_time": local_time,
        "timezone": timezone,
        "timezone_database_version": version,
    }


def _normalize_late(value: object) -> dict[str, object]:
    late = _object(value, "late_handling")
    if late.get("kind") == "skip":
        _exact_fields(late, {"kind"}, "late_handling")
        return {"kind": "skip"}
    if late.get("kind") == "deliver_within":
        _exact_fields(late, {"kind", "grace_seconds"}, "late_handling")
        grace = _nonnegative(late.get("grace_seconds"), "late_handling.grace_seconds")
        return {"kind": "deliver_within", "grace_seconds": str(grace)}
    _invalid("late_handling.kind", "must be skip or deliver_within")


def _schedule_candidates(
    schedule: dict[str, Any],
    target: dict[str, object],
    *,
    range_start: datetime,
    range_end: datetime,
    candidate_limit: int,
) -> tuple[list[tuple[datetime, dict[str, object]]], list[dict[str, object]]]:
    kind = schedule["kind"]
    if kind == "once":
        resolved = _resolve_boundary(_object(schedule["at"], "schedule.at"), target)
        return ([] if resolved is None else [(resolved, _object(schedule["at"], "schedule.at"))]), []
    if kind == "offsets":
        candidates: list[tuple[datetime, dict[str, object]]] = []
        for boundary in schedule["at"]:
            resolved = _resolve_boundary(_object(boundary, "schedule.at"), target)
            if resolved is not None:
                candidates.append((resolved, _object(boundary, "schedule.at")))
        return candidates, []
    start = _resolve_boundary(_object(schedule["start"], "schedule.start"), target)
    stop = _resolve_boundary(_object(schedule["stop"], "schedule.stop"), target)
    if start is None or stop is None:
        return [], []
    inclusive = bool(schedule["stop_inclusive"])
    if start > stop or (start == stop and not inclusive):
        raise SpineValidationError("semantic_conflict", "repeat_window start must precede stop")
    cadence = _object(schedule["cadence"], "schedule.cadence")
    candidates = []
    omitted: list[dict[str, object]] = []
    if cadence["kind"] == "fixed_elapsed":
        interval_seconds = int(str(cadence["interval_seconds"]))
        interval = timedelta(seconds=interval_seconds)
        if range_end <= start or range_start > stop or (range_start == stop and not inclusive):
            return [], []
        elapsed = max(0, int((range_start - start).total_seconds()))
        index = (elapsed + interval_seconds - 1) // interval_seconds
        current = start + index * interval
        while current < range_end and (current < stop or (inclusive and current == stop)):
            if len(candidates) >= candidate_limit:
                omitted.append(
                    {
                        "severity": "info",
                        "diagnostic_code": "density_truncated",
                        "field": "schedule.cadence",
                    }
                )
                break
            fact = _utc_text(current)
            candidates.append((current, {"cadence": cadence, "candidate_scheduled_fact": fact}))
            current += interval
        return candidates, omitted
    timezone = str(cadence["timezone"])
    zone = ZoneInfo(timezone)
    bounded_start = max(start, range_start)
    bounded_end = min(stop, range_end)
    if bounded_end < bounded_start or (bounded_end == bounded_start and (not inclusive or bounded_end == range_end)):
        return [], []
    local_start = (bounded_start.astimezone(zone) - timedelta(days=1)).replace(tzinfo=None)
    local_end = (bounded_end.astimezone(zone) + timedelta(days=1)).replace(tzinfo=None)
    rule = {
        key: value
        for key, value in cadence.items()
        if key not in {"kind", "seed_local_date", "local_time", "timezone", "timezone_database_version"}
    }
    rule.update(
        {
            "seed": f"{cadence['seed_local_date']}T{cadence['local_time']}",
            "start_bound": f"{cadence['seed_local_date']}T{cadence['local_time']}",
            "end_condition": {"kind": "unbounded"},
        }
    )
    expanded = expand_rule(
        rule,
        time_basis="local_instant",
        range_start=local_start.isoformat(timespec="seconds"),
        range_end=local_end.isoformat(timespec="seconds"),
        timezone=timezone,
        timezone_database_version=str(cadence["timezone_database_version"]),
    )
    for candidate in expanded.candidates:
        assert candidate.timezone_resolution is not None
        instant = _utc(candidate.timezone_resolution.utc_instant, "candidate")
        if not range_start <= instant < range_end:
            continue
        if start <= instant < stop or (inclusive and instant == stop):
            if len(candidates) >= candidate_limit:
                omitted.append(
                    {
                        "severity": "info",
                        "diagnostic_code": "density_truncated",
                        "field": "schedule.cadence",
                    }
                )
                break
            candidates.append(
                (
                    instant,
                    {"cadence": cadence, "candidate_scheduled_fact": candidate.scheduled_fact},
                )
            )
    for missing in expanded.omitted_local_candidates:
        omitted.append(
            {
                "severity": "warning",
                "diagnostic_code": "dst_nonexistent_omitted",
                "field": "schedule.cadence",
                "source_id": str(schedule.get("notification_schedule_id", "schedule")),
                "eligible_at_utc": missing.scheduled_fact,
            }
        )
    return candidates, omitted


def _resolve_boundary(boundary: dict[str, Any], target: dict[str, object]) -> datetime | None:
    if boundary["kind"] == "absolute_utc":
        return _utc(str(boundary["at_utc"]), "boundary.at_utc")
    if boundary["offset_basis"] == "elapsed":
        target_utc = _utc(str(target["target_utc_instant"]), "target.target_utc_instant")
        return target_utc + timedelta(seconds=int(str(boundary["offset_seconds"])))
    timezone = str(boundary.get("timezone") or target.get("timezone") or "")
    version = str(boundary.get("timezone_database_version") or target.get("timezone_database_version") or "")
    if not timezone or not version:
        raise SpineValidationError("semantic_conflict", "calendar offset timezone cannot be resolved")
    local_date_value = target.get("target_local_date")
    if local_date_value is None:
        target_utc = _utc(str(target["target_utc_instant"]), "target.target_utc_instant")
        local_date_value = target_utc.astimezone(ZoneInfo(timezone)).date().isoformat()
    parsed_date = parse_scheduled_fact(str(local_date_value), time_basis="local_date", field="target_local_date")
    assert isinstance(parsed_date, date)
    scheduled = f"{(parsed_date + timedelta(days=int(str(boundary['offset_days'])))).isoformat()}T{boundary['local_time']}"
    resolution = resolve_local_instant(scheduled, timezone=timezone, timezone_database_version=version)
    return None if resolution is None else _utc(resolution.utc_instant, "boundary")


def _target_binding(root: dict[str, Any], target: dict[str, object]) -> dict[str, object]:
    policy_target = _object(root["target"], "target")
    result: dict[str, object] = {
        "anchor_role": policy_target["anchor_role"],
        "application_scope": policy_target["application_scope"],
    }
    if policy_target["application_scope"] == "item":
        result["item_target_scheduled_fact"] = target["target_scheduled_fact"]
    else:
        result["target_occurrence_selector"] = target["target_occurrence_selector"]
    return result


def _late_allowed(eligible: datetime, *, evaluated: datetime, late: dict[str, Any]) -> bool:
    if eligible >= evaluated:
        return True
    if late["kind"] == "skip":
        return False
    return evaluated - eligible <= timedelta(seconds=int(str(late["grace_seconds"])))


def _utc(value: str, field: str) -> datetime:
    parsed = parse_scheduled_fact(value, time_basis="instant_utc", field=field)
    assert isinstance(parsed, datetime)
    return parsed


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_local_time(value: str, field: str) -> None:
    try:
        if datetime.strptime(value, "%H:%M:%S").strftime("%H:%M:%S") != value:
            raise ValueError
    except ValueError:
        _invalid(field, "must be HH:MM:SS")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid(field, "must be an object")
    return value


def _exact_fields(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _invalid(f"{field}.{unknown[0]}", "is not supported")
    required_by_context = {
        "notification": {"authoring_contract", "target", "schedule", "late_handling"},
    }
    for required in required_by_context.get(field, set()):
        if required not in value:
            _invalid(f"{field}.{required}", "is required")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        _invalid(field, "must be a non-empty string")
    return value


def _positive(value: object, field: str) -> int:
    if not isinstance(value, str) or not value.isdigit() or value.startswith("0"):
        _invalid(field, "must be a positive decimal string")
    return int(value)


def _nonnegative(value: object, field: str) -> int:
    if not isinstance(value, str) or not value.isdigit() or (len(value) > 1 and value.startswith("0")):
        _invalid(field, "must be a non-negative decimal string")
    return int(value)


def _signed(value: object, field: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, str):
        _invalid(field, "must be a signed decimal string")
    try:
        parsed = int(value)
    except ValueError:
        _invalid(field, "must be a signed decimal string")
    if str(parsed) != value or not minimum <= parsed <= maximum:
        _invalid(field, "is outside its canonical range")
    return parsed


def _invalid(field: str, detail: str) -> NoReturn:
    raise SpineValidationError("invalid_request", f"{field} {detail}")
