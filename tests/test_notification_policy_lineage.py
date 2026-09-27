"""Preserved schema-15 shared-intent policies must remain independently deliverable."""

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.commands import core as command_core
from spine.core.errors import SpineValidationError
from spine.core.notifications import normalize_notification_policy
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.ledger.notifications import NotificationPolicyResolver, insert_notification_schedule_policy, load_current_notification_policies
from spine.ledger.work import assert_work_instance_not_stale, create_work_instance
from spine.services.scheduling import materialize_notification_horizon
from spine.services.work import list_eligible_work, start_work
from tests import test_tickerd_adapter as tickerd_tests
from tests.facet_storage_support import all_rows, assign, catalog
from tests.test_ledger_sqlite import insert_valid_event_bundle

EVALUATED = "2026-06-06T08:00:00Z"
END = "2026-06-06T11:00:00Z"


class NotificationPolicyLineageTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        # Construct the actual predecessor layout, not a relabelled schema-17 DB.
        with patch("spine.ledger.facet_migration.install_facet_storage"), patch(
            "spine.ledger.facet_access_migration.install_facet_access"
        ):
            initialize_schema(self.db)
        def local_anchor(db, anchor_id):
            db.execute(
                "INSERT INTO temporal_anchors (anchor_id,anchor_kind,local_date,local_time,timezone,"
                "timezone_database_version,created_at_utc) VALUES (?,'local_instant','2026-06-06','10:00:00','Etc/UTC',?,?)",
                (anchor_id, system_timezone_database_version(), EVALUATED),
            )

        with (patch.object(self.db, "version_allocation"), patch("spine.ledger.facets.insert_snapshot"),
              patch("tests.test_ledger_sqlite.insert_instant_anchor", local_anchor)):
            insert_valid_event_bundle(self.db)
        self.ctx = CommandContext(ledger=self.db)
        route = handle("delivery_target.upsert", {
            "command_id": "route", "actor_subject_id": "subject-1", "delivery_target_id": "test-route",
            "owner_kind": "subject", "owner_subject_id": "subject-1", "channel": "whatsapp",
            "adapter_name": "openclaw", "target_ref": "synthetic-only", "updated_at_utc": EVALUATED,
        }, self.ctx)
        self.assertTrue(route["ok"], route)
        self.policies = []
        for offset in ("-3600", "-1800"):
            policy = normalize_notification_policy({
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "event_start", "application_scope": "item"},
                "schedule": {"kind": "once", "at": {
                    "kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": offset,
                }},
                "late_handling": {"kind": "skip"},
            }, item_id="event-1", item_version="1", command_id="historical-multi-reminder",
                created_at_utc=EVALUATED, recipient_kind="subject", recipient_id="subject-1",
                channel="whatsapp", delivery_target_id="test-route")
            with self.db:
                insert_notification_schedule_policy(self.db, normalized=policy)
            self.policies.append(policy.value)
        self.assertEqual(len({p["notification_intent_id"] for p in self.policies}), 1)
        self.assertEqual(len({p["notification_policy_id"] for p in self.policies}), 2)
        opportunities = handle("notification.opportunities", {
            "item_id": "event-1", "evaluated_at_utc": EVALUATED,
            "range_start_utc": EVALUATED, "range_end_utc": END, "limit": "100",
        }, self.ctx)
        self.assertTrue(opportunities["ok"], opportunities)
        self.assertEqual(len(opportunities["opportunities"]), 2)
        for index, opportunity in enumerate(opportunities["opportunities"]):
            create_work_instance(self.db, work_instance_id=f"old-work-{index}", item_id="event-1", item_version=1,
                notification_policy_id=opportunity["notification_policy_id"], notification_policy_item_version=1,
                notification_intent_id=opportunity["notification_intent_id"],
                notification_opportunity_id=opportunity["notification_opportunity_id"],
                normalized_notification_schedule_hash=opportunity["normalized_notification_schedule_hash"],
                target_anchor_role="event_start", application_scope="item",
                target_scheduled_fact=opportunity["target_scheduled_fact"], target_at_utc=opportunity["target_at_utc"],
                delivery_target_id="test-route", eligible_at_utc=opportunity["eligible_at_utc"], created_at_utc=EVALUATED)
        before = all_rows(self.db)
        self.assertEqual(migrate_schema(self.db).applied_versions, (16, 17))
        self.assertEqual(verify_schema(self.db).schema_version, 17)
        for table, rows in before.items():
            if table != "ledger_schema":
                self.assertEqual(all_rows(self.db)[table], rows, table)

    def work(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]

    def test_migrated_shared_intent_scheduler_is_idle_without_receipt_or_cancellation(self):
        before = all_rows(self.db)
        result = materialize_notification_horizon(self.db, evaluated_at_utc=EVALUATED, horizon_seconds=10800, max_items=100)
        self.assertEqual(result.failures, ())
        self.assertEqual(all_rows(self.db), before)

    def test_explicit_materialization_retains_each_sibling(self):
        before = self.work()
        result = handle("notification_work.materialize", {
            "command_id": "explicit", "actor_subject_id": "subject-1", "item_id": "event-1", "target_version": "1",
            "materialized_at_utc": EVALUATED, "range_start_utc": EVALUATED, "range_end_utc": END, "limit": "100",
        }, self.ctx)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["cancelled_work_instance_ids"], [])
        self.assertEqual(self.work(), before)

    def test_attempt_start_resolves_policy_not_shared_intent(self):
        for work in self.work():
            assert_work_instance_not_stale(self.db, work["work_instance_id"])

    def test_schedule_title_update_retains_sibling_work(self):
        before = self.work()
        result = handle("schedule.update", {
            "contract_version": "spine.schedule-update.v2", "command_id": "title", "actor_subject_id": "subject-1",
            "item_id": "event-1", "target_version": "1", "updated_at_utc": EVALUATED,
            "patch": {"item": {"title": "Updated appointment"}}, "materialization": {"mode": "none"},
        }, self.ctx)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.work(), before)
        for work in self.work():
            assert_work_instance_not_stale(self.db, work["work_instance_id"])

    def attach_facet(self, value, command_id):
        if not self.db.execute("SELECT 1 FROM item_archetype_assignments WHERE item_id='event-1'").fetchone():
            with self.db.atomic_command():
                archetype = catalog(self.db, actor="subject-1")
                assign(self.db, "event-1", 1, archetype, actor="subject-1")
        version = str(self.db.execute("SELECT current_version FROM coordination_items WHERE item_id='event-1'").fetchone()[0])
        return handle("item.facets.update", {
            "contract_version": "spine.item-facets.v1", "command_id": command_id, "actor_subject_id": "subject-1",
            "action_timestamp_utc": EVALUATED, "item_id": "event-1", "expected_item_version": version,
            "changes": [{"op": "set", "facet_key": "details0", "expected_binding_id": "binding0",
                         "facet_schema_revision_id": "revision", "values": {"flight": value}}],
        }, self.ctx)

    def test_three_facet_copy_forwards_preserve_both_siblings_and_noop_planning(self):
        work = self.work()
        for index in range(3):
            result = self.attach_facet(f"AC{index}", f"facet-{index}")
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["reconciliation_performed"])
            self.assertEqual(self.work(), work)
            for row in work:
                assert_work_instance_not_stale(self.db, row["work_instance_id"])
            self.test_migrated_shared_intent_scheduler_is_idle_without_receipt_or_cancellation()
        resolver = NotificationPolicyResolver(self.db, load_current_notification_policies(self.db, item_id="event-1"))
        for row in work:
            resolved = resolver.resolve(row["notification_policy_id"])
            self.assertEqual(resolved["item_version"], "4")
            self.assertNotEqual(resolved["source_notification_policy_id"], row["notification_policy_id"])
            self.assertEqual(resolved["normalized_notification_schedule_hash"], row["normalized_notification_schedule_hash"])
        explicit = handle("notification_work.materialize", {
            "command_id": "after-three-copies", "actor_subject_id": "subject-1", "item_id": "event-1", "target_version": "4",
            "materialized_at_utc": EVALUATED, "range_start_utc": EVALUATED, "range_end_utc": END, "limit": "100",
        }, self.ctx)
        self.assertTrue(explicit["ok"], explicit)
        self.assertFalse(explicit["changed"])
        self.assertEqual(self.work(), work)

    def test_facet_proof_requires_one_unchanged_successor_per_policy(self):
        from spine.ledger.facet_continuity import capture, verify
        before = capture(self.db, "event-1", 1)
        self.assertTrue(self.attach_facet("AC1", "facet-proof")["ok"])
        after = capture(self.db, "event-1", 2)
        # Isolate the policy portion: catalog assignment was introduced by the fixture.
        before = {**after, "policies": before["policies"]}
        verify(before, after)
        for mutation in ("drop", "duplicate_source", "change"):
            bad = copy.deepcopy(after)
            if mutation == "drop":
                bad["policies"].pop()
            elif mutation == "duplicate_source":
                bad["policies"][1]["source_policy_id"] = bad["policies"][0]["source_policy_id"]
            else:
                bad["policies"][0]["meaning"]["late_handling"] = {"kind": "deliver_within", "grace_seconds": "1"}
            with self.subTest(mutation=mutation), self.assertRaises(SpineValidationError):
                verify(before, bad)

    def test_missing_policy_never_falls_back_to_sibling_intent(self):
        resolver = NotificationPolicyResolver(self.db, self.policies[:1])
        self.assertIsNone(resolver.resolve(self.policies[1]["notification_policy_id"]))
        self.assertIsNone(resolver.resolve("missing"))

    def test_forked_broken_cross_item_and_cyclic_lineage_fail_closed(self):
        prior = self.policies[0]
        successor = {**prior, "notification_policy_id": "prospective", "item_version": "2",
                     "source_notification_policy_id": prior["notification_policy_id"]}
        self.assertEqual(NotificationPolicyResolver(self.db, [successor]).resolve(prior["notification_policy_id"]), successor)
        with self.assertRaisesRegex(SpineValidationError, "ambiguous notification policy lineage"):
            NotificationPolicyResolver(self.db, [successor, {**successor, "notification_policy_id": "fork"}]).resolve(
                prior["notification_policy_id"])
        for field, value in (("source_notification_policy_id", "missing"), ("item_version", "3")):
            bad = {**successor, field: value}
            resolver = NotificationPolicyResolver(self.db, [bad])
            if field == "item_version":
                # Synthetic corrupt history: predecessor version is not decreasing.
                original = resolver._load(prior["notification_policy_id"])
                resolver._history["cycle"] = {**original, "policy_id": "cycle", "version": 3}
                bad["source_notification_policy_id"] = "cycle"
            with self.subTest(field=field), self.assertRaisesRegex(SpineValidationError, "invalid notification policy lineage"):
                resolver.resolve(prior["notification_policy_id"])
        resolver = NotificationPolicyResolver(self.db, [{**successor, "source_notification_policy_id": "foreign"}])
        resolver._history["foreign"] = {**resolver._load(prior["notification_policy_id"]), "item_id": "another-item"}
        with self.assertRaisesRegex(SpineValidationError, "invalid notification policy lineage"):
            resolver.resolve(prior["notification_policy_id"])

    def test_real_schedule_change_and_disabled_policy_stay_stale_after_copy(self):
        self.assertTrue(self.attach_facet("AC1", "facet-stale")["ok"])
        policies = load_current_notification_policies(self.db, item_id="event-1")
        original = self.work()[0]
        current = NotificationPolicyResolver(self.db, policies).resolve(original["notification_policy_id"])
        for column, value in (("normalized_notification_schedule_hash", "f" * 64), ("status", "disabled")):
            self.db.execute("BEGIN")
            try:
                if column == "status":
                    self.db.execute("UPDATE notification_policies SET status='disabled',disabled_at_utc=? WHERE policy_id=?",
                                    (EVALUATED, current["notification_policy_id"]))
                self.db.execute(f"UPDATE notification_policies SET {column}=? WHERE policy_id=?",
                                (value, current["notification_policy_id"]))
                with self.subTest(column=column), self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
                    assert_work_instance_not_stale(self.db, original["work_instance_id"])
                sibling = self.work()[1]
                assert_work_instance_not_stale(self.db, sibling["work_instance_id"])
            finally:
                self.db.rollback()

    def test_unrelated_notification_materializes_and_all_work_can_start_without_sends(self):
        event = handle("event.create", {
            "command_id": "unrelated", "actor_subject_id": "subject-1", "created_at_utc": EVALUATED,
            "title": "Other event", "all_day": False,
            "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-06T10:00:00Z"},
        }, self.ctx)
        self.assertTrue(event["ok"], event)
        reminder = handle("reminder.create", {
            "command_id": "unrelated-reminder", "actor_subject_id": "subject-1", "created_at_utc": EVALUATED,
            "item_id": event["item_id"], "target_version": "1", "recipient_kind": "subject",
            "recipient_subject_id": "subject-1", "channel": "whatsapp", "delivery_target_id": "test-route",
            "notification": {"authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "event_start", "application_scope": "item"},
                "schedule": {"kind": "once", "at": {"kind": "absolute_utc", "at_utc": "2026-06-06T09:00:00Z"}},
                "late_handling": {"kind": "skip"}},
        }, self.ctx)
        self.assertTrue(reminder["ok"], reminder)
        cycle = materialize_notification_horizon(self.db, evaluated_at_utc=EVALUATED, horizon_seconds=10800, max_items=100)
        self.assertEqual(cycle.failures, ())
        eligible = list_eligible_work(self.db, now_utc="2026-06-06T09:30:00Z")
        self.assertEqual(len(eligible), 3)
        for row in eligible:
            start_work(self.db, work_instance_id=row["work_instance_id"], started_at_utc="2026-06-06T09:30:00Z")
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_reconcile_changes_only_the_exact_sibling(self):
        work = self.work()
        policies = load_current_notification_policies(self.db, item_id="event-1")
        for field, value, reason in (
            ("normalized_notification_schedule_hash", "f" * 64, "notification_schedule_superseded"),
            ("delivery_target_id", "different-route", "notification_routing_changed"),
        ):
            changed = [{**p, **({field: value} if p["notification_policy_id"] == work[0]["notification_policy_id"] else {})}
                       for p in policies]
            cancelled, retained, protected, reasons = command_core._schedule_reconcile_work_plan(
                self.db, item_id="event-1", active_policies=changed, target_changed=False, recurrence_changed=False,
            )
            with self.subTest(field=field):
                self.assertEqual(cancelled, [work[0]["work_instance_id"]])
                self.assertEqual(retained, [work[1]["work_instance_id"]])
                self.assertEqual(protected, [])
                self.assertEqual(reasons, {work[0]["work_instance_id"]: reason})

    def test_target_snapshots_do_not_overwrite_siblings(self):
        def targets(_db, *, policy, **kw):
            return [{"target_scheduled_fact": policy["notification_policy_id"], "target_utc_instant": EVALUATED}]

        with patch("spine.commands.core._notification_targets", targets):
            snapshots = command_core._current_notification_target_snapshots(
                self.db, item={}, policies=self.policies, recurrence=None, range_start_utc=EVALUATED, range_end_utc=END,
            )
        self.assertEqual(set(snapshots), {p["notification_policy_id"] for p in self.policies})
        for policy in self.policies:
            self.assertEqual(next(iter(snapshots[policy["notification_policy_id"]]))[2], policy["notification_policy_id"])

    def test_attempt_rejects_work_intent_mismatch(self):
        with self.db:
            self.db.execute("UPDATE work_instances SET notification_intent_id='wrong' WHERE work_instance_id='old-work-0'")
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            assert_work_instance_not_stale(self.db, "old-work-0")

    @unittest.skipUnless(tickerd_tests.TICKERD_AVAILABLE, "tickerd is not importable")
    def test_worker_reconciles_beyond_fatal_threshold_and_fake_delivery_is_attempt_backed(self):
        from spine.adapters import OpenClawNotificationProcessor, SpineTickerdWorkAdapter
        from spine.runtime.worker import FakeOpenClawSender, run_spine_worker

        self.assertTrue(self.attach_facet("AC1", "worker-facet-1")["ok"])
        self.assertTrue(self.attach_facet("AC2", "worker-facet-2")["ok"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Reconcile at a deterministic instant before the reminders are due.
            adapter = SpineTickerdWorkAdapter(self.db)
            envelope = replace(tickerd_tests.cycle_envelope(), actual_start_ts=datetime(2026, 6, 6, 8, tzinfo=UTC))
            for _ in range(4):
                self.assertTrue(adapter.reconcile(envelope, max_batches=1).ok)
            result = run_spine_worker(self.db, state_dir=root / "observe", runtime_mode="observe_only",
                max_cycles=4, tick_interval_ms=1, reconcile_interval_ms=1, install_signal_handlers=False)
            self.assertEqual(result.exit_code, 0)
            events = (root / "observe/events.jsonl").read_text()
            self.assertNotIn("fatal_threshold_exceeded", events)
            self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)

            sends = root / "fake-sends.jsonl"
            processor = OpenClawNotificationProcessor(sender=FakeOpenClawSender(sends))
            adapter = SpineTickerdWorkAdapter(self.db, runtime_mode="active", processor=processor)
            for hour, minute in ((9, 0), (9, 30)):
                envelope = replace(envelope, actual_start_ts=datetime(2026, 6, 6, hour, minute, tzinfo=UTC))
                for item in adapter.list_work_items(envelope, limit=100):
                    adapter.process_work_item(item, envelope, side_effects_allowed=True)
            self.assertEqual([w["status"] for w in self.work()], ["succeeded", "succeeded"])
            self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts WHERE attempt_status='succeeded'").fetchone()[0], 2)
            self.assertEqual(len([json.loads(line) for line in sends.read_text().splitlines()]), 2)
            terminal_work = self.work()
            attempts = [dict(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")]
            self.assertTrue(self.attach_facet("AC3", "after-fake-delivery")["ok"])
            self.assertEqual(self.work(), terminal_work)
            self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")], attempts)
