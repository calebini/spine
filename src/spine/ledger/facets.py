"""Transaction-owned facet persistence. Public commands/authorization are not exposed here."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from spine.core import facets as codec
from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError
from spine.ledger.notification_profiles import current_assignment, load_archetype, require_owner_exists
from spine.ledger.transactions import LedgerConnection

ENTRY_COLUMNS = (
    "facet_key",
    "facet_schema_revision_id",
    "facet_binding_id",
    "item_archetype_id",
    "item_archetype_revision_id",
    "archetype_selection_source",
    "archetype_source_ref",
    "value_contract_version",
    "values_json",
    "source_command_receipt_id",
)


def invariant(condition: bool) -> None:
    if not condition:
        raise SpineValidationError("environment_failure:facets", "facet persistence invariant failed")


def _transaction(db: sqlite3.Connection) -> None:
    invariant(isinstance(db, LedgerConnection) and getattr(db, "_facets_enabled", False) and db.in_transaction)


def _fields(definition: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    return [(f["key"], f["type"], int(f["required"]), int(f["queryable"]), f.get("target_kind", "none")) for f in definition["fields"]]


def load_definition(db: sqlite3.Connection, revision_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM facet_schema_revisions WHERE facet_schema_revision_id=?", (revision_id,)).fetchone()
    invariant(row is not None)
    definition = codec.decode_definition(
        row["definition_json"], row["definition_hash"], contract=row["definition_contract_version"], canonical=row["canonical_json_version"]
    )
    fields = db.execute(
        "SELECT field_key,value_type,required,queryable,target_kind FROM facet_schema_fields "
        "WHERE facet_schema_revision_id=? ORDER BY field_key LIMIT 33",
        (revision_id,),
    ).fetchall()
    invariant([tuple(f) for f in fields] == _fields(definition))
    return definition


def insert_revision(
    db: sqlite3.Connection, *, schema_id: str, revision_id: str, definition: object, receipt_id: str, expected_revision_id: str | None
) -> None:
    _transaction(db)
    normalized = codec.normalize_definition(definition)
    root = db.execute("SELECT * FROM facet_schemas WHERE facet_schema_id=?", (schema_id,)).fetchone()
    invariant(root is not None and root["status"] == "active")
    if expected_revision_id is not None and root["current_revision_id"] != expected_revision_id:
        raise SpineValidationError("stale_version", "facet schema revision changed")
    number = db.execute(
        "SELECT COALESCE(MAX(revision_number),0)+1 FROM facet_schema_revisions WHERE facet_schema_id=?", (schema_id,)
    ).fetchone()[0]
    invariant(isinstance(number, int) and number < 2**63)
    invariant(expected_revision_id is not None or number == 1)
    db.execute(
        "INSERT INTO facet_schema_revisions VALUES (?,?,?,?,?,?,?,?)",
        (
            revision_id,
            schema_id,
            number,
            codec.DEFINITION_VERSION,
            codec.CANONICAL_VERSION,
            canonical_json_text(normalized),
            codec.definition_hash(normalized),
            receipt_id,
        ),
    )
    db.executemany("INSERT INTO facet_schema_fields VALUES (?,?,?,?,?,?)", [(revision_id, *field) for field in _fields(normalized)])
    db.execute("UPDATE facet_schemas SET current_revision_id=? WHERE facet_schema_id=?", (revision_id, schema_id))


def insert_schema(
    db: sqlite3.Connection,
    *,
    schema_id: str,
    revision_id: str,
    owner: Mapping[str, Any],
    schema_key: str,
    definition: object,
    receipt_id: str,
) -> None:
    _transaction(db)
    require_owner_exists(db, owner)
    codec.key(schema_key)
    db.execute(
        "INSERT INTO facet_schemas VALUES (?,?,?,?,?,'active',?,?,NULL)",
        (schema_id, owner["owner_kind"], owner.get("owner_subject_id"), owner.get("owner_group_id"), schema_key, revision_id, receipt_id),
    )
    insert_revision(
        db, schema_id=schema_id, revision_id=revision_id, definition=definition, receipt_id=receipt_id, expected_revision_id=None
    )


def _check_binding(db: sqlite3.Connection, archetype_id: str, revision_id: str, *, fresh: bool) -> None:
    archetype = load_archetype(db, archetype_id, active_required=fresh)
    root = db.execute(
        "SELECT s.* FROM facet_schemas s JOIN facet_schema_revisions r "
        "ON s.facet_schema_id=r.facet_schema_id WHERE r.facet_schema_revision_id=?",
        (revision_id,),
    ).fetchone()
    invariant(root is not None)
    if fresh and root["status"] != "active":
        raise SpineValidationError("facet_schema_retired", "facet schema is retired")
    invariant(all(root[k] == archetype.get(k) for k in ("owner_kind", "owner_subject_id", "owner_group_id")))
    definition = load_definition(db, revision_id)
    if fresh and not set(definition["compatible_item_types"]) & set(archetype["revision"]["compatible_item_types"]):
        raise SpineValidationError("wrong_item_type", "incompatible facet binding")


def set_binding(
    db: sqlite3.Connection,
    *,
    binding_id: str,
    archetype_id: str,
    facet_key: str,
    revision_id: str,
    expected_binding_id: str | None,
    receipt_id: str,
) -> None:
    _transaction(db)
    codec.key(facet_key)
    _check_binding(db, archetype_id, revision_id, fresh=True)
    previous = db.execute(
        "SELECT facet_binding_id FROM archetype_facet_bindings WHERE item_archetype_id=? AND facet_key=? AND status='active'",
        (archetype_id, facet_key),
    ).fetchone()
    if (previous[0] if previous else None) != expected_binding_id:
        raise SpineValidationError("facet_binding_conflict", "facet binding changed")
    if previous:
        db.execute(
            "UPDATE archetype_facet_bindings SET status='superseded',ended_command_receipt_id=? WHERE facet_binding_id=?",
            (receipt_id, expected_binding_id),
        )
    db.execute(
        "INSERT INTO archetype_facet_bindings VALUES (?,?,?,?,'active',?,NULL)",
        (binding_id, archetype_id, facet_key, revision_id, receipt_id),
    )


def prepare_entry(
    db: sqlite3.Connection, *, item_id: str, item_version: int, binding_id: str, values: object, receipt_id: str
) -> dict[str, Any]:
    """Trusted-local domain checks; a permission-enforced caller must also authorize references."""
    _transaction(db)
    binding = db.execute("SELECT * FROM archetype_facet_bindings WHERE facet_binding_id=?", (binding_id,)).fetchone()
    if binding is None or binding["status"] != "active":
        raise SpineValidationError("facet_binding_conflict", "facet binding unavailable")
    _check_binding(db, binding["item_archetype_id"], binding["facet_schema_revision_id"], fresh=True)
    assignment = current_assignment(db, item_id=item_id, item_version=item_version)
    if not assignment or assignment["item_archetype_id"] != binding["item_archetype_id"]:
        raise SpineValidationError("facet_archetype_conflict", "item archetype does not match facet")
    definition = load_definition(db, binding["facet_schema_revision_id"])
    item = db.execute("SELECT item_type,current_version FROM coordination_items WHERE item_id=?", (item_id,)).fetchone()
    if item["current_version"] != item_version:
        raise SpineValidationError("stale_version", "item version changed")
    if (
        item["item_type"] not in definition["compatible_item_types"]
        or item["item_type"] not in assignment["archetype"]["revision"]["compatible_item_types"]
    ):
        raise SpineValidationError("wrong_item_type:item_id", "item type is incompatible with facet")
    normalized = codec.normalize_values(definition, values)
    for f in definition["fields"]:
        if f["type"] == "reference" and f["key"] in normalized:
            table, pk = ("subjects", "subject_id") if f["target_kind"] == "subject" else ("locations", "location_id")
            target = db.execute(f"SELECT * FROM {table} WHERE {pk}=?", (normalized[f["key"]],)).fetchone()
            if target is None or (table == "subjects" and target["status"] != "active"):
                raise SpineValidationError("facet_reference_unavailable", "facet reference unavailable")
    return {
        "facet_key": binding["facet_key"],
        "facet_schema_revision_id": binding["facet_schema_revision_id"],
        "facet_binding_id": binding_id,
        "item_archetype_id": binding["item_archetype_id"],
        "item_archetype_revision_id": assignment["item_archetype_revision_id"],
        "archetype_selection_source": assignment["selection_source"],
        "archetype_source_ref": assignment["source_ref"],
        "value_contract_version": codec.VALUE_VERSION,
        "values_json": canonical_json_text(normalized),
        "source_command_receipt_id": receipt_id,
    }


def retire_schema(db: sqlite3.Connection, *, schema_id: str, expected_revision_id: str, receipt_id: str) -> bool:
    """Retire future authoring, not historical decoding. Caller owns audit/receipt."""
    _transaction(db)
    row = db.execute("SELECT status,current_revision_id FROM facet_schemas WHERE facet_schema_id=?", (schema_id,)).fetchone()
    if row is None or row["current_revision_id"] != expected_revision_id:
        raise SpineValidationError("stale_version", "facet schema revision changed")
    if row["status"] == "retired":
        return False
    db.execute("UPDATE facet_schemas SET status='retired',retired_command_receipt_id=? WHERE facet_schema_id=?", (receipt_id, schema_id))
    return True


def remove_binding(db: sqlite3.Connection, *, binding_id: str, receipt_id: str) -> bool:
    _transaction(db)
    row = db.execute("SELECT status FROM archetype_facet_bindings WHERE facet_binding_id=?", (binding_id,)).fetchone()
    if row is None:
        raise SpineValidationError("facet_binding_conflict", "facet binding unavailable")
    if row[0] != "active":
        return False
    db.execute(
        "UPDATE archetype_facet_bindings SET status='retired',ended_command_receipt_id=? WHERE facet_binding_id=?", (receipt_id, binding_id)
    )
    return True


def _projections(
    db: sqlite3.Connection, entries: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    invariant(len(entries) <= 8)
    values: dict[str, Any] = {}
    references, typed = [], []
    for entry in entries:
        k, revision = entry["facet_key"], entry["facet_schema_revision_id"]
        invariant(k not in values)
        definition = load_definition(db, revision)
        v = codec.decode_values(definition, entry["values_json"], contract=entry["value_contract_version"])
        values[k] = v
        for f in definition["fields"]:
            if f["key"] not in v:
                continue
            value, kind = v[f["key"]], f["type"]
            if kind == "reference":
                references.append(
                    (
                        k,
                        f["key"],
                        revision,
                        "reference",
                        f["target_kind"],
                        value if f["target_kind"] == "subject" else None,
                        value if f["target_kind"] == "location" else None,
                    )
                )
            if f["queryable"]:
                number = int(value) if kind in {"boolean", "integer"} else None
                typed.append((k, f["key"], revision, kind, 1, value if number is None else None, number))
    return values, references, typed


def load_snapshot(db: sqlite3.Connection, item_id: str, version: int) -> list[dict[str, Any]]:
    marker = db.execute(
        "SELECT entry_count,values_bytes FROM item_facet_snapshots WHERE item_id=? AND item_version=?", (item_id, version)
    ).fetchone()
    invariant(marker is not None)
    entries = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM item_facet_entries WHERE item_id=? AND item_version=? ORDER BY facet_key LIMIT 9", (item_id, version)
        )
    ]
    values, references, _ = _projections(db, entries)
    invariant(tuple(marker) == (len(entries), codec.snapshot_size(values)))
    actual = db.execute(
        "SELECT facet_key,field_key,facet_schema_revision_id,value_type,target_kind,subject_id,location_id "
        "FROM item_facet_references WHERE item_id=? AND item_version=? ORDER BY facet_key,field_key LIMIT 257",
        (item_id, version),
    ).fetchall()
    invariant([tuple(r) for r in actual] == references)
    if entries:
        item = db.execute("SELECT item_type FROM coordination_items WHERE item_id=?", (item_id,)).fetchone()
        invariant(item is not None and item[0] in {"event", "task"})
        assignment = db.execute(
            "SELECT item_archetype_id FROM item_archetype_assignments WHERE item_id=? AND item_version=?", (item_id, version)
        ).fetchone()
        if assignment is None or any(e["item_archetype_id"] != assignment[0] for e in entries):
            raise SpineValidationError("facet_archetype_conflict", "facet snapshot and item archetype disagree")
        for entry in entries:
            archetype = load_archetype(db, entry["item_archetype_id"], revision_id=entry["item_archetype_revision_id"])
            invariant(item[0] in archetype["revision"]["compatible_item_types"])
            invariant(item[0] in load_definition(db, entry["facet_schema_revision_id"])["compatible_item_types"])
    return [{k: e[k] for k in ENTRY_COLUMNS} for e in entries]


def insert_snapshot(db: sqlite3.Connection, item_id: str, version: int, entries: Sequence[Mapping[str, Any]]) -> None:
    _transaction(db)
    entries = sorted(entries, key=lambda e: e["facet_key"])
    values, references, typed = _projections(db, entries)
    size = codec.snapshot_size(values)
    db.execute("INSERT INTO item_facet_snapshots VALUES (?,?,?,?)", (item_id, version, len(entries), size))
    db.executemany(
        "INSERT INTO item_facet_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(item_id, version, *(e[k] for k in ENTRY_COLUMNS)) for e in entries],
    )
    db.executemany("INSERT INTO item_facet_references VALUES (?,?,?,?,?,?,?,?,?)", [(item_id, version, *r) for r in references])
    db.execute("DELETE FROM item_facet_current_values WHERE item_id=?", (item_id,))
    db.executemany(
        "INSERT INTO item_facet_current_values "
        "(item_id,facet_key,field_key,item_version,facet_schema_revision_id,value_type,queryable,value_text,value_integer) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [(item_id, t[0], t[1], version, *t[2:]) for t in typed],
    )


def validate_current(db: sqlite3.Connection, item_id: str) -> None:
    item = db.execute("SELECT item_type,current_version FROM coordination_items WHERE item_id=?", (item_id,)).fetchone()
    invariant(item is not None)
    version = item["current_version"]
    entries = load_snapshot(db, item_id, version)
    if entries:
        invariant(item["item_type"] in {"event", "task"})
        assignment = db.execute(
            "SELECT item_archetype_id FROM item_archetype_assignments WHERE item_id=? AND item_version=?", (item_id, version)
        ).fetchone()
        if assignment is None or any(e["item_archetype_id"] != assignment[0] for e in entries):
            raise SpineValidationError("facet_archetype_conflict", "clear facets before changing the item archetype")
    _, _, typed = _projections(db, entries)
    actual = db.execute(
        "SELECT facet_key,field_key,facet_schema_revision_id,value_type,queryable,value_text,value_integer,item_version "
        "FROM item_facet_current_values WHERE item_id=? ORDER BY facet_key,field_key LIMIT 257",
        (item_id,),
    ).fetchall()
    invariant([tuple(r) for r in actual] == [(*t, version) for t in typed])


def rebuild_current_index(db: sqlite3.Connection, item_id: str) -> None:
    """Explicit maintenance primitive; never invoked by a reader to repair data."""
    _transaction(db)
    version = db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (item_id,)).fetchone()[0]
    entries = load_snapshot(db, item_id, version)
    _, _, typed = _projections(db, entries)
    db.execute("DELETE FROM item_facet_current_values WHERE item_id=?", (item_id,))
    db.executemany(
        "INSERT INTO item_facet_current_values "
        "(item_id,facet_key,field_key,item_version,facet_schema_revision_id,value_type,queryable,value_text,value_integer) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [(item_id, t[0], t[1], version, *t[2:]) for t in typed],
    )


def finalize(
    db: sqlite3.Connection,
    versions: Iterable[tuple[str, int]],
    items: Iterable[str],
    roots: Iterable[str],
    bindings: Iterable[str],
    definitions: Iterable[str] = (),
) -> tuple[frozenset[Any], ...]:
    """Bounded touched-state validation; full-ledger verification is explicitly separate."""
    versions, items, roots, bindings = frozenset(versions), frozenset(items), frozenset(roots), frozenset(bindings)
    definitions = frozenset(definitions)
    for revision_id in sorted(definitions):
        load_definition(db, revision_id)
    for item_id, version in sorted(versions):
        load_snapshot(db, item_id, version)
    for item_id in sorted(items):
        validate_current(db, item_id)
    for schema_id in sorted(roots):
        row = db.execute("SELECT current_revision_id FROM facet_schemas WHERE facet_schema_id=?", (schema_id,)).fetchone()
        latest = db.execute(
            "SELECT facet_schema_revision_id FROM facet_schema_revisions WHERE facet_schema_id=? ORDER BY revision_number DESC LIMIT 1",
            (schema_id,),
        ).fetchone()
        invariant(row is not None and latest is not None and row[0] == latest[0])
        load_definition(db, row[0])
    for binding_id in sorted(bindings):
        row = db.execute("SELECT * FROM archetype_facet_bindings WHERE facet_binding_id=?", (binding_id,)).fetchone()
        invariant(row is not None)
        _check_binding(db, row["item_archetype_id"], row["facet_schema_revision_id"], fresh=False)
    return versions, items, roots, bindings, definitions


def verify_all(db: sqlite3.Connection) -> None:
    """Explicit maintenance only. Never call this during normal admission."""
    for row in db.execute("SELECT facet_schema_revision_id FROM facet_schema_revisions"):
        load_definition(db, row[0])
    for row in db.execute("SELECT item_id,version FROM coordination_item_versions ORDER BY item_id,version"):
        load_snapshot(db, row[0], row[1])
    finalize(
        db,
        (),
        (r[0] for r in db.execute("SELECT item_id FROM coordination_items")),
        (r[0] for r in db.execute("SELECT facet_schema_id FROM facet_schemas")),
        (r[0] for r in db.execute("SELECT facet_binding_id FROM archetype_facet_bindings")),
    )


def probe(db: sqlite3.Connection, *, item_id: str, version: int, revision_id: str, field_key: str, value: object) -> bool:
    """One already-admitted candidate, not a public query or permission bypass."""
    definition = load_definition(db, revision_id)
    field = next((f for f in definition["fields"] if f["key"] == field_key and f["queryable"]), None)
    if field is None:
        codec.fail()
    normalized = codec.normalize_scalar(field, value)
    column = "value_integer" if field["type"] in {"boolean", "integer"} else "value_text"
    bound = int(normalized) if column == "value_integer" else normalized
    return (
        db.execute(
            f"SELECT 1 FROM item_facet_current_values WHERE item_id=? AND item_version=? "
            f"AND facet_schema_revision_id=? AND field_key=? AND value_type=? AND {column} IS NOT NULL "
            f"AND {column}=? LIMIT 1",
            (item_id, version, revision_id, field_key, field["type"], bound),
        ).fetchone()
        is not None
    )
