import unittest
from datetime import UTC, datetime

from spine.adapters import (
    NO_PROCESSOR_CONFIGURED,
    SIDE_EFFECTS_BLOCKED,
    SpineTickerdWorkAdapter,
    WorkProcessingOutcome,
    build_work_item_payload,
)
from spine.ledger import NotificationPolicyInput, TemporalAnchorInput, connect, create_task_v1, get_work_instance, initialize_schema
from spine.services import generate_notification_reminder_work, list_eligible_work

try:
    from tickerd import CycleEnvelope, RuntimeMode, TickerdConfig
    from tickerd.conformance import AdapterComponents, assert_basic_adapter_conformance

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


NOW = "2026-06-07T10:00:00Z"
SUBJECT_ID = "subject-1"


class TickerdPayloadTests(unittest.TestCase):
    def test_build_work_item_payload_omits_nulls_and_preserves_spine_identity(self) -> None:
        payload = build_work_item_payload(
            {
                "work_instance_id": "work-1",
                "item_id": "item-1",
                "item_version": 2,
                "work_kind": "notification_reminder",
                "eligible_at_utc": "2026-06-07T09:00:00Z",
                "notification_policy_id": None,
                "generation_source_kind": "notification_policy",
                "generation_source_ref": "policy-1",
                "work_subject_ref": "subject-1",
                "policy_basis_ref": "policy-1",
                "attempt_count": 0,
                "next_attempt_at_utc": None,
                "reason_code": None,
            }
        )

        self.assertEqual(payload["payload_version"], "spine.tickerd.work_item.v1")
        self.assertEqual(payload["work_instance_id"], "work-1")
        self.assertEqual(payload["item_id"], "item-1")
        self.assertEqual(payload["item_version"], 2)
        self.assertNotIn("notification_policy_id", payload)
        self.assertNotIn("next_attempt_at_utc", payload)


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class TickerdAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="tickerd-work",
            notification_policy_id="tickerd-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_maps_eligible_work_to_tickerd_work_item(self) -> None:
        adapter = SpineTickerdWorkAdapter(self.connection)

        items = adapter.list_work_items(cycle_envelope(), limit=10)

        self.assertEqual(adapter.read_mode(), RuntimeMode.OBSERVE_ONLY)
        self.assertEqual([item.item_id for item in items], ["tickerd-work"])
        self.assertEqual(items[0].payload["item_id"], "tickerd-task")
        self.assertEqual(items[0].payload["policy_basis_ref"], "tickerd-policy")

    def test_observe_only_processing_blocks_side_effects(self) -> None:
        adapter = SpineTickerdWorkAdapter(self.connection)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=False)

        self.assertEqual(result.reason, SIDE_EFFECTS_BLOCKED)

    def test_active_processing_without_handler_blocks(self) -> None:
        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active")
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)

        self.assertEqual(result.reason, NO_PROCESSOR_CONFIGURED)

    def test_active_processor_success_marks_work_succeeded(self) -> None:
        def processor(_connection, work_row, _envelope):
            self.assertEqual(work_row["work_instance_id"], "tickerd-work")
            self.assertEqual(work_row["status"], "in_progress")
            self.assertEqual(work_row["attempt_count"], 1)
            return WorkProcessingOutcome.succeeded("demo_processed")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)

        work = get_work_instance(self.connection, "tickerd-work")
        self.assertEqual(result.status.value, "processed")
        self.assertEqual(work["status"], "succeeded")
        self.assertEqual(work["attempt_count"], 1)
        self.assertEqual(work["reason_code"], "demo_processed")

    def test_active_processor_retry_schedules_next_attempt(self) -> None:
        def processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.retry(
                reason_code="transient_failure",
                next_attempt_at_utc="2026-06-07T10:30:00Z",
            )

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)

        work = get_work_instance(self.connection, "tickerd-work")
        self.assertEqual(result.status.value, "processed")
        self.assertEqual(work["status"], "eligible")
        self.assertEqual(work["attempt_count"], 1)
        self.assertEqual(work["reason_code"], "transient_failure")
        self.assertEqual(work["next_attempt_at_utc"], "2026-06-07T10:30:00Z")
        self.assertEqual(list_eligible_work(self.connection, now_utc="2026-06-07T10:29:00Z"), [])
        self.assertEqual(
            [row["work_instance_id"] for row in list_eligible_work(self.connection, now_utc="2026-06-07T10:30:00Z")],
            ["tickerd-work"],
        )

    def test_active_processor_failure_and_cancellation_persist_reason_codes(self) -> None:
        def failure_processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.failed("hard_failure")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=failure_processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]
        adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)
        failed = get_work_instance(self.connection, "tickerd-work")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["reason_code"], "hard_failure")

        generate_notification_reminder_work(
            self.connection,
            work_instance_id="tickerd-work-cancel",
            notification_policy_id="tickerd-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )

        def cancel_processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.cancelled("policy_disabled")

        cancel_adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=cancel_processor)
        cancel_item = next(item for item in cancel_adapter.list_work_items(cycle_envelope(), limit=10) if item.item_id == "tickerd-work-cancel")
        cancel_adapter.process_work_item(cancel_item, cycle_envelope(), side_effects_allowed=True)
        cancelled = get_work_instance(self.connection, "tickerd-work-cancel")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["reason_code"], "policy_disabled")

    def test_observe_only_with_processor_does_not_mutate_work(self) -> None:
        def processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.succeeded("should_not_run")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="observe_only", processor=processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=False)

        work = get_work_instance(self.connection, "tickerd-work")
        self.assertEqual(result.reason, SIDE_EFFECTS_BLOCKED)
        self.assertEqual(work["status"], "eligible")
        self.assertEqual(work["attempt_count"], 0)

    def test_passes_tickerd_basic_conformance_smoke(self) -> None:
        adapter = SpineTickerdWorkAdapter(self.connection)

        assert_basic_adapter_conformance(
            AdapterComponents(
                mode_reader=adapter,
                work_source=adapter,
                processor=adapter,
                reconciler=adapter,
            ),
            config=TickerdConfig(max_work_items_per_tick=5),
        )


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="tickerd-task",
        audit_id="audit-tickerd-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="tickerd-policy",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="tickerd-policy-trigger",
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


def cycle_envelope():
    return CycleEnvelope(
        trace_id="trace-1",
        cycle_id="cycle-1",
        causation_id="ROOT:cycle-1",
        scheduled_tick_ts=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        actual_start_ts=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        runtime_mode=RuntimeMode.OBSERVE_ONLY,
    )


if __name__ == "__main__":
    unittest.main()
