import unittest
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.commands import core as command_core
from spine.ledger import connect, initialize_schema


class RecurrenceCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        handle(
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

    def tearDown(self) -> None:
        self.connection.close()

    def test_initial_recurrence_failure_rolls_back_item_anchor_and_aggregate(self) -> None:
        original = command_core.insert_initial_recurrence_set

        def fail_after_insert(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected recurrence persistence failure")

        receipt_count_before = self.connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
        with (
            patch("spine.commands.core.insert_initial_recurrence_set", side_effect=fail_after_insert),
            self.assertRaisesRegex(RuntimeError, "injected recurrence"),
        ):
            handle(
                "event.create",
                {
                    "command_id": "cmd-event-rollback",
                    "actor_subject_id": "owner",
                    "created_at_utc": "2026-08-07T17:01:00Z",
                    "title": "Must roll back",
                    "all_day": False,
                    "start_anchor": {
                        "anchor_kind": "instant_utc",
                        "utc_instant": "2026-08-08T18:00:00Z",
                        "recurrence_set": {
                            "time_basis": "instant_utc",
                            "rules": [
                                {
                                    "frequency": "DAILY",
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

        for table in (
            "coordination_items",
            "coordination_item_versions",
            "temporal_anchors",
            "recurrence_sets",
            "recurrence_revisions",
            "audit_log",
        ):
            with self.subTest(table=table):
                self.assertEqual(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0],
            receipt_count_before,
        )

    def test_add_remove_and_override_create_complete_successor_revisions(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-event",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:01:00Z",
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
        self.assertTrue(event["ok"], event)
        recurrence = self.connection.execute(
            "SELECT recurrence_set_id FROM recurrence_sets WHERE source_item_id = ?",
            (event["item_id"],),
        ).fetchone()
        revision = self.connection.execute(
            "SELECT recurrence_revision_id FROM recurrence_revisions WHERE recurrence_set_id = ?",
            (recurrence["recurrence_set_id"],),
        ).fetchone()
        added = handle(
            "recurrence.instance.add",
            {
                "command_id": "cmd-add",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "recurrence_set_id": recurrence["recurrence_set_id"],
                "recurrence_revision_id": revision["recurrence_revision_id"],
                "added_at_utc": "2026-08-07T17:02:00Z",
                "scheduled_fact": "2026-08-20T18:00:00Z",
                "reason_code": "extra_session",
            },
            self.context,
        )
        self.assertTrue(added["ok"], added)
        self.assertEqual(added["effect"], "instance_add_rdate_created")
        occurrences = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-21T00:00:00Z",
            },
            self.context,
        )
        self.assertEqual(len(occurrences["occurrences"]), 4)
        remove_key = occurrences["occurrences"][1]["occurrence_key"]
        removed = handle(
            "recurrence.instance.remove",
            {
                "command_id": "cmd-remove",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "recurrence_set_id": added["recurrence_set_id"],
                "recurrence_revision_id": added["recurrence_revision_id"],
                "removed_at_utc": "2026-08-07T17:03:00Z",
                "target_occurrence_key": remove_key,
                "reason_code": "skip_one",
            },
            self.context,
        )
        self.assertTrue(removed["ok"], removed)
        after_remove = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-21T00:00:00Z",
            },
            self.context,
        )
        self.assertNotIn(remove_key, [value["occurrence_key"] for value in after_remove["occurrences"]])
        override_key = after_remove["occurrences"][1]["occurrence_key"]
        overridden = handle(
            "recurrence.instance.override",
            {
                "command_id": "cmd-override",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "3",
                "recurrence_set_id": removed["recurrence_set_id"],
                "recurrence_revision_id": removed["recurrence_revision_id"],
                "overridden_at_utc": "2026-08-07T17:04:00Z",
                "target_occurrence_key": override_key,
                "expressed_scheduled_fact": "2026-08-15T20:00:00Z",
                "common_detail_patch": {"title": "Late sync"},
                "reason_code": "move_once",
            },
            self.context,
        )
        self.assertTrue(overridden["ok"], overridden)
        self.assertEqual(overridden["effect"], "instance_override_created")
        final = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_basis": "expressed_time",
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-21T00:00:00Z",
            },
            self.context,
        )
        moved = next(value for value in final["occurrences"] if value["occurrence_key"] == override_key)
        self.assertEqual(moved["expressed_scheduled_fact"], "2026-08-15T20:00:00Z")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM recurrence_revisions").fetchone()[0],
            4,
        )

    def test_event_reschedule_can_attach_recurrence_once_and_then_defers_to_series_commands(self) -> None:
        event = handle(
            "event.create",
            {
                "command_id": "cmd-event-before-recurrence",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:01:00Z",
                "title": "Planning block",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": "2026-08-08T18:00:00Z",
                },
            },
            self.context,
        )
        attached = handle(
            "event.reschedule",
            {
                "command_id": "cmd-attach-recurrence",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "rescheduled_at_utc": "2026-08-07T17:02:00Z",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": "2026-08-08T18:00:00Z",
                    "recurrence_set": {
                        "time_basis": "instant_utc",
                        "rules": [
                            {
                                "frequency": "WEEKLY",
                                "seed": "2026-08-08T18:00:00Z",
                                "start_bound": "2026-08-08T18:00:00Z",
                                "end_condition": {"kind": "count", "count": "4"},
                            }
                        ],
                    },
                },
            },
            self.context,
        )

        self.assertTrue(attached["ok"], attached)
        self.assertTrue(attached["rescheduled"])
        recurrence = self.connection.execute(
            "SELECT * FROM recurrence_sets WHERE source_item_id = ?",
            (event["item_id"],),
        ).fetchone()
        revision = self.connection.execute(
            "SELECT * FROM recurrence_revisions WHERE recurrence_set_id = ?",
            (recurrence["recurrence_set_id"],),
        ).fetchone()
        self.assertEqual(recurrence["created_item_version"], 2)
        self.assertEqual(revision["source_item_version"], 2)
        anchor_count = self.connection.execute("SELECT COUNT(*) FROM temporal_anchors").fetchone()[0]

        rejected = handle(
            "event.reschedule",
            {
                "command_id": "cmd-reschedule-recurring-event",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "rescheduled_at_utc": "2026-08-07T17:03:00Z",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": "2026-08-09T18:00:00Z",
                },
            },
            self.context,
        )
        self.assertEqual(rejected["error"]["code"], "semantic_conflict")
        self.assertEqual(rejected["error"]["field"], "start_anchor")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM temporal_anchors").fetchone()[0],
            anchor_count,
        )

    def test_series_edit_whole_replaces_collections_and_records_lineage(self) -> None:
        event, recurrence, revision = self._create_daily_event("whole", count="5")
        segment_id = self.connection.execute(
            "SELECT segment_id FROM recurrence_segments WHERE recurrence_revision_id = ? AND status = 'active'",
            (revision,),
        ).fetchone()["segment_id"]
        edited = handle(
            "recurrence.series.edit",
            {
                "command_id": "cmd-whole-edit",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "recurrence_set_id": recurrence,
                "recurrence_revision_id": revision,
                "edited_at_utc": "2026-08-07T18:00:00Z",
                "edit_scope": "whole_series",
                "recurrence_patch": {
                    "rules": [
                        {
                            "segment_id": segment_id,
                            "frequency": "DAILY",
                            "interval": "2",
                            "seed": "2026-08-08T18:00:00Z",
                            "start_bound": "2026-08-08T18:00:00Z",
                            "end_condition": {"kind": "count", "count": "3"},
                        }
                    ],
                    "rdates": [],
                    "exdates": [],
                    "overrides": [],
                },
            },
            self.context,
        )
        self.assertTrue(edited["ok"], edited)
        self.assertEqual(edited["effect"], "series_edit_whole_applied")
        self.assertTrue(edited["lineage_ids"])
        expanded = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-15T00:00:00Z",
            },
            self.context,
        )
        self.assertEqual(
            [value["original_scheduled_fact"] for value in expanded["occurrences"]],
            ["2026-08-08T18:00:00Z", "2026-08-10T18:00:00Z", "2026-08-12T18:00:00Z"],
        )

    def test_series_edit_this_and_following_splits_and_preserves_count_total(self) -> None:
        event, recurrence, revision = self._create_daily_event("following", count="6")
        before = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-20T00:00:00Z",
            },
            self.context,
        )
        split_key = before["occurrences"][2]["occurrence_key"]
        edited = handle(
            "recurrence.series.edit",
            {
                "command_id": "cmd-following-edit",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "recurrence_set_id": recurrence,
                "recurrence_revision_id": revision,
                "edited_at_utc": "2026-08-07T18:01:00Z",
                "edit_scope": "this_and_following",
                "target_occurrence_key": split_key,
                "recurrence_patch": {
                    "rules": [
                        {
                            "frequency": "DAILY",
                            "interval": "2",
                            "seed": "2026-08-10T18:00:00Z",
                            "start_bound": "2026-08-10T18:00:00Z",
                            "end_condition": {"kind": "count", "count": "3"},
                        }
                    ]
                },
            },
            self.context,
        )
        self.assertTrue(edited["ok"], edited)
        self.assertEqual(edited["effect"], "series_edit_following_applied")
        self.assertEqual(edited["split_scheduled_fact"], "2026-08-10T18:00:00Z")
        active_segments = self.connection.execute(
            "SELECT COUNT(*) FROM recurrence_segments WHERE recurrence_revision_id = ? AND status = 'active'",
            (edited["recurrence_revision_id"],),
        ).fetchone()[0]
        self.assertEqual(active_segments, 2)
        expanded = handle(
            "item.occurrences",
            {
                "item_id": event["item_id"],
                "range_start": "2026-08-08T00:00:00Z",
                "range_end": "2026-08-20T00:00:00Z",
            },
            self.context,
        )
        self.assertEqual(
            [value["original_scheduled_fact"] for value in expanded["occurrences"]],
            [
                "2026-08-08T18:00:00Z",
                "2026-08-09T18:00:00Z",
                "2026-08-10T18:00:00Z",
                "2026-08-12T18:00:00Z",
                "2026-08-14T18:00:00Z",
            ],
        )

    def _create_daily_event(self, suffix: str, *, count: str):
        event = handle(
            "event.create",
            {
                "command_id": f"cmd-event-{suffix}",
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:01:00Z",
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
                                "seed": "2026-08-08T18:00:00Z",
                                "start_bound": "2026-08-08T18:00:00Z",
                                "end_condition": {"kind": "count", "count": count},
                            }
                        ],
                    },
                },
            },
            self.context,
        )
        row = self.connection.execute(
            """
            SELECT rs.recurrence_set_id, rr.recurrence_revision_id
            FROM recurrence_sets AS rs
            JOIN recurrence_revisions AS rr ON rr.recurrence_set_id = rs.recurrence_set_id
            WHERE rs.source_item_id = ?
            """,
            (event["item_id"],),
        ).fetchone()
        return event, row["recurrence_set_id"], row["recurrence_revision_id"]


if __name__ == "__main__":
    unittest.main()
