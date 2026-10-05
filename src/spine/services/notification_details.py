"""Candidate attempt-time resolution; no catalog discovery or authorization issuance."""

from spine.core import facets as facet_codec
from spine.core import rendering_definitions as codec
from spine.core.errors import SpineValidationError
from spine.core.notification_details import build_details, require
from spine.core.notification_rendering import _normalized_text
from spine.ledger.facets import load_definition
from spine.ledger.notifications import NotificationPolicyResolver, load_current_notification_policies
from spine.ledger.rendering_definitions import load_disclosure, load_presentation, load_revision, root_owner
from spine.services.rendering_authoring import destination


def resolve_details(db, *, work_row, base):
    policy = NotificationPolicyResolver(db, load_current_notification_policies(db, item_id=base.item_id)).resolve(
        str(work_row["notification_policy_id"])
    )
    require(policy is not None and int(policy["item_version"]) == base.rendered_item_version)
    presentation = load_presentation(db, str(policy["notification_policy_id"]), pending=False)
    if presentation["kind"] == "ordinary":
        return base
    revision = load_revision(db, presentation["definition"]["notification_rendering_definition_revision_id"])
    require(base.source_input["item_type"] in revision["revision"]["compatible_item_types"])
    grant = load_disclosure(db, presentation["disclosure_authorization_id"])
    current_destination = destination(db, policy)
    owner = db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (base.item_id,)).fetchone()
    root = db.execute(
        "SELECT * FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?",
        (presentation["definition"]["notification_rendering_definition_id"],),
    ).fetchone()
    require(root is not None)
    authorization = "active"
    if grant["status"] == "revoked":
        authorization = "revoked"
    elif owner is None:
        authorization = "unavailable"
    elif (
        root_owner(owner) != grant["scope"]["item_owner"]
        or root_owner(root) != root_owner(owner)
        or current_destination != grant["scope"]["destination"]
        or codec.use_scope(presentation["origin"]) != grant["scope"]["use_scope"]
    ):
        authorization = "scope_mismatch"
    else:
        table, key, identity = (
            ("subjects", "subject_id", owner["owner_subject_id"])
            if owner["owner_kind"] == "subject"
            else ("subject_groups", "group_id", owner["owner_group_id"])
        )
        state = db.execute(f"SELECT status FROM {table} WHERE {key}=?", (identity,)).fetchone()
        require(state is not None)
        if state[0] != "active":
            authorization = "unavailable"
    candidates, sources, locations = [], {}, {}
    for selection in revision["revision"]["selections"]:
        key = selection["selection_key"]
        candidate = {"selection_key": key, "outcome": "not_selected"}
        if key in presentation["effective_selection_keys"]:
            if authorization != "active":
                candidate["outcome"] = "disclosure_unavailable"
            else:
                candidate.update(_source(db, base, selection, grant["scope"], sources, locations))
        candidates.append(candidate)
    return build_details(
        base,
        {
            "policy_id": policy["notification_policy_id"],
            "policy_version": str(policy["item_version"]),
            "definition": presentation["definition"],
            "definition_hash": revision["definition_hash"],
            "disclosure_authorization_id": presentation["disclosure_authorization_id"],
            "disclosure_scope_hash": presentation["disclosure_scope_hash"],
            "authorization_state": authorization,
            "effective_selection_keys": presentation["effective_selection_keys"],
            "destination": current_destination,
        },
        candidates,
    )


def _source(db, base, selection, scope, sources, locations):
    facet_key = selection["facet_key"]
    if facet_key not in sources:
        marker = db.execute(
            "SELECT entry_count FROM item_facet_snapshots WHERE item_id=? AND item_version=?",
            (base.item_id, base.rendered_item_version),
        ).fetchone()
        require(marker is not None)
        count = db.execute(
            "SELECT facet_key FROM item_facet_entries WHERE item_id=? AND item_version=? LIMIT 9",
            (base.item_id, base.rendered_item_version),
        ).fetchall()
        require(len(count) == marker[0] and len(count) <= 8)
        sources[facet_key] = db.execute(
            "SELECT * FROM item_facet_entries WHERE item_id=? AND item_version=? AND facet_key=?",
            (base.item_id, base.rendered_item_version, facet_key),
        ).fetchone()
    entry = sources[facet_key]
    if entry is None:
        return {"outcome": "facet_missing"}
    # Decode retained snapshots through their own immutable schema, never latest.
    definition = load_definition(db, entry["facet_schema_revision_id"])
    values = facet_codec.decode_values(definition, entry["values_json"], contract=entry["value_contract_version"])
    binding = db.execute("SELECT * FROM archetype_facet_bindings WHERE facet_binding_id=?", (entry["facet_binding_id"],)).fetchone()
    require(
        binding is not None
        and (binding["facet_key"], binding["facet_schema_revision_id"], binding["item_archetype_id"])
        == (facet_key, entry["facet_schema_revision_id"], entry["item_archetype_id"])
    )
    if entry["facet_schema_revision_id"] != selection["facet_schema_revision_id"]:
        return {"outcome": "schema_mismatch"}
    field = next((f for f in definition["fields"] if f["key"] == selection["field_key"]), None)
    require(field is not None)
    if field["key"] not in values:
        return {"outcome": "field_missing"}
    raw = values[field["key"]]
    source = {
        "facet_key": facet_key,
        "facet_schema_revision_id": entry["facet_schema_revision_id"],
        "archetype_facet_binding_id": entry["facet_binding_id"],
        "field_key": field["key"],
    }
    if selection["projection"] == "location_label":
        require(field["type"] == "reference" and field["target_kind"] == "location")
        if raw not in scope["permitted_location_ids"]:
            return {"outcome": "reference_unavailable"}
        if raw not in locations:
            require(len(locations) < 8)
            locations[raw] = db.execute("SELECT label FROM locations WHERE location_id=?", (raw,)).fetchone()
        location = locations[raw]
        # A missing FK target is corruption, not optional absence.
        require(location is not None)
        raw, source["location_id"] = location[0], raw
    else:
        require(field["type"] in {"text", "enum", "integer", "boolean", "date"} and selection["projection"] == "value")
        if field["type"] == "boolean":
            raw = "true" if raw else "false"
    try:
        value = _normalized_text(raw, "detail")
    except SpineValidationError:
        return {"outcome": "invalid_text"}
    if len(value) > 120:
        return {"outcome": "value_too_long"}
    return {"outcome": "included", "value": value, "source": source, "label": selection["label"]}
