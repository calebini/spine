"""Ordinary child composition for internal recurring-task pages; no subcommands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from spine.commands import core as c
from spine.commands import temporal_bindings as bindings
from spine.commands.recurring_task_runtime import PREFIX, fail, instant, wire
from spine.core import occurrence_details
from spine.core import temporal_bindings as binding_facts
from spine.core.hashing import command_derived_id, hash_canonical_json
from spine.core.notification_profiles import compose_notification_plan
from spine.core.notifications import NormalizedNotificationPolicy
from spine.core.provenance import derive_occurrence_provenance
from spine.ledger import item_reads
from spine.ledger.common import TemporalAnchorInput
from spine.ledger.items import create_next_item_version, create_task_v1
from spine.ledger.notification_profiles import insert_application, insert_assignment, load_archetype, load_profile, require_owner_exists
from spine.ledger.notifications import insert_notification_schedule_policy, load_notification_policies_at_version
from spine.ledger.ownership import advance_ownership_epoch
from spine.ledger.provenance import persist_binding_provenance
from spine.ledger.relations import create_item_relation
from spine.ledger.rendering_definitions import select_presentation
from spine.ledger.supporting import ItemLocationInput, ItemSubjectRoleInput
from spine.ledger.temporal_bindings import (
    increment_binding_catalog_generation,
    insert_temporal_binding,
    insert_temporal_binding_revision,
    target_from_source,
)
from spine.ledger.work import cancel_work_instance
from spine.services import schedule_delivery
from spine.services.primary_locations import inline_location_inputs, reference_location_input
from spine.services.rendering_authoring import resolve

COMMAND = PREFIX + "reconcile"


def child_id(seed: str, role: str, path: str, prefix: str | None = None) -> str:
    return command_derived_id(prefix=prefix or role, command=COMMAND, command_id=seed, row_role=role, request_path=path)


def materialization(config: dict[str, Any], now: str, *, policies: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    selected = config["materialization"]
    if selected["mode"] == "none":
        return dict(selected)
    entries = (config["notification_plan"] or {}).get("resolved", {}).get("effective_templates", [])
    grace = max((int(e["template"]["late_handling"].get("grace_seconds", "0")) for e in entries), default=0)
    if policies is not None:
        grace = max(grace, max((int(p["late_handling"].get("grace_seconds", "0")) for p in policies), default=0))
    return {
        "mode": "bounded",
        "evaluated_at_utc": now,
        "range_start_utc": wire(instant(now) - timedelta(seconds=max(int(selected["lookback_seconds"]), grace))),
        "range_end_utc": wire(instant(now) + timedelta(seconds=int(selected["horizon_seconds"]))),
        "limit": selected["opportunity_limit"],
    }


def source_facts(
    db: Any, root: dict[str, Any], recurrence: dict[str, Any], occurrence: dict[str, Any], now: str, *, persist: bool, command_id: str
) -> dict[str, Any]:
    item = item_reads.hydrated_item(db, root["source_item_id"])
    occurrence = occurrence_details.decorate_occurrence(item, recurrence, dict(occurrence), include_internal=True)
    original = occurrence["original_scheduled_fact"]
    derived = derive_occurrence_provenance(
        occurrence=occurrence,
        recurrence=recurrence,
        item=item,
        consumer="temporal_binding",
        producer=COMMAND,
        range_basis="original_schedule",
        range_start=original,
        range_end=occurrence_details.next_scheduled_fact(original, time_basis=recurrence["time_basis"]),
        created_at_utc=now,
    )
    if persist:
        persist_binding_provenance(db, derived, command_id=command_id, at=now)
    return {
        **binding_facts.source_from_occurrence(recurrence, occurrence),
        "source_target_version": str(item["current_version"]),
        "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
        "source_occurrence_key": occurrence["occurrence_key"],
        "source_occurrence_selector_ref": "recurrence_target_selector_" + hash_canonical_json(occurrence["target_occurrence_selector"]),
        "source_occurrence_provenance_id": derived.value["occurrence_provenance_id"],
        "target_occurrence_selector": occurrence["target_occurrence_selector"],
    }


def create(
    db: Any,
    context: Any,
    root: dict[str, Any],
    config: dict[str, Any],
    assignment_id: str,
    generation_id: str,
    source: dict[str, Any],
    request: dict[str, Any],
    now: str,
    fault: Any,
    restoration: Any = None,
) -> dict[str, Any]:
    """Create task/owner first; then actual-item presentation and complete work."""
    seed, actor, outer = generation_id, request["actor_subject_id"], request["command_id"]
    item, template = config["task_template"]["item"], config["task_template"]
    owner = config["task_owner"]
    require_owner_exists(db, owner)
    target = target_from_source(source, int(config["offset_seconds"]))
    task_id = child_id(seed, "item", "/task")
    anchor_id = child_id(seed, "due_anchor", "/temporal_binding/resolved_target", "anchor")
    relation_id = child_id(seed, "relation", "/relationship")
    binding_id = child_id(seed, "temporal_binding", "/temporal_binding")
    revision_id = child_id(seed, "temporal_binding_revision", "/temporal_binding/revisions/0")
    owner_id = child_id(seed, "item_access_owner", "/task_owner")
    audit_id = child_id(outer, "audit", "/assignments/" + assignment_id + "/audit")
    receipt_id = child_id(outer, "command_receipt", "/command_receipt")
    header = {
        "temporal_binding_id": binding_id,
        "binding_contract": "spine.relative-temporal-binding.v1",
        "target_item_id": task_id,
        "target_anchor_role": "task_due",
        "source_item_id": root["source_item_id"],
        "source_anchor_role": "event_start",
        "relationship_id": relation_id,
        "binding_mode": "follow_source",
        "source_terminal_behavior": "require_decision",
        "created_by_command_id": outer,
        "created_by_subject_id": actor,
        "created_at_utc": now,
        "binding_status": "active",
    }
    revision = binding_facts.revision_value(
        command=COMMAND,
        command_id=outer,
        revision_id=revision_id,
        binding=header,
        prior=None,
        revision_index=1,
        source=source,
        source_scope="selected_occurrence",
        offset=int(config["offset_seconds"]),
        target=target,
        target_item_version=1,
        target_anchor_id=anchor_id,
        resolution_kind="initial",
        created_at=now,
    )
    roles = tuple(
        ItemSubjectRoleInput(
            subject_id=subject,
            role="assignee",
            item_subject_role_id=child_id(seed, "item_subject_role", f"/task/people/assignees/{index}"),
            created_at_utc=now,
        )
        for index, subject in enumerate(template["people"]["assignees"])
    )
    locations: tuple[ItemLocationInput, ...] = ()
    location = item["primary_location"]
    if location is not None:
        lid = child_id(seed, "item_location", "/task/primary_location")
        locations = (
            reference_location_input(location_id=location["location_id"], item_location_id=lid, created_at_utc=now)
            if location["mode"] == "reference"
            else inline_location_inputs(
                location, location_id=child_id(seed, "location", "/task/primary_location"), item_location_id=lid, created_at_utc=now
            ),
        )
    created, mappings, evidence = [], [], []
    if restoration is not None:
        from spine.services.recurring_task_restoration import extra_supporting

        extra_roles, extra_locations = extra_supporting(restoration, seed, now)
        roles += extra_roles
        locations += extra_locations

    def extension(connection: Any) -> None:
        fault("task")
        advance_ownership_epoch(connection)
        fault("ownership_state")
        connection.execute(
            "INSERT INTO item_access_owners VALUES(?,?,1,?,?,?,NULL,?)",
            (task_id, owner_id, owner["owner_kind"], owner.get("owner_subject_id"), owner.get("owner_group_id"), outer),
        )
        connection.execute(
            "INSERT INTO item_access_owner_revisions VALUES(?,?,1,?,?,?,NULL,?,?,?,?)",
            (
                task_id,
                owner_id,
                owner["owner_kind"],
                owner.get("owner_subject_id"),
                owner.get("owner_group_id"),
                outer,
                now,
                actor,
                receipt_id,
            ),
        )
        fault("owner")
        create_item_relation(
            connection,
            relation_id=relation_id,
            source_item_id=task_id,
            target_item_id=root["source_item_id"],
            relation_type="part_of",
            created_at_utc=now,
            created_by_subject_id=actor,
            manage_transaction=False,
        )
        insert_temporal_binding(connection, value=header)
        insert_temporal_binding_revision(connection, value=revision)
        increment_binding_catalog_generation(connection)
        fault("binding")
        archetype_id = None
        if item["archetype"] is not None:
            a = item["archetype"]
            archetype = load_archetype(connection, a["item_archetype_id"], revision_id=a["item_archetype_revision_id"])
            archetype_id = child_id(seed, "item_archetype_assignment", "/task/archetype")
            insert_assignment(
                connection,
                assignment_id=archetype_id,
                item_id=task_id,
                item_version=1,
                archetype=archetype,
                selection_source=a["selection_source"],
                source_ref=a.get("source_ref"),
                actor_subject_id=actor,
                command_id=outer,
                created_at_utc=now,
            )
        policies: tuple[tuple[str, NormalizedNotificationPolicy], ...] = ()
        if restoration is not None:
            from spine.services.recurring_task_restoration import insert_policies

            policies, restored_mappings = insert_policies(
                connection, context, restoration, task_id=task_id, generation_id=seed, assignment_id=assignment_id,
                archetype_assignment_id=archetype_id, request=request, now=now,
            )
            mappings.extend(restored_mappings)
        elif config["notification_plan"] is not None:
            plan = config["notification_plan"]["resolved"]
            route = schedule_delivery.resolve_delivery(
                config["delivery"]["requested"], ledger=db, defaults=context.delivery_target_defaults
            )
            if {k: v for k, v in route["snapshot"].items() if k != "delivery_state"} != config["delivery"]["resolved"]:
                fail("semantic_conflict", "configuration.delivery", "resolved destination changed")
            entries = plan["effective_templates"]
            reminders = [
                {"policy_key": e["policy_key"], "schedule": e["template"]["schedule"], "late_handling": e["template"]["late_handling"]}
                for e in entries
            ]
            policies = (
                c._schedule_normalize_policies(
                    reminders, item_id=task_id, item_type="task", recurring=False, command_id=seed, created_at_utc=now, delivery=route
                )
                if entries
                else ()
            )
            for entry, (key, normalized) in zip(entries, policies, strict=True):
                presentation = entry["presentation"]
                selection = (
                    {"kind": "ordinary"}
                    if presentation["kind"] == "ordinary"
                    else {
                        "kind": "definition",
                        "definition": presentation["definition"],
                        "effective_selection_keys": presentation["effective_selection_keys"],
                        "authorization": {
                            "resolution": "exact",
                            "disclosure_authorization_id": presentation["disclosure_authorization_id"],
                        },
                    }
                )
                origin = {"kind": entry["policy_origin"]}
                if entry["policy_origin"] != "custom_addition":
                    origin.update(
                        notification_profile_id=plan["profile"]["notification_profile_id"],
                        notification_profile_revision_id=plan["profile"]["notification_profile_revision_id"],
                        template_key=entry["source_key"],
                    )
                selected = cast(Callable[..., dict[str, Any]], resolve)(
                    connection, selection, policy=normalized.value, item_type="task", origin=origin
                )
                insert_notification_schedule_policy(connection, normalized=normalized)
                select_presentation(connection, str(normalized.value["notification_policy_id"]), selected)
                mappings.append(
                    {
                        "assignment_id": assignment_id,
                        "generation_id": seed,
                        "task_item_id": task_id,
                        "policy_key": key,
                        "creation_token": seed + ":" + key,
                        "notification_intent_id": normalized.value["notification_intent_id"],
                        "notification_policy_id": normalized.value["notification_policy_id"],
                    }
                )
            if plan["profile"] is not None:
                pinned = plan["profile"]
                profile = load_profile(
                    connection, pinned["notification_profile_id"], revision_id=pinned["notification_profile_revision_id"]
                )
                requested = config["notification_plan"]["requested"]
                composed = compose_notification_plan(
                    profile["revision"]["templates"],
                    suppress_template_keys=requested.get("suppress_template_keys", []),
                    replacements=requested.get("replacements", []),
                    custom_additions=requested["custom_additions"],
                )
                # Separate generation-scoped row identity from real outer attribution.
                app_id = child_id(seed, "notification_profile_application", "/notification_plan")
                insert_application(
                    connection,
                    application_id=app_id,
                    item_id=task_id,
                    item_version=1,
                    profile=profile,
                    selection_mode=plan["selection_mode"],
                    scope_chain=plan["scope_chain"],
                    assignment_id=archetype_id,
                    binding_id=plan["notification_profile_binding_id"],
                    suppress_template_keys=composed.suppress_template_keys,
                    replacements=composed.replacements,
                    additions=composed.custom_additions,
                    effective_hash=composed.normalized_effective_policy_set_hash,
                    origins=composed.origins,
                    policies=[(key, p.value) for key, p in policies],
                    actor_subject_id=actor,
                    command_id=outer,
                    identity_seed=seed,
                    created_at_utc=now,
                )
        fault("policies")
        work, refs, _ = c._schedule_materialize_successor(
            connection,
            item_id=task_id,
            item_version=1,
            recurrence=None,
            policies=[p.value for _, p in policies],
            policy_key_by_intent={str(p.value["notification_intent_id"]): key for key, p in policies},
            materialization=materialization(config, now, policies=[cast(dict[str, Any], p.value) for _, p in policies]),
            command_id=outer,
            created_at=now,
        )
        created.extend(work)
        evidence.extend(refs)
        fault("work")

    create_task_v1(
        db,
        item_id=task_id,
        audit_id=audit_id,
        created_at_utc=now,
        created_by_subject_id=actor,
        title=item["title"],
        summary=item["summary"],
        source_ref=item["source_ref"],
        priority=item["task_detail"]["priority"],
        due_anchor=TemporalAnchorInput(
            anchor_kind="local_instant",
            anchor_id=anchor_id,
            local_date=target["local_date"],
            local_time=target["local_time"],
            timezone=target["timezone"],
            timezone_database_version=target["timezone_database_version"],
        ),
        subject_roles=roles,
        item_locations=locations,
        facet_entries=restoration.facet_entries if restoration is not None else (),
        insert_canonical_extension=extension,
        audit_action="rule_page_applied",
        audit_reason_code="new_source_slot",
        audit_payload={"assignment_id": assignment_id, "generation_id": seed},
    )
    return {
        "task_item_id": task_id,
        "task_item_version": "1",
        "temporal_binding_id": binding_id,
        "temporal_binding_revision_id": revision_id,
        "relationship_id": relation_id,
        "item_access_owner_id": owner_id,
        "audit_id": audit_id,
        "due": target["utc_instant"],
        "work": created,
        "policy_mappings": mappings,
    }


def change(
    page: Any,
    assignment: dict[str, Any],
    generation: dict[str, Any],
    binding: dict[str, Any],
    current: dict[str, Any],
    source: dict[str, Any],
    config: dict[str, Any],
    *,
    target: dict[str, Any] | None = None,
    cancel: bool = False,
    detach: bool = False,
    managed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One ordinary successor, or a binding-only freshness witness. No child receipt."""
    db, request, now = page.db, page.request, page.now
    task_id, version = generation["task_item_id"], int(current["current_version"])
    prior = binding["latest_revision"]
    creates_version = target is not None or cancel or bool(managed)
    next_version = version + 1 if creates_version else version
    audit_id = child_id(request["command_id"], "audit", "/assignments/" + assignment["assignment_id"] + "/audit")
    anchor_id = current["detail"]["due_anchor_id"]
    if target is not None:
        anchor_id = child_id(request["command_id"], "due_anchor", "/assignments/" + assignment["assignment_id"] + "/due", "anchor")
    target_facts = target or bindings._scheduled_for_target(current)
    revision = binding_facts.revision_value(
        command=COMMAND,
        command_id=request["command_id"],
        revision_id=child_id(
            request["command_id"], "temporal_binding_revision", "/assignments/" + assignment["assignment_id"] + "/binding"
        ),
        binding=binding,
        prior=prior,
        revision_index=int(prior["revision_index"]) + 1,
        source=source,
        source_scope="selected_occurrence",
        offset=int(config["offset_seconds"]),
        target=target_facts,
        target_item_version=next_version,
        target_anchor_id=anchor_id,
        resolution_kind="source_terminal"
        if cancel
        else "detached"
        if detach
        else "target_rescheduled"
        if target is not None
        else "source_refreshed",
        created_at=now,
    )

    def prerequisites(connection: Any, _version: int) -> None:
        if target is not None:
            from spine.ledger.common import insert_temporal_anchor

            insert_temporal_anchor(
                connection,
                anchor=TemporalAnchorInput(
                    anchor_kind="local_instant",
                    anchor_id=anchor_id,
                    local_date=target["local_date"],
                    local_time=target["local_time"],
                    timezone=target["timezone"],
                    timezone_database_version=target["timezone_database_version"],
                ),
                anchor_id=anchor_id,
                default_created_at_utc=now,
            )

    def extension(connection: Any, successor: int) -> None:
        from spine.ledger.temporal_bindings import retire_temporal_binding

        if managed:
            adopt_supporting(page, assignment, generation, current, successor, config, managed)

        insert_temporal_binding_revision(connection, value=revision)
        if (cancel or detach) and binding["binding_status"] == "active":
            retire_temporal_binding(
                connection, temporal_binding_id=binding["temporal_binding_id"], command_id=request["command_id"], retired_at_utc=now
            )
        increment_binding_catalog_generation(connection)
        page.fault("binding")
        reconcile_work(
            page,
            task_id,
            successor,
            config,
            target_changed=target is not None,
            terminal=cancel,
            stale=detach,
            materialize=not cancel and not detach,
        )

    if creates_version:
        detail: dict[str, object] = {"task_status": "cancelled"} if cancel else {"due_anchor_id": anchor_id}
        edits: dict[str, Any] = {}
        if managed:
            detail.update(managed.get("task_detail", {}))
            if "priority" in managed:
                detail["priority"] = managed["priority"]
            edits = {k: managed[k] for k in ("title", "summary", "source_ref") if k in managed}
            if "assignees" in managed:
                edits.update(
                    subject_role_replacement_roles=("assignee",),
                    subject_roles=tuple(
                        ItemSubjectRoleInput(
                            subject_id=s,
                            role="assignee",
                            item_subject_role_id=child_id(
                                request["command_id"],
                                "item_subject_role",
                                "/assignments/" + assignment["assignment_id"] + "/assignees/" + str(i),
                            ),
                            created_at_utc=now,
                        )
                        for i, s in enumerate(managed["assignees"])
                    ),
                )
        create_next_item_version(
            db,
            item_id=task_id,
            target_version=version,
            created_at_utc=now,
            created_by_subject_id=request["actor_subject_id"],
            audit_id=audit_id,
            task_detail=detail,
            **edits,
            audit_action="rule_page_applied",
            reason_code="source_cancelled" if cancel else "source_moved",
            audit_payload={"assignment_id": assignment["assignment_id"]},
            insert_prerequisites=prerequisites,
            insert_canonical_extension=extension,
            supporting_command_id=request["command_id"],
        )
        page.runtime["audit_ids"].append(audit_id)
        page.fault("task")
    else:
        extension(db, version)
    page.changed = True
    page.mutations += 1
    return {"task_item_version": str(next_version), "temporal_binding_revision_id": revision["temporal_binding_revision_id"]}


