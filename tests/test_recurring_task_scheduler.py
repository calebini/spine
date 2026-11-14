"""Candidate worker reconciliation on synthetic ledgers. Never install a send adapter."""
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from spine.adapters.tickerd import SpineTickerdWorkAdapter
from spine.commands import recurring_task_automatic as automatic
from spine.commands.recurring_task_scheduler import RecurringTaskSweep
from spine.runtime.storage_safety import LedgerDurabilityLatchedError, StorageSafetyLatch
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages
from tests.test_tickerd_adapter import TICKERD_AVAILABLE, cycle_envelope


@unittest.skipUnless(TICKERD_AVAILABLE, "Tickerd dependency required")
class RecurringWorkerTests(unittest.TestCase):
    def setUp(self):
        self.h = pages.RecurringTaskReconcileTests()
        self.h.setUpClass()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.restart()

    def restart(self):
        self.sweep = RecurringTaskSweep(self.h.context, self.h.contracts, "owner", clock=lambda: self.h.now)
        self.latch = StorageSafetyLatch()
        self.adapter = SpineTickerdWorkAdapter(self.db, runtime_mode="active", scheduler_actor_subject_id="owner",
                                              recurring_tasks=self.sweep, storage_safety_latch=self.latch)

    def tick(self, mode="active", batches=1):
        envelope = replace(cycle_envelope(), runtime_mode=mode, actual_start_ts=datetime.fromisoformat(self.h.now))
        return self.adapter.reconcile(envelope, max_batches=batches)

    def cycles(self, n):
        visits = []
        for _ in range(n):
            result = self.tick()
            self.assertTrue(result.ok, self.sweep.last_visit)
            visits.append(self.sweep.last_visit)
        return visits

    def count(self, table):
        return self.db.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def test_generation_restart_and_readonly_continuations(self):
        self.h.created()
        self.cycles(1)
        self.assertEqual(self.count("related_task_generations"), 2)
        from spine.ledger import connect
        from spine.ledger.recurring_task_migration import attach_candidate

        # Restore the synthetic committed image, then reopen it with a new
        # connection, adapter, safety latch and no in-memory bookmarks.
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "restart.sqlite"
        snapshot = connect(path)
        try:
            self.db.backup(snapshot)
        finally:
            snapshot.close()
        self.db = connect(path)
        self.addCleanup(self.db.close)
        attach_candidate(self.db)
        self.h.context = replace(self.h.context, ledger=self.db)
        self.restart()
        self.cycles(8)
        self.assertEqual(self.count("related_task_generations"), 6)
        self.assertEqual(self.count("related_task_dirty_rules"), 0)
        before = base.dump(self.db), self.db.total_changes
        with patch.object(automatic, "dispatch", side_effect=AssertionError("idle publication")):
            self.assertTrue(all(v.status == "observed" for v in self.cycles(8)))
        self.assertEqual((base.dump(self.db), self.db.total_changes), before)

    def test_competing_roots_each_reach_the_tail(self):
        identities = {self.h.created(k)["result"]["rule"]["related_task_rule_id"] for k in ("pickup", "pickup-next")}
        self.assertEqual({v.rule_id for v in self.cycles(4)}, identities)
        self.cycles(28)
        self.assertEqual(self.count("related_task_generations"), 12)
        self.assertEqual(self.count("related_task_dirty_rules"), 0)

    def test_clock_catchup_skips_past_due_pickups(self):
        self.h.created()
        self.h.now = "2026-08-10T18:15:00Z"
        self.cycles(8)
        self.assertEqual(self.count("related_task_generations"), 4)
        self.assertEqual(self.count("side_effect_attempts"), 0)

    def reminder_rule(self):
        req = self.h.request("reminders")
        req["configuration"].update(
            notification_plan={"mode": "explicit", "notification_profile_id": self.h.profile["notification_profile_id"],
                               "revision_resolution": "current", "custom_additions": [], "rendering_applications": []},
            delivery={"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                      "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}},
            materialization={"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "3600", "opportunity_limit": "100"})
        response = self.h.run_command("create", req)
        self.assertTrue(response["ok"], response)
        return response["result"]["rule"]["related_task_rule_id"]

    def test_unavailable_destination_zero_churn_then_worker_recovers(self):
        blocked = self.reminder_rule()
        self.h.created()
        with self.db.atomic_command():
            self.db.execute("UPDATE delivery_targets SET status='inactive' WHERE delivery_target_id='owner-route'")
        self.cycles(18)
        self.assertEqual(self.count("related_task_generations"), 6)
        before = base.dump(self.db), self.db.total_changes
        visits = self.cycles(10)
        self.assertTrue(any(v.rule_id == blocked and "route_unavailable" in v.reasons for v in visits))
        self.assertEqual((base.dump(self.db), self.db.total_changes), before)
        with self.db.atomic_command():
            self.db.execute("UPDATE delivery_targets SET status='active' WHERE delivery_target_id='owner-route'")
        self.cycles(20)
        self.assertEqual(self.count("related_task_generations"), 12)
        self.h.now = "2026-08-08T19:00:00Z"
        self.cycles(10)
        self.assertEqual(self.count("work_instances"), 1)
        self.assertEqual(self.count("side_effect_attempts"), 0)

    def test_source_edit_invalidates_cursor_and_only_rule_lane_cancels_and_restores(self):
        rule = self.h.created()["result"]["rule"]
        child = self.h.reconcile(rule, source_candidates="1")["result"]["results"][0]
        self.cycles(1)
        self.h.source_change(exdates=[self.h.excluded(child)])
        self.assertEqual(self.cycles(1)[0].status, "stale_plan")
        self.cycles(12)
        self.assertEqual(self.count("related_task_source_cancellations"), 1)
        self.h.source_change(exdates=[])
        self.cycles(12)
        self.assertEqual(self.count("related_task_generations"), 7)
        self.assertEqual(self.count("related_task_assignments"), 6)
        ordinary = self.db.execute("SELECT count(*) FROM command_receipts WHERE command='schedule.binding.reconcile'")
        self.assertEqual(ordinary.fetchone()[0], 0)

    def test_clean_short_horizon_does_not_walk_assignments_then_rolls_forward(self):
        req = self.h.request("short-horizon")
        req["configuration"]["generation_horizon_seconds"] = "86400"
        self.assertTrue(self.h.run_command("create", req)["ok"])
        self.cycles(3)
        self.assertEqual(self.count("related_task_generations"), 0)
        self.h.now = "2026-08-08T00:00:00Z"
        self.cycles(3)
        self.assertEqual(self.count("related_task_generations"), 1)
        with patch.object(automatic, "plan", side_effect=AssertionError("clean historical scan")):
            self.cycles(4)

    def test_conflicting_first_assignment_does_not_hide_later_adoptions(self):
        rule = self.h.created()["result"]["rule"]
        original = self.h.reconcile(rule)["result"]["results"]
        first = original[0]["after"]["task_item_id"]
        self.h.edit_task(first, "Keep my custom wording")
        self.h.update_rule(rule, title="Collect Joe")
        self.cycles(14)
        titles = [self.db.execute("SELECT v.title FROM coordination_items i JOIN coordination_item_versions v "
                                  "ON v.item_id=i.item_id AND v.version=i.current_version WHERE i.item_id=?",
                                  (unit["after"]["task_item_id"],)).fetchone()[0] for unit in original]
        self.assertEqual(titles, ["Keep my custom wording"] + ["Collect Joe"] * 5)
        before = base.dump(self.db), self.db.total_changes
        visits = self.cycles(8)
        self.assertTrue(any("configuration_conflict" in v.reasons for v in visits))
        self.assertEqual((base.dump(self.db), self.db.total_changes), before)
        self.h.edit_task(first, "Collect Joe")
        self.cycles(10)
        self.assertIsNone(self.h.rule(rule["related_task_rule_id"])["adoption_intent"])

    def test_bounded_work_page_past_unchanged_prefix(self):
        self.reminder_rule()
        # The ordinary horizon is deliberately narrower than the rule's window.
        self.adapter = replace(self.adapter, materialization_horizon_seconds=1)
        self.cycles(10)
        self.h.now = "2026-08-13T19:00:00Z"
        self.restart()
        self.adapter = replace(self.adapter, materialization_horizon_seconds=1)
        first = self.cycles(1)[0]
        self.assertEqual((first.status, self.count("work_instances")), ("observed", 0))
        self.cycles(6)
        self.assertEqual(self.count("work_instances"), 1)
        before = base.dump(self.db), self.db.total_changes
        self.cycles(8)
        self.assertEqual((base.dump(self.db), self.db.total_changes), before)

    def test_actor_and_protected_cursor_fail_before_work(self):
        from spine.core.errors import SpineValidationError

        before = base.dump(self.db)
        self.sweep.actor = "absent"
        with self.assertRaisesRegex(SpineValidationError, "scheduler_actor"):
            self.tick()
        self.sweep.actor = "owner"
        self.sweep.context = replace(self.h.context, facet_cursor_config=None)
        with self.assertRaisesRegex(SpineValidationError, "cursor_configuration"):
            self.tick()
        self.assertEqual(base.dump(self.db), before)

    def test_actor_deactivated_during_plan_stops_publication(self):
        self.h.created()
        original = automatic.dispatch

        def deactivate(*args, **kwargs):
            with self.db.atomic_command():
                self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='owner'")
            return original(*args, **kwargs)

        before = self.count("command_receipts")
        with patch.object(automatic, "dispatch", side_effect=deactivate):
            self.assertFalse(self.tick().ok)
        self.assertEqual(self.sweep.last_visit.reasons, ("environment_failure:scheduler_actor",))
        self.assertEqual(self.count("related_task_generations"), 0)
        self.assertEqual(self.count("command_receipts"), before)

    def test_over_budget_root_does_not_starve_another_series(self):
        identities = sorted(self.h.created(k)["result"]["rule"]["related_task_rule_id"] for k in ("one", "two"))
        original = automatic.plan
        error = sqlite3.OperationalError("interrupted")
        error.sqlite_errorcode = sqlite3.SQLITE_INTERRUPT

        def exhaust(request, *args, **kwargs):
            if request["related_task_rule_id"] == identities[0]:
                raise error
            return original(request, *args, **kwargs)

        with patch.object(automatic, "plan", side_effect=exhaust):
            self.assertFalse(self.tick().ok)
            self.assertEqual(self.sweep.last_visit.reasons, ("capacity_exceeded",))
            for _ in range(16):
                self.tick()
        self.assertFalse(self.latch.is_latched)
        self.assertEqual(self.count("related_task_generations"), 6)

    def test_ordinary_binding_still_reconciles_on_opted_in_worker(self):
        from spine.commands.facet_runtime import FacetCursorConfig
        from spine.ledger.identity import read_ledger_instance_id
        from spine.ledger.recurring_task_migration import install_candidate
        from tests import test_binding_successor_materialization as ordinary

        h = ordinary.BindingSuccessorMaterializationTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        child = h.create()
        h.move("2026-08-23")
        install_candidate(h.db, disposable_test_ledger=True)
        ctx = replace(h.context, facet_cursor_config=FacetCursorConfig(b"x" * 32, read_ledger_instance_id(h.db), "test"))
        self.adapter = replace(self.adapter, connection=h.db, recurring_tasks=RecurringTaskSweep(ctx, self.h.contracts, "owner"))
        result = self.tick()
        self.assertTrue(result.ok)
        self.assertEqual(h.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?",
                                      (child["task"]["item_id"],)).fetchone()[0], 2)

    def test_real_tickerd_kernel_owns_cadence(self):
        from tickerd import TickerdConfig
        from tickerd.kernel import RuntimeKernel

        self.h.created()
        kernel = RuntimeKernel(TickerdConfig(reconcile_interval_ms=60000, max_reconcile_batches_per_tick=1),
                               mode_reader=self.adapter, work_source=self.adapter, processor=self.adapter,
                               reconciler=self.adapter, event_sink=Mock())
        moment = datetime.fromisoformat(self.h.now)
        kernel.startup(moment)
        cycle = kernel.run_cycle(moment, moment)
        self.assertTrue(cycle["reconcile_ran"], cycle)
        self.assertEqual(kernel.health_state.value, "UP", cycle)
        self.assertEqual(self.count("related_task_generations"), 2)
        before = base.dump(self.db)
        self.assertFalse(kernel.run_cycle(moment, moment)["reconcile_ran"])
        self.assertEqual(base.dump(self.db), before)

    def test_inactive_or_stopped_never_plans(self):
        self.h.created()
        before = base.dump(self.db)
        with patch.object(automatic, "plan", side_effect=AssertionError("unsafe observation")):
            for mode in ("observe_only", "suspended"):
                self.assertEqual(self.tick(mode).items_scanned, 0)
            self.assertEqual(self.tick(batches=0).items_scanned, 0)
            self.latch.latch()
            with self.assertRaises(LedgerDurabilityLatchedError):
                self.tick()
        self.assertEqual(base.dump(self.db), before)

    def test_storage_latch_between_plan_and_writer_prevents_all_effects(self):
        self.h.created()
        before = base.dump(self.db)
        original = automatic.dispatch

        def stop(*args, **kwargs):
            self.latch.latch()
            return original(*args, **kwargs)

        with patch.object(automatic, "dispatch", side_effect=stop), \
             patch("spine.adapters.tickerd.materialize_notification_horizon", side_effect=AssertionError("ordinary work after stop")), \
             self.assertRaises(LedgerDurabilityLatchedError):
            self.tick()
        self.assertEqual(base.dump(self.db), before)

    def test_writer_disk_failure_reaches_existing_latch(self):
        self.h.created()
        before = base.dump(self.db)
        error = sqlite3.OperationalError("injected durability failure")
        error.sqlite_errorcode = sqlite3.SQLITE_FULL
        with patch.object(automatic, "recheck", side_effect=error), self.assertRaises(sqlite3.OperationalError) as caught:
            self.tick()
        self.assertIs(caught.exception, error)
        self.assertTrue(self.latch.is_latched)
        self.assertEqual(base.dump(self.db), before)
