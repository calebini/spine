"""Transport-neutral dispatcher for the Spine agent command contract MVP."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

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
from spine.core.hashing import audit_log_payload_hash
from spine.core.recurrence import (
    MAX_EXPANSION_LIMIT,
    expand_daily_local_occurrences,
    normalize_daily_recurrence_rule,
    parse_local_date,
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
from spine.ledger.relations import create_item_relation
from spine.ledger.supporting import (
    ItemSubjectRoleInput,
    NotificationPolicyInput,
    current_locations,
    current_notification_policies,
    current_subject_roles,
    insert_notification_policy,
)
from spine.ledger.work import create_work_instance

MVP_COMMANDS = frozenset(
    {
        "subject.upsert",
        "subject_group.upsert",
        "delivery_target.upsert",
        "item.show",
        "item.list",
        "item.occurrences",
        "item.archive",
        "event.create",
        "event.update",
        "event.reschedule",
        "event.cancel",
        "task.create",
        "task.update",
        "task.complete",
        "task.cancel",
        "relation.create",
        "relation.list",
        "reminder.create",
    }
)

WRITE_COMMANDS = MVP_COMMANDS - {"item.show", "item.list", "item.occurrences", "relation.list"}


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
    if command == "item.show":
        return _handle_item_show(request, context)
    if command == "item.list":
        return _handle_item_list(request, context)
    if command == "item.occurrences":
        return _handle_item_occurrences(request, context)
    if command == "event.create":
        return _handle_event_create(request, context)
    if command == "task.create":
        return _handle_task_create(request, context)
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
    return _error(command, "unsupported_command", f"unsupported command: {command}", "command")


def _handle_subject_upsert(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields("subject.upsert", request, {"command_id", "actor_subject_id", "subject_id", "subject_kind", "display_name", "status", "updated_at_utc"})
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
        existing[key] != value
        for key, value in {"subject_kind": subject_kind, "display_name": display_name, "status": status}.items()
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
    return _subject_response(_subject(context.ledger, subject_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"])


def _handle_subject_group_upsert(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields("subject_group.upsert", request, {"command_id", "actor_subject_id", "group_id", "group_kind", "display_name", "status", "updated_at_utc"})
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
        return _subject_group_response(_subject_group(context.ledger, group_id), created=False, updated=False, receipt_id=replay["command_receipt_id"])
    existing = _subject_group(context.ledger, group_id, required=False)
    created = existing is None
    updated = created or any(
        existing[key] != value
        for key, value in {"group_kind": group_kind, "display_name": display_name, "status": status}.items()
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
    return _subject_group_response(_subject_group(context.ledger, group_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"])


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
        return _delivery_target_response(_delivery_target(context.ledger, delivery_target_id), created=False, updated=False, receipt_id=replay["command_receipt_id"])
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
    if existing is not None and _delivery_target_routing_changed(existing, desired) and _delivery_target_in_use(context.ledger, delivery_target_id):
        return _error("delivery_target.upsert", "semantic_conflict", "delivery target routing cannot change while referenced", "delivery_target_id")
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
    return _delivery_target_response(_delivery_target(context.ledger, delivery_target_id), created=created, updated=updated, receipt_id=receipt["command_receipt_id"])


def _handle_item_show(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields("item.show", request, {"item_id", "include_relations", "locations_limit", "subject_roles_limit", "notification_policies_limit", "relations_limit"})
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
        {"item_id", "range_start_local_date", "range_end_local_date", "limit"},
    )
    item_id = _required_str(request, "item_id")
    range_start = _required_str(request, "range_start_local_date")
    range_end = _required_str(request, "range_end_local_date")
    limit = _occurrence_limit(request.get("limit", 100))
    item = _hydrated_item(context.ledger, item_id)
    detail = item["detail"]

    if item["item_type"] == "event":
        seed = detail.get("start_anchor")
        recurrence_field = "start_anchor.recurrence_rule"
    elif item["item_type"] == "task":
        seed = detail.get("due_anchor")
        recurrence_field = "due_anchor.recurrence_rule"
    else:
        raise SpineValidationError(
            "unsupported_recurrence_item",
            "item.occurrences currently supports event and task items",
        )
    if not isinstance(seed, Mapping) or seed.get("recurrence_rule") is None:
        raise SpineValidationError(
            "recurrence_not_configured",
            f"{item['item_type']} item has no configured recurrence",
        )

    expanded = expand_daily_local_occurrences(
        item_id=item_id,
        anchor_kind=str(seed["anchor_kind"]),
        seed_local_date=str(seed["local_date"]),
        seed_local_time=str(seed["local_time"]) if seed.get("local_time") is not None else None,
        timezone=str(seed["timezone"]),
        recurrence_rule=str(seed["recurrence_rule"]),
        range_start_local_date=range_start,
        range_end_local_date=range_end,
        limit=limit,
    )
    seed_date = parse_local_date("seed.local_date", str(seed["local_date"]))
    occurrences: list[dict[str, Any]] = []
    for occurrence in expanded.occurrences:
        occurrence_date = parse_local_date("occurrence.local_date", occurrence.local_date)
        day_offset = (occurrence_date - seed_date).days
        scheduled_anchor = {
            "anchor_kind": seed["anchor_kind"],
            "local_date": occurrence.local_date,
            "timezone": occurrence.timezone,
        }
        if occurrence.local_time is not None:
            scheduled_anchor["local_time"] = occurrence.local_time
        row: dict[str, Any] = {
            "occurrence_id": occurrence.occurrence_id,
            "occurrence_key": occurrence.occurrence_key,
            "ordinal": str(occurrence.ordinal),
            "virtual": True,
        }
        if item["item_type"] == "event":
            row["occurrence_event_detail"] = {
                "event_status": detail["event_status"],
                "all_day": bool(detail["all_day"]),
                "start_anchor": scheduled_anchor,
            }
            if detail.get("end_anchor") is not None:
                row["occurrence_event_detail"]["end_anchor"] = _shift_virtual_local_anchor(
                    detail["end_anchor"],
                    day_offset=day_offset,
                )
        else:
            row["occurrence_task_detail"] = {
                "task_status": detail["task_status"],
                "due_anchor": scheduled_anchor,
            }
            if detail.get("defer_until_anchor") is not None:
                shifted_defer = _shift_virtual_local_anchor(
                    detail["defer_until_anchor"],
                    day_offset=day_offset,
                    required=False,
                )
                if shifted_defer is not None:
                    row["occurrence_task_detail"]["defer_until_anchor"] = shifted_defer
        occurrences.append(row)

    return {
        "ok": True,
        "command": "item.occurrences",
        "item_id": item_id,
        "item_type": item["item_type"],
        "current_version": str(item["current_version"]),
        "title": item["version"]["title"],
        "recurrence_field": recurrence_field,
        "recurrence_rule": seed["recurrence_rule"],
        "range_start_local_date": range_start,
        "range_end_local_date": range_end,
        "occurrences": occurrences,
        "limit": str(limit),
        "truncated": expanded.truncated,
    }


def _handle_event_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "created_at_utc", "title", "summary", "source_ref", "all_day", "start_anchor", "end_anchor", "visibility", "attendance_policy_ref"}
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
        end_anchor = _anchor_input(request.get("end_anchor"), "end_anchor", _derived_id("event.create", command_id, "end_anchor", "/end_anchor"))
    semantic = _semantic_request("event.create", command_id, actor, created_at, request, allowed)
    replay = _compatible_replay("event.create", command_id, semantic, context)
    if replay is not None:
        return _create_response("event.create", _receipt_item(context.ledger, replay), False, replay)
    item_id = _derived_id("event.create", command_id, "item", "/item")
    audit_id = _derived_id("event.create", command_id, "audit", "/audit")
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
        },
    )
    return _create_response("event.create", _hydrated_item(context.ledger, result.item_id), True, receipt)


def _handle_task_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "created_at_utc", "title", "summary", "source_ref", "due_anchor", "defer_until_anchor", "priority", "subject_roles"}
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
    defer_anchor = _anchor_input(request.get("defer_until_anchor"), "defer_until_anchor", _derived_id("task.create", command_id, "defer_until_anchor", "/defer_until_anchor")) if request.get("defer_until_anchor") is not None else None
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
        },
    )
    return _create_response("task.create", _hydrated_item(context.ledger, result.item_id), True, receipt)


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
        return response_fn(updated=False, item=_receipt_item(context.ledger, replay), target_version=str(target_version), audit_id=None, command_receipt_id=replay["command_receipt_id"])
    item = _require_item_for_write(context.ledger, command, item_id, expected_type, target_version)
    current_common = item["version"]
    common_changed = _changed_common(current_common, patch)
    roles_changed = replacement_subject_roles is not None and _subject_role_facts(item["subject_roles"]) != _subject_role_facts(replacement_subject_roles)
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
        return response_fn(updated=False, item=item, target_version=str(target_version), audit_id=None, command_receipt_id=receipt["command_receipt_id"])
    audit_id = _derived_id(command, command_id, "audit", "/audit")
    mutation = create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=updated_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        title=patch.get("title"),
        summary=patch["summary"] if "summary" in patch else _UNSET,
        source_ref=patch["source_ref"] if "source_ref" in patch else _UNSET,
        subject_roles=replacement_subject_roles if replacement_subject_roles is not None else _UNSET,
        subject_role_replacement_roles=("assignee", "owner") if replacement_subject_roles is not None else (),
        audit_action=f"{expected_type}_updated",
        reason_code=f"{expected_type}_updated",
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
    return response_fn(updated=True, item=_hydrated_item(context.ledger, item_id), target_version=str(target_version), audit_id=mutation.audit_id, command_receipt_id=receipt["command_receipt_id"])


def _handle_event_reschedule(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "item_id", "target_version", "rescheduled_at_utc", "all_day", "start_anchor", "end_anchor", "patch"}
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
    end_anchor = _anchor_input(request.get("end_anchor"), "end_anchor", _derived_id("event.reschedule", command_id, "end_anchor", "/end_anchor")) if request.get("end_anchor") is not None else None
    patch = _patch(request.get("patch", {}))
    semantic = _semantic_request("event.reschedule", command_id, actor, at, request, allowed)
    replay = _compatible_replay("event.reschedule", command_id, semantic, context)
    if replay is not None:
        return event_reschedule_response(rescheduled=False, item=_receipt_item(context.ledger, replay), target_version=str(target_version), audit_id=None, command_receipt_id=replay["command_receipt_id"])
    item = _require_item_for_write(context.ledger, "event.reschedule", item_id, "event", target_version)
    if item["detail"]["event_status"] == "cancelled":
        return _error("event.reschedule", "invalid_state_transition", "cancelled events cannot be rescheduled", "event_status")
    current = item["detail"]
    requested_end = _anchor_semantic_facts(_anchor_output(end_anchor)) if end_anchor is not None else None
    anchor_noop = (
        _anchor_semantic_facts(current["start_anchor"])
        == _anchor_semantic_facts(_anchor_output(start_anchor))
        and _anchor_semantic_facts(current.get("end_anchor")) == requested_end
        and bool(current["all_day"]) == all_day
    )
    common_noop = not _changed_common(item["version"], patch)
    if anchor_noop and common_noop:
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
            result_identity_facts={"command_receipt_id": _receipt_id("event.reschedule", command_id), "item_id": item_id, "target_version": str(target_version), "version": str(target_version), "current_version": str(target_version)},
        )
        return event_reschedule_response(rescheduled=False, item=item, target_version=str(target_version), audit_id=None, command_receipt_id=receipt["command_receipt_id"])
    audit_id = _derived_id("event.reschedule", command_id, "audit", "/audit")
    with context.ledger:
        insert_temporal_anchor(context.ledger, anchor=start_anchor, anchor_id=start_anchor.anchor_id or "", default_created_at_utc=at)
        if end_anchor is not None:
            insert_temporal_anchor(context.ledger, anchor=end_anchor, anchor_id=end_anchor.anchor_id or "", default_created_at_utc=at)
    mutation = create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        title=patch.get("title"),
        summary=patch["summary"] if "summary" in patch else _UNSET,
        source_ref=patch["source_ref"] if "source_ref" in patch else _UNSET,
        event_detail={
            "all_day": int(all_day),
            "start_anchor_id": start_anchor.anchor_id,
            "end_anchor_id": end_anchor.anchor_id if end_anchor is not None else None,
        },
        audit_action="event_rescheduled",
        reason_code="event_rescheduled",
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
        result_identity_facts={"command_receipt_id": _receipt_id("event.reschedule", command_id), "item_id": item_id, "target_version": str(target_version), "version": str(mutation.version), "current_version": str(mutation.version), "audit_id": mutation.audit_id},
    )
    return event_reschedule_response(rescheduled=True, item=_hydrated_item(context.ledger, item_id), target_version=str(target_version), audit_id=mutation.audit_id, command_receipt_id=receipt["command_receipt_id"])


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
        return _archive_response(_hydrated_item(context.ledger, item_id), False, replay["command_receipt_id"], replay["result_identity_facts"].get("audit_id"))
    item = _hydrated_item(context.ledger, item_id)
    if item["status"] == "archived":
        return _error("item.archive", "invalid_state_transition", "item is already archived", "status")
    if int(item["current_version"]) != target_version:
        return _error("item.archive", "stale_version", "target version is not current", "target_version")
    audit_id = _derived_id("item.archive", command_id, "audit", "/audit")
    archive_item(context.ledger, item_id=item_id, target_version=target_version, archived_at_utc=at, archived_by_subject_id=actor, audit_id=audit_id)
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
        result_identity_facts={"command_receipt_id": _receipt_id("item.archive", command_id), "item_id": item_id, "target_version": str(target_version), "current_version": str(target_version), "audit_id": audit_id},
    )
    return _archive_response(_hydrated_item(context.ledger, item_id), True, receipt["command_receipt_id"], audit_id)


def _handle_relation_create(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    allowed = {"command_id", "actor_subject_id", "source_item_id", "source_target_version", "target_item_id", "target_target_version", "relation_type", "created_at_utc"}
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
    _insert_audit(context.ledger, audit_id, source_id, "relation_created", actor, at, {"action": "relation_created", "relation_id": relation_id})
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
        result_identity_facts={"command_receipt_id": _receipt_id("relation.create", command_id), "relation_id": relation_id, "source_item_id": source_id, "source_target_version": str(source_version), "source_current_version": str(source["current_version"]), "target_item_id": target_id, "target_target_version": str(target_version), "target_current_version": str(target_version), "audit_id": audit_id},
    )
    return _relation_create_response(context.ledger, receipt["result_identity_facts"], created=True)


def _handle_relation_list(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    _check_fields("relation.list", request, {"item_id", "source_item_id", "target_item_id", "relation_type", "direction", "include_derived_aliases", "bounded", "limit"})
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
        "work_subject_ref",
        "recipient_kind",
        "recipient_subject_id",
        "recipient_group_id",
        "delivery_target_id",
        "channel",
        "eligible_at_utc",
        "trigger_anchor",
        "if_absent",
    }
    _check_fields("reminder.create", request, allowed)
    command_id, actor, created_at = _write_identity("reminder.create", request, "created_at_utc", context)
    item_id = _required_str(request, "item_id")
    target_version = _version(request, "target_version")
    channel = _enum(request.get("channel"), "channel", {"whatsapp"})
    eligible_at = _timestamp(request, "eligible_at_utc")
    trigger_anchor = _anchor_input(request.get("trigger_anchor") or {"anchor_kind": "instant_utc", "utc_instant": eligible_at}, "trigger_anchor", _derived_id("reminder.create", command_id, "trigger_anchor", "/trigger_anchor"))
    if_absent = bool(request.get("if_absent", False))
    semantic = _semantic_request("reminder.create", command_id, actor, created_at, request, allowed)
    replay = _compatible_replay("reminder.create", command_id, semantic, context)
    if replay is not None:
        return _reminder_response(replay["result_identity_facts"], created=False)

    route = _reminder_route(request, context, channel)
    if not route["ok"]:
        return route
    if not _has_openclaw(context):
        return _error("reminder.create", "environment_failure", "OpenClaw whatsapp binding is required", "channel")
    duplicate = _find_duplicate_reminder(
        context.ledger,
        item_id,
        eligible_at,
        channel,
        recipient_kind=str(route["recipient_kind"]),
        recipient_subject_id=route.get("recipient_subject_id"),
        recipient_group_id=route.get("recipient_group_id"),
        delivery_target_id=route.get("delivery_target_id"),
    )
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
            result_identity_facts={**duplicate, "command_receipt_id": _receipt_id("reminder.create", command_id), "target_version": str(target_version), "created": False},
        )
        return _reminder_response(receipt["result_identity_facts"], created=False)
    item = _require_item_for_write(context.ledger, "reminder.create", item_id, None, target_version)
    if duplicate is not None:
        return _error("reminder.create", "semantic_conflict", "matching active reminder already exists", "reminder")
    next_version = target_version + 1
    audit_id = _derived_id("reminder.create", command_id, "audit", "/audit")
    policy_id = _derived_id("reminder.create", command_id, "notification_policy", "/notification_policy")
    work_id = _derived_id("reminder.create", command_id, "work_instance", "/work_instance")
    with context.ledger:
        insert_temporal_anchor(context.ledger, anchor=trigger_anchor, anchor_id=trigger_anchor.anchor_id or "", default_created_at_utc=created_at)
    create_next_item_version(
        context.ledger,
        item_id=item_id,
        target_version=target_version,
        created_at_utc=created_at,
        created_by_subject_id=actor,
        audit_id=audit_id,
        audit_action="reminder_created",
        reason_code="reminder_created",
    )
    insert_notification_policy(
        context.ledger,
        item_id=item_id,
        version=next_version,
        policy=NotificationPolicyInput(
            policy_id=policy_id,
            recipient_kind=str(route["recipient_kind"]),
            recipient_subject_id=route.get("recipient_subject_id"),
            recipient_group_id=route.get("recipient_group_id"),
            channel_preference_ref=channel,
            delivery_target_id=route.get("delivery_target_id"),
            trigger_anchor_id=trigger_anchor.anchor_id,
        ),
        default_created_at_utc=created_at,
    )
    create_work_instance(
        context.ledger,
        work_instance_id=work_id,
        item_id=item_id,
        item_version=next_version,
        notification_policy_id=policy_id,
        notification_policy_item_version=next_version,
        delivery_target_id=route.get("delivery_target_id"),
        generation_source_kind="notification_policy",
        generation_source_ref=policy_id,
        work_subject_ref=str(route["work_subject_ref"]),
        policy_basis_ref=policy_id,
        eligible_at_utc=eligible_at,
        created_at_utc=created_at,
    )
    facts = {
        "command_receipt_id": _receipt_id("reminder.create", command_id),
        "item_id": item_id,
        "item_type": item["item_type"],
        "target_version": str(target_version),
        "version": str(next_version),
        "current_version": str(next_version),
        "audit_id": audit_id,
        "notification_policy_id": policy_id,
        "notification_policy_item_version": str(next_version),
        "work_instance_id": work_id,
        "trigger_anchor_id": trigger_anchor.anchor_id,
        "eligible_at_utc": eligible_at,
        "created": True,
        "predicted_delivery": _predicted_delivery(
            channel,
            str(route["work_subject_ref"]),
            eligible_at,
            delivery_target=route.get("delivery_target"),
            recipient_kind=str(route["recipient_kind"]),
            recipient_subject_id=route.get("recipient_subject_id"),
            recipient_group_id=route.get("recipient_group_id"),
        ),
    }
    receipt = _store_write_receipt(
        context,
        command="reminder.create",
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=created_at,
        effect="reminder_created",
        item_id=item_id,
        target_version=str(target_version),
        semantic_facts={**semantic, "version": str(next_version), "created": True},
        result_identity_facts=facts,
    )
    return _reminder_response(receipt["result_identity_facts"], created=True)


def _lifecycle(command: str, request: Mapping[str, Any], context: CommandContext, item_type: str, timestamp_field: str, effect_name: str, workflow: Any, terminal_status: str) -> dict[str, Any]:
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
        mutation = workflow(context.ledger, item_id=item_id, target_version=target_version, completed_at_utc=at, completed_by_subject_id=actor, completion_state=_optional_str(request, "completion_state"), audit_id=audit_id)
    elif command == "event.cancel":
        mutation = workflow(context.ledger, item_id=item_id, target_version=target_version, cancelled_at_utc=at, cancelled_by_subject_id=actor, audit_id=audit_id)
    else:
        mutation = workflow(context.ledger, item_id=item_id, target_version=target_version, cancelled_at_utc=at, cancelled_by_subject_id=actor, audit_id=audit_id)
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
        result_identity_facts={"command_receipt_id": _receipt_id(command, command_id), "item_id": item_id, "target_version": str(target_version), "version": str(mutation.version), "current_version": str(mutation.version), "audit_id": mutation.audit_id},
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
        "trigger_anchor": "anchor",
        "item_subject_role": "item_subject_role",
        "notification_policy": "notification_policy",
        "work_instance": "work_instance",
    }
    return command_derived_id(prefix=prefixes[row_role], command=command, command_id=command_id, row_role=row_role, request_path=request_path)


def _semantic_request(command: str, command_id: str, actor: str, action_timestamp: str, request: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
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
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > MAX_EXPANSION_LIMIT
    ):
        raise SpineValidationError(
            "invalid_limit",
            f"limit must be between 1 and {MAX_EXPANSION_LIMIT}",
        )
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
        "utc_instant",
        "window_start_utc",
        "window_end_utc",
        "recurrence_rule",
        "source",
    }
    for key in value:
        if key not in allowed:
            raise SpineValidationError(f"unsupported_field:{field}.{key}", f"unsupported anchor field: {key}")
    kind = _enum(value.get("anchor_kind"), f"{field}.anchor_kind", {"instant_utc", "local_instant", "local_date", "utc_window", "local_window"})
    _validate_anchor_shape(value, field, kind)
    recurrence_rule = _map_optional_str(value, "recurrence_rule")
    if recurrence_rule is not None:
        if not allow_recurrence:
            raise SpineValidationError(
                f"unsupported_field:{field}.recurrence_rule",
                f"{field}.recurrence_rule is not supported on this anchor",
            )
        if kind not in {"local_date", "local_instant"}:
            raise SpineValidationError(
                f"unsupported_field:{field}.recurrence_rule",
                f"{field}.recurrence_rule requires a local_date or local_instant anchor",
            )
        try:
            recurrence_rule = normalize_daily_recurrence_rule(recurrence_rule)
        except SpineValidationError as exc:
            raise SpineValidationError(
                f"invalid_{field}.recurrence_rule",
                exc.message,
            ) from exc
    return TemporalAnchorInput(
        anchor_id=anchor_id,
        anchor_kind=kind,
        local_date=_map_optional_str(value, "local_date"),
        local_time=_map_optional_str(value, "local_time"),
        timezone=_map_optional_str(value, "timezone"),
        utc_instant=_anchor_optional_utc(value, "utc_instant", field),
        window_start_utc=_anchor_optional_utc(value, "window_start_utc", field),
        window_end_utc=_anchor_optional_utc(value, "window_end_utc", field),
        recurrence_rule=recurrence_rule,
        source=_map_optional_str(value, "source"),
    )


def _validate_anchor_shape(value: Mapping[str, Any], field: str, kind: str) -> None:
    required_by_kind = {
        "instant_utc": {"utc_instant"},
        "local_instant": {"local_date", "local_time", "timezone"},
        "local_date": {"local_date", "timezone"},
        "utc_window": {"window_start_utc", "window_end_utc"},
        "local_window": {"local_date", "timezone"},
    }
    forbidden_by_kind = {
        "instant_utc": {"local_date", "local_time", "timezone", "window_start_utc", "window_end_utc"},
        "local_instant": {"utc_instant", "window_start_utc", "window_end_utc"},
        "local_date": {"local_time", "utc_instant", "window_start_utc", "window_end_utc"},
        "utc_window": {"local_date", "local_time", "timezone", "utc_instant"},
        "local_window": {"local_time", "utc_instant", "window_start_utc", "window_end_utc"},
    }
    for required in sorted(required_by_kind[kind]):
        if value.get(required) is None:
            raise SpineValidationError(f"missing_{field}.{required}", f"{field}.{required} is required for {kind}")
    for forbidden in sorted(forbidden_by_kind[kind]):
        if value.get(forbidden) is not None:
            raise SpineValidationError(f"unsupported_field:{field}.{forbidden}", f"{field}.{forbidden} is not valid for {kind}")
    if kind == "utc_window":
        start = _anchor_optional_utc(value, "window_start_utc", field)
        end = _anchor_optional_utc(value, "window_end_utc", field)
        if start is not None and end is not None and start > end:
            raise SpineValidationError(f"invalid_{field}.window_end_utc", f"{field}.window_end_utc must be after or equal to window_start_utc")


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
        "utc_instant": anchor.utc_instant,
        "window_start_utc": anchor.window_start_utc,
        "window_end_utc": anchor.window_end_utc,
        "recurrence_rule": anchor.recurrence_rule,
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
            "utc_instant",
            "window_start_utc",
            "window_end_utc",
            "recurrence_rule",
            "source",
        )
        if anchor.get(key) is not None
    }


def _shift_virtual_local_anchor(
    anchor: Any,
    *,
    day_offset: int,
    required: bool = True,
) -> dict[str, Any] | None:
    if not isinstance(anchor, Mapping):
        if required:
            raise SpineValidationError(
                "invalid_recurrence_anchor",
                "event end anchor must be available for recurrence expansion",
            )
        return None
    if anchor.get("anchor_kind") not in {"local_date", "local_instant"}:
        if required:
            raise SpineValidationError(
                "unsupported_recurrence_anchor",
                "recurrence expansion requires local event start/end anchors",
            )
        return None
    shifted_date = parse_local_date("anchor.local_date", str(anchor["local_date"])) + timedelta(
        days=day_offset
    )
    result = {
        "anchor_kind": anchor["anchor_kind"],
        "local_date": shifted_date.isoformat(),
        "timezone": anchor["timezone"],
    }
    if anchor.get("local_time") is not None:
        result["local_time"] = anchor["local_time"]
    return result


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
    for key in ("local_date", "local_time", "timezone", "utc_instant", "window_start_utc", "window_end_utc", "recurrence_rule", "source"):
        if row[key] is not None:
            result[key] = row[key]
    return result


def _require_item_for_write(connection: sqlite3.Connection, command: str, item_id: str, expected_type: str | None, target_version: int, *, field: str = "target_version") -> dict[str, Any]:
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


def _reminder_route(request: Mapping[str, Any], context: CommandContext, channel: str) -> dict[str, Any]:
    routed_fields = {"recipient_kind", "recipient_subject_id", "recipient_group_id", "delivery_target_id"}
    routed = any(field in request for field in routed_fields)
    if not routed:
        work_subject_ref = _required_str(request, "work_subject_ref")
        if not _subject_exists(context.ledger, work_subject_ref):
            return _error("reminder.create", "referenced_row_not_found", "work subject not found", "work_subject_ref")
        return {
            "ok": True,
            "recipient_kind": "subject",
            "recipient_subject_id": work_subject_ref,
            "recipient_group_id": None,
            "delivery_target_id": None,
            "delivery_target": None,
            "work_subject_ref": work_subject_ref,
        }
    if "work_subject_ref" in request:
        return _error("reminder.create", "invalid_request", "work_subject_ref cannot be combined with delivery target routing", "work_subject_ref")
    recipient_kind = _enum(request.get("recipient_kind"), "recipient_kind", {"subject", "subject_group"})
    recipient_subject_id = _optional_str(request, "recipient_subject_id")
    recipient_group_id = _optional_str(request, "recipient_group_id")
    delivery_target_id = _required_str(request, "delivery_target_id")
    if recipient_kind == "subject":
        if recipient_subject_id is None or recipient_group_id is not None:
            return _error("reminder.create", "invalid_request", "subject recipient requires recipient_subject_id only", "recipient_subject_id")
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
        return _error("reminder.create", "semantic_conflict", "delivery target channel does not match reminder channel", "delivery_target_id")
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


def _predicted_delivery(
    channel: str,
    work_subject_ref: str,
    eligible_at_utc: str,
    *,
    delivery_target: Mapping[str, Any] | None = None,
    recipient_kind: str = "subject",
    recipient_subject_id: Any = None,
    recipient_group_id: Any = None,
) -> dict[str, str]:
    prediction = {
        "channel": channel,
        "work_subject_ref": work_subject_ref,
        "eligible_at_utc": eligible_at_utc,
        "adapter_binding": "openclaw",
        "send_boundary": "no_external_send_from_authoring_command",
    }
    if delivery_target is not None:
        prediction["delivery_target_id"] = str(delivery_target["delivery_target_id"])
        prediction["target_ref"] = str(delivery_target["target_ref"])
        prediction["recipient_kind"] = recipient_kind
        if recipient_subject_id is not None:
            prediction["recipient_subject_id"] = str(recipient_subject_id)
        if recipient_group_id is not None:
            prediction["recipient_group_id"] = str(recipient_group_id)
    return prediction


def _find_duplicate_reminder(
    connection: sqlite3.Connection,
    item_id: str,
    eligible_at_utc: str,
    channel: str,
    *,
    recipient_kind: str,
    recipient_subject_id: Any,
    recipient_group_id: Any,
    delivery_target_id: Any,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
          p.policy_id, p.version, p.trigger_anchor_id, p.recipient_kind,
          p.recipient_subject_id, p.recipient_group_id, p.delivery_target_id,
          w.work_instance_id, w.work_subject_ref, i.item_type, i.current_version,
          dt.target_ref
        FROM notification_policies AS p
        JOIN work_instances AS w ON w.notification_policy_id = p.policy_id
        JOIN coordination_items AS i ON i.item_id = p.item_id
        LEFT JOIN delivery_targets AS dt ON dt.delivery_target_id = p.delivery_target_id
        WHERE p.item_id = ?
          AND p.recipient_kind = ?
          AND ((? IS NULL AND p.recipient_subject_id IS NULL) OR p.recipient_subject_id = ?)
          AND ((? IS NULL AND p.recipient_group_id IS NULL) OR p.recipient_group_id = ?)
          AND ((? IS NULL AND p.delivery_target_id IS NULL) OR p.delivery_target_id = ?)
          AND p.channel_preference_ref = ?
          AND p.status = 'active'
          AND w.eligible_at_utc = ?
          AND w.status = 'eligible'
        ORDER BY p.created_at_utc, p.policy_id
        LIMIT 1
        """,
        (
            item_id,
            recipient_kind,
            recipient_subject_id,
            recipient_subject_id,
            recipient_group_id,
            recipient_group_id,
            delivery_target_id,
            delivery_target_id,
            channel,
            eligible_at_utc,
        ),
    ).fetchone()
    if row is None:
        return None
    delivery_target = None
    if row["delivery_target_id"] is not None:
        delivery_target = {
            "delivery_target_id": row["delivery_target_id"],
            "target_ref": row["target_ref"],
        }
    return {
        "item_id": item_id,
        "item_type": row["item_type"],
        "version": str(row["version"]),
        "current_version": str(row["current_version"]),
        "notification_policy_id": row["policy_id"],
        "notification_policy_item_version": str(row["version"]),
        "work_instance_id": row["work_instance_id"],
        "trigger_anchor_id": row["trigger_anchor_id"],
        "eligible_at_utc": eligible_at_utc,
        "predicted_delivery": _predicted_delivery(
            channel,
            row["work_subject_ref"],
            eligible_at_utc,
            delivery_target=delivery_target,
            recipient_kind=row["recipient_kind"],
            recipient_subject_id=row["recipient_subject_id"],
            recipient_group_id=row["recipient_group_id"],
        ),
    }


def _has_openclaw(context: CommandContext) -> bool:
    binding = context.adapter_bindings.get("openclaw")
    return isinstance(binding, Mapping) and binding.get("binding_name") == "openclaw" and binding.get("channel") == "whatsapp" and binding.get("configured") is True


def _insert_audit(connection: sqlite3.Connection, audit_id: str, item_id: str, action: str, actor: str, created_at: str, payload: Mapping[str, Any]) -> None:
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
    if code == "recurrence_not_configured":
        return _error(command, "invalid_request", exc.message, "recurrence_rule")
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
