"""Transaction-owned, bounded trusted-identity service over canonical commands."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from itsdangerous import BadData, URLSafeSerializer

from spine.commands.context import CommandContext
from spine.commands.core import _handle_agenda_show, handle
from spine.commands.receipts import command_derived_id, get_command_receipt
from spine.core import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.schedule import system_timezone_database_version
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.sqlite import connect
from spine.web.contracts import API, REGISTRY, registry, validate
from spine.web.errors import WebError
from spine.web.history import record
from spine.web.permissions import Permissions, owner


@dataclass(frozen=True)
class WebConfig:
    database: str
    ledger_id: str
    realm_id: str = "local"
    host: str = "127.0.0.1:8090"
    origin: str = "http://127.0.0.1:8090"
    timezone: str = "UTC"
    request_seconds: float = 5.0
    busy_milliseconds: int = 2000
    sql_steps: int = 100_000

    def __post_init__(self) -> None:
        if not self.ledger_id or not self.realm_id or not self.host or not self.origin:
            raise ValueError("explicit web deployment configuration is required")
        if not (0 < self.request_seconds <= 5 and 0 <= self.busy_milliseconds <= 2000 and 0 < self.sql_steps <= 100_000):
            raise ValueError("web budgets may be reduced, not silently expanded")


class Budget:
    def __init__(self, db: sqlite3.Connection, config: WebConfig, started: float) -> None:
        self.db, self.deadline, self.maximum = db, started + config.request_seconds, config.sql_steps
        self.steps = self.lines = 0
        self.exhausted = False

    def check(self) -> None:
        if time.monotonic() >= self.deadline or self.steps > self.maximum:
            self.exhausted = True
            raise WebError("capacity_exceeded")

    def progress(self) -> int:
        self.steps += 100
        if self.steps > self.maximum or time.monotonic() >= self.deadline:
            self.exhausted = True
            return 1
        return 0

    def trace(self, frame: Any, event: str, arg: Any) -> Any:
        self.lines += 1
        if not self.exhausted and self.lines % 1024 == 0:
            self.check()
        return self.trace

    @contextmanager
    def active(self):
        previous = sys.gettrace()
        self.db.set_progress_handler(self.progress, 100)
        sys.settrace(self.trace)
        try:
            yield self
        finally:
            sys.settrace(previous)
            self.db.set_progress_handler(None, 0)


class WebService:
    def __init__(self, config: WebConfig, *, cursor_key: str | None = None) -> None:
        self.config = config
        self.entries, self.registry_hash = registry()
        # An ephemeral, server-only key intentionally invalidates cursors on restart.
        self.signer = URLSafeSerializer(
            cursor_key or secrets.token_urlsafe(48), salt="spine.trusted-web-cursor.v1", signer_kwargs={"digest_method": hashlib.sha256}
        )

    def connection(self):
        if not Path(self.config.database).is_file():
            raise WebError("admission_unavailable")
        return connect(self.config.database, busy_timeout_ms=self.config.busy_milliseconds)

    def preflight(self, db: sqlite3.Connection) -> dict[str, Any]:
        try:
            verify_runtime_schema(db)
        except SpineValidationError as exc:
            raise WebError("admission_unavailable") from exc
        state = db.execute("SELECT * FROM ledger_access_state WHERE singleton_id=1").fetchone()
        if state is None or state["ledger_id"] != self.config.ledger_id or state["realm_id"] != self.config.realm_id:
            raise WebError("admission_unavailable")
        if state["mode"] != "multi_user" or state["identity_mode"] != "trusted_identity":
            raise WebError("admission_unavailable")
        return dict(state)

    def public(self, kind: str) -> dict[str, Any]:
        started = time.monotonic()
        db = self.connection()
        try:
            with Budget(db, self.config, started).active():
                state = self.preflight(db)
                if kind == "ready":
                    return {"is_ready": True}
                if kind == "info":
                    from spine.web.contracts import artifact

                    return {
                        "contract_version": API,
                        "registry_version": REGISTRY,
                        "registry_hash": self.registry_hash,
                        "access_mode": "multi_user",
                        "identity_mode": "trusted_identity",
                        "warning": "Trusted identification — identity is not verified",
                        "server_time_utc": _now(),
                        "timezone": self.config.timezone,
                        "timezone_database_version": system_timezone_database_version(),
                        "limits": {k: str(v) for k, v in artifact("trusted-web-budgets.v1.json")["ceilings"].items()},
                    }
                rows = db.execute(
                    """SELECT a.account_id,b.subject_id,a.display_name AS account_display_name,
                    p.display_name AS subject_display_name FROM web_operators w
                    JOIN login_accounts a USING(account_id) JOIN account_subject_bindings b USING(account_id)
                    JOIN subjects p ON p.subject_id=b.subject_id
                    WHERE w.eligible=1 AND a.status='active' AND b.status='active' AND p.status='active'
                    AND a.realm_id=? AND b.ledger_id=? ORDER BY a.account_id LIMIT 33""",
                    (self.config.realm_id, self.config.ledger_id),
                ).fetchall()
                if len(rows) > 32:
                    raise WebError("capacity_exceeded")
                return {"contract_version": API, "access_epoch": str(state["access_epoch"]), "operators": [dict(r) for r in rows]}
        finally:
            db.close()

    def execute(self, target: str, body: dict[str, Any], account: str, selection: str) -> dict[str, Any]:
        started = time.monotonic()
        if not _id(account) or not _id(selection):
            raise WebError("invalid_request")
        _id_fields(body)
        entry = self.entries.get(target)
        if entry is None and target not in {"context", "items", "agenda"}:
            raise WebError("operation_unavailable")
        write = entry is not None and entry["access_mode"] == "write"
        db = self.connection()
        try:
            with Budget(db, self.config, started).active() as budget, db.atomic_command(write=write):
                self.preflight(db)
                permissions = Permissions(db, account, _now())
                if entry:
                    validate("trusted-web-command-request.schema.json", body, "#/$defs/" + target)
                    result, contract = self.command(db, permissions, target, body, entry)
                else:
                    result, contract = self.query(db, permissions, target, body)
                response = {
                    "contract_version": API,
                    "ok": True,
                    "identity_basis": "self_selected",
                    "account_id": account,
                    "subject_id": permissions.subject,
                    "selection_id": selection,
                    "access_epoch": str(permissions.identity["access_epoch"]),
                    "result_contract": contract,
                    "result": result,
                }
                if target == "task.complete":
                    response["work_reconciliation"] = "not_performed_by_this_command"
                budget.check()
                if len(json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()) > 4 * 1024 * 1024:
                    raise WebError("capacity_exceeded")
                validate(
                    "trusted-web-command-response.schema.json" if entry else "trusted-web-query-response.schema.json",
                    response,
                    "#/$defs/" + target,
                )
            # A separate snapshot observes revocation committed since a read began.
            with budget.active(), db.atomic_command(write=False):
                fresh = Permissions(db, account, _now())
                for field in ("subject_id", "binding_id", "binding_revision", "access_epoch"):
                    if fresh.identity[field] != permissions.identity[field]:
                        raise WebError("access_changed")
                # Time-bounded grants/memberships can expire without an epoch write.
                for kind, identity, operation in permissions.checked:
                    if kind == "item":
                        fresh.item(identity, edit=operation == "edit")
                    elif kind == "route":
                        fresh.route(identity, release_owner=permissions.release_scopes.get(identity))
                    else:
                        fresh.catalog(kind, identity, use=operation == "use")
            return response
        except sqlite3.OperationalError as exc:
            raise WebError("capacity_exceeded" if "locked" in str(exc) or "interrupt" in str(exc) else "admission_unavailable") from exc
        finally:
            db.close()

    def command(self, db, permissions: Permissions, command: str, body: dict[str, Any], entry: dict[str, Any]):
        request = body["request"]
        write = entry["access_mode"] == "write"
        receipt = get_command_receipt(db, request["command_id"]) if write else None
        if "actor_subject_id" in request and request["actor_subject_id"] != permissions.subject:
            raise WebError("command_id_unavailable" if receipt else "identity_unavailable")
        scope = body.get("create_owner_scope")
        link = None
        if receipt:
            link = db.execute("SELECT * FROM web_receipt_links WHERE command_id=?", (request["command_id"],)).fetchone()
            if link is None or link["account_id"] != permissions.identity["account_id"] or receipt["command"] != command:
                raise WebError("command_id_unavailable")
            if (
                link["binding_id"] != permissions.identity["binding_id"]
                or link["binding_revision"] != permissions.identity["binding_revision"]
            ):
                raise WebError("command_id_unavailable")
            old_scope = owner(dict(link)) if link["owner_kind"] else None
            if old_scope != scope:
                raise WebError("command_id_unavailable")
            if receipt.get("item_id"):
                permissions.item(receipt["item_id"])
        else:
            if "expected_access_epoch" in body and int(body["expected_access_epoch"]) != permissions.identity["access_epoch"]:
                raise WebError("access_changed")
            if scope is not None and not permissions.scope(scope):
                raise WebError("resource_unavailable")
            if command in {"schedule.update", "schedule.cancel", "task.complete"}:
                scope = owner(permissions.item(request["item_id"], edit=True))
                self.bound_items(db, permissions, request["item_id"], edit=True)
            elif "item_id" in request:
                permissions.item(request["item_id"])
                self.bound_items(db, permissions, request["item_id"])
            self.request_references(
                permissions, request, scope if command in {"schedule.build", "schedule.create", "schedule.update"} else None
            )
        changes = db.total_changes
        result = handle(command, request, CommandContext(ledger=db, ledger_path=self.config.database))
        _domain_ok(result)
        version_field = entry["response_version_field"]
        if version_field is not None and result.get(version_field) != entry["response_contract_version"]:
            raise WebError("admission_unavailable")
        if receipt and db.total_changes != changes:
            raise WebError("admission_unavailable")
        if command == "schedule.create" and not receipt:
            item_id = result["item_id"]
            identity = command_derived_id(
                prefix="item_access_owner",
                command=command,
                command_id=request["command_id"],
                row_role="item_access_owner",
                request_path="/create_owner_scope",
            )
            db.execute(
                "INSERT INTO item_access_owners VALUES(?,?,1,?,?,?,?,?)",
                (
                    item_id,
                    identity,
                    scope["owner_kind"],
                    scope.get("owner_subject_id"),
                    scope.get("owner_group_id"),
                    permissions.subject if scope["owner_kind"] == "subject_group" else None,
                    request["command_id"],
                ),
            )
            new_receipt = get_command_receipt(db, request["command_id"])
            record(db, "owner", identity, permissions.subject, request["created_at_utc"], new_receipt["command_receipt_id"])
            db.execute("UPDATE ledger_access_state SET access_epoch=access_epoch+1")
            permissions.identity["access_epoch"] += 1
        release = scope if not receipt and command in {"schedule.create", "schedule.update"} else None
        permissions.references(result, release_owner=release)
        if release and result.get("item_id"):
            # Check retained as well as newly-authored policy destinations.
            policies = db.execute(
                """SELECT p.delivery_target_id FROM notification_policies p
                JOIN coordination_items i ON i.item_id=p.item_id AND i.current_version=p.version
                WHERE p.item_id=? AND p.status='active' LIMIT 101""",
                (result["item_id"],),
            ).fetchall()
            if len(policies) > 100:
                raise WebError("capacity_exceeded")
            for policy in policies:
                if not policy[0]:
                    raise WebError("operation_unavailable")
                permissions.route(policy[0], release_owner=release)
        if write and not receipt:
            canonical_receipt = get_command_receipt(db, request["command_id"])
            semantic = {
                "api_version": API,
                "registry_version": REGISTRY,
                "command": command,
                "account_id": permissions.identity["account_id"],
                "subject_id": permissions.subject,
                "binding_id": permissions.identity["binding_id"],
                "binding_revision": str(permissions.identity["binding_revision"]),
                "create_owner_scope": body.get("create_owner_scope"),
                "request": canonical_receipt["semantic_facts"],
            }
            actual_scope = body.get("create_owner_scope") or {}
            db.execute(
                "INSERT INTO web_receipt_links VALUES(?,?,?,?,?,?,'self_selected',?,?,?,?,?,?,?)",
                (
                    canonical_receipt["command_receipt_id"],
                    request["command_id"],
                    permissions.identity["account_id"],
                    permissions.subject,
                    permissions.identity["binding_id"],
                    permissions.identity["binding_revision"],
                    permissions.identity["access_epoch"],
                    API,
                    REGISTRY,
                    actual_scope.get("owner_kind"),
                    actual_scope.get("owner_subject_id"),
                    actual_scope.get("owner_group_id"),
                    hash_canonical_json(semantic),
                ),
            )
        return result, entry["response_contract_version"]

    def request_references(self, p: Permissions, request: dict[str, Any], scope: dict[str, Any] | None) -> None:
        for key in ("owner",):
            if key in request and not p.scope(request[key]):
                raise WebError("resource_unavailable")
        if "scope_chain" in request and any(not p.scope(s) for s in request["scope_chain"]):
            raise WebError("resource_unavailable")
        delivery = request.get("delivery", request.get("patch", {}).get("delivery"))
        if delivery is not None and scope:
            target = delivery.get("target", {})
            if target.get("resolution") != "explicit" or not target.get("delivery_target_id"):
                raise WebError("operation_unavailable")
            p.route(target["delivery_target_id"], release_owner=scope)
        self.unsupported_references(request, p)
        p.references(request, release_owner=scope, use_catalog=scope is not None)

    def unsupported_references(self, value, p):
        if isinstance(value, list):
            for v in value:
                self.unsupported_references(v, p)
        elif isinstance(value, dict):
            if value.get("mode") == "reference" and "location_id" in value:
                raise WebError("operation_unavailable")
            if "subject_roles" in value and any(r["subject_id"] != p.subject for r in value["subject_roles"]):
                raise WebError("operation_unavailable")
            for v in value.values():
                self.unsupported_references(v, p)

    def bound_items(self, db, p: Permissions, item_id: str, *, edit: bool = False) -> None:
        origin = owner(p.item(item_id))
        visited, queue = set(), [item_id]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > 100:
                raise WebError("capacity_exceeded")
            rows = db.execute(
                """SELECT source_item_id,target_item_id FROM relative_temporal_bindings
                WHERE binding_status='active' AND (source_item_id=? OR target_item_id=?) LIMIT 101""",
                (current, current),
            ).fetchall()
            if len(rows) > 100:
                raise WebError("capacity_exceeded")
            for row in rows:
                for identity in row:
                    if owner(p.item(identity, edit=edit and identity != item_id)) != origin:
                        raise WebError("operation_unavailable")
                    if identity not in visited:
                        queue.append(identity)

    def query(self, db, p: Permissions, target: str, body: dict[str, Any]):
        if target == "context":
            validate("trusted-web-http.schema.json", body, "#/$defs/contextRequest")
            return self.context(db, p), "spine.trusted-web-context.v1"
        validate(f"trusted-web-{target}-request.schema.json", body)
        requested = body.get("item_ids")
        if requested is not None:
            for identity in requested:
                p.item(identity)
            ids = sorted(set(requested))
        else:
            ids = p.visible_item_ids()
        now = _now()
        query = {k: v for k, v in body.items() if k != "cursor"}
        if target == "items":
            query.setdefault("limit", "50")
            query.setdefault("item_types", ["event", "task"])
            query.setdefault("include_terminal", False)
        query_hash = hash_canonical_json(query)
        cursor = self.read_cursor(body.get("cursor"), p, target, query_hash, now)
        if target == "items":
            entries = []
            for identity in ids:
                row = db.execute(
                    """SELECT i.item_id,i.item_type,i.current_version,i.status,v.title,
                    COALESCE(t.task_status,e.event_status) AS detail_status FROM coordination_items i
                    JOIN coordination_item_versions v ON v.item_id=i.item_id AND v.version=i.current_version
                    LEFT JOIN task_details t ON t.item_id=i.item_id AND t.version=i.current_version
                    LEFT JOIN event_details e ON e.item_id=i.item_id AND e.version=i.current_version WHERE i.item_id=?""",
                    (identity,),
                ).fetchone()
                if row is None or row["item_type"] not in query["item_types"]:
                    continue
                access_owner = owner(p.item(identity))
                if query.get("owner_scope") is not None and query["owner_scope"] != access_owner:
                    continue
                if not query["include_terminal"] and (row["status"] != "active" or row["detail_status"] in {"done", "cancelled"}):
                    continue
                entries.append(
                    {
                        **dict(row),
                        "current_version": str(row["current_version"]),
                        "owner_scope": access_owner,
                        "allowed_operations": self.operations(p, identity),
                    }
                )
            snapshot = hash_canonical_json(entries)
            if cursor and cursor["source_snapshot_hash"] != snapshot:
                raise WebError("access_changed")
            if cursor:
                entries = [e for e in entries if e["item_id"] > cursor["last_ordering_key"][0]]
            limit = int(query["limit"])
            more = len(entries) > limit
            page = entries[:limit]
            next_cursor = self.cursor(p, target, query_hash, snapshot, [page[-1]["item_id"]], now, cursor) if more else None
            result = {
                "contract_version": "spine.trusted-web-items.v1",
                "entries": page,
                "limit": str(limit),
                "has_more": more,
                "next_cursor": next_cursor,
            }
        else:
            for identity in ids:
                self.bound_items(db, p, identity)
            domain = {**query, "contract_version": "spine.schedule-agenda.v1"}
            if cursor:
                domain["cursor"] = cursor["domain_cursor"]
            try:
                result = _handle_agenda_show(domain, CommandContext(ledger=db), candidate_item_ids=ids, maximum_range_days=31)
            except SpineValidationError as exc:
                if exc.code.startswith("stale_cursor") or cursor is not None:
                    raise WebError("access_changed") from exc
                _domain_ok({"ok": False, "error": {"code": exc.code}})
                raise
            start, end = result["normalized_range"]["range_start_utc"], result["normalized_range"]["range_end_utc"]
            if _parse(end) - _parse(start) > timedelta(days=31):
                raise WebError("invalid_request")
            p.references(result)
            for entry in result["entries"]:
                entry["owner_scope"] = owner(p.item(entry["item_id"]))
                entry["allowed_operations"] = self.operations(p, entry["item_id"])
            result["response_contract"] = "spine.trusted-web-agenda.v1"
            if result["next_cursor"]:
                result["next_cursor"] = self.cursor(
                    p,
                    target,
                    query_hash,
                    result["source_snapshot_hash"],
                    [result["entries"][-1]["item_id"]],
                    now,
                    cursor,
                    domain_cursor=result["next_cursor"],
                )
        return result, f"spine.trusted-web-{target}.v1"

    def operations(self, p: Permissions, identity: str) -> list[str]:
        try:
            p.item(identity, edit=True)
            return ["read", "edit"]
        except WebError as exc:
            if exc.code != "resource_unavailable":
                raise
            return ["read"]

    def context(self, db, p: Permissions) -> dict[str, Any]:
        scopes = [{"owner_kind": "subject", "owner_subject_id": p.subject}]
        scopes.extend({"owner_kind": "subject_group", "owner_group_id": group} for group in sorted(p.groups))
        if len(scopes) > 100:
            raise WebError("capacity_exceeded")
        routes = []
        for scope in scopes:
            field = "owner_subject_id" if scope["owner_kind"] == "subject" else "owner_group_id"
            rows = db.execute(
                f"SELECT * FROM delivery_targets WHERE {field}=? AND status='active' ORDER BY delivery_target_id LIMIT 101", (scope[field],)
            ).fetchall()
            if len(rows) > 100:
                raise WebError("capacity_exceeded")
            for row in rows:
                try:
                    p.route(row["delivery_target_id"], release_owner=scope)
                except WebError as exc:
                    if exc.code == "resource_unavailable":
                        continue
                    raise
                security = db.execute(
                    "SELECT revision FROM route_security_revisions WHERE delivery_target_id=?", (row["delivery_target_id"],)
                ).fetchone()
                approval = db.execute(
                    "SELECT current_revision FROM route_member_use_approvals WHERE delivery_target_id=?", (row["delivery_target_id"],)
                ).fetchone()
                routes.append(
                    {
                        "delivery_target_id": row["delivery_target_id"],
                        "display_name": row["display_name"] or row["delivery_target_id"],
                        "owner_scope": scope,
                        "channel": row["channel"],
                        "route_security_revision": str(security[0] if security else 1),
                        "member_approval_revision": str(approval[0]) if approval else None,
                    }
                )
                if len(routes) > 100:
                    raise WebError("capacity_exceeded")
        return {
            "contract_version": "spine.trusted-web-context.v1",
            "routes": routes,
            "owner_scopes": [
                {"owner_scope": s, "allowed_operations": ["read", "create"] + (["edit"] if p.scope(s, edit=True) else [])} for s in scopes
            ],
            "catalog_scopes": [{"owner_scope": s, "operations": ["catalog.read", "catalog.use"]} for s in scopes],
        }

    def read_cursor(self, token: str | None, p: Permissions, kind: str, query_hash: str, now: str):
        if token is None:
            return None
        try:
            cursor = self.signer.loads(token)
            validate("trusted-web-cursor.schema.json", cursor)
        except (BadData, ValueError, WebError) as exc:
            raise WebError("access_changed") from exc
        expected = {"query_kind": kind, "query_hash": query_hash, **self.cursor_identity(p)}
        if any(cursor.get(k) != v for k, v in expected.items()) or _parse(cursor["expires_at_utc"]) <= _parse(now):
            raise WebError("access_changed")
        if _parse(cursor["expires_at_utc"]) - _parse(cursor["issued_at_utc"]) != timedelta(seconds=900):
            raise WebError("access_changed")
        return cursor

    def cursor_identity(self, p: Permissions) -> dict[str, Any]:
        return {
            k: str(p.identity[k])
            for k in (
                "ledger_id",
                "realm_id",
                "account_id",
                "subject_id",
                "binding_id",
                "binding_revision",
                "access_epoch",
                "recovery_epoch",
            )
        }

    def cursor(self, p, kind, query_hash, snapshot, last, now, previous, *, domain_cursor=None):
        value = {
            "contract_version": "spine.trusted-web-cursor.v1",
            "query_kind": kind,
            **self.cursor_identity(p),
            "query_hash": query_hash,
            "source_snapshot_hash": snapshot,
            "last_ordering_key": last,
            "issued_at_utc": previous["issued_at_utc"] if previous else now,
            "expires_at_utc": previous["expires_at_utc"]
            if previous
            else (_parse(now) + timedelta(seconds=900)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if domain_cursor is not None:
            value["domain_cursor"] = domain_cursor
        validate("trusted-web-cursor.schema.json", value)
        return self.signer.dumps(value)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _id(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value.encode()) <= 256 and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _id_fields(value: Any, depth: int = 0) -> None:
    if depth > 40:
        raise WebError("invalid_request")
    if isinstance(value, dict):
        for k, v in value.items():
            if k.endswith("_id") and v is not None and not _id(v):
                raise WebError("invalid_request")
            _id_fields(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _id_fields(v, depth + 1)


def _domain_ok(result: dict[str, Any]) -> None:
    if not result.get("ok"):
        code = result.get("error", {}).get("code", "")
        details = {
            k: v
            for k, v in {"domain_code": code, "field": result.get("error", {}).get("field")}.items()
            if isinstance(v, str) and len(v) <= 128 and re.fullmatch(r"[a-zA-Z0-9_.:\[\]/-]+", v)
        }
        if code in {"stale_version", "semantic_conflict", "incompatible_replay"}:
            raise WebError("domain_conflict", **details)
        if code in {"referenced_row_not_found", "wrong_item_type"}:
            raise WebError("resource_unavailable")
        raise WebError("domain_failure", **details)
