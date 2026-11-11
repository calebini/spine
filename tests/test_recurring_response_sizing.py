"""Exact RF1 response-sizing evidence, using disposable ledgers and fixed clocks."""

from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from spine.commands import recurring_tasks as commands
from spine.core.canonical_json import canonical_json_bytes
from spine.services.recurring_task_reconcile import reconcile
from tests import test_recurring_task_reconcile as helpers

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf1_response_sizing_witness.json"


def digest(value):
    data = canonical_json_bytes(value)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def setup_case():
    h = helpers.RecurringTaskReconcileTests()
    h.contracts = helpers.base.contracts()
    with patch("spine.ledger.identity.secrets.token_hex", return_value="19" * 32):
        h.setUp()
    return h


def collect_baseline():
    """Capture actual response trials, final envelopes, replay and complete ledger state."""
    cases = {}
    for kind in ("changed", "noop", "dry_run", "byte_pages"):
        h = setup_case()
        try:
            rule = h.created()["result"]["rule"]
            if kind == "noop":
                rule = h.reconcile(rule, "rf1-seed")["result"]["rule"]
            context = replace(h.context, dry_run=kind == "dry_run")
            limits = {}
            if kind == "byte_pages":
                preview = h.run_command("reconcile", h.write("reconcile", rule, limits={}), context=replace(context, dry_run=True))
                h.assertTrue(preview["ok"], preview)
                limits["response_bytes"] = str(len(canonical_json_bytes(preview)) * 3 // 4)
            request = h.write("reconcile", rule, limits=limits)
            request["command_id"] = "rf1-sizing-page-0"
            before = helpers.base.dump(h.db)
            trials, pages, replay = [], [], None
            original = commands.success_response

            def capture(*args, _original=original, _trials=trials, **kwargs):
                response = _original(*args, **kwargs)
                _trials.append(digest(response))
                return response

            with patch.object(commands, "success_response", side_effect=capture):
                for index in range(10):
                    response = h.run_command("reconcile", request, context=context)
                    h.assertTrue(response["ok"], response)
                    pages.append(
                        {
                            **digest(response),
                            "effect": response["effect"],
                            "has_more": response["result"]["has_more"],
                            "assignments": [entry["assignment_id"] for entry in response["result"]["results"]],
                        }
                    )
                    if not context.dry_run:
                        at_replay = helpers.base.dump(h.db)
                        replay = h.run_command("reconcile", request, context=context)
                        h.assertTrue(replay["replayed"], replay)
                        h.assertEqual(helpers.base.dump(h.db), at_replay)
                    if kind != "byte_pages" or not response["result"]["has_more"]:
                        break
                    request = h.write("reconcile", response["result"]["rule"], limits=limits)
                    request.update(command_id=f"rf1-sizing-page-{index + 1}", cursor=response["result"]["next_cursor"])
                else:
                    raise AssertionError("pagination did not finish")
            after = helpers.base.dump(h.db)
            cases[kind] = {
                "trials": trials,
                "pages": pages,
                "replay": digest(replay),
                "ledger_sha256": hashlib.sha256(after.encode()).hexdigest(),
                "ledger_unchanged": before == after,
                "generation_count": h.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0],
            }
            h.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        finally:
            h.doCleanups()
    return cases


