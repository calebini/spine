"""RF3 relation composition, retained local helper and audit-trigger ownership."""

import ast
import re
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ChangeCategory
from spine.ledger import relations
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.temporal_bindings import binding_catalog_generation
from spine.ledger.transactions import LedgerConnection
from spine.services import mutation_propagation
from tests import test_binding_successor_materialization as bindings
from tests import test_ledger_supporting_sets as ledger
from tests import test_recurring_task_commands as recurring_base
from tests import test_recurring_task_reconcile as recurring


def dump(db):
    return "\n".join(db.iterdump())


class RelationPropagationTests(unittest.TestCase):
    def setUp(self):
        self.h = ledger.LedgerSupportingSetTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.connection
        ledger.create_task_pair(self.db)
        self.ctx = CommandContext(ledger=self.db)

    def request(self):
        return dict(command_id="relation-effect", actor_subject_id=ledger.SUBJECT_ID,
            source_item_id="task-dependent", source_target_version="1", target_item_id="task-prerequisite",
            target_target_version="1", relation_type="depends_on", created_at_utc=ledger.NOW)

    def native(self, identity="native", **kwargs):
        return relations.create_item_relation(self.db, relation_id=identity, source_item_id="task-dependent",
            target_item_id="task-prerequisite", relation_type="depends_on", created_at_utc=ledger.NOW,
            created_by_subject_id=ledger.SUBJECT_ID, **kwargs)

    def omit(self):
        original = mutation_propagation.propagate
        return patch.object(mutation_propagation, "propagate",
            side_effect=lambda *args, **kwargs: None if "relation_id" in kwargs else original(*args, **kwargs))

    def test_exact_effect_no_new_catalog_epoch_audit_or_work_and_replay_no_write(self):
        before = binding_catalog_generation(self.db)
        captured = []
        original = mutation_propagation.propagate

        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            captured.append(result)
            return result

        with patch.object(mutation_propagation, "propagate", side_effect=observe):
            response = handle("relation.create", self.request(), self.ctx)
        self.assertTrue(response["ok"], response)
        self.assertEqual(len(captured), 1)
        result = captured[0]
        self.assertEqual(result.bindings, ())
        self.assertEqual(result.owners, ())
        self.assertIsNone(result.ownership_epoch)
        effect = result.relations[0]
        self.assertIsNone(effect.before)
        self.assertEqual(effect.categories, {ChangeCategory.RELATION})
        self.assertEqual(effect.after, relations.relation_snapshot(self.db, effect.after.relation_id))
        self.assertEqual((effect.after.source_item_id, effect.after.target_item_id), ("task-dependent", "task-prerequisite"))
        self.assertEqual(binding_catalog_generation(self.db), before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit_log WHERE action='relation_created'").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 0)
        frozen = dump(self.db)
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("replay must not propagate")):
            self.assertTrue(handle("relation.create", self.request(), self.ctx)["ok"])
        self.assertEqual(dump(self.db), frozen)

    def test_bound_source_audit_trigger_is_the_only_relation_catalog_increment(self):
        h = bindings.BindingSuccessorMaterializationTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        created = h.create(materialize=False)
        before = binding_catalog_generation(h.db)
        request = self.request() | dict(actor_subject_id="owner", source_item_id=created["task"]["item_id"],
            target_item_id=h.h.event["item_id"])
        with patch.object(mutation_propagation, "increment_binding_catalog_generation", side_effect=AssertionError("SQL owns bump")):
            response = handle("relation.create", request, h.context)
        self.assertTrue(response["ok"], response)
        self.assertEqual(binding_catalog_generation(h.db), before + 1)

    def test_omitted_relation_propagation_rolls_back_all_three_composers(self):
        before = dump(self.db)
        with self.omit():
            result = handle("relation.create", self.request(), self.ctx)
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(self.db), before)
        h = bindings.BindingSuccessorMaterializationTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        before = dump(h.db)
        with self.omit():
            result = handle("schedule.related_task.create", h.h._related_request("follow_source"), h.context)
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(h.db), before)
        h = recurring.RecurringTaskReconcileTests()
        h.contracts = recurring_base.contracts()
        h.setUp()
        self.addCleanup(h.doCleanups)
        rule = h.created()["result"]["rule"]
        before = dump(h.db)
        with self.omit():
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(h.db), before)
        self.assertEqual(h.db.mutation_state, TransactionMutationState())

    def test_native_default_transaction_flag_cannot_bypass_composed_propagation(self):
        before = dump(self.db)
        for manage in (True, False):
            with self.subTest(manage_transaction=manage):
                with self.assertRaisesRegex(SpineValidationError, "unpropagated relation"), self.db.atomic_command():
                    self.native(manage_transaction=manage)
                self.assertEqual(dump(self.db), before)
                self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_standalone_helper_retains_local_commit_without_application_dependency(self):
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("standalone ledger owner")):
            identity = self.native(metadata_json='{"note":"retained exactly"}')
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(relations.relation_snapshot(self.db, identity).metadata_json, '{"note":"retained exactly"}')
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_duplicate_or_mismatched_propagation_rolls_back_native_write(self):
        before = dump(self.db)
        for mode in ("duplicate", "capture", "persisted"):
            with self.subTest(mode=mode):
                with self.assertRaises(SpineValidationError), self.db.atomic_command():
                    identity = self.native(manage_transaction=False)
                    if mode == "capture":
                        pending = self.db.mutation_state.propagation.relations
                        effect = pending[identity]
                        pending[identity] = replace(effect, after=replace(effect.after, relation_type="part_of"))
                    elif mode == "persisted":
                        self.db.execute("UPDATE coordination_item_relations SET relation_status='inactive' WHERE relation_id=?",
                                        (identity,))
                    mutation_propagation.propagate(self.db, relation_id=identity)
                    if mode == "duplicate":
                        mutation_propagation.propagate(self.db, relation_id=identity)
                self.assertEqual(dump(self.db), before)
                self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_nested_rollback_restores_debt_and_preserves_earlier_relation(self):
        with self.db.atomic_command():
            first = self.native("first")
            mutation_propagation.propagate(self.db, relation_id=first)
            for propagated in (False, True):
                with self.assertRaisesRegex(RuntimeError, "trial"), self.db.command_unit():
                    second = self.native("second", relation_status="inactive", manage_transaction=False)
                    if propagated:
                        mutation_propagation.propagate(self.db, relation_id=second)
                    raise RuntimeError("trial")
                self.assertEqual(self.db.mutation_state.propagation.relations, {})
                self.assertIsNotNone(relations.relation_snapshot(self.db, first))
                self.assertIsNone(relations.relation_snapshot(self.db, "second"))
            second = self.native("second", relation_status="inactive")
            mutation_propagation.propagate(self.db, relation_id=second)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_later_finalizer_failure_and_raw_commit_leave_no_relation(self):
        before = dump(self.db)
        with (patch("spine.ledger.facets.finalize", side_effect=RuntimeError("later")),
              self.assertRaisesRegex(RuntimeError, "later"), self.db.atomic_command()):
            mutation_propagation.propagate(self.db, relation_id=self.native())
        self.assertEqual(dump(self.db), before)
        with self.assertRaises(sqlite3.DatabaseError), self.db.atomic_command():
            self.native()
            self.db.execute("COMMIT")
        self.assertEqual(dump(self.db), before)

    def test_plain_context_without_facets_cannot_commit_relation_debt(self):
        with self.db.atomic_command():
            identity = self.native()
            effect = mutation_propagation.propagate(self.db, relation_id=identity).relations[0]
        db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(db.close)
        db.execute("CREATE TABLE trial(value INTEGER)")
        with self.assertRaisesRegex(SpineValidationError, "unpropagated relation"), db:
            db.execute("INSERT INTO trial VALUES(1)")
            db.mutation_state.propagation.relations[identity] = effect
        self.assertEqual(db.execute("SELECT * FROM trial").fetchall(), [])
        self.assertEqual(db.mutation_state, TransactionMutationState())

    def test_closed_relation_writer_and_caller_inventory(self):
        root = Path(__file__).parents[1] / "src/spine"
        writers, callers = {}, {}
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                name = str(path.relative_to(root))
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for _ in re.finditer(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+coordination_item_relations\b", node.value, re.I):
                        writers[name] = writers.get(name, 0) + 1
                if isinstance(node, ast.Call) and ast.unparse(node.func).rsplit(".", 1)[-1] == "create_item_relation":
                    callers[name] = callers.get(name, 0) + 1
        self.assertEqual(writers, {"ledger/relations.py": 1})
        self.assertEqual(callers, {"commands/core.py": 1, "commands/temporal_bindings.py": 1, "services/recurring_task_children.py": 1})