def reconcile_work(
    page: Any,
    item_id: str,
    version: int,
    config: dict[str, Any],
    *,
    target_changed: bool = False,
    terminal: bool = False,
    stale: bool = False,
    materialize: bool = True,
) -> None:
    """Bound complete ordinary work history before delegating classification."""
    db = page.db
    remaining = page.limits["work_rows"]
    rows = db.execute(
        "SELECT work_instance_id FROM work_instances WHERE item_id=? ORDER BY work_instance_id LIMIT ?", (item_id, remaining + 1)
    ).fetchall()
    if len(rows) > remaining:
        page.unit_oversized = True
        fail("capacity_exceeded", "limits.work_rows")
    policies = [p for p in load_notification_policies_at_version(db, item_id=item_id, item_version=version) if p["status"] == "active"]
    status = db.execute("SELECT task_status FROM task_details WHERE item_id=? AND version=?", (item_id, version)).fetchone()
    terminal = terminal or status is None or status[0] != "open"
    cancelled, retained, protected, reasons = c._schedule_reconcile_work_plan(
        db,
        item_id=item_id,
        active_policies=policies,
        target_changed=target_changed,
        recurrence_changed=False,
        temporal_binding_stale=stale,
        parent_terminal=terminal,
    )
    for identity in cancelled:
        cancel_work_instance(db, work_instance_id=identity, cancelled_at_utc=page.now, reason_code=reasons[identity], require_fresh=False)
    page.work["cancelled"].extend(cancelled)
    page.work["retained"].extend(retained)
    page.work["protected_stale"].extend(protected)
    if cancelled:
        page.changed = True
    if materialize and not terminal:
        created, _, _ = c._schedule_materialize_successor(
            db,
            item_id=item_id,
            item_version=version,
            recurrence=None,
            policies=policies,
            policy_key_by_intent={str(p["notification_intent_id"]): str(p["notification_intent_id"]) for p in policies},
            materialization=materialization(config, page.now),
            command_id=page.request["command_id"],
            created_at=page.now,
        )
        page.work["created"].extend(created)
        if created:
            page.changed = True
    page.fault("work")


