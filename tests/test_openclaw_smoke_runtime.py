import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spine.ledger import connect, get_side_effect_attempt, get_work_instance
from spine.runtime.openclaw_smoke import OpenClawSmokePaths, main, run_openclaw_smoke
from spine.runtime.seed_demo import DEMO_WORK_INSTANCE_ID, seed_demo_ledger

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


class OpenClawSmokeCliTests(unittest.TestCase):
    def test_cli_refuses_missing_database_without_seed_or_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "missing.sqlite"
            state_dir = Path(directory) / "state"

            with self.assertRaisesRegex(SystemExit, "database does not exist"):
                main(["--db", str(db_path), "--state-dir", str(state_dir)])


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class OpenClawSmokeRuntimeTests(unittest.TestCase):
    def test_fake_openclaw_smoke_processes_seeded_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"
            connection = connect(db_path)
            try:
                seed_demo_ledger(connection)
                result = run_openclaw_smoke(
                    connection,
                    state_dir=state_dir,
                    trace_id="openclaw-smoke-test",
                    max_cycles=1,
                    install_signal_handlers=False,
                )
                work = get_work_instance(connection, DEMO_WORK_INSTANCE_ID)
                attempt = get_side_effect_attempt(
                    connection,
                    f"openclaw-attempt-{DEMO_WORK_INSTANCE_ID}-1",
                )
            finally:
                connection.close()

            paths = OpenClawSmokePaths.from_state_dir(state_dir)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.reason, "max_cycles_reached")
            self.assertEqual(work["status"], "succeeded")
            self.assertEqual(work["attempt_count"], 1)
            self.assertEqual(work["reason_code"], "openclaw_delivered")
            self.assertEqual(attempt["adapter_name"], "openclaw")
            self.assertEqual(attempt["attempt_status"], "succeeded")
            self.assertEqual(attempt["reason_code"], "openclaw_delivered")
            self.assertEqual(
                attempt["provider_ref"],
                f"fake-openclaw:{DEMO_WORK_INSTANCE_ID}:openclaw-attempt-{DEMO_WORK_INSTANCE_ID}-1",
            )

            sends = [json.loads(line) for line in paths.sends_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["event"], "openclaw_fake_send")
            self.assertEqual(sends[0]["delivery_id"], DEMO_WORK_INSTANCE_ID)
            self.assertEqual(sends[0]["fake_result"], "delivered")

            events = [json.loads(line) for line in paths.runner.events_path.read_text(encoding="utf-8").splitlines()]
            summary = next(record for record in events if record["event"] == "cycle_summary")
            self.assertEqual(summary["runtime_mode"], "active")
            self.assertEqual(summary["items_scanned"], 1)
            self.assertEqual(summary["items_processed"], 1)
            self.assertEqual(summary["items_blocked"], 0)
            self.assertEqual(summary["items_failed"], 0)

    def test_cli_can_seed_and_run_fake_openclaw_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"

            stream = StringIO()
            with redirect_stdout(stream):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "--state-dir",
                        str(state_dir),
                        "--seed-demo",
                        "--max-cycles",
                        "1",
                        "--trace-id",
                        "openclaw-smoke-cli-test",
                    ]
                )

            paths = OpenClawSmokePaths.from_state_dir(state_dir)
            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["fake_result"], "delivered")
            self.assertTrue(paths.runner.events_path.exists())
            self.assertTrue(paths.sends_path.exists())


if __name__ == "__main__":
    unittest.main()
