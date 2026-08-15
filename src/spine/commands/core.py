"""Transport-neutral dispatcher for the Spine agent command contract MVP."""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION, __version__
from spine.commands.context import CommandContext
from spine.commands.receipts import (
    command_derived_id,
    command_receipt,
    get_command_receipt,
    insert_command_receipt,
)
from spine.commands.responses import (
    event_reschedule_response,
    event_update_response,
    item_list_response,
    item_show_response,
    task_update_response,
)
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import audit_log_payload_hash, hash_canonical_json
from spine.core.notifications import (
    NormalizedNotificationPolicy,
    expand_notification_policy,
    normalize_notification_policy,
    notification_id,
    revise_notification_policy,
)
from spine.core.occurrences import expand_recurrence_set
from spine.core.provenance import derive_occurrence_provenance, recurrence_set_identity_preimage
from spine.core.recurrence_mutations import (
    build_successor_recurrence_revision,
    derive_recurrence_lineage,
)
from spine.core.recurrence_set import (
    NormalizedRecurrenceSet,
    generated_id,
    normalize_initial_recurrence_set,
)
from spine.core.schedule import (
    expand_rule,
    normalize_rule,
    parse_scheduled_fact,
    resolve_local_instant,
    system_timezone_database_version,
)
from spine.ledger.common import TemporalAnchorInput, insert_temporal_anchor, require_utc_z
from spine.ledger.item_drafts import _UNSET
from spine.ledger.items import (
    archive_item,
    cancel_event,
    cancel_task,
    complete_task,
    create_event_v1,
    create_next_item_version,
    create_task_v1,
    get_current_item,
)
from spine.ledger.migrate import current_schema_version
from spine.ledger.notifications import (
    insert_notification_schedule_policy,
    load_current_notification_policies,
    persist_notification_target_selector,
    remove_copied_notification_policy,
)
from spine.ledger.provenance import (
    active_provenance_for_range,
    active_provenance_for_slot,
    close_recoverable_provenance_reports,
    insert_occurrence_provenance,
    supersede_occurrence_provenance,
)
from spine.ledger.recurrence import (
    insert_initial_recurrence_set,
    insert_recurrence_lineage,
    load_current_recurrence_set,
    load_target_occurrence_selector,
    persist_target_occurrence_selector,
)
from spine.ledger.relations import create_item_relation
from spine.ledger.supporting import (
    ItemSubjectRoleInput,
    current_locations,
    current_notification_policies,
    current_subject_roles,
)
from spine.ledger.work import create_work_instance

MVP_COMMANDS = frozenset(
    {
        "subject.upsert",
        "subject_group.upsert",
        "delivery_target.upsert",
        "system.info",
        "item.show",
        "item.list",
        "item.occurrences",
        "item.archive",
        "event.create",
        "event.update",
        "event.reschedule",
        "event.cancel",
        "task.create",
        "schedule.create",
        "schedule.show",
        "task.update",
        "task.complete",
        "task.cancel",
        "relation.create",
        "relation.list",
        "reminder.create",
        "reminder.edit",
        "reminder.disable",
        "notification.opportunities",
        "occurrence_provenance.regenerate",
        "notification_work.materialize",
        "recurrence.instance.add",
        "recurrence.instance.remove",
        "recurrence.instance.override",
        "recurrence.series.edit",
    }
)

WRITE_COMMANDS = MVP_COMMANDS - {
    "item.show",
    "schedule.show",
    "item.list",
    "item.occurrences",
    "relation.list",
    "notification.opportunities",
    "system.info",
}


