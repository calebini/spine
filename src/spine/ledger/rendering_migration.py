"""Atomic offline schema-19 installation and predecessor test support."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from importlib import resources

from spine.core.errors import SpineValidationError
from spine.ledger.preflight import expected_schema_objects, verify_runtime_schema
from spine.ledger.rendering_definitions import insert_presentation, invariant, verify_deep
from spine.ledger.transactions import LedgerConnection


def statements(script: str) -> list[str]:
    result, buffer = [], ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            result.append(buffer.strip())
            buffer = ""
    invariant(not buffer.strip(), "incomplete rendering candidate DDL")
    return result


def verify_candidate_schema(db: sqlite3.Connection) -> None:
    """Pinned metadata-only candidate validation; never scans domain rows."""
    manifest = json.loads(resources.files("spine.ledger").joinpath("schema_object_manifest.rendering-candidate.json").read_text())
    invariant(
        manifest["manifest_version"] == "spine.rendering-candidate-schema-manifest.v1"
        and manifest["predecessor_schema_version"] == "18"
        and manifest["activation"] == "internal_candidate_only"
    )
    expected = {item.name: (item.object_type, item.definition_sha256) for item in expected_schema_objects(version=18)}
    expected.update({item["name"]: (item["object_type"], item["definition_sha256"]) for item in manifest["objects"]})
    for name, (kind, digest) in expected.items():
        row = db.execute("SELECT type,sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()
        invariant(
            row is not None
            and row["type"] == kind
            and row["sql"] is not None
            and hashlib.sha256(row["sql"].encode()).hexdigest() == digest,
            "candidate schema-object definition mismatch",
        )


def _rebuild(db: sqlite3.Connection, table: str, transform: Callable[[str], str], extra_columns: str = "") -> None:
    original = db.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone()[0]
    indexes = [
        r[0]
        for r in db.execute(
            "SELECT sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name",
            (table,),
        )
    ]
    dependents = list(
        db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name!=? AND instr(sql,?)>0 ORDER BY name", (table, table)
        )
    )
    for name, _ in dependents:
        db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
    columns = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
    transformed = transform(original)
    invariant(transformed != original, "candidate rebuild did not change its contract")
    db.execute(re.sub(r'\ACREATE TABLE "?' + re.escape(table) + r'"?', f"CREATE TABLE {table}_candidate", transformed, count=1))
    names = ",".join('"' + c + '"' for c in columns)
    db.execute(
        f"INSERT INTO {table}_candidate ({names}{extra_columns}) SELECT {names}"
        + (",NULL,NULL,NULL" if extra_columns else "")
        + f" FROM {table}"
    )
    db.execute(f"DROP TABLE {table}")
    db.execute(f"ALTER TABLE {table}_candidate RENAME TO {table}")
    for script in indexes:
        db.execute(script)
    for _, script in dependents:
        db.execute(script)


def _rendering_table(sql: str) -> str:
    sql = sql.replace(
        "rendering_contract = 'spine.notification-rendering.v1'",
        "rendering_contract IN ('spine.notification-rendering.v1','spine.notification-rendering.v2')",
    )
    insertion = """
  base_rendering_json TEXT CHECK(base_rendering_json IS NULL OR (json_valid(base_rendering_json) AND length(CAST(base_rendering_json AS BLOB))<=32768)),
  details_evidence_json TEXT CHECK(details_evidence_json IS NULL OR (json_valid(details_evidence_json) AND length(CAST(details_evidence_json AS BLOB))<=16384)),
  details_contract_version TEXT,
  CHECK((rendering_contract='spine.notification-rendering.v1' AND base_rendering_json IS NULL AND details_evidence_json IS NULL AND details_contract_version IS NULL)
     OR (rendering_contract='spine.notification-rendering.v2' AND base_rendering_json IS NOT NULL AND details_evidence_json IS NOT NULL AND details_contract_version='spine.notification-rendering-details-evidence.v1')),
