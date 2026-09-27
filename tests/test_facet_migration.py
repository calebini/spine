from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.facet_migration import install_facet_storage
from spine.ledger.migrate import current_schema_version, migrate_schema, verify_schema
from spine.ledger.preflight import verify_runtime_schema
from tests.facet_storage_support import NOW, all_rows
from tests.test_ledger_sqlite import insert_valid_event_bundle, insert_valid_task_bundle


def predecessor(db):
    with patch("spine.ledger.facet_migration.install_facet_storage"):
        initialize_schema(db)
    # Raw predecessor fixture: the new allocator deliberately cannot write schema 15.
    # These helpers normally use its context, so enable no facet gate for this offline fixture.
    with patch.object(db, "version_allocation"), patch("spine.ledger.facets.insert_snapshot"):
        insert_valid_event_bundle(db)
        with patch("tests.test_ledger_sqlite.insert_subject"):
            insert_valid_task_bundle(db)
    with db:
        for kind in ("project", "collection"):
            db.execute(
                "INSERT INTO coordination_items (item_id,item_type,current_version,status,created_at_utc,updated_at_utc) "
                "VALUES (?,?,2,'active',?,?)",
                (kind, kind, NOW, NOW),
            )
            for version in (1, 2):
                db.execute(
                    "INSERT INTO coordination_item_versions VALUES (?,?,?,NULL,?,?,NULL,?,'subject-1')",
                    (kind, version, kind, "0" * 64, "1" * 64, NOW),
                )
        db.execute(
            "INSERT INTO coordination_catalog_audit_log VALUES ('old-audit','item_archetype','old-resource',"
            "'created','created','subject-1','old-command','{}',?,?)",
            ("0" * 64, NOW),
        )
    return all_rows(db)


class FacetMigrationTests(unittest.TestCase):
    def test_predecessor_all_types_history_and_backup_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect(Path(directory) / "ledger.sqlite")
            backup = sqlite3.connect(Path(directory) / "backup.sqlite")
            try:
                before = predecessor(db)
                db.backup(backup)
                result = migrate_schema(db)
                self.assertEqual(result.applied_versions, (16,))
                self.assertEqual(result.after_version, 16)
                after = all_rows(db)
                for table, rows in before.items():
                    if table != "ledger_schema":
                        self.assertEqual(after[table], rows, table)
                versions = [
                    (r[0], r[1]) for r in db.execute("SELECT item_id,version FROM coordination_item_versions ORDER BY item_id,version")
                ]
                markers = [tuple(r) for r in db.execute("SELECT * FROM item_facet_snapshots ORDER BY item_id,item_version")]
                self.assertEqual(markers, [(item, version, 0, 2) for item, version in versions])
                for table in (
                    "facet_schemas",
                    "facet_schema_revisions",
                    "archetype_facet_bindings",
                    "item_facet_entries",
                    "item_facet_references",
                    "item_facet_current_values",
                ):
                    self.assertEqual(after[table], [])
                fresh = connect()
                try:
                    initialize_schema(fresh)
                    sql = "SELECT type,name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                    self.assertEqual([tuple(r) for r in db.execute(sql)], [tuple(r) for r in fresh.execute(sql)])
                finally:
                    fresh.close()
                # Predecessor runtime's exact-match admission rejects the migrated file.
                with (
                    patch("spine.ledger.preflight.CURRENT_SCHEMA_VERSION", 15),
                    self.assertRaisesRegex(SpineValidationError, "ledger_schema_version_mismatch"),
                ):
                    verify_runtime_schema(db)
                restored = sqlite3.connect(Path(directory) / "restored.sqlite")
                restored.row_factory = sqlite3.Row
                try:
                    backup.backup(restored)
                    self.assertEqual(all_rows(restored), before)
                    self.assertEqual(current_schema_version(restored), 15)
                finally:
                    restored.close()
            finally:
                backup.close()
                db.close()

    def test_interruption_or_failed_parity_rolls_back_ddl_audit_and_backfill(self):
        for stage in ("verify_all", "verify_runtime_schema"):
            with self.subTest(stage=stage):
                db = connect()
                try:
                    before = predecessor(db)
                    objects = [tuple(r) for r in db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name")]
                    with (
                        patch(f"spine.ledger.facet_migration.{stage}", side_effect=RuntimeError("injected")),
                        self.assertRaisesRegex(RuntimeError, "injected"),
                    ):
                        install_facet_storage(db, applied_at_utc=NOW)
                    self.assertEqual(all_rows(db), before)
                    self.assertEqual(objects, [tuple(r) for r in db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name")])
                    self.assertEqual(current_schema_version(db), 15)
                    migrate_schema(db)
                    verify_schema(db)
                finally:
                    db.close()

    def test_corrupt_predecessor_is_not_activated(self):
        db = connect()
        try:
            predecessor(db)
            with db:
                db.execute("DROP INDEX independent_read_work_policy_idx")
            with self.assertRaises(SpineValidationError):
                migrate_schema(db, verify=False)
            self.assertEqual(current_schema_version(db), 15)
        finally:
            db.close()

    def test_catalog_rebuild_preserves_noncolliding_extra_indexes_and_triggers(self):
        db = connect()
        try:
            predecessor(db)
            db.execute("CREATE INDEX local_audit_command_idx ON coordination_catalog_audit_log(command_id)")
            db.execute(
                "CREATE TRIGGER local_audit_guard BEFORE DELETE ON coordination_catalog_audit_log "
                "BEGIN SELECT RAISE(ABORT,'local audit preservation'); END"
            )
            db.commit()
            before = [tuple(r) for r in db.execute("SELECT name,sql FROM sqlite_schema WHERE name LIKE 'local_audit_%' ORDER BY name")]
            migrate_schema(db)
            self.assertEqual(
                before, [tuple(r) for r in db.execute("SELECT name,sql FROM sqlite_schema WHERE name LIKE 'local_audit_%' ORDER BY name")]
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "local audit preservation"), db:
                db.execute("DELETE FROM coordination_catalog_audit_log")
        finally:
            db.close()
