import json
import sqlite3
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from spine.ledger import connect
from spine.runtime.seed_demo import (
    DEMO_TASK_ID,
    DEMO_WORK_INSTANCE_ID,
    main,
    seed_demo_ledger,
)
from spine.services import list_eligible_work


class SeedDemoRuntimeTests(unittest.TestCase):
    def test_seed_demo_ledger_creates_one_eligible_work_instance(self) -> None:
        connection = connect()
        try:
            result = seed_demo_ledger(connection)

            eligible = list_eligible_work(connection, now_utc="2026-06-07T10:00:00Z")
            self.assertEqual(result["item_id"], DEMO_TASK_ID)
            self.assertEqual(result["work_instance_id"], DEMO_WORK_INSTANCE_ID)
            self.assertEqual([row["work_instance_id"] for row in eligible], [DEMO_WORK_INSTANCE_ID])
            self.assertEqual(eligible[0]["item_id"], DEMO_TASK_ID)
        finally:
            connection.close()

    def test_cli_creates_database_and_prints_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "demo.sqlite"
            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main([str(db_path)])
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["database"], str(db_path))
            self.assertEqual(payload["work_instance_id"], DEMO_WORK_INSTANCE_ID)
            self.assertTrue(db_path.exists())

    def test_cli_refuses_existing_database_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "demo.sqlite"
            sqlite3.connect(db_path).close()

            with self.assertRaisesRegex(SystemExit, "database already exists"):
                main([str(db_path)])

    def test_cli_if_absent_seeds_existing_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "demo.sqlite"
            sqlite3.connect(db_path).close()
            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main(["--if-absent", str(db_path)])
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["seeded"])
            self.assertEqual(payload["work_instance_id"], DEMO_WORK_INSTANCE_ID)

            connection = connect(db_path)
            try:
                eligible = list_eligible_work(connection, now_utc="2026-06-07T10:00:00Z")
                self.assertEqual([row["work_instance_id"] for row in eligible], [DEMO_WORK_INSTANCE_ID])
            finally:
                connection.close()

    def test_cli_if_absent_is_noop_when_demo_work_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "demo.sqlite"
            connection = connect(db_path)
            try:
                seed_demo_ledger(connection)
            finally:
                connection.close()

            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main(["--if-absent", str(db_path)])
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertFalse(payload["seeded"])
            self.assertEqual(payload["work_instance_id"], DEMO_WORK_INSTANCE_ID)


if __name__ == "__main__":
    unittest.main()
