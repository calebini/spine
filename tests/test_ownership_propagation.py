"""RF3 owner writers: required history/epoch propagation, no access-policy changes."""

import ast
import re
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ChangeCategory, ConfiguredOwnerPropagation, LocalOwnerPropagation, OwnerMutation, OwnerSnapshot
from spine.ledger.items import create_task_v1
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.owner_mutations import insert_item_owner, record_item_owner_history
from spine.ledger.transactions import LedgerConnection
from spine.services import mutation_propagation
from spine.web.errors import WebError
from tests import test_ownership_bootstrap as bootstrap
from tests import test_people_schedule_integration as people
from tests import test_recurring_task_commands as recurring_base
from tests import test_recurring_task_reconcile as recurring
from tests import test_trusted_web_runtime as web


def dump(db):
    return "\n".join(db.iterdump())


class OwnershipPropagationTests(unittest.TestCase):
    def web(self, *, successor=False):
        if successor:
            people.PeopleScheduleIntegrationTests.setUpClass()
            h = people.PeopleScheduleIntegrationTests()
        else:
            h = web.TrustedWebRuntimeTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        return h

    def recurring(self):
        h = recurring.RecurringTaskReconcileTests()
        h.contracts = recurring_base.contracts()
        h.setUp()
        self.addCleanup(h.doCleanups)
        return h

    def unowned(self, h, name):
        return h.ok(handle("schedule.create", h.event(name)["request"], h.ctx))

    def adoption(self, item):
        return dict(operation="create", item_id=item, expected_item_version="1",
                    owner_scope=dict(owner_kind="subject", owner_subject_id="owner"))

    def omit_owners(self):
        original = mutation_propagation.propagate
        return patch.object(mutation_propagation, "propagate",
            side_effect=lambda *a, **kw: None if "ownership" in kw else original(*a, **kw))

    def test_exact_owner_effect_and_configured_epoch_for_both_web_paths(self):
        for successor in (False, True):
            with self.subTest(successor=successor):
                h = self.web(successor=successor)
                body = h.create_body(people=["owner"]) if successor else h.event()
                before = h.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]
                captured = []
                original = mutation_propagation.propagate

                def observe(*args, original=original, captured=captured, **kwargs):
                    result = original(*args, **kwargs)
                    if result.owners:
                        captured.append(result)
                    return result

                with patch.object(mutation_propagation, "propagate", side_effect=observe):
                    result = h.run_command("schedule.create", body)
                self.assertEqual(len(captured), 1)
                facts = captured[0]
                self.assertEqual((facts.ownership_epoch.before_epoch, facts.ownership_epoch.after_epoch), (before, before + 1))
                effect = facts.owners[0]
                self.assertIsNone(effect.before)
                self.assertEqual(effect.categories, {ChangeCategory.OWNERSHIP})
                self.assertEqual(effect.after.item_id, result["result"]["item_id"])
                self.assertEqual(effect.after.owner_subject_id, "owner")
                self.assertIsNone(effect.after.creator_subject_id)
                self.assertEqual(effect.history.receipt_id, result["result"]["command_receipt_id"])
                frozen = dump(h.db)
                with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("replay must not propagate")):
                    h.run_command("schedule.create", body)
                self.assertEqual(dump(h.db), frozen)

    def test_omitted_propagation_rolls_back_both_protected_create_paths(self):
        for successor in (False, True):
            with self.subTest(successor=successor):
                h = self.web(successor=successor)
                body = h.create_body() if successor else h.event()
                before = dump(h.db)
                with self.omit_owners(), self.assertRaises((WebError, SpineValidationError)):
                    h.run_command("schedule.create", body)
                self.assertEqual(dump(h.db), before)
                self.assertEqual(h.db.mutation_state, TransactionMutationState())

    def test_omitted_propagation_rolls_back_adoption_and_recurring_page(self):
        h = self.web()
        item = self.unowned(h, "unowned")["item_id"]
        before = dump(h.db)
        with self.omit_owners(), self.assertRaises(SpineValidationError):
            h.provision(item_adoptions=[self.adoption(item)])
        self.assertEqual(dump(h.db), before)
        h = self.recurring()
        rule = h.created()["result"]["rule"]
        before = dump(h.db)
        with self.omit_owners():
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(h.db), before)
        self.assertEqual(h.db.mutation_state, TransactionMutationState())

    def test_missing_history_or_epoch_and_wrong_capture_fail_closed(self):
        for case in ("history", "epoch", "capture"):
            with self.subTest(case=case):
                h = self.web()
                body, before = h.event(), dump(h.db)
                original = mutation_propagation.propagate

                def wrong(db, original=original, **kwargs):
                    if "ownership" not in kwargs:
                        return original(db, **kwargs)
                    identity = kwargs["ownership"].owner_id
                    pending = db.mutation_state.propagation.owners
                    effect = pending[identity]
                    pending[identity] = replace(effect, after=replace(effect.after, owner_subject_id="other"))
                    return original(db, **kwargs)

                target = {
                    "history": patch("spine.ledger.owner_mutations.record_item_owner_history"),
                    "epoch": patch.object(mutation_propagation, "advance_configured_epoch"),
                    "capture": patch.object(mutation_propagation, "propagate", side_effect=wrong),
                }[case]
                with target, self.assertRaises((WebError, SpineValidationError)):
                    h.run_command("schedule.create", body)
                self.assertEqual(dump(h.db), before)

    def test_header_history_equality_is_preserved_by_python_comparison(self):
        from spine.ledger.owner_mutations import record_item_owner_history

        h = self.web()

        def drift(db, identity, actor, at, receipt):
            pending = db.mutation_state.propagation.owners
            effect = pending[identity]
            pending[identity] = replace(effect, after=replace(effect.after, command_id="different"))
            record_item_owner_history(db, identity, actor, at, receipt)
            pending[identity] = replace(pending[identity], after=effect.after)

        before = dump(h.db)
        with (patch("spine.ledger.owner_mutations.record_item_owner_history", side_effect=drift),
              self.assertRaises((WebError, SpineValidationError))):
            h.run_command("schedule.create", h.event())
        self.assertEqual(dump(h.db), before)

    def test_duplicate_propagation_rolls_back_first_advance(self):
        h = self.web()
        original = mutation_propagation.propagate

        def twice(*args, **kwargs):
            if "ownership" not in kwargs:
                return original(*args, **kwargs)
            original(*args, **kwargs)
            return original(*args, **kwargs)

        before = dump(h.db)
        with patch.object(mutation_propagation, "propagate", side_effect=twice), self.assertRaises((WebError, SpineValidationError)):
            h.run_command("schedule.create", h.event())
        self.assertEqual(dump(h.db), before)

    def test_local_epoch_reservation_cannot_be_omitted(self):
        h = self.recurring()
        rule = h.created()["result"]["rule"]
        before = dump(h.db)
        with patch("spine.services.recurring_task_children.reserve_local_owner_epoch", return_value=2):
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(h.db), before)

    def test_nested_rollback_restores_owner_debt_and_shared_epoch(self):
        h = self.web()
        items = [self.unowned(h, name) for name in ("one", "two")]
        before = h.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]

        def create(index):
            mutation_propagation.reserve_local_owner_epoch(h.db)
            value = items[index]
            identity = "owner-" + str(index)
            insert_item_owner(h.db, OwnerSnapshot(value["item_id"], identity, 1, "subject", "owner", None, None, "native"))
            record_item_owner_history(h.db, identity, "owner", web.AT, value["command_receipt_id"])
            return identity

        with h.db.atomic_command():
            first = create(0)
            mutation_propagation.propagate(h.db, ownership=LocalOwnerPropagation(first))
            for propagated in (False, True):
                with self.assertRaisesRegex(RuntimeError, "trial"), h.db.command_unit():
                    second = create(1)
                    if propagated:
                        mutation_propagation.propagate(h.db, ownership=LocalOwnerPropagation(second))
                    raise RuntimeError("trial")
                self.assertFalse(h.db.mutation_state.propagation.owners)
                self.assertEqual(h.db.mutation_state.ownership.epoch_before, before)
                self.assertEqual(h.db.mutation_state.ownership.epoch_after, before + 1)
            second = create(1)
            mutation_propagation.propagate(h.db, ownership=LocalOwnerPropagation(second))
        self.assertEqual(h.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0], before + 1)
        self.assertEqual(h.db.mutation_state, TransactionMutationState())

    def test_configured_path_cannot_bootstrap_absent_state(self):
        h = self.recurring()
        with h.db.atomic_command():
            h.db.execute("DELETE FROM ledger_access_state")
        rule = h.created()["result"]["rule"]
        original = mutation_propagation.propagate

        def configured(db, **kwargs):
            if isinstance(kwargs.get("ownership"), LocalOwnerPropagation):
                kwargs["ownership"] = ConfiguredOwnerPropagation(kwargs["ownership"].owner_id, 0)
            return original(db, **kwargs)

        before = dump(h.db)
        with patch("spine.services.recurring_task_children.reserve_local_owner_epoch", return_value=1), \
                patch.object(mutation_propagation, "propagate", side_effect=configured):
            result = h.run_command("reconcile", h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(h.db), before)

    def test_closed_owner_writer_inventory(self):
        root = Path(__file__).parents[1] / "src/spine"
        calls, writers = {}, {}
        names = {"insert_item_owner", "record_item_owner_history", "reserve_local_owner_epoch",
                 "advance_ownership_epoch", "advance_configured_epoch"}
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                name = str(path.relative_to(root))
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for match in re.finditer(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
                                            r"(item_access_owners|item_access_owner_revisions)\b", node.value, re.I):
                        key = (name, match[1].lower())
                        writers[key] = writers.get(key, 0) + 1
                if isinstance(node, ast.Call):
                    target = ast.unparse(node.func).rsplit(".", 1)[-1]
                    if target in names:
                        key = (name, target)
                        calls[key] = calls.get(key, 0) + 1
        self.assertEqual(writers, {("ledger/owner_mutations.py", "item_access_owners"): 1,
                                   ("ledger/owner_mutations.py", "item_access_owner_revisions"): 1})
        self.assertEqual(calls, {
            ("services/recurring_task_children.py", "insert_item_owner"): 1,
            ("services/recurring_task_children.py", "record_item_owner_history"): 1,
            ("services/recurring_task_children.py", "reserve_local_owner_epoch"): 1,
            ("services/mutation_propagation.py", "advance_ownership_epoch"): 1,
            ("services/mutation_propagation.py", "advance_configured_epoch"): 1,
            ("web/history.py", "record_item_owner_history"): 1,
            ("web/service.py", "insert_item_owner"): 1,
            ("web/people_schedule_service.py", "insert_item_owner"): 1,
            ("web/provisioning.py", "insert_item_owner"): 1,
            ("web/ownership_provisioning.py", "advance_ownership_epoch"): 1,
        })

    def test_successor_provisioning_batch_owns_one_epoch_from_absent_or_local_state(self):
        for local in (False, True):
            with self.subTest(local=local):
                h = bootstrap.OwnershipBootstrapTests()
                h.setUp()
                self.addCleanup(h.doCleanups)
                h.install()
                if local:
                    with h.db.atomic_command():
                        mutation_propagation.reserve_local_owner_epoch(h.db)
                for identity in ("first", "second"):
                    create_task_v1(h.db, item_id=identity, audit_id=identity, created_by_subject_id="owner",
                                   title=identity, created_at_utc=bootstrap.AT)
                proposal = h.proposed(item_adoptions=[self.adoption(identity) for identity in ("first", "second")])
                request = h.request(proposal)
                original, effects = mutation_propagation.propagate, []

                def capture(*args, original=original, effects=effects, **kwargs):
                    result = original(*args, **kwargs)
                    effects.append(result)
                    return result

                with patch.object(mutation_propagation, "propagate", side_effect=capture):
                    response = bootstrap.apply(h.db, request, bootstrap=h.contracts)
                self.assertEqual(len(effects), 1)
                self.assertEqual(len(effects[0].owners), 2)
                self.assertEqual((effects[0].ownership_epoch.before_epoch, effects[0].ownership_epoch.after_epoch),
                                 (int(local), int(local) + 1))
                self.assertEqual(response["access_epoch"], str(int(local) + 1))
                frozen = dump(h.db)
                with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("replay")):
                    bootstrap.apply(h.db, request, bootstrap=h.contracts)
                self.assertEqual(dump(h.db), frozen)

    def test_native_owner_write_and_plain_context_cannot_omit_propagation(self):
        h = self.web()
        item = self.unowned(h, "native")
        before = dump(h.db)
        snapshot = OwnerSnapshot(item["item_id"], "native-owner", 1, "subject", "owner", None, None, "native")
        with self.assertRaisesRegex(SpineValidationError, "unpropagated ownership"), h.db.atomic_command():
            mutation_propagation.reserve_local_owner_epoch(h.db)
            insert_item_owner(h.db, snapshot)
            record_item_owner_history(h.db, snapshot.owner_id, "owner", web.AT, item["command_receipt_id"])
        self.assertEqual(dump(h.db), before)
        db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(db.close)
        db.execute("CREATE TABLE trial(value INTEGER)")
        with self.assertRaisesRegex(SpineValidationError, "unpropagated ownership"), db:
            db.execute("INSERT INTO trial VALUES(1)")
            db.mutation_state.propagation.owners[snapshot.owner_id] = OwnerMutation(snapshot)
        self.assertEqual(db.execute("SELECT * FROM trial").fetchall(), [])
        self.assertEqual(db.mutation_state, TransactionMutationState())
