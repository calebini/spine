"""SQLite persistence helpers for item archetypes and notification profiles."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.commands.receipts import command_derived_id
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_text
from spine.ledger.common import copy_id


def require_owner_exists(connection: sqlite3.Connection, owner: Mapping[str, object]) -> None:
    kind = str(owner["owner_kind"])
    if kind == "system":
        return
    table = "subjects" if kind == "subject" else "subject_groups"
    key = "subject_id" if kind == "subject" else "group_id"
    value = owner["owner_subject_id"] if kind == "subject" else owner["owner_group_id"]
    row = connection.execute(f"SELECT status FROM {table} WHERE {key} = ?", (value,)).fetchone()
    if row is None:
        raise SpineValidationError(f"referenced_row_not_found:owner.{key}", f"owner {key} not found")
    if row["status"] != "active":
        raise SpineValidationError(f"semantic_conflict:owner.{key}", f"owner {key} is inactive")


def load_archetype(
    connection: sqlite3.Connection,
    item_archetype_id: str,
    *,
    revision_id: str | None = None,
    active_required: bool = False,
) -> dict[str, Any]:
    root = connection.execute(
        "SELECT * FROM item_archetypes WHERE item_archetype_id = ?",
        (item_archetype_id,),
    ).fetchone()
    if root is None:
        raise SpineValidationError("referenced_row_not_found:item_archetype_id", "item archetype not found")
    if active_required and root["status"] != "active":
        raise SpineValidationError("semantic_conflict:item_archetype_id", "item archetype is retired")
    selected = revision_id or str(root["current_revision_id"])
    revision = connection.execute(
        """
        SELECT * FROM item_archetype_revisions
        WHERE item_archetype_revision_id = ? AND item_archetype_id = ?
        """,
        (selected, item_archetype_id),
    ).fetchone()
    if revision is None:
        raise SpineValidationError(
            "referenced_row_not_found:item_archetype_revision_id",
            "item archetype revision not found",
        )
    result = dict(root)
    result["revision"] = dict(revision)
    result["revision"]["compatible_item_types"] = json.loads(
        str(result["revision"].pop("compatible_item_types_json"))
    )
    return result


def load_profile(
    connection: sqlite3.Connection,
    notification_profile_id: str,
    *,
    revision_id: str | None = None,
    active_required: bool = False,
) -> dict[str, Any]:
    root = connection.execute(
        "SELECT * FROM notification_profiles WHERE notification_profile_id = ?",
        (notification_profile_id,),
    ).fetchone()
    if root is None:
        raise SpineValidationError(
            "referenced_row_not_found:notification_profile_id",
            "notification profile not found",
        )
    if active_required and root["status"] != "active":
        raise SpineValidationError("semantic_conflict:notification_profile_id", "notification profile is retired")
    selected = revision_id or str(root["current_revision_id"])
    revision = connection.execute(
        """
        SELECT * FROM notification_profile_revisions
        WHERE notification_profile_revision_id = ? AND notification_profile_id = ?
        """,
        (selected, notification_profile_id),
    ).fetchone()
    if revision is None:
        raise SpineValidationError(
            "referenced_row_not_found:notification_profile_revision_id",
            "notification profile revision not found",
        )
    template_rows = connection.execute(
        """
        SELECT * FROM notification_profile_templates
        WHERE notification_profile_revision_id = ? ORDER BY template_index
        """,
        (selected,),
    ).fetchall()
    result = dict(root)
    result["revision"] = dict(revision)
    result["revision"]["compatible_item_types"] = json.loads(
        str(result["revision"].pop("compatible_item_types_json"))
    )
    templates: list[dict[str, Any]] = []
    for row in template_rows:
        template = dict(row)
        template["schedule"] = json.loads(str(template.pop("schedule_json")))
        template["late_handling"] = json.loads(str(template.pop("late_handling_json")))
        templates.append(template)
    result["revision"]["templates"] = templates
    return result


def resolve_default_profile(
    connection: sqlite3.Connection,
    *,
    item_archetype_id: str,
    item_type: str,
    scope_chain: Sequence[Mapping[str, object]],
) -> dict[str, Any] | None:
    archetype = load_archetype(connection, item_archetype_id, active_required=True)
    if item_type not in archetype["revision"]["compatible_item_types"]:
        raise SpineValidationError(
            "semantic_conflict:item_archetype_id",
            "item archetype is incompatible with item type",
        )
    for scope in scope_chain:
        row = connection.execute(
            """
            SELECT * FROM notification_profile_bindings
            WHERE owner_kind = ? AND owner_subject_id IS ? AND owner_group_id IS ?
              AND item_archetype_id = ? AND status = 'active'
            """,
            (
                scope["owner_kind"],
                scope.get("owner_subject_id"),
                scope.get("owner_group_id"),
                item_archetype_id,
            ),
        ).fetchone()
        if row is None:
            continue
        profile = load_profile(connection, str(row["notification_profile_id"]), active_required=True)
        if item_type not in profile["revision"]["compatible_item_types"]:
            raise SpineValidationError(
                "semantic_conflict:notification_profile_binding_id",
                "bound profile is incompatible with item type",
            )
        return {"binding": dict(row), "profile": profile, "scope": dict(scope)}
    return None


def current_assignment(connection: sqlite3.Connection, *, item_id: str, item_version: int) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM item_archetype_assignments WHERE item_id = ? AND item_version = ?",
        (item_id, item_version),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["archetype"] = load_archetype(
        connection,
        str(row["item_archetype_id"]),
        revision_id=str(row["item_archetype_revision_id"]),
    )
    return result


def current_application(connection: sqlite3.Connection, *, item_id: str, item_version: int) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM notification_profile_applications WHERE item_id = ? AND item_version = ?",
        (item_id, item_version),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for field in (
        "scope_chain_json",
        "suppress_template_keys_json",
        "replacements_json",
        "additions_json",
    ):
        result[field.removesuffix("_json")] = json.loads(str(result.pop(field)))
    result["profile"] = load_profile(
        connection,
        str(row["notification_profile_id"]),
        revision_id=str(row["notification_profile_revision_id"]),
    )
    policies = connection.execute(
        """
        SELECT * FROM notification_profile_application_policies
        WHERE notification_profile_application_id = ?
        ORDER BY policy_origin, source_key
        """,
        (row["notification_profile_application_id"],),
    ).fetchall()
    result["policies"] = [dict(value) for value in policies]
    return result


def insert_assignment(
    connection: sqlite3.Connection,
    *,
    assignment_id: str,
    item_id: str,
    item_version: int,
    archetype: Mapping[str, Any],
    selection_source: str,
    source_ref: str | None,
    actor_subject_id: str,
    command_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO item_archetype_assignments (
          item_archetype_assignment_id, item_id, item_version, item_archetype_id,
          item_archetype_revision_id, selection_source, source_ref,
          created_by_subject_id, created_by_command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assignment_id,
            item_id,
            item_version,
            archetype["item_archetype_id"],
            archetype["revision"]["item_archetype_revision_id"],
            selection_source,
            source_ref,
            actor_subject_id,
            command_id,
            created_at_utc,
        ),
    )
    return {
        "item_archetype_assignment_id": assignment_id,
        "item_archetype_id": archetype["item_archetype_id"],
        "item_archetype_revision_id": archetype["revision"]["item_archetype_revision_id"],
        "archetype_key": archetype["archetype_key"],
        "selection_source": selection_source,
    }


def insert_application(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    item_id: str,
    item_version: int,
    profile: Mapping[str, Any],
    selection_mode: str,
    scope_chain: Sequence[Mapping[str, object]],
    assignment_id: str | None,
    binding_id: str | None,
    suppress_template_keys: Sequence[str],
    replacements: Sequence[Mapping[str, object]],
    additions: Sequence[Mapping[str, object]],
    effective_hash: str,
    origins: Sequence[Mapping[str, object]],
    policies: Sequence[tuple[str, Mapping[str, object]]],
    actor_subject_id: str,
    command_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO notification_profile_applications (
          notification_profile_application_id, item_id, item_version,
          notification_profile_id, notification_profile_revision_id, selection_mode,
          scope_chain_json, item_archetype_assignment_id, notification_profile_binding_id,
          suppress_template_keys_json, replacements_json, additions_json,
          normalized_effective_policy_set_hash, created_by_subject_id,
          created_by_command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            item_id,
            item_version,
            profile["notification_profile_id"],
            profile["revision"]["notification_profile_revision_id"],
            selection_mode,
            canonical_json_text(list(scope_chain)),
            assignment_id,
            binding_id,
            canonical_json_text(list(suppress_template_keys)),
            canonical_json_text(list(replacements)),
            canonical_json_text(list(additions)),
            effective_hash,
            actor_subject_id,
            command_id,
            created_at_utc,
        ),
    )
    policy_by_key = {key: policy for key, policy in policies}
    template_by_key = {str(value["template_key"]): value for value in profile["revision"]["templates"]}
    mappings: list[dict[str, Any]] = []
    for index, origin in enumerate(origins):
        policy = policy_by_key[str(origin["policy_key"])]
        template = template_by_key.get(str(origin["source_key"]))
        mapping_id = command_derived_id(
            prefix="notification_profile_application_policy",
            command="schedule.create",
            command_id=command_id,
            row_role="notification_profile_application_policy",
            request_path=f"/notification_plan/effective/{index}",
        )
        connection.execute(
            """
            INSERT INTO notification_profile_application_policies (
              notification_profile_application_policy_id, notification_profile_application_id,
              policy_origin, source_key, notification_profile_template_id,
              notification_intent_id, notification_policy_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping_id,
                application_id,
                origin["policy_origin"],
                origin["source_key"],
                template["notification_profile_template_id"] if template is not None else None,
                policy["notification_intent_id"],
                policy["notification_policy_id"],
            ),
        )
        mappings.append(
            {
                "policy_origin": origin["policy_origin"],
                "source_key": origin["source_key"],
                "notification_intent_id": policy["notification_intent_id"],
                "notification_policy_id": policy["notification_policy_id"],
            }
        )
    return {
        "notification_profile_application_id": application_id,
        "notification_profile_id": profile["notification_profile_id"],
        "notification_profile_revision_id": profile["revision"]["notification_profile_revision_id"],
        "selection_mode": selection_mode,
        "notification_profile_binding_id": binding_id,
        "normalized_effective_policy_set_hash": effective_hash,
        "policies": mappings,
    }


