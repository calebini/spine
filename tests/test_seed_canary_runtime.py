import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spine.adapters import NormalizedOpenClawResult, OpenClawNotificationProcessor
from spine.ledger import connect, get_side_effect_attempt, get_work_instance
from spine.runtime.seed_canary import main, seed_canary_reminder
from spine.services import list_eligible_work, start_work


@dataclass(frozen=True)
class FakeEnvelope:
    trace_id: str = "trace-canary"
    causation_id: str = "ROOT:canary"
    actual_start_ts: datetime = datetime(2026, 6, 15, 20, 0, 1, tzinfo=UTC)


class SeedCanaryRuntimeTests(unittest.TestCase):
    def test_seed_canary_reminder_creates_eligible_work_and_preview(self) -> None:
        connection = connect()
        try:
            result = seed_canary_reminder(
                connection,
                target_ref="canary-target",
                title="Spine canary",
                prefix="canary-test",
                now_utc="2026-06-15T20:00:00Z",
                eligible_at_utc="2026-06-15T20:00:00Z",
            )

            work = get_work_instance(connection, str(result["work_instance_id"]))
            eligible = list_eligible_work(connection, now_utc="2026-06-15T20:00:01Z")
        finally:
            connection.close()

        preview = result["predicted_openclaw_envelope"]
        self.assertTrue(result["seeded"])
        self.assertEqual(work["status"], "eligible")
        self.assertEqual(work["attempt_count"], 0)
        self.assertEqual([row["work_instance_id"] for row in eligible], [result["work_instance_id"]])
        self.assertEqual(preview["target_ref"], "canary-target")
        self.assertEqual(preview["channel_hint"], "whatsapp")
        self.assertEqual(preview["body_text"], "Reminder: Spine canary")
        self.assertEqual(preview["dedupe_key"], f"openclaw:{result['work_instance_id']}:1")
        self.assertEqual(preview["attempt_id"], f"openclaw-attempt-{result['work_instance_id']}-1")

    def test_fake_openclaw_canary_uses_the_single_attempt_ledger(self) -> None:
        connection = connect()
        sent = []
        try:
            seeded = seed_canary_reminder(
                connection,
                target_ref="fake-target",
                title="Fake delivery canary",
                prefix="fake-send",
                now_utc="2026-06-15T20:00:00Z",
                eligible_at_utc="2026-06-15T20:00:00Z",
            )
            work_id = str(seeded["work_instance_id"])
            start_work(connection, work_instance_id=work_id, started_at_utc="2026-06-15T20:00:01Z")

            def sender(message):
                sent.append(message)
                return NormalizedOpenClawResult.delivered(provider_ref="fake-receipt-verified")

            outcome = OpenClawNotificationProcessor(sender=sender)(
                connection, get_work_instance(connection, work_id), FakeEnvelope()
            )
            attempt_id = f"openclaw-attempt-{work_id}-1"
            attempt = get_side_effect_attempt(connection, attempt_id)
        finally:
            connection.close()
        self.assertEqual(outcome.status, "succeeded")
        self.assertEqual(len(sent), 1)
        self.assertEqual(attempt["attempt_status"], "succeeded")
        self.assertEqual(attempt["provider_ref"], "fake-receipt-verified")

    def test_cli_prints_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "canary.sqlite"
            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main(
                    [
                        str(db_path),
                        "--target-ref",
                        "target-1",
                        "--title",
                        "Check the canary",
                        "--prefix",
                        "cli-canary",
                        "--now-utc",
                        "2026-06-15T20:00:00Z",
                    ]
                )
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["database"], str(db_path))
            self.assertTrue(payload["work_instance_id"].startswith("work_instance_"))
            self.assertEqual(payload["target_ref"], "target-1")
            self.assertEqual(payload["predicted_openclaw_envelope"]["channel_hint"], "whatsapp")
            self.assertEqual(payload["predicted_openclaw_envelope"]["body_text"], "Reminder: Check the canary")

    def test_cli_allows_channel_preview_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "canary.sqlite"
            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main(
                    [
                        str(db_path),
                        "--target-ref",
                        "target-1",
                        "--title",
                        "Check the canary",
                        "--prefix",
                        "channel-canary",
                        "--now-utc",
                        "2026-06-15T20:00:00Z",
                        "--openclaw-channel",
                        "whatsapp",
                    ]
                )
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["predicted_openclaw_envelope"]["channel_hint"], "whatsapp")

    def test_cli_if_absent_reuses_existing_canary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "canary.sqlite"
            connection = connect(db_path)
            try:
                seed_canary_reminder(
                    connection,
                    target_ref="target-1",
                    title="Original title",
                    prefix="repeat-canary",
                    now_utc="2026-06-15T20:00:00Z",
                )
            finally:
                connection.close()

            stream = StringIO()
            original_stdout = None
            try:
                import sys

                original_stdout = sys.stdout
                sys.stdout = stream
                exit_code = main(
                    [
                        str(db_path),
                        "--target-ref",
                        "target-1",
                        "--title",
                        "Ignored title",
                        "--prefix",
                        "repeat-canary",
                        "--now-utc",
                        "2026-06-15T20:01:00Z",
                        "--if-absent",
                    ]
                )
            finally:
                if original_stdout is not None:
                    sys.stdout = original_stdout

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertFalse(payload["seeded"])
            self.assertTrue(payload["work_instance_id"].startswith("work_instance_"))
            self.assertEqual(payload["predicted_openclaw_envelope"]["body_text"], "Reminder: Original title")

    def test_cli_refuses_existing_canary_without_if_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "canary.sqlite"
            connection = connect(db_path)
            try:
                seed_canary_reminder(
                    connection,
                    target_ref="target-1",
                    title="Original title",
                    prefix="repeat-canary",
                    now_utc="2026-06-15T20:00:00Z",
                )
            finally:
                connection.close()

            with self.assertRaisesRegex(SystemExit, "canary work already exists"):
                main(
                    [
                        str(db_path),
                        "--target-ref",
                        "target-1",
                        "--title",
                        "Ignored title",
                        "--prefix",
                        "repeat-canary",
                    ]
                )

    def test_cli_refuses_empty_target_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "canary.sqlite"

            with self.assertRaisesRegex(SystemExit, "target_ref must be non-empty"):
                main([str(db_path), "--target-ref", " ", "--title", "Canary"])


if __name__ == "__main__":
    unittest.main()
