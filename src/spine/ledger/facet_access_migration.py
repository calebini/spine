"""Offline atomic grant-vocabulary extension; never used in routine admission."""

import sqlite3
from importlib import resources

from spine.core.errors import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema


def install_facet_access(db: sqlite3.Connection, *, applied_at_utc: str, fresh: bool = False) -> None:
    if db.in_transaction:
        raise SpineValidationError("ledger_migration_predecessor", "facet access migration requires an idle connection")
    verify_runtime_schema(db, expected_version=16)
    foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        verify_runtime_schema(db, expected_version=16)
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise SpineValidationError("ledger_migration_predecessor", "predecessor integrity check failed")
        extensions = [
            r[0]
            for r in db.execute(
                "SELECT sql FROM sqlite_schema WHERE tbl_name='access_grants' AND type IN ('index','trigger') "
                "AND sql IS NOT NULL ORDER BY type,name"
            )
        ]
        before = [tuple(r) for r in db.execute("SELECT * FROM access_grants ORDER BY grant_id")]
        dependents = [
            (r[0], r[1])
            for r in db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name!='access_grants' "
                "AND instr(sql,'access_grants')>0 ORDER BY name"
            )
        ]
        for name, _ in dependents:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        statement = ""
        for line in (
            resources.files("spine.ledger.migrations").joinpath("0017_facet_access_grants.sql").read_text().splitlines(keepends=True)
        ):
            statement += line
            if sqlite3.complete_statement(statement):
                db.execute(statement)
                statement = ""
        if statement.strip():
            raise RuntimeError("incomplete migration")
        for sql in extensions:
            db.execute(sql)
        for _, sql in dependents:
            db.execute(sql)
        if (
            before != [tuple(r) for r in db.execute("SELECT * FROM access_grants ORDER BY grant_id")]
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise SpineValidationError("ledger_migration_verification", "grant migration parity failed")
        db.execute("INSERT INTO ledger_schema VALUES(17,?)", (applied_at_utc,))
        if not fresh:
            verify_runtime_schema(db)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute(f"PRAGMA foreign_keys={foreign_keys}")
