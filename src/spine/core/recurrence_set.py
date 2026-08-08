"""Canonical recurrence-set normalization and content-addressed identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.schedule import (
    CANONICAL_JSON_VERSION,
    RECURRENCE_CONTRACT_VERSION,
    RECURRENCE_NORMALIZATION_VERSION,
    normalize_rule,
    parse_scheduled_fact,
    validate_timezone_context,
)

AUTHORING_VERSION = "spine.recurrence-authoring.v1"


@dataclass(frozen=True)
class NormalizedRecurrenceSet:
    """A first canonical recurrence revision plus its auditable preimages."""

    value: dict[str, object]
    recurrence_set_id_preimage: dict[str, object]
    normalized_hash_preimage: dict[str, object]
    recurrence_revision_id_preimage: dict[str, object]
    segment_id_preimages: tuple[dict[str, object], ...]
    rule_id_preimages: tuple[dict[str, object], ...]
    rdate_id_preimages: tuple[dict[str, object], ...]


def generated_id(prefix: str, derivation_version: str, fields: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Derive one recurrence id and return the exact versioned preimage."""

    preimage = {
        "derivation_version": derivation_version,
        "contract_version": RECURRENCE_CONTRACT_VERSION,
        "normalization_version": RECURRENCE_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        **fields,
    }
    return f"{prefix}_{hash_canonical_json(preimage)}", preimage


