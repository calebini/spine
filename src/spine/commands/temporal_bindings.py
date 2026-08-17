"""Command handlers for relative temporal bindings and atomic related tasks."""

from __future__ import annotations

import base64
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands.context import CommandContext
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.provenance import DerivedOccurrenceProvenance, derive_occurrence_provenance
from spine.core.temporal_bindings import binding_revision_preimage
from spine.ledger.common import TemporalAnchorInput, insert_temporal_anchor
from spine.ledger.items import create_next_item_version, create_task_v1
from spine.ledger.notifications import insert_notification_schedule_policy, load_current_notification_policies
from spine.ledger.provenance import active_provenance_for_slot, insert_occurrence_provenance, supersede_occurrence_provenance
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.relations import create_item_relation
from spine.ledger.temporal_bindings import (
    BINDING_STATES,
    binding_catalog_generation,
    binding_state,
    binding_view,
    increment_binding_catalog_generation,
    insert_temporal_binding,
    insert_temporal_binding_revision,
    load_temporal_binding,
    retire_temporal_binding,
    target_from_source,
)
from spine.ledger.work import cancel_work_instance

CREATE_CONTRACT = "spine.schedule-related-task-create.v1"
LIST_CONTRACT = "spine.schedule-binding-list.v1"
RECONCILE_CONTRACT = "spine.schedule-binding-reconcile.v1"


