from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.identity import install_identity, read_ledger_instance_id, schema13_identity
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.ledger.preflight import verify_runtime_schema
from spine.runtime.preflight import WorkerBootstrapConfig, admit_worker


def schema13(db):
    # Exercise real initialization up to the boundary without creating identity.
    with patch("spine.ledger.sqlite.install_identity"):
        initialize_schema(db)
    with db:
        for row in db.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'independent_read_%'").fetchall():
            db.execute('DROP INDEX ' + row[0])
        db.execute("DELETE FROM ledger_schema WHERE schema_version=15")


class LedgerIdentityTests(unittest.TestCase):
    def test_fresh_unique_stable_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            ids = []
            for name in ("a", "b"):
                db = connect(Path(directory) / name)
                initialize_schema(db)
                identity = read_ledger_instance_id(db)
                changes = db.total_changes
                initialize_schema(db)
                verify_runtime_schema(db)
                self.assertEqual(read_ledger_instance_id(db), identity)
                self.assertEqual(db.total_changes, changes)
                db.close()
                db = connect(Path(directory) / name)
                self.assertEqual(read_ledger_instance_id(db), identity)
                ids.append(identity)
                db.close()
            self.assertNotEqual(*ids)

    def test_deterministic_backfill_independent_of_insert_order_path_and_migration_time(self):
        identities = []
        for values in ((1, 2), (2, 1)):
            db = connect()
            schema13(db)
            db.execute("CREATE TABLE extra (i INTEGER, value BLOB)")
            db.executemany("INSERT INTO extra VALUES (?, ?)", [(i, b'bytes') for i in values])
            db.commit()
            expected = schema13_identity(db)
            with patch("spine.ledger.migrate._utc_now", return_value=f"2026-09-0{values[0]}T00:00:00Z"):
                result = migrate_schema(db)
            self.assertEqual(result.applied_versions, (14, 15))
            self.assertEqual(read_ledger_instance_id(db), expected)
            identities.append(expected)
            changes = db.total_changes
            migrate_schema(db, verify=False)
            self.assertEqual(db.total_changes, changes)
            db.close()
        self.assertEqual(*identities)

    def test_different_data_produces_different_backfill(self):
        db = connect()
        schema13(db)
        before = schema13_identity(db)
        db.execute("INSERT INTO subjects VALUES ('s','person','Person','active','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
        self.assertNotEqual(schema13_identity(db), before)
        db.close()

    def test_backup_restore_and_vacuum_preserve_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = connect(Path(directory) / "source")
            initialize_schema(source)
            identity = read_ledger_instance_id(source)
            target = connect(Path(directory) / "restored")
            source.backup(target)
            target.execute("VACUUM")
            verify_schema(target)
            self.assertEqual(read_ledger_instance_id(target), identity)
            source.close()
            target.close()

    def test_identity_mutation_and_replacement_rejected(self):
        db = connect()
        initialize_schema(db)
        identity = read_ledger_instance_id(db)
        for sql in (
            "UPDATE ledger_instance_metadata SET origin=origin",
            "DELETE FROM ledger_instance_metadata",
            "INSERT OR REPLACE INTO ledger_instance_metadata SELECT * FROM ledger_instance_metadata",
            "INSERT INTO ledger_instance_metadata SELECT * FROM ledger_instance_metadata",
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql)
            db.rollback()
            self.assertEqual(read_ledger_instance_id(db), identity)
        db.close()

    def test_missing_identity_fails_closed_and_is_not_repaired(self):
        db = connect()
        initialize_schema(db)
        # Simulate corruption out of band, restore DDL so the row check is tested.
        ddl = db.execute("SELECT sql FROM sqlite_schema WHERE name='ledger_instance_metadata_no_delete'").fetchone()[0]
        db.execute("DROP TRIGGER ledger_instance_metadata_no_delete")
        db.execute("DELETE FROM ledger_instance_metadata")
        db.execute(ddl)
        db.commit()
        for operation in (initialize_schema, verify_runtime_schema, verify_schema):
            with self.assertRaisesRegex(SpineValidationError, "ledger_instance_invalid"):
                operation(db)
        with self.assertRaisesRegex(SpineValidationError, "ledger_instance_invalid"):
            migrate_schema(db, verify=False)
        response = handle("system.info", {}, CommandContext(ledger=db))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["field"], "ledger_instance_id")
        health, events, resolver = Mock(), Mock(), Mock()
        result = admit_worker(db, config=WorkerBootstrapConfig(), health_sink=health,
                              event_sink=events, dependency_resolver=resolver)
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(result.cycles_completed, 0)
        self.assertEqual(events.emit.call_args.args[0]["reason"], "ledger_instance_invalid")
        resolver.assert_not_called()
        self.assertFalse(health.write.call_args.args[0].as_record()["is_ready"])
        db.close()

    def test_malformed_identity_rejected(self):
        db = connect()
        initialize_schema(db)
        db.execute("DROP TRIGGER ledger_instance_metadata_no_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ledger_instance_metadata SET ledger_instance_id='bad'")
        with self.assertRaisesRegex(SpineValidationError, "ledger_instance_invalid"):
            read_ledger_instance_id(db)
        db.close()

    def test_migration_failure_rolls_back_ddl_row_and_schema_version(self):
        db = connect()
        schema13(db)
        expected = schema13_identity(db)
        with (
            patch("spine.ledger.identity.read_ledger_instance_id", side_effect=RuntimeError("injected")),
            self.assertRaisesRegex(RuntimeError, "injected"),
        ):
            install_identity(db, fresh=False, applied_at_utc="2026-09-07T00:00:00Z")
        self.assertIsNone(db.execute("SELECT 1 FROM sqlite_schema WHERE name='ledger_instance_metadata'").fetchone())
        self.assertEqual(db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0], 13)
        migrate_schema(db)
        self.assertEqual(read_ledger_instance_id(db), expected)
        db.close()

    def test_routine_admission_never_backfills(self):
        db = connect()
        initialize_schema(db)
        statements = []
        db.set_trace_callback(statements.append)
        changes = db.total_changes
        with patch("spine.ledger.identity.schema13_identity", side_effect=AssertionError("deep scan")):
            verify_runtime_schema(db)
            initialize_schema(db)
            self.assertEqual(read_ledger_instance_id(db), read_ledger_instance_id(db))
        self.assertEqual(db.total_changes, changes)
        self.assertFalse(any("SELECT" in s.upper() and "FROM coordination_items" in s for s in statements))
        self.assertTrue(any("ledger_instance_metadata LIMIT 2" in s for s in statements))
        db.close()

    def test_v3_contract_requires_identity_and_v2_stays_frozen(self):
        import json
        root = Path(__file__).resolve().parents[1] / "contracts/schemas"
        v3 = json.loads((root / "system-info-response-v3.schema.json").read_text())
        self.assertIn("ledger_instance_id", v3["required"])
        Draft202012Validator.check_schema(v3)
        v2 = json.loads((root / "system-info-response-v2.schema.json").read_text())
        self.assertNotIn("ledger_instance_id", v2["properties"])


if __name__ == "__main__":
    unittest.main()
