from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_text
from spine.core.notification_rendering import render_notification


class NotificationRenderingTests(unittest.TestCase):
    def test_golf_examples_use_natural_deterministic_phrases(self) -> None:
        with patch(
            "spine.core.notification_rendering.system_timezone_database_version",
            return_value="2026a",
        ):
            tomorrow = render_notification(
                self._source(
                    attempted_at_utc="2026-08-23T18:00:00Z",
                    target_scheduled_fact="2026-08-24T14:00:00",
                    target_at_utc="2026-08-24T18:00:00Z",
                    location=self._location(),
                )
            )
            one_hour = render_notification(
                self._source(
                    attempted_at_utc="2026-08-24T17:00:00Z",
                    target_scheduled_fact="2026-08-24T14:00:00",
                    target_at_utc="2026-08-24T18:00:00Z",
                    location=self._location(),
                )
            )

        self.assertEqual(tomorrow.body_text, "Reminder: Tee time @ Lakeridge at 2 PM tomorrow")
        self.assertEqual(one_hour.body_text, "Reminder: Tee time @ Lakeridge in 1 hour")
        self.assertEqual(tomorrow.phrase_kind, "future_calendar")
        self.assertEqual(one_hour.phrase_kind, "future_relative")

    def test_relative_boundaries_and_half_up_minutes(self) -> None:
        cases = (
            (30, "now", "Reminder: Tee time is starting now"),
            (31, "future_relative", "Reminder: Tee time in 1 minute"),
            (89, "future_relative", "Reminder: Tee time in 1 minute"),
            (90, "future_relative", "Reminder: Tee time in 2 minutes"),
            (21_600, "future_relative", "Reminder: Tee time in 6 hours"),
            (-31, "past_relative", "Reminder: Tee time started 1 minute ago"),
            (-90, "past_relative", "Reminder: Tee time started 2 minutes ago"),
        )
        for delta, phrase_kind, body in cases:
            with self.subTest(delta=delta):
                value = render_notification(self._utc_source(delta))
                self.assertEqual(value.phrase_kind, phrase_kind)
                self.assertEqual(value.body_text, body)

    def test_task_relative_and_local_date_templates(self) -> None:
        task = render_notification({**self._utc_source(3600), "item_type": "task", "anchor_role": "task_due"})
        self.assertEqual(task.body_text, "Reminder: Tee time is due in 1 hour")
        with patch(
            "spine.core.notification_rendering.system_timezone_database_version",
            return_value="2026a",
        ):
            local_date = render_notification(
                {
                    **self._source(
                        attempted_at_utc="2026-08-23T16:00:00Z",
                        target_scheduled_fact="2026-08-24",
                        target_at_utc=None,
                    ),
                    "item_type": "task",
                    "anchor_role": "task_due",
                    "display_time_basis": "local_date",
                }
            )
        self.assertEqual(local_date.body_text, "Reminder: Tee time is due tomorrow")
        self.assertNotIn("clock", local_date.phrase_facts)

    def test_calendar_labels_clock_and_utc_authority(self) -> None:
        cases = (
            ("2026-08-23T00:00:00Z", "2026-08-23T20:00:01Z", "at 8 PM today"),
            ("2026-08-23T18:00:00Z", "2026-08-24T20:00:00Z", "at 8 PM tomorrow"),
            ("2026-08-23T18:00:00Z", "2026-08-22T12:00:00Z", "started at 12 PM yesterday"),
            ("2026-08-23T18:00:00Z", "2026-08-26T09:05:00Z", "at 9:05 AM Wednesday"),
            ("2026-08-23T18:00:00Z", "2026-09-10T09:05:00Z", "at 9:05 AM on September 10"),
            ("2026-12-31T18:00:00Z", "2027-01-10T09:05:00Z", "at 9:05 AM on January 10, 2027"),
        )
        for attempted, target, suffix in cases:
            with self.subTest(target=target):
                value = render_notification(
                    self._utc_source(
                        int(
                            (
                                datetime.strptime(target, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(attempted, "%Y-%m-%dT%H:%M:%SZ")
                            ).total_seconds()
                        ),
                        attempted_at_utc=attempted,
                    )
                )
                self.assertTrue(value.body_text.endswith(suffix), value.body_text)

    def test_location_text_normalization_and_virtual_connector(self) -> None:
        physical = render_notification(self._utc_source(3600, title="  Tee\t time  ", location=self._location(label=" Lakeridge\n Golf ")))
        virtual = render_notification(self._utc_source(3600, location=self._location(kind="virtual", label="Video room")))
        self.assertEqual(physical.body_text, "Reminder: Tee time @ Lakeridge Golf in 1 hour")
        self.assertEqual(virtual.body_text, "Reminder: Tee time via Video room in 1 hour")
        with self.assertRaisesRegex(SpineValidationError, "notification_rendering_invalid_text"):
            render_notification(self._utc_source(3600, title="Tee\u200btime"))

    def test_hashes_and_identity_are_byte_stable_and_bind_attempt_time(self) -> None:
        first = render_notification(self._utc_source(3600))
        second = render_notification(self._utc_source(3600))
        retry = render_notification({**self._utc_source(3600), "attempt_id": "attempt-2"})
        self.assertEqual(first, second)
        self.assertNotEqual(first.notification_rendering_id, retry.notification_rendering_id)
        self.assertNotEqual(first.rendering_input_hash, retry.rendering_input_hash)
        self.assertEqual(first.body_text, retry.body_text)
        self.assertEqual(canonical_json_text(first.input_hash_preimage), canonical_json_text(second.input_hash_preimage))

    def test_unavailable_timezone_and_oversized_output_fail_closed(self) -> None:
        with (
            patch(
                "spine.core.notification_rendering.system_timezone_database_version",
                return_value="2026b",
            ),
            self.assertRaisesRegex(SpineValidationError, "notification_rendering_timezone_database_unavailable"),
        ):
            render_notification(self._source())
        with self.assertRaisesRegex(SpineValidationError, "notification_rendering_output_too_large"):
            render_notification(self._utc_source(3600, title="x" * 1024))

    def _source(
        self,
        *,
        attempted_at_utc: str = "2026-08-23T18:00:00Z",
        target_scheduled_fact: str = "2026-08-24T14:00:00",
        target_at_utc: str | None = "2026-08-24T18:00:00Z",
        location: dict[str, str] | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "attempt_id": "attempt-1",
            "attempted_at_utc": attempted_at_utc,
            "work_instance_id": "work-1",
            "notification_opportunity_id": "opportunity-1",
            "notification_intent_id": "intent-1",
            "item_id": "item-1",
            "rendered_item_version": "1",
            "item_type": "event",
            "title": "Tee time",
            "anchor_role": "event_start",
            "target_scheduled_fact": target_scheduled_fact,
            "display_time_basis": "local_instant",
            "display_timezone": "America/Toronto",
            "timezone_database_version": "2026a",
            "primary_location": location,
        }
        if target_at_utc is not None:
            result["target_at_utc"] = target_at_utc
        return result

    def _utc_source(
        self,
        delta: int,
        *,
        attempted_at_utc: str = "2026-08-23T14:00:00Z",
        title: str = "Tee time",
        location: dict[str, str] | None = None,
    ) -> dict[str, object]:
        attempted = datetime.strptime(attempted_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        target = (attempted + timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "attempt_id": "attempt-1",
            "attempted_at_utc": attempted_at_utc,
            "work_instance_id": "work-1",
            "notification_opportunity_id": "opportunity-1",
            "notification_intent_id": "intent-1",
            "item_id": "item-1",
            "rendered_item_version": "1",
            "item_type": "event",
            "title": title,
            "anchor_role": "event_start",
            "target_scheduled_fact": target,
            "target_at_utc": target,
            "display_time_basis": "instant_utc",
            "display_timezone": "UTC",
            "timezone_database_version": None,
            "primary_location": location,
        }

    @staticmethod
    def _location(*, kind: str = "place", label: str = "Lakeridge") -> dict[str, str]:
        return {
            "location_id": "location-1",
            "item_location_id": "item-location-1",
            "location_kind": kind,
            "location_label": label,
        }


if __name__ == "__main__":
    unittest.main()
