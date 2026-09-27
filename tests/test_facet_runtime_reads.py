"""Real SQLite cursor races, shared operation budgets and CLI protected config."""

import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from spine.commands import facet_reads, handle
from spine.commands.cli import main
from spine.commands.facet_runtime import (
    FacetBudget,
    FacetCursorConfig,
    decode_cursor,
    encode_cursor,
    load_cursor_config,
    utc_now,
    wire_time,
)
from spine.core.errors import SpineValidationError
from spine.ledger import connect
from tests import test_facet_commands as commands
from tests.facet_storage_support import all_rows


class FacetReadRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        commands.FacetCommandTests.setUpClass()

    def setUp(self):
        self.h = commands.FacetCommandTests()
        self.h.setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "ledger.sqlite"
        target = sqlite3.connect(self.path)
        self.h.db.backup(target)
        target.close()
        self.h.db.close()
        self.h.db = connect(self.path)
        self.h.fixture.connection = self.h.db
        self.h.context = replace(self.h.context, ledger=self.h.db, ledger_path=str(self.path))
        self.other = connect(self.path)

    def tearDown(self):
        self.other.close()
        self.h.tearDown()
        self.directory.cleanup()

    def catalog_request(self):
        return self.h.request("facet_schema.list", owner={"owner_kind": "subject", "owner_subject_id": "owner"}, limit="1")

    def test_first_and_continuation_source_races_are_not_retried(self):
        schema, _ = self.h.catalog("a")
        self.h.catalog("b")
        request = self.catalog_request()
        page = self.h.call("facet_schema.list", request)
        for continuation in (False, True):
            req = {**request, "cursor": page["next_cursor"]} if continuation else request
            selected = schema
            original = facet_reads.source
            calls = []

            def racing(command, r, db, budget, original=original, calls=calls, selected=selected, continuation=continuation):
                facts, rows = original(command, r, db, budget)
                calls.append(1)
                if len(calls) == 1:
                    edited = self.h.request(
                        "facet_schema.publish",
                        facet_schema_id=selected["facet_schema_id"],
                        expected_current_revision_id=selected["facet_schema_revision_id"],
                        definition={**commands.DEFINITION, "display_name": f"Changed {continuation}"},
                    )
                    changed = handle("facet_schema.publish", edited, replace(self.h.context, ledger=self.other))
                    self.assertTrue(changed["ok"], changed)
                    schema.update(changed)
                return facts, rows

            before_receipts = self.h.db.execute("SELECT count(*) FROM command_receipts").fetchone()[0]
            with patch("spine.commands.facet_reads.source", racing):
                result = handle("facet_schema.list", req, self.h.context)
            self.assertFalse(result["ok"], result)
            self.assertEqual(result["error"]["code"], "stale_cursor" if continuation else "environment_failure")
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.h.db.execute("SELECT count(*) FROM command_receipts").fetchone()[0], before_receipts + 1)
            page = self.h.call("facet_schema.list", request)

    def test_cursor_context_expiry_query_and_canonical_encoding(self):
        self.h.catalog("a")
        self.h.catalog("b")
        request = self.catalog_request()
        page = self.h.call("facet_schema.list", request)
        token = page["next_cursor"]
        config = self.h.context.facet_cursor_config
        payload = decode_cursor(config, token)
        req = {**request, "cursor": token}
        before = all_rows(self.h.db)
        for config2, code in (
            (FacetCursorConfig(config.secret, "clone", config.generation), "stale_cursor"),
            (FacetCursorConfig(config.secret, config.ledger_id, "restored"), "stale_cursor"),
            (FacetCursorConfig(b"new" * 20, config.ledger_id, config.generation), "invalid_request"),
        ):
            result = handle("facet_schema.list", req, replace(self.h.context, facet_cursor_config=config2))
            self.assertEqual(result["error"]["code"], code)
        self.assertEqual(handle("facet_schema.list", {**req, "limit": "2"}, self.h.context)["error"]["code"], "invalid_request")
        expired = {
            **payload,
            "issued_at_utc": wire_time(utc_now() - timedelta(seconds=901)),
            "expires_at_utc": wire_time(utc_now() - timedelta(seconds=1)),
        }
        result = handle("facet_schema.list", {**request, "cursor": encode_cursor(config, expired)}, self.h.context)
        self.assertEqual(result["error"]["code"], "stale_cursor")
        malformed = {**payload, "extra": "forbidden"}
        self.assertEqual(
            handle("facet_schema.list", {**request, "cursor": encode_cursor(config, malformed)}, self.h.context)["error"]["code"],
            "invalid_request",
        )
        self.assertEqual(all_rows(self.h.db), before)

    def test_capacity_including_release_revalidation_has_no_durable_trace(self):
        for i in range(5):
            self.h.catalog(f"schema{i}")
        request = self.catalog_request()
        before = all_rows(self.h.db)
        with patch.object(FacetBudget, "progress", lambda self: 1):
            result = handle("facet_schema.list", request, self.h.context)
        self.assertEqual(result["error"]["code"], "environment_failure")
        original = facet_reads.source
        calls = []

        def exhausted(command, r, db, budget):
            calls.append(budget)
            if len(calls) == 2:
                budget.steps = 100001
            return original(command, r, db, budget)

        with patch("spine.commands.facet_reads.source", exhausted):
            result = handle("facet_schema.list", request, self.h.context)
        self.assertEqual(result["error"]["field"], "capacity")
        self.assertIs(calls[0], calls[1])
        self.assertEqual(all_rows(self.h.db), before)

    def test_concurrent_facet_and_schedule_edit_have_one_winner(self):
        schema, binding = self.h.catalog()
        event = self.h.event()
        ready = threading.Barrier(2)
        results = []
        facet = self.h.update(event["item_id"], schema, binding)
        update = {
            "contract_version": "spine.schedule-update.v2",
            "command_id": "race-schedule",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "1",
            "updated_at_utc": commands.NOW,
            "patch": {"item": {"title": "Moved title"}},
            "materialization": {"mode": "none"},
        }

        def run(command, request):
            db = connect(self.path)
            try:
                ready.wait(5)
                results.append(handle(command, request, replace(self.h.context, ledger=db)))
            finally:
                db.close()

        threads = [
            threading.Thread(target=run, args=("item.facets.update", facet)),
            threading.Thread(target=run, args=("schedule.update", update)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
            self.assertFalse(t.is_alive())
        self.assertEqual(sum(r["ok"] for r in results), 1, results)
        self.assertEqual([r["error"]["code"] for r in results if not r["ok"]], ["stale_version"])
        self.assertEqual(
            self.h.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0], 2
        )

    def test_candidate_and_deadline_bounds_fail_without_partial_page(self):
        for i in range(101):
            self.h.call(
                "facet_schema.create",
                owner={"owner_kind": "subject", "owner_subject_id": "owner"},
                schema_key=f"bounded{i}",
                definition=commands.DEFINITION,
            )
        before = all_rows(self.h.db)
        result = handle("facet_schema.list", self.catalog_request(), self.h.context)
        self.assertEqual(result["error"]["code"], "environment_failure")
        self.assertNotIn("schemas", result)
        with patch("spine.commands.facets.FacetBudget", lambda: FacetBudget(started=0)):
            result = handle("facet_schema.list", self.catalog_request(), self.h.context)
        self.assertEqual(result["error"]["field"], "capacity")
        self.assertEqual(all_rows(self.h.db), before)

    def test_cli_protected_config_and_preview_never_copy_ledger(self):
        self.h.catalog()
        config_path = Path(self.directory.name) / "cursors.json"
        # Test fixture files only; production reads configuration without creating it.
        config_path.write_text(json.dumps({"secret_hex": (b"a" * 32).hex(), "cursor_ledger_id": "local", "cursor_generation": "1"}))
        config_path.chmod(0o600)
        self.assertEqual(load_cursor_config(str(config_path)).secret, b"a" * 32)
        config_path.chmod(0o644)
        with self.assertRaises(SpineValidationError):
            load_cursor_config(str(config_path))
        config_path.chmod(0o600)
        with (
            patch.dict(os.environ, {"SPINE_FACET_CURSOR_CONFIG": str(config_path)}),
            patch("sys.stdin", io.StringIO(json.dumps(self.catalog_request()))),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            self.assertEqual(main(["--db", str(self.path), "facet_schema", "list"]), 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])
        request = self.h.request(
            "facet_schema.create",
            owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            schema_key="preview",
            definition=commands.DEFINITION,
        )
        before = all_rows(self.h.db)
        from spine.ledger.transactions import LedgerConnection

        with (
            patch.object(LedgerConnection, "backup", side_effect=AssertionError("whole ledger copy forbidden")),
            patch("sys.stdin", io.StringIO(json.dumps(request))),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            self.assertEqual(main(["--db", str(self.path), "--dry-run", "facet_schema", "create"]), 0, out.getvalue())
        self.assertTrue(json.loads(out.getvalue())["dry_run"])
        self.assertEqual(all_rows(self.h.db), before)
        with (
            patch("sys.stdin", io.StringIO('{"contract_version":"a","contract_version":"b"}')),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            self.assertEqual(main(["--db", str(self.path), "--dry-run", "facet_schema", "create"]), 2)
        self.assertTrue(json.loads(out.getvalue())["dry_run"])
        self.assertEqual(all_rows(self.h.db), before)
