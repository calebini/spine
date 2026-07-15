import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawBindingError,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawOutboundMessage,
    build_openclaw_gateway_command,
)
from spine.runtime.openclaw_smoke import main

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False


class OpenClawGatewaySenderTests(unittest.TestCase):
    def test_build_gateway_command_uses_gateway_call_send(self) -> None:
        config = OpenClawGatewayConfig(
            gateway_url="https://gateway.example",
            gateway_token="token-1",
            gateway_timeout_ms=12000,
        )

        cmd = build_openclaw_gateway_command(
            config,
            {
                "channel": "whatsapp",
                "to": "120363425701060269@g.us",
                "message": "Reminder",
                "idempotencyKey": "idem-1",
            },
        )

        self.assertEqual(cmd[:6], ["openclaw", "gateway", "call", "send", "--url", "https://gateway.example"])
        self.assertIn("--token", cmd)
        params = json.loads(cmd[cmd.index("--params") + 1])
        self.assertEqual(params["channel"], "whatsapp")
        self.assertEqual(params["to"], "120363425701060269@g.us")
        self.assertEqual(params["idempotencyKey"], "idem-1")
        self.assertEqual(cmd[cmd.index("--timeout") + 1], "12000")

    def test_gateway_config_reads_distinct_command_timeout_from_env(self) -> None:
        config = OpenClawGatewayConfig.from_env(
            {
                "SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS": "12000",
                "SPINE_OPENCLAW_COMMAND_TIMEOUT_MS": "19000",
                "SPINE_OPENCLAW_RETRY_DELAY_SECONDS": "60",
            }
        )

        self.assertEqual(config.gateway_timeout_ms, 12000)
        self.assertEqual(config.command_timeout_ms, 19000)
        self.assertEqual(config.retry_delay_seconds, 60)

    def test_gateway_sender_delivers_with_transport_meaningful_receipt(self) -> None:
        calls = []
        timeouts = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            timeouts.append(kwargs["timeout"])
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": "wamid.real"}), stderr="")

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(gateway_timeout_ms=12000, command_timeout_ms=19000),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "delivered")
        self.assertEqual(result.reason_code, "openclaw_delivered")
        self.assertEqual(result.provider_ref, "wamid.real")
        params = json.loads(calls[0][calls[0].index("--params") + 1])
        self.assertEqual(params["message"], "Reminder")
        self.assertEqual(calls[0][calls[0].index("--timeout") + 1], "12000")
        self.assertEqual(timeouts, [19.0])

    def test_gateway_sender_defaults_command_timeout_with_gateway_headroom(self) -> None:
        timeouts = []

        def runner(cmd, **kwargs):
            timeouts.append(kwargs["timeout"])
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": "wamid.real"}), stderr="")

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(gateway_timeout_ms=12000),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "delivered")
        self.assertEqual(timeouts, [17.0])

    def test_gateway_sender_enforces_command_timeout_headroom(self) -> None:
        timeouts = []

        def runner(cmd, **kwargs):
            timeouts.append(kwargs["timeout"])
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": "wamid.real"}), stderr="")

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(gateway_timeout_ms=12000, command_timeout_ms=12000),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "delivered")
        self.assertEqual(timeouts, [17.0])

    def test_gateway_sender_maps_subprocess_timeout_to_cli_timeout_reason(self) -> None:
        def runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(gateway_timeout_ms=12000, command_timeout_ms=19000, retry_delay_seconds=60),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "failed_transient")
        self.assertEqual(result.reason_code, "openclaw_gateway_cli_timeout")
        self.assertEqual(result.next_attempt_at_utc, "2026-06-07T10:01:00Z")

    def test_gateway_sender_fails_closed_on_non_verifiable_receipt(self) -> None:
        def runner(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": "rcpt:att-local"}), stderr="")

        result = OpenClawGatewaySender(OpenClawGatewayConfig(), command_runner=runner)(outbound_message())

        self.assertEqual(result.status, "failed_permanent")
        self.assertEqual(result.reason_code, "openclaw_accepted_unverified")

    def test_gateway_sender_maps_transient_gateway_failure_to_retry(self) -> None:
        def runner(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="gateway unavailable")

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(retry_delay_seconds=60),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "failed_transient")
        self.assertEqual(result.reason_code, "openclaw_gateway_transient")
        self.assertEqual(result.next_attempt_at_utc, "2026-06-07T10:01:00Z")

    def test_gateway_sender_maps_invalid_request_to_permanent_failure(self) -> None:
        def runner(cmd, **_kwargs):
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout='{"error":"INVALID_REQUEST","message":"unsupported channel: openclaw_auto"}',
                stderr="",
            )

        result = OpenClawGatewaySender(OpenClawGatewayConfig(), command_runner=runner)(outbound_message())

        self.assertEqual(result.status, "failed_permanent")
        self.assertEqual(result.reason_code, "openclaw_gateway_permanent")

    def test_gateway_sender_blocks_gateway_url_without_credentials(self) -> None:
        calls = 0

        def runner(cmd, **_kwargs):
            nonlocal calls
            calls += 1
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"messageId": "wamid.real"}), stderr="")

        result = OpenClawGatewaySender(
            OpenClawGatewayConfig(gateway_url="https://gateway.example"),
            command_runner=runner,
        )(outbound_message())

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason_code, "openclaw_gateway_auth_unresolved")
        self.assertEqual(calls, 0)

    def test_gateway_sender_raises_binding_error_when_openclaw_command_is_missing(self) -> None:
        def runner(_cmd, **_kwargs):
            raise FileNotFoundError("openclaw")

        with self.assertRaises(OpenClawBindingError):
            OpenClawGatewaySender(OpenClawGatewayConfig(), command_runner=runner)(outbound_message())


class OpenClawSmokeGatewayCliTests(unittest.TestCase):
    def test_gateway_sender_requires_explicit_real_send_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(SystemExit, "--sender gateway requires --allow-real-send"):
                main(
                    [
                        "--db",
                        str(root / "spine.sqlite"),
                        "--state-dir",
                        str(root / "state"),
                        "--seed-demo",
                        "--sender",
                        "gateway",
                    ]
                )

    @unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
    def test_fake_sender_remains_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stream = StringIO()
            with redirect_stdout(stream):
                exit_code = main(
                    [
                        "--db",
                        str(root / "spine.sqlite"),
                        "--state-dir",
                        str(root / "state"),
                        "--seed-demo",
                        "--max-cycles",
                        "1",
                    ]
                )

        payload = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["sender"], "fake")


def outbound_message(**overrides) -> OpenClawOutboundMessage:
    payload = {
        "delivery_id": "delivery-1",
        "attempt_id": "attempt-1",
        "trace_id": "trace-1",
        "causation_id": "cause-1",
        "channel_hint": "whatsapp",
        "target_ref": "120363425701060269@g.us",
        "body_text": "Reminder",
        "dedupe_key": "idem-1",
        "created_at_utc": "2026-06-07T10:00:00Z",
    }
    payload.update(overrides)
    return OpenClawOutboundMessage(**payload)


if __name__ == "__main__":
    unittest.main()
