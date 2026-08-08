"""Pure cross-source recurrence expansion and occurrence identity derivation."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, NoReturn

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_set import generated_id
from spine.core.schedule import (
    CANONICAL_JSON_VERSION,
    RECURRENCE_CONTRACT_VERSION,
    RECURRENCE_NORMALIZATION_VERSION,
    expand_rule,
    parse_scheduled_fact,
    resolve_local_instant,
    validate_range,
)


@dataclass(frozen=True)
class ExpandedRecurrenceSet:
    occurrences: tuple[dict[str, object], ...]
    diagnostics: tuple[dict[str, object], ...]


def expand_recurrence_set(
    recurrence_set: object,
    *,
    range_start: str,
    range_end: str,
    range_basis: str = "original_schedule",
    include_diagnostics: bool = False,
) -> ExpandedRecurrenceSet:
    """Expand one normalized recurrence revision before item-detail decoration."""

    root = _normalized_set(recurrence_set)
    time_basis = _required_text(root, "time_basis")
    validate_range(range_start, range_end, time_basis=time_basis)
    if range_basis not in {"original_schedule", "expressed_time"}:
        _invalid("range_basis", "must be original_schedule or expressed_time")
    timezone = _optional_text(root.get("timezone"))
    timezone_version = _optional_text(root.get("timezone_database_version"))

    segments = _active_segments(root, time_basis=time_basis)
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    diagnostics: list[dict[str, object]] = []
    active_overrides = _active_objects(root.get("overrides"), "overrides")
    expansion_windows = _expansion_windows(
        active_overrides,
        time_basis=time_basis,
        range_basis=range_basis,
        range_start=range_start,
        range_end=range_end,
    )

    rules = root.get("rules")
    if not isinstance(rules, list):
        _invalid("rules", "must be an array")
    for rule_index, rule in enumerate(rules):
        if not isinstance(rule, dict) or rule.get("status") != "active":
            continue
        segment = _segment_for_child(rule, segments, field=f"rules[{rule_index}].segment_id")
        segment_ref = _required_text(segment, "segment_index")
        selector = _rule_selector(rule)
        rule_id = _required_text(rule, "rule_id")
        for window_start, window_end in expansion_windows:
            expanded = expand_rule(
                selector,
                time_basis=time_basis,
                range_start=window_start,
                range_end=window_end,
                timezone=timezone,
                timezone_database_version=timezone_version,
                segment_start=_required_text(segment, "active_start"),
                segment_end=_optional_text(segment.get("active_end")),
            )
            for candidate in expanded.candidates:
                bucket = _bucket(buckets, segment_ref, candidate.scheduled_fact, segment)
                bucket["rule_sources"].append((selector, rule_id, candidate.rule_local_index))
                if candidate.timezone_resolution is not None:
                    bucket["timezone_resolution"] = candidate.timezone_resolution.as_contract()
            if include_diagnostics:
                for omitted in expanded.omitted_local_candidates:
                    assert timezone is not None and timezone_version is not None
                    diagnostics.append(
                        {
                            "severity": "warning",
                            "diagnostic_code": "dst_nonexistent_omitted",
                            "field": "timezone_resolution",
                            "scheduled_fact": omitted.scheduled_fact,
                            "timezone_resolution": {
                                "timezone": timezone,
                                "timezone_database_version": timezone_version,
                                "resolution_kind": "nonexistent_omitted",
                                "local_datetime": omitted.scheduled_fact,
                            },
                            "source_id": rule_id,
                        }
                    )

    rdates = root.get("rdates")
    if not isinstance(rdates, list):
        _invalid("rdates", "must be an array")
    for rdate_index, rdate in enumerate(rdates):
        if not isinstance(rdate, dict) or rdate.get("status") != "active":
            continue
        segment = _segment_for_child(rdate, segments, field=f"rdates[{rdate_index}].segment_id")
        segment_ref = _required_text(segment, "segment_index")
        scheduled_fact = _required_text(rdate, "scheduled_fact")
        parse_scheduled_fact(scheduled_fact, time_basis=time_basis, field=f"rdates[{rdate_index}].scheduled_fact")
        if not _inside_segment(scheduled_fact, segment) or not any(start <= scheduled_fact < end for start, end in expansion_windows):
            continue
        resolution = None
        if time_basis == "local_instant":
            assert timezone is not None and timezone_version is not None
            resolution = resolve_local_instant(
                scheduled_fact,
                timezone=timezone,
                timezone_database_version=timezone_version,
            )
            if resolution is None:
                if include_diagnostics:
                    diagnostics.append(
                        {
                            "severity": "warning",
                            "diagnostic_code": "dst_nonexistent_omitted",
                            "field": "timezone_resolution",
                            "scheduled_fact": scheduled_fact,
                            "timezone_resolution": {
                                "timezone": timezone,
                                "timezone_database_version": timezone_version,
                                "resolution_kind": "nonexistent_omitted",
                                "local_datetime": scheduled_fact,
                            },
                            "source_id": _required_text(rdate, "rdate_id"),
                        }
                    )
                continue
        bucket = _bucket(buckets, segment_ref, scheduled_fact, segment)
        bucket["rdate_sources"].append((_rdate_selector(rdate), _required_text(rdate, "rdate_id")))
        if resolution is not None:
            bucket["timezone_resolution"] = resolution.as_contract()

    exdate_keys = {_required_text(exdate, "target_occurrence_key") for exdate in _active_objects(root.get("exdates"), "exdates")}
    overrides = {_required_text(override, "target_occurrence_key"): override for override in active_overrides}

    occurrences: list[dict[str, object]] = []
    for (segment_ref, scheduled_fact), bucket in buckets.items():
        rule_sources = sorted(bucket["rule_sources"], key=lambda value: canonical_json_bytes(value[0]))
        rdate_sources = sorted(bucket["rdate_sources"], key=lambda value: canonical_json_bytes(value[0]))
        if len(rule_sources) == 1 and not rdate_sources:
            origin_kind = "rule"
        elif len(rdate_sources) == 1 and not rule_sources:
            origin_kind = "rdate"
        else:
            origin_kind = "union"

        selector = {
            "derivation_version": "spine.recurrence-target-occurrence-selector.v1",
            "contract_version": RECURRENCE_CONTRACT_VERSION,
            "normalization_version": RECURRENCE_NORMALIZATION_VERSION,
            "canonical_json_version": CANONICAL_JSON_VERSION,
            "recurrence_set_id": _required_text(root, "recurrence_set_id"),
            "segment_ref": segment_ref,
            "scheduled_fact": scheduled_fact,
            "origin_kind": origin_kind,
            "source_rule_selectors": [entry[0] for entry in rule_sources],
            "source_rdate_selectors": [entry[0] for entry in rdate_sources],
        }
        occurrence_key, _ = opaque_key("spine.recurrence-occurrence-key.v2", {"target_occurrence_selector": selector})
        if occurrence_key in exdate_keys:
            continue
        override = overrides.get(occurrence_key)
        expressed = scheduled_fact
        lifecycle = "active"
        override_id: str | None = None
        if override is not None:
            override_id = _required_text(override, "override_id")
            expressed = _optional_text(override.get("expressed_scheduled_fact")) or scheduled_fact
            lifecycle = _optional_text(override.get("lifecycle")) or "active"
            parse_scheduled_fact(expressed, time_basis=time_basis, field="overrides.expressed_scheduled_fact")
        selected_fact = scheduled_fact if range_basis == "original_schedule" else expressed
        if not range_start <= selected_fact < range_end:
            continue

        occurrence_id_fields: dict[str, object] = {
            "occurrence_key": occurrence_key,
            "recurrence_revision_id": _required_text(root, "recurrence_revision_id"),
            "normalized_recurrence_set_hash": _required_text(root, "normalized_recurrence_set_hash"),
            "time_basis": time_basis,
        }
        timezone_resolution = bucket.get("timezone_resolution")
        if timezone is not None:
            occurrence_id_fields["timezone"] = timezone
            occurrence_id_fields["timezone_database_version"] = timezone_version
        if timezone_resolution is not None:
            occurrence_id_fields["timezone_resolution"] = timezone_resolution
        occurrence_id, _ = generated_id("occurrence", "spine.recurrence-occurrence-id.v2", occurrence_id_fields)
        expressed_fields: dict[str, object] = {
            "occurrence_key": occurrence_key,
            "range_basis": range_basis,
            "original_scheduled_fact": scheduled_fact,
            "expressed_scheduled_fact": expressed,
        }
        if override_id is not None:
            expressed_fields["override_id"] = override_id
        expressed_schedule_key, _ = opaque_key("spine.recurrence-expressed-schedule-key.v1", expressed_fields)
        source_entries = [{"source_kind": "rule", "source_id": entry[1], "rule_local_index": entry[2]} for entry in rule_sources] + [
            {"source_kind": "rdate", "source_id": entry[1]} for entry in rdate_sources
        ]
        occurrence: dict[str, object] = {
            "occurrence_id": occurrence_id,
            "occurrence_key": occurrence_key,
            "target_occurrence_selector": selector,
            "recurrence_set_id": _required_text(root, "recurrence_set_id"),
            "recurrence_revision_id": _required_text(root, "recurrence_revision_id"),
            "segment_id": _required_text(bucket["segment"], "segment_id"),
            "origin_kind": origin_kind,
            "normalized_recurrence_set_hash": _required_text(root, "normalized_recurrence_set_hash"),
            "original_scheduled_fact": scheduled_fact,
            "expressed_scheduled_fact": expressed,
            "expressed_schedule_key": expressed_schedule_key,
            "range_basis": range_basis,
            "lifecycle": lifecycle,
            "source_entries": source_entries,
            "source_rule_ids": [entry[1] for entry in rule_sources],
            "source_rdate_ids": [entry[1] for entry in rdate_sources],
            "virtual": True,
        }
        if timezone_resolution is not None:
            occurrence["timezone_resolution"] = timezone_resolution
        elif time_basis == "local_date":
            occurrence["timezone"] = timezone
            occurrence["timezone_database_version"] = timezone_version
        if override_id is not None:
            assert override is not None
            occurrence["override_id"] = override_id
            for patch in ("common_detail_patch", "event_detail_patch", "task_detail_patch"):
                if patch in override:
                    occurrence[patch] = override[patch]
        occurrences.append(occurrence)

    if range_basis == "original_schedule":
        occurrences.sort(
            key=lambda value: (
                _required_text(value, "original_scheduled_fact"),
                _required_text(value, "occurrence_key"),
                _required_text(value, "occurrence_id"),
            )
        )
    else:
        occurrences.sort(
            key=lambda value: (
                _required_text(value, "expressed_scheduled_fact"),
                _required_text(value, "expressed_schedule_key"),
                _required_text(value, "occurrence_key"),
                _required_text(value, "occurrence_id"),
            )
        )
    diagnostics.sort(
        key=lambda value: (
            0 if value["severity"] == "warning" else 1,
            value["diagnostic_code"],
            value["field"],
            value.get("scheduled_fact", ""),
            value.get("source_id", ""),
        )
    )
    return ExpandedRecurrenceSet(tuple(occurrences), tuple(diagnostics))


def opaque_key(derivation_version: str, fields: dict[str, object]) -> tuple[str, dict[str, object]]:
    preimage = {
        "derivation_version": derivation_version,
        "contract_version": RECURRENCE_CONTRACT_VERSION,
        "normalization_version": RECURRENCE_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        **fields,
    }
    payload = canonical_json_bytes(preimage)
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return f"{encoded}.{hash_canonical_json(preimage)}", preimage


def _normalized_set(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid("recurrence_set", "must be an object")
    for field in (
        "recurrence_set_id",
        "recurrence_revision_id",
        "normalized_recurrence_set_hash",
        "time_basis",
        "segments",
        "rules",
        "rdates",
        "exdates",
        "overrides",
    ):
        if field not in value:
            _invalid(field, "is required")
    return value


def _active_segments(root: dict[str, Any], *, time_basis: str) -> list[dict[str, Any]]:
    raw = root.get("segments")
    if not isinstance(raw, list):
        _invalid("segments", "must be an array")
    result: list[dict[str, Any]] = []
    for index, segment in enumerate(raw):
        if not isinstance(segment, dict) or segment.get("status") != "active":
            continue
        start = _required_text(segment, "active_start")
        parse_scheduled_fact(start, time_basis=time_basis, field=f"segments[{index}].active_start")
        end = _optional_text(segment.get("active_end"))
        if end is not None:
            parse_scheduled_fact(end, time_basis=time_basis, field=f"segments[{index}].active_end")
        result.append(segment)
    return result


def _segment_for_child(child: dict[str, Any], segments: list[dict[str, Any]], *, field: str) -> dict[str, Any]:
    segment_id = _required_text(child, "segment_id")
    matches = [segment for segment in segments if segment.get("segment_id") == segment_id]
    if len(matches) != 1:
        raise SpineValidationError("semantic_conflict", f"{field} does not resolve to one active segment")
    return matches[0]


def _bucket(
    buckets: dict[tuple[str, str], dict[str, Any]],
    segment_ref: str,
    scheduled_fact: str,
    segment: dict[str, Any],
) -> dict[str, Any]:
    return buckets.setdefault(
        (segment_ref, scheduled_fact),
        {"segment": segment, "rule_sources": [], "rdate_sources": []},
    )


def _rule_selector(rule: dict[str, Any]) -> dict[str, object]:
    omitted = {"rule_id", "segment_id"}
    return {key: value for key, value in rule.items() if key not in omitted}


def _rdate_selector(rdate: dict[str, Any]) -> dict[str, object]:
    omitted = {"rdate_id", "segment_id"}
    return {key: value for key, value in rdate.items() if key not in omitted}


def _inside_segment(scheduled_fact: str, segment: dict[str, Any]) -> bool:
    start = _required_text(segment, "active_start")
    end = _optional_text(segment.get("active_end"))
    return start <= scheduled_fact and (end is None or scheduled_fact < end)


def _expansion_windows(
    overrides: list[dict[str, Any]],
    *,
    time_basis: str,
    range_basis: str,
    range_start: str,
    range_end: str,
) -> list[tuple[str, str]]:
    """Add exact proof windows for occurrences moved into an expressed-time range."""

    windows = [(range_start, range_end)]
    if range_basis != "expressed_time":
        return windows
    seen = {windows[0]}
    for override in overrides:
        expressed = _optional_text(override.get("expressed_scheduled_fact"))
        selector = override.get("target_occurrence_selector")
        if expressed is None or not range_start <= expressed < range_end:
            continue
        if not isinstance(selector, dict):
            _invalid("overrides.target_occurrence_selector", "must be an object")
        original = _required_text(selector, "scheduled_fact")
        parse_scheduled_fact(
            original,
            time_basis=time_basis,
            field="overrides.target_occurrence_selector.scheduled_fact",
        )
        if range_start <= original < range_end:
            continue
        window = (original, _next_scheduled_fact(original, time_basis=time_basis))
        if window not in seen:
            seen.add(window)
            windows.append(window)
    return windows


def _next_scheduled_fact(value: str, *, time_basis: str) -> str:
    parsed = parse_scheduled_fact(value, time_basis=time_basis, field="scheduled_fact")
    if time_basis == "local_date":
        assert isinstance(parsed, date) and not isinstance(parsed, datetime)
        return (parsed + timedelta(days=1)).isoformat()
    assert isinstance(parsed, datetime)
    advanced = parsed + timedelta(seconds=1)
    if time_basis == "local_instant":
        return advanced.isoformat(timespec="seconds")
    return advanced.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _active_objects(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _invalid(field, "must be an array")
    return [entry for entry in value if isinstance(entry, dict) and entry.get("status") == "active"]


def _required_text(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        _invalid(field, "must be a non-empty string")
    return result


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _invalid(field: str, detail: str) -> NoReturn:
    raise SpineValidationError("invalid_request", f"{field} {detail}")
