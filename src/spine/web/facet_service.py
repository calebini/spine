"""Closed permission-enforced facet adapter over the shared canonical handlers."""

import copy
import hashlib
import sqlite3
import time
from datetime import timedelta
from importlib import resources

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import facet_reads, facets
from spine.commands.core import _validation_error
from spine.commands.facet_runtime import FacetBudget, FacetCursorConfig, decode_cursor, encode_cursor, install_budget, parse_time, wire_time
from spine.commands.receipts import get_command_receipt
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.web.contracts import artifact, validate
from spine.web.errors import WebError
from spine.web.facet_authorization import PERMISSION_RESOLVERS, REPLAY_RESOLVERS, FacetPermissions
from spine.web.service import WebService, _id, _now

API = "spine.trusted-web-facets.v1"
REGISTRY = "spine.trusted-web-facet-registry.v1"


def registry():
    value = artifact("spine.trusted-web-facet-registry.v1.json")
    integration = artifact("archetype-facet-integration.v1.json")
    if integration["permission_resolvers"] != {k: list(v) for k, v in PERMISSION_RESOLVERS.items()} or integration[
        "replay_permission_resolvers"
    ] != {k: list(v) for k, v in REPLAY_RESOLVERS.items()}:
        raise WebError("admission_unavailable")
    try:
        validate("trusted-web-facet-registry.schema.json", value)
    except WebError as exc:
        raise WebError("admission_unavailable") from exc
    if (
        value.get("contract_version") != REGISTRY
        or value.get("api_contract") != API
        or not {API, REGISTRY} <= IMPLEMENTED_CONTRACT_VERSIONS
    ):
        raise WebError("admission_unavailable")
    entries = {e["command"]: e for e in value["commands"]}
    if set(entries) != set(facets.CONTRACTS) or len(value["commands"]) != len(entries):
        raise WebError("admission_unavailable")
    for command, e in entries.items():
        expected = {
            "command": command,
            "path": f"/api/v1/facets/commands/{command}",
            "method": "POST",
            "access_mode": "write" if command in facets.WRITES else "read",
            "result_contract": facets.CONTRACTS[command],
            "required_contract_versions": list(COMMAND_RUNTIME_CONTRACT_REGISTRY[command].required_contract_versions),
            "resolvers": list(PERMISSION_RESOLVERS[command]),
            "replay_resolvers": list(REPLAY_RESOLVERS.get(command, ())),
        }
        if e != expected or not set(e["required_contract_versions"]) <= IMPLEMENTED_CONTRACT_VERSIONS:
            raise WebError("admission_unavailable")
    for name, digest in artifact("trusted-web-facet-pins.v1.json")["files"].items():
        raw = resources.files("spine.contracts").joinpath("web", name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise WebError("admission_unavailable")
    return value


def domain_error(command, exc):
    error = _validation_error(command, exc)["error"]
    code, field = error["code"], error.get("field")
    if code == "stale_cursor" or (code == "environment_failure" and field in {"source", "cursor"}):
        return WebError("access_changed")
    if code == "environment_failure" and field == "capacity":
        return WebError("capacity_exceeded")
    if code in {"referenced_row_not_found", "facet_reference_unavailable"}:
        return WebError("resource_unavailable")
    if code in {"stale_version", "semantic_conflict", "facet_binding_conflict", "facet_archetype_conflict"}:
        return WebError("domain_conflict")
    if code == "invalid_request" and field == "cursor":
        return WebError("invalid_request")
    if code in {"environment_failure", "runtime_failure"}:
        return WebError("admission_unavailable")
    return WebError("domain_failure")


class FacetService:
    def __init__(self, config, *, cursor_config=None, now=_now, before_release=None):
        self.config, self.cursor_config, self.now, self.before_release = config, cursor_config, now, before_release
        self.registry = registry()
        self.base = WebService(config)

    def permissions(self, db, account, budget):
        self.base.preflight(db)
        return FacetPermissions(db, account, self.now(), budget)

    def install_budget(self, db, started):
        budget = FacetBudget(started=started)
        timeout = install_budget(db, budget)
        # Honor configured ceilings as well as the facet-family maximums.
        original_check, original_progress = budget.check, budget.progress

        def check():
            original_check()
            if time.monotonic() - started >= self.config.request_seconds or budget.steps > self.config.sql_steps:
                raise WebError("capacity_exceeded")

        def progress():
            return int(
                original_progress() or time.monotonic() - started >= self.config.request_seconds or budget.steps > self.config.sql_steps
            )

        budget.check = check
        db.set_progress_handler(progress, 100)
        return budget, timeout

    def capabilities(self, account, selection):
        started = time.monotonic()
        if not _id(account) or not _id(selection):
            raise WebError("identity_unavailable")
        db = self.base.connection()
        budget, timeout = self.install_budget(db, started)
        try:
            with db.atomic_command(write=False):
                self.permissions(db, account, budget)
                result = {
                    "contract_version": API,
                    "registry": self.registry,
                    "pagination_configured": isinstance(self.cursor_config, FacetCursorConfig),
                }
                validate("trusted-web-facet-capabilities.schema.json", result)
                budget.check()
                return result
        except SpineValidationError as exc:
            raise domain_error("facet_schema.list", exc) from exc
        except sqlite3.OperationalError as exc:
            raise WebError("capacity_exceeded" if "locked" in str(exc) or "interrupt" in str(exc) else "admission_unavailable") from exc
        finally:
            db.set_progress_handler(None, 0)
            db.execute(f"PRAGMA busy_timeout={timeout}")
            db.close()

    def execute(self, command, body, account, selection):
        started = time.monotonic()
        if command not in facets.CONTRACTS:
            raise WebError("operation_unavailable")
        if len(canonical_json_bytes(body)) > 1048576:
            raise WebError("capacity_exceeded")
        validate("trusted-web-facet-request.schema.json", body, "#/$defs/" + command)
        if not _id(account) or not _id(selection):
            raise WebError("identity_unavailable")
        request = copy.deepcopy(body["request"])
        db = self.base.connection()
        budget, timeout = self.install_budget(db, started)
        try:
            if command in facets.WRITES:
                with db.atomic_command():
                    p = self.permissions(db, account, budget)
                    receipt = get_command_receipt(db, request["command_id"])
                    if receipt:
                        link = db.execute("SELECT * FROM web_receipt_links WHERE command_id=?", (request["command_id"],)).fetchone()
                        if (
                            link is None
                            or link["account_id"] != account
                            or link["subject_id"] != p.subject
                            or link["binding_id"] != p.identity["binding_id"]
                            or link["api_version"] != API
                            or link["registry_version"] != REGISTRY
                            or receipt["command"] != command
                            or request["actor_subject_id"] != p.subject
                        ):
                            raise WebError("command_id_unavailable")
                        p.authorize(command, request, receipt["result_identity_facts"])
                    else:
                        if request["actor_subject_id"] != p.subject:
                            raise WebError("identity_unavailable")
                        if body["expected_access_epoch"] != str(p.identity["access_epoch"]):
                            raise WebError("access_changed")
                        p.authorize(command, request)
                    access, deadline = p.proof(selection)
                    request = facets.normalize(command, request)
                    result = facets.write(command, request, db, budget)
                    if not receipt:
                        db.execute(
                            "INSERT INTO web_receipt_links VALUES(?,?,?,?,?,?,'self_selected',?,?,?,NULL,NULL,NULL,?)",
                            (
                                result["command_receipt_id"],
                                request["command_id"],
                                account,
                                p.subject,
                                p.identity["binding_id"],
                                p.identity["binding_revision"],
                                p.identity["access_epoch"],
                                API,
                                REGISTRY,
                                hash_canonical_json(
                                    {"api_version": API, "request": request, "account_id": account, "subject_id": p.subject}
                                ),
                            ),
                        )
                    response = self.response(command, result, p, selection, budget)
                    if self.before_release:
                        self.before_release(db)
                    try:
                        fresh = self.permissions(db, account, budget)
                        fresh.authorize(command, request, receipt["result_identity_facts"] if receipt else None)
                        # Proof resources on fresh create need not include the newly created root.
                        proof, _ = fresh.proof(selection)
                        if proof != access or (deadline and self.now() >= deadline):
                            raise WebError("access_changed")
                    except WebError as exc:
                        if exc.code in {"resource_unavailable", "identity_unavailable"}:
                            raise WebError("access_changed") from exc
                        raise
                    budget.check()
                return response
            return self.read(db, command, request, account, selection, budget)
        except SpineValidationError as exc:
            raise domain_error(command, exc) from exc
        except sqlite3.IntegrityError as exc:
            raise WebError("domain_conflict") from exc
        except sqlite3.OperationalError as exc:
            raise WebError("capacity_exceeded" if "locked" in str(exc) or "interrupt" in str(exc) else "admission_unavailable") from exc
        finally:
            db.set_progress_handler(None, 0)
            db.execute(f"PRAGMA busy_timeout={timeout}")
            db.close()

    def response(self, command, result, p, selection, budget):
        response = {
            "contract_version": API,
            "ok": True,
            "identity_basis": "self_selected",
            "account_id": p.identity["account_id"],
            "subject_id": p.subject,
            "selection_id": selection,
            "access_epoch": str(p.identity["access_epoch"]),
            "result_contract": facets.CONTRACTS[command],
            "result": result,
        }
        budget.check()
        if len(canonical_json_bytes(response)) > 4194304:
            raise WebError("capacity_exceeded")
        try:
            validate("trusted-web-facet-response.schema.json", response, "#/$defs/" + command)
        except WebError as exc:
            raise WebError("admission_unavailable") from exc
        return response

    def read(self, db, command, request, account, selection, budget):
        base = {"ok": True, "command": command, "response_contract": facets.CONTRACTS[command]}
        page = command in facets.PAGES
        config = self.cursor_config
        with db.atomic_command(write=False):
            p = self.permissions(db, account, budget)
            request = facets.normalize(command, request)
            if page:
                if not isinstance(config, FacetCursorConfig):
                    raise WebError("admission_unavailable")
                config.validate()
            if page:
                facts, rows = p.source(command, request)
            else:
                facts = p.show(command, request)
            access, deadline = p.proof(selection)
            if page:
                result, payload = self.page(command, request, facts, rows, p, config, access, deadline)
            else:
                result, payload = {**base, **facts}, None
            response = self.response(command, result, p, selection, budget)
        if self.before_release:
            self.before_release(db)
        with db.atomic_command(write=False):
            try:
                fresh = self.permissions(db, account, budget)
                current = fresh.source(command, copy.deepcopy(request))[0] if page else fresh.show(command, request)
                fresh_access, fresh_deadline = fresh.proof(selection)
            except WebError as exc:
                if exc.code in {"resource_unavailable", "identity_unavailable"}:
                    raise WebError("access_changed") from exc
                raise
            budget.check()
            if access != fresh_access or facts != current or deadline != fresh_deadline or (deadline and self.now() >= deadline):
                raise WebError("access_changed")
            if payload and (
                self.now() >= payload["expires_at_utc"]
                or (payload["authorization_valid_until_utc"] and self.now() >= payload["authorization_valid_until_utc"])
            ):
                raise WebError("access_changed")
        return response

    def page(self, command, request, facts, rows, p, config, access, deadline):
        query = hash_canonical_json(
            {"contract_version": "spine.facet-query.v1", "command": command, "request": {k: v for k, v in request.items() if k != "cursor"}}
        )
        now = parse_time(self.now())
        payload = {
            "contract_version": "spine.facet-cursor.v1",
            "command": command,
            "query_hash": query,
            "context_hash": config.digest(
                "spine.facet-cursor-context.v1",
                {
                    "mode": "permission_enforced",
                    "cursor_ledger_id": config.ledger_id,
                    "cursor_generation": config.generation,
                    "principal": access["identity"]["principal"],
                },
            ),
            "access_hash": config.digest("spine.facet-cursor-access.v1", access),
            "source_snapshot_hash": config.digest(
                "spine.facet-cursor-source.v1", {"command": command, "query_hash": query, "facts": facts}
            ),
            "issued_at_utc": wire_time(now),
            "expires_at_utc": wire_time(now + timedelta(seconds=900)),
            "authorization_valid_until_utc": deadline,
            "last_key": "",
        }
        if command == "facet_schema.list":
            collection, key, scope = "schemas", "facet_schema_id", {"owner": request["owner"]}
            rows = [r for r in rows if r["status"] == request["status"]]
        elif command == "item_archetype.facet_binding.list":
            collection, key, scope = "bindings", "facet_key", {"item_archetype_id": request["item_archetype_id"]}
        else:
            collection, key = "items", "item_id"
            scope = {k: request[k] for k in ("owner", "facet_schema_revision_id", "field", "value")}
            rows = facet_reads.query_matches(p.db, request, rows)
        if "cursor" in request:
            cursor = decode_cursor(config, request["cursor"])
            if cursor["command"] != command or cursor["query_hash"] != query or parse_time(cursor["issued_at_utc"]) > now:
                raise WebError("invalid_request")
            if (
                any(cursor[k] != payload[k] for k in ("context_hash", "access_hash", "source_snapshot_hash"))
                or now >= parse_time(cursor["expires_at_utc"])
                or (cursor["authorization_valid_until_utc"] and now >= parse_time(cursor["authorization_valid_until_utc"]))
                or cursor["last_key"] not in {r[key] for r in rows}
            ):
                raise WebError("access_changed")
            payload = cursor.copy()
            rows = [r for r in rows if r[key] > cursor["last_key"]]
        selected, more = rows[: int(request["limit"])], len(rows) > int(request["limit"])
        token = None
        if more:
            payload["last_key"] = selected[-1][key]
            token = encode_cursor(config, payload)
        return {
            "ok": True,
            "command": command,
            "response_contract": facets.CONTRACTS[command],
            **scope,
            collection: selected,
            "limit": request["limit"],
            "has_more": more,
            "next_cursor": token,
        }, payload
