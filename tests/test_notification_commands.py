import unittest
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.commands import core as command_core
from spine.core import SpineValidationError
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema
from spine.services import prepare_work_attempt


class NotificationCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        created = handle(
            "subject.upsert",
            {
                "command_id": "cmd-owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": "2026-08-07T17:00:00Z",
            },
            self.context,
        )
        self.assertTrue(created["ok"])
        routed = handle(
            "delivery_target.upsert",
            {
                "command_id": "cmd-target",
                "actor_subject_id": "owner",
                "delivery_target_id": "whatsapp-owner",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "owner@example",
                "updated_at_utc": "2026-08-07T17:01:00Z",
            },
            self.context,
        )
        self.assertTrue(routed["ok"])

    def tearDown(self) -> None:
        self.connection.close()

    def test_notification_persistence_failure_rolls_back_item_version_and_policy(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-event-rollback-target",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:02:00Z",
                "title": "Appointment",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-08-08T18:00:00Z"},
            },
            self.context,
        )
        original = command_core.insert_notification_schedule_policy

        def fail_after_insert(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected notification persistence failure")

        with (
            patch("spine.commands.core.insert_notification_schedule_policy", side_effect=fail_after_insert),
            self.assertRaisesRegex(RuntimeError, "injected notification"),
        ):
            handle(
                "reminder.create",
                {
                    "command_id": "cmd-reminder-rollback",
                    "actor_subject_id": "owner",
                    "item_id": event["item_id"],
                    "target_version": "1",
                    "created_at_utc": "2026-08-07T18:00:00Z",
                    "recipient_kind": "subject",
                    "recipient_subject_id": "owner",
                    "channel": "whatsapp",
                    "delivery_target_id": "whatsapp-owner",
                    "notification": {
                        "authoring_contract": "spine.notification-schedule-authoring.v1",
                        "target": {"anchor_role": "event_start", "application_scope": "item"},
                        "schedule": {
                            "kind": "once",
                            "at": {"kind": "absolute_utc", "at_utc": "2026-08-08T12:00:00Z"},
                        },
                        "late_handling": {"kind": "skip"},
                    },
                },
                self.context,
            )

        item = self.connection.execute("SELECT current_version FROM coordination_items WHERE item_id = ?", (event["item_id"],)).fetchone()
        self.assertEqual(item["current_version"], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_schedules").fetchone()[0], 0)
        self.assertIsNone(self.connection.execute("SELECT 1 FROM command_receipts WHERE command_id = 'cmd-reminder-rollback'").fetchone())

    def test_create_structured_notification_persists_intent_without_work(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:02:00Z",
                "title": "Appointment",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": "2026-08-08T18:00:00Z",
                },
            },
            self.context,
        )
        response = handle(
            "reminder.create",
            {
                "command_id": "cmd-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-07T18:00:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-21600",
                        },
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )

        self.assertTrue(response["ok"], response)
        self.assertTrue(response["created"])
        self.assertEqual(response["version"], "2")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM notification_schedules").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0],
            0,
        )

        opportunities = handle(
            "notification.opportunities",
            {
                "item_id": event["item_id"],
                "evaluated_at_utc": "2026-08-08T10:00:00Z",
                "range_start_utc": "2026-08-08T10:00:00Z",
                "range_end_utc": "2026-08-08T18:00:00Z",
                "limit": "100",
                "include_diagnostics": True,
            },
            self.context,
        )
        self.assertTrue(opportunities["ok"], opportunities)
        self.assertEqual(len(opportunities["opportunities"]), 1)
        opportunity = opportunities["opportunities"][0]
        self.assertEqual(opportunity["eligible_at_utc"], "2026-08-08T12:00:00Z")
        self.assertEqual(opportunity["target_at_utc"], "2026-08-08T18:00:00Z")
        self.assertTrue(opportunity["actionable"])
        materialize_request = {
            "command_id": "cmd-materialize",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "2",
            "materialized_at_utc": "2026-08-08T10:00:00Z",
            "range_start_utc": "2026-08-08T10:00:00Z",
            "range_end_utc": "2026-08-08T18:00:00Z",
            "limit": "100",
        }
        materialized = handle("notification_work.materialize", materialize_request, self.context)
        replay = handle("notification_work.materialize", materialize_request, self.context)
        self.assertTrue(materialized["ok"], materialized)
        self.assertEqual(materialized["effect"], "notification_work_created")
        self.assertEqual(replay, materialized)
        work = self.connection.execute("SELECT * FROM work_instances").fetchone()
        self.assertEqual(work["notification_opportunity_id"], opportunity["notification_opportunity_id"])
        self.assertEqual(work["target_scheduled_fact"], "2026-08-08T18:00:00Z")

        edited = handle(
            "reminder.edit",
            {
                "command_id": "cmd-edit-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "notification_intent_id": response["notification_intent_id"],
                "notification_policy_id": response["notification_policy_id"],
                "updated_at_utc": "2026-08-08T10:01:00Z",
                "patch": {
                    "schedule": {
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-3600",
                        },
                    }
                },
            },
            self.context,
        )
        self.assertTrue(edited["ok"], edited)
        self.assertEqual(edited["current_version"], "3")
        reconciled = handle(
            "notification_work.materialize",
            {
                **materialize_request,
                "command_id": "cmd-materialize-edited",
                "target_version": "3",
                "materialized_at_utc": "2026-08-08T10:02:00Z",
            },
            self.context,
        )
        self.assertEqual(reconciled["effect"], "notification_work_reconciled")
        self.assertEqual(len(reconciled["created_work_instance_ids"]), 1)
        self.assertEqual(len(reconciled["cancelled_work_instance_ids"]), 1)

        disabled = handle(
            "reminder.disable",
            {
                "command_id": "cmd-disable-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "3",
                "notification_intent_id": edited["notification_intent_id"],
                "notification_policy_id": edited["notification_policy_id"],
                "disabled_at_utc": "2026-08-08T10:03:00Z",
            },
            self.context,
        )
        self.assertTrue(disabled["ok"], disabled)
        self.assertTrue(disabled["disabled"])
        disabled_opportunities = handle(
            "notification.opportunities",
            {
                "item_id": event["item_id"],
                "evaluated_at_utc": "2026-08-08T10:04:00Z",
                "range_start_utc": "2026-08-08T10:00:00Z",
                "range_end_utc": "2026-08-08T18:00:00Z",
                "limit": "100",
            },
            self.context,
        )
        self.assertFalse(disabled_opportunities["opportunities"][0]["actionable"])
        self.assertEqual(
            disabled_opportunities["opportunities"][0]["reason_code"],
            "notification_policy_disabled",
        )

    def test_notification_cursor_seeks_past_dense_first_page(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-event-pagination",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:02:00Z",
                "title": "Paged countdown",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-08-08T18:00:00Z"},
            },
            self.context,
        )
        created = handle(
            "reminder.create",
            {
                "command_id": "cmd-reminder-pagination",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-07T18:00:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {
                        "kind": "repeat_window",
                        "start": {"kind": "absolute_utc", "at_utc": "2026-08-08T08:00:00Z"},
                        "stop": {"kind": "absolute_utc", "at_utc": "2026-08-08T18:00:00Z"},
                        "stop_inclusive": False,
                        "cadence": {"kind": "fixed_elapsed", "interval_seconds": "3600"},
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        self.assertTrue(created["ok"], created)
        request = {
            "item_id": event["item_id"],
            "evaluated_at_utc": "2026-08-08T07:00:00Z",
            "range_start_utc": "2026-08-08T08:00:00Z",
            "range_end_utc": "2026-08-08T19:00:00Z",
            "limit": "3",
        }
        observed: list[str] = []
        cursor = None
        for _ in range(4):
            page = handle(
                "notification.opportunities",
                {**request, **({"cursor": cursor} if cursor is not None else {})},
                self.context,
            )
            self.assertTrue(page["ok"], page)
            observed.extend(value["eligible_at_utc"] for value in page["opportunities"])
            cursor = page["next_cursor"]
        self.assertEqual(
            observed,
            [f"2026-08-08T{hour:02d}:00:00Z" for hour in range(8, 18)],
        )
        self.assertIsNone(cursor)

        malformed = handle(
            "notification.opportunities",
            {**request, "cursor": "not-a-cursor"},
            self.context,
        )
        self.assertEqual(malformed["error"]["code"], "stale_cursor")
        self.assertEqual(malformed["error"]["field"], "cursor")

    def test_local_date_target_calendar_offset_round_trips_through_ledger(self) -> None:
        timezone_version = system_timezone_database_version()
        task = handle(
            "task.create",
            {
                "command_id": "cmd-local-date-task",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:02:00Z",
                "title": "File local-date report",
                "due_anchor": {
                    "anchor_kind": "local_date",
                    "local_date": "2026-03-09",
                    "timezone": "America/Los_Angeles",
                    "timezone_database_version": timezone_version,
                },
            },
            self.context,
        )
        policy = handle(
            "reminder.create",
            {
                "command_id": "cmd-local-date-reminder",
                "actor_subject_id": "owner",
                "item_id": task["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-03-01T00:00:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "task_due", "application_scope": "item"},
                    "schedule": {
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "calendar_days",
                            "offset_days": "-1",
                            "local_time": "08:00:00",
                        },
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        self.assertTrue(policy["ok"], policy)
        opportunities = handle(
            "notification.opportunities",
            {
                "item_id": task["item_id"],
                "evaluated_at_utc": "2026-03-01T00:00:00Z",
                "range_start_utc": "2026-03-08T00:00:00Z",
                "range_end_utc": "2026-03-09T00:00:00Z",
                "limit": "10",
            },
            self.context,
        )
        self.assertTrue(opportunities["ok"], opportunities)
        self.assertEqual(
            [row["eligible_at_utc"] for row in opportunities["opportunities"]],
            ["2026-03-08T15:00:00Z"],
        )

    def test_local_calendar_cadence_round_trips_selectors_and_dst_resolution(self) -> None:
        timezone_version = system_timezone_database_version()
        event = handle(
            "event.create",
            {
                "command_id": "cmd-local-calendar-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-03-01T00:00:00Z",
                "title": "Local morning cadence",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-03-12T18:00:00Z"},
            },
            self.context,
        )
        policy = handle(
            "reminder.create",
            {
                "command_id": "cmd-local-calendar-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-03-01T00:01:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {
                        "kind": "repeat_window",
                        "start": {"kind": "absolute_utc", "at_utc": "2026-03-07T00:00:00Z"},
                        "stop": {"kind": "absolute_utc", "at_utc": "2026-03-11T00:00:00Z"},
                        "stop_inclusive": False,
                        "cadence": {
                            "kind": "local_calendar",
                            "frequency": "DAILY",
                            "seed_local_date": "2026-03-07",
                            "local_time": "08:00:00",
                            "timezone": "America/Los_Angeles",
                            "timezone_database_version": timezone_version,
                        },
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        self.assertTrue(policy["ok"], policy)
        opportunities = handle(
            "notification.opportunities",
            {
                "item_id": event["item_id"],
                "evaluated_at_utc": "2026-03-01T00:00:00Z",
                "range_start_utc": "2026-03-07T00:00:00Z",
                "range_end_utc": "2026-03-11T00:00:00Z",
                "limit": "10",
            },
            self.context,
        )
        self.assertEqual(
            [row["eligible_at_utc"] for row in opportunities["opportunities"]],
            [
                "2026-03-07T16:00:00Z",
                "2026-03-08T15:00:00Z",
                "2026-03-09T15:00:00Z",
                "2026-03-10T15:00:00Z",
            ],
        )

    def test_recurrence_provenance_is_idempotent_and_enables_notification_targeting(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-recurring-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:02:00Z",
                "title": "Daily sync",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": "2026-08-08T18:00:00Z",
                    "recurrence_set": {
                        "time_basis": "instant_utc",
                        "rules": [
                            {
                                "frequency": "DAILY",
                                "interval": "1",
                                "seed": "2026-08-08T18:00:00Z",
                                "start_bound": "2026-08-08T18:00:00Z",
                                "end_condition": {"kind": "count", "count": "3"},
                            }
                        ],
                    },
                },
            },
            self.context,
        )
        create_policy = handle(
            "reminder.create",
            {
                "command_id": "cmd-each-reminder",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-08-07T18:00:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "delivery_target_id": "whatsapp-owner",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {
                        "anchor_role": "event_start",
                        "application_scope": "each_occurrence",
                    },
                    "schedule": {
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-21600",
                        },
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            self.context,
        )
        recurrence = self.connection.execute(
            "SELECT recurrence_set_id FROM recurrence_sets WHERE source_item_id = ?",
            (event["item_id"],),
        ).fetchone()
        revision = self.connection.execute(
            "SELECT recurrence_revision_id FROM recurrence_revisions WHERE recurrence_set_id = ?",
            (recurrence["recurrence_set_id"],),
        ).fetchone()
        request = {
            "command_id": "cmd-provenance",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "2",
            "recurrence_set_id": recurrence["recurrence_set_id"],
            "recurrence_revision_id": revision["recurrence_revision_id"],
            "regenerated_at_utc": "2026-08-07T18:01:00Z",
            "consumer": "notification_schedule",
            "range_start": "2026-08-08T00:00:00Z",
            "range_end": "2026-08-12T00:00:00Z",
        }
        generated = handle("occurrence_provenance.regenerate", request, self.context)
        replay = handle("occurrence_provenance.regenerate", request, self.context)
        opportunities = handle(
            "notification.opportunities",
            {
                "item_id": event["item_id"],
                "evaluated_at_utc": "2026-08-08T10:00:00Z",
                "range_start_utc": "2026-08-08T10:00:00Z",
                "range_end_utc": "2026-08-11T18:00:00Z",
                "limit": "100",
            },
            self.context,
        )

        self.assertTrue(create_policy["ok"], create_policy)
        self.assertTrue(generated["ok"], generated)
        self.assertEqual(generated["selected_count"], "3")
        self.assertEqual(generated["effect"], "provenance_regenerate_replaced")
        self.assertEqual(replay, generated)
        self.assertTrue(opportunities["ok"], opportunities)
        self.assertEqual(len(opportunities["opportunities"]), 3)
        self.assertTrue(all(value["occurrence_provenance_id"] for value in opportunities["opportunities"]))

        materialized = handle(
            "notification_work.materialize",
            {
                "command_id": "cmd-each-materialize",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "materialized_at_utc": "2026-08-08T10:00:00Z",
                "range_start_utc": "2026-08-08T10:00:00Z",
                "range_end_utc": "2026-08-11T18:00:00Z",
                "limit": "100",
            },
            self.context,
        )
        work_id = materialized["created_work_instance_ids"][0]
        changed = handle(
            "recurrence.instance.add",
            {
                "command_id": "cmd-add-after-work",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "recurrence_set_id": recurrence["recurrence_set_id"],
                "recurrence_revision_id": revision["recurrence_revision_id"],
                "added_at_utc": "2026-08-08T10:01:00Z",
                "scheduled_fact": "2026-08-15T18:00:00Z",
            },
            self.context,
        )
        self.assertTrue(changed["ok"], changed)
        with self.assertRaisesRegex(SpineValidationError, "recovery report"):
            prepare_work_attempt(
                self.connection,
                work_instance_id=work_id,
                adapter_name="openclaw",
                idempotency_key="stale-work",
                request_envelope={"kind": "test"},
                attempted_at_utc="2026-08-08T10:02:00Z",
            )
        report = self.connection.execute("SELECT * FROM recurrence_provenance_block_reports WHERE status = 'open'").fetchone()
        self.assertIsNotNone(report)
        recovered = handle(
            "occurrence_provenance.regenerate",
            {
                **request,
                "command_id": "cmd-provenance-recover",
                "target_version": "3",
                "recurrence_revision_id": changed["recurrence_revision_id"],
                "regenerated_at_utc": "2026-08-08T10:03:00Z",
            },
            self.context,
        )
        self.assertIn(report["block_report_id"], recovered["closed_block_report_ids"])


if __name__ == "__main__":
    unittest.main()