def handle_related_task_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    from spine.commands import core as c

    command = "schedule.related_task.create"
    allowed = {
        "contract_version",
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "source",
        "task",
        "relationship",
        "temporal_binding",
        "delivery",
        "reminders",
        "materialization",
    }
    c._check_fields(command, request, allowed)
    for field in (
        "contract_version",
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "source",
        "task",
        "relationship",
        "temporal_binding",
        "reminders",
        "materialization",
    ):
        if field not in request:
            raise SpineValidationError(f"missing_{field}", f"{field} is required")
    if request["contract_version"] != CREATE_CONTRACT:
        raise SpineValidationError("invalid_request:contract_version", f"contract_version must be {CREATE_CONTRACT}")
    command_id, actor, created_at = c._write_identity(command, request, "created_at_utc", context)
    semantic = c._semantic_request(command, command_id, actor, created_at, request, allowed)
    replay = c._compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        return _create_response(replay, "related_task_schedule_create_replay")
    _runtime_check(context.ledger, _create_versions())

    source_request = c._schedule_object(request["source"], "source")
    source_allowed = {
        "item_id",
        "target_version",
        "anchor_role",
        "scope",
        "source_recurrence_revision_id",
        "target_occurrence_key",
        "target_occurrence_selector",
    }
    c._schedule_exact_fields(source_request, source_allowed, "source")
    source_item_id = c._nested_required_str(source_request, "item_id", "source.item_id")
    source_version = c._version(source_request, "target_version")
    if source_request.get("anchor_role") != "event_start":
        raise SpineValidationError("invalid_request:source.anchor_role", "source.anchor_role must be event_start")
    scope = c._enum(source_request.get("scope"), "source.scope", {"item", "selected_occurrence"})
    source_item = c._hydrated_item(context.ledger, source_item_id)
    if source_item["item_type"] != "event":
        raise SpineValidationError("wrong_item_type:source.item_id", "source item must be an event")
    if source_item["status"] != "active" or source_item["detail"]["event_status"] != "scheduled":
        raise SpineValidationError("invalid_state_transition:source.item_id", "source event must be active and scheduled")
    if int(source_item["current_version"]) != source_version:
        raise SpineValidationError("stale_version:source.target_version", "source target version is not current")
    recurrence = load_current_recurrence_set(context.ledger, item_id=source_item_id)
    derived_provenance: DerivedOccurrenceProvenance | None = None
    selector_ref: str | None = None
    if scope == "item":
        if recurrence is not None:
            raise SpineValidationError("invalid_request:source.scope", "recurring source events require selected_occurrence")
        forbidden = {"source_recurrence_revision_id", "target_occurrence_key", "target_occurrence_selector"} & set(source_request)
        if forbidden:
            raise SpineValidationError(
                f"unsupported_field:source.{sorted(forbidden)[0]}", "selected-occurrence fields require selected_occurrence"
            )
        source = _source_from_item(source_item)
    else:
        if recurrence is None:
            raise SpineValidationError("invalid_request:source.scope", "selected_occurrence requires recurrence")
        requested_revision = c._nested_required_str(source_request, "source_recurrence_revision_id", "source.source_recurrence_revision_id")
        if requested_revision != recurrence["recurrence_revision_id"]:
            raise SpineValidationError("stale_version:source.source_recurrence_revision_id", "source recurrence revision is not current")
        occurrence_key = c._nested_required_str(source_request, "target_occurrence_key", "source.target_occurrence_key")
        requested_selector = c._schedule_object(source_request.get("target_occurrence_selector"), "source.target_occurrence_selector")
        occurrence = c._resolve_current_occurrence(recurrence, occurrence_key)
        if occurrence.get("target_occurrence_selector") != requested_selector:
            raise SpineValidationError("semantic_conflict:source.target_occurrence_selector", "selected occurrence selector is stale")
        decorated = c._decorate_occurrence(source_item, recurrence, dict(occurrence), include_internal=True)
        scheduled_fact = str(requested_selector["scheduled_fact"])
        range_end = c._next_scheduled_fact(scheduled_fact, time_basis=str(recurrence["time_basis"]))
        derived_provenance = derive_occurrence_provenance(
            occurrence=decorated,
            recurrence=recurrence,
            item=source_item,
            consumer="temporal_binding",
            producer=command,
            range_basis="original_schedule",
            range_start=scheduled_fact,
            range_end=range_end,
            created_at_utc=created_at,
        )
        selector_ref = "recurrence_target_selector_" + hash_canonical_json(requested_selector)
        source = _source_from_occurrence(recurrence, decorated)
        source.update(
            {
                "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
                "source_occurrence_key": occurrence_key,
                "source_occurrence_selector_ref": selector_ref,
                "source_occurrence_provenance_id": derived_provenance.value["occurrence_provenance_id"],
                "target_occurrence_selector": requested_selector,
            }
        )

    task_request = c._schedule_object(request["task"], "task")
    c._schedule_exact_fields(task_request, {"title", "summary", "source_ref", "priority", "subject_roles"}, "task")
    title = c._nested_required_str(task_request, "title", "task.title")
    roles_raw = task_request.get("subject_roles", [])
    subject_roles = c._task_subject_roles(
        context.ledger,
        command=command,
        command_id=command_id,
        value=roles_raw,
        field="task.subject_roles",
        request_path="/task/subject_roles",
    )
    relationship = c._schedule_object(request["relationship"], "relationship")
    c._schedule_exact_fields(relationship, {"relation_type"}, "relationship")
    if relationship.get("relation_type") != "part_of":
        raise SpineValidationError("invalid_request:relationship.relation_type", "relationship.relation_type must be part_of")
    binding_request = c._schedule_object(request["temporal_binding"], "temporal_binding")
    c._schedule_exact_fields(
        binding_request, {"binding_mode", "source_terminal_behavior", "offset_basis", "offset_seconds"}, "temporal_binding"
    )
    mode = c._enum(binding_request.get("binding_mode"), "temporal_binding.binding_mode", {"snapshot", "follow_source"})
    if binding_request.get("offset_basis") != "elapsed":
        raise SpineValidationError("invalid_request:temporal_binding.offset_basis", "offset_basis must be elapsed")
    offset = c._schedule_signed_decimal(binding_request.get("offset_seconds"), "temporal_binding.offset_seconds")
    if not -31_622_400 <= offset <= 31_622_400:
        raise SpineValidationError("invalid_request:temporal_binding.offset_seconds", "offset_seconds exceeds the 366-day bound")
    terminal_behavior = binding_request.get("source_terminal_behavior")
    if mode == "snapshot" and terminal_behavior is not None:
        raise SpineValidationError("invalid_request:temporal_binding.source_terminal_behavior", "snapshot forbids source_terminal_behavior")
    if mode == "follow_source":
        terminal_behavior = c._enum(
            terminal_behavior, "temporal_binding.source_terminal_behavior", {"cancel_target", "detach_at_last_value", "require_decision"}
        )
    target = target_from_source(source, offset)
    scheduled = {**target, "resolution_kind": "unambiguous", "offset_seconds": "0"}
    materialization = c._schedule_normalize_materialization(request["materialization"], scheduled=scheduled)
    reminders = request["reminders"]
    if not isinstance(reminders, Sequence) or isinstance(reminders, (str, bytes, bytearray)) or len(reminders) > 32:
        raise SpineValidationError("invalid_request:reminders", "reminders must contain zero through 32 policies")
    if reminders:
        if "delivery" not in request:
            raise SpineValidationError("missing_delivery", "delivery is required when reminders are present")
        delivery = c._schedule_resolve_delivery(request["delivery"], context)
        policies = c._schedule_normalize_policies(
            reminders,
            item_id=c._derived_id(command, command_id, "item", "/task"),
            item_type="task",
            recurring=False,
            command_id=command_id,
            created_at_utc=created_at,
            delivery=delivery,
        )
    else:
        if "delivery" in request:
            raise SpineValidationError("invalid_request:delivery", "delivery is forbidden when reminders is empty")
        if materialization["mode"] != "none":
            raise SpineValidationError("invalid_request:materialization.mode", "bounded materialization requires reminders")
        delivery = None
        policies = ()

    item_id = c._derived_id(command, command_id, "item", "/task")
    anchor_id = c._derived_id(command, command_id, "due_anchor", "/temporal_binding/resolved_target")
    relation_id = c._derived_id(command, command_id, "relation", "/relationship")
    binding_id = c._derived_id(command, command_id, "temporal_binding", "/temporal_binding")
    revision_id = c._derived_id(command, command_id, "temporal_binding_revision", "/temporal_binding/revisions/0")
    audit_id = c._derived_id(command, command_id, "audit", "/audit")
    anchor = TemporalAnchorInput(
        anchor_id=anchor_id,
        anchor_kind="local_instant",
        local_date=target["local_date"],
        local_time=target["local_time"],
        timezone=target["timezone"],
        timezone_database_version=target["timezone_database_version"],
    )
    header = {
        "temporal_binding_id": binding_id,
        "binding_contract": "spine.relative-temporal-binding.v1",
        "target_item_id": item_id,
        "target_anchor_role": "task_due",
        "source_item_id": source_item_id,
        "source_anchor_role": "event_start",
        "relationship_id": relation_id,
        "binding_mode": mode,
        "source_terminal_behavior": terminal_behavior,
        "created_by_command_id": command_id,
        "created_by_subject_id": actor,
        "created_at_utc": created_at,
        "binding_status": "active",
    }
    revision = _revision_value(
        command=command,
        command_id=command_id,
        revision_id=revision_id,
        binding=header,
        prior=None,
        revision_index=1,
        source=source,
        source_scope=scope,
        offset=offset,
        target=target,
        target_item_version=1,
        target_anchor_id=anchor_id,
        resolution_kind="initial",
        created_at=created_at,
    )
    receipt_holder: list[dict[str, Any]] = []

    def insert_bundle(connection: sqlite3.Connection) -> None:
        _injected_failure(context, "item")
        if derived_provenance is not None:
            _persist_provenance(connection, derived_provenance, command_id=command_id, at=created_at)
        _injected_failure(context, "provenance")
        create_item_relation(
            connection,
            relation_id=relation_id,
            source_item_id=item_id,
            target_item_id=source_item_id,
            relation_type="part_of",
            created_at_utc=created_at,
            created_by_subject_id=actor,
            manage_transaction=False,
        )
        _injected_failure(context, "relation")
        insert_temporal_binding(connection, value=header)
        insert_temporal_binding_revision(connection, value=revision)
        increment_binding_catalog_generation(connection)
        _injected_failure(context, "binding")
        for _, policy in policies:
            insert_notification_schedule_policy(connection, normalized=policy)
        _injected_failure(context, "policies")
        policy_values = [policy.value for _, policy in policies]
        created_work, opportunity_work, opportunity_count = c._schedule_materialize_successor(
            connection,
            item_id=item_id,
            item_version=1,
            recurrence=None,
            policies=policy_values,
            policy_key_by_intent={str(policy.value["notification_intent_id"]): key for key, policy in policies},
            materialization=materialization,
            command_id=command_id,
            created_at=created_at,
        )
        _injected_failure(context, "work")
        materialization_facts = c._schedule_update_materialization_facts(materialization, created_work, opportunity_work, opportunity_count)
        facts = {
            "command_id": command_id,
            "command_receipt_id": c._receipt_id(command, command_id),
            "audit_id": audit_id,
            "task": {
                "item_id": item_id,
                "current_version": "1",
                "task_status": "open",
                "title": title,
                "subject_roles": [dict(subject_id=r.subject_id, role=str(r.role), status=str(r.status)) for r in subject_roles],
            },
            "source": {"item_id": source_item_id, "target_version": str(source_version), "scope": scope, **source},
            "relationship": {
                "relation_id": relation_id,
                "relation_type": "part_of",
                "source_item_id": item_id,
                "target_item_id": source_item_id,
                "status": "active",
            },
            "temporal_binding": {
                **header,
                "latest_revision": revision,
                "binding_state": "snapshot_resolved" if mode == "snapshot" else "current",
            },
            "scheduled_time": {"anchor_id": anchor_id, "anchor_role": "task_due", **target},
            "delivery": None if delivery is None else delivery["snapshot"],
            "policies": [_policy_fact(key, policy.value) for key, policy in policies],
            "materialization": materialization_facts,
            "work_instance_ids": created_work,
            "phases": {
                "task": "authored",
                "relation": "authored",
                "binding": "resolved",
                "policies": "authored" if policies else "none",
                "opportunities": "expanded" if materialization["mode"] == "bounded" else "not_requested",
                "work": materialization_facts["state"],
                "delivery": "not_attempted",
            },
            "delivery_state": "not_attempted_by_command",
        }
        receipt = c._make_receipt(
            command=command,
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=created_at,
            effect="related_task_schedule_created",
            item_id=item_id,
            target_version="0",
            semantic_facts={**semantic, "normalized_result": facts},
            result_identity_facts=facts,
        )
        c.insert_command_receipt(connection, receipt)
        _injected_failure(context, "receipt")
        receipt_holder.append(receipt)

    create_task_v1(
        context.ledger,
        item_id=item_id,
        audit_id=audit_id,
        created_at_utc=created_at,
        created_by_subject_id=actor,
        title=title,
        summary=c._nested_optional_str(task_request, "summary", "task.summary"),
        source_ref=c._nested_optional_str(task_request, "source_ref", "task.source_ref"),
        priority=c._nested_optional_str(task_request, "priority", "task.priority"),
        due_anchor=anchor,
        subject_roles=subject_roles,
        insert_canonical_extension=insert_bundle,
        audit_action="related_task_schedule_created",
        audit_reason_code="related_task_schedule_created",
        audit_payload={
            "action": "related_task_schedule_created",
            "item_id": item_id,
            "source_item_id": source_item_id,
            "temporal_binding_id": binding_id,
        },
    )
    return _create_response(receipt_holder[0], "related_task_schedule_created")


