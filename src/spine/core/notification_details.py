"""Candidate-only deterministic detail suffix and immutable v2 envelope codecs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from spine.core import rendering_definitions as codec
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notification_rendering import (
    CANONICAL_JSON_VERSION as CANON,
)
from spine.core.notification_rendering import (
    INPUT_NORMALIZATION_VERSION,
    RENDERING_CONTRACT,
    RENDERING_PROFILE,
    NotificationRendering,
    _normalized_text,
)

DETAILS_CONTRACT = "spine.notification-rendering-details-evidence.v1"
RENDERING_V2 = "spine.notification-rendering.v2"
OMISSIONS = {
    "not_selected",
    "disclosure_unavailable",
    "facet_missing",
    "schema_mismatch",
    "field_missing",
    "reference_unavailable",
    "invalid_text",
    "value_too_long",
    "suffix_overflow",
}


def require(condition: bool) -> None:
    if not condition:
        raise SpineValidationError("notification_rendering_persistence_conflict", "invalid immutable rendering evidence")


def preimage(domain: str, **facts: Any) -> dict[str, Any]:
    return {"derivation_version": domain, "canonical_json_version": CANON, **facts}


def ordinary_view(base: NotificationRendering) -> dict[str, Any]:
    """The frozen v1 wire projection, without coupling pure rendering to storage."""
    value = base.as_persistence()
    for key in ("source_input_json", "phrase_facts_json", "location_id", "item_location_id", "location_kind", "location_label"):
        value.pop(key)
    value["rendered_item_version"] = str(value["rendered_item_version"])
    value.update(source_input=base.source_input, phrase_facts=base.phrase_facts, primary_location=base.source_input["primary_location"])
    return {k: v for k, v in value.items() if v is not None or k == "primary_location"}


def decode_ordinary(value: dict[str, Any]) -> NotificationRendering:
    """Check historical hashes without re-rendering or requiring today's tzdb."""
    try:
        versions = {
            "rendering_contract": RENDERING_CONTRACT,
            "rendering_profile": RENDERING_PROFILE,
            "input_normalization_version": INPUT_NORMALIZATION_VERSION,
            "canonical_json_version": CANON,
        }
        source, phrase = value["source_input"], value["phrase_facts"]
        input_facts = {"derivation_version": "spine.notification-rendering-input-hash.v1", **versions, "source_input": source}
        content = {
            "derivation_version": "spine.notification-rendering-content-hash.v1",
            **versions,
            "rendering_input_hash": value["rendering_input_hash"],
            "phrase_kind": value["phrase_kind"],
            "phrase_facts": phrase,
            "body_text": value["body_text"],
        }
        identity = {
            "derivation_version": "spine.notification-rendering-id.v1",
            **versions,
            "attempt_id": source["attempt_id"],
            "rendering_input_hash": value["rendering_input_hash"],
            "rendered_content_hash": value["rendered_content_hash"],
        }
        require(hash_canonical_json(input_facts) == value["rendering_input_hash"])
        require(hash_canonical_json(content) == value["rendered_content_hash"])
        require("notification_rendering_" + hash_canonical_json(identity) == value["notification_rendering_id"])
        require(_normalized_text(value["body_text"], "body") == value["body_text"] and len(value["body_text"]) <= 1024)
        base = NotificationRendering(
            value["notification_rendering_id"],
            source["attempt_id"],
            source["work_instance_id"],
            value["rendering_input_hash"],
            value["rendered_content_hash"],
            value["body_text"],
            value["phrase_kind"],
            source,
            phrase,
            input_facts,
            content,
            identity,
        )
        require(ordinary_view(base) == value)
        return base
    except (KeyError, TypeError, ValueError) as exc:
        raise SpineValidationError("notification_rendering_persistence_conflict", "invalid ordinary rendering evidence") from exc


