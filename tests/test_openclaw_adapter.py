import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawNotificationProcessor,
    build_openclaw_outbound_message,
)
from spine.ledger import (
    DeliveryTargetInput,
    NotificationPolicyInput,
    SubjectGroupInput,
    TemporalAnchorInput,
    connect,
    create_task_v1,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
    insert_delivery_target,
    insert_subject_group,
)
from spine.services import generate_notification_reminder_work, start_work


NOW = "2026-06-07T10:00:00Z"
SUBJECT_ID = "subject-1"


@dataclass(frozen=True)
class FakeEnvelope:
    trace_id: str = "trace-openclaw"
    cycle_id: str = "cycle-openclaw"
    causation_id: str = "ROOT:cycle-openclaw"
    actual_start_ts: datetime = datetime(2026, 6, 7, 10, 0, tzinfo=UTC)


class OpenClawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="openclaw-work",
            notification_policy_id="openclaw-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )
        start_work(
            self.connection,
            work_instance_id="openclaw-work",
            started_at_utc="2026-06-07T10:00:00Z",
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_build_outbound_message_from_work_row(self) -> None:
        work = get_work_instance(self.connection, "openclaw-work")

        outbound = build_openclaw_outbound_message(
            self.connection,
            work_row=work,
            trace_id="trace-1",
            causation_id="cause-1",
            created_at_utc=NOW,
        )

        self.assertEqual(outbound.delivery_id, "openclaw-work")
        self.assertEqual(outbound.attempt_id, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outbound.dedupe_key, "openclaw:openclaw-work:1")
        self.assertEqual(outbound.channel_hint, "whatsapp")
        self.assertEqual(outbound.target_ref, SUBJECT_ID)
        self.assertEqual(outbound.body_text, "Reminder: Submit forms")
        self.assertEqual(outbound.request_envelope()["payload_version"], "spine.openclaw.outbound.v1")

    def test_build_outbound_message_resolves_delivery_target_ref(self) -> None:
        create_routed_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="openclaw-routed-work",
            notification_policy_id="openclaw-routed-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )
        start_work(
            self.connection,
            work_instance_id="openclaw-routed-work",
            started_at_utc="2026-06-07T10:00:00Z",
        )

        outbound = build_openclaw_outbound_message(
            self.connection,
            work_row=get_work_instance(self.connection, "openclaw-routed-work"),
            trace_id="trace-1",
            causation_id="cause-1",
            created_at_utc=NOW,
        )

        self.assertEqual(outbound.target_ref, "120363409469948475@g.us")
        self.assertEqual(outbound.channel_hint, "whatsapp")
        self.assertEqual(outbound.body_text, "Reminder: Routed reminder")

    def test_success_result_records_attempt_and_returns_success_outcome(self) -> None:
        captured = []

        def sender(outbound):
            captured.append(outbound)
            return NormalizedOpenClawResult.delivered(provider_ref="wamid.demo")

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "succeeded")
        self.assertEqual(attempt["attempt_status"], "succeeded")
        self.assertEqual(attempt["adapter_name"], "openclaw")
        self.assertEqual(attempt["provider_ref"], "wamid.demo")
        self.assertEqual(attempt["reason_code"], "openclaw_delivered")
        self.assertIsNotNone(attempt["response_hash"])
        self.assertEqual(captured[0].channel_hint, "whatsapp")
        self.assertEqual(captured[0].body_text, "Reminder: Submit forms")

    def test_transient_result_records_failed_attempt_and_retry_outcome(self) -> None:
        def sender(_outbound):
            return NormalizedOpenClawResult.transient_failure(
                reason_code="openclaw_provider_transient",
                next_attempt_at_utc="2026-06-07T10:30:00Z",
            )

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "retry")
        self.assertEqual(outcome.reason_code, "openclaw_provider_transient")
        self.assertEqual(outcome.next_attempt_at_utc, "2026-06-07T10:30:00Z")
        self.assertEqual(attempt["attempt_status"], "failed")
        self.assertEqual(attempt["reason_code"], "openclaw_provider_transient")

    def test_permanent_result_records_failed_attempt_and_failed_outcome(self) -> None:
        def sender(_outbound):
            return NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_provider_permanent")

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "openclaw_provider_permanent")
        self.assertEqual(attempt["attempt_status"], "failed")
        self.assertEqual(attempt["reason_code"], "openclaw_provider_permanent")

    def test_binding_failure_records_rejected_attempt_and_failed_outcome(self) -> None:
        def sender(_outbound):
            raise OpenClawBindingError("openclaw unavailable")

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "openclaw_binding_failed")
        self.assertEqual(attempt["attempt_status"], "rejected")
        self.assertEqual(attempt["reason_code"], "openclaw_binding_failed")

    def test_sender_exception_records_failed_attempt_and_failed_outcome(self) -> None:
        def sender(_outbound):
            raise RuntimeError("provider exploded")

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "openclaw_send_exception")
        self.assertEqual(attempt["attempt_status"], "failed")
        self.assertEqual(attempt["reason_code"], "openclaw_send_exception")

    def test_malformed_transient_result_closes_attempt_as_failed(self) -> None:
        def sender(_outbound):
            return NormalizedOpenClawResult(status="failed_transient", reason_code="openclaw_provider_transient")

        processor = OpenClawNotificationProcessor(sender=sender)
        outcome = processor(self.connection, get_work_instance(self.connection, "openclaw-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "openclaw-attempt-openclaw-work-1")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "openclaw_missing_retry_at")
        self.assertEqual(attempt["attempt_status"], "failed")
        self.assertEqual(attempt["reason_code"], "openclaw_missing_retry_at")


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="openclaw-task",
        audit_id="audit-openclaw-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="openclaw-policy",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="openclaw-policy-trigger",
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-07T09:00:00Z",
                ),
            ),
        ),
    )


def create_routed_task_with_policy(connection) -> None:
    insert_subject_group(
        connection,
        group=SubjectGroupInput(
            group_id="openclaw-group",
            group_kind="transport_group",
            display_name="OpenClaw group",
        ),
        default_created_at_utc=NOW,
    )
    insert_delivery_target(
        connection,
        target=DeliveryTargetInput(
            delivery_target_id="openclaw-target",
            owner_kind="subject_group",
            owner_group_id="openclaw-group",
            channel="whatsapp",
            adapter_name="openclaw",
            target_ref="120363409469948475@g.us",
        ),
        default_created_at_utc=NOW,
    )
    create_task_v1(
        connection,
        item_id="openclaw-routed-task",
        audit_id="audit-openclaw-routed-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Routed reminder",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="openclaw-routed-policy",
                recipient_kind="subject_group",
                recipient_group_id="openclaw-group",
                channel_preference_ref="whatsapp",
                delivery_target_id="openclaw-target",
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="openclaw-routed-policy-trigger",
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-07T09:00:00Z",
                ),
            ),
        ),
    )


def insert_subject(connection) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO subjects (
              subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
            )
            VALUES (?, 'person', 'Chris', 'active', ?, ?)
            """,
            (SUBJECT_ID, NOW, NOW),
        )


if __name__ == "__main__":
    unittest.main()
