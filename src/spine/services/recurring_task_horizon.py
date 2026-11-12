"""Bounded future-source evidence for manual recurring-task reconciliation."""

from __future__ import annotations

from typing import Any

from spine.core.occurrences import _rule_selector
from spine.core.recurring_task_runtime import instant
from spine.core.schedule import normalize_rule, resolve_local_instant, rule_exhausted_before
from spine.ledger.recurring_task_sources import ProofBudget, _calendar_cost
from spine.timezones import timezone_for_version


def source_exhausted(recurrence: dict[str, Any], evaluation: str, budget: ProofBudget) -> bool:
    """Prove no source candidate remains at/after evaluation in this snapshot.

    The horizon being empty is insufficient. Future additions and moved
    occurrences also defeat the proof, even after every rule's COUNT is consumed.
    Exclusions do not reduce COUNT; unknown/unbounded futures remain waiting.
    This is read-only and does not create durable polling/progress evidence.
    """
    basis = recurrence["time_basis"]
    zone, version = recurrence.get("timezone"), recurrence.get("timezone_database_version")
    boundary = evaluation
    if basis == "local_instant":
        assert isinstance(zone, str) and isinstance(version, str)
        boundary = instant(evaluation).astimezone(timezone_for_version(zone, version)).strftime("%Y-%m-%dT%H:%M:%S")
    segments = {}
    for segment in recurrence["segments"]:
        budget.spend()
        if segment["status"] == "active":
            segments[segment["segment_id"]] = segment
    for addition in recurrence["rdates"]:
        budget.spend()
        segment = segments.get(addition["segment_id"])
        if addition["status"] != "active" or segment is None:
            continue
        fact = addition["scheduled_fact"]
        if fact >= max(boundary, segment["active_start"]) and (segment.get("active_end") is None or fact < segment["active_end"]):
            return False
    for override in recurrence["overrides"]:
        budget.spend()
        fact = override.get("expressed_scheduled_fact")
        if override["status"] != "active" or override["segment_id"] not in segments or not fact or override.get("lifecycle") == "cancelled":
            continue
        if basis == "local_instant":
            assert isinstance(zone, str) and isinstance(version, str)
            resolution = resolve_local_instant(fact, timezone=zone, timezone_database_version=version)
            if resolution is None:
                continue
            fact = resolution.utc_instant
        if fact >= evaluation:
            return False
    for rule in recurrence["rules"]:
        budget.spend()
        segment = segments.get(rule["segment_id"])
        if rule["status"] != "active" or segment is None:
            continue
        budget.spend(_calendar_cost(recurrence, rule, boundary))
        if not rule_exhausted_before(
            normalize_rule(_rule_selector(rule), time_basis=basis), boundary=boundary, time_basis=basis,
            timezone=zone, timezone_database_version=version,
            segment_start=segment["active_start"], segment_end=segment.get("active_end"),
        ):
            return False
    return True
