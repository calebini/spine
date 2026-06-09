import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from spine.adapters import (
    AttemptBackedSideEffectProcessor,
    AttemptBackedSideEffectRequest,
    NormalizedSideEffectResult,
    SideEffectBindingError,
)
from spine.ledger import (
    NotificationPolicyInput,
    TemporalAnchorInput,
    connect,
    create_task_v1,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
)
from spine.services import generate_notification_reminder_work, start_work


NOW = "2026-06-07T10:00:00Z"
SUBJECT_ID = "subject-1"


@dataclass(frozen=True)
class FakeEnvelope:
    trace_id: str = "trace-side-effect"
    causation_id: str = "ROOT:cycle-side-effect"
    actual_start_ts: datetime = datetime(2026, 6, 7, 10, 0, tzinfo=UTC)


class SideEffectsAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="generic-work",
            notification_policy_id="generic-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )
        start_work(
            self.connection,
            work_instance_id="generic-work",
            started_at_utc=NOW,
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_attempt_backed_processor_records_success_without_provider_specific_code(self) -> None:
        captured = []

        def sender(message: Mapping[str, str]) -> NormalizedSideEffectResult:
            captured.append(message)
            return NormalizedSideEffectResult.succeeded(
                reason_code="generic_delivered",
                provider_ref="provider-generic",
            )

        processor = AttemptBackedSideEffectProcessor(
            adapter_name="generic-notifier",
            build_request=build_generic_request,
            sender=sender,
        )
        outcome = processor(self.connection, get_work_instance(self.connection, "generic-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "generic-attempt-generic-work-1")
        self.assertEqual(outcome.status, "succeeded")
        self.assertEqual(attempt["adapter_name"], "generic-notifier")
        self.assertEqual(attempt["attempt_status"], "succeeded")
        self.assertEqual(attempt["provider_ref"], "provider-generic")
        self.assertEqual(captured[0]["body_text"], "Generic reminder")

    def test_attempt_backed_processor_records_binding_failure_as_rejected(self) -> None:
        def sender(_message: Mapping[str, str]) -> NormalizedSideEffectResult:
            raise SideEffectBindingError("binding unavailable")

        processor = AttemptBackedSideEffectProcessor(
            adapter_name="generic-notifier",
            build_request=build_generic_request,
            sender=sender,
            binding_failure_reason_code="generic_binding_failed",
        )
        outcome = processor(self.connection, get_work_instance(self.connection, "generic-work"), FakeEnvelope())

        attempt = get_side_effect_attempt(self.connection, "generic-attempt-generic-work-1")
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "generic_binding_failed")
        self.assertEqual(attempt["attempt_status"], "rejected")
        self.assertEqual(attempt["reason_code"], "generic_binding_failed")


def build_generic_request(
    _connection,
    work_row: Mapping[str, object],
    envelope: FakeEnvelope,
) -> AttemptBackedSideEffectRequest[Mapping[str, str]]:
    work_instance_id = str(work_row["work_instance_id"])
    attempt_count = str(work_row["attempt_count"])
    attempted_at_utc = f"{envelope.actual_start_ts.astimezone(UTC).replace(tzinfo=None).isoformat()}Z"
    message = {
        "body_text": "Generic reminder",
        "trace_id": envelope.trace_id,
    }
    return AttemptBackedSideEffectRequest(
        message=message,
        attempt_id=f"generic-attempt-{work_instance_id}-{attempt_count}",
        work_instance_id=work_instance_id,
        idempotency_key=f"generic:{work_instance_id}:{attempt_count}",
        request_envelope=message,
        attempted_at_utc=attempted_at_utc,
    )


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="generic-task",
        audit_id="audit-generic-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="generic-policy",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="generic-policy-trigger",
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
