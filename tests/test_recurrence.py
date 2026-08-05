import unittest

from spine.core import SpineValidationError
from spine.core.recurrence import (
    expand_daily_local_occurrences,
    normalize_daily_recurrence_rule,
    occurrence_id,
    occurrence_key,
    parse_daily_recurrence_rule,
)


class RecurrenceTests(unittest.TestCase):
    def test_daily_rule_normalizes_and_defaults_interval(self) -> None:
        self.assertEqual(
            normalize_daily_recurrence_rule("freq=daily"),
            "FREQ=DAILY;INTERVAL=1",
        )
        self.assertEqual(
            normalize_daily_recurrence_rule("COUNT=5;INTERVAL=2;FREQ=DAILY"),
            "FREQ=DAILY;INTERVAL=2;COUNT=5",
        )

    def test_daily_rule_rejects_unsupported_or_invalid_parts(self) -> None:
        for rule in (
            "FREQ=WEEKLY",
            "FREQ=DAILY;BYDAY=MO",
            "FREQ=DAILY;INTERVAL=0",
            "FREQ=DAILY;COUNT=01",
            "FREQ=DAILY;FREQ=DAILY",
        ):
            with self.subTest(rule=rule), self.assertRaises(SpineValidationError):
                parse_daily_recurrence_rule(rule)

    def test_daily_local_instant_expansion_is_bounded_and_stable(self) -> None:
        result = expand_daily_local_occurrences(
            item_id="morning-item",
            anchor_kind="local_instant",
            seed_local_date="2026-07-25",
            seed_local_time="08:00",
            timezone="America/Denver",
            recurrence_rule="FREQ=DAILY",
            range_start_local_date="2026-07-27",
            range_end_local_date="2026-07-30",
            limit=10,
        )

        self.assertFalse(result.truncated)
        self.assertEqual(
            [occurrence.local_date for occurrence in result.occurrences],
            ["2026-07-27", "2026-07-28", "2026-07-29"],
        )
        self.assertEqual([occurrence.ordinal for occurrence in result.occurrences], [3, 4, 5])
        self.assertEqual(result.occurrences[0].local_time, "08:00:00")
        self.assertEqual(
            result.occurrences[0].occurrence_key,
            "local_instant:2026-07-27T08:00:00[America/Denver]",
        )

    def test_count_and_interval_bound_the_expansion(self) -> None:
        result = expand_daily_local_occurrences(
            item_id="every-other-day",
            anchor_kind="local_date",
            seed_local_date="2026-07-25",
            seed_local_time=None,
            timezone="America/Denver",
            recurrence_rule="FREQ=DAILY;INTERVAL=2;COUNT=3",
            range_start_local_date="2026-07-01",
            range_end_local_date="2026-08-15",
            limit=10,
        )

        self.assertEqual(
            [occurrence.local_date for occurrence in result.occurrences],
            ["2026-07-25", "2026-07-27", "2026-07-29"],
        )
        self.assertFalse(result.truncated)

    def test_limit_reports_truncation(self) -> None:
        result = expand_daily_local_occurrences(
            item_id="daily",
            anchor_kind="local_date",
            seed_local_date="2026-07-25",
            seed_local_time=None,
            timezone="America/Denver",
            recurrence_rule="FREQ=DAILY",
            range_start_local_date="2026-07-25",
            range_end_local_date="2026-08-01",
            limit=2,
        )

        self.assertEqual(len(result.occurrences), 2)
        self.assertTrue(result.truncated)

    def test_expansion_horizon_is_bounded_from_the_seed(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_recurrence_range"):
            expand_daily_local_occurrences(
                item_id="old-daily",
                anchor_kind="local_date",
                seed_local_date="2000-01-01",
                seed_local_time=None,
                timezone="America/Denver",
                recurrence_rule="FREQ=DAILY",
                range_start_local_date="2026-07-25",
                range_end_local_date="2026-07-26",
                limit=10,
            )

    def test_nonexistent_local_time_is_omitted_without_changing_wall_clock(self) -> None:
        result = expand_daily_local_occurrences(
            item_id="dst-gap",
            anchor_kind="local_instant",
            seed_local_date="2026-03-07",
            seed_local_time="02:30",
            timezone="America/Denver",
            recurrence_rule="FREQ=DAILY;COUNT=3",
            range_start_local_date="2026-03-07",
            range_end_local_date="2026-03-12",
            limit=10,
        )

        self.assertEqual(
            [occurrence.local_date for occurrence in result.occurrences],
            ["2026-03-07", "2026-03-09", "2026-03-10"],
        )
        self.assertEqual([occurrence.ordinal for occurrence in result.occurrences], [1, 2, 3])
        self.assertTrue(all(occurrence.local_time == "02:30:00" for occurrence in result.occurrences))

    def test_daily_eight_am_stays_at_eight_across_offset_change(self) -> None:
        result = expand_daily_local_occurrences(
            item_id="daily-eight",
            anchor_kind="local_instant",
            seed_local_date="2026-10-31",
            seed_local_time="08:00",
            timezone="America/Denver",
            recurrence_rule="FREQ=DAILY",
            range_start_local_date="2026-10-31",
            range_end_local_date="2026-11-03",
            limit=10,
        )

        self.assertEqual(
            [occurrence.local_date for occurrence in result.occurrences],
            ["2026-10-31", "2026-11-01", "2026-11-02"],
        )
        self.assertTrue(all(occurrence.local_time == "08:00:00" for occurrence in result.occurrences))

    def test_occurrence_identity_uses_original_local_schedule(self) -> None:
        key = occurrence_key(
            anchor_kind="local_instant",
            local_date_value="2026-07-25",
            local_time_value="08:00:00",
            timezone="America/Denver",
        )

        self.assertEqual(
            occurrence_id(item_id="item-1", occurrence_key_value=key),
            occurrence_id(item_id="item-1", occurrence_key_value=key),
        )
        self.assertNotEqual(
            occurrence_id(item_id="item-1", occurrence_key_value=key),
            occurrence_id(item_id="item-2", occurrence_key_value=key),
        )


if __name__ == "__main__":
    unittest.main()
