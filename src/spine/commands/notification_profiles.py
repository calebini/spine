"""Public management and resolution commands for notification profiles."""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.receipts import (
    command_derived_id,
    command_receipt,
    get_command_receipt,
    insert_command_receipt,
)
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.hashing import hash_canonical_json
from spine.core.notification_profiles import (
    DYNAMIC_CATALOG_RECEIPT_EFFECTS,
    ITEM_ARCHETYPE_CONTRACT,
    NOTIFICATION_PROFILE_BINDING_CONTRACT,
    NOTIFICATION_PROFILE_CONTRACT,
    NOTIFICATION_PROFILE_METADATA_UPDATE_CONTRACT,
    normalize_archetype_revision,
    normalize_catalog_key,
    normalize_owner,
    normalize_profile_revision,
)
from spine.ledger.common import require_utc_z
from spine.ledger.notification_profiles import (
    load_archetype,
    load_profile,
    require_owner_exists,
    resolve_default_profile,
)

PROFILE_COMMANDS = frozenset(
    {
        "item_archetype.create",
        "item_archetype.revise",
        "item_archetype.retire",
        "item_archetype.show",
        "item_archetype.list",
        "notification_profile.create",
        "notification_profile.metadata.update",
        "notification_profile.revise",
        "notification_profile.retire",
        "notification_profile.show",
        "notification_profile.list",
        "notification_profile.binding.set",
        "notification_profile.binding.remove",
        "notification_profile.binding.list",
        "notification_profile.resolve",
    }
)

_CONTRACT_BY_COMMAND = {
    **{
        command: ITEM_ARCHETYPE_CONTRACT
        for command in PROFILE_COMMANDS
        if command.startswith("item_archetype.")
    },
    **{
        command: NOTIFICATION_PROFILE_CONTRACT
        for command in PROFILE_COMMANDS
        if command.startswith("notification_profile.")
        and not command.startswith("notification_profile.binding.")
        and command != "notification_profile.resolve"
    },
    **{
        command: NOTIFICATION_PROFILE_BINDING_CONTRACT
        for command in PROFILE_COMMANDS
        if command.startswith("notification_profile.binding.")
        or command == "notification_profile.resolve"
    },
    "notification_profile.metadata.update": NOTIFICATION_PROFILE_METADATA_UPDATE_CONTRACT,
}


def handle_notification_profile_command(
    command: str,
    request: Mapping[str, Any],
    context: CommandContext,
) -> dict[str, Any]:
    """Dispatch one catalog command without widening the main command module."""

    handlers = {
        "item_archetype.create": _archetype_create,
        "item_archetype.revise": _archetype_revise,
        "item_archetype.retire": lambda value, ctx: _retire_root(
            value, ctx, kind="item_archetype"
        ),
        "item_archetype.show": lambda value, ctx: _show_root(
            value, ctx, kind="item_archetype"
        ),
        "item_archetype.list": lambda value, ctx: _list_roots(
            value, ctx, kind="item_archetype"
        ),
        "notification_profile.create": _profile_create,
        "notification_profile.metadata.update": _profile_metadata_update,
        "notification_profile.revise": _profile_revise,
        "notification_profile.retire": lambda value, ctx: _retire_root(
            value, ctx, kind="notification_profile"
        ),
        "notification_profile.show": lambda value, ctx: _show_root(
            value, ctx, kind="notification_profile"
        ),
        "notification_profile.list": lambda value, ctx: _list_roots(
            value, ctx, kind="notification_profile"
        ),
        "notification_profile.binding.set": _binding_set,
        "notification_profile.binding.remove": _binding_remove,
        "notification_profile.binding.list": _binding_list,
        "notification_profile.resolve": _resolve,
    }
    return handlers[command](request, context)


