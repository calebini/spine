"""R3 invalidation: actual writers, rollback, bounded lookup and stale-page CAS."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.ledger import connect, items
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.recurring_task_catalog import catalog
from spine.ledger.recurring_task_invalidation import DirtyReason, acknowledge, mark
from spine.ledger.recurring_task_migration import attach_candidate
from spine.ledger.temporal_bindings import retire_temporal_binding
from spine.services import mutation_propagation
from tests import test_recurring_task_reconcile as helpers


def dump(db):
    return '\n'.join(db.iterdump())


class RecurringInvalidationTests(unittest.TestCase):
    def setUp(self):
        helpers.RecurringTaskReconcileTests.setUpClass()
        self.h = helpers.RecurringTaskReconcileTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.rule = self.h.created()["result"]["rule"]
        self.identity = self.rule["related_task_rule_id"]

    def dirty(self, db=None):
        row = (db or self.db).execute("SELECT * FROM related_task_dirty_rules WHERE related_task_rule_id=?",
                                    (self.identity,)).fetchone()
        return None if row is None else dict(row)

    def generate(self):
        return self.h.reconcile(self.rule)["result"]["results"][0]["after"]

    def test_source_item_and_recurrence_coalesce_without_child_fanout(self):
        self.generate()
        children = self.db.execute("SELECT item_id,current_version FROM coordination_items WHERE item_type='task'").fetchall()
        states = self.db.execute("SELECT * FROM related_task_assignment_revisions").fetchall()
        before = int(catalog(self.db))
        self.h.source_change()
        row = self.dirty()
        self.assertEqual((row["source_dirty"], row["target_dirty"], row["intent_dirty"]), (1, 0, 0))
        self.assertEqual(row["dirty_generation"], before + 1)
        self.assertEqual(int(catalog(self.db)), before + 1)
        self.assertEqual(self.db.execute(
            "SELECT item_id,current_version FROM coordination_items WHERE item_type='task'").fetchall(), children)
        self.assertEqual(self.db.execute("SELECT * FROM related_task_assignment_revisions").fetchall(), states)
        self.h.source_change()
        self.assertEqual(self.dirty()["dirty_generation"], before + 2)

    def test_target_edit_invalidates_old_expected_catalog_and_preserves_replay(self):
        child = self.generate()
        stale = self.h.write("reconcile", self.h.rule(self.identity), limits={})
        self.h.edit_task(child["task_item_id"], "Custom pickup")
        self.assertEqual(self.dirty()["target_dirty"], 1)
        refused = self.h.run_command("reconcile", stale)
        self.assertEqual((refused["error"]["code"], refused["error"]["field"]),
                         ("stale_version", "expected.catalog_generation"))
        fresh = self.h.write("reconcile", self.h.rule(self.identity), limits={})
        fresh["command_id"] = "refresh-child"
        self.assertTrue(self.h.run_command("reconcile", fresh)["ok"])
        self.h.edit_task(child["task_item_id"], "Another edit")
        before = dump(self.db)
        self.assertTrue(self.h.run_command("reconcile", fresh)["ok"])
        self.assertEqual(dump(self.db), before)

    def test_source_fanout_queues_roots_without_creating_assignments(self):
        second = self.h.created("second-pickup")["result"]["rule"]["related_task_rule_id"]
        before = int(catalog(self.db))
        self.h.source_change()
        rows = self.db.execute("SELECT related_task_rule_id,dirty_generation FROM related_task_dirty_rules").fetchall()
        self.assertEqual({r[0] for r in rows}, {self.identity, second})
        self.assertEqual({r[1] for r in rows}, {before + 1})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_assignments").fetchone()[0], 0)

    def test_public_preview_rolls_back_invalidation_and_replay_adds_nothing(self):
        request = dict(command_id="r3-cancel-source", actor_subject_id="owner", item_id=self.h.event["item_id"],
                       target_version="1", cancelled_at_utc=self.h.now)
        before = dump(self.db)
        preview = handle("event.cancel", request, replace(self.h.context, dry_run=True))
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(dump(self.db), before)
        actual = handle("event.cancel", request, self.h.context)
        self.assertTrue(actual["ok"], actual)
        self.assertEqual(self.dirty()["source_dirty"], 1)
        committed = dump(self.db)
        self.assertTrue(handle("event.cancel", request, self.h.context)["ok"])
        self.assertEqual(dump(self.db), committed)

    def test_standalone_native_item_helper_also_invalidates(self):
        child = self.generate()
        items.create_next_item_version(self.db, item_id=child["task_item_id"], target_version=1,
            title="Native edit", created_at_utc=self.h.now, created_by_subject_id="owner")
        self.assertEqual(self.dirty()["target_dirty"], 1)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_binding_retirement_invalidates_current_generation_only(self):
        child = self.generate()
        before = int(catalog(self.db))
        with self.db.atomic_command():
            retire_temporal_binding(self.db, temporal_binding_id=child["temporal_binding_id"],
                                    command_id="detach-r3", retired_at_utc=self.h.now)
            mutation_propagation.propagate(self.db, binding_id=child["temporal_binding_id"])
        self.assertEqual(self.dirty()["target_dirty"], 1)
        self.assertEqual(int(catalog(self.db)), before + 1)

    def test_merge_restart_and_once_per_transaction(self):
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.SOURCE)
            token = self.dirty()["dirty_generation"]
            changes = self.db.total_changes
            mark(self.db, self.identity, DirtyReason.SOURCE)
            self.assertEqual(self.db.total_changes, changes)
            mark(self.db, self.identity, DirtyReason.TARGET | DirtyReason.INTENT)
            self.assertEqual(self.dirty()["dirty_generation"], token)
            self.assertFalse(acknowledge(self.db, self.identity, token))
        with self.db.atomic_command():
            self.assertTrue(acknowledge(self.db, self.identity, token, assignment_after_seq=3))
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.TARGET)
        row = self.dirty()
        self.assertEqual((row["source_dirty"], row["target_dirty"], row["intent_dirty"], row["assignment_after_seq"]), (1, 1, 1, 0))
        self.assertGreater(row["dirty_generation"], token)

    def test_stale_cas_and_delete_reinsert_aba_never_lose_new_work(self):
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.SOURCE)
        old = self.dirty()["dirty_generation"]
        with self.db.atomic_command():
            self.assertTrue(acknowledge(self.db, self.identity, old))
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.TARGET)
        self.assertGreater(self.dirty()["dirty_generation"], old)
        before = dump(self.db)
        with self.db.atomic_command():
            self.assertFalse(acknowledge(self.db, self.identity, old))
            self.assertFalse(acknowledge(self.db, self.identity, old, assignment_after_seq=9))
        self.assertEqual(dump(self.db), before)

    def test_nested_and_outer_rollback_restore_catalog_queue_and_coalescing(self):
        before = dump(self.db)
        with self.assertRaisesRegex(RuntimeError, "outer"), self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.SOURCE)
            retained = self.dirty()
            with self.assertRaisesRegex(RuntimeError, "inner"), self.db.command_unit():
                mark(self.db, self.identity, DirtyReason.TARGET)
                raise RuntimeError("inner")
            self.assertEqual(self.dirty(), retained)
            self.assertEqual(self.db.mutation_state.recurring.invalidations[self.identity], int(DirtyReason.SOURCE))
            raise RuntimeError("outer")
        self.assertEqual(dump(self.db), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.TARGET)
        self.assertEqual(self.dirty()["source_dirty"], 0)

    def test_invalidation_failure_rolls_back_source_write(self):
        before = dump(self.db)
        with (patch("spine.ledger.recurring_task_invalidation.mark", side_effect=RuntimeError("dirty failure")),
              self.assertRaisesRegex(RuntimeError, "dirty failure")):
            self.h.source_change()
        self.assertEqual(dump(self.db), before)

    def test_unrelated_writer_and_repeated_read_do_not_touch_queue_or_catalog(self):
        before = int(catalog(self.db))
        result = handle("task.create", dict(command_id="unrelated-r3", actor_subject_id="owner",
            title="Independent task", created_at_utc=self.h.now), self.h.context)
        self.assertTrue(result["ok"], result)
        self.assertEqual(int(catalog(self.db)), before)
        self.assertIsNone(self.dirty())
        frozen = dump(self.db)
        for _ in range(3):
            self.h.rule(self.identity)
        self.assertEqual(dump(self.db), frozen)

    def test_cross_connection_old_page_cannot_clear_new_invalidation(self):
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            one = connect(Path(directory) / "test.sqlite")
            self.addCleanup(one.close)
            self.db.backup(one)
            attach_candidate(one)
            two = connect(Path(directory) / "test.sqlite")
            self.addCleanup(two.close)
            attach_candidate(two)
            old = self.dirty(one)["dirty_generation"]  # completed read-only planning
            with two.atomic_command():
                mark(two, self.identity, DirtyReason.TARGET)
            before = dump(two)
            with one.atomic_command():
                self.assertFalse(acknowledge(one, self.identity, old))
            self.assertEqual(dump(two), before)

    def test_indexed_source_and_target_plans_and_transaction_guard(self):
        with self.assertRaises(SpineValidationError):
            mark(self.db, self.identity, DirtyReason.SOURCE)
        queries = [
            ("SELECT related_task_rule_id FROM related_task_rules WHERE source_item_id=?", self.h.event["item_id"]),
            ("SELECT a.related_task_rule_id FROM related_task_generations g JOIN related_task_assignments a "
             "ON a.assignment_id=g.assignment_id WHERE g.task_item_id=? AND a.current_generation_id=g.generation_id", "unused"),
        ]
        for query, value in queries:
            plan = ' '.join(r[3] for r in self.db.execute("EXPLAIN QUERY PLAN " + query, (value,)))
            self.assertIn("SEARCH", plan)
            self.assertNotIn("SCAN", plan)
