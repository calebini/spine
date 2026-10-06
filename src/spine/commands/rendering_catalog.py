"""Internal rendering catalog handlers. Not registered with CLI or web adapters."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from spine.commands.context import CommandContext
from spine.commands.facet_runtime import FacetBudget, parse_time, utc_now, wire_time
from spine.commands.receipts import command_derived_id, command_receipt, get_command_receipt, insert_command_receipt
from spine.commands.rendering_runtime import RenderingAdmission, check_cursor, cursor_facts, page_payload
from spine.core import rendering_definitions as codec
from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.notification_profiles import normalize_catalog_key
from spine.ledger import facets
from spine.ledger.notification_profiles import require_owner_exists
from spine.ledger.rendering_definitions import invariant, load_disclosure, load_revision, root_owner
from spine.ledger.transactions import LedgerConnection
from spine.web.errors import WebError

DEFINITION_ID = "notification_rendering_definition_id"
REVISION_ID = "notification_rendering_definition_revision_id"
DISCLOSURE_ID = "disclosure_authorization_id"
WRITES = {"create", "publish", "retire", "provision", "revoke"}
COMMANDS = frozenset(
    {f"notification_rendering_definition.{operation}" for operation in ("create", "publish", "retire", "show", "list")}
    | {f"notification_rendering_disclosure.{operation}" for operation in ("provision", "revoke", "show", "list")}
)


class _Preview(Exception):
    def __init__(self, response):
        self.response = response


def normalize(command, value):
    family, operation = command.split(".")
    contract = codec.DEFINITIONS if family == "notification_rendering_definition" else codec.DISCLOSURES
    definition = contract == codec.DEFINITIONS
    identity = DEFINITION_ID if definition else DISCLOSURE_ID
    required, optional = {"contract_version"}, set()
    if operation in WRITES:
        required |= {"command_id", "actor_subject_id", "action_timestamp_utc"}
    if operation == "create":
        required |= {"owner", "definition_key", "revision"}
    elif operation == "publish":
        required |= {identity, "expected_current_revision_id", "revision"}
    elif operation in {"retire", "revoke"}:
        required |= {identity, "reason_code", "expected_current_revision_id" if definition else "expected_scope_hash"}
    elif operation == "provision":
        required.add("scope")
    elif operation == "show":
        required.add(identity)
        if definition:
            optional.add(REVISION_ID)
    elif operation == "list":
        required |= {"owner", "status", "limit"}
        optional.add("cursor")
    else:
        codec.fail("invalid_request", "command")
    request = codec.exact(value, required, optional)
    codec.bounded(request, 32768, "request")
    if request["contract_version"] != contract:
        codec.fail("invalid_request", "contract_version")
    for key in required - {"contract_version", "owner", "scope", "revision", "limit"}:
        codec.identity(request[key], key)
    if "action_timestamp_utc" in request:
        parse_time(request["action_timestamp_utc"])
    if "owner" in request:
        request["owner"] = codec.owner(request["owner"])
    if "revision" in request:
        request["revision"] = codec.normalize_revision(request["revision"])
    if "scope" in request:
        request["scope"] = codec.normalize_scope(request["scope"])
    for key in ("reason_code", "definition_key"):
        if key in request:
            request[key] = normalize_catalog_key(request[key], key)
    if operation == "list":
        if request["status"] not in ({"active", "retired"} if definition else {"active", "revoked"}):
            codec.fail("invalid_request", "status")
        if (
            not isinstance(request["limit"], str)
            or not request["limit"].isdigit()
            or str(int(request["limit"])) != request["limit"]
            or not 1 <= int(request["limit"]) <= 100
        ):
            codec.fail("invalid_request", "limit")
    return request


def row(db, table, key, identity, budget):
    budget.resolve(table, identity)
    value = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (identity,)).fetchone()
    if value is None:
        codec.fail("referenced_row_not_found", key)
    return dict(value)


def provenance(db, receipt_id):
    r = db.execute(
        "SELECT command_id,actor_subject_id,action_timestamp_utc FROM command_receipts WHERE command_receipt_id=?", (receipt_id,)
    ).fetchone()
    invariant(r is not None)
    return dict(r)


def record(db, identity, definition, budget, revision_id=None):
    if definition:
        root = row(db, "notification_rendering_definitions", DEFINITION_ID, identity, budget)
        revision = load_revision(db, revision_id or root["current_revision_id"])
        invariant(revision[DEFINITION_ID] == identity)
        return {
            DEFINITION_ID: identity,
            REVISION_ID: revision[REVISION_ID],
            "owner": root_owner(root),
            "definition_key": root["definition_key"],
            "status": root["status"],
            "current_revision_id": root["current_revision_id"],
            "revision_number": str(revision["revision_number"]),
            "revision": revision["revision"],
            "definition_hash": revision["definition_hash"],
            "created": provenance(db, root["created_receipt_id"]),
            "published": provenance(db, revision["created_receipt_id"]),
            "retired": None
            if root["retired_receipt_id"] is None
            else {"provenance": provenance(db, root["retired_receipt_id"]), "reason_code": root["retired_reason_code"]},
        }
    budget.resolve("notification_rendering_disclosures", identity)
    grant = load_disclosure(db, identity)
    return {
        DISCLOSURE_ID: identity,
        "scope": grant["scope"],
        "scope_hash": grant["scope_hash"],
        "status": grant["status"],
        "created": provenance(db, grant["created_receipt_id"]),
        "revoked": None
        if grant["revoked_receipt_id"] is None
        else {"provenance": provenance(db, grant["revoked_receipt_id"]), "reason_code": grant["revoked_reason_code"]},
    }


def validate_revision(db, revision, owning_scope, budget, permissions):
    for selection in revision["selections"]:
        schema = row(db, "facet_schema_revisions", "facet_schema_revision_id", selection["facet_schema_revision_id"], budget)
        root = row(db, "facet_schemas", "facet_schema_id", schema["facet_schema_id"], budget)
        if permissions:
            permissions.schema(selection["facet_schema_revision_id"], use=True)
            if selection["projection"] == "location_label":
                codec.fail("permission_denied", "revision.selections")
        if root["status"] != "active" or root_owner(root) != owning_scope:
            codec.fail("rendering_definition_invalid", "revision.selections")
        schema_definition = facets.load_definition(db, selection["facet_schema_revision_id"])
        if not set(revision["compatible_item_types"]) <= set(schema_definition["compatible_item_types"]):
            codec.fail("rendering_definition_invalid", "revision.compatible_item_types")
        fields = schema_definition["fields"]
        field = next((f for f in fields if f["key"] == selection["field_key"]), None)
        if (
            field is None
            or (selection["projection"] == "value" and field["type"] == "reference")
            or (selection["projection"] == "location_label" and (field["type"], field.get("target_kind")) != ("reference", "location"))
        ):
            codec.fail("rendering_definition_invalid", "revision.selections")


def insert_revision(db, identity, revision_id, revision, number, receipt_id):
    db.execute(
        "INSERT INTO notification_rendering_definition_revisions VALUES (?,?,?,?,?,?,?,?)",
        (
            revision_id,
            identity,
            number,
            codec.DEFINITIONS,
            codec.CANON,
            canonical_json_text(revision),
            codec.content_hash(codec.DEFINITIONS, "revision", revision),
            receipt_id,
        ),
    )
    db.executemany(
        "INSERT INTO notification_rendering_definition_fields VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                revision_id,
                index,
                *[selection[k] for k in ("selection_key", "facet_key", "facet_schema_revision_id", "field_key", "projection", "label")],
            )
            for index, selection in enumerate(revision["selections"])
        ],
    )


def validate_scope(db, scope, budget, permissions):
    own = scope["item_owner"]
    require_owner_exists(db, {**own, "owner_subject_id": own.get("owner_subject_id"), "owner_group_id": own.get("owner_group_id")})
    if permissions:
        permissions.owner_admin(own)
    ref = scope["definition"]
    root = row(db, "notification_rendering_definitions", DEFINITION_ID, ref[DEFINITION_ID], budget)
    if permissions:
        permissions.rendering(ref[DEFINITION_ID], use=True)
    if root["status"] != "active":
        codec.fail("rendering_definition_retired", "scope.definition")
    revision = load_revision(db, ref[REVISION_ID])
    if revision[DEFINITION_ID] != ref[DEFINITION_ID] or root_owner(root) != own:
        codec.fail("rendering_disclosure_scope_mismatch", "scope")
    keys = {s["selection_key"] for s in revision["revision"]["selections"]}
    if not set(scope["approved_selection_keys"]) <= keys:
        codec.fail("rendering_disclosure_scope_mismatch", "scope.approved_selection_keys")
    if scope["use_scope"]["kind"] == "profile":
        profile = row(db, "notification_profiles", "notification_profile_id", scope["use_scope"]["notification_profile_id"], budget)
        if permissions:
            permissions.catalog("notification_profile", profile["notification_profile_id"], use=True)
        if profile["status"] != "active" or root_owner(profile) != own:
            codec.fail("rendering_disclosure_scope_mismatch", "scope.use_scope")
    destination = scope["destination"]
    route = row(db, "delivery_targets", "delivery_target_id", destination["delivery_target_id"], budget)
    if permissions:
        permissions.route(destination["delivery_target_id"], release_owner=own)
    if (
        route["status"] != "active"
        or any(destination[k] != route[k] for k in ("channel", "adapter_name", "target_ref"))
        or destination["destination_source"] != "delivery_target"
    ):
        codec.fail("rendering_disclosure_scope_mismatch", "scope.destination")
    recipient = destination["recipient"]
    row(
        db,
        "subjects" if recipient["kind"] == "subject" else "subject_groups",
        "subject_id" if recipient["kind"] == "subject" else "group_id",
        recipient.get("subject_id", recipient.get("group_id")),
        budget,
    )
    for location in scope["permitted_location_ids"]:
        if permissions:
            codec.fail("permission_denied", "scope.permitted_location_ids")
        row(db, "locations", "location_id", location, budget)


def write(command, request, db, budget, permissions):
    operation = command.split(".")[1]
    definition = command.startswith("notification_rendering_definition.")
    existing = get_command_receipt(db, request["command_id"])
    if permissions and request["actor_subject_id"] != permissions.subject:
        codec.fail("permission_denied", "actor_subject_id")
    if existing:
        if existing["command"] != command or existing["semantic_facts_hash"] != hash_canonical_json(request):
            codec.fail("semantic_conflict", "command_id")
        result = dict(existing["result_identity_facts"])
        if permissions:
            prior = result["record"]
            if definition:
                permissions.rendering(prior[DEFINITION_ID])
            elif not permissions.scope(prior["scope"]["item_owner"]):
                codec.fail("permission_denied", "scope")
        return {**result, "changed": False, "replayed": True}
    actor = row(db, "subjects", "subject_id", request["actor_subject_id"], budget)
    if actor["status"] != "active":
        codec.fail("referenced_row_not_found", "actor_subject_id")

    def derived(role, path):
        return command_derived_id(prefix=role, command=command, command_id=request["command_id"], row_role=role, request_path=path)

    receipt_id, audit_id = derived("command_receipt", "/"), derived("audit", "/audit")
    changed = True
    if definition:
        if operation == "create":
            own = request["owner"]
            if own["owner_kind"] == "system":
                codec.fail("permission_denied", "owner")
            require_owner_exists(db, {**own, "owner_subject_id": own.get("owner_subject_id"), "owner_group_id": own.get("owner_group_id")})
            if permissions:
                permissions.owner_admin(own)
            validate_revision(db, request["revision"], own, budget, permissions)
            identity, revision_id = (
                derived("notification_rendering_definition", "/definition"),
                derived("notification_rendering_definition_revision", "/revision"),
            )
            db.execute(
                "INSERT INTO notification_rendering_definitions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    request["definition_key"],
                    "active",
                    revision_id,
                    receipt_id,
                    None,
                    None,
                    own["owner_kind"],
                    own.get("owner_subject_id"),
                    own.get("owner_group_id"),
                ),
            )
            insert_revision(db, identity, revision_id, request["revision"], 1, receipt_id)
            effect = "rendering_definition_created"
        else:
            identity = request[DEFINITION_ID]
            root = row(db, "notification_rendering_definitions", DEFINITION_ID, identity, budget)
            if permissions:
                permissions.rendering(identity, admin=True)
            if root["owner_kind"] == "system":
                codec.fail("permission_denied", "owner")
            if request["expected_current_revision_id"] != root["current_revision_id"]:
                codec.fail("stale_version", "expected_current_revision_id")
            prior = load_revision(db, root["current_revision_id"])
            if operation == "publish":
                if root["status"] != "active":
                    codec.fail("rendering_definition_retired", DEFINITION_ID)
                validate_revision(db, request["revision"], root_owner(root), budget, permissions)
                changed = request["revision"] != prior["revision"]
                if changed:
                    revision_id = derived("notification_rendering_definition_revision", "/revision")
                    insert_revision(db, identity, revision_id, request["revision"], prior["revision_number"] + 1, receipt_id)
                    db.execute(
                        "UPDATE notification_rendering_definitions SET current_revision_id=? WHERE notification_rendering_definition_id=?",
                        (revision_id, identity),
                    )
                effect = "rendering_definition_published" if changed else "rendering_definition_publish_noop"
            else:
                changed = root["status"] == "active"
                if not changed and root["retired_reason_code"] != request["reason_code"]:
                    codec.fail("semantic_conflict", "reason_code")
                if changed:
                    db.execute(
                        "UPDATE notification_rendering_definitions SET status='retired',retired_receipt_id=?,retired_reason_code=? "
                        "WHERE notification_rendering_definition_id=?",
                        (receipt_id, request["reason_code"], identity),
                    )
                effect = "rendering_definition_retired" if changed else "rendering_definition_retire_noop"
    else:
        if operation == "provision":
            scope = request["scope"]
            validate_scope(db, scope, budget, permissions)
            identity = derived("notification_rendering_disclosure", "/scope")
            own, ref, recipient = scope["item_owner"], scope["definition"], scope["destination"]["recipient"]
            db.execute(
                "INSERT INTO notification_rendering_disclosures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    ref[DEFINITION_ID],
                    ref[REVISION_ID],
                    codec.DISCLOSURES,
                    codec.CANON,
                    canonical_json_text(scope),
                    codec.content_hash(codec.DISCLOSURES, "scope", scope),
                    codec.match_hash(scope),
                    "active",
                    receipt_id,
                    None,
                    None,
                    scope["destination"]["delivery_target_id"],
                    recipient.get("subject_id"),
                    recipient.get("group_id"),
                    own["owner_kind"],
                    own.get("owner_subject_id"),
                    own.get("owner_group_id"),
                ),
            )
            db.executemany(
                "INSERT INTO notification_rendering_disclosure_locations VALUES (?,?)",
                [(identity, v) for v in scope["permitted_location_ids"]],
            )
            if scope["use_scope"]["kind"] == "profile":
                db.execute(
                    "INSERT INTO notification_rendering_disclosure_profiles VALUES (?,?)",
                    (identity, scope["use_scope"]["notification_profile_id"]),
                )
            effect = "rendering_disclosure_provisioned"
        else:
            identity = request[DISCLOSURE_ID]
            grant = load_disclosure(db, identity)
            if permissions:
                permissions.owner_admin(grant["scope"]["item_owner"])
            if request["expected_scope_hash"] != grant["scope_hash"]:
                codec.fail("stale_version", "expected_scope_hash")
            changed = grant["status"] == "active"
            if not changed and grant["revoked_reason_code"] != request["reason_code"]:
                codec.fail("semantic_conflict", "reason_code")
            if changed:
                db.execute(
                    "UPDATE notification_rendering_disclosures SET status='revoked',revoked_receipt_id=?,revoked_reason_code=? "
                    "WHERE disclosure_authorization_id=?",
                    (receipt_id, request["reason_code"], identity),
                )
            effect = "rendering_disclosure_revoked" if changed else "rendering_disclosure_revoke_noop"
    # Receipts precede record projection, with deferred FKs retaining atomicity.
    result = {
        "ok": True,
        "contract_version": request["contract_version"],
        "command": command,
        "command_id": request["command_id"],
        "changed": changed,
        "replayed": False,
        "effect": effect,
        "command_receipt_id": receipt_id,
        "audit_id": audit_id,
    }
    receipt = command_receipt(
        command=command,
        command_id=request["command_id"],
        actor_subject_id=request["actor_subject_id"],
        action_timestamp_utc=request["action_timestamp_utc"],
        effect=effect,
        semantic_facts=request,
        result_identity_facts={},
    )
    insert_command_receipt(db, receipt)
    result["record"] = record(db, identity, definition, budget)
    db.execute(
        "UPDATE command_receipts SET result_identity_facts_json=? WHERE command_receipt_id=?", (canonical_json_text(result), receipt_id)
    )
    payload = {"request": request, "result": result}
    db.execute(
        "INSERT INTO coordination_catalog_audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            audit_id,
            "notification_rendering_definition" if definition else "notification_rendering_disclosure",
            identity,
            operation,
            request.get("reason_code", effect),
            request["actor_subject_id"],
            request["command_id"],
            canonical_json_text(payload),
            hash_canonical_json(payload),
            request["action_timestamp_utc"],
        ),
    )
    return result


def read(command, request, db, budget, permissions, admission, config, now):
    definition = command.startswith("notification_rendering_definition.")
    identity = DEFINITION_ID if definition else DISCLOSURE_ID
    base = {"ok": True, "command": command, "contract_version": request["contract_version"]}
    generation = db.execute("SELECT generation FROM notification_rendering_catalog_state WHERE singleton=1").fetchone()[0]
    if command.endswith(".show"):
        if permissions:
            if definition:
                permissions.rendering(request[identity])
            else:
                grant = row(db, "notification_rendering_disclosures", DISCLOSURE_ID, request[identity], budget)
                if not permissions.scope(grant):
                    codec.fail("permission_denied", identity)
        result = {**base, "record": record(db, request[identity], definition, budget, request.get(REVISION_ID))}
    else:
        if config is None:
            codec.fail("environment_failure", "cursor_config")
        config.validate(db)
        query = {k: request[k] for k in ("owner", "status", "limit")}
        facts = cursor_facts(db, command, query, admission, permissions)
        prior = config.decode(request["cursor"]) if "cursor" in request else None
        if prior:
            check_cursor(prior, facts, config, now)
        own = request["owner"]
        table = "notification_rendering_definitions" if definition else "notification_rendering_disclosures"
        where, parameters = (
            ["r.owner_kind=?", "r.owner_subject_id IS ?", "r.owner_group_id IS ?", "r.status=?", f"r.{identity}>?"],
            [
                own["owner_kind"],
                own.get("owner_subject_id"),
                own.get("owner_group_id"),
                request["status"],
                prior["last_id"] if prior else "",
            ],
        )
        if permissions and not permissions.scope(own):
            if not definition:
                where.append("0")
            else:
                groups = list(permissions.groups)
                marks = ",".join("?" for _ in groups) or "NULL"
                where.append(f"""EXISTS(SELECT 1 FROM access_grants g JOIN access_grant_operations o
                    ON o.grant_id=g.grant_id AND o.revision=g.current_revision
                    WHERE g.resource_kind='notification_rendering_definition' AND g.resource_id=r.{identity}
                      AND g.resource_owner_revision=1 AND g.status='active' AND g.starts_at_utc<=?
                      AND (g.ends_at_utc IS NULL OR g.ends_at_utc>?) AND o.operation IN ('catalog.read','catalog.use')
                      AND (g.grantee_subject_id=? OR g.grantee_group_id IN ({marks})))""")
                parameters += [now, now, permissions.subject, *groups]
        rows = db.execute(
            f"SELECT r.{identity} FROM {table} r WHERE " + " AND ".join(where) + f" ORDER BY r.{identity} LIMIT ?",
            (*parameters, int(request["limit"]) + 1),
        ).fetchall()
        has_more = len(rows) > int(request["limit"])
        selected = rows[: int(request["limit"])]
        if permissions:
            for r in selected:
                if definition:
                    permissions.rendering(r[0])
        result = {
            **base,
            "records": [record(db, r[0], definition, budget) for r in selected],
            "has_more": has_more,
            "next_cursor": config.encode(page_payload(facts, config, selected[-1][0], now, prior)) if has_more else None,
            "limit": request["limit"],
        }
    codec.bounded(result, 4 * 1024 * 1024, "capacity")
    budget.check()
    if db.execute("SELECT generation FROM notification_rendering_catalog_state WHERE singleton=1").fetchone()[0] != generation:
        codec.fail("stale_cursor" if "cursor" in request else "environment_failure", "cursor" if "cursor" in request else "capacity")
    return result


def execute(command: str, request: Mapping, context: CommandContext, *, admission=None, cursor_config=None, now=None):
    """Explicit internal harness entry point; production discovery remains unchanged."""
    db = context.ledger
    invariant(isinstance(db, LedgerConnection) and getattr(db, "_renderings_enabled", False) and not db.in_transaction)
    admission = admission or RenderingAdmission()
    budget, timestamp = FacetBudget(), now or wire_time(utc_now())
    old_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
    db.execute(f"PRAGMA busy_timeout={min(old_timeout, 2000)}")
    db.set_progress_handler(budget.progress, 100)
    try:
        normalized = normalize(command, request)
        is_write = command.split(".")[1] in WRITES
        read_facts = None
        with db.atomic_command(write=command.split(".")[1] in WRITES):
            permissions = admission.permissions(db, timestamp, budget)
            if command.split(".")[1] in WRITES:
                result = write(command, normalized, db, budget, permissions)
                if context.dry_run:
                    from spine.ledger.rendering_definitions import finalize

                    finalize(db)
                    raise _Preview(result)
            else:
                read_facts = cursor_facts(db, command, {}, admission, permissions)
                result = read(command, normalized, db, budget, permissions, admission, cursor_config, timestamp)
        if not is_write:
            # End the evaluation snapshot before the release fence. A second
            # metadata-only snapshot observes concurrent catalog/access changes.
            with db.atomic_command(write=False):
                fresh_permissions = admission.permissions(db, timestamp, budget)
                fresh = cursor_facts(db, command, {}, admission, fresh_permissions)
                if fresh != read_facts:
                    codec.fail(
                        "stale_cursor" if "cursor" in normalized else "environment_failure",
                        "cursor" if "cursor" in normalized else "capacity",
                    )
                budget.check()
        return result | ({"dry_run": True} if context.dry_run else {})
    except _Preview as preview:
        return preview.response | {"dry_run": True}
    except (SpineValidationError, WebError, sqlite3.Error) as exc:
        if isinstance(exc, SpineValidationError):
            code, _, field = exc.code.partition(":")
        elif isinstance(exc, sqlite3.IntegrityError):
            code, field = "semantic_conflict", "request"
        elif isinstance(exc, WebError):
            code, field = ("environment_failure", "capacity") if exc.code == "capacity_exceeded" else ("permission_denied", "resource")
        else:
            code, field = "environment_failure", "capacity"
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": code,
                "field": field or "request",
                "message": str(exc) if isinstance(exc, SpineValidationError) else "rendering request could not complete",
            },
            **({"dry_run": True} if context.dry_run else {}),
        }
    finally:
        db.set_progress_handler(None, 0)
        db.execute(f"PRAGMA busy_timeout={old_timeout}")