def handle_binding_list(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    from spine.commands import core as c

    command = "schedule.binding.list"
    allowed = {
        "contract_version",
        "source_item_id",
        "target_item_id",
        "binding_mode",
        "binding_status",
        "binding_states",
        "limit",
        "cursor",
        "bounded",
    }
    c._check_fields(command, request, allowed)
    if request.get("contract_version") != LIST_CONTRACT:
        raise SpineValidationError("invalid_request:contract_version", f"contract_version must be {LIST_CONTRACT}")
    _runtime_check(context.ledger, _binding_family_versions())
    source_id = c._nested_optional_str(request, "source_item_id", "source_item_id")
    target_id = c._nested_optional_str(request, "target_item_id", "target_item_id")
    bounded = request.get("bounded", False)
    if not isinstance(bounded, bool):
        raise SpineValidationError("invalid_request:bounded", "bounded must be boolean")
    if source_id is None and target_id is None and not bounded:
        raise SpineValidationError("missing_source_item_id", "an endpoint filter or bounded=true is required")
    mode = None if "binding_mode" not in request else c._enum(request["binding_mode"], "binding_mode", {"snapshot", "follow_source"})
    status = c._enum(request.get("binding_status", "active"), "binding_status", {"active", "retired"})
    raw_states = request.get("binding_states", list(BINDING_STATES))
    if not isinstance(raw_states, Sequence) or isinstance(raw_states, (str, bytes, bytearray)) or not raw_states:
        raise SpineValidationError("invalid_request:binding_states", "binding_states must be a non-empty array")
    states = []
    for state in raw_states:
        if state not in BINDING_STATES:
            raise SpineValidationError("invalid_request:binding_states", "binding_states contains an unsupported value")
        if state in states:
            raise SpineValidationError("invalid_request:binding_states", "binding_states must be unique")
        states.append(str(state))
    states.sort(key=BINDING_STATES.index)
    limit = _decimal_limit(request.get("limit", "100"), 1000, "limit")
    query = {
        "source_item_id": source_id,
        "target_item_id": target_id,
        "binding_mode": mode,
        "binding_status": status,
        "binding_states": states,
        "limit": str(limit),
        "bounded": bounded,
    }
    generation = binding_catalog_generation(context.ledger)
    last: list[str] | None = None
    if request.get("cursor") is not None:
        payload = _decode_cursor(str(request["cursor"]))
        if payload.get("query") != query:
            raise SpineValidationError("invalid_request:cursor", "cursor query facts do not match")
        if int(str(payload.get("binding_catalog_generation", "-1"))) != generation:
            raise SpineValidationError("stale_cursor:cursor", "binding catalog changed")
        raw_last = payload.get("last")
        if not isinstance(raw_last, list) or len(raw_last) != 4 or not all(isinstance(v, str) for v in raw_last):
            raise SpineValidationError("invalid_request:cursor", "cursor ordering tuple is invalid")
        last = raw_last
    where = ["binding_status = ?"]
    params: list[object] = [status]
    if source_id is not None:
        where.append("source_item_id = ?")
        params.append(source_id)
    if target_id is not None:
        where.append("target_item_id = ?")
        params.append(target_id)
    if mode is not None:
        where.append("binding_mode = ?")
        params.append(mode)
    rows = context.ledger.execute(
        f"SELECT temporal_binding_id FROM relative_temporal_bindings WHERE {' AND '.join(where)} ORDER BY temporal_binding_id",
        tuple(params),
    ).fetchall()
    values = [binding_view(context.ledger, str(row["temporal_binding_id"])) for row in rows]
    values = [value for value in values if value["binding_state"] in states]
    values.sort(
        key=lambda v: (
            f"{BINDING_STATES.index(str(v['binding_state'])):02d}",
            str(v["source_item_id"]),
            str(v["target_item_id"]),
            str(v["temporal_binding_id"]),
        )
    )
    if last is not None:
        values = [value for value in values if _binding_order(value) > tuple(last)]
    has_more = len(values) > limit
    page = values[:limit]
    next_cursor = None
    if has_more and page:
        next_cursor = _encode_cursor(
            {
                "cursor_version": "spine.schedule-binding-list-cursor.v1",
                "query": query,
                "binding_catalog_generation": str(generation),
                "last": list(_binding_order(page[-1])),
            }
        )
    return {
        "ok": True,
        "command": command,
        "response_contract": "spine.schedule-binding-list-response.v1",
        "binding_catalog_generation": str(generation),
        "bindings": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def handle_binding_reconcile(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    from spine.commands import core as c

    command = "schedule.binding.reconcile"
    allowed = {
        "contract_version",
        "command_id",
        "actor_subject_id",
        "reconciled_at_utc",
        "temporal_binding_id",
        "target_temporal_binding_revision_id",
        "source_target_version",
        "source_recurrence_revision_id",
        "target_target_version",
        "expected_binding_state",
        "operator_resolution",
        "materialization",
    }
    c._check_fields(command, request, allowed)
    for field in (
        "contract_version",
        "command_id",
        "actor_subject_id",
        "reconciled_at_utc",
        "temporal_binding_id",
        "target_temporal_binding_revision_id",
        "source_target_version",
        "target_target_version",
        "expected_binding_state",
        "materialization",
    ):
        if field not in request:
            raise SpineValidationError(f"missing_{field}", f"{field} is required")
    if request["contract_version"] != RECONCILE_CONTRACT:
        raise SpineValidationError("invalid_request:contract_version", f"contract_version must be {RECONCILE_CONTRACT}")
    command_id, actor, at = c._write_identity(command, request, "reconciled_at_utc", context)
    semantic = c._semantic_request(command, command_id, actor, at, request, allowed)
    replay = c._compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        return _reconcile_response(replay, "schedule_binding_reconcile_replay")
    _runtime_check(context.ledger, _reconcile_versions())
    binding_id = c._required_str(request, "temporal_binding_id")
    binding = load_temporal_binding(context.ledger, binding_id)
    revision = binding["latest_revision"]
    assert isinstance(revision, Mapping)
    if binding["binding_status"] != "active" or binding["binding_mode"] != "follow_source":
        raise SpineValidationError("invalid_state_transition:temporal_binding_id", "only active follow_source bindings can reconcile")
    if request["target_temporal_binding_revision_id"] != revision["temporal_binding_revision_id"]:
        raise SpineValidationError("stale_version:target_temporal_binding_revision_id", "binding revision is not current")
    source_current = c._hydrated_item(context.ledger, str(binding["source_item_id"]))
    target_current = c._hydrated_item(context.ledger, str(binding["target_item_id"]))
    if c._version(request, "source_target_version") != int(source_current["current_version"]):
        raise SpineValidationError("stale_version:source_target_version", "source item version is not current")
    if c._version(request, "target_target_version") != int(target_current["current_version"]):
        raise SpineValidationError("stale_version:target_target_version", "target item version is not current")
    current_recurrence = load_current_recurrence_set(context.ledger, item_id=str(binding["source_item_id"]))
    if revision["source_scope"] == "selected_occurrence" and current_recurrence is not None:
        requested_recurrence = c._required_str(request, "source_recurrence_revision_id")
        if requested_recurrence != current_recurrence["recurrence_revision_id"]:
            raise SpineValidationError("stale_version:source_recurrence_revision_id", "source recurrence revision is not current")
    elif "source_recurrence_revision_id" in request:
        raise SpineValidationError("unsupported_field:source_recurrence_revision_id", "source recurrence revision is not applicable")
    state, source = binding_state(context.ledger, binding)
    expected = c._enum(request["expected_binding_state"], "expected_binding_state", set(BINDING_STATES))
    if expected != state:
        raise SpineValidationError("stale_version:expected_binding_state", f"binding state is {state}")
    operator = request.get("operator_resolution")
    if operator is not None:
        operator = c._enum(operator, "operator_resolution", {"cancel_target", "detach_at_current_target"})
    legal_detach = {"current", "stale", "source_terminal", "source_unresolved", "target_diverged"}
    if operator == "detach_at_current_target" and state not in legal_detach:
        raise SpineValidationError("invalid_request:operator_resolution", "detach is not legal for this state")
    if operator == "cancel_target" and not (
        state == "source_unresolved" or (state == "source_terminal" and binding["source_terminal_behavior"] == "require_decision")
    ):
        raise SpineValidationError("invalid_request:operator_resolution", "cancel_target is not legal for this state")
    if state == "target_diverged" and operator != "detach_at_current_target":
        raise SpineValidationError("semantic_conflict:operator_resolution", "target divergence requires explicit detach")
    materialization = c._schedule_normalize_materialization(request["materialization"], scheduled=_scheduled_for_target(target_current))

    if operator == "detach_at_current_target":
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            materialization,
            "binding_detached",
            True,
            True,
            False,
        )
    if state == "current":
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            materialization,
            "source_unchanged",
            False,
            False,
            False,
        )
    if state == "stale":
        if source is None:
            raise SpineValidationError("runtime_failure:source", "stale binding source did not resolve")
        target = target_from_source(source, int(revision["offset_seconds"]))
        current_target = _scheduled_for_target(target_current)
        if all(
            current_target.get(k) == target.get(k)
            for k in ("local_date", "local_time", "timezone", "timezone_database_version", "utc_instant")
        ):
            return _manual_reconcile(
                context,
                binding,
                revision,
                source,
                state,
                command_id,
                actor,
                at,
                semantic,
                materialization,
                "source_refreshed",
                True,
                False,
                False,
            )
        return _versioned_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            materialization,
            target,
            "target_rescheduled",
            False,
        )
    if state == "source_terminal":
        behavior = binding["source_terminal_behavior"]
        if operator == "cancel_target" or behavior == "cancel_target":
            return _versioned_reconcile(
                context,
                binding,
                revision,
                source,
                state,
                command_id,
                actor,
                at,
                semantic,
                {"mode": "none"},
                None,
                "target_cancelled",
                True,
            )
        if behavior == "detach_at_last_value":
            return _manual_reconcile(
                context,
                binding,
                revision,
                source,
                state,
                command_id,
                actor,
                at,
                semantic,
                {"mode": "none"},
                "binding_detached",
                True,
                True,
                False,
            )
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            {"mode": "none"},
            "decision_required",
            False,
            False,
            True,
        )
    if state == "source_unresolved":
        if operator == "cancel_target":
            return _versioned_reconcile(
                context,
                binding,
                revision,
                source,
                state,
                command_id,
                actor,
                at,
                semantic,
                {"mode": "none"},
                None,
                "target_cancelled",
                True,
            )
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            {"mode": "none"},
            "decision_required",
            False,
            False,
            True,
        )
    if state == "target_terminal":
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            {"mode": "none"},
            "target_terminal_retired",
            True,
            True,
            False,
            parent_terminal=True,
        )
    if state == "relationship_inactive":
        return _manual_reconcile(
            context,
            binding,
            revision,
            source,
            state,
            command_id,
            actor,
            at,
            semantic,
            {"mode": "none"},
            "relationship_inactive_retired",
            True,
            True,
            False,
        )
    raise SpineValidationError("invalid_state_transition:temporal_binding_id", f"binding state cannot reconcile: {state}")