@dataclass(frozen=True)
class DetailedNotificationRendering(NotificationRendering):
    base: NotificationRendering
    details: dict[str, Any]

    def as_view(self) -> dict[str, Any]:
        return {
            "rendering_contract": RENDERING_V2,
            "notification_rendering_id": self.notification_rendering_id,
            "base_rendering": ordinary_view(self.base),
            "details": self.details,
            "rendering_input_hash": self.rendering_input_hash,
            "rendered_content_hash": self.rendered_content_hash,
            "body_text": self.body_text,
        }

    def as_persistence(self) -> dict[str, Any]:
        # Common source/phrase columns remain the ordinary base; only final facts
        # and the three versioned supporting columns differ.
        return self.base.as_persistence() | {
            "rendering_contract": RENDERING_V2,
            "notification_rendering_id": self.notification_rendering_id,
            "rendering_input_hash": self.rendering_input_hash,
            "rendered_content_hash": self.rendered_content_hash,
            "body_text": self.body_text,
            "base_rendering_json": canonical_json_text(ordinary_view(self.base)),
            "details_evidence_json": canonical_json_text(self.details),
            "details_contract_version": DETAILS_CONTRACT,
        }


def build_details(base: NotificationRendering, facts: dict[str, Any], candidates: list[dict[str, Any]]) -> DetailedNotificationRendering:
    """Finalize already authorized/resolved candidates; never retain omitted facts."""
    require(1 <= len(candidates) <= 8)
    suffix = "".join(f" · {s['label']}: {s['value']}" for s in candidates if s["outcome"] == "included")
    overflow = len(base.body_text + suffix) > 1024
    selections = []
    for candidate in candidates:
        if overflow and candidate["outcome"] == "included":
            selections.append({"selection_key": candidate["selection_key"], "outcome": "suffix_overflow"})
        else:
            selections.append({k: v for k, v in candidate.items() if k != "label"})
    details = facts | {
        "contract_version": DETAILS_CONTRACT,
        "attempt_id": base.attempt_id,
        "base_rendering_input_hash": base.rendering_input_hash,
        "base_rendered_content_hash": base.rendered_content_hash,
        "rendered_item_version": str(base.rendered_item_version),
        "selections": selections,
        "outcome": "suffix_overflow" if overflow else "details_included" if suffix else "ordinary_only",
        "body_text": base.body_text if overflow else base.body_text + suffix,
    }
    details["input_hash"] = hash_canonical_json({k: v for k, v in details.items() if k != "body_text"} | {"canonical_json_version": CANON})
    details["content_hash"] = hash_canonical_json(
        {"contract_version": DETAILS_CONTRACT, "canonical_json_version": CANON, "body_text": details["body_text"]}
    )
    result = assemble(base, details)
    require(len(canonical_json_bytes(details)) <= 16384 and len(canonical_json_bytes(result.as_view())) <= 32768)
    return result


