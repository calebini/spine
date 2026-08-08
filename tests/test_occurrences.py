from __future__ import annotations

import copy
import unittest

from spine.core.occurrences import expand_recurrence_set
from spine.core.recurrence_set import normalize_initial_recurrence_set
from spine.core.schedule import system_timezone_database_version


class RecurrenceSetExpansionTests(unittest.TestCase):
    def test_cross_rule_and_rdate_union_has_one_stable_occurrence(self) -> None:
        normalized = normalize_initial_recurrence_set(
            {
                "time_basis": "instant_utc",
                "rules": [
                    {
                        "frequency": "DAILY",
                        "seed": "2026-08-01T08:00:00Z",
                        "start_bound": "2026-08-01T08:00:00Z",
                        "end_condition": {"kind": "count", "count": "2"},
                    },
                    {
                        "frequency": "WEEKLY",
                        "by_weekday": ["SA"],
                        "seed": "2026-08-01T08:00:00Z",
                        "start_bound": "2026-08-01T08:00:00Z",
                        "end_condition": {"kind": "count", "count": "1"},
                    },
                ],
                "rdates": [{"scheduled_fact": "2026-08-01T08:00:00Z"}],
            },
            source_item_id="item_union",
            seed_anchor_id="anchor_union",
            seed_scheduled_fact="2026-08-01T08:00:00Z",
            created_item_version="1",
            source_item_version="1",
            command_id="cmd_union",
        )
        expanded = expand_recurrence_set(
            normalized.value,
            range_start="2026-08-01T00:00:00Z",
            range_end="2026-08-03T00:00:00Z",
        )

        self.assertEqual(len(expanded.occurrences), 2)
        union = expanded.occurrences[0]
        self.assertEqual(union["origin_kind"], "union")
        self.assertEqual(len(union["source_rule_ids"]), 2)  # type: ignore[arg-type]
        self.assertEqual(len(union["source_rdate_ids"]), 1)  # type: ignore[arg-type]
        self.assertEqual(
            [entry["rule_local_index"] for entry in union["source_entries"] if entry["source_kind"] == "rule"],  # type: ignore[index]
            ["0", "0"],
        )
        self.assertTrue(str(union["occurrence_key"]).count(".") == 1)

    def test_occurrence_key_ignores_current_source_ids_but_occurrence_id_binds_revision(self) -> None:
        first = self._daily_local_set(command_id="cmd_first")
        second = copy.deepcopy(first.value)
        second["recurrence_revision_id"] = "recurrence_revision_new"
        second["normalized_recurrence_set_hash"] = "b" * 64
        second["rules"][0]["rule_id"] = "recurrence_rule_new"  # type: ignore[index]
        left = expand_recurrence_set(
            first.value,
            range_start="2026-08-01T00:00:00",
            range_end="2026-08-03T00:00:00",
        ).occurrences[0]
        right = expand_recurrence_set(
            second,
            range_start="2026-08-01T00:00:00",
            range_end="2026-08-03T00:00:00",
        ).occurrences[0]
        self.assertEqual(left["occurrence_key"], right["occurrence_key"])
        self.assertNotEqual(left["occurrence_id"], right["occurrence_id"])
        self.assertNotEqual(left["source_rule_ids"], right["source_rule_ids"])

    def test_exdate_removes_and_move_override_changes_expressed_order(self) -> None:
        normalized = self._daily_local_set(command_id="cmd_exceptions")
        baseline = expand_recurrence_set(
            normalized.value,
            range_start="2026-08-01T00:00:00",
            range_end="2026-08-05T00:00:00",
        )
        first_key = baseline.occurrences[0]["occurrence_key"]
        second_key = baseline.occurrences[1]["occurrence_key"]
        changed = copy.deepcopy(normalized.value)
        changed["exdates"] = [
            {
                "exdate_id": "recurrence_exdate_one",
                "segment_id": changed["segments"][0]["segment_id"],
                "target_occurrence_key": first_key,
                "target_occurrence_selector": baseline.occurrences[0]["target_occurrence_selector"],
                "scheduled_fact": baseline.occurrences[0]["original_scheduled_fact"],
                "reason_code": "skip",
                "status": "active",
            }
        ]
        changed["overrides"] = [
            {
                "override_id": "recurrence_override_two",
                "segment_id": changed["segments"][0]["segment_id"],
                "target_occurrence_key": second_key,
                "target_occurrence_selector": baseline.occurrences[1]["target_occurrence_selector"],
                "override_kind": "move",
                "revision_key": "revkey_two",
                "expressed_scheduled_fact": "2026-08-04T08:00:00",
                "status": "active",
            }
        ]
        expanded = expand_recurrence_set(
            changed,
            range_start="2026-08-01T00:00:00",
            range_end="2026-08-05T23:00:00",
            range_basis="expressed_time",
        )
        keys = [entry["occurrence_key"] for entry in expanded.occurrences]
        self.assertNotIn(first_key, keys)
        moved = next(entry for entry in expanded.occurrences if entry["occurrence_key"] == second_key)
        self.assertEqual(moved["expressed_scheduled_fact"], "2026-08-04T08:00:00")
        self.assertEqual(moved["override_id"], "recurrence_override_two")

    def test_expressed_range_includes_occurrence_moved_in_from_outside_original_range(self) -> None:
        normalized = self._daily_local_set(command_id="cmd_moved_in")
        baseline = expand_recurrence_set(
            normalized.value,
            range_start="2026-08-01T00:00:00",
            range_end="2026-08-06T00:00:00",
        )
        original = baseline.occurrences[0]
        changed = copy.deepcopy(normalized.value)
        changed["overrides"] = [
            {
                "override_id": "recurrence_override_moved_in",
                "segment_id": changed["segments"][0]["segment_id"],
                "target_occurrence_key": original["occurrence_key"],
                "target_occurrence_selector": original["target_occurrence_selector"],
                "override_kind": "move",
                "revision_key": "revkey_moved_in",
                "expressed_scheduled_fact": "2026-09-10T08:00:00",
                "status": "active",
            }
        ]

        expressed = expand_recurrence_set(
            changed,
            range_start="2026-09-10T00:00:00",
            range_end="2026-09-11T00:00:00",
            range_basis="expressed_time",
        )

        self.assertEqual(len(expressed.occurrences), 1)
        self.assertEqual(expressed.occurrences[0]["occurrence_key"], original["occurrence_key"])
        self.assertEqual(
            expressed.occurrences[0]["original_scheduled_fact"],
            "2026-08-01T08:00:00",
        )

    def test_dst_diagnostic_is_source_specific(self) -> None:
        version = system_timezone_database_version()
        normalized = normalize_initial_recurrence_set(
            {
                "time_basis": "local_instant",
                "timezone": "America/Los_Angeles",
                "timezone_database_version": version,
                "rules": [
                    {
                        "frequency": "DAILY",
                        "seed": "2026-03-07T02:30:00",
                        "start_bound": "2026-03-07T02:30:00",
                        "end_condition": {"kind": "count", "count": "3"},
                    }
                ],
            },
            source_item_id="item_dst",
            seed_anchor_id="anchor_dst",
            seed_scheduled_fact="2026-03-07T02:30:00",
            created_item_version="1",
            source_item_version="1",
        )
        expanded = expand_recurrence_set(
            normalized.value,
            range_start="2026-03-07T00:00:00",
            range_end="2026-03-12T00:00:00",
            include_diagnostics=True,
        )
        self.assertEqual(len(expanded.occurrences), 3)
        self.assertEqual(len(expanded.diagnostics), 1)
        self.assertEqual(expanded.diagnostics[0]["scheduled_fact"], "2026-03-08T02:30:00")
        self.assertEqual(expanded.diagnostics[0]["source_id"], normalized.value["rules"][0]["rule_id"])  # type: ignore[index]

    def test_nonexistent_rdate_emits_source_specific_diagnostic(self) -> None:
        version = system_timezone_database_version()
        normalized = normalize_initial_recurrence_set(
            {
                "time_basis": "local_instant",
                "timezone": "America/Los_Angeles",
                "timezone_database_version": version,
                "rules": [
                    {
                        "frequency": "DAILY",
                        "seed": "2026-03-07T03:30:00",
                        "start_bound": "2026-03-07T03:30:00",
                        "end_condition": {"kind": "count", "count": "1"},
                    }
                ],
                "rdates": [{"scheduled_fact": "2026-03-08T02:30:00"}],
            },
            source_item_id="item_dst_rdate",
            seed_anchor_id="anchor_dst_rdate",
            seed_scheduled_fact="2026-03-07T03:30:00",
            created_item_version="1",
            source_item_version="1",
        )
        expanded = expand_recurrence_set(
            normalized.value,
            range_start="2026-03-07T00:00:00",
            range_end="2026-03-10T00:00:00",
            include_diagnostics=True,
        )
        rdate_id = normalized.value["rdates"][0]["rdate_id"]  # type: ignore[index]
        diagnostic = next(value for value in expanded.diagnostics if value["source_id"] == rdate_id)
        self.assertEqual(diagnostic["scheduled_fact"], "2026-03-08T02:30:00")

    def _daily_local_set(self, *, command_id: str):
        version = system_timezone_database_version()
        return normalize_initial_recurrence_set(
            {
                "time_basis": "local_instant",
                "timezone": "America/Los_Angeles",
                "timezone_database_version": version,
                "rules": [
                    {
                        "frequency": "DAILY",
                        "seed": "2026-08-01T08:00:00",
                        "start_bound": "2026-08-01T08:00:00",
                        "end_condition": {"kind": "count", "count": "4"},
                    }
                ],
            },
            source_item_id="item_daily",
            seed_anchor_id="anchor_daily",
            seed_scheduled_fact="2026-08-01T08:00:00",
            created_item_version="1",
            source_item_version="1",
            command_id=command_id,
        )


if __name__ == "__main__":
    unittest.main()
