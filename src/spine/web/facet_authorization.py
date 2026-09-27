"""Facet-family authority and complete bounded access proofs. No transport policy."""

from spine.commands import facet_reads
from spine.commands.facets import revision
from spine.core import facets as codec
from spine.core.canonical_json import canonical_json_bytes
from spine.ledger import facets
from spine.web.errors import WebError
from spine.web.permissions import Permissions, owner
from spine.web.read_authorization import _decimal_facts
from spine.web.read_cursor import cursor_identity

CATALOGS = {"facet_schema": ("facet_schemas", "facet_schema_id"), "item_archetype": ("item_archetypes", "item_archetype_id")}
PERMISSION_RESOLVERS = {
    "facet_schema.create": ("owner.catalog_admin",),
    "facet_schema.publish": ("schema.catalog_admin",),
    "facet_schema.retire": ("schema.catalog_admin",),
    "facet_schema.show": ("schema.catalog_read",),
    "facet_schema.list": ("owner.authorized_catalog_candidates",),
    "item_archetype.facet_binding.set": ("archetype.catalog_admin", "schema.catalog_admin", "same_catalog_owner"),
    "item_archetype.facet_binding.remove": ("archetype.catalog_admin",),
    "item_archetype.facet_binding.list": ("archetype.catalog_read", "returned_schemas.catalog_read"),
    "item.facets.update": (
        "item.edit",
        "fresh_sets.archetype_catalog_use",
        "fresh_sets.schema_catalog_use",
        "fresh_sets.reference_authority",
    ),
    "item.facets.show": ("item.read_current_authority", "returned_references.read"),
    "item.facets.query": ("schema.catalog_read", "owner.authorized_item_candidates", "reference_predicate.read"),
}
REPLAY_RESOLVERS = {
    "facet_schema.create": ("receipt.schema.catalog_read",),
    "facet_schema.publish": ("receipt.schema.catalog_read",),
    "facet_schema.retire": ("receipt.schema.catalog_read",),
    "item_archetype.facet_binding.set": ("receipt.archetype.catalog_read", "receipt.schema.catalog_read"),
    "item_archetype.facet_binding.remove": ("receipt.archetype.catalog_read",),
    "item.facets.update": ("receipt.item.read_current_authority",),
}