def normalize_initial_recurrence_set(
    authoring: object,
    *,
    source_item_id: str,
    seed_anchor_id: str,
    seed_scheduled_fact: str,
    created_item_version: str,
    source_item_version: str,
    command_id: str | None = None,
    require_available_timezone_data: bool = True,
) -> NormalizedRecurrenceSet:
    """Normalize initial authoring and derive revision-one identities.

    The owning item command calls this before persistence, then writes the returned
    value and its item rows in the same database transaction.
    """

    root = _authoring_object(authoring)
    _required_text(source_item_id, "source_item_id")
    _required_text(seed_anchor_id, "seed_anchor_id")
    _positive_decimal(created_item_version, "created_item_version")
    _positive_decimal(source_item_version, "source_item_version")
    if command_id is not None:
        _required_text(command_id, "command_id")

    time_basis = root.get("time_basis")
    if time_basis not in {"local_date", "local_instant", "instant_utc"}:
        _invalid("time_basis", "must be local_date, local_instant, or instant_utc")
    assert isinstance(time_basis, str)
    parse_scheduled_fact(seed_scheduled_fact, time_basis=time_basis, field="seed_scheduled_fact")

    timezone, timezone_database_version = _timezone_facts(
        root,
        time_basis=time_basis,
        require_available=require_available_timezone_data,
    )
    recurrence_set_fields: dict[str, object] = {
        "source_item_id": source_item_id,
        "seed_anchor_id": seed_anchor_id,
        "created_item_version": created_item_version,
        "time_basis": time_basis,
    }
    if timezone is not None:
        recurrence_set_fields["timezone"] = timezone
        recurrence_set_fields["timezone_database_version"] = timezone_database_version
    recurrence_set_id, recurrence_set_id_preimage = generated_id("recurrence_set", "spine.recurrence-set-id.v1", recurrence_set_fields)

    segment_preimages, label_to_ref = _normalize_initial_segments(
        root.get("segments"),
        seed_scheduled_fact=seed_scheduled_fact,
        time_basis=time_basis,
    )
    rule_preimages = _normalize_initial_rules(
        root.get("rules"),
        time_basis=time_basis,
        segments_supplied="segments" in root,
        label_to_ref=label_to_ref,
        segments=segment_preimages,
    )
    rdate_preimages = _normalize_initial_rdates(
        root.get("rdates", []),
        time_basis=time_basis,
        segments_supplied="segments" in root,
        label_to_ref=label_to_ref,
        segments=segment_preimages,
    )
    if not rule_preimages and not rdate_preimages:
        _invalid("rules", "a recurrence set requires an active rule or rdate")

    normalized_hash_preimage: dict[str, object] = {
        "derivation_version": "normalized_recurrence_set_hash.v1",
        "contract_version": RECURRENCE_CONTRACT_VERSION,
        "normalization_version": RECURRENCE_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "recurrence_set_id": recurrence_set_id,
        "revision_number": "1",
        "source_item_id": source_item_id,
        "created_item_version": created_item_version,
        "source_item_version": source_item_version,
        "seed_anchor_id": seed_anchor_id,
        "time_basis": time_basis,
        "segments": segment_preimages,
        "rules": rule_preimages,
        "rdates": rdate_preimages,
        "exdates": [],
        "overrides": [],
    }
    if timezone is not None:
        normalized_hash_preimage["timezone"] = timezone
        normalized_hash_preimage["timezone_database_version"] = timezone_database_version
    normalized_hash = hash_canonical_json(normalized_hash_preimage)

    revision_fields: dict[str, object] = {
        "recurrence_set_id": recurrence_set_id,
        "revision_number": "1",
        "normalized_recurrence_set_hash": normalized_hash,
    }
    if command_id is not None:
        revision_fields["command_id"] = command_id
    recurrence_revision_id, recurrence_revision_id_preimage = generated_id(
        "recurrence_revision", "spine.recurrence-revision-id.v1", revision_fields
    )

    public_segments: list[dict[str, object]] = []
    segment_ids_by_ref: dict[str, str] = {}
    segment_id_preimages: list[dict[str, object]] = []
    for segment in segment_preimages:
        segment_id, preimage = generated_id(
            "recurrence_segment",
            "spine.recurrence-segment-id.v1",
            {"recurrence_revision_id": recurrence_revision_id, **segment},
        )
        segment_id_preimages.append(preimage)
        segment_ref = _text(segment["segment_index"])
        segment_ids_by_ref[segment_ref] = segment_id
        public_segments.append({"segment_id": segment_id, **segment})

    public_rules: list[dict[str, object]] = []
    rule_id_preimages: list[dict[str, object]] = []
    for rule in rule_preimages:
        rule_id, preimage = generated_id(
            "recurrence_rule",
            "spine.recurrence-rule-id.v1",
            {"recurrence_revision_id": recurrence_revision_id, **rule},
        )
        rule_id_preimages.append(preimage)
        segment_ref = _text(rule["segment_ref"])
        public_rules.append(
            {
                "rule_id": rule_id,
                "segment_id": segment_ids_by_ref[segment_ref],
                **{key: value for key, value in rule.items() if key != "segment_ref"},
            }
        )

    public_rdates: list[dict[str, object]] = []
    rdate_id_preimages: list[dict[str, object]] = []
    for rdate in rdate_preimages:
        rdate_id, preimage = generated_id(
            "recurrence_rdate",
            "spine.recurrence-rdate-id.v1",
            {"recurrence_revision_id": recurrence_revision_id, **rdate},
        )
        rdate_id_preimages.append(preimage)
        segment_ref = _text(rdate["segment_ref"])
        public_rdates.append(
            {
                "rdate_id": rdate_id,
                "segment_id": segment_ids_by_ref[segment_ref],
                **{key: value for key, value in rdate.items() if key != "segment_ref"},
            }
        )

    value: dict[str, object] = {
        "contract_version": RECURRENCE_CONTRACT_VERSION,
        "normalization_version": RECURRENCE_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "recurrence_set_id": recurrence_set_id,
        "recurrence_revision_id": recurrence_revision_id,
        "revision_number": "1",
        "source_item_id": source_item_id,
        "created_item_version": created_item_version,
        "source_item_version": source_item_version,
        "seed_anchor_id": seed_anchor_id,
        "time_basis": time_basis,
        "normalized_recurrence_set_hash": normalized_hash,
        "segments": public_segments,
        "rules": public_rules,
        "rdates": public_rdates,
        "exdates": [],
        "overrides": [],
    }
    if timezone is not None:
        value["timezone"] = timezone
        value["timezone_database_version"] = timezone_database_version
    return NormalizedRecurrenceSet(
        value=value,
        recurrence_set_id_preimage=recurrence_set_id_preimage,
        normalized_hash_preimage=normalized_hash_preimage,
        recurrence_revision_id_preimage=recurrence_revision_id_preimage,
        segment_id_preimages=tuple(segment_id_preimages),
        rule_id_preimages=tuple(rule_id_preimages),
        rdate_id_preimages=tuple(rdate_id_preimages),
    )