def _manual_reconcile(
    context: CommandContext,
    binding: Mapping[str, object],
    prior: Mapping[str, object],
    source: Mapping[str, object] | None,
    state: str,
    command_id: str,
    actor: str,
    at: str,
    semantic: Mapping[str, Any],
    materialization: Mapping[str, object],
    outcome: str,
    truth_changed: bool,
    retire: bool,
    temporal_stale: bool,
    *,
    parent_terminal: bool = False,
) -> dict[str, Any]:
    from spine.commands import core as c

    item_id = str(binding["target_item_id"])
    target_item = c._hydrated_item(context.ledger, item_id)
    target = _scheduled_for_target(target_item)
    revision = None
    if truth_changed:
        revision = _revision_value(
            command="schedule.binding.reconcile",
            command_id=command_id,
            revision_id=c._derived_id("schedule.binding.reconcile", command_id, "temporal_binding_revision", "/temporal_binding/revision"),
            binding=binding,
            prior=prior,
            revision_index=int(prior["revision_index"]) + 1,
            source=source or _source_from_prior(prior),
            source_scope=str(prior["source_scope"]),
            offset=int(prior["offset_seconds"]),
            target=target,
            target_item_version=int(target_item["current_version"]),
            target_anchor_id=str(target_item["detail"]["due_anchor_id"]),
            resolution_kind=_resolution_kind(outcome),
            created_at=at,
        )
    receipt_holder: list[dict[str, Any]] = []
    with context.ledger:
        if revision is not None:
            if source is not None:
                _refresh_selected_provenance(context.ledger, source, command_id, at, revision)
            insert_temporal_binding_revision(context.ledger, value=revision)
        if retire:
            retire_temporal_binding(
                context.ledger, temporal_binding_id=str(binding["temporal_binding_id"]), command_id=command_id, retired_at_utc=at
            )
        if truth_changed:
            increment_binding_catalog_generation(context.ledger)
        policies = [p for p in load_current_notification_policies(context.ledger, item_id=item_id) if p["status"] == "active"]
        cancelled, retained, protected, reasons = c._schedule_reconcile_work_plan(
            context.ledger,
            item_id=item_id,
            active_policies=policies,
            target_changed=False,
            recurrence_changed=False,
            temporal_binding_stale=temporal_stale,
            parent_terminal=parent_terminal,
        )
        for work_id in cancelled:
            cancel_work_instance(
                context.ledger,
                work_instance_id=work_id,
                cancelled_at_utc=at,
                reason_code=reasons[work_id],
                require_fresh=False,
            )
        created, evidence, count = c._schedule_materialize_successor(
            context.ledger,
            item_id=item_id,
            item_version=int(target_item["current_version"]),
            recurrence=None,
            policies=policies,
            policy_key_by_intent={str(p["notification_intent_id"]): str(p["notification_intent_id"]) for p in policies},
            materialization=materialization,
            command_id=command_id,
            created_at=at,
        )
        work_changed = bool(cancelled or created)
        if truth_changed or work_changed:
            c._insert_schedule_operation_audit(
                context.ledger,
                audit_id=c._derived_id("schedule.binding.reconcile", command_id, "audit", "/audit"),
                item_id=item_id,
                action="binding_reconciled" if truth_changed else "schedule_reconciled",
                reason_code=outcome,
                actor=actor,
                created_at=at,
            )
        receipt = _store_reconcile_receipt(
            context.ledger,
            binding,
            prior,
            revision,
            state,
            outcome,
            command_id,
            actor,
            at,
            semantic,
            target_version=int(target_item["current_version"]),
            truth_changed=truth_changed,
            work_changed=work_changed,
            cancelled=cancelled,
            retained=retained,
            protected=protected,
            created=created,
            materialization=c._schedule_update_materialization_facts(materialization, created, evidence, count),
        )
        receipt_holder.append(receipt)
    return _reconcile_response(receipt_holder[0], str(receipt_holder[0]["effect"]))


