from __future__ import annotations

import unittest

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.ledger import (
    connect,
    create_external_projection,
    create_next_item_version,
    get_candidate_action,
    get_current_item,
    get_side_effect_attempt,
    get_work_instance,
    initialize_schema,
)
from spine.services import (
    cancel_work,
    fail_work,
    list_eligible_work,
    plan_projection_sync,
    prepare_candidate_action_attempt,
    prepare_projection_attempt,
    prepare_work_attempt,
    require_processable_work,
    retry_work,
    start_work,
    succeed_work,
)
from tests.canonical_helpers import seed_notification_work

NOW = "2026-08-01T00:00:00Z"
ELIGIBLE = "2026-08-01T01:00:00Z"
SUBJECT_ID = "subject-services"


class ServiceWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_materialized_work_is_eligible_and_processable(self) -> None:
        seeded = self._seed("service-eligible")
        eligible = list_eligible_work(self.connection, now_utc=ELIGIBLE)

        self.assertEqual(
            [row["work_instance_id"] for row in eligible], [seeded["work_instance_id"]]
        )
        processable = require_processable_work(
            self.connection, str(seeded["work_instance_id"])
        )
        self.assertEqual(processable["notification_intent_id"], seeded["notification_intent_id"])

    def test_work_attempt_gate_requires_started_work_and_persists_attempt(self) -> None:
        seeded = self._seed("service-attempt")
        work_id = str(seeded["work_instance_id"])
        start_work(self.connection, work_instance_id=work_id, started_at_utc=ELIGIBLE)
        gate = prepare_work_attempt(
            self.connection,
            attempt_id="service-attempt-row",
            work_instance_id=work_id,
            adapter_name="notification",
            idempotency_key="service-attempt",
            request_envelope={"body": "Canonical notification test", "to": SUBJECT_ID},
            attempted_at_utc=ELIGIBLE,
        )

        self.assertTrue(gate.may_start_external_write)
        attempt = get_side_effect_attempt(self.connection, gate.attempt.attempt_id)
        self.assertEqual(attempt["attempt_status"], "started")
        self.assertEqual(attempt["work_instance_id"], work_id)

    def test_work_lifecycle_success_retry_failure_and_cancel(self) -> None:
        succeeded_seed = self._seed("service-success")
        succeeded_id = str(succeeded_seed["work_instance_id"])
        started = start_work(
            self.connection,
            work_instance_id=succeeded_id,
            started_at_utc=ELIGIBLE,
            reason_code="processor_started",
        )
        self.assertEqual(started.status, "in_progress")
        succeeded = succeed_work(
            self.connection,
            work_instance_id=succeeded_id,
            succeeded_at_utc="2026-08-01T01:01:00Z",
            reason_code="delivered",
        )
        self.assertEqual(succeeded.status, "succeeded")

        retry_seed = self._seed("service-retry")
        retry_id = str(retry_seed["work_instance_id"])
        start_work(self.connection, work_instance_id=retry_id, started_at_utc=ELIGIBLE)
        retried = retry_work(
            self.connection,
            work_instance_id=retry_id,
            next_attempt_at_utc="2026-08-01T01:30:00Z",
            updated_at_utc="2026-08-01T01:01:00Z",
            reason_code="transient_adapter_failure",
        )
        self.assertEqual(retried.status, "eligible")
        self.assertNotIn(
            retry_id,
            [row["work_instance_id"] for row in list_eligible_work(
                self.connection, now_utc="2026-08-01T01:29:59Z"
            )],
        )
        self.assertIn(
            retry_id,
            [row["work_instance_id"] for row in list_eligible_work(
                self.connection, now_utc="2026-08-01T01:30:00Z"
            )],
        )

        failed_seed = self._seed("service-fail")
        failed_id = str(failed_seed["work_instance_id"])
        fail_work(
            self.connection,
            work_instance_id=failed_id,
            failed_at_utc="2026-08-01T01:01:00Z",
            reason_code="recipient_unreachable",
        )
        self.assertEqual(get_work_instance(self.connection, failed_id)["reason_code"], "recipient_unreachable")

        cancelled_seed = self._seed("service-cancel")
        cancelled_id = str(cancelled_seed["work_instance_id"])
        cancel_work(
            self.connection,
            work_instance_id=cancelled_id,
            cancelled_at_utc="2026-08-01T01:01:00Z",
            reason_code="policy_disabled",
        )
        self.assertEqual(get_work_instance(self.connection, cancelled_id)["status"], "cancelled")

    def test_invalid_work_transition_is_rejected(self) -> None:
        seeded = self._seed("service-invalid-transition")
        with self.assertRaisesRegex(SpineValidationError, "work_outcome_rejected"):
            succeed_work(
                self.connection,
                work_instance_id=str(seeded["work_instance_id"]),
                succeeded_at_utc=ELIGIBLE,
            )

    def test_policy_disable_removes_work_from_eligibility(self) -> None:
        seeded = self._seed("service-disabled")
        current = self._current_version(seeded["item_id"])
        response = handle(
            "reminder.disable",
            {
                "command_id": "cmd-service-disable",
                "actor_subject_id": SUBJECT_ID,
                "item_id": seeded["item_id"],
                "target_version": str(current),
                "notification_intent_id": seeded["notification_intent_id"],
                "notification_policy_id": seeded["notification_policy_id"],
                "disabled_at_utc": "2026-08-01T00:10:00Z",
            },
            CommandContext(ledger=self.connection),
        )
        self.assertTrue(response["ok"], response)
        self.assertEqual(list_eligible_work(self.connection, now_utc=ELIGIBLE), [])
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            require_processable_work(self.connection, str(seeded["work_instance_id"]))

    def test_projection_and_candidate_attempt_gates_remain_fail_closed(self) -> None:
        seeded = self._seed("service-projection")
        item_id = str(seeded["item_id"])
        current = self._current_version(item_id)
        planned = plan_projection_sync(
            self.connection,
            candidate_action_id="service-candidate",
            item_id=item_id,
            created_at_utc=NOW,
            evidence_ref="service-plan",
        )
        self.assertEqual(planned.item_version, current)
        gate = prepare_candidate_action_attempt(
            self.connection,
            attempt_id="service-candidate-attempt",
            candidate_action_id="service-candidate",
            adapter_name="projection-planner",
            idempotency_key="service-candidate",
            request_envelope={"item_id": item_id},
            attempted_at_utc=NOW,
        )
        self.assertEqual(
            get_side_effect_attempt(self.connection, gate.attempt.attempt_id)["candidate_action_id"],
            "service-candidate",
        )
        self.assertEqual(get_candidate_action(self.connection, "service-candidate")["status"], "open")

        create_external_projection(
            self.connection,
            projection_id="service-projection",
            item_id=item_id,
            adapter_name="calendar",
            external_ref="external-service-task",
            projection_status="current",
            last_projected_version=current,
            updated_at_utc=NOW,
        )
        create_next_item_version(
            self.connection,
            item_id=item_id,
            target_version=current,
            audit_id="audit-service-projection-vnext",
            created_at_utc="2026-08-01T00:10:00Z",
            created_by_subject_id=SUBJECT_ID,
            supporting_command_id="cmd-service-projection-forward",
        )
        with self.assertRaisesRegex(SpineValidationError, "side_effect_attempt_rejected"):
            prepare_projection_attempt(
                self.connection,
                attempt_id="service-stale-projection-attempt",
                projection_id="service-projection",
                item_id=item_id,
                source_item_version=current,
                adapter_name="calendar",
                idempotency_key="service-stale-projection",
                request_envelope={"summary": "Canonical notification test"},
                attempted_at_utc="2026-08-01T00:11:00Z",
            )

    def test_item_read_surface_returns_canonical_policy_truth(self) -> None:
        seeded = self._seed("service-read")
        current = get_current_item(self.connection, str(seeded["item_id"]))

        self.assertEqual(current["item_id"], seeded["item_id"])
        policy = current["notification_policies"][0]
        self.assertEqual(policy["notification_intent_id"], seeded["notification_intent_id"])
        self.assertEqual(policy["notification_policy_id"], seeded["notification_policy_id"])
        self.assertEqual(policy["schedule"]["kind"], "once")

    def _seed(self, prefix: str) -> dict[str, object]:
        return seed_notification_work(
            self.connection,
            prefix=prefix,
            subject_id=SUBJECT_ID,
            now_utc=NOW,
            eligible_at_utc=ELIGIBLE,
        )

    def _current_version(self, item_id: object) -> int:
        return int(
            self.connection.execute(
                "SELECT current_version FROM coordination_items WHERE item_id = ?",
                (str(item_id),),
            ).fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()
