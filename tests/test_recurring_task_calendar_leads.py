"""Pinned calendar-lead proofs and actual disposable-ledger child composition."""

import copy
import struct
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from spine import timezones
from spine.commands import core, handle
from spine.core.errors import SpineValidationError
from spine.core.notifications import _resolve_boundary
from spine.ledger.recurrence import load_current_recurrence_set
from spine.services.recurring_task_leads import validate_reminder_lead
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


def calendar(days=-1, clock="09:00:00", **zone):
    return {"kind": "target_offset", "offset_basis": "calendar_days", "offset_days": str(days), "local_time": clock, **zone}


def elapsed(seconds):
    return {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": str(seconds)}


def configuration(schedule, *, horizon=4838400, offset=5400):
    return {"offset_seconds": str(offset), "generation_horizon_seconds": str(horizon),
            "notification_plan": {"resolved": {"effective_templates": [{"template": {"schedule": schedule}}]}}}


class CalendarLeadProofTests(unittest.TestCase):
    def setUp(self):
        self.version = timezones.system_timezone_database_version()
        self.utc = {"time_basis": "instant_utc"}
        self.local = {"time_basis": "local_instant", "timezone": "America/New_York", "timezone_database_version": self.version}

    def test_utc_bound_equality_task_offset_and_no_timezone_work_for_elapsed(self):
        schedule = {"kind": "once", "at": calendar()}
        lead = 86400 + 86399 - 9 * 3600 - 5400
        validate_reminder_lead(configuration(schedule, horizon=lead), self.utc)
        with self.assertRaisesRegex(SpineValidationError, "horizon"):
            validate_reminder_lead(configuration(schedule, horizon=lead - 1), self.utc)
        with patch("spine.services.recurring_task_leads.timezone_offset_bounds", side_effect=AssertionError("elapsed is timezone-free")):
            validate_reminder_lead(configuration({"kind": "once", "at": elapsed(-600)}, horizon=1), self.utc)

    def test_calendar_same_zone_window_order_and_mixed_window_proof(self):
        def window(start, stop):
            return {"kind": "repeat_window", "start": start, "stop": stop}
        validate_reminder_lead(configuration(window(calendar(), calendar(clock="10:00:00"))), self.local)
        validate_reminder_lead(configuration(window(calendar(-2), elapsed(-600))), self.local)
        for start, stop in ((calendar(clock="10:00:00"), calendar()), (calendar(), calendar()),
                            (calendar(0), elapsed(-600)), (elapsed(-600), elapsed(-600))):
            with self.subTest(start=start, stop=stop), self.assertRaisesRegex(SpineValidationError, "ordering"):
                validate_reminder_lead(configuration(window(start, stop)), self.local)

    def test_offsets_use_earliest_enabled_boundary_and_reject_absolute(self):
        schedule = {"kind": "offsets", "at": [elapsed(-600), calendar(-10)]}
        with self.assertRaisesRegex(SpineValidationError, "horizon"):
            validate_reminder_lead(configuration(schedule, horizon=86400), self.local)
        validate_reminder_lead(configuration(schedule), self.local)
        with self.assertRaisesRegex(SpineValidationError, "cannot be proved"):
            validate_reminder_lead(configuration({"kind": "once", "at": {"kind": "absolute_utc", "at_utc": base.NOW}}), self.utc)

    def test_bound_contains_real_resolutions_across_dst_date_lines_and_task_rollover(self):
        for task_zone in ("UTC", "America/New_York", "Pacific/Apia", "Australia/Lord_Howe"):
            target_min, _ = timezones.timezone_offset_bounds(task_zone, self.version)
            for reminder_zone in (task_zone, "Pacific/Kiritimati"):
                _, reminder_max = timezones.timezone_offset_bounds(reminder_zone, self.version)
                boundary = calendar(timezone=reminder_zone, timezone_database_version=self.version)
                for offset in (-90000, 5400, 90000):
                    horizon = 86400 + 86399 - 32400 - target_min + reminder_max - offset
                    source = {"time_basis": "local_instant", "timezone": task_zone, "timezone_database_version": self.version}
                    validate_reminder_lead(configuration({"kind": "once", "at": boundary}, horizon=horizon, offset=offset), source)
                    for stamp in ("2011-12-30T08:00:00+00:00", "2026-03-08T08:00:00+00:00", "2026-11-01T07:00:00+00:00",
                                  "2500-04-04T12:00:00+00:00"):
                        start = datetime.fromisoformat(stamp)
                        due = start + timedelta(seconds=offset)
                        local_day = due.astimezone(timezones.timezone_for_version(task_zone, self.version)).date().isoformat()
                        target = {"target_utc_instant": due.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "target_local_date": local_day,
                                  "timezone": task_zone, "timezone_database_version": self.version}
                        reminder = _resolve_boundary(boundary, target)
                        if reminder is not None:
                            self.assertLessEqual((start - reminder).total_seconds(), horizon)

    def test_gap_omission_and_earliest_fold_are_still_notification_owned(self):
        target = {"target_local_date": "2026-03-09", "target_utc_instant": "2026-03-09T15:00:00Z",
                  "timezone": "America/New_York", "timezone_database_version": self.version}
        self.assertIsNone(_resolve_boundary(calendar(clock="02:30:00"), target))
        target.update(target_local_date="2026-11-02", target_utc_instant="2026-11-02T15:00:00Z")
        self.assertEqual(_resolve_boundary(calendar(clock="01:30:00"), target), datetime(2026, 11, 1, 5, 30, tzinfo=UTC))

    def test_footer_offsets_are_included_even_when_absent_from_historical_types(self):
        header = b"TZif2" + b"\0" * 15 + struct.pack(">6I", 0, 0, 0, 0, 1, 4)
        body = struct.pack(">iBB", 0, 0, 0) + b"STD\0"
        for tail, expected in ((b"STD0DST-2,M3.2.0,M11.1.0", (0, 7200)),
                               (b"STD0DST,M3.2.0,M11.1.0", (0, 3600)),
                               (b"<+0545>-5:45", (0, 20700))):
            data = header + body + header + body + b"\n" + tail + b"\n"
            timezones._decode_zone("Test/Bounds", data)
            self.assertEqual(timezones._offset_bounds(data), expected)

    def test_version_failure_is_not_hidden_or_replaced_by_live_offsets(self):
        source = self.local | {"timezone_database_version": "not-installed"}
        with self.assertRaises(SpineValidationError) as raised:
            validate_reminder_lead(configuration({"kind": "once", "at": calendar()}), source)
        self.assertTrue(raised.exception.code.startswith("environment_failure"))

    def test_changed_source_without_exact_time_facts_is_a_structured_conflict(self):
        for source in ({"time_basis": "local_date"}, {"time_basis": "local_instant", "timezone": None}):
            with self.subTest(source=source), self.assertRaises(SpineValidationError) as raised:
                validate_reminder_lead(configuration({"kind": "once", "at": calendar()}), source)
            self.assertEqual(raised.exception.code, "semantic_conflict:configuration.notification_plan")


class CalendarLeadCommandTests(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    run_command = base.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    rule = pages.RecurringTaskReconcileTests.rule
    source_change = pages.RecurringTaskReconcileTests.source_change
    excluded = pages.RecurringTaskReconcileTests.excluded

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def calendar_request(self, *, schedule=None):
        request = self.request()
        config = request["configuration"]
        config["notification_plan"] = {"mode": "none", "custom_additions": [{
            "policy_key": "previous_day", "schedule": schedule or {"kind": "once", "at": calendar()},
            "late_handling": {"kind": "skip"},
        }]}
        config["delivery"] = {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                              "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}}
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        return request

    def test_create_reconcile_materializes_calendar_reminders_and_replays_without_duplicates(self):
        request = self.calendar_request()
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        initial = self.reconcile(created["result"]["rule"])
        self.assertEqual(len(initial["result"]["results"]), 6)
        # The first previous-day reminder is already past and skip-late; five remain.
        self.assertEqual(len(initial["result"]["work"]["created"]), 5)
        times = {row[0] for row in self.db.execute("SELECT eligible_at_utc FROM work_instances")}
        self.assertEqual(times, {f"2026-08-{day:02}T09:00:00Z" for day in range(8, 13)})
        before = base.dump(self.db)
        with patch("spine.services.recurring_task_leads.timezone_offset_bounds", side_effect=AssertionError("replay must not reprove")):
            replayed = self.run_command("create", request)
        self.assertTrue(replayed["replayed"], replayed)
        self.assertEqual(base.dump(self.db), before)
        second = self.reconcile(initial["result"]["rule"], "calendar-noop")
        self.assertFalse(second["changed"])
        self.assertEqual(second["result"]["work"]["created"], [])

    def test_insufficient_horizon_rejects_create_and_update_without_writes(self):
        request = self.calendar_request()
        request["configuration"]["generation_horizon_seconds"] = "134998"
        before = base.dump(self.db)
        rejected = self.run_command("create", request)
        self.assertEqual((rejected["error"]["code"], rejected["error"]["field"]),
                         ("semantic_conflict", "configuration.generation_horizon_seconds"), rejected)
        self.assertEqual(base.dump(self.db), before)
        request["configuration"]["generation_horizon_seconds"] = "134999"
        accepted = self.run_command("create", request)
        self.assertTrue(accepted["ok"], accepted)
        config = copy.deepcopy(request["configuration"])
        config["generation_horizon_seconds"] = "134998"
        before = base.dump(self.db)
        rejected = self.run_command("update", self.write("update", accepted["result"]["rule"], configuration=config,
                                                         adoption_scope="upcoming_open"))
        self.assertEqual(rejected["error"]["field"], "configuration.generation_horizon_seconds", rejected)
        self.assertEqual(base.dump(self.db), before)

    def test_calendar_repeat_window_produces_expected_work(self):
        request = self.calendar_request(schedule={"kind": "repeat_window", "start": calendar(0, "09:00:00"),
            "stop": calendar(0, "10:00:00"), "stop_inclusive": False,
            "cadence": {"kind": "fixed_elapsed", "interval_seconds": "1800"}})
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        initial = self.reconcile(created["result"]["rule"])
        self.assertEqual(len(initial["result"]["work"]["created"]), 12)
        self.assertEqual({row[0][11:] for row in self.db.execute("SELECT eligible_at_utc FROM work_instances")}, {"09:00:00Z", "09:30:00Z"})

    def test_local_source_materialization_spans_dst_with_calendar_labels_preserved(self):
        version = timezones.system_timezone_database_version()
        self.now = "2026-03-06T12:00:00Z"
        seed = "2026-03-07T11:30:00"
        event = handle("event.create", {
            "command_id": "calendar-local-source", "actor_subject_id": "owner", "created_at_utc": self.now,
            "title": "Local class", "all_day": False,
            "start_anchor": {"anchor_kind": "local_instant", "local_date": "2026-03-07", "local_time": "11:30:00",
                "timezone": "America/New_York", "timezone_database_version": version,
                "recurrence_set": {"time_basis": "local_instant", "timezone": "America/New_York", "timezone_database_version": version,
                    "rules": [{"frequency": "DAILY", "seed": seed, "start_bound": seed,
                               "end_condition": {"kind": "count", "count": "3"}}]}},
        }, self.context)
        self.assertTrue(event["ok"], event)
        recurrence = load_current_recurrence_set(self.db, item_id=event["item_id"])
        request = self.calendar_request()
        request.update(requested_at_utc=self.now, source={"item_id": event["item_id"], "item_version": "1",
            "recurrence_set_id": recurrence["recurrence_set_id"], "recurrence_revision_id": recurrence["recurrence_revision_id"]})
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        result = self.reconcile(created["result"]["rule"])
        self.assertEqual(len(result["result"]["work"]["created"]), 3)
        self.assertEqual({row[0] for row in self.db.execute("SELECT eligible_at_utc FROM work_instances")},
                         {"2026-03-06T14:00:00Z", "2026-03-07T14:00:00Z", "2026-03-08T13:00:00Z"})

    def test_calendar_adoption_cancellation_and_restoration_keep_prior_history(self):
        request = self.calendar_request()
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        first_page = self.reconcile(created["result"]["rule"])
        config = copy.deepcopy(request["configuration"])
        config["generation_horizon_seconds"] = "4838400"
        config["notification_plan"]["custom_additions"][0]["schedule"]["at"] = calendar(0, "09:00:00")
        updated = self.run_command("update", self.write("update", first_page["result"]["rule"], configuration=config,
                                                        adoption_scope="upcoming_open"))
        self.assertTrue(updated["ok"], updated)
        adopted = self.reconcile(updated["result"]["rule"], "calendar-adopt")
        self.assertTrue(all(entry["outcome"] == "adopted" for entry in adopted["result"]["results"]))
        selected = adopted["result"]["results"][0]
        task = selected["after"]["task_item_id"]
        self.source_change(exdates=[self.excluded(selected)])
        self.reconcile(self.rule(updated["result"]["rule"]["related_task_rule_id"]), "calendar-cancel")
        cancelled = copy.deepcopy(core._hydrated_item(self.db, task))
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(updated["result"]["rule"]["related_task_rule_id"]), "calendar-restore")
        row = next(value for value in restored["result"]["results"] if value["assignment_id"] == selected["assignment_id"])
        self.assertEqual(row["outcome"], "restored")
        self.assertNotEqual(row["after"]["task_item_id"], task)
        self.assertEqual(core._hydrated_item(self.db, task), cancelled)
        self.assertEqual(len(restored["result"]["work"]["created"]), 1)
        self.assertEqual(self.db.execute("SELECT eligible_at_utc FROM work_instances WHERE work_instance_id=?",
                                        (restored["result"]["work"]["created"][0],)).fetchone()[0], "2026-08-08T09:00:00Z")
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_changed_source_time_facts_block_only_new_generation_before_writes(self):
        request = self.calendar_request()
        request["configuration"]["generation_horizon_seconds"] = "134999"
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        # Inject a valid newly observed timezone at the projection seam. No SQL
        # mutation of immutable recurrence facts; full source writers remain R3.
        recurrence = copy.deepcopy(load_current_recurrence_set(self.db, item_id=self.event["item_id"]))
        recurrence.update(time_basis="local_instant", timezone="America/New_York",
                          timezone_database_version=timezones.system_timezone_database_version())
        from spine.services.recurring_task_leads import validate_reminder_lead as real_validate

        def changed(config, _source):
            return real_validate(config, recurrence)

        with patch("spine.services.recurring_task_reconcile.validate_reminder_lead", side_effect=changed):
            result = self.reconcile(created["result"]["rule"])
        self.assertEqual(result["result"]["future_generation"], "blocked")
        self.assertTrue(all(entry["reason"] == "configuration_invalid" for entry in result["result"]["results"]))
        for table in ("related_task_assignments", "related_task_generations", "notification_policies", "work_instances"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
