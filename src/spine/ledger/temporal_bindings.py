"""Persistence and deterministic read-state for relative temporal bindings."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from spine.core.errors import SpineValidationError
from spine.core.occurrences import expand_recurrence_set
from spine.core.schedule import resolve_local_instant, system_timezone_database_version
from spine.ledger.recurrence import load_current_recurrence_set, load_target_occurrence_selector

BINDING_STATES = (
    "retired",
    "snapshot_resolved",
    "snapshot_diverged",
    "target_terminal",
    "source_terminal",
    "relationship_inactive",
    "source_unresolved",
    "target_diverged",
    "stale",
    "current",
)


def insert_temporal_binding(connection: sqlite3.Connection, *, value: Mapping[str, object]) -> None:
    connection.execute(
        """
        INSERT INTO relative_temporal_bindings (
          temporal_binding_id, binding_contract, target_item_id, target_anchor_role,
          source_item_id, source_anchor_role, relationship_id, binding_mode,
          source_terminal_behavior, created_by_command_id, created_by_subject_id,
          created_at_utc, binding_status, retired_at_utc, retired_by_command_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["temporal_binding_id"],
            value["binding_contract"],
            value["target_item_id"],
            value["target_anchor_role"],
            value["source_item_id"],
            value["source_anchor_role"],
            value["relationship_id"],
            value["binding_mode"],
            value.get("source_terminal_behavior"),
            value["created_by_command_id"],
            value["created_by_subject_id"],
            value["created_at_utc"],
            value.get("binding_status", "active"),
            value.get("retired_at_utc"),
            value.get("retired_by_command_id"),
        ),
    )


