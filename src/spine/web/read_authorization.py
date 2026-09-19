"""Private authorization observations and timed transition bounds for v2 reads."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from spine.core.canonical_json import canonical_json_text
from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError
from spine.web.permissions import Permissions, owner


class ReadPermissions(Permissions):
    """Retain denied probes too: gaining a necessary source must invalidate a read."""

    def __init__(self, db, account_id, now):
        super().__init__(db, account_id, now)
        self.probes: dict[str, tuple[str, str, dict[str, Any]]] = {}
        self.core_probe_keys: set[str] = set()
        self.optional = False
        self.core_discovery = False
        self.discovery = False
        self.discovered: tuple[str, ...] | None = None

    def remember(self, kind, identity, kwargs):
        key = canonical_json_text(_decimal_facts([kind, identity, kwargs]))
        self.probes[key] = (kind, identity, kwargs)
        if not self.optional:
            self.core_probe_keys.add(key)

    def item(self, item_id, *, edit=False):
        self.remember("item", item_id, {"edit": edit})
        return super().item(item_id, edit=edit)

    def catalog(self, kind, resource, *, use=False):
        self.remember(kind, resource, {"use": use})
        return super().catalog(kind, resource, use=use)

    def route(self, route_id, *, release_owner=None):
        self.remember("route", route_id, {"release_owner": release_owner})
        return super().route(route_id, release_owner=release_owner)


def authorization_identity(snapshot, selection):
    p, db = snapshot.permissions, snapshot.db
    # Subjects have no numeric revision column. Fence their entire canonical row;
    # do not invent a public cursor subject_revision in this internal slice.
    subject = dict(db.execute("SELECT * FROM subjects WHERE subject_id=?", (p.subject,)).fetchone())
    operator = dict(db.execute("SELECT * FROM web_operators WHERE account_id=?", (p.identity["account_id"],)).fetchone())
    return {**p.identity, "subject": subject, "operator": operator, "selection_id": selection}


def authorization_evidence(snapshot, probes, core_keys):
    """Recheck exactly the supplied probes under this transaction's current clock.

    This object is private. Neither it nor its digest belongs in a public cursor.
    Successful owner revisions and checked grants are retained even if another
    authorization path would still allow the same resource.
    """
    db, original = snapshot.db, snapshot.permissions
    result = {}
    grants = {}
    for key, (kind, identity, kwargs) in sorted(probes.items()):
        with nullcontext() if key in core_keys else snapshot.budget.optional():
            snapshot.budget.check()
            p = Permissions(db, original.identity["account_id"], snapshot.evaluated_at_utc)
            try:
                if kind == "item":
                    value = p.item(identity, **kwargs)
                    result[key] = {"owner": owner(value), "revision": value["current_revision"]}
                elif kind == "route":
                    value = p.route(identity, **kwargs)
                    security = db.execute(
                        "SELECT revision FROM route_security_revisions WHERE delivery_target_id=?", (identity,)
                    ).fetchone()
                    approval = db.execute("SELECT * FROM route_member_use_approvals WHERE delivery_target_id=?", (identity,)).fetchone()
                    result[key] = {
                        "owner": owner(value), "status": value["status"],
                        "security": None if security is None else security[0],
                        "approval": None if approval is None else dict(approval),
                    }
                else:
                    p.catalog(kind, identity, **kwargs)
                    table = {"notification_profile": "notification_profiles", "item_archetype": "item_archetypes"}[kind]
                    value = dict(db.execute(f"SELECT * FROM {table} WHERE {kind}_id=?", (identity,)).fetchone())
                    result[key] = owner(value)
            except WebError as exc:
                if exc.code not in {"resource_unavailable", "operation_unavailable"}:
                    raise
                result[key] = exc.code
            for identity in sorted(p.matched_grants):
                row = dict(db.execute("SELECT * FROM access_grants WHERE grant_id=?", (identity,)).fetchone())
                row["operations"] = [r[0] for r in db.execute(
                    "SELECT operation FROM access_grant_operations WHERE grant_id=? AND revision=? ORDER BY operation",
                    (identity, row["current_revision"]),
                )]
                grants[identity] = row
    memberships = [dict(r) for r in db.execute(
        """SELECT m.*,g.status AS group_status FROM subject_memberships m
        JOIN adopted_access_groups a USING(group_id) JOIN subject_groups g USING(group_id)
        WHERE m.subject_id=? AND m.status='active' AND m.starts_at_utc<=? ORDER BY m.membership_id""",
        (original.subject, original.now),
    )]
    return hash_canonical_json(_decimal_facts({"checks": result, "grants": grants, "memberships": memberships}))


def authorization_deadline(snapshot):
    """Earliest prospective activation/expiry, including undisclosed future candidates.

    Equality probes use grantee indexes. No follower/relation graph is enumerated.
    Only the nullable time bound may be disclosed, never its underlying grant.
    """
    p, db = snapshot.permissions, snapshot.db
    transitions = []
    row = db.execute(
        """SELECT MIN(m.starts_at_utc) FROM subject_memberships m
        JOIN adopted_access_groups a USING(group_id) JOIN subject_groups g USING(group_id)
        WHERE m.subject_id=? AND m.status='active' AND g.status='active' AND m.starts_at_utc>?""",
        (p.subject, p.now),
    ).fetchone()
    if row[0] is not None:
        transitions.append(row[0])
    resources = {(kind, identity) for kind, identity, _ in p.probes.values() if kind != "route"}
    if p.discovery:
        resources = {(kind, identity) for kind, identity in resources if kind != "item"}
        resources.add(("item", None))
    for column, grantee, index in [("grantee_subject_id", p.subject, "access_grants_subject")] + [
        ("grantee_group_id", group, "access_grants_group") for group in sorted(p.groups)
    ]:
        for kind, identity in sorted(resources, key=lambda pair: (pair[0], pair[1] or "")):
            sql, params = transition_query(column, index, kind, identity, grantee, p.now)
            core_resource = any(
                k in p.core_probe_keys and (probe[0], probe[1]) == (kind, identity)
                for k, probe in p.probes.items()
            ) or (identity is None and p.core_discovery)
            with nullcontext() if core_resource else snapshot.budget.optional():
                for value in db.execute(sql, params).fetchone():
                    if value is not None:
                        transitions.append(value)
    return min(transitions, default=None)


def transition_query(column, index, kind, identity, grantee, now):
    restriction = " AND g.resource_id=?" if identity is not None else ""
    operations = "'item.read','item.edit'" if kind == "item" else "'catalog.read','catalog.use'"
    # Ignore stale-owner and unsupported-operation grants: they cannot grant a read.
    sql = f"""SELECT MIN(CASE WHEN g.starts_at_utc>? THEN g.starts_at_utc END),
        MIN(CASE WHEN g.ends_at_utc>? THEN g.ends_at_utc END)
        FROM access_grants g INDEXED BY {index}
        WHERE g.{column}=? AND g.status='active' AND g.resource_kind=?{restriction}
        AND (g.ends_at_utc IS NULL OR g.ends_at_utc>?)
        AND (g.resource_kind!='item' OR EXISTS (SELECT 1 FROM item_access_owners a
          WHERE a.item_id=g.resource_id AND a.current_revision=g.resource_owner_revision))
        AND (g.resource_kind='item' OR g.resource_owner_revision=1)
        AND EXISTS (SELECT 1 FROM access_grant_operations o WHERE o.grant_id=g.grant_id
          AND o.revision=g.current_revision AND o.operation IN ({operations}))"""
    params = (now, now, grantee, kind, *((identity,) if identity is not None else ()), now)
    return sql, params


def _decimal_facts(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        return {key: _decimal_facts(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_decimal_facts(v) for v in value]
    return value
