import unittest
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.commands.receipts import command_derived_id
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema
from spine.services import scheduling as scheduler_service
from spine.services.scheduling import materialize_notification_horizon


class SchedulerNotificationPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        subject = handle(
            "subject.upsert",
            {
                "command_id": "scheduler-plan-owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": "2026-08-01T00:00:00Z",
            },
            self.context,
        )
        self.assertTrue(subject["ok"], subject)
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": "scheduler-plan-route",
                "actor_subject_id": "owner",
                "delivery_target_id": "whatsapp-owner",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "owner@example",
                "updated_at_utc": "2026-08-01T00:01:00Z",
            },
            self.context,
        )
        self.assertTrue(route["ok"], route)

    def tearDown(self) -> None:
        self.connection.close()

    def test_exhausted_one_shot_produces_no_scheduler_receipt(self) -> None:
        self._create_event_reminder(
            "exhausted",
            event_at="2026-08-02T12:00:00Z",
            reminder_at="2026-08-02T11:00:00Z",
            late_handling={"kind": "skip"},
        )

        first = self._cycle("2026-08-10T10:00:00Z")
        second = self._cycle("2026-08-10T10:01:00Z")

        self.assertFalse(first.failures, first.failures)
        self.assertFalse(second.failures, second.failures)
        self.assertEqual(self._scheduler_receipt_count(), 0)
        self.assertEqual(self._work_count(), 0)

    def test_future_one_shot_materializes_normally(self) -> None:
        self._create_event_reminder(
            "future",
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T11:00:00Z",
            late_handling={"kind": "skip"},
        )

        cycle = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=7200)

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertEqual(cycle.items_repaired, 1)
        self.assertEqual(self._work_count(), 1)
        self.assertEqual(self._scheduler_receipt_effects(), ["notification_work_created"])

    def test_explicit_zero_selected_materialization_remains_receipt_bearing(self) -> None:
        _, policy = self._create_event_reminder(
            "explicit-zero",
            event_at="2026-08-02T12:00:00Z",
            reminder_at="2026-08-02T11:00:00Z",
            late_handling={"kind": "skip"},
        )

        result = handle(
            "notification_work.materialize",
            {
                "command_id": "explicit-zero-materialize",
                "actor_subject_id": "owner",
                "item_id": policy["item_id"],
                "target_version": policy["current_version"],
                "materialized_at_utc": "2026-08-10T10:00:00Z",
                "range_start_utc": "2026-08-10T10:00:00Z",
                "range_end_utc": "2026-08-11T10:00:00Z",
                "limit": "1000",
            },
            self.context,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["effect"], "notification_work_zero_selected")
        receipt = self.connection.execute(
            "SELECT effect FROM command_receipts WHERE command_id = 'explicit-zero-materialize'"
        ).fetchone()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["effect"], "notification_work_zero_selected")

    def test_deliver_within_policy_remains_eligible_through_grace(self) -> None:
        self._create_event_reminder(
            "grace",
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T09:55:00Z",
            late_handling={"kind": "deliver_within", "grace_seconds": "600"},
        )

        cycle = self._cycle("2026-08-10T10:00:00Z")

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertEqual(cycle.items_repaired, 1)
        self.assertEqual(self._work_count(), 1)

    def test_existing_equivalent_work_suppresses_all_retained_receipt(self) -> None:
        _, policy = self._create_event_reminder(
            "retained",
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T11:00:00Z",
            late_handling={"kind": "skip"},
        )
        first = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=7200)
        receipts_after_first = self._scheduler_receipt_count()
        explicit = handle(
            "notification_work.materialize",
            {
                "command_id": "retained-explicit-materialize",
                "actor_subject_id": "owner",
                "item_id": policy["item_id"],
                "target_version": policy["current_version"],
                "materialized_at_utc": "2026-08-10T10:00:00Z",
                "range_start_utc": "2026-08-10T10:00:00Z",
                "range_end_utc": "2026-08-10T12:00:00Z",
                "limit": "1000",
            },
            self.context,
        )

        second = self._cycle("2026-08-10T10:01:00Z", horizon_seconds=7200)

        self.assertFalse(first.failures, first.failures)
        self.assertTrue(explicit["ok"], explicit)
        self.assertEqual(explicit["effect"], "notification_work_all_retained")
        self.assertIsNotNone(
            self.connection.execute(
                "SELECT 1 FROM command_receipts WHERE command_id = 'retained-explicit-materialize'"
            ).fetchone()
        )
        self.assertFalse(second.failures, second.failures)
        self.assertEqual(second.items_repaired, 0)
        self.assertEqual(self._scheduler_receipt_count(), receipts_after_first)
        self.assertEqual(self._scheduler_receipt_effects(), ["notification_work_created"])

    def test_local_target_relative_policy_uses_canonical_expansion(self) -> None:
        timezone_version = system_timezone_database_version()
        event = handle(
            "event.create",
            {
                "command_id": "local-target-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-01T01:00:00Z",
                "title": "Local lunch",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "local_instant",
                    "local_date": "2026-08-10",
                    "local_time": "12:00:00",
                    "timezone": "America/Toronto",
                    "timezone_database_version": timezone_version,
                },
            },
            self.context,
        )
        self.assertTrue(event["ok"], event)
        policy = handle(
            "reminder.create",
            {
                "command_id": "local-target-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-01T01:01:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {
                        "kind": "once",
                        "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        self.assertTrue(policy["ok"], policy)

        first = self._cycle("2026-08-10T14:00:00Z", horizon_seconds=7200)
        receipts = self._scheduler_receipt_count()
        second = self._cycle("2026-08-10T14:01:00Z", horizon_seconds=7200)

        self.assertFalse(first.failures, first.failures)
        self.assertFalse(second.failures, second.failures)
        self.assertEqual(self._work_count(), 1)
        self.assertEqual(self._scheduler_receipt_count(), receipts)

    def test_stale_cancellable_work_dispatches_reconciliation(self) -> None:
        _, policy = self._create_event_reminder(
            "stale",
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T11:00:00Z",
            late_handling={"kind": "skip"},
        )
        first = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=7200)
        old_work = self.connection.execute("SELECT work_instance_id FROM work_instances").fetchone()["work_instance_id"]
        edited = handle(
            "reminder.edit",
            {
                "command_id": "stale-reminder-edit",
                "actor_subject_id": "owner",
                "item_id": policy["item_id"],
                "target_version": policy["current_version"],
                "notification_intent_id": policy["notification_intent_id"],
                "notification_policy_id": policy["notification_policy_id"],
                "updated_at_utc": "2026-08-10T10:01:00Z",
                "patch": {
                    "schedule": {
                        "kind": "once",
                        "at": {"kind": "absolute_utc", "at_utc": "2026-08-10T11:30:00Z"},
                    }
                },
            },
            self.context,
        )
        self.assertTrue(edited["ok"], edited)

        second = self._cycle("2026-08-10T10:02:00Z", horizon_seconds=7200)

        self.assertFalse(first.failures, first.failures)
        self.assertFalse(second.failures, second.failures)
        self.assertEqual(second.items_repaired, 1)
        old = self.connection.execute(
            "SELECT status, reason_code FROM work_instances WHERE work_instance_id = ?", (old_work,)
        ).fetchone()
        self.assertEqual((old["status"], old["reason_code"]), ("cancelled", "notification_schedule_superseded"))
        statuses = [row["status"] for row in self.connection.execute("SELECT status FROM work_instances ORDER BY status")]
        self.assertEqual(statuses, ["cancelled", "eligible"])
        self.assertEqual(self._scheduler_receipt_effects(), ["notification_work_created", "notification_work_reconciled"])

    def test_disabled_policy_work_reconciles_without_new_opportunity(self) -> None:
        _, policy = self._create_event_reminder(
            "disabled",
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T11:00:00Z",
            late_handling={"kind": "skip"},
        )
        first = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=7200)
        work_id = self.connection.execute("SELECT work_instance_id FROM work_instances").fetchone()["work_instance_id"]
        disabled = handle(
            "reminder.disable",
            {
                "command_id": "disabled-reminder-disable",
                "actor_subject_id": "owner",
                "item_id": policy["item_id"],
                "target_version": policy["current_version"],
                "notification_intent_id": policy["notification_intent_id"],
                "notification_policy_id": policy["notification_policy_id"],
                "disabled_at_utc": "2026-08-10T10:01:00Z",
            },
            self.context,
        )
        self.assertTrue(disabled["ok"], disabled)

        second = self._cycle("2026-08-10T10:02:00Z", horizon_seconds=7200)

        self.assertFalse(first.failures, first.failures)
        self.assertFalse(second.failures, second.failures)
        self.assertEqual(second.items_repaired, 1)
        work = self.connection.execute(
            "SELECT status, reason_code FROM work_instances WHERE work_instance_id = ?", (work_id,)
        ).fetchone()
        self.assertEqual((work["status"], work["reason_code"]), ("cancelled", "notification_policy_disabled"))

    def test_exhausted_recurrence_skips_provenance_and_materialization(self) -> None:
        self._create_recurring_event_reminder("recurrence-exhausted", seed="2026-08-01T12:00:00Z", count="2")

        cycle = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=172800)

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertEqual(self._scheduler_receipt_count(), 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM occurrence_provenance").fetchone()[0], 0)
        self.assertEqual(self._work_count(), 0)

    def test_active_recurrence_repairs_provenance_then_materializes(self) -> None:
        self._create_recurring_event_reminder("recurrence-active", seed="2026-08-10T12:00:00Z", count="2")

        cycle = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=172800)

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertEqual(cycle.items_repaired, 1)
        self.assertGreater(self.connection.execute("SELECT COUNT(*) FROM occurrence_provenance").fetchone()[0], 0)
        self.assertEqual(self._work_count(), 2)
        self.assertCountEqual(
            self._scheduler_receipt_effects(),
            ["provenance_regenerate_replaced", "notification_work_created"],
        )
        receipts = self._scheduler_receipt_count()

        second = self._cycle("2026-08-10T10:01:00Z", horizon_seconds=172800)

        self.assertFalse(second.failures, second.failures)
        self.assertEqual(second.items_repaired, 0)
        self.assertEqual(self._scheduler_receipt_count(), receipts)

    def test_exhausted_items_do_not_consume_dispatch_limit(self) -> None:
        command_ids = ["fair-a", "fair-b"]
        ordered = sorted(
            command_ids,
            key=lambda value: command_derived_id(
                prefix="item",
                command="event.create",
                command_id=f"{value}-event",
                row_role="item",
                request_path="/item",
            ),
        )
        self._create_event_reminder(
            ordered[0],
            event_at="2026-08-02T12:00:00Z",
            reminder_at="2026-08-02T11:00:00Z",
            late_handling={"kind": "skip"},
        )
        self._create_event_reminder(
            ordered[1],
            event_at="2026-08-10T12:00:00Z",
            reminder_at="2026-08-10T11:00:00Z",
            late_handling={"kind": "skip"},
        )

        cycle = self._cycle("2026-08-10T10:00:00Z", horizon_seconds=7200, max_items=1)

        self.assertFalse(cycle.failures, cycle.failures)
        self.assertEqual(cycle.items_repaired, 1)
        self.assertEqual(self._work_count(), 1)
        self.assertEqual(self._scheduler_receipt_effects(), ["notification_work_created"])

    def test_candidate_discovery_is_bounded_and_rotates_fairly(self) -> None:
        for index in range(3):
            self._create_event_reminder(
                f"rotation-{index}",
                event_at="2026-08-02T12:00:00Z",
                reminder_at="2026-08-02T11:00:00Z",
                late_handling={"kind": "skip"},
            )

        with (
            patch.object(scheduler_service, "_SCHEDULER_SCAN_MINIMUM", 2),
            patch.object(scheduler_service, "_SCHEDULER_SCAN_MULTIPLIER", 1),
            patch.object(scheduler_service, "_SCHEDULER_SCAN_MAXIMUM", 2),
        ):
            first = scheduler_service._scheduler_candidate_rows(
                self.connection,
                evaluated=scheduler_service._utc("2026-08-10T10:00:00Z"),
                max_items=1,
            )
            second = scheduler_service._scheduler_candidate_rows(
                self.connection,
                evaluated=scheduler_service._utc("2026-08-10T10:01:00Z"),
                max_items=1,
            )

        first_ids = {str(row["item_id"]) for row in first}
        second_ids = {str(row["item_id"]) for row in second}
        self.assertEqual((len(first_ids), len(second_ids)), (2, 2))
        self.assertNotEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids | second_ids), 3)

    def _create_event_reminder(
        self,
        name: str,
        *,
        event_at: str,
        reminder_at: str,
        late_handling: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        event = handle(
            "event.create",
            {
                "command_id": f"{name}-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-01T01:00:00Z",
                "title": name,
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": event_at},
            },
            self.context,
        )
        self.assertTrue(event["ok"], event)
        policy = handle(
            "reminder.create",
            {
                "command_id": f"{name}-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-01T01:01:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {"kind": "once", "at": {"kind": "absolute_utc", "at_utc": reminder_at}},
                    "late_handling": late_handling,
                },
            },
            self.context,
        )
        self.assertTrue(policy["ok"], policy)
        return event, policy

    def _create_recurring_event_reminder(self, name: str, *, seed: str, count: str) -> tuple[dict[str, object], dict[str, object]]:
        event = handle(
            "event.create",
            {
                "command_id": f"{name}-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-01T01:00:00Z",
                "title": name,
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": seed,
                    "recurrence_set": {
                        "time_basis": "instant_utc",
                        "rules": [
                            {
                                "frequency": "DAILY",
                                "interval": "1",
                                "seed": seed,
                                "start_bound": seed,
                                "end_condition": {"kind": "count", "count": count},
                            }
                        ],
                    },
                },
            },
            self.context,
        )
        self.assertTrue(event["ok"], event)
        policy = handle(
            "reminder.create",
            {
                "command_id": f"{name}-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-01T01:01:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "each_occurrence"},
                    "schedule": {
                        "kind": "once",
                        "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        self.assertTrue(policy["ok"], policy)
        return event, policy

    def _cycle(self, evaluated_at_utc: str, *, horizon_seconds: int = 86400, max_items: int = 100):
        return materialize_notification_horizon(
            self.connection,
            evaluated_at_utc=evaluated_at_utc,
            horizon_seconds=horizon_seconds,
            max_items=max_items,
            actor_subject_id="owner",
        )

    def _scheduler_receipt_count(self) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE command_id LIKE 'scheduler_command_%'"
        ).fetchone()[0]

    def _scheduler_receipt_effects(self) -> list[str]:
        return [
            row["effect"]
            for row in self.connection.execute(
                """
                SELECT effect FROM command_receipts
                WHERE command_id LIKE 'scheduler_command_%'
                ORDER BY created_at_utc, command_receipt_id
                """
            )
        ]

    def _work_count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
