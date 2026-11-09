"""Internal R1 canonical identities and immutable payload decoders.

No command registration, task generation, clock, persistence or sending lives here.
The command-specific normalization layer is a later delivery checkpoint.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError

CONTRACT = "spine.recurring-related-tasks.v1"
CANONICAL = "spine.canonical-json.v1"
MAX_INTEGER = 9223372036854775807
IDENTITIES = {
    "rule": ("related_task_rule", {"owner", "rule_key"}, set()),
    "rule_revision": (
        "related_task_rule_revision",
        {"related_task_rule_id", "revision_index", "configuration_hash"},
        {"prior_revision_id"},
    ),
    "assignment": ("related_task_assignment", {"related_task_rule_id", "initial_selector"}, set()),
    "generation": ("related_task_generation", {"assignment_id", "generation_index"}, set()),
    "proof": ("related_task_proof", {"related_task_rule_id", "proof_kind", "proof_payload"}, set()),
    "assignment_revision": (
        "related_task_assignment_revision",
        {"assignment_id", "change_version", "state_hash"},
        {"prior_assignment_revision_id"},
    ),
    "intent": ("related_task_intent", {"related_task_rule_id", "rule_change_version", "intent_kind", "intent_payload"}, set()),
    "suppression": ("related_task_suppression", {"assignment_id", "target_generation_id"}, set()),
}
STATE_FIELDS = frozenset(
    {
        "generation_id",
        "selector",
        "occurrence_key",
        "source_item_version",
        "recurrence_revision_id",
        "proof_id",
        "task_item_id",
        "task_item_version",
        "temporal_binding_revision_id",
        "adopted_rule_revision_id",
        "managed_baseline",
        "disposition",
        "restoration_veto",
        "reason",
    }
)
PROOF_COMMON = frozenset(
    {
        "source_item_id",
        "source_item_version",
        "recurrence_set_id",
        "recurrence_revision_id",
        "normalized_recurrence_set_hash",
        "selector",
        "occurrence_key",
        "lineage_ids",
    }
)
PROOF_FIELDS = {
    "enrollment": ({"enrolled_recurrence_revision_id"}, set()),
    "identity": (set(), {"prior_proof_id", "prior_selector"}),
    "carry_forward": ({"prior_proof_id", "prior_selector", "hops"}, set()),
    "component_candidate": ({"basis_revision_id", "component_selector", "hops"}, set()),
    "new_rdate": ({"rdate_id", "prior_recurrence_revision_id"}, set()),
    "excluded": ({"prior_proof_id", "prior_selector", "exdate_id", "exclusion_active", "actionable"}, set()),
    "occurrence_cancelled": ({"prior_proof_id", "prior_selector", "override_id", "lifecycle", "actionable"}, set()),
    "source_cancelled": ({"cancelled_event_version", "event_status"}, set()),
}


def invariant(condition: object, detail: str = "invalid recurring-task storage") -> None:
    if not condition:
        raise SpineValidationError("environment_failure:recurring_tasks", detail)


def integer(value: object, *, minimum: int = 0) -> int:
    invariant(
        isinstance(value, str) and 0 < len(value) <= 19 and value.isascii() and value.isdecimal() and str(int(value)) == value,
        "noncanonical recurring-task counter",
    )
    result = int(str(value))
    invariant(minimum <= result <= MAX_INTEGER, "recurring-task counter out of bounds")
    return result


def closed(value: Mapping[str, Any], required: set[str] | frozenset[str], optional: set[str] | frozenset[str] = frozenset()) -> None:
    invariant(isinstance(value, Mapping), "expected recurring-task object")
    invariant(required <= value.keys() <= required | optional, "recurring-task payload fields mismatch")
    canonical_json_bytes(dict(value))


def derive(kind: str, fields: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    invariant(kind in IDENTITIES, "unknown recurring-task derivation")
    prefix, required, optional = IDENTITIES[kind]
    closed(fields, required, optional)
    preimage = {
        "derivation_version": "spine." + prefix.replace("_", "-") + "-id.v1",
        "contract_version": CONTRACT,
        "canonical_json_version": CANONICAL,
        **fields,
    }
    return prefix + "_" + hashlib.sha256(canonical_json_bytes(preimage)).hexdigest(), preimage


def payload_hash(kind: str, value: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    invariant(kind in {"configuration", "state"}, "unknown recurring-task payload hash")
    field, version = (
        ("configuration", "spine.related-task-rule-configuration.v1")
        if kind == "configuration"
        else ("state", "spine.related-task-assignment-state.v1")
    )
    preimage: dict[str, object] = {
        "derivation_version": version,
        "contract_version": CONTRACT,
        "canonical_json_version": CANONICAL,
        field: dict(value),
    }
    return hashlib.sha256(canonical_json_bytes(preimage)).hexdigest(), preimage


def decode(text: str) -> dict[str, Any]:
    """Reject duplicate keys, noncanonical bytes and values outside canonical JSON."""

    def pairs(entries: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in entries:
            invariant(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=pairs)
        invariant(isinstance(value, dict), "expected recurring-task JSON object")
        assert isinstance(value, dict)
        invariant(canonical_json_bytes(value).decode() == text, "noncanonical stored JSON")
    except (ValueError, TypeError, UnicodeError, RecursionError, SpineValidationError) as exc:
        raise SpineValidationError("environment_failure:recurring_tasks", "invalid canonical stored JSON") from exc
    return value


def validate_state(value: Mapping[str, Any]) -> None:
    closed(value, STATE_FIELDS, {"pending_intent_id"})
    invariant(type(value["restoration_veto"]) is bool, "invalid restoration veto")
    invariant(
        value["disposition"] in {"governed", "source_cancelled", "done", "manual_cancelled", "detached", "suppressed", "decision_required"}
    )
    for field in ("source_item_version", "task_item_version"):
        integer(value[field], minimum=1)
    closed(
        value["managed_baseline"], {"task_template", "offset_basis", "offset_seconds", "notification_plan", "delivery", "materialization"}
    )


def validate_proof(kind: str, value: Mapping[str, Any]) -> None:
    invariant(kind in PROOF_FIELDS, "unknown source proof kind")
    required, optional = PROOF_FIELDS[kind]
    common = PROOF_COMMON - {"selector", "occurrence_key"} if kind == "source_cancelled" else PROOF_COMMON
    closed(value, common | required, optional)
    integer(value["source_item_version"], minimum=1)
    invariant(isinstance(value["lineage_ids"], list) and all(isinstance(v, str) for v in value["lineage_ids"]), "invalid lineage set")
    invariant(value["lineage_ids"] == sorted(set(value["lineage_ids"])), "invalid lineage order")
    invariant(("prior_proof_id" in value) == ("prior_selector" in value), "unpaired prior proof")
    if "hops" in value:
        invariant(isinstance(value["hops"], list), "expected source proof hops")
        for hop in value["hops"]:
            closed(hop, {"prior_revision_id", "new_revision_id", "prior_selector", "selector", "lineage_ids"})
            ids = hop["lineage_ids"]
            invariant(isinstance(ids, list) and all(isinstance(v, str) for v in ids), "invalid hop lineage")
            invariant(ids == sorted(set(ids)), "noncanonical hop lineage order")
    if kind == "component_candidate":
        closed(value["component_selector"], {"source_kind", "selector"})
        invariant(value["component_selector"]["source_kind"] in {"rule", "rdate"})
    if kind == "source_cancelled":
        invariant(value["event_status"] == "cancelled" and not value["lineage_ids"])
        integer(value["cancelled_event_version"], minimum=1)
    else:
        invariant(occurrence_key(value["selector"]) == value["occurrence_key"], "proof occurrence key mismatch")
    if kind == "excluded":
        invariant(value["exclusion_active"] is True and value["actionable"] is False)
    if kind == "occurrence_cancelled":
        invariant(value["lifecycle"] == "cancelled" and value["actionable"] is False)


def occurrence_key(selector: Mapping[str, object]) -> str:
    preimage = {
        "derivation_version": "spine.recurrence-occurrence-key.v2",
        "contract_version": "spine.recurrence.contract.v1",
        "normalization_version": "spine.recurrence.normalization.v1",
        "canonical_json_version": CANONICAL,
        "target_occurrence_selector": dict(selector),
    }
    raw = canonical_json_bytes(preimage)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode() + "." + hashlib.sha256(raw).hexdigest()
