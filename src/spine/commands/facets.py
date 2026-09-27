"""Trusted-local facet command family. Web admission is deliberately not enabled."""

from __future__ import annotations

import copy
import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.facet_runtime import FacetBudget, failure, install_budget, parse_time
from spine.commands.receipts import command_derived_id, command_receipt, get_command_receipt, insert_command_receipt
from spine.core import facets as codec
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notification_profiles import normalize_owner
from spine.ledger import facet_continuity, facets
from spine.ledger.item_drafts import ItemVersionDraft
from spine.ledger.items import create_item_version_from_draft
from spine.ledger.notification_profiles import load_archetype, require_owner_exists
from spine.ledger.transactions import LedgerConnection

CONTRACTS = {
    **dict.fromkeys((f"facet_schema.{s}" for s in ("create", "publish", "retire", "show", "list")), "spine.facet-schemas.v1"),
    **dict.fromkeys((f"item_archetype.facet_binding.{s}" for s in ("set", "remove", "list")), "spine.archetype-facet-bindings.v1"),
    "item.facets.update": "spine.item-facets.v1",
    "item.facets.show": "spine.item-facets.v1",
    "item.facets.query": "spine.item-facet-query.v1",
}
WRITES = frozenset(c for c in CONTRACTS if c.rsplit(".", 1)[1] in {"create", "publish", "retire", "set", "remove", "update"})
PAGES = frozenset({"facet_schema.list", "item_archetype.facet_binding.list", "item.facets.query"})
FIELDS = {
    "facet_schema.create": ({"owner", "schema_key", "definition"}, set()),
    "facet_schema.publish": ({"facet_schema_id", "expected_current_revision_id", "definition"}, set()),
    "facet_schema.retire": ({"facet_schema_id", "expected_current_revision_id"}, set()),
    "facet_schema.show": ({"facet_schema_id"}, {"facet_schema_revision_id"}),
    "facet_schema.list": ({"owner"}, {"status", "limit", "cursor"}),
    "item_archetype.facet_binding.set": ({"item_archetype_id", "facet_key", "facet_schema_revision_id", "expected_binding_id"}, set()),
    "item_archetype.facet_binding.remove": ({"item_archetype_id", "facet_key", "expected_binding_id"}, set()),
    "item_archetype.facet_binding.list": ({"item_archetype_id"}, {"limit", "cursor"}),
    "item.facets.update": ({"item_id", "expected_item_version", "changes"}, set()),
    "item.facets.show": ({"item_id"}, {"item_version"}),
    "item.facets.query": ({"owner", "facet_schema_revision_id", "field", "value"}, {"limit", "cursor"}),
}


def exact(value: object, required: set[str], optional: set[str] | None = None, path: str = "request") -> dict[str, Any]:
    if not isinstance(value, dict):
        failure("invalid_request", path)
    assert isinstance(value, dict)
    prefix = "" if path == "request" else path + "."
    if set(value) - required - (optional or set()):
        failure("unsupported_field", prefix + sorted(set(value) - required - (optional or set()))[0])
    if required - set(value):
        failure("missing_required_field", prefix + sorted(required - set(value))[0])
    return value


