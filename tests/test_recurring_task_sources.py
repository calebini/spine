"""Authentic source producer, membership and stored-lineage tests for R1."""

import copy
import unittest

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.recurrence_mutations import build_successor_recurrence_revision, derive_recurrence_lineage
from spine.core.recurrence_set import generated_id
from spine.ledger.recurrence import insert_initial_recurrence_set, insert_recurrence_lineage, load_current_recurrence_set
from spine.ledger.recurring_task_migration import install_candidate
from spine.ledger.recurring_task_sources import ProofBudget, candidate, continuity, require_candidate, verify_proof
from tests import test_recurrence_commands as recurrence_tests


class RecurringTaskSourceTests(unittest.TestCase):
    def setUp(self):
        self.helper = recurrence_tests.RecurrenceCommandTests()
        self.helper.setUp()
        self.addCleanup(self.helper.tearDown)
        self.db = self.helper.connection
        self.context = self.helper.context

    def event(self, frequency="DAILY", *, seed="2026-08-08T18:00:00Z", count="6", rdates=None, rules=None):
        rule = {"frequency": frequency, "seed": seed, "start_bound": seed, "end_condition": {"kind": "count", "count": count}}
        response = handle(
            "event.create",
            {
                "command_id": "r1-" + frequency + seed,
                "actor_subject_id": "owner",
                "created_at_utc": "2026-08-07T17:01:00Z",
                "title": "Source",
                "all_day": False,
                "start_anchor": {
                    "anchor_kind": "instant_utc",
                    "utc_instant": seed,
                    "recurrence_set": {"time_basis": "instant_utc", "rules": rules or [rule], "rdates": rdates or []},
                },
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)
        current = load_current_recurrence_set(self.db, item_id=response["item_id"])
        return response, current

    def successor(self, event, current, *, count_split=False, changed_seed=False, missing_copy=False, rdates=None):
        # Existing version producer, then the actual recurrence normalizer and
        # insertion helpers. These are newly authored synthetic facts, not edits
        # to already stored source history.
        updated = handle(
            "event.update",
            {
                "command_id": "r1-next-version",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "updated_at_utc": "2026-08-07T18:00:00Z",
                "patch": {"title": "Source updated"},
            },
            self.context,
        )
        self.assertTrue(updated["ok"], updated)
        segments = [
            {**s, "source_revision_id": current["recurrence_revision_id"], "lineage_parent_segment_id": s["segment_id"]}
            for s in current["segments"]
        ]
        rules = copy.deepcopy(current["rules"])
        if count_split:
            segments[0]["active_start"] = "2026-08-10T18:00:00Z"
            rules[0]["start_bound"] = "2026-08-10T18:00:00Z"
            rules[0]["end_condition"] = {"kind": "count", "count": "4"}
        if changed_seed:
            rules[0]["seed"] = "2026-08-09T18:00:00Z"
            rules[0]["start_bound"] = rules[0]["seed"]
        successor = build_successor_recurrence_revision(
            current, source_item_version="2", command_id="r1-successor", segments=segments, rules=rules, rdates=rdates
        )
        lines = derive_recurrence_lineage(current, successor.value, command_id="r1-successor", effect="series_edit_following_applied")
        if count_split:
            # The accepted COUNT split has changed bounds/count, so the generic
            # exact-byte matcher cannot produce its copy fact. Author a real
            # registered copy row; R1 independently checks the arithmetic/seed.
            line = next(v for v in lines if v["lineage_role"] == "rule_revision")
            fields = {k: v for k, v in line.items() if k not in {"lineage_id", "payload_hash"}}
            fields.update(effect="copied", prior_child_id=current["rules"][0]["rule_id"])
            line.update(
                fields,
                lineage_id=generated_id("recurrence_lineage", "spine.recurrence-lineage-id.v1", fields)[0],
                payload_hash=hash_canonical_json({**fields, "command_effect": "series_edit_following_applied"}),
            )
        if missing_copy:
            lines = [line for line in lines if line["lineage_role"] != "rule_revision"]
        with self.db.atomic_command(write=True):
            insert_initial_recurrence_set(self.db, normalized=successor, command_id="r1-successor", created_at_utc="2026-08-07T18:00:00Z")
            insert_recurrence_lineage(self.db, lineage=lines)
        return successor.value, lines

    def hop(self, before, after, lines):
        return {
            "prior_revision_id": before["header"]["recurrence_revision_id"],
            "new_revision_id": after["header"]["recurrence_revision_id"],
            "prior_selector": before["selector"],
            "selector": after["selector"],
            "lineage_ids": sorted(v["lineage_id"] for v in lines),
        }

    def test_selector_local_membership_all_frequencies_and_old_seed_without_history_walk(self):
        facts = {
            "DAILY": "2026-08-10T18:00:00Z",
            "WEEKLY": "2026-08-15T18:00:00Z",
            "MONTHLY": "2026-09-08T18:00:00Z",
            "YEARLY": "2027-08-08T18:00:00Z",
        }
        for frequency, fact in facts.items():
            with self.subTest(frequency=frequency):
                _, current = self.event(frequency)
                with self.db.atomic_command(write=False):
                    self.assertIsNotNone(candidate(self.db, current["recurrence_revision_id"], fact, ProofBudget()))
                    self.assertIsNone(candidate(self.db, current["recurrence_revision_id"], "2026-08-09T17:00:00Z", ProofBudget()))
        _, current = self.event(seed="1900-01-01T18:00:00Z", count="100000")
        queries = []
        self.db.set_trace_callback(queries.append)
        with self.db.atomic_command(write=False):
            result = candidate(self.db, current["recurrence_revision_id"], "2026-08-08T18:00:00Z", ProofBudget(steps=40))
        self.db.set_trace_callback(None)
        self.assertIsNotNone(result)
        self.assertLess(len(queries), 12)
        self.assertFalse(any("OFFSET" in q or "occurrence_provenance" in q for q in queries))

    def test_union_requires_every_contributor_and_duplicate_dates_collapse(self):
        _, current = self.event(rdates=[{"scheduled_fact": "2026-08-08T18:00:00Z"}, {"scheduled_fact": "2026-08-08T18:00:00Z"}])
        with self.db.atomic_command(write=False):
            result = candidate(self.db, current["recurrence_revision_id"], "2026-08-08T18:00:00Z", ProofBudget())
            self.assertEqual(result["selector"]["origin_kind"], "union")
            self.assertEqual(len(result["rdates"]), 1)
            incomplete = copy.deepcopy(result["selector"])
            incomplete["source_rdate_selectors"] = []
            with self.assertRaisesRegex(SpineValidationError, "complete current candidate"):
                require_candidate(self.db, current["recurrence_revision_id"], incomplete, ProofBudget())

    def test_move_and_exclusion_preserve_original_source_membership(self):
        event, current = self.event()
        fact = "2026-08-08T18:00:00Z"
        with self.db.atomic_command(write=False):
            original = candidate(self.db, current["recurrence_revision_id"], fact, ProofBudget())
        moved = handle(
            "recurrence.instance.override",
            {
                "command_id": "r1-move-one",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "recurrence_set_id": current["recurrence_set_id"],
                "recurrence_revision_id": current["recurrence_revision_id"],
                "overridden_at_utc": "2026-08-07T18:00:00Z",
                "target_occurrence_key": original["occurrence_key"],
                "expressed_scheduled_fact": "2026-08-08T20:00:00Z",
                "reason_code": "move_once",
            },
            self.context,
        )
        self.assertTrue(moved["ok"], moved)
        with self.db.atomic_command(write=False):
            after = candidate(self.db, moved["recurrence_revision_id"], fact, ProofBudget())
            self.assertEqual(after["selector"], original["selector"])
            self.assertIsNone(candidate(self.db, moved["recurrence_revision_id"], "2026-08-08T20:00:00Z", ProofBudget()))
        removed = handle(
            "recurrence.instance.remove",
            {
                "command_id": "r1-exclude-one",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "recurrence_set_id": current["recurrence_set_id"],
                "recurrence_revision_id": moved["recurrence_revision_id"],
                "removed_at_utc": "2026-08-07T18:01:00Z",
                "target_occurrence_key": original["occurrence_key"],
                "reason_code": "no_class",
            },
            self.context,
        )
        self.assertTrue(removed["ok"], removed)
        with self.db.atomic_command(write=False):
            after = candidate(self.db, removed["recurrence_revision_id"], fact, ProofBudget())
            self.assertEqual(after["selector"], original["selector"])
        expanded = handle(
            "item.occurrences",
            {"item_id": event["item_id"], "range_start": "2026-08-08T00:00:00Z", "range_end": "2026-08-09T00:00:00Z"},
            self.context,
        )
        self.assertTrue(expanded["ok"], expanded)
        self.assertEqual(expanded["occurrences"], [])

    def test_correct_copy_and_count_split_use_stored_children_and_lineage(self):
        self.check_copy(split=True)

    def test_unchanged_stream_copy_uses_stored_children_and_lineage(self):
        self.check_copy(split=False)

    def check_copy(self, *, split):
        event, current = self.event()
        successor, lines = self.successor(event, current, count_split=split)
        with self.db.atomic_command(write=False):
            before = candidate(self.db, current["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            after = candidate(self.db, successor["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            resolved = continuity(
                self.db, current["recurrence_revision_id"], before["selector"], [self.hop(before, after, lines)], ProofBudget()
            )
            self.assertEqual(resolved["selector"], after["selector"])
            self.assertEqual(resolved["rules"][0][1]["seed"], "2026-08-08T18:00:00Z")
            if split:
                self.assertIsNone(candidate(self.db, successor["recurrence_revision_id"], "2026-08-14T18:00:00Z", ProofBudget()))

    def test_missing_lineage_and_budget_exhaustion_fail_closed(self):
        event, current = self.event()
        successor, lines = self.successor(event, current, missing_copy=True)
        with self.db.atomic_command(write=False):
            before = candidate(self.db, current["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            after = candidate(self.db, successor["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            with self.assertRaisesRegex(SpineValidationError, "unproved union contributor"):
                continuity(self.db, current["recurrence_revision_id"], before["selector"], [self.hop(before, after, lines)], ProofBudget())
            with self.assertRaisesRegex(SpineValidationError, "exhausted"):
                continuity(
                    self.db, current["recurrence_revision_id"], before["selector"], [self.hop(before, after, lines)], ProofBudget(hops=0)
                )

    def test_equal_ordinal_or_shifted_original_fact_is_not_continuity(self):
        event, current = self.event()
        successor, lines = self.successor(event, current, changed_seed=True)
        with self.db.atomic_command(write=False):
            before = candidate(self.db, current["recurrence_revision_id"], "2026-08-08T18:00:00Z", ProofBudget())
            after = candidate(self.db, successor["recurrence_revision_id"], "2026-08-09T18:00:00Z", ProofBudget())
            with self.assertRaisesRegex(SpineValidationError, "per-occurrence retarget"):
                continuity(self.db, current["recurrence_revision_id"], before["selector"], [self.hop(before, after, lines)], ProofBudget())

    def test_current_public_add_producer_preserves_initial_ancestry_so_cannot_certify_copy(self):
        event, current = self.event()
        added = handle(
            "recurrence.instance.add",
            {
                "command_id": "r1-public-add",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "1",
                "recurrence_set_id": current["recurrence_set_id"],
                "recurrence_revision_id": current["recurrence_revision_id"],
                "added_at_utc": "2026-08-07T18:00:00Z",
                "scheduled_fact": "2026-08-20T18:00:00Z",
                "reason_code": "extra",
            },
            self.context,
        )
        self.assertTrue(added["ok"], added)
        with self.db.atomic_command(write=False):
            before = candidate(self.db, current["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            after = candidate(self.db, added["recurrence_revision_id"], "2026-08-11T18:00:00Z", ProofBudget())
            lines = [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM recurrence_lineage WHERE new_recurrence_revision_id=?", (added["recurrence_revision_id"],)
                )
            ]
            self.assertEqual(after["segment"]["source_revision_id"], "initial")
            with self.assertRaisesRegex(SpineValidationError, "incorrect ancestry"):
                continuity(self.db, current["recurrence_revision_id"], before["selector"], [self.hop(before, after, lines)], ProofBudget())

    def test_new_rdate_requires_novelty_actual_add_lineage_and_bounded_unchanged_history(self):
        event, initial = self.event()
        added_dates = [
            {"scheduled_fact": fact, "segment_id": initial["segments"][0]["segment_id"], "status": "active"}
            for fact in ["2026-08-08T18:00:00Z", "2026-08-20T18:00:00Z"]
        ]
        successor, lines = self.successor(event, initial, rdates=added_dates)
        install_candidate(self.db, disposable_test_ledger=True)
        root = {
            "source_item_id": event["item_id"],
            "recurrence_set_id": initial["recurrence_set_id"],
            "related_task_rule_id": "not-yet-inserted-test-root",
            "enrolled_recurrence_revision_id": initial["recurrence_revision_id"],
        }
        with self.db.atomic_command(write=False):
            result = candidate(self.db, successor["recurrence_revision_id"], "2026-08-20T18:00:00Z", ProofBudget())
            payload = {
                "source_item_id": event["item_id"],
                "source_item_version": "2",
                "recurrence_set_id": initial["recurrence_set_id"],
                "recurrence_revision_id": successor["recurrence_revision_id"],
                "normalized_recurrence_set_hash": successor["normalized_recurrence_set_hash"],
                "selector": result["selector"],
                "occurrence_key": result["occurrence_key"],
                "rdate_id": result["rdates"][0][0]["rdate_id"],
                "prior_recurrence_revision_id": initial["recurrence_revision_id"],
                "lineage_ids": sorted(line["lineage_id"] for line in lines),
            }
            before = self.db.total_changes
            verify_proof(self.db, root, "new_rdate", payload, ProofBudget())
            self.assertEqual(self.db.total_changes, before)
            with self.assertRaisesRegex(SpineValidationError, "exhausted"):
                verify_proof(self.db, root, "new_rdate", payload, ProofBudget(hops=0))
            alias = candidate(self.db, successor["recurrence_revision_id"], "2026-08-08T18:00:00Z", ProofBudget())
            bad = {
                **payload,
                "selector": alias["selector"],
                "occurrence_key": alias["occurrence_key"],
                "rdate_id": alias["rdates"][0][0]["rdate_id"],
            }
            with self.assertRaisesRegex(SpineValidationError, "aliases an included old slot"):
                verify_proof(self.db, root, "new_rdate", bad, ProofBudget())


if __name__ == "__main__":
    unittest.main()