def insert_temporal_binding_revision(connection: sqlite3.Connection, *, value: Mapping[str, object]) -> None:
    connection.execute(
        """
        INSERT INTO relative_temporal_binding_revisions (
          temporal_binding_revision_id, temporal_binding_id, revision_index,
          source_temporal_binding_revision_id, source_target_version, source_scope,
          source_anchor_id, source_recurrence_revision_id, source_occurrence_key,
          source_occurrence_selector_ref, source_occurrence_provenance_id,
          source_scheduled_fact, offset_basis, offset_seconds, resolved_source_utc,
          resolved_target_utc, target_local_date, target_local_time, target_timezone,
          target_timezone_database_version, target_item_version, target_anchor_id,
          resolution_kind, normalized_temporal_binding_revision_hash,
          created_by_command_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value["temporal_binding_revision_id"],
            value["temporal_binding_id"],
            int(str(value["revision_index"])),
            value.get("source_temporal_binding_revision_id"),
            int(str(value["source_target_version"])),
            value["source_scope"],
            value.get("source_anchor_id"),
            value.get("source_recurrence_revision_id"),
            value.get("source_occurrence_key"),
            value.get("source_occurrence_selector_ref"),
            value.get("source_occurrence_provenance_id"),
            value["source_scheduled_fact"],
            value["offset_basis"],
            int(str(value["offset_seconds"])),
            value["resolved_source_utc"],
            value["resolved_target_utc"],
            value["target_local_date"],
            value["target_local_time"],
            value["target_timezone"],
            value["target_timezone_database_version"],
            int(str(value["target_item_version"])),
            value["target_anchor_id"],
            value["resolution_kind"],
            value["normalized_temporal_binding_revision_hash"],
            value["created_by_command_id"],
            value["created_at_utc"],
        ),
    )


def retire_temporal_binding(connection: sqlite3.Connection, *, temporal_binding_id: str, command_id: str, retired_at_utc: str) -> None:
    cursor = connection.execute(
        """
        UPDATE relative_temporal_bindings
        SET binding_status = 'retired', retired_at_utc = ?, retired_by_command_id = ?
        WHERE temporal_binding_id = ? AND binding_status = 'active'
        """,
        (retired_at_utc, command_id, temporal_binding_id),
    )
    if cursor.rowcount != 1:
        raise SpineValidationError("stale_version:temporal_binding_id", "temporal binding is no longer active")


def load_temporal_binding(connection: sqlite3.Connection, temporal_binding_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM relative_temporal_bindings WHERE temporal_binding_id = ?",
        (temporal_binding_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("referenced_row_not_found:temporal_binding_id", "temporal binding not found")
    value = dict(row)
    value["latest_revision"] = load_latest_temporal_binding_revision(connection, temporal_binding_id)
    return value


def load_latest_temporal_binding_revision(connection: sqlite3.Connection, temporal_binding_id: str) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT * FROM relative_temporal_binding_revisions
        WHERE temporal_binding_id = ? ORDER BY revision_index DESC LIMIT 1
        """,
        (temporal_binding_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError("runtime_failure:temporal_binding_revision", "temporal binding has no revision")
    value = dict(row)
    for field in ("revision_index", "source_target_version", "offset_seconds", "target_item_version"):
        value[field] = str(value[field])
    if value.get("source_occurrence_selector_ref") is not None:
        value["target_occurrence_selector"] = load_target_occurrence_selector(
            connection, selector_ref=str(value["source_occurrence_selector_ref"])
        )
    return value


def active_binding_for_target(connection: sqlite3.Connection, *, item_id: str, anchor_role: str = "task_due") -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT temporal_binding_id FROM relative_temporal_bindings
        WHERE target_item_id = ? AND target_anchor_role = ? AND binding_status = 'active'
        """,
        (item_id, anchor_role),
    ).fetchone()
    return None if row is None else load_temporal_binding(connection, str(row["temporal_binding_id"]))


def binding_catalog_generation(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT binding_catalog_generation FROM temporal_binding_catalog_state WHERE singleton_id = 1").fetchone()
    if row is None:
        raise SpineValidationError("runtime_failure:binding_catalog_generation", "binding catalog singleton is missing")
    return int(row["binding_catalog_generation"])


def increment_binding_catalog_generation(connection: sqlite3.Connection) -> None:
    cursor = connection.execute(
        """
        UPDATE temporal_binding_catalog_state
        SET binding_catalog_generation = binding_catalog_generation + 1
        WHERE singleton_id = 1
        """
    )
    if cursor.rowcount != 1:
        raise SpineValidationError("runtime_failure:binding_catalog_generation", "binding catalog singleton is missing")


def binding_state(connection: sqlite3.Connection, binding: Mapping[str, object]) -> tuple[str, dict[str, object] | None]:
    revision = _mapping(binding["latest_revision"], "latest_revision")
    if binding["binding_status"] == "retired":
        return "retired", None
    target = _target_snapshot(connection, str(binding["target_item_id"]))
    if binding["binding_mode"] == "snapshot":
        return ("snapshot_resolved" if target is not None and _target_equals_revision(target, revision) else "snapshot_diverged"), None
    if target is None or target["terminal"]:
        return "target_terminal", None
    source_shell = connection.execute(
        "SELECT item_type, status, current_version FROM coordination_items WHERE item_id = ?",
        (binding["source_item_id"],),
    ).fetchone()
    if source_shell is None or source_shell["status"] != "active" or source_shell["item_type"] != "event":
        return "source_terminal", None
    source_detail = connection.execute(
        "SELECT event_status FROM event_details WHERE item_id = ? AND version = ?",
        (binding["source_item_id"], source_shell["current_version"]),
    ).fetchone()
    if source_detail is None or source_detail["event_status"] != "scheduled":
        return "source_terminal", None
    relation = connection.execute(
        "SELECT relation_status, relation_type, source_item_id, target_item_id FROM coordination_item_relations WHERE relation_id = ?",
        (binding["relationship_id"],),
    ).fetchone()
    if (
        relation is None
        or relation["relation_status"] != "active"
        or relation["relation_type"] != "part_of"
        or relation["source_item_id"] != binding["target_item_id"]
        or relation["target_item_id"] != binding["source_item_id"]
    ):
        return "relationship_inactive", None
    source = resolve_binding_source(connection, binding=binding, revision=revision)
    if source is None:
        return "source_unresolved", None
    if not _target_equals_revision(target, revision):
        return "target_diverged", source
    stale = int(str(source["source_target_version"])) != int(str(revision["source_target_version"]))
    stale = stale or source["source_scheduled_fact"] != revision["source_scheduled_fact"]
    stale = stale or source["resolved_source_utc"] != revision["resolved_source_utc"]
    if revision["source_scope"] == "selected_occurrence":
        stale = stale or source.get("source_recurrence_revision_id") != revision.get("source_recurrence_revision_id")
        stale = stale or source.get("source_occurrence_key") != revision.get("source_occurrence_key")
        stale = stale or source.get("source_occurrence_provenance_id") != revision.get("source_occurrence_provenance_id")
    return ("stale" if stale else "current"), source


def resolve_binding_source(
    connection: sqlite3.Connection, *, binding: Mapping[str, object], revision: Mapping[str, object]
) -> dict[str, object] | None:
    source_item_id = str(binding["source_item_id"])
    shell = connection.execute(
        "SELECT current_version FROM coordination_items WHERE item_id = ? AND item_type = 'event' AND status = 'active'",
        (source_item_id,),
    ).fetchone()
    if shell is None:
        return None
    version = int(shell["current_version"])
    if revision["source_scope"] == "item":
        row = connection.execute(
            """
            SELECT a.* FROM event_details AS e
            JOIN temporal_anchors AS a ON a.anchor_id = e.start_anchor_id
            WHERE e.item_id = ? AND e.version = ? AND e.event_status = 'scheduled'
            """,
            (source_item_id, version),
        ).fetchone()
        if row is None:
            return None
        anchor = dict(row)
        resolved = _anchor_resolution(anchor)
        if resolved is None:
            return None
        return {
            "source_target_version": str(version),
            "source_anchor_id": anchor["anchor_id"],
            "source_scheduled_fact": resolved["scheduled_fact"],
            "resolved_source_utc": resolved["utc_instant"],
            "timezone": resolved["timezone"],
            "timezone_database_version": resolved["timezone_database_version"],
        }
    recurrence = load_current_recurrence_set(connection, item_id=source_item_id)
    selector = revision.get("target_occurrence_selector")
    if recurrence is None or not isinstance(selector, Mapping):
        return None
    scheduled = selector.get("scheduled_fact")
    if not isinstance(scheduled, str):
        return None
    from spine.commands.core import _decorate_occurrence, _next_scheduled_fact

    expansion = expand_recurrence_set(
        recurrence,
        range_basis="original_schedule",
        range_start=scheduled,
        range_end=_next_scheduled_fact(scheduled, time_basis=str(recurrence["time_basis"])),
    )
    item = _source_item_for_occurrence(connection, source_item_id, version)
    matches = []
    for raw in expansion.occurrences:
        value = _decorate_occurrence(item, recurrence, dict(raw), include_internal=True)
        if value.get("target_occurrence_selector") == selector and value.get("actionable") is True:
            matches.append(value)
    if len(matches) != 1:
        return None
    occurrence = matches[0]
    expressed = str(occurrence["expressed_scheduled_fact"])
    if recurrence["time_basis"] == "instant_utc":
        utc_instant = expressed
        timezone = "UTC"
        timezone_version = system_timezone_database_version()
    else:
        resolution = occurrence.get("timezone_resolution")
        if not isinstance(resolution, Mapping):
            resolution = resolve_local_instant(
                expressed,
                timezone=str(recurrence["timezone"]),
                timezone_database_version=str(recurrence["timezone_database_version"]),
            )
            if resolution is None:
                return None
            utc_instant = resolution.utc_instant
        else:
            utc_instant = str(resolution["utc_instant"])
        timezone = str(recurrence["timezone"])
        timezone_version = str(recurrence["timezone_database_version"])
    provenance = connection.execute(
        """
        SELECT occurrence_provenance_id FROM occurrence_provenance
        WHERE item_id = ? AND recurrence_revision_id = ? AND occurrence_key = ?
          AND consumer = 'temporal_binding' AND management_status = 'active' AND actionable = 1
        ORDER BY occurrence_provenance_id LIMIT 1
        """,
        (source_item_id, recurrence["recurrence_revision_id"], occurrence["occurrence_key"]),
    ).fetchone()
    return {
        "source_target_version": str(version),
        "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
        "source_occurrence_key": occurrence["occurrence_key"],
        "source_occurrence_provenance_id": None if provenance is None else provenance["occurrence_provenance_id"],
        "target_occurrence_selector": dict(selector),
        "source_scheduled_fact": occurrence["original_scheduled_fact"],
        "resolved_source_utc": utc_instant,
        "timezone": timezone,
        "timezone_database_version": timezone_version,
        "occurrence": occurrence,
        "recurrence": recurrence,
    }


def binding_view(connection: sqlite3.Connection, temporal_binding_id: str) -> dict[str, object]:
    binding = load_temporal_binding(connection, temporal_binding_id)
    state, source = binding_state(connection, binding)
    revision = dict(_mapping(binding.pop("latest_revision"), "latest_revision"))
    mode = str(binding["binding_mode"])
    terminal_behavior = binding.get("source_terminal_behavior")
    automatic = state in {"stale", "target_terminal", "relationship_inactive"} or (
        state == "source_terminal" and terminal_behavior in {"cancel_target", "detach_at_last_value"}
    )
    decision = state in {"source_unresolved", "target_diverged"} or (state == "source_terminal" and terminal_behavior == "require_decision")
    recurrence_reconcile_input: dict[str, object] = {}
    if revision["source_scope"] == "selected_occurrence":
        source_recurrence_revision_id = (
            source.get("source_recurrence_revision_id") if source is not None else None
        ) or revision.get("source_recurrence_revision_id")
        recurrence_reconcile_input["source_recurrence_revision_id"] = source_recurrence_revision_id
    result: dict[str, object] = {
        **binding,
        "latest_revision": revision,
        "binding_state": state,
        "reconcile_required": mode == "follow_source" and binding["binding_status"] == "active" and state != "current",
        "automatic_reconcile_eligible": automatic and mode == "follow_source" and binding["binding_status"] == "active",
        "operator_decision_required": decision and mode == "follow_source" and binding["binding_status"] == "active",
        "reconcile_inputs": {
            "temporal_binding_id": temporal_binding_id,
            "target_temporal_binding_revision_id": revision["temporal_binding_revision_id"],
            "source_target_version": str(
                source["source_target_version"] if source is not None else _current_version(connection, str(binding["source_item_id"]))
            ),
            "target_target_version": str(_current_version(connection, str(binding["target_item_id"]))),
            "expected_binding_state": state,
            **recurrence_reconcile_input,
        },
    }
    if source is not None:
        result["current_source"] = {key: value for key, value in source.items() if key not in {"occurrence", "recurrence"}}
    return result


def active_follow_binding_current(connection: sqlite3.Connection, *, item_id: str) -> bool:
    binding = active_binding_for_target(connection, item_id=item_id)
    if binding is None or binding["binding_mode"] != "follow_source":
        return True
    state, _ = binding_state(connection, binding)
    return state == "current"


def _target_snapshot(connection: sqlite3.Connection, item_id: str) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT i.status AS shell_status, i.current_version, t.task_status, a.*
        FROM coordination_items AS i
        JOIN task_details AS t ON t.item_id = i.item_id AND t.version = i.current_version
        LEFT JOIN temporal_anchors AS a ON a.anchor_id = t.due_anchor_id
        WHERE i.item_id = ? AND i.item_type = 'task'
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    value = dict(row)
    value["terminal"] = value["shell_status"] != "active" or value["task_status"] != "open" or value.get("anchor_id") is None
    resolution = None if value.get("anchor_id") is None else _anchor_resolution(value)
    if resolution is not None:
        value.update(resolution)
    return value


def _target_equals_revision(target: Mapping[str, object], revision: Mapping[str, object]) -> bool:
    return (
        target.get("anchor_kind") == "local_instant"
        and target.get("local_date") == revision.get("target_local_date")
        and target.get("local_time") == revision.get("target_local_time")
        and target.get("timezone") == revision.get("target_timezone")
        and target.get("timezone_database_version") == revision.get("target_timezone_database_version")
        and target.get("utc_instant") == revision.get("resolved_target_utc")
    )


def _anchor_resolution(anchor: Mapping[str, object]) -> dict[str, str] | None:
    kind = anchor.get("anchor_kind")
    if kind == "instant_utc":
        value = str(anchor["utc_instant"])
        return {
            "scheduled_fact": value,
            "utc_instant": value,
            "timezone": "UTC",
            "timezone_database_version": system_timezone_database_version(),
        }
    if kind != "local_instant":
        return None
    scheduled = f"{anchor['local_date']}T{anchor['local_time']}"
    resolution = resolve_local_instant(
        scheduled,
        timezone=str(anchor["timezone"]),
        timezone_database_version=str(anchor["timezone_database_version"]),
    )
    if resolution is None:
        return None
    return {
        "scheduled_fact": scheduled,
        "utc_instant": resolution.utc_instant,
        "timezone": str(anchor["timezone"]),
        "timezone_database_version": str(anchor["timezone_database_version"]),
    }


def target_from_source(source: Mapping[str, object], offset_seconds: int) -> dict[str, str]:
    source_utc = datetime.strptime(str(source["resolved_source_utc"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    from datetime import timedelta

    target_utc = source_utc + timedelta(seconds=offset_seconds)
    timezone = str(source["timezone"])
    local = target_utc.astimezone(ZoneInfo(timezone))
    return {
        "local_date": local.date().isoformat(),
        "local_time": local.strftime("%H:%M:%S"),
        "timezone": timezone,
        "timezone_database_version": str(source["timezone_database_version"]),
        "utc_instant": target_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _current_version(connection: sqlite3.Connection, item_id: str) -> int:
    row = connection.execute("SELECT current_version FROM coordination_items WHERE item_id = ?", (item_id,)).fetchone()
    return 0 if row is None else int(row["current_version"])


def _source_item_for_occurrence(connection: sqlite3.Connection, item_id: str, version: int) -> dict[str, object]:
    from spine.commands.core import _hydrated_item_at_version

    return _hydrated_item_at_version(connection, item_id, version)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(f"runtime_failure:{field}", f"{field} must be an object")
    return value
