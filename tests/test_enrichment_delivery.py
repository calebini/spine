"""Opted-in existing-source research through independent mocked worker to fake delivery."""

import hashlib
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
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine.adapters.contextual_experiment import Source, digest
from spine.adapters.contextual_live import LiveCaptureStore, LiveLauncher
from spine.adapters.enrichment import EnrichmentStore, open_source
from spine.adapters.openclaw import (
    NormalizedOpenClawResult,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
)
from spine.commands import CommandContext, handle
from spine.ledger import get_notification_rendering, get_work_instance
from spine.runtime.contextual_experiment_demo import seed
from spine.services.contextual_experiment import utc
from spine.services.enrichment import SCHEMA, EnrichmentExperiment
from spine.services.work import retry_work, start_work
from spine.web.provisioning import apply, plan
from tests.openclaw_helpers import IdempotentGatewayRunner

ROOT = Path(__file__).parents[1]
OWNER = Path(os.environ.get("IMPETUS_SRC", ROOT.parent / "impetus/src"))
FIXTURE = Path(__file__).parent / "fixtures/contextual_live_worker.py"


@unittest.skipUnless((OWNER / "impetus").is_dir(), "Independent Impetus checkout required")
class EnrichmentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime(2060, 1, 1, 10, tzinfo=UTC)
        self.observed = self.now + timedelta(seconds=5)
        self.db, self.work, config = seed(self.root / "source.sqlite3", self.now)
        self.item = config["opted_in_item_ids"][0]
        self.adopt()
        self.source = open_source(self.root / "source.sqlite3")
        self.provider = files("spine.contracts").joinpath("contextual_notification/live-configuration.json").read_text()
        self.provider_path = self.root / "provider.json"
        self.provider_path.write_text(self.provider)
        config.update(contract="spine.notification-enrichment-config.v1", synthetic_only=False,
                      work_instance_id=self.work, actor_subject_id="owner", retention_reference="fake-private-test-policy",
                      approved_context_sha256="0" * 64, provider_configuration_json=self.provider)
        config["approved_context_sha256"] = digest(self.source.preview(self.work, config)["context"])
        self.config = config
        self.store_path = self.root / "capture.sqlite3"
        EnrichmentStore.initialize(self.store_path, self.source.namespace)
        self.store = EnrichmentStore(self.store_path, self.source.namespace)
        self.env = {k: v for k, v in os.environ.items() if k not in {
            "IMPETUS_OPENAI_API_KEY", "IMPETUS_OPENAI_API_KEY_FILE", "OPENAI_API_KEY"
        }}
        self.env["PYTHONPATH"] = str(OWNER)
        self.state = self.root / "worker"
        subprocess.run([*self.command(), "init", "--namespace", self.source.namespace], env=self.env,
                       check=True, capture_output=True)
        self.experiment = self.experiment_for()
        self.sent = []

    def tearDown(self):
        self.source.ledger.close()
        self.store.close()
        self.db.close()
        self.tmp.cleanup()

    def adopt(self):
        state = self.db.execute("SELECT access_epoch FROM ledger_access_state WHERE singleton_id=1").fetchone()
        epoch = str(state[0]) if state else "0"
        proposed = plan(self.db, dict(
            contract_version="spine.trusted-web-provisioning.v1", ledger_id="enrichment-tests", expected_access_epoch=epoch,
            item_adoptions=[dict(operation="create", item_id=self.item, owner_scope={"owner_kind": "subject", "owner_subject_id": "owner"},
                                 expected_item_version="1")]))
        self.assertTrue(proposed["can_apply"], proposed)
        apply(self.db, dict(contract_version="spine.trusted-web-provisioning.v1", command_id="enrichment-adopt",
                            actor_subject_id="owner", action_timestamp_utc=utc(self.now), expected_access_epoch=epoch, plan=proposed))

    def command(self, scenario="context"):
        return [sys.executable, str(FIXTURE), "--state", str(self.state), "--now", utc(self.now), "--scenario", scenario]

    def experiment_for(self, scenario="context", enabled=True):
        launcher = LiveLauncher(self.command(scenario), provider_configuration_path=self.provider_path,
                                enabled=True, environment=self.env)
        return EnrichmentExperiment(self.source, self.store, launcher, self.config,
                                    clock=lambda: self.observed, enabled=enabled)

    def research(self, scenario="context"):
        self.experiment = self.experiment_for(scenario)
        before = list(self.db.iterdump())
        opportunity, exported = self.experiment.export(self.work, utc(self.now))
        self.assertEqual(json.loads(exported["request"])["context"], self.source.preview(self.work, self.config)["context"])
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 0)
        return opportunity, exported, record

    def sender(self, message):
        attempt = self.db.execute("SELECT * FROM side_effect_attempts WHERE attempt_id=?", (message.attempt_id,)).fetchone()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt["attempt_status"], "started")
        ordinary = get_notification_rendering(self.db, attempt_id=message.attempt_id)
        self.assertIsNotNone(ordinary)
        self.sent.append(message)
        return NormalizedOpenClawResult.delivered(provider_ref="fake-message-one")

    def deliver(self, *, advance=0, sender=None, start=True):
        at = self.now + timedelta(seconds=120 + advance)
        if start:
            start_work(self.db, work_instance_id=self.work, started_at_utc=utc(at))
        envelope = SimpleNamespace(actual_start_ts=at, trace_id="fake-enrichment", causation_id="ROOT:fake")
        processor = OpenClawNotificationProcessor(sender or self.sender, enrichment=self.experiment)
        return processor(self.db, get_work_instance(self.db, self.work), envelope)

    def test_addendum_to_one_attempt_and_duplicate_attempt_is_not_sent(self):
        opportunity, exported, capture = self.research()
        self.assertTrue(capture["usable_for_hypothetical_selection"], capture)
        self.assertFalse(capture["selected"] or capture["sent"])
        self.assertEqual(self.deliver().status, "succeeded")
        message = self.sent[0]
        self.assertTrue(message.body_text.endswith("\n\nHope it goes well!"))
        outbound = message.request_envelope()
        Draft202012Validator(SCHEMA["$defs"]["outbound"]).validate(outbound)
        self.assertEqual(outbound["payload_version"], "spine.openclaw.outbound.v3")
        self.assertEqual(outbound["enriched_content_sha256"], hashlib.sha256(message.body_text.encode()).hexdigest())
        self.assertNotEqual(message.body_text, message.notification_rendering.body_text)
        self.assertEqual(self.store.receipt(message.attempt_id)[0], outbound)
        evidence = self.experiment.delivery_evidence(self.db, message.attempt_id)
        self.assertEqual(evidence["envelope"]["body_text"], message.body_text)
        self.assertEqual(evidence["attempt_status"], "succeeded")
        self.deliver(start=False)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.store.get(opportunity)["request"], exported["request"])

    def test_no_addition_uses_identical_ordinary_pipeline(self):
        self.research("no-addition")
        self.assertEqual(self.deliver().status, "succeeded")
        message = self.sent[0]
        self.assertEqual(message.body_text, message.notification_rendering.body_text)
        self.assertEqual(message.request_envelope()["payload_version"], "spine.openclaw.outbound.v2")
        self.assertEqual(self.store.choice(self.work)[0]["kind"], "ordinary")

    def test_count_failure_falls_back_without_generation(self):
        _, _, record = self.research("count-failure")
        self.assertEqual(len(record["execution"]["calls"]), 1)
        self.assertEqual(self.deliver().status, "succeeded")
        self.assertEqual(self.sent[0].body_text, self.sent[0].notification_rendering.body_text)

    def test_late_generation_falls_back(self):
        _, _, record = self.research("late")
        self.assertEqual(record["execution"]["observations"][0]["call_ordinal"], 2)
        self.assertEqual(self.deliver().status, "succeeded")
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")

    def test_first_observation_after_cutoff_cannot_enable_enrichment(self):
        self.observed = self.now + timedelta(seconds=121)
        _, _, record = self.research()
        self.assertFalse(record["usable_for_hypothetical_selection"])
        self.deliver()
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")

    def test_committed_ordinary_choice_blocks_research_and_late_upgrade(self):
        opportunity, _ = self.experiment.export(self.work, utc(self.now))
        rendering_body = "Ordinary reminder"
        self.assertIsNone(self.experiment.content_choice(self.db, self.work, rendering_body))
        record = self.experiment.run(opportunity, utc(self.now))
        self.assertIsNone(record["execution"])
        self.assertFalse(self.store.get(opportunity)["launched"])
        self.deliver()
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")

    def test_consent_drift_falls_back_and_cannot_upgrade_after_restore(self):
        self.research()
        self.experiment.config["disclosure_revision"] = "revoked"
        self.deliver()
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")
        self.experiment.config["disclosure_revision"] = self.config["disclosure_revision"]
        self.assertIsNone(self.experiment.content_choice(self.db, self.work, "Ordinary"))

    def test_consent_race_at_attempt_gate_sends_ordinary_only(self):
        self.research()
        check = self.experiment.check_choice
        def revoked(db, work, choice):
            self.experiment.config["disclosure_revision"] = "revoked-at-gate"
            return check(db, work, choice)
        with patch.object(self.experiment, "check_choice", revoked):
            self.assertEqual(self.deliver().status, "succeeded")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 1)
        self.assertIsNone(self.experiment.delivery_evidence(self.db, self.sent[0].attempt_id))

    def test_missing_private_store_never_blocks_ordinary_delivery(self):
        self.research()
        self.store.close()
        self.assertEqual(self.deliver().status, "succeeded")
        self.assertEqual(self.sent[0].body_text, self.sent[0].notification_rendering.body_text)

    def test_lost_response_restart_reads_without_config_and_delivers_retained_result(self):
        real = self.experiment.client
        class Lost:
            prepare = real.prepare
            def exchange(self, operation, raw):
                value = real.exchange(operation, raw)
                return None if operation == "invoke" else value
        self.experiment.client = Lost()
        opportunity, exported = self.experiment.export(self.work, utc(self.now))
        self.assertEqual(self.experiment.run(opportunity, utc(self.now))["reason"], "unresolved")
        self.store.close()
        self.store = EnrichmentStore(self.store_path, self.source.namespace)
        self.provider_path.unlink()
        reader = LiveLauncher(self.command(), enabled=False, environment=dict(self.env, IMPETUS_OPENAI_API_KEY="fake-forbidden"))
        read_config = dict(self.config)
        read_config.pop("provider_configuration_json")
        self.experiment = EnrichmentExperiment(self.source, self.store, reader, read_config,
                                              clock=lambda: self.observed)
        found = self.experiment.run(opportunity)
        self.assertEqual(found["exchange"], "read")
        self.assertEqual(found["reason"], "succeeded", found)
        self.assertEqual(len(found["execution"]["calls"]), 2)
        self.assertFalse(found["usable_for_hypothetical_selection"])
        self.experiment = EnrichmentExperiment(self.source, self.store, reader, self.config,
                                              clock=lambda: self.observed, enabled=True)
        found = self.experiment.run(opportunity)
        self.assertEqual(found["exchange"], "read")
        self.assertTrue(found["usable_for_hypothetical_selection"])
        self.deliver()
        self.assertTrue(self.sent[0].body_text.endswith("Hope it goes well!"))
        self.assertEqual(self.store.get(opportunity)["request"], exported["request"])

    def test_late_response_after_ordinary_attempt_cannot_create_another_message(self):
        opportunity, exported = self.experiment.export(self.work, utc(self.now))
        self.experiment.client.prepare(exported["binding"])
        self.assertTrue(self.store.mark_launched(opportunity))
        response = self.experiment.client.exchange("invoke", exported["request"])
        self.deliver()
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")
        late = self.experiment.capture(opportunity, response, utc(self.now + timedelta(seconds=121)), "invoke")
        self.assertFalse(late["usable_for_hypothetical_selection"])
        self.deliver(start=False)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.store.choice(self.work)[0]["kind"], "ordinary")

    def test_delivery_retry_keeps_logical_key_without_research_or_duplicate_delivery(self):
        opportunity, _, original = self.research()
        runner = IdempotentGatewayRunner(timeout_after_first_delivery=True)
        sender = OpenClawGatewaySender(OpenClawGatewayConfig(command="fake-gateway", retry_delay_seconds=10), command_runner=runner)
        self.assertEqual(self.deliver(sender=sender).status, "retry")
        retry_work(self.db, work_instance_id=self.work, next_attempt_at_utc=utc(self.now + timedelta(seconds=130)),
                   updated_at_utc=utc(self.now + timedelta(seconds=120)), reason_code="fake-retry")
        self.assertEqual(self.deliver(advance=10, sender=sender).status, "succeeded")
        self.assertEqual(len(runner.requests), 2)
        self.assertEqual(len(runner.visible_deliveries), 1)
        self.assertEqual(runner.requests[0]["idempotencyKey"], runner.requests[1]["idempotencyKey"])
        self.assertTrue(all(r["message"].endswith("Hope it goes well!") for r in runner.requests))
        self.assertEqual(self.store.get(opportunity)["launched"], True)
        self.assertEqual(len(original["execution"]["calls"]), 2)

    def test_export_excludes_private_fields_and_oversize_composition_falls_back(self):
        _, exported, _ = self.research()
        text = exported["request"].decode()
        self.assertNotIn("Do not disclose this summary", text)
        self.assertNotIn("synthetic@example.invalid", text)
        self.assertIsNone(self.experiment.content_choice(self.db, self.work, "X" * 1024))
        self.assertEqual(self.store.choice(self.work)[0]["reason"], "composition_rejected")
        self.deliver()
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")

    def test_source_edit_uses_updated_ordinary_content_without_old_addendum(self):
        self.research()
        result = handle("schedule.update", dict(contract_version="spine.schedule-update.v2", command_id="enrichment-edit",
                        actor_subject_id="owner", item_id=self.item, target_version="1", updated_at_utc=utc(self.now),
                        patch={"item": {"title": "Changed lesson"}}, materialization={"mode": "none"}),
                        CommandContext(ledger=self.db))
        self.assertTrue(result["ok"], result)
        self.deliver()
        self.assertIn("Changed lesson", self.sent[0].body_text)
        self.assertNotIn("Hope it goes well!", self.sent[0].body_text)

    def test_private_receipt_failure_at_gate_still_sends_ordinary(self):
        self.research()
        receipt = self.store.receipt
        calls = []
        def unavailable(attempt):
            calls.append(attempt)
            if len(calls) > 1:
                raise sqlite3.OperationalError("fake private evidence loss")
            return receipt(attempt)
        with patch.object(self.store, "receipt", unavailable):
            self.assertEqual(self.deliver().status, "succeeded")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0].request_envelope()["payload_version"], "spine.openclaw.outbound.v2")

    def test_disabled_by_default_and_invalid_actor_or_disclosure_cannot_export(self):
        experiment = self.experiment_for(enabled=False)
        opportunity, _ = experiment.export(self.work, utc(self.now))
        self.assertIsNone(experiment.run(opportunity, utc(self.now))["execution"])
        self.assertFalse(self.store.get(opportunity)["launched"])
        bad = dict(self.config, actor_subject_id="other")
        with self.assertRaisesRegex(ValueError, "owner"):
            self.source.snapshot(self.work, bad)
        with self.assertRaisesRegex(ValueError, "disclosure_drift"):
            self.source.snapshot(self.work, dict(self.config, approved_context_sha256="0" * 64))
        with self.assertRaises(ValueError):
            Source(self.db).snapshot(self.work, self.config)

    def test_closed_shapes_profile_separation_readonly_source_and_immutability(self):
        self.assertRaises(sqlite3.OperationalError, self.source.ledger.execute, "UPDATE subjects SET display_name='forbidden'")
        with self.assertRaises(sqlite3.OperationalError):
            open_source(self.root / "missing.sqlite3")
        self.assertFalse((self.root / "missing.sqlite3").exists())
        synthetic = self.root / "synthetic.sqlite3"
        LiveCaptureStore.initialize(synthetic, self.source.namespace)
        with self.assertRaises(sqlite3.OperationalError):
            EnrichmentStore(synthetic, self.source.namespace)
        self.research()
        self.deliver()
        for statement in ("DELETE FROM enrichment_choices", "UPDATE enrichment_choices SET record='{}'", "DELETE FROM enrichment_receipts"):
            with self.assertRaises(sqlite3.IntegrityError), self.store.conn:
                self.store.conn.execute(statement)


class EnrichmentContractTests(unittest.TestCase):
    def test_exact_schema_resource_and_pins(self):
        folder = ROOT / "contracts/contextual_notification"
        for name in ("enrichment-v1.schema.json", "enrichment-pins.v1.json", "enrichment-choice.json", "enrichment-outbound.json"):
            self.assertEqual((folder / name).read_bytes(),
                             files("spine.contracts").joinpath("contextual_notification/" + name).read_bytes())
        pins = json.loads((folder / "enrichment-pins.v1.json").read_bytes())
        self.assertEqual(hashlib.sha256((folder / "enrichment-v1.schema.json").read_bytes()).hexdigest(), pins["schema_sha256"])
        for name, expected in pins["files"].items():
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), expected)
        for kind, name in (("choice", "enrichment-choice.json"), ("outbound", "enrichment-outbound.json")):
            value = json.loads((folder / name).read_bytes())
            Draft202012Validator(SCHEMA["$defs"][kind]).validate(value)
            value["unapproved"] = True
            self.assertFalse(Draft202012Validator(SCHEMA["$defs"][kind]).is_valid(value))
        Draft202012Validator.check_schema(SCHEMA)
