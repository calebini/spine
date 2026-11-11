"""RF2: closed mutation ownership, SQL/Python rollback and connection reuse."""

from __future__ import annotations

import ast
import sqlite3
import unittest
from contextlib import ExitStack
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.transactions import LedgerConnection


def mark(state: TransactionMutationState, label: str) -> None:
    state.ownership.epoch_consumed = True
    state.recurring.rows.add(("root", label, None))
    state.renderings.pending[label] = {"kind": "ordinary", "nested": {"values": [label]}}
    state.renderings.versions.add((label, 1))
    state.renderings.catalog.add(("root", label))
    state.renderings.profiles.add(label)
    state.renderings.attempts.add(label)
    state.facets.versions.add((label, 1))
    state.facets.allocations.add((label, 1))
    state.facets.roots.add(label)
    state.facets.items.add(label)
    state.facets.bindings.add(label)
    state.facets.definitions.add(label)


class TransactionMutationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE value_for_test(value INTEGER PRIMARY KEY)")
        self.db.execute("CREATE TABLE child_for_test(value INTEGER REFERENCES value_for_test DEFERRABLE INITIALLY DEFERRED)")

    def assert_empty(self) -> None:
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())
        self.assertFalse(self.db._command_transaction)
        self.assertFalse(self.db._command_write)

    def test_closed_registration_covers_every_declared_obligation(self) -> None:
        state = self.db.mutation_state
        expected = {
            "ownership": {"epoch_consumed"},
            "recurring": {"rows"},
            "renderings": {"pending", "versions", "catalog", "profiles", "attempts"},
            "facets": {"versions", "allocations", "roots", "items", "bindings", "definitions"},
        }
        self.assertEqual([f.name for f in fields(state)], list(expected))
        self.assertEqual(state._components(), tuple(getattr(state, k) for k in expected))
        for name, members in expected.items():
            self.assertEqual({f.name for f in fields(getattr(state, name))}, members)
        with self.assertRaises(AttributeError):
            state.unregistered = set()
        # Connection feature/authority/producer flags cannot enter checkpoints.
        for name in ("_facets_enabled", "_renderings_enabled", "_recurring_tasks_enabled", "_facet_producer", "_allow_commit"):
            self.assertFalse(hasattr(state, name))

    def test_deep_checkpoints_and_reset_keep_component_container_identity(self) -> None:
        state = self.db.mutation_state
        mark(state, "accepted")
        snapshot = state.checkpoint()
        components = state._components()
        containers = [(component, f.name, getattr(component, f.name)) for component in components
                      for f in fields(component) if isinstance(getattr(component, f.name), (set, dict))]
        mark(state, "trial")
        state.renderings.pending["accepted"]["nested"]["values"].append("changed")
        self.assertEqual(snapshot.renderings.pending["accepted"]["nested"]["values"], ["accepted"])
        state.restore(snapshot)
        self.assertEqual(state, snapshot)
        for left, right in zip(components, state._components(), strict=True):
            self.assertIs(left, right)
        for component, name, value in containers:
            self.assertIs(getattr(component, name), value)
        state.renderings.pending["accepted"]["nested"]["values"].append("again")
        self.assertEqual(snapshot.renderings.pending["accepted"]["nested"]["values"], ["accepted"])
        state.reset()
        self.assertEqual(state, TransactionMutationState())
        self.assertTrue(snapshot.ownership.epoch_consumed)
        with self.assertRaises(TypeError):
            state.facets.restore(snapshot.renderings)

    def test_connections_never_share_state(self) -> None:
        other = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(other.close)
        mark(self.db.mutation_state, "first")
        self.assertEqual(other.mutation_state, TransactionMutationState())

    def test_nested_rollback_preserves_previous_units_and_epoch_consumption(self) -> None:
        state = self.db.mutation_state
        with self.db.atomic_command():
            mark(state, "accepted")
            self.db.execute("INSERT INTO value_for_test VALUES(1)")
            accepted = state.checkpoint()
            with self.assertRaisesRegex(RuntimeError, "outer trial"), self.db.command_unit():
                mark(state, "outer")
                self.db.execute("INSERT INTO value_for_test VALUES(2)")
                outer = state.checkpoint()
                with self.assertRaisesRegex(RuntimeError, "inner trial"), self.db.command_unit(nested=True):
                    mark(state, "inner")
                    state.renderings.pending["accepted"]["nested"]["values"].append("leak")
                    self.db.execute("INSERT INTO value_for_test VALUES(3)")
                    raise RuntimeError("inner trial")
                self.assertEqual(state, outer)
                self.assertEqual(self.db._command_unit_depth, 1)
                with self.db.command_unit(nested=True):
                    mark(state, "inner-success")
                    self.db.execute("INSERT INTO value_for_test VALUES(4)")
                raise RuntimeError("outer trial")
            self.assertEqual(state, accepted)
            self.assertTrue(state.ownership.epoch_consumed)
            self.assertEqual(self.db._command_unit_depth, 0)
            self.assertFalse(self.db._command_unit_active)
            self.assertEqual(self.db.execute("SELECT value FROM value_for_test").fetchall(), [(1,)])
        self.assert_empty()
        self.assertIs(self.db.mutation_state, state)
        self.assertEqual(self.db.execute("SELECT value FROM value_for_test").fetchall(), [(1,)])

    def test_all_transaction_exit_paths_clear_even_without_enabled_features(self) -> None:
        for mode in ("commit", "rollback", "context", "context-fail", "atomic", "atomic-fail"):
            with self.subTest(mode=mode):
                if mode.startswith("atomic"):
                    try:
                        with self.db.atomic_command():
                            mark(self.db.mutation_state, mode)
                            if mode.endswith("fail"):
                                raise RuntimeError("test")
                    except RuntimeError:
                        self.assertTrue(mode.endswith("fail"))
                else:
                    mark(self.db.mutation_state, mode)
                    if mode in {"commit", "rollback"}:
                        getattr(self.db, mode)()
                    else:
                        try:
                            with self.db:
                                if mode.endswith("fail"):
                                    raise RuntimeError("test")
                        except RuntimeError:
                            self.assertTrue(mode.endswith("fail"))
                self.assert_empty()

    def test_deferred_commit_failure_clears_obligations_and_reuses_connection(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            mark(self.db.mutation_state, "failed")
            self.db.execute("INSERT INTO child_for_test VALUES(99)")
        self.assert_empty()
        self.assertEqual(self.db.execute("SELECT * FROM child_for_test").fetchall(), [])
        with self.db.atomic_command():
            self.db.execute("INSERT INTO value_for_test VALUES(99)")
            self.db.execute("INSERT INTO child_for_test VALUES(99)")
        self.assert_empty()

    def enable_mock_finalizers(self) -> None:
        # Isolate finalizer orchestration; real feature triggers/proofs are covered
        # by the facet/rendering/recurring storage and response-witness suites.
        self.db._recurring_tasks_enabled = True
        self.db._renderings_enabled = True
        self.db._facets_enabled = True
        self.db._allow_commit = False
        self.db._facet_producer = None

    def test_finalizers_run_in_dependency_order_and_share_live_state(self) -> None:
        self.enable_mock_finalizers()
        calls = []

        def recurring(db, rows):
            calls.append("recurring")
            self.assertIs(db, self.db)
            self.assertEqual(rows, frozenset({("root", "accepted", None)}))

        def rendering(db):
            calls.append("rendering")
            db.mutation_state.facets.items.add("rendering-added")

        def facets(db, *proof):
            calls.append("facets")
            self.assertIn("rendering-added", proof[1])
            return proof

        with (patch("spine.ledger.recurring_tasks.finalize", side_effect=recurring),
              patch("spine.ledger.rendering_definitions.finalize", side_effect=rendering),
              patch("spine.ledger.facets.finalize", side_effect=facets), self.db.atomic_command()):
            mark(self.db.mutation_state, "accepted")
        self.assertEqual(calls, ["recurring", "rendering", "facets"])
        self.assert_empty()
        self.assertTrue(self.db._facets_enabled)
        self.assertTrue(self.db._renderings_enabled)
        self.assertTrue(self.db._recurring_tasks_enabled)
        self.assertIsNone(self.db._facet_producer)
        self.assertFalse(self.db._allow_commit)

    def test_finalizer_failure_at_each_component_rolls_back_sql_and_state(self) -> None:
        self.enable_mock_finalizers()
        names = ("recurring_tasks", "rendering_definitions", "facets")
        for failing in names:
            with self.subTest(failing=failing), ExitStack() as stack:
                calls = []
                error = RuntimeError(failing)

                def finalizer(name, calls=calls, failing=failing, error=error):
                    def run(db, *args):
                        calls.append(name)
                        db.execute("INSERT INTO value_for_test VALUES(?)", (len(calls),))
                        mark(db.mutation_state, name)
                        if name == failing:
                            raise error
                        return args
                    return run

                for name in names:
                    stack.enter_context(patch(f"spine.ledger.{name}.finalize", side_effect=finalizer(name)))
                with self.assertRaises(RuntimeError) as caught, self.db.atomic_command():
                    mark(self.db.mutation_state, "initial")
                self.assertIs(caught.exception, error)
                self.assertEqual(calls, list(names[:names.index(failing) + 1]))
                self.assertEqual(self.db.execute("SELECT * FROM value_for_test").fetchall(), [])
                self.assert_empty()
                self.assertFalse(self.db._allow_commit)

    def test_facet_allocation_and_exact_proof_checks_are_preserved(self) -> None:
        self.db._facets_enabled = True
        self.db._allow_commit = False
        with patch("spine.ledger.facets.finalize", return_value=()) as finalize:
            with self.assertRaisesRegex(SpineValidationError, "unfinalized item version"), self.db.atomic_command():
                self.db.mutation_state.facets.allocations.add(("orphan", 1))
            finalize.assert_not_called()
            self.assert_empty()
            with self.assertRaisesRegex(SpineValidationError, "facet finalization incomplete"), self.db.atomic_command():
                pass
            finalize.assert_called_once()
            self.assert_empty()

    def test_interruption_clears_state_without_masking_sqlite_error(self) -> None:
        with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"), self.db.atomic_command():
            mark(self.db.mutation_state, "accepted")
            self.db.execute("INSERT INTO value_for_test VALUES(1)")
            try:
                with self.db.command_unit(), self.db.command_unit(nested=True):
                    mark(self.db.mutation_state, "trial")
                    # Interrupt after the write VM has inserted rows, not during
                    # statement preparation (which can leave the transaction live).
                    self.db.set_progress_handler(lambda: 1, 1000)
                    try:
                        self.db.execute("WITH RECURSIVE n(v) AS (VALUES(2) UNION ALL SELECT v+1 FROM n WHERE v<10000) "
                                        "INSERT INTO value_for_test SELECT v FROM n")
                    finally:
                        self.db.set_progress_handler(None, 0)
            except sqlite3.OperationalError:
                self.assertFalse(self.db.in_transaction)
                self.assertEqual(self.db.mutation_state, TransactionMutationState())
                with self.assertRaisesRegex(RuntimeError, "owning command"), self.db.command_unit():
                    pass
                raise
        self.assert_empty()
        self.assertEqual(self.db.execute("SELECT * FROM value_for_test").fetchall(), [])
        with self.db.atomic_command():
            self.db.execute("INSERT INTO value_for_test VALUES(3)")
        self.assert_empty()

    def test_no_parallel_legacy_connection_trackers_remain(self) -> None:
        removed = {"_ownership_epoch_consumed", "_recurring_task_rows"}
        removed.update("_rendering_" + name for name in ("pending", "versions", "catalog", "profiles", "attempts"))
        removed.update("_facet_" + name for name in ("versions", "allocations", "roots", "items", "bindings", "definitions"))
        root = Path(__file__).resolve().parents[1] / "src/spine"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, removed, f"{path}:{node.lineno}")
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in {"getattr", "setattr", "hasattr"}
                        and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)):
                    self.assertNotIn(node.args[1].value, removed, f"{path}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
