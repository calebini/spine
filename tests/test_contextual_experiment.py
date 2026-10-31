"""Real Spine authoring/rendering, independent Impetus subprocess and capture only."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from spine.adapters.contextual_experiment import CaptureStore, LocalImpetus, Source, dump
from spine.commands import CommandContext, handle
from spine.runtime.contextual_experiment_demo import seed
from spine.services.contextual_experiment import SCHEMA, Experiment, utc

IMPETUS = Path(os.environ.get("IMPETUS_SRC", Path(__file__).resolve().parents[2] / "impetus/src"))


@unittest.skipUnless((IMPETUS / "impetus").is_dir(), "Independent Impetus checkout required; set IMPETUS_SRC")
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.db, self.work, self.config = seed(self.root / "ledger.sqlite3", self.now)
        self.source = Source(self.db)
        self.path = self.root / "capture.sqlite3"
        CaptureStore.initialize(self.path, self.source.namespace)
        self.store = CaptureStore(self.path, self.source.namespace)
        self.env = dict(os.environ, PYTHONPATH=str(IMPETUS))
        self.command = [sys.executable, "-m", "impetus", "--state", str(self.root / "impetus")]
        subprocess.run([*self.command, "init", "--namespace", self.source.namespace], env=self.env, check=True, capture_output=True)
        self.experiment = Experiment(self.source, self.store, self.client(), self.config)

    def tearDown(self):
        self.store.close()
        self.db.close()
        self.tmp.cleanup()

    def client(self, scenario="context"):
        return LocalImpetus([*self.command, "--scenario", scenario], environment=self.env)

    def export(self):
        return self.experiment.export(self.work, utc(self.now))

    def test_context_and_stable_export_readback_without_ledger_writes(self):
        before = list(self.db.iterdump())
        opportunity, exported = self.export()
        request = json.loads(exported["request"])
        self.assertEqual(request["context"]["archetype"], "lesson")
        self.assertIn("in 1 hour", request["context"]["notification"]["ordinary_text"])
        self.assertNotIn("Do not disclose", exported["request"].decode())
        self.assertEqual(request["context"]["facets"], [])
        self.assertEqual(self.experiment.export(self.work, utc(self.now + timedelta(seconds=10)))[1]["request"], exported["request"])
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(record["reason"], "succeeded")
        self.assertTrue(record["usable_for_hypothetical_selection"])
        self.assertFalse(record["sent"])
        self.assertFalse(record["selected"])
        self.assertEqual(record["execution"]["result"]["basis"], "provided_context")
        self.assertEqual(record["request_sha256"], hashlib.sha256(exported["request"]).hexdigest())
        again = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(again["exchange"], "read")
        self.assertEqual(again["execution"]["calls"], record["execution"]["calls"])
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_sourced_no_addition_failure_and_uncertainty(self):
        for scenario, status in (
            ("sourced", "succeeded"),
            ("no-addition", "succeeded"),
            ("failure", "uncertain"),
            ("timeout", "uncertain"),
            ("invalid", "failed"),
        ):
            with self.subTest(scenario=scenario):
                # Fresh real ledger namespace for each independent synthetic opportunity.
                folder = self.root / scenario
                folder.mkdir()
                ledger, work, config = seed(folder / "ledger", self.now, archetype="activity")
                source = Source(ledger)
                config["allowed_tools"] = ["fixture.lookup.v1"] if scenario == "sourced" else []
                CaptureStore.initialize(folder / "capture", source.namespace)
                store = CaptureStore(folder / "capture", source.namespace)
                command = [sys.executable, "-m", "impetus", "--state", str(folder / "impetus")]
                try:
                    subprocess.run([*command, "init", "--namespace", source.namespace], env=self.env, check=True, capture_output=True)
                    exp = Experiment(source, store, LocalImpetus([*command, "--scenario", scenario], environment=self.env), config)
                    opportunity, _ = exp.export(work, utc(self.now))
                    record = exp.run(opportunity, utc(self.now))
                    self.assertEqual(record["execution"]["status"], status, record)
                    if scenario == "sourced":
                        self.assertEqual(len(record["execution"]["calls"]), 3)
                        self.assertEqual(record["execution"]["result"]["sources"][0]["observation_ordinal"], 2)
                    if scenario == "no-addition":
                        self.assertEqual(record["execution"]["result"]["kind"], "no_addition")
                    if status != "succeeded":
                        self.assertIsNone(record["execution"]["result"])
                        self.assertFalse(record["usable_for_hypothetical_selection"])
                finally:
                    store.close()
                    ledger.close()

    def test_lost_response_then_reopen_only_reads(self):
        real = self.client()

        class Lost:
            def exchange(self, operation, raw):
                result = real.exchange(operation, raw)
                return None if operation == "invoke" else result

        self.experiment.client = Lost()
        opportunity, _ = self.export()
        self.assertEqual(self.experiment.run(opportunity, utc(self.now))["reason"], "unresolved")
        self.store.close()
        self.store = CaptureStore(self.path, self.source.namespace)
        self.experiment = Experiment(self.source, self.store, self.client(), self.config)
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(record["exchange"], "read")
        self.assertEqual(record["execution"]["status"], "succeeded")
        self.assertEqual(len(record["execution"]["calls"]), 1)

    def test_send_marker_without_spawn_never_reinvokes(self):
        opportunity, _ = self.export()
        self.store.mark_launched(opportunity)  # crash after commit but before spawn
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(record["reason"], "absent")
        self.assertEqual(record["exchange"], "read")
        self.assertFalse(record["usable_for_hypothetical_selection"])

    def test_stale_source_and_changed_disclosure_cannot_use_or_research(self):
        opportunity, exported = self.export()
        first = self.experiment.run(opportunity, utc(self.now))
        item_id = json.loads(exported["request"])["source_refs"]["item_id"]
        result = handle(
            "schedule.update",
            dict(
                contract_version="spine.schedule-update.v2",
                command_id="change-source",
                actor_subject_id="owner",
                item_id=item_id,
                target_version="1",
                updated_at_utc=utc(self.now),
                patch={"item": {"title": "Changed synthetic lesson"}},
                materialization={"mode": "none"},
            ),
            CommandContext(ledger=self.db),
        )
        self.assertTrue(result["ok"], result)
        again = self.experiment.run(opportunity, utc(self.now))
        self.assertFalse(again["usable_for_hypothetical_selection"])
        self.assertIn(again["source"], ("stale", "unavailable"))
        self.assertEqual(again["execution"]["calls"], first["execution"]["calls"])
        self.assertEqual(self.export()[1]["request"], exported["request"])
        config = dict(self.config, opted_in_item_ids=[])
        exp = Experiment(self.source, self.store, self.client(), config)
        self.assertFalse(exp.readback(opportunity, utc(self.now))["usable_for_hypothetical_selection"])

    def test_late_capture_keeps_proposal_for_review(self):
        opportunity, exported = self.export()
        record = self.experiment.run(opportunity, utc(self.now))
        late = self.experiment.readback(opportunity, utc(self.now + timedelta(seconds=150)))
        self.assertFalse(late["usable_for_hypothetical_selection"])
        self.assertTrue(late["result_completed_by_cutoff"])
        self.assertEqual(late["execution"]["result"], record["execution"]["result"])
        self.assertEqual(len(self.store.history(opportunity)), 2)

    def test_source_change_before_spawn_blocks_invocation(self):
        opportunity, _ = self.export()
        self.experiment.config["opted_in_item_ids"] = []
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(record["exchange"], "not_invoked")
        self.assertFalse(self.store.get(opportunity)["launched"])

    def test_binding_conflict_and_untrusted_success_are_rejected(self):
        opportunity, exported = self.export()
        response = self.client().exchange("invoke", exported["request"])
        response["request_sha256"] = "a" * 64
        record = self.experiment.capture(opportunity, response, utc(self.now), "invoke")
        self.assertEqual(record["reason"], "invalid_response")
        self.assertIsNone(record["execution"])
        response = self.client().exchange("invoke", exported["request"])
        response["execution"]["result"]["basis"] = "retrieved"
        response["execution"]["result"]["sources"] = []
        self.assertEqual(self.experiment.capture(opportunity, response, utc(self.now), "invoke")["reason"], "invalid_response")
        changed = exported["request"] + b" "
        self.assertEqual(self.client().exchange("invoke", changed)["disposition"], "conflict")

    def test_missing_store_namespace_and_unapproved_input(self):
        with self.assertRaises(sqlite3.OperationalError):
            CaptureStore(self.root / "missing", self.source.namespace)
        with self.assertRaises(ValueError):
            CaptureStore(self.path, "other-ledger")
        self.experiment.config["opted_in_item_ids"] = []
        with self.assertRaises(ValueError):
            self.export()

    def test_permitted_facet_projection_and_redaction(self):
        request = json.loads(self.export()[1]["request"])
        item = request["source_refs"]["item_id"]
        archetype = self.db.execute("SELECT item_archetype_id FROM item_archetypes").fetchone()[0]
        context = CommandContext(ledger=self.db)
        owner = {"owner_kind": "subject", "owner_subject_id": "owner"}
        schema = handle(
            "facet_schema.create",
            dict(
                contract_version="spine.facet-schemas.v1",
                command_id="schema-details",
                actor_subject_id="owner",
                action_timestamp_utc=utc(self.now),
                owner=owner,
                schema_key="details",
                definition={
                    "display_name": "Lesson details",
                    "description": None,
                    "compatible_item_types": ["event"],
                    "fields": [
                        {"key": "instrument", "type": "text", "max_length": "64", "required": True, "queryable": False},
                        {"key": "private_note", "type": "text", "max_length": "64", "required": False, "queryable": False},
                    ],
                },
            ),
            context,
        )
        self.assertTrue(schema["ok"], schema)
        binding = handle(
            "item_archetype.facet_binding.set",
            dict(
                contract_version="spine.archetype-facet-bindings.v1",
                command_id="bind-details",
                actor_subject_id="owner",
                action_timestamp_utc=utc(self.now),
                item_archetype_id=archetype,
                facet_key="details",
                facet_schema_revision_id=schema["facet_schema_revision_id"],
                expected_binding_id=None,
            ),
            context,
        )
        self.assertTrue(binding["ok"], binding)
        updated = handle(
            "item.facets.update",
            dict(
                contract_version="spine.item-facets.v1",
                command_id="values-details",
                actor_subject_id="owner",
                action_timestamp_utc=utc(self.now),
                item_id=item,
                expected_item_version="1",
                changes=[
                    {
                        "op": "set",
                        "facet_key": "details",
                        "expected_binding_id": binding["facet_binding_id"],
                        "facet_schema_revision_id": schema["facet_schema_revision_id"],
                        "values": {"instrument": "piano", "private_note": "hidden"},
                    }
                ],
            ),
            context,
        )
        self.assertTrue(updated["ok"], updated)
        config = dict(self.config, facet_fields={"details": ["instrument"]})
        snapshot = self.source.snapshot(self.work, config)
        self.assertEqual(snapshot["context"]["facets"][0]["values"], {"instrument": "piano"})
        self.assertNotIn("hidden", dump(snapshot).decode())
        # Original exported request remains immutable despite this source edit.
        self.assertEqual(json.loads(self.export()[1]["request"])["context"]["facets"], [])

    def test_worker_death_and_capture_restart_do_not_repeat_research(self):
        real = self.client()
        script = """
