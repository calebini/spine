"""Pure normalization for relative temporal binding revisions."""

from __future__ import annotations

from collections.abc import Mapping

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json


def binding_revision_preimage(
    *,
    binding: Mapping[str, object],
    source: Mapping[str, object],
    source_scope: str,
    offset_seconds: int,
    target: Mapping[str, str],
    target_item_version: int,
    resolution_kind: str,
) -> dict[str, object]:
    """Return the exact semantic preimage for one immutable binding revision."""

    preimage: dict[str, object] = {
        "binding_revision_hash_derivation_version": "spine.normalized-temporal-binding-revision-hash.v1",
        "binding_contract": "spine.relative-temporal-binding.v1",
        "binding_normalization_version": "spine.relative-temporal-binding-normalization.v1",
        "canonical_json_version": "spine.canonical-json.v1",
        "source_item_id": binding["source_item_id"],
        "source_anchor_role": "event_start",
        "target_item_id": binding["target_item_id"],
        "target_anchor_role": "task_due",
        "relationship_id": binding["relationship_id"],
        "relationship_type": "part_of",
        "binding_mode": binding["binding_mode"],
        "source_scope": source_scope,
        "source_target_version": str(source["source_target_version"]),
        "source_scheduled_fact": source["source_scheduled_fact"],
        "resolved_source_utc": source["resolved_source_utc"],
        "offset_basis": "elapsed",
        "offset_seconds": str(offset_seconds),
        "target_item_version": str(target_item_version),
        "target_local_date": target["local_date"],
        "target_local_time": target["local_time"],
        "timezone": target["timezone"],
        "timezone_database_version": target["timezone_database_version"],
        "resolved_target_utc": target["utc_instant"],
        "resolution_kind": resolution_kind,
    }
    if binding.get("source_terminal_behavior") is not None:
        preimage["source_terminal_behavior"] = binding["source_terminal_behavior"]
    if source_scope == "item":
        preimage["source_anchor_id"] = source["source_anchor_id"]
    else:
        preimage["target_occurrence_selector"] = source["target_occurrence_selector"]
        preimage["source_recurrence_revision_id"] = source["source_recurrence_revision_id"]
    return preimage


def revision_value(
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


def source_from_occurrence(recurrence: Mapping[str, object], occurrence: Mapping[str, object]) -> dict[str, object]:
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


def source_from_prior(prior: Mapping[str, object]) -> dict[str, object]:
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
