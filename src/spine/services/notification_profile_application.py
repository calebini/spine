"""Profile-aware schedule composition and immutable application provenance."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.commands.receipts import command_derived_id
from spine.core import SpineValidationError
from spine.core.notification_profiles import compose_notification_plan
from spine.ledger.notification_profiles import (
    current_application,
    current_assignment,
    insert_application,
    insert_assignment,
    load_archetype,
    load_profile,
    require_owner_exists,
    resolve_default_profile,
)


def prepare_schedule_create_profile(
    connection: sqlite3.Connection,
    *,
    item: Mapping[str, Any],
    item_id: str,
    item_type: str,
    notification_plan: object,
    command_id: str,
    actor_subject_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    """Resolve an optional archetype and one complete desired notification plan."""

    assignment = _prepare_assignment(
        connection,
        item.get("archetype"),
        item_id=item_id,
        item_type=item_type,
        command_id=command_id,
        actor_subject_id=actor_subject_id,
        created_at_utc=created_at_utc,
    )
    plan = _mapping(notification_plan, "notification_plan")
    _exact(
        plan,
        {
            "mode",
            "notification_profile_id",
            "revision_resolution",
            "notification_profile_revision_id",
            "scope_chain",
            "on_no_match",
            "suppress_template_keys",
            "replacements",
            "custom_additions",
        },
        "notification_plan",
    )
    mode = plan.get("mode")
    if mode not in {"none", "explicit", "archetype_default"}:
        raise SpineValidationError(
            "invalid_request:notification_plan.mode",
            "mode must be none, explicit, or archetype_default",
        )
    suppress = plan.get("suppress_template_keys", [])
    replacements = plan.get("replacements", [])
    additions = plan.get("custom_additions", [])
    if mode == "none":
        _forbid(
            plan,
            {
                "notification_profile_id",
                "revision_resolution",
                "notification_profile_revision_id",
                "scope_chain",
                "on_no_match",
                "suppress_template_keys",
                "replacements",
            },
            "notification_plan",
        )
        reminders = _custom_only(additions)
        return {
            "assignment": assignment,
            "application": None,
            "reminders": reminders,
            "projection": {
                "selection_mode": "none",
                "application": None,
                "policy_origins": [
                    {
                        "policy_key": reminder["policy_key"],
                        "policy_origin": "custom_addition",
                        "source_key": reminder["policy_key"],
                    }
                    for reminder in reminders
                ],
            },
        }

    scope_chain: tuple[dict[str, Any], ...] = ()
    binding_id: str | None = None
    if mode == "explicit":
        _forbid(plan, {"scope_chain", "on_no_match"}, "notification_plan")
        profile_id = _required(plan, "notification_profile_id", "notification_plan")
        resolution = _required(plan, "revision_resolution", "notification_plan")
        if resolution == "current":
            if "notification_profile_revision_id" in plan:
                raise SpineValidationError(
                    "invalid_request:notification_plan.notification_profile_revision_id",
                    "current resolution cannot name a revision",
                )
            profile = load_profile(connection, profile_id, active_required=True)
        elif resolution == "exact":
            revision_id = _required(
                plan, "notification_profile_revision_id", "notification_plan"
            )
            profile = load_profile(
                connection,
                profile_id,
                revision_id=revision_id,
                active_required=True,
            )
        else:
            raise SpineValidationError(
                "invalid_request:notification_plan.revision_resolution",
                "revision_resolution must be current or exact",
            )
    else:
        _forbid(
            plan,
            {
                "notification_profile_id",
                "revision_resolution",
                "notification_profile_revision_id",
            },
            "notification_plan",
        )
        if assignment is None:
            raise SpineValidationError(
                "invalid_request:item.archetype",
                "archetype_default requires an item archetype assignment",
            )
        scope_chain = _scope_chain(plan.get("scope_chain"))
        for owner in scope_chain:
            require_owner_exists(connection, owner)
        resolution_result = resolve_default_profile(
            connection,
            item_archetype_id=assignment["archetype"]["item_archetype_id"],
            item_type=item_type,
            scope_chain=scope_chain,
        )
        if resolution_result is None:
            on_no_match = plan.get("on_no_match", "fail")
            if on_no_match != "use_custom_only":
                raise SpineValidationError(
                    "referenced_row_not_found:notification_plan.scope_chain",
                    "no active notification profile binding matched the scope chain",
                )
            _forbid(
                plan,
                {"suppress_template_keys", "replacements"},
                "notification_plan",
            )
            reminders = _custom_only(additions)
            return {
                "assignment": assignment,
                "application": None,
                "reminders": reminders,
                "projection": {
                    "selection_mode": "custom_only_fallback",
                    "scope_chain": list(scope_chain),
                    "application": None,
                    "policy_origins": [
                        {
                            "policy_key": reminder["policy_key"],
                            "policy_origin": "custom_addition",
                            "source_key": reminder["policy_key"],
                        }
                        for reminder in reminders
                    ],
                },
            }
        if plan.get("on_no_match", "fail") not in {"fail", "use_custom_only"}:
            raise SpineValidationError(
                "invalid_request:notification_plan.on_no_match",
                "on_no_match must be fail or use_custom_only",
            )
        profile = resolution_result["profile"]
        binding_id = str(
            resolution_result["binding"]["notification_profile_binding_id"]
        )

    if item_type not in profile["revision"]["compatible_item_types"]:
        raise SpineValidationError(
            "semantic_conflict:notification_plan.notification_profile_id",
            "notification profile is incompatible with item type",
        )
    composed = compose_notification_plan(
        profile["revision"]["templates"],
        suppress_template_keys=suppress,
        replacements=replacements,
        custom_additions=additions,
    )
    application_id = command_derived_id(
        prefix="notification_profile_application",
        command="schedule.create",
        command_id=command_id,
        row_role="notification_profile_application",
        request_path="/notification_plan",
    )
    application = {
        "notification_profile_application_id": application_id,
        "profile": profile,
        "selection_mode": mode,
        "scope_chain": scope_chain,
        "binding_id": binding_id,
        "composed": composed,
        "actor_subject_id": actor_subject_id,
        "created_at_utc": created_at_utc,
    }
    projection = {
        "selection_mode": mode,
        "scope_chain": list(scope_chain),
        "notification_profile_application_id": application_id,
        "notification_profile_id": profile["notification_profile_id"],
        "notification_profile_revision_id": profile["revision"][
            "notification_profile_revision_id"
        ],
        "notification_profile_binding_id": binding_id,
        "normalized_revision_hash": profile["revision"][
            "normalized_revision_hash"
        ],
        "normalized_effective_policy_set_hash": (
            composed.normalized_effective_policy_set_hash
        ),
        "suppress_template_keys": list(composed.suppress_template_keys),
        "replacements": list(composed.replacements),
        "custom_additions": list(composed.custom_additions),
        "policy_origins": list(composed.origins),
    }
    return {
        "assignment": assignment,
        "application": application,
        "reminders": list(composed.reminders),
        "projection": projection,
    }


def persist_schedule_create_profile(
    connection: sqlite3.Connection,
    *,
    prepared: Mapping[str, Any],
    item_id: str,
    command_id: str,
    actor_subject_id: str,
    created_at_utc: str,
    policies: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Persist assignment/application facts inside schedule.create's transaction."""

    assignment = prepared.get("assignment")
    assignment_facts = None
    if isinstance(assignment, Mapping):
        assignment_facts = insert_assignment(
            connection,
            assignment_id=str(assignment["item_archetype_assignment_id"]),
            item_id=item_id,
            item_version=1,
            archetype=_mapping(assignment["archetype"], "assignment.archetype"),
            selection_source=str(assignment["selection_source"]),
            source_ref=(
                str(assignment["source_ref"])
                if assignment.get("source_ref") is not None
                else None
            ),
            actor_subject_id=actor_subject_id,
            command_id=command_id,
            created_at_utc=created_at_utc,
        )
    application = prepared.get("application")
    application_facts = None
    if isinstance(application, Mapping):
        composed = application["composed"]
        application_facts = insert_application(
            connection,
            application_id=str(application["notification_profile_application_id"]),
            item_id=item_id,
            item_version=1,
            profile=_mapping(application["profile"], "application.profile"),
            selection_mode=str(application["selection_mode"]),
            scope_chain=application["scope_chain"],
            assignment_id=(
                str(assignment["item_archetype_assignment_id"])
                if isinstance(assignment, Mapping)
                else None
            ),
            binding_id=(
                str(application["binding_id"])
                if application.get("binding_id") is not None
                else None
            ),
            suppress_template_keys=composed.suppress_template_keys,
            replacements=composed.replacements,
            additions=composed.custom_additions,
            effective_hash=composed.normalized_effective_policy_set_hash,
            origins=composed.origins,
            policies=policies,
            actor_subject_id=actor_subject_id,
            command_id=command_id,
            created_at_utc=created_at_utc,
        )
    return {
        "archetype": assignment_facts,
        "notification_profile": application_facts,
    }