def normalize(command: str, request: Mapping[str, Any]) -> dict[str, Any]:
    r = copy.deepcopy(dict(request))
    required, optional = FIELDS[command]
    common = {"contract_version"} | ({"command_id", "actor_subject_id", "action_timestamp_utc"} if command in WRITES else set())
    exact(r, required | common, optional)
    if r["contract_version"] != CONTRACTS[command]:
        failure("invalid_request", "contract_version")
    for k, v in r.items():
        if k.endswith("_id") or k in {"cursor", "schema_key", "facet_key", "field"}:
            if v is None and k == "expected_binding_id":
                continue
            if not isinstance(v, str) or not v:
                failure("invalid_request", k)
            codec.nfc(v)  # Reject surrogates, but never rewrite opaque identities.
        if k in {"schema_key", "facet_key", "field"}:
            codec.key(v)
        if k in {"expected_item_version", "item_version", "limit"} and (codec.integer(v) < 1 or k == "limit" and int(v) > 100):
            failure("invalid_request", k)
    if command in WRITES:
        try:
            parse_time(r["action_timestamp_utc"])
        except ValueError:
            failure("invalid_timestamp", "action_timestamp_utc")
    if "owner" in r:
        owner = normalize_owner(r["owner"])
        if command == "item.facets.query" and owner["owner_kind"] == "system":
            failure("invalid_request", "owner")
        r["owner"] = {k: v for k, v in owner.items() if v is not None}
    if "definition" in r and not isinstance(r["definition"], dict):
        failure("facet_schema_invalid", "definition")
    if "changes" in r:
        if not isinstance(r["changes"], list) or not 1 <= len(r["changes"]) <= 8:
            failure("invalid_request", "changes")
        keys = set()
        for change in r["changes"]:
            if not isinstance(change, dict) or change.get("op") not in ("set", "remove"):
                failure("invalid_request", "changes")
            extra = {"expected_binding_id", "facet_schema_revision_id", "values"} if change["op"] == "set" else set()
            exact(change, {"op", "facet_key"} | extra, path="changes")
            k = codec.key(change["facet_key"])
            if k in keys:
                failure("facet_value_invalid", "changes")
            keys.add(k)
            if extra:
                for name in ("expected_binding_id", "facet_schema_revision_id"):
                    if not isinstance(change[name], str) or not change[name]:
                        failure("invalid_request", f"changes.{k}.{name}")
                if not isinstance(change["values"], dict) or len(change["values"]) > 32:
                    failure("facet_value_invalid", f"changes.{k}.values")
                values = change["values"]
                for field, value in values.items():
                    codec.key(field)
                    if type(value) not in {str, bool}:
                        failure("facet_value_invalid", f"changes.{k}.values.{field}")
                    if isinstance(value, str):
                        values[field] = codec.nfc(value)
                if len(canonical_json_bytes(values)) > 16384:
                    failure("facet_value_invalid", f"changes.{k}.values")
        r["changes"].sort(key=lambda v: v["facet_key"])
    if command in PAGES:
        r.setdefault("limit", "25")
    if command == "facet_schema.list":
        r.setdefault("status", "active")
        if r["status"] not in ("active", "retired"):
            failure("invalid_request", "status")
    return r


def derived(command: str, request: dict[str, Any], role: str, path: str) -> str:
    return command_derived_id(prefix=role, command=command, command_id=request["command_id"], row_role=role, request_path=path)


