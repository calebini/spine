from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import patch

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawNotificationProcessor,
    build_openclaw_outbound_message,
    build_openclaw_side_effect_request,
)
from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core.hashing import side_effect_request_payload_hash
from spine.ledger import (
    connect,
    get_notification_rendering,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
)
from spine.runtime.canonical_seed import seed_canonical_notification_work
from spine.services import start_work
from spine.services.attempts import prepare_work_attempt
from tests.canonical_helpers import seed_notification_work

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

    def test_build_outbound_message_from_canonical_work_row(self) -> None:
        outbound = self._outbound()

        self.assertEqual(outbound.delivery_id, self.work_id)
        self.assertEqual(outbound.attempt_id, f"openclaw-attempt-{self.work_id}-1")
        self.assertEqual(outbound.dedupe_key, f"openclaw:{self.work_id}:1")
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
        self.assertEqual(outbound.request_envelope()["payload_version"], "spine.openclaw.outbound.v1")
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
                "group_kind": "transport_group",
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
