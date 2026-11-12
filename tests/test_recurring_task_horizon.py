"""Finite-source proofs reuse recurrence semantics without historical expansion."""

import copy
import unittest
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.core.schedule import normalize_rule, rule_exhausted_before
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_sources import ProofBudget
from spine.services.recurring_task_horizon import source_exhausted
from spine.timezones import system_timezone_database_version
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


class RuleExhaustionTests(unittest.TestCase):
    def rule(self, *, end=None, frequency="DAILY", seed="2026-08-08T18:00:00Z", basis="instant_utc", **selectors):
        return normalize_rule({
            "frequency": frequency, "seed": seed, "start_bound": seed,
            "end_condition": end or {"kind": "count", "count": "6"}, **selectors,
        }, time_basis=basis)

    def test_count_and_until_are_inclusive_but_segment_end_is_exclusive(self):
        for end in ({"kind": "count", "count": "6"}, {"kind": "until", "until": "2026-08-13T18:00:00Z"}):
            with self.subTest(end=end):
                rule = self.rule(end=end)
                self.assertFalse(rule_exhausted_before(rule, boundary="2026-08-13T18:00:00Z", time_basis="instant_utc"))
                self.assertTrue(rule_exhausted_before(rule, boundary="2026-08-13T18:00:01Z", time_basis="instant_utc"))
        self.assertTrue(rule_exhausted_before(
            self.rule(), boundary="2026-08-10T18:00:00Z", time_basis="instant_utc", segment_end="2026-08-10T18:00:00Z",
        ))

    def test_segment_start_count_and_invalid_monthly_dates_use_expansion_semantics(self):
        self.assertFalse(rule_exhausted_before(
            self.rule(), boundary="2026-08-14T18:00:00Z", time_basis="instant_utc", segment_start="2026-08-10T18:00:00Z",
        ))
        self.assertTrue(rule_exhausted_before(
            self.rule(), boundary="2026-08-16T18:00:00Z", time_basis="instant_utc", segment_start="2026-08-10T18:00:00Z",
        ))
        monthly = self.rule(frequency="MONTHLY", seed="2026-01-31T18:00:00Z", end={"kind": "count", "count": "3"})
        self.assertFalse(rule_exhausted_before(monthly, boundary="2026-04-01T00:00:00Z", time_basis="instant_utc"))
        self.assertTrue(rule_exhausted_before(monthly, boundary="2026-06-01T00:00:00Z", time_basis="instant_utc"))

    def test_nonexistent_local_candidate_does_not_consume_count(self):
        rule = self.rule(seed="2026-03-07T02:30:00", basis="local_instant", end={"kind": "count", "count": "2"})
        kwargs = {"time_basis": "local_instant", "timezone": "America/New_York",
                  "timezone_database_version": system_timezone_database_version()}
        self.assertFalse(rule_exhausted_before(rule, boundary="2026-03-09T02:30:00", **kwargs))
        self.assertTrue(rule_exhausted_before(rule, boundary="2026-03-10T02:30:00", **kwargs))

    def test_old_daily_count_is_arithmetic_and_unbounded_is_not_exhausted(self):
        with patch("spine.core.schedule._active_periods", side_effect=AssertionError("must not expand history")):
            self.assertTrue(rule_exhausted_before(
                self.rule(seed="1900-01-01T12:00:00Z"), boundary="2026-09-01T00:00:00Z", time_basis="instant_utc",
            ))
            self.assertFalse(rule_exhausted_before(
                self.rule(seed="1900-01-01T12:00:00Z", end={"kind": "unbounded"}),
                boundary="2026-09-01T00:00:00Z", time_basis="instant_utc",
            ))

    def test_sparse_yearly_rule_is_not_exhausted_between_valid_candidates(self):
        rule = self.rule(frequency="YEARLY", seed="2024-02-29T18:00:00Z", end={"kind": "count", "count": "2"})
        self.assertFalse(rule_exhausted_before(rule, boundary="2027-09-01T00:00:00Z", time_basis="instant_utc"))
        self.assertFalse(rule_exhausted_before(rule, boundary="2028-02-29T18:00:00Z", time_basis="instant_utc"))
        self.assertTrue(rule_exhausted_before(rule, boundary="2028-03-01T00:00:00Z", time_basis="instant_utc"))


