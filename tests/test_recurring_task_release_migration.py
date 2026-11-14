"""R4 migration/preflight substrate. Disposable ledgers, no public activation."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.core.errors import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.migrate import _apply_migration, current_schema_version, migrate_schema
from spine.ledger.preflight import expected_schema_objects, verify_runtime_schema
from spine.ledger.recurring_task_migration import MIGRATION, install_recurring_task_storage
from spine.ledger.recurring_tasks import TABLE_KEYS
from tests import test_binding_successor_materialization as ordinary

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-11-14T10:00:00Z"


def state(db):
    objects = list(db.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"))
    tables = [r[1] for r in objects if r[0] == "table"]
    return ([tuple(r) for r in objects], {t: sorted(tuple(r) for r in db.execute(f'SELECT * FROM "{t}"')) for t in tables})


class ReleaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        initialize_schema(self.db)

    def install(self, **kwargs):
        install_recurring_task_storage(self.db, applied_at_utc=AT, **kwargs)

    def test_ordered_dispatch_uses_atomic_migration_and_initializes_no_rules(self):
        identity = read_ledger_instance_id(self.db)
        _apply_migration(self.db, version=20, migration_name=MIGRATION)
        self.assertEqual(verify_runtime_schema(self.db, expected_version=20).schema_version, 20)
        self.assertEqual(read_ledger_instance_id(self.db), identity)
        for table in TABLE_KEYS:
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                             int(table == "related_task_catalog_state"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ledger_access_state").fetchone()[0], 0)
        before = state(self.db), self.db.total_changes
        self.install()
        self.assertEqual((state(self.db), self.db.total_changes), before)

    def test_default_remains_closed_until_coherent_runtime_activation(self):
        self.assertEqual(IMPLEMENTED_LEDGER_SCHEMA_VERSION, 19)
        self.assertEqual(migrate_schema(self.db).after_version, 19)
        self.install()
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_unsupported"):
            migrate_schema(self.db)

    def test_all_faults_restore_old_schema_rows_fk_and_version(self):
        before = state(self.db)
        for stage in ("preflight", "ownership_created", "ownership_copied", "ownership_dropped",
                      "ownership_rebuilt", "ddl", "verified", "activation"):
            with self.subTest(stage=stage):
                def fail(actual, stage=stage):
                    if actual == stage:
                        raise RuntimeError(stage)

                with self.assertRaisesRegex(RuntimeError, stage):
                    self.install(fault=fail)
                self.assertEqual(state(self.db), before)
                self.assertFalse(self.db.in_transaction)
                self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertFalse(getattr(self.db, "_recurring_tasks_enabled", False))

    def test_existing_ownership_and_scheduling_history_retains_exact_values(self):
        fixture = ordinary.BindingSuccessorMaterializationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.create()
        db = fixture.db
        with db.atomic_command():
            db.execute("INSERT INTO ledger_access_state VALUES(1,'migration-fixture','realm','multi_user','trusted_identity',7,3)")
        _, rows = state(db)
        before = {t: r for t, r in rows.items() if t != "ledger_schema"}
        install_recurring_task_storage(db, applied_at_utc=AT)
        after = state(db)[1]
        self.assertEqual({t: after[t] for t in before}, before)
        self.assertEqual(current_schema_version(db), 20)
        self.assertEqual(tuple(db.execute("SELECT access_epoch,recovery_epoch FROM ledger_access_state").fetchone()), (7, 3))

    def test_runtime_metadata_check_never_scans_ledger_or_runs_deep_verification(self):
        self.install()
        traced = []
        self.db.set_trace_callback(traced.append)
        self.addCleanup(self.db.set_trace_callback, None)
        for _ in range(3):
            verify_runtime_schema(self.db, expected_version=20)
        selects = [s.lower() for s in traced]
        self.assertFalse(any("pragma integrity_check" in s or "pragma foreign_key_check" in s or "quick_check" in s for s in selects))
        self.assertFalse(any("from related_task_" in s or "from coordination_items" in s for s in selects))

    def test_missing_drifted_and_extra_objects_keep_normal_preflight_errors(self):
        self.install()
        self.db.execute("CREATE TABLE operator_extra(note TEXT)")
        verify_runtime_schema(self.db, expected_version=20)
        self.db.execute("DROP INDEX related_task_rules_source_idx")
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_missing_indexes"):
            verify_runtime_schema(self.db, expected_version=20)
        self.db.execute("CREATE INDEX related_task_rules_source_idx ON related_task_rules(related_task_rule_id)")
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_object_definition_mismatch"):
            verify_runtime_schema(self.db, expected_version=20)

    def test_manifest_is_exact_predecessor_plus_pinned_delta(self):
        path = ROOT / "src/spine/ledger/schema_object_manifest.recurring-tasks-candidate.json"
        expected = {o.name: (o.object_type, o.definition_sha256) for o in expected_schema_objects(version=19)}
        expected.update({o["name"]: (o["object_type"], o["definition_sha256"]) for o in json.loads(path.read_bytes())["objects"]})
        actual = {o.name: (o.object_type, o.definition_sha256) for o in expected_schema_objects(version=20)}
        self.assertEqual(actual, expected)

    def test_idle_connection_required_and_unknown_dependents_fail_atomically(self):
        before = state(self.db)
        with self.db.atomic_command(), self.assertRaises(SpineValidationError):
            self.install()
        self.assertEqual(state(self.db), before)
        self.db.execute("CREATE VIEW operator_view AS SELECT * FROM ledger_access_state")
        before = state(self.db)
        with self.assertRaisesRegex(SpineValidationError, "unsupported ownership migration dependent"):
            self.install()
        self.assertEqual(state(self.db), before)

    def test_metadata_mismatch_at_final_gate_rolls_back_everything(self):
        original = verify_runtime_schema

        def drift(db, *, expected_version=None):
            if expected_version == 20:
                raise SpineValidationError("ledger_schema_object_definition_mismatch", "injected final manifest drift")
            return original(db, expected_version=expected_version)

        before = state(self.db)
        with patch("spine.ledger.recurring_task_migration.verify_runtime_schema", side_effect=drift), \
             self.assertRaisesRegex(SpineValidationError, "injected final manifest drift"):
            self.install()
        self.assertEqual(state(self.db), before)

    def test_second_writer_cannot_enter_during_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "migration.sqlite"
            db = connect(path)
            other = connect(path, busy_timeout_ms=0)
            try:
                initialize_schema(db)

                def compete(stage):
                    if stage in {"preflight", "ddl"}:
                        # WAL readers see the predecessor, never a half-rebuilt
                        # ownership table or a partially installed family.
                        self.assertEqual(current_schema_version(other), 19)
                        self.assertIsNone(other.execute("SELECT name FROM sqlite_schema WHERE name='related_task_rules'").fetchone())
                        with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                            other.execute("BEGIN IMMEDIATE")

                install_recurring_task_storage(db, applied_at_utc=AT, fault=compete)
                verify_runtime_schema(other, expected_version=20)
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
            finally:
                other.close()
                db.close()