def prepare_schedule_update_profile(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_version: int,
    next_version: int,
    item_type: str,
    archetype_patch_present: bool,
    archetype_patch: object,
    notification_plan_present: bool,
    notification_plan: object,
    command_id: str,
    actor_subject_id: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    """Resolve explicit update actions without mutating current pinned facts."""

    existing_assignment = current_assignment(
        connection, item_id=item_id, item_version=item_version
    )
    existing_application = current_application(
        connection, item_id=item_id, item_version=item_version
    )
    assignment_action = "retain"
    desired_assignment = existing_assignment
    if archetype_patch_present:
        value = _mapping(archetype_patch, "patch.archetype")
        assignment_action = _required(value, "action", "patch.archetype")
        if assignment_action == "retain":
            _exact(value, {"action"}, "patch.archetype")
        elif assignment_action == "clear":
            _exact(value, {"action"}, "patch.archetype")
            desired_assignment = None
        elif assignment_action == "select":
            selection = dict(value)
            selection.pop("action")
            desired_assignment = _prepare_update_assignment(
                connection,
                selection,
                item_id=item_id,
                item_type=item_type,
                command_id=command_id,
                actor_subject_id=actor_subject_id,
                updated_at_utc=updated_at_utc,
            )
        else:
            raise SpineValidationError(
                "invalid_request:patch.archetype.action",
                "archetype action must be retain, clear, or select",
            )

    profile_action = "retain"
    desired_application: dict[str, Any] | None = existing_application
    reminders: list[dict[str, Any]] | None = None
    projection: dict[str, Any] | None = None
    if notification_plan_present:
        plan = _mapping(notification_plan, "patch.notification_plan")
        profile_action = _required(plan, "action", "patch.notification_plan")
        if profile_action == "retain":
            _exact(plan, {"action"}, "patch.notification_plan")
        elif profile_action == "clear":
            _exact(
                plan, {"action", "custom_additions"}, "patch.notification_plan"
            )
            reminders = _custom_only(plan.get("custom_additions"))
            desired_application = None
            projection = {
                "profile_action": "clear",
                "application": None,
                "policy_origins": [
                    {
                        "policy_key": reminder["policy_key"],
                        "policy_origin": "custom_addition",
                        "source_key": reminder["policy_key"],
                    }
                    for reminder in reminders
                ],
            }
        elif profile_action in {"explicit", "archetype_default"}:
            create_plan = dict(plan)
            create_plan["mode"] = create_plan.pop("action")
            prepared = _prepare_plan_for_update(
                connection,
                item_id=item_id,
                item_type=item_type,
                assignment=desired_assignment,
                plan=create_plan,
                command_id=command_id,
                actor_subject_id=actor_subject_id,
                updated_at_utc=updated_at_utc,
            )
            desired_application = prepared["application"]
            reminders = prepared["reminders"]
            projection = prepared["projection"]
        elif profile_action == "upgrade_current_revision":
            _exact(
                plan,
                {
                    "action",
                    "suppress_template_keys",
                    "replacements",
                    "custom_additions",
                },
                "patch.notification_plan",
            )
            if existing_application is None:
                raise SpineValidationError(
                    "semantic_conflict:patch.notification_plan.action",
                    "upgrade_current_revision requires an existing profile application",
                )
            profile = load_profile(
                connection,
                str(existing_application["notification_profile_id"]),
                active_required=True,
            )
            composed = compose_notification_plan(
                profile["revision"]["templates"],
                suppress_template_keys=plan.get("suppress_template_keys", []),
                replacements=plan.get("replacements", []),
                custom_additions=plan.get("custom_additions", []),
            )
            desired_application = _update_application(
                profile=profile,
                selection_mode=str(existing_application["selection_mode"]),
                scope_chain=tuple(existing_application["scope_chain"]),
                binding_id=(
                    str(existing_application["notification_profile_binding_id"])
                    if existing_application.get("notification_profile_binding_id")
                    is not None
                    else None
                ),
                composed=composed,
                command_id=command_id,
                actor_subject_id=actor_subject_id,
                updated_at_utc=updated_at_utc,
            )
            reminders = list(composed.reminders)
            projection = _application_projection(
                desired_application, profile_action=profile_action
            )
        else:
            raise SpineValidationError(
                "invalid_request:patch.notification_plan.action",
                "profile action must be retain, clear, explicit, "
                "archetype_default, or upgrade_current_revision",
            )

    return {
        "assignment_action": assignment_action,
        "desired_assignment": desired_assignment,
        "profile_action": profile_action,
        "desired_application": desired_application,
        "reminders": reminders,
        "projection": projection,
        "replace_assignment": assignment_action != "retain",
        "replace_application": profile_action != "retain",
        "application_changed": (
            profile_action != "retain"
            and not (profile_action == "clear" and existing_application is None)
        ),
        "next_version": next_version,
    }


def persist_schedule_update_profile(
    connection: sqlite3.Connection,
    *,
    prepared: Mapping[str, Any],
    item_id: str,
    item_version: int,
    command_id: str,
    actor_subject_id: str,
    updated_at_utc: str,
    policies: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Replace copied-forward profile facts inside a successor transaction."""

    replace_application = bool(prepared["replace_application"])
    replace_assignment = bool(prepared["replace_assignment"])
    if replace_application:
        row = connection.execute(
            """
            SELECT notification_profile_application_id
            FROM notification_profile_applications
            WHERE item_id = ? AND item_version = ?
            """,
            (item_id, item_version),
        ).fetchone()
        if row is not None:
            connection.execute(
                """
                DELETE FROM notification_profile_application_policies
                WHERE notification_profile_application_id = ?
                """,
                (row["notification_profile_application_id"],),
            )
            connection.execute(
                """
                DELETE FROM notification_profile_applications
                WHERE notification_profile_application_id = ?
                """,
                (row["notification_profile_application_id"],),
            )
    if replace_assignment:
        if not replace_application:
            connection.execute(
                """
                UPDATE notification_profile_applications
                SET item_archetype_assignment_id = NULL
                WHERE item_id = ? AND item_version = ?
                """,
                (item_id, item_version),
            )
        connection.execute(
            """
            DELETE FROM item_archetype_assignments
            WHERE item_id = ? AND item_version = ?
            """,
            (item_id, item_version),
        )

    assignment_facts = None
    desired_assignment = prepared.get("desired_assignment")
    if replace_assignment and isinstance(desired_assignment, Mapping):
        assignment_facts = insert_assignment(
            connection,
            assignment_id=str(
                desired_assignment["item_archetype_assignment_id"]
            ),
            item_id=item_id,
            item_version=item_version,
            archetype=_mapping(
                desired_assignment["archetype"], "desired_assignment.archetype"
            ),
            selection_source=str(desired_assignment["selection_source"]),
            source_ref=(
                str(desired_assignment["source_ref"])
                if desired_assignment.get("source_ref") is not None
                else None
            ),
            actor_subject_id=actor_subject_id,
            command_id=command_id,
            created_at_utc=updated_at_utc,
        )

    application_facts = None
    desired_application = prepared.get("desired_application")
    if replace_application and isinstance(desired_application, Mapping):
        composed = desired_application["composed"]
        application_facts = insert_application(
            connection,
            application_id=str(
                desired_application["notification_profile_application_id"]
            ),
            item_id=item_id,
            item_version=item_version,
            profile=_mapping(
                desired_application["profile"], "desired_application.profile"
            ),
            selection_mode=str(desired_application["selection_mode"]),
            scope_chain=desired_application["scope_chain"],
            assignment_id=(
                str(desired_assignment["item_archetype_assignment_id"])
                if isinstance(desired_assignment, Mapping)
                else None
            ),
            binding_id=(
                str(desired_application["binding_id"])
                if desired_application.get("binding_id") is not None
                else None
            ),
            suppress_template_keys=composed.suppress_template_keys,
            replacements=composed.replacements,
            additions=composed.custom_additions,
            effective_hash=composed.normalized_effective_policy_set_hash,
            origins=composed.origins,
            policies=policies,
            actor_subject_id=actor_subject_id,
            command_id=command_id,
            created_at_utc=updated_at_utc,
        )
    return {
        "archetype": assignment_facts,
        "notification_profile": application_facts,
    }


def _prepare_update_assignment(
    connection: sqlite3.Connection,
    selection: Mapping[str, Any],
    *,
    item_id: str,
    item_type: str,
    command_id: str,
    actor_subject_id: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    _exact(
        selection,
        {
            "item_archetype_id",
            "revision_resolution",
            "item_archetype_revision_id",
            "selection_source",
            "source_ref",
        },
        "patch.archetype",
    )
    root_id = _required(selection, "item_archetype_id", "patch.archetype")
    resolution = _required(selection, "revision_resolution", "patch.archetype")
    if resolution == "current":
        if "item_archetype_revision_id" in selection:
            raise SpineValidationError(
                "invalid_request:patch.archetype.item_archetype_revision_id",
                "current resolution cannot name a revision",
            )
        archetype = load_archetype(connection, root_id, active_required=True)
    elif resolution == "exact":
        revision_id = _required(
            selection, "item_archetype_revision_id", "patch.archetype"
        )
        archetype = load_archetype(
            connection,
            root_id,
            revision_id=revision_id,
            active_required=True,
        )
    else:
        raise SpineValidationError(
            "invalid_request:patch.archetype.revision_resolution",
            "revision_resolution must be current or exact",
        )
    if item_type not in archetype["revision"]["compatible_item_types"]:
        raise SpineValidationError(
            "semantic_conflict:patch.archetype.item_archetype_id",
            "item archetype is incompatible with item type",
        )
    source = _required(selection, "selection_source", "patch.archetype")
    if source not in {"operator_explicit", "agent_selected", "imported"}:
        raise SpineValidationError(
            "invalid_request:patch.archetype.selection_source",
            "selection_source is invalid",
        )
    source_ref = selection.get("source_ref")
    if source_ref is not None and (not isinstance(source_ref, str) or not source_ref):
        raise SpineValidationError(
            "invalid_request:patch.archetype.source_ref",
            "source_ref must be a non-empty string",
        )
    return {
        "item_archetype_assignment_id": command_derived_id(
            prefix="item_archetype_assignment",
            command="schedule.update",
            command_id=command_id,
            row_role="item_archetype_assignment",
            request_path="/patch/archetype",
        ),
        "item_id": item_id,
        "archetype": archetype,
        "selection_source": source,
        "source_ref": source_ref,
        "actor_subject_id": actor_subject_id,
        "created_at_utc": updated_at_utc,
    }


def _prepare_plan_for_update(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    item_type: str,
    assignment: Mapping[str, Any] | None,
    plan: Mapping[str, Any],
    command_id: str,
    actor_subject_id: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    _exact(
        plan,
        {
            "mode",
            "notification_profile_id",
            "revision_resolution",
            "notification_profile_revision_id",
            "scope_chain",
            "on_no_match",
            "suppress_template_keys",
            "replacements",
            "custom_additions",
        },
        "patch.notification_plan",
    )
    mode = str(plan["mode"])
    scope_chain: tuple[dict[str, Any], ...] = ()
    binding_id: str | None = None
    if mode == "explicit":
        _forbid(plan, {"scope_chain", "on_no_match"}, "patch.notification_plan")
        profile_id = _required(
            plan, "notification_profile_id", "patch.notification_plan"
        )
        resolution = _required(
            plan, "revision_resolution", "patch.notification_plan"
        )
        if resolution == "current":
            if "notification_profile_revision_id" in plan:
                raise SpineValidationError(
                    "invalid_request:patch.notification_plan.notification_profile_revision_id",
                    "current resolution cannot name a revision",
                )
            profile = load_profile(connection, profile_id, active_required=True)
        elif resolution == "exact":
            revision_id = _required(
                plan,
                "notification_profile_revision_id",
                "patch.notification_plan",
            )
            profile = load_profile(
                connection,
                profile_id,
                revision_id=revision_id,
                active_required=True,
            )
        else:
            raise SpineValidationError(
                "invalid_request:patch.notification_plan.revision_resolution",
                "revision_resolution must be current or exact",
            )
    else:
        _forbid(
            plan,
            {
                "notification_profile_id",
                "revision_resolution",
                "notification_profile_revision_id",
            },
            "patch.notification_plan",
        )
        if assignment is None:
            raise SpineValidationError(
                "invalid_request:patch.archetype",
                "archetype_default requires an item archetype assignment",
            )
        scope_chain = _scope_chain(plan.get("scope_chain"))
        for owner in scope_chain:
            require_owner_exists(connection, owner)
        result = resolve_default_profile(
            connection,
            item_archetype_id=str(
                assignment["archetype"]["item_archetype_id"]
            ),
            item_type=item_type,
            scope_chain=scope_chain,
        )
        if result is None:
            on_no_match = plan.get("on_no_match", "fail")
            if on_no_match != "use_custom_only":
                raise SpineValidationError(
                    "referenced_row_not_found:patch.notification_plan.scope_chain",
                    "no active notification profile binding matched the scope chain",
                )
            _forbid(
                plan,
                {"suppress_template_keys", "replacements"},
                "patch.notification_plan",
            )
            reminders = _custom_only(plan.get("custom_additions"))
            return {
                "application": None,
                "reminders": reminders,
                "projection": {
                    "profile_action": "archetype_default",
                    "selection_mode": "custom_only_fallback",
                    "scope_chain": list(scope_chain),
                    "application": None,
                    "policy_origins": [
                        {
                            "policy_key": reminder["policy_key"],
                            "policy_origin": "custom_addition",
                            "source_key": reminder["policy_key"],
                        }
                        for reminder in reminders
                    ],
                },
            }
        if plan.get("on_no_match", "fail") not in {
            "fail",
            "use_custom_only",
        }:
            raise SpineValidationError(
                "invalid_request:patch.notification_plan.on_no_match",
                "on_no_match must be fail or use_custom_only",
            )
        profile = result["profile"]
        binding_id = str(
            result["binding"]["notification_profile_binding_id"]
        )
    if item_type not in profile["revision"]["compatible_item_types"]:
        raise SpineValidationError(
            "semantic_conflict:patch.notification_plan.notification_profile_id",
            "notification profile is incompatible with item type",
        )
    composed = compose_notification_plan(
        profile["revision"]["templates"],
        suppress_template_keys=plan.get("suppress_template_keys", []),
        replacements=plan.get("replacements", []),
        custom_additions=plan.get("custom_additions", []),
    )
    application = _update_application(
        profile=profile,
        selection_mode=mode,
        scope_chain=scope_chain,
        binding_id=binding_id,
        composed=composed,
        command_id=command_id,
        actor_subject_id=actor_subject_id,
        updated_at_utc=updated_at_utc,
    )
    return {
        "application": application,
        "reminders": list(composed.reminders),
        "projection": _application_projection(
            application, profile_action=mode
        ),
    }


def _update_application(
    *,
    profile: Mapping[str, Any],
    selection_mode: str,
    scope_chain: Sequence[Mapping[str, Any]],
    binding_id: str | None,
    composed: Any,
    command_id: str,
    actor_subject_id: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    return {
        "notification_profile_application_id": command_derived_id(
            prefix="notification_profile_application",
            command="schedule.update",
            command_id=command_id,
            row_role="notification_profile_application",
            request_path="/patch/notification_plan",
        ),
        "profile": profile,
        "selection_mode": selection_mode,
        "scope_chain": tuple(scope_chain),
        "binding_id": binding_id,
        "composed": composed,
        "actor_subject_id": actor_subject_id,
        "created_at_utc": updated_at_utc,
    }


def _application_projection(
    application: Mapping[str, Any], *, profile_action: str
) -> dict[str, Any]:
    profile = application["profile"]
    composed = application["composed"]
    return {
        "profile_action": profile_action,
        "selection_mode": application["selection_mode"],
        "scope_chain": list(application["scope_chain"]),
        "notification_profile_application_id": application[
            "notification_profile_application_id"
        ],
        "notification_profile_id": profile["notification_profile_id"],
        "notification_profile_revision_id": profile["revision"][
            "notification_profile_revision_id"
        ],
        "notification_profile_binding_id": application["binding_id"],
        "normalized_revision_hash": profile["revision"][
            "normalized_revision_hash"
        ],
        "normalized_effective_policy_set_hash": (
            composed.normalized_effective_policy_set_hash
        ),
        "suppress_template_keys": list(composed.suppress_template_keys),
        "replacements": list(composed.replacements),
        "custom_additions": list(composed.custom_additions),
        "policy_origins": list(composed.origins),
    }


def _prepare_assignment(
    connection: sqlite3.Connection,
    value: object,
    *,
    item_id: str,
    item_type: str,
    command_id: str,
    actor_subject_id: str,
    created_at_utc: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    selection = _mapping(value, "item.archetype")
    _exact(
        selection,
        {
            "item_archetype_id",
            "revision_resolution",
            "item_archetype_revision_id",
            "selection_source",
            "source_ref",
        },
        "item.archetype",
    )
    root_id = _required(selection, "item_archetype_id", "item.archetype")
    resolution = _required(selection, "revision_resolution", "item.archetype")
    if resolution == "current":
        if "item_archetype_revision_id" in selection:
            raise SpineValidationError(
                "invalid_request:item.archetype.item_archetype_revision_id",
                "current resolution cannot name a revision",
            )
        archetype = load_archetype(connection, root_id, active_required=True)
    elif resolution == "exact":
        revision_id = _required(
            selection, "item_archetype_revision_id", "item.archetype"
        )
        archetype = load_archetype(
            connection,
            root_id,
            revision_id=revision_id,
            active_required=True,
        )
    else:
        raise SpineValidationError(
            "invalid_request:item.archetype.revision_resolution",
            "revision_resolution must be current or exact",
        )
    if item_type not in archetype["revision"]["compatible_item_types"]:
        raise SpineValidationError(
            "semantic_conflict:item.archetype.item_archetype_id",
            "item archetype is incompatible with item type",
        )
    source = _required(selection, "selection_source", "item.archetype")
    if source not in {"operator_explicit", "agent_selected", "imported"}:
        raise SpineValidationError(
            "invalid_request:item.archetype.selection_source",
            "selection_source is invalid",
        )
    source_ref = selection.get("source_ref")
    if source_ref is not None and (not isinstance(source_ref, str) or not source_ref):
        raise SpineValidationError(
            "invalid_request:item.archetype.source_ref",
            "source_ref must be a non-empty string",
        )
    return {
        "item_archetype_assignment_id": command_derived_id(
            prefix="item_archetype_assignment",
            command="schedule.create",
            command_id=command_id,
            row_role="item_archetype_assignment",
            request_path="/item/archetype",
        ),
        "item_id": item_id,
        "archetype": archetype,
        "selection_source": source,
        "source_ref": source_ref,
        "actor_subject_id": actor_subject_id,
        "created_at_utc": created_at_utc,
    }


def _custom_only(value: object) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 1 <= len(value) <= 32
    ):
        raise SpineValidationError(
            "invalid_request:notification_plan.custom_additions",
            "custom_additions must contain one through 32 reminders",
        )
    result = [dict(_mapping(entry, "notification_plan.custom_additions[]")) for entry in value]
    return result


def _scope_chain(value: object) -> tuple[dict[str, Any], ...]:
    from spine.core.notification_profiles import normalize_owner

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 1 <= len(value) <= 8
    ):
        raise SpineValidationError(
            "invalid_request:notification_plan.scope_chain",
            "scope_chain must contain one through eight exact owners",
        )
    owners = tuple(
        normalize_owner(entry, f"notification_plan.scope_chain[{index}]")
        for index, entry in enumerate(value)
    )
    identities = [
        (
            owner["owner_kind"],
            owner["owner_subject_id"],
            owner["owner_group_id"],
        )
        for owner in owners
    ]
    if len(identities) != len(set(identities)):
        raise SpineValidationError(
            "semantic_conflict:notification_plan.scope_chain",
            "scope_chain owners must be unique",
        )
    return owners


def _forbid(value: Mapping[str, Any], fields: set[str], prefix: str) -> None:
    present = sorted(fields & set(value))
    if present:
        raise SpineValidationError(
            f"invalid_request:{prefix}.{present[0]}",
            f"{present[0]} is not allowed for this selection mode",
        )


def _exact(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SpineValidationError(
            f"unsupported_field:{field}.{unknown[0]}",
            f"unsupported field: {field}.{unknown[0]}",
        )


def _required(value: Mapping[str, Any], key: str, prefix: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise SpineValidationError(
            f"invalid_request:{prefix}.{key}",
            f"{prefix}.{key} is required",
        )
    return result


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(
            f"invalid_request:{field}", f"{field} must be an object"
        )
    return value