def assemble(base: NotificationRendering, details: dict[str, Any]) -> DetailedNotificationRendering:
    """Check closed evidence, nested binding and hashes before any persistence."""
    required = {
        "contract_version",
        "attempt_id",
        "base_rendering_input_hash",
        "base_rendered_content_hash",
        "rendered_item_version",
        "policy_id",
        "policy_version",
        "definition",
        "definition_hash",
        "disclosure_authorization_id",
        "disclosure_scope_hash",
        "authorization_state",
        "effective_selection_keys",
        "destination",
        "selections",
        "outcome",
        "body_text",
        "input_hash",
        "content_hash",
    }
    require(set(details) == required and details["contract_version"] == DETAILS_CONTRACT)
    require(codec.definition_reference(details["definition"]) == details["definition"])
    require(codec.normalize_destination(details["destination"]) == details["destination"])
    for key in ("policy_id", "disclosure_authorization_id"):
        codec.identity(details[key], key)
    for key in ("definition_hash", "disclosure_scope_hash", "input_hash", "content_hash"):
        require(isinstance(details[key], str) and re.fullmatch(r"[0-9a-f]{64}", details[key]) is not None)
    require(
        (details["attempt_id"], details["rendered_item_version"], details["policy_version"])
        == (base.attempt_id, str(base.rendered_item_version), str(base.rendered_item_version))
    )
    require(
        details["base_rendering_input_hash"] == base.rendering_input_hash
        and details["base_rendered_content_hash"] == base.rendered_content_hash
    )
    require(details["authorization_state"] in {"active", "revoked", "unavailable", "scope_mismatch"})
    require(details["effective_selection_keys"] == sorted(set(details["effective_selection_keys"])))
    require(1 <= len(details["selections"]) <= 8 and len(details["effective_selection_keys"]) <= 8)
    keys = []
    for selection in details["selections"]:
        keys.append(selection["selection_key"])
        codec.normalize_catalog_key(selection["selection_key"], "selection_key")
        included = selection["outcome"] == "included"
        require(set(selection) == ({"selection_key", "outcome", "value", "source"} if included else {"selection_key", "outcome"}))
        require(included or selection["outcome"] in OMISSIONS)
        if selection["selection_key"] not in details["effective_selection_keys"]:
            require(selection["outcome"] == "not_selected")
        elif details["authorization_state"] != "active":
            require(selection["outcome"] == "disclosure_unavailable")
        if included:
            require(details["authorization_state"] == "active" and 1 <= len(selection["value"]) <= 120)
            require(_normalized_text(selection["value"], "value") == selection["value"])
            source = selection["source"]
            require(set(source) - {"location_id"} == {"facet_key", "facet_schema_revision_id", "archetype_facet_binding_id", "field_key"})
            for key in ("facet_key", "field_key"):
                codec.normalize_catalog_key(source[key], key)
            for key in set(source) - {"facet_key", "field_key"}:
                codec.identity(source[key], key)
    require(len(keys) == len(set(keys)) and set(details["effective_selection_keys"]) <= set(keys))
    included = any(s["outcome"] == "included" for s in details["selections"])
    overflow = any(s["outcome"] == "suffix_overflow" for s in details["selections"])
    require(details["outcome"] == ("details_included" if included else "suffix_overflow" if overflow else "ordinary_only"))
    require(not included or not overflow)
    require(not overflow or details["authorization_state"] == "active")
    require(1 <= len(details["body_text"]) <= 1024)
    require(included or details["body_text"] == base.body_text)
    require(
        details["input_hash"]
        == hash_canonical_json(
            {k: v for k, v in details.items() if k not in {"input_hash", "content_hash", "body_text"}} | {"canonical_json_version": CANON}
        )
    )
    require(
        details["content_hash"]
        == hash_canonical_json({"contract_version": DETAILS_CONTRACT, "canonical_json_version": CANON, "body_text": details["body_text"]})
    )
    input_facts = preimage(
        "spine.notification-rendering-input-hash.v2",
        base_rendering_input_hash=base.rendering_input_hash,
        details_input_hash=details["input_hash"],
    )
    input_hash = hash_canonical_json(input_facts)
    content = preimage("spine.notification-rendering-content-hash.v2", rendering_input_hash=input_hash, body_text=details["body_text"])
    content_hash = hash_canonical_json(content)
    identity = preimage(
        "spine.notification-rendering-id.v2",
        attempt_id=base.attempt_id,
        rendering_input_hash=input_hash,
        rendered_content_hash=content_hash,
    )
    value = DetailedNotificationRendering(
        "notification_rendering_" + hash_canonical_json(identity),
        base.attempt_id,
        base.work_instance_id,
        input_hash,
        content_hash,
        details["body_text"],
        base.phrase_kind,
        base.source_input,
        base.phrase_facts,
        input_facts,
        content,
        identity,
        base,
        details,
    )
    require(len(canonical_json_bytes(details)) <= 16384 and len(canonical_json_bytes(value.as_view())) <= 32768)
    return value


def decode_detailed(value: dict[str, Any]) -> DetailedNotificationRendering:
    try:
        require(
            set(value)
            == {
                "rendering_contract",
                "notification_rendering_id",
                "base_rendering",
                "details",
                "rendering_input_hash",
                "rendered_content_hash",
                "body_text",
            }
        )
        require(value["rendering_contract"] == RENDERING_V2)
        result = assemble(decode_ordinary(value["base_rendering"]), value["details"])
        require(result.as_view() == value)
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise SpineValidationError("notification_rendering_persistence_conflict", "invalid detailed rendering evidence") from exc
