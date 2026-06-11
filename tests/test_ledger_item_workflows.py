import sqlite3
import unittest

from spine.core import SpineValidationError
from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.ledger import (
    EventDraft,
    ItemVersionDraft,
    TaskDraft,
    TemporalAnchorInput,
    archive_item,
    assert_ledger_invariants,
    cancel_event,
    cancel_task,
    complete_task,
    connect,
    create_event_from_draft,
    create_event_v1,
    create_item_version_from_draft,
    create_next_item_version,
    create_task_from_draft,
    create_task_v1,
    creation_audit_payload,
    get_current_item,
    initialize_schema,
    mutation_audit_payload,
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

    def test_create_event_from_draft_with_instant_utc_start(self) -> None:
        created = create_event_from_draft(
            self.connection,
            EventDraft(
                item_id="event-draft",
                audit_id="audit-event-draft",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Dentist",
                all_day=False,
                start_anchor=TemporalAnchorInput(
                    anchor_id="event-draft-start",
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-06T14:00:00Z",
                ),
            ),
        )

        self.assertEqual(created.item_id, "event-draft")
        item = get_current_item(self.connection, "event-draft")
        self.assertEqual(item["item_type"], "event")
        self.assertEqual(item["detail"]["start_anchor_id"], "event-draft-start")
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

    def test_create_task_from_draft_with_no_due_anchor(self) -> None:
        created = create_task_from_draft(
            self.connection,
            TaskDraft(
                item_id="task-draft",
                audit_id="audit-task-draft",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Submit forms",
            ),
        )

        self.assertEqual(created.item_id, "task-draft")
        item = get_current_item(self.connection, "task-draft")
        self.assertEqual(item["item_type"], "task")
        self.assertIsNone(item["detail"]["due_anchor_id"])
        assert_ledger_invariants(self.connection)

    def test_create_task_v1_uses_scoped_invariant_validation(self) -> None:
        self.insert_event_with_unadvanced_current_version()

        create_task_v1(
            self.connection,
            item_id="task-created-after-unrelated-issue",
            audit_id="audit-task-created-after-unrelated-issue",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        item = get_current_item(self.connection, "task-created-after-unrelated-issue")
        self.assertEqual(item["item_type"], "task")
        with self.assertRaisesRegex(SpineValidationError, "ledger_current_version_mismatch"):
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

    def test_create_next_item_version_from_current_v1(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-versioned",
            audit_id="audit-task-versioned-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        mutated = create_next_item_version(
            self.connection,
            item_id="task-versioned",
            target_version=1,
            audit_id="audit-task-versioned-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
            title="Submit updated forms",
        )

        self.assertEqual(mutated.previous_version, 1)
        self.assertEqual(mutated.version, 2)
        current = get_current_item(self.connection, "task-versioned")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["version"]["title"], "Submit updated forms")
        self.assertEqual(current["detail"]["task_status"], "open")
        self.assertEqual(
            self.version_title("task-versioned", 1),
            "Submit forms",
        )
        assert_ledger_invariants(self.connection)

    def test_create_item_version_from_draft_from_current_v1(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-versioned-draft",
            audit_id="audit-task-versioned-draft-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        mutated = create_item_version_from_draft(
            self.connection,
            ItemVersionDraft(
                item_id="task-versioned-draft",
                target_version=1,
                audit_id="audit-task-versioned-draft-v2",
                created_at_utc="2026-06-06T11:00:00Z",
                created_by_subject_id=SUBJECT_ID,
                title="Submit updated forms",
            ),
        )

        self.assertEqual(mutated.previous_version, 1)
        self.assertEqual(mutated.version, 2)
        current = get_current_item(self.connection, "task-versioned-draft")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["version"]["title"], "Submit updated forms")
        self.assertEqual(current["detail"]["task_status"], "open")
        assert_ledger_invariants(self.connection)

    def test_create_next_item_version_rejects_missing_intermediate_version(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-no-v2",
            audit_id="audit-task-no-v2-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_item_version"):
            create_next_item_version(
                self.connection,
                item_id="task-no-v2",
                target_version=2,
                audit_id="audit-task-no-v2-v3",
                created_at_utc="2026-06-06T11:00:00Z",
                created_by_subject_id=SUBJECT_ID,
            )

        self.assertEqual(self.current_version("task-no-v2"), 1)
        self.assert_version_absent("task-no-v2", 2)

    def test_mutation_against_stale_v1_is_rejected_after_v2_exists(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-stale",
            audit_id="audit-task-stale-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )
        create_next_item_version(
            self.connection,
            item_id="task-stale",
            target_version=1,
            audit_id="audit-task-stale-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "stale_item_version"):
            create_next_item_version(
                self.connection,
                item_id="task-stale",
                target_version=1,
                audit_id="audit-task-stale-retry",
                created_at_utc="2026-06-06T12:00:00Z",
                created_by_subject_id=SUBJECT_ID,
            )

        self.assertEqual(self.current_version("task-stale"), 2)
        self.assert_version_absent("task-stale", 3)

    def test_event_cancellation_creates_v2_and_preserves_v1(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-cancel",
            audit_id="audit-event-cancel-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-cancel-start",
                anchor_kind="instant_utc",
                utc_instant="2026-06-06T14:00:00Z",
            ),
        )

        cancel_event(
            self.connection,
            item_id="event-cancel",
            target_version=1,
            audit_id="audit-event-cancel-v2",
            cancelled_at_utc="2026-06-06T11:00:00Z",
            cancelled_by_subject_id=SUBJECT_ID,
        )

        current = get_current_item(self.connection, "event-cancel")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["detail"]["event_status"], "cancelled")
        self.assertEqual(self.event_status("event-cancel", 1), "scheduled")
        self.assertEqual(self.event_status("event-cancel", 2), "cancelled")
        assert_ledger_invariants(self.connection)

    def test_cancelled_event_cannot_be_rescheduled_by_mvp_transition(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-terminal",
            audit_id="audit-event-terminal-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-terminal-start",
                anchor_kind="instant_utc",
                utc_instant="2026-06-06T14:00:00Z",
            ),
        )
        cancel_event(
            self.connection,
            item_id="event-terminal",
            target_version=1,
            audit_id="audit-event-terminal-v2",
            cancelled_at_utc="2026-06-06T11:00:00Z",
            cancelled_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "invalid_event_transition"):
            cancel_event(
                self.connection,
                item_id="event-terminal",
                target_version=2,
                audit_id="audit-event-terminal-v3",
                cancelled_at_utc="2026-06-06T12:00:00Z",
                cancelled_by_subject_id=SUBJECT_ID,
            )

        self.assert_version_absent("event-terminal", 3)

    def test_generic_next_version_rejects_event_reschedule_bypass(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-bypass",
            audit_id="audit-event-bypass-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=TemporalAnchorInput(
                anchor_id="event-bypass-start",
                anchor_kind="instant_utc",
                utc_instant="2026-06-06T14:00:00Z",
            ),
        )
        cancel_event(
            self.connection,
            item_id="event-bypass",
            target_version=1,
            audit_id="audit-event-bypass-v2",
            cancelled_at_utc="2026-06-06T11:00:00Z",
            cancelled_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "invalid_event_transition"):
            create_next_item_version(
                self.connection,
                item_id="event-bypass",
                target_version=2,
                audit_id="audit-event-bypass-v3",
                created_at_utc="2026-06-06T12:00:00Z",
                created_by_subject_id=SUBJECT_ID,
                event_detail={"event_status": "scheduled"},
            )

        self.assert_version_absent("event-bypass", 3)

    def test_task_completion_creates_v2_and_records_completion_fields(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-complete",
            audit_id="audit-task-complete-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        complete_task(
            self.connection,
            item_id="task-complete",
            target_version=1,
            audit_id="audit-task-complete-v2",
            completed_at_utc="2026-06-06T11:00:00Z",
            completed_by_subject_id=SUBJECT_ID,
            completion_state="submitted",
        )

        current = get_current_item(self.connection, "task-complete")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["detail"]["task_status"], "done")
        self.assertEqual(current["detail"]["completion_state"], "submitted")
        self.assertEqual(current["detail"]["completed_at_utc"], "2026-06-06T11:00:00Z")
        self.assertEqual(current["detail"]["completed_by_subject_id"], SUBJECT_ID)
        self.assertEqual(self.task_status("task-complete", 1), "open")
        assert_ledger_invariants(self.connection)

    def test_task_cancellation_creates_v2(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-cancel",
            audit_id="audit-task-cancel-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        cancel_task(
            self.connection,
            item_id="task-cancel",
            target_version=1,
            audit_id="audit-task-cancel-v2",
            cancelled_at_utc="2026-06-06T11:00:00Z",
            cancelled_by_subject_id=SUBJECT_ID,
        )

        current = get_current_item(self.connection, "task-cancel")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["detail"]["task_status"], "cancelled")
        self.assertEqual(self.task_status("task-cancel", 1), "open")
        assert_ledger_invariants(self.connection)

    def test_terminal_task_rejects_further_transitions(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-terminal",
            audit_id="audit-task-terminal-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )
        complete_task(
            self.connection,
            item_id="task-terminal",
            target_version=1,
            audit_id="audit-task-terminal-v2",
            completed_at_utc="2026-06-06T11:00:00Z",
            completed_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "invalid_task_transition"):
            cancel_task(
                self.connection,
                item_id="task-terminal",
                target_version=2,
                audit_id="audit-task-terminal-v3",
                cancelled_at_utc="2026-06-06T12:00:00Z",
                cancelled_by_subject_id=SUBJECT_ID,
            )

        self.assert_version_absent("task-terminal", 3)

    def test_generic_next_version_rejects_terminal_task_reopen_bypass(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-bypass",
            audit_id="audit-task-bypass-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )
        complete_task(
            self.connection,
            item_id="task-bypass",
            target_version=1,
            audit_id="audit-task-bypass-v2",
            completed_at_utc="2026-06-06T11:00:00Z",
            completed_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "invalid_task_transition"):
            create_next_item_version(
                self.connection,
                item_id="task-bypass",
                target_version=2,
                audit_id="audit-task-bypass-v3",
                created_at_utc="2026-06-06T12:00:00Z",
                created_by_subject_id=SUBJECT_ID,
                task_detail={"task_status": "open"},
            )

        self.assert_version_absent("task-bypass", 3)

    def test_archive_updates_shell_and_writes_audit_without_new_item_version(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-archive",
            audit_id="audit-task-archive-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        archive_item(
            self.connection,
            item_id="task-archive",
            target_version=1,
            audit_id="audit-task-archive",
            archived_at_utc="2026-06-06T11:00:00Z",
            archived_by_subject_id=SUBJECT_ID,
        )

        current = get_current_item(self.connection, "task-archive")
        self.assertEqual(current["status"], "archived")
        self.assertEqual(current["current_version"], 1)
        self.assertEqual(current["archived_at_utc"], "2026-06-06T11:00:00Z")
        self.assert_version_absent("task-archive", 2)
        audit = self.audit("audit-task-archive")
        self.assertEqual(audit["action"], "item_archived")
        assert_ledger_invariants(self.connection)

    def test_mutation_audit_row_is_written_with_expected_payload_hash(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-audit-mutation",
            audit_id="audit-task-audit-mutation-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
        )

        complete_task(
            self.connection,
            item_id="task-audit-mutation",
            target_version=1,
            audit_id="audit-task-audit-mutation-v2",
            completed_at_utc="2026-06-06T11:00:00Z",
            completed_by_subject_id=SUBJECT_ID,
        )

        audit = self.audit("audit-task-audit-mutation-v2")
        self.assertEqual(audit["item_id"], "task-audit-mutation")
        self.assertEqual(audit["action"], "task_completed")
        self.assertEqual(audit["reason_code"], "task_completed")
        self.assertEqual(
            audit["payload_hash"],
            audit_log_payload_hash(
                mutation_audit_payload(
                    action="task_completed",
                    item_id="task-audit-mutation",
                    item_type="task",
                    previous_version=1,
                    version=2,
                )
            ),
        )

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

    def assert_version_absent(self, item_id: str, version: int) -> None:
        count = self.connection.execute(
            "SELECT COUNT(*) FROM coordination_item_versions WHERE item_id = ? AND version = ?",
            (item_id, version),
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def current_version(self, item_id: str) -> int:
        return self.connection.execute(
            "SELECT current_version FROM coordination_items WHERE item_id = ?",
            (item_id,),
        ).fetchone()[0]

    def version_title(self, item_id: str, version: int) -> str:
        return self.connection.execute(
            "SELECT title FROM coordination_item_versions WHERE item_id = ? AND version = ?",
            (item_id, version),
        ).fetchone()[0]

    def event_status(self, item_id: str, version: int) -> str:
        return self.connection.execute(
            "SELECT event_status FROM event_details WHERE item_id = ? AND version = ?",
            (item_id, version),
        ).fetchone()[0]

    def task_status(self, item_id: str, version: int) -> str:
        return self.connection.execute(
            "SELECT task_status FROM task_details WHERE item_id = ? AND version = ?",
            (item_id, version),
        ).fetchone()[0]

    def audit(self, audit_id: str) -> sqlite3.Row:
        return self.connection.execute(
            "SELECT * FROM audit_log WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()

    def insert_event_with_unadvanced_current_version(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO temporal_anchors (anchor_id, anchor_kind, utc_instant, created_at_utc)
                VALUES ('unrelated-event-start', 'instant_utc', ?, ?)
                """,
                (NOW, NOW),
            )
            self.connection.execute(
                """
                INSERT INTO coordination_items (
                  item_id, item_type, current_version, status, created_at_utc, updated_at_utc
                )
                VALUES ('unrelated-event', 'event', 1, 'active', ?, ?)
                """,
                (NOW, NOW),
            )
            self.connection.execute(
                """
                INSERT INTO coordination_item_versions (
                  item_id, version, title, intent_hash, normalized_fields_hash,
                  created_at_utc, created_by_subject_id
                )
                VALUES ('unrelated-event', 1, 'Dentist', ?, ?, ?, ?)
                """,
                (
                    coordination_item_version_intent_hash(title="Dentist"),
                    coordination_item_version_normalized_fields_hash(title="Dentist"),
                    NOW,
                    SUBJECT_ID,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO event_details (
                  item_id, version, event_status, all_day, start_anchor_id
                )
                VALUES ('unrelated-event', 1, 'scheduled', 0, 'unrelated-event-start')
                """
            )
            self.connection.execute(
                """
                INSERT INTO temporal_anchors (anchor_id, anchor_kind, utc_instant, created_at_utc)
                VALUES ('unrelated-event-v2-start', 'instant_utc', ?, ?)
                """,
                (NOW, NOW),
            )
            self.connection.execute(
                """
                INSERT INTO coordination_item_versions (
                  item_id, version, title, intent_hash, normalized_fields_hash,
                  created_at_utc, created_by_subject_id
                )
                VALUES ('unrelated-event', 2, 'Dentist updated', ?, ?, ?, ?)
                """,
                (
                    coordination_item_version_intent_hash(title="Dentist updated"),
                    coordination_item_version_normalized_fields_hash(title="Dentist updated"),
                    NOW,
                    SUBJECT_ID,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO event_details (
                  item_id, version, event_status, all_day, start_anchor_id
                )
                VALUES ('unrelated-event', 2, 'scheduled', 0, 'unrelated-event-v2-start')
                """
            )


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
