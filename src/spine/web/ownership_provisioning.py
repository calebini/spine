"""Internal, explicitly injected v3 provisioning contracts; no HTTP activation."""

from __future__ import annotations

import copy
import sqlite3
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine.core.errors import SpineValidationError
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.ownership import advance_ownership_epoch, project_access_state, read_access_state
from spine.ledger.recurring_task_migration import verify_candidate_schema
from spine.ledger.transactions import LedgerConnection
from spine.web.errors import WebError

CONTRACT = "spine.trusted-web-provisioning.v3"


class OwnershipProvisioningContracts:
    """Source contracts supplied by an internal caller, never implicitly loaded."""

    def __init__(self, documents: dict[str, dict[str, Any]], *, fault: Callable[[str], None] | None = None) -> None:
        self.documents = {v["$id"]: copy.deepcopy(v) for v in documents.values()}
        self.registry = Registry().with_resources((uri, Resource.from_contents(v)) for uri, v in self.documents.items())
        self.fault = fault or (lambda stage: None)

    def validate(self, name: str, value: Any) -> None:
        uri = "https://cortext.local/spine/contracts/schemas/local-ownership-bootstrap/" + name + ".schema.json"
        if uri not in self.documents:
            raise WebError("admission_unavailable")
        if not Draft202012Validator(self.documents[uri], registry=self.registry, format_checker=FormatChecker()).is_valid(value):
            raise WebError("invalid_request")

    def admit(self, db: sqlite3.Connection) -> None:
        if not isinstance(db, LedgerConnection) or not getattr(db, "_recurring_tasks_enabled", False):
            raise WebError("admission_unavailable")
        try:
            verify_candidate_schema(db)
            read_ledger_instance_id(db)
        except SpineValidationError as exc:
            raise WebError("admission_unavailable") from exc

    def state(self, db: sqlite3.Connection) -> dict[str, Any] | None:
        try:
            return read_access_state(db)
        except SpineValidationError as exc:
            raise WebError("admission_unavailable") from exc

    def witness(self, state: dict[str, Any] | None) -> dict[str, Any] | None:
        return project_access_state(state)

    def check_operators(self, db: sqlite3.Connection, normalized: dict[str, Any], conflicts: list[dict[str, str]]) -> None:
        rows = db.execute(
            """SELECT o.account_id FROM web_operators o JOIN login_accounts a ON a.account_id=o.account_id
               JOIN account_subject_bindings b ON b.account_id=a.account_id AND b.ledger_id=? AND b.status='active'
               JOIN subjects s ON s.subject_id=b.subject_id
               WHERE o.eligible=1 AND a.status='active' AND a.realm_id=? AND s.status='active' LIMIT 33""",
            (normalized["ledger_id"], normalized["realm_id"]),
        ).fetchall()
        if len(rows) > 32:
            raise WebError("capacity_exceeded")
        eligible = {("account", r[0]) for r in rows}
        for operation in normalized["operators"]:
            if operation["operation"] == "create":
                eligible.add(("new", operation["subject_id"]))
            elif operation["eligible"]:
                eligible.add(("account", operation["account_id"]))
            else:
                eligible.discard(("account", operation["account_id"]))
        if len(eligible) > 32:
            raise WebError("capacity_exceeded")
        if not eligible:
            conflicts.append({"code": "eligible_operator_required", "operation_path": "/operators"})

    def will_change(self, db: sqlite3.Connection, normalized: dict[str, Any], state: dict[str, Any] | None) -> bool:
        if state is None or state["mode"] == "trusted_local":
            return True
        for key in ("operators", "memberships", "item_adoptions", "grants", "route_approvals"):
            for op in normalized[key]:
                if op["operation"] == "create" or key == "item_adoptions":
                    return True
                if key == "operators":
                    row = db.execute("SELECT eligible FROM web_operators WHERE account_id=?", (op["account_id"],)).fetchone()
                    if row is None or bool(row[0]) != op["eligible"]:
                        return True
                elif key == "memberships":
                    row = db.execute("SELECT role FROM subject_memberships WHERE membership_id=?", (op["membership_id"],)).fetchone()
                    if op["operation"] == "revoke" or row is None or row[0] != op["role"]:
                        return True
                elif key == "grants":
                    row = db.execute("SELECT status FROM access_grants WHERE grant_id=?", (op["grant_id"],)).fetchone()
                    if row is None or row[0] != "revoked":
                        return True
                else:
                    row = db.execute("SELECT status,approved_route_security_revision FROM route_member_use_approvals "
                                     "WHERE delivery_target_id=?", (op["delivery_target_id"],)).fetchone()
                    if row is None or tuple(row) != (op["status"], int(op["expected_route_security_revision"])):
                        return True
        return False

    def prepare_change(self, db: Any, normalized: dict[str, Any], state: dict[str, Any] | None) -> None:
        try:
            if state is None:
                db.execute("INSERT INTO ledger_access_state VALUES(1,?,?,'multi_user','trusted_identity',1,1)",
                           (normalized["ledger_id"], normalized["realm_id"]))
                db._ownership_epoch_consumed = True
            else:
                advance_ownership_epoch(db)
                if state["mode"] == "trusted_local":
                    db.execute("UPDATE ledger_access_state SET realm_id=?,mode='multi_user',identity_mode='trusted_identity' "
                               "WHERE singleton_id=1", (normalized["realm_id"],))
        except SpineValidationError as exc:
            raise WebError("admission_unavailable") from exc
        self.fault("state")