class _Preview(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result


def execute(command: str, request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    db = context.ledger
    if not isinstance(db, LedgerConnection) or db.in_transaction or db._command_transaction:
        failure("environment_failure", "ledger", "facet commands require an idle transaction-aware ledger")
    assert isinstance(db, LedgerConnection)
    if context.transport_metadata.get("adapter") not in {None, "cli"}:
        failure("environment_failure", "admission", "use trusted-local admission or the dedicated facet web adapter")
    budget = FacetBudget()
    old_timeout = install_budget(db, budget)
    try:
        if len(canonical_json_bytes(dict(request))) > 1024 * 1024:
            failure("environment_failure", "capacity")
        r = normalize(command, request)
        if command in WRITES:
            try:
                with db.atomic_command():
                    response = write(command, r, db, budget)
                    budget.check()
                    if len(canonical_json_bytes(response)) > 4 * 1024 * 1024:
                        failure("environment_failure", "capacity")
                    if context.dry_run:
                        # Run the same touched-set proof, then roll back the entire
                        # bounded transaction. No ledger backup or external calls.
                        from spine.ledger.facets import finalize

                        expected = (
                            frozenset(db._facet_versions),
                            frozenset(db._facet_items),
                            frozenset(db._facet_roots),
                            frozenset(db._facet_bindings),
                            frozenset(db._facet_definitions),
                        )
                        if finalize(db, *expected) != expected or not db._facet_allocations <= db._facet_versions:
                            failure("environment_failure", "facets")
                        if command == "item.facets.update":
                            response["reconciliation_performed"] = False
                        raise _Preview(response)
            except _Preview as preview:
                response = preview.result
        else:
            from spine.commands.facet_reads import read

            response = read(command, r, db, budget, context)
        if command not in WRITES:
            budget.check()
            if len(canonical_json_bytes(response)) > 4 * 1024 * 1024:
                failure("environment_failure", "capacity")
        if context.dry_run:
            response["dry_run"] = True
        return response
    except sqlite3.OperationalError as exc:
        raise SpineValidationError("environment_failure:capacity", "facet operation could not complete within its budget") from exc
    finally:
        db.set_progress_handler(None, 0)
        db.execute(f"PRAGMA busy_timeout={old_timeout}")


def required_row(db: sqlite3.Connection, table: str, key: str, value: str, budget: FacetBudget) -> dict[str, Any]:
    budget.resolve(table, value)
    row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
    if row is None:
        failure("referenced_row_not_found", key)
    return dict(row)


def revision(db: sqlite3.Connection, revision_id: str, budget: FacetBudget) -> dict[str, Any]:
    row = required_row(db, "facet_schema_revisions", "facet_schema_revision_id", revision_id, budget)
    return {
        "facet_schema_id": row["facet_schema_id"],
        "facet_schema_revision_id": revision_id,
        "revision_number": str(row["revision_number"]),
        "definition": facets.load_definition(db, revision_id),
        "definition_hash": row["definition_hash"],
    }


def write(command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget) -> dict[str, Any]:
    stored = get_command_receipt(db, r["command_id"])
    if stored:
        if "definition" in r:
            r["definition"] = codec.normalize_definition(r["definition"])
        if stored["command"] != command or stored["semantic_facts_hash"] != hash_canonical_json(r):
            failure("semantic_conflict", "command_id")
        result = dict(stored["result_identity_facts"])
        result.update(changed=False, replayed=True)
        if command == "item.facets.update":
            result.update(changed_facet_keys=[], reconciliation_performed=False)
        return result
    required_row(db, "subjects", "subject_id", r["actor_subject_id"], budget)
    rid = derived(command, r, "command_receipt", "/")
    aid = derived(command, r, "audit", "/audit")
    base = {
        "ok": True,
        "command": command,
        "response_contract": CONTRACTS[command],
        "command_id": r["command_id"],
        "command_receipt_id": rid,
        "replayed": False,
    }
    resource: str | None
    if command.startswith("facet_schema."):
        facts, changed, effect, resource = schema_write(command, r, db, budget, rid)
        kind = "facet_schema"
    elif command.startswith("item_archetype."):
        facts, changed, effect, resource = binding_write(command, r, db, budget, rid)
        kind = "archetype_facet_binding"
    else:
        facts, changed = item_write(r, db, budget, rid, aid)
        effect = "item_facets_updated" if changed else "item_facets_update_noop"
        resource, kind = r["item_id"], "item"
    result = {**base, **facts, "changed": changed, "effect": effect}
    if changed:
        result["audit_id"] = aid
        if kind != "item":
            db.execute(
                "INSERT INTO coordination_catalog_audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    aid,
                    kind,
                    resource,
                    effect,
                    effect,
                    r["actor_subject_id"],
                    r["command_id"],
                    canonical_json_text(facts),
                    hash_canonical_json(facts),
                    r["action_timestamp_utc"],
                ),
            )
    receipt = command_receipt(
        command=command,
        command_id=r["command_id"],
        actor_subject_id=r["actor_subject_id"],
        action_timestamp_utc=r["action_timestamp_utc"],
        effect=effect,
        semantic_facts=r,
        result_identity_facts=result,
        item_id=r.get("item_id"),
        target_version=r.get("expected_item_version"),
    )
    insert_command_receipt(db, receipt)
    return result


def schema_write(
    command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget, rid: str
) -> tuple[dict[str, Any], bool, str, str]:
    if command == "facet_schema.create":
        owner = normalize_owner(r["owner"])
        budget.resolve("owner", canonical_json_text(owner))
        require_owner_exists(db, owner)
        r["definition"] = codec.normalize_definition(r["definition"])
        schema_id = derived(command, r, "facet_schema", "/facet_schema")
        revision_id = derived(command, r, "facet_schema_revision", "/facet_schema/revision")
        facets.insert_schema(
            db,
            schema_id=schema_id,
            revision_id=revision_id,
            owner=owner,
            schema_key=r["schema_key"],
            definition=r["definition"],
            receipt_id=rid,
        )
        prior, number, changed, effect = None, 1, True, "facet_schema_created"
    else:
        schema_id = r["facet_schema_id"]
        root = required_row(db, "facet_schemas", "facet_schema_id", schema_id, budget)
        prior = root["current_revision_id"]
        if prior != r["expected_current_revision_id"]:
            failure("stale_version", "expected_current_revision_id")
        current = revision(db, prior, budget)
        revision_id, number = prior, int(current["revision_number"])
        if command == "facet_schema.publish":
            if root["status"] != "active":
                failure("facet_schema_retired", "facet_schema_id")
            r["definition"] = codec.normalize_definition(r["definition"])
            changed = current["definition"] != r["definition"]
            if changed:
                revision_id = derived(command, r, "facet_schema_revision", "/facet_schema/revision")
                facets.insert_revision(
                    db, schema_id=schema_id, revision_id=revision_id, definition=r["definition"], receipt_id=rid, expected_revision_id=prior
                )
                number += 1
            effect = "facet_schema_published" if changed else "facet_schema_publish_noop"
        else:
            changed = facets.retire_schema(db, schema_id=schema_id, expected_revision_id=prior, receipt_id=rid)
            effect = "facet_schema_retired" if changed else "facet_schema_retire_noop"
    return (
        {"facet_schema_id": schema_id, "prior_revision_id": prior, "facet_schema_revision_id": revision_id, "revision_number": str(number)},
        changed,
        effect,
        schema_id,
    )


def binding_write(
    command: str, r: dict[str, Any], db: LedgerConnection, budget: FacetBudget, rid: str
) -> tuple[dict[str, Any], bool, str, str | None]:
    archetype = required_row(db, "item_archetypes", "item_archetype_id", r["item_archetype_id"], budget)
    current = db.execute(
        "SELECT * FROM archetype_facet_bindings WHERE item_archetype_id=? AND facet_key=? AND status='active'",
        (r["item_archetype_id"], r["facet_key"]),
    ).fetchone()
    prior = current["facet_binding_id"] if current else None
    if prior != r["expected_binding_id"]:
        failure("facet_binding_conflict", "expected_binding_id")
    result_id = prior
    facts = {"item_archetype_id": r["item_archetype_id"], "facet_key": r["facet_key"], "prior_binding_id": prior}
    if command.endswith(".set"):
        selected = revision(db, r["facet_schema_revision_id"], budget)
        root = required_row(db, "facet_schemas", "facet_schema_id", selected["facet_schema_id"], budget)
        if any(root[k] != archetype[k] for k in ("owner_kind", "owner_subject_id", "owner_group_id")):
            failure("facet_binding_conflict", "facet_schema_revision_id")
        if root["status"] != "active":
            failure("facet_schema_retired", "facet_schema_revision_id")
        a = load_archetype(db, r["item_archetype_id"], active_required=True)
        if not set(a["revision"]["compatible_item_types"]) & set(selected["definition"]["compatible_item_types"]):
            failure("wrong_item_type", "facet_schema_revision_id")
        changed = current is None or current["facet_schema_revision_id"] != r["facet_schema_revision_id"]
        if changed:
            result_id = derived(command, r, "archetype_facet_binding", "/facet_binding")
            facets.set_binding(
                db,
                binding_id=result_id,
                archetype_id=r["item_archetype_id"],
                facet_key=r["facet_key"],
                revision_id=r["facet_schema_revision_id"],
                expected_binding_id=prior,
                receipt_id=rid,
            )
        facts["facet_schema_revision_id"] = r["facet_schema_revision_id"]
        effect = "facet_binding_set" if changed else "facet_binding_set_noop"
    else:
        changed = prior is not None
        if prior is not None:
            facets.remove_binding(db, binding_id=prior, receipt_id=rid)
        effect = "facet_binding_removed" if changed else "facet_binding_remove_noop"
    facts["facet_binding_id"] = result_id
    return facts, changed, effect, result_id


def item_write(r: dict[str, Any], db: LedgerConnection, budget: FacetBudget, rid: str, aid: str) -> tuple[dict[str, Any], bool]:
    item = required_row(db, "coordination_items", "item_id", r["item_id"], budget)
    if item["item_type"] not in {"event", "task"}:
        failure("wrong_item_type", "item_id")
    version = item["current_version"]
    if version != int(r["expected_item_version"]):
        failure("stale_version", "expected_item_version")
    entries = {e["facet_key"]: e for e in facets.load_snapshot(db, r["item_id"], version)}
    changed_keys = []
    for change in r["changes"]:
        key = change["facet_key"]
        old = entries.get(key)
        if change["op"] == "remove":
            if old:
                del entries[key]
                changed_keys.append(key)
            continue
        binding = required_row(db, "archetype_facet_bindings", "facet_binding_id", change["expected_binding_id"], budget)
        if binding["facet_key"] != key or binding["facet_schema_revision_id"] != change["facet_schema_revision_id"]:
            failure("facet_binding_conflict", f"changes.{key}.expected_binding_id")
        d = revision(db, binding["facet_schema_revision_id"], budget)["definition"]
        budget.resolve("item_archetypes", binding["item_archetype_id"])
        for f in d["fields"]:
            if f["type"] == "reference" and f["key"] in change["values"]:
                budget.resolve(f["target_kind"], change["values"][f["key"]])
        new = facets.prepare_entry(
            db,
            item_id=r["item_id"],
            item_version=version,
            binding_id=change["expected_binding_id"],
            values=change["values"],
            receipt_id=rid,
        )
        if old is None or any(old[k] != new[k] for k in facets.ENTRY_COLUMNS if k != "source_command_receipt_id"):
            entries[key] = new
            changed_keys.append(key)
    codec.snapshot_size({k: codec.parse_object(e["values_json"], maximum=16384) for k, e in entries.items()})
    reconciliation = False
    if changed_keys:
        before = facet_continuity.capture(db, r["item_id"], version)
        create_item_version_from_draft(
            db,
            ItemVersionDraft(
                item_id=r["item_id"],
                target_version=version,
                created_at_utc=r["action_timestamp_utc"],
                created_by_subject_id=r["actor_subject_id"],
                audit_id=aid,
                audit_action="item_facets_updated",
                reason_code="item_facets_updated",
                audit_payload={"changed_facet_keys": changed_keys},
                facet_entries=tuple(entries[k] for k in sorted(entries)),
            ),
            supporting_command_id=r["command_id"],
        )
        facet_continuity.verify(before, facet_continuity.capture(db, r["item_id"], version + 1))
        reconciliation = (
            bool(before["policies"])
            or db.execute(
                "SELECT 1 FROM work_instances WHERE item_id=? AND work_kind='notification_reminder' LIMIT 1", (r["item_id"],)
            ).fetchone()
            is not None
        )
    return {
        "item_id": r["item_id"],
        "prior_item_version": str(version),
        "item_version": str(version + bool(changed_keys)),
        "changed_facet_keys": changed_keys,
        "reconciliation_performed": reconciliation,
    }, bool(changed_keys)
