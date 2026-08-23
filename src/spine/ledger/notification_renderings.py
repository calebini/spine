"""Immutable notification-rendering evidence persistence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from typing import Any

from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.notification_rendering import NotificationRendering


def insert_notification_rendering(
    connection: sqlite3.Connection,
    *,
    rendering: NotificationRendering,
    manage_transaction: bool = True,
) -> None:
    """Persist one immutable rendering linked to its started attempt."""

    value = rendering.as_persistence()
    try:
        with connection if manage_transaction else nullcontext():
            connection.execute(
                """
                INSERT INTO notification_renderings (
                  notification_rendering_id, attempt_id, work_instance_id,
                  notification_opportunity_id, notification_intent_id, item_id,
                  rendered_item_version, rendering_contract, rendering_profile,
                  input_normalization_version, canonical_json_version,
                  rendering_input_hash, rendered_content_hash, body_text, phrase_kind,
                  attempted_at_utc, target_scheduled_fact, target_at_utc,
                  display_time_basis, display_timezone, timezone_database_version,
                  delta_seconds, occurrence_provenance_id, recurrence_revision_id,
                  occurrence_key, temporal_binding_id, temporal_binding_revision_id,
                  location_id, item_location_id, location_kind, location_label,
                  source_input_json, phrase_facts_json, created_at_utc
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    value["notification_rendering_id"],
                    value["attempt_id"],
                    value["work_instance_id"],
                    value["notification_opportunity_id"],
                    value["notification_intent_id"],
                    value["item_id"],
                    value["rendered_item_version"],
                    value["rendering_contract"],
                    value["rendering_profile"],
                    value["input_normalization_version"],
                    value["canonical_json_version"],
                    value["rendering_input_hash"],
                    value["rendered_content_hash"],
                    value["body_text"],
                    value["phrase_kind"],
                    value["attempted_at_utc"],
                    value["target_scheduled_fact"],
                    value["target_at_utc"],
                    value["display_time_basis"],
                    value["display_timezone"],
                    value["timezone_database_version"],
                    int(value["delta_seconds"]) if value["delta_seconds"] is not None else None,
                    value["occurrence_provenance_id"],
                    value["recurrence_revision_id"],
                    value["occurrence_key"],
                    value["temporal_binding_id"],
                    value["temporal_binding_revision_id"],
                    value["location_id"],
                    value["item_location_id"],
                    value["location_kind"],
                    value["location_label"],
                    value["source_input_json"],
                    value["phrase_facts_json"],
                    value["created_at_utc"],
                ),
            )
    except sqlite3.Error as exc:
        raise SpineValidationError(
            "notification_rendering_persistence_conflict",
            str(exc),
        ) from exc


def get_notification_rendering(connection: sqlite3.Connection, *, attempt_id: str) -> dict[str, Any] | None:
    """Load and validate stored rendering evidence for one attempt."""

    row = connection.execute(
        "SELECT * FROM notification_renderings WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return None
    value: dict[str, Any] = dict(row)
    source_input = _canonical_object(value.pop("source_input_json"), "source_input_json")
    phrase_facts = _canonical_object(value.pop("phrase_facts_json"), "phrase_facts_json")
    value["rendered_item_version"] = str(value["rendered_item_version"])
    if value.get("delta_seconds") is not None:
        value["delta_seconds"] = str(value["delta_seconds"])
    value["source_input"] = source_input
    value["phrase_facts"] = phrase_facts
    return value


def notification_rendering_view(value: dict[str, Any]) -> dict[str, Any]:
    """Project stored rendering evidence into the capability-gated readback shape."""

    fields = (
        "notification_rendering_id",
        "attempt_id",
        "work_instance_id",
        "notification_opportunity_id",
        "notification_intent_id",
        "item_id",
        "rendered_item_version",
        "rendering_contract",
        "rendering_profile",
        "input_normalization_version",
        "canonical_json_version",
        "rendering_input_hash",
        "rendered_content_hash",
        "body_text",
        "phrase_kind",
        "attempted_at_utc",
        "target_scheduled_fact",
        "target_at_utc",
        "display_time_basis",
        "display_timezone",
        "timezone_database_version",
        "delta_seconds",
        "occurrence_provenance_id",
        "recurrence_revision_id",
        "occurrence_key",
        "temporal_binding_id",
        "temporal_binding_revision_id",
        "created_at_utc",
        "source_input",
        "phrase_facts",
    )
    result = {field: value[field] for field in fields if value.get(field) is not None}
    if value.get("location_id") is None:
        result["primary_location"] = None
    else:
        result["primary_location"] = {
            "location_id": value["location_id"],
            "item_location_id": value["item_location_id"],
            "location_kind": value["location_kind"],
            "location_label": value["location_label"],
        }
    return result


def _canonical_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise SpineValidationError("notification_rendering_persistence_conflict", f"{field} is not text")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SpineValidationError("notification_rendering_persistence_conflict", f"{field} is invalid JSON") from exc
    if not isinstance(parsed, dict) or canonical_json_text(parsed) != value:
        raise SpineValidationError("notification_rendering_persistence_conflict", f"{field} is not canonical JSON")
    return parsed
