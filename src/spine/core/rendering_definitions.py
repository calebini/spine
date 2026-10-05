"""Pure codecs for the candidate rendering integration; no capability activation."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.facets import parse_object
from spine.core.hashing import hash_canonical_json
from spine.core.notification_profiles import (
    NormalizedProfileRevision,
    normalize_catalog_key,
    normalize_owner,
    normalize_profile_revision,
)
from spine.core.notification_rendering import _normalized_text

CANON = "spine.canonical-json.v1"
DEFINITIONS = "spine.notification-rendering-definitions.v1"
DISCLOSURES = "spine.notification-rendering-disclosures.v1"
PRESENTATION = "spine.notification-rendering-presentation.v1"
PROFILE_V2 = "spine.notification-profiles.v2"
MAX_INTEGER = 9223372036854775807


def fail(code: str, field: str, message: str = "rendering request could not complete") -> Any:
    raise SpineValidationError(f"{code}:{field}", message)


def exact(value: object, required: set[str], optional: set[str] | None = None, field: str = "request") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        fail("invalid_request", field)
    result = copy.deepcopy(dict(value))
    extra = set(result) - required - (optional or set())
    prefix = "" if field == "request" else field + "."
    if extra:
        fail("unsupported_field", prefix + sorted(extra)[0])
    missing = required - set(result)
    if missing:
        fail("missing_required_field", prefix + sorted(missing)[0])
    canonical_json_bytes(result)  # Reject numbers and invalid Unicode before interpretation.
    return result


def identity(value: object, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        fail("invalid_request", field)
    canonical_json_bytes(value)
    return value


def text(value: object, field: str, maximum: int) -> str:
    try:
        result = _normalized_text(identity(value, field, max(maximum, 32768)), field)
    except SpineValidationError as exc:
        fail("invalid_request", field, str(exc))
    if not result or len(result) > maximum:
        fail("invalid_request", field)
    return result


def owner(value: object) -> dict[str, Any]:
    normalized = normalize_owner(value)
    return {k: v for k, v in normalized.items() if v is not None}


def sorted_strings(value: object, field: str, maximum: int, *, minimum: int = 0, keys: bool = False) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail("invalid_request", field)
    values = [normalize_catalog_key(v, field) if keys else identity(v, field) for v in value]
    if len(values) != len(set(values)):
        fail("semantic_conflict", field, "duplicate values are not permitted")
    return sorted(values)


def definition_reference(value: object) -> dict[str, str]:
    result = exact(value, {"notification_rendering_definition_id", "notification_rendering_definition_revision_id"}, field="definition")
    return {k: identity(v, "definition." + k) for k, v in result.items()}


def normalize_revision(value: object) -> dict[str, Any]:
    revision = exact(
        value,
        {"display_name", "description", "compatible_item_types", "base_rendering_contract", "base_rendering_profile", "selections"},
        field="revision",
    )
    revision["display_name"] = text(revision["display_name"], "revision.display_name", 160)
    if revision["description"] is not None:
        revision["description"] = text(revision["description"], "revision.description", 2000)
    types = revision["compatible_item_types"]
    if not isinstance(types, list) or not 1 <= len(types) <= 2 or any(not isinstance(v, str) or v not in {"event", "task"} for v in types):
        fail("rendering_definition_invalid", "revision.compatible_item_types")
    if len(types) != len(set(types)):
        fail("rendering_definition_invalid", "revision.compatible_item_types")
    revision["compatible_item_types"] = sorted(types)
    if (
        revision["base_rendering_contract"] != "spine.notification-rendering.v1"
        or revision["base_rendering_profile"] != "spine.notification-rendering.concise-en-ca.v1"
    ):
        fail("rendering_definition_invalid", "revision.base_rendering_contract")
    selections = revision["selections"]
    if not isinstance(selections, list) or not 1 <= len(selections) <= 8:
        fail("rendering_definition_invalid", "revision.selections")
    names, sources = set(), set()
    normalized = []
    for selection in selections:
        selection = exact(
            selection,
            {"selection_key", "facet_key", "facet_schema_revision_id", "field_key", "label", "projection"},
            field="revision.selections",
        )
        for k in ("selection_key", "facet_key", "field_key"):
            selection[k] = normalize_catalog_key(selection[k], "revision.selections." + k)
        identity(selection["facet_schema_revision_id"], "revision.selections.facet_schema_revision_id")
        selection["label"] = text(selection["label"], "revision.selections.label", 40)
        if selection["projection"] not in {"value", "location_label"}:
            fail("rendering_definition_invalid", "revision.selections.projection")
        source = tuple(selection[k] for k in ("facet_key", "facet_schema_revision_id", "field_key"))
        if selection["selection_key"] in names or source in sources:
            fail("rendering_definition_invalid", "revision.selections", "duplicate selection")
        names.add(selection["selection_key"])
        sources.add(source)
        normalized.append(selection)
    revision["selections"] = normalized
    bounded(revision, 8192, "revision")
    return revision


def normalize_scope(value: object) -> dict[str, Any]:
    scope = exact(
        value, {"item_owner", "definition", "approved_selection_keys", "use_scope", "destination", "permitted_location_ids"}, field="scope"
    )
    scope["item_owner"] = owner(scope["item_owner"])
    if scope["item_owner"]["owner_kind"] == "system":
        fail("invalid_request", "scope.item_owner")
    scope["definition"] = definition_reference(scope["definition"])
    scope["approved_selection_keys"] = sorted_strings(
        scope["approved_selection_keys"], "scope.approved_selection_keys", 8, minimum=1, keys=True
    )
    scope["permitted_location_ids"] = sorted_strings(scope["permitted_location_ids"], "scope.permitted_location_ids", 64)
    use = scope["use_scope"]
    if not isinstance(use, Mapping) or use.get("kind") not in {"profile", "direct_policy"}:
        fail("invalid_request", "scope.use_scope")
    scope["use_scope"] = exact(use, {"kind", "notification_profile_id"} if use["kind"] == "profile" else {"kind"}, field="scope.use_scope")
    if use["kind"] == "profile":
        identity(use["notification_profile_id"], "scope.use_scope.notification_profile_id")
    scope["destination"] = normalize_destination(scope["destination"])
    bounded(scope, 24576, "scope")
    return scope


def normalize_destination(value: object) -> dict[str, Any]:
    result = exact(
        value, {"recipient", "delivery_target_id", "channel", "adapter_name", "destination_source", "target_ref"}, field="destination"
    )
    recipient = result["recipient"]
    if not isinstance(recipient, Mapping) or recipient.get("kind") not in {"subject", "subject_group"}:
        fail("invalid_request", "destination.recipient")
    key = "subject_id" if recipient["kind"] == "subject" else "group_id"
    result["recipient"] = exact(recipient, {"kind", key}, field="destination.recipient")
    identity(recipient[key], "destination.recipient." + key)
    for key, maximum in (
        ("delivery_target_id", 256),
        ("channel", 64),
        ("adapter_name", 128),
        ("destination_source", 128),
        ("target_ref", 1024),
    ):
        identity(result[key], "destination." + key, maximum)
    return result


def normalize_origin(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("kind") not in {"direct", "custom_addition", "profile_template", "profile_replacement"}:
        fail("invalid_request", "origin")
    fields = {"kind"}
    if value["kind"] in {"profile_template", "profile_replacement"}:
        fields |= {"notification_profile_id", "notification_profile_revision_id", "template_key"}
    result = exact(value, fields, field="origin")
    for k in fields - {"kind"}:
        if k == "template_key":
            normalize_catalog_key(result[k], "origin.template_key")
        else:
            identity(result[k], "origin." + k)
    return result


def normalize_selection(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("kind") == "ordinary":
        return exact(value, {"kind"}, field="presentation")
    result = exact(value, {"kind", "definition", "authorization", "effective_selection_keys"}, field="presentation")
    if result["kind"] != "definition":
        fail("invalid_request", "presentation.kind")
    result["definition"] = definition_reference(result["definition"])
    result["effective_selection_keys"] = sorted_strings(
        result["effective_selection_keys"], "presentation.effective_selection_keys", 8, keys=True
    )
    authorization = result["authorization"]
    if not isinstance(authorization, Mapping) or authorization.get("resolution") not in {"exact", "unique_match"}:
        fail("invalid_request", "presentation.authorization")
    required = {"resolution", "disclosure_authorization_id"} if authorization["resolution"] == "exact" else {"resolution"}
    result["authorization"] = exact(authorization, required, field="presentation.authorization")
    if "disclosure_authorization_id" in authorization:
        identity(authorization["disclosure_authorization_id"], "presentation.authorization.disclosure_authorization_id")
    return result


def normalize_presentation(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("kind") == "ordinary":
        return exact(value, {"kind"}, field="presentation")
    result = exact(
        value,
        {"kind", "definition", "disclosure_authorization_id", "disclosure_scope_hash", "effective_selection_keys", "origin"},
        field="presentation",
    )
    if result["kind"] != "definition":
        fail("invalid_request", "presentation.kind")
    result["definition"] = definition_reference(result["definition"])
    identity(result["disclosure_authorization_id"], "presentation.disclosure_authorization_id")
    digest = result["disclosure_scope_hash"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        fail("invalid_request", "presentation.disclosure_scope_hash")
    result["effective_selection_keys"] = sorted_strings(
        result["effective_selection_keys"], "presentation.effective_selection_keys", 8, keys=True
    )
    result["origin"] = normalize_origin(result["origin"])
    bounded(result, 8192, "presentation")
    return result


def bounded(value: object, maximum: int, field: str) -> None:
    if len(canonical_json_bytes(value)) > maximum:
        fail("environment_failure", "capacity", field + " exceeds its byte bound")


def stored_object(value: object, maximum: int, field: str = "rendering") -> dict[str, Any]:
    try:
        if not isinstance(value, str):
            raise ValueError("text required")
        parsed = parse_object(value, maximum=maximum)
        if canonical_json_text(parsed) != value:
            raise ValueError("noncanonical")
        return parsed
    except (ValueError, TypeError, SpineValidationError) as exc:
        raise SpineValidationError("environment_failure:" + field, "corrupt rendering supporting facts") from exc


def content_hash(contract: str, key: str, value: object) -> str:
    return hash_canonical_json({"contract_version": contract, "canonical_json_version": CANON, key: value})


def derived_hash(domain: str, **facts: Any) -> str:
    return hash_canonical_json({"derivation_version": domain, "canonical_json_version": CANON, **facts})


def presentation_hash(value: object) -> str:
    return derived_hash("spine.notification-policy-presentation-hash.v1", presentation=normalize_presentation(value))


def presentation_set_hash(entries: list[dict[str, Any]]) -> str:
    entries = sorted(entries, key=lambda v: v["notification_policy_id"])
    if len({v["notification_policy_id"] for v in entries}) != len(entries):
        fail("environment_failure", "presentation", "duplicate policy in presentation set")
    return derived_hash("spine.notification-presentation-set-hash.v1", entries=entries)


def match_hash(scope: dict[str, Any]) -> str:
    return derived_hash(
        "spine.rendering-disclosure-match.v1", **{k: scope[k] for k in ("item_owner", "definition", "use_scope", "destination")}
    )


def use_scope(origin: dict[str, Any]) -> dict[str, str]:
    if origin["kind"] in {"profile_template", "profile_replacement"}:
        return {"kind": "profile", "notification_profile_id": origin["notification_profile_id"]}
    return {"kind": "direct_policy"}


def normalize_profile_v2(value: object) -> NormalizedProfileRevision:
    revision = exact(value, {"compatible_item_types", "templates"}, field="revision")
    raw = revision["templates"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
        fail("invalid_request", "revision.templates")
    ordinary = []
    renderings = {}
    for template in raw:
        template = exact(template, {"template_key", "schedule", "late_handling"}, {"rendering"}, field="revision.templates")
        rendering = template.pop("rendering", {"kind": "ordinary"})
        if not isinstance(rendering, Mapping) or rendering.get("kind") not in {"ordinary", "definition"}:
            fail("invalid_request", "revision.templates.rendering")
        rendering = exact(
            rendering, {"kind", "definition"} if rendering["kind"] == "definition" else {"kind"}, field="revision.templates.rendering"
        )
        if rendering["kind"] == "definition":
            rendering["definition"] = definition_reference(rendering["definition"])
        renderings[template["template_key"]] = rendering
        ordinary.append(template)
    old = normalize_profile_revision({"compatible_item_types": revision["compatible_item_types"], "templates": ordinary})
    templates = []
    for template in old.templates:
        normalized = {k: v for k, v in template.items() if k != "normalized_template_hash"}
        normalized["rendering"] = renderings[normalized["template_key"]]
        normalized["normalized_template_hash"] = derived_hash("spine.notification-profile-template-hash.v2", template=normalized)
        templates.append(normalized)
    content = {"compatible_item_types": list(old.compatible_item_types), "templates": templates}
    return NormalizedProfileRevision(
        old.compatible_item_types, tuple(templates), derived_hash("spine.notification-profile-revision-hash.v2", revision=content)
    )
