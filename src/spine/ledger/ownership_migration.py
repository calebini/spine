"""Ownership-state rebuild inside the unpublished recurring-task candidate."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from importlib import resources

from spine.core.recurring_tasks import invariant
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.ownership import read_access_state

RESOURCE = "ownership_bootstrap.candidate.sql"
TEMPORARY = "ledger_access_state_bootstrap_new"
TRIGGERS = ("web_group_status_changed", "web_route_security_changed", "web_subject_status_changed")


def rebuild_access_state(db: sqlite3.Connection, fault: Callable[[str], None]) -> None:
    """Caller owns explicit migration transaction and FK restoration."""
    invariant(db.in_transaction and db.execute("PRAGMA foreign_keys").fetchone()[0] == 0)
    read_ledger_instance_id(db)
    read_access_state(db)  # Reject invalid existing identifiers before any copy.
    invariant(db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (TEMPORARY,)).fetchone() is None,
              "ownership migration temporary name collision")
    dependencies = db.execute(
        "SELECT type,name,sql FROM sqlite_schema WHERE type IN ('trigger','view') AND instr(lower(sql),'ledger_access_state')>0"
    ).fetchall()
    invariant({r["name"] for r in dependencies} == set(TRIGGERS), "unsupported ownership migration dependent object")
    definitions = {r["name"]: r["sql"] for r in dependencies}
    sql = resources.files("spine.ledger").joinpath(RESOURCE).read_text()
    db.execute(sql.replace("CREATE TABLE ledger_access_state", f'CREATE TABLE "{TEMPORARY}"', 1))
    fault("ownership_created")
    columns = "singleton_id,ledger_id,realm_id,mode,identity_mode,access_epoch,recovery_epoch"
    db.execute(f"INSERT INTO {TEMPORARY}({columns}) SELECT {columns} FROM ledger_access_state")
    fault("ownership_copied")
    for name in TRIGGERS:
        db.execute(f"DROP TRIGGER {name}")
    db.execute("DROP TABLE ledger_access_state")
    fault("ownership_dropped")
    db.execute(f"ALTER TABLE {TEMPORARY} RENAME TO ledger_access_state")
    for name in TRIGGERS:
        db.execute(definitions[name])
    read_access_state(db)
    fault("ownership_rebuilt")
