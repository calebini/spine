"""SPINE-051 executable candidate checks; no live activation or real adapters."""

import copy
import json
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.commands.rendering_catalog import execute
from spine.commands.rendering_runtime import RenderingCursorConfig
from spine.core import rendering_definitions as codec
from spine.ledger import connect, initialize_schema
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.rendering_definitions import load_presentation, verify_deep
from spine.ledger.rendering_migration import install_candidate
from tests import test_schedule_operations_command as scheduling
from tests.facet_storage_support import DEFINITION, NOW

ROOT = Path(__file__).parents[1]


class RenderingFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text()) for p in (ROOT / "contracts/schemas").glob("*.schema.json")]
        cls.registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)

    def setUp(self):
        self.fixture = scheduling.ScheduleOperationsCommandTests()
        self.fixture.setUp()
        self.db = self.fixture.connection
        self.context = CommandContext(ledger=self.db)
        install_candidate(self.db, disposable_test_ledger=True)
        self.config = RenderingCursorConfig("test", "generation", read_ledger_instance_id(self.db), b"x" * 32)
        self.counter = 0
        self.scope = {"owner_kind": "subject", "owner_subject_id": "owner"}
        schema = handle(
            "facet_schema.create",
            {
                "contract_version": "spine.facet-schemas.v1",
                "command_id": "rendering-schema",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.scope,
                "schema_key": "flight",
                "definition": DEFINITION,
            },
            self.context,
        )
        self.assertTrue(schema["ok"], schema)
        self.revision = {
            "display_name": "Flight details",
            "description": None,
            "compatible_item_types": ["event"],
            "base_rendering_contract": "spine.notification-rendering.v1",
            "base_rendering_profile": "spine.notification-rendering.concise-en-ca.v1",
            "selections": [
                {
                    "selection_key": "flight",
                    "facet_key": "flight",
                    "facet_schema_revision_id": schema["facet_schema_revision_id"],
                    "field_key": "flight",
                    "projection": "value",
                    "label": "Flight",
                }
            ],
        }

    def tearDown(self):
        self.fixture.tearDown()

    def request(self, command, **facts):
        self.counter += 1
        value = {"contract_version": codec.DEFINITIONS if "definition." in command else codec.DISCLOSURES}
        if command.rsplit(".", 1)[1] not in {"show", "list"}:
            value.update(command_id=f"rendering-{self.counter}", actor_subject_id="owner", action_timestamp_utc=NOW)
        return value | facts

    def call(self, command, request=None, **facts):
        response = execute(command, request or self.request(command, **facts), self.context, cursor_config=self.config, now=NOW)
        self.assertTrue(response["ok"], response)
        uri = "https://cortext.local/spine/contracts/schemas/notification-rendering-definition-responses.schema.json#/$defs/" + command
        Draft202012Validator({"$ref": uri}, registry=self.registry).validate(response)
        return response

    def create(self, key="flight"):
        return self.call("notification_rendering_definition.create", owner=self.scope, definition_key=key, revision=self.revision)

    def test_rendering_is_publicly_activated_only_on_local_surface(self):
        self.assertEqual(self.db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0], 19)
        result = handle(
            "notification_rendering_definition.create",
            self.request("notification_rendering_definition.create", owner=self.scope, definition_key="flight", revision=self.revision),
            self.context,
        )
        self.assertTrue(result["ok"], result)
        web_registry = json.loads((ROOT / "contracts/spine.trusted-web-command-registry.v1.json").read_text())
        self.assertNotIn("notification_rendering_definition.create", {r["command"] for r in web_registry["commands"]})

    def test_catalog_replay_noop_retirement_dry_run_and_immutability(self):
        command = "notification_rendering_definition.create"
        request = self.request(command, owner=self.scope, definition_key="flight", revision=self.revision)
        first = self.call(command, request)
        generation = self.db.execute("SELECT generation FROM notification_rendering_catalog_state").fetchone()[0]
        replay = self.call(command, request)
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["record"], replay["record"])
        self.assertEqual(generation, self.db.execute("SELECT generation FROM notification_rendering_catalog_state").fetchone()[0])
        r = first["record"]
        noop = self.call(
            "notification_rendering_definition.publish",
            notification_rendering_definition_id=r["notification_rendering_definition_id"],
            expected_current_revision_id=r["current_revision_id"],
            revision=self.revision,
        )
        self.assertFalse(noop["changed"])
        self.assertEqual(r, noop["record"])
        self.assertEqual(generation, self.db.execute("SELECT generation FROM notification_rendering_catalog_state").fetchone()[0])
        preview_request = self.request(command, owner=self.scope, definition_key="preview", revision=self.revision)
        before = self.db.total_changes
        preview = execute(command, preview_request, replace(self.context, dry_run=True), now=NOW)
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(preview["dry_run"])
        self.assertIsNone(self.db.execute("SELECT 1 FROM notification_rendering_definitions WHERE definition_key='preview'").fetchone())
        self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id=?", (preview_request["command_id"],)).fetchone())
        self.assertGreater(self.db.total_changes, before)  # Executed validation, rolled back.
        retired = self.call(
            "notification_rendering_definition.retire",
            notification_rendering_definition_id=r["notification_rendering_definition_id"],
            expected_current_revision_id=r["current_revision_id"],
            reason_code="replaced",
        )
        self.assertEqual(retired["record"]["status"], "retired")
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            self.db.execute("UPDATE notification_rendering_definition_revisions SET definition_hash=?", ("a" * 64,))
        verify_deep(self.db)

    def test_authenticated_keyset_cursor_no_durable_reads_and_staleness(self):
        self.create("flight_one")
        self.create("flight_two")
        request = self.request("notification_rendering_definition.list", owner=self.scope, status="active", limit="1")
        before = self.db.total_changes
        first = self.call("notification_rendering_definition.list", request)
        self.assertTrue(first["has_more"])
        second = self.call("notification_rendering_definition.list", request | {"cursor": first["next_cursor"]})
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["records"][0], second["records"][0])
        self.assertEqual(self.db.total_changes, before)
        self.create("flight_three")
        stale = execute(
            "notification_rendering_definition.list",
            request | {"cursor": first["next_cursor"]},
            self.context,
            cursor_config=self.config,
            now=NOW,
        )
        self.assertEqual(stale["error"]["code"], "stale_cursor")
        tampered = execute(
            "notification_rendering_definition.list",
            request | {"cursor": first["next_cursor"] + "x"},
            self.context,
            cursor_config=self.config,
            now=NOW,
        )
        self.assertEqual(tampered["error"]["code"], "stale_cursor")

    def test_all_existing_policy_writers_stage_explicit_support(self):
        result = handle("schedule.create", self.fixture.event_request("ordinary", materialize=False), self.context)
        self.assertTrue(result["ok"], result)
        policies = self.db.execute("SELECT policy_id FROM notification_policies").fetchall()
        self.assertTrue(policies)
        for r in policies:
            self.assertEqual(load_presentation(self.db, r[0]), {"kind": "ordinary"})
        verify_deep(self.db)

    def test_catalog_closed_query_status_binding_and_capacity_fail_closed(self):
        self.create("one")
        self.create("two")
        request = self.request("notification_rendering_definition.list", owner=self.scope, status="active", limit="1")
        first = self.call("notification_rendering_definition.list", request)
        for changed in ({"limit": "2"}, {"status": "retired"}):
            result = execute(
                "notification_rendering_definition.list",
                request | changed | {"cursor": first["next_cursor"]},
                self.context,
                cursor_config=self.config,
                now=NOW,
            )
            self.assertEqual(result["error"]["code"], "stale_cursor")
        for status in (None, "all"):
            result = execute(
                "notification_rendering_definition.list", request | {"status": status}, self.context, cursor_config=self.config, now=NOW
            )
            self.assertFalse(result["ok"])
        from unittest.mock import patch

        from spine.commands.facet_runtime import FacetBudget

        with patch("spine.commands.rendering_catalog.FacetBudget", return_value=FacetBudget(steps=100001)):
            result = execute(
                "notification_rendering_definition.show",
                self.request(
                    "notification_rendering_definition.show",
                    notification_rendering_definition_id=first["records"][0]["notification_rendering_definition_id"],
                ),
                self.context,
                now=NOW,
            )
        self.assertEqual(result["error"]["code"], "environment_failure")

    def test_candidate_migration_fault_rolls_back_every_stage(self):
        for stage in ("preflight", "ddl", "backfill", "verified"):
            with self.subTest(stage=stage):
                db = connect()
                with patch("spine.ledger.rendering_migration.install_rendering_storage"):
                    initialize_schema(db)
                before = [tuple(r) for r in db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY name")]

                def fault(current, stage=stage):
                    if current == stage:
                        raise RuntimeError("injected migration interruption")

                with self.assertRaises(RuntimeError):
                    install_candidate(db, disposable_test_ledger=True, fault=fault)
                self.assertEqual(before, [tuple(r) for r in db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY name")])
                self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertFalse(db.in_transaction)
                db.close()

    def test_v2_profile_normalization_matches_computed_fixture(self):
        vector = json.loads((ROOT / "tests/fixtures/notification_rendering_integration/request_profile_create.json").read_text())
        normalized = codec.normalize_profile_v2(vector["revision"])
        from tests.rendering_integration_reference import digest, normalized_v2_revision, preimage

        expected = normalized_v2_revision(copy.deepcopy(vector["revision"]))
        self.assertEqual(
            normalized.normalized_revision_hash, digest(preimage("spine.notification-profile-revision-hash.v2", revision=expected))
        )
