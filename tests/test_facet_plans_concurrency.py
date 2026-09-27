"""Storage-specific scale and real SQLite lock/snapshot proofs, not a general soak."""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.ledger import ItemVersionDraft, connect, create_item_version_from_draft, create_task_v1, facets, initialize_schema
from spine.ledger.preflight import verify_runtime_schema
from tests.facet_storage_support import DEFINITION, NOW, receipt, seeded_snapshot


class FacetPlansConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "ledger.sqlite"
        self.db = connect(self.path)
        initialize_schema(self.db)
        handle(
            "subject.upsert",
            {
                "command_id": "owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": NOW,
            },
            CommandContext(ledger=self.db),
        )
        with patch("spine.ledger.items.insert_snapshot", seeded_snapshot):
            create_task_v1(self.db, item_id="task", title="Flight", created_at_utc=NOW, created_by_subject_id="owner")

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def measured_probe(self):
        steps = 0
        statements = []

        def progress():
            nonlocal steps
            steps += 1
            return steps >= 100000

        self.db.set_trace_callback(statements.append)
        self.db.set_progress_handler(progress, 1)
        try:
            self.assertTrue(facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="flight", value="AC123"))
            self.assertTrue(facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="seats", value="2"))
        finally:
            self.db.set_progress_handler(None, 0)
            self.db.set_trace_callback(None)
        plans = [r[3] for sql in statements if sql.startswith("SELECT") for r in self.db.execute("EXPLAIN QUERY PLAN " + sql)]
        self.assertTrue(any("item_facet_current_text_idx" in p and "SEARCH" in p for p in plans), plans)
        self.assertTrue(any("item_facet_current_integer_idx" in p and "SEARCH" in p for p in plans), plans)
        self.assertFalse(any("SCAN" in p or "TEMP B-TREE" in p for p in plans), plans)
        return steps

    def test_candidate_rooted_plan_with_100000_unrelated_owner_items_and_history(self):
        small = self.measured_probe()
        # Explicit offline fixture loader. No production command batches 100000 items.
        raw = sqlite3.connect(self.path)
        raw.execute("PRAGMA foreign_keys=ON")
        try:
            with raw:
                raw.execute("INSERT INTO subjects VALUES ('other','person','Other','active',?,?)", (NOW, NOW))
                raw.executemany(
                    "INSERT INTO coordination_items (item_id,item_type,current_version,status,created_at_utc,updated_at_utc) "
                    "VALUES (?,'task',1,'active',?,?)",
                    ((f"other{i}", NOW, NOW) for i in range(100000)),
                )
                raw.execute(
                    "INSERT INTO coordination_item_versions SELECT item_id,1,'Other',NULL,?, ?,NULL,?,'other' "
                    "FROM coordination_items WHERE item_id LIKE 'other%'",
                    ("0" * 64, "1" * 64, NOW),
                )
                raw.execute(
                    "INSERT INTO task_details (item_id,version,task_status) SELECT item_id,1,'open' "
                    "FROM coordination_items WHERE item_id LIKE 'other%'"
                )
                raw.execute(
                    "INSERT INTO item_subject_roles (item_subject_role_id,item_id,version,subject_id,role,status,created_at_utc) "
                    "SELECT item_id,item_id,1,'other','owner','active',? FROM coordination_items WHERE item_id LIKE 'other%'",
                    (NOW,),
                )
                raw.execute(
                    "INSERT INTO item_archetype_assignments SELECT 'assignment-'||i.item_id,i.item_id,1,a.item_archetype_id,"
                    "a.item_archetype_revision_id,a.selection_source,NULL,'other','fixture',? "
                    "FROM coordination_items i CROSS JOIN item_archetype_assignments a "
                    "WHERE i.item_id LIKE 'other%' AND a.item_id='task' AND a.item_version=1",
                    (NOW,),
                )
                raw.execute("INSERT INTO item_facet_snapshots SELECT item_id,1,1,29 FROM coordination_items WHERE item_id LIKE 'other%'")
                raw.execute(
                    "INSERT INTO item_facet_entries SELECT i.item_id,1,e.facet_key,e.facet_schema_revision_id,e.facet_binding_id,"
                    "e.item_archetype_id,e.item_archetype_revision_id,e.archetype_selection_source,e.archetype_source_ref,"
                    'e.value_contract_version,\'{"flight":"ZZ1"}\',e.source_command_receipt_id FROM coordination_items i '
                    "CROSS JOIN item_facet_entries e WHERE i.item_id LIKE 'other%' "
                    "AND e.item_id='task' AND e.item_version=1 AND e.facet_key='details0'"
                )
                raw.execute(
                    "INSERT INTO item_facet_current_values SELECT item_id,'details0','flight',1,'revision','text',1,'ZZ1',NULL "
                    "FROM coordination_items WHERE item_id LIKE 'other%'"
                )
                raw.executemany(
                    "INSERT INTO coordination_item_versions VALUES ('other0',?,'History',NULL,?,?,NULL,?,'other')",
                    ((v, "0" * 64, "1" * 64, NOW) for v in range(2, 10002)),
                )
                raw.execute(
                    "INSERT INTO task_details (item_id,version,task_status) SELECT item_id,version,'open' "
                    "FROM coordination_item_versions WHERE item_id='other0' AND version>1"
                )
                raw.execute(
                    "INSERT INTO item_facet_snapshots SELECT item_id,version,0,2 "
                    "FROM coordination_item_versions WHERE item_id='other0' AND version>1"
                )
                raw.execute("UPDATE coordination_items SET current_version=10001 WHERE item_id='other0'")
                raw.execute("DELETE FROM item_facet_current_values WHERE item_id='other0'")
                raw.execute("INSERT INTO item_access_owners SELECT item_id,'own-'||item_id,1,'subject',"
                            "CASE WHEN item_id='task' THEN 'owner' ELSE 'other' END,NULL,NULL,'fixture' FROM coordination_items")
                raw.execute("INSERT INTO item_access_owner_revisions SELECT item_id,item_access_owner_id,1,owner_kind,"
                            "owner_subject_id,NULL,NULL,'fixture',?,'owner',(SELECT command_receipt_id FROM command_receipts LIMIT 1) "
                            "FROM item_access_owners", (NOW,))
            self.assertEqual(raw.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            raw.close()
        large = self.measured_probe()
        self.assertLessEqual(large, small + 30)
        self.assertLess(large, 3000)
        from spine.commands.facet_runtime import FacetCursorConfig
        statements = []
        self.db.set_trace_callback(statements.append)
        try:
            response = handle("item.facets.query", {
                "contract_version": "spine.item-facet-query.v1", "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "facet_schema_revision_id": "revision", "field": "flight", "value": "AC123"},
                CommandContext(ledger=self.db, facet_cursor_config=FacetCursorConfig(b"a" * 32, "ledger", "generation")))
        finally:
            self.db.set_trace_callback(None)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["items"], [{"item_id": "task", "item_version": "1"}])
        public_plans = [r[3] for sql in statements if sql.startswith("SELECT") for r in self.db.execute("EXPLAIN QUERY PLAN " + sql)]
        self.assertTrue(any("item_access_owners_subject" in p and "SEARCH" in p for p in public_plans), public_plans)
        self.assertTrue(any("item_facet_current_text_idx" in p and "SEARCH" in p for p in public_plans), public_plans)
        self.assertFalse(any("SCAN item_facet" in p or "json_" in p for p in public_plans), public_plans)
        # Fail a deliberately tiny VM budget without inventing a partial match.
        before = self.db.total_changes
        self.db.set_progress_handler(lambda: 1, 1)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="flight", value="AC123")
        finally:
            self.db.set_progress_handler(None, 0)
        self.assertEqual(self.db.total_changes, before)

    def test_real_writer_lock_and_snapshot_consistency(self):
        acquired, attempted = threading.Event(), threading.Event()
        result = []

        def stale_writer():
            db = connect(self.path, busy_timeout_ms=100)
            try:
                attempted.set()
                with db.atomic_command():
                    acquired.set()
            except sqlite3.OperationalError as exc:
                result.append(str(exc))
            finally:
                db.close()

        with self.db.atomic_command():
            thread = threading.Thread(target=stale_writer)
            thread.start()
            self.assertTrue(attempted.wait(5))
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertFalse(acquired.is_set())
            self.assertIn("locked", result[0])
        reader = connect(self.path)
        try:
            with reader.atomic_command(write=False):
                self.assertEqual(len(facets.load_snapshot(reader, "task", 1)), 8)
                create_item_version_from_draft(
                    self.db,
                    ItemVersionDraft(
                        item_id="task",
                        target_version=1,
                        title="Updated",
                        created_at_utc=NOW,
                        created_by_subject_id="owner",
                        facet_entries=(),
                    ),
                )
                facets.validate_current(reader, "task")
                self.assertEqual(reader.execute("SELECT current_version FROM coordination_items WHERE item_id='task'").fetchone()[0], 1)
            self.assertEqual(reader.execute("SELECT current_version FROM coordination_items WHERE item_id='task'").fetchone()[0], 2)
            self.assertEqual(facets.load_snapshot(reader, "task", 2), [])
            with self.assertRaises(SpineValidationError):
                create_item_version_from_draft(
                    reader, ItemVersionDraft(item_id="task", target_version=1, created_at_utc=NOW, created_by_subject_id="owner")
                )
        finally:
            reader.close()

    def test_competing_publish_and_binding_writes_recheck_under_lock(self):
        other = connect(self.path)
        try:
            with self.db.atomic_command():
                rid = receipt(self.db, "publish1")
                facets.insert_revision(
                    self.db,
                    schema_id="schema",
                    revision_id="revision2",
                    definition=DEFINITION,
                    receipt_id=rid,
                    expected_revision_id="revision",
                )
            with self.assertRaises(SpineValidationError), other.atomic_command():
                facets.insert_revision(
                    other,
                    schema_id="schema",
                    revision_id="revision3",
                    definition=DEFINITION,
                    receipt_id=receipt(other, "publish2"),
                    expected_revision_id="revision",
                )
            archetype = self.db.execute("SELECT item_archetype_id FROM archetype_facet_bindings LIMIT 1").fetchone()[0]
            with self.db.atomic_command():
                facets.set_binding(
                    self.db,
                    binding_id="replacement",
                    archetype_id=archetype,
                    facet_key="details0",
                    revision_id="revision2",
                    expected_binding_id="binding0",
                    receipt_id=receipt(self.db, "bind1"),
                )
            with self.assertRaises(SpineValidationError), other.atomic_command():
                facets.set_binding(
                    other,
                    binding_id="loser",
                    archetype_id=archetype,
                    facet_key="details0",
                    revision_id="revision2",
                    expected_binding_id="binding0",
                    receipt_id=receipt(other, "bind2"),
                )
            self.assertIsNone(other.execute("SELECT 1 FROM command_receipts WHERE command_id IN ('publish2','bind2')").fetchone())
        finally:
            other.close()

    def test_index_cannot_repair_corrupt_canonical_definition(self):
        before = [tuple(r) for r in self.db.execute("SELECT * FROM item_facet_current_values ORDER BY item_id,facet_key,field_key")]
        raw = sqlite3.connect(self.path)
        try:
            with raw:
                trigger = raw.execute("SELECT sql FROM sqlite_schema WHERE name='facet_schema_revisions_immutable_update'").fetchone()[0]
                raw.execute("DROP TRIGGER facet_schema_revisions_immutable_update")
                raw.execute("UPDATE facet_schema_revisions SET definition_json=' '||definition_json")
                raw.execute(trigger)
        finally:
            raw.close()
        verify_runtime_schema(self.db)  # bounded schema check, never data repair
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            facets.rebuild_current_index(self.db, "task")
        self.assertEqual(
            before, [tuple(r) for r in self.db.execute("SELECT * FROM item_facet_current_values ORDER BY item_id,facet_key,field_key")]
        )

    def test_subject_inactivation_and_schema_retirement_win_before_fresh_set(self):
        other = connect(self.path)
        try:
            with other.atomic_command():
                other.execute("UPDATE subjects SET status='inactive' WHERE subject_id='owner'")
            with self.assertRaisesRegex(SpineValidationError, "facet_reference_unavailable"), self.db.atomic_command():
                facets.prepare_entry(
                    self.db,
                    item_id="task",
                    item_version=1,
                    binding_id="binding0",
                    values={"flight": "AC1", "person": "owner"},
                    receipt_id=receipt(self.db, "rejected-reference"),
                )
            with other.atomic_command():
                facets.retire_schema(other, schema_id="schema", expected_revision_id="revision", receipt_id=receipt(other, "retired"))
            with self.assertRaisesRegex(SpineValidationError, "facet_schema_retired"), self.db.atomic_command():
                facets.prepare_entry(
                    self.db,
                    item_id="task",
                    item_version=1,
                    binding_id="binding0",
                    values={"flight": "AC1"},
                    receipt_id=receipt(self.db, "rejected-catalog"),
                )
            facets.validate_current(self.db, "task")
            self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id LIKE 'rejected-%'").fetchone())
        finally:
            other.close()
