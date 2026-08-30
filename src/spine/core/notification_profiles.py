"""Pure normalization and composition for item archetypes and notification profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from spine.core import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notifications import (
    NOTIFICATION_AUTHORING_VERSION,
    normalize_notification_policy,
)

ITEM_ARCHETYPE_CONTRACT = "spine.item-archetypes.v1"
NOTIFICATION_PROFILE_CONTRACT = "spine.notification-profiles.v1"
NOTIFICATION_PROFILE_METADATA_UPDATE_CONTRACT = "spine.notification-profile-metadata-update.v1"
NOTIFICATION_PROFILE_BINDING_CONTRACT = "spine.notification-profile-bindings.v1"
NOTIFICATION_PROFILE_APPLICATION_CONTRACT = "spine.notification-profile-application.v1"
NOTIFICATION_PROFILE_READBACK_CONTRACT = "spine.notification-profile-readback.v1"

DYNAMIC_CATALOG_RECEIPT_EFFECTS = frozenset(
    {
        "item_archetype_created",
        "item_archetype_revised",
        "item_archetype_retired",
        "item_archetype_retire_noop",
        "notification_profile_created",
        "notification_profile_revised",
        "notification_profile_retired",
        "notification_profile_retire_noop",
        "notification_profile_metadata_updated",
        "notification_profile_metadata_update_noop",
        "notification_profile_binding_set",
        "notification_profile_binding_set_noop",
        "notification_profile_binding_removed",
        "notification_profile_binding_remove_noop",
    }
)

_KEY = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_ITEM_TYPES = frozenset({"event", "task"})
_OWNER_KINDS = frozenset({"system", "subject", "subject_group"})


@dataclass(frozen=True)
class NormalizedProfileRevision:
    compatible_item_types: tuple[str, ...]
    templates: tuple[dict[str, Any], ...]
    normalized_revision_hash: str


@dataclass(frozen=True)
class ComposedNotificationPlan:
    reminders: tuple[dict[str, Any], ...]
    origins: tuple[dict[str, Any], ...]
    suppress_template_keys: tuple[str, ...]
    replacements: tuple[dict[str, Any], ...]
    custom_additions: tuple[dict[str, Any], ...]
    normalized_effective_policy_set_hash: str


def normalize_catalog_key(value: object, field: str) -> str:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must match {_KEY.pattern}")
    return value


def normalize_owner(value: object, field: str = "owner") -> dict[str, str | None]:
    owner = _mapping(value, field)
    allowed = {"owner_kind", "owner_subject_id", "owner_group_id"}
    _exact_fields(owner, allowed, field)
    kind = owner.get("owner_kind")
    if kind not in _OWNER_KINDS:
        raise SpineValidationError(f"invalid_request:{field}.owner_kind", "owner_kind must be system, subject, or subject_group")
    subject_id = _optional_string(owner.get("owner_subject_id"), f"{field}.owner_subject_id")
    group_id = _optional_string(owner.get("owner_group_id"), f"{field}.owner_group_id")
    if kind == "system":
        if subject_id is not None or group_id is not None:
            raise SpineValidationError(f"invalid_request:{field}", "system owner cannot contain an owner id")
    elif kind == "subject":
        if subject_id is None or group_id is not None:
            raise SpineValidationError(f"invalid_request:{field}", "subject owner requires owner_subject_id only")
    elif group_id is None or subject_id is not None:
        raise SpineValidationError(f"invalid_request:{field}", "subject_group owner requires owner_group_id only")
    return {"owner_kind": str(kind), "owner_subject_id": subject_id, "owner_group_id": group_id}


def normalize_item_types(value: object, field: str = "compatible_item_types") -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an array")
    if not 1 <= len(value) <= 2 or any(item not in _ITEM_TYPES for item in value):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must contain event and/or task")
    result = tuple(sorted(str(item) for item in value))
    if len(result) != len(set(result)):
        raise SpineValidationError(f"semantic_conflict:{field}", f"{field} values must be unique")
    return result


def normalize_archetype_revision(value: object) -> dict[str, Any]:
    revision = _mapping(value, "revision")
    _exact_fields(revision, {"display_name", "description", "compatible_item_types"}, "revision")
    display_name = _required_string(revision.get("display_name"), "revision.display_name", maximum=160)
    description = _optional_string(revision.get("description"), "revision.description", maximum=2000)
    item_types = normalize_item_types(revision.get("compatible_item_types"), "revision.compatible_item_types")
    normalized = {
        "display_name": display_name,
        "description": description,
        "compatible_item_types": list(item_types),
    }
    normalized["normalized_content_hash"] = hash_canonical_json(normalized)
    return normalized


def normalize_profile_revision(value: object) -> NormalizedProfileRevision:
    revision = _mapping(value, "revision")
    _exact_fields(revision, {"compatible_item_types", "templates"}, "revision")
    item_types = normalize_item_types(revision.get("compatible_item_types"), "revision.compatible_item_types")
    raw_templates = revision.get("templates")
    if not isinstance(raw_templates, Sequence) or isinstance(raw_templates, (str, bytes, bytearray)):
        raise SpineValidationError("invalid_request:revision.templates", "revision.templates must be an array")
    if not 1 <= len(raw_templates) <= 32:
        raise SpineValidationError("invalid_request:revision.templates", "revision.templates must contain 1 through 32 entries")
    templates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_templates):
        template = _mapping(raw, f"revision.templates[{index}]")
        _exact_fields(template, {"template_key", "schedule", "late_handling"}, f"revision.templates[{index}]")
        key = normalize_catalog_key(template.get("template_key"), f"revision.templates[{index}].template_key")
        if key in seen:
            raise SpineValidationError(f"semantic_conflict:revision.templates[{index}].template_key", "template_key must be unique")
        seen.add(key)
        schedule = _closed_json_object(template.get("schedule"), f"revision.templates[{index}].schedule")
        late = _closed_json_object(template.get("late_handling"), f"revision.templates[{index}].late_handling")
        normalized = {
            "template_key": key,
            "schedule": schedule,
            "late_handling": late,
        }
        normalized["normalized_template_hash"] = hash_canonical_json(normalized)
        templates.append(normalized)
    templates.sort(key=lambda item: str(item["template_key"]))
    _validate_template_semantics(templates, item_types)
    preimage = {
        "contract_version": NOTIFICATION_PROFILE_CONTRACT,
        "compatible_item_types": list(item_types),
        "templates": templates,
    }
    return NormalizedProfileRevision(
        compatible_item_types=item_types,
        templates=tuple(templates),
        normalized_revision_hash=hash_canonical_json(preimage),
    )


def _validate_template_semantics(
    templates: Sequence[Mapping[str, Any]],
    item_types: Sequence[str],
) -> None:
    """Prove template validity and non-duplication before catalog mutation."""

    for item_type in item_types:
        target_anchor = "event_start" if item_type == "event" else "task_due"
        seen_hashes: dict[str, str] = {}
        for template in templates:
            key = str(template["template_key"])
            normalized = normalize_notification_policy(
                {
                    "authoring_contract": NOTIFICATION_AUTHORING_VERSION,
                    "target": {
                        "anchor_role": target_anchor,
                        "application_scope": "item",
                    },
                    "schedule": template["schedule"],
                    "late_handling": template["late_handling"],
                },
                item_id="profile_validation_item",
                item_version="1",
                command_id=f"profile_validation_{key}",
                created_at_utc="2000-01-01T00:00:00Z",
                recipient_kind="subject",
                recipient_id="profile_validation_subject",
                channel="profile_validation",
                delivery_target_id="profile_validation_target",
            )
            schedule_hash = str(
                normalized.value["normalized_notification_schedule_hash"]
            )
            prior = seen_hashes.get(schedule_hash)
            if prior is not None:
                raise SpineValidationError(
                    "semantic_conflict:revision.templates",
                    f"templates {prior} and {key} normalize to duplicate "
                    f"{item_type} notification policies",
                )
            seen_hashes[schedule_hash] = key


def compose_notification_plan(
    templates: Sequence[Mapping[str, Any]],
    *,
    suppress_template_keys: object,
    replacements: object,
    custom_additions: object,
) -> ComposedNotificationPlan:
    by_key = {str(value["template_key"]): value for value in templates}
    suppress = _sorted_keys(suppress_template_keys, "notification_plan.suppress_template_keys")
    unknown_suppressed = sorted(set(suppress) - set(by_key))
    if unknown_suppressed:
        raise SpineValidationError(
            "referenced_row_not_found:notification_plan.suppress_template_keys",
            f"unknown template keys: {unknown_suppressed}",
        )
    replacement_values = _policy_overlays(replacements, "notification_plan.replacements", key_field="template_key")
    replacement_by_key = {str(value["template_key"]): value for value in replacement_values}
    unknown_replaced = sorted(set(replacement_by_key) - set(by_key))
    if unknown_replaced:
        raise SpineValidationError("referenced_row_not_found:notification_plan.replacements", f"unknown template keys: {unknown_replaced}")
    overlap = sorted(set(suppress) & set(replacement_by_key))
    if overlap:
        raise SpineValidationError("semantic_conflict:notification_plan", f"template keys cannot be suppressed and replaced: {overlap}")
    additions = _policy_overlays(custom_additions, "notification_plan.custom_additions", key_field="policy_key")
    reminders: list[dict[str, Any]] = []
    origins: list[dict[str, Any]] = []
    for key in sorted(by_key):
        if key in suppress:
            continue
        replacement = replacement_by_key.get(key)
        source: Mapping[str, Any]
        if replacement is None:
            source = by_key[key]
            origin = "profile_template"
        else:
            source = replacement
            origin = "profile_replacement"
        reminders.append({"policy_key": f"profile_{key}", "schedule": source["schedule"], "late_handling": source["late_handling"]})
        origins.append({"policy_key": f"profile_{key}", "policy_origin": origin, "source_key": key, "template_key": key})
    for addition in additions:
        key = str(addition["policy_key"])
        reminders.append({"policy_key": key, "schedule": addition["schedule"], "late_handling": addition["late_handling"]})
        origins.append({"policy_key": key, "policy_origin": "custom_addition", "source_key": key})
    if not 1 <= len(reminders) <= 32:
        raise SpineValidationError("invalid_request:notification_plan", "effective notification plan must contain 1 through 32 policies")
    reminders.sort(key=lambda item: str(item["policy_key"]))
    origins.sort(key=lambda item: str(item["policy_key"]))
    effective_hash = hash_canonical_json(
        {
            "contract_version": NOTIFICATION_PROFILE_APPLICATION_CONTRACT,
            "reminders": reminders,
            "origins": origins,
        }
    )
    return ComposedNotificationPlan(
        reminders=tuple(reminders),
        origins=tuple(origins),
        suppress_template_keys=suppress,
        replacements=tuple(replacement_values),
        custom_additions=tuple(additions),
        normalized_effective_policy_set_hash=effective_hash,
    )


def _policy_overlays(value: object, field: str, *, key_field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        entry = _mapping(raw, f"{field}[{index}]")
        _exact_fields(entry, {key_field, "schedule", "late_handling"}, f"{field}[{index}]")
        key = normalize_catalog_key(entry.get(key_field), f"{field}[{index}].{key_field}")
        if key in seen:
            raise SpineValidationError(f"semantic_conflict:{field}[{index}].{key_field}", f"{key_field} must be unique")
        seen.add(key)
        result.append(
            {
                key_field: key,
                "schedule": _closed_json_object(entry.get("schedule"), f"{field}[{index}].schedule"),
                "late_handling": _closed_json_object(entry.get("late_handling"), f"{field}[{index}].late_handling"),
            }
        )
    result.sort(key=lambda item: str(item[key_field]))
    return result


def _sorted_keys(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an array")
    keys = tuple(sorted(normalize_catalog_key(item, f"{field}[]") for item in value))
    if len(keys) != len(set(keys)):
        raise SpineValidationError(f"semantic_conflict:{field}", f"{field} values must be unique")
    return keys


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an object")
    return value


def _closed_json_object(value: object, field: str) -> dict[str, Any]:
    return dict(_mapping(value, field))


def _exact_fields(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SpineValidationError(f"unsupported_field:{field}.{unknown[0]}", f"unsupported field: {field}.{unknown[0]}")


def _required_string(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a non-empty string up to {maximum} characters")
    return value


def _optional_string(value: object, field: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be null or a non-empty string up to {maximum} characters")
    return value
