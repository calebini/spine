"""Deterministic recurrence-occurrence provenance identities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_set import generated_id


@dataclass(frozen=True)
class DerivedOccurrenceProvenance:
    value: dict[str, object]
    slot_key_preimage: dict[str, object]
    content_hash_preimage: dict[str, object]
    provenance_id_preimage: dict[str, object]


def recurrence_set_identity_preimage(recurrence: Mapping[str, object]) -> dict[str, object]:
    value: dict[str, object] = {
        "derivation_version": "spine.recurrence-set-id.v1",
        "contract_version": recurrence["contract_version"],
        "normalization_version": recurrence["normalization_version"],
        "canonical_json_version": recurrence["canonical_json_version"],
        "source_item_id": recurrence["source_item_id"],
        "seed_anchor_id": recurrence["seed_anchor_id"],
        "created_item_version": recurrence["created_item_version"],
        "time_basis": recurrence["time_basis"],
    }
    if recurrence.get("timezone") is not None:
        value["timezone"] = recurrence["timezone"]
        value["timezone_database_version"] = recurrence["timezone_database_version"]
    return value


def derive_occurrence_provenance(
    *,
    occurrence: Mapping[str, object],
    recurrence: Mapping[str, object],
    item: Mapping[str, Any],
    consumer: str,
    producer: str | None,
    range_basis: str,
    range_start: str,
    range_end: str,
    created_at_utc: str,
) -> DerivedOccurrenceProvenance:
    slot_key, slot_preimage = generated_id(
        "occurrence_provenance_slot",
        "spine.occurrence-provenance-slot.v1",
        {
            "consumer": consumer,
            "item_id": item["item_id"],
            "recurrence_set_id": recurrence["recurrence_set_id"],
            "range_basis": range_basis,
            "range_start": range_start,
            "range_end": range_end,
            "original_scheduled_fact": occurrence["original_scheduled_fact"],
        },
    )
    timezone_facts = _timezone_facts(occurrence, recurrence)
    identity_fields: dict[str, object] = {
        "occurrence_provenance_slot_key": slot_key,
        "source_item_version": recurrence["source_item_version"],
        "shell_status": item["status"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
        "occurrence_key": occurrence["occurrence_key"],
        "original_scheduled_fact": occurrence["original_scheduled_fact"],
        "expressed_scheduled_fact": occurrence["expressed_scheduled_fact"],
        **timezone_facts,
        "source_rule_ids": occurrence["source_rule_ids"],
        "source_rdate_ids": occurrence["source_rdate_ids"],
        "source_entries": occurrence["source_entries"],
        "lifecycle": occurrence["lifecycle"],
        "actionable": occurrence["actionable"],
        "recurrence_set_identity_preimage": recurrence_set_identity_preimage(recurrence),
    }
    if producer is not None:
        identity_fields["producer"] = producer
    if item.get("archived_at_utc") is not None:
        identity_fields["archived_at_utc"] = item["archived_at_utc"]
    if occurrence.get("override_id") is not None:
        identity_fields["override_id"] = occurrence["override_id"]
    provenance_id, provenance_preimage = generated_id(
        "occurrence_provenance",
        "spine.occurrence-provenance-id.v2",
        identity_fields,
    )
    semantic_snapshot: dict[str, object] = {
        "occurrence_provenance_slot_key": slot_key,
        "consumer": consumer,
        "item_id": item["item_id"],
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "range_basis": range_basis,
        "range_start": range_start,
        "range_end": range_end,
        **identity_fields,
    }
    content_preimage = {
        "derivation_version": "spine.occurrence-provenance-content-hash.v2",
        "contract_version": recurrence["contract_version"],
        "normalization_version": recurrence["normalization_version"],
        "canonical_json_version": recurrence["canonical_json_version"],
        "provenance": semantic_snapshot,
    }
    content_hash = hash_canonical_json(content_preimage)
    selector = occurrence["target_occurrence_selector"]
    value = {
        "occurrence_provenance_id": provenance_id,
        "occurrence_provenance_slot_key": slot_key,
        "producer": producer,
        "consumer": consumer,
        "item_id": item["item_id"],
        "source_item_version": recurrence["source_item_version"],
        "shell_status": item["status"],
        "archived_at_utc": item.get("archived_at_utc"),
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "normalized_recurrence_set_hash": recurrence["normalized_recurrence_set_hash"],
        "target_occurrence_selector": selector,
        "occurrence_id": occurrence["occurrence_id"],
        "occurrence_key": occurrence["occurrence_key"],
        "range_basis": range_basis,
        "range_start": range_start,
        "range_end": range_end,
        "original_scheduled_fact": occurrence["original_scheduled_fact"],
        "expressed_scheduled_fact": occurrence["expressed_scheduled_fact"],
        **timezone_facts,
        "override_id": occurrence.get("override_id"),
        "lifecycle": occurrence["lifecycle"],
        "actionable": occurrence["actionable"],
        "source_entries": occurrence["source_entries"],
        "content_hash": content_hash,
        "contract_version": recurrence["contract_version"],
        "normalization_version": recurrence["normalization_version"],
        "canonical_json_version": recurrence["canonical_json_version"],
        "management_status": "active",
        "created_at_utc": created_at_utc,
    }
    return DerivedOccurrenceProvenance(
        value=value,
        slot_key_preimage=slot_preimage,
        content_hash_preimage=content_preimage,
        provenance_id_preimage=provenance_preimage,
    )


def _timezone_facts(occurrence: Mapping[str, object], recurrence: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    if recurrence.get("timezone") is not None:
        result["timezone"] = recurrence["timezone"]
        result["timezone_database_version"] = recurrence["timezone_database_version"]
    resolution = occurrence.get("timezone_resolution")
    if isinstance(resolution, Mapping):
        result["timezone_resolution_kind"] = resolution["resolution_kind"]
        result["timezone_utc_instant"] = resolution["utc_instant"]
        result["timezone_offset_seconds"] = resolution["offset_seconds"]
    return result