class FacetPermissions(Permissions):
    def __init__(self, db, account, now, budget):
        self.budget = budget
        super().__init__(db, account, now)
        self.scopes = []

    def touch(self, kind, resource, operation):
        # Canonical handlers count table identities; permission aliases must not
        # count the same resource twice in the shared budget.
        kind = {"item": "coordination_items", "facet_schema": "facet_schemas", "item_archetype": "item_archetypes"}.get(kind, kind)
        self.budget.resolve(kind, resource)
        super().touch(kind, resource, operation)

    def row(self, table, key, identity):
        self.touch(table, identity, "read")
        row = self.db.execute(f"SELECT * FROM {table} WHERE {key}=?", (identity,)).fetchone()
        if row is None:
            raise WebError("resource_unavailable")
        return dict(row)

    def owner_admin(self, scope):
        if not self.scope(scope, edit=True):
            raise WebError("resource_unavailable")

    def catalog(self, kind, resource, *, use=False, admin=False):
        if kind not in CATALOGS:
            raise WebError("operation_unavailable")
        value = self.row(*CATALOGS[kind], resource)
        if admin:
            self.owner_admin(value)
        elif (
            not self.scope(value)
            and not self.grant(kind, resource, 1, "catalog.use" if use else "catalog.read")
            and (use or not self.grant(kind, resource, 1, "catalog.use"))
        ):
            raise WebError("resource_unavailable")
        self.checked.add((kind, resource, "admin" if admin else "use" if use else "read"))
        return value

    def schema_revision(self, identity, *, use=False, admin=False):
        row = self.row("facet_schema_revisions", "facet_schema_revision_id", identity)
        root = self.catalog("facet_schema", row["facet_schema_id"], use=use, admin=admin)
        return root

    def reference(self, kind, identity):
        # No implicit shared subject/location resolver. Never echo rejected IDs.
        if kind != "subject" or identity != self.subject:
            raise WebError("resource_unavailable")
        return facet_reads.reference(self.db, kind, identity, self.budget)

    def authorize(self, command, request, receipt=None):
        if receipt is not None:
            if command.startswith("facet_schema."):
                self.catalog("facet_schema", receipt["facet_schema_id"])
            elif command.startswith("item_archetype."):
                self.catalog("item_archetype", receipt["item_archetype_id"])
                if command.endswith(".set"):
                    self.schema_revision(receipt["facet_schema_revision_id"])
            else:
                self.item(receipt["item_id"])
            return
        if command == "facet_schema.create":
            self.owner_admin(request["owner"])
        elif command in {"facet_schema.publish", "facet_schema.retire", "facet_schema.show"}:
            self.catalog("facet_schema", request["facet_schema_id"], admin=not command.endswith(".show"))
        elif command.startswith("item_archetype."):
            self.catalog("item_archetype", request["item_archetype_id"], admin=not command.endswith(".list"))
            if command.endswith(".set"):
                self.schema_revision(request["facet_schema_revision_id"], admin=True)
        elif command in {"item.facets.show", "item.facets.update"}:
            self.item(request["item_id"], edit=command.endswith(".update"))
            if command.endswith(".update"):
                for change in request["changes"]:
                    if change["op"] != "set":
                        continue
                    binding = self.row("archetype_facet_bindings", "facet_binding_id", change["expected_binding_id"])
                    self.catalog("item_archetype", binding["item_archetype_id"], use=True)
                    self.schema_revision(change["facet_schema_revision_id"], use=True)
                    definition = facets.load_definition(self.db, change["facet_schema_revision_id"])
                    for field in definition["fields"]:
                        if field["type"] == "reference" and field["key"] in change["values"]:
                            self.reference(field["target_kind"], change["values"][field["key"]])

    def candidates(self, kind, scope):
        """Indexed owner/grantee enumeration, never an all-ledger/filter-in-Python scan."""
        self.scopes.append((kind, scope))
        table, key = ("item_access_owners", "item_id") if kind == "item" else CATALOGS[kind]
        where, params = (
            "r.owner_kind=? AND r.owner_subject_id IS ? AND r.owner_group_id IS ?",
            (scope["owner_kind"], scope.get("owner_subject_id"), scope.get("owner_group_id")),
        )
        if self.scope(scope):
            query = f"SELECT r.{key} FROM {table} r WHERE {where} ORDER BY r.{key} LIMIT 101"
        else:
            groups = sorted(self.groups)
            marks = ",".join("?" for _ in groups) or "NULL"
            ops = "'item.read','item.edit'" if kind == "item" else "'catalog.read','catalog.use'"
            revision_check = "r.current_revision" if kind == "item" else "1"
            query = f"""SELECT DISTINCT r.{key} FROM access_grants g JOIN {table} r ON r.{key}=g.resource_id
                WHERE g.resource_kind=? AND (g.grantee_subject_id=? OR g.grantee_group_id IN ({marks}))
                AND g.status='active' AND g.starts_at_utc<=? AND (g.ends_at_utc IS NULL OR g.ends_at_utc>?)
                AND g.resource_owner_revision={revision_check} AND {where}
                AND EXISTS(SELECT 1 FROM access_grant_operations o WHERE o.grant_id=g.grant_id
                  AND o.revision=g.current_revision AND o.operation IN ({ops})) ORDER BY r.{key} LIMIT 101"""
            params = (kind, self.subject, *groups, self.now, self.now, *params)
        rows = self.db.execute(query, params).fetchall()
        if len(rows) > 100:
            raise WebError("capacity_exceeded")
        ids = [row[0] for row in rows]
        for identity in ids:
            self.item(identity) if kind == "item" else self.catalog(kind, identity)
        return ids

    def source(self, command, request):
        db, budget = self.db, self.budget
        if command == "facet_schema.list":
            roots = [self.catalog("facet_schema", identity) for identity in self.candidates("facet_schema", request["owner"])]
            return {"roots": [facet_reads.root_fact(row) for row in roots]}, [facet_reads.root_view(row) for row in roots]
        if command == "item_archetype.facet_binding.list":
            root = self.catalog("item_archetype", request["item_archetype_id"])
            rows = db.execute(
                "SELECT * FROM archetype_facet_bindings WHERE item_archetype_id=? AND status='active' ORDER BY facet_key LIMIT 101",
                (request["item_archetype_id"],),
            ).fetchall()
            if len(rows) > 100:
                raise WebError("capacity_exceeded")
            values, facts = [], []
            for row in rows:
                value = facet_reads.binding_view(row)
                schema = self.schema_revision(row["facet_schema_revision_id"])
                values.append(value)
                facts.append({"binding": value, "schema": facet_reads.root_fact(schema)})
            return {"archetype": {k: root[k] for k in ("item_archetype_id", "current_revision_id", "status")}, "bindings": facts}, values
        root = self.schema_revision(request["facet_schema_revision_id"])
        selected = revision(db, request["facet_schema_revision_id"], budget)
        field = next((v for v in selected["definition"]["fields"] if v["key"] == request["field"] and v["queryable"]), None)
        if field is None:
            raise WebError("domain_failure")
        ref = self.reference(field["target_kind"], request["value"]) if field["type"] == "reference" else None
        request["value"] = codec.normalize_scalar(field, request["value"])
        rows = []
        for identity in self.candidates("item", request["owner"]):
            scope = self.item(identity)
            item = self.row("coordination_items", "item_id", identity)
            rows.append(
                {
                    "item_id": identity,
                    "current_version": str(item["current_version"]),
                    "owner": owner(scope),
                    "owner_revision": str(scope["current_revision"]),
                }
            )
        return {
            "schema": {
                **facet_reads.root_fact(root),
                "facet_schema_revision_id": request["facet_schema_revision_id"],
                "definition_hash": selected["definition_hash"],
            },
            "candidates": rows,
            "reference": ref,
        }, rows

    def show(self, command, request):
        self.authorize(command, request)
        if command == "item.facets.show":
            item = self.row("coordination_items", "item_id", request["item_id"])
            version = int(request.get("item_version", item["current_version"]))
            if (
                self.db.execute(
                    "SELECT 1 FROM coordination_item_versions WHERE item_id=? AND version=?", (request["item_id"], version)
                ).fetchone()
                is None
            ):
                raise WebError("resource_unavailable")
            for entry in facets.load_snapshot(self.db, request["item_id"], version):
                values = codec.parse_object(entry["values_json"], maximum=16384)
                for field in facets.load_definition(self.db, entry["facet_schema_revision_id"])["fields"]:
                    if field["type"] == "reference" and field["key"] in values:
                        self.reference(field["target_kind"], values[field["key"]])
        result = facet_reads.show(command, request, self.db, self.budget)
        if command == "item.facets.show":
            for entry in result["entries"]:
                for ref in entry["references"]:
                    self.reference(ref["target_kind"], ref["target_id"])
        return result

    def proof(self, selection):
        """Closed row proof across identity, all memberships and relevant grants."""
        db = self.db
        buckets = {"identity": {}, "memberships": {}, "grants": {}}
        transitions = []

        def add(bucket, table, keys, row):
            if row is None:
                raise WebError("identity_unavailable")
            value = _decimal_facts(dict(row))
            key = [value[k] for k in keys]
            buckets[bucket][(table, canonical_json_bytes(key))] = {"table": table, "key": key, "row": value}
            if sum(map(len, buckets.values())) > 100:
                raise WebError("capacity_exceeded")
            for k in ("starts_at_utc", "ends_at_utc"):
                if value.get(k) is not None and value[k] > self.now:
                    transitions.append(value[k])

        for table, key, identity in (
            ("ledger_access_state", "singleton_id", 1),
            ("web_operators", "account_id", self.identity["account_id"]),
            ("login_accounts", "account_id", self.identity["account_id"]),
            ("account_subject_bindings", "binding_id", self.identity["binding_id"]),
            ("subjects", "subject_id", self.subject),
        ):
            add("identity", table, [key], db.execute(f"SELECT * FROM {table} WHERE {key}=?", (identity,)).fetchone())
        members = db.execute(
            "SELECT * FROM subject_memberships WHERE subject_id=? ORDER BY membership_id LIMIT 101", (self.subject,)
        ).fetchall()
        groups = set()
        for row in members:
            add("memberships", "subject_memberships", ["membership_id"], row)
            groups.add(row["group_id"])
        for group in sorted(groups):
            for table in ("subject_groups", "adopted_access_groups"):
                row = db.execute(f"SELECT * FROM {table} WHERE group_id=?", (group,)).fetchone()
                if row is not None:
                    add("memberships", table, ["group_id"], row)
        resources = {(kind, identity) for kind, identity, _ in self.checked if kind in {"item", *CATALOGS}}
        clauses, args = [], []
        for kind, identity in sorted(resources):
            clauses.append("(g.resource_kind=? AND g.resource_id=?)")
            args.extend((kind, identity))
        for kind, scope in self.scopes:
            table, key = ("item_access_owners", "item_id") if kind == "item" else CATALOGS[kind]
            clauses.append(
                f"(g.resource_kind=? AND EXISTS(SELECT 1 FROM {table} r WHERE r.{key}=g.resource_id AND r.owner_kind=? "
                "AND r.owner_subject_id IS ? AND r.owner_group_id IS ?))"
            )
            args.extend((kind, scope["owner_kind"], scope.get("owner_subject_id"), scope.get("owner_group_id")))
        if clauses:
            marks = ",".join("?" for _ in groups) or "NULL"
            rows = db.execute(
                f"SELECT * FROM access_grants g WHERE (g.grantee_subject_id=? OR g.grantee_group_id IN ({marks})) AND ("
                + " OR ".join(clauses)
                + ") ORDER BY g.grant_id LIMIT 101",
                (self.subject, *sorted(groups), *args),
            ).fetchall()
            for row in rows:
                add("grants", "access_grants", ["grant_id"], row)
                for operation in db.execute(
                    "SELECT * FROM access_grant_operations WHERE grant_id=? AND revision=? ORDER BY operation LIMIT 101",
                    (row["grant_id"], row["current_revision"]),
                ):
                    add("grants", "access_grant_operations", ["grant_id", "revision", "operation"], operation)
        subject = dict(db.execute("SELECT * FROM subjects WHERE subject_id=?", (self.subject,)).fetchone())
        principal = cursor_identity({**self.identity, "subject": subject, "selection_id": selection})
        arrays = {k: [values[key] for key in sorted(values)] for k, values in buckets.items()}
        return {
            "mode": "permission_enforced",
            "identity": {"principal": principal, "rows": arrays["identity"]},
            "memberships": arrays["memberships"],
            "grants": arrays["grants"],
            "deployment_access_mode": "multi_user",
        }, min(transitions, default=None)
