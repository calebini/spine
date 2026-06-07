import json
import tempfile
import unittest
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spine.ledger import NotificationPolicyInput, TemporalAnchorInput, connect, create_task_v1, initialize_schema
from spine.runtime.tickerd_observe import main, run_observe_cycles
from spine.services import generate_notification_reminder_work

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


NOW = "2026-06-07T10:00:00Z"
SUBJECT_ID = "subject-1"


class TickerdObserveCliTests(unittest.TestCase):
    def test_cli_refuses_missing_database_without_initialization_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_db = Path(directory) / "missing.sqlite"

            with self.assertRaisesRegex(SystemExit, "database does not exist"):
                main([str(missing_db)])


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class TickerdObserveRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)
        create_task_with_policy(self.connection)
        generate_notification_reminder_work(
            self.connection,
            work_instance_id="runtime-work",
            notification_policy_id="runtime-policy",
            eligible_at_utc="2026-06-07T09:00:00Z",
            created_at_utc=NOW,
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_observe_cycles_emit_jsonl_records_for_eligible_work(self) -> None:
        stream = StringIO()

        summaries = run_observe_cycles(
            self.connection,
            cycles=1,
            trace_id="runtime-test",
            stream=stream,
            start_at_utc=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        )

        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(summaries[0]["items_scanned"], 1)
        self.assertEqual(summaries[0]["items_blocked"], 1)
        self.assertIn("startup", [record["event"] for record in records])
        self.assertIn("work_item_blocked", [record["event"] for record in records])
        self.assertIn("cycle_summary", [record["event"] for record in records])
        blocked = next(record for record in records if record["event"] == "work_item_blocked")
        self.assertEqual(blocked["item_id"], "runtime-work")
        self.assertEqual(blocked["reason"], "SIDE_EFFECTS_BLOCKED")

    def test_cli_can_initialize_empty_database_and_emit_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "spine.sqlite"
            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main([str(db_path), "--initialize-schema", "--trace-id", "cli-test"])
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(exit_code, 0)
        self.assertEqual(records[-2]["event"], "cycle_summary")
        self.assertEqual(records[-2]["items_scanned"], 0)


def create_task_with_policy(connection) -> None:
    create_task_v1(
        connection,
        item_id="runtime-task",
        audit_id="audit-runtime-task",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
        notification_policies=(
            NotificationPolicyInput(
                policy_id="runtime-policy",
                recipient_subject_id=SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id="runtime-policy-trigger",
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