def _versioned_reconcile(
    context: CommandContext,
    binding: Mapping[str, object],
    prior: Mapping[str, object],
    source: Mapping[str, object] | None,
    state: str,
    command_id: str,
    actor: str,
    at: str,
    semantic: Mapping[str, Any],
    materialization: Mapping[str, object],
    target: Mapping[str, str] | None,
    outcome: str,
    cancel_target: bool,
) -> dict[str, Any]:
    from spine.commands import core as c

    item_id = str(binding["target_item_id"])
    current = c._hydrated_item(context.ledger, item_id)
    current_version = int(current["current_version"])
    next_version = current_version + 1
    new_anchor_id = str(current["detail"]["due_anchor_id"])
    anchor = None
    if target is not None:
        new_anchor_id = c._derived_id("schedule.binding.reconcile", command_id, "due_anchor", "/target/scheduled_time")
        anchor = TemporalAnchorInput(
            anchor_id=new_anchor_id,
            anchor_kind="local_instant",
            local_date=target["local_date"],
            local_time=target["local_time"],
            timezone=target["timezone"],
            timezone_database_version=target["timezone_database_version"],
        )
    target_facts = target or _scheduled_for_target(current)
    revision = _revision_value(
        command="schedule.binding.reconcile",
        command_id=command_id,
        revision_id=c._derived_id("schedule.binding.reconcile", command_id, "temporal_binding_revision", "/temporal_binding/revision"),
        binding=binding,
        prior=prior,
        revision_index=int(prior["revision_index"]) + 1,
        source=source or _source_from_prior(prior),
        source_scope=str(prior["source_scope"]),
        offset=int(prior["offset_seconds"]),
        target=target_facts,
        target_item_version=next_version,
        target_anchor_id=new_anchor_id,
        resolution_kind="source_terminal" if cancel_target else "target_rescheduled",
        created_at=at,
    )
    receipt_holder: list[dict[str, Any]] = []

    def prerequisites(connection: sqlite3.Connection, _version: int) -> None:
        if anchor is not None:
            insert_temporal_anchor(connection, anchor=anchor, anchor_id=new_anchor_id, default_created_at_utc=at)

    def extension(connection: sqlite3.Connection, version: int) -> None:
        if source is not None:
            _refresh_selected_provenance(connection, source, command_id, at, revision)
        insert_temporal_binding_revision(connection, value=revision)
        if cancel_target:
            retire_temporal_binding(
                connection, temporal_binding_id=str(binding["temporal_binding_id"]), command_id=command_id, retired_at_utc=at
            )
        increment_binding_catalog_generation(connection)
        policies = [p for p in load_current_notification_policies(connection, item_id=item_id) if p["status"] == "active"]
        cancelled, retained, protected, reasons = c._schedule_reconcile_work_plan(
            connection,
            item_id=item_id,
            active_policies=policies,
            target_changed=target is not None,
            recurrence_changed=False,
            parent_terminal=cancel_target,
        )
        for work_id in cancelled:
            cancel_work_instance(
                connection,
                work_instance_id=work_id,
                cancelled_at_utc=at,
                reason_code=reasons[work_id],
                require_fresh=False,
            )
        created, evidence, count = c._schedule_materialize_successor(
            connection,
            item_id=item_id,
            item_version=version,
            recurrence=None,
            policies=policies,
            policy_key_by_intent={str(p["notification_intent_id"]): str(p["notification_intent_id"]) for p in policies},
            materialization=materialization,
            command_id=command_id,
            created_at=at,
        )
        work_changed = bool(cancelled or created)
        receipt_holder.append(
            _store_reconcile_receipt(
                connection,
                binding,
                prior,
                revision,
                state,
                outcome,
                command_id,
                actor,
                at,
                semantic,
                target_version=version,
                truth_changed=True,
                work_changed=work_changed,
                cancelled=cancelled,
                retained=retained,
                protected=protected,
                created=created,
                materialization=c._schedule_update_materialization_facts(materialization, created, evidence, count),
            )
        )

    create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=current_version,
        created_at_utc=at,
        created_by_subject_id=actor,
        audit_id=c._derived_id("schedule.binding.reconcile", command_id, "audit", "/audit"),
        task_detail={"task_status": "cancelled"} if cancel_target else {"due_anchor_id": new_anchor_id},
        audit_action="binding_target_cancelled" if cancel_target else "binding_target_rescheduled",
        reason_code=outcome,
        insert_prerequisites=prerequisites,
        insert_canonical_extension=extension,
        supporting_command_id=command_id,
    )
    return _reconcile_response(receipt_holder[0], str(receipt_holder[0]["effect"]))


