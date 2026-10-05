"""Pinned profile decoder: v1 history is never rehashed as v2."""

from spine.core import rendering_definitions as codec
from spine.core.notification_profiles import normalize_profile_revision
from spine.ledger.rendering_definitions import invariant, load_revision, root_owner


def decode_revision(db, profile):
    revision = profile["revision"]
    marker = db.execute(
        "SELECT profile_contract_version FROM notification_profile_rendering_revisions WHERE notification_profile_revision_id=?",
        (revision["notification_profile_revision_id"],),
    ).fetchone()
    templates = []
    for template in revision["templates"]:
        row = db.execute(
            "SELECT * FROM notification_profile_template_renderings WHERE notification_profile_template_id=?",
            (template["notification_profile_template_id"],),
        ).fetchone()
        normalized = {k: template[k] for k in ("template_key", "schedule", "late_handling")}
        if marker:
            invariant(marker[0] == codec.PROFILE_V2 and row is not None)
            rendering = {"kind": row["kind"]}
            if row["kind"] == "definition":
                rendering["definition"] = {
                    "notification_rendering_definition_id": row["definition_root_id"],
                    "notification_rendering_definition_revision_id": row["definition_revision_id"],
                }
                definition = load_revision(db, row["definition_revision_id"])
                invariant(definition["notification_rendering_definition_id"] == row["definition_root_id"])
                root = db.execute(
                    "SELECT * FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?",
                    (row["definition_root_id"],),
                ).fetchone()
                invariant(root_owner(root) == root_owner(profile))
                invariant(set(revision["compatible_item_types"]) <= set(definition["revision"]["compatible_item_types"]))
            normalized["rendering"] = rendering
            template["rendering"] = rendering
        else:
            invariant(row is None, "v1 profile has rendering sidecars")
        templates.append(normalized)
    normalized_revision = {"compatible_item_types": revision["compatible_item_types"], "templates": templates}
    expected = (codec.normalize_profile_v2 if marker else normalize_profile_revision)(normalized_revision)
    invariant(expected.normalized_revision_hash == revision["normalized_revision_hash"], "profile hash decoder mismatch")
    invariant([t["normalized_template_hash"] for t in expected.templates] == [t["normalized_template_hash"] for t in revision["templates"]])
    revision["revision_contract"] = codec.PROFILE_V2 if marker else "spine.notification-profiles.v1"


def project(profile):
    revision = profile["revision"]
    content = {
        "compatible_item_types": revision["compatible_item_types"],
        "templates": [
            {k: t[k] for k in ("template_key", "schedule", "late_handling", "normalized_template_hash", "rendering") if k in t}
            for t in revision["templates"]
        ],
    }
    return {
        "notification_profile_id": profile["notification_profile_id"],
        "owner": root_owner(profile),
        **{k: profile[k] for k in ("profile_key", "display_name", "description", "status", "current_revision_id")},
        "revision": {
            k: revision[k] if k != "revision_number" else str(revision[k])
            for k in ("notification_profile_revision_id", "revision_number", "revision_contract", "normalized_revision_hash")
        }
        | {"content": content},
    }
