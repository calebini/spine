"""Manual R2 customization, source-history, budget and writer-edge regressions."""

import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import core, handle
from spine.ledger import connect
from spine.ledger.common import TemporalAnchorInput, insert_temporal_anchor
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_migration import attach_candidate
from spine.ledger.recurring_task_sources import ProofBudget
from spine.services.item_mutations import create_next_item_version
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages
from tests import test_recurring_task_restoration as restoration


class RecurringTaskEdges(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    run_command = base.RecurringTaskCommandTests.run_command
    created = base.RecurringTaskCommandTests.created
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    rule = pages.RecurringTaskReconcileTests.rule
    source_change = pages.RecurringTaskReconcileTests.source_change
    excluded = pages.RecurringTaskReconcileTests.excluded
    authored = restoration.RecurringTaskRestorationTests.authored
    cycle = restoration.RecurringTaskRestorationTests.cycle

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def add_date(self, fact, key):
        current = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        version = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (self.event["item_id"],)).fetchone()[0]
        result = handle("recurrence.instance.add", {
            "command_id": key, "actor_subject_id": "owner", "item_id": self.event["item_id"], "target_version": str(version),
            "recurrence_set_id": current["recurrence_set_id"], "recurrence_revision_id": current["recurrence_revision_id"],
            "added_at_utc": self.now, "scheduled_fact": fact, "reason_code": "extra_class",
        }, self.context)
        self.assertTrue(result["ok"], result)
        return result

    def test_restoration_preserves_actual_nonterminal_details_and_defer_anchor(self):
        initial, first = self.authored(reminders=False)
        task = first["after"]["task_item_id"]
        with self.db.atomic_command(write=True):
            insert_temporal_anchor(self.db, anchor=TemporalAnchorInput(anchor_kind="instant_utc", utc_instant="2026-08-08T12:00:00Z"),
                                   anchor_id="individual-defer", default_created_at_utc=self.now)
            create_next_item_version(self.db, item_id=task, target_version=1, created_at_utc=self.now, created_by_subject_id="owner",
                title="Special pickup", summary="Bring the science kit", source_ref="individual-choice",
                task_detail={"priority": "high", "completion_state": "kit_ready", "defer_until_anchor_id": "individual-defer"},
                supporting_command_id="individual-detail")
        before = copy.deepcopy(core._hydrated_item(self.db, task))
        _, _, child = self.cycle(initial["result"]["rule"], first)
        for key in ("title", "summary", "source_ref"):
            self.assertEqual(child["version"][key], before["version"][key])
        for key in ("priority", "completion_state"):
            self.assertEqual(child["detail"][key], before["detail"][key], key)
        self.assertIsNotNone(child["detail"]["defer_until_anchor_id"])
        self.assertEqual(child["detail"]["defer_until_anchor"]["utc_instant"], "2026-08-08T12:00:00Z")
        self.assertEqual(child["detail"]["task_status"], "open")
        self.assertIsNone(child["detail"]["completed_at_utc"])

    def test_delayed_new_rdate_after_copy_revisions_creates_one_assignment(self):
        root = self.created()["result"]["rule"]
        fact = "2026-08-20T18:00:00Z"
        self.add_date(fact, "positive-added")
        self.add_date("2027-01-01T18:00:00Z", "later-copy-one")
        self.add_date("2027-02-01T18:00:00Z", "later-copy-two")
        result = self.reconcile(self.rule(root["related_task_rule_id"]))
        self.assertEqual(len(result["result"]["results"]), 7)
        self.assertEqual([(entry["selector"]["scheduled_fact"], entry["outcome"]) for entry in result["result"]["results"]],
                         [(f"2026-08-{day:02}T18:00:00Z", "created") for day in (*range(8, 14), 20)])
        selected = next(entry for entry in result["result"]["results"] if entry["selector"]["scheduled_fact"] == fact)
        repeated = self.reconcile(result["result"]["rule"], "repeat-delayed")
        self.assertFalse(repeated["changed"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations WHERE assignment_id=?",
                                        (selected["assignment_id"],)).fetchone()[0], 1)

    def test_novelty_and_continuity_budget_failures_do_not_cancel_or_partial_create(self):
        root = self.created()["result"]["rule"]
        self.add_date("2026-08-20T18:00:00Z", "budget-added")
        self.add_date("2027-01-01T18:00:00Z", "budget-copy-one")
        self.add_date("2027-02-01T18:00:00Z", "budget-copy-two")
        current = self.rule(root["related_task_rule_id"])
        for limits in ({"proof_steps": "1"}, {"lineage_hops": "1"}):
            with self.subTest(limits=limits):
                before = base.dump(self.db)
                request = self.write("reconcile", current, limits=limits)
                result = self.run_command("reconcile", request)
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["error"]["code"], "capacity_exceeded", result)
                self.assertEqual(base.dump(self.db), before)

    def test_lineage_limit_is_path_depth_not_sum_of_rechecks_or_other_tasks(self):
        root = self.created()["result"]["rule"]
        for index, date in enumerate(("2026-08-20", "2027-01-01", "2027-02-01")):
            self.add_date(date + "T18:00:00Z", f"path-copy-{index}")
        current = self.rule(root["related_task_rule_id"])
        before = base.dump(self.db)
        failed = self.run_command("reconcile", self.write("reconcile", current, limits={"lineage_hops": "2"}))
        self.assertEqual(failed["error"]["code"], "capacity_exceeded")
        self.assertEqual(failed["error"]["field"], "limits.lineage_hops")
        self.assertEqual(base.dump(self.db), before)
        result = self.reconcile(current, "exact-path-budget", lineage_hops="3")
        self.assertEqual([entry["outcome"] for entry in result["result"]["results"]], ["created"] * 7)

    def test_unproved_delayed_rdate_rolls_back_birth_proof_without_cancelling_other_tasks(self):
        root = self.created()["result"]["rule"]
        fact = "2026-08-20T18:00:00Z"
        self.add_date(fact, "incomplete-added")
        derive = core.derive_recurrence_lineage

        def omit_copy(*args, **kwargs):
            return [line for line in derive(*args, **kwargs)
                    if not (line["lineage_role"] == "rdate_revision" and line["effect"] == "copied")]

        with patch.object(core, "derive_recurrence_lineage", side_effect=omit_copy):
            self.add_date("2027-01-01T18:00:00Z", "missing-copy-evidence")
        result = self.reconcile(self.rule(root["related_task_rule_id"]))
        self.assertEqual([entry["outcome"] for entry in result["result"]["results"]], ["created"] * 6 + ["decision_required"])
        self.assertEqual(result["result"]["results"][-1]["reason"], "source_continuity_unresolved")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_source_proofs WHERE proof_kind='new_rdate'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM task_details WHERE task_status='cancelled'").fetchone()[0], 0)

    def test_exact_shared_proof_step_budget_and_one_step_under_are_atomic(self):
        root = self.created()["result"]["rule"]
        self.add_date("2026-08-20T18:00:00Z", "step-added")
        self.add_date("2027-01-01T18:00:00Z", "step-copy")
        current = self.rule(root["related_task_rule_id"])
        request = self.write("reconcile", current, limits={})
        preview = replace(self.context, dry_run=True)
        before = base.dump(self.db)
        consumed = 0
        spend = ProofBudget.spend

        def count(budget, amount=1):
            nonlocal consumed
            if budget.on_exhausted is not None:
                consumed += amount
            return spend(budget, amount)

        with patch.object(ProofBudget, "spend", count):
            result = self.run_command("reconcile", request, context=preview)
        self.assertTrue(result["ok"], result)
        self.assertGreater(consumed, 1)
        self.assertEqual(base.dump(self.db), before)
        for limit, success in ((consumed - 1, False), (consumed, True)):
            with self.subTest(limit=limit):
                limited = self.write("reconcile", current, limits={"proof_steps": str(limit)})
                result = self.run_command("reconcile", limited, context=preview)
                self.assertEqual(result["ok"], success, result)
                if not success:
                    self.assertEqual(result["error"]["field"], "limits.proof_steps")
                else:
                    self.assertEqual([entry["outcome"] for entry in result["result"]["results"]], ["created"] * 7)
                self.assertEqual(base.dump(self.db), before)

    def test_restoration_honors_explicitly_cleared_individual_details(self):
        initial, first = self.authored(reminders=False)
        task = first["after"]["task_item_id"]
        with self.db.atomic_command(write=True):
            insert_temporal_anchor(self.db, anchor=TemporalAnchorInput(anchor_kind="instant_utc", utc_instant="2026-08-08T12:00:00Z"),
                                   anchor_id="cleared-defer", default_created_at_utc=self.now)
            create_next_item_version(self.db, item_id=task, target_version=1, created_at_utc=self.now, created_by_subject_id="owner",
                task_detail={"priority": "high", "completion_state": "kit_ready", "defer_until_anchor_id": "cleared-defer"},
                supporting_command_id="before-clear")
            create_next_item_version(self.db, item_id=task, target_version=2, created_at_utc=self.now, created_by_subject_id="owner",
                task_detail={"priority": None, "completion_state": None, "defer_until_anchor_id": None},
                supporting_command_id="clear-details")
        _, _, child = self.cycle(initial["result"]["rule"], first, "clear-cycle")
        for key in ("priority", "completion_state", "defer_until_anchor_id"):
            self.assertIsNone(child["detail"][key], key)

    def first_generation_race(self, keys):
        root = self.created()["result"]["rule"]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "first-generation.sqlite")
            target = connect(path)
            self.db.backup(target)
            target.close()
            barrier = threading.Barrier(2)

            def run(key):
                db = connect(path)
                try:
                    attach_candidate(db)
                    context = replace(self.context, ledger=db)
                    request = self.write("reconcile", root, limits={}) | {"command_id": key}
                    barrier.wait(timeout=10)
                    result = self.run_command("reconcile", request, context=context)
                    if result["ok"]:
                        before = base.dump(db)
                        replay = self.run_command("reconcile", request, context=context)
                        self.assertTrue(replay["replayed"])
                        self.assertEqual(base.dump(db), before)
                    return result
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, keys))
            if keys[0] == keys[1]:
                self.assertTrue(all(result["ok"] for result in results), results)
                self.assertEqual(sum(result["replayed"] for result in results), 1)
                self.assertEqual(results[0] | {"replayed": True}, results[1] | {"replayed": True})
            else:
                self.assertEqual(sum(result["ok"] for result in results), 1, results)
                loser = next(result for result in results if not result["ok"])
                self.assertEqual(loser["error"]["code"], "stale_version", loser)
            db = connect(path)
            try:
                for table in ("related_task_assignments", "related_task_generations", "related_task_selector_reservations"):
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 6)
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                db.close()

    def test_physical_first_generation_race_has_one_reservation_set_and_replay(self):
        self.first_generation_race(("first-racer-a", "first-racer-b"))

    def test_same_command_first_generation_race_returns_one_creation_and_one_replay(self):
        self.first_generation_race(("same-first-racer", "same-first-racer"))