def copy_forward_profile_facts(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    previous_version: int,
    next_version: int,
    created_at_utc: str,
    created_by_command_id: str,
) -> None:
    assignment = connection.execute(
        "SELECT * FROM item_archetype_assignments WHERE item_id = ? AND item_version = ?",
        (item_id, previous_version),
    ).fetchone()
    new_assignment_id: str | None = None
    if assignment is not None:
        new_assignment_id = copy_id(str(assignment["item_archetype_assignment_id"]), next_version)
        connection.execute(
            """
            INSERT INTO item_archetype_assignments (
              item_archetype_assignment_id, item_id, item_version, item_archetype_id,
              item_archetype_revision_id, selection_source, source_ref,
              created_by_subject_id, created_by_command_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_assignment_id,
                item_id,
                next_version,
                assignment["item_archetype_id"],
                assignment["item_archetype_revision_id"],
                assignment["selection_source"],
                assignment["source_ref"],
                assignment["created_by_subject_id"],
                created_by_command_id,
                created_at_utc,
            ),
        )
    application = connection.execute(
        "SELECT * FROM notification_profile_applications WHERE item_id = ? AND item_version = ?",
        (item_id, previous_version),
    ).fetchone()
    if application is None:
        return
    new_application_id = copy_id(str(application["notification_profile_application_id"]), next_version)
    connection.execute(
        """
        INSERT INTO notification_profile_applications (
          notification_profile_application_id, item_id, item_version,
          notification_profile_id, notification_profile_revision_id, selection_mode,
          scope_chain_json, item_archetype_assignment_id, notification_profile_binding_id,
          suppress_template_keys_json, replacements_json, additions_json,
          normalized_effective_policy_set_hash, created_by_subject_id,
          created_by_command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_application_id,
            item_id,
            next_version,
            application["notification_profile_id"],
            application["notification_profile_revision_id"],
            application["selection_mode"],
            application["scope_chain_json"],
            new_assignment_id,
            application["notification_profile_binding_id"],
            application["suppress_template_keys_json"],
            application["replacements_json"],
            application["additions_json"],
            application["normalized_effective_policy_set_hash"],
            application["created_by_subject_id"],
            created_by_command_id,
            created_at_utc,
        ),
    )
    rows = connection.execute(
        """
        SELECT * FROM notification_profile_application_policies
        WHERE notification_profile_application_id = ?
        """,
        (application["notification_profile_application_id"],),
    ).fetchall()
    for row in rows:
        current_policy = connection.execute(
            """
            SELECT policy_id FROM notification_policies
            WHERE item_id = ? AND version = ? AND notification_intent_id = ?
            """,
            (item_id, next_version, row["notification_intent_id"]),
        ).fetchone()
        if current_policy is None:
            continue
        connection.execute(
            """
            INSERT INTO notification_profile_application_policies (
              notification_profile_application_policy_id, notification_profile_application_id,
              policy_origin, source_key, notification_profile_template_id,
              notification_intent_id, notification_policy_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                copy_id(str(row["notification_profile_application_policy_id"]), next_version),
                new_application_id,
                row["policy_origin"],
                row["source_key"],
                row["notification_profile_template_id"],
                row["notification_intent_id"],
                current_policy["policy_id"],
            ),
        )
