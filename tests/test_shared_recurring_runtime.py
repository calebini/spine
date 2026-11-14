"""RF1 runtime/catalog extraction preserves bytes, history and caller ownership."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from spine.commands import receipts as receipt_commands
from spine.commands import recurring_task_runtime as admission
from spine.commands import recurring_tasks as commands
from spine.core import recurring_task_runtime as runtime
from spine.core.errors import SpineValidationError
from spine.ledger import receipts
from spine.ledger import recurring_task_catalog as catalog
from tests import test_recurring_task_commands as helpers

ROOT = Path(__file__).resolve().parents[1]


class SharedRecurringRuntimeTests(unittest.TestCase):
    def test_extracted_and_preexisting_admission_bodies_match_captured_baseline(self):
        witness = json.loads((ROOT / "tests/fixtures/internal_operations/rf1_runtime_catalog_witness.json").read_text())
        amendment = json.loads((ROOT / "tests/fixtures/internal_operations/r2_admission_read_body_amendment.json").read_text())
        self.assertEqual(amendment["baseline_fixture"], "tests/fixtures/internal_operations/rf1_runtime_catalog_witness.json")
        self.assertEqual(hashlib.sha256((ROOT / amendment["baseline_fixture"]).read_bytes()).hexdigest(),
                         amendment["baseline_fixture_sha256"])
        self.assertEqual(amendment["baseline_variant"], "bodies")
        replacements = {(entry["path"], entry["name"]): entry for entry in amendment["replacements"]}
        self.assertEqual(len(amendment["replacements"]), 2)
        self.assertEqual(set(replacements), {
            ("src/spine/commands/recurring_task_runtime.py", "RecurringTaskContracts"),
            ("src/spine/core/recurring_task_runtime.py", "verify_cursor"),
        })
        amended = [replacements.get((entry["path"], entry["name"]), entry) for entry in witness["bodies"]]
        calendar = json.loads((ROOT / "tests/fixtures/internal_operations/r2_calendar_lead_body_amendment.json").read_text())
        self.assertEqual(calendar["prior_amendment"], "tests/fixtures/internal_operations/r2_admission_read_body_amendment.json")
        self.assertEqual(hashlib.sha256((ROOT / calendar["prior_amendment"]).read_bytes()).hexdigest(),
                         calendar["prior_amendment_sha256"])
        calendar_replacements = {(entry["path"], entry["name"]): entry for entry in calendar["replacements"]}
        self.assertEqual(len(calendar["replacements"]), 2)
        self.assertEqual(set(calendar_replacements), {("src/spine/commands/recurring_tasks.py", name) for name in ("create", "update")})
        calendar_amended = [calendar_replacements.get((entry["path"], entry["name"]), entry) for entry in amended]
        r3 = json.loads((ROOT / "tests/fixtures/internal_operations/r3_catalog_body_amendment.json").read_text())
        self.assertEqual(r3["prior_amendment"], "tests/fixtures/internal_operations/r2_calendar_lead_body_amendment.json")
        self.assertEqual(hashlib.sha256((ROOT / r3["prior_amendment"]).read_bytes()).hexdigest(), r3["prior_amendment_sha256"])
        self.assertEqual(len(r3["replacements"]), 1)
        r3_replacements = {(entry["path"], entry["name"]): entry for entry in r3["replacements"]}
        self.assertEqual(set(r3_replacements), {("src/spine/ledger/recurring_task_catalog.py", "advance_catalog")})
        r3_amended = [r3_replacements.get((entry["path"], entry["name"]), entry) for entry in calendar_amended]
        queue = json.loads((ROOT / "tests/fixtures/internal_operations/r3_rule_queue_body_amendment.json").read_text())
        self.assertEqual(queue["prior_amendment"], "tests/fixtures/internal_operations/r3_catalog_body_amendment.json")
        self.assertEqual(hashlib.sha256((ROOT / queue["prior_amendment"]).read_bytes()).hexdigest(), queue["prior_amendment_sha256"])
        writers = {(e["path"], e["name"]): e for e in queue["replacements"]}
        self.assertEqual(len(queue["replacements"]), 3)
        self.assertEqual(set(writers), {("src/spine/commands/recurring_tasks.py", name) for name in ("create", "update", "retire")})
        queued = [writers.get((e["path"], e["name"]), e) for e in r3_amended]
        fence = json.loads((ROOT / "tests/fixtures/internal_operations/r3_automatic_dispatch_body_amendment.json").read_text())
        self.assertEqual(fence["prior_amendment"], "tests/fixtures/internal_operations/r3_rule_queue_body_amendment.json")
        self.assertEqual(hashlib.sha256((ROOT / fence["prior_amendment"]).read_bytes()).hexdigest(), fence["prior_amendment_sha256"])
        adapter = fence["replacement"]
        self.assertEqual((adapter["path"], adapter["name"]), ("src/spine/commands/recurring_tasks.py", "execute"))
        fenced = [adapter if (e["path"], e["name"]) == (adapter["path"], adapter["name"]) else e for e in queued]
        durability = json.loads((ROOT / "tests/fixtures/internal_operations/r3_worker_durability_body_amendment.json").read_text())
        self.assertEqual(durability["prior_amendment"], "tests/fixtures/internal_operations/r3_automatic_dispatch_body_amendment.json")
        prior_digest = hashlib.sha256((ROOT / durability["prior_amendment"]).read_bytes()).hexdigest()
        self.assertEqual(prior_digest, durability["prior_amendment_sha256"])
        worker = durability["replacement"]
        self.assertEqual((worker["path"], worker["name"]), (adapter["path"], adapter["name"]))
        guarded = [worker if e == adapter else e for e in fenced]
        # Accept one complete captured state, never a per-function mix. Retain
        # both original RF1 baselines and narrowly record the two functional R2
        # corrections authorized after RF2 and the one R3 catalog-coalescing
        # change; all other body hashes stay frozen.
        mismatches = []
        for variant in (witness["bodies"], witness["committed_bodies"], amended, calendar_amended, r3_amended, queued, fenced, guarded):
            failures = []
            for entry in variant:
                nodes = ast.parse((ROOT / entry["path"]).read_text()).body
                node = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == entry["name"]), None)
                if node is not None and node.name == "execute":
                    # RF1's only approved adapter-body change: inject the required
                    # byte-sizing capability. Keep the original body hashes intact.
                    calls = [
                        n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "reconcile"
                    ]
                    self.assertEqual(len(calls), 1)
                    sizing = [k for k in calls[0].keywords if k.arg == "response_size"]
                    self.assertEqual(len(sizing), 1)
                    self.assertEqual(ast.unparse(sizing[0].value), "response_sizer(command, value, now, dry_run=context.dry_run)")
                    calls[0].keywords.remove(sizing[0])
                body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False) if node else "missing"
                if hashlib.sha256(body.encode()).hexdigest() != entry["body_sha256"]:
                    failures.append((entry["path"], entry["name"]))
            if not failures:
                return
            mismatches.append(failures)
        self.fail(f"No complete captured baseline or authorized R2/R3 amendment matches: {mismatches}")

    def test_command_aliases_share_the_lower_implementation(self):
        for name in ("fail", "instant", "wire", "cursor_config", "sign_cursor", "verify_cursor", "cursor_payload"):
            self.assertIs(getattr(admission, name), getattr(runtime, name))
        for name in (
            "catalog",
            "advance_catalog",
            "lookup",
            "source_snapshot",
            "intent_view",
            "pending_adoption",
            "stored_projection",
            "rule_view",
        ):
            self.assertIs(getattr(commands, name), getattr(catalog, name))
        for name in ("get_command_receipt", "receipt_from_row"):
            self.assertIs(getattr(receipt_commands, name), getattr(receipts, name))

    def test_lower_owners_import_without_command_or_service_loading(self):
        program = (
            "import sys; from spine.core import recurring_task_runtime; "
            "from spine.ledger import receipts, recurring_task_catalog; "
            "assert not any(m.startswith(('spine.commands', 'spine.services')) for m in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cursor_bytes_and_failure_precedence_remain_exact(self):
        contracts = helpers.contracts()
        vectors = json.loads((ROOT / "tests/fixtures/recurring_related_tasks/cursors.json").read_text())["vectors"]
        for vector in vectors:
            payload = vector["payload"]
            config = helpers.FacetCursorConfig(bytes.fromhex(vector["key_hex"]), payload["query"]["ledger_instance_id"], payload["key_id"])
            arguments = (payload["query"], vector["purpose"], payload["issued_at_utc"], payload["catalog_generation"], contracts)
            with self.subTest(purpose=vector["purpose"]):
                self.assertEqual(runtime.sign_cursor(config, payload, contracts), vector["wire"])
                self.assertEqual(runtime.verify_cursor(config, vector["wire"], *arguments), payload)
                for bad in (
                    None,
                    replace(config, secret=b"short"),
                    replace(config, ledger_id="other"),
                ):
                    with self.assertRaises(SpineValidationError) as caught:
                        runtime.verify_cursor(bad, "invalid", *arguments)
                    self.assertEqual(caught.exception.code, "environment_failure:cursor_configuration")
                for token in ("invalid", vector["wire"] + "=", "!" + vector["wire"]):
                    with self.assertRaises(SpineValidationError) as caught:
                        runtime.verify_cursor(config, token, *arguments)
                    self.assertEqual(
                        (caught.exception.code, caught.exception.message), ("invalid_request:cursor", "invalid recurring-task cursor")
                    )
                with self.assertRaises(SpineValidationError) as caught:
                    runtime.verify_cursor(
                        config, vector["wire"], arguments[0], arguments[1], payload["expires_at_utc"], arguments[3], contracts
                    )
                self.assertEqual(caught.exception.code, "stale_cursor:cursor")
                with self.assertRaises(SpineValidationError) as caught:
                    runtime.verify_cursor(config, vector["wire"], arguments[0], arguments[1], arguments[2], "changed", contracts)
                self.assertEqual(caught.exception.code, "stale_cursor:cursor")
        self.assertEqual(runtime.wire(runtime.instant("2026-11-11T12:00:00+02:00")), "2026-11-11T10:00:00Z")
        with self.assertRaises(SpineValidationError) as caught:
            runtime.wire(datetime(2026, 11, 11))
        self.assertEqual(caught.exception.code, "environment_failure:clock")

    def test_catalog_and_historical_receipts_stay_read_only_and_rollback_owned(self):
        h = helpers.RecurringTaskCommandTests()
        h.contracts = helpers.contracts()
        h.setUp()
        self.addCleanup(h.doCleanups)
        created = h.created()
        rule = created["result"]["rule"]
        before = helpers.dump(h.db)
        changes = h.db.total_changes
        receipt = receipts.get_command_receipt(h.db, h.request()["command_id"])
        self.assertEqual(receipt["result_identity_facts"], created)
        self.assertIsNone(receipts.get_command_receipt(h.db, "absent"))
        self.assertEqual(
            catalog.rule_view(h.db, catalog.lookup(h.db, "related_task_rules", rule["related_task_rule_id"], "related_task_rule_id")), rule
        )
        self.assertEqual(h.db.total_changes, changes)
        with self.assertRaisesRegex(RuntimeError, "outer failure"), h.db.atomic_command(write=True):
            generation = int(catalog.catalog(h.db))
            catalog.advance_catalog(h.db)
            self.assertEqual(catalog.catalog(h.db), str(generation + 1))
            self.assertEqual(receipts.get_command_receipt(h.db, h.request()["command_id"]), receipt)
            raise RuntimeError("outer failure")
        self.assertEqual(helpers.dump(h.db), before)
        with self.assertRaises(SpineValidationError) as caught:
            catalog.lookup(h.db, "related_task_rules", "missing", "related_task_rule_id")
        self.assertEqual(caught.exception.code, "referenced_row_not_found:related_task_rule_id")
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
