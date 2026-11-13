"""RF3 binding seam: exact consequences, bypass rejection and paired rollback."""

import ast
import re
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ChangeCategory
from spine.ledger import temporal_bindings
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.temporal_bindings import binding_catalog_generation, retire_temporal_binding
from spine.ledger.transactions import LedgerConnection
from spine.services import mutation_propagation
from tests import test_binding_successor_materialization as binding_tests
from tests import test_recurring_task_commands as recurring_base
from tests import test_recurring_task_reconcile as recurring_tests


class MutationPropagationTests(unittest.TestCase):
    def setUp(self):
        self.h = binding_tests.BindingSuccessorMaterializationTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.db = self.h.db

    def identity(self, created):
        return self.h.h._binding_for(created["task"]["item_id"])["temporal_binding_id"]

    def retire(self, identity, key):
        retire_temporal_binding(self.db, temporal_binding_id=identity, command_id=key, retired_at_utc="2026-08-17T12:00:00Z")

    def capture(self, calls):
        original = mutation_propagation.propagate

        def observed(*args, **kwargs):
            effect = original(*args, **kwargs)
            if effect.bindings:
                calls.append(effect)
            return effect

        return patch.object(mutation_propagation, "propagate", side_effect=observed)

    def test_create_move_and_detach_propagate_once_with_exact_typed_facts(self):
        calls = []
        before = binding_catalog_generation(self.db)
        with self.capture(calls):
            created = self.h.create(materialize=False)
        self.assertEqual(binding_catalog_generation(self.db), before + 1)
        self.assertEqual(len(calls), 1)
        first = calls.pop().bindings[0]
        self.assertIsNone(first.before)
        self.assertEqual(first.after.binding_id, self.identity(created))
        self.assertEqual(first.after.target_item_id, created["task"]["item_id"])
        self.assertEqual(first.after.source_item_id, self.h.h.event["item_id"])
        self.assertEqual(first.categories, {ChangeCategory.BINDING, ChangeCategory.TIME})
        self.h.move("2026-08-23")
        # The ordinary source audit has its own existing trigger-owned bump.
        self.assertEqual(binding_catalog_generation(self.db), before + 2)
        with self.capture(calls):
            self.h.ok("schedule.binding.reconcile", self.h.request(created, materialization={"mode": "none"}))
        moved = calls.pop().bindings[0]
        self.assertEqual(moved.before, first.after)
        self.assertEqual(moved.after.target_item_version, 2)
        self.assertIn(ChangeCategory.TIME, moved.categories)
        with self.capture(calls):
            self.h.ok("schedule.binding.reconcile", self.h.request(
                created, key="detach", materialization={"mode": "none"}, operator="detach_at_current_target"))
        detached = calls.pop().bindings[0]
        self.assertEqual(detached.before, moved.after)
        self.assertEqual(detached.after.status, "retired")
        self.assertEqual(detached.categories, {ChangeCategory.BINDING})
        self.assertEqual(binding_catalog_generation(self.db), before + 4)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_version_only_refresh_is_not_a_time_change_and_noop_replay_do_not_propagate(self):
        created = self.h.create(materialize=False)
        self.h.ok("schedule.update", {"contract_version": "spine.schedule-update.v2", "command_id": "title-only",
            "actor_subject_id": "owner", "item_id": self.h.h.event["item_id"], "target_version": "1",
            "updated_at_utc": "2026-08-17T12:00:00Z", "patch": {"item": {"title": "Same time, new title"}},
            "materialization": {"mode": "none"}})
        calls = []
        with self.capture(calls):
            request = self.h.request(created, materialization={"mode": "none"})
            self.h.ok("schedule.binding.reconcile", request)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].bindings[0].categories, {ChangeCategory.BINDING})
        before = binding_catalog_generation(self.db)
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("no propagation for no-op/replay")):
            self.h.ok("schedule.binding.reconcile", request)
            self.h.ok("schedule.binding.reconcile", self.h.request(created, key="noop", materialization={"mode": "none"}))
        self.assertEqual(binding_catalog_generation(self.db), before)

    def test_missing_propagation_aborts_public_create_and_both_reconcile_paths(self):
        before = self.h.dump()
        with patch.object(mutation_propagation, "propagate", return_value=None):
            response = handle("schedule.related_task.create", self.h.h._related_request("follow_source"), self.h.context)
        self.assertFalse(response["ok"], response)
        self.assertEqual(self.h.dump(), before)
        created = self.h.create(materialize=False)
        for mode in ("move", "detach"):
            if mode == "move":
                self.h.move("2026-08-23")
            before = self.h.dump()
            request = self.h.request(created, key="bypass-" + mode, materialization={"mode": "none"},
                operator="detach_at_current_target" if mode == "detach" else None)
            with patch.object(mutation_propagation, "propagate", return_value=None):
                response = handle("schedule.binding.reconcile", request, self.h.context)
            self.assertFalse(response["ok"], response)
            self.assertEqual(self.h.dump(), before)
            self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_direct_writer_missing_or_duplicate_propagation_rolls_back(self):
        identity = self.identity(self.h.create(materialize=False))
        before = self.h.dump()
        with self.assertRaisesRegex(SpineValidationError, "unpropagated"), self.db.atomic_command():
            self.retire(identity, "missing")
        self.assertEqual(self.h.dump(), before)
        with self.assertRaisesRegex(SpineValidationError, "already propagated"), self.db.atomic_command():
            self.retire(identity, "duplicate")
            mutation_propagation.propagate(self.db, binding_id=identity)
            mutation_propagation.propagate(self.db, binding_id=identity)
        self.assertEqual(self.h.dump(), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_nested_unit_rollback_keeps_first_consequence_and_discards_second_debt(self):
        first = self.identity(self.h.create(materialize=False, key="first"))
        second = self.identity(self.h.create(materialize=False, key="second"))
        before = binding_catalog_generation(self.db)
        with self.db.atomic_command():
            self.retire(first, "first-retire")
            mutation_propagation.propagate(self.db, binding_id=first)
            for propagated in (False, True):
                with self.assertRaisesRegex(RuntimeError, "trial"), self.db.command_unit():
                    self.retire(second, "second-retire")
                    if propagated:
                        mutation_propagation.propagate(self.db, binding_id=second)
                    raise RuntimeError("trial")
                self.assertEqual(self.db.mutation_state.propagation.bindings, {})
                self.assertEqual(binding_catalog_generation(self.db), before + 1)
        self.assertEqual(binding_catalog_generation(self.db), before + 1)
        with self.db.atomic_command():
            self.retire(second, "second-retry")
            mutation_propagation.propagate(self.db, binding_id=second)
        self.assertEqual(binding_catalog_generation(self.db), before + 2)

    def test_later_finalizer_failure_rolls_back_effect_and_catalog(self):
        identity = self.identity(self.h.create(materialize=False))
        before = self.h.dump()
        with (patch("spine.ledger.facets.finalize", side_effect=RuntimeError("later finalizer")),
              self.assertRaisesRegex(RuntimeError, "later finalizer"), self.db.atomic_command()):
            self.retire(identity, "later-failure")
            mutation_propagation.propagate(self.db, binding_id=identity)
        self.assertEqual(self.h.dump(), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_missing_catalog_consequence_cannot_be_marked_propagated(self):
        identity = self.identity(self.h.create(materialize=False))
        before = self.h.dump()
        with (patch.object(mutation_propagation, "increment_binding_catalog_generation", return_value=None),
              self.assertRaisesRegex(SpineValidationError, "consequence missing"), self.db.atomic_command()):
            self.retire(identity, "missing-catalog")
            mutation_propagation.propagate(self.db, binding_id=identity)
        self.assertEqual(self.h.dump(), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_native_projection_mismatch_is_rejected_before_catalog_acknowledgment(self):
        original = temporal_bindings.binding_revision
        before = self.h.dump()

        def wrong(*args):
            return replace(original(*args), target_item_version=999)

        with patch.object(temporal_bindings, "binding_revision", side_effect=wrong):
            response = handle("schedule.related_task.create", self.h.h._related_request("follow_source"), self.h.context)
        self.assertFalse(response["ok"], response)
        self.assertIn("incomplete or changed", response["error"]["message"])
        self.assertEqual(self.h.dump(), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_new_header_and_revision_need_only_one_persisted_snapshot_read(self):
        queries = []
        original = temporal_bindings.insert_temporal_binding

        def omitted_default(db, *, value):
            value = dict(value)
            value.pop("binding_status", None)
            original(db, value=value)

        self.db.set_trace_callback(queries.append)
        try:
            with patch("spine.commands.temporal_bindings.insert_temporal_binding", side_effect=omitted_default):
                self.h.create(materialize=False)
        finally:
            self.db.set_trace_callback(None)
        self.assertEqual(len([q for q in queries if q.startswith("SELECT b.temporal_binding_id AS binding_id,")]), 1)

    def test_pending_obligation_cannot_escape_plain_context_without_facets(self):
        calls = []
        with self.capture(calls):
            self.h.create(materialize=False)
        effect = calls[0].bindings[0]
        db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(db.close)
        db.execute("CREATE TABLE trial(value INTEGER)")
        with self.assertRaisesRegex(SpineValidationError, "unpropagated"), db:
            db.execute("INSERT INTO trial VALUES(1)")
            db.mutation_state.propagation.bindings[effect.after.binding_id] = effect
        self.assertEqual(db.execute("SELECT * FROM trial").fetchall(), [])
        self.assertEqual(db.mutation_state, TransactionMutationState())

    def test_propagation_requires_transaction_and_native_writer_cannot_raw_commit(self):
        identity = self.identity(self.h.create(materialize=False))
        with self.assertRaisesRegex(SpineValidationError, "owned transaction"):
            mutation_propagation.propagate(self.db, binding_id=identity)
        before = self.h.dump()
        with self.assertRaises(sqlite3.DatabaseError), self.db.atomic_command():
            self.retire(identity, "raw-commit")
            self.db.execute("COMMIT")
        self.assertEqual(self.h.dump(), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_missing_propagation_aborts_recurring_creation_and_change(self):
        h = recurring_tests.RecurringTaskReconcileTests()
        h.contracts = recurring_base.contracts()
        h.setUp()
        self.addCleanup(h.doCleanups)
        rule = h.created()["result"]["rule"]
        before = recurring_base.dump(h.db)
        with patch.object(mutation_propagation, "propagate", return_value=None):
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual(recurring_base.dump(h.db), before)
        created = h.reconcile(rule)
        first = created["result"]["results"][0]
        h.source_change(exdates=[h.excluded(first)])
        rule = h.rule(rule["related_task_rule_id"])
        before = recurring_base.dump(h.db)
        with patch.object(mutation_propagation, "propagate", return_value=None):
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}) | {"command_id": "bypass-child-change"})
        self.assertFalse(result["ok"], result)
        self.assertEqual(recurring_base.dump(h.db), before)
        self.assertEqual(h.db.mutation_state, TransactionMutationState())

    def test_closed_binding_call_inventory_and_one_catalog_owner(self):
        root = Path(__file__).parents[1] / "src/spine"
        actual = {}
        sql_writers = {}
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for match in re.finditer(
                        r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
                        r"(relative_temporal_bindings|relative_temporal_binding_revisions)\b",
                        node.value, re.IGNORECASE,
                    ):
                        key = (str(path.relative_to(root)), match[1].lower())
                        sql_writers[key] = sql_writers.get(key, 0) + 1
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func).rsplit(".", 1)[-1]
                    if name in {"insert_temporal_binding", "insert_temporal_binding_revision", "retire_temporal_binding",
                                "increment_binding_catalog_generation", "record_binding", "propagate"}:
                        key = (str(path.relative_to(root)), name)
                        actual[key] = actual.get(key, 0) + 1
        self.assertEqual(sql_writers, {
            ("ledger/temporal_bindings.py", "relative_temporal_bindings"): 2,
            ("ledger/temporal_bindings.py", "relative_temporal_binding_revisions"): 1,
        })
        self.assertEqual(actual, {
            ("commands/temporal_bindings.py", "insert_temporal_binding"): 1,
            ("commands/temporal_bindings.py", "insert_temporal_binding_revision"): 3,
            ("commands/temporal_bindings.py", "retire_temporal_binding"): 2,
            ("commands/core.py", "propagate"): 7,
            ("commands/temporal_bindings.py", "propagate"): 4,
            ("services/recurring_task_children.py", "insert_temporal_binding"): 1,
            ("services/recurring_task_children.py", "insert_temporal_binding_revision"): 2,
            ("services/recurring_task_children.py", "retire_temporal_binding"): 1,
            ("services/recurring_task_children.py", "propagate"): 4,
            ("web/service.py", "propagate"): 1,
            ("web/people_schedule_service.py", "propagate"): 1,
            ("web/provisioning.py", "propagate"): 1,
            ("ledger/temporal_bindings.py", "record_binding"): 3,
            ("services/mutation_propagation.py", "increment_binding_catalog_generation"): 1,
        })
