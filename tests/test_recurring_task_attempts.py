"""Disposable ledgers exercise the final gate; no adapter or send is invoked."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger import connect, create_started_attempt
from spine.ledger.attempts import complete_side_effect_attempt
from spine.ledger.work import start_work_instance
from spine.services.attempts import prepare_work_attempt
from spine.services.notification_rendering import resolve_notification_rendering
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages
from tests import test_recurring_task_restoration as restoration


class RecurringAttemptTests(unittest.TestCase):
    def setUp(self):
        restoration.RecurringTaskRestorationTests.setUpClass()
        self.h = restoration.RecurringTaskRestorationTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        initial, self.child = self.h.authored()
        self.rule = initial["result"]["rule"]
        self.work = self.db.execute("SELECT work_instance_id FROM work_instances WHERE item_id=?",
                                    (self.child["after"]["task_item_id"],)).fetchone()[0]
        start_work_instance(self.db, work_instance_id=self.work, started_at_utc=self.h.now)

    def attempt(self, key="attempt", direct=False, **extra):
        operation = create_started_attempt if direct else prepare_work_attempt
        return operation(self.db, work_instance_id=self.work, adapter_name="capture", idempotency_key=key,
                         attempt_id=key, attempted_at_utc=self.h.now, request_envelope={"test": True}, **extra)

    def denied(self, *, direct=True):
        before = base.dump(self.db)
        with self.assertRaises(SpineValidationError) as error:
            self.attempt(direct=direct)
        self.assertEqual(error.exception.code, "stale_work_instance")
        self.assertEqual(base.dump(self.db), before)
        self.assertFalse(self.db.in_transaction)

    def test_current_work_is_admitted_under_write_transaction(self):
        from spine.ledger.recurring_task_attempts import assert_attempt_current

        def guard(db, work):
            self.assertTrue(db.in_transaction)
            assert_attempt_current(db, work)

        with patch("spine.ledger.recurring_task_attempts.assert_attempt_current", side_effect=guard) as checked:
            self.attempt()
        self.assertEqual(checked.call_count, 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 1)

    def test_source_change_without_due_change_is_refused_until_reconciled(self):
        self.h.source_change()
        self.denied()
        self.h.reconcile(self.rule, "fresh-source")
        self.attempt()

    def test_excluded_source_before_observer_refuses_without_cancelling_work(self):
        self.h.source_change(exdates=[self.h.excluded(self.child)])
        self.denied()
        self.assertEqual(self.db.execute("SELECT status FROM work_instances WHERE work_instance_id=?", (self.work,)).fetchone()[0],
                         "in_progress")

    def test_pending_material_adoption_blocks_current_work(self):
        pages.RecurringTaskReconcileTests.update_rule(self.h, self.rule, title="New pickup title")
        self.denied()

    def test_pending_cancel_cleanup_blocks(self):
        request = self.h.write("retire", self.h.rule(self.rule["related_task_rule_id"]), disposition="cancel_open")
        self.assertTrue(self.h.run_command("retire", request)["ok"])
        self.denied()

    def test_keep_following_retirement_still_admits_current_work(self):
        request = self.h.write("retire", self.h.rule(self.rule["related_task_rule_id"]), disposition="keep_following")
        self.assertTrue(self.h.run_command("retire", request)["ok"])
        self.attempt()

    def test_budget_exhaustion_fails_closed_without_writes(self):
        with patch("spine.ledger.recurring_task_attempts.verify_proof",
                   side_effect=SpineValidationError("source_continuity_unresolved", "budget")):
            self.denied()

    def test_retry_attempt_rechecks_but_already_started_outcome_can_complete(self):
        self.attempt()
        self.h.source_change(exdates=[self.h.excluded(self.child)])
        before = base.dump(self.db)
        with self.assertRaises(SpineValidationError):
            self.attempt("retry", direct=True)
        self.assertEqual(base.dump(self.db), before)
        complete_side_effect_attempt(self.db, attempt_id="attempt", attempt_status="succeeded", completed_at_utc=self.h.now)
        self.assertEqual(self.db.execute("SELECT attempt_status FROM side_effect_attempts").fetchone()[0], "succeeded")

    def test_source_change_between_optimistic_service_read_and_attempt_is_caught(self):
        from spine.ledger.work import assert_work_instance_not_stale

        def optimistic_read(db, identity):
            assert_work_instance_not_stale(db, identity)
            self.h.source_change()

        with (
            patch("spine.services.attempts.assert_work_instance_not_stale", side_effect=optimistic_read),
            self.assertRaises(SpineValidationError),
        ):
            self.attempt()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_joined_attempt_does_not_commit_caller_and_rolls_back_with_it(self):
        before = base.dump(self.db)
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.atomic_command(write=True):
            self.attempt(direct=True, manage_transaction=False)
            raise RuntimeError("rollback")
        self.assertEqual(base.dump(self.db), before)

    def test_unowned_attempt_cannot_disable_transaction_management(self):
        with self.assertRaises(SpineValidationError):
            self.attempt(direct=True, manage_transaction=False)
        self.assertFalse(self.db.in_transaction)

    def rendering(self):
        work = dict(self.db.execute("SELECT * FROM work_instances WHERE work_instance_id=?", (self.work,)).fetchone())
        return resolve_notification_rendering(self.db, work_row=work, attempt_id="attempt", attempted_at_utc=self.h.now)

    def test_rendered_attempt_is_guarded_and_replay_cannot_send_twice(self):
        rendering = self.rendering()
        first = self.attempt(notification_rendering=rendering)
        self.assertTrue(first.may_start_external_write)
        before = base.dump(self.db)
        replay = self.attempt(notification_rendering=rendering)
        self.assertFalse(replay.may_start_external_write)
        self.assertEqual(base.dump(self.db), before)

    def test_rendered_attempt_checks_pending_intent_before_persisting_rendering(self):
        rendering = self.rendering()
        pages.RecurringTaskReconcileTests.update_rule(self.h, self.rule, title="New pickup title")
        before = base.dump(self.db)
        with self.assertRaises(SpineValidationError) as error:
            self.attempt(notification_rendering=rendering)
        self.assertEqual(error.exception.code, "stale_work_instance")
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 0)

    def test_future_only_configuration_does_not_block_old_assignment(self):
        pages.RecurringTaskReconcileTests.update_rule(self.h, self.rule, title="Future pickup", scope="new_assignments_only")
        self.attempt()

    def test_individually_edited_task_needs_refreshed_witness(self):
        pages.RecurringTaskReconcileTests.edit_task(self.h, self.child["after"]["task_item_id"], "Custom title")
        self.denied()
        self.h.reconcile(self.rule, "observe-title")
        self.attempt()

    def test_explicitly_detached_child_is_independent_after_observation(self):
        from spine.ledger.temporal_bindings import retire_temporal_binding
        from spine.services.mutation_propagation import propagate

        identity = self.child["after"]["temporal_binding_id"]
        with self.db.atomic_command(write=True):
            retire_temporal_binding(self.db, temporal_binding_id=identity, command_id="detach", retired_at_utc=self.h.now)
            propagate(self.db, binding_id=identity)
        self.denied()
        self.h.reconcile(self.rule, "observe-detach")
        self.h.source_change(event_detail={"event_status": "cancelled"})
        self.attempt()

    def test_superseded_generation_cannot_start_another_attempt(self):
        self.h.source_change(exdates=[self.h.excluded(self.child)])
        self.h.reconcile(self.rule, "source-cancel")
        self.h.source_change(exdates=[])
        restored = self.h.reconcile(self.rule, "source-restore")
        self.assertTrue(any(v["outcome"] == "restored" for v in restored["result"]["results"]))
        self.denied()

    def test_writer_cannot_interleave_between_final_proof_and_attempt_insert(self):
        from spine.ledger.recurring_task_attempts import assert_attempt_current
        from spine.ledger.recurring_task_migration import attach_candidate

        with tempfile.TemporaryDirectory() as directory:
            primary = connect(Path(directory) / "attempt.sqlite")
            competing = None
            try:
                self.db.backup(primary)
                attach_candidate(primary)
                competing = sqlite3.connect(Path(directory) / "attempt.sqlite", timeout=0)

                def guard(db, work):
                    assert_attempt_current(db, work)
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        competing.execute("BEGIN IMMEDIATE")

                with patch("spine.ledger.recurring_task_attempts.assert_attempt_current", side_effect=guard):
                    create_started_attempt(primary, work_instance_id=self.work, adapter_name="capture", idempotency_key="locked",
                                           attempted_at_utc=self.h.now, request_envelope={}, attempt_id="locked")
                competing.execute("BEGIN IMMEDIATE")
                competing.rollback()
                self.assertEqual(primary.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 1)
            finally:
                if competing:
                    competing.close()
                primary.close()

    def test_owner_revision_mismatch_refuses_inside_attempt_transaction(self):
        # Fault injection remains inside a rollback-only disposable transaction;
        # it cannot bypass or leave an incomplete owner/history mutation.
        from spine.ledger.recurring_task_attempts import assert_attempt_current

        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.atomic_command(write=True):
            self.db.execute("UPDATE item_access_owners SET current_revision=current_revision+1 WHERE item_id=?",
                            (self.child["after"]["task_item_id"],))
            with self.assertRaises(SpineValidationError):
                assert_attempt_current(self.db, self.work)
            raise RuntimeError("rollback")
        self.attempt()