def _authoring_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid("recurrence_set", "must be an object")
    allowed = {"time_basis", "timezone", "timezone_database_version", "rules", "rdates", "segments"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        _invalid(unknown[0], "is not supported")
    if "time_basis" not in value:
        _invalid("time_basis", "is required")
    if "rules" not in value:
        _invalid("rules", "is required")
    return value


def _timezone_facts(root: dict[str, Any], *, time_basis: str, require_available: bool) -> tuple[str | None, str | None]:
    timezone = root.get("timezone")
    version = root.get("timezone_database_version")
    if time_basis == "instant_utc":
        if timezone is not None:
            _invalid("timezone", "must be absent for instant_utc")
        if version is not None:
            _invalid("timezone_database_version", "must be absent for instant_utc")
        return None, None
    _required_text(timezone, "timezone")
    _required_text(version, "timezone_database_version")
    if require_available:
        validate_timezone_context(
            time_basis=time_basis,
            timezone=_text(timezone),
            timezone_database_version=_text(version),
        )
    return _text(timezone), _text(version)


def _normalize_initial_segments(
    value: object,
    *,
    seed_scheduled_fact: str,
    time_basis: str,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    labels: dict[str, dict[str, object]] = {}
    if value is None:
        raw_segments = [{"active_start": seed_scheduled_fact}]
    else:
        if not isinstance(value, list) or not value:
            _invalid("segments", "must be a non-empty array")
        raw_segments = value

    sortable: list[tuple[bytes, dict[str, object], str | None]] = []
    for index, raw in enumerate(raw_segments):
        field = f"segments[{index}]"
        if not isinstance(raw, dict):
            _invalid(field, "must be an object")
        allowed = {"segment_label", "active_start", "active_end", "reason_code"}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            _invalid(f"{field}.{unknown[0]}", "is not supported")
        label = raw.get("segment_label")
        if value is not None:
            _required_text(label, f"{field}.segment_label")
            if label in labels:
                raise SpineValidationError("semantic_conflict", f"{field}.segment_label is duplicated")
        start = raw.get("active_start")
        if not isinstance(start, str):
            _invalid(f"{field}.active_start", "is required")
        parse_scheduled_fact(start, time_basis=time_basis, field=f"{field}.active_start")
        segment: dict[str, object] = {
            "active_start": start,
            "source_revision_id": "initial",
            "status": "active",
        }
        end = raw.get("active_end")
        if end is not None:
            if not isinstance(end, str):
                _invalid(f"{field}.active_end", "must be a scheduled fact")
            parse_scheduled_fact(end, time_basis=time_basis, field=f"{field}.active_end")
            if end <= start:
                _invalid(f"{field}.active_end", "must be greater than active_start")
            segment["active_end"] = end
        reason = raw.get("reason_code")
        if reason is not None:
            _required_text(reason, f"{field}.reason_code")
            segment["reason_code"] = reason
        sortable.append((canonical_json_bytes(segment), segment, _optional_text(label)))
        if label is not None:
            labels[_text(label)] = segment

    sortable.sort(key=lambda entry: (_text(entry[1]["active_start"]), entry[0]))
    normalized: list[dict[str, object]] = []
    label_to_ref: dict[str, str] = {}
    previous_end: str | None = None
    previous_unbounded = False
    for index, (_, segment, label) in enumerate(sortable):
        start = _text(segment["active_start"])
        if previous_unbounded or (previous_end is not None and start < previous_end):
            raise SpineValidationError("semantic_conflict", f"segments[{index}] overlaps an active segment")
        segment = {"segment_index": str(index), **segment}
        normalized.append(segment)
        if label is not None:
            label_to_ref[label] = str(index)
        previous_end = _optional_text(segment.get("active_end"))
        previous_unbounded = previous_end is None
    return normalized, label_to_ref


def _normalize_initial_rules(
    value: object,
    *,
    time_basis: str,
    segments_supplied: bool,
    label_to_ref: dict[str, str],
    segments: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        _invalid("rules", "must be a non-empty array")
    normalized: list[dict[str, object]] = []
    seen: set[bytes] = set()
    for index, raw in enumerate(value):
        field = f"rules[{index}]"
        if not isinstance(raw, dict):
            _invalid(field, "must be an object")
        segment_ref = _authoring_segment_ref(raw, field=field, segments_supplied=segments_supplied, label_to_ref=label_to_ref)
        canonical = normalize_rule(raw, time_basis=time_basis, field=field).as_contract()
        candidate: dict[str, object] = {"segment_ref": segment_ref, **canonical, "status": "active"}
        _validate_child_bounds(_text(candidate["start_bound"]), segment_ref=segment_ref, segments=segments, field=f"{field}.start_bound")
        key = canonical_json_bytes(candidate)
        if key not in seen:
            normalized.append(candidate)
            seen.add(key)
    normalized.sort(key=lambda child: (_text(child["segment_ref"]), canonical_json_bytes(_child_semantics(child))))
    return normalized


def _normalize_initial_rdates(
    value: object,
    *,
    time_basis: str,
    segments_supplied: bool,
    label_to_ref: dict[str, str],
    segments: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _invalid("rdates", "must be an array")
    normalized: list[dict[str, object]] = []
    seen: set[bytes] = set()
    for index, raw in enumerate(value):
        field = f"rdates[{index}]"
        if not isinstance(raw, dict):
            _invalid(field, "must be an object")
        unknown = sorted(set(raw) - {"scheduled_fact", "segment_label"})
        if unknown:
            _invalid(f"{field}.{unknown[0]}", "is not supported")
        segment_ref = _authoring_segment_ref(raw, field=field, segments_supplied=segments_supplied, label_to_ref=label_to_ref)
        scheduled_fact = raw.get("scheduled_fact")
        if not isinstance(scheduled_fact, str):
            _invalid(f"{field}.scheduled_fact", "is required")
        parse_scheduled_fact(scheduled_fact, time_basis=time_basis, field=f"{field}.scheduled_fact")
        _validate_child_bounds(scheduled_fact, segment_ref=segment_ref, segments=segments, field=f"{field}.scheduled_fact")
        candidate: dict[str, object] = {
            "segment_ref": segment_ref,
            "scheduled_fact": scheduled_fact,
            "status": "active",
        }
        key = canonical_json_bytes(candidate)
        if key not in seen:
            normalized.append(candidate)
            seen.add(key)
    normalized.sort(key=lambda child: (_text(child["segment_ref"]), canonical_json_bytes(_child_semantics(child))))
    return normalized


def _authoring_segment_ref(raw: dict[str, Any], *, field: str, segments_supplied: bool, label_to_ref: dict[str, str]) -> str:
    label = raw.get("segment_label")
    if segments_supplied:
        _required_text(label, f"{field}.segment_label")
        if label not in label_to_ref:
            _invalid(f"{field}.segment_label", "does not name an authoring segment")
        return label_to_ref[_text(label)]
    if label is not None:
        _invalid(f"{field}.segment_label", "must be absent when segments is omitted")
    return "0"


def _validate_child_bounds(scheduled_fact: str, *, segment_ref: str, segments: list[dict[str, object]], field: str) -> None:
    segment = segments[int(segment_ref)]
    start = _text(segment["active_start"])
    end = _optional_text(segment.get("active_end"))
    if scheduled_fact < start or (end is not None and scheduled_fact >= end):
        raise SpineValidationError("semantic_conflict", f"{field} is outside its active segment")


def _child_semantics(child: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in child.items() if key != "segment_ref"}


def _required_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value:
        _invalid(field, "must be a non-empty string")


def _positive_decimal(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.isdigit() or value.startswith("0"):
        _invalid(field, "must be a positive decimal string")


def _text(value: object) -> str:
    assert isinstance(value, str)
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _invalid(field: str, detail: str) -> NoReturn:
    raise SpineValidationError("invalid_request", f"{field} {detail}")