def handle(command: str, request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    """Dispatch the MVP command-core interface."""

    if command not in MVP_COMMANDS:
        return _error(command, "unsupported_command", f"unsupported command: {command}", "command")
    if not isinstance(request, Mapping):
        return _error(command, "invalid_request", "request must be a JSON object", "request")
    if context.ledger is None:
        return _error(command, "invalid_request", f"{command} requires CommandContext.ledger", "ledger")
    try:
        if context.dry_run and command in WRITE_COMMANDS:
            preview = sqlite3.connect(":memory:")
            preview.row_factory = sqlite3.Row
            context.ledger.backup(preview)
            try:
                preview_context = CommandContext(
                    ledger=preview,
                    ledger_path=context.ledger_path,
                    dry_run=context.dry_run,
                    transport_metadata=context.transport_metadata,
                    correlation_id=context.correlation_id,
                    adapter_bindings=context.adapter_bindings,
                    delivery_target_defaults=context.delivery_target_defaults,
                )
                result = _dispatch(command, request, preview_context)
            finally:
                preview.close()
            result["dry_run"] = True
            return result
        return _dispatch(command, request, context)
    except SpineValidationError as exc:
        response = _validation_error(command, exc)
        if context.dry_run and command in WRITE_COMMANDS:
            response["dry_run"] = True
        return response
    except sqlite3.IntegrityError as exc:
        response = _error(command, "semantic_conflict", str(exc), "request")
        if context.dry_run and command in WRITE_COMMANDS:
            response["dry_run"] = True
        return response


def _dispatch(command: str, request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    if command == "subject.upsert":
        return _handle_subject_upsert(request, context)
    if command == "subject_group.upsert":
        return _handle_subject_group_upsert(request, context)
    if command == "delivery_target.upsert":
        return _handle_delivery_target_upsert(request, context)
    if command == "system.info":
        return _handle_system_info(request, context)
    if command == "item.show":
        return _handle_item_show(request, context)
    if command == "schedule.show":
        return _handle_schedule_show(request, context)
    if command == "item.list":
        return _handle_item_list(request, context)
    if command == "item.occurrences":
        return _handle_item_occurrences(request, context)
    if command == "event.create":
        return _handle_event_create(request, context)
    if command == "task.create":
        return _handle_task_create(request, context)
    if command == "schedule.create":
        return _handle_schedule_create(request, context)
    if command == "event.update":
        return _handle_common_update("event.update", "event", request, context)
    if command == "task.update":
        return _handle_common_update("task.update", "task", request, context)
    if command == "event.reschedule":
        return _handle_event_reschedule(request, context)
    if command == "event.cancel":
        return _handle_event_cancel(request, context)
    if command == "task.complete":
        return _handle_task_complete(request, context)
    if command == "task.cancel":
        return _handle_task_cancel(request, context)
    if command == "item.archive":
        return _handle_item_archive(request, context)
    if command == "relation.create":
        return _handle_relation_create(request, context)
    if command == "relation.list":
        return _handle_relation_list(request, context)
    if command == "reminder.create":
        return _handle_reminder_create(request, context)
    if command == "reminder.edit":
        return _handle_reminder_edit(request, context)
    if command == "reminder.disable":
        return _handle_reminder_disable(request, context)
    if command == "notification.opportunities":
        return _handle_notification_opportunities(request, context)
    if command == "occurrence_provenance.regenerate":
        return _handle_occurrence_provenance_regenerate(request, context)
    if command == "notification_work.materialize":
        return _handle_notification_work_materialize(request, context)
    if command in {
        "recurrence.instance.add",
        "recurrence.instance.remove",
        "recurrence.instance.override",
    }:
        return _handle_recurrence_instance_mutation(command, request, context)
    if command == "recurrence.series.edit":
        return _handle_recurrence_series_edit(request, context)
    return _error(command, "unsupported_command", f"unsupported command: {command}", "command")


def _handle_subject_upsert(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields(
        "subject.upsert",
        request,
        {"command_id", "actor_subject_id", "subject_id", "subject_kind", "display_name", "status", "updated_at_utc"},
    )
    command_id = _required_str(request, "command_id")
    actor_subject_id = _required_str(request, "actor_subject_id")
    subject_id = _required_str(request, "subject_id")
    subject_kind = _enum(request.get("subject_kind"), "subject_kind", {"person", "agent"})
    display_name = _required_str(request, "display_name")
    status = _enum(request.get("status", "active"), "status", {"active", "inactive"})
    updated_at_utc = _timestamp(request, "updated_at_utc")
    semantic_facts = {
        "command": "subject.upsert",
        "command_id": command_id,
        "actor_subject_id": actor_subject_id,
        "action_timestamp_utc": updated_at_utc,
        "subject_id": subject_id,
        "subject_kind": subject_kind,
        "display_name": display_name,
        "status": status,
    }
    replay = _compatible_replay("subject.upsert", command_id, semantic_facts, context)
    if replay is not None:
        subject = _subject(context.ledger, subject_id)
        response = _subject_response(subject, created=False, updated=False, receipt_id=replay["command_receipt_id"])
        return response
    if not _subject_exists(context.ledger, actor_subject_id):
        count = context.ledger.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        if not (count == 0 and actor_subject_id == subject_id):
            return _error("subject.upsert", "referenced_row_not_found", "actor subject not found", "actor_subject_id")
    existing = _subject(context.ledger, subject_id, required=False)
    created = existing is None
    updated = created or any(
        existing[key] != value for key, value in {"subject_kind": subject_kind, "display_name": display_name, "status": status}.items()
    )
    effect = "subject_created" if created else "subject_updated" if updated else "subject_noop"
    receipt = _make_receipt(
        command="subject.upsert",
        command_id=command_id,
        actor_subject_id=actor_subject_id,
        action_timestamp_utc=updated_at_utc,
        effect=effect,
        semantic_facts={**semantic_facts, "created": created, "updated": updated},
        result_identity_facts={
            "command_receipt_id": _receipt_id("subject.upsert", command_id),
            "subject_id": subject_id,
            "created": created,
            "updated": updated,
        },
    )
    with context.ledger:
        if created:
            context.ledger.execute(
                """
                INSERT INTO subjects (
                  subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (subject_id, subject_kind, display_name, status, updated_at_utc, updated_at_utc),
            )
        elif updated:
            context.ledger.execute(
                """
                UPDATE subjects
                SET subject_kind = ?, display_name = ?, status = ?, updated_at_utc = ?
                WHERE subject_id = ?
                """,
                (subject_kind, display_name, status, updated_at_utc, subject_id),
            )
        insert_command_receipt(context.ledger, receipt)
    return _subject_response(
        _subject(context.ledger, subject_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"]
    )


def _handle_subject_group_upsert(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields(
        "subject_group.upsert",
        request,
        {"command_id", "actor_subject_id", "group_id", "group_kind", "display_name", "status", "updated_at_utc"},
    )
    command_id, actor, updated_at_utc = _write_identity("subject_group.upsert", request, "updated_at_utc", context)
    group_id = _required_str(request, "group_id")
    group_kind = _enum(request.get("group_kind"), "group_kind", {"household", "project", "team", "transport_group"})
    display_name = _required_str(request, "display_name")
    status = _enum(request.get("status", "active"), "status", {"active", "inactive"})
    semantic_facts = {
        "command": "subject_group.upsert",
        "command_id": command_id,
        "actor_subject_id": actor,
        "action_timestamp_utc": updated_at_utc,
        "group_id": group_id,
        "group_kind": group_kind,
        "display_name": display_name,
        "status": status,
    }
    replay = _compatible_replay("subject_group.upsert", command_id, semantic_facts, context)
    if replay is not None:
        return _subject_group_response(
            _subject_group(context.ledger, group_id), created=False, updated=False, receipt_id=replay["command_receipt_id"]
        )
    existing = _subject_group(context.ledger, group_id, required=False)
    created = existing is None
    updated = created or any(
        existing[key] != value for key, value in {"group_kind": group_kind, "display_name": display_name, "status": status}.items()
    )
    effect = "subject_group_created" if created else "subject_group_updated" if updated else "subject_group_noop"
    receipt = _make_receipt(
        command="subject_group.upsert",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=updated_at_utc,
        effect=effect,
        semantic_facts={**semantic_facts, "created": created, "updated": updated},
        result_identity_facts={
            "command_receipt_id": _receipt_id("subject_group.upsert", command_id),
            "group_id": group_id,
            "created": created,
            "updated": updated,
        },
    )
    with context.ledger:
        if created:
            context.ledger.execute(
                """
                INSERT INTO subject_groups (
                  group_id, group_kind, display_name, status, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (group_id, group_kind, display_name, status, updated_at_utc, updated_at_utc),
            )
        elif updated:
            context.ledger.execute(
                """
                UPDATE subject_groups
                SET group_kind = ?, display_name = ?, status = ?, updated_at_utc = ?
                WHERE group_id = ?
                """,
                (group_kind, display_name, status, updated_at_utc, group_id),
            )
        insert_command_receipt(context.ledger, receipt)
    return _subject_group_response(
        _subject_group(context.ledger, group_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"]
    )


def _handle_system_info(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    """Report the exact local authority versions needed for safe authoring."""

    _check_fields("system.info", request, set())
    ledger_version = current_schema_version(context.ledger)
    if ledger_version != IMPLEMENTED_LEDGER_SCHEMA_VERSION:
        raise SpineValidationError(
            "environment_failure:ledger_schema_version",
            f"runtime requires ledger schema {IMPLEMENTED_LEDGER_SCHEMA_VERSION}; found {ledger_version}",
        )
    return {
        "ok": True,
        "command": "system.info",
        "response_contract": "spine.system-info.v1",
        "runtime_version": __version__,
        "implemented_ledger_schema_version": str(IMPLEMENTED_LEDGER_SCHEMA_VERSION),
        "ledger_schema_version": str(ledger_version),
        "timezone_database_version": system_timezone_database_version(),
        "implemented_contract_versions": sorted(IMPLEMENTED_CONTRACT_VERSIONS),
    }


def _handle_delivery_target_upsert(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "delivery_target_id",
        "owner_kind",
        "owner_subject_id",
        "owner_group_id",
        "channel",
        "adapter_name",
        "account_id",
        "target_ref",
        "display_name",
        "status",
        "updated_at_utc",
    }
    _check_fields("delivery_target.upsert", request, allowed)
    command_id, actor, updated_at_utc = _write_identity("delivery_target.upsert", request, "updated_at_utc", context)
    delivery_target_id = _required_str(request, "delivery_target_id")
    owner_kind = _enum(request.get("owner_kind"), "owner_kind", {"subject", "subject_group"})
    owner_subject_id = _optional_str(request, "owner_subject_id")
    owner_group_id = _optional_str(request, "owner_group_id")
    channel = _required_str(request, "channel")
    adapter_name = _required_str(request, "adapter_name")
    account_id = _optional_str(request, "account_id")
    target_ref = _required_str(request, "target_ref")
    display_name = _optional_str(request, "display_name")
    status = _enum(request.get("status", "active"), "status", {"active", "inactive"})
    if owner_kind == "subject":
        if owner_subject_id is None or owner_group_id is not None:
            return _error("delivery_target.upsert", "invalid_request", "subject target requires owner_subject_id only", "owner_subject_id")
        if not _subject_exists(context.ledger, owner_subject_id):
            return _error("delivery_target.upsert", "referenced_row_not_found", "owner subject not found", "owner_subject_id")
    else:
        if owner_group_id is None or owner_subject_id is not None:
            return _error("delivery_target.upsert", "invalid_request", "group target requires owner_group_id only", "owner_group_id")
        if not _subject_group_exists(context.ledger, owner_group_id):
            return _error("delivery_target.upsert", "referenced_row_not_found", "owner group not found", "owner_group_id")
    semantic_facts = _semantic_request("delivery_target.upsert", command_id, actor, updated_at_utc, request, allowed)
    replay = _compatible_replay("delivery_target.upsert", command_id, semantic_facts, context)
    if replay is not None:
        return _delivery_target_response(
            _delivery_target(context.ledger, delivery_target_id), created=False, updated=False, receipt_id=replay["command_receipt_id"]
        )
    existing = _delivery_target(context.ledger, delivery_target_id, required=False)
    created = existing is None
    desired = {
        "owner_kind": owner_kind,
        "owner_subject_id": owner_subject_id,
        "owner_group_id": owner_group_id,
        "channel": channel,
        "adapter_name": adapter_name,
        "account_id": account_id,
        "target_ref": target_ref,
        "display_name": display_name,
        "status": status,
    }
    if (
        existing is not None
        and _delivery_target_routing_changed(existing, desired)
        and _delivery_target_in_use(context.ledger, delivery_target_id)
    ):
        return _error(
            "delivery_target.upsert", "semantic_conflict", "delivery target routing cannot change while referenced", "delivery_target_id"
        )
    updated = created or any(existing[key] != value for key, value in desired.items())
    effect = "delivery_target_created" if created else "delivery_target_updated" if updated else "delivery_target_noop"
    receipt = _make_receipt(
        command="delivery_target.upsert",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=updated_at_utc,
        effect=effect,
        semantic_facts={**semantic_facts, "created": created, "updated": updated},
        result_identity_facts={
            "command_receipt_id": _receipt_id("delivery_target.upsert", command_id),
            "delivery_target_id": delivery_target_id,
            "created": created,
            "updated": updated,
        },
    )
    with context.ledger:
        if created:
            context.ledger.execute(
                """
                INSERT INTO delivery_targets (
                  delivery_target_id, owner_kind, owner_subject_id, owner_group_id, channel,
                  adapter_name, account_id, target_ref, display_name, status, created_at_utc,
                  updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_target_id,
                    owner_kind,
                    owner_subject_id,
                    owner_group_id,
                    channel,
                    adapter_name,
                    account_id,
                    target_ref,
                    display_name,
                    status,
                    updated_at_utc,
                    updated_at_utc,
                ),
            )
        elif updated:
            context.ledger.execute(
                """
                UPDATE delivery_targets
                SET owner_kind = ?, owner_subject_id = ?, owner_group_id = ?, channel = ?,
                    adapter_name = ?, account_id = ?, target_ref = ?, display_name = ?,
                    status = ?, updated_at_utc = ?
                WHERE delivery_target_id = ?
                """,
                (
                    owner_kind,
                    owner_subject_id,
                    owner_group_id,
                    channel,
                    adapter_name,
                    account_id,
                    target_ref,
                    display_name,
                    status,
                    updated_at_utc,
                    delivery_target_id,
                ),
            )
        insert_command_receipt(context.ledger, receipt)
    return _delivery_target_response(
        _delivery_target(context.ledger, delivery_target_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"]
    )


def _handle_item_show(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields(
        "item.show",
        request,
        {"item_id", "include_relations", "locations_limit", "subject_roles_limit", "notification_policies_limit", "relations_limit"},
    )
    item_id = _required_str(request, "item_id")
    item = _hydrated_item(context.ledger, item_id)
    include_relations = bool(request.get("include_relations", False))
    locations_limit = _limit(request.get("locations_limit", 50))
    subject_roles_limit = _limit(request.get("subject_roles_limit", 50))
    notification_policies_limit = _limit(request.get("notification_policies_limit", 50))
    relations_limit = _limit(request.get("relations_limit", 50))
    locations = _limit_sequence(item.get("locations", ()), locations_limit)
    subject_roles = _limit_sequence(item.get("subject_roles", ()), subject_roles_limit)
    notification_policies = _limit_sequence(item.get("notification_policies", ()), notification_policies_limit)
    shown_item = {
        **item,
        "locations": locations[0],
        "subject_roles": subject_roles[0],
        "notification_policies": notification_policies[0],
    }
    relations: tuple[list[dict[str, Any]], bool] = ([], False)
    if include_relations:
        relations = _limit_sequence(_relations_for_item(context.ledger, item_id), relations_limit)
    return item_show_response(
        shown_item,
        include_relations=include_relations,
        relations=relations[0],
        locations_limit=str(locations_limit),
        locations_truncated=locations[1],
        subject_roles_limit=str(subject_roles_limit),
        subject_roles_truncated=subject_roles[1],
        notification_policies_limit=str(notification_policies_limit),
        notification_policies_truncated=notification_policies[1],
        relations_limit=str(relations_limit),
        relations_truncated=relations[1],
    )


def _handle_schedule_show(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    from spine.services.schedule_readback import build_schedule_readback

    _check_fields(
        "schedule.show",
        request,
        {"item_id", "include", "notification_policies_limit", "work_instances_limit", "side_effect_attempts_limit"},
    )
    item_id = _required_str(request, "item_id")
    raw_include = request.get("include", ["policies", "work", "attempts"])
    if not isinstance(raw_include, Sequence) or isinstance(raw_include, (str, bytes, bytearray)):
        raise SpineValidationError("invalid_request:include", "include must be an array")
    include_values: list[str] = []
    for value in raw_include:
        if not isinstance(value, str) or value not in {"policies", "work", "attempts"}:
            raise SpineValidationError(
                "invalid_request:include",
                "include values must be policies, work, or attempts",
            )
        include_values.append(value)
    if len(include_values) != len(set(include_values)):
        raise SpineValidationError("invalid_request:include", "include values must be unique")
    policies_limit = _limit(request.get("notification_policies_limit", 100))
    work_limit = _schedule_show_limit(request.get("work_instances_limit", 1000), "work_instances_limit")
    attempts_limit = _schedule_show_limit(request.get("side_effect_attempts_limit", 1000), "side_effect_attempts_limit")
    item = _hydrated_item(context.ledger, item_id)
    item_response = item_show_response(item, notification_policies_limit="0")
    item_view = {
        key: value
        for key, value in item_response.items()
        if key
        not in {
            "ok",
            "command",
            "notification_policies",
            "notification_policies_limit",
            "notification_policies_truncated",
        }
    }
    return build_schedule_readback(
        context.ledger,
        item=item,
        item_view=item_view,
        include=frozenset(include_values),
        policies_limit=policies_limit,
        work_limit=work_limit,
        attempts_limit=attempts_limit,
    )


def _handle_item_list(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields("item.list", request, {"item_type", "status", "include_archived", "limit"})
    limit = _limit(request.get("limit", 50))
    item_type = request.get("item_type")
    status = request.get("status")
    if status is not None and "include_archived" in request:
        return _error("item.list", "invalid_request", "status and include_archived are mutually exclusive", "include_archived")
    include_archived = bool(request.get("include_archived", False))
    if item_type is not None:
        item_type = _enum(item_type, "item_type", {"event", "task", "project", "collection"})
    if status is not None:
        status = _enum(status, "status", {"active", "archived"})
    where = []
    params: list[Any] = []
    if item_type is not None:
        where.append("item_type = ?")
        params.append(item_type)
    if status is not None:
        where.append("status = ?")
        params.append(status)
    elif not include_archived:
        where.append("status = 'active'")
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = context.ledger.execute(
        f"""
        SELECT item_id
        FROM coordination_items
        {clause}
        ORDER BY updated_at_utc DESC, item_id ASC
        LIMIT ?
        """,
        (*params, limit + 1),
    ).fetchall()
    truncated = len(rows) > limit
    items = [_hydrated_item(context.ledger, row["item_id"]) for row in rows[:limit]]
    return item_list_response(items, limit=str(limit), truncated=truncated)


def _handle_item_occurrences(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields(
        "item.occurrences",
        request,
        {"item_id", "range_start", "range_end", "limit", "cursor", "range_basis", "include_diagnostics"},
    )
    item_id = _required_str(request, "item_id")
    range_start = _required_str(request, "range_start")
    range_end = _required_str(request, "range_end")
    limit = _occurrence_limit(request.get("limit", "100"))
    range_basis = _enum(request.get("range_basis", "original_schedule"), "range_basis", {"original_schedule", "expressed_time"})
    include_diagnostics = request.get("include_diagnostics", False)
    if not isinstance(include_diagnostics, bool):
        raise SpineValidationError("invalid_request:include_diagnostics", "include_diagnostics must be boolean")
    item = _hydrated_item(context.ledger, item_id)
    if item["item_type"] not in {"event", "task"}:
        raise SpineValidationError(
            "unsupported_recurrence_item",
            "item.occurrences supports event and task items",
        )
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    if recurrence is None:
        raise SpineValidationError("recurrence_not_configured", f"{item['item_type']} item has no recurrence set")
    expanded = expand_recurrence_set(
        recurrence,
        range_start=range_start,
        range_end=range_end,
        range_basis=range_basis,
        include_diagnostics=include_diagnostics,
    )
    cursor_facts = _recurrence_cursor_facts(
        item=item,
        recurrence=recurrence,
        range_basis=range_basis,
        range_start=range_start,
        range_end=range_end,
        limit=str(limit),
        include_diagnostics=include_diagnostics,
    )
    last_tuple = _decode_recurrence_cursor(request.get("cursor"), expected=cursor_facts)
    decorated = [_decorate_occurrence(item, recurrence, dict(value)) for value in expanded.occurrences]
    if last_tuple is not None:
        decorated = [value for value in decorated if list(_occurrence_ordering_tuple(value, range_basis)) > last_tuple]
    page = decorated[: limit + 1]
    has_more = len(page) > limit
    occurrences = page[:limit]
    next_cursor = None
    if has_more:
        next_cursor = _encode_recurrence_cursor(
            {**cursor_facts, "last_ordering_tuple": list(_occurrence_ordering_tuple(occurrences[-1], range_basis))}
        )
    diagnostics = list(expanded.diagnostics)
    if include_diagnostics and has_more:
        diagnostics.append(
            {
                "severity": "info",
                "diagnostic_code": "pagination_observation",
                "field": "limit",
                "message": "additional occurrences are available",
            }
        )
    response = {
        "ok": True,
        "command": "item.occurrences",
        "response_contract": "spine.item-occurrences.recurrence.v1",
        "item_id": item_id,
        "item_type": item["item_type"],
        "current_version": str(item["current_version"]),
        "source_item_version": recurrence["source_item_version"],
        "status": item["status"],
        "title": item["version"]["title"],
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "revision_number": recurrence["revision_number"],
        "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
        "time_basis": recurrence["time_basis"],
        "range_basis": range_basis,
        "range_start": range_start,
        "range_end": range_end,
        "limit": str(limit),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "occurrences": occurrences,
        "diagnostics": diagnostics,
    }
    if recurrence.get("timezone") is not None:
        response["timezone"] = recurrence["timezone"]
        response["timezone_database_version"] = recurrence["timezone_database_version"]
    if item["status"] == "archived":
        response["archived_at_utc"] = item["archived_at_utc"]
    return response


def _handle_event_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "title",
        "summary",
        "source_ref",
        "all_day",
        "start_anchor",
        "end_anchor",
        "visibility",
        "attendance_policy_ref",
    }
    _check_fields("event.create", request, allowed)
    command_id, actor, created_at = _write_identity("event.create", request, "created_at_utc", context)
    title = _required_str(request, "title")
    all_day = _required_bool(request, "all_day")
    start_anchor = _anchor_input(
        request.get("start_anchor"),
        "start_anchor",
        _derived_id("event.create", command_id, "start_anchor", "/start_anchor"),
        allow_recurrence=True,
    )
    end_anchor = None
    if request.get("end_anchor") is not None:
        end_anchor = _anchor_input(
            request.get("end_anchor"), "end_anchor", _derived_id("event.create", command_id, "end_anchor", "/end_anchor")
        )
    semantic = _semantic_request("event.create", command_id, actor, created_at, request, allowed)
    replay = _compatible_replay("event.create", command_id, semantic, context)
    if replay is not None:
        return _create_response("event.create", _receipt_item(context.ledger, replay), False, replay)
    item_id = _derived_id("event.create", command_id, "item", "/item")
    audit_id = _derived_id("event.create", command_id, "audit", "/audit")
    recurrence = _normalize_authored_recurrence(
        request.get("start_anchor"),
        field="start_anchor",
        anchor=start_anchor,
        item_id=item_id,
        command_id=command_id,
    )
    result = create_event_v1(
        context.ledger,
        item_id=item_id,
        audit_id=audit_id,
        created_at_utc=created_at,
        created_by_subject_id=actor,
        title=title,
        summary=_optional_str(request, "summary"),
        source_ref=_optional_str(request, "source_ref"),
        all_day=all_day,
        start_anchor=start_anchor,
        end_anchor=end_anchor,
        visibility=_optional_str(request, "visibility"),
        attendance_policy_ref=_optional_str(request, "attendance_policy_ref"),
        insert_canonical_extension=_recurrence_insert_callback(recurrence, command_id=command_id, created_at_utc=created_at),
    )
    receipt = _store_write_receipt(
        context,
        command="event.create",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=created_at,
        effect="event_created",
        item_id=result.item_id,
        target_version="0",
        semantic_facts={**semantic, "item_id": result.item_id, "version": "1", "created": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id("event.create", command_id),
            "item_id": result.item_id,
            "version": "1",
            "current_version": "1",
            "audit_id": result.audit_id,
            **_recurrence_identity_facts(recurrence),
        },
    )
    return _create_response("event.create", _hydrated_item(context.ledger, result.item_id), True, receipt)


def _handle_task_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "title",
        "summary",
        "source_ref",
        "due_anchor",
        "defer_until_anchor",
        "priority",
        "subject_roles",
    }
    _check_fields("task.create", request, allowed)
    command_id, actor, created_at = _write_identity("task.create", request, "created_at_utc", context)
    title = _required_str(request, "title")
    due_anchor = (
        _anchor_input(
            request.get("due_anchor"),
            "due_anchor",
            _derived_id("task.create", command_id, "due_anchor", "/due_anchor"),
            allow_recurrence=True,
        )
        if request.get("due_anchor") is not None
        else None
    )
    defer_anchor = (
        _anchor_input(
            request.get("defer_until_anchor"),
            "defer_until_anchor",
            _derived_id("task.create", command_id, "defer_until_anchor", "/defer_until_anchor"),
        )
        if request.get("defer_until_anchor") is not None
        else None
    )
    subject_roles = _task_subject_roles(
        context.ledger,
        command="task.create",
        command_id=command_id,
        value=request.get("subject_roles", []),
        field="subject_roles",
        request_path="/subject_roles",
    )
    semantic = _semantic_request("task.create", command_id, actor, created_at, request, allowed)
    replay = _compatible_replay("task.create", command_id, semantic, context)
    if replay is not None:
        return _create_response("task.create", _receipt_item(context.ledger, replay), False, replay)
    item_id = _derived_id("task.create", command_id, "item", "/item")
    audit_id = _derived_id("task.create", command_id, "audit", "/audit")
    recurrence = _normalize_authored_recurrence(
        request.get("due_anchor"),
        field="due_anchor",
        anchor=due_anchor,
        item_id=item_id,
        command_id=command_id,
    )
    result = create_task_v1(
        context.ledger,
        item_id=item_id,
        audit_id=audit_id,
        created_at_utc=created_at,
        created_by_subject_id=actor,
        title=title,
        summary=_optional_str(request, "summary"),
        source_ref=_optional_str(request, "source_ref"),
        priority=_optional_str(request, "priority"),
        due_anchor=due_anchor,
        defer_until_anchor=defer_anchor,
        subject_roles=subject_roles,
        insert_canonical_extension=_recurrence_insert_callback(recurrence, command_id=command_id, created_at_utc=created_at),
    )
    receipt = _store_write_receipt(
        context,
        command="task.create",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=created_at,
        effect="task_created",
        item_id=result.item_id,
        target_version="0",
        semantic_facts={**semantic, "item_id": result.item_id, "version": "1", "created": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id("task.create", command_id),
            "item_id": result.item_id,
            "version": "1",
            "current_version": "1",
            "audit_id": result.audit_id,
            **_recurrence_identity_facts(recurrence),
        },
    )
    return _create_response("task.create", _hydrated_item(context.ledger, result.item_id), True, receipt)


def _handle_schedule_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    command = "schedule.create"
    allowed = {
        "contract_version",
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "item",
        "scheduled_time",
        "delivery",
        "reminders",
        "materialization",
    }
    _check_fields(command, request, allowed)
    for required_field in (
        "contract_version",
        "command_id",
        "actor_subject_id",
        "created_at_utc",
        "item",
        "scheduled_time",
        "delivery",
        "reminders",
        "materialization",
    ):
        if required_field not in request:
            raise SpineValidationError(f"missing_{required_field}", f"{required_field} is required")
    if request.get("contract_version") != "spine.schedule-create.v1":
        raise SpineValidationError("invalid_request:contract_version", "contract_version must be spine.schedule-create.v1")
    command_id, actor, created_at = _write_identity(command, request, "created_at_utc", context)
    semantic = _schedule_semantic_request(command_id, actor, created_at, request, allowed)
    replay = _compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        if not _schedule_create_evidence_matches(context.ledger, replay):
            return _error(command, "runtime_failure", "stored schedule.create evidence is incomplete or inconsistent")
        return _schedule_create_response(replay, response_effect="schedule_create_replay")

    if current_schema_version(context.ledger) != IMPLEMENTED_LEDGER_SCHEMA_VERSION:
        raise SpineValidationError(
            "environment_failure:ledger_schema_version",
            f"schedule.create requires ledger schema {IMPLEMENTED_LEDGER_SCHEMA_VERSION}",
        )
    required_contracts = {
        "spine.schedule-create.v1",
        "spine.schedule-create-normalization.v1",
        "spine.schedule-create-response.v1",
        "spine.schedule-create-receipt.v1",
    }
    if not required_contracts.issubset(IMPLEMENTED_CONTRACT_VERSIONS):
        raise SpineValidationError(
            "environment_failure:contract_version",
            "runtime does not declare the complete schedule.create contract family",
        )

    item_request = _schedule_object(request.get("item"), "item")
    item_type = _enum(item_request.get("item_type"), "item.item_type", {"event", "task"})
    title = _nested_required_str(item_request, "title", "item.title")
    _schedule_validate_item_fields(item_request, item_type=item_type)

    scheduled_request = _schedule_object(request.get("scheduled_time"), "scheduled_time")
    scheduled = _schedule_resolve_initial_time(scheduled_request)
    anchor_id = _derived_id(command, command_id, "start_anchor" if item_type == "event" else "due_anchor", "/scheduled_time")
    anchor = TemporalAnchorInput(
        anchor_id=anchor_id,
        anchor_kind="local_instant",
        local_date=scheduled["local_date"],
        local_time=scheduled["local_time"],
        timezone=scheduled["timezone"],
        timezone_database_version=scheduled["timezone_database_version"],
    )

    delivery = _schedule_resolve_delivery(request.get("delivery"), context)
    materialization = _schedule_normalize_materialization(
        request.get("materialization"),
        scheduled=scheduled,
    )
    item_id = _derived_id(command, command_id, "item", "/item")
    audit_id = _derived_id(command, command_id, "audit", "/audit")

    recurrence_authoring = scheduled_request.get("recurrence")
    raw_anchor: dict[str, object] = {
        "anchor_kind": "local_instant",
        "local_date": scheduled["local_date"],
        "local_time": scheduled["local_time"],
        "timezone": scheduled["timezone"],
        "timezone_database_version": scheduled["timezone_database_version"],
    }
    if recurrence_authoring is not None:
        recurrence_fields = _schedule_object(recurrence_authoring, "scheduled_time.recurrence")
        raw_anchor["recurrence_set"] = {
            "time_basis": "local_instant",
            "timezone": scheduled["timezone"],
            "timezone_database_version": scheduled["timezone_database_version"],
            **_canonical_value(recurrence_fields),
        }
    recurrence = _normalize_authored_recurrence(
        raw_anchor,
        field="scheduled_time",
        anchor=anchor,
        item_id=item_id,
        command_id=command_id,
    )

    subject_roles: tuple[ItemSubjectRoleInput, ...] = ()
    if item_type == "task":
        task_detail = _schedule_object(item_request.get("task_detail"), "item.task_detail")
        raw_roles = task_detail.get("subject_roles", [])
        if isinstance(raw_roles, Sequence) and not isinstance(raw_roles, (str, bytes, bytearray)):
            raw_roles = sorted(
                raw_roles,
                key=lambda value: (
                    str(value.get("role", "")) if isinstance(value, Mapping) else "",
                    str(value.get("subject_id", "")) if isinstance(value, Mapping) else "",
                    str(value.get("status", "active")) if isinstance(value, Mapping) else "",
                ),
            )
        subject_roles = _task_subject_roles(
            context.ledger,
            command=command,
            command_id=command_id,
            value=raw_roles,
            field="item.task_detail.subject_roles",
            request_path="/item/task_detail/subject_roles",
        )

    normalized_policies = _schedule_normalize_policies(
        request.get("reminders"),
        item_id=item_id,
        item_type=item_type,
        recurring=recurrence is not None,
        command_id=command_id,
        created_at_utc=created_at,
        delivery=delivery,
    )
    audit_payload: dict[str, object] = {
        "action": "schedule_created",
        "item_id": item_id,
        "item_type": item_type,
        "version": "1",
        "command_id": command_id,
    }
    receipt_holder: list[dict[str, Any]] = []

    def insert_schedule_bundle(connection: sqlite3.Connection) -> None:
        if recurrence is not None:
            insert_initial_recurrence_set(connection, normalized=recurrence, command_id=command_id, created_at_utc=created_at)
        _schedule_fail_if_requested(context, "item")
        for _, policy in normalized_policies:
            insert_notification_schedule_policy(connection, normalized=policy)
        _schedule_fail_if_requested(context, "policies")

        provenance_ids: list[str] = []
        opportunity_work: list[dict[str, object]] = []
        work_instance_ids: list[str] = []
        materialization_facts: dict[str, object]
        if materialization["mode"] == "none":
            materialization_facts = {
                "mode": "none",
                "state": "not_requested",
                "opportunity_count": "0",
                "work_instance_count": "0",
                "opportunity_work": [],
                "work_instance_ids": [],
            }
        else:
            item = _hydrated_item(connection, item_id)
            if recurrence is not None:
                source_start, source_end = _schedule_recurrence_source_range(
                    recurrence.value,
                    policies=[policy.value for _, policy in normalized_policies],
                    eligibility_start=_parse_utc_datetime(str(materialization["range_start_utc"])),
                    eligibility_end=_parse_utc_datetime(str(materialization["range_end_utc"])),
                )
                expanded = expand_recurrence_set(
                    recurrence.value,
                    range_basis="expressed_time",
                    range_start=source_start,
                    range_end=source_end,
                )
                for occurrence in expanded.occurrences:
                    decorated = _decorate_occurrence(item, recurrence.value, dict(occurrence), include_internal=True)
                    derived = derive_occurrence_provenance(
                        occurrence=decorated,
                        recurrence=recurrence.value,
                        item=item,
                        consumer="notification_schedule",
                        producer=command,
                        range_basis="expressed_time",
                        range_start=source_start,
                        range_end=source_end,
                        created_at_utc=created_at,
                    )
                    insert_occurrence_provenance(connection, derived=derived)
                    provenance_ids.append(str(derived.value["occurrence_provenance_id"]))
            _schedule_fail_if_requested(context, "provenance")

            opportunities_response = _handle_notification_opportunities(
                {
                    "item_id": item_id,
                    "evaluated_at_utc": materialization["evaluated_at_utc"],
                    "range_start_utc": materialization["range_start_utc"],
                    "range_end_utc": materialization["range_end_utc"],
                    "limit": materialization["limit"],
                },
                CommandContext(ledger=connection),
            )
            if opportunities_response["has_more"]:
                raise SpineValidationError(
                    "invalid_request:materialization.limit",
                    "materialization.limit is smaller than the complete actionable opportunity set",
                )
            opportunities = [dict(value) for value in opportunities_response["opportunities"]]
            if any(not bool(value["actionable"]) for value in opportunities):
                raise SpineValidationError(
                    "semantic_conflict:materialization",
                    "new schedule.create opportunities must all be actionable",
                )
            policy_key_by_id = {
                str(policy.value["notification_policy_id"]): policy_key for policy_key, policy in normalized_policies
            }
            for opportunity in opportunities:
                work_id, _ = notification_id(
                    "work_instance",
                    "spine.notification-work-instance-id.v1",
                    {
                        "notification_opportunity_id": opportunity["notification_opportunity_id"],
                        "delivery_target_id": opportunity["delivery_target_id"],
                    },
                )
                recipient_id = opportunity.get("recipient_subject_id") or opportunity.get("recipient_group_id")
                create_work_instance(
                    connection,
                    work_instance_id=work_id,
                    item_id=item_id,
                    item_version=1,
                    notification_policy_id=str(opportunity["notification_policy_id"]),
                    notification_policy_item_version=1,
                    notification_intent_id=str(opportunity["notification_intent_id"]),
                    notification_opportunity_id=str(opportunity["notification_opportunity_id"]),
                    normalized_notification_schedule_hash=str(opportunity["normalized_notification_schedule_hash"]),
                    occurrence_provenance_id=(
                        str(opportunity["occurrence_provenance_id"])
                        if opportunity.get("occurrence_provenance_id") is not None
                        else None
                    ),
                    target_anchor_role=str(opportunity["anchor_role"]),
                    application_scope=str(opportunity["application_scope"]),
                    target_scheduled_fact=str(opportunity["target_scheduled_fact"]),
                    target_at_utc=(str(opportunity["target_at_utc"]) if opportunity.get("target_at_utc") is not None else None),
                    occurrence_key=(str(opportunity["occurrence_key"]) if opportunity.get("occurrence_key") is not None else None),
                    delivery_target_id=str(opportunity["delivery_target_id"]),
                    generation_source_kind="schedule_tick",
                    generation_source_ref=str(opportunity["notification_opportunity_id"]),
                    work_subject_ref=f"{opportunity['recipient_kind']}:{recipient_id}",
                    policy_basis_ref=str(opportunity["normalized_notification_schedule_hash"]),
                    eligible_at_utc=str(opportunity["eligible_at_utc"]),
                    created_at_utc=created_at,
                    manage_transaction=False,
                )
                work_instance_ids.append(work_id)
                evidence: dict[str, object] = {
                    "policy_key": policy_key_by_id[str(opportunity["notification_policy_id"])],
                    "notification_intent_id": opportunity["notification_intent_id"],
                    "notification_policy_id": opportunity["notification_policy_id"],
                    "notification_opportunity_id": opportunity["notification_opportunity_id"],
                    "eligible_at_utc": opportunity["eligible_at_utc"],
                    "work_instance_id": work_id,
                }
                if opportunity.get("occurrence_key") is not None:
                    evidence["occurrence_key"] = opportunity["occurrence_key"]
                    provenance_row = connection.execute(
                        """
                        SELECT original_scheduled_fact, expressed_scheduled_fact
                        FROM occurrence_provenance
                        WHERE occurrence_provenance_id = ?
                        """,
                        (opportunity["occurrence_provenance_id"],),
                    ).fetchone()
                    if provenance_row is not None:
                        evidence["original_scheduled_fact"] = provenance_row["original_scheduled_fact"]
                        evidence["expressed_scheduled_fact"] = provenance_row["expressed_scheduled_fact"]
                opportunity_work.append(evidence)
            _schedule_fail_if_requested(context, "work")
            materialization_facts = {
                "mode": "bounded",
                "state": "materialized" if work_instance_ids else "completed_zero_selected",
                "evaluated_at_utc": materialization["evaluated_at_utc"],
                "range_start_utc": materialization["range_start_utc"],
                "range_end_utc": materialization["range_end_utc"],
                "limit": materialization["limit"],
                "opportunity_count": str(len(opportunities)),
                "work_instance_count": str(len(work_instance_ids)),
                "opportunity_work": opportunity_work,
                "work_instance_ids": work_instance_ids,
            }

        policies_facts = [
            {
                "policy_key": policy_key,
                "notification_intent_id": policy.value["notification_intent_id"],
                "notification_policy_id": policy.value["notification_policy_id"],
                "notification_schedule_id": policy.value["notification_schedule_id"],
                "normalized_notification_schedule_hash": policy.value["normalized_notification_schedule_hash"],
                "status": "active",
            }
            for policy_key, policy in normalized_policies
        ]
        phases = {
            "item": "created",
            "policies": "authored",
            "provenance": (
                "regenerated" if recurrence is not None and materialization["mode"] == "bounded" else
                "not_requested" if recurrence is not None else
                "not_applicable"
            ),
            "opportunities": "expanded" if materialization["mode"] == "bounded" else "not_requested",
            "work": (
                str(materialization_facts["state"])
                if materialization["mode"] == "bounded"
                else "not_requested"
            ),
            "delivery": "not_attempted",
        }
        result_facts: dict[str, Any] = {
            "command_id": command_id,
            "command_receipt_id": _receipt_id(command, command_id),
            "audit_id": audit_id,
            "created_at_utc": created_at,
            "item_id": item_id,
            "item_type": item_type,
            "current_version": "1",
            "title": title,
            "scheduled_time": {
                "anchor_id": anchor_id,
                "time_basis": "local_instant",
                "local_date": scheduled["local_date"],
                "local_time": scheduled["local_time"],
                "timezone": scheduled["timezone"],
                "timezone_database_version": scheduled["timezone_database_version"],
                "resolution_kind": "unambiguous",
                "utc_instant": scheduled["utc_instant"],
                "offset_seconds": scheduled["offset_seconds"],
            },
            "delivery": delivery["snapshot"],
            "policies": policies_facts,
            "materialization": materialization_facts,
            "phases": phases,
        }
        if recurrence is not None:
            result_facts["recurrence"] = {
                "recurrence_set_id": recurrence.value["recurrence_set_id"],
                "recurrence_revision_id": recurrence.value["recurrence_revision_id"],
                "revision_number": recurrence.value["revision_number"],
                "normalized_recurrence_set_hash": recurrence.value["normalized_recurrence_set_hash"],
                "diagnostics": [],
            }
        receipt = _make_receipt(
            command=command,
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=created_at,
            effect="schedule_created",
            item_id=item_id,
            target_version="0",
            semantic_facts={
                **semantic,
                "resolved_timezone_database_version": scheduled["timezone_database_version"],
                "resolved_initial_utc_instant": scheduled["utc_instant"],
                "resolved_delivery": delivery["snapshot"],
                "normalized_result": result_facts,
            },
            result_identity_facts=result_facts,
        )
        insert_command_receipt(connection, receipt)
        _schedule_fail_if_requested(context, "receipt")
        receipt_holder.append(receipt)
        audit_payload.update(
            {
                "notification_policy_ids": [value["notification_policy_id"] for value in policies_facts],
                "occurrence_provenance_ids": sorted(provenance_ids),
                "work_instance_ids": work_instance_ids,
                "command_receipt_id": receipt["command_receipt_id"],
            }
        )

    common_create = {
        "item_id": item_id,
        "audit_id": audit_id,
        "created_at_utc": created_at,
        "created_by_subject_id": actor,
        "title": title,
        "summary": _nested_optional_str(item_request, "summary", "item.summary"),
        "source_ref": _nested_optional_str(item_request, "source_ref", "item.source_ref"),
        "insert_canonical_extension": insert_schedule_bundle,
        "audit_action": "schedule_created",
        "audit_reason_code": "schedule_created",
        "audit_payload": audit_payload,
    }
    if item_type == "event":
        event_detail = _schedule_object(item_request.get("event_detail"), "item.event_detail")
        create_event_v1(
            context.ledger,
            **common_create,
            all_day=False,
            start_anchor=anchor,
            visibility=_nested_optional_str(event_detail, "visibility", "item.event_detail.visibility"),
            attendance_policy_ref=_nested_optional_str(
                event_detail,
                "attendance_policy_ref",
                "item.event_detail.attendance_policy_ref",
            ),
        )
    else:
        task_detail = _schedule_object(item_request.get("task_detail"), "item.task_detail")
        create_task_v1(
            context.ledger,
            **common_create,
            priority=_nested_optional_str(task_detail, "priority", "item.task_detail.priority"),
            due_anchor=anchor,
            subject_roles=subject_roles,
        )
    if len(receipt_holder) != 1:
        return _error(command, "runtime_failure", "schedule.create did not produce exactly one command receipt")
    receipt = receipt_holder[0]
    if not _schedule_create_evidence_matches(context.ledger, receipt):
        return _error(command, "runtime_failure", "committed schedule.create evidence does not match its receipt")
    return _schedule_create_response(receipt, response_effect="schedule_created")


def _handle_common_update(command: str, expected_type: str, request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "item_id", "target_version", "updated_at_utc", "patch"}
    _check_fields(command, request, allowed)
    command_id, actor, updated_at = _write_identity(command, request, "updated_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    if "patch" not in request:
        raise SpineValidationError("missing_patch", "patch is required")
    patch = _patch(request["patch"], allow_subject_roles=expected_type == "task")
    replacement_subject_roles: tuple[ItemSubjectRoleInput, ...] | None = None
    if "subject_roles" in patch:
        replacement_subject_roles = _task_subject_roles(
            context.ledger,
            command=command,
            command_id=command_id,
            value=patch["subject_roles"],
            field="patch.subject_roles",
            request_path="/patch/subject_roles",
        )
    semantic = _semantic_request(command, command_id, actor, updated_at, request, allowed)
    replay = _compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        response_fn = event_update_response if expected_type == "event" else task_update_response
        return response_fn(
            updated=False,
            item=_receipt_item(context.ledger, replay),
            target_version=str(target_version),
            audit_id=None,
            command_receipt_id=replay["command_receipt_id"],
        )
    item = _require_item_for_write(context.ledger, command, item_id, expected_type, target_version)
    current_common = item["version"]
    common_changed = _changed_common(current_common, patch)
    roles_changed = replacement_subject_roles is not None and _subject_role_facts(item["subject_roles"]) != _subject_role_facts(
        replacement_subject_roles
    )
    if not common_changed and not roles_changed:
        receipt = _store_write_receipt(
            context,
            command=command,
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=updated_at,
            effect=f"{expected_type}_update_noop",
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, "updated": False},
            result_identity_facts={
                "command_receipt_id": _receipt_id(command, command_id),
                "item_id": item_id,
                "target_version": str(target_version),
                "version": str(item["current_version"]),
                "current_version": str(item["current_version"]),
            },
        )
        response_fn = event_update_response if expected_type == "event" else task_update_response
        return response_fn(
            updated=False, item=item, target_version=str(target_version), audit_id=None, command_receipt_id=receipt["command_receipt_id"]
        )
    audit_id = _derived_id(command, command_id, "audit", "/audit")
    mutation = create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=updated_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        title=patch.get("title"),
        summary=patch.get("summary", _UNSET),
        source_ref=patch.get("source_ref", _UNSET),
        subject_roles=replacement_subject_roles if replacement_subject_roles is not None else _UNSET,
        subject_role_replacement_roles=("assignee", "owner") if replacement_subject_roles is not None else (),
        audit_action=f"{expected_type}_updated",
        reason_code=f"{expected_type}_updated",
        supporting_command_id=command_id,
    )
    receipt = _store_write_receipt(
        context,
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=updated_at,
        effect=f"{expected_type}_updated",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, "version": str(mutation.version), "updated": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id(command, command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "version": str(mutation.version),
            "current_version": str(mutation.version),
            "audit_id": mutation.audit_id,
        },
    )
    response_fn = event_update_response if expected_type == "event" else task_update_response
    return response_fn(
        updated=True,
        item=_hydrated_item(context.ledger, item_id),
        target_version=str(target_version),
        audit_id=mutation.audit_id,
        command_receipt_id=receipt["command_receipt_id"],
    )


def _handle_event_reschedule(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "rescheduled_at_utc",
        "all_day",
        "start_anchor",
        "end_anchor",
        "patch",
    }
    _check_fields("event.reschedule", request, allowed)
    command_id, actor, at = _write_identity("event.reschedule", request, "rescheduled_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    all_day = _required_bool(request, "all_day")
    start_anchor = _anchor_input(
        request.get("start_anchor"),
        "start_anchor",
        _derived_id("event.reschedule", command_id, "start_anchor", "/start_anchor"),
        allow_recurrence=True,
    )
    end_anchor = (
        _anchor_input(request.get("end_anchor"), "end_anchor", _derived_id("event.reschedule", command_id, "end_anchor", "/end_anchor"))
        if request.get("end_anchor") is not None
        else None
    )
    patch = _patch(request.get("patch", {}))
    semantic = _semantic_request("event.reschedule", command_id, actor, at, request, allowed)
    replay = _compatible_replay("event.reschedule", command_id, semantic, context)
    if replay is not None:
        return event_reschedule_response(
            rescheduled=False,
            item=_receipt_item(context.ledger, replay),
            target_version=str(target_version),
            audit_id=None,
            command_receipt_id=replay["command_receipt_id"],
        )
    item = _require_item_for_write(context.ledger, "event.reschedule", item_id, "event", target_version)
    if item["detail"]["event_status"] == "cancelled":
        return _error("event.reschedule", "invalid_state_transition", "cancelled events cannot be rescheduled", "event_status")
    current_recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    if current_recurrence is not None:
        return _error(
            "event.reschedule",
            "semantic_conflict",
            "recurring events must be changed through recurrence commands",
            "start_anchor",
        )
    recurrence = _normalize_authored_recurrence(
        request.get("start_anchor"),
        field="start_anchor",
        anchor=start_anchor,
        item_id=item_id,
        command_id=command_id,
        created_item_version=str(target_version + 1),
        source_item_version=str(target_version + 1),
    )
    current = item["detail"]
    requested_end = _anchor_semantic_facts(_anchor_output(end_anchor)) if end_anchor is not None else None
    anchor_noop = (
        _anchor_semantic_facts(current["start_anchor"]) == _anchor_semantic_facts(_anchor_output(start_anchor))
        and _anchor_semantic_facts(current.get("end_anchor")) == requested_end
        and bool(current["all_day"]) == all_day
    )
    common_noop = not _changed_common(item["version"], patch)
    if anchor_noop and common_noop and recurrence is None:
        receipt = _store_write_receipt(
            context,
            command="event.reschedule",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=at,
            effect="event_reschedule_noop",
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, "rescheduled": False},
            result_identity_facts={
                "command_receipt_id": _receipt_id("event.reschedule", command_id),
                "item_id": item_id,
                "target_version": str(target_version),
                "version": str(target_version),
                "current_version": str(target_version),
            },
        )
        return event_reschedule_response(
            rescheduled=False,
            item=item,
            target_version=str(target_version),
            audit_id=None,
            command_receipt_id=receipt["command_receipt_id"],
        )
    audit_id = _derived_id("event.reschedule", command_id, "audit", "/audit")

    def insert_prerequisites(connection: sqlite3.Connection, _version: int) -> None:
        insert_temporal_anchor(
            connection,
            anchor=start_anchor,
            anchor_id=start_anchor.anchor_id or "",
            default_created_at_utc=at,
        )
        if end_anchor is not None:
            insert_temporal_anchor(
                connection,
                anchor=end_anchor,
                anchor_id=end_anchor.anchor_id or "",
                default_created_at_utc=at,
            )

    def insert_extension(connection: sqlite3.Connection, _version: int) -> None:
        if recurrence is not None:
            insert_initial_recurrence_set(
                connection,
                normalized=recurrence,
                command_id=command_id,
                created_at_utc=at,
            )

    mutation = create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        title=patch.get("title"),
        summary=patch.get("summary", _UNSET),
        source_ref=patch.get("source_ref", _UNSET),
        event_detail={
            "all_day": int(all_day),
            "start_anchor_id": start_anchor.anchor_id,
            "end_anchor_id": end_anchor.anchor_id if end_anchor is not None else None,
        },
        audit_action="event_rescheduled",
        reason_code="event_rescheduled",
        insert_prerequisites=insert_prerequisites,
        insert_canonical_extension=insert_extension,
        supporting_command_id=command_id,
    )
    receipt = _store_write_receipt(
        context,
        command="event.reschedule",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=at,
        effect="event_rescheduled",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, "version": str(mutation.version), "rescheduled": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id("event.reschedule", command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "version": str(mutation.version),
            "current_version": str(mutation.version),
            "audit_id": mutation.audit_id,
            **_recurrence_identity_facts(recurrence),
        },
    )
    return event_reschedule_response(
        rescheduled=True,
        item=_hydrated_item(context.ledger, item_id),
        target_version=str(target_version),
        audit_id=mutation.audit_id,
        command_receipt_id=receipt["command_receipt_id"],
    )


def _handle_event_cancel(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    return _lifecycle("event.cancel", request, context, "event", "cancelled_at_utc", "cancelled", cancel_event, "cancelled")


def _handle_task_complete(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    return _lifecycle("task.complete", request, context, "task", "completed_at_utc", "completed", complete_task, "done")


def _handle_task_cancel(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    return _lifecycle("task.cancel", request, context, "task", "cancelled_at_utc", "cancelled", cancel_task, "cancelled")


def _handle_item_archive(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "item_id", "target_version", "archived_at_utc"}
    _check_fields("item.archive", request, allowed)
    command_id, actor, at = _write_identity("item.archive", request, "archived_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    semantic = _semantic_request("item.archive", command_id, actor, at, request, allowed)
    replay = _compatible_replay("item.archive", command_id, semantic, context)
    if replay is not None:
        return _archive_response(
            _hydrated_item(context.ledger, item_id), False, replay["command_receipt_id"], replay["result_identity_facts"].get("audit_id")
        )
    item = _hydrated_item(context.ledger, item_id)
    if item["status"] == "archived":
        return _error("item.archive", "invalid_state_transition", "item is already archived", "status")
    if int(item["current_version"]) != target_version:
        return _error("item.archive", "stale_version", "target version is not current", "target_version")
    audit_id = _derived_id("item.archive", command_id, "audit", "/audit")
    archive_item(
        context.ledger, item_id=item_id, target_version=target_version, archived_at_utc=at, archived_by_subject_id=actor, audit_id=audit_id
    )
    receipt = _store_write_receipt(
        context,
        command="item.archive",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=at,
        effect="item_archived",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, "archived": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id("item.archive", command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "current_version": str(target_version),
            "audit_id": audit_id,
        },
    )
    return _archive_response(_hydrated_item(context.ledger, item_id), True, receipt["command_receipt_id"], audit_id)


def _handle_relation_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "source_item_id",
        "source_target_version",
        "target_item_id",
        "target_target_version",
        "relation_type",
        "created_at_utc",
    }
    _check_fields("relation.create", request, allowed)
    command_id, actor, at = _write_identity("relation.create", request, "created_at_utc", context)
    source_id = _required_str(request, "source_item_id")
    target_id = _required_str(request, "target_item_id")
    source_version = _version(request, "source_target_version")
    target_version = _version(request, "target_target_version")
    relation_type = _enum(request.get("relation_type"), "relation_type", {"depends_on", "part_of"})
    semantic = _semantic_request("relation.create", command_id, actor, at, request, allowed)
    replay = _compatible_replay("relation.create", command_id, semantic, context)
    if replay is not None:
        return _relation_create_response(context.ledger, replay["result_identity_facts"], created=False)
    source = _require_item_for_write(context.ledger, "relation.create", source_id, None, source_version, field="source_target_version")
    _require_item_for_write(context.ledger, "relation.create", target_id, None, target_version, field="target_target_version")
    relation_id = _derived_id("relation.create", command_id, "relation", "/relation")
    audit_id = _derived_id("relation.create", command_id, "audit", "/audit")
    create_item_relation(
        context.ledger,
        relation_id=relation_id,
        source_item_id=source_id,
        target_item_id=target_id,
        relation_type=relation_type,
        created_at_utc=at,
        created_by_subject_id=actor,
    )
    _insert_audit(
        context.ledger, audit_id, source_id, "relation_created", actor, at, {"action": "relation_created", "relation_id": relation_id}
    )
    receipt = _store_write_receipt(
        context,
        command="relation.create",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=at,
        effect="relation_created",
        item_id=source_id,
        target_version=str(source_version),
        semantic_facts={**semantic, "relation_id": relation_id, "created": True},
        result_identity_facts={
            "command_receipt_id": _receipt_id("relation.create", command_id),
            "relation_id": relation_id,
            "source_item_id": source_id,
            "source_target_version": str(source_version),
            "source_current_version": str(source["current_version"]),
            "target_item_id": target_id,
            "target_target_version": str(target_version),
            "target_current_version": str(target_version),
            "audit_id": audit_id,
        },
    )
    return _relation_create_response(context.ledger, receipt["result_identity_facts"], created=True)


def _handle_relation_list(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields(
        "relation.list",
        request,
        {"item_id", "source_item_id", "target_item_id", "relation_type", "direction", "include_derived_aliases", "bounded", "limit"},
    )
    limit = _limit(request.get("limit", 50))
    include_aliases = bool(request.get("include_derived_aliases", False))
    relation_type = request.get("relation_type")
    allowed_types = {"depends_on", "part_of", "blocks", "contains"} if include_aliases else {"depends_on", "part_of"}
    if relation_type is not None:
        relation_type = _enum(relation_type, "relation_type", allowed_types)
    item_id = request.get("item_id")
    source_id = request.get("source_item_id")
    target_id = request.get("target_item_id")
    if not any([item_id, source_id, target_id, request.get("bounded")]):
        return _error("relation.list", "missing_required_field", "item_id or bounded=true is required", "item_id")
    if "direction" in request and (source_id is not None or target_id is not None):
        return _error("relation.list", "invalid_request", "direction is only valid with item_id", "direction")
    source = _required_str(request, "source_item_id") if source_id is not None else None
    target = _required_str(request, "target_item_id") if target_id is not None else None
    item = _required_str(request, "item_id") if item_id is not None else None
    direction = request.get("direction", "both")
    if item is not None and direction not in {"source", "target", "both"}:
        return _error("relation.list", "invalid_request", "direction must be source, target, or both", "direction")
    rows = context.ledger.execute(
        """
        SELECT *
        FROM coordination_item_relations
        WHERE relation_status = 'active'
        ORDER BY relation_type, source_item_id, target_item_id, relation_id
        """
    ).fetchall()
    relations = [_relation_element(dict(row)) for row in rows]
    if include_aliases:
        relations.extend(_derived_aliases([dict(row) for row in rows], None))
    relations = [
        relation
        for relation in relations
        if _relation_matches_filters(
            relation,
            relation_type=relation_type,
            source_id=source,
            target_id=target,
            item_id=item,
            direction=str(direction),
        )
    ]
    relations.sort(key=lambda row: (row["relation_type"], row["source_item_id"], row["target_item_id"], row["relation_id"]))
    truncated = len(relations) > limit
    return {"ok": True, "command": "relation.list", "relations": relations[:limit], "limit": str(limit), "truncated": truncated}


def _relation_matches_filters(
    relation: Mapping[str, Any],
    *,
    relation_type: str | None,
    source_id: str | None,
    target_id: str | None,
    item_id: str | None,
    direction: str,
) -> bool:
    if relation_type is not None and relation["relation_type"] != relation_type:
        return False
    if source_id is not None and relation["source_item_id"] != source_id:
        return False
    if target_id is not None and relation["target_item_id"] != target_id:
        return False
    if item_id is not None:
        if direction == "source":
            return relation["source_item_id"] == item_id
        if direction == "target":
            return relation["target_item_id"] == item_id
        return relation["source_item_id"] == item_id or relation["target_item_id"] == item_id
    return True


def _handle_reminder_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "created_at_utc",
        "recipient_kind",
        "recipient_subject_id",
        "recipient_group_id",
        "delivery_target_id",
        "channel",
        "notification",
        "if_absent",
    }
    _check_fields("reminder.create", request, allowed)
    command_id, actor, created_at = _write_identity("reminder.create", request, "created_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    channel = _required_str(request, "channel")
    if_absent = bool(request.get("if_absent", False))
    semantic = _semantic_request("reminder.create", command_id, actor, created_at, request, allowed)
    replay = _compatible_replay("reminder.create", command_id, semantic, context)
    if replay is not None:
        return _reminder_response(replay["result_identity_facts"], created=False)

    route = _reminder_route(request, context, channel)
    if not route["ok"]:
        return route
    item = _require_item_for_write(context.ledger, "reminder.create", item_id, None, target_version)
    notification = request.get("notification")
    if not isinstance(notification, Mapping):
        return _error("reminder.create", "invalid_request", "notification must be an object", "notification")
    target = notification.get("target")
    if not isinstance(target, Mapping):
        return _error("reminder.create", "invalid_request", "notification.target must be an object", "notification.target")
    anchor_role = target.get("anchor_role")
    expected_role = "event_start" if item["item_type"] == "event" else "task_due"
    if anchor_role != expected_role:
        return _error(
            "reminder.create", "semantic_conflict", f"target anchor role must be {expected_role}", "notification.target.anchor_role"
        )
    anchor_field = "start_anchor" if item["item_type"] == "event" else "due_anchor"
    if not isinstance(item["detail"].get(anchor_field), Mapping):
        return _error(
            "reminder.create",
            "semantic_conflict",
            "notification target anchor is unavailable",
            "notification.target.anchor_role",
        )
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    application_scope = target.get("application_scope")
    selector: dict[str, object] | None = None
    occurrence_key: str | None = None
    if recurrence is None and application_scope != "item":
        return _error(
            "reminder.create",
            "semantic_conflict",
            "non-recurring targets require application_scope=item",
            "notification.target.application_scope",
        )
    if recurrence is not None and application_scope == "item":
        return _error(
            "reminder.create", "semantic_conflict", "recurring targets require an occurrence scope", "notification.target.application_scope"
        )
    if application_scope == "selected_occurrence":
        occurrence_key = target.get("target_occurrence_key") if isinstance(target.get("target_occurrence_key"), str) else None
        if occurrence_key is None:
            return _error(
                "reminder.create",
                "invalid_request",
                "selected occurrence requires target_occurrence_key",
                "notification.target.target_occurrence_key",
            )
        selector = _resolve_current_occurrence_selector(recurrence, occurrence_key)
    elif application_scope not in {"item", "each_occurrence"}:
        return _error("reminder.create", "invalid_request", "unsupported application_scope", "notification.target.application_scope")
    recipient_id = str(route["recipient_subject_id"] or route["recipient_group_id"])
    normalized = normalize_notification_policy(
        dict(notification),
        item_id=item_id,
        item_version=str(target_version + 1),
        command_id=command_id,
        created_at_utc=created_at,
        recipient_kind=str(route["recipient_kind"]),
        recipient_id=recipient_id,
        channel=channel,
        delivery_target_id=str(route["delivery_target_id"]),
        resolved_target_occurrence_selector=selector,
    )
    duplicate = _find_duplicate_structured_notification(context.ledger, item_id=item_id, normalized=normalized.value)
    if duplicate is not None and if_absent:
        receipt = _store_write_receipt(
            context,
            command="reminder.create",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=created_at,
            effect="reminder_duplicate_noop",
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, "created": False},
            result_identity_facts={
                **duplicate,
                "command_receipt_id": _receipt_id("reminder.create", command_id),
                "target_version": str(target_version),
                "current_version": str(item["current_version"]),
                "created": False,
            },
        )
        return _reminder_response(receipt["result_identity_facts"], created=False)
    if duplicate is not None:
        return _error("reminder.create", "semantic_conflict", "matching active notification already exists", "notification")
    next_version = target_version + 1
    audit_id = _derived_id("reminder.create", command_id, "audit", "/audit")
    policy = normalized.value
    facts = {
        "command_receipt_id": _receipt_id("reminder.create", command_id),
        "item_id": item_id,
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "version": str(next_version),
        "current_version": str(next_version),
        "audit_id": audit_id,
        "notification_intent_id": policy["notification_intent_id"],
        "notification_policy_id": policy["notification_policy_id"],
        "notification_schedule_id": policy["notification_schedule_id"],
        "notification_policy_item_version": str(next_version),
        "normalized_notification_schedule_hash": policy["normalized_notification_schedule_hash"],
        "notification_contract_version": policy["contract_version"],
        "notification_normalization_version": policy["normalization_version"],
        "canonical_json_version": policy["canonical_json_version"],
        "created": True,
    }
    receipt = _make_receipt(
        command="reminder.create",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=created_at,
        effect="reminder_created",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={
            **semantic,
            "version": str(next_version),
            "notification_intent_id": policy["notification_intent_id"],
            "notification_policy_id": policy["notification_policy_id"],
            "normalized_notification_schedule_hash": policy["normalized_notification_schedule_hash"],
            "normalized_target": policy["target"],
            "normalized_schedule": policy["schedule"],
            "normalized_late_handling": policy["late_handling"],
            "created": True,
        },
        result_identity_facts=facts,
    )

    def insert_policy(connection: sqlite3.Connection, _version: int) -> None:
        if selector is not None and occurrence_key is not None:
            recurrence_selector_ref = persist_target_occurrence_selector(connection, occurrence_key=occurrence_key, selector=selector)
            target_ref = persist_notification_target_selector(
                connection,
                recurrence_selector_ref=recurrence_selector_ref,
                occurrence_key=occurrence_key,
                selector=selector,
            )
            normalized.value["target"]["target_occurrence_selector_ref"] = target_ref  # type: ignore[index]
        insert_notification_schedule_policy(connection, normalized=normalized)
        insert_command_receipt(connection, receipt)

    create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=created_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        audit_action="reminder_created",
        reason_code="reminder_created",
        insert_canonical_extension=insert_policy,
        supporting_command_id=command_id,
    )
    return _reminder_response(receipt["result_identity_facts"], created=True)


def _handle_reminder_edit(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "notification_intent_id",
        "notification_policy_id",
        "updated_at_utc",
        "patch",
    }
    _check_fields("reminder.edit", request, allowed)
    command_id, actor, updated_at = _write_identity("reminder.edit", request, "updated_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    intent_id = _required_str(request, "notification_intent_id")
    policy_id = _required_str(request, "notification_policy_id")
    patch = request.get("patch")
    if not isinstance(patch, Mapping) or not patch:
        raise SpineValidationError("invalid_patch", "patch must be a non-empty object")
    allowed_patch = {
        "recipient_kind",
        "recipient_subject_id",
        "recipient_group_id",
        "channel",
        "delivery_target_id",
        "target",
        "schedule",
        "late_handling",
    }
    unknown = sorted(set(patch) - allowed_patch)
    if unknown:
        raise SpineValidationError(f"unsupported_patch.{unknown[0]}", "unsupported notification patch field")
    semantic = _semantic_request("reminder.edit", command_id, actor, updated_at, request, allowed)
    replay = _compatible_replay("reminder.edit", command_id, semantic, context)
    if replay is not None:
        return {"ok": True, "command": "reminder.edit", **replay["result_identity_facts"]}
    item = _require_item_for_write(context.ledger, "reminder.edit", item_id, None, target_version)
    current = _current_notification_policy(
        context.ledger,
        item_id=item_id,
        notification_intent_id=intent_id,
        notification_policy_id=policy_id,
    )
    recipient_kind = str(patch.get("recipient_kind", current["recipient_kind"]))
    recipient_subject_id = patch.get("recipient_subject_id", current.get("recipient_subject_id"))
    recipient_group_id = patch.get("recipient_group_id", current.get("recipient_group_id"))
    route = _reminder_route(
        {
            "recipient_kind": recipient_kind,
            **({"recipient_subject_id": recipient_subject_id} if recipient_subject_id is not None else {}),
            **({"recipient_group_id": recipient_group_id} if recipient_group_id is not None else {}),
            "delivery_target_id": patch.get("delivery_target_id", current["delivery_target_id"]),
        },
        context,
        str(patch.get("channel", current["channel"])),
    )
    if not route["ok"]:
        return {**route, "command": "reminder.edit"}
    authored_target = _notification_authoring_target(patch.get("target", current["target"]))
    selector = _notification_target_selector(
        authored_target,
        recurrence=load_current_recurrence_set(context.ledger, item_id=item_id),
        current_target=current["target"],
    )
    revised = revise_notification_policy(
        current,
        item_version=str(target_version + 1),
        command_id=command_id,
        changed_at_utc=updated_at,
        recipient_kind=str(route["recipient_kind"]),
        recipient_id=str(route["recipient_subject_id"] or route["recipient_group_id"]),
        channel=str(patch.get("channel", current["channel"])),
        delivery_target_id=str(route["delivery_target_id"]),
        target=authored_target,
        schedule=patch.get("schedule", current["schedule"]),
        late_handling=patch.get("late_handling", current["late_handling"]),
        resolved_target_occurrence_selector=selector,
    )
    unchanged = (
        current["status"] == "active"
        and current["recipient_kind"] == revised.value["recipient_kind"]
        and current.get("recipient_subject_id") == revised.value.get("recipient_subject_id")
        and current.get("recipient_group_id") == revised.value.get("recipient_group_id")
        and current["channel"] == revised.value["channel"]
        and current["delivery_target_id"] == revised.value["delivery_target_id"]
        and current["normalized_notification_schedule_hash"] == revised.value["normalized_notification_schedule_hash"]
    )
    if unchanged:
        facts = {
            "command_receipt_id": _receipt_id("reminder.edit", command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "current_version": str(target_version),
            "notification_intent_id": intent_id,
            "notification_policy_id": policy_id,
            "notification_schedule_id": current["notification_schedule_id"],
            "normalized_notification_schedule_hash": current["normalized_notification_schedule_hash"],
            "updated": False,
            "effect": "reminder_edit_noop",
        }
        receipt = _store_write_receipt(
            context,
            command="reminder.edit",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=updated_at,
            effect="reminder_edit_noop",
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, **facts},
            result_identity_facts=facts,
        )
        return {"ok": True, "command": "reminder.edit", **receipt["result_identity_facts"]}
    audit_id = _derived_id("reminder.edit", command_id, "audit", "/audit")
    facts = _notification_mutation_facts(
        command="reminder.edit",
        command_id=command_id,
        item=item,
        target_version=target_version,
        audit_id=audit_id,
        policy=revised.value,
        changed_field="updated",
        effect="reminder_updated",
    )
    receipt = _make_receipt(
        command="reminder.edit",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=updated_at,
        effect="reminder_updated",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, **facts},
        result_identity_facts=facts,
    )
    _persist_notification_successor(
        context,
        item=item,
        current=current,
        revised=revised,
        selector=selector,
        target_version=target_version,
        command_id=command_id,
        actor=actor,
        changed_at_utc=updated_at,
        audit_id=audit_id,
        action="reminder_updated",
        receipt=receipt,
    )
    return {"ok": True, "command": "reminder.edit", **receipt["result_identity_facts"]}


def _handle_reminder_disable(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "notification_intent_id",
        "notification_policy_id",
        "disabled_at_utc",
        "reason_code",
    }
    _check_fields("reminder.disable", request, allowed)
    command_id, actor, disabled_at = _write_identity("reminder.disable", request, "disabled_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    intent_id = _required_str(request, "notification_intent_id")
    policy_id = _required_str(request, "notification_policy_id")
    semantic = _semantic_request("reminder.disable", command_id, actor, disabled_at, request, allowed)
    replay = _compatible_replay("reminder.disable", command_id, semantic, context)
    if replay is not None:
        return {"ok": True, "command": "reminder.disable", **replay["result_identity_facts"]}
    item = _require_item_for_write(context.ledger, "reminder.disable", item_id, None, target_version)
    current = _current_notification_policy(
        context.ledger,
        item_id=item_id,
        notification_intent_id=intent_id,
        notification_policy_id=policy_id,
    )
    if current["status"] == "disabled":
        facts = {
            "command_receipt_id": _receipt_id("reminder.disable", command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "current_version": str(target_version),
            "notification_intent_id": intent_id,
            "notification_policy_id": policy_id,
            "notification_schedule_id": current["notification_schedule_id"],
            "normalized_notification_schedule_hash": current["normalized_notification_schedule_hash"],
            "disabled": False,
            "effect": "reminder_disable_noop",
        }
        receipt = _store_write_receipt(
            context,
            command="reminder.disable",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=disabled_at,
            effect="reminder_disable_noop",
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, **facts},
            result_identity_facts=facts,
        )
        return {"ok": True, "command": "reminder.disable", **receipt["result_identity_facts"]}
    target = _notification_authoring_target(current["target"])
    selector = _notification_target_selector(
        target,
        recurrence=load_current_recurrence_set(context.ledger, item_id=item_id),
        current_target=current["target"],
    )
    recipient_field = "recipient_subject_id" if current["recipient_kind"] == "subject" else "recipient_group_id"
    revised = revise_notification_policy(
        current,
        item_version=str(target_version + 1),
        command_id=command_id,
        changed_at_utc=disabled_at,
        recipient_kind=str(current["recipient_kind"]),
        recipient_id=str(current[recipient_field]),
        channel=str(current["channel"]),
        delivery_target_id=str(current["delivery_target_id"]),
        target=target,
        schedule=current["schedule"],
        late_handling=current["late_handling"],
        status="disabled",
        disabled_at_utc=disabled_at,
        resolved_target_occurrence_selector=selector,
    )
    audit_id = _derived_id("reminder.disable", command_id, "audit", "/audit")
    facts = _notification_mutation_facts(
        command="reminder.disable",
        command_id=command_id,
        item=item,
        target_version=target_version,
        audit_id=audit_id,
        policy=revised.value,
        changed_field="disabled",
        effect="reminder_disabled",
    )
    receipt = _make_receipt(
        command="reminder.disable",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=disabled_at,
        effect="reminder_disabled",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, **facts},
        result_identity_facts=facts,
    )
    _persist_notification_successor(
        context,
        item=item,
        current=current,
        revised=revised,
        selector=selector,
        target_version=target_version,
        command_id=command_id,
        actor=actor,
        changed_at_utc=disabled_at,
        audit_id=audit_id,
        action="reminder_disabled",
        receipt=receipt,
    )
    return {"ok": True, "command": "reminder.disable", **receipt["result_identity_facts"]}


def _handle_notification_opportunities(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "item_id",
        "evaluated_at_utc",
        "notification_intent_id",
        "range_start_utc",
        "range_end_utc",
        "limit",
        "cursor",
        "include_diagnostics",
    }
    _check_fields("notification.opportunities", request, allowed)
    item_id = _required_str(request, "item_id")
    evaluated_at = _timestamp(request, "evaluated_at_utc")
    range_start = _timestamp(request, "range_start_utc")
    range_end = _timestamp(request, "range_end_utc")
    limit = _notification_limit(request.get("limit"))
    intent_id = _optional_str(request, "notification_intent_id")
    include_diagnostics = request.get("include_diagnostics", False)
    if not isinstance(include_diagnostics, bool):
        raise SpineValidationError("invalid_include_diagnostics", "include_diagnostics must be boolean")
    start_value = parse_scheduled_fact(range_start, time_basis="instant_utc", field="range_start_utc")
    end_value = parse_scheduled_fact(range_end, time_basis="instant_utc", field="range_end_utc")
    assert isinstance(start_value, datetime) and isinstance(end_value, datetime)
    if end_value <= start_value:
        raise SpineValidationError("invalid_range_end_utc", "range_end_utc must be after range_start_utc")
    if end_value - start_value > timedelta(days=366):
        raise SpineValidationError("invalid_range_end_utc", "notification opportunity range exceeds 366 days")

    item = _hydrated_item(context.ledger, item_id)
    policies = load_current_notification_policies(context.ledger, item_id=item_id, notification_intent_id=intent_id)
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    cursor_facts = _notification_cursor_facts(
        item=item,
        policies=policies,
        recurrence=recurrence,
        evaluated_at_utc=evaluated_at,
        notification_intent_id=intent_id,
        range_start_utc=range_start,
        range_end_utc=range_end,
        limit=str(limit),
        include_diagnostics=include_diagnostics,
    )
    last = _decode_notification_cursor(request.get("cursor"), expected=cursor_facts)

    opportunities: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    expansion_start = range_start
    if last is not None and last[0] > expansion_start:
        # Re-enter at the cursor's inclusive eligibility instant so dense
        # cadences seek to the page boundary. The full ordering tuple below
        # removes the prior row while preserving same-instant peers.
        expansion_start = last[0]
    for policy in policies:
        targets = _notification_targets(
            context.ledger,
            item=item,
            policy=policy,
            recurrence=recurrence,
            range_start_utc=expansion_start,
            range_end_utc=range_end,
        )
        actionable, reason = _notification_policy_actionability(context.ledger, item=item, policy=policy)
        expanded = expand_notification_policy(
            policy,
            targets=targets,
            evaluated_at_utc=evaluated_at,
            range_start_utc=expansion_start,
            range_end_utc=range_end,
            policy_actionable=actionable,
            non_actionable_reason=reason,
            include_diagnostics=include_diagnostics,
            candidate_limit=limit + (2 if last is not None else 1),
        )
        opportunities.extend(dict(value) for value in expanded.opportunities)
        diagnostics.extend(dict(value) for value in expanded.diagnostics)
    opportunities.sort(
        key=lambda value: (
            str(value["eligible_at_utc"]),
            str(value["notification_opportunity_id"]),
        )
    )
    if last is not None:
        opportunities = [
            value
            for value in opportunities
            if (
                str(value["eligible_at_utc"]),
                str(value["notification_opportunity_id"]),
            )
            > tuple(last)
        ]
    has_more = len(opportunities) > limit
    page = opportunities[:limit]
    next_cursor = None
    if has_more:
        cursor_value = {
            **cursor_facts,
            "last_ordering_tuple": [
                str(page[-1]["eligible_at_utc"]),
                str(page[-1]["notification_opportunity_id"]),
            ],
        }
        next_cursor = _encode_notification_cursor(cursor_value)
    diagnostics.sort(
        key=lambda value: (
            0 if value["severity"] == "warning" else 1,
            str(value["diagnostic_code"]),
            str(value["field"]),
            str(value.get("eligible_at_utc", "")),
            str(value.get("source_id", "")),
        )
    )
    return {
        "ok": True,
        "command": "notification.opportunities",
        "response_contract": "spine.notification-opportunities.v1",
        "item_id": item_id,
        "item_type": item["item_type"],
        "current_version": str(item["current_version"]),
        "evaluated_at_utc": evaluated_at,
        "range_start_utc": range_start,
        "range_end_utc": range_end,
        "limit": str(limit),
        "opportunities": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "diagnostics": diagnostics if include_diagnostics else [],
    }


def _handle_occurrence_provenance_regenerate(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "recurrence_set_id",
        "recurrence_revision_id",
        "regenerated_at_utc",
        "consumer",
        "producer",
        "range_basis",
        "range_start",
        "range_end",
        "occurrence_keys",
    }
    _check_fields("occurrence_provenance.regenerate", request, allowed)
    command_id, actor, regenerated_at = _write_identity("occurrence_provenance.regenerate", request, "regenerated_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    requested_set_id = _required_str(request, "recurrence_set_id")
    requested_revision_id = _required_str(request, "recurrence_revision_id")
    consumer = _required_str(request, "consumer")
    producer = _optional_str(request, "producer")
    range_basis = _enum(
        request.get("range_basis", "original_schedule"),
        "range_basis",
        {"original_schedule", "expressed_time"},
    )
    range_start = _required_str(request, "range_start")
    range_end = _required_str(request, "range_end")
    requested_keys: list[str] | None = None
    if "occurrence_keys" in request:
        raw_keys = request["occurrence_keys"]
        if not isinstance(raw_keys, list) or not raw_keys or not all(isinstance(value, str) and value for value in raw_keys):
            raise SpineValidationError("invalid_occurrence_keys", "occurrence_keys must be a non-empty string array")
        if len(set(raw_keys)) != len(raw_keys):
            raise SpineValidationError("semantic_conflict:occurrence_keys", "occurrence_keys must be unique")
        requested_keys = raw_keys
    semantic = _semantic_request(
        "occurrence_provenance.regenerate",
        command_id,
        actor,
        regenerated_at,
        request,
        allowed,
    )
    replay = _compatible_replay("occurrence_provenance.regenerate", command_id, semantic, context)
    if replay is not None:
        return {
            "ok": True,
            "command": "occurrence_provenance.regenerate",
            **replay["result_identity_facts"],
        }
    item = _hydrated_item(context.ledger, item_id)
    if int(item["current_version"]) != target_version:
        raise SpineValidationError("stale_version:target_version", "target version is not current")
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    if recurrence is None:
        raise SpineValidationError("recurrence_not_configured", "item has no recurrence set")
    if recurrence["recurrence_set_id"] != requested_set_id:
        raise SpineValidationError("stale_version:recurrence_set_id", "recurrence set is not current")
    if recurrence["recurrence_revision_id"] != requested_revision_id:
        raise SpineValidationError("stale_version:recurrence_revision_id", "recurrence revision is not current")
    expanded = expand_recurrence_set(
        recurrence,
        range_start=range_start,
        range_end=range_end,
        range_basis=range_basis,
    )
    occurrences = [_decorate_occurrence(item, recurrence, dict(value), include_internal=True) for value in expanded.occurrences]
    if requested_keys is not None:
        available = {str(value["occurrence_key"]): value for value in occurrences}
        missing = [key for key in requested_keys if key not in available]
        if missing:
            raise SpineValidationError(
                "semantic_conflict:occurrence_keys",
                "every occurrence key must resolve inside the canonical range",
            )
        selected_set = set(requested_keys)
        occurrences = [value for value in occurrences if str(value["occurrence_key"]) in selected_set]
    derived = [
        derive_occurrence_provenance(
            occurrence=value,
            recurrence=recurrence,
            item=item,
            consumer=consumer,
            producer=producer,
            range_basis=range_basis,
            range_start=range_start,
            range_end=range_end,
            created_at_utc=regenerated_at,
        )
        for value in occurrences
    ]
    retained: list[str] = []
    newly_active: list[str] = []
    superseded: list[str] = []
    receipt: dict[str, Any]
    with context.ledger:
        for value in derived:
            current = active_provenance_for_slot(
                context.ledger,
                slot_key=str(value.value["occurrence_provenance_slot_key"]),
            )
            if current is not None and current["content_hash"] == value.value["content_hash"]:
                retained.append(current["occurrence_provenance_id"])
                continue
            if current is not None:
                supersede_occurrence_provenance(
                    context.ledger,
                    occurrence_provenance_id=current["occurrence_provenance_id"],
                    command_id=command_id,
                    superseded_at_utc=regenerated_at,
                    replacement_occurrence_provenance_id=str(value.value["occurrence_provenance_id"]),
                )
                superseded.append(current["occurrence_provenance_id"])
            insert_occurrence_provenance(context.ledger, derived=value)
            newly_active.append(str(value.value["occurrence_provenance_id"]))
        if requested_keys is None:
            selected_slots = {str(value.value["occurrence_provenance_slot_key"]) for value in derived}
            for current in active_provenance_for_range(
                context.ledger,
                consumer=consumer,
                item_id=item_id,
                recurrence_set_id=requested_set_id,
                range_basis=range_basis,
                range_start=range_start,
                range_end=range_end,
            ):
                if current["occurrence_provenance_slot_key"] not in selected_slots:
                    supersede_occurrence_provenance(
                        context.ledger,
                        occurrence_provenance_id=current["occurrence_provenance_id"],
                        command_id=command_id,
                        superseded_at_utc=regenerated_at,
                        replacement_occurrence_provenance_id=None,
                    )
                    superseded.append(current["occurrence_provenance_id"])
        closed_reports, unresolved_reports = close_recoverable_provenance_reports(
            context.ledger,
            item_id=item_id,
            consumer=consumer,
            recurrence_set_id=requested_set_id,
            command_id=command_id,
            closed_at_utc=regenerated_at,
            range_basis=range_basis,
            range_start=range_start,
            range_end=range_end,
        )
        changed = bool(newly_active or superseded or closed_reports)
        effect = (
            "provenance_regenerate_replaced"
            if newly_active or superseded
            else "provenance_regenerate_resolved_report"
            if closed_reports
            else "provenance_regenerate_unresolved_report"
            if unresolved_reports
            else "provenance_regenerate_zero_selected"
            if not derived
            else "provenance_regenerate_all_retained"
        )
        selected_keys = [str(value["occurrence_key"]) for value in occurrences]
        facts: dict[str, Any] = {
            "command_receipt_id": _receipt_id("occurrence_provenance.regenerate", command_id),
            "item_id": item_id,
            "item_type": item["item_type"],
            "target_version": str(target_version),
            "current_version": str(item["current_version"]),
            "source_item_version": recurrence["source_item_version"],
            "shell_status": item["status"],
            "recurrence_set_id": requested_set_id,
            "recurrence_revision_id": requested_revision_id,
            "revision_number": recurrence["revision_number"],
            "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
            "recurrence_set_identity_preimage": recurrence_set_identity_preimage(recurrence),
            "changed": changed,
            "effect": effect,
            "consumer": consumer,
            "range_basis": range_basis,
            "range_start": range_start,
            "range_end": range_end,
            "selected_count": str(len(selected_keys)),
            "selected_occurrence_keys": selected_keys,
            "retained_occurrence_provenance_ids": sorted(retained),
            "newly_active_occurrence_provenance_ids": sorted(newly_active),
            "superseded_occurrence_provenance_ids": sorted(set(superseded)),
            "closed_block_report_ids": closed_reports,
            "unresolved_block_reports": unresolved_reports,
        }
        if producer is not None:
            facts["producer"] = producer
        if item.get("archived_at_utc") is not None:
            facts["archived_at_utc"] = item["archived_at_utc"]
        receipt = _make_receipt(
            command="occurrence_provenance.regenerate",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=regenerated_at,
            effect=effect,
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, **facts},
            result_identity_facts=facts,
        )
        insert_command_receipt(context.ledger, receipt)
    return {
        "ok": True,
        "command": "occurrence_provenance.regenerate",
        **receipt["result_identity_facts"],
    }


def _handle_notification_work_materialize(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "materialized_at_utc",
        "notification_intent_id",
        "range_start_utc",
        "range_end_utc",
        "limit",
        "notification_opportunity_ids",
    }
    _check_fields("notification_work.materialize", request, allowed)
    command_id, actor, materialized_at = _write_identity("notification_work.materialize", request, "materialized_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    intent_id = _optional_str(request, "notification_intent_id")
    range_start = _timestamp(request, "range_start_utc")
    range_end = _timestamp(request, "range_end_utc")
    limit = _notification_limit(request.get("limit"))
    explicit_ids: list[str] | None = None
    if "notification_opportunity_ids" in request:
        raw_ids = request["notification_opportunity_ids"]
        if not isinstance(raw_ids, list) or not raw_ids or not all(isinstance(value, str) and value for value in raw_ids):
            raise SpineValidationError(
                "invalid_notification_opportunity_ids",
                "notification_opportunity_ids must be a non-empty string array",
            )
        if len(raw_ids) != len(set(raw_ids)):
            raise SpineValidationError(
                "semantic_conflict:notification_opportunity_ids",
                "notification_opportunity_ids must be unique",
            )
        explicit_ids = raw_ids
    semantic = _semantic_request(
        "notification_work.materialize",
        command_id,
        actor,
        materialized_at,
        request,
        allowed,
    )
    replay = _compatible_replay("notification_work.materialize", command_id, semantic, context)
    if replay is not None:
        return {
            "ok": True,
            "command": "notification_work.materialize",
            **replay["result_identity_facts"],
        }
    item = _hydrated_item(context.ledger, item_id)
    if int(item["current_version"]) != target_version:
        raise SpineValidationError("stale_version:target_version", "target version is not current")
    opportunities_response = _handle_notification_opportunities(
        {
            "item_id": item_id,
            "evaluated_at_utc": materialized_at,
            "range_start_utc": range_start,
            "range_end_utc": range_end,
            "limit": str(limit),
            **({"notification_intent_id": intent_id} if intent_id is not None else {}),
        },
        context,
    )
    candidates = [dict(value) for value in opportunities_response["opportunities"] if value["actionable"]]
    if explicit_ids is not None:
        by_id = {str(value["notification_opportunity_id"]): value for value in candidates}
        missing = [value for value in explicit_ids if value not in by_id]
        if missing:
            raise SpineValidationError(
                "semantic_conflict:notification_opportunity_ids",
                "every requested notification opportunity must be actionable in the bounded range",
            )
        selected = [by_id[value] for value in explicit_ids]
        selected.sort(
            key=lambda value: (
                str(value["eligible_at_utc"]),
                str(value["notification_opportunity_id"]),
            )
        )
    else:
        selected = candidates
    policies = load_current_notification_policies(context.ledger, item_id=item_id)
    policies_by_intent = {str(value["notification_intent_id"]): value for value in policies}
    valid_targets = _current_notification_target_snapshots(
        context.ledger,
        item=item,
        policies=policies,
        recurrence=load_current_recurrence_set(context.ledger, item_id=item_id),
        range_start_utc=range_start,
        range_end_utc=range_end,
    )
    created_ids: list[str] = []
    retained_ids: list[str] = []
    cancelled_ids: list[str] = []
    with context.ledger:
        existing_rows = context.ledger.execute(
            """
            SELECT * FROM work_instances
            WHERE item_id = ? AND work_kind = 'notification_reminder'
              AND status = 'eligible' AND eligible_at_utc >= ? AND eligible_at_utc < ?
            ORDER BY work_instance_id
            """,
            (item_id, range_start, range_end),
        ).fetchall()
        for work in existing_rows:
            reason = _notification_work_stale_reason(
                context.ledger,
                item=item,
                work=work,
                policy=policies_by_intent.get(str(work["notification_intent_id"])),
                valid_targets=valid_targets,
            )
            if reason is not None:
                context.ledger.execute(
                    """
                    UPDATE work_instances
                    SET status = 'cancelled', reason_code = ?, updated_at_utc = ?
                    WHERE work_instance_id = ? AND status = 'eligible'
                    """,
                    (reason, materialized_at, work["work_instance_id"]),
                )
                cancelled_ids.append(work["work_instance_id"])
        for opportunity in selected:
            existing = context.ledger.execute(
                """
                SELECT work_instance_id, status FROM work_instances
                WHERE notification_opportunity_id = ? AND delivery_target_id = ?
                """,
                (
                    opportunity["notification_opportunity_id"],
                    opportunity["delivery_target_id"],
                ),
            ).fetchone()
            if existing is not None:
                retained_ids.append(existing["work_instance_id"])
                continue
            work_id, _ = notification_id(
                "work_instance",
                "spine.notification-work-instance-id.v1",
                {
                    "notification_opportunity_id": opportunity["notification_opportunity_id"],
                    "delivery_target_id": opportunity["delivery_target_id"],
                },
            )
            recipient_id = opportunity.get("recipient_subject_id") or opportunity.get("recipient_group_id")
            create_work_instance(
                context.ledger,
                work_instance_id=work_id,
                item_id=item_id,
                item_version=target_version,
                notification_policy_id=str(opportunity["notification_policy_id"]),
                notification_policy_item_version=int(str(opportunity["source_item_version"])),
                notification_intent_id=str(opportunity["notification_intent_id"]),
                notification_opportunity_id=str(opportunity["notification_opportunity_id"]),
                normalized_notification_schedule_hash=str(opportunity["normalized_notification_schedule_hash"]),
                occurrence_provenance_id=(
                    str(opportunity["occurrence_provenance_id"]) if opportunity.get("occurrence_provenance_id") is not None else None
                ),
                target_anchor_role=str(opportunity["anchor_role"]),
                application_scope=str(opportunity["application_scope"]),
                target_scheduled_fact=str(opportunity["target_scheduled_fact"]),
                target_at_utc=(str(opportunity["target_at_utc"]) if opportunity.get("target_at_utc") is not None else None),
                occurrence_key=(str(opportunity["occurrence_key"]) if opportunity.get("occurrence_key") is not None else None),
                delivery_target_id=str(opportunity["delivery_target_id"]),
                generation_source_kind="schedule_tick",
                generation_source_ref=str(opportunity["notification_opportunity_id"]),
                work_subject_ref=f"{opportunity['recipient_kind']}:{recipient_id}",
                policy_basis_ref=str(opportunity["normalized_notification_schedule_hash"]),
                eligible_at_utc=str(opportunity["eligible_at_utc"]),
                created_at_utc=materialized_at,
                manage_transaction=False,
            )
            created_ids.append(work_id)
        if cancelled_ids:
            effect = "notification_work_reconciled"
        elif created_ids:
            effect = "notification_work_created"
        elif retained_ids:
            effect = "notification_work_all_retained"
        else:
            effect = "notification_work_zero_selected"
        facts = {
            "command_receipt_id": _receipt_id("notification_work.materialize", command_id),
            "item_id": item_id,
            "item_type": item["item_type"],
            "target_version": str(target_version),
            "current_version": str(item["current_version"]),
            "materialized_at_utc": materialized_at,
            "range_start_utc": range_start,
            "range_end_utc": range_end,
            "limit": str(limit),
            "selected_notification_opportunity_ids": [value["notification_opportunity_id"] for value in selected],
            "created_work_instance_ids": sorted(created_ids),
            "retained_work_instance_ids": sorted(retained_ids),
            "cancelled_work_instance_ids": sorted(cancelled_ids),
            "changed": bool(created_ids or cancelled_ids),
            "effect": effect,
        }
        if intent_id is not None:
            facts["notification_intent_id"] = intent_id
        receipt = _make_receipt(
            command="notification_work.materialize",
            command_id=command_id,
            actor_subject_id=actor,
            action_timestamp_utc=materialized_at,
            effect=effect,
            item_id=item_id,
            target_version=str(target_version),
            semantic_facts={**semantic, **facts},
            result_identity_facts=facts,
        )
        insert_command_receipt(context.ledger, receipt)
    return {
        "ok": True,
        "command": "notification_work.materialize",
        **receipt["result_identity_facts"],
    }


def _handle_recurrence_instance_mutation(command: str, request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    timestamp_field = {
        "recurrence.instance.add": "added_at_utc",
        "recurrence.instance.remove": "removed_at_utc",
        "recurrence.instance.override": "overridden_at_utc",
    }[command]
    common_allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "recurrence_set_id",
        "recurrence_revision_id",
        timestamp_field,
        "segment_id",
        "reason_code",
    }
    if command == "recurrence.instance.add":
        allowed = common_allowed | {
            "scheduled_fact",
            "common_detail_patch",
            "event_detail_patch",
            "task_detail_patch",
        }
    elif command == "recurrence.instance.remove":
        allowed = common_allowed | {"target_occurrence_key"}
    else:
        allowed = common_allowed | {
            "target_occurrence_key",
            "expressed_scheduled_fact",
            "common_detail_patch",
            "event_detail_patch",
            "task_detail_patch",
            "lifecycle",
        }
    _check_fields(command, request, allowed)
    command_id, actor, changed_at = _write_identity(command, request, timestamp_field, context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    requested_set = _required_str(request, "recurrence_set_id")
    requested_revision = _required_str(request, "recurrence_revision_id")
    semantic = _semantic_request(command, command_id, actor, changed_at, request, allowed)
    replay = _compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        return {"ok": True, "command": command, **replay["result_identity_facts"]}
    item = _require_item_for_write(context.ledger, command, item_id, None, target_version)
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    if recurrence is None:
        raise SpineValidationError("recurrence_not_configured", "item has no recurrence set")
    if recurrence["recurrence_set_id"] != requested_set:
        raise SpineValidationError("stale_version:recurrence_set_id", "recurrence set is not current")
    if recurrence["recurrence_revision_id"] != requested_revision:
        raise SpineValidationError("stale_version:recurrence_revision_id", "recurrence revision is not current")

    rules = [dict(value) for value in recurrence["rules"]]
    rdates = [dict(value) for value in recurrence["rdates"]]
    exdates = [dict(value) for value in recurrence["exdates"]]
    overrides = [dict(value) for value in recurrence["overrides"]]
    effect: str
    produced: dict[str, object] = {}
    if command == "recurrence.instance.add":
        scheduled_fact = _required_str(request, "scheduled_fact")
        parse_scheduled_fact(
            scheduled_fact,
            time_basis=str(recurrence["time_basis"]),
            field="scheduled_fact",
        )
        segment = _select_recurrence_segment(
            recurrence, scheduled_fact=scheduled_fact, requested_segment_id=_optional_str(request, "segment_id")
        )
        duplicate = _occurrence_at_scheduled_fact(recurrence, scheduled_fact)
        patch_fields = _normalized_recurrence_override_fields(request, item_type=str(item["item_type"]), require_any=False)
        if duplicate is not None and not patch_fields:
            return _recurrence_mutation_noop(
                context,
                command=command,
                command_id=command_id,
                actor=actor,
                changed_at=changed_at,
                semantic=semantic,
                item=item,
                target_version=target_version,
                recurrence=recurrence,
                effect="duplicate_add_noop",
                extra={"scheduled_fact": scheduled_fact, "occurrence_key": duplicate["occurrence_key"]},
            )
        if duplicate is None:
            rdates.append(
                {
                    "segment_id": segment["segment_id"],
                    "scheduled_fact": scheduled_fact,
                    "status": "active",
                }
            )
            effect = "instance_add_rdate_created"
            produced = {"scheduled_fact": scheduled_fact}
        else:
            overrides, effect, produced = _replace_or_add_override(
                overrides,
                recurrence=recurrence,
                occurrence=duplicate,
                segment=segment,
                command_id=command_id,
                patch_fields=patch_fields,
                reason_code=_optional_str(request, "reason_code"),
                created_effect="instance_add_override_created",
                replaced_effect="instance_add_override_replaced",
            )
    elif command == "recurrence.instance.remove":
        key = _required_str(request, "target_occurrence_key")
        reason = _required_str(request, "reason_code")
        existing_exdate = next(
            (value for value in exdates if value.get("status") == "active" and value["target_occurrence_key"] == key),
            None,
        )
        if existing_exdate is not None:
            if existing_exdate["reason_code"] != reason:
                raise SpineValidationError("semantic_conflict:reason_code", "excluded occurrence has a different reason code")
            return _recurrence_mutation_noop(
                context,
                command=command,
                command_id=command_id,
                actor=actor,
                changed_at=changed_at,
                semantic=semantic,
                item=item,
                target_version=target_version,
                recurrence=recurrence,
                effect="remove_noop_already_excluded",
                extra={"target_occurrence_key": key},
            )
        occurrence = _resolve_current_occurrence(recurrence, key)
        segment = _segment_for_occurrence(recurrence, occurrence, requested_segment_id=_optional_str(request, "segment_id"))
        exdates.append(
            {
                "segment_id": segment["segment_id"],
                "target_occurrence_key": key,
                "target_occurrence_selector": occurrence["target_occurrence_selector"],
                "scheduled_fact": occurrence["original_scheduled_fact"],
                "reason_code": reason,
                "status": "active",
            }
        )
        override_superseded = False
        for value in overrides:
            if value.get("status") == "active" and value["target_occurrence_key"] == key:
                value["status"] = "superseded"
                override_superseded = True
        effect = "instance_remove_exdate_created_override_superseded" if override_superseded else "instance_remove_exdate_created"
        produced = {"target_occurrence_key": key}
    else:
        key = _required_str(request, "target_occurrence_key")
        occurrence = _resolve_current_occurrence(recurrence, key)
        segment = _segment_for_occurrence(recurrence, occurrence, requested_segment_id=_optional_str(request, "segment_id"))
        patch_fields = _normalized_recurrence_override_fields(request, item_type=str(item["item_type"]), require_any=True)
        reason = _optional_str(request, "reason_code")
        active_override = next(
            (value for value in overrides if value.get("status") == "active" and value["target_occurrence_key"] == key),
            None,
        )
        if active_override is not None and _override_semantics(active_override) == {
            **patch_fields,
            **({"reason_code": reason} if reason is not None else {}),
        }:
            return _recurrence_mutation_noop(
                context,
                command=command,
                command_id=command_id,
                actor=actor,
                changed_at=changed_at,
                semantic=semantic,
                item=item,
                target_version=target_version,
                recurrence=recurrence,
                effect="override_noop",
                extra={"target_occurrence_key": key, "override_id": active_override["override_id"]},
            )
        overrides, effect, produced = _replace_or_add_override(
            overrides,
            recurrence=recurrence,
            occurrence=occurrence,
            segment=segment,
            command_id=command_id,
            patch_fields=patch_fields,
            reason_code=reason,
            created_effect="instance_override_created",
            replaced_effect="instance_override_replaced",
        )

    successor = build_successor_recurrence_revision(
        recurrence,
        source_item_version=str(target_version + 1),
        command_id=command_id,
        rules=rules,
        rdates=rdates,
        exdates=exdates,
        overrides=overrides,
    )
    if produced.get("revision_key") is not None:
        created_override = next(
            value
            for value in successor.value["overrides"]  # type: ignore[union-attr]
            if value.get("revision_key") == produced["revision_key"]
        )
        produced["override_id"] = created_override["override_id"]
    elif produced.get("scheduled_fact") is not None:
        created_rdate = next(
            value
            for value in successor.value["rdates"]  # type: ignore[union-attr]
            if value.get("status") == "active" and value["scheduled_fact"] == produced["scheduled_fact"]
        )
        produced["rdate_id"] = created_rdate["rdate_id"]
    elif produced.get("target_occurrence_key") is not None:
        created_exdate = next(
            value
            for value in successor.value["exdates"]  # type: ignore[union-attr]
            if value.get("status") == "active" and value["target_occurrence_key"] == produced["target_occurrence_key"]
        )
        produced["exdate_id"] = created_exdate["exdate_id"]
    audit_id = _derived_id(command, command_id, "audit", "/audit")
    lineage = derive_recurrence_lineage(recurrence, successor.value, command_id=command_id, effect=effect)

    facts = {
        "command_receipt_id": _receipt_id(command, command_id),
        "item_id": item_id,
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "current_version": str(target_version + 1),
        "recurrence_set_id": successor.value["recurrence_set_id"],
        "prior_recurrence_revision_id": recurrence["recurrence_revision_id"],
        "recurrence_revision_id": successor.value["recurrence_revision_id"],
        "revision_number": successor.value["revision_number"],
        "normalized_recurrence_set_hash": successor.value["normalized_recurrence_set_hash"],
        "audit_id": audit_id,
        "lineage_ids": [value["lineage_id"] for value in lineage],
        "lineage": lineage,
        "changed": True,
        "effect": effect,
        **produced,
    }
    receipt = _make_receipt(
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=changed_at,
        effect=effect,
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, **facts},
        result_identity_facts=facts,
    )

    def insert_revision(connection: sqlite3.Connection, _version: int) -> None:
        insert_initial_recurrence_set(
            connection,
            normalized=successor,
            command_id=command_id,
            created_at_utc=changed_at,
        )
        insert_recurrence_lineage(connection, lineage=lineage)
        insert_command_receipt(connection, receipt)

    create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=changed_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        audit_action=effect,
        reason_code=effect,
        insert_canonical_extension=insert_revision,
        supporting_command_id=command_id,
    )
    return {"ok": True, "command": command, **receipt["result_identity_facts"]}


def _handle_recurrence_series_edit(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    command = "recurrence.series.edit"
    allowed = {
        "command_id",
        "actor_subject_id",
        "item_id",
        "target_version",
        "recurrence_set_id",
        "recurrence_revision_id",
        "edited_at_utc",
        "edit_scope",
        "target_occurrence_key",
        "recurrence_patch",
    }
    _check_fields(command, request, allowed)
    command_id, actor, changed_at = _write_identity(command, request, "edited_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    requested_set = _required_str(request, "recurrence_set_id")
    requested_revision = _required_str(request, "recurrence_revision_id")
    scope = _enum(
        request.get("edit_scope"),
        "edit_scope",
        {"one", "this_and_following", "whole_series"},
    )
    patch = request.get("recurrence_patch")
    if not isinstance(patch, Mapping):
        raise SpineValidationError("missing_recurrence_patch", "recurrence_patch must be an object")
    forbidden_identity = sorted(set(patch) & {"time_basis", "timezone", "timezone_database_version"})
    if forbidden_identity:
        field = forbidden_identity[0]
        raise SpineValidationError(
            f"unsupported_field:recurrence_patch.{field}",
            "recurrence-set identity facts cannot be edited",
        )
    target_key = _optional_str(request, "target_occurrence_key")
    if scope in {"one", "this_and_following"} and target_key is None:
        raise SpineValidationError("missing_target_occurrence_key", "target_occurrence_key is required")
    if scope == "whole_series" and target_key is not None:
        raise SpineValidationError(
            "unsupported_field:target_occurrence_key",
            "whole_series forbids target_occurrence_key",
        )
    semantic = _semantic_request(command, command_id, actor, changed_at, request, allowed)
    replay = _compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        return {"ok": True, "command": command, **replay["result_identity_facts"]}
    item = _require_item_for_write(context.ledger, command, item_id, None, target_version)
    recurrence = load_current_recurrence_set(context.ledger, item_id=item_id)
    if recurrence is None:
        raise SpineValidationError("recurrence_not_configured", "item has no recurrence set")
    if recurrence["recurrence_set_id"] != requested_set:
        raise SpineValidationError("stale_version:recurrence_set_id", "recurrence set is not current")
    if recurrence["recurrence_revision_id"] != requested_revision:
        raise SpineValidationError("stale_version:recurrence_revision_id", "recurrence revision is not current")

    if scope == "one":
        successor, effect, produced = _series_edit_one(
            recurrence,
            patch=patch,
            target_occurrence_key=str(target_key),
            item_type=str(item["item_type"]),
            command_id=command_id,
            source_item_version=str(target_version + 1),
        )
    elif scope == "whole_series":
        successor, effect, produced = _series_edit_whole(
            recurrence,
            patch=patch,
            item_type=str(item["item_type"]),
            command_id=command_id,
            source_item_version=str(target_version + 1),
        )
    else:
        successor, effect, produced = _series_edit_following(
            recurrence,
            patch=patch,
            target_occurrence_key=str(target_key),
            item_type=str(item["item_type"]),
            command_id=command_id,
            source_item_version=str(target_version + 1),
        )
    if successor is None:
        return _recurrence_mutation_noop(
            context,
            command=command,
            command_id=command_id,
            actor=actor,
            changed_at=changed_at,
            semantic=semantic,
            item=item,
            target_version=target_version,
            recurrence=recurrence,
            effect="series_edit_noop",
            extra={"edit_scope": scope, **produced},
        )
    return _persist_series_edit_success(
        context,
        item=item,
        target_version=target_version,
        recurrence=recurrence,
        successor=successor,
        command_id=command_id,
        actor=actor,
        changed_at=changed_at,
        effect=effect,
        semantic=semantic,
        produced={"edit_scope": scope, **produced},
    )


def _series_edit_one(
    recurrence: Mapping[str, object],
    *,
    patch: Mapping[str, Any],
    target_occurrence_key: str,
    item_type: str,
    command_id: str,
    source_item_version: str,
) -> tuple[NormalizedRecurrenceSet | None, str, dict[str, object]]:
    unknown = sorted(set(patch) - {"exclude", "override"})
    if unknown:
        raise SpineValidationError(f"unsupported_field:recurrence_patch.{unknown[0]}", "unsupported one-scope patch field")
    if len(patch) != 1:
        if not patch:
            return None, "series_edit_noop", {"target_occurrence_key": target_occurrence_key}
        raise SpineValidationError("invalid_recurrence_patch", "one scope requires exactly one operation")
    occurrence = _resolve_current_occurrence(recurrence, target_occurrence_key)
    segment = _segment_for_occurrence(recurrence, occurrence, requested_segment_id=None)
    exdates = [dict(value) for value in recurrence["exdates"]]  # type: ignore[index]
    overrides = [dict(value) for value in recurrence["overrides"]]  # type: ignore[index]
    produced: dict[str, object] = {"target_occurrence_key": target_occurrence_key}
    if "exclude" in patch:
        exclude = patch["exclude"]
        if not isinstance(exclude, Mapping) or set(exclude) != {"reason_code"}:
            raise SpineValidationError("invalid_recurrence_patch", "exclude requires only reason_code")
        reason = exclude.get("reason_code")
        if not isinstance(reason, str) or not reason:
            raise SpineValidationError("invalid_recurrence_patch", "exclude reason_code is required")
        existing = next(
            (value for value in exdates if value.get("status") == "active" and value["target_occurrence_key"] == target_occurrence_key),
            None,
        )
        if existing is not None:
            if existing["reason_code"] == reason:
                return None, "series_edit_noop", produced
            raise SpineValidationError("semantic_conflict:reason_code", "excluded occurrence has a different reason")
        exdates.append(
            {
                "segment_id": segment["segment_id"],
                "target_occurrence_key": target_occurrence_key,
                "target_occurrence_selector": occurrence["target_occurrence_selector"],
                "scheduled_fact": occurrence["original_scheduled_fact"],
                "reason_code": reason,
                "status": "active",
            }
        )
        for value in overrides:
            if value.get("status") == "active" and value["target_occurrence_key"] == target_occurrence_key:
                value["status"] = "superseded"
        effect = "series_edit_one_excluded"
    else:
        override = patch["override"]
        if not isinstance(override, Mapping):
            raise SpineValidationError("invalid_recurrence_patch", "override must be an object")
        allowed = {
            "expressed_scheduled_fact",
            "common_detail_patch",
            "event_detail_patch",
            "task_detail_patch",
            "lifecycle",
            "reason_code",
        }
        unknown = sorted(set(override) - allowed)
        if unknown:
            raise SpineValidationError(f"unsupported_field:recurrence_patch.override.{unknown[0]}", "unsupported override field")
        fields = _normalized_recurrence_override_fields(override, item_type=item_type, require_any=True)
        reason = _optional_str(override, "reason_code")
        active = next(
            (value for value in overrides if value.get("status") == "active" and value["target_occurrence_key"] == target_occurrence_key),
            None,
        )
        requested_semantics = {**fields, **({"reason_code": reason} if reason is not None else {})}
        if active is not None and _override_semantics(active) == requested_semantics:
            return None, "series_edit_noop", produced
        overrides, branch, produced_override = _replace_or_add_override(
            overrides,
            recurrence=recurrence,
            occurrence=occurrence,
            segment=segment,
            command_id=command_id,
            patch_fields=fields,
            reason_code=reason,
            created_effect="series_edit_one_override_created",
            replaced_effect="series_edit_one_override_replaced",
        )
        effect = branch
        produced.update(produced_override)
    successor = build_successor_recurrence_revision(
        recurrence,
        source_item_version=source_item_version,
        command_id=command_id,
        exdates=exdates,
        overrides=overrides,
    )
    return successor, effect, produced


def _series_edit_whole(
    recurrence: Mapping[str, object],
    *,
    patch: Mapping[str, Any],
    item_type: str,
    command_id: str,
    source_item_version: str,
) -> tuple[NormalizedRecurrenceSet | None, str, dict[str, object]]:
    collections = _series_replacement_collections(
        recurrence,
        patch=patch,
        item_type=item_type,
        command_id=command_id,
        allowed_segment_ids={
            str(value["segment_id"])
            for value in recurrence["segments"]  # type: ignore[index]
            if value["status"] == "active"
        },
        default_segment_ref=None,
    )
    if not patch:
        return None, "series_edit_noop", {}
    successor = build_successor_recurrence_revision(
        recurrence,
        source_item_version=source_item_version,
        command_id=command_id,
        **collections,
    )
    if _specified_series_collections_equal(recurrence, successor.value, set(patch)):
        return None, "series_edit_noop", {}
    return successor, "series_edit_whole_applied", {}


def _series_replacement_collections(
    recurrence: Mapping[str, object],
    *,
    patch: Mapping[str, Any],
    item_type: str,
    command_id: str,
    allowed_segment_ids: set[str],
    default_segment_ref: str | None,
) -> dict[str, list[dict[str, object]]]:
    allowed = {"rules", "rdates", "exdates", "overrides"}
    unknown = sorted(set(patch) - allowed)
    if unknown:
        raise SpineValidationError(f"unsupported_field:recurrence_patch.{unknown[0]}", "unsupported recurrence collection")
    result: dict[str, list[dict[str, object]]] = {}
    for name in allowed:
        if name not in patch:
            continue
        rows = patch[name]
        if not isinstance(rows, list):
            raise SpineValidationError(f"invalid_recurrence_patch:{name}", f"recurrence_patch.{name} must be an array")
        normalized_rows: list[dict[str, object]] = []
        for index, raw in enumerate(rows):
            if not isinstance(raw, Mapping):
                raise SpineValidationError(f"invalid_recurrence_patch:{name}[{index}]", "collection entry must be an object")
            entry = dict(raw)
            supplied_segment = entry.pop("segment_id", None)
            if default_segment_ref is None:
                if not isinstance(supplied_segment, str) or supplied_segment not in allowed_segment_ids:
                    raise SpineValidationError(
                        f"semantic_conflict:recurrence_patch.{name}[{index}].segment_id",
                        "whole-series entries must name one active segment",
                    )
                entry["segment_id"] = supplied_segment
            else:
                if supplied_segment is not None:
                    raise SpineValidationError(
                        f"unsupported_field:recurrence_patch.{name}[{index}].segment_id",
                        "following-scope entries cannot name a segment",
                    )
                entry["segment_ref"] = default_segment_ref
            if name == "rules":
                forbidden = sorted(
                    set(entry)
                    - {
                        "segment_id",
                        "segment_ref",
                        "frequency",
                        "interval",
                        "seed",
                        "start_bound",
                        "end_condition",
                        "by_month",
                        "by_month_day",
                        "by_weekday",
                        "by_set_position",
                        "week_start",
                    }
                )
                if forbidden:
                    raise SpineValidationError(
                        f"unsupported_field:recurrence_patch.rules[{index}].{forbidden[0]}",
                        "generated rule fields are forbidden",
                    )
                entry["status"] = "active"
            elif name == "rdates":
                expected = {"segment_id", "segment_ref", "scheduled_fact"}
                forbidden = sorted(set(entry) - expected)
                if forbidden or "scheduled_fact" not in entry:
                    field = forbidden[0] if forbidden else "scheduled_fact"
                    raise SpineValidationError(f"invalid_recurrence_patch:rdates[{index}].{field}", "invalid rdate entry")
                entry["status"] = "active"
            else:
                key = entry.get("target_occurrence_key")
                if not isinstance(key, str) or not key:
                    raise SpineValidationError(
                        f"invalid_recurrence_patch:{name}[{index}].target_occurrence_key",
                        "target occurrence key is required",
                    )
                occurrence = _resolve_current_occurrence(recurrence, key)
                target_segment = _segment_for_occurrence(
                    recurrence, occurrence, requested_segment_id=(str(supplied_segment) if supplied_segment is not None else None)
                )
                if name == "exdates":
                    forbidden = sorted(set(entry) - {"segment_id", "segment_ref", "target_occurrence_key", "reason_code"})
                    reason = entry.get("reason_code")
                    if forbidden or not isinstance(reason, str) or not reason:
                        field = forbidden[0] if forbidden else "reason_code"
                        raise SpineValidationError(f"invalid_recurrence_patch:exdates[{index}].{field}", "invalid exdate entry")
                    entry.update(
                        {
                            "target_occurrence_selector": occurrence["target_occurrence_selector"],
                            "scheduled_fact": occurrence["original_scheduled_fact"],
                            "status": "active",
                        }
                    )
                else:
                    allowed_override = {
                        "segment_id",
                        "segment_ref",
                        "target_occurrence_key",
                        "expressed_scheduled_fact",
                        "common_detail_patch",
                        "event_detail_patch",
                        "task_detail_patch",
                        "lifecycle",
                        "reason_code",
                    }
                    forbidden = sorted(set(entry) - allowed_override)
                    if forbidden:
                        raise SpineValidationError(
                            f"unsupported_field:recurrence_patch.overrides[{index}].{forbidden[0]}",
                            "generated override fields are forbidden",
                        )
                    fields = _normalized_recurrence_override_fields(entry, item_type=item_type, require_any=True)
                    kind, path = _override_kind(fields)
                    selector = occurrence["target_occurrence_selector"]
                    segment_ref = default_segment_ref or str(target_segment["segment_index"])
                    revision_key, _ = generated_id(
                        "revkey",
                        "spine.recurrence-override-revision-key.v2",
                        {
                            "command_id": command_id,
                            "recurrence_set_id": recurrence["recurrence_set_id"],
                            "prior_recurrence_revision_id": recurrence["recurrence_revision_id"],
                            "target_occurrence_selector": selector,
                            "segment_ref": segment_ref,
                            "override_path": path,
                        },
                    )
                    entry = {
                        **({"segment_id": supplied_segment} if default_segment_ref is None else {"segment_ref": default_segment_ref}),
                        "target_occurrence_key": key,
                        "target_occurrence_selector": selector,
                        "override_kind": kind,
                        "revision_key": revision_key,
                        **fields,
                        **({"reason_code": raw["reason_code"]} if raw.get("reason_code") is not None else {}),
                        "status": "active",
                    }
            normalized_rows.append(entry)
        result[name] = normalized_rows
    if not result:
        return result
    active_rules = result.get("rules", [dict(value) for value in recurrence["rules"]])  # type: ignore[index]
    active_rdates = result.get("rdates", [dict(value) for value in recurrence["rdates"]])  # type: ignore[index]
    if not any(value.get("status", "active") == "active" for value in active_rules + active_rdates):
        raise SpineValidationError("semantic_conflict:recurrence_patch", "a series must retain an active rule or rdate")
    return result


def _specified_series_collections_equal(current: Mapping[str, object], successor: Mapping[str, object], specified: set[str]) -> bool:
    current_segments = {
        str(value["segment_id"]): str(value["segment_id"])
        for value in current["segments"]  # type: ignore[index]
    }
    successor_segments = {
        str(value["segment_id"]): str(value.get("lineage_parent_segment_id") or value["segment_id"])
        for value in successor["segments"]  # type: ignore[index]
    }
    id_fields = {"rules": "rule_id", "rdates": "rdate_id", "exdates": "exdate_id", "overrides": "override_id"}
    for name in specified:
        if name not in id_fields:
            continue
        left = _series_collection_semantics(current[name], current_segments, id_fields[name])
        right = _series_collection_semantics(successor[name], successor_segments, id_fields[name])
        if left != right:
            return False
    return True


def _series_collection_semantics(rows: object, segment_map: Mapping[str, str], id_field: str) -> list[bytes]:
    assert isinstance(rows, list)
    result: list[bytes] = []
    for raw in rows:
        assert isinstance(raw, Mapping)
        value = {key: raw[key] for key in raw if key not in {id_field, "segment_id", "revision_key", "prior_target_occurrence_key"}}
        value["segment_identity"] = segment_map[str(raw["segment_id"])]
        result.append(canonical_json_bytes(value))
    return sorted(result)


def _series_edit_following(
    recurrence: Mapping[str, object],
    *,
    patch: Mapping[str, Any],
    target_occurrence_key: str,
    item_type: str,
    command_id: str,
    source_item_version: str,
) -> tuple[NormalizedRecurrenceSet | None, str, dict[str, object]]:
    if not patch:
        return None, "series_edit_noop", {"target_occurrence_key": target_occurrence_key}
    occurrence = _resolve_current_occurrence(recurrence, target_occurrence_key)
    split = str(occurrence["original_scheduled_fact"])
    selected = _segment_for_occurrence(recurrence, occurrence, requested_segment_id=None)
    prior_revision = str(recurrence["recurrence_revision_id"])
    selected_id = str(selected["segment_id"])
    segment_drafts: list[dict[str, object]] = []
    token_by_id: dict[str, str] = {}
    for segment in recurrence["segments"]:  # type: ignore[index]
        if segment["status"] != "active" or segment["segment_id"] == selected_id:
            continue
        token = f"copy:{segment['segment_id']}"
        token_by_id[str(segment["segment_id"])] = token
        segment_drafts.append(
            {
                "segment_ref": token,
                "active_start": segment["active_start"],
                **({"active_end": segment["active_end"]} if segment.get("active_end") is not None else {}),
                "source_revision_id": prior_revision,
                "status": "active",
                "lineage_parent_segment_id": segment["segment_id"],
                "created_by_command_id": command_id,
            }
        )
    if split > str(selected["active_start"]):
        token_by_id[selected_id] = "prefix"
        segment_drafts.append(
            {
                "segment_ref": "prefix",
                "active_start": selected["active_start"],
                "active_end": split,
                "source_revision_id": prior_revision,
                "status": "active",
                "lineage_parent_segment_id": selected_id,
                "created_by_command_id": command_id,
                "reason_code": "this_and_following_prefix",
            }
        )
        historical_status = "retired"
    else:
        historical_status = "superseded"
    segment_drafts.append(
        {
            "segment_ref": "historical",
            "active_start": selected["active_start"],
            **({"active_end": selected["active_end"]} if selected.get("active_end") is not None else {}),
            "source_revision_id": prior_revision,
            "status": historical_status,
            "lineage_parent_segment_id": selected_id,
            "created_by_command_id": command_id,
            "reason_code": "this_and_following_split",
        }
    )
    segment_drafts.append(
        {
            "segment_ref": "following",
            "active_start": split,
            **({"active_end": selected["active_end"]} if selected.get("active_end") is not None else {}),
            "source_revision_id": prior_revision,
            "status": "active",
            "lineage_parent_segment_id": selected_id,
            "created_by_command_id": command_id,
            "reason_code": "this_and_following_applied",
        }
    )
    replacements = _series_replacement_collections(
        recurrence,
        patch=patch,
        item_type=item_type,
        command_id=command_id,
        allowed_segment_ids={selected_id},
        default_segment_ref="following",
    )
    collections: dict[str, list[dict[str, object]]] = {"rules": [], "rdates": [], "exdates": [], "overrides": []}
    for name in collections:
        for raw in recurrence[name]:  # type: ignore[index]
            row = dict(raw)
            segment_id = str(row["segment_id"])
            if row.get("status") != "active":
                continue
            if segment_id != selected_id:
                row.pop("segment_id", None)
                row["segment_ref"] = token_by_id[segment_id]
                collections[name].append(row)
                continue
            scheduled = _recurrence_child_scheduled_fact(row, name=name)
            if split > str(selected["active_start"]) and (name == "rules" or scheduled < split):
                prefix = dict(row)
                prefix.pop("segment_id", None)
                prefix["segment_ref"] = "prefix"
                collections[name].append(prefix)
            if name in replacements:
                continue
            if name == "rules":
                following = _following_rule_copy(row, split=split, time_basis=str(recurrence["time_basis"]))
                if following is None:
                    continue
            elif scheduled < split:
                continue
            else:
                following = dict(row)
            following.pop("segment_id", None)
            following["segment_ref"] = "following"
            collections[name].append(following)
        if name in replacements:
            collections[name].extend(replacements[name])
    if not any(value.get("status", "active") == "active" for value in collections["rules"] + collections["rdates"]):
        raise SpineValidationError("semantic_conflict:recurrence_patch", "following segment must retain an active rule or rdate")
    provisional = build_successor_recurrence_revision(
        recurrence,
        source_item_version=source_item_version,
        command_id=command_id,
        segments=segment_drafts,
        rules=collections["rules"],
        rdates=collections["rdates"],
        exdates=[],
        overrides=[],
    )
    collections["exdates"] = _retarget_following_children(
        provisional.value,
        rows=collections["exdates"],
        name="exdates",
        command_id=command_id,
        prior_recurrence=recurrence,
    )
    collections["overrides"] = _retarget_following_children(
        provisional.value,
        rows=collections["overrides"],
        name="overrides",
        command_id=command_id,
        prior_recurrence=recurrence,
    )
    successor = build_successor_recurrence_revision(
        recurrence,
        source_item_version=source_item_version,
        command_id=command_id,
        segments=segment_drafts,
        **collections,
    )
    return (
        successor,
        "series_edit_following_applied",
        {
            "target_occurrence_key": target_occurrence_key,
            "split_scheduled_fact": split,
        },
    )


def _recurrence_child_scheduled_fact(row: Mapping[str, object], *, name: str) -> str:
    if name == "rules":
        return str(row["start_bound"])
    if name in {"rdates", "exdates"}:
        return str(row["scheduled_fact"])
    selector = row.get("target_occurrence_selector")
    if not isinstance(selector, Mapping) or not isinstance(selector.get("scheduled_fact"), str):
        raise SpineValidationError("semantic_conflict:target_occurrence_key", "override selector is incomplete")
    return str(selector["scheduled_fact"])


def _following_rule_copy(row: Mapping[str, object], *, split: str, time_basis: str) -> dict[str, object] | None:
    result = dict(row)
    if str(result["start_bound"]) < split:
        result["start_bound"] = split
    end = result.get("end_condition")
    if isinstance(end, Mapping) and end.get("kind") == "count":
        original_count = int(str(end["count"]))
        rule = normalize_rule(row, time_basis=time_basis, field="copied_rule")
        produced = expand_rule(
            rule,
            time_basis=time_basis,
            range_start=str(row["start_bound"]),
            range_end=split,
            candidate_limit=max(original_count + 1, 10_000),
        )
        remaining = original_count - len(produced.candidates)
        if remaining <= 0:
            return None
        result["end_condition"] = {"kind": "count", "count": str(remaining)}
    return result


def _retarget_following_children(
    provisional: Mapping[str, object],
    *,
    rows: list[dict[str, object]],
    name: str,
    command_id: str,
    prior_recurrence: Mapping[str, object],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows:
        scheduled = _recurrence_child_scheduled_fact(row, name=name)
        expansion = expand_recurrence_set(
            dict(provisional),
            range_basis="original_schedule",
            range_start=scheduled,
            range_end=_next_scheduled_fact(scheduled, time_basis=str(provisional["time_basis"])),
        )
        matches = [value for value in expansion.occurrences if value["original_scheduled_fact"] == scheduled]
        if len(matches) != 1:
            raise SpineValidationError(
                "semantic_conflict:target_occurrence_key",
                "target-bearing child has no unique following occurrence",
            )
        occurrence = matches[0]
        updated = dict(row)
        prior_key = updated.get("target_occurrence_key")
        updated["target_occurrence_key"] = occurrence["occurrence_key"]
        updated["target_occurrence_selector"] = occurrence["target_occurrence_selector"]
        if prior_key != occurrence["occurrence_key"]:
            updated["prior_target_occurrence_key"] = prior_key
        if name == "overrides":
            fields = _override_semantics(updated)
            fields.pop("reason_code", None)
            _, path = _override_kind(fields)
            revision_key, _ = generated_id(
                "revkey",
                "spine.recurrence-override-revision-key.v2",
                {
                    "command_id": command_id,
                    "recurrence_set_id": prior_recurrence["recurrence_set_id"],
                    "prior_recurrence_revision_id": prior_recurrence["recurrence_revision_id"],
                    "target_occurrence_selector": occurrence["target_occurrence_selector"],
                    "segment_ref": occurrence["target_occurrence_selector"]["segment_ref"],
                    "override_path": path,
                },
            )
            updated["revision_key"] = revision_key
        result.append(updated)
    return result


def _persist_series_edit_success(
    context: CommandContext,
    *,
    item: Mapping[str, Any],
    target_version: int,
    recurrence: Mapping[str, object],
    successor: NormalizedRecurrenceSet,
    command_id: str,
    actor: str,
    changed_at: str,
    effect: str,
    semantic: Mapping[str, Any],
    produced: Mapping[str, object],
) -> dict[str, Any]:
    command = "recurrence.series.edit"
    audit_id = _derived_id(command, command_id, "audit", "/audit")
    lineage = derive_recurrence_lineage(recurrence, successor.value, command_id=command_id, effect=effect)

    facts = {
        "command_receipt_id": _receipt_id(command, command_id),
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "current_version": str(target_version + 1),
        "recurrence_set_id": successor.value["recurrence_set_id"],
        "prior_recurrence_revision_id": recurrence["recurrence_revision_id"],
        "recurrence_revision_id": successor.value["recurrence_revision_id"],
        "revision_number": successor.value["revision_number"],
        "normalized_recurrence_set_hash": successor.value["normalized_recurrence_set_hash"],
        "audit_id": audit_id,
        "lineage_ids": [value["lineage_id"] for value in lineage],
        "lineage": lineage,
        "changed": True,
        "effect": effect,
        **dict(produced),
    }
    receipt = _make_receipt(
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=changed_at,
        effect=effect,
        item_id=str(item["item_id"]),
        target_version=str(target_version),
        semantic_facts={**semantic, **facts},
        result_identity_facts=facts,
    )

    def insert_revision(connection: sqlite3.Connection, _version: int) -> None:
        insert_initial_recurrence_set(connection, normalized=successor, command_id=command_id, created_at_utc=changed_at)
        insert_recurrence_lineage(connection, lineage=lineage)
        insert_command_receipt(connection, receipt)

    create_next_item_version(
        context.ledger,
        item_id=str(item["item_id"]),
        target_version=target_version,
        created_at_utc=changed_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        audit_action=effect,
        reason_code=effect,
        insert_canonical_extension=insert_revision,
        supporting_command_id=command_id,
    )
    return {"ok": True, "command": command, **receipt["result_identity_facts"]}


def _lifecycle(
    command: str,
    request: Mapping[str, Any],
    context: CommandContext,
    item_type: str,
    timestamp_field: str,
    effect_name: str,
    workflow: Any,
    terminal_status: str,
) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "item_id", "target_version", timestamp_field}
    if command == "task.complete":
        allowed = allowed | {"completion_state"}
    _check_fields(command, request, allowed)
    command_id, actor, at = _write_identity(command, request, timestamp_field, context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    semantic = _semantic_request(command, command_id, actor, at, request, allowed)
    replay = _compatible_replay(command, command_id, semantic, context)
    if replay is not None:
        return _lifecycle_response(
            command,
            _receipt_item(context.ledger, replay),
            effect_name,
            False,
            replay["command_receipt_id"],
            replay["result_identity_facts"].get("audit_id"),
            target_version=str(replay["result_identity_facts"]["target_version"]),
        )
    item = _hydrated_item(context.ledger, item_id)
    if item["item_type"] != item_type:
        return _wrong_type(command, item_id, item_type, str(item["item_type"]))
    detail_status = item["detail"]["event_status"] if item_type == "event" else item["detail"]["task_status"]
    if detail_status == terminal_status or detail_status != ("scheduled" if item_type == "event" else "open"):
        return _error(command, "invalid_state_transition", "item is already terminal", "status")
    item = _require_item_for_write(context.ledger, command, item_id, item_type, target_version)
    audit_id = _derived_id(command, command_id, "audit", "/audit")
    if command == "task.complete":
        mutation = workflow(
            context.ledger,
            item_id=item_id,
            target_version=target_version,
            completed_at_utc=at,
            completed_by_subject_id=actor,
            completion_state=_optional_str(request, "completion_state"),
            audit_id=audit_id,
            supporting_command_id=command_id,
        )
    elif command == "event.cancel":
        mutation = workflow(
            context.ledger,
            item_id=item_id,
            target_version=target_version,
            cancelled_at_utc=at,
            cancelled_by_subject_id=actor,
            audit_id=audit_id,
            supporting_command_id=command_id,
        )
    else:
        mutation = workflow(
            context.ledger,
            item_id=item_id,
            target_version=target_version,
            cancelled_at_utc=at,
            cancelled_by_subject_id=actor,
            audit_id=audit_id,
            supporting_command_id=command_id,
        )
    receipt = _store_write_receipt(
        context,
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=at,
        effect=f"{item_type}_{effect_name}",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, "version": str(mutation.version), effect_name: True},
        result_identity_facts={
            "command_receipt_id": _receipt_id(command, command_id),
            "item_id": item_id,
            "target_version": str(target_version),
            "version": str(mutation.version),
            "current_version": str(mutation.version),
            "audit_id": mutation.audit_id,
        },
    )
    return _lifecycle_response(
        command,
        _hydrated_item(context.ledger, item_id),
        effect_name,
        True,
        receipt["command_receipt_id"],
        mutation.audit_id,
        target_version=str(target_version),
    )


def _write_identity(command: str, request: Mapping[str, Any], timestamp_field: str, context: CommandContext) -> tuple[str, str, str]:
    command_id = _required_str(request, "command_id")
    actor = _required_str(request, "actor_subject_id")
    action_timestamp = _timestamp(request, timestamp_field)
    if command != "subject.upsert" and not _subject_exists(context.ledger, actor):
        raise SpineValidationError("actor_not_found", "actor subject not found")
    return command_id, actor, action_timestamp


def _schedule_semantic_request(
    command_id: str,
    actor: str,
    created_at: str,
    request: Mapping[str, Any],
    allowed: set[str],
) -> dict[str, Any]:
    semantic = _semantic_request("schedule.create", command_id, actor, created_at, request, allowed)
    reminders = semantic.get("reminders")
    if isinstance(reminders, list) and all(isinstance(entry, dict) for entry in reminders):
        semantic["reminders"] = sorted(reminders, key=lambda entry: str(entry.get("policy_key", "")))
    item = semantic.get("item")
    if isinstance(item, dict):
        task_detail = item.get("task_detail")
        if isinstance(task_detail, dict):
            roles = task_detail.get("subject_roles")
            if isinstance(roles, list) and all(isinstance(entry, dict) for entry in roles):
                normalized_roles = [
                    {**entry, **({"status": "active"} if "status" not in entry else {})}
                    for entry in roles
                ]
                task_detail["subject_roles"] = sorted(
                    normalized_roles,
                    key=lambda entry: (
                        str(entry.get("role", "")),
                        str(entry.get("subject_id", "")),
                        str(entry.get("status", "")),
                    ),
                )
    return semantic


def _schedule_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an object")
    return dict(value)


def _schedule_exact_fields(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SpineValidationError(
            f"unsupported_field:{field}.{unknown[0]}",
            f"unsupported field for {field}: {unknown[0]}",
        )


def _nested_required_str(value: Mapping[str, Any], key: str, field: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or result == "":
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a non-empty string")
    return result


def _nested_optional_str(value: Mapping[str, Any], key: str, field: str) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    if not isinstance(result, str):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a string")
    return result


def _schedule_validate_item_fields(item: Mapping[str, Any], *, item_type: str) -> None:
    _schedule_exact_fields(item, {"item_type", "title", "summary", "source_ref", "event_detail", "task_detail"}, "item")
    if item_type == "event":
        if "task_detail" in item:
            raise SpineValidationError("invalid_request:item.task_detail", "event items cannot contain task_detail")
        detail = _schedule_object(item.get("event_detail"), "item.event_detail")
        _schedule_exact_fields(detail, {"all_day", "visibility", "attendance_policy_ref"}, "item.event_detail")
        if detail.get("all_day") is not False:
            raise SpineValidationError("invalid_request:item.event_detail.all_day", "schedule.create events require all_day=false")
    else:
        if "event_detail" in item:
            raise SpineValidationError("invalid_request:item.event_detail", "task items cannot contain event_detail")
        detail = _schedule_object(item.get("task_detail"), "item.task_detail")
        _schedule_exact_fields(detail, {"priority", "subject_roles"}, "item.task_detail")


def _schedule_resolve_initial_time(value: Mapping[str, Any]) -> dict[str, str]:
    _schedule_exact_fields(
        value,
        {"time_basis", "local_date", "local_time", "timezone", "timezone_database_version", "recurrence"},
        "scheduled_time",
    )
    if value.get("time_basis") != "local_instant":
        raise SpineValidationError("invalid_request:scheduled_time.time_basis", "scheduled_time.time_basis must be local_instant")
    local_date = _nested_required_str(value, "local_date", "scheduled_time.local_date")
    local_time = _nested_required_str(value, "local_time", "scheduled_time.local_time")
    timezone = _nested_required_str(value, "timezone", "scheduled_time.timezone")
    local_datetime = f"{local_date}T{local_time}"
    try:
        parse_scheduled_fact(local_datetime, time_basis="local_instant", field="scheduled_time.local_time")
    except SpineValidationError as exc:
        if len(local_date) != 10 or local_datetime[:10] != local_date:
            raise SpineValidationError("invalid_request:scheduled_time.local_date", "scheduled_time.local_date is invalid") from exc
        raise
    directive = _schedule_object(value.get("timezone_database_version"), "scheduled_time.timezone_database_version")
    kind = directive.get("kind")
    if kind == "explicit":
        _schedule_exact_fields(directive, {"kind", "version"}, "scheduled_time.timezone_database_version")
        version = _nested_required_str(directive, "version", "scheduled_time.timezone_database_version.version")
    elif kind == "system_current":
        _schedule_exact_fields(directive, {"kind"}, "scheduled_time.timezone_database_version")
        version = system_timezone_database_version()
    else:
        raise SpineValidationError(
            "invalid_request:scheduled_time.timezone_database_version.kind",
            "timezone_database_version.kind must be explicit or system_current",
        )
    try:
        resolution = resolve_local_instant(local_datetime, timezone=timezone, timezone_database_version=version)
    except SpineValidationError as exc:
        if exc.code == "invalid_request:timezone":
            raise SpineValidationError("invalid_request:scheduled_time.timezone", exc.message) from exc
        if exc.code == "environment_failure:timezone_database_version":
            raise SpineValidationError("environment_failure:scheduled_time.timezone_database_version", exc.message) from exc
        raise
    if resolution is None:
        raise SpineValidationError(
            "invalid_request:scheduled_time.local_time",
            "initial local time does not exist in the pinned timezone data",
        )
    if resolution.resolution_kind != "unambiguous":
        raise SpineValidationError(
            "invalid_request:scheduled_time.local_time",
            "initial local time is ambiguous in the pinned timezone data",
        )
    return {
        "local_date": local_date,
        "local_time": local_time,
        "timezone": timezone,
        "timezone_database_version": version,
        "utc_instant": resolution.utc_instant,
        "offset_seconds": resolution.offset_seconds,
    }


def _schedule_resolve_delivery(value: object, context: CommandContext) -> dict[str, Any]:
    delivery = _schedule_object(value, "delivery")
    _schedule_exact_fields(
        delivery,
        {"recipient_kind", "recipient_subject_id", "recipient_group_id", "channel", "target"},
        "delivery",
    )
    recipient_kind = _enum(delivery.get("recipient_kind"), "delivery.recipient_kind", {"subject", "subject_group"})
    channel = _nested_required_str(delivery, "channel", "delivery.channel")
    subject_id = _nested_optional_str(delivery, "recipient_subject_id", "delivery.recipient_subject_id")
    group_id = _nested_optional_str(delivery, "recipient_group_id", "delivery.recipient_group_id")
    if recipient_kind == "subject":
        if subject_id is None or group_id is not None:
            raise SpineValidationError(
                "invalid_request:delivery.recipient_subject_id",
                "subject recipient requires recipient_subject_id only",
            )
        if not _subject_exists(context.ledger, subject_id):
            raise SpineValidationError("referenced_row_not_found:delivery.recipient_subject_id", "recipient subject not found")
        recipient_id = subject_id
    else:
        if group_id is None or subject_id is not None:
            raise SpineValidationError(
                "invalid_request:delivery.recipient_group_id",
                "subject_group recipient requires recipient_group_id only",
            )
        if not _subject_group_exists(context.ledger, group_id):
            raise SpineValidationError("referenced_row_not_found:delivery.recipient_group_id", "recipient group not found")
        recipient_id = group_id

    target_request = _schedule_object(delivery.get("target"), "delivery.target")
    resolution_source = target_request.get("resolution")
    default_key: str | None = None
    if resolution_source == "explicit":
        _schedule_exact_fields(target_request, {"resolution", "delivery_target_id"}, "delivery.target")
        delivery_target_id = _nested_required_str(
            target_request,
            "delivery_target_id",
            "delivery.target.delivery_target_id",
        )
    elif resolution_source == "context_default":
        _schedule_exact_fields(target_request, {"resolution", "default_key"}, "delivery.target")
        default_key = _nested_required_str(target_request, "default_key", "delivery.target.default_key")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", default_key) is None:
            raise SpineValidationError("invalid_request:delivery.target.default_key", "default_key has an invalid format")
        default_value = context.delivery_target_defaults.get(default_key)
        if default_value is None:
            raise SpineValidationError("referenced_row_not_found:delivery.target.default_key", "delivery target default not found")
        if isinstance(default_value, str):
            delivery_target_id = default_value
        elif isinstance(default_value, Sequence) and not isinstance(default_value, (bytes, bytearray, str)):
            matches = [candidate for candidate in default_value if isinstance(candidate, str) and candidate]
            if len(matches) == 0:
                raise SpineValidationError("referenced_row_not_found:delivery.target.default_key", "delivery target default not found")
            if len(matches) != 1:
                raise SpineValidationError("semantic_conflict:delivery.target.default_key", "delivery target default is ambiguous")
            delivery_target_id = matches[0]
        else:
            raise SpineValidationError("semantic_conflict:delivery.target.default_key", "delivery target default is invalid")
    else:
        raise SpineValidationError(
            "invalid_request:delivery.target.resolution",
            "delivery.target.resolution must be explicit or context_default",
        )

    target = _delivery_target(context.ledger, delivery_target_id, required=False)
    missing_field = "delivery.target.delivery_target_id" if resolution_source == "explicit" else "delivery.target.default_key"
    if target is None:
        raise SpineValidationError(f"referenced_row_not_found:{missing_field}", "delivery target not found")
    if target["status"] != "active":
        raise SpineValidationError(f"semantic_conflict:{missing_field}", "delivery target is inactive")
    if target["channel"] != channel:
        raise SpineValidationError("semantic_conflict:delivery.channel", "delivery target channel does not match delivery.channel")
    expected_owner = target["owner_subject_id"] if recipient_kind == "subject" else target["owner_group_id"]
    if target["owner_kind"] != recipient_kind or expected_owner != recipient_id:
        raise SpineValidationError(
            f"semantic_conflict:delivery.{'recipient_subject_id' if recipient_kind == 'subject' else 'recipient_group_id'}",
            "delivery target owner does not match recipient",
        )
    snapshot: dict[str, object] = {
        "delivery_target_id": delivery_target_id,
        "resolution_source": resolution_source,
        "recipient_kind": recipient_kind,
        "channel": channel,
        "adapter_name": target["adapter_name"],
        "target_ref": target["target_ref"],
        "delivery_state": "not_attempted_by_command",
        ("recipient_subject_id" if recipient_kind == "subject" else "recipient_group_id"): recipient_id,
    }
    if default_key is not None:
        snapshot["default_key"] = default_key
    return {
        "recipient_kind": recipient_kind,
        "recipient_id": recipient_id,
        "recipient_subject_id": subject_id,
        "recipient_group_id": group_id,
        "channel": channel,
        "delivery_target_id": delivery_target_id,
        "snapshot": snapshot,
    }


def _schedule_normalize_materialization(value: object, *, scheduled: Mapping[str, str]) -> dict[str, object]:
    materialization = _schedule_object(value, "materialization")
    mode = materialization.get("mode")
    if mode == "none":
        _schedule_exact_fields(materialization, {"mode"}, "materialization")
        return {"mode": "none"}
    if mode != "bounded":
        raise SpineValidationError("invalid_request:materialization.mode", "materialization.mode must be none or bounded")
    _schedule_exact_fields(materialization, {"mode", "evaluated_at_utc", "range", "limit"}, "materialization")
    evaluated_at = _nested_required_str(materialization, "evaluated_at_utc", "materialization.evaluated_at_utc")
    try:
        require_utc_z("materialization.evaluated_at_utc", evaluated_at)
    except SpineValidationError as exc:
        raise SpineValidationError("invalid_request:materialization.evaluated_at_utc", exc.message) from exc
    raw_limit = materialization.get("limit")
    if not isinstance(raw_limit, str) or not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 1000:
        raise SpineValidationError("invalid_request:materialization.limit", "materialization.limit must be 1 through 1000")
    range_request = _schedule_object(materialization.get("range"), "materialization.range")
    range_kind = range_request.get("kind")
    if range_kind == "item_relative":
        _schedule_exact_fields(
            range_request,
            {"kind", "start_offset_seconds", "end_offset_seconds"},
            "materialization.range",
        )
        start_offset = _schedule_signed_decimal(
            range_request.get("start_offset_seconds"),
            "materialization.range.start_offset_seconds",
        )
        end_offset = _schedule_signed_decimal(
            range_request.get("end_offset_seconds"),
            "materialization.range.end_offset_seconds",
        )
        initial = _parse_utc_datetime(scheduled["utc_instant"])
        start = initial + timedelta(seconds=start_offset)
        end = initial + timedelta(seconds=end_offset)
    elif range_kind == "local_range":
        _schedule_exact_fields(
            range_request,
            {"kind", "range_start_local", "range_end_local"},
            "materialization.range",
        )
        start_local = _nested_required_str(
            range_request,
            "range_start_local",
            "materialization.range.range_start_local",
        )
        end_local = _nested_required_str(
            range_request,
            "range_end_local",
            "materialization.range.range_end_local",
        )
        start = _schedule_resolve_range_boundary(start_local, "range_start_local", scheduled)
        end = _schedule_resolve_range_boundary(end_local, "range_end_local", scheduled)
    else:
        raise SpineValidationError(
            "invalid_request:materialization.range.kind",
            "materialization.range.kind must be local_range or item_relative",
        )
    if end <= start:
        raise SpineValidationError(
            "invalid_request:materialization.range",
            "materialization range end must be later than its start",
        )
    if end - start > timedelta(days=366):
        raise SpineValidationError(
            "invalid_request:materialization.range",
            "materialization range must not exceed 366 elapsed days",
        )
    return {
        "mode": "bounded",
        "evaluated_at_utc": evaluated_at,
        "range_start_utc": _schedule_utc_text(start),
        "range_end_utc": _schedule_utc_text(end),
        "limit": raw_limit,
    }


def _schedule_signed_decimal(value: object, field: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0|-?[1-9][0-9]*", value) is None:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a canonical signed decimal string")
    return int(value)


def _schedule_resolve_range_boundary(value: str, name: str, scheduled: Mapping[str, str]) -> datetime:
    field = f"materialization.range.{name}"
    try:
        parse_scheduled_fact(value, time_basis="local_instant", field=field)
        resolution = resolve_local_instant(
            value,
            timezone=scheduled["timezone"],
            timezone_database_version=scheduled["timezone_database_version"],
        )
    except SpineValidationError as exc:
        if exc.code == "invalid_request:timezone":
            raise SpineValidationError("invalid_request:scheduled_time.timezone", exc.message) from exc
        if exc.code == "environment_failure:timezone_database_version":
            raise SpineValidationError("environment_failure:scheduled_time.timezone_database_version", exc.message) from exc
        raise
    if resolution is None:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} does not exist in the pinned timezone data")
    if resolution.resolution_kind != "unambiguous":
        raise SpineValidationError(f"invalid_request:{field}", f"{field} is ambiguous in the pinned timezone data")
    return _parse_utc_datetime(resolution.utc_instant)


def _schedule_normalize_policies(
    value: object,
    *,
    item_id: str,
    item_type: str,
    recurring: bool,
    command_id: str,
    created_at_utc: str,
    delivery: Mapping[str, Any],
) -> tuple[tuple[str, NormalizedNotificationPolicy], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError("invalid_request:reminders", "reminders must be an array")
    if not 1 <= len(value) <= 32:
        raise SpineValidationError("invalid_request:reminders", "reminders must contain 1 through 32 policies")
    keyed: list[tuple[str, int, Mapping[str, Any]]] = []
    seen_keys: set[str] = set()
    for index, raw in enumerate(value):
        reminder = _schedule_object(raw, f"reminders[{index}]")
        _schedule_exact_fields(reminder, {"policy_key", "schedule", "late_handling"}, f"reminders[{index}]")
        policy_key = _nested_required_str(reminder, "policy_key", f"reminders[{index}].policy_key")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", policy_key) is None:
            raise SpineValidationError(
                f"invalid_request:reminders[{index}].policy_key",
                "policy_key has an invalid format",
            )
        if policy_key in seen_keys:
            raise SpineValidationError(
                f"semantic_conflict:reminders[{index}].policy_key",
                "policy_key must be unique",
            )
        seen_keys.add(policy_key)
        keyed.append((policy_key, index, reminder))
    result: list[tuple[str, NormalizedNotificationPolicy]] = []
    seen_schedules: set[str] = set()
    for policy_key, index, reminder in sorted(keyed, key=lambda entry: entry[0]):
        normalized = normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {
                    "anchor_role": "event_start" if item_type == "event" else "task_due",
                    "application_scope": "each_occurrence" if recurring else "item",
                },
                "schedule": reminder.get("schedule"),
                "late_handling": reminder.get("late_handling"),
            },
            item_id=item_id,
            item_version="1",
            command_id=command_id,
            created_at_utc=created_at_utc,
            recipient_kind=str(delivery["recipient_kind"]),
            recipient_id=str(delivery["recipient_id"]),
            channel=str(delivery["channel"]),
            delivery_target_id=str(delivery["delivery_target_id"]),
        )
        schedule_hash = str(normalized.value["normalized_notification_schedule_hash"])
        if schedule_hash in seen_schedules:
            raise SpineValidationError(
                f"semantic_conflict:reminders[{index}]",
                "reminder duplicates another normalized policy",
            )
        seen_schedules.add(schedule_hash)
        result.append((policy_key, normalized))
    return tuple(result)


def _schedule_recurrence_source_range(
    recurrence: Mapping[str, object],
    *,
    policies: list[dict[str, object]],
    eligibility_start: datetime,
    eligibility_end: datetime,
) -> tuple[str, str]:
    minimum_offset = 0
    maximum_offset = 0
    for policy in policies:
        target = _schedule_object(policy.get("target"), "notification policy target")
        if target.get("application_scope") == "item":
            continue
        offsets = _schedule_policy_offsets(policy)
        minimum_offset = min(minimum_offset, *offsets)
        maximum_offset = max(maximum_offset, *offsets)
    conservative = timedelta(days=2)
    target_start = eligibility_start - timedelta(seconds=maximum_offset) - conservative
    target_end = eligibility_end - timedelta(seconds=minimum_offset) + conservative
    basis = str(recurrence["time_basis"])
    if basis == "instant_utc":
        return _schedule_utc_text(target_start), _schedule_utc_text(target_end)
    zone = ZoneInfo(str(recurrence["timezone"]))
    local_start = target_start.astimezone(zone)
    local_end = target_end.astimezone(zone)
    if basis == "local_date":
        return local_start.date().isoformat(), (local_end.date() + timedelta(days=1)).isoformat()
    return (
        local_start.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S"),
        (local_end.replace(tzinfo=None) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _schedule_policy_offsets(policy: Mapping[str, object]) -> list[int]:
    schedule = _schedule_object(policy.get("schedule"), "notification policy schedule")
    kind = schedule.get("kind")
    if kind == "once":
        boundaries = [_schedule_object(schedule.get("at"), "notification schedule boundary")]
    elif kind == "offsets":
        raw_boundaries = schedule.get("at")
        if not isinstance(raw_boundaries, Sequence) or isinstance(raw_boundaries, (str, bytes, bytearray)):
            raise SpineValidationError("invalid_request:reminders", "notification offsets must be an array")
        boundaries = [_schedule_object(entry, "notification schedule boundary") for entry in raw_boundaries]
    else:
        boundaries = [
            _schedule_object(schedule.get("start"), "notification schedule start"),
            _schedule_object(schedule.get("stop"), "notification schedule stop"),
        ]
    values = [0]
    for boundary in boundaries:
        if boundary.get("kind") != "target_offset":
            continue
        if boundary.get("offset_basis") == "elapsed":
            values.append(int(str(boundary["offset_seconds"])))
        else:
            values.append(int(str(boundary["offset_days"])) * 86_400)
    return values


def _parse_utc_datetime(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SpineValidationError("invalid_request:timestamp", "timestamp must be canonical UTC with trailing Z") from exc


def _schedule_utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _schedule_fail_if_requested(context: CommandContext, phase: str) -> None:
    if context.transport_metadata.get("schedule_create_fail_after") == phase:
        raise SpineValidationError(
            "runtime_failure:schedule_create_injected_failure",
            f"injected schedule.create failure after {phase}",
        )


def _schedule_create_response(receipt: Mapping[str, Any], *, response_effect: str) -> dict[str, Any]:
    facts = receipt.get("result_identity_facts")
    if not isinstance(facts, Mapping):
        raise SpineValidationError("runtime_failure:schedule_create_receipt", "schedule.create receipt result is invalid")
    return {
        "ok": True,
        "command": "schedule.create",
        "response_contract": "spine.schedule-create-response.v1",
        "effect": response_effect,
        **dict(facts),
        "receipt": {
            "receipt_contract": "spine.schedule-create-receipt.v1",
            "command_receipt_id": receipt["command_receipt_id"],
            "effect": "schedule_created",
            "semantic_facts_hash": receipt["semantic_facts_hash"],
            "created_at_utc": receipt["created_at_utc"],
        },
    }


def _schedule_create_evidence_matches(connection: sqlite3.Connection, receipt: Mapping[str, Any]) -> bool:
    facts = receipt.get("result_identity_facts")
    if not isinstance(facts, Mapping):
        return False
    try:
        item_id = str(facts["item_id"])
        command_receipt_id = str(facts["command_receipt_id"])
        audit_id = str(facts["audit_id"])
        policies = facts["policies"]
        materialization = facts["materialization"]
    except (KeyError, TypeError):
        return False
    if not isinstance(policies, Sequence) or isinstance(policies, (str, bytes, bytearray)):
        return False
    if not isinstance(materialization, Mapping):
        return False
    item_row = connection.execute(
        "SELECT item_type FROM coordination_items WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    version_row = connection.execute(
        "SELECT 1 FROM coordination_item_versions WHERE item_id = ? AND version = 1",
        (item_id,),
    ).fetchone()
    audit_row = connection.execute(
        "SELECT action, reason_code FROM audit_log WHERE audit_id = ? AND item_id = ?",
        (audit_id, item_id),
    ).fetchone()
    receipt_row = connection.execute(
        "SELECT command_id, command, effect FROM command_receipts WHERE command_receipt_id = ?",
        (command_receipt_id,),
    ).fetchone()
    if (
        item_row is None
        or version_row is None
        or str(item_row["item_type"]) != str(facts.get("item_type"))
        or audit_row is None
        or audit_row["action"] != "schedule_created"
        or audit_row["reason_code"] != "schedule_created"
        or receipt_row is None
        or receipt_row["command"] != "schedule.create"
        or receipt_row["effect"] != "schedule_created"
        or receipt_row["command_id"] != receipt.get("command_id")
    ):
        return False
    for policy in policies:
        if not isinstance(policy, Mapping):
            return False
        row = connection.execute(
            """
            SELECT notification_intent_id, schedule_id, normalized_notification_schedule_hash, status
            FROM notification_policies
            WHERE policy_id = ? AND item_id = ? AND version = 1
            """,
            (policy.get("notification_policy_id"), item_id),
        ).fetchone()
        if row is None or any(
            str(row[column]) != str(policy[expected])
            for column, expected in (
                ("notification_intent_id", "notification_intent_id"),
                ("schedule_id", "notification_schedule_id"),
                ("normalized_notification_schedule_hash", "normalized_notification_schedule_hash"),
                ("status", "status"),
            )
        ):
            return False
    work_ids = materialization.get("work_instance_ids")
    if not isinstance(work_ids, Sequence) or isinstance(work_ids, (str, bytes, bytearray)):
        return False
    for work_id in work_ids:
        work_row = connection.execute(
            "SELECT item_id, item_version FROM work_instances WHERE work_instance_id = ?",
            (work_id,),
        ).fetchone()
        if work_row is None or work_row["item_id"] != item_id or int(work_row["item_version"]) != 1:
            return False
        attempt = connection.execute(
            "SELECT 1 FROM side_effect_attempts WHERE work_instance_id = ? LIMIT 1",
            (work_id,),
        ).fetchone()
        if attempt is not None:
            return False
    return True


def _compatible_replay(command: str, command_id: str, semantic_facts: Mapping[str, Any], context: CommandContext) -> dict[str, Any] | None:
    existing = get_command_receipt(context.ledger, command_id)
    if existing is None:
        return None
    if existing["command"] != command:
        raise SpineValidationError("command_id_reuse", "command_id was already used by a different command")
    existing_facts = existing["semantic_facts"]
    if any(existing_facts.get(key) != value for key, value in semantic_facts.items()):
        raise SpineValidationError("incompatible_replay", "command_id replay facts do not match")
    return existing


def _store_write_receipt(context: CommandContext, **kwargs: Any) -> dict[str, Any]:
    receipt = _make_receipt(**kwargs)
    with context.ledger:
        insert_command_receipt(context.ledger, receipt)
    return receipt


def _make_receipt(**kwargs: Any) -> dict[str, Any]:
    return command_receipt(command_receipt_id=_receipt_id(kwargs["command"], kwargs["command_id"]), **kwargs)


def _receipt_id(command: str, command_id: str) -> str:
    return _derived_id(command, command_id, "command_receipt", "/")


def _derived_id(command: str, command_id: str, row_role: str, request_path: str) -> str:
    prefixes = {
        "item": "item",
        "audit": "audit",
        "command_receipt": "command_receipt",
        "relation": "relation",
        "start_anchor": "anchor",
        "end_anchor": "anchor",
        "due_anchor": "anchor",
        "defer_until_anchor": "anchor",
        "item_subject_role": "item_subject_role",
        "notification_policy": "notification_policy",
        "work_instance": "work_instance",
    }
    return command_derived_id(
        prefix=prefixes[row_role], command=command, command_id=command_id, row_role=row_role, request_path=request_path
    )


def _semantic_request(
    command: str, command_id: str, actor: str, action_timestamp: str, request: Mapping[str, Any], allowed: set[str]
) -> dict[str, Any]:
    facts = {
        "command": command,
        "command_id": command_id,
        "actor_subject_id": actor,
        "action_timestamp_utc": action_timestamp,
    }
    for key in sorted(allowed):
        if key in {"command_id", "actor_subject_id"}:
            continue
        if key in request:
            facts[key] = _canonical_value(request[key])
    return facts


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    return str(value)


def _required_str(request: Mapping[str, Any], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or value == "":
        raise SpineValidationError(f"missing_{field}", f"{field} must be a non-empty string")
    return value


def _optional_str(request: Mapping[str, Any], field: str) -> str | None:
    value = request.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpineValidationError(f"invalid_{field}", f"{field} must be a string")
    return value


def _required_bool(request: Mapping[str, Any], field: str) -> bool:
    value = request.get(field)
    if not isinstance(value, bool):
        raise SpineValidationError(f"invalid_{field}", f"{field} must be a boolean")
    return value


def _timestamp(request: Mapping[str, Any], field: str) -> str:
    value = _required_str(request, field)
    try:
        return require_utc_z(field, value)
    except SpineValidationError as exc:
        raise SpineValidationError(f"invalid_timestamp_{field}", exc.message) from exc


def _version(request: Mapping[str, Any], field: str) -> int:
    value = request.get(field)
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise SpineValidationError(f"invalid_{field}", f"{field} must be a positive integer")
    return value


def _limit(value: Any) -> int:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or value < 0 or value > 100:
        raise SpineValidationError("invalid_limit", "limit must be between 0 and 100")
    return value


def _occurrence_limit(value: Any) -> int:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 1000:
        raise SpineValidationError(
            "invalid_limit",
            "limit must be between 1 and 1000",
        )
    return value


def _schedule_show_limit(value: Any, field: str) -> int:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 1000:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be between 0 and 1000")
    return value


def _limit_sequence(values: Any, limit: int) -> tuple[list[Any], bool]:
    sequence = list(values if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)) else ())
    return sequence[:limit], len(sequence) > limit


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SpineValidationError(f"unsupported_{field}", f"{field} must be one of {sorted(allowed)}")
    return value


def _patch(value: Any, *, allow_subject_roles: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError("invalid_patch", "patch must be an object")
    patch: dict[str, Any] = {}
    for key, val in value.items():
        if key == "subject_roles" and allow_subject_roles:
            patch[key] = val
            continue
        if key not in {"title", "summary", "source_ref"}:
            raise SpineValidationError(f"unsupported_patch.{key}", f"unsupported patch field: {key}")
        if key == "title":
            if not isinstance(val, str) or val == "":
                raise SpineValidationError("invalid_patch.title", "patch.title must be a non-empty string")
            patch[key] = val
        elif val is not None and not isinstance(val, str):
            raise SpineValidationError(f"invalid_patch.{key}", f"patch.{key} must be a string or null")
        else:
            patch[key] = val
    return patch


def _changed_common(current: Mapping[str, Any], patch: Mapping[str, Any]) -> bool:
    return any(current.get(key) != patch[key] for key in ("title", "summary", "source_ref") if key in patch)


def _anchor_input(
    value: Any,
    field: str,
    anchor_id: str,
    *,
    allow_recurrence: bool = False,
) -> TemporalAnchorInput:
    if not isinstance(value, Mapping):
        raise SpineValidationError(f"invalid_{field}", f"{field} must be an object")
    allowed = {
        "anchor_kind",
        "local_date",
        "local_time",
        "timezone",
        "timezone_database_version",
        "utc_instant",
        "window_start_utc",
        "window_end_utc",
        "recurrence_set",
        "source",
    }
    for key in value:
        if key not in allowed:
            raise SpineValidationError(f"unsupported_field:{field}.{key}", f"unsupported anchor field: {key}")
    recurrence_set = value.get("recurrence_set")
    effective = dict(value)
    if (
        effective.get("timezone_database_version") is None
        and isinstance(recurrence_set, Mapping)
        and recurrence_set.get("timezone_database_version") is not None
    ):
        effective["timezone_database_version"] = recurrence_set["timezone_database_version"]
    kind = _enum(
        value.get("anchor_kind"), f"{field}.anchor_kind", {"instant_utc", "local_instant", "local_date", "utc_window", "local_window"}
    )
    _validate_anchor_shape(effective, field, kind)
    if recurrence_set is not None:
        if not allow_recurrence:
            raise SpineValidationError(
                f"unsupported_field:{field}.recurrence_set",
                f"{field}.recurrence_set is not supported on this anchor",
            )
        if kind not in {"local_date", "local_instant", "instant_utc"}:
            raise SpineValidationError(
                f"unsupported_field:{field}.recurrence_set",
                f"{field}.recurrence_set requires a scheduled-value anchor",
            )
        if not isinstance(recurrence_set, Mapping):
            raise SpineValidationError(f"invalid_{field}.recurrence_set", f"{field}.recurrence_set must be an object")
    return TemporalAnchorInput(
        anchor_id=anchor_id,
        anchor_kind=kind,
        local_date=_map_optional_str(effective, "local_date"),
        local_time=_map_optional_str(effective, "local_time"),
        timezone=_map_optional_str(effective, "timezone"),
        timezone_database_version=_map_optional_str(effective, "timezone_database_version"),
        utc_instant=_anchor_optional_utc(effective, "utc_instant", field),
        window_start_utc=_anchor_optional_utc(effective, "window_start_utc", field),
        window_end_utc=_anchor_optional_utc(effective, "window_end_utc", field),
        source=_map_optional_str(effective, "source"),
    )


def _normalize_authored_recurrence(
    raw_anchor: Any,
    *,
    field: str,
    anchor: TemporalAnchorInput | None,
    item_id: str,
    command_id: str,
    created_item_version: str = "1",
    source_item_version: str = "1",
) -> NormalizedRecurrenceSet | None:
    if not isinstance(raw_anchor, Mapping) or raw_anchor.get("recurrence_set") is None:
        return None
    if anchor is None or anchor.anchor_id is None:
        raise SpineValidationError(f"invalid_{field}.recurrence_set", f"{field} has no seed anchor")
    authoring = raw_anchor["recurrence_set"]
    if not isinstance(authoring, Mapping):
        raise SpineValidationError(f"invalid_{field}.recurrence_set", f"{field}.recurrence_set must be an object")
    time_basis = authoring.get("time_basis")
    anchor_kind = str(anchor.anchor_kind)
    if time_basis != anchor_kind:
        raise SpineValidationError("invalid_request:time_basis", f"{field}.recurrence_set.time_basis must match anchor_kind")
    if anchor_kind in {"local_date", "local_instant"} and authoring.get("timezone") != anchor.timezone:
        raise SpineValidationError("invalid_request:timezone", f"{field}.recurrence_set.timezone must match the anchor")
    if anchor_kind in {"local_date", "local_instant"} and authoring.get("timezone_database_version") != anchor.timezone_database_version:
        raise SpineValidationError(
            "invalid_request:timezone_database_version",
            f"{field}.recurrence_set.timezone_database_version must match the anchor",
        )
    seed_scheduled_fact = _anchor_scheduled_fact(anchor, field=field)
    return normalize_initial_recurrence_set(
        dict(authoring),
        source_item_id=item_id,
        seed_anchor_id=anchor.anchor_id,
        seed_scheduled_fact=seed_scheduled_fact,
        created_item_version=created_item_version,
        source_item_version=source_item_version,
        command_id=command_id,
    )


def _anchor_scheduled_fact(anchor: TemporalAnchorInput, *, field: str) -> str:
    kind = str(anchor.anchor_kind)
    if kind == "local_date" and anchor.local_date is not None:
        return anchor.local_date
    if kind == "local_instant" and anchor.local_date is not None and anchor.local_time is not None:
        return f"{anchor.local_date}T{anchor.local_time}"
    if kind == "instant_utc" and anchor.utc_instant is not None:
        return anchor.utc_instant
    raise SpineValidationError(f"invalid_{field}", f"{field} does not contain a canonical schedule seed")


def _recurrence_insert_callback(
    recurrence: NormalizedRecurrenceSet | None,
    *,
    command_id: str,
    created_at_utc: str,
) -> Callable[[sqlite3.Connection], None] | None:
    if recurrence is None:
        return None

    def insert(connection: sqlite3.Connection) -> None:
        insert_initial_recurrence_set(
            connection,
            normalized=recurrence,
            command_id=command_id,
            created_at_utc=created_at_utc,
        )

    return insert


def _recurrence_identity_facts(recurrence: NormalizedRecurrenceSet | None) -> dict[str, object]:
    if recurrence is None:
        return {}
    return {
        "recurrence_set_id": recurrence.value["recurrence_set_id"],
        "recurrence_revision_id": recurrence.value["recurrence_revision_id"],
        "normalized_recurrence_set_hash": recurrence.value["normalized_recurrence_set_hash"],
        "recurrence_set_identity_preimage": recurrence.recurrence_set_id_preimage,
    }


def _validate_anchor_shape(value: Mapping[str, Any], field: str, kind: str) -> None:
    required_by_kind = {
        "instant_utc": {"utc_instant"},
        "local_instant": {"local_date", "local_time", "timezone", "timezone_database_version"},
        "local_date": {"local_date", "timezone", "timezone_database_version"},
        "utc_window": {"window_start_utc", "window_end_utc"},
        "local_window": {"local_date", "timezone", "timezone_database_version"},
    }
    forbidden_by_kind = {
        "instant_utc": {"local_date", "local_time", "timezone", "timezone_database_version", "window_start_utc", "window_end_utc"},
        "local_instant": {"utc_instant", "window_start_utc", "window_end_utc"},
        "local_date": {"local_time", "utc_instant", "window_start_utc", "window_end_utc"},
        "utc_window": {"local_date", "local_time", "timezone", "timezone_database_version", "utc_instant"},
        "local_window": {"local_time", "utc_instant", "window_start_utc", "window_end_utc"},
    }
    for forbidden in sorted(forbidden_by_kind[kind]):
        if value.get(forbidden) is not None:
            raise SpineValidationError(f"unsupported_field:{field}.{forbidden}", f"{field}.{forbidden} is not valid for {kind}")
    for required in sorted(required_by_kind[kind]):
        if value.get(required) is None:
            raise SpineValidationError(f"missing_{field}.{required}", f"{field}.{required} is required for {kind}")
    if kind == "utc_window":
        start = _anchor_optional_utc(value, "window_start_utc", field)
        end = _anchor_optional_utc(value, "window_end_utc", field)
        if start is not None and end is not None and start > end:
            raise SpineValidationError(
                f"invalid_{field}.window_end_utc", f"{field}.window_end_utc must be after or equal to window_start_utc"
            )


def _anchor_optional_utc(value: Mapping[str, Any], key: str, field: str) -> str | None:
    item = _map_optional_str(value, key)
    if item is None:
        return None
    try:
        return require_utc_z(f"{field}.{key}", item)
    except SpineValidationError as exc:
        raise SpineValidationError(f"invalid_timestamp_{field}.{key}", exc.message) from exc


def _map_optional_str(value: Mapping[str, Any], field: str) -> str | None:
    item = value.get(field)
    if item is None:
        return None
    if not isinstance(item, str):
        raise SpineValidationError(f"invalid_{field}", f"{field} must be a string")
    return item


def _anchor_output(anchor: TemporalAnchorInput) -> dict[str, Any]:
    row = {
        "anchor_id": anchor.anchor_id,
        "anchor_kind": anchor.anchor_kind,
        "created_at_utc": anchor.created_at_utc,
        "local_date": anchor.local_date,
        "local_time": anchor.local_time,
        "timezone": anchor.timezone,
        "timezone_database_version": anchor.timezone_database_version,
        "utc_instant": anchor.utc_instant,
        "window_start_utc": anchor.window_start_utc,
        "window_end_utc": anchor.window_end_utc,
        "source": anchor.source,
    }
    return {key: value for key, value in row.items() if value is not None}


def _anchor_semantic_facts(anchor: Any) -> dict[str, Any] | None:
    if not isinstance(anchor, Mapping):
        return None
    return {
        key: anchor[key]
        for key in (
            "anchor_kind",
            "local_date",
            "local_time",
            "timezone",
            "timezone_database_version",
            "utc_instant",
            "window_start_utc",
            "window_end_utc",
            "source",
        )
        if anchor.get(key) is not None
    }


def _decorate_occurrence(
    item: Mapping[str, Any],
    recurrence: Mapping[str, Any],
    occurrence: dict[str, Any],
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    detail = item["detail"]
    time_basis = str(recurrence["time_basis"])
    expressed = str(occurrence["expressed_scheduled_fact"])
    lifecycle = str(occurrence["lifecycle"])
    scheduled_anchor = _value_anchor_from_scheduled_fact(
        expressed,
        time_basis=time_basis,
        timezone=recurrence.get("timezone"),
    )
    event_patch = occurrence.pop("event_detail_patch", None)
    task_patch = occurrence.pop("task_detail_patch", None)
    occurrence.pop("common_detail_patch", None)
    if not include_internal:
        occurrence.pop("target_occurrence_selector", None)
    if item["item_type"] == "event":
        event_status = "cancelled" if detail["event_status"] == "cancelled" or lifecycle == "cancelled" else "scheduled"
        all_day = bool(detail["all_day"])
        if isinstance(event_patch, Mapping) and "all_day" in event_patch:
            all_day = bool(event_patch["all_day"])
        result_detail: dict[str, Any] = {
            "event_status": event_status,
            "all_day": all_day,
            "start_anchor": scheduled_anchor,
        }
        if isinstance(event_patch, Mapping) and "end_scheduled_fact" in event_patch:
            if event_patch["end_scheduled_fact"] is not None:
                result_detail["end_anchor"] = _value_anchor_from_scheduled_fact(
                    str(event_patch["end_scheduled_fact"]),
                    time_basis=time_basis,
                    timezone=recurrence.get("timezone"),
                )
        elif detail.get("end_anchor") is not None:
            result_detail["end_anchor"] = _shift_value_anchor(
                detail["end_anchor"],
                seed_anchor=detail["start_anchor"],
                new_seed_fact=expressed,
                time_basis=time_basis,
            )
        occurrence["occurrence_event_detail"] = result_detail
        actionable = item["status"] == "active" and detail["event_status"] == "scheduled" and lifecycle != "cancelled"
    else:
        if detail["task_status"] in {"done", "cancelled"}:
            task_status = detail["task_status"]
        elif lifecycle == "completed":
            task_status = "done"
        elif lifecycle == "cancelled":
            task_status = "cancelled"
        else:
            task_status = "open"
        result_detail = {"task_status": task_status, "due_anchor": scheduled_anchor}
        if isinstance(task_patch, Mapping) and "priority" in task_patch:
            result_detail["priority"] = task_patch["priority"]
        elif "priority" in detail:
            result_detail["priority"] = detail["priority"]
        if isinstance(task_patch, Mapping) and "defer_until_scheduled_fact" in task_patch:
            if task_patch["defer_until_scheduled_fact"] is not None:
                result_detail["defer_until_anchor"] = _value_anchor_from_scheduled_fact(
                    str(task_patch["defer_until_scheduled_fact"]),
                    time_basis=time_basis,
                    timezone=recurrence.get("timezone"),
                )
        elif detail.get("defer_until_anchor") is not None:
            result_detail["defer_until_anchor"] = _shift_value_anchor(
                detail["defer_until_anchor"],
                seed_anchor=detail["due_anchor"],
                new_seed_fact=expressed,
                time_basis=time_basis,
            )
        occurrence["occurrence_task_detail"] = result_detail
        actionable = item["status"] == "active" and detail["task_status"] == "open" and lifecycle == "active"
    occurrence["actionable"] = actionable
    return occurrence


def _value_anchor_from_scheduled_fact(value: str, *, time_basis: str, timezone: object) -> dict[str, Any]:
    parse_scheduled_fact(value, time_basis=time_basis, field="scheduled_fact")
    if time_basis == "local_date":
        return {"anchor_kind": "local_date", "local_date": value, "timezone": timezone}
    if time_basis == "local_instant":
        local_date, local_time = value.split("T", 1)
        return {
            "anchor_kind": "local_instant",
            "local_date": local_date,
            "local_time": local_time,
            "timezone": timezone,
        }
    return {"anchor_kind": "instant_utc", "utc_instant": value}


def _shift_value_anchor(
    anchor: Mapping[str, Any],
    *,
    seed_anchor: Mapping[str, Any],
    new_seed_fact: str,
    time_basis: str,
) -> dict[str, Any]:
    anchor_fact = _scheduled_fact_from_anchor(anchor, time_basis=time_basis)
    seed_fact = _scheduled_fact_from_anchor(seed_anchor, time_basis=time_basis)
    parsed_anchor = parse_scheduled_fact(anchor_fact, time_basis=time_basis, field="anchor")
    parsed_seed = parse_scheduled_fact(seed_fact, time_basis=time_basis, field="seed_anchor")
    parsed_new = parse_scheduled_fact(new_seed_fact, time_basis=time_basis, field="new_seed")
    shifted = parsed_new + (parsed_anchor - parsed_seed)
    shifted_fact = _format_scheduled_fact(shifted, time_basis=time_basis)
    return _value_anchor_from_scheduled_fact(
        shifted_fact,
        time_basis=time_basis,
        timezone=anchor.get("timezone"),
    )


def _scheduled_fact_from_anchor(anchor: Mapping[str, Any], *, time_basis: str) -> str:
    if time_basis == "local_date":
        return str(anchor["local_date"])
    if time_basis == "local_instant":
        return f"{anchor['local_date']}T{anchor['local_time']}"
    return str(anchor["utc_instant"])


def _format_scheduled_fact(value: date | datetime, *, time_basis: str) -> str:
    if time_basis == "local_date":
        assert isinstance(value, date) and not isinstance(value, datetime)
        return value.isoformat()
    assert isinstance(value, datetime)
    if time_basis == "local_instant":
        return value.isoformat(timespec="seconds")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _recurrence_cursor_facts(
    *,
    item: Mapping[str, Any],
    recurrence: Mapping[str, Any],
    range_basis: str,
    range_start: str,
    range_end: str,
    limit: str,
    include_diagnostics: bool,
) -> dict[str, Any]:
    identity_preimage: dict[str, Any] = {
        "derivation_version": "spine.recurrence-set-id.v1",
        "contract_version": recurrence["contract_version"],
        "normalization_version": recurrence["normalization_version"],
        "canonical_json_version": recurrence["canonical_json_version"],
        "source_item_id": recurrence["source_item_id"],
        "seed_anchor_id": recurrence["seed_anchor_id"],
        "created_item_version": recurrence["created_item_version"],
        "time_basis": recurrence["time_basis"],
    }
    if recurrence.get("timezone") is not None:
        identity_preimage["timezone"] = recurrence["timezone"]
        identity_preimage["timezone_database_version"] = recurrence["timezone_database_version"]
    facts: dict[str, Any] = {
        "cursor_version": "spine.recurrence-cursor.v2",
        "contract_version": recurrence["contract_version"],
        "normalization_version": recurrence["normalization_version"],
        "canonical_json_version": recurrence["canonical_json_version"],
        "item_id": item["item_id"],
        "source_item_version": recurrence["source_item_version"],
        "shell_status": item["status"],
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
        "range_basis": range_basis,
        "range_start": range_start,
        "range_end": range_end,
        "limit": limit,
        "include_diagnostics": include_diagnostics,
        "recurrence_set_identity_preimage": identity_preimage,
    }
    if item["status"] == "archived":
        facts["archived_at_utc"] = item["archived_at_utc"]
    return facts


def _notification_limit(value: Any) -> int:
    if isinstance(value, str) and value.isdigit() and not value.startswith("0"):
        parsed = int(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        parsed = value
    else:
        raise SpineValidationError("invalid_limit", "limit must be a positive decimal string")
    if parsed < 1 or parsed > 1000:
        raise SpineValidationError("invalid_limit", "limit must be between 1 and 1000")
    return parsed


def _notification_cursor_facts(
    *,
    item: Mapping[str, Any],
    policies: Sequence[Mapping[str, object]],
    recurrence: Mapping[str, object] | None,
    evaluated_at_utc: str,
    notification_intent_id: str | None,
    range_start_utc: str,
    range_end_utc: str,
    limit: str,
    include_diagnostics: bool,
) -> dict[str, object]:
    facts: dict[str, object] = {
        "cursor_version": "spine.notification-opportunities-cursor.v1",
        "command": "notification.opportunities",
        "contract_version": "spine.notification-schedule.contract.v1",
        "normalization_version": "spine.notification-schedule.normalization.v1",
        "canonical_json_version": "spine.canonical-json.v1",
        "item_id": item["item_id"],
        "current_version": str(item["current_version"]),
        "evaluated_at_utc": evaluated_at_utc,
        "range_start_utc": range_start_utc,
        "range_end_utc": range_end_utc,
        "limit": limit,
        "include_diagnostics": include_diagnostics,
        "selected_policies": [
            {
                "notification_policy_id": policy["notification_policy_id"],
                "normalized_notification_schedule_hash": policy["normalized_notification_schedule_hash"],
            }
            for policy in policies
        ],
    }
    if notification_intent_id is not None:
        facts["notification_intent_id"] = notification_intent_id
    if recurrence is not None:
        facts.update(
            {
                "recurrence_revision_id": recurrence["recurrence_revision_id"],
                "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
            }
        )
    return facts


def _encode_notification_cursor(value: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value)
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii") + "." + hash_canonical_json(value)


def _decode_notification_cursor(value: Any, *, expected: Mapping[str, Any]) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.count(".") != 1:
        raise SpineValidationError("stale_cursor:cursor", "cursor is malformed")
    encoded, digest = value.split(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        decoded = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SpineValidationError("stale_cursor:cursor", "cursor is malformed") from exc
    last = decoded.pop("last_ordering_tuple", None) if isinstance(decoded, dict) else None
    if (
        not isinstance(decoded, dict)
        or canonical_json_bytes({**decoded, "last_ordering_tuple": last}) != payload
        or hash_canonical_json({**decoded, "last_ordering_tuple": last}) != digest
        or decoded != dict(expected)
        or not isinstance(last, list)
        or len(last) != 2
        or not all(isinstance(entry, str) for entry in last)
    ):
        raise SpineValidationError("stale_cursor:cursor", "cursor facts are stale")
    return last


def _notification_policy_actionability(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    policy: Mapping[str, object],
) -> tuple[bool, str | None]:
    if policy["status"] != "active":
        return False, "notification_policy_disabled"
    if item["status"] != "active":
        return False, "item_inactive"
    detail = item["detail"]
    if item["item_type"] == "event" and detail["event_status"] != "scheduled":
        return False, "event_not_scheduled"
    if item["item_type"] == "task" and detail["task_status"] != "open":
        return False, "task_not_open"
    target = _delivery_target(connection, str(policy["delivery_target_id"]), required=False)
    recipient_id = policy.get("recipient_subject_id") or policy.get("recipient_group_id")
    owner_id = None if target is None else target.get("owner_subject_id") or target.get("owner_group_id")
    if (
        target is None
        or target["status"] != "active"
        or target["channel"] != policy["channel"]
        or target["owner_kind"] != policy["recipient_kind"]
        or owner_id != recipient_id
    ):
        return False, "delivery_target_unavailable"
    return True, None


def _notification_targets(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    policy: Mapping[str, object],
    recurrence: Mapping[str, object] | None,
    range_start_utc: str,
    range_end_utc: str,
) -> list[dict[str, object]]:
    target = policy["target"]
    if not isinstance(target, Mapping):
        raise SpineValidationError("invalid_notification_storage", "policy target is invalid")
    scope = target["application_scope"]
    if scope == "item":
        anchor = item["detail"].get("start_anchor" if item["item_type"] == "event" else "due_anchor")
        if not isinstance(anchor, Mapping):
            raise SpineValidationError("semantic_conflict", "notification target anchor is unavailable")
        return [_notification_target_from_anchor(anchor)]
    if recurrence is None:
        raise SpineValidationError("semantic_conflict", "recurrence-bound notification has no recurrence set")
    params: list[object] = [
        item["item_id"],
        recurrence["recurrence_revision_id"],
    ]
    selected_clause = ""
    if scope == "selected_occurrence":
        selected_clause = "AND op.occurrence_key = ?"
        params.append(target["target_occurrence_key"])
    rows = connection.execute(
        f"""
        SELECT op.*
        FROM occurrence_provenance AS op
        WHERE op.item_id = ?
          AND op.recurrence_revision_id = ?
          AND op.consumer = 'notification_schedule'
          AND op.management_status = 'active'
          {selected_clause}
        ORDER BY op.original_scheduled_fact, op.occurrence_key
        """,
        tuple(params),
    ).fetchall()
    values: list[dict[str, object]] = []
    for row in rows:
        selector = load_target_occurrence_selector(connection, selector_ref=row["target_occurrence_selector_ref"])
        value: dict[str, object] = {
            "target_scheduled_fact": row["expressed_scheduled_fact"],
            "target_occurrence_selector": selector,
            "occurrence_id": row["occurrence_id"],
            "occurrence_key": row["occurrence_key"],
            "occurrence_provenance_id": row["occurrence_provenance_id"],
            "recurrence_set_id": row["recurrence_set_id"],
            "recurrence_revision_id": row["recurrence_revision_id"],
            "lifecycle": "scheduled" if row["lifecycle"] == "active" else row["lifecycle"],
            "actionable": bool(row["actionable"]),
        }
        if row["timezone_utc_instant"] is not None:
            value["target_utc_instant"] = row["timezone_utc_instant"]
        elif recurrence["time_basis"] == "instant_utc":
            value["target_utc_instant"] = row["expressed_scheduled_fact"]
        if recurrence.get("timezone") is not None:
            value["timezone"] = recurrence["timezone"]
            value["timezone_database_version"] = recurrence["timezone_database_version"]
            value["target_local_date"] = str(row["expressed_scheduled_fact"]).split("T", 1)[0]
        values.append(value)
    return values


def _current_notification_target_snapshots(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    policies: Sequence[Mapping[str, object]],
    recurrence: Mapping[str, object] | None,
    range_start_utc: str,
    range_end_utc: str,
) -> dict[str, set[tuple[object, ...]]]:
    result: dict[str, set[tuple[object, ...]]] = {}
    for policy in policies:
        snapshots: set[tuple[object, ...]] = set()
        for target in _notification_targets(
            connection,
            item=item,
            policy=policy,
            recurrence=recurrence,
            range_start_utc=range_start_utc,
            range_end_utc=range_end_utc,
        ):
            snapshots.add(
                (
                    policy["target"]["anchor_role"],  # type: ignore[index]
                    policy["target"]["application_scope"],  # type: ignore[index]
                    target["target_scheduled_fact"],
                    target.get("target_utc_instant"),
                    target.get("occurrence_key"),
                )
            )
        result[str(policy["notification_intent_id"])] = snapshots
    return result


def _notification_work_stale_reason(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    work: sqlite3.Row,
    policy: Mapping[str, object] | None,
    valid_targets: Mapping[str, set[tuple[object, ...]]],
) -> str | None:
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


def _notification_target_from_anchor(anchor: Mapping[str, Any]) -> dict[str, object]:
    kind = str(anchor["anchor_kind"])
    if kind == "instant_utc":
        value = str(anchor["utc_instant"])
        return {"target_scheduled_fact": value, "target_utc_instant": value, "lifecycle": "scheduled", "actionable": True}
    timezone = str(anchor["timezone"])
    timezone_version = str(anchor.get("timezone_database_version") or system_timezone_database_version())
    local_date_value = str(anchor["local_date"])
    result: dict[str, object] = {
        "target_scheduled_fact": local_date_value,
        "target_local_date": local_date_value,
        "timezone": timezone,
        "timezone_database_version": timezone_version,
        "lifecycle": "scheduled",
        "actionable": True,
    }
    if kind == "local_instant":
        local_time = str(anchor["local_time"])
        if len(local_time) == 5:
            local_time += ":00"
        scheduled = f"{local_date_value}T{local_time}"
        resolution = resolve_local_instant(
            scheduled,
            timezone=timezone,
            timezone_database_version=timezone_version,
        )
        if resolution is None:
            raise SpineValidationError("semantic_conflict", "notification target is a nonexistent local instant")
        result["target_scheduled_fact"] = scheduled
        result["target_utc_instant"] = resolution.utc_instant
    return result


def _encode_recurrence_cursor(value: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value)
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii") + "." + hash_canonical_json(value)


def _decode_recurrence_cursor(value: Any, *, expected: Mapping[str, Any]) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.count(".") != 1:
        raise SpineValidationError("stale_version:cursor", "cursor is malformed")
    encoded, digest = value.split(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        decoded = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SpineValidationError("stale_version:cursor", "cursor is malformed") from exc
    if not isinstance(decoded, dict) or canonical_json_bytes(decoded) != payload or hash_canonical_json(decoded) != digest:
        raise SpineValidationError("stale_version:cursor", "cursor digest or encoding is invalid")
    last = decoded.pop("last_ordering_tuple", None)
    if decoded != dict(expected) or not isinstance(last, list) or not all(isinstance(entry, str) for entry in last):
        raise SpineValidationError("stale_version:cursor", "cursor facts are stale")
    return last


def _occurrence_ordering_tuple(value: Mapping[str, Any], range_basis: str) -> tuple[str, ...]:
    if range_basis == "original_schedule":
        return (
            str(value["original_scheduled_fact"]),
            str(value["occurrence_key"]),
            str(value["occurrence_id"]),
        )
    return (
        str(value["expressed_scheduled_fact"]),
        str(value["expressed_schedule_key"]),
        str(value["occurrence_key"]),
        str(value["occurrence_id"]),
    )


def _check_fields(command: str, request: Mapping[str, Any], allowed: set[str]) -> None:
    for key in request:
        if key not in allowed:
            raise SpineValidationError(f"unsupported_field:{key}", f"unsupported field for {command}: {key}")


def _subject_exists(connection: sqlite3.Connection, subject_id: str) -> bool:
    return connection.execute("SELECT 1 FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone() is not None


def _task_subject_roles(
    connection: sqlite3.Connection,
    *,
    command: str,
    command_id: str,
    value: Any,
    field: str,
    request_path: str,
) -> tuple[ItemSubjectRoleInput, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError(f"invalid_{field}", f"{field} must be an array")
    result: list[ItemSubjectRoleInput] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        element_field = f"{field}[{index}]"
        if not isinstance(raw, Mapping):
            raise SpineValidationError(f"invalid_{element_field}", f"{element_field} must be an object")
        for key in raw:
            if key not in {"subject_id", "role", "status"}:
                raise SpineValidationError(
                    f"unsupported_field:{element_field}.{key}",
                    f"unsupported subject role field: {key}",
                )
        subject_id = raw.get("subject_id")
        if subject_id is None:
            raise SpineValidationError(f"missing_{element_field}.subject_id", f"{element_field}.subject_id is required")
        if not isinstance(subject_id, str) or subject_id == "":
            raise SpineValidationError(f"invalid_{element_field}.subject_id", f"{element_field}.subject_id must be a non-empty string")
        role = raw.get("role")
        if role is None:
            raise SpineValidationError(f"missing_{element_field}.role", f"{element_field}.role is required")
        if role not in {"assignee", "owner"}:
            raise SpineValidationError(f"invalid_{element_field}.role", f"{element_field}.role must be assignee or owner")
        status = raw.get("status", "active")
        if status not in {"active", "inactive"}:
            raise SpineValidationError(f"invalid_{element_field}.status", f"{element_field}.status must be active or inactive")
        if not _subject_exists(connection, subject_id):
            raise SpineValidationError(
                f"subject_role_subject_not_found:{element_field}.subject_id",
                f"subject not found: {subject_id}",
            )
        identity = (subject_id, role)
        if identity in seen:
            raise SpineValidationError(f"invalid_{field}", f"{field} contains a duplicate subject_id and role")
        seen.add(identity)
        result.append(
            ItemSubjectRoleInput(
                item_subject_role_id=_derived_id(command, command_id, "item_subject_role", f"{request_path}/{index}"),
                subject_id=subject_id,
                role=role,
                status=status,
            )
        )
    return tuple(result)


def _subject_role_facts(subject_roles: Sequence[Any]) -> tuple[tuple[str, str, str], ...]:
    facts = []
    for row in subject_roles:
        subject_id = row.subject_id if isinstance(row, ItemSubjectRoleInput) else row["subject_id"]
        role = row.role if isinstance(row, ItemSubjectRoleInput) else row["role"]
        status = row.status if isinstance(row, ItemSubjectRoleInput) else row["status"]
        if role in {"assignee", "owner"}:
            facts.append((str(subject_id), str(role), str(status)))
    return tuple(sorted(facts))


def _subject(connection: sqlite3.Connection, subject_id: str, *, required: bool = True) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone()
    if row is None:
        if required:
            raise SpineValidationError("subject_not_found", f"subject not found: {subject_id}")
        return None
    return dict(row)


def _subject_response(subject: Mapping[str, Any] | None, *, created: bool, updated: bool, receipt_id: str) -> dict[str, Any]:
    assert subject is not None
    return {
        "ok": True,
        "command": "subject.upsert",
        "created": created,
        "updated": updated,
        "subject_id": subject["subject_id"],
        "subject_kind": subject["subject_kind"],
        "display_name": subject["display_name"],
        "status": subject["status"],
        "created_at_utc": subject["created_at_utc"],
        "updated_at_utc": subject["updated_at_utc"],
        "command_receipt_id": receipt_id,
    }


def _subject_group_exists(connection: sqlite3.Connection, group_id: str) -> bool:
    return connection.execute("SELECT 1 FROM subject_groups WHERE group_id = ?", (group_id,)).fetchone() is not None


def _subject_group(connection: sqlite3.Connection, group_id: str, *, required: bool = True) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM subject_groups WHERE group_id = ?", (group_id,)).fetchone()
    if row is None:
        if required:
            raise SpineValidationError("subject_group_not_found", f"subject group not found: {group_id}")
        return None
    return dict(row)


def _subject_group_response(group: Mapping[str, Any] | None, *, created: bool, updated: bool, receipt_id: str) -> dict[str, Any]:
    assert group is not None
    return {
        "ok": True,
        "command": "subject_group.upsert",
        "created": created,
        "updated": updated,
        "group_id": group["group_id"],
        "group_kind": group["group_kind"],
        "display_name": group["display_name"],
        "status": group["status"],
        "created_at_utc": group["created_at_utc"],
        "updated_at_utc": group["updated_at_utc"],
        "command_receipt_id": receipt_id,
    }


def _delivery_target(connection: sqlite3.Connection, delivery_target_id: str, *, required: bool = True) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM delivery_targets WHERE delivery_target_id = ?", (delivery_target_id,)).fetchone()
    if row is None:
        if required:
            raise SpineValidationError("delivery_target_not_found", f"delivery target not found: {delivery_target_id}")
        return None
    return dict(row)


def _delivery_target_routing_changed(existing: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    routing_fields = ("owner_kind", "owner_subject_id", "owner_group_id", "channel", "adapter_name", "account_id", "target_ref")
    return any(existing[field] != desired[field] for field in routing_fields)


def _delivery_target_in_use(connection: sqlite3.Connection, delivery_target_id: str) -> bool:
    policy = connection.execute(
        "SELECT 1 FROM notification_policies WHERE delivery_target_id = ? LIMIT 1",
        (delivery_target_id,),
    ).fetchone()
    if policy is not None:
        return True
    work = connection.execute(
        "SELECT 1 FROM work_instances WHERE delivery_target_id = ? LIMIT 1",
        (delivery_target_id,),
    ).fetchone()
    return work is not None


def _delivery_target_response(target: Mapping[str, Any] | None, *, created: bool, updated: bool, receipt_id: str) -> dict[str, Any]:
    assert target is not None
    response = {
        "ok": True,
        "command": "delivery_target.upsert",
        "created": created,
        "updated": updated,
        "delivery_target_id": target["delivery_target_id"],
        "owner_kind": target["owner_kind"],
        "owner_subject_id": target["owner_subject_id"],
        "owner_group_id": target["owner_group_id"],
        "channel": target["channel"],
        "adapter_name": target["adapter_name"],
        "account_id": target["account_id"],
        "target_ref": target["target_ref"],
        "display_name": target["display_name"],
        "status": target["status"],
        "created_at_utc": target["created_at_utc"],
        "updated_at_utc": target["updated_at_utc"],
        "command_receipt_id": receipt_id,
    }
    return {key: value for key, value in response.items() if value is not None}


def _hydrated_item(connection: sqlite3.Connection, item_id: str) -> dict[str, Any]:
    item = get_current_item(connection, item_id)
    detail = dict(item["detail"])
    for key in ("start_anchor_id", "end_anchor_id", "due_anchor_id", "defer_until_anchor_id"):
        if detail.get(key) is not None:
            detail[key.removesuffix("_id")] = _anchor_row(connection, str(detail[key]), field=key)
    item["detail"] = detail
    return item


def _receipt_item(connection: sqlite3.Connection, receipt: Mapping[str, Any]) -> dict[str, Any]:
    facts = receipt["result_identity_facts"]
    return _hydrated_item_at_version(connection, str(facts["item_id"]), int(facts["version"]))


def _hydrated_item_at_version(connection: sqlite3.Connection, item_id: str, version: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
          i.item_id, i.item_type, i.status, i.created_at_utc, i.archived_at_utc,
          v.title, v.summary, v.intent_hash, v.normalized_fields_hash, v.source_ref,
          v.created_at_utc AS version_created_at_utc,
          v.created_by_subject_id
        FROM coordination_items AS i
        JOIN coordination_item_versions AS v
          ON v.item_id = i.item_id
         AND v.version = ?
        WHERE i.item_id = ?
        """,
        (version, item_id),
    ).fetchone()
    if row is None:
        raise SpineValidationError("item_not_found", f"coordination item version not found: {item_id} v{version}")
    detail = _detail_at_version(connection, item_id=item_id, item_type=row["item_type"], version=version)
    for key in ("start_anchor_id", "end_anchor_id", "due_anchor_id", "defer_until_anchor_id"):
        if detail.get(key) is not None:
            detail[key.removesuffix("_id")] = _anchor_row(connection, str(detail[key]), field=key)
    return {
        "item_id": row["item_id"],
        "item_type": row["item_type"],
        "current_version": version,
        "status": row["status"],
        "created_at_utc": row["created_at_utc"],
        "updated_at_utc": row["version_created_at_utc"],
        "archived_at_utc": row["archived_at_utc"],
        "version": {
            "version": str(version),
            "title": row["title"],
            "summary": row["summary"],
            "intent_hash": row["intent_hash"],
            "normalized_fields_hash": row["normalized_fields_hash"],
            "source_ref": row["source_ref"],
            "created_at_utc": row["version_created_at_utc"],
            "created_by_subject_id": row["created_by_subject_id"],
        },
        "detail": detail,
        "locations": current_locations(connection, item_id=item_id, version=version),
        "subject_roles": current_subject_roles(connection, item_id=item_id, version=version),
        "notification_policies": current_notification_policies(connection, item_id=item_id, version=version),
    }


def _detail_at_version(connection: sqlite3.Connection, *, item_id: str, item_type: str, version: int) -> dict[str, Any]:
    if item_type == "event":
        row = connection.execute(
            """
            SELECT event_status, all_day, start_anchor_id, end_anchor_id, visibility,
                   attendance_policy_ref
            FROM event_details
            WHERE item_id = ? AND version = ?
            """,
            (item_id, version),
        ).fetchone()
    elif item_type == "task":
        row = connection.execute(
            """
            SELECT task_status, completion_state, priority, due_anchor_id, defer_until_anchor_id,
                   completed_at_utc, completed_by_subject_id
            FROM task_details
            WHERE item_id = ? AND version = ?
            """,
            (item_id, version),
        ).fetchone()
    else:
        return {}
    if row is None:
        raise SpineValidationError("item_not_found", f"coordination item detail not found: {item_id} v{version}")
    return dict(row)


def _anchor_row(connection: sqlite3.Connection, anchor_id: str, *, field: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM temporal_anchors WHERE anchor_id = ?", (anchor_id,)).fetchone()
    if row is None:
        raise SpineValidationError(f"anchor_not_found:{field}", f"anchor not found: {anchor_id}")
    result = {"anchor_id": row["anchor_id"], "anchor_kind": row["anchor_kind"], "created_at_utc": row["created_at_utc"]}
    for key in (
        "local_date",
        "local_time",
        "timezone",
        "timezone_database_version",
        "utc_instant",
        "window_start_utc",
        "window_end_utc",
        "source",
    ):
        if row[key] is not None:
            result[key] = row[key]
    recurrence = connection.execute(
        "SELECT recurrence_set_id FROM recurrence_sets WHERE seed_anchor_id = ?",
        (anchor_id,),
    ).fetchone()
    if recurrence is not None:
        result["recurrence_set_id"] = recurrence["recurrence_set_id"]
    return result


def _require_item_for_write(
    connection: sqlite3.Connection,
    command: str,
    item_id: str,
    expected_type: str | None,
    target_version: int,
    *,
    field: str = "target_version",
) -> dict[str, Any]:
    item = _hydrated_item(connection, item_id)
    if expected_type is not None and item["item_type"] != expected_type:
        raise SpineValidationError(f"wrong_type:{expected_type}:{item['item_type']}", "wrong item type")
    if item["status"] == "archived":
        raise SpineValidationError("archived_item", "archived items are immutable")
    if int(item["current_version"]) != target_version:
        raise SpineValidationError(f"stale_version:{field}", "target version is not current")
    return item


def _create_response(command: str, item: Mapping[str, Any], created: bool, receipt: Mapping[str, Any]) -> dict[str, Any]:
    shown = item_show_response(item)
    result = {
        "ok": True,
        "command": command,
        "created": created,
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "version": str(item["current_version"]),
        "current_version": str(item["current_version"]),
        "current_common": shown["current_common"],
        "audit_id": receipt["result_identity_facts"].get("audit_id"),
        "command_receipt_id": receipt["command_receipt_id"],
    }
    if item["item_type"] == "event":
        result["event_detail"] = shown["event_detail"]
    if item["item_type"] == "task":
        result["task_detail"] = shown["task_detail"]
        result["subject_roles"] = shown["subject_roles"]
    return {key: value for key, value in result.items() if value is not None}


def _lifecycle_response(
    command: str,
    item: Mapping[str, Any],
    effect_name: str,
    effect_value: bool,
    receipt_id: str,
    audit_id: Any,
    *,
    target_version: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        effect_name: effect_value,
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "target_version": target_version,
        "version": str(item["current_version"]),
        "current_version": str(item["current_version"]),
        "updated_at_utc": item["updated_at_utc"],
        "audit_id": audit_id,
        "command_receipt_id": receipt_id,
    }


def _archive_response(item: Mapping[str, Any], archived: bool, receipt_id: str, audit_id: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "item.archive",
        "archived": archived,
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "target_version": str(item["current_version"]),
        "version": str(item["current_version"]),
        "current_version": str(item["current_version"]),
        "status": item["status"],
        "archived_at_utc": item.get("archived_at_utc"),
        "updated_at_utc": item["updated_at_utc"],
        "audit_id": audit_id,
        "command_receipt_id": receipt_id,
    }


def _relation_create_response(connection: sqlite3.Connection, facts: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM coordination_item_relations WHERE relation_id = ?", (facts["relation_id"],)).fetchone()
    if row is None:
        raise SpineValidationError("relation_not_found", "relation not found")
    return {
        "ok": True,
        "command": "relation.create",
        "created": created,
        "relation_id": row["relation_id"],
        "source_item_id": row["source_item_id"],
        "source_target_version": str(facts["source_target_version"]),
        "source_current_version": str(facts["source_current_version"]),
        "target_item_id": row["target_item_id"],
        "target_target_version": str(facts["target_target_version"]),
        "target_current_version": str(facts["target_current_version"]),
        "relation_type": row["relation_type"],
        "relation_status": row["relation_status"],
        "created_at_utc": row["created_at_utc"],
        "created_by_subject_id": row["created_by_subject_id"],
        "audit_id": facts.get("audit_id"),
        "command_receipt_id": facts["command_receipt_id"],
    }


def _relation_element(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relation_id": row["relation_id"],
        "relation_type": row["relation_type"],
        "source_item_id": row["source_item_id"],
        "target_item_id": row["target_item_id"],
        "relation_status": row["relation_status"],
        "created_at_utc": row["created_at_utc"],
        "created_by_subject_id": row["created_by_subject_id"],
        "result_kind": "stored",
        "derived": False,
    }


def _derived_aliases(rows: Sequence[Mapping[str, Any]], relation_type: Any) -> list[dict[str, Any]]:
    aliases = []
    for row in rows:
        if row["relation_type"] == "depends_on" and relation_type in {None, "blocks"}:
            alias_type = "blocks"
        elif row["relation_type"] == "part_of" and relation_type in {None, "contains"}:
            alias_type = "contains"
        else:
            continue
        aliases.append(
            {
                "relation_id": row["relation_id"],
                "relation_type": alias_type,
                "source_item_id": row["target_item_id"],
                "target_item_id": row["source_item_id"],
                "relation_status": row["relation_status"],
                "created_at_utc": row["created_at_utc"],
                "created_by_subject_id": row["created_by_subject_id"],
                "result_kind": "derived_alias",
                "derived": True,
                "derived_from_relation_id": row["relation_id"],
                "derived_from_relation_type": row["relation_type"],
                "derived_source_item_id": row["source_item_id"],
                "derived_target_item_id": row["target_item_id"],
            }
        )
    return aliases


def _relations_for_item(connection: sqlite3.Connection, item_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM coordination_item_relations
        WHERE relation_status = 'active'
          AND (source_item_id = ? OR target_item_id = ?)
        ORDER BY relation_type, source_item_id, target_item_id, relation_id
        """,
        (item_id, item_id),
    ).fetchall()
    return [_relation_element(dict(row)) for row in rows]


def _reminder_response(facts: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
    response = {"ok": True, "command": "reminder.create", **dict(facts)}
    response["created"] = created
    return response


def _current_notification_policy(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    notification_intent_id: str,
    notification_policy_id: str,
) -> dict[str, object]:
    policies = load_current_notification_policies(
        connection,
        item_id=item_id,
        notification_intent_id=notification_intent_id,
    )
    if not policies:
        raise SpineValidationError("referenced_row_not_found", "notification intent is not current")
    policy = policies[0]
    if policy["notification_policy_id"] != notification_policy_id:
        raise SpineValidationError(
            "stale_version:notification_policy_id",
            "notification policy is not current",
        )
    return policy


def _notification_authoring_target(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise SpineValidationError("invalid_target", "target must be an object")
    return {key: value[key] for key in ("anchor_role", "application_scope", "target_occurrence_key") if key in value}


def _notification_target_selector(
    target: Mapping[str, object],
    *,
    recurrence: Mapping[str, object] | None,
    current_target: object,
) -> dict[str, object] | None:
    if target.get("application_scope") != "selected_occurrence":
        return None
    key = target.get("target_occurrence_key")
    if not isinstance(key, str):
        raise SpineValidationError(
            "invalid_target.target_occurrence_key",
            "selected occurrence requires target_occurrence_key",
        )
    if isinstance(current_target, Mapping) and current_target.get("target_occurrence_key") == key:
        selector = current_target.get("target_occurrence_selector")
        if isinstance(selector, dict):
            return selector
    return _resolve_current_occurrence_selector(recurrence, key)


def _persist_notification_successor(
    context: CommandContext,
    *,
    item: Mapping[str, Any],
    current: Mapping[str, object],
    revised: Any,
    selector: dict[str, object] | None,
    target_version: int,
    command_id: str,
    actor: str,
    changed_at_utc: str,
    audit_id: str,
    action: str,
    receipt: Mapping[str, object],
) -> None:
    def insert_successor(connection: sqlite3.Connection, next_version: int) -> None:
        remove_copied_notification_policy(
            connection,
            item_id=str(item["item_id"]),
            item_version=next_version,
            notification_intent_id=str(current["notification_intent_id"]),
        )
        target = revised.value["target"]
        if selector is not None:
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
            target["target_occurrence_selector_ref"] = target_ref
        insert_notification_schedule_policy(connection, normalized=revised)
        insert_command_receipt(connection, receipt)

    create_next_item_version(
        context.ledger,
        item_id=str(item["item_id"]),
        target_version=target_version,
        created_at_utc=changed_at_utc,
        created_by_subject_id=actor,
        audit_id=audit_id,
        audit_action=action,
        reason_code=action,
        insert_canonical_extension=insert_successor,
        supporting_command_id=command_id,
    )


def _notification_mutation_facts(
    *,
    command: str,
    command_id: str,
    item: Mapping[str, Any],
    target_version: int,
    audit_id: str,
    policy: Mapping[str, object],
    changed_field: str,
    effect: str,
) -> dict[str, object]:
    return {
        "command_receipt_id": _receipt_id(command, command_id),
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "version": str(target_version + 1),
        "current_version": str(target_version + 1),
        "audit_id": audit_id,
        "notification_intent_id": policy["notification_intent_id"],
        "notification_policy_id": policy["notification_policy_id"],
        "notification_schedule_id": policy["notification_schedule_id"],
        "normalized_notification_schedule_hash": policy["normalized_notification_schedule_hash"],
        changed_field: True,
        "effect": effect,
    }


def _reminder_route(request: Mapping[str, Any], context: CommandContext, channel: str) -> dict[str, Any]:
    routed_fields = {"recipient_kind", "recipient_subject_id", "recipient_group_id", "delivery_target_id"}
    routed = any(field in request for field in routed_fields)
    if not routed:
        return _error(
            "reminder.create",
            "missing_required_field",
            "recipient and delivery target routing are required",
            "recipient_kind",
        )
    recipient_kind = _enum(request.get("recipient_kind"), "recipient_kind", {"subject", "subject_group"})
    recipient_subject_id = _optional_str(request, "recipient_subject_id")
    recipient_group_id = _optional_str(request, "recipient_group_id")
    delivery_target_id = _required_str(request, "delivery_target_id")
    if recipient_kind == "subject":
        if recipient_subject_id is None or recipient_group_id is not None:
            return _error(
                "reminder.create", "invalid_request", "subject recipient requires recipient_subject_id only", "recipient_subject_id"
            )
        if not _subject_exists(context.ledger, recipient_subject_id):
            return _error("reminder.create", "referenced_row_not_found", "recipient subject not found", "recipient_subject_id")
        work_subject_ref = f"subject:{recipient_subject_id}"
    else:
        if recipient_group_id is None or recipient_subject_id is not None:
            return _error("reminder.create", "invalid_request", "group recipient requires recipient_group_id only", "recipient_group_id")
        if not _subject_group_exists(context.ledger, recipient_group_id):
            return _error("reminder.create", "referenced_row_not_found", "recipient group not found", "recipient_group_id")
        work_subject_ref = f"subject_group:{recipient_group_id}"

    target = _delivery_target(context.ledger, delivery_target_id, required=False)
    if target is None:
        return _error("reminder.create", "referenced_row_not_found", "delivery target not found", "delivery_target_id")
    if target["status"] != "active":
        return _error("reminder.create", "invalid_state_transition", "delivery target is not active", "delivery_target_id")
    if target["adapter_name"] != "openclaw":
        return _error("reminder.create", "environment_failure", "OpenClaw delivery target is required", "delivery_target_id")
    if target["channel"] != channel:
        return _error(
            "reminder.create", "semantic_conflict", "delivery target channel does not match reminder channel", "delivery_target_id"
        )
    if recipient_kind == "subject" and (target["owner_kind"] != "subject" or target["owner_subject_id"] != recipient_subject_id):
        return _error("reminder.create", "semantic_conflict", "delivery target owner does not match recipient", "delivery_target_id")
    if recipient_kind == "subject_group" and (target["owner_kind"] != "subject_group" or target["owner_group_id"] != recipient_group_id):
        return _error("reminder.create", "semantic_conflict", "delivery target owner does not match recipient", "delivery_target_id")
    return {
        "ok": True,
        "recipient_kind": recipient_kind,
        "recipient_subject_id": recipient_subject_id,
        "recipient_group_id": recipient_group_id,
        "delivery_target_id": delivery_target_id,
        "delivery_target": target,
        "work_subject_ref": work_subject_ref,
    }


def _find_duplicate_structured_notification(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    normalized: Mapping[str, object],
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
          p.policy_id, p.notification_intent_id, p.schedule_id,
          p.version, p.normalized_notification_schedule_hash,
          i.item_type, i.current_version
        FROM notification_policies AS p
        JOIN coordination_items AS i ON i.item_id = p.item_id
        WHERE p.item_id = ?
          AND p.version = i.current_version
          AND p.recipient_kind = ?
          AND ((? IS NULL AND p.recipient_subject_id IS NULL) OR p.recipient_subject_id = ?)
          AND ((? IS NULL AND p.recipient_group_id IS NULL) OR p.recipient_group_id = ?)
          AND ((? IS NULL AND p.delivery_target_id IS NULL) OR p.delivery_target_id = ?)
          AND p.channel = ?
          AND p.normalized_notification_schedule_hash = ?
          AND p.status = 'active'
        ORDER BY p.created_at_utc, p.policy_id
        LIMIT 1
        """,
        (
            item_id,
            normalized["recipient_kind"],
            normalized.get("recipient_subject_id"),
            normalized.get("recipient_subject_id"),
            normalized.get("recipient_group_id"),
            normalized.get("recipient_group_id"),
            normalized["delivery_target_id"],
            normalized["delivery_target_id"],
            normalized["channel"],
            normalized["normalized_notification_schedule_hash"],
        ),
    ).fetchone()
    if row is None:
        return None
    return {
        "item_id": item_id,
        "item_type": row["item_type"],
        "version": str(row["version"]),
        "current_version": str(row["current_version"]),
        "notification_intent_id": row["notification_intent_id"],
        "notification_policy_id": row["policy_id"],
        "notification_schedule_id": row["schedule_id"],
        "notification_policy_item_version": str(row["version"]),
        "normalized_notification_schedule_hash": row["normalized_notification_schedule_hash"],
    }


def _resolve_current_occurrence_selector(recurrence: Mapping[str, object] | None, occurrence_key: str) -> dict[str, object]:
    current = _resolve_current_occurrence(recurrence, occurrence_key)
    selector = current.get("target_occurrence_selector")
    assert isinstance(selector, dict)
    return selector


def _resolve_current_occurrence(recurrence: Mapping[str, object] | None, occurrence_key: str) -> dict[str, object]:
    if recurrence is None:
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "selected occurrence requires a current recurrence set",
        )
    if occurrence_key.count(".") != 1:
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "occurrence key is malformed",
        )
    encoded, digest = occurrence_key.split(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        preimage = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "occurrence key is malformed",
        ) from exc
    if (
        not isinstance(preimage, dict)
        or canonical_json_bytes(preimage) != payload
        or hash_canonical_json(preimage) != digest
        or preimage.get("derivation_version") != "spine.recurrence-occurrence-key.v2"
    ):
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "occurrence key does not verify",
        )
    selector = preimage.get("target_occurrence_selector")
    if not isinstance(selector, dict) or selector.get("recurrence_set_id") != recurrence.get("recurrence_set_id"):
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "occurrence key does not belong to this recurrence set",
        )
    scheduled_fact = selector.get("scheduled_fact")
    if not isinstance(scheduled_fact, str):
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "occurrence key selector is incomplete",
        )
    range_end = _next_scheduled_fact(scheduled_fact, time_basis=str(recurrence["time_basis"]))
    expansion = expand_recurrence_set(
        dict(recurrence),
        range_basis="original_schedule",
        range_start=scheduled_fact,
        range_end=range_end,
    )
    matches = [value for value in expansion.occurrences if value.get("occurrence_key") == occurrence_key]
    if len(matches) != 1 or matches[0].get("lifecycle") != "active":
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "selected occurrence is not uniquely current and actionable",
        )
    current_selector = matches[0].get("target_occurrence_selector")
    if not isinstance(current_selector, dict) or current_selector != selector:
        raise SpineValidationError(
            "semantic_conflict:notification.target.target_occurrence_key",
            "selected occurrence selector is stale",
        )
    return dict(matches[0])


def _next_scheduled_fact(value: str, *, time_basis: str) -> str:
    parsed = parse_scheduled_fact(value, time_basis=time_basis, field="scheduled_fact")
    if time_basis == "local_date":
        assert isinstance(parsed, date) and not isinstance(parsed, datetime)
        return (parsed + timedelta(days=1)).isoformat()
    assert isinstance(parsed, datetime)
    advanced = parsed + timedelta(seconds=1)
    return _format_scheduled_fact(advanced, time_basis=time_basis)


def _select_recurrence_segment(
    recurrence: Mapping[str, object],
    *,
    scheduled_fact: str,
    requested_segment_id: str | None,
) -> dict[str, object]:
    segments = [
        value
        for value in recurrence["segments"]  # type: ignore[union-attr]
        if value["status"] == "active"
        and str(value["active_start"]) <= scheduled_fact
        and (value.get("active_end") is None or scheduled_fact < str(value["active_end"]))
    ]
    if len(segments) != 1:
        field = "scheduled_fact" if not segments else "segments"
        raise SpineValidationError(f"semantic_conflict:{field}", "scheduled fact must resolve to one active segment")
    segment = dict(segments[0])
    if requested_segment_id is not None and requested_segment_id != segment["segment_id"]:
        raise SpineValidationError("semantic_conflict:segment_id", "segment_id does not contain the occurrence")
    return segment


def _segment_for_occurrence(
    recurrence: Mapping[str, object],
    occurrence: Mapping[str, object],
    *,
    requested_segment_id: str | None,
) -> dict[str, object]:
    segment = next(
        (
            dict(value)
            for value in recurrence["segments"]  # type: ignore[union-attr]
            if value["segment_id"] == occurrence["segment_id"]
        ),
        None,
    )
    if segment is None:
        raise SpineValidationError("semantic_conflict:segments", "occurrence segment is missing")
    if requested_segment_id is not None and requested_segment_id != segment["segment_id"]:
        raise SpineValidationError("semantic_conflict:segment_id", "segment_id does not match target occurrence")
    return segment


def _occurrence_at_scheduled_fact(recurrence: Mapping[str, object], scheduled_fact: str) -> dict[str, object] | None:
    expanded = expand_recurrence_set(
        dict(recurrence),
        range_basis="original_schedule",
        range_start=scheduled_fact,
        range_end=_next_scheduled_fact(scheduled_fact, time_basis=str(recurrence["time_basis"])),
    )
    matches = [dict(value) for value in expanded.occurrences if value["original_scheduled_fact"] == scheduled_fact]
    if len(matches) > 1:
        raise SpineValidationError("semantic_conflict:scheduled_fact", "scheduled fact is ambiguous")
    return matches[0] if matches else None


def _normalized_recurrence_override_fields(request: Mapping[str, Any], *, item_type: str, require_any: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    expressed = request.get("expressed_scheduled_fact")
    if expressed is not None:
        if not isinstance(expressed, str):
            raise SpineValidationError("invalid_expressed_scheduled_fact", "expressed_scheduled_fact must be a string")
        result["expressed_scheduled_fact"] = expressed
    common = request.get("common_detail_patch")
    if common is not None:
        if not isinstance(common, Mapping) or not common:
            raise SpineValidationError("invalid_common_detail_patch", "common_detail_patch must be a non-empty object")
        unknown = sorted(set(common) - {"title", "summary", "source_ref"})
        if unknown:
            raise SpineValidationError(f"unsupported_field:common_detail_patch.{unknown[0]}", "unsupported common detail patch field")
        result["common_detail_patch"] = _canonical_value(common)
    event_patch = request.get("event_detail_patch")
    if event_patch is not None:
        if item_type != "event":
            raise SpineValidationError("semantic_conflict:event_detail_patch", "event patch requires an event")
        if not isinstance(event_patch, Mapping) or not event_patch:
            raise SpineValidationError("invalid_event_detail_patch", "event_detail_patch must be a non-empty object")
        unknown = sorted(set(event_patch) - {"all_day", "end_scheduled_fact"})
        if unknown:
            raise SpineValidationError(f"unsupported_field:event_detail_patch.{unknown[0]}", "unsupported event patch field")
        result["event_detail_patch"] = _canonical_value(event_patch)
    task_patch = request.get("task_detail_patch")
    if task_patch is not None:
        if item_type != "task":
            raise SpineValidationError("semantic_conflict:task_detail_patch", "task patch requires a task")
        if not isinstance(task_patch, Mapping) or not task_patch:
            raise SpineValidationError("invalid_task_detail_patch", "task_detail_patch must be a non-empty object")
        unknown = sorted(set(task_patch) - {"priority", "defer_until_scheduled_fact"})
        if unknown:
            raise SpineValidationError(f"unsupported_field:task_detail_patch.{unknown[0]}", "unsupported task patch field")
        result["task_detail_patch"] = _canonical_value(task_patch)
    lifecycle = request.get("lifecycle")
    if lifecycle is not None:
        allowed = {"active", "cancelled"} if item_type == "event" else {"active", "cancelled", "completed"}
        result["lifecycle"] = _enum(lifecycle, "lifecycle", allowed)
    if require_any and not result:
        raise SpineValidationError("missing_override", "an override field is required")
    return result


def _override_kind(fields: Mapping[str, object]) -> tuple[str, str]:
    move = "expressed_scheduled_fact" in fields
    detail = any(key in fields for key in ("common_detail_patch", "event_detail_patch", "task_detail_patch"))
    lifecycle = "lifecycle" in fields
    parts = [name for present, name in ((move, "move"), (detail, "detail_patch"), (lifecycle, "lifecycle")) if present]
    if not parts:
        raise SpineValidationError("missing_override", "an override field is required")
    return "_".join(parts), "/".join(parts)


def _replace_or_add_override(
    overrides: list[dict[str, object]],
    *,
    recurrence: Mapping[str, object],
    occurrence: Mapping[str, object],
    segment: Mapping[str, object],
    command_id: str,
    patch_fields: Mapping[str, object],
    reason_code: str | None,
    created_effect: str,
    replaced_effect: str,
) -> tuple[list[dict[str, object]], str, dict[str, object]]:
    kind, path = _override_kind(patch_fields)
    selector = occurrence["target_occurrence_selector"]
    segment_ref = str(segment["segment_index"])
    revision_key, _ = generated_id(
        "revkey",
        "spine.recurrence-override-revision-key.v2",
        {
            "command_id": command_id,
            "recurrence_set_id": recurrence["recurrence_set_id"],
            "prior_recurrence_revision_id": recurrence["recurrence_revision_id"],
            "target_occurrence_selector": selector,
            "segment_ref": segment_ref,
            "override_path": path,
        },
    )
    replaced = False
    for value in overrides:
        if value.get("status") == "active" and value["target_occurrence_key"] == occurrence["occurrence_key"]:
            value["status"] = "superseded"
            replaced = True
    override = {
        "segment_id": segment["segment_id"],
        "target_occurrence_key": occurrence["occurrence_key"],
        "target_occurrence_selector": selector,
        "override_kind": kind,
        "revision_key": revision_key,
        **dict(patch_fields),
        **({"reason_code": reason_code} if reason_code is not None else {}),
        "status": "active",
    }
    overrides.append(override)
    return overrides, replaced_effect if replaced else created_effect, {"revision_key": revision_key}


def _override_semantics(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value[key]
        for key in (
            "expressed_scheduled_fact",
            "common_detail_patch",
            "event_detail_patch",
            "task_detail_patch",
            "lifecycle",
            "reason_code",
        )
        if value.get(key) is not None
    }


def _recurrence_mutation_noop(
    context: CommandContext,
    *,
    command: str,
    command_id: str,
    actor: str,
    changed_at: str,
    semantic: Mapping[str, Any],
    item: Mapping[str, Any],
    target_version: int,
    recurrence: Mapping[str, object],
    effect: str,
    extra: Mapping[str, object],
) -> dict[str, Any]:
    facts = {
        "command_receipt_id": _receipt_id(command, command_id),
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "current_version": str(target_version),
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "revision_number": recurrence["revision_number"],
        "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
        "changed": False,
        "effect": effect,
        **dict(extra),
    }
    receipt = _store_write_receipt(
        context,
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=changed_at,
        effect=effect,
        item_id=str(item["item_id"]),
        target_version=str(target_version),
        semantic_facts={**semantic, **facts},
        result_identity_facts=facts,
    )
    return {"ok": True, "command": command, **receipt["result_identity_facts"]}


def _insert_audit(
    connection: sqlite3.Connection, audit_id: str, item_id: str, action: str, actor: str, created_at: str, payload: Mapping[str, Any]
) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO audit_log (
              audit_id, item_id, stage, action, reason_code, actor_ref, payload_hash, created_at_utc
            )
            VALUES (?, ?, 'item', ?, ?, ?, ?, ?)
            """,
            (audit_id, item_id, action, action, actor, audit_log_payload_hash(payload), created_at),
        )


def _error(command: str, code: str, message: str, field: str | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return {"ok": False, "command": command, "error": error}


def _validation_error(command: str, exc: SpineValidationError) -> dict[str, Any]:
    code = exc.code
    if code.startswith("runtime_failure:"):
        return _error(command, "runtime_failure", exc.message)
    if code.startswith("environment_failure:"):
        return _error(command, "environment_failure", exc.message, code.split(":", 1)[1])
    if code.startswith("referenced_row_not_found:"):
        return _error(command, "referenced_row_not_found", exc.message, code.split(":", 1)[1])
    if code.startswith("semantic_conflict:"):
        return _error(command, "semantic_conflict", exc.message, code.split(":", 1)[1])
    if code.startswith("invalid_request:"):
        return _error(command, "invalid_request", exc.message, code.split(":", 1)[1])
    if code == "recurrence_not_configured":
        return _error(command, "invalid_request", exc.message, "item_id")
    if code == "unsupported_recurrence_item":
        return _error(command, "invalid_request", exc.message, "item_id")
    if code.startswith("unsupported_field:"):
        return _error(command, "unsupported_field", exc.message, code.split(":", 1)[1])
    if code.startswith("unsupported_patch."):
        return _error(command, "unsupported_field", exc.message, "patch." + code.split(".", 1)[1])
    if code.startswith("invalid_patch."):
        return _error(command, "invalid_request", exc.message, "patch." + code.split(".", 1)[1])
    if code.startswith("stale_version:"):
        return _error(command, "stale_version", exc.message, code.split(":", 1)[1])
    if code.startswith("stale_cursor:"):
        return _error(command, "stale_cursor", exc.message, code.split(":", 1)[1])
    if code.startswith("wrong_type:"):
        _, expected, actual = code.split(":")
        return _wrong_type(command, "", expected, actual)
    if code.startswith("anchor_not_found:"):
        return _error(command, "referenced_row_not_found", exc.message, code.split(":", 1)[1])
    if code.startswith("subject_role_subject_not_found:"):
        return _error(command, "referenced_row_not_found", exc.message, code.split(":", 1)[1])
    if code == "actor_not_found":
        return _error(command, "referenced_row_not_found", exc.message, "actor_subject_id")
    if code == "subject_not_found":
        return _error(command, "referenced_row_not_found", exc.message, "subject_id")
    if code in {"item_not_found", "anchor_not_found"}:
        return _error(command, "referenced_row_not_found", exc.message, "item_id")
    if code in {"command_id_reuse", "incompatible_replay"}:
        return _error(command, "semantic_conflict", exc.message, "command_id")
    if code in {"item_relation_rejected"}:
        return _error(command, "semantic_conflict", exc.message, "relation")
    if code == "archived_item":
        return _error(command, "invalid_state_transition", exc.message, "status")
    if code.startswith("invalid_timestamp"):
        field = code.removeprefix("invalid_timestamp").removeprefix("_")
        return _error(command, "invalid_timestamp", exc.message, field or None)
    if code.startswith("missing_"):
        field = code.removeprefix("missing_")
        return _error(command, "missing_required_field", exc.message, field)
    if code.startswith("invalid_"):
        field = code.removeprefix("invalid_")
        return _error(command, "invalid_request", exc.message, field)
    if code.startswith("unsupported_"):
        field = code.removeprefix("unsupported_")
        public_code = "unsupported_field" if field in {"relation_type", "channel", "item_type", "status"} else "invalid_request"
        return _error(command, public_code, exc.message, field)
    if code in {"item_type_mismatch"}:
        return _error(command, "wrong_item_type", exc.message, "item_id")
    if code.startswith("invalid_") or "transition" in code:
        return _error(command, "invalid_state_transition", exc.message, "status")
    return _error(command, "invalid_request", exc.message, "request")


def _wrong_type(command: str, item_id: str, expected: str, actual: str) -> dict[str, Any]:
    return _error(command, "wrong_item_type", f"expected {expected} item but found {actual}", "item_id")