def _archetype_create(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "item_archetype.create"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "owner",
            "archetype_key",
            "revision",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    owner = _operator_owner(request)
    require_owner_exists(connection, owner)
    archetype_key = normalize_catalog_key(
        request.get("archetype_key"), "archetype_key"
    )
    revision = normalize_archetype_revision(request.get("revision"))
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    root_id = _derived(command, command_id, "item_archetype", "/")
    revision_id = _derived(
        command, command_id, "item_archetype_revision", "/revision"
    )
    facts = {
        "item_archetype_id": root_id,
        "item_archetype_revision_id": revision_id,
        "revision_number": "1",
        "archetype_key": archetype_key,
        "status": "active",
    }
    receipt = _make_receipt(
        command,
        command_id,
        actor,
        timestamp,
        "item_archetype_created",
        semantic,
        facts,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO item_archetypes (
              item_archetype_id, owner_kind, owner_subject_id, owner_group_id,
              archetype_key, status, current_revision_id, created_by_subject_id,
              created_by_command_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                root_id,
                owner["owner_kind"],
                owner["owner_subject_id"],
                owner["owner_group_id"],
                archetype_key,
                revision_id,
                actor,
                command_id,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO item_archetype_revisions (
              item_archetype_revision_id, item_archetype_id, revision_number,
              display_name, description, compatible_item_types_json,
              normalized_content_hash, created_by_subject_id,
              created_by_command_id, created_at_utc
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                root_id,
                revision["display_name"],
                revision["description"],
                canonical_json_text(revision["compatible_item_types"]),
                revision["normalized_content_hash"],
                actor,
                command_id,
                timestamp,
            ),
        )
        _insert_audit(
            connection,
            command,
            command_id,
            actor,
            timestamp,
            "item_archetype",
            root_id,
            "created",
            facts,
        )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _archetype_revise(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "item_archetype.revise"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "item_archetype_id",
            "expected_current_revision_id",
            "revision",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    root_id = _required_string(request, "item_archetype_id")
    expected = _required_string(request, "expected_current_revision_id")
    revision = normalize_archetype_revision(request.get("revision"))
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    root = load_archetype(connection, root_id, active_required=True)
    _require_operator_owned(root)
    if root["current_revision_id"] != expected:
        raise SpineValidationError(
            "stale_version:expected_current_revision_id",
            "expected_current_revision_id is not current",
        )
    next_number = int(root["revision"]["revision_number"]) + 1
    revision_id = _derived(
        command, command_id, "item_archetype_revision", "/revision"
    )
    facts = {
        "item_archetype_id": root_id,
        "item_archetype_revision_id": revision_id,
        "revision_number": str(next_number),
        "status": "active",
    }
    receipt = _make_receipt(
        command,
        command_id,
        actor,
        timestamp,
        "item_archetype_revised",
        semantic,
        facts,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO item_archetype_revisions (
              item_archetype_revision_id, item_archetype_id, revision_number,
              display_name, description, compatible_item_types_json,
              normalized_content_hash, created_by_subject_id,
              created_by_command_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                root_id,
                next_number,
                revision["display_name"],
                revision["description"],
                canonical_json_text(revision["compatible_item_types"]),
                revision["normalized_content_hash"],
                actor,
                command_id,
                timestamp,
            ),
        )
        connection.execute(
            "UPDATE item_archetypes SET current_revision_id = ? WHERE item_archetype_id = ?",
            (revision_id, root_id),
        )
        _insert_audit(
            connection,
            command,
            command_id,
            actor,
            timestamp,
            "item_archetype",
            root_id,
            "revised",
            facts,
        )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _profile_create(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.create"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "owner",
            "profile_key",
            "display_name",
            "description",
            "revision",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    owner = _operator_owner(request)
    require_owner_exists(connection, owner)
    profile_key = normalize_catalog_key(request.get("profile_key"), "profile_key")
    display_name = _required_string(request, "display_name", maximum=160)
    description = _optional_string(request, "description", maximum=2000)
    revision = normalize_profile_revision(request.get("revision"))
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    root_id = _derived(command, command_id, "notification_profile", "/")
    revision_id = _derived(
        command, command_id, "notification_profile_revision", "/revision"
    )
    facts = {
        "notification_profile_id": root_id,
        "notification_profile_revision_id": revision_id,
        "revision_number": "1",
        "profile_key": profile_key,
        "status": "active",
        "normalized_revision_hash": revision.normalized_revision_hash,
    }
    receipt = _make_receipt(
        command,
        command_id,
        actor,
        timestamp,
        "notification_profile_created",
        semantic,
        facts,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO notification_profiles (
              notification_profile_id, owner_kind, owner_subject_id, owner_group_id,
              profile_key, display_name, description, status, current_revision_id,
              created_by_subject_id, created_by_command_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                root_id,
                owner["owner_kind"],
                owner["owner_subject_id"],
                owner["owner_group_id"],
                profile_key,
                display_name,
                description,
                revision_id,
                actor,
                command_id,
                timestamp,
            ),
        )
        _insert_profile_revision(
            connection,
            command=command,
            command_id=command_id,
            actor=actor,
            timestamp=timestamp,
            profile_id=root_id,
            revision_id=revision_id,
            revision_number=1,
            revision=revision,
        )
        _insert_audit(
            connection,
            command,
            command_id,
            actor,
            timestamp,
            "notification_profile",
            root_id,
            "created",
            facts,
        )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _profile_metadata_update(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.metadata.update"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "notification_profile_id",
            "expected_metadata",
            "metadata",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    profile_id = _required_string(request, "notification_profile_id")
    expected_metadata = _normalize_profile_metadata(
        request.get("expected_metadata"), "expected_metadata"
    )
    metadata = _normalize_profile_metadata(request.get("metadata"), "metadata")
    semantic = {
        **dict(request),
        "expected_metadata": expected_metadata,
        "metadata": metadata,
    }
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    root = load_profile(connection, profile_id, active_required=True)
    _require_operator_owned(root)
    current_metadata = {
        "display_name": str(root["display_name"]),
        "description": root["description"],
    }
    if current_metadata != expected_metadata:
        raise SpineValidationError(
            "stale_version:expected_metadata",
            "expected_metadata does not match current profile metadata",
        )
    changed = current_metadata != metadata
    effect = (
        "notification_profile_metadata_updated"
        if changed
        else "notification_profile_metadata_update_noop"
    )
    facts = {
        "notification_profile_id": profile_id,
        "notification_profile_revision_id": str(root["current_revision_id"]),
        "display_name": metadata["display_name"],
        "description": metadata["description"],
        "status": "active",
    }
    receipt = _make_receipt(
        command,
        command_id,
        actor,
        timestamp,
        effect,
        semantic,
        facts,
    )
    with connection:
        if changed:
            connection.execute(
                """
                UPDATE notification_profiles
                SET display_name = ?, description = ?
                WHERE notification_profile_id = ?
                """,
                (metadata["display_name"], metadata["description"], profile_id),
            )
            _insert_audit(
                connection,
                command,
                command_id,
                actor,
                timestamp,
                "notification_profile",
                profile_id,
                "metadata_updated",
                {
                    **facts,
                    "expected_metadata": expected_metadata,
                    "metadata": metadata,
                },
            )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _profile_revise(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.revise"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "notification_profile_id",
            "expected_current_revision_id",
            "revision",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    profile_id = _required_string(request, "notification_profile_id")
    expected = _required_string(request, "expected_current_revision_id")
    revision = normalize_profile_revision(request.get("revision"))
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    root = load_profile(connection, profile_id, active_required=True)
    _require_operator_owned(root)
    if root["current_revision_id"] != expected:
        raise SpineValidationError(
            "stale_version:expected_current_revision_id",
            "expected_current_revision_id is not current",
        )
    next_number = int(root["revision"]["revision_number"]) + 1
    revision_id = _derived(
        command, command_id, "notification_profile_revision", "/revision"
    )
    facts = {
        "notification_profile_id": profile_id,
        "notification_profile_revision_id": revision_id,
        "revision_number": str(next_number),
        "status": "active",
        "normalized_revision_hash": revision.normalized_revision_hash,
    }
    receipt = _make_receipt(
        command,
        command_id,
        actor,
        timestamp,
        "notification_profile_revised",
        semantic,
        facts,
    )
    with connection:
        _insert_profile_revision(
            connection,
            command=command,
            command_id=command_id,
            actor=actor,
            timestamp=timestamp,
            profile_id=profile_id,
            revision_id=revision_id,
            revision_number=next_number,
            revision=revision,
        )
        connection.execute(
            """
            UPDATE notification_profiles
            SET current_revision_id = ?
            WHERE notification_profile_id = ?
            """,
            (revision_id, profile_id),
        )
        _insert_audit(
            connection,
            command,
            command_id,
            actor,
            timestamp,
            "notification_profile",
            profile_id,
            "revised",
            facts,
        )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _normalize_profile_metadata(value: Any, field: str) -> dict[str, Any]:
    metadata = _mapping(value, field)
    unexpected = sorted(set(metadata) - {"display_name", "description"})
    if unexpected:
        raise SpineValidationError(
            f"unsupported_field:{field}.{unexpected[0]}",
            f"unsupported field: {field}.{unexpected[0]}",
        )
    missing = sorted({"display_name", "description"} - set(metadata))
    if missing:
        raise SpineValidationError(
            f"missing_required_field:{field}.{missing[0]}",
            f"missing required field: {field}.{missing[0]}",
        )
    display_name = metadata.get("display_name")
    if not isinstance(display_name, str) or not 1 <= len(display_name) <= 160:
        raise SpineValidationError(
            f"invalid_request:{field}.display_name",
            f"{field}.display_name must be a non-empty string up to 160 characters",
        )
    description = metadata.get("description")
    if description is not None and (
        not isinstance(description, str) or not 1 <= len(description) <= 2000
    ):
        raise SpineValidationError(
            f"invalid_request:{field}.description",
            f"{field}.description must be null or a non-empty string up to 2000 characters",
        )
    return {"display_name": display_name, "description": description}


def _insert_profile_revision(
    connection: sqlite3.Connection,
    *,
    command: str,
    command_id: str,
    actor: str,
    timestamp: str,
    profile_id: str,
    revision_id: str,
    revision_number: int,
    revision: Any,
) -> None:
    connection.execute(
        """
        INSERT INTO notification_profile_revisions (
          notification_profile_revision_id, notification_profile_id,
          revision_number, compatible_item_types_json,
          normalized_revision_hash, created_by_subject_id,
          created_by_command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            profile_id,
            revision_number,
            canonical_json_text(list(revision.compatible_item_types)),
            revision.normalized_revision_hash,
            actor,
            command_id,
            timestamp,
        ),
    )
    for index, template in enumerate(revision.templates):
        template_id = _derived(
            command,
            command_id,
            "notification_profile_template",
            f"/revision/templates/{index}",
        )
        connection.execute(
            """
            INSERT INTO notification_profile_templates (
              notification_profile_template_id, notification_profile_revision_id,
              template_key, template_index, schedule_json, late_handling_json,
              normalized_template_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                template_id,
                revision_id,
                template["template_key"],
                index,
                canonical_json_text(template["schedule"]),
                canonical_json_text(template["late_handling"]),
                template["normalized_template_hash"],
            ),
        )


def _retire_root(
    request: Mapping[str, Any],
    context: CommandContext,
    *,
    kind: str,
) -> dict[str, Any]:
    command = f"{kind}.retire"
    id_field = f"{kind}_id"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            id_field,
            "reason_code",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    root_id = _required_string(request, id_field)
    reason = _required_string(request, "reason_code")
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    table = "item_archetypes" if kind == "item_archetype" else "notification_profiles"
    row = connection.execute(
        f"SELECT owner_kind, status FROM {table} WHERE {id_field} = ?",
        (root_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError(
            f"referenced_row_not_found:{id_field}", f"{id_field} was not found"
        )
    _require_operator_owned(row)
    changed = row["status"] == "active"
    effect = f"{kind}_retired" if changed else f"{kind}_retire_noop"
    facts = {id_field: root_id, "status": "retired", "reason_code": reason}
    receipt = _make_receipt(
        command, command_id, actor, timestamp, effect, semantic, facts
    )
    with connection:
        if changed:
            connection.execute(
                f"""
                UPDATE {table}
                SET status = 'retired', retired_by_subject_id = ?,
                    retired_by_command_id = ?, retired_at_utc = ?,
                    retirement_reason = ?
                WHERE {id_field} = ?
                """,
                (actor, command_id, timestamp, reason, root_id),
            )
            _insert_audit(
                connection,
                command,
                command_id,
                actor,
                timestamp,
                kind,
                root_id,
                "retired",
                facts,
            )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _show_root(
    request: Mapping[str, Any],
    context: CommandContext,
    *,
    kind: str,
) -> dict[str, Any]:
    command = f"{kind}.show"
    id_field = f"{kind}_id"
    revision_field = f"{kind}_revision_id"
    _check(command, request, {"contract_version", id_field, revision_field})
    _require_contract(command, request)
    root_id = _required_string(request, id_field)
    revision_id = _optional_string(request, revision_field)
    loader = load_archetype if kind == "item_archetype" else load_profile
    entry = loader(_connection(context), root_id, revision_id=revision_id)
    return {
        "ok": True,
        "command": command,
        "response_contract": _CONTRACT_BY_COMMAND[command],
        kind: entry,
    }


def _list_roots(
    request: Mapping[str, Any],
    context: CommandContext,
    *,
    kind: str,
) -> dict[str, Any]:
    command = f"{kind}.list"
    _check(
        command,
        request,
        {"contract_version", "owner", "status", "limit", "cursor"},
    )
    _require_contract(command, request)
    owner = normalize_owner(request.get("owner"))
    status = _optional_string(request, "status")
    if status is not None and status not in {"active", "retired"}:
        raise SpineValidationError(
            "invalid_request:status", "status must be active or retired"
        )
    limit = _limit(request.get("limit"))
    connection = _connection(context)
    require_owner_exists(connection, owner)
    table = "item_archetypes" if kind == "item_archetype" else "notification_profiles"
    id_field = f"{kind}_id"
    key_field = "archetype_key" if kind == "item_archetype" else "profile_key"
    metadata_columns = (
        ", display_name, description" if kind == "notification_profile" else ""
    )
    query = (
        f"SELECT {id_field}, {key_field}, status, current_revision_id{metadata_columns} "
        f"FROM {table} "
        "WHERE owner_kind = ? AND owner_subject_id IS ? AND owner_group_id IS ?"
    )
    params: list[Any] = [
        owner["owner_kind"],
        owner["owner_subject_id"],
        owner["owner_group_id"],
    ]
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += f" ORDER BY {key_field}, {id_field}"
    rows = connection.execute(query, tuple(params)).fetchall()
    snapshot_facts: list[dict[str, Any]] = []
    for row in rows:
        facts: dict[str, Any] = {
            "id": str(row[id_field]),
            "key": str(row[key_field]),
            "status": str(row["status"]),
            "current_revision_id": str(row["current_revision_id"]),
        }
        if kind == "notification_profile":
            facts["display_name"] = str(row["display_name"])
            facts["description"] = row["description"]
        snapshot_facts.append(facts)
    snapshot_hash = hash_canonical_json(snapshot_facts)
    query_facts = {
        "kind": kind,
        "owner": owner,
        "status": status,
        "limit": str(limit),
    }
    last: tuple[str, str] | None = None
    if request.get("cursor") is not None:
        cursor = _decode_catalog_cursor(str(request["cursor"]))
        if cursor.get("query") != query_facts:
            raise SpineValidationError(
                "invalid_request:cursor", "cursor query facts do not match"
            )
        if cursor.get("snapshot_hash") != snapshot_hash:
            raise SpineValidationError(
                "stale_cursor:cursor", "catalog changed"
            )
        raw_last = cursor.get("last")
        if (
            not isinstance(raw_last, list)
            or len(raw_last) != 2
            or not all(isinstance(value, str) for value in raw_last)
        ):
            raise SpineValidationError(
                "invalid_request:cursor", "cursor ordering tuple is invalid"
            )
        last = (raw_last[0], raw_last[1])
    if last is not None:
        rows = [
            row
            for row in rows
            if (str(row[key_field]), str(row[id_field])) > last
        ]
    has_more = len(rows) > limit
    page = rows[:limit]
    loader = load_archetype if kind == "item_archetype" else load_profile
    entries = [
        loader(connection, str(row[id_field]))
        for row in page
    ]
    next_cursor = None
    if has_more and page:
        final = page[-1]
        next_cursor = _encode_catalog_cursor(
            {
                "cursor_version": "spine.notification-profile-catalog-cursor.v1",
                "query": query_facts,
                "snapshot_hash": snapshot_hash,
                "last": [
                    str(final[key_field]),
                    str(final[id_field]),
                ],
            }
        )
    return {
        "ok": True,
        "command": command,
        "response_contract": _CONTRACT_BY_COMMAND[command],
        "entries": entries,
        "count": str(len(entries)),
        "catalog_snapshot_hash": snapshot_hash,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _binding_set(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.binding.set"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "owner",
            "item_archetype_id",
            "notification_profile_id",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    owner = _operator_owner(request)
    require_owner_exists(connection, owner)
    archetype_id = _required_string(request, "item_archetype_id")
    profile_id = _required_string(request, "notification_profile_id")
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    archetype = load_archetype(connection, archetype_id, active_required=True)
    profile = load_profile(connection, profile_id, active_required=True)
    overlap = set(archetype["revision"]["compatible_item_types"]) & set(
        profile["revision"]["compatible_item_types"]
    )
    if not overlap:
        raise SpineValidationError(
            "semantic_conflict:notification_profile_id",
            "profile and archetype have no compatible item type",
        )
    current = connection.execute(
        """
        SELECT * FROM notification_profile_bindings
        WHERE owner_kind = ? AND owner_subject_id IS ? AND owner_group_id IS ?
          AND item_archetype_id = ? AND status = 'active'
        """,
        (
            owner["owner_kind"],
            owner["owner_subject_id"],
            owner["owner_group_id"],
            archetype_id,
        ),
    ).fetchone()
    if current is not None and current["notification_profile_id"] == profile_id:
        binding_id = str(current["notification_profile_binding_id"])
        effect = "notification_profile_binding_set_noop"
        changed = False
    else:
        binding_id = _derived(
            command, command_id, "notification_profile_binding", "/"
        )
        effect = "notification_profile_binding_set"
        changed = True
    facts = {
        "notification_profile_binding_id": binding_id,
        "item_archetype_id": archetype_id,
        "notification_profile_id": profile_id,
        "status": "active",
        "compatible_item_types": sorted(overlap),
    }
    receipt = _make_receipt(
        command, command_id, actor, timestamp, effect, semantic, facts
    )
    with connection:
        if changed:
            if current is not None:
                connection.execute(
                    """
                    UPDATE notification_profile_bindings
                    SET status = 'retired', retired_by_subject_id = ?,
                        retired_by_command_id = ?, retired_at_utc = ?
                    WHERE notification_profile_binding_id = ?
                    """,
                    (
                        actor,
                        command_id,
                        timestamp,
                        current["notification_profile_binding_id"],
                    ),
                )
            connection.execute(
                """
                INSERT INTO notification_profile_bindings (
                  notification_profile_binding_id, owner_kind,
                  owner_subject_id, owner_group_id, item_archetype_id,
                  notification_profile_id, status, created_by_subject_id,
                  created_by_command_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    binding_id,
                    owner["owner_kind"],
                    owner["owner_subject_id"],
                    owner["owner_group_id"],
                    archetype_id,
                    profile_id,
                    actor,
                    command_id,
                    timestamp,
                ),
            )
            _insert_audit(
                connection,
                command,
                command_id,
                actor,
                timestamp,
                "notification_profile_binding",
                binding_id,
                "set",
                facts,
            )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _binding_remove(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.binding.remove"
    _check(
        command,
        request,
        {
            "contract_version",
            "command_id",
            "actor_subject_id",
            "action_timestamp_utc",
            "notification_profile_binding_id",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    command_id, actor, timestamp = _write_identity(request, context)
    binding_id = _required_string(request, "notification_profile_binding_id")
    semantic = dict(request)
    replay = _compatible_replay(connection, command, command_id, semantic)
    if replay is not None:
        return _success(command, replay)
    row = connection.execute(
        """
        SELECT * FROM notification_profile_bindings
        WHERE notification_profile_binding_id = ?
        """,
        (binding_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError(
            "referenced_row_not_found:notification_profile_binding_id",
            "notification profile binding was not found",
        )
    _require_operator_owned(row)
    changed = row["status"] == "active"
    effect = (
        "notification_profile_binding_removed"
        if changed
        else "notification_profile_binding_remove_noop"
    )
    facts = {
        "notification_profile_binding_id": binding_id,
        "status": "retired",
    }
    receipt = _make_receipt(
        command, command_id, actor, timestamp, effect, semantic, facts
    )
    with connection:
        if changed:
            connection.execute(
                """
                UPDATE notification_profile_bindings
                SET status = 'retired', retired_by_subject_id = ?,
                    retired_by_command_id = ?, retired_at_utc = ?
                WHERE notification_profile_binding_id = ?
                """,
                (actor, command_id, timestamp, binding_id),
            )
            _insert_audit(
                connection,
                command,
                command_id,
                actor,
                timestamp,
                "notification_profile_binding",
                binding_id,
                "removed",
                facts,
            )
        insert_command_receipt(connection, receipt)
    return _success(command, receipt)


def _binding_list(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    command = "notification_profile.binding.list"
    _check(
        command,
        request,
        {
            "contract_version",
            "owner",
            "item_archetype_id",
            "status",
            "limit",
            "cursor",
        },
    )
    _require_contract(command, request)
    connection = _connection(context)
    owner = normalize_owner(request.get("owner"))
    require_owner_exists(connection, owner)
    archetype_id = _optional_string(request, "item_archetype_id")
    status = _optional_string(request, "status")
    if status is not None and status not in {"active", "retired"}:
        raise SpineValidationError(
            "invalid_request:status", "status must be active or retired"
        )
    limit = _limit(request.get("limit"))
    query = (
        "SELECT * FROM notification_profile_bindings "
        "WHERE owner_kind = ? AND owner_subject_id IS ? AND owner_group_id IS ?"
    )
    params: list[Any] = [
        owner["owner_kind"],
        owner["owner_subject_id"],
        owner["owner_group_id"],
    ]
    if archetype_id is not None:
        query += " AND item_archetype_id = ?"
        params.append(archetype_id)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY item_archetype_id, notification_profile_binding_id"
    rows = connection.execute(query, tuple(params)).fetchall()
    snapshot_hash = hash_canonical_json(
        [
            {
                "notification_profile_binding_id": str(
                    row["notification_profile_binding_id"]
                ),
                "item_archetype_id": str(row["item_archetype_id"]),
                "notification_profile_id": str(
                    row["notification_profile_id"]
                ),
                "status": str(row["status"]),
            }
            for row in rows
        ]
    )
    query_facts = {
        "owner": owner,
        "item_archetype_id": archetype_id,
        "status": status,
        "limit": str(limit),
    }
    last: tuple[str, str] | None = None
    if request.get("cursor") is not None:
        cursor = _decode_catalog_cursor(str(request["cursor"]))
        if cursor.get("query") != query_facts:
            raise SpineValidationError(
                "invalid_request:cursor", "cursor query facts do not match"
            )
        if cursor.get("snapshot_hash") != snapshot_hash:
            raise SpineValidationError(
                "stale_cursor:cursor", "binding catalog changed"
            )
        raw_last = cursor.get("last")
        if (
            not isinstance(raw_last, list)
            or len(raw_last) != 2
            or not all(isinstance(value, str) for value in raw_last)
        ):
            raise SpineValidationError(
                "invalid_request:cursor", "cursor ordering tuple is invalid"
            )
        last = (raw_last[0], raw_last[1])
    if last is not None:
        rows = [
            row
            for row in rows
            if (
                str(row["item_archetype_id"]),
                str(row["notification_profile_binding_id"]),
            )
            > last
        ]
    has_more = len(rows) > limit
    page = rows[:limit]
    entries = [dict(row) for row in page]
    next_cursor = None
    if has_more and page:
        final = page[-1]
        next_cursor = _encode_catalog_cursor(
            {
                "cursor_version": "spine.notification-profile-catalog-cursor.v1",
                "query": query_facts,
                "snapshot_hash": snapshot_hash,
                "last": [
                    str(final["item_archetype_id"]),
                    str(final["notification_profile_binding_id"]),
                ],
            }
        )
    return {
        "ok": True,
        "command": command,
        "response_contract": _CONTRACT_BY_COMMAND[command],
        "entries": entries,
        "count": str(len(entries)),
        "catalog_snapshot_hash": snapshot_hash,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _resolve(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    command = "notification_profile.resolve"
    _check(
        command,
        request,
        {
            "contract_version",
            "item_type",
            "item_archetype_id",
            "scope_chain",
        },
    )
    _require_contract(command, request)
    item_type = _required_string(request, "item_type")
    if item_type not in {"event", "task"}:
        raise SpineValidationError(
            "invalid_request:item_type", "item_type must be event or task"
        )
    archetype_id = _required_string(request, "item_archetype_id")
    scope_chain = _normalize_scope_chain(request.get("scope_chain"))
    connection = _connection(context)
    for owner in scope_chain:
        require_owner_exists(connection, owner)
    result = resolve_default_profile(
        connection,
        item_archetype_id=archetype_id,
        item_type=item_type,
        scope_chain=scope_chain,
    )
    if result is None:
        return {
            "ok": True,
            "command": command,
            "response_contract": _CONTRACT_BY_COMMAND[command],
            "effect": "no_matching_profile",
            "scope_chain": list(scope_chain),
        }
    return {
        "ok": True,
        "command": command,
        "response_contract": _CONTRACT_BY_COMMAND[command],
        "effect": "notification_profile_resolved",
        "scope_chain": list(scope_chain),
        "matched_scope": result["scope"],
        "binding": result["binding"],
        "profile": result["profile"],
    }


def _insert_audit(
    connection: sqlite3.Connection,
    command: str,
    command_id: str,
    actor: str,
    timestamp: str,
    resource_kind: str,
    resource_id: str,
    action: str,
    payload: Mapping[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO coordination_catalog_audit_log (
          catalog_audit_id, resource_kind, resource_id, action,
          reason_code, actor_subject_id, command_id, payload_json,
          payload_hash, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _derived(command, command_id, "catalog_audit", "/audit"),
            resource_kind,
            resource_id,
            action,
            action,
            actor,
            command_id,
            canonical_json_text(dict(payload)),
            hash_canonical_json(dict(payload)),
            timestamp,
        ),
    )


def _make_receipt(
    command: str,
    command_id: str,
    actor: str,
    timestamp: str,
    effect: str,
    semantic: Mapping[str, Any],
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    if effect not in DYNAMIC_CATALOG_RECEIPT_EFFECTS:
        raise RuntimeError(f"unregistered dynamic-catalog receipt effect: {effect}")
    return command_receipt(
        command=command,
        command_id=command_id,
        actor_subject_id=actor,
        action_timestamp_utc=timestamp,
        effect=effect,
        semantic_facts=semantic,
        result_identity_facts=facts,
    )


def _success(command: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "response_contract": _CONTRACT_BY_COMMAND[command],
        "effect": receipt["effect"],
        **dict(_mapping(receipt["result_identity_facts"], "result_identity_facts")),
        "receipt": {
            "command_receipt_id": receipt["command_receipt_id"],
            "command_id": receipt["command_id"],
            "effect": receipt["effect"],
            "semantic_facts_hash": receipt["semantic_facts_hash"],
            "created_at_utc": receipt["created_at_utc"],
        },
    }


def _compatible_replay(
    connection: sqlite3.Connection,
    command: str,
    command_id: str,
    semantic: Mapping[str, Any],
) -> dict[str, Any] | None:
    receipt = get_command_receipt(connection, command_id)
    if receipt is None:
        return None
    if receipt["command"] != command:
        raise SpineValidationError(
            "semantic_conflict:command_id",
            "command_id is already committed for another command",
        )
    if receipt["semantic_facts_hash"] != hash_canonical_json(dict(semantic)):
        raise SpineValidationError(
            "semantic_conflict:command_id",
            "command_id replay differs from the committed request",
        )
    return receipt


def _write_identity(
    request: Mapping[str, Any], context: CommandContext
) -> tuple[str, str, str]:
    connection = _connection(context)
    command_id = _required_string(request, "command_id")
    actor = _required_string(request, "actor_subject_id")
    timestamp = _required_string(request, "action_timestamp_utc")
    require_utc_z("action_timestamp_utc", timestamp)
    require_owner_exists(
        connection,
        {
            "owner_kind": "subject",
            "owner_subject_id": actor,
            "owner_group_id": None,
        },
    )
    return command_id, actor, timestamp


def _operator_owner(request: Mapping[str, Any]) -> dict[str, str | None]:
    owner = normalize_owner(request.get("owner"))
    if owner["owner_kind"] == "system":
        raise SpineValidationError(
            "semantic_conflict:owner.owner_kind",
            "ordinary operator commands cannot mutate system-owned catalog entries",
        )
    return owner


def _require_operator_owned(row: Mapping[str, Any]) -> None:
    if row["owner_kind"] == "system":
        raise SpineValidationError(
            "semantic_conflict:owner_kind",
            "system-owned catalog entries are read-only",
        )


def _normalize_scope_chain(value: Any) -> tuple[dict[str, str | None], ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 1 <= len(value) <= 8
    ):
        raise SpineValidationError(
            "invalid_request:scope_chain",
            "scope_chain must contain one through eight exact owners",
        )
    owners = tuple(
        normalize_owner(entry, f"scope_chain[{index}]")
        for index, entry in enumerate(value)
    )
    keys = [
        (
            owner["owner_kind"],
            owner["owner_subject_id"],
            owner["owner_group_id"],
        )
        for owner in owners
    ]
    if len(keys) != len(set(keys)):
        raise SpineValidationError(
            "semantic_conflict:scope_chain", "scope_chain owners must be unique"
        )
    return owners


def _require_contract(command: str, request: Mapping[str, Any]) -> None:
    actual = _required_string(request, "contract_version")
    expected = _CONTRACT_BY_COMMAND[command]
    if actual != expected:
        raise SpineValidationError(
            "unsupported_contract_version:contract_version",
            f"expected {expected}",
        )


def _check(
    command: str, request: Mapping[str, Any], allowed: set[str]
) -> None:
    unknown = sorted(set(request) - allowed)
    if unknown:
        raise SpineValidationError(
            f"unsupported_field:{unknown[0]}",
            f"{command} does not accept field {unknown[0]}",
        )


def _required_string(
    request: Mapping[str, Any], field: str, *, maximum: int = 512
) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise SpineValidationError(
            f"invalid_request:{field}",
            f"{field} must be a non-empty string up to {maximum} characters",
        )
    return value


def _optional_string(
    request: Mapping[str, Any], field: str, *, maximum: int = 512
) -> str | None:
    value = request.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise SpineValidationError(
            f"invalid_request:{field}",
            f"{field} must be a non-empty string up to {maximum} characters",
        )
    return value


def _limit(value: Any) -> int:
    if not isinstance(value, str) or not value.isdecimal():
        raise SpineValidationError(
            "invalid_request:limit", "limit must be a decimal string"
        )
    limit = int(value)
    if not 1 <= limit <= 500:
        raise SpineValidationError(
            "limit_exceeded:limit", "limit must be between 1 and 500"
        )
    return limit


def _encode_catalog_cursor(payload: Mapping[str, object]) -> str:
    raw = canonical_json_bytes(payload)
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{encoded}.{hash_canonical_json(payload)}"


def _decode_catalog_cursor(value: str) -> dict[str, object]:
    try:
        encoded, digest = value.split(".", 1)
        raw = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        )
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpineValidationError(
            "invalid_request:cursor", "cursor is malformed"
        ) from exc
    if (
        not isinstance(payload, dict)
        or canonical_json_bytes(payload) != raw
        or hash_canonical_json(payload) != digest
        or payload.get("cursor_version")
        != "spine.notification-profile-catalog-cursor.v1"
    ):
        raise SpineValidationError(
            "invalid_request:cursor", "cursor does not verify"
        )
    return payload


def _derived(
    command: str, command_id: str, row_role: str, request_path: str
) -> str:
    return command_derived_id(
        prefix=row_role,
        command=command,
        command_id=command_id,
        row_role=row_role,
        request_path=request_path,
    )


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(
            f"invalid_request:{field}", f"{field} must be an object"
        )
    return value


def _connection(context: CommandContext) -> sqlite3.Connection:
    if context.ledger is None:
        raise SpineValidationError(
            "runtime_context_missing:ledger", "a ledger connection is required"
        )
    return context.ledger
