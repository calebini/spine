"""Generated bindings cannot bypass recurring lifecycle through the v1 command."""

import unittest
from dataclasses import replace

from spine.commands import handle
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_migration import install_candidate
from spine.ledger.temporal_bindings import binding_view
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as helpers


class RecurringBindingGuardTests(unittest.TestCase):
    def setUp(self):
        helpers.RecurringTaskReconcileTests.setUpClass()
        self.h = helpers.RecurringTaskReconcileTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.rule = self.h.created()["result"]["rule"]
        self.initial = self.h.reconcile(self.rule)
        self.child = self.initial["result"]["results"][0]

    def request(self, operator=None):
        view = binding_view(self.db, self.child["after"]["temporal_binding_id"])
        inputs = dict(view["reconcile_inputs"])
        recurrence = load_current_recurrence_set(self.db, item_id=self.h.event["item_id"])
        inputs["source_recurrence_revision_id"] = recurrence["recurrence_revision_id"]
        request = {"contract_version": "spine.schedule-binding-reconcile.v1", "command_id": "direct-binding",
                   "actor_subject_id": "owner", "reconciled_at_utc": self.h.now, **inputs, "materialization": {"mode": "none"}}
        if operator:
            request["operator_resolution"] = operator
        return request

    def denied(self):
        before = base.dump(self.db)
        value = handle("schedule.binding.reconcile", self.request(), self.h.context)
        self.assertFalse(value["ok"], value)
        self.assertEqual((value["error"]["code"], value["error"]["field"]), ("semantic_conflict", "temporal_binding_id"))
        self.assertEqual(base.dump(self.db), before)

    def test_current_governed_binding_allows_read_proven_noop_and_replay(self):
        request = self.request()
        result = handle("schedule.binding.reconcile", request, self.h.context)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["resolution_outcome"], "source_unchanged")
        self.h.source_change()
        before = base.dump(self.db)
        replay = handle("schedule.binding.reconcile", request, self.h.context)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(replay["effect"], "schedule_binding_reconcile_replay")
        self.assertEqual(base.dump(self.db), before)

    def test_source_change_requires_assignment_reconcile_before_direct_maintenance(self):
        self.h.source_change()
        self.denied()
        self.h.reconcile(self.rule, "refresh-assignment")
        value = handle("schedule.binding.reconcile", self.request(), self.h.context)
        self.assertTrue(value["ok"], value)

    def test_archived_source_must_not_trigger_legacy_automatic_cancel(self):
        result = handle("item.archive", {"command_id": "archive-source", "actor_subject_id": "owner",
            "item_id": self.h.event["item_id"], "target_version": "1", "archived_at_utc": self.h.now}, self.h.context)
        self.assertTrue(result["ok"], result)
        self.denied()
        task = self.db.execute("SELECT task_status FROM task_details WHERE item_id=? AND version=1",
                               (self.child["after"]["task_item_id"],)).fetchone()[0]
        self.assertEqual(task, "open")

    def test_proved_source_cancel_and_exclusion_still_require_family_cause_witness(self):
        self.h.source_change(event_detail={"event_status": "cancelled"})
        self.denied()
        self.h.reconcile(self.rule, "family-cancel")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_source_cancellations").fetchone()[0], 6)

    def test_pending_material_adoption_blocks_old_binding_even_when_current(self):
        self.h.update_rule(self.rule, title="Collect Joe")
        self.denied()

    def test_pending_retirement_cleanup_blocks_old_binding(self):
        request = self.h.write("retire", self.h.rule(self.rule["related_task_rule_id"]), disposition="cancel_open")
        response = self.h.run_command("retire", request)
        self.assertTrue(response["ok"], response)
        self.denied()

    def test_keep_following_retirement_preserves_current_binding_maintenance(self):
        request = self.h.write("retire", self.h.rule(self.rule["related_task_rule_id"]), disposition="keep_following")
        self.assertTrue(self.h.run_command("retire", request)["ok"])
        result = handle("schedule.binding.reconcile", self.request(), self.h.context)
        self.assertTrue(result["ok"], result)

    def test_explicit_detach_survives_pending_adoption_and_prevents_regeneration(self):
        self.h.update_rule(self.rule, title="Collect Joe")
        request = self.request("detach_at_current_target")
        before = base.dump(self.db)
        preview = handle("schedule.binding.reconcile", request, replace(self.h.context, dry_run=True))
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(base.dump(self.db), before)
        result = handle("schedule.binding.reconcile", request, self.h.context)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["resolution_outcome"], "binding_detached")
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM related_task_dirty_rules").fetchone())
        repaired = self.h.reconcile(self.rule, "observe-detach")
        selected = next(r for r in repaired["result"]["results"] if r["assignment_id"] == self.child["assignment_id"])
        self.assertEqual(selected["reason"], "binding_detached")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_explicit_cancel_of_unresolved_source_is_manual_not_source_restorable(self):
        self.h.source_change(exdates=[self.h.excluded(self.child)])
        self.denied()
        request = self.request("cancel_target")
        result = handle("schedule.binding.reconcile", request, self.h.context)
        self.assertTrue(result["ok"], result)
        self.h.source_change(exdates=[])
        repaired = self.h.reconcile(self.rule, "observe-manual-cancel")
        selected = next(r for r in repaired["result"]["results"] if r["assignment_id"] == self.child["assignment_id"])
        self.assertEqual(selected["reason"], "task_manually_cancelled")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_source_cancellations").fetchone()[0], 0)

    def test_current_task_change_requires_exact_assignment_witness(self):
        self.h.edit_task(self.child["after"]["task_item_id"], "Personal title")
        self.denied()

    def test_ordinary_binding_on_candidate_ledger_keeps_v1_move_behavior(self):
        from tests import test_binding_successor_materialization as ordinary

        # Make the ordinary task before admitting the private schema; the guard
        # must not impose recurring-family lifecycle on an unrelated binding.
        h = ordinary.BindingSuccessorMaterializationTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        child = h.create()
        h.move("2026-08-23")
        install_candidate(h.db, disposable_test_ledger=True)
        response = handle("schedule.binding.reconcile", h.request(child), h.context)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["resolution_outcome"], "target_rescheduled")
        self.assertEqual(response["target_item_version"], "2")
