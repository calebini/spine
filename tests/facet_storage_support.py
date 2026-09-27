"""Real SQLite fixtures for the internal facet foundation; no public facet commands."""

from spine.commands import CommandContext, handle
from spine.commands.receipts import command_receipt, insert_command_receipt
from spine.core import facets as codec
from spine.ledger import facets

NOW = "2035-01-01T00:00:00Z"
DEFINITION = {
    "display_name": "Flight details",
    "description": None,
    "compatible_item_types": ["event", "task"],
    "fields": [
        {"key": "flight", "type": "text", "max_length": "64", "required": True, "queryable": True},
        {"key": "confirmed", "type": "boolean", "required": False, "queryable": True},
        {
            "key": "seats",
            "type": "integer",
            "min": "-9223372036854775808",
            "max": "9223372036854775807",
            "required": False,
            "queryable": True,
        },
        {"key": "day", "type": "date", "required": False, "queryable": True},
        {"key": "class", "type": "enum", "choices": ["economy", "business"], "required": False, "queryable": True},
        {"key": "person", "type": "reference", "target_kind": "subject", "required": False, "queryable": False},
        {"key": "airport", "type": "reference", "target_kind": "location", "required": False, "queryable": True},
    ],
}


def receipt(db, key, actor="owner"):
    value = command_receipt(
        command="fixture.facet.storage",
        command_id=key,
        actor_subject_id=actor,
        action_timestamp_utc=NOW,
        effect="fixture",
        semantic_facts={},
        result_identity_facts={},
    )
    insert_command_receipt(db, value)
    return value["command_receipt_id"]


def catalog(db, actor="owner"):
    row = db.execute("SELECT item_archetype_id FROM item_archetypes WHERE archetype_key='fixture_facets'").fetchone()
    if row:
        return row[0]
    response = handle(
        "item_archetype.create",
        {
            "contract_version": "spine.item-archetypes.v1",
            "command_id": "fixture-archetype",
            "actor_subject_id": actor,
            "action_timestamp_utc": NOW,
            "owner": {"owner_kind": "subject", "owner_subject_id": actor},
            "archetype_key": "fixture_facets",
            "revision": {"display_name": "Fixture", "description": None, "compatible_item_types": ["event", "task"]},
        },
        CommandContext(ledger=db),
    )
    assert response["ok"], response
    archetype = response["item_archetype_id"]
    rid = receipt(db, "fixture-catalog", actor)
    facets.insert_schema(
        db,
        schema_id="schema",
        revision_id="revision",
        owner={"owner_kind": "subject", "owner_subject_id": actor},
        schema_key="flight",
        definition=DEFINITION,
        receipt_id=rid,
    )
    for i in range(8):
        facets.set_binding(
            db,
            binding_id=f"binding{i}",
            archetype_id=archetype,
            facet_key=f"details{i}",
            revision_id="revision",
            expected_binding_id=None,
            receipt_id=rid,
        )
    return archetype


def assign(db, item_id, version, archetype, actor="owner"):
    revision = db.execute("SELECT current_revision_id FROM item_archetypes WHERE item_archetype_id=?", (archetype,)).fetchone()[0]
    db.execute(
        "INSERT INTO item_archetype_assignments VALUES (?,?,?,?,?,'operator_explicit',NULL,?,?,?)",
        (f"fixture-assignment-{item_id}-{version}", item_id, version, archetype, revision, actor, "fixture-catalog", NOW),
    )


def seeded_snapshot(db, item_id, version, entries):
    """Seed initial snapshots for existing producer tests without changing version counts."""
    if version == 1 and not entries:
        actor = db.execute(
            "SELECT created_by_subject_id FROM coordination_item_versions WHERE item_id=? AND version=1", (item_id,)
        ).fetchone()[0]
        archetype = catalog(db, actor)
        assign(db, item_id, version, archetype, actor)
        rid = receipt(db, f"fixture-values-{item_id}", actor)
        entries = [
            facets.prepare_entry(
                db,
                item_id=item_id,
                item_version=version,
                binding_id=f"binding{i}",
                values={"flight": "AC123", "confirmed": True, "seats": "2", "day": "2036-02-29", "class": "economy", "person": actor},
                receipt_id=rid,
            )
            for i in range(8)
        ]
    facets.insert_snapshot(db, item_id, version, entries)


def all_rows(db):
    """Content, not total_changes (which includes rolled-back work)."""
    return {
        r[0]: [tuple(row) for row in db.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
        for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }


NORMALIZED = codec.normalize_definition(DEFINITION)