def _store_reconcile_receipt(
    connection: sqlite3.Connection,
    binding: Mapping[str, object],
    prior: Mapping[str, object],
    revision: Mapping[str, object] | None,
    state: str,
    outcome: str,
    command_id: str,
    actor: str,
    at: str,
    semantic: Mapping[str, Any],
    *,
    target_version: int,
    truth_changed: bool,
    work_changed: bool,
    cancelled: Sequence[str],
    retained: Sequence[str],
    protected: Sequence[str],
    created: Sequence[str],
    materialization: Mapping[str, object],
) -> dict[str, Any]:
    from spine.commands import core as c

    effect = _reconcile_effect(outcome, work_changed)
    facts = {
        "command_id": command_id,
        "command_receipt_id": c._receipt_id("schedule.binding.reconcile", command_id),
        "temporal_binding_id": binding["temporal_binding_id"],
        "resolution_outcome": outcome,
        "truth_changed": truth_changed,
        "work_changed": work_changed,
        "binding_state_before": state,
        "binding_state_after": "retired"
        if outcome in {"binding_detached", "target_cancelled", "target_terminal_retired", "relationship_inactive_retired"}
        else "current"
        if truth_changed
        else state,
        "prior_temporal_binding_revision_id": prior["temporal_binding_revision_id"],
        "current_temporal_binding_revision_id": (revision or prior)["temporal_binding_revision_id"],
        "source_item_id": binding["source_item_id"],
        "target_item_id": binding["target_item_id"],
        "target_item_version": str(target_version),
        "work_reconciliation": {
            "cancelled_work_instance_ids": list(cancelled),
            "retained_work_instance_ids": list(retained),
            "protected_stale_work_instance_ids": list(protected),
            "created_work_instance_ids": list(created),
        },
        "materialization": dict(materialization),
        "delivery_state": "not_attempted_by_command",
    }
    receipt = c._make_receipt(
        command="schedule.binding.reconcile",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=at,
        effect=effect,
        item_id=str(binding["target_item_id"]),
        target_version=str(
            target_version - 1 if truth_changed and outcome in {"target_rescheduled", "target_cancelled"} else target_version
        ),
        semantic_facts={**semantic, "normalized_result": facts},
        result_identity_facts=facts,
    )
    c.insert_command_receipt(connection, receipt)
    return receipt


def _revision_value(
    *,
    command: str,
    command_id: str,
    revision_id: str,
    binding: Mapping[str, object],
    prior: Mapping[str, object] | None,
    revision_index: int,
    source: Mapping[str, object],
    source_scope: str,
    offset: int,
    target: Mapping[str, str],
    target_item_version: int,
    target_anchor_id: str,
    resolution_kind: str,
    created_at: str,
) -> dict[str, object]:
    preimage = binding_revision_preimage(
        binding=binding,
        source=source,
        source_scope=source_scope,
        offset_seconds=offset,
        target=target,
        target_item_version=target_item_version,
        resolution_kind=resolution_kind,
    )
    return {
        "temporal_binding_revision_id": revision_id,
        "temporal_binding_id": binding["temporal_binding_id"],
        "revision_index": str(revision_index),
        **({"source_temporal_binding_revision_id": prior["temporal_binding_revision_id"]} if prior is not None else {}),
        "source_target_version": str(source["source_target_version"]),
        "source_scope": source_scope,
        "source_anchor_id": source.get("source_anchor_id"),
        "source_recurrence_revision_id": source.get("source_recurrence_revision_id"),
        "source_occurrence_key": source.get("source_occurrence_key"),
        "source_occurrence_selector_ref": source.get("source_occurrence_selector_ref")
        or (prior or {}).get("source_occurrence_selector_ref"),
        "source_occurrence_provenance_id": source.get("source_occurrence_provenance_id")
        or (prior or {}).get("source_occurrence_provenance_id"),
        "source_scheduled_fact": source["source_scheduled_fact"],
        "offset_basis": "elapsed",
        "offset_seconds": str(offset),
        "resolved_source_utc": source["resolved_source_utc"],
        "resolved_target_utc": target["utc_instant"],
        "target_local_date": target["local_date"],
        "target_local_time": target["local_time"],
        "target_timezone": target["timezone"],
        "target_timezone_database_version": target["timezone_database_version"],
        "target_item_version": str(target_item_version),
        "target_anchor_id": target_anchor_id,
        "resolution_kind": resolution_kind,
        "normalized_temporal_binding_revision_hash": hash_canonical_json(preimage),
        "created_by_command_id": command_id,
        "created_at_utc": created_at,
    }


