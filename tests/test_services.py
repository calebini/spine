import unittest

from spine.core import SpineValidationError
from spine.ledger import (
    NotificationPolicyInput,
    TemporalAnchorInput,
    connect,
    create_external_projection,
    create_next_item_version,
    create_task_v1,
    get_candidate_action,
    get_side_effect_attempt,
    initialize_schema,
)
from spine.services import (
    generate_notification_reminder_work,
    get_current,
    list_eligible_work,
    plan_projection_sync,
    prepare_candidate_action_attempt,
    prepare_projection_attempt,
    prepare_work_attempt,
    require_processable_work,
)


NOW = "2026-06-07T10:00:00Z"
SUBJECT_ID = "subject-1"


class ServiceWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_generate_notification_work_and_list_eligible_work(self) -> None:
        create_task_with_policy(self.connection)

        created = generate_notification_reminder_work(
            self.connection,
            work_instance_id="service-work",
            notification_policy_id="service-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )

        self.assertEqual(created.work_instance_id, "service-work")
        eligible = list_eligible_work(self.connection, now_utc=NOW)
        self.assertEqual([row["work_instance_id"] for row in eligible], ["service-work"])
        processable = require_processable_work(self.connection, "service-work")
        self.assertEqual(processable["item_version"], 1)

    def test_work_attempt_gate_persists_started_attempt_before_write(self) -> None:
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="service-work-attempt",
            notification_policy_id="service-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )

        gate = prepare_work_attempt(
            self.connection,
            attempt_id="service-work-attempt-row",
            work_instance_id="service-work-attempt",
            adapter_name="notification",
            idempotency_key="service-work-attempt",
            request_envelope={"body": "Submit forms", "to": SUBJECT_ID},
            attempted_at_utc="2026-06-07T10:01:00Z",
        )

        self.assertTrue(gate.may_start_external_write)
        attempt = get_side_effect_attempt(self.connection, gate.attempt.attempt_id)
        self.assertEqual(attempt["attempt_status"], "started")
        self.assertEqual(attempt["work_instance_id"], "service-work-attempt")

    def test_work_attempt_gate_rejects_stale_work(self) -> None:
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="service-stale-work",
            notification_policy_id="service-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id="service-task",
            target_version=1,
            audit_id="audit-service-task-v2",
            created_at_utc="2026-06-07T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        self.assertEqual(list_eligible_work(self.connection, now_utc="2026-06-07T12:00:00Z"), [])
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            prepare_work_attempt(
                self.connection,
                attempt_id="service-stale-work-attempt",
                work_instance_id="service-stale-work",
                adapter_name="notification",
                idempotency_key="service-stale-work",
                request_envelope={"body": "Submit forms"},
                attempted_at_utc="2026-06-07T12:00:00Z",
            )

    def test_plan_projection_sync_and_prepare_candidate_action_attempt(self) -> None:
        create_task_with_policy(self.connection)

        planned = plan_projection_sync(
            self.connection,
            candidate_action_id="service-candidate",
            item_id="service-task",
            created_at_utc=NOW,
            evidence_ref="service-plan",
        )
        self.assertEqual(planned.item_version, 1)
        self.assertEqual(get_candidate_action(self.connection, "service-candidate")["action_kind"], "sync_projection")

        gate = prepare_candidate_action_attempt(
            self.connection,
            attempt_id="service-candidate-attempt",
            candidate_action_id="service-candidate",
            adapter_name="projection-planner",
            idempotency_key="service-candidate",
            request_envelope={"item_id": "service-task"},
            attempted_at_utc="2026-06-07T10:01:00Z",
        )
        attempt = get_side_effect_attempt(self.connection, gate.attempt.attempt_id)
        self.assertEqual(attempt["candidate_action_id"], "service-candidate")
        self.assertEqual(attempt["item_id"], "service-task")

    def test_prepare_projection_attempt_rejects_stale_source_version(self) -> None:
        create_task_with_policy(self.connection)
        create_external_projection(
            self.connection,
            projection_id="service-projection",
            item_id="service-task",
            adapter_name="calendar",
            external_ref="external-service-task",
            projection_status="current",
            last_projected_version=1,
            updated_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id="service-task",
            target_version=1,
            audit_id="audit-service-task-v2",
            created_at_utc="2026-06-07T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            prepare_projection_attempt(
                self.connection,
                attempt_id="service-stale-projection-attempt",
                projection_id="service-projection",
                item_id="service-task",
                source_item_version=1,
                adapter_name="calendar",
                idempotency_key="service-stale-projection",
                request_envelope={"summary": "Submit forms"},
                attempted_at_utc="2026-06-07T12:00:00Z",
            )

    def test_item_service_read_surface_returns_current_truth(self) -> None:
        create_task_with_policy(self.connection)

        current = get_current(self.connection, "service-task")

        self.assertEqual(current["item_id"], "service-task")
        self.assertEqual(current["current_version"], 1)
        self.assertEqual(current["notification_policies"][0]["policy_id"], "service-policy")


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="service-task",
        audit_id="audit-service-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="service-policy",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="service-policy-trigger",
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
