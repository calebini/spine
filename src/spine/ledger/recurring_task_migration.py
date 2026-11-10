"""Explicit internal schema-20 candidate; not wired into public migrations yet."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from importlib import resources

from spine.core.recurring_tasks import invariant
from spine.ledger.facets import verify_all
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.ownership import read_access_state
from spine.ledger.ownership_migration import RESOURCE as OWNERSHIP_RESOURCE
from spine.ledger.ownership_migration import rebuild_access_state
from spine.ledger.preflight import expected_schema_objects, verify_runtime_schema
from spine.ledger.recurring_tasks import verify_deep
from spine.ledger.rendering_definitions import verify_deep as verify_rendering_deep
from spine.ledger.sqlite import assert_ledger_invariants
from spine.ledger.transactions import LedgerConnection

CANDIDATE_SCHEMA_VERSION = 20
MANIFEST = "schema_object_manifest.recurring-tasks-candidate.json"
MIGRATION = "0020_recurring_related_tasks.sql"


def statements(script: str) -> list[str]:
    result: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            result.append(buffer.strip())
            buffer = ""
    invariant(not buffer.strip(), "incomplete recurring-task migration")
    return result


def verify_candidate_schema(db: sqlite3.Connection) -> None:
    """Bounded schema metadata checks, never domain/history scans."""
    manifest = json.loads(resources.files("spine.ledger").joinpath(MANIFEST).read_text())
    invariant(
        manifest["manifest_version"] == "spine.recurring-tasks-candidate-schema-manifest.v1"
        and manifest["predecessor_schema_version"] == "19"
        and manifest["candidate_schema_version"] == "20"
        and manifest["activation"] == "internal_candidate_only"
    )
    migration = resources.files("spine.ledger.migrations").joinpath(MIGRATION).read_bytes()
    invariant(hashlib.sha256(migration).hexdigest() == manifest["migration_sha256"], "recurring-task migration drift")
    ownership = resources.files("spine.ledger").joinpath(OWNERSHIP_RESOURCE).read_bytes()
    invariant(hashlib.sha256(ownership).hexdigest() == manifest["ownership_bootstrap_sha256"], "ownership migration drift")
    expected = {obj.name: (obj.object_type, obj.definition_sha256) for obj in expected_schema_objects(version=19)}
    expected.update({obj["name"]: (obj["object_type"], obj["definition_sha256"]) for obj in manifest["objects"]})
    for name, (kind, digest) in expected.items():
        row = db.execute("SELECT type,sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()
        invariant(
            row is not None
            and row["type"] == kind
            and row["sql"] is not None
            and hashlib.sha256(row["sql"].encode()).hexdigest() == digest,
            "recurring-task schema-object mismatch: " + name,
        )


def attach_candidate(db: sqlite3.Connection) -> None:
    """Opt into internal write validation on a reopened candidate connection."""
    invariant(isinstance(db, LedgerConnection) and not db.in_transaction, "candidate requires an idle ledger connection")
    assert isinstance(db, LedgerConnection)
    invariant(
        db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0] == CANDIDATE_SCHEMA_VERSION,
        "candidate schema version mismatch",
    )
    verify_candidate_schema(db)
    db.enable_recurring_tasks()


def install_candidate(
    db: sqlite3.Connection,
    *,
    disposable_test_ledger: bool = False,
    applied_at_utc: str = "1970-01-01T00:00:00Z",
    fault: Callable[[str], None] | None = None,
) -> None:
    """One atomic candidate migration, only on explicitly disposable test ledgers.

    Normal initialization, CURRENT_SCHEMA_VERSION and migrate_schema remain 19.
    Recording candidate 20 ensures ordinary old writers refuse this ledger.
    """
    invariant(
        disposable_test_ledger and isinstance(db, LedgerConnection) and not db.in_transaction,
        "recurring-task candidate requires an idle disposable test ledger",
    )
    if db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0] == CANDIDATE_SCHEMA_VERSION:
        attach_candidate(db)
        return
    verify_runtime_schema(db, expected_version=19)
    inject = fault or (lambda stage: None)
    invariant(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys must be enabled")
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        verify_runtime_schema(db, expected_version=19)
        invariant(not db.execute("PRAGMA foreign_key_check").fetchall(), "predecessor foreign-key check failed")
        invariant(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "predecessor integrity check failed")
        inject("preflight")
        rebuild_access_state(db, inject)
        script = resources.files("spine.ledger.migrations").joinpath(MIGRATION).read_text()
        for statement in statements(script):
            db.execute(statement)
        inject("ddl")
        verify_candidate_schema(db)
        read_ledger_instance_id(db)
        read_access_state(db)
        invariant(not db.execute("PRAGMA foreign_key_check").fetchall(), "candidate foreign-key check failed")
        invariant(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "candidate integrity check failed")
        assert_ledger_invariants(db)
        verify_all(db)
        verify_rendering_deep(db)
        verify_deep(db)
        inject("verified")
        db.execute("INSERT INTO ledger_schema VALUES (?,?)", (CANDIDATE_SCHEMA_VERSION, applied_at_utc))
        inject("activation")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")
        invariant(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign key enforcement restoration failed")
    attach_candidate(db)