class RecurringTaskHorizonTests(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    created = base.RecurringTaskCommandTests.created
    run_command = base.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    source_change = pages.RecurringTaskReconcileTests.source_change
    rule = pages.RecurringTaskReconcileTests.rule

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def test_elapsed_finite_source_reports_exhausted_without_polling_progress(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        self.assertEqual(initial["result"]["future_generation"], "waiting")
        progress = tuple(self.db.execute("SELECT * FROM related_task_rule_progress").fetchone())
        audit_count = self.db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        self.now = "2026-09-01T00:00:00Z"
        for key in ("exhausted-once", "exhausted-twice"):
            result = self.reconcile(initial["result"]["rule"], key)
            self.assertEqual(result["result"]["future_generation"], "source_exhausted")
            self.assertFalse(result["changed"])
            self.assertFalse(result["result"]["has_more"])
            self.assertEqual(tuple(self.db.execute("SELECT * FROM related_task_rule_progress").fetchone()), progress)
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], audit_count)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_future_rdate_and_moved_override_prevent_premature_exhaustion(self):
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        segment = recurrence["segments"][0]["segment_id"]
        for field, value in (
            ("rdates", {"status": "active", "segment_id": segment, "scheduled_fact": "2027-01-01T18:00:00Z"}),
            ("overrides", {"status": "active", "segment_id": segment, "expressed_scheduled_fact": "2027-01-01T18:00:00Z"}),
        ):
            with self.subTest(field=field):
                projected = copy.deepcopy(recurrence)
                projected[field] = [value]
                self.assertFalse(source_exhausted(projected, "2026-09-01T00:00:00Z", ProofBudget()))
                value["status"] = "superseded"
                self.assertTrue(source_exhausted(projected, "2026-09-01T00:00:00Z", ProofBudget()))

    def test_actual_moved_source_beyond_horizon_remains_waiting(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        self.source_change(overrides=[{
            "segment_id": recurrence["segments"][0]["segment_id"], "target_occurrence_key": first["occurrence_key"],
            "target_occurrence_selector": first["selector"], "status": "active",
            "expressed_scheduled_fact": "2027-01-01T18:00:00Z", "reason_code": "move",
        }])
        self.now = "2026-09-01T00:00:00Z"
        result = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "future-move")
        self.assertEqual(result["result"]["future_generation"], "waiting")
        self.assertEqual(result["result"]["results"][0]["outcome"], "followed")

    def test_exhaustion_proof_is_read_only_and_budgeted(self):
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        before = base.dump(self.db)
        with self.assertRaises(SpineValidationError):
            source_exhausted(recurrence, "2026-09-01T00:00:00Z", ProofBudget(1))
        self.assertTrue(source_exhausted(recurrence, "2026-09-01T00:00:00Z", ProofBudget(10)))
        self.assertEqual(base.dump(self.db), before)

    def test_local_source_and_moved_label_use_the_pinned_zone(self):
        recurrence = copy.deepcopy(load_current_recurrence_set(self.db, item_id=self.event["item_id"]))
        recurrence.update(time_basis="local_instant", timezone="America/New_York",
                          timezone_database_version=system_timezone_database_version())
        for segment in recurrence["segments"]:
            segment["active_start"] = segment["active_start"].removesuffix("Z")
        for rule in recurrence["rules"]:
            rule["seed"] = rule["seed"].removesuffix("Z")
            rule["start_bound"] = rule["start_bound"].removesuffix("Z")
        # The sixth daily candidate is 18:00 local / 22:00 UTC, not 18:00 UTC.
        self.assertFalse(source_exhausted(recurrence, "2026-08-13T22:00:00Z", ProofBudget()))
        self.assertTrue(source_exhausted(recurrence, "2026-08-13T22:00:01Z", ProofBudget()))
        recurrence["overrides"] = [{
            "status": "active", "segment_id": recurrence["segments"][0]["segment_id"],
            "expressed_scheduled_fact": "2026-09-01T00:00:00",
        }]
        self.assertFalse(source_exhausted(recurrence, "2026-09-01T04:00:00Z", ProofBudget()))
        self.assertTrue(source_exhausted(recurrence, "2026-09-01T04:00:01Z", ProofBudget()))
