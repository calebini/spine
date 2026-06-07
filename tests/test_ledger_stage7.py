import unittest

from spine.core import SpineValidationError
from spine.core.hashing import side_effect_request_hash, side_effect_request_payload_hash
from spine.ledger import (
    NotificationPolicyInput,
    TemporalAnchorInput,
    assert_candidate_action_not_stale,
    assert_work_instance_not_stale,
    connect,
    create_candidate_action,
    create_external_projection,
    create_next_item_version,
    create_started_attempt,
    create_task_v1,
    create_work_instance,
    get_candidate_action,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
)


NOW = "2026-06-06T10:00:00Z"
SUBJECT_ID = "subject-1"


class LedgerStage7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_generate_notification_reminder_work_from_policy(self) -> None:
        create_task_with_policy(self.connection)

        created = create_work_instance(
            self.connection,
            work_instance_id="work-reminder-1",
            item_id="task-stage7",
            item_version=1,
            notification_policy_id="policy-stage7",
            notification_policy_item_version=1,
            generation_source_kind="notification_policy",
            generation_source_ref="policy-stage7",
            work_subject_ref=SUBJECT_ID,
            policy_basis_ref="policy-stage7",
            eligible_at_utc="2026-06-06T09:00:00Z",
            created_at_utc=NOW,
        )

        self.assertEqual(created.work_instance_id, "work-reminder-1")
        work = get_work_instance(self.connection, "work-reminder-1")
        self.assertEqual(work["item_id"], "task-stage7")
        self.assertEqual(work["item_version"], 1)
        self.assertEqual(work["notification_policy_id"], "policy-stage7")
        self.assertEqual(work["status"], "eligible")

    def test_derivative_work_requires_source_subject_and_policy_basis(self) -> None:
        create_task_with_policy(self.connection)

        with self.assertRaisesRegex(SpineValidationError, "work_instance_rejected"):
            create_work_instance(
                self.connection,
                work_instance_id="work-bad-derivative",
                item_id="task-stage7",
                item_version=1,
                generation_source_kind="schedule_tick",
                generation_source_ref="tick-1",
                eligible_at_utc="2026-06-06T09:00:00Z",
                created_at_utc=NOW,
            )

    def test_reject_reminder_delivery_pressure_without_work_row(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-without-origin",
                adapter_name="notification",
                idempotency_key="idem-without-origin",
                request_envelope={"body": "Reminder"},
                attempted_at_utc=NOW,
            )

    def test_reject_work_attempt_when_bound_item_version_is_stale(self) -> None:
        create_task_with_policy(self.connection)
        create_work_instance(
            self.connection,
            work_instance_id="work-stale",
            item_id="task-stage7",
            item_version=1,
            notification_policy_id="policy-stage7",
            notification_policy_item_version=1,
            generation_source_kind="notification_policy",
            generation_source_ref="policy-stage7",
            work_subject_ref=SUBJECT_ID,
            policy_basis_ref="policy-stage7",
            eligible_at_utc="2026-06-06T09:00:00Z",
            created_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id="task-stage7",
            target_version=1,
            audit_id="audit-task-stage7-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            assert_work_instance_not_stale(self.connection, "work-stale")
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-stale-work",
                work_instance_id="work-stale",
                adapter_name="notification",
                idempotency_key="idem-stale-work",
                request_envelope={"body": "Reminder"},
                attempted_at_utc=NOW,
            )

    def test_create_candidate_action_bound_to_item_version(self) -> None:
        create_task_with_policy(self.connection)

        created = create_candidate_action(
            self.connection,
            candidate_action_id="candidate-sync",
            item_id="task-stage7",
            item_version=1,
            action_kind="sync_projection",
            requires_approval=True,
            created_at_utc=NOW,
            evidence_ref="policy-check",
        )

        self.assertEqual(created.candidate_action_id, "candidate-sync")
        action = get_candidate_action(self.connection, "candidate-sync")
        self.assertEqual(action["action_kind"], "sync_projection")
        self.assertEqual(action["requires_approval"], 1)
        self.assertEqual(action["status"], "open")

    def test_reject_candidate_action_attempt_when_stale(self) -> None:
        create_task_with_policy(self.connection)
        create_candidate_action(
            self.connection,
            candidate_action_id="candidate-stale",
            item_id="task-stage7",
            item_version=1,
            action_kind="deliver_notification",
            requires_approval=False,
            created_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id="task-stage7",
            target_version=1,
            audit_id="audit-task-stage7-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_candidate_action"):
            assert_candidate_action_not_stale(self.connection, "candidate-stale")
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-stale-candidate",
                candidate_action_id="candidate-stale",
                adapter_name="notification",
                idempotency_key="idem-stale-candidate",
                request_envelope={"body": "Reminder"},
                attempted_at_utc=NOW,
            )

    def test_create_started_attempt_with_durable_request_hashes(self) -> None:
        create_task_with_policy(self.connection)
        create_work_instance(
            self.connection,
            work_instance_id="work-attempt",
            item_id="task-stage7",
            item_version=1,
            notification_policy_id="policy-stage7",
            notification_policy_item_version=1,
            generation_source_kind="notification_policy",
            generation_source_ref="policy-stage7",
            work_subject_ref=SUBJECT_ID,
            policy_basis_ref="policy-stage7",
            eligible_at_utc="2026-06-06T09:00:00Z",
            created_at_utc=NOW,
        )

        started = create_started_attempt(
            self.connection,
            attempt_id="attempt-work",
            work_instance_id="work-attempt",
            adapter_name="notification",
            idempotency_key="idem-work",
            request_envelope={"body": "Submit forms", "to": SUBJECT_ID},
            attempted_at_utc=NOW,
        )

        expected_payload_hash = side_effect_request_payload_hash(
            adapter_name="notification",
            request_envelope={"body": "Submit forms", "to": SUBJECT_ID},
        )
        expected_request_hash = side_effect_request_hash(
            adapter_name="notification",
            idempotency_key="idem-work",
            request_payload_hash=expected_payload_hash,
            work_instance_id="work-attempt",
        )
        self.assertEqual(started.request_payload_hash, expected_payload_hash)
        self.assertEqual(started.request_hash, expected_request_hash)
        attempt = get_side_effect_attempt(self.connection, "attempt-work")
        self.assertEqual(attempt["attempt_status"], "started")
        self.assertEqual(attempt["item_id"], "task-stage7")

    def test_reject_attempt_with_ambiguous_origin_linkage(self) -> None:
        create_task_with_policy(self.connection)
        create_work_instance(
            self.connection,
            work_instance_id="work-ambiguous",
            item_id="task-stage7",
            item_version=1,
            eligible_at_utc="2026-06-06T09:00:00Z",
            created_at_utc=NOW,
        )
        create_candidate_action(
            self.connection,
            candidate_action_id="candidate-ambiguous",
            item_id="task-stage7",
            item_version=1,
            action_kind="deliver_notification",
            requires_approval=False,
            created_at_utc=NOW,
        )

        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-ambiguous",
                work_instance_id="work-ambiguous",
                candidate_action_id="candidate-ambiguous",
                adapter_name="notification",
                idempotency_key="idem-ambiguous",
                request_envelope={"body": "Reminder"},
                attempted_at_utc=NOW,
            )

    def test_reject_projection_write_from_stale_source_version(self) -> None:
        create_task_with_policy(self.connection)
        create_external_projection(
            self.connection,
            projection_id="projection-stale",
            item_id="task-stage7",
            adapter_name="calendar",
            external_ref="external-1",
            projection_status="current",
            last_projected_version=1,
            updated_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id="task-stage7",
            target_version=1,
            audit_id="audit-task-stage7-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            create_started_attempt(
                self.connection,
                attempt_id="attempt-stale-projection",
                projection_id="projection-stale",
                item_id="task-stage7",
                source_item_version=1,
                adapter_name="calendar",
                idempotency_key="idem-stale-projection",
                request_envelope={"summary": "Submit forms"},
                attempted_at_utc=NOW,
            )


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="task-stage7",
        audit_id="audit-task-stage7",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="policy-stage7",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="policy-stage7-trigger",
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-06T09:00:00Z",
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
