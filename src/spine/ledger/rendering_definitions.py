"""Immutable rendering support and transaction-owned policy finalization.

This module is candidate-only until the complete integration release activates.
Policy support is staged until the owning transaction finalizes: existing editors
may delete a just-copied policy before replacing it, but committed support is immutable.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.core import rendering_definitions as codec
from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError


def invariant(condition: bool, message: str = "rendering persistence invariant failed") -> None:
    if not condition:
        raise SpineValidationError("environment_failure:rendering", message)


def root_owner(row: Mapping[str, Any]) -> dict[str, str]:
    return {k: row[k] for k in ("owner_kind", "owner_subject_id", "owner_group_id") if row[k] is not None}


def load_revision(db: sqlite3.Connection, revision_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT * FROM notification_rendering_definition_revisions WHERE notification_rendering_definition_revision_id=?", (revision_id,)
    ).fetchone()
    invariant(row is not None, "missing rendering revision")
    revision = codec.stored_object(row["revision_json"], 8192)
    invariant(row["contract_version"] == codec.DEFINITIONS and row["canonical_json_version"] == codec.CANON)
    invariant(codec.normalize_revision(revision) == revision)
    invariant(codec.content_hash(codec.DEFINITIONS, "revision", revision) == row["definition_hash"])
    root = db.execute(
        "SELECT notification_rendering_definition_id FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?",
        (row["notification_rendering_definition_id"],),
    ).fetchone()
    invariant(root is not None)
    projected = db.execute(
        "SELECT selection_key,facet_key,facet_schema_revision_id,field_key,projection,label "
        "FROM notification_rendering_definition_fields WHERE definition_revision_id=? ORDER BY selection_index LIMIT 9",
        (revision_id,),
    ).fetchall()
    columns = ("selection_key", "facet_key", "facet_schema_revision_id", "field_key", "projection", "label")
    invariant([tuple(r) for r in projected] == [tuple(s[c] for c in columns) for s in revision["selections"]])
    return {**dict(row), "revision": revision}


def load_disclosure(db: sqlite3.Connection, authorization_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM notification_rendering_disclosures WHERE disclosure_authorization_id=?", (authorization_id,)).fetchone()
    invariant(row is not None, "missing rendering disclosure")
    scope = codec.stored_object(row["scope_json"], 24576)
    invariant(
        codec.normalize_scope(scope) == scope
        and row["scope_contract_version"] == codec.DISCLOSURES
        and row["canonical_json_version"] == codec.CANON
    )
    invariant(row["scope_hash"] == codec.content_hash(codec.DISCLOSURES, "scope", scope) and row["match_hash"] == codec.match_hash(scope))
    ref = scope["definition"]
    invariant(
        (row["definition_root_id"], row["definition_revision_id"])
        == tuple(ref[k] for k in ("notification_rendering_definition_id", "notification_rendering_definition_revision_id"))
    )
    invariant(root_owner(row) == scope["item_owner"])
    recipient = scope["destination"]["recipient"]
    invariant(row["delivery_target_id"] == scope["destination"]["delivery_target_id"])
    invariant((row["recipient_subject_id"], row["recipient_group_id"]) == (recipient.get("subject_id"), recipient.get("group_id")))
    locations = [
        r[0]
        for r in db.execute(
            "SELECT location_id FROM notification_rendering_disclosure_locations "
            "WHERE disclosure_authorization_id=? ORDER BY location_id LIMIT 65",
            (authorization_id,),
        )
    ]
    invariant(locations == scope["permitted_location_ids"])
    profiles = [
        r[0]
        for r in db.execute(
            "SELECT notification_profile_id FROM notification_rendering_disclosure_profiles WHERE disclosure_authorization_id=?",
            (authorization_id,),
        )
    ]
    invariant(profiles == ([scope["use_scope"]["notification_profile_id"]] if scope["use_scope"]["kind"] == "profile" else []))
    definition = load_revision(db, row["definition_revision_id"])
    invariant(definition["notification_rendering_definition_id"] == row["definition_root_id"])
    invariant(set(scope["approved_selection_keys"]) <= {s["selection_key"] for s in definition["revision"]["selections"]})
    return {**dict(row), "scope": scope}


def load_presentation(db: sqlite3.Connection, policy_id: str, *, pending: bool = True) -> dict[str, Any]:
    staged = getattr(db, "_rendering_pending", {})
    if pending and policy_id in staged:
        return dict(staged[policy_id])
    row = db.execute("SELECT * FROM notification_policy_presentations WHERE notification_policy_id=?", (policy_id,)).fetchone()
    invariant(row is not None, "missing explicit policy presentation")
    value = codec.stored_object(row["presentation_json"], 8192)
    invariant(codec.normalize_presentation(value) == value and codec.presentation_hash(value) == row["presentation_hash"])
    invariant(row["presentation_contract_version"] == codec.PRESENTATION and row["canonical_json_version"] == codec.CANON)
    policy = db.execute(
        "SELECT item_id,version,source_notification_policy_id FROM notification_policies WHERE policy_id=?", (policy_id,)
    ).fetchone()
    invariant(policy is not None and (row["item_id"], row["item_version"], row["source_policy_id"]) == tuple(policy))
    if value["kind"] == "ordinary":
        invariant(all(row[k] is None for k in ("definition_root_id", "definition_revision_id", "disclosure_authorization_id")))
    else:
        ref = value["definition"]
        invariant(
            row["definition_root_id"] == ref["notification_rendering_definition_id"]
            and row["definition_revision_id"] == ref["notification_rendering_definition_revision_id"]
            and row["disclosure_authorization_id"] == value["disclosure_authorization_id"]
        )
        disclosure = load_disclosure(db, value["disclosure_authorization_id"])
        invariant(disclosure["scope_hash"] == value["disclosure_scope_hash"] and disclosure["scope"]["definition"] == ref)
        invariant(set(value["effective_selection_keys"]) <= set(disclosure["scope"]["approved_selection_keys"]))
        origin = value["origin"]
        invariant(disclosure["scope"]["use_scope"] == codec.use_scope(origin), "presentation use scope differs from its origin")
        if origin["kind"] in {"profile_template", "profile_replacement"}:
            application = db.execute(
                "SELECT a.notification_profile_id,a.notification_profile_revision_id,p.policy_origin,p.source_key "
                "FROM notification_profile_application_policies p JOIN notification_profile_applications a "
                "USING(notification_profile_application_id) WHERE p.notification_policy_id=?",
                (policy_id,),
            ).fetchone()
            invariant(
                application is not None
                and tuple(application)
                == (origin["notification_profile_id"], origin["notification_profile_revision_id"], origin["kind"], origin["template_key"]),
                "presentation profile origin lacks exact application evidence",
            )
    return value


def stage_policy(db: sqlite3.Connection, policy: Mapping[str, Any]) -> None:
    if not getattr(db, "_renderings_enabled", False):
        return
    identity = str(policy["notification_policy_id"])
    invariant(identity not in db._rendering_pending, "duplicate policy producer")
    source = policy.get("source_notification_policy_id")
    db._rendering_pending[identity] = load_presentation(db, str(source)) if source else {"kind": "ordinary"}


def select_presentation(db: sqlite3.Connection, policy_id: str, presentation: object) -> None:
    invariant(getattr(db, "_renderings_enabled", False) and db.in_transaction)
    invariant(policy_id in db._rendering_pending, "presentation can only be selected for a fresh policy")
    db._rendering_pending[policy_id] = codec.normalize_presentation(presentation)


def insert_presentation(db: sqlite3.Connection, policy: Mapping[str, Any], presentation: Mapping[str, Any]) -> None:
    value = codec.normalize_presentation(presentation)
    ref = value.get("definition", {})
    db.execute(
        "INSERT INTO notification_policy_presentations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            policy["policy_id"],
            policy["item_id"],
            policy["version"],
            codec.PRESENTATION,
            codec.CANON,
            canonical_json_text(value),
            codec.presentation_hash(value),
            ref.get("notification_rendering_definition_id"),
            ref.get("notification_rendering_definition_revision_id"),
            value.get("disclosure_authorization_id"),
            policy["source_notification_policy_id"],
        ),
    )


def finalize(db: sqlite3.Connection) -> None:
    """Check only transaction-owned versions and catalog objects, never history."""
    invariant(getattr(db, "_renderings_enabled", False))
    versions = set(db._facet_versions) | set(db._rendering_versions)
    for item_id, version in sorted(versions):
        policies = db.execute(
            "SELECT * FROM notification_policies WHERE item_id=? AND version=? ORDER BY policy_id LIMIT 101", (item_id, version)
        ).fetchall()
        invariant(len(policies) <= 100, "rendering policy capacity exceeded")
        sources = set()
        for row in policies:
            policy_id, source = row["policy_id"], row["source_notification_policy_id"]
            existing = db.execute("SELECT 1 FROM notification_policy_presentations WHERE notification_policy_id=?", (policy_id,)).fetchone()
            if not existing:
                invariant(policy_id in db._rendering_pending, "unregistered policy writer or missing presentation")
                insert_presentation(db, row, db._rendering_pending[policy_id])
            presentation = load_presentation(db, policy_id, pending=False)
            if source:
                predecessor = db.execute(
                    "SELECT item_id,version,notification_intent_id FROM notification_policies WHERE policy_id=?", (source,)
                ).fetchone()
                invariant(
                    predecessor is not None
                    and predecessor["item_id"] == item_id
                    and predecessor["version"] < version
                    and predecessor["notification_intent_id"] == row["notification_intent_id"]
                    and source not in sources,
                    "forked or invalid presentation ancestry",
                )
                sources.add(source)
                prior = load_presentation(db, source, pending=False)
                if prior["kind"] == "definition" and presentation["kind"] == "definition":
                    invariant(prior["origin"] == presentation["origin"], "copied presentation origin changed")
        count = db.execute(
            "SELECT COUNT(*) FROM notification_policy_presentations WHERE item_id=? AND item_version=?", (item_id, version)
        ).fetchone()[0]
        invariant(count == len(policies), "policy presentation set mismatch")
    for kind, identity in sorted(db._rendering_catalog):
        if kind == "root":
            root = db.execute(
                "SELECT * FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?", (identity,)
            ).fetchone()
            invariant(root is not None)
            latest = db.execute(
                "SELECT notification_rendering_definition_revision_id FROM notification_rendering_definition_revisions "
                "WHERE notification_rendering_definition_id=? ORDER BY revision_number DESC LIMIT 1",
                (identity,),
            ).fetchone()
            invariant(latest is not None and root["current_revision_id"] == latest[0], "rendering root does not select its latest revision")
            load_revision(db, latest[0])
        elif kind == "revision":
            load_revision(db, identity)
        elif kind == "disclosure":
            load_disclosure(db, identity)
    from spine.ledger.notification_profiles import load_profile

    for identity in sorted(db._rendering_profiles):
        parent = db.execute(
            "SELECT notification_profile_id FROM notification_profile_revisions WHERE notification_profile_revision_id=?", (identity,)
        ).fetchone()
        invariant(parent is not None)
        load_profile(db, parent[0], revision_id=identity)
    from spine.ledger.notification_renderings import get_notification_rendering
    for attempt_id in sorted(db._rendering_attempts):
        invariant(get_notification_rendering(db, attempt_id=attempt_id) is not None, "missing attempt rendering")
    if db._rendering_catalog:
        db.execute(
            "UPDATE notification_rendering_catalog_state SET generation=generation+1 WHERE singleton=1 AND generation<?",
            (codec.MAX_INTEGER,),
        )
        invariant(db.execute("SELECT changes()").fetchone()[0] == 1, "rendering catalog generation exhausted")


def verify_deep(db: sqlite3.Connection) -> None:
    """Explicit offline verification; deliberately scans immutable history."""
    for r in db.execute("SELECT notification_rendering_definition_revision_id FROM notification_rendering_definition_revisions"):
        load_revision(db, r[0])
    for r in db.execute("SELECT disclosure_authorization_id FROM notification_rendering_disclosures"):
        load_disclosure(db, r[0])
    for r in db.execute("SELECT policy_id FROM notification_policies"):
        load_presentation(db, r[0], pending=False)
    invalid_ancestry = db.execute("""SELECT 1 FROM notification_policies p LEFT JOIN notification_policies s
        ON s.policy_id=p.source_notification_policy_id
        WHERE p.source_notification_policy_id IS NOT NULL AND
          (s.policy_id IS NULL OR s.item_id!=p.item_id OR s.version>=p.version OR s.notification_intent_id!=p.notification_intent_id)
        LIMIT 1""").fetchone()
    forks = db.execute("""SELECT 1 FROM notification_policies WHERE source_notification_policy_id IS NOT NULL
        GROUP BY item_id,version,source_notification_policy_id HAVING COUNT(*)>1 LIMIT 1""").fetchone()
    invariant(invalid_ancestry is None and forks is None, "invalid historical presentation ancestry")
    from spine.ledger.notification_profiles import load_profile
    from spine.ledger.rendering_profiles import decode_revision

    for r in db.execute("SELECT notification_profile_id,notification_profile_revision_id FROM notification_profile_revisions"):
        value = load_profile(db, r[0], revision_id=r[1])
        if not getattr(db, "_renderings_enabled", False):
            decode_revision(db, value)
    invariant(
        db.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0]
        == db.execute("SELECT COUNT(*) FROM notification_policy_presentations").fetchone()[0]
    )
    from spine.ledger.notification_renderings import get_notification_rendering
    for row in db.execute("SELECT attempt_id FROM notification_renderings"):
        invariant(get_notification_rendering(db, attempt_id=row[0]) is not None)
