from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
    build_openclaw_outbound_message,
    build_openclaw_side_effect_request,
)
from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core.hashing import side_effect_request_hash, side_effect_request_payload_hash
from spine.ledger import (
    connect,
    create_started_attempt,
    get_notification_rendering,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
)
from spine.runtime.canonical_seed import seed_canonical_notification_work
from spine.services import retry_work, start_work, succeed_work
from spine.services.attempts import prepare_work_attempt
from tests.canonical_helpers import seed_notification_work
from tests.openclaw_helpers import IdempotentGatewayRunner

NOW = "2026-08-01T00:00:00Z"
ELIGIBLE = "2026-08-01T01:00:00Z"
SUBJECT_ID = "subject-openclaw"


@dataclass(frozen=True)
class FakeEnvelope:
    trace_id: str = "trace-openclaw"
    cycle_id: str = "cycle-openclaw"
    causation_id: str = "ROOT:cycle-openclaw"
    actual_start_ts: datetime = datetime(2026, 8, 1, 1, 0, tzinfo=UTC)


class OpenClawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.seeded = seed_notification_work(
            self.connection,
            prefix="openclaw",
            subject_id=SUBJECT_ID,
            now_utc=NOW,
            eligible_at_utc=ELIGIBLE,
            title="Submit forms",
        )
        self.work_id = str(self.seeded["work_instance_id"])
        start_work(self.connection, work_instance_id=self.work_id, started_at_utc=ELIGIBLE)

    def tearDown(self) -> None:
        self.connection.close()

    def test_timeout_retry_records_two_attempts_but_one_provider_delivery(self) -> None:
        gateway = IdempotentGatewayRunner(timeout_after_first_delivery=True)
        sent = []

        def sender(message):
            # Every transport invocation must already have matching durable evidence.
            attempt = get_side_effect_attempt(self.connection, message.attempt_id)
            rendering = get_notification_rendering(self.connection, attempt_id=message.attempt_id)
            self.assertEqual(attempt["attempt_status"], "started")
            self.assertEqual(rendering["body_text"], message.body_text)
            sent.append(message)
            return OpenClawGatewaySender(OpenClawGatewayConfig(), command_runner=gateway)(message)

        first = self._process(sender)
        self.assertEqual(first.status, "retry")
        self.assertEqual(first.reason_code, "openclaw_gateway_cli_timeout")
        self.assertEqual(first.next_attempt_at_utc, "2026-08-01T01:05:00Z")
        retry_work(self.connection, work_instance_id=self.work_id, next_attempt_at_utc=first.next_attempt_at_utc,
                   updated_at_utc=ELIGIBLE, reason_code=first.reason_code)

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "retry.sqlite"
            disk = connect(ledger)
            self.connection.backup(disk)
            disk.close()
            self.connection.close()
            self.connection = connect(ledger)
            start_work(self.connection, work_instance_id=self.work_id, started_at_utc=first.next_attempt_at_utc)
            work = get_work_instance(self.connection, self.work_id)
            envelope = FakeEnvelope(actual_start_ts=datetime(2026, 8, 1, 1, 5, tzinfo=UTC))

            # A fresh process rebuilds the identical request from durable work alone.
            script = """
import json, sys
from spine.adapters import build_openclaw_outbound_message
from spine.ledger import connect, get_work_instance
db = connect(sys.argv[1])
message = build_openclaw_outbound_message(db, work_row=get_work_instance(db, sys.argv[2]),
    trace_id="trace-openclaw", causation_id="ROOT:cycle-openclaw", created_at_utc="2026-08-01T01:05:00Z")
print(json.dumps(message.request_envelope()))
db.close()
"""
            reconstructed = json.loads(subprocess.check_output(
                [sys.executable, "-c", script, str(ledger), self.work_id], text=True,
            ))
            processor = OpenClawNotificationProcessor(sender=sender)
            second = processor(self.connection, work, envelope)
            self.assertEqual(second.status, "succeeded")
            self.assertEqual(sent[1].request_envelope(), reconstructed)
            replay = processor(self.connection, work, envelope)
            self.assertEqual(replay.reason_code, "side_effect_attempt_replay_suppressed")
            self.assertEqual(len(sent), 2)
            attempts = [get_side_effect_attempt(self.connection, m.attempt_id) for m in sent]
            self.assertEqual([a["attempt_status"] for a in attempts], ["failed", "succeeded"])
            self.assertEqual([a["attempt_id"] for a in attempts],
                             [f"openclaw-attempt-{self.work_id}-1", f"openclaw-attempt-{self.work_id}-2"])
            self.assertEqual([a["idempotency_key"] for a in attempts],
                             [f"openclaw:{self.work_id}:1", f"openclaw:{self.work_id}:2"])
            self.assertEqual(attempts[1]["provider_ref"], "wamid.delivery-1")
            for message, attempt in zip(sent, attempts, strict=True):
                payload_hash = side_effect_request_payload_hash(adapter_name="openclaw", request_envelope=message.request_envelope())
                self.assertEqual(attempt["request_payload_hash"], payload_hash)
                self.assertEqual(attempt["request_hash"], side_effect_request_hash(
                    adapter_name="openclaw", idempotency_key=message.dedupe_key,
                    request_payload_hash=payload_hash, work_instance_id=self.work_id,
                ))
                rendering = get_notification_rendering(self.connection, attempt_id=message.attempt_id)
                self.assertEqual(rendering["notification_rendering_id"], message.notification_rendering.notification_rendering_id)
                self.assertEqual(rendering["rendered_content_hash"], message.notification_rendering.rendered_content_hash)
                self.assertEqual(rendering["body_text"], message.body_text)
            self.assertNotEqual(attempts[0]["request_payload_hash"], attempts[1]["request_payload_hash"])
            self.assertNotEqual(sent[0].body_text, sent[1].body_text)
            with self.assertRaisesRegex(SpineValidationError, "UNIQUE constraint failed: side_effect_attempts.adapter_name"):
                create_started_attempt(
                    self.connection, attempt_id="duplicate-ledger-key", adapter_name="openclaw",
                    idempotency_key=sent[0].dedupe_key, work_instance_id=self.work_id,
                    request_envelope=sent[0].request_envelope(), attempted_at_utc=first.next_attempt_at_utc,
                )
            succeed_work(self.connection, work_instance_id=self.work_id,
                         succeeded_at_utc=first.next_attempt_at_utc, reason_code=second.reason_code)
            final = get_work_instance(self.connection, self.work_id)
            self.assertEqual((final["status"], final["attempt_count"]), ("succeeded", 2))
            self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 2)
            self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 2)
            self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.connection.close()

        self.assertEqual([r["idempotencyKey"] for r in gateway.requests], [f"openclaw-delivery:{self.work_id}"] * 2)
        self.assertEqual(len(gateway.visible_deliveries), 1)

    def test_same_target_and_body_on_different_work_have_different_provider_keys(self) -> None:
        first = self._outbound()
        seeded = seed_notification_work(
            self.connection, prefix="another-openclaw", subject_id=SUBJECT_ID,
            delivery_target_id=str(get_work_instance(self.connection, self.work_id)["delivery_target_id"]),
            now_utc=NOW, eligible_at_utc=ELIGIBLE,
            title="Submit forms",
        )
        other_id = str(seeded["work_instance_id"])
        start_work(self.connection, work_instance_id=other_id, started_at_utc=ELIGIBLE)
        second = build_openclaw_outbound_message(
            self.connection, work_row=get_work_instance(self.connection, other_id),
            trace_id="trace-2", causation_id="cause-2", created_at_utc=NOW,
        )
        self.assertEqual((first.target_ref, first.body_text), (second.target_ref, second.body_text))
        self.assertNotEqual(first.provider_idempotency_key, second.provider_idempotency_key)

    def test_pre_upgrade_envelope_replay_cannot_resend_or_rewrite_evidence(self) -> None:
        request = build_openclaw_side_effect_request(
            self.connection, work_row=get_work_instance(self.connection, self.work_id), envelope=FakeEnvelope(),
        )
        historical = dict(request.request_envelope)
        historical["payload_version"] = "spine.openclaw.outbound.v1"
        del historical["provider_idempotency_key"]
        prepare_work_attempt(
            self.connection, attempt_id=request.attempt_id, work_instance_id=request.work_instance_id,
            adapter_name="openclaw", idempotency_key=request.idempotency_key, request_envelope=historical,
            attempted_at_utc=request.attempted_at_utc, notification_rendering=request.notification_rendering,
        )
        before = list(self.connection.iterdump())
        sent = []
        outcome = self._process(lambda message: sent.append(message) or NormalizedOpenClawResult.delivered(provider_ref="wamid.bad"))
        self.assertEqual(outcome.reason_code, "notification_rendering_persistence_conflict")
        self.assertEqual(sent, [])
        self.assertEqual(list(self.connection.iterdump()), before)

    def test_build_outbound_message_from_canonical_work_row(self) -> None:
        outbound = self._outbound()

        self.assertEqual(outbound.delivery_id, self.work_id)
        self.assertEqual(outbound.attempt_id, f"openclaw-attempt-{self.work_id}-1")
        self.assertEqual(outbound.dedupe_key, f"openclaw:{self.work_id}:1")
        self.assertEqual(outbound.provider_idempotency_key, f"openclaw-delivery:{self.work_id}")
        self.assertEqual(outbound.channel_hint, "whatsapp")
        target = self.connection.execute(
            "SELECT target_ref FROM delivery_targets WHERE delivery_target_id = ?",
            (
                self.connection.execute(
                    "SELECT delivery_target_id FROM work_instances WHERE work_instance_id = ?",
                    (self.work_id,),
                ).fetchone()[0],
            ),
        ).fetchone()[0]
        self.assertEqual(outbound.target_ref, target)
        self.assertEqual(outbound.body_text, "Reminder: Submit forms is due in 2 hours")
        self.assertEqual(outbound.request_envelope()["payload_version"], "spine.openclaw.outbound.v2")
        self.assertEqual(outbound.request_envelope()["provider_idempotency_key"], outbound.provider_idempotency_key)
        schema = json.loads((Path(__file__).parents[1] / "contracts/schemas/openclaw-outbound-v2.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(outbound.request_envelope())
        self.assertEqual(
            outbound.request_envelope()["notification_rendering_id"],
            outbound.notification_rendering.notification_rendering_id,
        )
        self.assertEqual(
            outbound.request_envelope()["rendered_content_hash"],
            outbound.notification_rendering.rendered_content_hash,
        )

    def test_group_owned_delivery_target_is_resolved(self) -> None:
        context = CommandContext(ledger=self.connection)
        group = handle(
            "subject_group.upsert",
            {
                "command_id": "cmd-openclaw-group",
                "actor_subject_id": SUBJECT_ID,
                "group_id": "openclaw-group",
                "display_name": "OpenClaw group",
                "updated_at_utc": NOW,
            },
            context,
        )
        self.assertTrue(group["ok"], group)
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": "cmd-openclaw-group-route",
                "actor_subject_id": SUBJECT_ID,
                "delivery_target_id": "openclaw-group-target",
                "owner_kind": "subject_group",
                "owner_group_id": "openclaw-group",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "120363409469948475@g.us",
                "updated_at_utc": NOW,
            },
            context,
        )
        self.assertTrue(route["ok"], route)
        seeded = seed_canonical_notification_work(
            self.connection,
            prefix="openclaw-group",
            actor_subject_id=SUBJECT_ID,
            title="Routed reminder",
            delivery_target_id="openclaw-group-target",
            channel="whatsapp",
            recipient_kind="subject_group",
            recipient_id="openclaw-group",
            now_utc=NOW,
            eligible_at_utc=ELIGIBLE,
        )
        work_id = str(seeded["work_instance_id"])
        start_work(self.connection, work_instance_id=work_id, started_at_utc=ELIGIBLE)
        outbound = build_openclaw_outbound_message(
            self.connection,
            work_row=get_work_instance(self.connection, work_id),
            trace_id="trace-1",
            causation_id="cause-1",
            created_at_utc=NOW,
        )

        self.assertEqual(outbound.target_ref, "120363409469948475@g.us")
        self.assertEqual(outbound.body_text, "Reminder: Routed reminder is due in 2 hours")

    def test_success_result_records_attempt_and_returns_success_outcome(self) -> None:
        captured = []

        def sender(outbound):
            captured.append(outbound)
            return NormalizedOpenClawResult.delivered(provider_ref="wamid.demo")

        outcome = self._process(sender)
        attempt = self._attempt()
        self.assertEqual(outcome.status, "succeeded")
        self.assertEqual(attempt["attempt_status"], "succeeded")
        self.assertEqual(attempt["adapter_name"], "openclaw")
        self.assertEqual(attempt["provider_ref"], "wamid.demo")
        self.assertEqual(attempt["reason_code"], "openclaw_delivered")
        self.assertEqual(captured[0].body_text, "Reminder: Submit forms is due in 1 hour")
        rendering = get_notification_rendering(self.connection, attempt_id=str(attempt["attempt_id"]))
        self.assertIsNotNone(rendering)
        assert rendering is not None
        self.assertEqual(rendering["body_text"], captured[0].body_text)
        self.assertEqual(rendering["rendered_item_version"], "2")
        self.assertEqual(
            attempt["request_payload_hash"],
            side_effect_request_payload_hash(
                adapter_name="openclaw",
                request_envelope=captured[0].request_envelope(),
            ),
        )

    def test_rendering_uses_current_title_without_reidentifying_retained_work(self) -> None:
        current_version = self.connection.execute(
            "SELECT current_version FROM coordination_items WHERE item_id = ?",
            (self.seeded["item_id"],),
        ).fetchone()[0]
        updated = handle(
            "task.update",
            {
                "command_id": "cmd-openclaw-current-title",
                "actor_subject_id": SUBJECT_ID,
                "item_id": self.seeded["item_id"],
                "target_version": str(current_version),
                "updated_at_utc": "2026-08-01T00:30:00Z",
                "patch": {"title": "Submit final forms"},
            },
            CommandContext(ledger=self.connection),
        )
        self.assertTrue(updated["ok"], updated)

        captured = []
        outcome = self._process(
            lambda outbound: captured.append(outbound) or NormalizedOpenClawResult.delivered(provider_ref="wamid.current-title")
        )

        self.assertEqual(outcome.status, "succeeded")
        self.assertEqual(captured[0].body_text, "Reminder: Submit final forms is due in 1 hour")
        rendering = get_notification_rendering(self.connection, attempt_id=self._attempt()["attempt_id"])
        self.assertEqual(rendering["rendered_item_version"], updated["version"])

    def test_rendering_and_attempt_start_are_atomic(self) -> None:
        request = build_openclaw_side_effect_request(
            self.connection,
            work_row=get_work_instance(self.connection, self.work_id),
            envelope=FakeEnvelope(),
        )
        with (
            patch(
                "spine.services.attempts.insert_notification_rendering",
                side_effect=SpineValidationError(
                    "notification_rendering_persistence_conflict",
                    "forced persistence failure",
                ),
            ),
            self.assertRaisesRegex(
                SpineValidationError,
                "notification_rendering_persistence_conflict",
            ),
        ):
            prepare_work_attempt(
                self.connection,
                attempt_id=request.attempt_id,
                work_instance_id=request.work_instance_id,
                adapter_name="openclaw",
                idempotency_key=request.idempotency_key,
                request_envelope=request.request_envelope,
                attempted_at_utc=request.attempted_at_utc,
                notification_rendering=request.notification_rendering,
            )

        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 0)

    def test_compatible_attempt_replay_reuses_rendering_and_suppresses_transport(self) -> None:
        request = build_openclaw_side_effect_request(
            self.connection,
            work_row=get_work_instance(self.connection, self.work_id),
            envelope=FakeEnvelope(),
        )
        arguments = {
            "attempt_id": request.attempt_id,
            "work_instance_id": request.work_instance_id,
            "adapter_name": "openclaw",
            "idempotency_key": request.idempotency_key,
            "request_envelope": request.request_envelope,
            "attempted_at_utc": request.attempted_at_utc,
            "notification_rendering": request.notification_rendering,
        }
        first = prepare_work_attempt(self.connection, **arguments)
        replay = prepare_work_attempt(self.connection, **arguments)

        self.assertTrue(first.may_start_external_write)
        self.assertFalse(replay.may_start_external_write)
        self.assertEqual(first.attempt, replay.attempt)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 1)

    def test_transient_result_records_failed_attempt_and_retry_outcome(self) -> None:
        outcome = self._process(
            lambda _outbound: NormalizedOpenClawResult.transient_failure(
                reason_code="openclaw_provider_transient",
                next_attempt_at_utc="2026-08-01T01:30:00Z",
            )
        )
        self.assertEqual(outcome.status, "retry")
        self.assertEqual(outcome.next_attempt_at_utc, "2026-08-01T01:30:00Z")
        self.assertEqual(self._attempt()["attempt_status"], "failed")

    def test_permanent_result_records_failed_attempt(self) -> None:
        outcome = self._process(lambda _outbound: NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_provider_permanent"))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(self._attempt()["reason_code"], "openclaw_provider_permanent")

    def test_binding_failure_records_rejected_attempt(self) -> None:
        def sender(_outbound):
            raise OpenClawBindingError("openclaw unavailable")

        outcome = self._process(sender)
        self.assertEqual(outcome.reason_code, "openclaw_binding_failed")
        self.assertEqual(self._attempt()["attempt_status"], "rejected")

    def test_sender_exception_records_failed_attempt(self) -> None:
        def sender(_outbound):
            raise RuntimeError("provider exploded")

        outcome = self._process(sender)
        self.assertEqual(outcome.reason_code, "openclaw_send_exception")
        self.assertEqual(self._attempt()["attempt_status"], "failed")

    def test_malformed_transient_result_closes_attempt_as_failed(self) -> None:
        outcome = self._process(
            lambda _outbound: NormalizedOpenClawResult(status="failed_transient", reason_code="openclaw_provider_transient")
        )
        self.assertEqual(outcome.reason_code, "openclaw_missing_retry_at")
        self.assertEqual(self._attempt()["attempt_status"], "failed")

    def _outbound(self):
        return build_openclaw_outbound_message(
            self.connection,
            work_row=get_work_instance(self.connection, self.work_id),
            trace_id="trace-1",
            causation_id="cause-1",
            created_at_utc=NOW,
        )

    def _process(self, sender):
        return OpenClawNotificationProcessor(sender=sender)(
            self.connection, get_work_instance(self.connection, self.work_id), FakeEnvelope()
        )

    def _attempt(self):
        return get_side_effect_attempt(self.connection, f"openclaw-attempt-{self.work_id}-1")


if __name__ == "__main__":
    unittest.main()
