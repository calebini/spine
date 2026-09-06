"""Bounded selected-subject authorization, independent of the transport."""

from __future__ import annotations

import sqlite3
from typing import Any

from spine.web.errors import WebError


def owner(value: dict[str, Any]) -> dict[str, str]:
    kind = value["owner_kind"]
    return {
        "owner_kind": kind,
        **(
            {"owner_subject_id": value["owner_subject_id"]}
            if kind == "subject"
            else {"owner_group_id": value["owner_group_id"]}
            if kind == "subject_group"
            else {}
        ),
    }


class Permissions:
    def __init__(self, db: sqlite3.Connection, account_id: str, now: str) -> None:
        self.db, self.now = db, now
        row = db.execute(
            """SELECT a.account_id,a.revision AS account_revision,b.binding_id,b.revision AS binding_revision,
            b.subject_id,s.access_epoch,s.ledger_id,s.realm_id,s.recovery_epoch
            FROM web_operators w JOIN login_accounts a USING(account_id)
            JOIN account_subject_bindings b USING(account_id)
            JOIN subjects p ON p.subject_id=b.subject_id
            JOIN ledger_access_state s ON s.ledger_id=b.ledger_id AND s.realm_id=a.realm_id
            WHERE a.account_id=? AND w.eligible=1 AND a.status='active' AND b.status='active' AND p.status='active'""",
            (account_id,),
        ).fetchone()
        if row is None:
            raise WebError("identity_unavailable")
        self.identity = dict(row)
        self.subject = str(row["subject_id"])
        groups = db.execute(
            """SELECT m.group_id,m.role FROM subject_memberships m
            JOIN adopted_access_groups a USING(group_id) JOIN subject_groups g USING(group_id)
            WHERE m.subject_id=? AND m.status='active' AND m.starts_at_utc<=? AND g.status='active'
            ORDER BY m.group_id LIMIT 101""",
            (self.subject, now),
        ).fetchall()
        if len(groups) > 100 or len({r["group_id"] for r in groups}) != len(groups):
            raise WebError("capacity_exceeded")
        self.groups = {str(r["group_id"]): str(r["role"]) for r in groups}
        self.checked: set[tuple[str, str, str]] = set()
        self.visited: set[tuple[str, str]] = set()
        self.release_scopes: dict[str, dict[str, Any]] = {}
        self.matched_grants: set[str] = set()

    def scope(self, scope: dict[str, Any], *, edit: bool = False, creator: str | None = None) -> bool:
        if scope["owner_kind"] == "subject":
            return scope.get("owner_subject_id") == self.subject
        if scope["owner_kind"] == "subject_group":
            role = self.groups.get(str(scope.get("owner_group_id")))
            return role is not None and (not edit or role in {"admin", "owner"} or creator == self.subject)
        return False

    def grant(self, kind: str, resource: str, revision: int, operation: str) -> bool:
        groups = list(self.groups)
        marks = ",".join("?" for _ in groups) or "NULL"
        rows = self.db.execute(
            f"""SELECT g.grant_id FROM access_grants g
            JOIN access_grant_operations o ON o.grant_id=g.grant_id AND o.revision=g.current_revision
            WHERE g.resource_kind=? AND g.resource_id=? AND g.resource_owner_revision=?
            AND g.status='active' AND g.starts_at_utc<=? AND (g.ends_at_utc IS NULL OR g.ends_at_utc>?)
            AND o.operation=? AND (g.grantee_subject_id=? OR g.grantee_group_id IN ({marks})) LIMIT 101""",
            (kind, resource, revision, self.now, self.now, operation, self.subject, *groups),
        ).fetchall()
        if len(rows) > 100:
            raise WebError("capacity_exceeded")
        self.matched_grants.update(str(r[0]) for r in rows)
        if len(self.matched_grants) > 100:
            raise WebError("capacity_exceeded")
        return bool(rows)

    def touch(self, kind: str, resource: str, operation: str) -> None:
        self.visited.add((kind, resource))
        if len(self.visited) > 100:
            raise WebError("capacity_exceeded")

    def item(self, item_id: str, *, edit: bool = False) -> dict[str, Any]:
        self.touch("item", item_id, "edit" if edit else "read")
        row = self.db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            raise WebError("resource_unavailable")
        value = dict(row)
        allowed = self.scope(value, edit=edit, creator=value["creator_entitlement_subject_id"])
        if not allowed:
            allowed = self.grant("item", item_id, int(value["current_revision"]), "item.edit" if edit else "item.read")
            if not edit and not allowed:
                allowed = self.grant("item", item_id, int(value["current_revision"]), "item.edit")
        if not allowed:
            raise WebError("resource_unavailable")
        self.checked.add(("item", item_id, "edit" if edit else "read"))
        return value

    def catalog(self, kind: str, resource: str, *, use: bool = False) -> None:
        self.touch(kind, resource, "use" if use else "read")
        table = {"item_archetype": "item_archetypes", "notification_profile": "notification_profiles"}[kind]
        row = self.db.execute(f"SELECT * FROM {table} WHERE {kind}_id=?", (resource,)).fetchone()
        if row is None or (
            not self.scope(dict(row))
            and not self.grant(kind, resource, 1, "catalog.use" if use else "catalog.read")
            and (use or not self.grant(kind, resource, 1, "catalog.use"))
        ):
            raise WebError("resource_unavailable")
        self.checked.add((kind, resource, "use" if use else "read"))

    def route(self, route_id: str, *, release_owner: dict[str, Any] | None = None) -> dict[str, Any]:
        self.touch("route", route_id, "use" if release_owner else "read")
        row = self.db.execute("SELECT * FROM delivery_targets WHERE delivery_target_id=?", (route_id,)).fetchone()
        if row is None or not self.scope(dict(row)):
            raise WebError("resource_unavailable")
        result = dict(row)
        if release_owner is not None:
            self.release_scopes[route_id] = release_owner
            if owner(result) != owner(release_owner) or result["status"] != "active":
                raise WebError("operation_unavailable")
            if result["owner_kind"] == "subject_group" and self.groups[result["owner_group_id"]] == "member":
                approval = self.db.execute(
                    """SELECT a.status,a.approved_route_security_revision,
                    COALESCE(s.revision,1) AS security_revision FROM route_member_use_approvals a
                    LEFT JOIN route_security_revisions s USING(delivery_target_id)
                    WHERE a.delivery_target_id=? AND a.owner_group_id=?""",
                    (route_id, result["owner_group_id"]),
                ).fetchone()
                if (
                    approval is None
                    or approval["status"] != "approved"
                    or approval["approved_route_security_revision"] != approval["security_revision"]
                ):
                    raise WebError("resource_unavailable")
        self.checked.add(("route", route_id, "use" if release_owner else "read"))
        return result

    def references(self, value: Any, *, release_owner: dict[str, Any] | None = None, use_catalog: bool = False) -> None:
        if isinstance(value, list):
            for v in value:
                self.references(v, release_owner=release_owner, use_catalog=use_catalog)
        elif isinstance(value, dict):
            if "scope_chain" in value and any(not self.scope(s) for s in value["scope_chain"]):
                raise WebError("resource_unavailable")
            for key, v in value.items():
                if key.endswith("item_ids") and isinstance(v, list):
                    for identity in v:
                        if isinstance(identity, str):
                            self.item(identity)
                    continue
                if isinstance(v, str) and v:
                    if key in {"item_id", "source_item_id", "target_item_id", "related_item_id"}:
                        self.item(v)
                    elif key in {"item_archetype_id", "notification_profile_id"}:
                        self.catalog(key.removesuffix("_id"), v, use=use_catalog)
                    elif key == "delivery_target_id":
                        self.route(v, release_owner=release_owner)
                elif isinstance(v, (dict, list)):
                    self.references(v, release_owner=release_owner, use_catalog=use_catalog)

    def visible_item_ids(self) -> list[str]:
        groups = list(self.groups)
        marks = ",".join("?" for _ in groups) or "NULL"
        # UNION uses the owner/grantee indexes; do not enumerate coordination_items first.
        rows = self.db.execute(
            f"""SELECT item_id FROM item_access_owners WHERE owner_subject_id=?
            UNION SELECT item_id FROM item_access_owners WHERE owner_group_id IN ({marks})
            UNION SELECT resource_id FROM access_grants WHERE resource_kind='item' AND status='active'
              AND (grantee_subject_id=? OR grantee_group_id IN ({marks}))
            ORDER BY item_id LIMIT 101""",
            (self.subject, *groups, self.subject, *groups),
        ).fetchall()
        if len(rows) > 100:
            raise WebError("capacity_exceeded")
        result = []
        for row in rows:
            try:
                self.item(str(row[0]))
            except WebError as exc:
                if exc.code != "resource_unavailable":
                    raise
            else:
                result.append(str(row[0]))
        return result
