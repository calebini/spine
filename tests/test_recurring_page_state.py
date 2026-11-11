"""RF2 page ownership: real SQL checkpoints, exact rollback and spent budgets."""

from __future__ import annotations

import ast
import sqlite3
import sys
import unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_operations import ChildWorkOverflow
from spine.services.recurring_task_page_state import PageBoundary, PageCheckpoint, PageState
from spine.services.recurring_task_reconcile import Page


class RecurringPageStateTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE writes(value TEXT)")
        self.runtime = {"audit_ids": [], "cutoffs": []}
        self.root = {"next_assignment_seq": 1, "nested": {"stable": True}}
        self.state = PageState(self.root, self.runtime)
        self.budget = ProofBudget(100, 20)
        # Exercise the real unit orchestration without irrelevant source expansion.
        self.page = Page.__new__(Page)
        self.page.db = self.db
        self.page.state = self.state
        self.page.budget = self.budget
        self.page.limits = {"mutations": 10, "work_rows": 10}
        self.selector = {"scheduled_fact": "2026-11-14T11:30:00", "segment_id": "segment"}

    def mutate(self, label):
        self.db.execute("INSERT INTO writes VALUES(?)", (label,))
        self.db.mutation_state.ownership.epoch_consumed = True
        self.db.mutation_state.recurring.rows.add(("root", label, None))
        self.db.mutation_state.renderings.pending[label] = {"kind": "ordinary"}
        self.db.mutation_state.facets.versions.add((label, 1))
        self.state.root["next_assignment_seq"] += 1
        self.state.runtime["audit_ids"].append(label)
        self.state.runtime["cutoffs"].append(label)
        self.state.work["created"].append(label)
        self.state.mappings.append({"policy": label})
        self.state.changed = self.state.owners = True
        self.state.mutations += 1
        self.budget.spend(3, hop=True)
        return {"outcome": label}

    def accept(self, label):
        result = self.page.unit(lambda: self.mutate(label), self.selector)
        self.state.results.append(result)
        self.state.position["after"] = label

    def values(self):
        return [r[0] for r in self.db.execute("SELECT value FROM writes")]

    def test_closed_checkpoint_excludes_execution_and_nonrefundable_budgets(self):
        self.assertEqual({f.name for f in fields(PageCheckpoint)}, {
            "root", "runtime", "work", "mappings", "changed", "owners", "mutations", "result_count", "position", "lane",
        })
        self.assertEqual({f.name for f in fields(PageState)}, {
            "root", "runtime", "work", "mappings", "changed", "owners", "mutations", "results", "position", "lane", "_units",
        })
        for name in ("budget", "clock", "context", "request", "db", "unit_oversized"):
            self.assertFalse(hasattr(self.state, name))

    def test_suffix_rollback_keeps_earlier_units_and_consumed_proof(self):
        initial = self.state.checkpoint()
        with self.db.atomic_command():
            self.accept("first")
            first = self.state.checkpoint()
            sql_state = self.db.mutation_state.checkpoint()
            result = self.state.results[0]
            mappings, position = self.state.mappings, self.state.position
            self.state.lane = "source"
            self.accept("second")
            self.accept("third")
            self.assertEqual((self.budget.steps, self.budget.hops), (91, 17))
            self.assertEqual(self.state.rollback_last(), "source")
            self.assertEqual(self.values(), ["first", "second"])
            self.assertEqual(self.state.position, {"after": "second"})
            self.assertEqual(self.state.rollback_last(), "source")
            # The second unit began in the source lane after the first accepted result.
            self.assertEqual(self.state.root, first.root)
            self.assertEqual(self.state.runtime, first.runtime)
            self.assertEqual(self.state.work, first.work)
            self.assertEqual(self.state.mutations, first.mutations)
            self.assertEqual(self.state.position, first.position)
            self.assertEqual(self.db.mutation_state, sql_state)
            self.assertEqual(self.values(), ["first"])
            self.assertIs(self.state.results[0], result)
            self.assertIs(self.state.mappings, mappings)
            self.assertIs(self.state.position, position)
            self.assertIs(self.state.root, self.root)
            self.assertIs(self.state.runtime, self.runtime)
            self.assertEqual((self.budget.steps, self.budget.hops), (91, 17))
            self.assertEqual(self.state.rollback_last(), "assignments")
            self.assertEqual(self.state.checkpoint(), initial)
            self.assertEqual(self.values(), [])
            self.assertFalse(self.state.has_units)
        self.assertEqual(self.db._command_unit_depth, 0)

    def test_projection_trial_restores_all_outputs_without_refunding_proof(self):
        with self.db.atomic_command():
            self.accept("accepted")
            checkpoint = self.state.checkpoint()
            sql_state = self.db.mutation_state.checkpoint()
            with self.assertRaises(PageBoundary), self.state.trial(self.db):
                self.mutate("projection")
                self.state.root["nested"]["stable"] = False
                self.state.position["after"] = "projection"
                self.state.results.append({"outcome": "projection"})
                raise PageBoundary()
            self.assertEqual(self.state.checkpoint(), checkpoint)
            self.assertEqual(self.db.mutation_state, sql_state)
            self.assertEqual(self.values(), ["accepted"])
            self.assertEqual((self.budget.steps, self.budget.hops), (94, 18))
            self.assertTrue(self.state.has_units)
            self.assertEqual(self.db._command_unit_depth, 1)
            # Successful projection releases its own scope, not the retained unit.
            with self.state.trial(self.db):
                self.db.execute("INSERT INTO writes VALUES('final')")
            self.assertEqual(self.db._command_unit_depth, 1)
            self.state.close((None, None, None))
            self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.values(), ["accepted", "final"])

    def test_wrong_order_and_foreign_units_fail_without_changing_stack(self):
        with self.db.atomic_command():
            first = self.state.begin_unit(self.db)
            self.mutate("first")
            second = self.state.begin_unit(self.db)
            self.mutate("second")
            error = (RuntimeError, RuntimeError("rollback"), None)
            with self.assertRaisesRegex(RuntimeError, "LIFO"):
                self.state.rollback(first, error)
            with self.assertRaisesRegex(RuntimeError, "LIFO"):
                PageState({}, {}).rollback(second, error)
            with self.assertRaises(ValueError):
                self.state.rollback(second, (None, None, None))
            self.assertEqual(self.values(), ["first", "second"])
            self.assertEqual(self.db._command_unit_depth, 2)
            self.state.close(error)
            self.assertEqual(self.values(), [])
            self.assertEqual(self.db._command_unit_depth, 0)

    def test_failed_unit_restores_python_and_sql_before_propagating(self):
        with self.db.atomic_command():
            self.accept("accepted")
            checkpoint = self.state.checkpoint()

            def operation():
                self.mutate("failed")
                raise RuntimeError("programming failure")

            with self.assertRaisesRegex(RuntimeError, "programming failure"):
                self.page.unit(operation, self.selector)
            self.assertEqual(self.state.checkpoint(), checkpoint)
            self.assertEqual(self.values(), ["accepted"])
            self.assertEqual(self.budget.steps, 94)
            self.state.close((None, None, None))
        self.assertEqual(self.values(), ["accepted"])

    def test_recovery_reference_failure_cannot_strand_an_entered_scope(self):
        initial = self.state.checkpoint()
        error = RuntimeError("reference lookup failed")
        with self.assertRaisesRegex(RuntimeError, "reference lookup failed"), self.db.atomic_command():
            self.accept("accepted")

            def operation():
                self.mutate("rejected")
                raise SpineValidationError("delivery_target_inactive", "route inactive")

            try:
                with patch("spine.services.recurring_task_reconcile.references", side_effect=error):
                    self.page.unit(operation, self.selector, assignment={"assignment_id": "assignment"})
            finally:
                self.state.close(sys.exc_info())
        self.assertEqual(self.state.checkpoint(), initial)
        self.assertFalse(self.state.has_units)
        self.assertEqual(self.values(), [])
        self.assertEqual(self.db._command_unit_depth, 0)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_recoverable_rejection_retains_only_decision_not_failed_mutations(self):
        with self.db.atomic_command():
            self.accept("accepted")

            def operation():
                self.mutate("rejected")
                raise SpineValidationError("delivery_target_inactive", "route inactive")

            decision = self.page.unit(operation, self.selector)
            self.assertEqual((decision["outcome"], decision["reason"]), ("decision_required", "route_unavailable"))
            self.state.results.append(decision)
            self.assertEqual(self.values(), ["accepted"])
            self.assertEqual(self.state.runtime["audit_ids"], ["accepted"])
            self.assertEqual(self.budget.steps, 94)
            self.assertEqual(self.state.rollback_last(), "assignments")
            self.assertEqual(len(self.state.results), 1)
            self.state.close((None, None, None))

    def test_work_and_mutation_boundaries_keep_prior_unit_without_budget_reset(self):
        for kind in ("work_rows", "mutations"):
            with self.subTest(kind=kind), self.db.atomic_command():
                self.page.limits[kind] = 1
                self.accept("accepted")
                checkpoint = self.state.checkpoint()
                result = self.page.unit(lambda: self.mutate("excess"), self.selector)
                self.assertIsNone(result)
                self.assertEqual(self.state.checkpoint(), checkpoint)
                self.assertEqual(self.values(), ["accepted"])
                self.assertEqual(self.budget.steps, 94)
                self.state.close((RuntimeError, RuntimeError("discard test"), None))
                self.page.limits[kind] = 10
                self.budget.steps, self.budget.hops = 100, 20

    def test_individually_oversized_signal_is_not_refunded_into_a_partial_page(self):
        with self.db.atomic_command():
            self.accept("accepted")

            def operation():
                self.mutate("too-large")
                self.page.unit_oversized = True
                raise SpineValidationError("capacity_exceeded:limits.work_rows", "one task is oversized")

            with self.assertRaisesRegex(SpineValidationError, "oversized"):
                self.page.unit(operation, self.selector)
            self.assertTrue(self.page.unit_oversized)
            self.assertEqual(self.values(), ["accepted"])
            self.state.close((None, None, None))

    def test_child_overflow_evidence_cannot_become_a_successful_prefix_page(self):
        initial = self.state.checkpoint()
        with self.assertRaises(ChildWorkOverflow), self.db.atomic_command():
            try:
                self.accept("accepted")

                def operation():
                    self.mutate("oversized-child")
                    raise ChildWorkOverflow()

                self.page.unit(operation, self.selector)
            finally:
                self.state.close(sys.exc_info())
        self.assertEqual(self.values(), [])
        self.assertEqual(self.state.checkpoint(), initial)
        self.assertEqual(self.budget.steps, 94)
        self.assertEqual(self.db._command_unit_depth, 0)

    def test_interrupt_unwinds_all_units_without_masking_original_error(self):
        initial = self.state.checkpoint()
        with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"), self.db.atomic_command():
            try:
                self.accept("accepted")

                def operation():
                    self.mutate("trial")
                    self.db.set_progress_handler(lambda: 1, 1000)
                    try:
                        self.db.execute("WITH RECURSIVE n(v) AS (VALUES(2) UNION ALL SELECT v+1 FROM n WHERE v<10000) "
                                        "INSERT INTO writes SELECT v FROM n")
                    finally:
                        self.db.set_progress_handler(None, 0)

                self.page.unit(operation, self.selector)
            finally:
                self.state.close(sys.exc_info())
        self.assertEqual(self.values(), [])
        self.assertEqual(self.state.checkpoint(), initial)
        self.assertFalse(self.state.has_units)
        self.assertEqual(self.budget.steps, 94)
        self.assertEqual(self.db._command_unit_depth, 0)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_checkpoint_is_deep_and_failed_entry_does_not_register_a_unit(self):
        saved = self.state.checkpoint()
        self.state.root["nested"]["stable"] = False
        self.state.restore(saved)
        self.assertTrue(self.state.root["nested"]["stable"])
        self.state.root["nested"]["stable"] = False
        self.assertTrue(saved.root["nested"]["stable"])
        with self.assertRaisesRegex(RuntimeError, "owning command"):
            self.state.begin_unit(self.db)
        self.assertFalse(self.state.has_units)

    def test_page_data_has_one_owner_and_no_budget_inside_snapshot(self):
        root = Path(__file__).resolve().parents[1] / "src/spine/services"
        moved = {"root", "runtime", "results", "work", "mappings", "changed", "owners", "mutations", "position", "lane", "units"}
        for name in ("recurring_task_reconcile.py", "recurring_task_children.py", "recurring_task_adoption.py"):
            tree = ast.parse((root / name).read_text())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id in {"page", "self"}):
                    self.assertNotIn(node.attr, moved, f"{name}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
