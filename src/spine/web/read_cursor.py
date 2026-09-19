"""Internal v2 cursor codec. Independent of v1, with no route activation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.web.read_contracts import read_error, utc_datetime

CURSOR = "spine.trusted-web-cursor.v2"
DOMAIN = CURSOR.encode("ascii") + b"\0"
SCHEMA = "trusted-web-read-cursor.schema.json"
MAX_TOKEN_BYTES = 8192
IDENTITY_FIELDS = (
    "ledger_id", "realm_id", "recovery_epoch", "account_id", "account_revision",
    "subject_id", "subject_revision", "account_subject_binding_revision", "selection_id", "access_epoch",
)
SUBJECT_FIELDS = ("subject_id", "subject_kind", "display_name", "status", "created_at_utc", "updated_at_utc")


def cursor_identity(identity):
    """A content revision, not a persisted or monotonically increasing counter.

    Only the selected subject's closed canonical row participates. The retained
    private proof still compares the complete row, including any future columns.
    """
    subject = {field: identity["subject"][field] for field in SUBJECT_FIELDS}
    revision = str(1 + int(hash_canonical_json({"contract_version": "spine.trusted-web-subject-revision.v1", "subject": subject}), 16))
    return {
        **{field: str(identity[field]) for field in IDENTITY_FIELDS
           if field not in {"subject_revision", "account_subject_binding_revision"}},
        "subject_revision": revision,
        "account_subject_binding_revision": str(identity["binding_revision"]),
    }


def service_time(value):
    try:
        if not isinstance(value, str) or not utc_datetime(value):
            raise ValueError
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise read_error("admission_unavailable") from exc


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _b64(raw) != value:
        raise ValueError
    return raw


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class CursorCodec:
    def __init__(self, contracts, *, key=None):
        self.contracts = contracts
        self._key = secrets.token_bytes(32) if key is None else key
        fixture_key = contracts.artifacts["trusted-web-read-cursor-vectors.v2.json"]["public_test_key"].encode("utf-8")
        if not isinstance(self._key, bytes) or len(self._key) < 32 or hmac.compare_digest(self._key, fixture_key):
            raise read_error("admission_unavailable")

    def encode(self, payload):
        self.contracts.validate(SCHEMA, payload, output=True)
        self.check_times(payload, payload["issued_at_utc"])
        raw = canonical_json_bytes(payload)
        token = "v2." + _b64(raw) + "." + _b64(hmac.digest(self._key, DOMAIN + raw, hashlib.sha256))
        if len(token) > MAX_TOKEN_BYTES:
            raise read_error("capacity_exceeded")
        return token

    def decode(self, token, *, now):
        try:
            if not isinstance(token, str) or len(token) > MAX_TOKEN_BYTES or not token.isascii():
                raise ValueError
            version, encoded, signature = token.split(".")
            if version != "v2":
                raise ValueError
            raw, mac = _unb64(encoded), _unb64(signature)
            if not hmac.compare_digest(mac, hmac.digest(self._key, DOMAIN + raw, hashlib.sha256)):
                raise ValueError
            # Authenticate the exact bytes before interpreting JSON or any field.
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
            if canonical_json_bytes(payload) != raw:
                raise ValueError
        except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError, SpineValidationError) as exc:
            raise read_error("invalid_request") from exc
        self.contracts.validate(SCHEMA, payload)
        self.check_times(payload, now)
        return payload

    def check_times(self, payload, now):
        current = service_time(now)
        issued, expires, evaluated = (datetime.fromisoformat(payload[k]) for k in (
            "issued_at_utc", "expires_at_utc", "authorization_evaluated_at_utc",
        ))
        if not evaluated <= issued < expires <= issued + timedelta(seconds=self.contracts.bounds["cursor_seconds_max"]):
            raise read_error("invalid_request")
        deadline = payload["authorization_valid_until_utc"]
        if deadline is not None and datetime.fromisoformat(deadline) <= evaluated:
            raise read_error("invalid_request")
        if current < issued or current >= expires or (deadline is not None and current >= datetime.fromisoformat(deadline)):
            raise read_error("access_changed")
