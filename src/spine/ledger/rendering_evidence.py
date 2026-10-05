"""Validate immutable v2 evidence against its exact historical ledger sources."""

from spine.core import facets as facet_codec
from spine.core.notification_details import require
from spine.core.notification_rendering import _normalized_text
from spine.ledger.facets import load_definition
from spine.ledger.rendering_definitions import load_disclosure, load_presentation, load_revision


def validate_evidence_definition(db, rendering):
    details = rendering.details
    revision = load_revision(db, details["definition"]["notification_rendering_definition_revision_id"])
    require(revision["definition_hash"] == details["definition_hash"])
    require(revision["notification_rendering_definition_id"] == details["definition"]["notification_rendering_definition_id"])
    grant = load_disclosure(db, details["disclosure_authorization_id"])
    require(grant["scope_hash"] == details["disclosure_scope_hash"] and grant["scope"]["definition"] == details["definition"])
    require(set(details["effective_selection_keys"]) <= set(grant["scope"]["approved_selection_keys"]))
    if details["authorization_state"] == "active":
        require(details["destination"] == grant["scope"]["destination"])
    policy = db.execute("SELECT item_id,version FROM notification_policies WHERE policy_id=?", (details["policy_id"],)).fetchone()
    require(policy is not None and tuple(policy) == (rendering.item_id, rendering.rendered_item_version))
    presentation = load_presentation(db, details["policy_id"], pending=False)
    require(
        presentation["kind"] == "definition"
        and all(
            presentation[k] == details[k]
            for k in (
                "definition",
                "disclosure_authorization_id",
                "disclosure_scope_hash",
                "effective_selection_keys",
            )
        )
    )
    selected = revision["revision"]["selections"]
    require([s["selection_key"] for s in selected] == [s["selection_key"] for s in details["selections"]])
    suffix = ""
    for definition, evidence in zip(selected, details["selections"], strict=True):
        if evidence["outcome"] != "included":
            continue
        source = evidence["source"]
        require(all(source[k] == definition[k] for k in ("facet_key", "facet_schema_revision_id", "field_key")))
        require(("location_id" in source) == (definition["projection"] == "location_label"))
        entry = db.execute(
            "SELECT * FROM item_facet_entries WHERE item_id=? AND item_version=? AND facet_key=?",
            (rendering.item_id, rendering.rendered_item_version, source["facet_key"]),
        ).fetchone()
        require(
            entry is not None
            and entry["facet_binding_id"] == source["archetype_facet_binding_id"]
            and entry["facet_schema_revision_id"] == source["facet_schema_revision_id"]
        )
        schema = load_definition(db, source["facet_schema_revision_id"])
        values = facet_codec.decode_values(schema, entry["values_json"], contract=entry["value_contract_version"])
        field = next((f for f in schema["fields"] if f["key"] == source["field_key"]), None)
        require(field is not None and source["field_key"] in values)
        raw = values[source["field_key"]]
        if "location_id" in source:
            require(field["type"] == "reference" and field["target_kind"] == "location")
            require(source["location_id"] == raw and raw in grant["scope"]["permitted_location_ids"])
            location = db.execute("SELECT label FROM locations WHERE location_id=?", (raw,)).fetchone()
            require(location is not None)
            raw = location[0]
        else:
            require(field["type"] in {"text", "enum", "integer", "boolean", "date"})
            if field["type"] == "boolean":
                raw = "true" if raw else "false"
        require(evidence["value"] == _normalized_text(raw, "detail"))
        suffix += f" · {definition['label']}: {evidence['value']}"
    require(details["body_text"] == rendering.base.body_text + suffix)
