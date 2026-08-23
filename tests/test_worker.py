import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spine.commands import CommandContext, handle
from spine.ledger import connect, get_side_effect_attempt, get_work_instance, initialize_schema
from spine.runtime.seed_demo import seed_demo_ledger
from spine.runtime.worker import SpineWorkerPaths, main, run_spine_worker

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

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["--db", str(db_path), "--state-dir", str(state_dir), "--max-cycles", "1"])

            self.assertEqual(exit_code, 3)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["reason"], "ledger_runtime_preflight_failed")
            health = json.loads((state_dir / "health.json").read_text(encoding="utf-8"))
            self.assertEqual(health["state"], "DOWN")
            self.assertFalse(health["is_ready"])

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
                seeded = seed_demo_ledger(connection)
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
                work = get_work_instance(connection, str(seeded["work_instance_id"]))
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
                seeded = seed_demo_ledger(connection)
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
                work_id = str(seeded["work_instance_id"])
                work = get_work_instance(connection, work_id)
                attempt_row = connection.execute(
                    "SELECT attempt_id FROM side_effect_attempts WHERE work_instance_id = ?",
                    (work_id,),
                ).fetchone()
                self.assertIsNotNone(attempt_row)
                attempt = get_side_effect_attempt(connection, attempt_row["attempt_id"])
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

    def test_fake_runner_delivers_all_reminders_attached_to_one_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "spine.sqlite"
            state_dir = root / "state"
            connection = connect(db_path)
            try:
                initialize_schema(connection)
                base_context = CommandContext(ledger=connection)
                self.assertTrue(
                    handle(
                        "subject.upsert",
                        {
                            "command_id": "cmd-worker-multi-agent",
                            "actor_subject_id": "worker-multi-agent",
                            "subject_id": "worker-multi-agent",
                            "subject_kind": "agent",
                            "display_name": "Worker multi agent",
                            "status": "active",
                            "updated_at_utc": "2026-07-19T10:00:00Z",
                        },
                        base_context,
                    )["ok"]
                )
                self.assertTrue(
                    handle(
                        "subject_group.upsert",
                        {
                            "command_id": "cmd-worker-multi-group",
                            "actor_subject_id": "worker-multi-agent",
                            "group_id": "worker-multi-group",
                            "group_kind": "transport_group",
                            "display_name": "Worker multi group",
                            "updated_at_utc": "2026-07-19T10:01:00Z",
                        },
                        base_context,
                    )["ok"]
                )
                self.assertTrue(
                    handle(
                        "delivery_target.upsert",
                        {
                            "command_id": "cmd-worker-multi-target",
                            "actor_subject_id": "worker-multi-agent",
                            "delivery_target_id": "worker-multi-target",
                            "owner_kind": "subject_group",
                            "owner_group_id": "worker-multi-group",
                            "channel": "whatsapp",
                            "adapter_name": "openclaw",
                            "target_ref": "worker-multi@g.us",
                            "updated_at_utc": "2026-07-19T10:02:00Z",
                        },
                        base_context,
                    )["ok"]
                )
                event = handle(
                    "event.create",
                    {
                        "command_id": "cmd-worker-multi-event",
                        "actor_subject_id": "worker-multi-agent",
                        "created_at_utc": "2026-07-19T10:03:00Z",
                        "title": "Multi reminder canary",
                        "all_day": False,
                        "start_anchor": {
                            "anchor_kind": "instant_utc",
                            "utc_instant": "2026-07-21T12:00:00Z",
                        },
                    },
                    base_context,
                )
                reminders = []
                for index, eligible_at in enumerate(
                    (
                        "2026-07-19T11:45:00Z",
                        "2026-07-19T11:50:00Z",
                        "2026-07-19T11:55:00Z",
                        "2026-07-19T12:00:00Z",
                    ),
                    start=1,
                ):
                    reminders.append(
                        handle(
                            "reminder.create",
                            {
                                "command_id": f"cmd-worker-multi-reminder-{index}",
                                "actor_subject_id": "worker-multi-agent",
                                "item_id": event["item_id"],
                                "target_version": index,
                                "created_at_utc": f"2026-07-19T10:0{index + 3}:00Z",
                                "recipient_kind": "subject_group",
                                "recipient_group_id": "worker-multi-group",
                                "delivery_target_id": "worker-multi-target",
                                "channel": "whatsapp",
                                "notification": {
                                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                                    "target": {
                                        "anchor_role": "event_start",
                                        "application_scope": "item",
                                    },
                                    "schedule": {
                                        "kind": "once",
                                        "at": {"kind": "absolute_utc", "at_utc": eligible_at},
                                    },
                                    "late_handling": {
                                        "kind": "deliver_within",
                                        "grace_seconds": "86400",
                                    },
                                },
                            },
                            base_context,
                        )
                    )
                materialized = handle(
                    "notification_work.materialize",
                    {
                        "command_id": "cmd-worker-multi-materialize",
                        "actor_subject_id": "worker-multi-agent",
                        "item_id": event["item_id"],
                        "target_version": "5",
                        "materialized_at_utc": "2026-07-19T10:08:00Z",
                        "range_start_utc": "2026-07-19T11:00:00Z",
                        "range_end_utc": "2026-07-19T13:00:00Z",
                        "limit": "100",
                    },
                    base_context,
                )
                self.assertTrue(materialized["ok"], materialized)

                result = run_spine_worker(
                    connection,
                    state_dir=state_dir,
                    runtime_mode="active",
                    trace_id="spine-worker-multi-reminder-test",
                    max_cycles=1,
                    tick_interval_ms=1,
                    reconcile_interval_ms=1,
                    bindings=("openclaw",),
                    install_signal_handlers=False,
                )
                work_rows = [
                    get_work_instance(connection, work_id)
                    for work_id in materialized["created_work_instance_ids"]
                ]
            finally:
                connection.close()

            paths = SpineWorkerPaths.from_state_dir(state_dir)
            sends = [json.loads(line) for line in paths.sends_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(all(response["ok"] and response["created"] for response in reminders))
            self.assertEqual({row["item_version"] for row in work_rows}, {5})
            self.assertTrue(all(row["status"] == "succeeded" and row["attempt_count"] == 1 for row in work_rows))
            self.assertEqual(len(sends), 4)
            self.assertEqual({send["target_ref"] for send in sends}, {"worker-multi@g.us"})

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
