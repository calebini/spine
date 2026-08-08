from __future__ import annotations

import copy
import unittest

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_set import normalize_initial_recurrence_set
from spine.core.schedule import system_timezone_database_version


class InitialRecurrenceSetNormalizationTests(unittest.TestCase):
    def test_derives_complete_every_three_days_revision(self) -> None:
        version = system_timezone_database_version()
        result = normalize_initial_recurrence_set(
            {
                "time_basis": "local_instant",
                "timezone": "America/Los_Angeles",
                "timezone_database_version": version,
                "rules": [
                    {
                        "frequency": "DAILY",
                        "interval": "3",
                        "seed": "2026-08-03T08:00:00",
                        "start_bound": "2026-08-03T08:00:00",
                        "end_condition": {"kind": "unbounded"},
                    }
                ],
            },
            source_item_id="item_morning",
            seed_anchor_id="anchor_morning",
            seed_scheduled_fact="2026-08-03T08:00:00",
            created_item_version="1",
            source_item_version="1",
            command_id="cmd_create_morning",
        )

        value = result.value
        self.assertEqual(value["normalized_recurrence_set_hash"], hash_canonical_json(result.normalized_hash_preimage))
        self.assertEqual(value["segments"][0]["active_start"], "2026-08-03T08:00:00")  # type: ignore[index]
        self.assertEqual(value["rules"][0]["interval"], "3")  # type: ignore[index]
        self.assertEqual(value["rdates"], [])
        self.assertEqual(value["exdates"], [])
        self.assertEqual(value["overrides"], [])
        self.assertTrue(str(value["recurrence_set_id"]).startswith("recurrence_set_"))
        self.assertTrue(str(value["recurrence_revision_id"]).startswith("recurrence_revision_"))
        self.assertEqual(
            value["recurrence_set_id"],
            "recurrence_set_" + hash_canonical_json(result.recurrence_set_id_preimage),
        )
        self.assertEqual(
            value["recurrence_revision_id"],
            "recurrence_revision_" + hash_canonical_json(result.recurrence_revision_id_preimage),
        )
        self.assertNotIn("segment_id", result.normalized_hash_preimage["segments"][0])  # type: ignore[index]
        self.assertEqual(result.normalized_hash_preimage["rules"][0]["segment_ref"], "0")  # type: ignore[index]

    def test_request_order_is_not_hash_bearing_and_active_duplicates_collapse(self) -> None:
        authoring = {
            "time_basis": "instant_utc",
            "segments": [
                {"segment_label": "later", "active_start": "2026-09-01T08:00:00Z"},
                {
                    "segment_label": "first",
                    "active_start": "2026-08-01T08:00:00Z",
                    "active_end": "2026-09-01T08:00:00Z",
                },
            ],
            "rules": [
                {
                    "segment_label": "later",
                    "frequency": "WEEKLY",
                    "by_weekday": ["FR", "MO"],
                    "seed": "2026-09-01T08:00:00Z",
                    "start_bound": "2026-09-01T08:00:00Z",
                    "end_condition": {"kind": "unbounded"},
                },
                {
                    "segment_label": "first",
                    "frequency": "DAILY",
                    "seed": "2026-08-01T08:00:00Z",
                    "start_bound": "2026-08-01T08:00:00Z",
                    "end_condition": {"kind": "until", "until": "2026-08-31T08:00:00Z"},
                },
            ],
            "rdates": [
                {"segment_label": "later", "scheduled_fact": "2026-09-03T08:00:00Z"},
                {"segment_label": "later", "scheduled_fact": "2026-09-03T08:00:00Z"},
            ],
        }
        reordered = copy.deepcopy(authoring)
        reordered["segments"].reverse()
        reordered["rules"].reverse()
        reordered["rules"][1]["by_weekday"] = list(reversed(reordered["rules"][1]["by_weekday"]))
        reordered["rdates"].reverse()

        kwargs = {
            "source_item_id": "item_order",
            "seed_anchor_id": "anchor_order",
            "seed_scheduled_fact": "2026-08-01T08:00:00Z",
            "created_item_version": "1",
            "source_item_version": "1",
            "command_id": "cmd_order",
        }
        left = normalize_initial_recurrence_set(authoring, **kwargs)
        right = normalize_initial_recurrence_set(reordered, **kwargs)

        self.assertEqual(left.value, right.value)
        self.assertEqual(len(left.value["rdates"]), 1)  # type: ignore[arg-type]
        self.assertEqual(left.value["segments"][0]["active_start"], "2026-08-01T08:00:00Z")  # type: ignore[index]
        self.assertEqual(left.value["rules"][1]["by_weekday"], ["MO", "FR"])  # type: ignore[index]

    def test_local_timezone_version_must_be_available(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "environment_failure:timezone_database_version"):
            normalize_initial_recurrence_set(
                {
                    "time_basis": "local_date",
                    "timezone": "America/Los_Angeles",
                    "timezone_database_version": "not-installed",
                    "rules": [
                        {
                            "frequency": "DAILY",
                            "seed": "2026-08-01",
                            "start_bound": "2026-08-01",
                            "end_condition": {"kind": "unbounded"},
                        }
                    ],
                },
                source_item_id="item",
                seed_anchor_id="anchor",
                seed_scheduled_fact="2026-08-01",
                created_item_version="1",
                source_item_version="1",
            )

    def test_local_timezone_name_must_be_available_at_authoring(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_request:timezone"):
            normalize_initial_recurrence_set(
                {
                    "time_basis": "local_date",
                    "timezone": "Not/A_Real_Zone",
                    "timezone_database_version": system_timezone_database_version(),
                    "rules": [
                        {
                            "frequency": "DAILY",
                            "seed": "2026-08-01",
                            "start_bound": "2026-08-01",
                            "end_condition": {"kind": "unbounded"},
                        }
                    ],
                },
                source_item_id="item",
                seed_anchor_id="anchor",
                seed_scheduled_fact="2026-08-01",
                created_item_version="1",
                source_item_version="1",
            )

    def test_segment_labels_are_discarded_and_children_resolve_to_sorted_segments(self) -> None:
        result = normalize_initial_recurrence_set(
            {
                "time_basis": "instant_utc",
                "segments": [
                    {"segment_label": "b", "active_start": "2027-01-01T08:00:00Z"},
                    {
                        "segment_label": "a",
                        "active_start": "2026-01-01T08:00:00Z",
                        "active_end": "2027-01-01T08:00:00Z",
                    },
                ],
                "rules": [
                    {
                        "segment_label": "b",
                        "frequency": "YEARLY",
                        "seed": "2027-01-01T08:00:00Z",
                        "start_bound": "2027-01-01T08:00:00Z",
                        "end_condition": {"kind": "unbounded"},
                    }
                ],
                "rdates": [{"segment_label": "a", "scheduled_fact": "2026-06-01T08:00:00Z"}],
            },
            source_item_id="item_segmented",
            seed_anchor_id="anchor_segmented",
            seed_scheduled_fact="2026-01-01T08:00:00Z",
            created_item_version="1",
            source_item_version="1",
        )
        self.assertNotIn("segment_label", str(result.normalized_hash_preimage))
        segments = result.value["segments"]
        rules = result.value["rules"]
        rdates = result.value["rdates"]
        self.assertEqual(rules[0]["segment_id"], segments[1]["segment_id"])  # type: ignore[index]
        self.assertEqual(rdates[0]["segment_id"], segments[0]["segment_id"])  # type: ignore[index]

    def test_overlapping_segments_fail_before_id_derivation(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "semantic_conflict"):
            normalize_initial_recurrence_set(
                {
                    "time_basis": "instant_utc",
                    "segments": [
                        {
                            "segment_label": "a",
                            "active_start": "2026-01-01T00:00:00Z",
                            "active_end": "2026-03-01T00:00:00Z",
                        },
                        {"segment_label": "b", "active_start": "2026-02-01T00:00:00Z"},
                    ],
                    "rules": [
                        {
                            "segment_label": "a",
                            "frequency": "DAILY",
                            "seed": "2026-01-01T00:00:00Z",
                            "start_bound": "2026-01-01T00:00:00Z",
                            "end_condition": {"kind": "unbounded"},
                        }
                    ],
                },
                source_item_id="item",
                seed_anchor_id="anchor",
                seed_scheduled_fact="2026-01-01T00:00:00Z",
                created_item_version="1",
                source_item_version="1",
            )


if __name__ == "__main__":
    unittest.main()
