import json
import tempfile
import unittest
from pathlib import Path

from spine.ledger import connect
from spine.runtime.seed_demo import seed_demo_ledger
from spine.runtime.tickerd_runner import SpineRunnerPaths, main, run_foreground

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


class TickerdRunnerCliTests(unittest.TestCase):
    def test_cli_refuses_missing_database_without_initialization_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "missing.sqlite"
            state_dir = Path(directory) / "state"

            with self.assertRaisesRegex(SystemExit, "database does not exist"):
                main(["--db", str(db_path), "--state-dir", str(state_dir), "--max-cycles", "1"])


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class TickerdRunnerTests(unittest.TestCase):
    def test_foreground_runner_writes_lock_health_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"
            connection = connect(db_path)
            try:
                seeded = seed_demo_ledger(connection)
                result = run_foreground(
                    connection,
                    state_dir=state_dir,
                    trace_id="runner-test",
                    max_cycles=1,
                    tick_interval_ms=1,
                    reconcile_interval_ms=1,
                    install_signal_handlers=False,
                )
            finally:
                connection.close()

            paths = SpineRunnerPaths.from_state_dir(state_dir)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.reason, "max_cycles_reached")
            self.assertEqual(result.cycles_completed, 1)
            self.assertTrue(paths.lock_path.exists())
            self.assertTrue(paths.owner_path.exists())
            self.assertTrue(paths.health_path.exists())
            self.assertTrue(paths.events_path.exists())

            health = json.loads(paths.health_path.read_text(encoding="utf-8"))
            self.assertEqual(health["state"], "DOWN")
            self.assertFalse(health["is_ready"])
            self.assertEqual(health["last_failure_reason"], "max_cycles_reached")

            records = [json.loads(line) for line in paths.events_path.read_text(encoding="utf-8").splitlines()]
            events = [record["event"] for record in records]
            self.assertIn("startup", events)
            self.assertIn("work_item_blocked", events)
            self.assertIn("cycle_summary", events)
            self.assertIn("shutdown", events)
            blocked = next(record for record in records if record["event"] == "work_item_blocked")
            self.assertEqual(blocked["item_id"], seeded["work_instance_id"])
            self.assertEqual(blocked["reason"], "SIDE_EFFECTS_BLOCKED")
            summary = next(record for record in records if record["event"] == "cycle_summary")
            self.assertEqual(summary["items_scanned"], 1)
            self.assertEqual(summary["items_blocked"], 1)

    def test_cli_runs_foreground_runner_against_initialized_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"

            exit_code = main(
                [
                    "--db",
                    str(db_path),
                    "--state-dir",
                    str(state_dir),
                    "--initialize-schema",
                    "--max-cycles",
                    "1",
                    "--tick-interval-ms",
                    "1",
                    "--reconcile-interval-ms",
                    "1",
                    "--trace-id",
                    "runner-cli-test",
                ]
            )

            paths = SpineRunnerPaths.from_state_dir(state_dir)
            records = [json.loads(line) for line in paths.events_path.read_text(encoding="utf-8").splitlines()]
            summary = next(record for record in records if record["event"] == "cycle_summary")
            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["items_scanned"], 0)


if __name__ == "__main__":
    unittest.main()
