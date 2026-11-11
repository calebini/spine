"""Internal R2 handlers. Not registered with any public dispatcher or worker."""

from __future__ import annotations

import copy
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.facet_runtime import FacetBudget, install_budget
from spine.commands.receipts import command_receipt, get_command_receipt, insert_command_receipt
from spine.commands.recurring_task_runtime import (
    PREFIX,
    RESPONSE,
    RecurringTaskContracts,
    cursor_payload,
    fail,
    instant,
    sign_cursor,
    verify_cursor,
    wire,
)
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import audit_log_payload_hash, command_derived_id, hash_canonical_json
from spine.core.recurring_tasks import CONTRACT, derive, payload_hash
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.notification_profiles import require_owner_exists
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_task_catalog import (
    advance_catalog as advance_catalog,
)
from spine.ledger.recurring_task_catalog import (
    catalog as catalog,
)
from spine.ledger.recurring_task_catalog import (
    intent_view as intent_view,
)
from spine.ledger.recurring_task_catalog import (
    lookup as lookup,
)
from spine.ledger.recurring_task_catalog import (
    pending_adoption as pending_adoption,
)
from spine.ledger.recurring_task_catalog import (
    rule_view as rule_view,
)
from spine.ledger.recurring_task_catalog import (
    source_snapshot as source_snapshot,
)
from spine.ledger.recurring_task_catalog import (
    stored_projection as stored_projection,
)
from spine.ledger.recurring_task_migration import verify_candidate_schema
from spine.ledger.recurring_tasks import compare_and_swap, insert_record, read_record
from spine.ledger.transactions import LedgerConnection
from spine.services.recurring_task_configuration import normalize_configuration

if TYPE_CHECKING:
    from spine.services.recurring_task_reconcile import ResponseSizer

DELIVERY = "not_attempted_by_command"
INTERNAL_COMMANDS = frozenset(PREFIX + name for name in ("create", "update", "retire", "show", "list", "reconcile", "assignment.suppress"))


