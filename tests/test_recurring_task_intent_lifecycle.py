"""R2 intent/lifecycle integration on disposable ledgers; no public activation."""

import unittest

from spine.ledger import item_reads
from spine.ledger.recurrence import load_current_recurrence_set
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


class RecurringTaskIntentLifecycleTests(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    created = base.RecurringTaskCommandTests.created
    run_command = base.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    source_change = pages.RecurringTaskReconcileTests.source_change
    rule = pages.RecurringTaskReconcileTests.rule
    excluded = pages.RecurringTaskReconcileTests.excluded
    edit_task = pages.RecurringTaskReconcileTests.edit_task
    update_rule = pages.RecurringTaskReconcileTests.update_rule

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def selected(self, result, first):
        return next(row for row in result["result"]["results"] if row["assignment_id"] == first["assignment_id"])

    def move(self, first):
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        self.source_change(overrides=[{
            "segment_id": recurrence["segments"][0]["segment_id"], "target_occurrence_key": first["occurrence_key"],
            "target_occurrence_selector": first["selector"], "status": "active",
            "expressed_scheduled_fact": "2026-08-18T18:00:00Z", "reason_code": "move",
        }])

    def test_new_source_cancellation_resolves_adoption_as_terminal_without_an_extra_page(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        rule = self.update_rule(initial["result"]["rule"], title="Updated pickup")
        intent_id = rule["adoption_intent"]["intent_id"]
        self.source_change(exdates=[self.excluded(first)])
        result = self.reconcile(self.rule(rule["related_task_rule_id"]), "cancel-during-adoption")
        self.assertEqual(self.selected(result, first)["outcome"], "cancelled")
        self.assertIsNone(result["result"]["rule"]["adoption_intent"])
        outcome = self.db.execute("SELECT outcome FROM related_task_intent_outcomes WHERE intent_id=? AND assignment_id=?",
                                  (intent_id, first["assignment_id"])).fetchone()
        self.assertEqual(outcome[0], "skipped_terminal")
        self.assertEqual(item_reads.hydrated_item(self.db, first["after"]["task_item_id"])["version"]["title"], "Pick up Joe")

    def test_restoration_does_not_implicitly_adopt_pending_configuration(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "cancel")
        rule = self.update_rule(cancelled["result"]["rule"], title="New template")
        intent_id = rule["adoption_intent"]["intent_id"]
        self.source_change(exdates=[])
        result = self.reconcile(self.rule(rule["related_task_rule_id"]), "restore-with-intent")
        selected = self.selected(result, first)
        self.assertEqual(selected["outcome"], "restored")
        self.assertEqual(selected["after"]["adopted_rule_revision_id"], first["after"]["adopted_rule_revision_id"])
        self.assertEqual(item_reads.hydrated_item(self.db, selected["after"]["task_item_id"])["version"]["title"], "Pick up Joe")
        self.assertIsNone(result["result"]["rule"]["adoption_intent"])
        outcome = self.db.execute("SELECT outcome FROM related_task_intent_outcomes WHERE intent_id=? AND assignment_id=?",
                                  (intent_id, first["assignment_id"])).fetchone()
        self.assertEqual(outcome[0], "skipped_terminal")

    def test_overdue_skip_is_final_for_that_intent_even_if_source_moves_future(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first, second = initial["result"]["results"][:2]
        self.edit_task(second["after"]["task_item_id"], "Independent wording")
        rule = self.update_rule(initial["result"]["rule"], title="Desired wording")
        self.now = "2026-08-08T19:30:00Z"
        skipped = self.reconcile(rule, "skip-overdue")
        self.assertEqual(self.selected(skipped, first)["outcome"], "skipped_due")
        self.assertIsNotNone(skipped["result"]["rule"]["adoption_intent"])
        self.move(first)
        followed = self.reconcile(self.rule(rule["related_task_rule_id"]), "follow-after-skip")
        selected = self.selected(followed, first)
        self.assertEqual(selected["outcome"], "followed")
        self.assertEqual(selected["after"]["adopted_rule_revision_id"], first["after"]["adopted_rule_revision_id"])
        self.assertEqual(item_reads.hydrated_item(self.db, first["after"]["task_item_id"])["version"]["title"], "Pick up Joe")

    def test_existing_conflict_does_not_poison_generation_coverage_or_disappear_between_pages(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.edit_task(first["after"]["task_item_id"], "Independent wording")
        rule = self.update_rule(initial["result"]["rule"], title="Desired wording")
        cursor, results = None, []
        for index in range(10):
            request = self.write("reconcile", rule, limits={"assignments": "1"}) | {"command_id": f"coverage-{index}"}
            if cursor:
                request["cursor"] = cursor
            result = self.run_command("reconcile", request)
            self.assertTrue(result["ok"], result)
            results.append(result)
            rule, cursor = result["result"]["rule"], result["result"]["next_cursor"]
            if not result["result"]["has_more"]:
                break
        else:
            self.fail("bounded selection did not terminate")
        self.assertEqual(results[0]["result"]["results"][0]["outcome"], "decision_required")
        self.assertEqual(results[0]["result"]["coverage"]["generation"]["status"], "complete")
        self.assertEqual(results[-1]["result"]["coverage"]["adoption"]["status"], "decision_required")
        self.assertIsNotNone(rule["adoption_intent"])
        self.assertIsNone(cursor)

    def test_keep_following_reports_both_retirement_and_preserved_adoption_coverage(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.update_rule(initial["result"]["rule"], priority="high")
        retired = self.run_command("retire", self.write("retire", rule, disposition="keep_following"))
        self.assertTrue(retired["ok"], retired)
        result = self.reconcile(retired["result"]["rule"], "retired-adoption")
        self.assertEqual(result["result"]["coverage"]["adoption"]["status"], "complete")
        self.assertEqual(result["result"]["coverage"]["retirement"]["status"], "complete")
        self.assertEqual(result["result"]["coverage"]["retirement"]["processed_count"], "6")
        self.assertEqual(result["result"]["future_generation"], "rule_retired")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_new_assignments_above_adoption_high_water_do_not_inflate_intent_coverage(self):
        initial = self.reconcile(self.created()["result"]["rule"], source_candidates="1")
        rule = self.update_rule(initial["result"]["rule"], priority="high")
        self.assertEqual(rule["adoption_intent"]["assignment_high_water"], "1")
        result = self.reconcile(rule, "adopt-and-generate")
        self.assertEqual(result["result"]["coverage"]["adoption"]["processed_count"], "1")
        self.assertEqual(result["result"]["coverage"]["adoption"]["status"], "complete")
        self.assertEqual(result["result"]["coverage"]["generation"]["processed_count"], "5")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes").fetchone()[0], 1)

    def test_lifecycle_receipt_replay_preserves_all_rows_and_coverage(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        rule = self.update_rule(initial["result"]["rule"], title="Updated pickup")
        self.source_change(exdates=[self.excluded(first)])
        request = self.write("reconcile", self.rule(rule["related_task_rule_id"]), limits={}) | {"command_id": "lifecycle-replay"}
        result = self.run_command("reconcile", request)
        self.assertTrue(result["ok"], result)
        before = base.dump(self.db)
        replay = self.run_command("reconcile", request)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay, result | {"replayed": True})
        self.assertEqual(base.dump(self.db), before)