import os,sys
from impetus.adapters.sqlite import Store
from impetus.adapters.clock import Clock
from impetus.adapters.deterministic import Model,Tool
from impetus.services.worker import Worker
class Dies(Model):
 def respond(self,payload): os._exit(86)
s=Store(sys.argv[1]);Worker(s,Dies(),Tool(),Clock()).invoke(sys.stdin.buffer.read())
"""
        state = str(self.root / "impetus")
        env = self.env

        class Dies:
            def exchange(self, operation, raw):
                if operation == "invoke":
                    proc = subprocess.run([sys.executable, "-c", script, state], input=raw, env=env)
                    if proc.returncode != 86:
                        raise AssertionError(proc.returncode)
                    return None
                return real.exchange(operation, raw)

        self.experiment.client = Dies()
        opportunity, _ = self.export()
        self.assertEqual(self.experiment.run(opportunity, utc(self.now))["reason"], "unresolved")
        subprocess.run([*self.command, "recover"], env=self.env, check=True, capture_output=True)
        self.store.close()
        self.store = CaptureStore(self.path, self.source.namespace)
        exp = Experiment(self.source, self.store, self.client(), self.config)
        record = exp.run(opportunity, utc(self.now))
        self.assertEqual(record["exchange"], "read")
        self.assertEqual(record["execution"]["status"], "uncertain")
        self.assertEqual(len(record["execution"]["calls"]), 1)
        self.assertIsNone(record["execution"]["result"])
        self.assertFalse(record["usable_for_hypothetical_selection"])

    def test_contract_copies_agree(self):
        canonical = IMPETUS.parent / "contracts/schemas/contextual-notification-local-v1.schema.json"
        packaged = Path(__file__).parents[1] / "src/spine/contracts/contextual_notification/local-v1.schema.json"
        self.assertEqual(canonical.read_bytes(), packaged.read_bytes())
        Draft202012Validator.check_schema(SCHEMA)
