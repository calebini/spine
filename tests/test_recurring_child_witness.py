"""Exact pre-RF2-composition lifecycle envelopes and whole-ledger witnesses."""

from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.canonical_json import canonical_json_bytes
from spine.ledger.recurrence import load_current_recurrence_set
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_restoration as helpers

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf2_child_composition_witness.json"


def collect_lifecycle():
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
        self.assertEqual(collect_lifecycle(), fixture["cases"])
