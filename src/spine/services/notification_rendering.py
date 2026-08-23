"""Resolve current Spine truth into deterministic notification renderings."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.notification_rendering import NotificationRendering, render_notification
from spine.ledger.items import get_current_item
from spine.ledger.temporal_bindings import active_binding_for_target, binding_state


def resolve_notification_rendering(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    attempt_id: str,
    attempted_at_utc: str,
) -> NotificationRendering:
    """Resolve current canonical facts and render one ordinary reminder attempt."""

    if work_row.get("work_kind") != "notification_reminder" or work_row.get("notification_opportunity_id") is None:
        raise SpineValidationError(
            "notification_rendering_unsupported_work",
            "v1 rendering requires structured notification_reminder work",
        )
    item_id = str(work_row["item_id"])
    item = get_current_item(connection, item_id)
    item_type = str(item["item_type"])
    if item_type not in {"event", "task"}:
        raise SpineValidationError(
            "notification_rendering_unsupported_work",
            f"v1 rendering does not support item type {item_type}",
        )
    version = int(item["current_version"])
    version_facts = _mapping(item["version"], "item.version")
    anchor_role = str(work_row.get("target_anchor_role") or "")
    expected_anchor_role = "event_start" if item_type == "event" else "task_due"
    if anchor_role != expected_anchor_role:
        _unresolved("work target anchor role does not match the current item")

    target = _target_facts(connection, work_row=work_row, item_id=item_id, item_version=version)
    primary_location = _primary_location(item)
    source: dict[str, Any] = {
        "attempt_id": attempt_id,
        "attempted_at_utc": attempted_at_utc,
        "work_instance_id": str(work_row["work_instance_id"]),
        "notification_opportunity_id": str(work_row["notification_opportunity_id"]),
        "notification_intent_id": _required_work_fact(work_row, "notification_intent_id"),
        "item_id": item_id,
        "rendered_item_version": str(version),
        "item_type": item_type,
        "title": version_facts.get("title"),
        "anchor_role": anchor_role,
        **target,
        "primary_location": primary_location,
    }
    if item_type == "task":
        binding = active_binding_for_target(connection, item_id=item_id)
        if binding is not None and binding.get("binding_mode") == "follow_source":
            state, _ = binding_state(connection, binding)
            if state != "current":
                _unresolved("follow-source temporal binding is not current")
            revision = _mapping(binding["latest_revision"], "temporal_binding.latest_revision")
            source.update(
                {
                    "temporal_binding_id": str(binding["temporal_binding_id"]),
                    "temporal_binding_revision_id": str(revision["temporal_binding_revision_id"]),
                }
            )
    return render_notification(source)


def assert_rendering_matches_current(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    rendering: NotificationRendering,
) -> None:
    """Re-resolve a rendering inside the attempt-start transaction."""

    current = resolve_notification_rendering(
        connection,
        work_row=work_row,
        attempt_id=rendering.attempt_id,
        attempted_at_utc=rendering.attempted_at_utc,
    )
    if (
        current.notification_rendering_id != rendering.notification_rendering_id
        or current.rendering_input_hash != rendering.rendering_input_hash
        or current.rendered_content_hash != rendering.rendered_content_hash
        or current.body_text != rendering.body_text
    ):
        raise SpineValidationError(
            "notification_rendering_persistence_conflict",
            "rendering source facts changed before attempt persistence",
        )


def _target_facts(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    item_id: str,
    item_version: int,
) -> dict[str, Any]:
    provenance_id = work_row.get("occurrence_provenance_id")
    if provenance_id is not None:
        row = connection.execute(
            """
            SELECT op.*, rs.time_basis
            FROM occurrence_provenance AS op
            JOIN recurrence_sets AS rs ON rs.recurrence_set_id = op.recurrence_set_id
            WHERE op.occurrence_provenance_id = ?
            """,
            (str(provenance_id),),
        ).fetchone()
        if row is None or row["management_status"] != "active" or row["actionable"] != 1:
            _unresolved("current occurrence provenance is unavailable")
        scheduled_fact = str(row["expressed_scheduled_fact"])
        target_at_utc = row["timezone_utc_instant"] or (scheduled_fact if scheduled_fact.endswith("Z") else None)
        _require_work_target_match(work_row, scheduled_fact=scheduled_fact, target_at_utc=target_at_utc)
        time_basis = str(row["time_basis"])
        result = _display_authority(
            time_basis=time_basis,
            timezone=row["timezone"],
            timezone_database_version=row["timezone_database_version"],
            scheduled_fact=scheduled_fact,
            target_at_utc=target_at_utc,
        )
        result.update(
            {
                "recurrence_revision_id": str(row["recurrence_revision_id"]),
                "occurrence_key": str(row["occurrence_key"]),
                "occurrence_provenance_id": str(row["occurrence_provenance_id"]),
            }
        )
        return result

    detail_table, anchor_column = (
        ("event_details", "start_anchor_id") if work_row.get("target_anchor_role") == "event_start" else ("task_details", "due_anchor_id")
    )
    anchor = connection.execute(
        f"""
        SELECT a.* FROM {detail_table} AS d
        JOIN temporal_anchors AS a ON a.anchor_id = d.{anchor_column}
        WHERE d.item_id = ? AND d.version = ?
        """,
        (item_id, item_version),
    ).fetchone()
    if anchor is None:
        _unresolved("current target anchor is unavailable")
    time_basis = str(anchor["anchor_kind"])
    if time_basis == "instant_utc":
        scheduled_fact = str(anchor["utc_instant"])
        target_at_utc: object | None = anchor["utc_instant"]
    elif time_basis == "local_date":
        scheduled_fact = str(anchor["local_date"])
        target_at_utc = None
    elif time_basis == "local_instant":
        scheduled_fact = f"{anchor['local_date']}T{anchor['local_time']}"
        target_at_utc = work_row.get("target_at_utc")
    else:
        raise SpineValidationError(
            "notification_rendering_unsupported_work",
            f"v1 rendering does not support anchor kind {time_basis}",
        )
    _require_work_target_match(work_row, scheduled_fact=scheduled_fact, target_at_utc=target_at_utc)
    return _display_authority(
        time_basis=time_basis,
        timezone=anchor["timezone"],
        timezone_database_version=anchor["timezone_database_version"],
        scheduled_fact=scheduled_fact,
        target_at_utc=target_at_utc,
    )


def _display_authority(
    *,
    time_basis: str,
    timezone: object,
    timezone_database_version: object,
    scheduled_fact: str,
    target_at_utc: object,
) -> dict[str, Any]:
    if time_basis == "instant_utc":
        return {
            "target_scheduled_fact": scheduled_fact,
            "target_at_utc": str(target_at_utc),
            "display_time_basis": "instant_utc",
            "display_timezone": "UTC",
            "timezone_database_version": None,
        }
    if not isinstance(timezone, str) or not timezone:
        _unresolved("local target timezone is unavailable")
    if not isinstance(timezone_database_version, str) or not timezone_database_version:
        _unresolved("local target timezone database version is unavailable")
    result: dict[str, Any] = {
        "target_scheduled_fact": scheduled_fact,
        "display_time_basis": time_basis,
        "display_timezone": timezone,
        "timezone_database_version": timezone_database_version,
    }
    if time_basis == "local_instant":
        if not isinstance(target_at_utc, str) or not target_at_utc:
            _unresolved("local-instant target UTC resolution is unavailable")
        result["target_at_utc"] = target_at_utc
    return result


def _require_work_target_match(work_row: Mapping[str, object], *, scheduled_fact: str, target_at_utc: object) -> None:
    if work_row.get("target_scheduled_fact") != scheduled_fact or work_row.get("target_at_utc") != target_at_utc:
        _unresolved("work target snapshot does not match current canonical target")


def _primary_location(item: Mapping[str, object]) -> dict[str, str] | None:
    locations = item.get("locations")
    if not isinstance(locations, list):
        return None
    for value in locations:
        if isinstance(value, Mapping) and value.get("role") == "primary":
            return {
                "location_id": str(value["location_id"]),
                "item_location_id": str(value["item_location_id"]),
                "location_kind": str(value["kind"]),
                "location_label": str(value["label"]),
            }
    return None


def _required_work_fact(work_row: Mapping[str, object], name: str) -> str:
    value = work_row.get(name)
    if not isinstance(value, str) or not value:
        _unresolved(f"work is missing {name}")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _unresolved(f"{field} is unavailable")
    return value


def _unresolved(message: str) -> None:
    raise SpineValidationError("notification_rendering_source_unresolved", message)
