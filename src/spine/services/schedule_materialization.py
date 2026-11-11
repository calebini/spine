"""Compose successor notification work inside the caller-owned transaction.

No child command, receipt, commit, delivery or implicit materialization mode.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.notification_targets import parse_utc_datetime, recurrence_source_range, target_from_anchor
from spine.core.notifications import expand_notification_policy, notification_id
from spine.core.occurrence_details import decorate_occurrence
from spine.core.occurrences import expand_recurrence_set
from spine.core.provenance import derive_occurrence_provenance
from spine.ledger.item_reads import hydrated_item_at_version
from spine.ledger.provenance import insert_occurrence_provenance
from spine.ledger.schedule_work import provenance_exists, provenance_scheduled_facts, work_exists
from spine.ledger.work import create_work_instance


def materialize_successor(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_version: int,
    recurrence: Mapping[str, Any] | None,
    policies: Sequence[Mapping[str, object]],
    policy_key_by_intent: Mapping[str, str],
    materialization: Mapping[str, object],
    command_id: str,
    created_at: str,
) -> tuple[list[str], list[dict[str, object]], int]:
    if materialization["mode"] == "none":
        return [], [], 0
    item = hydrated_item_at_version(connection, item_id, item_version)
    range_start = str(materialization["range_start_utc"])
    range_end = str(materialization["range_end_utc"])
    targets_by_intent: dict[str, list[dict[str, object]]] = {}
    if recurrence is not None:
        source_start, source_end = recurrence_source_range(
            recurrence,
            policies=[dict(value) for value in policies],
            eligibility_start=parse_utc_datetime(range_start),
            eligibility_end=parse_utc_datetime(range_end),
        )
        expanded = expand_recurrence_set(
            recurrence,
            range_start=source_start,
            range_end=source_end,
            range_basis="expressed_time",
        )
        provenance_targets: list[dict[str, object]] = []
        for raw in expanded.occurrences:
            occurrence = decorate_occurrence(item, recurrence, dict(raw), include_internal=True)
            derived = derive_occurrence_provenance(
                occurrence=occurrence,
                recurrence=recurrence,
                item=item,
                consumer="notification_schedule",
                producer="schedule.update",
                range_basis="expressed_time",
                range_start=source_start,
                range_end=source_end,
                created_at_utc=created_at,
            )
            existing = provenance_exists(connection, str(derived.value["occurrence_provenance_id"]))
            if not existing:
                insert_occurrence_provenance(connection, derived=derived)
            target: dict[str, object] = {
                "target_scheduled_fact": occurrence["expressed_scheduled_fact"],
                "target_occurrence_selector": occurrence["target_occurrence_selector"],
                "occurrence_id": occurrence["occurrence_id"],
                "occurrence_key": occurrence["occurrence_key"],
                "occurrence_provenance_id": derived.value["occurrence_provenance_id"],
                "recurrence_set_id": recurrence["recurrence_set_id"],
                "recurrence_revision_id": recurrence["recurrence_revision_id"],
                "lifecycle": "scheduled" if occurrence["lifecycle"] == "active" else occurrence["lifecycle"],
                "actionable": bool(occurrence["actionable"]),
            }
            timezone_resolution = occurrence.get("timezone_resolution")
            if isinstance(timezone_resolution, Mapping):
                target["target_utc_instant"] = timezone_resolution["utc_instant"]
            elif recurrence["time_basis"] == "instant_utc":
                target["target_utc_instant"] = occurrence["expressed_scheduled_fact"]
            if recurrence.get("timezone") is not None:
                target["timezone"] = recurrence["timezone"]
                target["timezone_database_version"] = recurrence["timezone_database_version"]
                target["target_local_date"] = str(occurrence["expressed_scheduled_fact"]).split("T", 1)[0]
            provenance_targets.append(target)
        for policy in policies:
            targets_by_intent[str(policy["notification_intent_id"])] = provenance_targets
    else:
        anchor = item["detail"].get("start_anchor" if item["item_type"] == "event" else "due_anchor")
        if not isinstance(anchor, Mapping):
            raise SpineValidationError("semantic_conflict:materialization", "successor primary schedule is unavailable")
        target = target_from_anchor(anchor)
        for policy in policies:
            targets_by_intent[str(policy["notification_intent_id"])] = [target]

    opportunities: list[dict[str, object]] = []
    for policy in policies:
        expanded_policy = expand_notification_policy(
            policy,
            targets=targets_by_intent[str(policy["notification_intent_id"])],
            evaluated_at_utc=str(materialization["evaluated_at_utc"]),
            range_start_utc=range_start,
            range_end_utc=range_end,
            candidate_limit=int(str(materialization["limit"])) + 1,
        )
        opportunities.extend(dict(value) for value in expanded_policy.opportunities if bool(value["actionable"]))
    opportunities.sort(key=lambda value: (str(value["eligible_at_utc"]), str(value["notification_opportunity_id"])))
    limit = int(str(materialization["limit"]))
    if len(opportunities) > limit:
        raise SpineValidationError(
            "invalid_request:materialization.limit",
            "materialization.limit is smaller than the complete actionable opportunity set",
        )
    created: list[str] = []
    evidence: list[dict[str, object]] = []
    for opportunity in opportunities:
        work_id, _ = notification_id(
            "work_instance",
            "spine.notification-work-instance-id.v1",
            {
                "notification_opportunity_id": opportunity["notification_opportunity_id"],
                "delivery_target_id": opportunity["delivery_target_id"],
            },
        )
        if work_exists(connection, work_id):
            continue
        recipient_id = opportunity.get("recipient_subject_id") or opportunity.get("recipient_group_id")
        create_work_instance(
            connection,
            work_instance_id=work_id,
            item_id=item_id,
            item_version=item_version,
            notification_policy_id=str(opportunity["notification_policy_id"]),
            notification_policy_item_version=item_version,
            notification_intent_id=str(opportunity["notification_intent_id"]),
            notification_opportunity_id=str(opportunity["notification_opportunity_id"]),
            normalized_notification_schedule_hash=str(opportunity["normalized_notification_schedule_hash"]),
            occurrence_provenance_id=(
                str(opportunity["occurrence_provenance_id"])
                if opportunity.get("occurrence_provenance_id") is not None else None
            ),
            target_anchor_role=str(opportunity["anchor_role"]),
            application_scope=str(opportunity["application_scope"]),
            target_scheduled_fact=str(opportunity["target_scheduled_fact"]),
            target_at_utc=str(opportunity["target_at_utc"]) if opportunity.get("target_at_utc") is not None else None,
            occurrence_key=str(opportunity["occurrence_key"]) if opportunity.get("occurrence_key") is not None else None,
            delivery_target_id=str(opportunity["delivery_target_id"]),
            generation_source_kind="schedule_tick",
            generation_source_ref=str(opportunity["notification_opportunity_id"]),
            work_subject_ref=f"{opportunity['recipient_kind']}:{recipient_id}",
            policy_basis_ref=str(opportunity["normalized_notification_schedule_hash"]),
            eligible_at_utc=str(opportunity["eligible_at_utc"]),
            created_at_utc=created_at,
            manage_transaction=False,
        )
        created.append(work_id)
        evidence_value: dict[str, object] = {
            "policy_key": policy_key_by_intent[str(opportunity["notification_intent_id"])],
            "notification_intent_id": opportunity["notification_intent_id"],
            "notification_policy_id": opportunity["notification_policy_id"],
            "notification_opportunity_id": opportunity["notification_opportunity_id"],
            "eligible_at_utc": opportunity["eligible_at_utc"],
            "work_instance_id": work_id,
        }
        if opportunity.get("occurrence_key") is not None:
            evidence_value["occurrence_key"] = opportunity["occurrence_key"]
            provenance_row = provenance_scheduled_facts(connection, str(opportunity["occurrence_provenance_id"]))
            if provenance_row is not None:
                evidence_value["original_scheduled_fact"] = provenance_row["original_scheduled_fact"]
                evidence_value["expressed_scheduled_fact"] = provenance_row["expressed_scheduled_fact"]
        evidence.append(evidence_value)
    return created, evidence, len(opportunities)
