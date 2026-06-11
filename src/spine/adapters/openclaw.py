"""OpenClaw-style notification adapter skeleton."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Mapping, Sequence

from spine.adapters.side_effects import (
    AttemptBackedSideEffectProcessor,
    AttemptBackedSideEffectRequest,
    NormalizedSideEffectResult,
    SideEffectBindingError,
    record_side_effect_result,
)
from spine.adapters.tickerd import WorkProcessingOutcome
from spine.ledger import get_current_item
from spine.ledger.common import require_utc_z, utc_z_from_datetime

OPENCLAW_ADAPTER_NAME = "openclaw"

OpenClawResultStatus = Literal["delivered", "failed_transient", "failed_permanent", "blocked"]
OpenClawSender = Callable[["OpenClawOutboundMessage"], "NormalizedOpenClawResult"]
OpenClawCommandRunner = Callable[..., subprocess.CompletedProcess[str]]

NON_VERIFIABLE_RECEIPT_LITERALS = {"none", "null", "n/a", "na", "placeholder", "synthetic"}
NON_VERIFIABLE_RECEIPT_PREFIXES = ("att-", "rcpt:att-", "local:")


class OpenClawBindingError(SideEffectBindingError):
    """Raised when the configured OpenClaw sender cannot be invoked."""


@dataclass(frozen=True)
class OpenClawOutboundMessage:
    """Spine outbound message envelope for the OpenClaw replacement path."""

    delivery_id: str
    attempt_id: str
    trace_id: str
    causation_id: str
    channel_hint: str
    target_ref: str
    body_text: str
    dedupe_key: str
    created_at_utc: str

    def request_envelope(self) -> dict[str, str]:
        return {
            "payload_version": "spine.openclaw.outbound.v1",
            "delivery_id": self.delivery_id,
            "attempt_id": self.attempt_id,
            "trace_id": self.trace_id,
            "causation_id": self.causation_id,
            "channel_hint": self.channel_hint,
            "target_ref": self.target_ref,
            "body_text": self.body_text,
            "dedupe_key": self.dedupe_key,
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True)
class OpenClawGatewayConfig:
    """Runtime configuration for the OpenClaw gateway CLI binding."""

    command: str = "openclaw"
    gateway_url: str | None = None
    gateway_token: str | None = None
    gateway_password: str | None = None
    gateway_timeout_ms: int = 10000
    retry_delay_seconds: int = 300

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "OpenClawGatewayConfig":
        source = env or os.environ
        timeout_raw = _env_first(source, "SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS", "KINFLOW_GATEWAY_TIMEOUT_MS") or "10000"
        retry_raw = _env_first(source, "SPINE_OPENCLAW_RETRY_DELAY_SECONDS") or "300"
        return cls(
            command=_env_first(source, "SPINE_OPENCLAW_COMMAND") or "openclaw",
            gateway_url=_env_first(source, "SPINE_OPENCLAW_GATEWAY_URL", "KINFLOW_GATEWAY_URL"),
            gateway_token=_env_first(source, "SPINE_OPENCLAW_GATEWAY_TOKEN", "KINFLOW_GATEWAY_TOKEN"),
            gateway_password=_env_first(source, "SPINE_OPENCLAW_GATEWAY_PASSWORD", "KINFLOW_GATEWAY_PASSWORD"),
            gateway_timeout_ms=int(timeout_raw),
            retry_delay_seconds=int(retry_raw),
        )


@dataclass(frozen=True)
class OpenClawGatewaySender:
    """OpenClaw gateway CLI sender used only when an operator opts into real sends."""

    config: OpenClawGatewayConfig
    command_runner: OpenClawCommandRunner = subprocess.run

    def __call__(self, message: OpenClawOutboundMessage) -> NormalizedOpenClawResult:
        blocked = _validate_gateway_message(message, self.config)
        if blocked is not None:
            return blocked

        params = {
            "channel": message.channel_hint.strip().lower(),
            "to": message.target_ref.strip(),
            "message": message.body_text,
            "idempotencyKey": message.dedupe_key.strip(),
        }
        cmd = build_openclaw_gateway_command(self.config, params)
        try:
            completed = self.command_runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.gateway_timeout_ms / 1000,
            )
        except FileNotFoundError as exc:
            raise OpenClawBindingError("openclaw command unavailable") from exc
        except subprocess.TimeoutExpired:
            return NormalizedOpenClawResult.transient_failure(
                reason_code="openclaw_gateway_timeout",
                next_attempt_at_utc=_plus_seconds(message.created_at_utc, self.config.retry_delay_seconds),
            )

        if completed.returncode != 0:
            return _normalize_gateway_failure_response(
                stderr=completed.stderr,
                stdout=completed.stdout,
                created_at_utc=message.created_at_utc,
                retry_delay_seconds=self.config.retry_delay_seconds,
            )

        try:
            payload = json.loads((completed.stdout or "").strip())
        except json.JSONDecodeError:
            return NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_response_unmappable")
        if not isinstance(payload, dict):
            return NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_response_unmappable")

        provider_ref = _extract_provider_ref(payload)
        if not _provider_ref_transport_meaningful(provider_ref):
            return NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_accepted_unverified")
        return NormalizedOpenClawResult.delivered(provider_ref=provider_ref)


@dataclass(frozen=True)
class NormalizedOpenClawResult:
    """Normalized OpenClaw send result used before a real host binding exists."""

    status: OpenClawResultStatus
    reason_code: str
    provider_ref: str | None = None
    next_attempt_at_utc: str | None = None

    @classmethod
    def delivered(cls, *, provider_ref: str, reason_code: str = "openclaw_delivered") -> "NormalizedOpenClawResult":
        return cls("delivered", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def transient_failure(cls, *, reason_code: str, next_attempt_at_utc: str) -> "NormalizedOpenClawResult":
        return cls("failed_transient", reason_code=reason_code, next_attempt_at_utc=next_attempt_at_utc)

    @classmethod
    def permanent_failure(cls, *, reason_code: str, provider_ref: str | None = None) -> "NormalizedOpenClawResult":
        return cls("failed_permanent", reason_code=reason_code, provider_ref=provider_ref)

    @classmethod
    def blocked(cls, *, reason_code: str) -> "NormalizedOpenClawResult":
        return cls("blocked", reason_code=reason_code)


def build_openclaw_gateway_command(config: OpenClawGatewayConfig, params: Mapping[str, object]) -> list[str]:
    """Build the OpenClaw gateway CLI invocation without executing it."""

    cmd = [
        config.command,
        "gateway",
        "call",
        "send",
        "--timeout",
        str(config.gateway_timeout_ms),
        "--params",
        json.dumps(dict(params), sort_keys=True),
        "--json",
    ]
    if config.gateway_url:
        cmd[4:4] = ["--url", config.gateway_url]
    if config.gateway_token:
        cmd.extend(["--token", config.gateway_token])
    if config.gateway_password:
        cmd.extend(["--password", config.gateway_password])
    return cmd


@dataclass(frozen=True)
class OpenClawNotificationProcessor:
    """Active Tickerd processor that sends reminder work through an OpenClaw-style sender."""

    sender: OpenClawSender
    channel_hint: str = "openclaw_auto"

    def __call__(self, connection: sqlite3.Connection, work_row: Mapping[str, object], envelope: Any) -> WorkProcessingOutcome:
        processor: AttemptBackedSideEffectProcessor[OpenClawOutboundMessage] = AttemptBackedSideEffectProcessor(
            adapter_name=OPENCLAW_ADAPTER_NAME,
            build_request=lambda request_connection, request_work_row, request_envelope: build_openclaw_side_effect_request(
                request_connection,
                work_row=request_work_row,
                envelope=request_envelope,
                channel_hint=self.channel_hint,
            ),
            sender=lambda outbound: normalize_openclaw_result(self.sender(outbound)),
            binding_error_type=OpenClawBindingError,
            binding_failure_reason_code="openclaw_binding_failed",
            send_exception_reason_code="openclaw_send_exception",
            missing_retry_reason_code="openclaw_missing_retry_at",
        )
        return processor(connection, work_row, envelope)


def build_openclaw_side_effect_request(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    envelope: Any,
    channel_hint: str = "openclaw_auto",
) -> AttemptBackedSideEffectRequest[OpenClawOutboundMessage]:
    """Build the generic attempt-backed request for an OpenClaw outbound message."""

    outbound = build_openclaw_outbound_message(
        connection,
        work_row=work_row,
        trace_id=str(envelope.trace_id),
        causation_id=str(envelope.causation_id),
        created_at_utc=_utc_z(envelope.actual_start_ts),
        channel_hint=channel_hint,
    )
    return AttemptBackedSideEffectRequest(
        message=outbound,
        attempt_id=outbound.attempt_id,
        work_instance_id=outbound.delivery_id,
        idempotency_key=outbound.dedupe_key,
        request_envelope=outbound.request_envelope(),
        attempted_at_utc=outbound.created_at_utc,
    )


def build_openclaw_outbound_message(
    connection: sqlite3.Connection,
    *,
    work_row: Mapping[str, object],
    trace_id: str,
    causation_id: str,
    created_at_utc: str,
    channel_hint: str = "openclaw_auto",
) -> OpenClawOutboundMessage:
    """Map Spine reminder work into an OpenClaw-style outbound message."""

    require_utc_z("created_at_utc", created_at_utc)
    item = get_current_item(connection, str(work_row["item_id"]))
    work_instance_id = str(work_row["work_instance_id"])
    attempt_count = str(work_row["attempt_count"])
    target_ref = str(work_row.get("work_subject_ref") or "")
    title = str(item["version"]["title"])  # type: ignore[index]
    return OpenClawOutboundMessage(
        delivery_id=work_instance_id,
        attempt_id=f"openclaw-attempt-{work_instance_id}-{attempt_count}",
        trace_id=trace_id,
        causation_id=causation_id,
        channel_hint=channel_hint,
        target_ref=target_ref,
        body_text=f"Reminder: {title}",
        dedupe_key=f"openclaw:{work_instance_id}:{attempt_count}",
        created_at_utc=created_at_utc,
    )


def record_openclaw_result(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    result: NormalizedOpenClawResult,
    completed_at_utc: str,
) -> WorkProcessingOutcome:
    """Persist normalized OpenClaw result and return the matching Spine work outcome."""

    return record_side_effect_result(
        connection,
        attempt_id=attempt_id,
        result=normalize_openclaw_result(result),
        completed_at_utc=completed_at_utc,
        missing_retry_reason_code="openclaw_missing_retry_at",
    )


def normalize_openclaw_result(result: NormalizedOpenClawResult) -> NormalizedSideEffectResult:
    """Translate OpenClaw-shaped outcomes into provider-neutral side-effect outcomes."""

    if result.status == "delivered":
        return NormalizedSideEffectResult.succeeded(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    if result.status == "failed_transient":
        return NormalizedSideEffectResult.retry(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
            next_attempt_at_utc=result.next_attempt_at_utc or "",
        )
    if result.status == "failed_permanent":
        return NormalizedSideEffectResult.failed(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    if result.status == "blocked":
        return NormalizedSideEffectResult.cancelled(
            reason_code=result.reason_code,
            provider_ref=result.provider_ref,
        )
    raise ValueError(f"unknown OpenClaw result status: {result.status}")


def _utc_z(value: datetime) -> str:
    return utc_z_from_datetime(value)


def _env_first(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return None


def _validate_gateway_message(
    message: OpenClawOutboundMessage,
    config: OpenClawGatewayConfig,
) -> NormalizedOpenClawResult | None:
    if not message.channel_hint.strip():
        return NormalizedOpenClawResult.blocked(reason_code="openclaw_channel_unresolved")
    if not message.target_ref.strip():
        return NormalizedOpenClawResult.blocked(reason_code="openclaw_destination_unresolved")
    if not message.dedupe_key.strip():
        return NormalizedOpenClawResult.blocked(reason_code="openclaw_idempotency_unresolved")
    if config.gateway_url and not (config.gateway_token or config.gateway_password):
        return NormalizedOpenClawResult.blocked(reason_code="openclaw_gateway_auth_unresolved")
    return None


def _normalize_gateway_failure_response(
    *,
    stderr: str | None,
    stdout: str | None,
    created_at_utc: str,
    retry_delay_seconds: int,
) -> NormalizedOpenClawResult:
    message = (stderr or stdout or "gateway call failed").strip()
    lowered = message.lower()
    if "timeout" in lowered or "timed out" in lowered or "unavailable" in lowered or "rate" in lowered:
        return NormalizedOpenClawResult.transient_failure(
            reason_code="openclaw_gateway_transient",
            next_attempt_at_utc=_plus_seconds(created_at_utc, retry_delay_seconds),
        )
    if "blocked" in lowered or "policy" in lowered:
        return NormalizedOpenClawResult.blocked(reason_code="openclaw_gateway_blocked")
    if "auth" in lowered or "invalid request" in lowered or "unsupported" in lowered or "unknown target" in lowered:
        return NormalizedOpenClawResult.permanent_failure(reason_code="openclaw_gateway_permanent")
    return NormalizedOpenClawResult.transient_failure(
        reason_code="openclaw_gateway_transient",
        next_attempt_at_utc=_plus_seconds(created_at_utc, retry_delay_seconds),
    )


def _extract_provider_ref(payload: Mapping[str, object]) -> str | None:
    for candidate in _provider_ref_candidates(payload):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _provider_ref_candidates(payload: Mapping[str, object]) -> Sequence[object]:
    candidates: list[object] = []
    for key in ("messageId", "id", "receipt", "ref"):
        if key in payload:
            candidates.append(payload[key])
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, Mapping):
        nested_result = nested_payload.get("result")
        if isinstance(nested_result, Mapping):
            for key in ("messageId", "id", "receipt", "ref"):
                if key in nested_result:
                    candidates.append(nested_result[key])
        for key in ("messageId", "id", "receipt", "ref"):
            if key in nested_payload:
                candidates.append(nested_payload[key])
    return tuple(candidates)


def _provider_ref_transport_meaningful(provider_ref: str | None) -> bool:
    if provider_ref is None:
        return False
    token = provider_ref.strip()
    if not token:
        return False
    lowered = token.lower()
    if lowered in NON_VERIFIABLE_RECEIPT_LITERALS:
        return False
    return not lowered.startswith(NON_VERIFIABLE_RECEIPT_PREFIXES)


def _plus_seconds(created_at_utc: str, seconds: int) -> str:
    require_utc_z("created_at_utc", created_at_utc)
    value = created_at_utc
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    return _utc_z(parsed + timedelta(seconds=seconds))
