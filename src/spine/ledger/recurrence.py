"""Relational persistence for canonical recurrence aggregates."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_set import NormalizedRecurrenceSet


def insert_initial_recurrence_set(
    connection: sqlite3.Connection,
    *,
    normalized: NormalizedRecurrenceSet,
    command_id: str,
    created_at_utc: str,
) -> None:
    """Insert a normalized revision-one aggregate inside an owning item transaction."""

    value = normalized.value
    connection.execute(
        """
        INSERT OR IGNORE INTO recurrence_sets (
          recurrence_set_id, source_item_id, created_item_version, seed_anchor_id,
          time_basis, timezone, timezone_database_version, contract_version,
          normalization_version, canonical_json_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["recurrence_set_id"],
            value["source_item_id"],
            int(str(value["created_item_version"])),
            value["seed_anchor_id"],
            value["time_basis"],
            value.get("timezone"),
            value.get("timezone_database_version"),
            value["contract_version"],
            value["normalization_version"],
            value["canonical_json_version"],
        ),
    )
    connection.execute(
        """
        INSERT INTO recurrence_revisions (
          recurrence_revision_id, recurrence_set_id, revision_number,
          source_item_version, normalized_recurrence_set_hash,
          prior_recurrence_revision_id, command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["recurrence_revision_id"],
            value["recurrence_set_id"],
            int(str(value["revision_number"])),
            int(str(value["source_item_version"])),
            value["normalized_recurrence_set_hash"],
            value.get("prior_recurrence_revision_id"),
            command_id,
            created_at_utc,
        ),
    )
    for segment in _objects(value["segments"], "segments"):
        connection.execute(
            """
            INSERT INTO recurrence_segments (
              segment_id, recurrence_revision_id, segment_index, active_start,
              active_end, source_revision_id, status, lineage_parent_segment_id,
              created_by_command_id, reason_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment["segment_id"],
                value["recurrence_revision_id"],
                int(str(segment["segment_index"])),
                segment["active_start"],
                segment.get("active_end"),
                segment["source_revision_id"],
                segment["status"],
                segment.get("lineage_parent_segment_id"),
                segment.get("created_by_command_id"),
                segment.get("reason_code"),
            ),
        )
    segment_ref_by_id = {
        str(segment["segment_id"]): int(str(segment["segment_index"])) for segment in _objects(value["segments"], "segments")
    }
    for rule in _objects(value["rules"], "rules"):
        end = _mapping(rule["end_condition"], "end_condition")
        connection.execute(
            """
            INSERT INTO recurrence_rules (
              rule_id, recurrence_revision_id, segment_id, segment_ref, frequency,
              interval_value, seed, start_bound, end_kind, end_count, end_until,
              week_start, status, rule_duplicate_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule["rule_id"],
                value["recurrence_revision_id"],
                rule["segment_id"],
                segment_ref_by_id[str(rule["segment_id"])],
                rule["frequency"],
                int(str(rule["interval"])),
                rule["seed"],
                rule["start_bound"],
                end["kind"],
                int(str(end["count"])) if "count" in end else None,
                end.get("until"),
                rule.get("week_start"),
                rule["status"],
                int(str(rule["rule_duplicate_index"])) if "rule_duplicate_index" in rule else None,
            ),
        )
        for selector_kind in ("by_month", "by_month_day", "by_weekday", "by_set_position"):
            selector_values = rule.get(selector_kind, [])
            if not isinstance(selector_values, list):
                raise SpineValidationError("invalid_recurrence_storage", selector_kind)
            for selector_index, selector_value in enumerate(selector_values):
                connection.execute(
                    """
                    INSERT INTO recurrence_rule_selectors (
                      rule_id, selector_kind, selector_index, selector_value
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (rule["rule_id"], selector_kind, selector_index, selector_value),
                )
    for rdate in _objects(value["rdates"], "rdates"):
        connection.execute(
            """
            INSERT INTO recurrence_rdates (
              rdate_id, recurrence_revision_id, segment_id, segment_ref,
              scheduled_fact, status, rdate_duplicate_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rdate["rdate_id"],
                value["recurrence_revision_id"],
                rdate["segment_id"],
                segment_ref_by_id[str(rdate["segment_id"])],
                rdate["scheduled_fact"],
                rdate["status"],
                int(str(rdate["rdate_duplicate_index"])) if "rdate_duplicate_index" in rdate else None,
            ),
        )
    for exdate in _objects(value.get("exdates", []), "exdates"):
        selector = _mapping(exdate["target_occurrence_selector"], "target_occurrence_selector")
        selector_ref = persist_target_occurrence_selector(
            connection,
            occurrence_key=str(exdate["target_occurrence_key"]),
            selector=selector,
        )
        connection.execute(
            """
            INSERT INTO recurrence_exdates (
              exdate_id, recurrence_revision_id, segment_id, segment_ref,
              target_occurrence_selector_ref, target_occurrence_key,
              prior_target_occurrence_key, scheduled_fact, reason_code, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exdate["exdate_id"],
                value["recurrence_revision_id"],
                exdate["segment_id"],
                segment_ref_by_id[str(exdate["segment_id"])],
                selector_ref,
                exdate["target_occurrence_key"],
                exdate.get("prior_target_occurrence_key"),
                exdate["scheduled_fact"],
                exdate["reason_code"],
                exdate["status"],
            ),
        )
    for override in _objects(value.get("overrides", []), "overrides"):
        selector = _mapping(override["target_occurrence_selector"], "target_occurrence_selector")
        selector_ref = persist_target_occurrence_selector(
            connection,
            occurrence_key=str(override["target_occurrence_key"]),
            selector=selector,
        )
        connection.execute(
            """
            INSERT INTO recurrence_overrides (
              override_id, recurrence_revision_id, segment_id, segment_ref,
              target_occurrence_selector_ref, target_occurrence_key,
              prior_target_occurrence_key, override_kind, revision_key,
              expressed_scheduled_fact, common_detail_patch_json,
              event_detail_patch_json, task_detail_patch_json, lifecycle,
              reason_code, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                override["override_id"],
                value["recurrence_revision_id"],
                override["segment_id"],
                segment_ref_by_id[str(override["segment_id"])],
                selector_ref,
                override["target_occurrence_key"],
                override.get("prior_target_occurrence_key"),
                override["override_kind"],
                override["revision_key"],
                override.get("expressed_scheduled_fact"),
                _json_text(override.get("common_detail_patch")),
                _json_text(override.get("event_detail_patch")),
                _json_text(override.get("task_detail_patch")),
                override.get("lifecycle"),
                override.get("reason_code"),
                override["status"],
            ),
        )


def insert_recurrence_lineage(connection: sqlite3.Connection, *, lineage: list[dict[str, object]]) -> None:
    """Persist a deterministic lineage bundle inside the revision transaction."""

    for value in lineage:
        connection.execute(
            """
            INSERT INTO recurrence_lineage (
              lineage_id, command_id, recurrence_set_id,
              prior_recurrence_revision_id, new_recurrence_revision_id,
              lineage_role, prior_segment_id, new_segment_id,
              prior_child_id, new_child_id, effect, lineage_index, payload_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                value["lineage_id"],
                value["command_id"],
                value["recurrence_set_id"],
                value["prior_recurrence_revision_id"],
                value["new_recurrence_revision_id"],
                value["lineage_role"],
                value.get("prior_segment_id"),
                value.get("new_segment_id"),
                value.get("prior_child_id"),
                value.get("new_child_id"),
                value["effect"],
                int(str(value["lineage_index"])),
                value["payload_hash"],
            ),
        )


def load_current_recurrence_set(connection: sqlite3.Connection, *, item_id: str) -> dict[str, object] | None:
    """Load the one recurrence revision bound to the current item version."""

    header = connection.execute(
        """
        SELECT rs.*, rr.recurrence_revision_id, rr.revision_number,
               rr.source_item_version, rr.normalized_recurrence_set_hash
        FROM coordination_items AS item
        JOIN recurrence_sets AS rs ON rs.source_item_id = item.item_id
        JOIN recurrence_revisions AS rr
          ON rr.recurrence_set_id = rs.recurrence_set_id
         AND rr.source_item_version <= item.current_version
        WHERE item.item_id = ?
        ORDER BY rr.source_item_version DESC, rr.revision_number DESC
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if header is None:
        return None
    revision_id = header["recurrence_revision_id"]
    segments = [
        dict(row)
        for row in connection.execute(
            """
        SELECT segment_id, CAST(segment_index AS TEXT) AS segment_index,
               active_start, active_end, source_revision_id, status,
               lineage_parent_segment_id, created_by_command_id, reason_code
        FROM recurrence_segments
        WHERE recurrence_revision_id = ?
        ORDER BY segment_index
        """,
            (revision_id,),
        )
    ]
    rules: list[dict[str, object]] = []
    for row in connection.execute(
        """
        SELECT * FROM recurrence_rules
        WHERE recurrence_revision_id = ?
        ORDER BY segment_ref, rule_id
        """,
        (revision_id,),
    ):
        end: dict[str, str] = {"kind": row["end_kind"]}
        if row["end_count"] is not None:
            end["count"] = str(row["end_count"])
        if row["end_until"] is not None:
            end["until"] = row["end_until"]
        rule: dict[str, object] = {
            "rule_id": row["rule_id"],
            "segment_id": row["segment_id"],
            "frequency": row["frequency"],
            "interval": str(row["interval_value"]),
            "seed": row["seed"],
            "start_bound": row["start_bound"],
            "end_condition": end,
            "status": row["status"],
        }
        if row["week_start"] is not None:
            rule["week_start"] = row["week_start"]
        if row["rule_duplicate_index"] is not None:
            rule["rule_duplicate_index"] = str(row["rule_duplicate_index"])
        for selector in connection.execute(
            """
            SELECT selector_kind, selector_value
            FROM recurrence_rule_selectors
            WHERE rule_id = ?
            ORDER BY selector_kind, selector_index
            """,
            (row["rule_id"],),
        ):
            selector_values = rule.setdefault(str(selector["selector_kind"]), [])
            assert isinstance(selector_values, list)
            selector_values.append(str(selector["selector_value"]))
        rules.append(rule)
    rdates = [
        _rdate_row(row)
        for row in connection.execute(
            """
            SELECT * FROM recurrence_rdates
            WHERE recurrence_revision_id = ?
            ORDER BY segment_ref, scheduled_fact, rdate_id
            """,
            (revision_id,),
        )
    ]
    exdates = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM recurrence_exdates WHERE recurrence_revision_id = ? ORDER BY segment_ref, scheduled_fact, exdate_id",
            (revision_id,),
        )
    ]
    overrides = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM recurrence_overrides WHERE recurrence_revision_id = ? ORDER BY segment_ref, target_occurrence_key, override_id",
            (revision_id,),
        )
    ]
    value: dict[str, object] = {
        "contract_version": header["contract_version"],
        "normalization_version": header["normalization_version"],
        "canonical_json_version": header["canonical_json_version"],
        "recurrence_set_id": header["recurrence_set_id"],
        "recurrence_revision_id": revision_id,
        "revision_number": str(header["revision_number"]),
        "source_item_id": header["source_item_id"],
        "created_item_version": str(header["created_item_version"]),
        "source_item_version": str(header["source_item_version"]),
        "seed_anchor_id": header["seed_anchor_id"],
        "time_basis": header["time_basis"],
        "normalized_recurrence_set_hash": header["normalized_recurrence_set_hash"],
        "segments": [_omit_none(segment) for segment in segments],
        "rules": rules,
        "rdates": rdates,
        "exdates": [_stored_exdate(connection, row) for row in exdates],
        "overrides": [_stored_override(connection, row) for row in overrides],
    }
    if header["timezone"] is not None:
        value["timezone"] = header["timezone"]
        value["timezone_database_version"] = header["timezone_database_version"]
    return value


def persist_target_occurrence_selector(
    connection: sqlite3.Connection,
    *,
    occurrence_key: str,
    selector: dict[str, object],
) -> str:
    """Persist one revision-independent selector as inspectable relational facts."""

    selector_ref = "recurrence_target_selector_" + hash_canonical_json(selector)
    connection.execute(
        """
        INSERT OR IGNORE INTO recurrence_target_occurrence_selectors (
          target_occurrence_selector_ref, occurrence_key, recurrence_set_id,
          segment_ref, scheduled_fact, origin_kind
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            selector_ref,
            occurrence_key,
            selector["recurrence_set_id"],
            int(str(selector["segment_ref"])),
            selector["scheduled_fact"],
            selector["origin_kind"],
        ),
    )
    rule_sources = selector.get("source_rule_selectors", [])
    if not isinstance(rule_sources, list):
        raise SpineValidationError("invalid_recurrence_storage", "source_rule_selectors must be an array")
    for source_index, source in enumerate(rule_sources):
        rule = _mapping(source, "source_rule_selector")
        end = _mapping(rule["end_condition"], "end_condition")
        connection.execute(
            """
            INSERT OR IGNORE INTO recurrence_target_rule_sources (
              target_occurrence_selector_ref, source_index, frequency,
              interval_value, seed, start_bound, end_kind, end_count,
              end_until, week_start, status, rule_duplicate_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selector_ref,
                source_index,
                rule["frequency"],
                int(str(rule["interval"])),
                rule["seed"],
                rule["start_bound"],
                end["kind"],
                int(str(end["count"])) if "count" in end else None,
                end.get("until"),
                rule.get("week_start"),
                rule["status"],
                int(str(rule["rule_duplicate_index"])) if "rule_duplicate_index" in rule else None,
            ),
        )
        for selector_kind in ("by_month", "by_month_day", "by_weekday", "by_set_position"):
            values = rule.get(selector_kind, [])
            if not isinstance(values, list):
                raise SpineValidationError("invalid_recurrence_storage", selector_kind)
            for selector_index, selector_value in enumerate(values):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO recurrence_target_rule_source_selectors (
                      target_occurrence_selector_ref, source_index, selector_kind,
                      selector_index, selector_value
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (selector_ref, source_index, selector_kind, selector_index, selector_value),
                )
    rdate_sources = selector.get("source_rdate_selectors", [])
    if not isinstance(rdate_sources, list):
        raise SpineValidationError("invalid_recurrence_storage", "source_rdate_selectors must be an array")
    for source_index, source in enumerate(rdate_sources):
        rdate = _mapping(source, "source_rdate_selector")
        connection.execute(
            """
            INSERT OR IGNORE INTO recurrence_target_rdate_sources (
              target_occurrence_selector_ref, source_index, scheduled_fact,
              status, rdate_duplicate_index
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                selector_ref,
                source_index,
                rdate["scheduled_fact"],
                rdate["status"],
                int(str(rdate["rdate_duplicate_index"])) if "rdate_duplicate_index" in rdate else None,
            ),
        )
    return selector_ref


def load_target_occurrence_selector(connection: sqlite3.Connection, *, selector_ref: str) -> dict[str, object]:
    """Reconstruct one canonical selector from its relational facts."""

    row = connection.execute(
        "SELECT * FROM recurrence_target_occurrence_selectors WHERE target_occurrence_selector_ref = ?",
        (selector_ref,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("referenced_row_not_found", "occurrence selector is missing")
    rules: list[dict[str, object]] = []
    for source in connection.execute(
        """
        SELECT * FROM recurrence_target_rule_sources
        WHERE target_occurrence_selector_ref = ? ORDER BY source_index
        """,
        (selector_ref,),
    ):
        end: dict[str, object] = {"kind": source["end_kind"]}
        if source["end_count"] is not None:
            end["count"] = str(source["end_count"])
        if source["end_until"] is not None:
            end["until"] = source["end_until"]
        rule: dict[str, object] = {
            "frequency": source["frequency"],
            "interval": str(source["interval_value"]),
            "seed": source["seed"],
            "start_bound": source["start_bound"],
            "end_condition": end,
            "status": source["status"],
        }
        if source["week_start"] is not None:
            rule["week_start"] = source["week_start"]
        if source["rule_duplicate_index"] is not None:
            rule["rule_duplicate_index"] = str(source["rule_duplicate_index"])
        for selector in connection.execute(
            """
            SELECT selector_kind, selector_value
            FROM recurrence_target_rule_source_selectors
            WHERE target_occurrence_selector_ref = ? AND source_index = ?
            ORDER BY selector_kind, selector_index
            """,
            (selector_ref, source["source_index"]),
        ):
            selector_values = rule.setdefault(str(selector["selector_kind"]), [])
            assert isinstance(selector_values, list)
            selector_values.append(str(selector["selector_value"]))
        rules.append(rule)
    rdates: list[dict[str, object]] = []
    for source in connection.execute(
        """
        SELECT * FROM recurrence_target_rdate_sources
        WHERE target_occurrence_selector_ref = ? ORDER BY source_index
        """,
        (selector_ref,),
    ):
        rdate: dict[str, object] = {
            "scheduled_fact": source["scheduled_fact"],
            "status": source["status"],
        }
        if source["rdate_duplicate_index"] is not None:
            rdate["rdate_duplicate_index"] = str(source["rdate_duplicate_index"])
        rdates.append(rdate)
    return {
        "derivation_version": "spine.recurrence-target-occurrence-selector.v1",
        "contract_version": "spine.recurrence.contract.v1",
        "normalization_version": "spine.recurrence.normalization.v1",
        "canonical_json_version": "spine.canonical-json.v1",
        "recurrence_set_id": row["recurrence_set_id"],
        "segment_ref": str(row["segment_ref"]),
        "scheduled_fact": row["scheduled_fact"],
        "origin_kind": row["origin_kind"],
        "source_rule_selectors": rules,
        "source_rdate_selectors": rdates,
    }


def _rdate_row(row: sqlite3.Row) -> dict[str, object]:
    result: dict[str, object] = {
        "rdate_id": row["rdate_id"],
        "segment_id": row["segment_id"],
        "scheduled_fact": row["scheduled_fact"],
        "status": row["status"],
    }
    if row["rdate_duplicate_index"] is not None:
        result["rdate_duplicate_index"] = str(row["rdate_duplicate_index"])
    return result


def _stored_exdate(connection: sqlite3.Connection, row: dict[str, Any]) -> dict[str, object]:
    value = _omit_none(
        {key: value for key, value in row.items() if key not in {"recurrence_revision_id", "segment_ref", "target_occurrence_selector_ref"}}
    )
    value["target_occurrence_selector"] = load_target_occurrence_selector(connection, selector_ref=row["target_occurrence_selector_ref"])
    return value


def _stored_override(connection: sqlite3.Connection, row: dict[str, Any]) -> dict[str, object]:
    value = _omit_none(
        {
            key: value
            for key, value in row.items()
            if key not in {"recurrence_revision_id", "segment_ref", "target_occurrence_selector_ref"} and not key.endswith("_json")
        }
    )
    value["target_occurrence_selector"] = load_target_occurrence_selector(connection, selector_ref=row["target_occurrence_selector_ref"])
    for stored, public in (
        ("common_detail_patch_json", "common_detail_patch"),
        ("event_detail_patch_json", "event_detail_patch"),
        ("task_detail_patch_json", "task_detail_patch"),
    ):
        if row[stored] is not None:
            value[public] = json.loads(row[stored])
    return value


def _objects(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
        raise SpineValidationError("invalid_recurrence_storage", f"{field} must be an object array")
    return value


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpineValidationError("invalid_recurrence_storage", f"{field} must be an object")
    return value


def _omit_none(value: dict[str, Any]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item is not None}


def _json_text(value: object) -> str | None:
    return None if value is None else canonical_json_bytes(value).decode("utf-8")
