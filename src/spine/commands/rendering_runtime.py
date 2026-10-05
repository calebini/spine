"""Protected configuration and bounded admission for internal rendering handlers."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from dataclasses import dataclass
from datetime import timedelta

from spine.commands.facet_runtime import _decode, _encode, parse_time, wire_time
from spine.core import rendering_definitions as codec
from spine.core.canonical_json import canonical_json_bytes
from spine.core.facets import parse_object
from spine.ledger.identity import read_ledger_instance_id
from spine.web.errors import WebError
from spine.web.permissions import Permissions


@dataclass(frozen=True)
class RenderingAdmission:
    """Adapter-supplied context, not a model-authored request identity."""

    mode: str = "trusted_local"
    account_id: str | None = None
    audience: str = "trusted_local_full_scope"

    def permissions(self, db, now, budget):
        if self.mode == "trusted_local" and self.account_id is None and self.audience == "trusted_local_full_scope":
            return None
        if self.mode != "permission_enforced" or not self.account_id or not self.audience:
            codec.fail("permission_denied", "admission")
        return RenderingPermissions(db, self.account_id, now, budget)


class RenderingPermissions(Permissions):
    def __init__(self, db, account, now, budget):
        self.budget = budget
        super().__init__(db, account, now)

    def touch(self, kind, resource, operation):
        self.budget.resolve(kind, resource)
        super().touch(kind, resource, operation)

    def rendering(self, identity, *, use=False, admin=False):
        self.touch("notification_rendering_definition", identity, "admin" if admin else "use" if use else "read")
        row = self.db.execute(
            "SELECT * FROM notification_rendering_definitions WHERE notification_rendering_definition_id=?", (identity,)
        ).fetchone()
        if row is None:
            raise WebError("resource_unavailable")
        value = dict(row)
        if admin:
            self.owner_admin(value)
        elif (
            not self.scope(value)
            and not self.grant("notification_rendering_definition", identity, 1, "catalog.use" if use else "catalog.read")
            and (use or not self.grant("notification_rendering_definition", identity, 1, "catalog.use"))
        ):
            raise WebError("resource_unavailable")
        return value

    def owner_admin(self, scope):
        if not self.scope(scope, edit=True):
            raise WebError("resource_unavailable")

    def schema(self, revision_id, *, use=False):
        row = self.db.execute(
            "SELECT facet_schema_id FROM facet_schema_revisions WHERE facet_schema_revision_id=?", (revision_id,)
        ).fetchone()
        if row is None:
            raise WebError("resource_unavailable")
        root = self.db.execute("SELECT * FROM facet_schemas WHERE facet_schema_id=?", (row[0],)).fetchone()
        self.touch("facet_schema", row[0], "use" if use else "read")
        if (
            not self.scope(dict(root))
            and not self.grant("facet_schema", row[0], 1, "catalog.use" if use else "catalog.read")
            and (use or not self.grant("facet_schema", row[0], 1, "catalog.use"))
        ):
            raise WebError("resource_unavailable")


@dataclass(frozen=True)
class RenderingCursorConfig:
    key_id: str
    key_generation: str
    ledger_instance_id: str
    secret: bytes

    def validate(self, db):
        if (
            not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", v) for v in (self.key_id, self.key_generation))
            or not isinstance(self.secret, bytes)
            or not 32 <= len(self.secret) <= 64
            or self.ledger_instance_id != read_ledger_instance_id(db)
        ):
            codec.fail("environment_failure", "cursor_config")

    def encode(self, payload):
        raw = canonical_json_bytes(payload)
        mac = hmac.new(
            self.secret, b"spine.notification-rendering-cursor.v1\0" + self.key_id.encode("ascii") + b"\0" + raw, hashlib.sha256
        ).digest()
        token = f"nrc1.{self.key_id}.{_encode(raw)}.{_encode(mac)}"
        if len(token) > 4096:
            codec.fail("environment_failure", "capacity")
        return token

    def decode(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 4096:
                raise ValueError()
            prefix, key, body, signature = token.split(".")
            if prefix != "nrc1" or key != self.key_id:
                raise ValueError()
            raw, mac = _decode(body), _decode(signature)
            expected = hmac.new(
                self.secret, b"spine.notification-rendering-cursor.v1\0" + key.encode("ascii") + b"\0" + raw, hashlib.sha256
            ).digest()
            if not hmac.compare_digest(mac, expected):
                raise ValueError()
            return codec.stored_object(raw.decode("utf-8"), 4096)
        except Exception as exc:
            # No cursor payload, signature or inaccessible identity is echoed.
            from spine.core.errors import SpineValidationError

            raise SpineValidationError("stale_cursor:cursor", "rendering cursor is unavailable") from exc


def load_cursor_config(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()} or info.st_mode & 0o077:
                raise ValueError()
            data = parse_object(stream.read(8193).decode("utf-8"), maximum=8192)
        data = codec.exact(data, {"contract_version", "key_id", "key_generation", "ledger_instance_id", "secret_hex"})
        if data["contract_version"] != "spine.notification-rendering-cursor-config.v1" or not re.fullmatch(
            r"[0-9a-f]{64,128}", data["secret_hex"]
        ):
            raise ValueError()
        return RenderingCursorConfig(data["key_id"], data["key_generation"], data["ledger_instance_id"], bytes.fromhex(data["secret_hex"]))
    except Exception as exc:
        from spine.core.errors import SpineValidationError

        raise SpineValidationError("environment_failure:cursor_config", "protected rendering cursor configuration unavailable") from exc


def cursor_facts(db, command, query, admission, permissions):
    ledger_id = read_ledger_instance_id(db)
    epoch = str(permissions.identity["access_epoch"]) if permissions else None
    # The fixed expiry is shortened by every indexed future membership/grant transition.
    valid_until = None
    if permissions:
        candidates = []
        for table in ("subject_memberships", "access_grants"):
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            if {"starts_at_utc", "ends_at_utc"} <= columns:
                if table == "access_grants":
                    rows = db.execute(
                        "SELECT starts_at_utc,ends_at_utc FROM access_grants WHERE grantee_subject_id=? "
                        "OR grantee_group_id IN (SELECT group_id FROM subject_memberships WHERE subject_id=?) LIMIT 101",
                        (permissions.subject, permissions.subject),
                    ).fetchall()
                else:
                    rows = db.execute(
                        "SELECT starts_at_utc,ends_at_utc FROM subject_memberships WHERE subject_id=? LIMIT 101", (permissions.subject,)
                    ).fetchall()
                if len(rows) > 100:
                    codec.fail("environment_failure", "capacity")
                candidates += [v for r in rows for v in r if v is not None and v > permissions.now]
        valid_until = min(candidates) if candidates else None
    context = {
        "mode": admission.mode,
        "account_id": admission.account_id,
        "subject_id": permissions.subject if permissions else None,
        "audience": admission.audience,
        "ledger_instance_id": ledger_id,
    }
    return {
        "contract_version": "spine.notification-rendering-cursor.v1",
        "ledger_instance_id": ledger_id,
        "command": command,
        "query_hash": codec.derived_hash("spine.rendering-cursor-query.v1", query=query),
        "context_hash": codec.derived_hash("spine.rendering-cursor-context.v1", context=context),
        "access_hash": codec.derived_hash(
            "spine.rendering-cursor-access.v1", access={"access_epoch": epoch, "valid_until_utc": valid_until}
        ),
        "catalog_generation": str(
            db.execute("SELECT generation FROM notification_rendering_catalog_state WHERE singleton=1").fetchone()[0]
        ),
        "access_epoch": epoch,
        "access_valid_until_utc": valid_until,
    }


def page_payload(facts, config, last_id, now, prior=None):
    issue = prior["issued_at_utc"] if prior else now
    expiry = prior["expires_at_utc"] if prior else wire_time(parse_time(now) + timedelta(seconds=900))
    if facts["access_valid_until_utc"]:
        expiry = min(expiry, facts["access_valid_until_utc"])
    return {**facts, "key_generation": config.key_generation, "last_id": last_id, "issued_at_utc": issue, "expires_at_utc": expiry}


def check_cursor(payload, facts, config, now):
    expected = set(facts) | {"key_generation", "last_id", "issued_at_utc", "expires_at_utc"}
    try:
        if set(payload) != expected or any(payload[k] != v for k, v in facts.items()) or payload["key_generation"] != config.key_generation:
            raise ValueError()
        codec.identity(payload["last_id"], "cursor")
        issued, expiry = (parse_time(payload[k]) for k in ("issued_at_utc", "expires_at_utc"))
        current = parse_time(now)
        if not issued <= current < expiry or expiry - issued > timedelta(seconds=900):
            raise ValueError()
    except Exception:
        codec.fail("stale_cursor", "cursor")
