import json
import tempfile
import unittest
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spine.ledger import connect, initialize_schema
from spine.runtime.tickerd_observe import main, run_observe_cycles
from tests.canonical_helpers import seed_notification_work

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
        self.seeded = seed_notification_work(
            self.connection,
            prefix="tickerd-runtime",
            subject_id=SUBJECT_ID,
            now_utc="2026-06-07T08:00:00Z",
            eligible_at_utc="2026-06-07T09:00:00Z",
            title="Submit forms",
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
        self.assertEqual(blocked["item_id"], self.seeded["work_instance_id"])
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


if __name__ == "__main__":
    unittest.main()
