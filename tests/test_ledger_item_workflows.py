import sqlite3
import unittest

from spine.core import SpineValidationError
from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.ledger import (
    TemporalAnchorInput,
    assert_ledger_invariants,
    connect,
    create_event_v1,
    create_task_v1,
    creation_audit_payload,
    get_current_item,
    initialize_schema,
)


NOW = "2026-06-06T10:00:00Z"
SUBJECT_ID = "subject-1"


class LedgerItemWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_create_event_v1_with_instant_utc_start(self) -> None:
        created = create_event_v1(
            self.connection,
            item_id="event-1",
            audit_id="audit-event-1",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            summary="Bring forms",
            source_ref="manual",
            all_day=False,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-1-start",
                anchor_kind="instant_utc",
                utc_instant="2026-06-06T14:00:00Z",
            ),
        )

        self.assertEqual(created.item_id, "event-1")
        self.assertEqual(created.version, 1)
        item = get_current_item(self.connection, "event-1")
        self.assertEqual(item["item_type"], "event")
        self.assertEqual(item["current_version"], 1)
        self.assertEqual(item["version"]["title"], "Dentist")
        self.assertEqual(item["detail"]["event_status"], "scheduled")
        self.assertEqual(item["detail"]["all_day"], 0)
        self.assertEqual(item["detail"]["start_anchor_id"], "event-1-start")
        self.assertEqual(
            item["version"]["intent_hash"],
            coordination_item_version_intent_hash(
                title="Dentist",
                summary="Bring forms",
                source_ref="manual",
            ),
        )
        self.assertEqual(
            item["version"]["normalized_fields_hash"],
            coordination_item_version_normalized_fields_hash(title="Dentist", summary="Bring forms"),
        )
        assert_ledger_invariants(self.connection)

    def test_create_all_day_event_v1_with_local_date_anchor(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-all-day",
            audit_id="audit-event-all-day",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Conference day",
            all_day=True,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-all-day-start",
                anchor_kind="local_date",
                local_date="2026-06-07",
                timezone="America/New_York",
            ),
        )

        item = get_current_item(self.connection, "event-all-day")
        self.assertEqual(item["detail"]["all_day"], 1)
        self.assertEqual(item["detail"]["start_anchor_id"], "event-all-day-start")
        assert_ledger_invariants(self.connection)

    def test_create_task_v1_with_no_due_anchor(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-1",
            audit_id="audit-task-1",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        item = get_current_item(self.connection, "task-1")
        self.assertEqual(item["item_type"], "task")
        self.assertEqual(item["detail"]["task_status"], "open")
        self.assertIsNone(item["detail"]["due_anchor_id"])
        assert_ledger_invariants(self.connection)

    def test_create_task_v1_with_due_local_date(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-due",
            audit_id="audit-task-due",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="File paperwork",
            due_anchor=TemporalAnchorInput(
                anchor_id="task-due-anchor",
                anchor_kind="local_date",
                local_date="2026-06-08",
                timezone="America/New_York",
            ),
        )

        item = get_current_item(self.connection, "task-due")
        self.assertEqual(item["detail"]["due_anchor_id"], "task-due-anchor")
        assert_ledger_invariants(self.connection)

    def test_create_done_task_v1_without_completion_metadata_is_rejected_atomically(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "item_create_rejected"):
            create_task_v1(
                self.connection,
                item_id="done-task",
                audit_id="audit-done-task",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Already done",
                task_status="done",
            )

        self.assert_item_absent("done-task")

    def test_all_day_event_with_instant_start_is_rejected_atomically(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "item_create_rejected"):
            create_event_v1(
                self.connection,
                item_id="bad-all-day",
                audit_id="audit-bad-all-day",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Bad all day",
                all_day=True,
                start_anchor=TemporalAnchorInput(
                    anchor_id="bad-all-day-start",
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-06T14:00:00Z",
                ),
            )

        self.assert_item_absent("bad-all-day")
        self.assert_anchor_absent("bad-all-day-start")

    def test_timed_event_with_date_anchor_is_rejected_atomically(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "item_create_rejected"):
            create_event_v1(
                self.connection,
                item_id="bad-timed",
                audit_id="audit-bad-timed",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Bad timed",
                all_day=False,
                start_anchor=TemporalAnchorInput(
                    anchor_id="bad-timed-start",
                    anchor_kind="local_date",
                    local_date="2026-06-06",
                    timezone="America/New_York",
                ),
            )

        self.assert_item_absent("bad-timed")
        self.assert_anchor_absent("bad-timed-start")

    def test_audit_row_is_written_with_expected_payload_hash(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-audit",
            audit_id="audit-event-audit",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Audit me",
            all_day=False,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-audit-start",
                anchor_kind="instant_utc",
                utc_instant="2026-06-06T14:00:00Z",
            ),
        )

        audit = self.connection.execute(
            "SELECT * FROM audit_log WHERE audit_id = 'audit-event-audit'"
        ).fetchone()
        self.assertEqual(audit["item_id"], "event-audit")
        self.assertEqual(audit["stage"], "item")
        self.assertEqual(audit["action"], "created")
        self.assertEqual(audit["reason_code"], "item_created")
        self.assertEqual(audit["actor_ref"], SUBJECT_ID)
        self.assertEqual(
            audit["payload_hash"],
            audit_log_payload_hash(
                creation_audit_payload(item_id="event-audit", item_type="event", version=1)
            ),
        )

    def test_missing_subject_rejects_create_and_leaves_no_partial_item(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "item_create_rejected"):
            create_task_v1(
                self.connection,
                item_id="task-no-subject",
                audit_id="audit-task-no-subject",
                created_at_utc=NOW,
                created_by_subject_id="missing-subject",
                title="No subject",
            )

        self.assert_item_absent("task-no-subject")

    def assert_item_absent(self, item_id: str) -> None:
        count = self.connection.execute(
            "SELECT COUNT(*) FROM coordination_items WHERE item_id = ?",
            (item_id,),
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def assert_anchor_absent(self, anchor_id: str) -> None:
        count = self.connection.execute(
            "SELECT COUNT(*) FROM temporal_anchors WHERE anchor_id = ?",
            (anchor_id,),
        ).fetchone()[0]
        self.assertEqual(count, 0)


def insert_subject(connection: sqlite3.Connection) -> None:
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
