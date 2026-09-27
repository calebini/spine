"""Bounded facet readback and authenticated local pagination, with release checks."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.facet_runtime import (
    FacetBudget,
    FacetCursorConfig,
    decode_cursor,
    encode_cursor,
    failure,
    parse_time,
    utc_now,
    wire_time,
)
from spine.commands.facets import CONTRACTS, PAGES, required_row, revision
from spine.core import facets as codec
from spine.core.hashing import hash_canonical_json
from spine.ledger import facets
from spine.ledger.transactions import LedgerConnection


def owner(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("owner_kind", "owner_subject_id", "owner_group_id") if row.get(k) is not None}


def root_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "facet_schema_id": row["facet_schema_id"],
        "owner": owner(row),
        "schema_key": row["schema_key"],
        "current_revision_id": row["current_revision_id"],
        "status": row["status"],
    }


def root_fact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("facet_schema_id", "current_revision_id", "status")}


def binding_view(row: Any) -> dict[str, Any]:
    return {k: row[k] for k in ("facet_binding_id", "item_archetype_id", "facet_key", "facet_schema_revision_id", "status")}


def reference(db: LedgerConnection, kind: str, identity: str, budget: FacetBudget) -> dict[str, Any]:
    table, pk = ("subjects", "subject_id") if kind == "subject" else ("locations", "location_id")
    row = required_row(db, table, pk, identity, budget)
    return {"target_kind": kind, "target_id": identity, "status": row["status"] if kind == "subject" else "active"}


def show(command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget) -> dict[str, Any]:
    if command == "facet_schema.show":
        root = required_row(db, "facet_schemas", "facet_schema_id", r["facet_schema_id"], budget)
        selected = revision(db, r.get("facet_schema_revision_id", root["current_revision_id"]), budget)
        if selected["facet_schema_id"] != root["facet_schema_id"]:
            failure("referenced_row_not_found", "facet_schema_revision_id")
        return {"root": root_view(root), "revision": selected}
    item = required_row(db, "coordination_items", "item_id", r["item_id"], budget)
    version = int(r.get("item_version", item["current_version"]))
    if db.execute("SELECT 1 FROM coordination_item_versions WHERE item_id=? AND version=?", (r["item_id"], version)).fetchone() is None:
        failure("referenced_row_not_found", "item_version")
    entries = []
    for entry in facets.load_snapshot(db, r["item_id"], version):
        selected = revision(db, entry["facet_schema_revision_id"], budget)
        values = codec.parse_object(entry["values_json"], maximum=16384)
        refs = []
        for f in selected["definition"]["fields"]:
            if f["type"] == "reference" and f["key"] in values:
                refs.append({"field": f["key"], **reference(db, f["target_kind"], values[f["key"]], budget)})
        archetype = {
            "item_archetype_id": entry["item_archetype_id"],
            "item_archetype_revision_id": entry["item_archetype_revision_id"],
            "selection_source": entry["archetype_selection_source"],
        }
        if entry["archetype_source_ref"] is not None:
            archetype["source_ref"] = entry["archetype_source_ref"]
        entries.append(
            {
                "facet_key": entry["facet_key"],
                "facet_schema_revision_id": entry["facet_schema_revision_id"],
                "facet_binding_id": entry["facet_binding_id"],
                "archetype": archetype,
                "values": values,
                "source_command_receipt_id": entry["source_command_receipt_id"],
                "schema_revision": selected,
                "references": refs,
            }
        )
    return {"item_id": r["item_id"], "item_version": str(version), "entries": entries}


def source(command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bounded source proof. Revalidation does not reconstruct the result or retry."""
    if command == "facet_schema.list":
        o = r["owner"]
        rows = [
            dict(v)
            for v in db.execute(
                "SELECT * FROM facet_schemas WHERE owner_kind=? AND owner_subject_id IS ? AND owner_group_id IS ? "
                "ORDER BY facet_schema_id LIMIT 101",
                (o["owner_kind"], o.get("owner_subject_id"), o.get("owner_group_id")),
            )
        ]
        for row in rows:
            budget.resolve("facet_schemas", row["facet_schema_id"])
        return {"roots": [root_fact(v) for v in rows]}, [root_view(v) for v in rows]
    if command == "item_archetype.facet_binding.list":
        a = required_row(db, "item_archetypes", "item_archetype_id", r["item_archetype_id"], budget)
        rows = db.execute(
            "SELECT * FROM archetype_facet_bindings WHERE item_archetype_id=? AND status='active' ORDER BY facet_key LIMIT 101",
            (r["item_archetype_id"],),
        ).fetchall()
        proof = []
        for row in rows:
            budget.resolve("archetype_facet_bindings", row["facet_binding_id"])
            selected = required_row(db, "facet_schema_revisions", "facet_schema_revision_id", row["facet_schema_revision_id"], budget)
            root = required_row(db, "facet_schemas", "facet_schema_id", selected["facet_schema_id"], budget)
            proof.append({"binding": binding_view(row), "schema": root_fact(root)})
        return {"archetype": {k: a[k] for k in ("item_archetype_id", "current_revision_id", "status")}, "bindings": proof}, [
            binding_view(v) for v in rows
        ]
    selected = revision(db, r["facet_schema_revision_id"], budget)
    root = required_row(db, "facet_schemas", "facet_schema_id", selected["facet_schema_id"], budget)
    declaration = next((f for f in selected["definition"]["fields"] if f["key"] == r["field"]), None)
    if declaration is None or not declaration["queryable"]:
        failure("invalid_request", "field")
    r["value"] = codec.normalize_scalar(declaration, r["value"])
    ref = reference(db, declaration["target_kind"], r["value"], budget) if declaration["type"] == "reference" else None
    o = r["owner"]
    column = "owner_subject_id" if o["owner_kind"] == "subject" else "owner_group_id"
    rows = db.execute(
        f"SELECT a.*,i.current_version FROM item_access_owners a JOIN coordination_items i ON i.item_id=a.item_id "
        f"WHERE a.{column}=? AND a.owner_kind=? ORDER BY a.item_id LIMIT 101",
        (o[column], o["owner_kind"]),
    ).fetchall()
    candidates = []
    for row in rows:
        budget.resolve("coordination_items", row["item_id"])
        candidates.append(
            {
                "item_id": row["item_id"],
                "current_version": str(row["current_version"]),
                "owner": owner(dict(row)),
                "owner_revision": str(row["current_revision"]),
            }
        )
    return {
        "schema": {
            **root_fact(root),
            "facet_schema_revision_id": selected["facet_schema_revision_id"],
            "definition_hash": selected["definition_hash"],
        },
        "candidates": candidates,
        "reference": ref,
    }, candidates