class RecurringResponseSizingTests(unittest.TestCase):
    def test_complete_envelope_trials_replay_and_ledger_match_prechange_witness(self):
        self.assertEqual(collect_baseline(), json.loads(FIXTURE.read_text())["cases"])

    def test_sizer_uses_the_command_envelope_and_current_audit_snapshot(self):
        result = {"title": "Après l’école 🧪", "results": [], "delivery": "not_attempted_by_command"}
        for changed in (False, True):
            for dry_run in (False, True):
                with self.subTest(changed=changed, dry_run=dry_run):
                    request = {"command_id": "rf1-unicode"}
                    measure = commands.response_sizer(commands.PREFIX + "reconcile", request, helpers.base.NOW, dry_run=dry_run)
                    request["command_id"] = "must-not-replace-bound-identity"
                    for audits in ((), ("audit_z", "audit_a"), ("audit_a",)):
                        before = deepcopy(result)
                        expected = commands.success_response(
                            commands.PREFIX + "reconcile",
                            {"command_id": "rf1-unicode"},
                            result,
                            "rule_page_applied" if changed else "rule_page_noop",
                            changed,
                            helpers.base.NOW,
                            {"audit_ids": audits},
                            dry_run=dry_run,
                        )
                        self.assertEqual(
                            measure(
                                result=result,
                                effect=expected["effect"],
                                changed=changed,
                                audit_ids=audits,
                            ),
                            len(canonical_json_bytes(expected)),
                        )
                        self.assertEqual(result, before)

    def test_sizing_capability_is_required_before_any_ledger_access(self):
        untouched = Mock()
        with self.assertRaisesRegex(TypeError, "response_size"):
            reconcile(untouched, {}, {}, untouched, untouched, helpers.base.NOW, {}, untouched)
        self.assertEqual(untouched.mock_calls, [])
        h = setup_case()
        self.addCleanup(h.doCleanups)
        rule = h.created()["result"]["rule"]
        request = h.write("reconcile", rule, limits={})
        created = h.run_command("reconcile", request)
        self.assertTrue(created["ok"], created)
        before = helpers.base.dump(h.db)
        with patch.object(commands, "response_sizer", side_effect=AssertionError("admission/replay must not create a sizer")):
            denied = h.run_command("reconcile", request, context=replace(h.context, transport_metadata={"adapter": "web"}))
            self.assertEqual((denied["error"]["code"], denied["error"]["field"]), ("environment_failure", "admission"))
            replayed = h.run_command("reconcile", request)
            self.assertTrue(replayed["replayed"], replayed)
        self.assertEqual(helpers.base.dump(h.db), before)

    def test_sizing_failure_aborts_without_partial_work_and_connection_is_reusable(self):
        h = setup_case()
        self.addCleanup(h.doCleanups)
        rule = h.created()["result"]["rule"]
        request = h.write("reconcile", rule, limits={})
        before = helpers.base.dump(h.db)
        failure = Mock(side_effect=RuntimeError("sizing failed"))
        with patch.object(commands, "response_sizer", return_value=failure), self.assertRaisesRegex(RuntimeError, "sizing failed"):
            h.run_command("reconcile", request)
        self.assertGreater(failure.call_count, 0)
        self.assertEqual(helpers.base.dump(h.db), before)
        response = h.run_command("reconcile", request)
        self.assertTrue(response["ok"], response)
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_exact_and_one_byte_under_limits_preserve_atomic_units(self):
        def trial(limit, dry_run):
            # Command admission owns its transaction: use identical fresh ledgers,
            # not an enclosing writer that admission deliberately rejects.
            h = setup_case()
            try:
                rule = h.created()["result"]["rule"]
                before = helpers.base.dump(h.db)
                request = h.write("reconcile", rule, limits={"response_bytes": str(limit)})
                response = h.run_command("reconcile", request, context=replace(h.context, dry_run=dry_run))
                if dry_run or not response["ok"]:
                    self.assertEqual(helpers.base.dump(h.db), before)
                else:
                    self.assertEqual(
                        h.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0],
                        len(response["result"]["results"]),
                    )
                self.assertEqual(h.db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
                return response
            finally:
                h.doCleanups()

        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                whole = trial(262144, dry_run)
                self.assertTrue(whole["ok"], whole)
                self.assertEqual(len(whole["result"]["results"]), 6)
                self.assertFalse(whole["result"]["has_more"])
                size = len(canonical_json_bytes(whole))
                # The complete result also publishes its limits. Find the fixed
                # point rather than assuming the original six-digit cap is free.
                for _ in range(3):
                    exact = trial(size, dry_run)
                    self.assertTrue(exact["ok"], exact)
                    actual_size = len(canonical_json_bytes(exact))
                    if actual_size == size:
                        break
                    size = actual_size
                else:
                    self.fail("exact response-size limit did not stabilize")
                self.assertEqual(len(exact["result"]["results"]), 6)
                self.assertFalse(exact["result"]["has_more"])
                under = trial(size - 1, dry_run)
                if under["ok"]:
                    self.assertLessEqual(len(canonical_json_bytes(under)), size - 1)
                    self.assertTrue(under["result"]["has_more"])
                    self.assertLess(len(under["result"]["results"]), 6)
                else:
                    self.assertEqual((under["error"]["code"], under["error"]["field"]), ("capacity_exceeded", "limits.response_bytes"))
