import unittest
from datetime import date, datetime

from spine.core import SpineValidationError
from spine.core.schedule import (
    expand_rule,
    normalize_rule,
    parse_scheduled_fact,
    resolve_local_instant,
    system_timezone_database_version,
)


def rule(
    *,
    frequency: str,
    seed: str,
    start_bound: str | None = None,
    end_condition: dict[str, str] | None = None,
    **selectors: object,
) -> dict[str, object]:
    return {
        "frequency": frequency,
        "seed": seed,
        "start_bound": start_bound or seed,
        "end_condition": end_condition or {"kind": "unbounded"},
        **selectors,
    }


class CanonicalScheduleEngineTests(unittest.TestCase):
    def test_rule_defaults_are_hash_ready(self) -> None:
        daily = normalize_rule(
            rule(frequency="DAILY", seed="2026-08-08T08:00:00"),
            time_basis="local_instant",
        )
        self.assertEqual(daily.as_contract()["interval"], "1")

        weekly = normalize_rule(
            rule(frequency="WEEKLY", seed="2026-08-08"),
            time_basis="local_date",
        )
        self.assertEqual(weekly.as_contract()["by_weekday"], ["SA"])
        self.assertEqual(weekly.as_contract()["week_start"], "MO")

        monthly = normalize_rule(
            rule(frequency="MONTHLY", seed="2026-08-31"),
            time_basis="local_date",
        )
        self.assertEqual(monthly.as_contract()["by_month_day"], ["31"])

        yearly = normalize_rule(
            rule(frequency="YEARLY", seed="2024-02-29T12:00:00Z"),
            time_basis="instant_utc",
        )
        self.assertEqual(yearly.as_contract()["by_month"], ["2"])
        self.assertEqual(yearly.as_contract()["by_month_day"], ["29"])

    def test_selector_arrays_normalize_in_contract_order(self) -> None:
        normalized = normalize_rule(
            rule(
                frequency="YEARLY",
                seed="2026-01-01",
                by_month=["12", "1", "6"],
                by_weekday=["FR", "MO"],
                by_set_position=["-1", "1"],
            ),
            time_basis="local_date",
        )
        self.assertEqual(normalized.as_contract()["by_month"], ["1", "6", "12"])
        self.assertEqual(normalized.as_contract()["by_weekday"], ["MO", "FR"])
        self.assertEqual(normalized.as_contract()["by_set_position"], ["-1", "1"])

    def test_invalid_selector_families_fail_closed(self) -> None:
        invalid = (
            rule(frequency="DAILY", seed="2026-08-08", by_weekday=["SA"]),
            rule(frequency="WEEKLY", seed="2026-08-08", by_month=["8"]),
            rule(
                frequency="MONTHLY",
                seed="2026-08-08",
                by_month_day=["8"],
                by_weekday=["SA"],
            ),
            rule(frequency="YEARLY", seed="2026-08-08", by_set_position=["1"]),
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SpineValidationError):
                normalize_rule(value, time_basis="local_date")

    def test_every_three_days_local_instant(self) -> None:
        timezone_version = system_timezone_database_version()
        result = expand_rule(
            rule(frequency="DAILY", seed="2026-08-08T08:00:00", interval="3"),
            time_basis="local_instant",
            timezone="America/Los_Angeles",
            timezone_database_version=timezone_version,
            range_start="2026-08-08T00:00:00",
            range_end="2026-08-20T00:00:00",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            [
                "2026-08-08T08:00:00",
                "2026-08-11T08:00:00",
                "2026-08-14T08:00:00",
                "2026-08-17T08:00:00",
            ],
        )

    def test_weekly_interval_uses_week_start_periods(self) -> None:
        result = expand_rule(
            rule(
                frequency="WEEKLY",
                seed="2026-08-05",
                interval="2",
                by_weekday=["FR", "MO"],
                week_start="SU",
            ),
            time_basis="local_date",
            timezone="America/Los_Angeles",
            timezone_database_version=system_timezone_database_version(),
            range_start="2026-08-01",
            range_end="2026-09-01",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-08-07", "2026-08-17", "2026-08-21", "2026-08-31"],
        )

    def test_monthly_last_day_omits_no_month(self) -> None:
        result = expand_rule(
            rule(frequency="MONTHLY", seed="2026-01-31", by_month_day=["-1"]),
            time_basis="local_date",
            timezone="America/Los_Angeles",
            timezone_database_version=system_timezone_database_version(),
            range_start="2026-01-01",
            range_end="2026-05-01",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"],
        )

    def test_monthly_last_weekday_uses_set_position(self) -> None:
        result = expand_rule(
            rule(
                frequency="MONTHLY",
                seed="2026-01-01",
                by_weekday=["MO", "TU", "WE", "TH", "FR"],
                by_set_position=["-1"],
            ),
            time_basis="local_date",
            timezone="America/Los_Angeles",
            timezone_database_version=system_timezone_database_version(),
            range_start="2026-01-01",
            range_end="2026-04-01",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-01-30", "2026-02-27", "2026-03-31"],
        )

    def test_yearly_set_position_applies_across_selected_months(self) -> None:
        result = expand_rule(
            rule(
                frequency="YEARLY",
                seed="2026-01-01",
                by_month=["1", "12"],
                by_weekday=["MO"],
                by_set_position=["1", "-1"],
            ),
            time_basis="local_date",
            timezone="America/Los_Angeles",
            timezone_database_version=system_timezone_database_version(),
            range_start="2026-01-01",
            range_end="2027-01-01",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-01-05", "2026-12-28"],
        )

    def test_until_is_inclusive_for_fixed_utc(self) -> None:
        result = expand_rule(
            rule(
                frequency="DAILY",
                seed="2026-08-08T08:00:00Z",
                end_condition={"kind": "until", "until": "2026-08-10T08:00:00Z"},
            ),
            time_basis="instant_utc",
            range_start="2026-08-01T00:00:00Z",
            range_end="2026-08-20T00:00:00Z",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-08-08T08:00:00Z", "2026-08-09T08:00:00Z", "2026-08-10T08:00:00Z"],
        )

    def test_nonexistent_local_candidate_does_not_consume_count(self) -> None:
        timezone_version = system_timezone_database_version()
        result = expand_rule(
            rule(
                frequency="DAILY",
                seed="2026-03-07T02:30:00",
                end_condition={"kind": "count", "count": "3"},
            ),
            time_basis="local_instant",
            timezone="America/Denver",
            timezone_database_version=timezone_version,
            range_start="2026-03-07T00:00:00",
            range_end="2026-03-12T00:00:00",
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.candidates],
            ["2026-03-07T02:30:00", "2026-03-09T02:30:00", "2026-03-10T02:30:00"],
        )
        self.assertEqual(
            [candidate.rule_local_index for candidate in result.candidates],
            ["0", "1", "2"],
        )
        self.assertEqual(
            [candidate.scheduled_fact for candidate in result.omitted_local_candidates],
            ["2026-03-08T02:30:00"],
        )

    def test_ambiguous_local_candidate_selects_earliest_utc_instant(self) -> None:
        resolved = resolve_local_instant(
            "2026-11-01T01:30:00",
            timezone="America/Denver",
            timezone_database_version=system_timezone_database_version(),
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.resolution_kind, "ambiguous_earliest_instant")
        self.assertEqual(resolved.utc_instant, "2026-11-01T07:30:00Z")
        self.assertEqual(resolved.offset_seconds, "-21600")

    def test_pinned_timezone_database_version_fails_closed(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "environment_failure:timezone_database_version"):
            resolve_local_instant(
                "2026-08-08T08:00:00",
                timezone="America/Los_Angeles",
                timezone_database_version="not-installed",
            )

    def test_scheduled_facts_are_exact_and_ranges_are_bounded(self) -> None:
        for value in ("2026-8-08", "2026-08-08T08:00", "2026-08-08T08:00:00+00:00"):
            with self.subTest(value=value), self.assertRaises(SpineValidationError):
                parse_scheduled_fact(value, time_basis="local_date", field="fact")

        with self.assertRaisesRegex(SpineValidationError, "range_too_large"):
            expand_rule(
                rule(frequency="DAILY", seed="2026-01-01T00:00:00Z"),
                time_basis="instant_utc",
                range_start="2026-01-01T00:00:00Z",
                range_end="2037-01-02T00:00:01Z",
            )

    def test_utc_parse_returns_aware_datetime(self) -> None:
        parsed = parse_scheduled_fact(
            "2026-08-08T08:00:00Z",
            time_basis="instant_utc",
            field="fact",
        )
        self.assertIsInstance(parsed, datetime)
        assert isinstance(parsed, datetime)
        self.assertIsNotNone(parsed.tzinfo)

    def test_seeked_rule_indexes_match_full_stream_across_frequency_families(self) -> None:
        timezone_version = system_timezone_database_version()
        cases = (
            (
                rule(frequency="DAILY", seed="2020-01-01T02:30:00"),
                "local_instant",
                {"timezone": "America/Denver", "timezone_database_version": timezone_version},
                "2020-01-01T00:00:00",
                "2029-12-31T00:00:00",
                "2029-01-01T00:00:00",
            ),
            (
                rule(
                    frequency="WEEKLY",
                    seed="2020-01-01",
                    interval="3",
                    by_weekday=["MO", "WE", "FR"],
                    week_start="SU",
                ),
                "local_date",
                {"timezone": "America/Los_Angeles", "timezone_database_version": timezone_version},
                "2020-01-01",
                "2029-12-31",
                "2029-01-01",
            ),
            (
                rule(
                    frequency="MONTHLY",
                    seed="2020-01-01T08:00:00Z",
                    interval="2",
                    by_weekday=["MO", "TU", "WE", "TH", "FR"],
                    by_set_position=["-1"],
                ),
                "instant_utc",
                {},
                "2020-01-01T00:00:00Z",
                "2029-12-31T00:00:00Z",
                "2029-01-01T00:00:00Z",
            ),
            (
                rule(
                    frequency="YEARLY",
                    seed="2020-01-01",
                    by_month=["1", "6", "12"],
                    by_weekday=["MO"],
                    by_set_position=["1", "-1"],
                ),
                "local_date",
                {"timezone": "America/Los_Angeles", "timezone_database_version": timezone_version},
                "2020-01-01",
                "2029-12-31",
                "2029-01-01",
            ),
        )
        for authored, basis, timezone_facts, full_start, end, narrow_start in cases:
            with self.subTest(frequency=authored["frequency"], time_basis=basis):
                full = expand_rule(
                    authored,
                    time_basis=basis,
                    range_start=full_start,
                    range_end=end,
                    **timezone_facts,
                )
                narrow = expand_rule(
                    authored,
                    time_basis=basis,
                    range_start=narrow_start,
                    range_end=end,
                    **timezone_facts,
                )
                expected = {
                    candidate.scheduled_fact: candidate.rule_local_index
                    for candidate in full.candidates
                    if candidate.scheduled_fact >= narrow_start
                }
                self.assertEqual(
                    {candidate.scheduled_fact: candidate.rule_local_index for candidate in narrow.candidates},
                    expected,
                )

    def test_far_future_daily_seek_uses_calendar_index_without_prior_period_expansion(self) -> None:
        result = expand_rule(
            rule(frequency="DAILY", seed="0001-01-01T08:00:00"),
            time_basis="local_instant",
            timezone="UTC",
            timezone_database_version=system_timezone_database_version(),
            range_start="9000-01-01T00:00:00",
            range_end="9000-01-04T00:00:00",
        )
        expected_index = (date(9000, 1, 1) - date(1, 1, 1)).days
        self.assertEqual(
            [(candidate.scheduled_fact, candidate.rule_local_index) for candidate in result.candidates],
            [
                ("9000-01-01T08:00:00", str(expected_index)),
                ("9000-01-02T08:00:00", str(expected_index + 1)),
                ("9000-01-03T08:00:00", str(expected_index + 2)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
