"""Atomic schema-18 location freeze; offline migration, never routine admission."""

import sqlite3
from importlib import resources

from spine.core.errors import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema


def install_facet_location_freeze(db: sqlite3.Connection, *, applied_at_utc: str, fresh: bool = False) -> None:
    if db.in_transaction:
        raise SpineValidationError("ledger_migration_predecessor", "location freeze migration requires an idle connection")
    verify_runtime_schema(db, expected_version=17)
    try:
        db.execute("BEGIN IMMEDIATE")
        verify_runtime_schema(db, expected_version=17)
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise SpineValidationError("ledger_migration_predecessor", "predecessor integrity check failed")
        # execute, not executescript: DDL and version activation share this transaction.
        statement = ""
        for line in (
            resources.files("spine.ledger.migrations").joinpath("0018_facet_location_immutability.sql").read_text().splitlines(keepends=True)
        ):
            statement += line
            if sqlite3.complete_statement(statement):
                db.execute(statement)
                statement = ""
        if statement.strip():
            raise RuntimeError("incomplete migration")
        db.execute("INSERT INTO ledger_schema VALUES(18,?)", (applied_at_utc,))
        if not fresh:
            verify_runtime_schema(db, expected_version=18)
        db.commit()
    except BaseException:
        db.rollback()
        raise