def _source_from_item(item: Mapping[str, Any]) -> dict[str, object]:
    from spine.commands import core as c

    anchor = item["detail"].get("start_anchor")
    if not isinstance(anchor, Mapping):
        raise SpineValidationError("semantic_conflict:source.item_id", "source event requires an exactly timed start")
    if anchor.get("anchor_kind") == "instant_utc":
        from spine.core.schedule import system_timezone_database_version

        instant = str(anchor["utc_instant"])
        return {
            "source_target_version": str(item["current_version"]),
            "source_anchor_id": anchor["anchor_id"],
            "source_scheduled_fact": instant,
            "resolved_source_utc": instant,
            "timezone": "UTC",
            "timezone_database_version": system_timezone_database_version(),
        }
    if anchor.get("anchor_kind") != "local_instant":
        raise SpineValidationError("semantic_conflict:source.item_id", "source event requires an exactly timed start")
    resolution = c._schedule_resolve_initial_time(
        {
            "time_basis": "local_instant",
            "local_date": anchor["local_date"],
            "local_time": anchor["local_time"],
            "timezone": anchor["timezone"],
            "timezone_database_version": {"kind": "explicit", "version": anchor["timezone_database_version"]},
        }
    )
    return {
        "source_target_version": str(item["current_version"]),
        "source_anchor_id": anchor["anchor_id"],
        "source_scheduled_fact": f"{anchor['local_date']}T{anchor['local_time']}",
        "resolved_source_utc": resolution["utc_instant"],
        "timezone": anchor["timezone"],
        "timezone_database_version": anchor["timezone_database_version"],
    }


def _source_from_occurrence(recurrence: Mapping[str, object], occurrence: Mapping[str, object]) -> dict[str, object]:
    if recurrence["time_basis"] == "instant_utc":
        from spine.core.schedule import system_timezone_database_version

        return {
            "source_target_version": recurrence["source_item_version"],
            "source_scheduled_fact": occurrence["original_scheduled_fact"],
            "resolved_source_utc": occurrence["expressed_scheduled_fact"],
            "timezone": "UTC",
            "timezone_database_version": system_timezone_database_version(),
        }
    resolution = occurrence.get("timezone_resolution")
    if not isinstance(resolution, Mapping):
        raise SpineValidationError("semantic_conflict:source.target_occurrence_key", "selected occurrence has no UTC resolution")
    return {
        "source_target_version": recurrence["source_item_version"],
        "source_scheduled_fact": occurrence["original_scheduled_fact"],
        "resolved_source_utc": resolution["utc_instant"],
        "timezone": recurrence["timezone"],
        "timezone_database_version": recurrence["timezone_database_version"],
    }


def _source_from_prior(prior: Mapping[str, object]) -> dict[str, object]:
    return {
        "source_target_version": prior["source_target_version"],
        "source_anchor_id": prior.get("source_anchor_id"),
        "source_recurrence_revision_id": prior.get("source_recurrence_revision_id"),
        "source_occurrence_key": prior.get("source_occurrence_key"),
        "source_occurrence_selector_ref": prior.get("source_occurrence_selector_ref"),
        "source_occurrence_provenance_id": prior.get("source_occurrence_provenance_id"),
        "target_occurrence_selector": prior.get("target_occurrence_selector"),
        "source_scheduled_fact": prior["source_scheduled_fact"],
        "resolved_source_utc": prior["resolved_source_utc"],
        "timezone": prior["target_timezone"],
        "timezone_database_version": prior["target_timezone_database_version"],
    }


def _scheduled_for_target(item: Mapping[str, Any]) -> dict[str, str]:
    from spine.commands import core as c

    anchor = item["detail"].get("due_anchor")
    if not isinstance(anchor, Mapping) or anchor.get("anchor_kind") != "local_instant":
        raise SpineValidationError("semantic_conflict:target_item_id", "target task has no local-instant due anchor")
    resolved = c._schedule_resolve_initial_time(
        {
            "time_basis": "local_instant",
            "local_date": anchor["local_date"],
            "local_time": anchor["local_time"],
            "timezone": anchor["timezone"],
            "timezone_database_version": {"kind": "explicit", "version": anchor["timezone_database_version"]},
        }
    )
    return {
        "local_date": str(anchor["local_date"]),
        "local_time": str(anchor["local_time"]),
        "timezone": str(anchor["timezone"]),
        "timezone_database_version": str(anchor["timezone_database_version"]),
        "utc_instant": str(resolved["utc_instant"]),
        "resolution_kind": "unambiguous",
        "offset_seconds": str(resolved["offset_seconds"]),
    }


def _persist_provenance(connection: sqlite3.Connection, derived: DerivedOccurrenceProvenance, *, command_id: str, at: str) -> None:
    current = active_provenance_for_slot(connection, slot_key=str(derived.value["occurrence_provenance_slot_key"]))
    if current is not None and current["content_hash"] == derived.value["content_hash"]:
        return
    if current is not None:
        supersede_occurrence_provenance(
            connection,
            occurrence_provenance_id=str(current["occurrence_provenance_id"]),
            command_id=command_id,
            superseded_at_utc=at,
            replacement_occurrence_provenance_id=str(derived.value["occurrence_provenance_id"]),
        )
    insert_occurrence_provenance(connection, derived=derived)


