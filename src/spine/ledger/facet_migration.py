"""Offline, atomic schema-15 -> schema-16 maintenance (never routine preflight)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib import resources

from spine.core.errors import SpineValidationError
from spine.ledger.facets import invariant, verify_all
from spine.ledger.preflight import current_schema_version, verify_runtime_schema
from spine.ledger.transactions import LedgerConnection


def install_facet_storage(db: sqlite3.Connection, *, applied_at_utc: str, fresh: bool = False) -> None:
    from spine.ledger.sqlite import assert_ledger_invariants

    if db.in_transaction or current_schema_version(db) != 15:
        raise SpineValidationError("ledger_migration_predecessor", "facet migration requires idle schema 15")
    db.execute("BEGIN IMMEDIATE")
    try:
        manifest = json.loads(resources.files("spine.ledger").joinpath("schema_object_manifest.schema15.json").read_text())
        for obj in manifest["schemas"]["15"]["objects"]:
            actual = db.execute("SELECT type,sql FROM sqlite_schema WHERE name=?", (obj["name"],)).fetchone()
            invariant(
                actual is not None
                and actual[0] == obj["object_type"]
                and hashlib.sha256(actual[1].encode()).hexdigest() == obj["definition_sha256"]
            )
        invariant(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        invariant(not db.execute("PRAGMA foreign_key_check").fetchall())
        assert_ledger_invariants(db)
        audit_before = [tuple(r) for r in db.execute("SELECT * FROM coordination_catalog_audit_log ORDER BY catalog_audit_id")]
        audit_extensions = [
            r[0]
            for r in db.execute(
                "SELECT sql FROM sqlite_schema WHERE tbl_name='coordination_catalog_audit_log' "
                "AND type IN ('index','trigger') AND sql IS NOT NULL AND name!='coordination_catalog_audit_resource_idx' "
                "ORDER BY type,name"
            )
        ]
        sql = resources.files("spine.ledger.migrations").joinpath("0016_archetype_facet_storage.sql").read_text()
        # executescript implicitly commits: execute complete statements individually instead.
        statement = ""
        for line in sql.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                db.execute(statement)
                statement = ""
        invariant(not statement.strip())
        for sql in audit_extensions:
            db.execute(sql)
        invariant(audit_before == [tuple(r) for r in db.execute("SELECT * FROM coordination_catalog_audit_log ORDER BY catalog_audit_id")])
        invariant(
            db.execute("SELECT COUNT(*) FROM item_facet_snapshots").fetchone()[0]
            == db.execute("SELECT COUNT(*) FROM coordination_item_versions").fetchone()[0]
        )
        verify_all(db)
        invariant(not db.execute("PRAGMA foreign_key_check").fetchall())
        db.execute("INSERT INTO ledger_schema VALUES (16,?)", (applied_at_utc,))
        # Fresh initialization is also used to generate the current compiled manifest.
        # Existing-ledger migration must verify it before committing activation.
        if not fresh:
            verify_runtime_schema(db, expected_version=16)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    if isinstance(db, LedgerConnection):
        db.enable_facets()
