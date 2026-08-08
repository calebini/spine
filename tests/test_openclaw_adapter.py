from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawNotificationProcessor,
    build_openclaw_outbound_message,
)
from spine.commands import CommandContext, handle
from spine.ledger import connect, get_side_effect_attempt, get_work_instance, initialize_schema
from spine.runtime.canonical_seed import seed_canonical_notification_work
from spine.services import start_work
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
            (self.connection.execute(
                "SELECT delivery_target_id FROM work_instances WHERE work_instance_id = ?",
                (self.work_id,),
            ).fetchone()[0],),
        ).fetchone()[0]
        self.assertEqual(outbound.target_ref, target)
        self.assertEqual(outbound.body_text, "Reminder: Submit forms")
        self.assertEqual(outbound.request_envelope()["payload_version"], "spine.openclaw.outbound.v1")

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
        self.assertEqual(outbound.body_text, "Reminder: Routed reminder")

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
        self.assertEqual(captured[0].body_text, "Reminder: Submit forms")

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
        outcome = self._process(
            lambda _outbound: NormalizedOpenClawResult.permanent_failure(
                reason_code="openclaw_provider_permanent"
            )
        )
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
            lambda _outbound: NormalizedOpenClawResult(
                status="failed_transient", reason_code="openclaw_provider_transient"
            )
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
        return get_side_effect_attempt(
            self.connection, f"openclaw-attempt-{self.work_id}-1"
        )


if __name__ == "__main__":
    unittest.main()
