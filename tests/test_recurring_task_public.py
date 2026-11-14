"""Public local CLI and worker startup on disposable schema-20 ledgers."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.commands.cli import main
from spine.commands.registry import RECURRING_TASK_COMMANDS, WORKER_REQUIRED_CONTRACT_VERSIONS
from spine.ledger import connect
from spine.runtime.worker import run_spine_worker
from tests import test_recurring_task_commands as base


class RecurringPublicTests(unittest.TestCase):
    def setUp(self):
        self.h = base.RecurringTaskCommandTests()
        self.h.setUpClass()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = root / "ledger.sqlite"
        self.db = connect(self.path)
        self.h.db.backup(self.db)
        self.db.close()
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        config = self.h.context.facet_cursor_config
        self.key = root / "cursor.json"
        self.key.write_text(json.dumps({"secret_hex": config.secret.hex(), "cursor_ledger_id": config.ledger_id,
                                       "cursor_generation": config.generation}))
        self.key.chmod(0o600)
        self.enterContext(patch.dict(os.environ, {"SPINE_FACET_CURSOR_CONFIG": str(self.key)}))
        clock = self.enterContext(patch("spine.commands.recurring_tasks.datetime"))
        clock.now.return_value = datetime.fromisoformat(base.NOW)
        self.root = root

    def cli(self, name, request, *, flags=(), success=True):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output):
            code = main(["--db", str(self.path), "--input", "-", *flags, *name.split(".")])
        response = json.loads(output.getvalue())
        self.assertEqual(response["ok"], success, response)
        self.assertEqual(code == 0, success, response)
        return response

    def command(self, action, request, **kwargs):
        return self.cli("schedule.related_task_rule." + action, request, **kwargs)

    def shown(self, identity):
        return self.command("show", {"contract_version": "spine.recurring-related-tasks.v1",
                                     "related_task_rule_id": identity})["result"]["rule"]

    def test_public_create_preview_replay_paginated_generation_and_local_ownership(self):
        request = self.h.request("public")
        preview = self.command("create", request, flags=("--dry-run",))
        self.assertTrue(preview["dry_run"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM related_task_rules").fetchone()[0], 0)
        created = self.command("create", request)
        self.assertEqual(self.command("create", request)["command_receipt_id"], created["command_receipt_id"])
        identity = created["result"]["rule"]["related_task_rule_id"]
        cursor, tasks = {}, []
        for index in range(8):
            req = self.h.write("public-page-" + str(index), self.shown(identity), limits={"source_candidates": "2"}, **cursor)
            result = self.command("reconcile", req)["result"]
            tasks.extend(v["after"]["task_item_id"] for v in result["results"] if v["outcome"] == "created")
            if not result["has_more"]:
                break
            cursor = {"cursor": result["next_cursor"]}
        self.assertEqual(len(set(tasks)), 6)
        self.assertFalse(result["has_more"])
        self.assertEqual(self.db.execute("SELECT mode,realm_id FROM ledger_access_state").fetchone()[:], ("trusted_local", None))
        self.assertEqual(self.db.execute("SELECT count(*) FROM login_accounts").fetchone()[0], 0)
        listing = self.command("list", {"contract_version": "spine.recurring-related-tasks.v1", "limit": "1"})
        self.assertFalse(listing["result"]["has_more"])
        first = self.command("show", {"contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": identity,
                                       "view": "assignments", "limit": "1"})["result"]["rows"][0]
        self.assertIsNotNone(first)

    def test_public_family_never_admits_web_context_or_missing_assets(self):
        request = {"contract_version": "spine.recurring-related-tasks.v1"}
        response = handle("schedule.related_task_rule.list", request,
                          CommandContext(ledger=self.db, transport_metadata={"adapter": "web"}))
        self.assertFalse(response["ok"])
        with patch("spine.commands.recurring_task_package._read", side_effect=FileNotFoundError("missing")):
            response = self.command("list", request, success=False)
        self.assertEqual(response["error"]["field"], "runtime_contracts")

    def test_worker_missing_configuration_stops_before_processor_and_can_restart_configured(self):
        self.command("create", self.h.request("worker"))
        with patch("spine.runtime.worker._worker_processor", side_effect=AssertionError("processing before admission")):
            result = run_spine_worker(self.db, state_dir=self.root / "bad-state", max_cycles=1, install_signal_handlers=False)
        self.assertNotEqual(result.exit_code, 0)
        health = json.loads((self.root / "bad-state/health.json").read_text())
        self.assertEqual(health["state"], "DOWN")
        self.assertFalse(health["is_ready"])
        result = run_spine_worker(self.db, state_dir=self.root / "good-state", max_cycles=1, install_signal_handlers=False,
                                  scheduler_actor_subject_id="owner", facet_cursor_config=str(self.key))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_required_worker_versions_include_recurring_family(self):
        self.assertEqual(len(RECURRING_TASK_COMMANDS), 7)
        self.assertIn("spine.recurring-related-tasks.v1", WORKER_REQUIRED_CONTRACT_VERSIONS)
        self.assertIn("spine.ownership-access-state.v1", WORKER_REQUIRED_CONTRACT_VERSIONS)

    def test_existing_facet_key_does_not_require_actor_without_rules(self):
        from spine.runtime.worker import _recurring_scheduler

        self.assertIsNone(_recurring_scheduler(self.db, None, str(self.key)))

    def test_public_ownership_successor_promotes_local_state_only_by_explicit_plan(self):
        from spine.ledger.identity import read_ledger_instance_id

        created = self.command("create", self.h.request("owned"))["result"]["rule"]
        self.command("reconcile", self.h.write("owned-page", created, limits={"source_candidates": "1"}))
        epoch = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        proposal = self.cli("web_access.plan", {"contract_version": "spine.trusted-web-provisioning.v3",
            "ledger_id": read_ledger_instance_id(self.db), "realm_id": "explicit-test-realm", "expected_access_epoch": epoch,
            "operators": [{"operation": "create", "subject_id": "owner", "display_name": "Operator",
                           "activation_basis": "trusted_local_approval"}]})
        self.assertTrue(proposal["can_apply"], proposal)
        req = {"contract_version": "spine.trusted-web-provisioning.v3", "command_id": "promote-explicitly",
               "actor_subject_id": "owner", "action_timestamp_utc": base.NOW,
               "expected_access_epoch": epoch, "plan": proposal}
        self.cli("web_access.apply", req, flags=("--dry-run",))
        self.assertEqual(self.db.execute("SELECT mode FROM ledger_access_state").fetchone()[0], "trusted_local")
        self.cli("web_access.apply", req)
        self.assertEqual(self.db.execute("SELECT mode,realm_id FROM ledger_access_state").fetchone()[:],
                         ("multi_user", "explicit-test-realm"))