def _refresh_selected_provenance(
    connection: sqlite3.Connection, source: Mapping[str, object], command_id: str, at: str, revision: dict[str, object]
) -> None:
    recurrence = source.get("recurrence")
    occurrence = source.get("occurrence")
    if not isinstance(recurrence, Mapping) or not isinstance(occurrence, Mapping):
        return
    from spine.commands import core as c

    item = c._hydrated_item(connection, str(recurrence["source_item_id"]))
    scheduled = str(source["target_occurrence_selector"]["scheduled_fact"])  # type: ignore[index]
    derived = derive_occurrence_provenance(
        occurrence=occurrence,
        recurrence=recurrence,
        item=item,
        consumer="temporal_binding",
        producer="schedule.binding.reconcile",
        range_basis="original_schedule",
        range_start=scheduled,
        range_end=c._next_scheduled_fact(scheduled, time_basis=str(recurrence["time_basis"])),
        created_at_utc=at,
    )
    _persist_provenance(connection, derived, command_id=command_id, at=at)
    revision["source_occurrence_provenance_id"] = derived.value["occurrence_provenance_id"]
    revision["source_occurrence_selector_ref"] = "recurrence_target_selector_" + hash_canonical_json(source["target_occurrence_selector"])


def _policy_fact(key: str, value: Mapping[str, object]) -> dict[str, object]:
    return {
        "policy_key": key,
        "notification_intent_id": value["notification_intent_id"],
        "notification_policy_id": value["notification_policy_id"],
        "notification_schedule_id": value["notification_schedule_id"],
        "normalized_notification_schedule_hash": value["normalized_notification_schedule_hash"],
        "status": value["status"],
    }


def _create_response(receipt: Mapping[str, Any], effect: str) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "schedule.related_task.create",
        "response_contract": "spine.schedule-related-task-create-response.v1",
        "effect": effect,
        **dict(receipt["result_identity_facts"]),
        "receipt": {
            "receipt_contract": "spine.schedule-related-task-create-receipt.v1",
            "command_receipt_id": receipt["command_receipt_id"],
            "effect": receipt["effect"],
            "semantic_facts_hash": receipt["semantic_facts_hash"],
            "created_at_utc": receipt["created_at_utc"],
        },
    }


def _reconcile_response(receipt: Mapping[str, Any], effect: str) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "schedule.binding.reconcile",
        "response_contract": "spine.schedule-binding-reconcile-response.v1",
        "effect": effect,
        **dict(receipt["result_identity_facts"]),
        "receipt": {
            "receipt_contract": "spine.schedule-binding-reconcile-receipt.v1",
            "command_receipt_id": receipt["command_receipt_id"],
            "effect": receipt["effect"],
            "semantic_facts_hash": receipt["semantic_facts_hash"],
            "created_at_utc": receipt["created_at_utc"],
        },
    }


def _reconcile_effect(outcome: str, work: bool) -> str:
    base = {
        "target_rescheduled": "binding_target_rescheduled",
        "source_refreshed": "binding_source_refreshed",
        "source_unchanged": "binding_reconcile_noop",
        "target_cancelled": "binding_target_cancelled",
        "binding_detached": "binding_detached",
        "target_terminal_retired": "binding_target_terminal_retired",
        "relationship_inactive_retired": "binding_relationship_inactive_retired",
        "decision_required": "binding_decision_required",
    }[outcome]
    if not work:
        return base
    return "binding_work_reconciled" if outcome == "source_unchanged" else base + "_and_work_reconciled"


def _resolution_kind(outcome: str) -> str:
    return {
        "source_refreshed": "source_refreshed",
        "binding_detached": "detached",
        "target_terminal_retired": "target_terminal",
        "relationship_inactive_retired": "relationship_inactive",
    }.get(outcome, "source_refreshed")


def _runtime_check(connection: sqlite3.Connection, required: set[str]) -> None:
    from spine.ledger.migrate import current_schema_version

    if current_schema_version(connection) != IMPLEMENTED_LEDGER_SCHEMA_VERSION:
        raise SpineValidationError(
            "environment_failure:ledger_schema_version", f"binding commands require schema {IMPLEMENTED_LEDGER_SCHEMA_VERSION}"
        )
    if not required.issubset(IMPLEMENTED_CONTRACT_VERSIONS):
        raise SpineValidationError(
            "environment_failure:contract_version", "runtime does not advertise the complete binding contract family"
        )


def _injected_failure(context: CommandContext, phase: str) -> None:
    if context.transport_metadata.get("related_task_create_fail_after") == phase:
        raise SpineValidationError("runtime_failure:injected", f"injected related-task failure after {phase}")


def _create_versions() -> set[str]:
    return _binding_family_versions()


def _reconcile_versions() -> set[str]:
    return _binding_family_versions()


def _binding_family_versions() -> set[str]:
    return {
        "spine.relative-temporal-binding.v1",
        "spine.relative-temporal-binding-normalization.v1",
        "spine.normalized-temporal-binding-revision-hash.v1",
        "spine.temporal-binding-catalog.v1",
        CREATE_CONTRACT,
        "spine.schedule-related-task-create-response.v1",
        "spine.schedule-related-task-create-receipt.v1",
        LIST_CONTRACT,
        "spine.schedule-binding-list-response.v1",
        "spine.schedule-binding-list-cursor.v1",
        RECONCILE_CONTRACT,
        "spine.schedule-binding-reconcile-response.v1",
        "spine.schedule-binding-reconcile-receipt.v1",
    }


def _decimal_limit(value: object, maximum: int, field: str) -> int:
    if not isinstance(value, str) or not value.isdigit() or not 1 <= int(value) <= maximum:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a decimal string in 1..{maximum}")
    return int(value)


def _binding_order(value: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        f"{BINDING_STATES.index(str(value['binding_state'])):02d}",
        str(value["source_item_id"]),
        str(value["target_item_id"]),
        str(value["temporal_binding_id"]),
    )


def _encode_cursor(payload: Mapping[str, object]) -> str:
    raw = canonical_json_bytes(payload)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=") + "." + hash_canonical_json(payload)


def _decode_cursor(value: str) -> dict[str, object]:
    try:
        encoded, digest = value.split(".", 1)
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        import json

        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SpineValidationError("invalid_request:cursor", "cursor is malformed") from exc
    if (
        not isinstance(payload, dict)
        or canonical_json_bytes(payload) != raw
        or hash_canonical_json(payload) != digest
        or payload.get("cursor_version") != "spine.schedule-binding-list-cursor.v1"
    ):
        raise SpineValidationError("invalid_request:cursor", "cursor does not verify")
    return payload
