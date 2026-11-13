"""Real manual pages discharge only proven dirty coverage, never idle time."""

import copy
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import audit_log_payload_hash, command_derived_id, hash_canonical_json
from spine.ledger.recurring_task_invalidation import DirtyReason, mark
from spine.services.recurring_task_reconcile import Page, entry
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as helpers


class RecurringAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        helpers.RecurringTaskReconcileTests.setUpClass()
        self.h = helpers.RecurringTaskReconcileTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.db
        self.rule = self.h.created()["result"]["rule"]
        self.identity = self.rule["related_task_rule_id"]

    def dirty(self):
        value = self.db.execute("SELECT * FROM related_task_dirty_rules WHERE related_task_rule_id=?",
                                (self.identity,)).fetchone()
        return dict(value) if value else None

    def mark(self):
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.TARGET)

    def page(self, key, **limits):
        return self.h.reconcile(self.rule, key, **limits)

    def continuation(self, response, key):
        request = self.h.write("reconcile", response["result"]["rule"],
                               limits=response["result"]["selection"]["limits"], cursor=response["result"]["next_cursor"])
        request["command_id"] = key
        value = self.h.run_command("reconcile", request)
        self.assertTrue(value["ok"], value)
        return value

    def test_complete_retained_page_discharges_queue_once_and_idle_does_not_advance(self):
        self.page("generate")
        self.mark()
        before = self.db.execute("SELECT progress_version FROM related_task_rule_progress").fetchone()[0]
        result = self.page("acknowledge")
        self.assertTrue(result["changed"])
        self.assertEqual(result["effect"], "rule_page_applied")
        self.assertEqual({r["outcome"] for r in result["result"]["results"]}, {"retained"})
        self.assertIsNone(self.dirty())
        self.assertEqual(self.db.execute("SELECT progress_version FROM related_task_rule_progress").fetchone()[0], before + 1)
        progress = self.db.execute("SELECT * FROM related_task_rule_progress").fetchall()
        idle = self.page("idle")
        self.assertFalse(idle["changed"])
        self.assertEqual(self.db.execute("SELECT * FROM related_task_rule_progress").fetchall(), progress)
        # Explicit commands still have receipts. Compatible replay is write-free.
        request = self.h.write("reconcile", result["result"]["rule"], limits={}) | {"command_id": "idle"}
        before = base.dump(self.db)
        self.assertTrue(self.h.run_command("reconcile", request)["replayed"])
        self.assertEqual(base.dump(self.db), before)

    def test_acknowledgement_changes_only_queue_progress_root_and_exact_receipt_audit(self):
        self.page("generate")
        self.mark()
        permitted = {"related_task_dirty_rules", "related_task_catalog_state", "related_task_rules",
                     "related_task_rule_progress", "command_receipts", "audit_log", "temporal_binding_catalog_state"}

        def stable_rows():
            return {r[0]: [tuple(row) for row in self.db.execute("SELECT * FROM " + r[0]).fetchall()]
                    for r in self.db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
                    if r[0] not in permitted}

        before = stable_rows()
        binding_catalog = self.db.execute("SELECT binding_catalog_generation FROM temporal_binding_catalog_state").fetchone()[0]
        root = dict(self.db.execute("SELECT * FROM related_task_rules").fetchone())
        result = self.page("ack-evidence")
        for table, rows in stable_rows().items():
            self.assertEqual(rows, before[table], table)
        after = dict(self.db.execute("SELECT * FROM related_task_rules").fetchone())
        self.assertEqual(after, root | {"change_version": root["change_version"] + 1})
        receipt = self.db.execute("SELECT * FROM command_receipts WHERE command_id='ack-evidence'").fetchone()
        semantic = json.loads(receipt["semantic_facts_json"])
        self.assertEqual(receipt["semantic_facts_hash"], hash_canonical_json(semantic))
        self.assertEqual(semantic["normalized_result"]["result"], result["result"])
        audit_id = command_derived_id(prefix="audit", command=receipt["command"], command_id="ack-evidence",
                                     row_role="audit", request_path="/audit")
        audit = self.db.execute("SELECT * FROM audit_log WHERE audit_id=?", (audit_id,)).fetchone()
        self.assertEqual(audit["payload_hash"], audit_log_payload_hash({
            "command": receipt["command"], "request": semantic["request"], "result": result["result"]}))
        self.assertEqual(result["audit_ids"], [audit_id])
        # Retain the existing audit trigger's invalidation of binding read cursors.
        self.assertEqual(self.db.execute("SELECT binding_catalog_generation FROM temporal_binding_catalog_state").fetchone()[0],
                         binding_catalog + 1)

    def test_partial_assignment_pages_acknowledge_contiguous_prefix_then_clear(self):
        self.page("generate")
        self.mark()
        token = self.dirty()["dirty_generation"]
        first = self.page("ack-first", assignments="2")
        self.assertEqual(self.dirty()["assignment_after_seq"], 2)
        second = self.continuation(first, "ack-second")
        self.assertEqual((self.dirty()["assignment_after_seq"], self.dirty()["dirty_generation"]), (4, token))
        third = self.continuation(second, "ack-last")
        self.assertFalse(third["result"]["has_more"])
        self.assertIsNone(self.dirty())

    def test_blocked_assignment_prefix_cannot_be_cleared_by_later_cursor_page(self):
        first = self.page("generate")["result"]["results"][0]
        self.mark()
        original = Page.blocked
        from spine.services.recurring_task_reconcile import process_existing

        def block(page, assignment):
            if assignment["assignment_id"] == first["assignment_id"]:
                return original(page, first["selector"], assignment, "configuration_invalid")
            return process_existing(page, assignment)

        with patch("spine.services.recurring_task_reconcile.process_existing", side_effect=block):
            result = self.page("blocked-first", assignments="2")
            self.assertEqual(self.dirty()["assignment_after_seq"], 0)
            result = self.continuation(result, "blocked-second")
            self.continuation(result, "blocked-last")
        self.assertIsNotNone(self.dirty())
        self.assertEqual(self.dirty()["assignment_after_seq"], 0)
        self.page("resolved")
        self.assertIsNone(self.dirty())

    def test_unreserved_source_gap_before_cursor_cannot_be_cleared(self):
        self.mark()
        original = Page.create

        def blocked(page, occurrence, **kwargs):
            if occurrence["original_scheduled_fact"] == "2026-08-08T18:00:00Z":
                return entry(occurrence["target_occurrence_selector"], "decision_required", "source_continuity_unresolved")
            return original(page, occurrence, **kwargs)

        with patch.object(Page, "create", blocked):
            first = self.page("blocked-source", source_candidates="1")
            self.assertTrue(first["result"]["has_more"])
            for index in range(10):
                first = self.continuation(first, "source-next-" + str(index))
                if not first["result"]["has_more"]:
                    break
            else:
                self.fail("source pages did not terminate")
        self.assertIsNotNone(self.dirty())
        self.page("source-resolved")
        self.assertIsNone(self.dirty())

    def test_repair_keeps_its_own_invalidation_for_subsequent_proven_page(self):
        self.page("generate")
        self.h.source_change()
        old = self.dirty()["dirty_generation"]
        self.page("refresh")
        self.assertGreater(self.dirty()["dirty_generation"], old)
        self.page("confirm")
        self.assertIsNone(self.dirty())

    def test_preview_and_receipt_failure_roll_back_acknowledgement(self):
        self.page("generate")
        self.mark()
        request = self.h.write("reconcile", self.h.rule(self.identity), limits={})
        before = base.dump(self.db)
        preview = self.h.run_command("reconcile", request, context=replace(self.h.context, dry_run=True))
        self.assertTrue(preview["changed"], preview)
        self.assertEqual(base.dump(self.db), before)

        def fail(stage):
            if stage == "receipt":
                raise RuntimeError("after acknowledgement")

        with self.assertRaisesRegex(RuntimeError, "after acknowledgement"):
            self.h.run_command("reconcile", request, fault=fail)
        self.assertEqual(base.dump(self.db), before)

    def test_byte_trim_rolls_back_tentative_ack_and_advances_only_retained_units(self):
        self.page("generate")
        self.mark()
        request = self.h.write("reconcile", self.h.rule(self.identity), limits={})
        preview = self.h.run_command("reconcile", request, context=replace(self.h.context, dry_run=True))
        limit = len(canonical_json_bytes(preview)) * 3 // 4
        response = self.page("byte-ack", response_bytes=str(limit))
        self.assertTrue(response["result"]["has_more"])
        self.assertLessEqual(len(canonical_json_bytes(response)), limit)
        self.assertEqual(self.dirty()["assignment_after_seq"], int(response["result"]["selection"]["lane_end"]["assignment_after_seq"]))
        self.assertLess(self.dirty()["assignment_after_seq"], 6)
        for index in range(10):
            response = self.continuation(response, "byte-next-" + str(index))
            if not response["result"]["has_more"]:
                break
        else:
            self.fail("byte-limited pages did not terminate")
        self.assertIsNone(self.dirty())

    def test_new_source_write_invalidates_old_page_cursor_without_acknowledgement(self):
        self.page("generate")
        self.mark()
        first = self.page("first", assignments="2")
        self.h.source_change()
        request = self.h.write("reconcile", self.h.rule(self.identity),
            limits=first["result"]["selection"]["limits"], cursor=first["result"]["next_cursor"])
        request["command_id"] = "stale-continuation"
        before = base.dump(self.db)
        result = self.h.run_command("reconcile", request)
        self.assertEqual(result["error"]["code"], "stale_cursor")
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.dirty()["assignment_after_seq"], 0)

    def test_same_transaction_invalidation_and_generation_mismatch_leave_queue(self):
        self.page("generate")
        self.mark()
        from spine.services.recurring_task_acknowledgement import acknowledge_page

        old = copy.deepcopy(self.dirty())
        with self.db.atomic_command():
            mark(self.db, self.identity, DirtyReason.SOURCE)
            self.assertFalse(acknowledge_page(self.db, self.identity, old,
                original={"assignment_after_seq": "0"}, position={"assignment_after_seq": "0"},
                results=[], processed_assignments=0, existing_more=False, source_more=False, source_prefix_unproved=False))
        self.assertGreater(self.dirty()["dirty_generation"], old["dirty_generation"])
