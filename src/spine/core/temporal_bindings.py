"""Pure normalization for relative temporal binding revisions."""

from __future__ import annotations

from collections.abc import Mapping


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