def mappings(db: Any, assignment_id: str, generation: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Map only the family's actual immutable creation tokens, never unrelated policies."""
    from spine.ledger.supporting import current_notification_policies

    result = []
    version = db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (generation["task_item_id"],)).fetchone()[0]
    for policy in current_notification_policies(db, item_id=generation["task_item_id"], version=version):
        token = str(policy.get("intent_created_by_command_id", ""))
        key = token.rpartition(":")[2]
        belongs = token.startswith(generation["generation_id"] + ":")
        if not belongs:
            from spine.commands.receipts import get_command_receipt

            receipt = get_command_receipt(db, token.rpartition(":")[0])
            belongs = (
                receipt is not None
                and receipt["command"] == COMMAND
                and any(
                    p["generation_id"] == generation["generation_id"] and p["notification_intent_id"] == policy["notification_intent_id"]
                    for p in receipt["result_identity_facts"]["result"].get("policy_mappings", [])
                )
            )
        if policy["status"] != "active" or not belongs:
            continue
        result.append(
            {
                "assignment_id": assignment_id,
                "generation_id": generation["generation_id"],
                "task_item_id": generation["task_item_id"],
                "policy_key": key,
                "creation_token": token,
                "notification_intent_id": policy["notification_intent_id"],
                "notification_policy_id": policy["notification_policy_id"],
            }
        )
    return result


