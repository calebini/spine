import unittest
from datetime import UTC, datetime

from spine.adapters import (
    NO_PROCESSOR_CONFIGURED,
    SIDE_EFFECTS_BLOCKED,
    SpineTickerdWorkAdapter,
    WorkProcessingOutcome,
    build_work_item_payload,
)
from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.ledger import connect, get_work_instance, initialize_schema
from spine.services import list_eligible_work
from tests.canonical_helpers import seed_notification_work

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
                "notification_policy_id": "notification-policy-1",
                "notification_policy_item_version": 2,
                "notification_intent_id": "notification-intent-1",
                "notification_opportunity_id": "notification-opportunity-1",
                "normalized_notification_schedule_hash": "a" * 64,
                "occurrence_provenance_id": "occurrence-provenance-1",
                "target_anchor_role": "event_start",
                "application_scope": "each_occurrence",
                "target_scheduled_fact": "2026-06-07T10:00:00Z",
                "target_at_utc": "2026-06-07T10:00:00Z",
                "occurrence_key": "occurrence-key-1",
                "delivery_target_id": "delivery-target-1",
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
        self.assertEqual(payload["notification_opportunity_id"], "notification-opportunity-1")
        self.assertEqual(payload["occurrence_provenance_id"], "occurrence-provenance-1")
        self.assertEqual(payload["delivery_target_id"], "delivery-target-1")
        self.assertNotIn("next_attempt_at_utc", payload)


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class TickerdAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.seeded = seed_notification_work(
            self.connection,
            prefix="tickerd",
            subject_id=SUBJECT_ID,
            now_utc="2026-06-07T08:00:00Z",
            eligible_at_utc="2026-06-07T09:00:00Z",
            title="Submit forms",
        )
        self.work_id = str(self.seeded["work_instance_id"])

    def tearDown(self) -> None:
        self.connection.close()

    def test_maps_eligible_work_to_tickerd_work_item(self) -> None:
        adapter = SpineTickerdWorkAdapter(self.connection)

        items = adapter.list_work_items(cycle_envelope(), limit=10)

        self.assertEqual(adapter.read_mode(), RuntimeMode.OBSERVE_ONLY)
        self.assertEqual([item.item_id for item in items], [self.work_id])
        self.assertEqual(items[0].payload["item_id"], self.seeded["item_id"])
        self.assertEqual(items[0].payload["notification_intent_id"], self.seeded["notification_intent_id"])

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

    def test_reconcile_materializes_structured_policy_before_work_selection(self) -> None:
        context = CommandContext(ledger=self.connection)
        event = handle(
            "event.create",
            {
                "command_id": "cmd-tickerd-horizon-event",
                "actor_subject_id": SUBJECT_ID,
                "created_at_utc": "2026-06-07T08:00:00Z",
                "title": "Horizon appointment",
                "all_day": False,
                "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-06-07T12:00:00Z"},
            },
            context,
        )
        reminder = handle(
            "reminder.create",
            {
                "command_id": "cmd-tickerd-horizon-reminder",
                "actor_subject_id": SUBJECT_ID,
                "item_id": event["item_id"],
                "target_version": "1",
                "created_at_utc": "2026-06-07T08:01:00Z",
                "recipient_kind": "subject",
                "recipient_subject_id": SUBJECT_ID,
                "channel": "whatsapp",
                "delivery_target_id": "tickerd-delivery-target",
                "notification": {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "event_start", "application_scope": "item"},
                    "schedule": {
                        "kind": "once",
                        "at": {"kind": "absolute_utc", "at_utc": "2026-06-07T11:00:00Z"},
                    },
                    "late_handling": {"kind": "skip"},
                },
            },
            context,
        )
        self.assertTrue(reminder["ok"], reminder)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM work_instances WHERE item_id = ?", (event["item_id"],)).fetchone()[0],
            0,
        )

        adapter = SpineTickerdWorkAdapter(
            self.connection,
            scheduler_actor_subject_id=SUBJECT_ID,
            materialization_horizon_seconds=86_400,
        )
        result = adapter.reconcile(cycle_envelope(), max_batches=1)

        self.assertTrue(result.ok)
        work = self.connection.execute("SELECT * FROM work_instances WHERE item_id = ?", (event["item_id"],)).fetchone()
        self.assertIsNotNone(work)
        self.assertEqual(work["eligible_at_utc"], "2026-06-07T11:00:00Z")
        self.assertEqual(work["notification_intent_id"], reminder["notification_intent_id"])

    def test_reconcile_rejects_an_unbounded_materialization_horizon(self) -> None:
        adapter = SpineTickerdWorkAdapter(
            self.connection,
            scheduler_actor_subject_id=SUBJECT_ID,
            materialization_horizon_seconds=31_622_401,
        )
        with self.assertRaisesRegex(SpineValidationError, "366 days"):
            adapter.reconcile(cycle_envelope(), max_batches=1)

    def test_active_processor_success_marks_work_succeeded(self) -> None:
        def processor(_connection, work_row, _envelope):
            self.assertEqual(work_row["work_instance_id"], self.work_id)
            self.assertEqual(work_row["status"], "in_progress")
            self.assertEqual(work_row["attempt_count"], 1)
            return WorkProcessingOutcome.succeeded("demo_processed")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)

        work = get_work_instance(self.connection, self.work_id)
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

        work = get_work_instance(self.connection, self.work_id)
        self.assertEqual(result.status.value, "processed")
        self.assertEqual(work["status"], "eligible")
        self.assertEqual(work["attempt_count"], 1)
        self.assertEqual(work["reason_code"], "transient_failure")
        self.assertEqual(work["next_attempt_at_utc"], "2026-06-07T10:30:00Z")
        self.assertEqual(list_eligible_work(self.connection, now_utc="2026-06-07T10:29:00Z"), [])
        self.assertEqual(
            [row["work_instance_id"] for row in list_eligible_work(self.connection, now_utc="2026-06-07T10:30:00Z")],
            [self.work_id],
        )

    def test_active_processor_failure_and_cancellation_persist_reason_codes(self) -> None:
        def failure_processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.failed("hard_failure")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=failure_processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]
        adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=True)
        failed = get_work_instance(self.connection, self.work_id)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["reason_code"], "hard_failure")

        cancel_seed = seed_notification_work(
            self.connection,
            prefix="tickerd-cancel",
            subject_id=SUBJECT_ID,
            now_utc="2026-06-07T08:00:00Z",
            eligible_at_utc="2026-06-07T09:00:00Z",
            title="Cancel reminder",
        )
        cancel_work_id = str(cancel_seed["work_instance_id"])

        def cancel_processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.cancelled("policy_disabled")

        cancel_adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="active", processor=cancel_processor)
        cancel_item = next(item for item in cancel_adapter.list_work_items(cycle_envelope(), limit=10) if item.item_id == cancel_work_id)
        cancel_adapter.process_work_item(cancel_item, cycle_envelope(), side_effects_allowed=True)
        cancelled = get_work_instance(self.connection, cancel_work_id)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["reason_code"], "policy_disabled")

    def test_observe_only_with_processor_does_not_mutate_work(self) -> None:
        def processor(_connection, _work_row, _envelope):
            return WorkProcessingOutcome.succeeded("should_not_run")

        adapter = SpineTickerdWorkAdapter(self.connection, runtime_mode="observe_only", processor=processor)
        item = adapter.list_work_items(cycle_envelope(), limit=10)[0]

        result = adapter.process_work_item(item, cycle_envelope(), side_effects_allowed=False)

        work = get_work_instance(self.connection, self.work_id)
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