"""  # noqa: E501 -- exact DDL bytes are pinned by the candidate schema manifest.
    return sql.replace("  CHECK (created_at_utc", insertion + "  CHECK (created_at_utc", 1)


def install_candidate(db: sqlite3.Connection, *, disposable_test_ledger: bool = False, fault: Callable[[str], None] | None = None) -> None:
    """Atomic schema-18 candidate, never a production initialize/migrate path."""
    if not disposable_test_ledger or db.in_transaction or not isinstance(db, LedgerConnection):
        raise SpineValidationError("ledger_migration_predecessor", "candidate rendering storage requires an idle disposable test ledger")
    if db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0] == 19:
        verify_candidate_schema(db)
        db.enable_renderings()
        return
    _install(db, fault=fault)


def install_rendering_storage(
    db: sqlite3.Connection, *, applied_at_utc: str, fresh: bool = False, fault: Callable[[str], None] | None = None
) -> None:
    """Offline schema-19 activation; all writers must be excluded by the operator."""
    if db.in_transaction or not isinstance(db, LedgerConnection):
        raise SpineValidationError("ledger_migration_predecessor", "rendering migration requires an idle transaction-aware ledger")
    _install(db, applied_at_utc=applied_at_utc, fault=fault)


def _install(db, *, applied_at_utc=None, fault=None):
    verify_runtime_schema(db, expected_version=18)
    inject = fault or (lambda stage: None)
    fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
    db.execute("PRAGMA foreign_keys=OFF")
    preserved = (
        "notification_policies",
        "notification_profiles",
        "notification_profile_revisions",
        "notification_profile_templates",
        "command_receipts",
        "side_effect_attempts",
        "work_instances",
        "access_grants",
        "coordination_catalog_audit_log",
        "notification_renderings",
    )
    try:
        db.execute("BEGIN EXCLUSIVE")
        verify_runtime_schema(db, expected_version=18)
        invariant(
            db.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and not db.execute("PRAGMA foreign_key_check").fetchall(),
            "predecessor integrity check failed",
        )
        before = {t: sorted(tuple(r) for r in db.execute(f"SELECT * FROM {t}")) for t in preserved}
        inject("preflight")
        _rebuild(
            db,
            "access_grants",
            lambda s: s.replace("'facet_schema')", "'facet_schema','notification_rendering_definition')").replace(
                "resource_kind!='facet_schema'", "resource_kind NOT IN ('facet_schema','notification_rendering_definition')"
            ),
        )
        _rebuild(
            db,
            "coordination_catalog_audit_log",
            lambda s: s.replace(
                "'archetype_facet_binding')",
                "'archetype_facet_binding','notification_rendering_definition','notification_rendering_disclosure')",
            ),
        )
        _rebuild(db, "notification_renderings", _rendering_table, ",base_rendering_json,details_evidence_json,details_contract_version")
        for statement in statements(resources.files("spine.ledger").joinpath("rendering_integration.candidate.sql").read_text()):
            db.execute(statement)
        for operation in ("INSERT", "UPDATE"):
            db.execute(f"""CREATE TRIGGER rendering_grant_resource_{operation.lower()} BEFORE {operation} ON access_grants
                WHEN NEW.resource_kind='notification_rendering_definition' AND (NEW.resource_owner_revision!=1 OR
                  NOT EXISTS(SELECT 1 FROM notification_rendering_definitions WHERE notification_rendering_definition_id=NEW.resource_id))
                BEGIN SELECT RAISE(ABORT,'rendering grant requires resource'); END""")
        inject("ddl")
        for policy in db.execute("SELECT * FROM notification_policies ORDER BY item_id,version,policy_id").fetchall():
            insert_presentation(db, policy, {"kind": "ordinary"})
        inject("backfill")
        for table in preserved:
            columns = (
                "*"
                if table != "notification_renderings"
                else ",".join(
                    r[1]
                    for r in db.execute("PRAGMA table_info(notification_renderings)")
                    if r[1] not in {"base_rendering_json", "details_evidence_json", "details_contract_version"}
                )
            )
            invariant(
                before[table] == sorted(tuple(r) for r in db.execute(f"SELECT {columns} FROM {table}")),
                "migration changed historical facts",
            )
        verify_deep(db)
        verify_candidate_schema(db)
        invariant(not db.execute("PRAGMA foreign_key_check").fetchall(), "candidate foreign key verification failed")
        inject("verified")
        if applied_at_utc is not None:
            db.execute("INSERT INTO ledger_schema VALUES(19,?)", (applied_at_utc,))
            verify_runtime_schema(db, expected_version=19)
            inject("activation")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute(f"PRAGMA foreign_keys={fk}")
    db.enable_renderings()