def adopt_supporting(
    page: Any,
    assignment: dict[str, Any],
    generation: dict[str, Any],
    current: dict[str, Any],
    version: int,
    config: dict[str, Any],
    patch: dict[str, Any],
) -> None:
    """Replace only fresh successor supporting rows, retaining historical rows."""
    from spine.ledger.notification_profiles import current_assignment
    from spine.ledger.notifications import remove_copied_notification_policy
    from spine.ledger.supporting import insert_item_location
    from spine.services.notification_profile_application import persist_schedule_update_profile

    db, request, now = page.db, page.request, page.now
    task_id, command_id = generation["task_item_id"], request["command_id"]
    path = "/assignments/" + assignment["assignment_id"]
    if "primary_location" in patch:
        db.execute("DELETE FROM item_locations WHERE item_id=? AND version=? AND role='primary'", (task_id, version))
        location = patch["primary_location"]
        if location is not None:
            iid = child_id(command_id, "item_location", path + "/primary_location")
            selected = (
                reference_location_input(location_id=location["location_id"], item_location_id=iid, created_at_utc=now)
                if location["mode"] == "reference"
                else inline_location_inputs(
                    location,
                    location_id=child_id(command_id, "location", path + "/primary_location"),
                    item_location_id=iid,
                    created_at_utc=now,
                )
            )
            insert_item_location(db, item_id=task_id, version=version, item_location=selected, default_created_at_utc=now)
    if "archetype" not in patch and "reminders" not in patch:
        return
    selected_archetype = config["task_template"]["item"]["archetype"]
    old = current_assignment(db, item_id=task_id, item_version=int(current["current_version"]))
    desired_assignment = None
    if selected_archetype is not None:
        archetype = load_archetype(
            db, selected_archetype["item_archetype_id"], revision_id=selected_archetype["item_archetype_revision_id"]
        )
        desired_assignment = {
            "item_archetype_assignment_id": child_id(command_id, "item_archetype_assignment", path + "/archetype"),
            "archetype": archetype,
            "selection_source": selected_archetype["selection_source"],
            "source_ref": selected_archetype.get("source_ref"),
        }
        if "archetype" not in patch and old is not None:
            # Let the existing owner retain the copied assignment. Only its ID
            # is needed by a replacement application below.
            copied = current_assignment(db, item_id=task_id, item_version=version)
            if copied is None:
                fail("environment_failure", "assignment")
            desired_assignment["item_archetype_assignment_id"] = copied["item_archetype_assignment_id"]
    desired_policies: tuple[tuple[str, NormalizedNotificationPolicy], ...] = ()
    desired_application = None
    if "reminders" in patch:
        plan = (config["notification_plan"] or {}).get("resolved", {})
        entries = plan.get("effective_templates", [])
        route = (
            schedule_delivery.resolve_delivery(
                config["delivery"]["requested"], ledger=db, defaults=page.context.delivery_target_defaults
            ) if entries else None
        )
        if route and {k: v for k, v in route["snapshot"].items() if k != "delivery_state"} != config["delivery"]["resolved"]:
            fail("semantic_conflict", "configuration.delivery")
        family = mappings(db, assignment["assignment_id"], generation, config)
        family_ids = {p["notification_intent_id"] for p in family}
        current_family = [p for p in current["notification_policies"] if p["notification_intent_id"] in family_ids]
        by_key = {p["policy_key"]: p for p in family}
        desired = []
        for selected in entries:
            key = selected["policy_key"]
            identity = by_key.get(key)
            desired.append(
                {
                    "policy_key": key,
                    "schedule": selected["template"]["schedule"],
                    "late_handling": selected["template"]["late_handling"],
                    **(
                        {
                            "notification_intent_id": identity["notification_intent_id"],
                            "notification_policy_id": identity["notification_policy_id"],
                        }
                        if identity
                        else {}
                    ),
                }
            )
        desired_policies, _, _ = c._schedule_update_normalize_policies(
            current_family,
            desired=desired,
            delivery=route,
            item=current,
            next_version=version,
            command_id=command_id,
            updated_at=now,
            policy_keys={p["notification_intent_id"]: p["policy_key"] for p in family},
            established_policy_intents=family_ids,
            recurring=False,
        )
        for prior in current_family:
            remove_copied_notification_policy(
                db, item_id=task_id, item_version=version, notification_intent_id=prior["notification_intent_id"]
            )
        for selected, (_key, policy) in zip(entries, desired_policies, strict=True):
            origin = {"kind": selected["policy_origin"]}
            if selected["policy_origin"] != "custom_addition":
                origin.update(
                    notification_profile_id=plan["profile"]["notification_profile_id"],
                    notification_profile_revision_id=plan["profile"]["notification_profile_revision_id"],
                    template_key=selected["source_key"],
                )
            presentation = selected["presentation"]
            selection = (
                {"kind": "ordinary"}
                if presentation["kind"] == "ordinary"
                else {
                    "kind": "definition",
                    "definition": presentation["definition"],
                    "effective_selection_keys": presentation["effective_selection_keys"],
                    "authorization": {"resolution": "exact", "disclosure_authorization_id": presentation["disclosure_authorization_id"]},
                }
            )
            resolved = cast(Callable[..., dict[str, Any]], resolve)(db, selection, policy=policy.value, item_type="task", origin=origin)
            insert_notification_schedule_policy(db, normalized=policy)
            select_presentation(db, str(policy.value["notification_policy_id"]), resolved)
            page.mappings.append(
                {
                    "assignment_id": assignment["assignment_id"],
                    "generation_id": generation["generation_id"],
                    "task_item_id": task_id,
                    "policy_key": selected["policy_key"],
                    "creation_token": policy.value["intent_created_by_command_id"],
                    "notification_intent_id": policy.value["notification_intent_id"],
                    "notification_policy_id": policy.value["notification_policy_id"],
                }
            )
        active = {p.value["notification_intent_id"] for _, p in desired_policies}
        for prior in current_family:
            if prior["notification_intent_id"] not in active:
                insert_notification_schedule_policy(
                    db, normalized=c._schedule_disabled_policy(prior, item_version=version, command_id=command_id, updated_at=now)
                )
        if plan.get("profile"):
            pin = plan["profile"]
            profile = load_profile(db, pin["notification_profile_id"], revision_id=pin["notification_profile_revision_id"])
            requested = config["notification_plan"]["requested"]
            composed = compose_notification_plan(
                profile["revision"]["templates"],
                suppress_template_keys=requested.get("suppress_template_keys", []),
                replacements=requested.get("replacements", []),
                custom_additions=requested["custom_additions"],
            )
            desired_application = {
                "notification_profile_application_id": child_id(
                    command_id, "notification_profile_application", path + "/notification_plan"
                ),
                "profile": profile,
                "selection_mode": plan["selection_mode"],
                "scope_chain": plan["scope_chain"],
                "binding_id": plan["notification_profile_binding_id"],
                "composed": composed,
            }
    persist_schedule_update_profile(
        db,
        prepared={
            "replace_assignment": "archetype" in patch,
            "replace_application": "reminders" in patch,
            "desired_assignment": desired_assignment,
            "desired_application": desired_application,
        },
        item_id=task_id,
        item_version=version,
        command_id=command_id,
        actor_subject_id=request["actor_subject_id"],
        updated_at_utc=now,
        policies=[(k, p.value) for k, p in desired_policies],
    )
