"""Candidate-only semantic planning and transaction-fenced automatic dispatch."""
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import recurring_task_automatic as auto
from spine.core.errors import SpineValidationError
from spine.ledger import connect
from spine.ledger.recurring_task_migration import attach_candidate
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as helpers


class AutomaticPageTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers.RecurringTaskReconcileTests()
        self.h.setUpClass()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.rule = self.h.created()["result"]["rule"]
        self.identity = self.rule["related_task_rule_id"]

    def request(self, key, **kwargs):
        return self.h.write(key, self.h.rule(self.identity), **({"limits": {}} | kwargs))

    def plan(self, request, **kwargs):
        before = base.dump(self.db), self.db.total_changes
        p = auto.plan(request, self.h.context, contracts=self.h.contracts, now=kwargs.get("now", self.h.now))
        self.assertEqual((base.dump(self.db), self.db.total_changes), before)
        return p

    def dispatch(self, p, request, **kwargs):
        return auto.dispatch(p, request, self.h.context, contracts=self.h.contracts, clock=kwargs.get("clock", lambda: self.h.now))

    def apply(self, key, **kwargs):
        req = self.request(key, **kwargs)
        p = self.plan(req)
        result = self.dispatch(p, req)
        self.assertEqual(result.status, "applied", (p, result.response))
        return result.response["result"]

    def test_create_retained_idle_and_manual_noop(self):
        initial = self.apply("create-page")
        self.assertEqual(len(initial["results"]), 6)
        for key in ("check-one", "check-two"):
            req = self.request(key)
            before = base.dump(self.db)
            p = self.plan(req)
            self.assertEqual([u.action for u in p.units], ["retained"] * 6)
            self.assertFalse(p.dispatchable)
            with patch.object(auto, "execute", side_effect=AssertionError("idle dispatched a command")):
                self.assertEqual(self.dispatch(p, req).status, "observed")
            self.assertEqual(base.dump(self.db), before)
        explicit = self.h.run_command("reconcile", self.request("manual"))
        self.assertFalse(explicit["changed"])
        self.assertIsNotNone(explicit["command_receipt_id"])

    def test_rechecks_source_and_due_and_request_under_writer(self):
        req = self.request("before")
        p = self.plan(req)
        for changed_req, time in ((req, "2026-08-08T19:30:00Z"), (req, "2026-08-07T17:59:59Z"),
                                  (req | {"limits": {"source_candidates": "2"}}, self.h.now)):
            before = base.dump(self.db)
            self.assertEqual(self.dispatch(p, changed_req, clock=lambda t=time: t).status, "stale_plan")
            self.assertEqual(base.dump(self.db), before)
        self.h.source_change()
        before = base.dump(self.db)
        self.assertEqual(self.dispatch(p, req).status, "stale_plan")
        self.assertEqual(base.dump(self.db), before)

    def test_signed_continuation_and_expiry(self):
        limits = {"source_candidates": "2"}
        first = self.apply("first", limits=limits)
        req = self.request("second", limits=limits, cursor=first["next_cursor"])
        p = self.plan(req)
        self.assertEqual(sum(u.action == "create" for u in p.units), 2)
        before = base.dump(self.db)
        expired = self.dispatch(p, req, clock=lambda: "2026-08-07T19:00:00Z")
        self.assertEqual(expired.response["error"]["code"], "stale_cursor")
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.dispatch(p, req).status, "applied")

    def test_delayed_added_date_and_copy_chain_under_bounded_automatic_pages(self):
        from tests.test_recurring_task_r2_edges import RecurringTaskEdges

        for fact, key in (("2026-08-20T18:00:00Z", "positive"), ("2027-01-01T18:00:00Z", "copy1"), ("2027-02-01T18:00:00Z", "copy2")):
            RecurringTaskEdges.add_date(self.h, fact, key)
        cursor, created = {}, []
        for i in range(5):
            result = self.apply("delayed-" + str(i), limits={"source_candidates": "2"}, **cursor)
            created.extend(u["selector"]["scheduled_fact"] for u in result["results"] if u["outcome"] == "created")
            if not result["has_more"]:
                break
            cursor = {"cursor": result["next_cursor"]}
        self.assertFalse(result["has_more"])
        self.assertEqual(created, [f"2026-08-{day:02}T18:00:00Z" for day in (*range(8, 14), 20)])

    def test_one_shot_coverage_and_post_retirement_idle(self):
        self.h.run_command("retire", self.h.write("retire-empty", self.rule, disposition="cancel_open"))
        req = self.request("coverage")
        p = self.plan(req)
        self.assertEqual(p.units, ())
        self.assertTrue(p.progress)
        self.assertEqual(self.dispatch(p, req).status, "applied")
        self.assertFalse(self.plan(self.request("now-idle")).dispatchable)

    def test_cancellation_and_reinstatement_match_real_generations(self):
        first = self.apply("generate")["results"][0]
        self.h.source_change(exdates=[self.h.excluded(first)])
        self.assertIn("cancelled", {u["outcome"] for u in self.apply("excluded")["results"]})
        self.h.source_change(exdates=[])
        req = self.request("reinstate")
        p = self.plan(req)
        self.assertIn("restore", [u.action for u in p.units])
        result = self.dispatch(p, req)
        self.assertEqual(result.status, "applied", result.response)
        successors = [u for u in result.response["result"]["results"] if u["outcome"] == "restored"]
        self.assertEqual([u["assignment_id"] for u in successors], [first["assignment_id"]])

    def test_unchanged_adoption_conflict_never_receipt_churns_and_edit_releases_it(self):
        first = self.apply("generate")["results"][0]["after"]["task_item_id"]
        self.h.edit_task(first, "My custom wording")
        self.h.update_rule(self.rule, title="Collect Joe")
        self.apply("adoption")
        for key in ("same-conflict", "still-conflicted"):
            p = self.plan(self.request(key))
            self.assertFalse(p.dispatchable, p)
            self.assertIn("decision_required", [u.action for u in p.units])
        self.h.edit_task(first, "Collect Joe")
        self.assertIsNone(self.apply("resolved")["rule"]["adoption_intent"])

    def reminder_rule(self, *, horizon=None):
        request = self.h.request("reminder")
        config = request["configuration"]
        config["notification_plan"] = {"mode": "explicit", "notification_profile_id": self.h.profile["notification_profile_id"],
                                       "revision_resolution": "current", "custom_additions": [], "rendering_applications": []}
        config["delivery"] = {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                              "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}}
        if horizon:
            config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": horizon,
                                         "opportunity_limit": "100"}
        self.identity = self.h.run_command("create", request)["result"]["rule"]["related_task_rule_id"]

    def test_newly_in_horizon_work_repairs_once_without_regenerating_task(self):
        self.reminder_rule(horizon="3600")
        generated = self.apply("tasks")
        self.assertFalse(generated["work"]["created"])
        self.h.now = "2026-08-08T19:00:00Z"
        req = self.request("eligible-reminder")
        p = self.plan(req)
        self.assertEqual([u.action for u in p.units if u.changed], ["repair_work"])
        outcome = self.dispatch(p, req)
        self.assertEqual(outcome.status, "applied", outcome.response)
        self.assertEqual(len(outcome.response["result"]["work"]["created"]), 1)
        self.assertFalse(self.plan(self.request("idle-again")).dispatchable)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_old_noop_receipt_is_never_reported_as_a_new_repair(self):
        self.reminder_rule(horizon="3600")
        self.apply("create-all")
        req = self.request("same-key")
        explicit = self.h.run_command("reconcile", req)
        self.assertFalse(explicit["changed"])
        self.h.now = "2026-08-08T19:00:00Z"
        p = self.plan(req)
        self.assertTrue(p.dispatchable)
        before = base.dump(self.db)
        replay = self.dispatch(p, req)
        self.assertEqual(replay.status, "replayed", replay.response)
        self.assertEqual(replay.response["command_receipt_id"], explicit["command_receipt_id"])
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(len(self.apply("fresh-key")["work"]["created"]), 1)

    def test_work_budget_stops_plan_at_whole_creation_and_retained_boundaries(self):
        self.reminder_rule(horizon="4838400")
        req = self.request("one-work", limits={"work_rows": "1"})
        p = self.plan(req)
        self.assertTrue(p.has_more)
        self.assertEqual([u.action for u in p.units], ["create"])
        first = self.dispatch(p, req)
        self.assertEqual(first.status, "applied", first.response)
        self.assertEqual(len(first.response["result"]["work"]["created"]), 1)
        self.apply("rest")
        p = self.plan(self.request("one-retained", limits={"work_rows": "1"}))
        self.assertEqual([u.action for u in p.units], ["retained"])
        self.assertTrue(p.has_more)

    def test_lease_after_observation_invalidates_cancellation_plan_without_touching_protected_work(self):
        from spine.ledger.work import start_work_instance

        self.reminder_rule(horizon="604800")
        generated = self.apply("cancel-setup")
        selected = generated["results"][0]
        wid = self.db.execute("SELECT work_instance_id FROM work_instances WHERE item_id=?",
                              (selected["after"]["task_item_id"],)).fetchone()[0]
        retired = self.h.run_command("retire", self.h.write("retire", self.h.rule(self.identity), disposition="cancel_open"))
        self.assertTrue(retired["ok"], retired)
        req = self.request("cancel-page")
        prior = self.plan(req)
        start_work_instance(self.db, work_instance_id=wid, started_at_utc=self.h.now)
        fresh = self.plan(req)
        self.assertEqual(prior.catalog_generation, fresh.catalog_generation)
        before = base.dump(self.db)
        self.assertEqual(self.dispatch(prior, req).status, "stale_plan")
        self.assertEqual(base.dump(self.db), before)
        result = self.dispatch(fresh, req)
        self.assertEqual(result.status, "applied", result.response)
        self.assertIn(wid, result.response["result"]["work"]["protected_stale"])

    def test_byte_bound_retaining_only_noop_prefix_never_commits_a_receipt(self):
        from spine.commands import recurring_tasks

        self.apply("only-first", limits={"source_candidates": "1"})
        # Inject the command-owned byte sizer only: isolate the branch where
        # the proposed child suffix fits the work budget but not the envelope.
        def size(**kwargs):
            return 2**30 if any(u["outcome"] == "created" for u in kwargs["result"]["results"]) else 1

        with patch.object(recurring_tasks, "response_sizer", return_value=size):
            # The first retained prefix really advances enrolled coverage once.
            self.apply("ack-real-prefix")
            req = self.request("no-fit")
            p = self.plan(req)
            self.assertEqual(p.units[0].action, "retained")
            self.assertTrue(p.dispatchable)
            before = base.dump(self.db)
            result = self.dispatch(p, req)
        self.assertEqual(result.status, "no_semantic_change", result.response)
        self.assertEqual(base.dump(self.db), before)

    def test_destination_change_without_catalog_bump_rejects_old_plan(self):
        self.reminder_rule()
        req = self.request("route")
        prior = self.plan(req)
        with self.db.atomic_command():
            self.db.execute("UPDATE delivery_targets SET status='inactive' WHERE delivery_target_id='owner-route'")
        blocked = self.plan(req)
        self.assertFalse(blocked.dispatchable, blocked)
        self.assertEqual({u.reason for u in blocked.units}, {"route_unavailable"})
        self.assertEqual(prior.catalog_generation, blocked.catalog_generation)
        before = base.dump(self.db)
        self.assertEqual(self.dispatch(prior, req).status, "stale_plan")
        self.assertEqual(base.dump(self.db), before)

    def test_proof_budget_and_context_fail_closed(self):
        req = self.request("bounded", limits={"proof_steps": "1"})
        before = base.dump(self.db)
        with self.assertRaisesRegex(SpineValidationError, "capacity_exceeded"):
            self.plan(req)
        ctx = replace(self.h.context, transport_metadata={"adapter": "web"})
        with self.assertRaisesRegex(SpineValidationError, "admission"):
            auto.plan(req, ctx, contracts=self.h.contracts, now=self.h.now)
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.db.execute("PRAGMA query_only").fetchone()[0], 0)

    def test_finalizer_cutoff_rolls_back_all_children(self):
        req = self.request("late-commit")
        p = self.plan(req)
        before = base.dump(self.db)
        clock = iter((self.h.now, "2026-08-08T19:30:00Z"))
        result = self.dispatch(p, req, clock=lambda: next(clock))
        self.assertEqual(result.response["error"]["code"], "stale_evaluation")
        self.assertEqual(base.dump(self.db), before)

    def test_competing_writer_cannot_change_plan_between_recheck_and_commit(self):
        req = self.request("locked")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.sqlite"
            db = connect(path)
            other = sqlite3.connect(path, timeout=0)
            try:
                self.db.backup(db)
                db.close()
                db = connect(path)
                attach_candidate(db)
                ctx = replace(self.h.context, ledger=db)
                p = auto.plan(req, ctx, contracts=self.h.contracts, now=self.h.now)
                original = auto.recheck

                def fenced(*args):
                    original(*args)
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        other.execute("BEGIN IMMEDIATE")

                with patch.object(auto, "recheck", side_effect=fenced) as guard:
                    result = auto.dispatch(p, req, ctx, contracts=self.h.contracts, clock=lambda: self.h.now)
                self.assertEqual(result.status, "applied", result.response)
                guard.assert_called_once()
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
            finally:
                other.close()
                db.close()
