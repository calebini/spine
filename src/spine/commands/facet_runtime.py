"""Bounded local facet execution and protected cursor configuration.

Configuration is supplied by the adapter, never by a command payload. It is not
executor authentication. The dedicated web adapter supplies permission-enforced
context and access proofs; it does not use the trusted-local OS identity binding.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import sqlite3
import stat
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.facets import parse_object


def failure(code: str, field: str, message: str = "facet request could not complete") -> NoReturn:
    raise SpineValidationError(f"{code}:{field}", message)


@dataclass
class FacetBudget:
    """One budget survives snapshot evaluation, release checks and finalization."""

    started: float = field(default_factory=time.monotonic)
    steps: int = 0
    resources: set[tuple[str, str]] = field(default_factory=set)

    def check(self) -> None:
        if self.steps > 100_000 or time.monotonic() - self.started >= 5:
            failure("environment_failure", "capacity", "facet operation capacity exceeded")

    def progress(self) -> int:
        self.steps += 100
        return int(self.steps > 100_000 or time.monotonic() - self.started >= 5)

    def resolve(self, kind: str, identity: str) -> None:
        self.resources.add((kind, identity))
        if len(self.resources) > 100:
            failure("environment_failure", "capacity", "facet resource capacity exceeded")
        self.check()


@dataclass(frozen=True)
class FacetCursorConfig:
    secret: bytes
    ledger_id: str
    generation: str

    def validate(self) -> None:
        if (
            not isinstance(self.secret, bytes)
            or len(self.secret) < 32
            or not isinstance(self.ledger_id, str)
            or not self.ledger_id
            or not isinstance(self.generation, str)
            or not self.generation
        ):
            failure("environment_failure", "cursor_config", "protected facet cursor configuration required")

    def digest(self, domain: str, value: object) -> str:
        return hmac.new(self.secret, canonical_json_bytes({"contract_version": domain, "value": value}), hashlib.sha256).hexdigest()

    def bindings(self) -> tuple[str, str]:
        principal = {"os_uid": str(os.getuid())}
        context = self.digest(
            "spine.facet-cursor-context.v1",
            {
                "mode": "trusted_local",
                "cursor_ledger_id": self.ledger_id,
                "cursor_generation": self.generation,
                "principal": principal,
            },
        )
        access = self.digest(
            "spine.facet-cursor-access.v1",
            {
                "mode": "trusted_local",
                "identity": principal,
                "memberships": [],
                "grants": [],
                "deployment_access_mode": "trusted_local",
            },
        )
        return context, access


def load_cursor_config(path: str) -> FacetCursorConfig:
    """Read an operator-owned, non-symlink, private regular file; never provision it."""
    try:
        descriptor = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()} or info.st_mode & 0o077:
                raise ValueError("permissions")
            value = parse_object(stream.read(8193).decode("utf-8"), maximum=8192)
        if set(value) != {"secret_hex", "cursor_ledger_id", "cursor_generation"}:
            raise ValueError("shape")
        secret = value["secret_hex"]
        if not isinstance(secret, str) or not re.fullmatch(r"[0-9a-f]{64,256}", secret):
            raise ValueError("key")
        config = FacetCursorConfig(bytes.fromhex(secret), value["cursor_ledger_id"], value["cursor_generation"])
        config.validate()
        return config
    except (OSError, ValueError, TypeError, SpineValidationError) as exc:
        raise SpineValidationError("environment_failure:cursor_config", "protected facet cursor configuration unavailable") from exc


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("encoding")
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise ValueError("encoding")
    return decoded


def encode_cursor(config: FacetCursorConfig, payload: dict[str, Any]) -> str:
    raw = canonical_json_bytes(payload)
    mac = hmac.new(config.secret, b"spine.facet-cursor.v1\0" + raw, hashlib.sha256).digest()
    token = f"fc1.{_encode(raw)}.{_encode(mac)}"
    if len(token) > 4096:
        failure("environment_failure", "capacity")
    return token


def decode_cursor(config: FacetCursorConfig, token: object) -> dict[str, Any]:
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError("token")
        prefix, body, signature = token.split(".")
        if prefix != "fc1":
            raise ValueError("prefix")
        raw, mac = _decode(body), _decode(signature)
        expected = hmac.new(config.secret, b"spine.facet-cursor.v1\0" + raw, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("mac")
        payload = parse_object(raw.decode("utf-8"), maximum=4096)
        required = {
            "contract_version",
            "command",
            "context_hash",
            "query_hash",
            "access_hash",
            "source_snapshot_hash",
            "issued_at_utc",
            "expires_at_utc",
            "authorization_valid_until_utc",
            "last_key",
        }
        if set(payload) != required or canonical_json_bytes(payload) != raw or payload["contract_version"] != "spine.facet-cursor.v1":
            raise ValueError("shape")
        if payload["command"] not in {"facet_schema.list", "item_archetype.facet_binding.list", "item.facets.query"}:
            raise ValueError("command")
        for k in ("context_hash", "query_hash", "access_hash", "source_snapshot_hash"):
            if not isinstance(payload[k], str) or not re.fullmatch(r"[0-9a-f]{64}", payload[k]):
                raise ValueError("hash")
        if not isinstance(payload["last_key"], str) or not payload["last_key"]:
            raise ValueError("key")
        if payload["command"] == "item_archetype.facet_binding.list" and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", payload["last_key"]):
            raise ValueError("key")
        issued, expires = parse_time(payload["issued_at_utc"]), parse_time(payload["expires_at_utc"])
        if expires != issued + timedelta(seconds=900):
            raise ValueError("expiry")
        deadline = payload["authorization_valid_until_utc"]
        if deadline is not None and parse_time(deadline) <= issued:
            raise ValueError("deadline")
        return payload
    except (ValueError, TypeError, KeyError, binascii.Error, SpineValidationError) as exc:
        raise SpineValidationError("invalid_request:cursor", "invalid facet cursor") from exc


def parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise ValueError("timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def wire_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def install_budget(db: sqlite3.Connection, budget: FacetBudget) -> int:
    old_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
    db.execute(f"PRAGMA busy_timeout={min(old_timeout, 2000)}")
    db.set_progress_handler(budget.progress, 100)
    return int(old_timeout)
