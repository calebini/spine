"""Explicit bounded local access provisioning; never a web route."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from spine.commands.receipts import command_derived_id, command_receipt, get_command_receipt, insert_command_receipt
from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import hash_canonical_json
from spine.web.contracts import validate
from spine.web.errors import WebError
from spine.web.history import record

ARRAYS = ("operators", "memberships", "item_adoptions", "grants", "route_approvals")
TABLES = {
    "subject": ("subjects", "subject_id"),
    "subject_group": ("subject_groups", "group_id"),
    "account": ("login_accounts", "account_id"),
    "binding": ("account_subject_bindings", "binding_id"),
    "membership": ("subject_memberships", "membership_id"),
    "item": ("coordination_items", "item_id"),
    "grant": ("access_grants", "grant_id"),
    "route": ("delivery_targets", "delivery_target_id"),
    "item_archetype": ("item_archetypes", "item_archetype_id"),
    "notification_profile": ("notification_profiles", "notification_profile_id"),
}


def derived(command_id: str, role: str, path: str) -> str:
    return command_derived_id(prefix=role, command="web_access.apply", command_id=command_id, row_role=role, request_path=path)


def epoch(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT access_epoch FROM ledger_access_state WHERE singleton_id=1").fetchone()
    return int(row[0]) if row else 0


def plan(db: sqlite3.Connection, request: dict[str, Any], *, realm: str = "local") -> dict[str, Any]:
    validate("trusted-web-provisioning-plan-request.schema.json", request)
    normalized = dict(request)
    for key in ARRAYS:
        normalized[key] = sorted(request.get(key, []), key=canonical_json_bytes)
    if sum(len(normalized[k]) for k in ARRAYS) > 100:
        raise WebError("capacity_exceeded")
    state = db.execute("SELECT * FROM ledger_access_state WHERE singleton_id=1").fetchone()
    if state and (state["ledger_id"] != request["ledger_id"] or state["realm_id"] != realm):
        raise WebError("admission_unavailable")
    if int(request["expected_access_epoch"]) != epoch(db):
        raise WebError("access_changed")
    refs: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    targets: set[tuple[str, ...]] = set()
    membership_changes: dict[str, dict[str, dict[str, Any]]] = {}
    required_groups: dict[str, str] = {}

    def conflict(code: str, path: str) -> None:
        conflicts.append({"code": code, "operation_path": path})

    def reference(kind: str, identity: str, path: str) -> dict[str, Any] | None:
        table, key = TABLES[kind]
        row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (identity,)).fetchone()
        if row is None:
            conflict("missing_reference", path)
            return None
        value = dict(row)
        ref_kind = "catalog" if kind in {"item_archetype", "notification_profile"} else kind
        ref_id = kind + ":" + identity if ref_kind == "catalog" else identity
        revision = value.get("current_revision", value.get("revision", value.get("current_version")))
        refs[ref_kind, ref_id] = {
            "kind": ref_kind,
            "id": ref_id,
            "revision": str(revision) if revision is not None else None,
            "state_hash": hash_canonical_json({k: str(v) if type(v) is int else v for k, v in value.items()}),
        }
        if len(refs) > 100:
            raise WebError("capacity_exceeded")
        return value

    def active(kind: str, identity: str, path: str) -> dict[str, Any] | None:
        value = reference(kind, identity, path)
        if value and value["status"] != "active":
            conflict("invalid_state", path)
        return value

    def scope(value: dict[str, Any], path: str) -> None:
        kind = value["owner_kind"]
        if kind == "subject_group":
            required_groups[value["owner_group_id"]] = path
        active(kind, value["owner_subject_id"] if kind == "subject" else value["owner_group_id"], path)

    for key in ARRAYS:
        for index, operation in enumerate(normalized[key]):
            path = f"/{key}/{index}"
            action = operation["operation"]
            target: tuple[str, ...]
            if key == "operators":
                if action == "create":
                    active("subject", operation["subject_id"], path)
                    target = (key, operation["subject_id"])
                    existing = db.execute(
                        "SELECT 1 FROM account_subject_bindings WHERE subject_id=? AND status='active' LIMIT 1", (operation["subject_id"],)
                    ).fetchone()
                    if existing:
                        conflict("invalid_state", path)
                    warnings.append({"code": "new_account_unverified", "operation_path": path})
                else:
                    account = active("account", operation["account_id"], path)
                    binding = active("binding", operation["binding_id"], path)
                    target = (key, binding["subject_id"] if binding else operation["account_id"])
                    if account and (account["revision"] != int(operation["expected_account_revision"]) or account["realm_id"] != realm):
                        conflict("stale_reference", path)
                    if binding and (
                        binding["account_id"] != operation["account_id"]
                        or binding["revision"] != int(operation["expected_binding_revision"])
                    ):
                        conflict("stale_reference", path)
            elif key == "memberships":
                old = None if action == "create" else reference("membership", operation["membership_id"], path)
                if action != "create" and old is None:
                    continue
                group = operation["group_id"] if action == "create" else old["group_id"]
                subject = operation["subject_id"] if action == "create" else old["subject_id"]
                active("subject_group", group, path)
                active("subject", subject, path)
                target = (key, group, subject)
                if group not in membership_changes:
                    rows = db.execute(
                        "SELECT * FROM subject_memberships WHERE group_id=? AND status='active' LIMIT 101", (group,)
                    ).fetchall()
                    if len(rows) > 100:
                        raise WebError("capacity_exceeded")
                    if len({r["subject_id"] for r in rows}) != len(rows):
                        conflict("duplicate_target", path)
                    membership_changes[group] = {r["subject_id"]: dict(r) for r in rows}
                members = membership_changes[group]
                if action == "create":
                    if subject in members:
                        conflict("duplicate_target", path)
                    members[subject] = {"role": operation["role"], "status": "active"}
                else:
                    if old["current_revision"] != int(operation["expected_revision"]):
                        conflict("stale_reference", path)
                    if old["status"] == "ended":
                        conflict("invalid_state", path)
                    if action == "revoke":
                        if operation["ends_at_utc"] < old["starts_at_utc"]:
                            conflict("invalid_state", path)
                        members.pop(subject, None)
                    else:
                        members[subject] = {"role": operation["role"], "status": "active"}
            elif key == "item_adoptions":
                item = reference("item", operation["item_id"], path)
                scope(operation["owner_scope"], path)
                target = (key, operation["item_id"])
                if item and item["current_version"] != int(operation["expected_item_version"]):
                    conflict("stale_reference", path)
                if db.execute("SELECT 1 FROM item_access_owners WHERE item_id=?", (operation["item_id"],)).fetchone():
                    conflict("already_owned", path)
                warnings.append({"code": "creator_entitlement_not_adopted", "operation_path": path})
            elif key == "grants":
                if action == "create":
                    resource = reference(operation["resource_kind"], operation["resource_id"], path)
                    scope(operation["grantee"], path)
                    target = (
                        key,
                        operation["resource_kind"],
                        operation["resource_id"],
                        canonical_json_bytes(operation["grantee"]).decode(),
                    )
                    revision = 1
                    if operation["resource_kind"] == "item":
                        access = db.execute(
                            "SELECT current_revision FROM item_access_owners WHERE item_id=?", (operation["resource_id"],)
                        ).fetchone()
                        if access is None:
                            conflict("missing_reference", path)
                        else:
                            revision = access[0]
                    if resource and revision != int(operation["resource_owner_revision"]):
                        conflict("stale_reference", path)
                    if operation["ends_at_utc"] is not None and operation["ends_at_utc"] <= operation["starts_at_utc"]:
                        conflict("invalid_grant", path)
                else:
                    grant = reference("grant", operation["grant_id"], path)
                    target = (key, operation["grant_id"])
                    if grant and grant["current_revision"] != int(operation["expected_revision"]):
                        conflict("stale_reference", path)
            else:
                route = active("route", operation["delivery_target_id"], path)
                active("subject_group", operation["owner_group_id"], path)
                required_groups[operation["owner_group_id"]] = path
                target = (key, operation["delivery_target_id"])
                security = db.execute(
                    "SELECT revision FROM route_security_revisions WHERE delivery_target_id=?", (operation["delivery_target_id"],)
                ).fetchone()
                approval = db.execute(
                    "SELECT current_revision FROM route_member_use_approvals WHERE delivery_target_id=?", (operation["delivery_target_id"],)
                ).fetchone()
                if route and (route["owner_kind"] != "subject_group" or route["owner_group_id"] != operation["owner_group_id"]):
                    conflict("invalid_state", path)
                if int(operation["expected_route_security_revision"]) != (security[0] if security else 1):
                    conflict("stale_reference", path)
                if int(operation["expected_approval_revision"]) != (approval[0] if approval else 0):
                    conflict("stale_reference", path)
            if target in targets:
                conflict("duplicate_target", path)
            targets.add(target)

    for group, members in membership_changes.items():
        if sum(m["role"] == "owner" for m in members.values()) != 1:
            path = next(
                f"/memberships/{i}"
                for i, o in enumerate(normalized["memberships"])
                if o.get("group_id") == group
                or (
                    o.get("membership_id")
                    and db.execute("SELECT group_id FROM subject_memberships WHERE membership_id=?", (o["membership_id"],)).fetchone()[0]
                    == group
                )
            )
            conflict("owner_required", path)
    for group, path in required_groups.items():
        if group not in membership_changes and not db.execute("SELECT 1 FROM adopted_access_groups WHERE group_id=?", (group,)).fetchone():
            conflict("owner_required", path)
    referenced = [refs[k] for k in sorted(refs)]
    digest = hash_canonical_json({"normalized_plan": normalized, "references": referenced})
    return {
        "contract_version": "spine.trusted-web-provisioning.v1",
        "ok": True,
        "command": "web_access.plan",
        "normalized_plan": normalized,
        "references": referenced,
        "plan_hash": digest,
        "can_apply": not conflicts,
        "conflicts": conflicts,
        "warnings": warnings,
    }


def apply(db: sqlite3.Connection, request: dict[str, Any], *, realm: str = "local") -> dict[str, Any]:
    validate("trusted-web-provisioning-apply-request.schema.json", request)
    command_id, actor, at = request["command_id"], request["actor_subject_id"], request["action_timestamp_utc"]
    # atomic_command suppresses helper commits and owns rollback of the entire bundle.
    with db.atomic_command():
        if db.execute("SELECT 1 FROM subjects WHERE subject_id=? AND status='active'", (actor,)).fetchone() is None:
            raise WebError("resource_unavailable")
        semantic = {k: request[k] for k in ("contract_version", "actor_subject_id", "action_timestamp_utc", "expected_access_epoch")}
        semantic["normalized_plan"] = request["plan"]["normalized_plan"]
        semantic["plan_hash"] = request["plan"]["plan_hash"]
        semantic["realm_id"] = realm
        replay = get_command_receipt(db, command_id)
        if replay:
            if replay["command"] != "web_access.apply" or replay["semantic_facts_hash"] != hash_canonical_json(semantic):
                raise WebError("command_id_unavailable")
            return {**replay["result_identity_facts"]["response"], "replayed": True}
        proposed = request["plan"]
        if request["expected_access_epoch"] != proposed["normalized_plan"]["expected_access_epoch"]:
            raise WebError("access_changed")
        current = plan(db, proposed["normalized_plan"], realm=realm)
        if not current["can_apply"] or current["plan_hash"] != proposed["plan_hash"] or current["references"] != proposed["references"]:
            raise WebError("domain_conflict")
        before = epoch(db)
        if before == 0:
            db.execute(
                "INSERT INTO ledger_access_state VALUES(1,?,?,'multi_user','trusted_identity',1,1)",
                (current["normalized_plan"]["ledger_id"], realm),
            )
        results = []
        changed = before == 0
        for key in ARRAYS:
            for i, operation in enumerate(current["normalized_plan"][key]):
                result = _apply_operation(db, key, operation, command_id, at, realm, f"/{key}/{i}", actor)
                changed |= result["effect"] != "retained"
                results.append(result)
                if result["effect"] != "retained":
                    receipt = derived(command_id, "command_receipt", "/")
                    ids = result["row_ids"]
                    if key == "operators":
                        if operation["operation"] == "create":
                            record(db, "account", ids[0], actor, at, receipt)
                            record(db, "binding", ids[1], actor, at, receipt)
                        record(db, "operator", ids[0], actor, at, receipt)
                    elif key != "memberships":
                        record(
                            db, {"item_adoptions": "owner", "grants": "grant", "route_approvals": "route"}[key], ids[0], actor, at, receipt
                        )
        if changed and before:
            db.execute("UPDATE ledger_access_state SET access_epoch=? WHERE singleton_id=1", (before + 1,))
        if len(db.execute("SELECT account_id FROM web_operators WHERE eligible=1 LIMIT 33").fetchall()) > 32:
            raise WebError("capacity_exceeded")
        after = epoch(db)
        audit_id = derived(command_id, "access_audit", "/audit")
        receipt_id = derived(command_id, "command_receipt", "/")
        response = {
            "contract_version": "spine.trusted-web-provisioning.v1",
            "ok": True,
            "command": "web_access.apply",
            "command_id": command_id,
            "command_receipt_id": receipt_id,
            "audit_id": audit_id,
            "effect": "web_access_applied" if changed else "web_access_noop",
            "changed": changed,
            "replayed": False,
            "access_epoch": str(after),
            "plan_hash": current["plan_hash"],
            "results": results,
        }
        db.execute("INSERT INTO access_audit_log VALUES(?,?,?,?,?,?)", (audit_id, command_id, actor, at, current["plan_hash"], after))
        insert_command_receipt(
            db,
            command_receipt(
                command="web_access.apply",
                command_id=command_id,
                actor_subject_id=actor,
                action_timestamp_utc=at,
                effect=response["effect"],
                semantic_facts=semantic,
                result_identity_facts={"response": response},
                command_receipt_id=receipt_id,
            ),
        )
        return response


def _apply_operation(
    db: sqlite3.Connection, key: str, o: dict[str, Any], command: str, at: str, realm: str, path: str, actor: str
) -> dict[str, Any]:
    ids: list[str] = []
    revision, effect = 1, "created"
    action = o["operation"]
    if key == "operators":
        if action == "create":
            account, binding = derived(command, "account", path), derived(command, "account_subject_binding", path + "/binding")
            db.execute(
                "INSERT INTO login_accounts VALUES(?,?,?,'active',1,'trusted_local_approval',?,?,?)",
                (account, realm, o["display_name"], at, at, command),
            )
            db.execute(
                "INSERT INTO account_subject_bindings VALUES(?,?,(SELECT ledger_id FROM ledger_access_state),?,1,'active',?,?)",
                (binding, account, o["subject_id"], at, command),
            )
            db.execute("INSERT INTO web_operators VALUES(?,1,1,?)", (account, command))
            ids = [account, binding]
        else:
            prior = db.execute("SELECT * FROM web_operators WHERE account_id=?", (o["account_id"],)).fetchone()
            ids = [o["account_id"]]
            if prior and prior["eligible"] == int(o["eligible"]):
                revision, effect = prior["revision"], "retained"
            else:
                revision = prior["revision"] + 1 if prior else 1
                db.execute(
                    "INSERT INTO web_operators VALUES(?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
                    "eligible=excluded.eligible,revision=excluded.revision,updated_by_command_id=excluded.updated_by_command_i"
                    "d",
                    (o["account_id"], int(o["eligible"]), revision, command),
                )
                effect = "updated"
    elif key == "memberships":
        if action == "create":
            identity = derived(command, "subject_membership", path)
            db.execute(
                "INSERT INTO subject_memberships VALUES(?,?,?,?,'active',?,NULL,1)",
                (identity, o["group_id"], o["subject_id"], o["role"], o["starts_at_utc"]),
            )
            group = o["group_id"]
        else:
            identity = o["membership_id"]
            old = db.execute("SELECT * FROM subject_memberships WHERE membership_id=?", (identity,)).fetchone()
            group = old["group_id"]
            revision = old["current_revision"]
            if action == "set" and o["role"] == old["role"]:
                effect = "retained"
            else:
                revision += 1
                db.execute(
                    "UPDATE subject_memberships SET role=?,status=?,ends_at_utc=?,current_revision=? WHERE membership_id=?",
                    (o.get("role", old["role"]), "ended" if action == "revoke" else "active", o.get("ends_at_utc"), revision, identity),
                )
                effect = "revoked" if action == "revoke" else "updated"
        adoption = db.execute("INSERT OR IGNORE INTO adopted_access_groups VALUES(?)", (group,))
        if adoption.rowcount and effect == "retained":
            effect = "updated"
            revision += 1
            db.execute("UPDATE subject_memberships SET current_revision=? WHERE membership_id=?", (revision, identity))
        if effect != "retained":
            db.execute(
                "INSERT INTO subject_membership_revisions SELECT "
                "membership_id,current_revision,role,status,starts_at_utc,ends_at_utc,?,?,?,? FROM subject_memberships "
                "WHERE membership_id=?",
                (command, at, actor, derived(command, "command_receipt", "/"), identity),
            )
        ids = [identity]
    elif key == "item_adoptions":
        identity = derived(command, "item_access_owner", path)
        scope = o["owner_scope"]
        db.execute(
            "INSERT INTO item_access_owners VALUES(?,?,1,?,?,?,NULL,?)",
            (o["item_id"], identity, scope["owner_kind"], scope.get("owner_subject_id"), scope.get("owner_group_id"), command),
        )
        ids = [identity]
    elif key == "grants":
        if action == "create":
            identity = derived(command, "access_grant", path)
            grantee = o["grantee"]
            db.execute(
                "INSERT INTO access_grants VALUES(?,1,?,?,?,?,?,?,'active',?,?,?,?)",
                (
                    identity,
                    o["resource_kind"],
                    o["resource_id"],
                    int(o["resource_owner_revision"]),
                    grantee["owner_kind"],
                    grantee.get("owner_subject_id"),
                    grantee.get("owner_group_id"),
                    o["starts_at_utc"],
                    o["ends_at_utc"],
                    command,
                    actor,
                ),
            )
            db.executemany("INSERT INTO access_grant_operations VALUES(?,1,?)", [(identity, p) for p in o["operations"]])
        else:
            identity = o["grant_id"]
            old = db.execute("SELECT * FROM access_grants WHERE grant_id=?", (identity,)).fetchone()
            revision = old["current_revision"]
            if old["status"] == "revoked":
                effect = "retained"
            else:
                revision += 1
                db.execute("UPDATE access_grants SET status='revoked',current_revision=? WHERE grant_id=?", (revision, identity))
                effect = "revoked"
        ids = [identity]
    else:
        identity = o["delivery_target_id"]
        prior = db.execute("SELECT * FROM route_member_use_approvals WHERE delivery_target_id=?", (identity,)).fetchone()
        if (
            prior
            and prior["status"] == o["status"]
            and prior["approved_route_security_revision"] == int(o["expected_route_security_revision"])
        ):
            effect, revision = "retained", prior["current_revision"]
        else:
            revision = prior["current_revision"] + 1 if prior else 1
            db.execute(
                "INSERT INTO route_member_use_approvals VALUES(?,?,?,?,?,?) ON CONFLICT(delivery_target_id) DO UPDATE SET "
                "current_revision=excluded.current_revision,owner_group_id=excluded.owner_group_id,approved_route_security"
                "_revision=excluded.approved_route_security_revision,status=excluded.status,updated_by_command_id=excluded"
                ".updated_by_command_id",
                (identity, revision, o["owner_group_id"], int(o["expected_route_security_revision"]), o["status"], command),
            )
            effect = "updated" if prior else "created"
        ids = [identity]
    return {"operation_path": path, "effect": effect, "row_ids": ids, "current_revision": str(revision)}


def handle(command: str, request: dict[str, Any], context: Any) -> dict[str, Any]:
    realm = os.environ.get("SPINE_WEB_REALM_ID", "local")
    try:
        if command == "web_access.plan":
            with context.ledger.atomic_command(write=False):
                return plan(context.ledger, request, realm=realm)
        return apply(context.ledger, request, realm=realm)
    except WebError as exc:
        return {"ok": False, "command": command, "error": {"code": exc.code, "message": exc.code.replace("_", " ")}}
