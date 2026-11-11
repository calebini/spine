"""Pure recurring-task time, failure and protected-cursor primitives.

No command admission, ledger access, identity authority or external I/O lives here.
The caller supplies the existing cursor schema validator; this is not a new codec.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn, Protocol

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.recurring_tasks import CANONICAL, decode

CURSOR = "spine.recurring-related-tasks.cursor.v1"
PREFIX = "schedule.related_task_rule."


class CursorValidator(Protocol):
    """Narrow validation capability, without importing the command adapter."""

    def validate(
        self, resource: str, value: Any, *, definition: str | None = None, output: bool = False
    ) -> None: ...


def fail(code: str, field: str, message: str = "recurring-task request could not complete") -> NoReturn:
    raise SpineValidationError(code + ":" + field, message)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def wire(value: datetime) -> str:
    if value.tzinfo is None:
        fail("environment_failure", "clock")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _b64(raw) != value:
        raise ValueError("noncanonical base64url")
    return raw


def cursor_config(config: Any, ledger_id: str) -> None:
    if (
        config is None
        or not isinstance(getattr(config, "secret", None), bytes)
        or len(config.secret) < 32
        or getattr(config, "ledger_id", None) != ledger_id
        or not isinstance(getattr(config, "generation", None), str)
        or not config.generation
    ):
        fail("environment_failure", "cursor_configuration")


def sign_cursor(config: Any, payload: dict[str, Any], contracts: CursorValidator) -> str:
    cursor_config(config, payload["query"]["ledger_instance_id"])
    contracts.validate("cursor", payload, output=True)
    raw = canonical_json_bytes(payload)
    tag = hmac.new(config.secret, CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()
    return _b64(raw) + "." + _b64(tag)


def verify_cursor(
    config: Any, token: str, query: dict[str, Any], purpose: str, now: str, catalog: str, contracts: CursorValidator
) -> dict[str, Any]:
    cursor_config(config, query["ledger_instance_id"])
    try:
        body, tag = token.split(".")
        raw, mac = _unb64(body), _unb64(tag)
        if not hmac.compare_digest(mac, hmac.new(config.secret, CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()):
            raise ValueError("signature")
        payload = decode(raw.decode("utf-8"))
        contracts.validate("cursor", payload)
        if payload["key_id"] != config.generation or payload["purpose"] != purpose or payload["query"] != query:
            raise ValueError("binding")
        if instant(payload["expires_at_utc"]) != instant(payload["issued_at_utc"]) + timedelta(seconds=3600):
            raise ValueError("lifetime")
    except (ValueError, UnicodeError, SpineValidationError, KeyError, TypeError) as exc:
        raise SpineValidationError("invalid_request:cursor", "invalid recurring-task cursor") from exc
    if payload["catalog_generation"] != catalog or instant(now) >= instant(payload["expires_at_utc"]):
        fail("stale_cursor", "cursor")
    return payload


def cursor_payload(config: Any, *, purpose: str, query: dict[str, Any], catalog: str, now: str, after: Any) -> dict[str, Any]:
    cursor_config(config, query["ledger_instance_id"])
    return {
        "cursor_version": CURSOR,
        "canonical_json_version": CANONICAL,
        "key_id": config.generation,
        "purpose": purpose,
        "query": query,
        "catalog_generation": catalog,
        "issued_at_utc": now,
        "expires_at_utc": wire(instant(now) + timedelta(seconds=3600)),
        "after": after,
    }
