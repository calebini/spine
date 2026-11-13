"""Exact pre-RF2-composition lifecycle envelopes and whole-ledger witnesses."""

from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core import recurrence_mutations
from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import audit_log_payload_hash, command_derived_id, hash_canonical_json
from spine.ledger.recurrence import load_current_recurrence_set
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_restoration as helpers

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf2_child_composition_witness.json"


def collect_lifecycle(observe=None):
    h = helpers.RecurringTaskRestorationTests()
    h.contracts = base.contracts()
    ids = itertools.count()
    with patch("spine.ledger.identity.secrets.token_hex", return_value="29" * 32), patch(
        "spine.ledger.items.new_id", side_effect=lambda prefix: prefix + "_rf2_" + str(next(ids)),
    ):
        h.setUp()
        try:
            evidence = {}

            def capture(name, result):
                h.assertTrue(result["ok"], result)
                if observe is not None:
                    observe(name, result, h.db)
                encoded = canonical_json_bytes(result)
                evidence[name] = {
                    "response_sha256": hashlib.sha256(encoded).hexdigest(), "response_bytes": len(encoded),
                    "ledger_sha256": hashlib.sha256(base.dump(h.db).encode()).hexdigest(),
                    "effect": result["effect"], "changed": result["changed"],
                }
                h.assertEqual(h.db.execute("PRAGMA foreign_key_check").fetchall(), [])
                h.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
                return result["result"]["rule"]

            initial, first = h.authored(archetype=True)
            rule = capture("create", initial)
            recurrence = load_current_recurrence_set(h.db, item_id=h.event["item_id"])
            h.source_change(overrides=[{
                "segment_id": recurrence["segments"][0]["segment_id"], "target_occurrence_key": first["occurrence_key"],
                "target_occurrence_selector": first["selector"], "status": "active",
                "expressed_scheduled_fact": "2026-08-08T20:00:00Z", "reason_code": "move",
            }])
            moved = h.reconcile(h.rule(rule["related_task_rule_id"]), "rf2-move")
            rule = capture("move", moved)
            selected = next(r for r in moved["result"]["results"] if r["assignment_id"] == first["assignment_id"])
            h.source_change(exdates=[h.excluded(selected)])
            rule = capture("cancel", h.reconcile(h.rule(rule["related_task_rule_id"]), "rf2-cancel"))
            h.source_change(exdates=[])
            restored = h.reconcile(h.rule(rule["related_task_rule_id"]), "rf2-restore")
            rule = capture("restore", restored)
            desired = h.request()["configuration"]
            desired["generation_horizon_seconds"] = "4838400"
            desired["task_template"]["item"]["title"] = "Collect Joe"
            desired["task_template"]["people"]["assignees"] = []
            updated = h.run_command("update", h.write("update", rule, configuration=desired, adoption_scope="upcoming_open"))
            h.assertTrue(updated["ok"], updated)
            rule = capture("adopt_clear", h.reconcile(updated["result"]["rule"], "rf2-adopt"))
            request = h.write("reconcile", rule, limits={}) | {"command_id": "rf2-noop"}
            capture("noop", h.run_command("reconcile", request))
            capture("replay", h.run_command("reconcile", request))
            return evidence
        finally:
            h.doCleanups()


class RecurringChildWitnessTests(unittest.TestCase):
    def test_complete_lifecycle_envelopes_and_sql_match_prechange_checkpoint(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source_commit"], "07fc937")
        normalize = recurrence_mutations._normalize_segments

        def historical_segments(rows, **kwargs):
            # Reproduce the immutable pre-correction producer, not a fallback
            # in the runtime. The old parent was retained on repeated copies.
            if not kwargs["explicit"]:
                rows = [{**row, "lineage_parent_segment_id": row.get("lineage_parent_segment_id") or row["segment_id"]}
                        for row in rows]
                kwargs["explicit"] = True
            return normalize(rows, **kwargs)

        with (patch.object(recurrence_mutations, "_normalize_segments", side_effect=historical_segments),
              patch("spine.services.mutation_propagation.invalidate_effects")):
            self.assertEqual(collect_lifecycle(), fixture["cases"])

    def test_pre_r3_producer_matches_only_the_explicit_parent_correction_amendment(self):
        fixture = json.loads(FIXTURE.read_text())
        amendment = json.loads(FIXTURE.with_name("r2_immediate_parent_witness_amendment.json").read_text())
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), amendment["baseline_sha256"])
        self.assertEqual(set(amendment["cases"]), {"cancel", "restore", "adopt_clear", "noop", "replay"})
        for name, case in amendment["cases"].items():
            for key in ("response_bytes", "changed", "effect"):
                self.assertEqual(case[key], fixture["cases"][name][key])
        with patch("spine.services.mutation_propagation.invalidate_effects"):
            self.assertEqual(collect_lifecycle(), fixture["cases"] | amendment["cases"])

    def test_r3_invalidation_changes_only_catalog_queue_and_bound_receipt_evidence(self):
        def without_catalog(value):
            if isinstance(value, dict):
                return {k: without_catalog(v) for k, v in value.items() if k != "catalog_generation"}
            if isinstance(value, list):
                return [without_catalog(v) for v in value]
            return value

        def capture(target):
            def observe(name, result, db):
                # R3 deliberately changes the catalog, derived queue and receipts
                # bound to exact expected facts. All ordinary/domain history stays.
                tables = {r[0]: [dict(v) for v in db.execute('SELECT * FROM ' + r[0])]
                          for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
                          if r[0] not in {"related_task_catalog_state", "related_task_dirty_rules"}}
                audit_hashes = {}
                for receipt in tables["command_receipts"]:
                    semantic = json.loads(receipt["semantic_facts_json"])
                    self.assertEqual(hash_canonical_json(semantic), receipt["semantic_facts_hash"])
                    if receipt["command"].startswith("schedule.related_task_rule."):
                        response = semantic["normalized_result"]
                        if response["changed"]:
                            identity = command_derived_id(prefix="audit", command=receipt["command"],
                                command_id=semantic["request"]["command_id"], row_role="audit", request_path="/audit")
                            audit_hashes[identity] = audit_log_payload_hash({
                                "command": receipt["command"], "request": semantic["request"], "result": response["result"]})
                    del receipt["semantic_facts_hash"]
                    for key in ("semantic_facts_json", "result_identity_facts_json"):
                        receipt[key] = without_catalog(json.loads(receipt[key]))
                for audit in tables["audit_log"]:
                    if audit["audit_id"] in audit_hashes:
                        self.assertEqual(audit["payload_hash"], audit_hashes[audit["audit_id"]])
                        del audit["payload_hash"]
                target[name] = (without_catalog(result), tables)
            return observe

        before, after = {}, {}
        with patch("spine.services.mutation_propagation.invalidate_effects"):
            collect_lifecycle(capture(before))
        # Freeze the initial R3 invalidation increment independently of the
        # subsequent coverage-only acknowledgement. The latter deliberately
        # replaces one queued no-op with a progress/audit-bearing applied page;
        # test_recurring_task_acknowledgement verifies its exact write boundary.
        with patch("spine.services.recurring_task_acknowledgement.acknowledge_page", return_value=False):
            collect_lifecycle(capture(after))
        self.assertEqual(before, after)
