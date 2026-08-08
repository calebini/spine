from __future__ import annotations

import unittest

from spine.core.errors import SpineValidationError
from spine.core.notifications import expand_notification_policy, normalize_notification_policy
from spine.core.schedule import system_timezone_database_version


class NotificationScheduleEngineTests(unittest.TestCase):
    def test_hourly_six_hours_before_produces_six_distinct_opportunities(self) -> None:
        policy = self._policy(
            schedule={
                "kind": "repeat_window",
                "start": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-21600"},
                "stop": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "0"},
                "stop_inclusive": False,
                "cadence": {"kind": "fixed_elapsed", "interval_seconds": "3600"},
            },
            late={"kind": "deliver_within", "grace_seconds": "900"},
        )
        expanded = expand_notification_policy(
            policy.value,
            targets=[
                {
                    "target_scheduled_fact": "2026-08-10T18:00:00Z",
                    "target_utc_instant": "2026-08-10T18:00:00Z",
                }
            ],
            evaluated_at_utc="2026-08-10T11:00:00Z",
            range_start_utc="2026-08-10T00:00:00Z",
            range_end_utc="2026-08-11T00:00:00Z",
        )
        self.assertEqual(
            [value["eligible_at_utc"] for value in expanded.opportunities],
            [
                "2026-08-10T12:00:00Z",
                "2026-08-10T13:00:00Z",
                "2026-08-10T14:00:00Z",
                "2026-08-10T15:00:00Z",
                "2026-08-10T16:00:00Z",
                "2026-08-10T17:00:00Z",
            ],
        )
        self.assertEqual(len({row["notification_opportunity_id"] for row in expanded.opportunities}), 6)

    def test_offsets_normalize_order_and_duplicates(self) -> None:
        left = self._policy(
            schedule={
                "kind": "offsets",
                "at": [
                    {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                    {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-86400"},
                    {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                ],
            },
            late={"kind": "skip"},
        )
        right = self._policy(
            schedule={
                "kind": "offsets",
                "at": [
                    {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-86400"},
                    {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                ],
            },
            late={"kind": "skip"},
        )
        self.assertEqual(left.value["schedule"], right.value["schedule"])
        self.assertEqual(left.value["normalized_notification_schedule_hash"], right.value["normalized_notification_schedule_hash"])

    def test_calendar_day_offset_preserves_local_clock_across_dst(self) -> None:
        version = system_timezone_database_version()
        policy = self._policy(
            schedule={
                "kind": "once",
                "at": {
                    "kind": "target_offset",
                    "offset_basis": "calendar_days",
                    "offset_days": "-1",
                    "local_time": "08:00:00",
                },
            },
            late={"kind": "skip"},
        )
        expanded = expand_notification_policy(
            policy.value,
            targets=[
                {
                    "target_scheduled_fact": "2026-03-09T10:00:00",
                    "target_utc_instant": "2026-03-09T17:00:00Z",
                    "target_local_date": "2026-03-09",
                    "timezone": "America/Los_Angeles",
                    "timezone_database_version": version,
                }
            ],
            evaluated_at_utc="2026-03-01T00:00:00Z",
            range_start_utc="2026-03-08T00:00:00Z",
            range_end_utc="2026-03-09T00:00:00Z",
        )
        self.assertEqual(expanded.opportunities[0]["eligible_at_utc"], "2026-03-08T15:00:00Z")

    def test_local_calendar_daily_cadence_survives_dst(self) -> None:
        version = system_timezone_database_version()
        policy = self._policy(
            schedule={
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
                    "timezone_database_version": version,
                },
            },
            late={"kind": "skip"},
        )
        expanded = expand_notification_policy(
            policy.value,
            targets=[
                {
                    "target_scheduled_fact": "2026-03-12T10:00:00Z",
                    "target_utc_instant": "2026-03-12T10:00:00Z",
                }
            ],
            evaluated_at_utc="2026-03-01T00:00:00Z",
            range_start_utc="2026-03-07T00:00:00Z",
            range_end_utc="2026-03-11T00:00:00Z",
        )
        self.assertEqual(
            [row["eligible_at_utc"] for row in expanded.opportunities],
            [
                "2026-03-07T16:00:00Z",
                "2026-03-08T15:00:00Z",
                "2026-03-09T15:00:00Z",
                "2026-03-10T15:00:00Z",
            ],
        )

    def test_dense_fixed_cadence_seeks_to_the_requested_range(self) -> None:
        policy = self._policy(
            schedule={
                "kind": "repeat_window",
                "start": {"kind": "absolute_utc", "at_utc": "2026-01-01T00:00:00Z"},
                "stop": {"kind": "absolute_utc", "at_utc": "2026-05-01T00:00:00Z"},
                "stop_inclusive": False,
                "cadence": {"kind": "fixed_elapsed", "interval_seconds": "3600"},
            },
            late={"kind": "deliver_within", "grace_seconds": "31557600"},
        )
        expanded = expand_notification_policy(
            policy.value,
            targets=[
                {
                    "target_scheduled_fact": "2026-05-01T00:00:00Z",
                    "target_utc_instant": "2026-05-01T00:00:00Z",
                }
            ],
            evaluated_at_utc="2026-04-29T00:00:00Z",
            range_start_utc="2026-04-29T00:00:00Z",
            range_end_utc="2026-04-30T00:00:00Z",
            candidate_limit=25,
            include_diagnostics=True,
        )

        self.assertEqual(len(expanded.opportunities), 24)
        self.assertEqual(expanded.opportunities[0]["eligible_at_utc"], "2026-04-29T00:00:00Z")
        self.assertEqual(expanded.opportunities[-1]["eligible_at_utc"], "2026-04-29T23:00:00Z")
        self.assertEqual(expanded.diagnostics, ())

    def test_local_calendar_timezone_pin_is_validated_at_authoring(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "environment_failure:timezone_database_version"):
            self._policy(
                schedule={
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
                        "timezone_database_version": "not-installed",
                    },
                },
                late={"kind": "skip"},
            )

    def test_calendar_day_boundary_timezone_name_is_validated_at_authoring(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_request:timezone"):
            self._policy(
                schedule={
                    "kind": "once",
                    "at": {
                        "kind": "target_offset",
                        "offset_basis": "calendar_days",
                        "offset_days": "-1",
                        "local_time": "08:00:00",
                        "timezone": "Not/A_Real_Zone",
                        "timezone_database_version": system_timezone_database_version(),
                    },
                },
                late={"kind": "skip"},
            )

    def test_late_skip_and_delivery_grace_are_distinct_from_identity(self) -> None:
        schedule = {
            "kind": "once",
            "at": {"kind": "absolute_utc", "at_utc": "2026-08-10T10:00:00Z"},
        }
        skipped = self._policy(schedule=schedule, late={"kind": "skip"})
        grace = self._policy(schedule=schedule, late={"kind": "deliver_within", "grace_seconds": "900"})
        target = [{"target_scheduled_fact": "2026-08-10T18:00:00Z", "target_utc_instant": "2026-08-10T18:00:00Z"}]
        common = {
            "targets": target,
            "evaluated_at_utc": "2026-08-10T10:10:00Z",
            "range_start_utc": "2026-08-10T00:00:00Z",
            "range_end_utc": "2026-08-11T00:00:00Z",
        }
        self.assertEqual(expand_notification_policy(skipped.value, **common).opportunities, ())
        self.assertEqual(len(expand_notification_policy(grace.value, **common).opportunities), 1)

    def _policy(self, *, schedule, late):
        return normalize_notification_policy(
            {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "event_start", "application_scope": "item"},
                "schedule": schedule,
                "late_handling": late,
            },
            item_id="item_event",
            item_version="2",
            command_id="cmd_notification",
            created_at_utc="2026-08-07T18:00:00Z",
            recipient_kind="subject",
            recipient_id="subject_owner",
            channel="whatsapp",
            delivery_target_id="delivery_target_whatsapp",
        )


if __name__ == "__main__":
    unittest.main()
