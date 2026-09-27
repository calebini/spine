"""Facet-only version equivalence; no work, lease, attempt or rendering mutations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from spine.core.errors import SpineValidationError
from spine.ledger.notifications import load_current_notification_policies

POLICY_FIELDS = (
    "notification_intent_id",
    "intent_created_item_version",
    "intent_created_by_command_id",
    "status",
    "recipient_kind",
    "recipient_subject_id",
    "recipient_group_id",
    "channel",
    "delivery_target_id",
    "target",
    "normalized_notification_schedule_hash",
    "late_handling",
)


def policy_meaning(policy: dict[str, Any]) -> dict[str, Any]:
    return {k: policy.get(k) for k in POLICY_FIELDS}


def capture(db: sqlite3.Connection, item_id: str, version: int) -> dict[str, Any]:
    """Exact bounded target-local proof, excluding only documented copy evidence."""
    proof: dict[str, Any] = {}
    shell = dict(db.execute("SELECT * FROM coordination_items WHERE item_id=?", (item_id,)).fetchone())
    proof["item"] = {k: v for k, v in shell.items() if k not in {"current_version", "updated_at_utc"}}
    for table, version_column, excluded in (
        ("coordination_item_versions", "version", {"created_at_utc", "created_by_subject_id"}),
        ("event_details", "version", set()),
        ("task_details", "version", set()),
        ("item_locations", "version", {"item_location_id", "created_at_utc"}),
        ("item_subject_roles", "version", {"item_subject_role_id", "created_at_utc"}),
        ("item_archetype_assignments", "item_version", {"item_archetype_assignment_id", "created_at_utc", "created_by_command_id"}),
        (
            "notification_profile_applications",
            "item_version",
            {"notification_profile_application_id", "item_archetype_assignment_id", "created_at_utc", "created_by_command_id"},
        ),
    ):
        rows = db.execute(f"SELECT * FROM {table} WHERE item_id=? AND {version_column}=? LIMIT 101", (item_id, version)).fetchall()
        if len(rows) > 100:
            raise SpineValidationError("environment_failure:capacity", "facet continuity capacity exceeded")
        proof[table] = sorted(
            ({k: v for k, v in dict(r).items() if k not in excluded | {version_column}} for r in rows),
            key=lambda v: json.dumps(v, sort_keys=True),
        )
    anchor_ids = sorted(
        {
            value
            for table in ("event_details", "task_details")
            for detail in proof[table]
            for key, value in detail.items()
            if key.endswith("_anchor_id") and value is not None
        }
    )
    proof["anchors"] = [
        tuple(db.execute("SELECT * FROM temporal_anchors WHERE anchor_id=?", (anchor_id,)).fetchone()) for anchor_id in anchor_ids
    ]
    proof["profile_policies"] = [
        tuple(r)
        for r in db.execute(
            "SELECT p.policy_origin,p.source_key,p.notification_profile_template_id,p.notification_intent_id "
            "FROM notification_profile_applications a JOIN notification_profile_application_policies p "
            "ON p.notification_profile_application_id=a.notification_profile_application_id "
            "WHERE a.item_id=? AND a.item_version=? ORDER BY p.policy_origin,p.source_key LIMIT 101",
            (item_id, version),
        )
    ]
    if len(proof["profile_policies"]) > 100:
        raise SpineValidationError("environment_failure:capacity", "facet continuity capacity exceeded")
    policies = load_current_notification_policies(db, item_id=item_id)
    if len(policies) > 100:
        raise SpineValidationError("environment_failure:capacity", "facet continuity capacity exceeded")
    proof["policies"] = sorted((policy_meaning(p) for p in policies), key=lambda p: str(p["notification_intent_id"]))
    if len({p["notification_intent_id"] for p in proof["policies"]}) != len(policies):
        raise SpineValidationError("environment_failure:facets", "ambiguous notification intent")
    proof["recurrence"] = [
        tuple(r)
        for r in db.execute(
            "SELECT rr.recurrence_revision_id,rr.normalized_recurrence_set_hash FROM recurrence_sets rs "
            "JOIN recurrence_revisions rr ON rr.recurrence_set_id=rs.recurrence_set_id "
            "WHERE rs.source_item_id=? AND rr.source_item_version<=? "
            "ORDER BY rr.source_item_version DESC,rr.revision_number DESC LIMIT 1",
            (item_id, version),
        )
    ]
    proof["bindings"] = [
        tuple(r)
        for r in db.execute(
            "SELECT * FROM relative_temporal_bindings WHERE target_item_id=? ORDER BY temporal_binding_id LIMIT 101", (item_id,)
        )
    ]
    if len(proof["bindings"]) > 100:
        raise SpineValidationError("environment_failure:capacity", "facet continuity capacity exceeded")
    proof["binding_revisions"] = [
        tuple(row)
        for binding in proof["bindings"]
        for row in db.execute(
            "SELECT * FROM relative_temporal_binding_revisions WHERE temporal_binding_id=? ORDER BY revision_index DESC LIMIT 1",
            (binding[0],),
        )
    ]
    return proof


def verify(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        raise SpineValidationError("environment_failure:facets", "facet-only notification equivalence failed")
