import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spine.ledger import connect, get_side_effect_attempt, get_work_instance, initialize_schema
from spine.runtime.worker import SpineWorkerPaths, main, run_spine_worker
from spine.runtime.seed_demo import DEMO_WORK_INSTANCE_ID, seed_demo_ledger

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


class SpineWorkerCliValidationTests(unittest.TestCase):
    def test_cli_refuses_missing_database_without_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "missing.sqlite"
            state_dir = Path(directory) / "state"

            with self.assertRaisesRegex(SystemExit, "database does not exist"):
                main(["--db", str(db_path), "--state-dir", str(state_dir), "--max-cycles", "1"])

    def test_cli_refuses_gateway_sender_without_explicit_real_send_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "spine.sqlite"
            state_dir = Path(directory) / "state"
            connection = connect(db_path)
            try:
                initialize_schema(connection)
            finally:
                connection.close()

            with self.assertRaisesRegex(SystemExit, "--openclaw-sender gateway requires --allow-real-send"):
                main(
                    [
                        "--db",
                        str(db_path),
                        "--state-dir",
                        str(state_dir),
                        "--openclaw-sender",
                        "gateway",
                        "--max-cycles",
                        "1",
                    ]
                )

    def test_cli_refuses_unsupported_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "spine.sqlite"
            state_dir = Path(directory) / "state"
            connection = connect(db_path)
            try:
                initialize_schema(connection)
            finally:
                connection.close()

            with self.assertRaisesRegex(SystemExit, "unsupported worker binding"):
                main(
                    [
                        "--db",
                        str(db_path),
                        "--state-dir",
                        str(state_dir),
                        "--bindings",
                        "calendar",
                        "--max-cycles",
                        "1",
                    ]
                )

    def test_cli_refuses_empty_openclaw_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "spine.sqlite"
            state_dir = Path(directory) / "state"
            connection = connect(db_path)
            try:
                initialize_schema(connection)
            finally:
                connection.close()

            with self.assertRaisesRegex(SystemExit, "--openclaw-channel must be non-empty"):
                main(
                    [
                        "--db",
                        str(db_path),
                        "--state-dir",
                        str(state_dir),
                        "--openclaw-channel",
                        " ",
                        "--max-cycles",
                        "1",
                    ]
                )


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class SpineWorkerRuntimeTests(unittest.TestCase):
    def test_observe_only_runner_blocks_work_without_fake_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"
            connection = connect(db_path)
            try:
                seed_demo_ledger(connection)
                result = run_spine_worker(
                    connection,
                    state_dir=state_dir,
                    runtime_mode="observe_only",
                    trace_id="spine-worker-observe-test",
                    max_cycles=1,
                    tick_interval_ms=1,
                    reconcile_interval_ms=1,
                    bindings=("openclaw",),
                    install_signal_handlers=False,
                )
                work = get_work_instance(connection, DEMO_WORK_INSTANCE_ID)
            finally:
                connection.close()

            paths = SpineWorkerPaths.from_state_dir(state_dir)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(work["status"], "eligible")
            self.assertFalse(paths.sends_path.exists())
            events = [json.loads(line) for line in paths.runner.events_path.read_text(encoding="utf-8").splitlines()]
            blocked = next(record for record in events if record["event"] == "work_item_blocked")
            self.assertEqual(blocked["reason"], "SIDE_EFFECTS_BLOCKED")

    def test_fake_runner_processes_seeded_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"
            connection = connect(db_path)
            try:
                seed_demo_ledger(connection)
                result = run_spine_worker(
                    connection,
                    state_dir=state_dir,
                    runtime_mode="active",
                    trace_id="spine-worker-fake-test",
                    max_cycles=1,
                    tick_interval_ms=1,
                    reconcile_interval_ms=1,
                    bindings=("openclaw",),
                    install_signal_handlers=False,
                )
                work = get_work_instance(connection, DEMO_WORK_INSTANCE_ID)
                attempt = get_side_effect_attempt(
                    connection,
                    f"openclaw-attempt-{DEMO_WORK_INSTANCE_ID}-1",
                )
            finally:
                connection.close()

            paths = SpineWorkerPaths.from_state_dir(state_dir)
            sends = [json.loads(line) for line in paths.sends_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.reason, "max_cycles_reached")
            self.assertEqual(work["status"], "succeeded")
            self.assertEqual(work["reason_code"], "openclaw_delivered")
            self.assertEqual(attempt["adapter_name"], "openclaw")
            self.assertEqual(attempt["attempt_status"], "succeeded")
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["event"], "openclaw_fake_send")
            self.assertEqual(sends[0]["channel_hint"], "whatsapp")

    def test_cli_can_initialize_empty_database_for_observe_only_trial(self) -> None:
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
                        "--initialize-schema",
                        "--mode",
                        "observe_only",
                        "--max-cycles",
                        "1",
                        "--tick-interval-ms",
                        "1",
                        "--reconcile-interval-ms",
                        "1",
                        "--trace-id",
                        "spine-worker-cli-test",
                        "--openclaw-channel",
                        "whatsapp",
                    ]
                )

            paths = SpineWorkerPaths.from_state_dir(state_dir)
            payload = json.loads(stream.getvalue())
            events = [json.loads(line) for line in paths.runner.events_path.read_text(encoding="utf-8").splitlines()]
            summary = next(record for record in events if record["event"] == "cycle_summary")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["runtime_mode"], "observe_only")
            self.assertEqual(payload["bindings"], "openclaw")
            self.assertEqual(payload["openclaw_channel"], "whatsapp")
            self.assertEqual(payload["openclaw_sender"], "fake")
            self.assertEqual(summary["items_scanned"], 0)


if __name__ == "__main__":
    unittest.main()
