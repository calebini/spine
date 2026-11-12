"""R2 intent/lifecycle integration on disposable ledgers; no public activation."""

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.ledger import connect, item_reads
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_migration import attach_candidate
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

    def route(self, target):
        result = handle("delivery_target.upsert", {
            "command_id": "route-" + target, "actor_subject_id": "owner", "delivery_target_id": "owner-route",
            "owner_kind": "subject", "owner_subject_id": "owner", "channel": "test", "adapter_name": "capture",
            "target_ref": target, "updated_at_utc": self.now,
        }, self.context)
        self.assertTrue(result["ok"], result)

    def reminder_adoption(self, rule):
        config = self.request()["configuration"]
        config["generation_horizon_seconds"] = "4838400"
        config["notification_plan"] = {
            "mode": "explicit", "notification_profile_id": self.profile["notification_profile_id"],
            "revision_resolution": "current", "custom_additions": [], "rendering_applications": [],
        }
        config["delivery"] = {
            "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        updated = self.run_command("update", self.write("update", rule, configuration=config, adoption_scope="upcoming_open"))
        self.assertTrue(updated["ok"], updated)
        return updated["result"]["rule"]

    def assignment_state(self, assignment):
        from spine.ledger.recurring_tasks import read_record

        root = read_record(self.db, "related_task_assignments", assignment["assignment_id"])
        return read_record(self.db, "related_task_assignment_revisions", root["current_assignment_revision_id"])["state_json"]

    def test_changed_route_records_conflicts_and_recovers_without_partial_child_writes(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.reminder_adoption(initial["result"]["rule"])
        intent = rule["adoption_intent"]["intent_id"]
        self.route("test://changed-never-send")
        blocked = self.reconcile(rule, "blocked-route")
        self.assertEqual(blocked["result"]["coverage"]["adoption"]["status"], "decision_required")
        for result in blocked["result"]["results"]:
            self.assertEqual((result["outcome"], result["reason"]), ("decision_required", "route_unavailable"))
            state = self.assignment_state(result)
            self.assertEqual((state["disposition"], state["pending_intent_id"]), ("decision_required", intent))
            self.assertEqual(result["after"]["task_item_version"], "1")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes WHERE outcome='conflict'").fetchone()[0], 6)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0], 0)
        state_count = self.db.execute("SELECT COUNT(*) FROM related_task_assignment_revisions").fetchone()[0]
        repeated = self.reconcile(blocked["result"]["rule"], "blocked-route-again")
        self.assertFalse(repeated["changed"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_assignment_revisions").fetchone()[0], state_count)
        self.route("test://never-send")
        recovered = self.reconcile(blocked["result"]["rule"], "recovered-route")
        self.assertIsNone(recovered["result"]["rule"]["adoption_intent"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes WHERE outcome='conflict'").fetchone()[0], 6)
        self.assertEqual(len(recovered["result"]["policy_mappings"]), 6)
        links = self.db.execute(
            "SELECT notification_profile_application_policy_id FROM notification_profile_application_policies"
        ).fetchall()
        self.assertEqual(len({row[0] for row in links}), 6)
        self.assertEqual({row[0] for row in self.db.execute("SELECT created_by_command_id FROM notification_profile_applications")},
                         {"recovered-route"})

    def test_blocked_unit_evidence_obeys_mutation_budget_and_preview_rollback(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.reminder_adoption(initial["result"]["rule"])
        self.route("test://changed-never-send")
        request = self.write("reconcile", rule, limits={"mutations": "1"}) | {"command_id": "blocked-budget"}
        before = base.dump(self.db)
        preview = self.run_command("reconcile", request, context=replace(self.context, dry_run=True))
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(base.dump(self.db), before)
        for stage in ("audit", "receipt"):
            def fault(actual, expected=stage):
                if actual == expected:
                    raise RuntimeError("blocked-state rollback probe")
            with self.assertRaisesRegex(RuntimeError, "blocked-state rollback probe"):
                self.run_command("reconcile", request, fault=fault)
            self.assertEqual(base.dump(self.db), before)
        result = self.run_command("reconcile", request)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["result"]["results"]), 1)
        self.assertTrue(result["result"]["has_more"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes").fetchone()[0], 1)

    def test_blocked_unit_byte_boundary_rolls_back_its_state_and_outcome_together(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.reminder_adoption(initial["result"]["rule"])
        self.route("test://changed-never-send")
        full = self.run_command("reconcile", self.write("reconcile", rule, limits={}), context=replace(self.context, dry_run=True))
        self.assertTrue(full["ok"], full)
        cap = len(canonical_json_bytes(full)) * 3 // 4
        result = self.reconcile(rule, "blocked-byte-cap", response_bytes=str(cap))
        self.assertLessEqual(len(canonical_json_bytes(result)), cap)
        self.assertTrue(result["result"]["has_more"])
        count = len(result["result"]["results"])
        self.assertGreater(count, 0)
        self.assertLess(count, 6)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes").fetchone()[0], count)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_assignment_revisions").fetchone()[0], 6 + count)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0], 0)

    def test_disclosure_rejection_records_conflict_without_adopting_or_touching_task(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.update_rule(initial["result"]["rule"], priority="high")
        with patch("spine.services.recurring_task_children.change",
                   side_effect=SpineValidationError("rendering_disclosure_unavailable", "controlled boundary failure")):
            result = self.reconcile(rule, "disclosure-boundary")
        self.assertEqual(result["result"]["coverage"]["adoption"]["status"], "decision_required")
        self.assertEqual({row["reason"] for row in result["result"]["results"]}, {"disclosure_unavailable"})
        for row in result["result"]["results"]:
            self.assertEqual(row["after"]["adopted_rule_revision_id"], row["before"]["adopted_rule_revision_id"])
            self.assertEqual(row["after"]["task_item_version"], row["before"]["task_item_version"])
            self.assertEqual(self.assignment_state(row)["reason"], "disclosure_unavailable")
        recovered = self.reconcile(result["result"]["rule"], "disclosure-recovered")
        self.assertIsNone(recovered["result"]["rule"]["adoption_intent"])

    def test_cancel_retirement_cannot_complete_over_an_ownership_conflict(self):
        from spine.ledger.items import create_next_item_version

        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        task = first["after"]["task_item_id"]
        # Synthetic historical owner revision, not a new public transfer command.
        # The owner identity stays the same but the exact creation witness drifts.
        with self.db:
            self.db.execute(
                "INSERT INTO item_access_owner_revisions SELECT item_id,item_access_owner_id,2,owner_kind,"
                "owner_subject_id,owner_group_id,creator_entitlement_subject_id,created_by_command_id,"
                "changed_at_utc,changed_by_subject_id,command_receipt_id FROM item_access_owner_revisions WHERE item_id=?",
                (task,),
            )
            self.db.execute("UPDATE item_access_owners SET current_revision=2 WHERE item_id=?", (task,))
        retired = self.run_command("retire", self.write("retire", initial["result"]["rule"], disposition="cancel_open"))
        self.assertTrue(retired["ok"], retired)
        result = self.reconcile(retired["result"]["rule"], "retirement-owner-conflict")
        self.assertEqual(self.selected(result, first)["outcome"], "decision_required")
        self.assertEqual(result["result"]["rule"]["retirement_intent"]["status"], "pending")
        self.assertEqual(result["result"]["coverage"]["retirement"]["status"], "decision_required")
        self.assertEqual(item_reads.hydrated_item(self.db, task)["detail"]["task_status"], "open")
        with self.db.atomic_command(write=True):
            create_next_item_version(
                self.db, item_id=task, target_version=1, supporting_command_id="manual-owner-done",
                created_by_subject_id="owner", created_at_utc=self.now,
                task_detail={"task_status": "done", "completed_at_utc": self.now, "completed_by_subject_id": "owner"},
            )
        resolved = self.reconcile(result["result"]["rule"], "retirement-terminal-resolution")
        self.assertEqual(resolved["result"]["rule"]["retirement_intent"]["status"], "complete")
        self.assertEqual(self.db.execute("SELECT outcome FROM related_task_intent_outcomes WHERE assignment_id=?",
                                         (first["assignment_id"],)).fetchone()[0], "conflict")

    def test_existing_adoption_conflict_resolves_when_source_cancels(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.edit_task(first["after"]["task_item_id"], "Independent wording")
        rule = self.update_rule(initial["result"]["rule"], title="Desired wording")
        blocked = self.reconcile(rule, "conflict-before-cancel")
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(rule["related_task_rule_id"]), "cancel-conflict")
        self.assertEqual(self.selected(cancelled, first)["outcome"], "cancelled")
        self.assertIsNotNone(blocked["result"]["rule"]["adoption_intent"])
        self.assertIsNone(cancelled["result"]["rule"]["adoption_intent"])
        self.assertEqual(self.db.execute("SELECT outcome FROM related_task_intent_outcomes WHERE assignment_id=?",
                                         (first["assignment_id"],)).fetchone()[0], "conflict")

    def test_resolved_conflict_skip_stays_final_through_restoration_while_other_conflict_remains(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first, second = initial["result"]["results"][:2]
        for row in (first, second):
            self.edit_task(row["after"]["task_item_id"], "Independent wording")
        rule = self.update_rule(initial["result"]["rule"], title="Desired wording")
        self.reconcile(rule, "two-conflicts")
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(rule["related_task_rule_id"]), "resolve-first-by-cancel")
        self.assertIsNotNone(cancelled["result"]["rule"]["adoption_intent"])
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(rule["related_task_rule_id"]), "restore-resolved-conflict")
        successor = self.selected(restored, first)
        self.assertEqual(successor["outcome"], "restored")
        self.edit_task(second["after"]["task_item_id"], "Desired wording")
        resolved = self.reconcile(restored["result"]["rule"], "resolve-second-conflict")
        self.assertIsNone(resolved["result"]["rule"]["adoption_intent"])
        self.assertEqual(item_reads.hydrated_item(self.db, successor["after"]["task_item_id"])["version"]["title"], "Independent wording")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes WHERE outcome='conflict'").fetchone()[0], 2)

    def test_overdue_resolution_of_prior_conflict_is_not_reopened_after_a_move(self):
        from spine.ledger.recurring_task_sources import ProofBudget
        from spine.ledger.recurring_tasks import read_record
        from spine.services.recurring_task_adoption import resolved as resolved_intent

        initial = self.reconcile(self.created()["result"]["rule"])
        first, second = initial["result"]["results"][:2]
        for row in (first, second):
            self.edit_task(row["after"]["task_item_id"], "Independent wording")
        rule = self.update_rule(initial["result"]["rule"], title="Desired wording")
        blocked = self.reconcile(rule, "conflicts-before-overdue")
        self.now = "2026-08-08T19:30:00Z"
        skipped = self.reconcile(blocked["result"]["rule"], "resolve-overdue-conflict")
        self.assertEqual(self.selected(skipped, first)["outcome"], "skipped_due")
        self.move(first)
        followed = self.reconcile(self.rule(rule["related_task_rule_id"]), "follow-resolved-overdue")
        self.assertEqual(self.selected(followed, first)["outcome"], "followed")
        before = base.dump(self.db)
        with self.db.atomic_command(write=True):
            assignment = read_record(self.db, "related_task_assignments", first["assignment_id"])
            intent = followed["result"]["rule"]["adoption_intent"]
            with self.assertRaises(SpineValidationError):
                resolved_intent(self.db, assignment, intent, budget=ProofBudget(1))
            self.assertTrue(resolved_intent(self.db, assignment, intent, budget=ProofBudget(32)))
        self.assertEqual(base.dump(self.db), before)
        self.edit_task(second["after"]["task_item_id"], "Desired wording")
        resolved = self.reconcile(followed["result"]["rule"], "resolve-last-overdue-conflict")
        self.assertIsNone(resolved["result"]["rule"]["adoption_intent"])
        self.assertEqual(item_reads.hydrated_item(self.db, first["after"]["task_item_id"])["version"]["title"], "Independent wording")

    def test_physical_adoption_retirement_race_serializes_and_replays_only_winner(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.update_rule(initial["result"]["rule"], priority="high")
        intent_id = rule["adoption_intent"]["intent_id"]
        requests = {
            "reconcile": self.write("reconcile", rule, limits={}) | {"command_id": "race-adopt"},
            "retire": self.write("retire", rule, disposition="cancel_open") | {"command_id": "race-retire"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "adoption-retirement.sqlite")
            target = connect(path)
            self.db.backup(target)
            target.close()
            barrier = threading.Barrier(2)

            def run(name):
                db = connect(path)
                try:
                    attach_candidate(db)
                    context = replace(self.context, ledger=db)
                    barrier.wait(timeout=10)
                    result = self.run_command(name, requests[name], context=context)
                    if result["ok"]:
                        before = base.dump(db)
                        replay = self.run_command(name, requests[name], context=context)
                        self.assertEqual(replay, result | {"replayed": True})
                        self.assertEqual(base.dump(db), before)
                    return name, result
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(run, name) for name in requests]
                outcomes = [job.result(timeout=20) for job in jobs]
            self.assertEqual(sum(result["ok"] for _, result in outcomes), 1, outcomes)
            loser = next(result for _, result in outcomes if not result["ok"])
            self.assertEqual(loser["error"]["code"], "stale_version", loser)
            winner = next(name for name, result in outcomes if result["ok"])
            db = connect(path)
            try:
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                status = db.execute("SELECT status FROM related_task_intents WHERE intent_id=?", (intent_id,)).fetchone()[0]
                self.assertEqual(status, "complete" if winner == "reconcile" else "superseded")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes").fetchone()[0],
                                 6 if winner == "reconcile" else 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)
            finally:
                db.close()

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
