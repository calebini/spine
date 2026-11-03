"""Fresh real Spine source, independent mock Impetus child and non-sending capture."""

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from spine.adapters.contextual_experiment import CaptureStore, Source, dump
from spine.adapters.contextual_live import LiveCaptureStore, LiveLauncher
from spine.commands import CommandContext, handle
from spine.runtime.contextual_live_capture import initialize
from spine.services.contextual_experiment import utc
from spine.services.contextual_live import SCHEMA, LiveExperiment

IMPETUS = Path(os.environ.get("IMPETUS_SRC", Path(__file__).resolve().parents[2] / "impetus/src"))
FIXTURE = Path(__file__).parent / "fixtures/contextual_live_worker.py"


@unittest.skipUnless((IMPETUS / "impetus").is_dir(), "Independent Impetus checkout required; set IMPETUS_SRC")
class LiveCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime(2060, 1, 1, 10, tzinfo=UTC)
        self.observed = self.now + timedelta(seconds=30)
        self.config_text = files("spine.contracts").joinpath("contextual_notification/live-configuration.json").read_text()
        self.folder = self.root / "fresh"
        self.db, self.work, self.config, self.store = initialize(self.folder, self.now, self.config_text)
        self.source = Source(self.db)
        self.config_path = self.root / "nonsecret-config.json"
        self.config_path.write_text(self.config_text)
        self.env = {k: v for k, v in os.environ.items() if k not in {
            "IMPETUS_OPENAI_API_KEY", "IMPETUS_OPENAI_API_KEY_FILE", "OPENAI_API_KEY"
        }}
        self.env["PYTHONPATH"] = str(IMPETUS)
        self.state = self.root / "impetus"
        subprocess.run([*self.command(), "--namespace", self.source.namespace, "init"], env=self.env, check=True, capture_output=True)
        self.experiment = self.make_experiment()

    def tearDown(self):
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)
        self.store.close()
        self.db.close()
        self.tmp.cleanup()

    def command(self, scenario="context"):
        return [sys.executable, str(FIXTURE), "--state", str(self.state), "--now", utc(self.now), "--scenario", scenario]

    def launcher(self, scenario="context", enabled=True, environment=None):
        return LiveLauncher(self.command(scenario), provider_configuration_path=self.config_path if enabled else None,
                            enabled=enabled, environment=environment or self.env)

    def make_experiment(self, scenario="context", launcher=None, config=None):
        return LiveExperiment(self.source, self.store, launcher or self.launcher(scenario), self.config if config is None else config,
                              clock=lambda: self.observed)

    def export(self):
        return self.experiment.export(self.work, utc(self.now))

    def run_scenario(self, scenario):
        self.experiment = self.make_experiment(scenario)
        opportunity, exported = self.export()
        return opportunity, exported, self.experiment.run(opportunity, utc(self.now))

    def test_connected_context_success_and_immutable_source(self):
        before = list(self.db.iterdump())
        opportunity, exported, record = self.run_scenario("context")
        self.assertEqual(record["reason"], "succeeded", record)
        self.assertTrue(record["usable_for_hypothetical_selection"])
        self.assertEqual(record["execution"]["result"]["basis"], "provided_context")
        self.assertEqual(record["execution"]["result"]["sources"], [])
        self.assertEqual([c["ordinal"] for c in record["execution"]["calls"]], [1, 2])
        self.assertIsNone(record["execution"]["calls"][1]["tokens"]["reasoning_tokens"])
        self.assertEqual(record["execution"]["calls"][0]["reserve"]["amount"], 1000000)
        self.assertFalse(record["sent"] or record["selected"])
        self.assertNotIn("Do not disclose", exported["request"].decode())
        self.assertEqual(self.experiment.export(self.work, utc(self.now + timedelta(seconds=5)))[1]["request"], exported["request"])
        again = self.experiment.run(opportunity)
        self.assertEqual(again["exchange"], "read")
        self.assertEqual(again["execution"], record["execution"])
        self.assertEqual(list(self.db.iterdump()), before)

    def test_successful_no_addition(self):
        _, _, record = self.run_scenario("no-addition")
        self.assertEqual(record["reason"], "succeeded", record)
        self.assertEqual(record["execution"]["result"]["kind"], "no_addition")

    def test_count_failure_retains_uncertainty_without_generation(self):
        _, _, record = self.run_scenario("count-failure")
        self.assertEqual(record["reason"], "uncertain", record)
        self.assertEqual(len(record["execution"]["calls"]), 1)
        self.assertIsNone(record["execution"]["calls"][0]["usage"])
        self.assertFalse(record["usable_for_hypothetical_selection"])

    def test_over_limit_count_retains_failed_truth(self):
        _, _, record = self.run_scenario("over-limit")
        self.assertEqual(record["reason"], "failed", record)
        self.assertEqual(len(record["execution"]["calls"]), 1)
        self.assertEqual(record["execution"]["reason"], "provider_count_over_limit")

    def test_count_generation_mismatch_retains_usage_but_no_proposal(self):
        _, _, record = self.run_scenario("mismatch")
        self.assertEqual(record["reason"], "failed", record)
        self.assertEqual(record["execution"]["reason"], "provider_count_mismatch")
        self.assertIsNotNone(record["execution"]["calls"][1]["usage"])
        self.assertIsNone(record["execution"]["result"])

    def test_unknown_generation_keeps_full_generation_reserve(self):
        _, _, record = self.run_scenario("generation-unknown")
        self.assertEqual(record["reason"], "uncertain", record)
        self.assertEqual(record["execution"]["calls"][1]["reserve"]["amount"], record["binding"]["generation_reserve"])

    def test_late_counted_generation_invoke_and_readback_are_schema_valid(self):
        opportunity, exported = self.export()
        launcher = self.launcher("late")
        launcher.prepare(exported["binding"])
        self.assertTrue(self.store.mark_launched(opportunity))
        invoke = launcher.exchange("invoke", exported["request"])
        Draft202012Validator(SCHEMA["$defs"]["response"]).validate(invoke)
        captured = self.experiment.capture(opportunity, invoke, utc(self.observed), "invoke")
        self.assertEqual(captured["reason"], "failed", captured)
        self.assertEqual(captured["execution"]["observations"][0]["call_ordinal"], 2)
        self.assertFalse(captured["usable_for_hypothetical_selection"])
        read = dict(interface=invoke["interface"], version=invoke["version"], ledger_instance_id=invoke["ledger_instance_id"],
                    work_id=invoke["work_id"], request_sha256=invoke["request_sha256"])
        found = self.launcher(enabled=False).exchange("read", dump(read))
        Draft202012Validator(SCHEMA["$defs"]["response"]).validate(found)
        again = self.experiment.readback(opportunity)
        self.assertEqual(again["execution"], captured["execution"])

    def test_invalid_execution_records_are_unusable_without_losing_marker(self):
        opportunity, _, record = self.run_scenario("context")
        raw = dict(interface="contextual-notification-experiment", version="impetus.openai.v1",
                   ledger_instance_id=record["ledger_instance_id"], work_id=record["work_id"], request_sha256=record["request_sha256"],
                   disposition="found", execution=record["execution"], reason=None)
        def set_path(value, path, replacement):
            for key in path[:-1]:
                value = value[key]
            value[path[-1]] = replacement
        changes = [
            (["configuration_revision"], "wrong"), (["prompt_revision"], "wrong"),
            (["authorized_nanodollars"], 0), (["calls", 0, "reserve", "amount"], 0),
            (["calls", 1, "count_call_ordinal"], 2), (["calls", 1, "request_sha256"], "a" * 64),
            (["calls", 1, "provider_model"], "wrong"), (["calls", 1, "tokens", "total_tokens"], 999),
            (["calls", 1, "tokens", "input_tokens"], 51), (["calls", 1, "usage", "amount"], 0),
            (["calls", 1, "reserve", "amount"], 0), (["calls", 0, "certainty"], "uncertain"),
            (["calls", 1, "possible_entry_at_utc"], "2060-02-30T00:00:00Z"),
            (["result", "basis"], "retrieved"), (["result", "text"], "é" * 300),
        ]
        for path, replacement in changes:
            with self.subTest(path=path):
                changed = copy.deepcopy(raw)
                set_path(changed["execution"], path, replacement)
                rejected = self.experiment.capture(opportunity, changed, utc(self.observed), "read")
                self.assertEqual(rejected["reason"], "invalid_response")
                self.assertIsNone(rejected["execution"])
                self.assertFalse(rejected["usable_for_hypothetical_selection"])
                self.assertTrue(self.store.get(opportunity)["launched"])
        changed = copy.deepcopy(raw)
        generation = changed["execution"]["calls"][1]
        generation["tokens"].update(input_tokens=51, total_tokens=81)
        generation["usage"]["amount"] = 17100
        generation["reserve"]["amount"] -= 100
        self.assertEqual(self.experiment.capture(opportunity, changed, utc(self.observed), "read")["reason"], "invalid_response")

    def test_unavailable_readback_never_reinvokes(self):
        opportunity, _ = self.export()
        self.store.mark_launched(opportunity)
        operations = []
        class Unavailable:
            def exchange(self, operation, raw):
                operations.append(operation)
                return None
        self.experiment = self.make_experiment(launcher=Unavailable())
        for _ in range(2):
            self.assertEqual(self.experiment.run(opportunity)["reason"], "unresolved")
        self.assertEqual(operations, ["read", "read"])

    def test_lost_response_restart_and_read_without_config_or_credentials(self):
        real = self.launcher()
        class Lost:
            prepare = real.prepare
            def exchange(self, operation, raw):
                result = real.exchange(operation, raw)
                return None if operation == "invoke" else result
        self.experiment = self.make_experiment(launcher=Lost())
        opportunity, exported = self.export()
        self.assertEqual(self.experiment.run(opportunity, utc(self.now))["reason"], "unresolved")
        self.store.close()
        self.store = LiveCaptureStore(self.folder / "capture.sqlite3", self.source.namespace)
        self.config_path.unlink()
        changed = dict(self.config)
        changed.pop("provider_configuration_json")
        env = dict(self.env, IMPETUS_OPENAI_API_KEY="synthetic-forbidden-on-read", OPENAI_API_KEY="synthetic-forbidden-on-read")
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False, environment=env), config=changed)
        record = self.experiment.run(opportunity)
        self.assertEqual(record["reason"], "succeeded", record)
        self.assertEqual(record["exchange"], "read")
        self.assertEqual(len(record["execution"]["calls"]), 2)
        self.assertFalse(record["usable_for_hypothetical_selection"])
        self.assertEqual(self.experiment.export(self.work)[1]["request"], exported["request"])

    def test_marker_without_spawn_does_not_invoke_even_when_read_absent(self):
        opportunity, _ = self.export()
        self.store.mark_launched(opportunity)
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False))
        for _ in range(2):
            record = self.experiment.run(opportunity)
            self.assertEqual(record["reason"], "absent")
            self.assertEqual(record["exchange"], "read")

    def test_worker_death_during_count_recovery_does_not_resume(self):
        opportunity, _, record = self.run_scenario("die-count")
        self.assertEqual(record["reason"], "unresolved")
        subprocess.run([*self.command(), "recover"], env=self.env, check=True, capture_output=True)
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False))
        record = self.experiment.run(opportunity)
        self.assertEqual(record["reason"], "uncertain", record)
        self.assertEqual(len(record["execution"]["calls"]), 1)

    def test_worker_death_after_count_does_not_repeat_generation(self):
        opportunity, _, record = self.run_scenario("die-generation")
        self.assertEqual(record["reason"], "unresolved")
        subprocess.run([*self.command(), "recover"], env=self.env, check=True, capture_output=True)
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False))
        record = self.experiment.run(opportunity)
        self.assertEqual(record["reason"], "uncertain", record)
        self.assertEqual(len(record["execution"]["calls"]), 2)

    def test_death_after_completed_count_never_starts_generation_on_reopen(self):
        opportunity, _, record = self.run_scenario("die-after-count")
        self.assertEqual(record["reason"], "unresolved")
        self.store.close()
        self.store = LiveCaptureStore(self.folder / "capture.sqlite3", self.source.namespace)
        subprocess.run([*self.command(), "recover"], env=self.env, check=True, capture_output=True)
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False))
        record = self.experiment.run(opportunity)
        self.assertEqual(record["reason"], "interrupted", record)
        self.assertEqual(len(record["execution"]["calls"]), 1)
        self.assertEqual(record["execution"]["calls"][0]["certainty"], "complete")

    def test_source_configuration_drift_and_late_readback(self):
        opportunity, exported, first = self.run_scenario("context")
        late = self.experiment.readback(opportunity, utc(self.now + timedelta(seconds=150)))
        self.assertFalse(late["usable_for_hypothetical_selection"])
        self.experiment.config["disclosure_revision"] = "changed"
        stale = self.experiment.run(opportunity)
        self.assertEqual(stale["source"], "stale")
        self.assertFalse(stale["usable_for_hypothetical_selection"])
        item = json.loads(exported["request"])["source_refs"]["item_id"]
        response = handle("schedule.update", dict(
            contract_version="spine.schedule-update.v2", command_id="synthetic-drift", actor_subject_id="owner", item_id=item,
            target_version="1", updated_at_utc=utc(self.now), patch={"item": {"title": "Changed synthetic lesson"}},
            materialization={"mode": "none"}), CommandContext(ledger=self.db))
        self.assertTrue(response["ok"], response)
        stale = self.experiment.run(opportunity)
        self.assertFalse(stale["usable_for_hypothetical_selection"])
        self.assertEqual(stale["execution"]["calls"], first["execution"]["calls"])
        self.assertEqual(self.export()[1]["request"], exported["request"])

    def test_changed_provider_configuration_keeps_original_readback_bindings(self):
        opportunity, exported, original = self.run_scenario("context")
        config = json.loads(self.config_text)
        config["max_output_tokens"] = 256
        current = dict(self.config, provider_configuration_json=json.dumps(config))
        self.experiment = self.make_experiment(config=current, launcher=self.launcher(enabled=False))
        record = self.experiment.run(opportunity)
        self.assertEqual(record["execution"], original["execution"])
        self.assertEqual(record["binding"], exported["binding"])
        self.assertEqual(record["source"], "stale")
        self.assertFalse(record["usable_for_hypothetical_selection"])

    def test_invalid_late_observation_references_and_times_are_unusable(self):
        opportunity, exported = self.export()
        launcher = self.launcher("late")
        launcher.prepare(exported["binding"])
        self.store.mark_launched(opportunity)
        response = launcher.exchange("invoke", exported["request"])
        for reference in (0, 1, 3, True):
            with self.subTest(reference=reference):
                changed = copy.deepcopy(response)
                changed["execution"]["observations"][0]["call_ordinal"] = reference
                self.assertEqual(self.experiment.capture(opportunity, changed, utc(self.observed), "invoke")["reason"],
                                 "invalid_response")
        changed = copy.deepcopy(response)
        changed["execution"]["observations"][0]["observed_at_utc"] = "2060-01-01T09:00:00Z"
        self.assertEqual(self.experiment.capture(opportunity, changed, utc(self.observed), "invoke")["reason"], "invalid_response")

    def test_prelaunch_drift_and_explicit_enablement_fail_before_marker(self):
        opportunity, _ = self.export()
        self.experiment = self.make_experiment(launcher=self.launcher(enabled=False))
        with self.assertRaisesRegex(ValueError, "not_enabled"):
            self.experiment.run(opportunity, utc(self.now))
        self.assertFalse(self.store.get(opportunity)["launched"])
        self.experiment = self.make_experiment()
        self.config_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, "configuration_drift"):
            self.experiment.run(opportunity, utc(self.now))
        self.assertFalse(self.store.get(opportunity)["launched"])
        self.experiment.config["opted_in_item_ids"] = []
        self.assertEqual(self.experiment.run(opportunity, utc(self.now))["exchange"], "not_invoked")

    def test_fresh_format_two_and_immutable_records_preserve_format_one(self):
        with self.assertRaises(FileExistsError):
            initialize(self.folder, self.now, self.config_text)
        old_path = self.root / "format-one"
        CaptureStore.initialize(old_path, self.source.namespace)
        with self.assertRaisesRegex(ValueError, "live_capture_format"):
            LiveCaptureStore(old_path, self.source.namespace)
        with self.assertRaisesRegex(ValueError, "capture_format"):
            CaptureStore(self.folder / "capture.sqlite3", self.source.namespace)
        with self.assertRaises(ValueError):
            LiveCaptureStore(self.folder / "capture.sqlite3", "different-ledger")
        with self.assertRaisesRegex(ValueError, "capture_namespace"):
            LiveExperiment(SimpleNamespace(namespace="different-ledger"), self.store, self.launcher(), self.config)
        opportunity, exported = self.export()
        self.store.mark_launched(opportunity)
        for statement in ("UPDATE exports SET binding='{}'", "UPDATE exports SET launched=0", "DELETE FROM exports"):
            with self.assertRaises(sqlite3.IntegrityError), self.store.conn:
                self.store.conn.execute(statement)
        self.assertEqual(self.store.get(opportunity)["request"], exported["request"])
