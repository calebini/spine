"""FS-14: real storage, cutover, history and serialized location/facet writes."""

import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger import connect, facets
from spine.ledger.facet_location_migration import install_facet_location_freeze
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.ledger.preflight import current_schema_version, verify_runtime_schema
from tests import test_facet_storage as storage_tests
from tests.facet_storage_support import DEFINITION, NOW, all_rows, receipt


class FacetLocationFreezeTests(unittest.TestCase):
    def seed(self, *, predecessor=False):
        h = storage_tests.FacetStorageTests()
        if predecessor:
            with patch("spine.ledger.facet_location_migration.install_facet_location_freeze"):
                h.setUp()
        else:
            h.setUp()
        self.addCleanup(h.tearDown)
        definition = copy.deepcopy(DEFINITION)
        next(field for field in definition["fields"] if field["key"] == "airport")["queryable"] = False
        with patch("tests.facet_storage_support.DEFINITION", definition):
            h.create()
        with h.db:
            h.db.execute(
                "INSERT INTO locations(location_id,label,kind,created_at_utc,updated_at_utc) VALUES ('airport','Original','place',?,?)",
                (NOW, NOW),
            )
        return h

    def attach(self, h, location="airport"):
        # Caller owns the transaction so lock-interleaving tests exercise the real finalizer.
        version = h.db.execute("SELECT current_version FROM coordination_items WHERE item_id='task'").fetchone()[0]
        entry = facets.prepare_entry(
            h.db, item_id="task", item_version=version, binding_id="binding0",
            values={"flight": "AC123", "airport": location}, receipt_id=receipt(h.db, f"attach-{version}"),
        )
        h.next(facet_entries=[entry])

    def objects(self, db):
        return [tuple(r) for r in db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name")]

    def test_nonqueryable_facet_history_freezes_all_canonical_fields_and_allows_metadata(self):
        h = self.seed()
        with h.db.atomic_command():
            self.attach(h)
        self.assertEqual(h.db.execute("SELECT count(*) FROM item_locations").fetchone()[0], 0)
        self.assertEqual(h.db.execute("SELECT count(*) FROM item_facet_references WHERE location_id='airport'").fetchone()[0], 1)
        for column in ("label", "kind", "address_text", "latitude", "longitude", "timezone", "provider_ref"):
            with self.subTest(column=column), self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"), h.db:
                h.db.execute(f"UPDATE locations SET {column}={column} WHERE location_id='airport'")
        with h.db:
            h.db.execute("UPDATE locations SET metadata_json='{}',updated_at_utc=? WHERE location_id='airport'", (NOW,))
        history = facets.load_snapshot(h.db, "task", 2)
        h.next(facet_entries=())
        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"), h.db:
            h.db.execute("UPDATE locations SET label='Changed' WHERE location_id='airport'")
        with h.db:
            h.db.execute(
                "INSERT INTO locations(location_id,label,kind,created_at_utc,updated_at_utc) "
                "VALUES ('new-airport','Corrected','place',?,?)",
                (NOW, NOW),
            )
        with h.db.atomic_command():
            self.attach(h, "new-airport")
        self.assertEqual(facets.load_snapshot(h.db, "task", 2), history)
        self.assertEqual(h.db.execute("SELECT label FROM locations WHERE location_id='airport'").fetchone()[0], "Original")
        verify_schema(h.db)

    def test_populated_cutover_preserves_every_row_backup_and_trigger_parity(self):
        h = self.seed(predecessor=True)
        with h.db.atomic_command():
            self.attach(h)
        # Reproduce the actual old gap, not a relabelled current database.
        with h.db:
            h.db.execute("UPDATE locations SET label='Cutover label' WHERE location_id='airport'")
            h.db.execute("CREATE INDEX local_location_label ON locations(label)")
        before = all_rows(h.db)
        backup = sqlite3.connect(":memory:")
        self.addCleanup(backup.close)
        h.db.backup(backup)
        with self.assertRaises(SpineValidationError):
            verify_runtime_schema(h.db)
        result = migrate_schema(h.db)
        self.assertEqual(result.applied_versions, (18,))
        for table, rows in before.items():
            if table != "ledger_schema":
                self.assertEqual(all_rows(h.db)[table], rows, table)
        self.assertEqual(h.db.execute("SELECT label FROM locations WHERE location_id='airport'").fetchone()[0], "Cutover label")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"), h.db:
            h.db.execute("UPDATE locations SET label='After' WHERE location_id='airport'")
        self.assertEqual(migrate_schema(h.db).applied_versions, ())
        with self.assertRaises(SpineValidationError):
            verify_runtime_schema(h.db, expected_version=17)
        fresh = self.seed()
        sql = "SELECT sql FROM sqlite_schema WHERE name='locations_referenced_canonical_fields_update'"
        self.assertEqual(h.db.execute(sql).fetchone()[0], fresh.db.execute(sql).fetchone()[0])
        backup.row_factory = sqlite3.Row
        self.assertEqual(current_schema_version(backup), 17)
        self.assertEqual(all_rows(backup), before)
        verify_runtime_schema(backup, expected_version=17)
        restored = sqlite3.connect(":memory:")
        self.addCleanup(restored.close)
        restored.row_factory = sqlite3.Row
        backup.backup(restored)
        self.assertEqual(all_rows(restored), before)
        verify_runtime_schema(restored, expected_version=17)

    def test_failed_attachment_does_not_leave_a_freeze_or_partial_version(self):
        h = self.seed()
        before = all_rows(h.db)
        with self.assertRaisesRegex(RuntimeError, "abort attachment"), h.db.atomic_command():
            self.attach(h)
            raise RuntimeError("abort attachment")
        self.assertEqual(all_rows(h.db), before)
        with h.db:
            h.db.execute("UPDATE locations SET label='Still unreferenced' WHERE location_id='airport'")
        verify_schema(h.db)

    def test_interruption_after_ddl_or_activation_rolls_back(self):
        for stage in ("create", "activate"):
            with self.subTest(stage=stage):
                h = self.seed(predecessor=True)
                with h.db.atomic_command():
                    self.attach(h)
                before, objects = all_rows(h.db), self.objects(h.db)
                if stage == "create":
                    def reject_create(action, *args):
                        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TRIGGER else sqlite3.SQLITE_OK
                    h.db.set_authorizer(reject_create)
                    with self.assertRaises(sqlite3.DatabaseError):
                        install_facet_location_freeze(h.db, applied_at_utc=NOW)
                    h.db.set_authorizer(h.db._authorize_commit)
                else:
                    def check(db, **kwargs):
                        if current_schema_version(db) == 18:
                            raise RuntimeError("injected activation failure")
                        return verify_runtime_schema(db, **kwargs)
                    with (
                        patch("spine.ledger.facet_location_migration.verify_runtime_schema", check),
                        self.assertRaisesRegex(RuntimeError, "injected"),
                    ):
                        install_facet_location_freeze(h.db, applied_at_utc=NOW)
                self.assertEqual(all_rows(h.db), before)
                self.assertEqual(self.objects(h.db), objects)
                self.assertFalse(h.db.in_transaction)
                self.assertEqual(h.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_trigger_drift_is_rejected_before_and_after_migration(self):
        for predecessor in (False, True):
            h = self.seed(predecessor=predecessor)
            with h.db:
                h.db.execute("DROP TRIGGER locations_referenced_canonical_fields_update")
                h.db.execute("CREATE TRIGGER locations_referenced_canonical_fields_update BEFORE UPDATE ON locations BEGIN SELECT 1; END")
            before = all_rows(h.db)
            with self.assertRaises(SpineValidationError):
                migrate_schema(h.db) if predecessor else verify_runtime_schema(h.db)
            self.assertEqual(all_rows(h.db), before)

    def test_indexed_lookup_and_two_connection_write_orders(self):
        for first in ("attachment", "update"):
            with self.subTest(first=first), tempfile.TemporaryDirectory() as directory:
                h = self.seed()
                path = Path(directory) / "ledger.sqlite"
                target = sqlite3.connect(path)
                h.db.backup(target)
                target.close()
                h.db.close()
                h.db = connect(path, busy_timeout_ms=0)
                other = connect(path, busy_timeout_ms=0)
                try:
                    if first == "attachment":
                        with h.db.atomic_command():
                            self.attach(h)
                            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"), other:
                                other.execute("UPDATE locations SET label='Raced' WHERE location_id='airport'")
                        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"), other:
                            other.execute("UPDATE locations SET label='Raced' WHERE location_id='airport'")
                    else:
                        with other:
                            other.execute("UPDATE locations SET label='Before attachment' WHERE location_id='airport'")
                            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"), h.db.atomic_command():
                                self.attach(h)
                        with h.db.atomic_command():
                            self.attach(h)
                        label = h.db.execute("SELECT label FROM locations WHERE location_id='airport'").fetchone()[0]
                        self.assertEqual(label, "Before attachment")
                    plan = " ".join(r[3] for r in h.db.execute(
                        "EXPLAIN QUERY PLAN SELECT 1 FROM item_facet_references WHERE location_id=?", ("airport",),
                    ))
                    self.assertIn("SEARCH", plan)
                    self.assertIn("item_facet_references_location_idx", plan)
                    verify_schema(h.db)
                finally:
                    other.close()