class Preview(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result


def success_response(
    command: str, request: dict[str, Any], result: dict[str, Any], effect: str,
    changed: bool, now: str, runtime: dict[str, Any], *, dry_run: bool = False,
) -> dict[str, Any]:
    """One projection for byte planning and the persisted write receipt."""
    audits = list(runtime["audit_ids"])
    if changed:
        audits.append(command_derived_id(
            prefix="audit", command=command, command_id=request["command_id"], row_role="audit", request_path="/audit"
        ))
    response = {
        "ok": True, "response_contract": RESPONSE, "command": command,
        "changed": changed, "effect": effect, "evaluated_at_utc": now, "result": result,
        "command_id": request["command_id"],
        "command_receipt_id": command_derived_id(
            prefix="command_receipt", command=command, command_id=request["command_id"],
            row_role="command_receipt", request_path="/command_receipt",
        ),
        "audit_ids": sorted(audits), "replayed": False,
    }
    if dry_run:
        response.update(command_receipt_id=None, audit_ids=[], dry_run=True, commit_cutoff_recheck_required=True)
    return response


def response_sizer(command: str, request: dict[str, Any], now: str, *, dry_run: bool) -> ResponseSizer:
    """Bind immutable outer identity; measure fresh accepted facts at each trial."""
    command_id = request["command_id"]

    def measure(*, result: dict[str, Any], effect: str, changed: bool, audit_ids: Sequence[str]) -> int:
        response = success_response(
            command, {"command_id": command_id}, result, effect, changed, now,
            {"audit_ids": audit_ids}, dry_run=dry_run,
        )
        return len(canonical_json_bytes(response))

    return measure


def expected(db: Any, request: dict[str, Any], root: dict[str, Any]) -> None:
    source = source_snapshot(db, root)
    actual = {
        "rule_change_version": str(root["change_version"]),
        "rule_revision_id": root["current_revision_id"],
        "source_item_version": source["source_item_version"],
        "recurrence_revision_id": source["recurrence_revision_id"],
        "catalog_generation": catalog(db),
    }
    for field, value in actual.items():
        if request["expected"][field] != value:
            fail("stale_version", "expected." + field)


def configuration_record(
    db: Any, root_id: str, config: dict[str, Any], request: dict[str, Any], now: str, prior: dict[str, Any] | None = None
) -> str:
    digest = payload_hash("configuration", config)[0]
    index = 1 if prior is None else prior["revision_index"] + 1
    fields = {"related_task_rule_id": root_id, "revision_index": str(index), "configuration_hash": digest}
    if prior:
        fields["prior_revision_id"] = prior["related_task_rule_revision_id"]
    identity = derive("rule_revision", fields)[0]
    insert_record(
        db,
        "related_task_rule_revisions",
        {
            "related_task_rule_revision_id": identity,
            "related_task_rule_id": root_id,
            "revision_index": index,
            "prior_revision_id": fields.get("prior_revision_id"),
            "configuration_json": config,
            "configuration_hash": digest,
            "created_by_subject_id": request["actor_subject_id"],
            "created_by_command_id": request["command_id"],
            "created_at_utc": now,
        },
    )
    return identity


def new_intent(db: Any, root: dict[str, Any], kind: str, payload: dict[str, Any], request: dict[str, Any], now: str) -> str:
    version = root["change_version"] + 1
    identity = derive(
        "intent",
        {
            "related_task_rule_id": root["related_task_rule_id"],
            "rule_change_version": str(version),
            "intent_kind": kind,
            "intent_payload": payload,
        },
    )[0]
    insert_record(
        db,
        "related_task_intents",
        {
            "intent_id": identity,
            "related_task_rule_id": root["related_task_rule_id"],
            "rule_change_version": version,
            "intent_kind": kind,
            "intent_json": payload,
            "status": "pending",
            "created_by_command_id": request["command_id"],
            "created_at_utc": now,
        },
    )
    return identity


def create(db: Any, request: dict[str, Any], context: Any, contracts: Any, now: str) -> tuple[dict[str, Any], str, bool]:
    require_owner_exists(db, request["owner"])
    source = request["source"]
    item = db.execute(
        "SELECT i.item_type,i.status,i.current_version,d.event_status FROM coordination_items i "
        "LEFT JOIN event_details d ON d.item_id=i.item_id AND d.version=i.current_version WHERE i.item_id=?",
        (source["item_id"],),
    ).fetchone()
    if item is None:
        fail("referenced_row_not_found", "source.item_id")
    for field, value in [("item_version", str(item["current_version"]))]:
        if source[field] != value:
            fail("stale_version", "source." + field)
    current = source_snapshot(db, {"source_item_id": source["item_id"]})
    for field in ("recurrence_set_id", "recurrence_revision_id"):
        if source[field] != current[field]:
            fail("stale_version", "source." + field)
    if item["item_type"] != "event" or item["status"] != "active" or item["event_status"] != "scheduled":
        fail("semantic_conflict", "source.item_id")
    header = db.execute("SELECT time_basis FROM recurrence_sets WHERE recurrence_set_id=?", (source["recurrence_set_id"],)).fetchone()
    if header[0] not in {"local_instant", "instant_utc"}:
        fail("semantic_conflict", "source.item_id")
    identity = derive("rule", {"owner": request["owner"], "rule_key": request["rule_key"]})[0]
    if db.execute(
        "SELECT 1 FROM related_task_rules WHERE owner_key=? AND rule_key=?",
        (canonical_json_bytes(request["owner"]).decode(), request["rule_key"]),
    ).fetchone():
        fail("semantic_conflict", "rule_key")
    config = normalize_configuration(request["configuration"], context, contracts)
    enrollment = copy.deepcopy(request["enrollment"])
    if enrollment["kind"] == "selected_occurrence":
        from spine.commands import core

        recurrence = load_current_recurrence_set(db, item_id=source["item_id"])
        if recurrence is None:
            fail("environment_failure", "source")
        occurrence = core._resolve_current_occurrence(recurrence, enrollment["occurrence_key"])
        enrollment.update(selector=occurrence["target_occurrence_selector"], recurrence_revision_id=source["recurrence_revision_id"])
    revision = configuration_record(db, identity, config, request, now)
    owner = request["owner"]
    insert_record(
        db,
        "related_task_rules",
        {
            "related_task_rule_id": identity,
            "owner_kind": owner["owner_kind"],
            "owner_subject_id": owner.get("owner_subject_id"),
            "owner_group_id": owner.get("owner_group_id"),
            "owner_key": owner,
            "rule_key": request["rule_key"],
            "source_item_id": source["item_id"],
            "recurrence_set_id": source["recurrence_set_id"],
            "enrolled_source_version": int(source["item_version"]),
            "enrolled_recurrence_revision_id": source["recurrence_revision_id"],
            "enrolled_at_utc": now,
            "enrollment_json": enrollment,
            "current_revision_id": revision,
            "change_version": 1,
            "next_assignment_seq": 1,
            "status": "active",
            "retirement_intent_id": None,
            "created_by_subject_id": request["actor_subject_id"],
            "created_by_command_id": request["command_id"],
            "created_at_utc": now,
        },
    )
    advance_catalog(db)
    root = lookup(db, "related_task_rules", identity, "related_task_rule_id")
    return (
        {"rule": rule_view(db, root), "generation_started": False, "materialized_work_count": "0", "delivery": DELIVERY},
        "rule_created",
        True,
    )


def update(
    db: Any, request: dict[str, Any], root: dict[str, Any], context: Any, contracts: Any, now: str
) -> tuple[dict[str, Any], str, bool]:
    if root["status"] != "active":
        fail("semantic_conflict", "related_task_rule_id")
    prior = read_record(db, "related_task_rule_revisions", root["current_revision_id"])
    if request["configuration"]["task_owner"] != prior["configuration_json"]["task_owner"]:
        fail("semantic_conflict", "configuration.task_owner")
    config = normalize_configuration(request["configuration"], context, contracts)
    equal = config == prior["configuration_json"]
    pending = pending_adoption(db, root["related_task_rule_id"])
    if pending and pending["configuration_revision_id"] != root["current_revision_id"]:
        fail("environment_failure", "intent")
    if pending and not equal:
        fail("semantic_conflict", "configuration")
    different = None
    if request["adoption_scope"] == "upcoming_open" and equal and pending is None:
        different = db.execute(
            "SELECT 1 FROM related_task_assignments a JOIN related_task_assignment_revisions s "
            "ON s.assignment_revision_id=a.current_assignment_revision_id "
            "WHERE a.related_task_rule_id=? AND s.adopted_rule_revision_id<>? LIMIT 1",
            (root["related_task_rule_id"], root["current_revision_id"]),
        ).fetchone()
    wants = request["adoption_scope"] == "upcoming_open" and (not equal or pending is not None or different is not None)
    revision = root["current_revision_id"] if equal else configuration_record(db, root["related_task_rule_id"], config, request, now, prior)
    intent_id, high_water = None, None
    if wants and pending:
        intent_id, high_water = pending["intent_id"], pending["assignment_high_water"]
    elif wants:
        high_water = str(root["next_assignment_seq"] - 1)
        intent_id = new_intent(
            db,
            root,
            "adopt",
            {"configuration_revision_id": revision, "scope": "upcoming_open", "assignment_high_water": high_water},
            request,
            now,
        )
        if high_water == "0":
            db.execute("UPDATE related_task_intents SET status='complete' WHERE intent_id=?", (intent_id,))
    changed = not equal or wants and pending is None
    if changed:
        compare_and_swap(db, "related_task_rules", root["related_task_rule_id"], root["change_version"], {"current_revision_id": revision})
        advance_catalog(db)
    root = lookup(db, "related_task_rules", root["related_task_rule_id"], "related_task_rule_id")
    effect = "rule_configuration_updated" if not equal else "rule_adoption_requested" if changed else "rule_update_noop"
    return (
        {
            "rule": rule_view(db, root),
            "prior_rule_revision_id": prior["related_task_rule_revision_id"],
            "new_rule_revision_id": revision,
            "adoption_scope": request["adoption_scope"],
            "intent_id": intent_id,
            "assignment_high_water": high_water,
            "delivery": DELIVERY,
        },
        effect,
        bool(changed),
    )


def retire(db: Any, request: dict[str, Any], root: dict[str, Any], now: str) -> tuple[dict[str, Any], str, bool]:
    existing = intent_view(db, root["retirement_intent_id"])
    if existing:
        if existing["disposition"] != request["disposition"]:
            fail("semantic_conflict", "disposition")
        changed, identity, high_water, status = False, existing["intent_id"], existing["assignment_high_water"], existing["status"]
    else:
        high_water = str(root["next_assignment_seq"] - 1)
        payload = {"disposition": request["disposition"], "assignment_high_water": high_water}
        adoption = pending_adoption(db, root["related_task_rule_id"])
        if adoption and request["disposition"] != "keep_following":
            payload["superseded_adoption_intent_id"] = adoption["intent_id"]
            db.execute("UPDATE related_task_intents SET status='superseded' WHERE intent_id=?", (adoption["intent_id"],))
        identity = new_intent(db, root, "retire", payload, request, now)
        status = "complete" if high_water == "0" and adoption is None else "pending"
        if status == "complete":
            db.execute("UPDATE related_task_intents SET status='complete' WHERE intent_id=?", (identity,))
        compare_and_swap(
            db,
            "related_task_rules",
            root["related_task_rule_id"],
            root["change_version"],
            {"status": "retired", "retirement_intent_id": identity},
        )
        advance_catalog(db)
        changed = True
    root = lookup(db, "related_task_rules", root["related_task_rule_id"], "related_task_rule_id")
    return (
        {
            "rule": rule_view(db, root),
            "generation_stopped": True,
            "cleanup_status": status,
            "retirement_intent_id": identity,
            "assignment_high_water": high_water,
            "disposition": request["disposition"],
            "delivery": DELIVERY,
        },
        "rule_retired" if changed else "rule_retire_noop",
        changed,
    )


def read(db: Any, command: str, request: dict[str, Any], context: Any, contracts: Any, now: str) -> dict[str, Any]:
    query: dict[str, Any] = {"contract_version": CONTRACT, "ledger_instance_id": read_ledger_instance_id(db)}
    config = context.facet_cursor_config
    if command.endswith("list"):
        query.update(
            owner=request.get("owner"), source_item_id=request.get("source_item_id"), status=request["status"], limit=request["limit"]
        )
        clauses: list[str] = []
        args: list[Any] = []
        if request.get("owner") is not None:
            clauses.append("owner_key=?")
            args.append(canonical_json_bytes(request["owner"]).decode())
        if request.get("source_item_id") is not None:
            clauses.append("source_item_id=?")
            args.append(request["source_item_id"])
        if request["status"] != "all":
            clauses.append("status=?")
            args.append(request["status"])
        purpose, table, key, root = "list", "related_task_rules", "related_task_rule_id", None
    else:
        root = lookup(db, "related_task_rules", request["related_task_rule_id"], "related_task_rule_id")
        view = request["view"]
        if view == "rule":
            return {"rule": rule_view(db, root), "read_at_utc": now, "delivery": DELIVERY}
        if view == "proof":
            proof = lookup(db, "related_task_source_proofs", request["proof_id"], "proof_id")
            if proof["related_task_rule_id"] != root["related_task_rule_id"]:
                fail("referenced_row_not_found", "proof_id")
            return {
                "proof": stored_projection(db, "related_task_source_proofs", proof["proof_id"]),
                "read_at_utc": now,
                "delivery": DELIVERY,
            }
        purpose = view
        query.update(related_task_rule_id=root["related_task_rule_id"], view=view, limit=request.get("limit", "50"))
        if view == "assignments":
            table, key = "related_task_assignments", "assignment_seq"
            clauses, args = ["related_task_rule_id=?"], [root["related_task_rule_id"]]
        else:
            assignment = lookup(db, "related_task_assignments", request["assignment_id"], "assignment_id")
            if assignment["related_task_rule_id"] != root["related_task_rule_id"]:
                fail("referenced_row_not_found", "assignment_id")
            from spine.services.recurring_task_reads import assignment_view

            if view == "assignment":
                return {"assignment": assignment_view(db, assignment, root), "read_at_utc": now, "delivery": DELIVERY}
            query["assignment_id"] = assignment["assignment_id"]
            table, key = (
                ("related_task_generations", "generation_index")
                if view == "generations"
                else ("related_task_assignment_revisions", "change_version")
            )
            clauses, args = ["assignment_id=?"], [assignment["assignment_id"]]
    after = "" if purpose == "list" else "0"
    if "cursor" in request:
        after = verify_cursor(config, request["cursor"], query, purpose, now, catalog(db), contracts)["after"]
    clauses.append(key + ">?")
    args.append(after if purpose == "list" else int(after))
    limit = int(request["limit"])
    records = db.execute(
        "SELECT * FROM " + table + " WHERE " + " AND ".join(clauses) + " ORDER BY " + key + " LIMIT ?", (*args, limit + 1)
    ).fetchall()
    rows: list[dict[str, Any]] = []
    last = after
    for record in records[:limit]:
        if purpose == "list":
            value = rule_view(db, read_record(db, table, record[key]), summary=True)
        elif purpose == "assignments":
            from spine.services.recurring_task_reads import assignment_view

            assert root is not None
            value = assignment_view(db, read_record(db, table, record["assignment_id"]), root)
        else:
            value = stored_projection(db, table, record["generation_id" if purpose == "generations" else "assignment_revision_id"])
        if len(canonical_json_bytes(rows + [value])) > 1040384:
            if not rows:
                fail("capacity_exceeded", "response_bytes")
            break
        rows.append(value)
        last = str(record[key])
    more = len(records) > len(rows)
    token = None
    if more:
        token = sign_cursor(
            config, cursor_payload(config, purpose=purpose, query=query, catalog=catalog(db), now=now, after=last), contracts
        )
    return {
        "rows": rows,
        "query": query,
        "catalog_generation": catalog(db),
        "has_more": more,
        "next_cursor": token,
        "read_at_utc": now,
        "delivery": DELIVERY,
    }


def execute(
    command: str,
    request: Any,
    context: Any,
    *,
    contracts: RecurringTaskContracts,
    clock: Callable[[], str] | None = None,
    fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Internal development entry; shared command context, one owning transaction."""
    db, timeout = context.ledger, None
    clock = clock or (lambda: wire(datetime.now(UTC)))
    fault = fault or (lambda stage: None)
    runtime: dict[str, Any] = {"cutoffs": [], "audit_ids": []}
    try:
        if (
            not isinstance(db, LedgerConnection)
            or db.in_transaction
            or not getattr(db, "_recurring_tasks_enabled", False)
            or context.transport_metadata not in ({}, {"adapter": "cli"})
        ):
            fail("environment_failure", "admission")
        verify_candidate_schema(db)
        if not set(contracts.descriptor["required_existing_contract_versions"]) <= set(IMPLEMENTED_CONTRACT_VERSIONS):
            fail("environment_failure", "contract_version")
        if command not in INTERNAL_COMMANDS:
            fail("unsupported_command", "command")
        value = contracts.request(command, request)
        writes = contracts.descriptor["commands"][command]["mutates"]
        budget = FacetBudget()
        timeout = install_budget(db, budget)
        with db.atomic_command(write=writes):
            semantic = {
                "contract_version": CONTRACT,
                "normalization_version": "spine.recurring-related-tasks.normalization.v1",
                "canonical_json_version": "spine.canonical-json.v1",
                "request": value,
            }
            prior = get_command_receipt(db, value["command_id"]) if writes else None
            if prior:
                if prior["command"] != command or prior["semantic_facts"].get("request") != value:
                    fail("command_id_conflict", "command_id")
                if (
                    hash_canonical_json(prior["semantic_facts"]) != prior["semantic_facts_hash"]
                    or prior["semantic_facts"].get("normalized_result") != prior["result_identity_facts"]
                ):
                    fail("environment_failure", "receipt")
                response: dict[str, Any] = copy.deepcopy(prior["result_identity_facts"])
                receipt_id = command_derived_id(
                    prefix="command_receipt",
                    command=command,
                    command_id=value["command_id"],
                    row_role="command_receipt",
                    request_path="/command_receipt",
                )
                if prior["command_receipt_id"] != receipt_id or response["command_receipt_id"] != receipt_id:
                    fail("environment_failure", "receipt")
                original_rule = response["result"].get("rule")
                if original_rule:
                    retained = lookup(db, "related_task_rule_revisions", original_rule["rule_revision_id"], "receipt")
                    if (
                        retained["configuration_json"] != original_rule["configuration"]
                        or retained["configuration_hash"] != original_rule["configuration_hash"]
                    ):
                        fail("environment_failure", "receipt")
                for identity in response["audit_ids"]:
                    audit = db.execute("SELECT action,actor_ref FROM audit_log WHERE audit_id=?", (identity,)).fetchone()
                    if audit is None or audit[0] != response["effect"] or audit[1] != value["actor_subject_id"]:
                        fail("environment_failure", "receipt")
                response["replayed"] = True
                contracts.response(command, response)
                return dict(response)
            now = clock()
            try:
                if not isinstance(now, str) or wire(instant(now)) != now:
                    fail("environment_failure", "clock")
            except (TypeError, ValueError) as exc:
                raise SpineValidationError("environment_failure:clock", "invalid execution clock") from exc
            if writes and db.execute("SELECT 1 FROM subjects WHERE subject_id=?", (value["actor_subject_id"],)).fetchone() is None:
                fail("referenced_row_not_found", "actor_subject_id")
            if not writes:
                result = read(db, command, value, context, contracts, now)
                effect, changed = ("rules_listed" if command.endswith("list") else "rule_shown"), False
            elif command == PREFIX + "create":
                result, effect, changed = create(db, value, context, contracts, now)
            else:
                root = lookup(db, "related_task_rules", value["related_task_rule_id"], "related_task_rule_id")
                if command == PREFIX + "reconcile":
                    from spine.services.recurring_task_reconcile import continuation

                    continuation(db, value, root, context, contracts, now)
                expected(db, value, root)
                if command == PREFIX + "update":
                    result, effect, changed = update(db, value, root, context, contracts, now)
                elif command == PREFIX + "retire":
                    result, effect, changed = retire(db, value, root, now)
                elif command == PREFIX + "assignment.suppress":
                    from spine.services.recurring_task_states import suppress

                    result, effect, changed = suppress(db, value, root, now)
                elif command == PREFIX + "reconcile":
                    from spine.services.recurring_task_reconcile import reconcile

                    result, effect, changed = reconcile(
                        db, value, root, context, contracts, now, runtime, fault,
                        response_size=response_sizer(command, value, now, dry_run=context.dry_run),
                    )
                else:
                    fail(
                        "unsupported_command",
                        "command",
                        "manual reconciliation and suppression are not yet wired in this internal checkpoint",
                    )
            response = {
                "ok": True,
                "response_contract": RESPONSE,
                "command": command,
                "changed": changed,
                "effect": effect,
                "evaluated_at_utc": now,
                "result": result,
            }
            if writes:
                receipt_id = command_derived_id(
                    prefix="command_receipt",
                    command=command,
                    command_id=value["command_id"],
                    row_role="command_receipt",
                    request_path="/command_receipt",
                )
                audit_ids = list(runtime["audit_ids"])
                source_item_id = result["rule"]["source_item_id"] if "rule" in result else root["source_item_id"]
                if changed:
                    root_id = source_item_id
                    identity = command_derived_id(
                        prefix="audit", command=command, command_id=value["command_id"], row_role="audit", request_path="/audit"
                    )
                    audit_ids.append(identity)
                    db.execute(
                        "INSERT INTO audit_log(audit_id,item_id,stage,action,reason_code,actor_ref,payload_hash,created_at_utc) "
                        "VALUES(?,?,'related_task_rule',?,?,?,?,?)",
                        (
                            identity,
                            root_id,
                            effect,
                            effect,
                            value["actor_subject_id"],
                            audit_log_payload_hash({"command": command, "request": value, "result": result}),
                            now,
                        ),
                    )
                response = success_response(command, value, result, effect, changed, now, runtime, dry_run=context.dry_run)
                fault("audit")
                if not context.dry_run:
                    receipt = command_receipt(
                        command=command,
                        command_id=value["command_id"],
                        actor_subject_id=value["actor_subject_id"],
                        action_timestamp_utc=value["requested_at_utc"],
                        effect=effect,
                        semantic_facts={**semantic, "normalized_result": response},
                        result_identity_facts=response,
                        command_receipt_id=receipt_id,
                        item_id=source_item_id,
                        created_at_utc=now,
                    )
                    insert_command_receipt(db, receipt)
                    fault("receipt")
            else:
                response["commit_cutoff_recheck_required"] = True
            contracts.response(command, response)
            response_limit = int(value["limits"]["response_bytes"]) if command == PREFIX + "reconcile" else 1048576
            if len(canonical_json_bytes(response)) > response_limit:
                fail("capacity_exceeded", "limits.response_bytes" if command == PREFIX + "reconcile" else "response_bytes")
            if context.dry_run and writes:
                db._finalize_pending()
                raise Preview(response)
            if writes:
                try:
                    commit_now = clock()
                    if wire(instant(commit_now)) != commit_now or instant(commit_now) < instant(now):
                        fail("environment_failure", "clock")
                    if any(due <= commit_now for due in runtime["cutoffs"]):
                        fail("stale_evaluation", "evaluated_at_utc")
                except (TypeError, ValueError) as exc:
                    raise SpineValidationError("environment_failure:clock", "invalid commit clock") from exc
            budget.check()
        return response
    except Preview as preview:
        return preview.result
    except (SpineValidationError, sqlite3.Error) as exc:
        if isinstance(exc, SpineValidationError):
            code, _, field = exc.code.partition(":")
            if code == "source_continuity_unresolved":
                code, field = "semantic_conflict", field or "source"
        else:
            code, field = (
                ("semantic_conflict", "storage") if isinstance(exc, sqlite3.IntegrityError) else ("environment_failure", "storage")
            )
        return {
            "ok": False,
            "response_contract": RESPONSE,
            "command": command,
            "changed": False,
            "error": {"code": code, "field": field or "request", "message": str(exc)},
        }
    finally:
        if timeout is not None:
            db.set_progress_handler(None, 0)
            db.execute(f"PRAGMA busy_timeout={timeout}")
