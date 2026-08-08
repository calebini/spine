"""Canonical construction of successor recurrence revisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_set import NormalizedRecurrenceSet, generated_id
from spine.core.schedule import normalize_rule, parse_scheduled_fact


def build_successor_recurrence_revision(
    current: Mapping[str, object],
    *,
    source_item_version: str,
    command_id: str,
    segments: Sequence[Mapping[str, object]] | None = None,
    rules: Sequence[Mapping[str, object]] | None = None,
    rdates: Sequence[Mapping[str, object]] | None = None,
    exdates: Sequence[Mapping[str, object]] | None = None,
    overrides: Sequence[Mapping[str, object]] | None = None,
) -> NormalizedRecurrenceSet:
    """Build a complete immutable successor for unchanged segment topology."""

    time_basis = str(current["time_basis"])
    prior_revision_id = str(current["recurrence_revision_id"])
    revision_number = str(int(str(current["revision_number"])) + 1)
    segment_rows = _object_array(current["segments"])
    segment_preimages, segment_ref_by_id = _normalize_segments(
        segments if segments is not None else segment_rows,
        prior_revision_id=prior_revision_id,
        command_id=command_id,
        explicit=segments is not None,
    )

    rule_preimages = _normalize_rules(
        rules if rules is not None else _object_array(current["rules"]),
        time_basis=time_basis,
        segment_ref_by_id=segment_ref_by_id,
    )
    rdate_preimages = _normalize_rdates(
        rdates if rdates is not None else _object_array(current["rdates"]),
        time_basis=time_basis,
        segment_ref_by_id=segment_ref_by_id,
    )
    exdate_preimages = _normalize_exdates(
        exdates if exdates is not None else _object_array(current["exdates"]),
        segment_ref_by_id=segment_ref_by_id,
    )
    override_preimages = _normalize_overrides(
        overrides if overrides is not None else _object_array(current["overrides"]),
        time_basis=time_basis,
        segment_ref_by_id=segment_ref_by_id,
    )
    hash_preimage: dict[str, object] = {
        "derivation_version": "normalized_recurrence_set_hash.v1",
        "contract_version": current["contract_version"],
        "normalization_version": current["normalization_version"],
        "canonical_json_version": current["canonical_json_version"],
        "recurrence_set_id": current["recurrence_set_id"],
        "revision_number": revision_number,
        "source_item_id": current["source_item_id"],
        "created_item_version": current["created_item_version"],
        "source_item_version": source_item_version,
        "seed_anchor_id": current["seed_anchor_id"],
        "time_basis": time_basis,
        "segments": segment_preimages,
        "rules": rule_preimages,
        "rdates": rdate_preimages,
        "exdates": [{key: item for key, item in value.items() if key != "target_occurrence_key"} for value in exdate_preimages],
        "overrides": [{key: item for key, item in value.items() if key != "target_occurrence_key"} for value in override_preimages],
    }
    if current.get("timezone") is not None:
        hash_preimage["timezone"] = current["timezone"]
        hash_preimage["timezone_database_version"] = current["timezone_database_version"]
    normalized_hash = hash_canonical_json(hash_preimage)
    revision_id, revision_preimage = generated_id(
        "recurrence_revision",
        "spine.recurrence-revision-id.v1",
        {
            "recurrence_set_id": current["recurrence_set_id"],
            "revision_number": revision_number,
            "normalized_recurrence_set_hash": normalized_hash,
            "prior_recurrence_revision_id": prior_revision_id,
            "command_id": command_id,
        },
    )
    segments, segment_ids, segment_id_preimages = _materialize_segments(segment_preimages, revision_id)
    public_rules, rule_id_preimages = _materialize_rules(rule_preimages, revision_id, segment_ids)
    public_rdates, rdate_id_preimages = _materialize_rdates(rdate_preimages, revision_id, segment_ids)
    public_exdates = _materialize_exdates(exdate_preimages, revision_id, segment_ids)
    public_overrides = _materialize_overrides(override_preimages, revision_id, segment_ids)
    value: dict[str, object] = {
        "contract_version": current["contract_version"],
        "normalization_version": current["normalization_version"],
        "canonical_json_version": current["canonical_json_version"],
        "recurrence_set_id": current["recurrence_set_id"],
        "recurrence_revision_id": revision_id,
        "prior_recurrence_revision_id": prior_revision_id,
        "revision_number": revision_number,
        "source_item_id": current["source_item_id"],
        "created_item_version": current["created_item_version"],
        "source_item_version": source_item_version,
        "seed_anchor_id": current["seed_anchor_id"],
        "time_basis": time_basis,
        "normalized_recurrence_set_hash": normalized_hash,
        "segments": segments,
        "rules": public_rules,
        "rdates": public_rdates,
        "exdates": public_exdates,
        "overrides": public_overrides,
    }
    if current.get("timezone") is not None:
        value["timezone"] = current["timezone"]
        value["timezone_database_version"] = current["timezone_database_version"]
    return NormalizedRecurrenceSet(
        value=value,
        recurrence_set_id_preimage={},
        normalized_hash_preimage=hash_preimage,
        recurrence_revision_id_preimage=revision_preimage,
        segment_id_preimages=tuple(segment_id_preimages),
        rule_id_preimages=tuple(rule_id_preimages),
        rdate_id_preimages=tuple(rdate_id_preimages),
    )


def _normalize_segments(
    rows: Sequence[Mapping[str, object]],
    *,
    prior_revision_id: str,
    command_id: str,
    explicit: bool,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    pending: list[tuple[str, dict[str, object]]] = []
    for position, row in enumerate(rows):
        token = str(row.get("segment_ref") or row.get("segment_id") or f"draft:{position}")
        preimage: dict[str, object] = {
            "active_start": row["active_start"],
            "source_revision_id": row.get("source_revision_id", prior_revision_id),
            "status": str(row.get("status", "active")),
            "created_by_command_id": row.get("created_by_command_id", command_id),
        }
        if row.get("active_end") is not None:
            preimage["active_end"] = row["active_end"]
        parent = row.get("lineage_parent_segment_id")
        if parent is None and not explicit and row.get("segment_id") is not None:
            parent = row["segment_id"]
        if parent is not None:
            preimage["lineage_parent_segment_id"] = parent
        if row.get("reason_code") is not None:
            preimage["reason_code"] = row["reason_code"]
        pending.append((token, preimage))
    pending.sort(key=lambda entry: (str(entry[1]["active_start"]), canonical_json_bytes(entry[1])))
    values: list[dict[str, object]] = []
    refs: dict[str, str] = {}
    for index, (token, preimage) in enumerate(pending):
        ref = str(index)
        if token in refs:
            raise ValueError(f"duplicate recurrence segment token: {token}")
        refs[token] = ref
        values.append({"segment_index": ref, **preimage})
    return values, refs


def _normalize_rules(
    rows: Sequence[Mapping[str, object]],
    *,
    time_basis: str,
    segment_ref_by_id: Mapping[str, str],
) -> list[dict[str, object]]:
    values: dict[bytes, dict[str, object]] = {}
    for index, row in enumerate(rows):
        segment_ref = _segment_ref(row, segment_ref_by_id)
        authoring = {
            key: row[key]
            for key in (
                "frequency",
                "interval",
                "seed",
                "start_bound",
                "end_condition",
                "by_month",
                "by_month_day",
                "by_weekday",
                "by_set_position",
                "week_start",
            )
            if key in row
        }
        normalized = normalize_rule(authoring, time_basis=time_basis, field=f"rules[{index}]").as_contract()
        value = {"segment_ref": segment_ref, **normalized, "status": str(row.get("status", "active"))}
        if row.get("rule_duplicate_index") is not None:
            value["rule_duplicate_index"] = str(row["rule_duplicate_index"])
        values[canonical_json_bytes(value)] = value
    return sorted(values.values(), key=lambda value: (str(value["segment_ref"]), canonical_json_bytes(value)))


def _normalize_rdates(
    rows: Sequence[Mapping[str, object]],
    *,
    time_basis: str,
    segment_ref_by_id: Mapping[str, str],
) -> list[dict[str, object]]:
    values: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        segment_ref = _segment_ref(row, segment_ref_by_id)
        fact = str(row["scheduled_fact"])
        parse_scheduled_fact(fact, time_basis=time_basis, field="rdates.scheduled_fact")
        value: dict[str, object] = {
            "segment_ref": segment_ref,
            "scheduled_fact": fact,
            "status": str(row.get("status", "active")),
        }
        if row.get("rdate_duplicate_index") is not None:
            value["rdate_duplicate_index"] = str(row["rdate_duplicate_index"])
        values[(segment_ref, fact)] = value
    return sorted(values.values(), key=lambda value: (str(value["segment_ref"]), str(value["scheduled_fact"])))


def _normalize_exdates(rows: Sequence[Mapping[str, object]], *, segment_ref_by_id: Mapping[str, str]) -> list[dict[str, object]]:
    values = []
    for row in rows:
        value = {
            "segment_ref": _segment_ref(row, segment_ref_by_id),
            "target_occurrence_selector": row["target_occurrence_selector"],
            "scheduled_fact": row["scheduled_fact"],
            "reason_code": row["reason_code"],
            "status": str(row.get("status", "active")),
            "target_occurrence_key": row["target_occurrence_key"],
        }
        if row.get("prior_target_occurrence_key") is not None:
            value["prior_target_occurrence_key"] = row["prior_target_occurrence_key"]
        values.append(value)
    return sorted(values, key=lambda value: (str(value["segment_ref"]), canonical_json_bytes(value)))


def _normalize_overrides(
    rows: Sequence[Mapping[str, object]],
    *,
    time_basis: str,
    segment_ref_by_id: Mapping[str, str],
) -> list[dict[str, object]]:
    values = []
    for row in rows:
        if row.get("expressed_scheduled_fact") is not None:
            parse_scheduled_fact(str(row["expressed_scheduled_fact"]), time_basis=time_basis, field="overrides.expressed_scheduled_fact")
        value = {
            key: row[key]
            for key in (
                "target_occurrence_key",
                "target_occurrence_selector",
                "override_kind",
                "revision_key",
                "expressed_scheduled_fact",
                "common_detail_patch",
                "event_detail_patch",
                "task_detail_patch",
                "lifecycle",
                "reason_code",
                "prior_target_occurrence_key",
            )
            if row.get(key) is not None
        }
        value.update({"segment_ref": _segment_ref(row, segment_ref_by_id), "status": str(row.get("status", "active"))})
        values.append(value)
    return sorted(values, key=lambda value: (str(value["segment_ref"]), canonical_json_bytes(value)))


def _materialize_segments(
    values: list[dict[str, object]], revision_id: str
) -> tuple[list[dict[str, object]], dict[str, str], list[dict[str, object]]]:
    public, ids, preimages = [], {}, []
    for value in values:
        generated, preimage = generated_id(
            "recurrence_segment", "spine.recurrence-segment-id.v1", {"recurrence_revision_id": revision_id, **value}
        )
        ids[str(value["segment_index"])] = generated
        public.append({"segment_id": generated, **value})
        preimages.append(preimage)
    return public, ids, preimages


def _materialize_rules(
    values: list[dict[str, object]], revision_id: str, segment_ids: Mapping[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    public, preimages = [], []
    for value in values:
        generated, preimage = generated_id(
            "recurrence_rule", "spine.recurrence-rule-id.v1", {"recurrence_revision_id": revision_id, **value}
        )
        ref = str(value["segment_ref"])
        public.append(
            {"rule_id": generated, "segment_id": segment_ids[ref], **{key: item for key, item in value.items() if key != "segment_ref"}}
        )
        preimages.append(preimage)
    return public, preimages


def _materialize_rdates(
    values: list[dict[str, object]], revision_id: str, segment_ids: Mapping[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    public, preimages = [], []
    for value in values:
        generated, preimage = generated_id(
            "recurrence_rdate", "spine.recurrence-rdate-id.v1", {"recurrence_revision_id": revision_id, **value}
        )
        ref = str(value["segment_ref"])
        public.append(
            {"rdate_id": generated, "segment_id": segment_ids[ref], **{key: item for key, item in value.items() if key != "segment_ref"}}
        )
        preimages.append(preimage)
    return public, preimages


def _materialize_exdates(values: list[dict[str, object]], revision_id: str, segment_ids: Mapping[str, str]) -> list[dict[str, object]]:
    public = []
    for value in values:
        identity = {key: item for key, item in value.items() if key not in {"target_occurrence_key", "prior_target_occurrence_key"}}
        generated, _ = generated_id(
            "recurrence_exdate", "spine.recurrence-exdate-id.v2", {"recurrence_revision_id": revision_id, **identity}
        )
        ref = str(value["segment_ref"])
        public.append(
            {"exdate_id": generated, "segment_id": segment_ids[ref], **{key: item for key, item in value.items() if key != "segment_ref"}}
        )
    return public


def _materialize_overrides(values: list[dict[str, object]], revision_id: str, segment_ids: Mapping[str, str]) -> list[dict[str, object]]:
    public = []
    for value in values:
        identity = {key: item for key, item in value.items() if key not in {"target_occurrence_key", "prior_target_occurrence_key"}}
        generated, _ = generated_id(
            "recurrence_override", "spine.recurrence-override-id.v2", {"recurrence_revision_id": revision_id, **identity}
        )
        ref = str(value["segment_ref"])
        public.append(
            {"override_id": generated, "segment_id": segment_ids[ref], **{key: item for key, item in value.items() if key != "segment_ref"}}
        )
    return public


def _segment_ref(row: Mapping[str, object], refs: Mapping[str, str]) -> str:
    if row.get("segment_ref") is not None:
        value = str(row["segment_ref"])
        return refs.get(value, value)
    return refs[str(row["segment_id"])]


def _object_array(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [dict(row) for row in value if isinstance(row, Mapping)]


def derive_recurrence_lineage(
    current: Mapping[str, object],
    successor: Mapping[str, object],
    *,
    command_id: str,
    effect: str,
) -> list[dict[str, object]]:
    """Derive deterministic, inspectable lineage for one changed revision."""

    drafts: list[dict[str, object]] = []
    for segment in _object_array(successor["segments"]):
        parent = segment.get("lineage_parent_segment_id")
        drafts.append(
            {
                "lineage_role": "segment_revision",
                **({"prior_segment_id": parent} if parent is not None else {}),
                "new_segment_id": segment["segment_id"],
                "effect": str(segment["status"]),
            }
        )
    for collection, id_field in (
        ("rules", "rule_id"),
        ("rdates", "rdate_id"),
        ("exdates", "exdate_id"),
        ("overrides", "override_id"),
    ):
        prior_rows = _object_array(current[collection])
        for child in _object_array(successor[collection]):
            prior_id = _find_prior_child_id(child, prior_rows, id_field=id_field)
            drafts.append(
                {
                    "lineage_role": collection[:-1] + "_revision",
                    **({"prior_child_id": prior_id} if prior_id is not None else {}),
                    "new_child_id": child[id_field],
                    "effect": "copied" if prior_id is not None else "created",
                }
            )
    result: list[dict[str, object]] = []
    for index, draft in enumerate(drafts):
        identity: dict[str, object] = {
            "command_id": command_id,
            "recurrence_set_id": successor["recurrence_set_id"],
            "prior_recurrence_revision_id": current["recurrence_revision_id"],
            "new_recurrence_revision_id": successor["recurrence_revision_id"],
            **draft,
            "lineage_index": str(index),
        }
        lineage_id, _ = generated_id("recurrence_lineage", "spine.recurrence-lineage-id.v1", identity)
        payload = {**identity, "command_effect": effect}
        result.append(
            {
                "lineage_id": lineage_id,
                **identity,
                "payload_hash": hash_canonical_json(payload),
            }
        )
    return result


def _find_prior_child_id(
    child: Mapping[str, object],
    prior_rows: Sequence[Mapping[str, object]],
    *,
    id_field: str,
) -> str | None:
    child_key = _child_lineage_key(child, id_field=id_field)
    matches = [row for row in prior_rows if _child_lineage_key(row, id_field=id_field) == child_key]
    return str(matches[0][id_field]) if len(matches) == 1 else None


def _child_lineage_key(child: Mapping[str, object], *, id_field: str) -> bytes:
    ignored = {id_field, "segment_id", "prior_target_occurrence_key"}
    return canonical_json_bytes({key: child[key] for key in sorted(child) if key not in ignored})
