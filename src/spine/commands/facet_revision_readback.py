"""Exact, trusted-local historical facet lookup. No catalog enumeration or writes."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.facet_runtime import FacetBudget, failure, install_budget
from spine.core import facets as codec
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.notification_profiles import normalize_owner
from spine.ledger import facets
from spine.ledger.transactions import LedgerConnection

COMMAND = "facet_schema.revision.show"
CONTRACT = "spine.facet-schema-revision-readback.v1"
REQUEST_BYTES = 1024 * 1024
RESPONSE_BYTES = 4 * 1024 * 1024


def normalize(request: Mapping[str, Any]) -> dict[str, Any]:
    from spine.commands.facets import exact

    r = exact(dict(request), {"contract_version", "facet_schema_revision_id"})
    if r["contract_version"] != CONTRACT:
        failure("unsupported_contract_version", "contract_version")
    identity = r["facet_schema_revision_id"]
    if not isinstance(identity, str) or not identity or any(0xD800 <= ord(c) <= 0xDFFF for c in identity):
        failure("invalid_request", "facet_schema_revision_id")
    return r


def lookup(db: LedgerConnection, identity: str, budget: FacetBudget) -> dict[str, Any]:
    from spine.commands.facet_reads import root_view
    from spine.commands.facets import required_row

    selected = required_row(db, "facet_schema_revisions", "facet_schema_revision_id", identity, budget)
    root_id = selected["facet_schema_id"]
    budget.resolve("facet_schemas", root_id)
    root = db.execute("SELECT * FROM facet_schemas WHERE facet_schema_id=?", (root_id,)).fetchone()
    facets.invariant(root is not None)
    root = dict(root)
    # Validate persisted projection facts without dereferencing owners/references or
    # treating a corrupt stored link as evidence that the requested revision is absent.
    facets.invariant(root["facet_schema_id"] == root_id and root["status"] in {"active", "retired"})
    for value in (root_id, root["current_revision_id"]):
        facets.invariant(isinstance(value, str) and bool(value))
        codec.nfc(value)
    facets.invariant(type(selected["revision_number"]) is int and 0 < selected["revision_number"] < 2**63)
    codec.key(root["schema_key"])
    view = root_view(root)
    normalized_owner = normalize_owner(view["owner"])
    facets.invariant(view["owner"] == {k: v for k, v in normalized_owner.items() if v is not None})
    budget.resolve("facet_schema_revisions", root["current_revision_id"])
    current = db.execute(
        "SELECT facet_schema_id FROM facet_schema_revisions WHERE facet_schema_revision_id=?", (root["current_revision_id"],)
    ).fetchone()
    facets.invariant(current is not None and current[0] == root_id)
    definition = facets.load_definition(db, identity)
    return {
        "ok": True,
        "command": COMMAND,
        "response_contract": CONTRACT,
        "root": view,
        "revision": {
            "facet_schema_id": root_id,
            "facet_schema_revision_id": identity,
            "revision_number": str(selected["revision_number"]),
            "definition": definition,
            "definition_hash": selected["definition_hash"],
        },
    }


def execute(request: Mapping[str, Any], context: CommandContext) -> dict[str, Any]:
    db = context.ledger
    if not isinstance(db, LedgerConnection) or db.in_transaction or db._command_transaction:
        failure("environment_failure", "ledger", "facet commands require an idle transaction-aware ledger")
    if context.transport_metadata.get("adapter") not in {None, "cli"}:
        failure("environment_failure", "admission", "revision readback requires trusted-local admission")
    budget = FacetBudget()
    old_timeout = install_budget(db, budget)
    try:
        r = normalize(request)
        if len(canonical_json_bytes(r)) > REQUEST_BYTES:
            failure("environment_failure", "capacity")
        with db.atomic_command(write=False):
            try:
                result = lookup(db, r["facet_schema_revision_id"], budget)
            except SpineValidationError as exc:
                if exc.code.startswith(("referenced_row_not_found:", "environment_failure:")):
                    raise
                failure("environment_failure", "facets", "invalid persisted facet evidence")
            except (TypeError, ValueError, KeyError, UnicodeError, OverflowError) as exc:
                raise SpineValidationError("environment_failure:facets", "invalid persisted facet evidence") from exc
            if context.dry_run:
                result["dry_run"] = True
            if len(canonical_json_bytes(result)) > RESPONSE_BYTES:
                failure("environment_failure", "capacity")
            budget.check()
        budget.check()
        return result
    except sqlite3.OperationalError as exc:
        raise SpineValidationError("environment_failure:capacity", "facet operation could not complete within its budget") from exc
    except sqlite3.DatabaseError as exc:
        raise SpineValidationError("environment_failure:facets", "invalid persisted facet evidence") from exc
    finally:
        db.set_progress_handler(None, 0)
        db.execute(f"PRAGMA busy_timeout={old_timeout}")