def query_matches(db: LedgerConnection, r: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for row in rows:
        item_id, version = row["item_id"], int(row["current_version"])
        marker = db.execute(
            "SELECT entry_count FROM item_facet_snapshots WHERE item_id=? AND item_version=?", (item_id, version)
        ).fetchone()
        if (
            marker is None
            or db.execute(
                "SELECT 1 FROM item_facet_current_values WHERE item_id=? AND item_version<>? LIMIT 1", (item_id, version)
            ).fetchone()
        ):
            failure("environment_failure", "facets", "current facet index version mismatch")
        if facets.probe(
            db, item_id=item_id, version=version, revision_id=r["facet_schema_revision_id"], field_key=r["field"], value=r["value"]
        ):
            matches.append({"item_id": item_id, "item_version": str(version)})
    return matches


def read(command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget, context: CommandContext) -> dict[str, Any]:
    base = {"ok": True, "command": command, "response_contract": CONTRACTS[command]}
    if command not in PAGES:
        with db.atomic_command(write=False):
            return {**base, **show(command, r, db, budget)}
    config = context.facet_cursor_config
    if not isinstance(config, FacetCursorConfig):
        failure("environment_failure", "cursor_config", "protected facet cursor configuration required, including first pages")
    assert isinstance(config, FacetCursorConfig)
    config.validate()
    cursor = decode_cursor(config, r["cursor"]) if "cursor" in r else None
    now = utc_now()
    with db.atomic_command(write=False):
        facts, rows = source(command, r, db, budget)
        semantic = {k: v for k, v in r.items() if k != "cursor"}
        query_hash = hash_canonical_json({"contract_version": "spine.facet-query.v1", "command": command, "request": semantic})
        source_hash = config.digest("spine.facet-cursor-source.v1", {"command": command, "query_hash": query_hash, "facts": facts})
        context_hash, access_hash = config.bindings()
        if command == "facet_schema.list":
            rows = [v for v in rows if v["status"] == r["status"]]
            collection, key = "schemas", "facet_schema_id"
            scope = {"owner": r["owner"]}
        elif command == "item_archetype.facet_binding.list":
            collection, key = "bindings", "facet_key"
            scope = {"item_archetype_id": r["item_archetype_id"]}
        else:
            rows = query_matches(db, r, rows)
            collection, key = "items", "item_id"
            scope = {
                "owner": r["owner"],
                "facet_schema_revision_id": r["facet_schema_revision_id"],
                "field": r["field"],
                "value": r["value"],
            }
        payload = {
            "contract_version": "spine.facet-cursor.v1",
            "command": command,
            "context_hash": context_hash,
            "query_hash": query_hash,
            "access_hash": access_hash,
            "source_snapshot_hash": source_hash,
            "issued_at_utc": wire_time(now),
            "expires_at_utc": wire_time(now + timedelta(seconds=900)),
            "authorization_valid_until_utc": None,
            "last_key": "",
        }
        if cursor:
            if cursor["command"] != command or cursor["query_hash"] != query_hash or parse_time(cursor["issued_at_utc"]) > now:
                failure("invalid_request", "cursor")
            if (
                any(cursor[k] != payload[k] for k in ("context_hash", "access_hash", "source_snapshot_hash"))
                or now >= parse_time(cursor["expires_at_utc"])
                or cursor["authorization_valid_until_utc"] is not None
                or cursor["last_key"] not in {v[key] for v in rows}
            ):
                failure("stale_cursor", "cursor")
            payload = cursor.copy()
            rows = [v for v in rows if v[key] > cursor["last_key"]]
        page, more = rows[: int(r["limit"])], len(rows) > int(r["limit"])
        token = None
        if more:
            payload["last_key"] = page[-1][key]
            token = encode_cursor(config, payload)
        result = {**base, **scope, collection: page, "limit": r["limit"], "has_more": more, "next_cursor": token}
    # The old snapshot is released. Recheck the source in a new read transaction;
    # never reuse the old SQLite snapshot or restart page construction.
    with db.atomic_command(write=False):
        current_facts, _ = source(command, r, db, budget)
        budget.check()
        current_hash = config.digest("spine.facet-cursor-source.v1", {"command": command, "query_hash": query_hash, "facts": current_facts})
        if current_hash != source_hash:
            failure("stale_cursor" if cursor else "environment_failure", "cursor" if cursor else "source", "facet source changed")
        if utc_now() >= parse_time(payload["expires_at_utc"]):
            failure("stale_cursor" if cursor else "environment_failure", "cursor")
    return result
