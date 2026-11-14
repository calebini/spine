"""Read-only automatic discovery with bounded independent lanes and root fairness."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger.recurring_task_invalidation import DirtyReason, mark
from spine.services.recurring_task_planning import DiscoveryLimits, discover
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


class RecurringDiscoveryTests(unittest.TestCase):
    def setUp(self):
        pages.RecurringTaskReconcileTests.setUpClass()
        self.h = pages.RecurringTaskReconcileTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.rule = self.h.created()["result"]["rule"]

    def plan(self, **kwargs):
        before, changes = base.dump(self.db), self.db.total_changes
        # Forbid writes, including writes that a preview might later roll back.
        self.db.execute("PRAGMA query_only=ON")
        try:
            result = discover(self.db, evaluated_at_utc=kwargs.pop("evaluated_at_utc", self.h.now), **kwargs)
        finally:
            self.db.execute("PRAGMA query_only=OFF")
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.db.total_changes, changes)
        return result

    def test_new_root_discovers_candidates_without_generating_or_receipting(self):
        first = self.plan().roots[0]
        self.assertEqual(len(first.occurrence_keys), 6)
        self.assertEqual(first.assignment_ids, ())
        self.assertIsNone(first.diagnostic)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 0)

    def test_retained_root_is_stable_across_idle_clock_ticks(self):
        self.h.reconcile(self.rule)
        first = self.plan().roots[0]
        for time in ("2026-08-07T18:00:01Z", "2026-08-07T18:01:00Z", "2026-08-07T19:00:00Z"):
            later = self.plan(evaluated_at_utc=time).roots[0]
            self.assertEqual(later, first)
        self.assertEqual(first.occurrence_keys, ())
        self.assertEqual(first.assignment_ids, ())

    def test_source_and_assignment_limits_are_independent(self):
        self.h.reconcile(self.rule, assignments="1", source_candidates="2")
        with self.db.atomic_command(write=True):
            mark(self.db, self.rule["related_task_rule_id"], DirtyReason.SOURCE)
        plan = self.plan(limits=DiscoveryLimits(assignments=1, source_candidates=1)).roots[0]
        self.assertEqual(len(plan.assignment_ids), 1)
        self.assertEqual(len(plan.occurrence_keys), 1)
        self.assertTrue(plan.assignments_more)
        self.assertTrue(plan.sources_more)

    def test_dirty_marker_and_fingerprint_change_but_discovery_never_acknowledges(self):
        self.h.reconcile(self.rule)
        prior = self.plan().roots[0]
        self.h.source_change()
        changed = self.plan().roots[0]
        self.assertNotEqual(prior.fingerprint, changed.fingerprint)
        self.assertEqual(len(changed.assignment_ids), 6)
        self.assertIsNotNone(changed.dirty_generation)
        self.assertEqual(self.plan().roots[0], changed)

    def test_pending_adoption_selects_maintenance_without_waiting_for_queue(self):
        self.h.reconcile(self.rule)
        self.h.update_rule(self.rule, title="Pickup changed")
        self.assertEqual(len(self.plan().roots[0].assignment_ids), 6)

    def test_retirement_selects_cleanup_and_never_new_generations(self):
        self.h.reconcile(self.rule, source_candidates="1")
        request = self.h.write("retire", self.h.rule(self.rule["related_task_rule_id"]), disposition="cancel_open")
        self.assertTrue(self.h.run_command("retire", request)["ok"])
        root = self.plan().roots[0]
        self.assertEqual(len(root.assignment_ids), 1)
        self.assertEqual(root.occurrence_keys, ())

    def test_source_budget_failure_keeps_the_maintenance_lane(self):
        self.h.reconcile(self.rule)
        self.h.source_change()
        root = self.plan(limits=DiscoveryLimits(proof_steps=1)).roots[0]
        self.assertIsNotNone(root.diagnostic)
        self.assertEqual(len(root.assignment_ids), 6)
        self.assertEqual(root.occurrence_keys, ())

    def test_round_robin_continues_past_dense_or_failed_roots(self):
        for key in ("second", "third"):
            self.assertTrue(self.h.run_command("create", self.h.request(key))["ok"])
        after, visited = None, []
        for _ in range(4):
            cycle = self.plan(after_root=after, limits=DiscoveryLimits(roots=1, proof_steps=1))
            self.assertEqual(len(cycle.roots), 1)
            self.assertIsNotNone(cycle.roots[0].diagnostic)
            visited.append(cycle.roots[0].rule_id)
            after = cycle.next_root_after
        self.assertEqual(len(set(visited[:3])), 3)
        self.assertEqual(visited[0], visited[3])

    def test_rollover_finds_new_source_without_a_dirty_marker(self):
        request = self.h.request("short-horizon")
        request["configuration"]["generation_horizon_seconds"] = "86400"
        created = self.h.run_command("create", request)
        self.assertTrue(created["ok"], created)
        identity = created["result"]["rule"]["related_task_rule_id"]
        first = next(p for p in self.plan().roots if p.rule_id == identity)
        second = next(p for p in self.plan(evaluated_at_utc="2026-08-08T00:00:00Z").roots if p.rule_id == identity)
        self.assertEqual(first.occurrence_keys, ())
        self.assertEqual(len(second.occurrence_keys), 1)
        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_overdue_unreserved_occurrences_are_not_backfilled(self):
        root = self.plan(evaluated_at_utc="2026-08-09T20:00:00Z").roots[0]
        self.assertEqual(len(root.occurrence_keys), 4)

    def test_cancelled_source_does_not_generate(self):
        self.h.source_change(event_detail={"event_status": "cancelled"})
        self.assertEqual(self.plan().roots[0].occurrence_keys, ())

    def test_invalid_limits_and_ambient_transaction_are_rejected(self):
        for bad in (0, True, 129):
            with self.assertRaises(SpineValidationError):
                discover(self.db, evaluated_at_utc=self.h.now, limits=replace(DiscoveryLimits(), roots=bad))
        with self.db.atomic_command(write=True), self.assertRaises(SpineValidationError):
            discover(self.db, evaluated_at_utc=self.h.now)

    def test_discovery_does_not_call_command_or_reconcile_preview(self):
        with patch("spine.commands.recurring_tasks.execute", side_effect=AssertionError("no command")), \
             patch("spine.services.recurring_task_reconcile.reconcile", side_effect=AssertionError("no preview")):
            self.plan()
