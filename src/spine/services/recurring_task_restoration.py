"""Copy a cancelled generation's actual facts; never re-resolve a catalog default."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from spine.core import facets as facet_codec
from spine.core.errors import SpineValidationError
from spine.core.notifications import NormalizedNotificationPolicy, normalize_notification_policy
from spine.core.recurring_task_runtime import fail
from spine.ledger import facets
from spine.ledger.common import TemporalAnchorInput
from spine.ledger.notification_profiles import current_application, current_assignment, insert_application
from spine.ledger.notifications import insert_notification_schedule_policy
from spine.ledger.recurring_task_sources import ProofBudget
from spine.ledger.rendering_definitions import load_presentation, select_presentation
from spine.ledger.supporting import ItemLocationInput, ItemSubjectRoleInput
from spine.ledger.transactions import LedgerConnection
from spine.services import rendering_authoring, schedule_delivery
from spine.services.recurring_task_operations import ChildInvocation


@dataclass(frozen=True)
class Restoration:
    current: dict[str, Any]
    configuration: dict[str, Any]
    family_keys: dict[str, str]
    facet_entries: tuple[dict[str, Any], ...]
    application: dict[str, Any] | None


def defer_anchor(snapshot: Restoration, seed: str) -> TemporalAnchorInput | None:
    """Copy the actual optional defer fact into the new item, not its old ID."""
    from spine.services.recurring_task_children import child_id

    anchor = snapshot.current["detail"].get("defer_until_anchor")
    if anchor is None:
        return None
    fields = {key: anchor[key] for key in (
        "anchor_kind", "local_date", "local_time", "timezone", "timezone_database_version",
        "utc_instant", "window_start_utc", "window_end_utc", "source",
    ) if key in anchor}
    return TemporalAnchorInput(**fields, anchor_id=child_id(seed, "defer_anchor", "/restored/defer", "anchor"))


def prepare(db: LedgerConnection, *, command_id: str, budget: ProofBudget, assignment_id: str,
            generation: dict[str, Any], current: dict[str, Any], binding: dict[str, Any],
            config: dict[str, Any]) -> Restoration:
    from spine.services.recurring_task_children import child_id, mappings

    item_id, version = generation["task_item_id"], int(current["current_version"])
    budget.spend(len(current["subject_roles"]) + len(current["locations"]) + len(current["notification_policies"]))
    restored = copy.deepcopy(config)
    item = restored["task_template"]["item"]
    for key in ("title", "summary", "source_ref"):
        item[key] = current["version"][key]
    item["task_detail"]["priority"] = current["detail"]["priority"]
    restored["offset_seconds"] = binding["latest_revision"]["offset_seconds"]
    restored["task_template"]["people"]["assignees"] = sorted({
        row["subject_id"] for row in current["subject_roles"] if row["role"] == "assignee" and row["status"] == "active"
    })
    for role in current["subject_roles"]:
        if role["status"] == "active":
            subject = db.execute("SELECT status FROM subjects WHERE subject_id=?", (role["subject_id"],)).fetchone()
            if subject is None or subject[0] != "active":
                fail("semantic_conflict", "configuration.task_template", "restored subject is unavailable")
    location = next((row for row in current["locations"] if row["role"] == "primary"), None)
    item["primary_location"] = None if location is None else {"mode": "reference", "location_id": location["location_id"]}
    archetype = current_assignment(db, item_id=item_id, item_version=version)
    item["archetype"] = None if archetype is None else {
        "item_archetype_id": archetype["item_archetype_id"],
        "item_archetype_revision_id": archetype["item_archetype_revision_id"],
        "revision_resolution": "exact", "selection_source": archetype["selection_source"],
        **({"source_ref": archetype["source_ref"]} if archetype["source_ref"] is not None else {}),
    }
    receipt = child_id(command_id, "command_receipt", "/command_receipt")
    entries = []
    for prior in facets.load_snapshot(db, item_id, version):
        budget.spend()
        definition = facets.load_definition(db, prior["facet_schema_revision_id"])
        values = facet_codec.decode_values(definition, prior["values_json"], contract=prior["value_contract_version"])
        try:
            entry = facets.prepare_entry(db, item_id=item_id, item_version=version, binding_id=prior["facet_binding_id"],
                                         values=values, receipt_id=receipt)
        except SpineValidationError as exc:
            if exc.code.startswith("facet_"):
                fail("semantic_conflict", "configuration.task_template", "restored facet is unavailable")
            raise
        if any(prior[key] != entry[key] for key in facets.ENTRY_COLUMNS if key != "source_command_receipt_id"):
            fail("semantic_conflict", "configuration.task_template", "restoration cannot migrate a facet revision")
        entries.append(entry)
    family = {row["notification_intent_id"]: row["policy_key"] for row in mappings(db, assignment_id, generation, config)}
    return Restoration(current, restored, family, tuple(entries), current_application(db, item_id=item_id, item_version=version))


def extra_supporting(snapshot: Restoration, seed: str, now: str) -> tuple[tuple[ItemSubjectRoleInput, ...], tuple[ItemLocationInput, ...]]:
    from spine.services.recurring_task_children import child_id

    # New item-scoped rows, the same explicit subjects and location identities.
    # Assignees/primary location are composed by the ordinary child path.
    roles = tuple(ItemSubjectRoleInput(
        subject_id=row["subject_id"], role=row["role"], status=row["status"], created_at_utc=now,
        item_subject_role_id=child_id(seed, "item_subject_role", "/restored/roles/" + row["item_subject_role_id"]),
    ) for row in snapshot.current["subject_roles"] if row["role"] != "assignee" or row["status"] != "active")
    locations = tuple(ItemLocationInput(
        role=row["role"], location_id=row["location_id"], created_at_utc=now,
        item_location_id=child_id(seed, "item_location", "/restored/locations/" + row["item_location_id"]),
    ) for row in snapshot.current["locations"] if row["role"] != "primary")
    return roles, locations


def pinned_selection(presentation: dict[str, Any]) -> dict[str, Any]:
    if presentation["kind"] == "ordinary":
        return {"kind": "ordinary"}
    return {"kind": "definition", "definition": presentation["definition"],
            "effective_selection_keys": presentation["effective_selection_keys"],
            "authorization": {"resolution": "exact", "disclosure_authorization_id": presentation["disclosure_authorization_id"]}}


def restored_policy_inputs(db: LedgerConnection, prior: dict[str, Any], defaults: Mapping[str, Any]
                           ) -> tuple[schedule_delivery.ResolvedDelivery, dict[str, Any], dict[str, Any]]:
    if prior["target"]["anchor_role"] != "task_due" or prior["target"]["application_scope"] != "item":
        fail("semantic_conflict", "configuration.task_template", "restored task has an independent recurrence target")
    recipient = "recipient_subject_id" if prior["recipient_kind"] == "subject" else "recipient_group_id"
    try:
        route = schedule_delivery.resolve_delivery({
            "recipient_kind": prior["recipient_kind"], recipient: prior[recipient], "channel": prior["channel"],
            "target": {"resolution": "explicit", "delivery_target_id": prior["delivery_target_id"]},
        }, ledger=db, defaults=defaults)
    except SpineValidationError:
        fail("semantic_conflict", "configuration.delivery", "restored destination is unavailable")
    selection = pinned_selection(load_presentation(db, prior["notification_policy_id"]))
    origin = cast(Callable[..., dict[str, Any]], rendering_authoring.policy_origin)(db, prior)
    return route, selection, origin


def restored_policy(prior: dict[str, Any], route: schedule_delivery.ResolvedDelivery, *, generation_id: str, key: str | None,
                    task_id: str, now: str) -> NormalizedNotificationPolicy:
    from spine.services.recurring_task_children import child_id

    token = generation_id + ":" + key if key is not None else child_id(
        generation_id, "notification", "/restored/independent/" + prior["notification_intent_id"]
    )
    return normalize_notification_policy({
        "authoring_contract": "spine.notification-schedule-authoring.v1",
        "target": {k: prior["target"][k] for k in ("anchor_role", "application_scope")},
        "schedule": prior["schedule"], "late_handling": prior["late_handling"],
    }, item_id=task_id, item_version="1", command_id=token, created_at_utc=now,
        recipient_kind=route["recipient_kind"], recipient_id=route["recipient_id"], channel=route["channel"],
        delivery_target_id=route["delivery_target_id"])


def insert_policies(db: LedgerConnection, invocation: ChildInvocation, snapshot: Restoration, *, task_id: str, generation_id: str,
                    assignment_id: str, archetype_assignment_id: str | None
                    ) -> tuple[tuple[tuple[str, NormalizedNotificationPolicy], ...], list[dict[str, Any]]]:
    from spine.services.recurring_task_children import child_id

    now = invocation.now
    policies, mappings, by_prior = [], [], {}
    for prior in snapshot.current["notification_policies"]:
        if prior["status"] != "active":
            continue
        route, selection, origin = restored_policy_inputs(db, prior, invocation.delivery_target_defaults)
        old_id = prior["notification_intent_id"]
        key = snapshot.family_keys.get(old_id)
        # Family keys retain the ratified generation/key convention. Independent
        # reminders have no family key: use the existing command-ID derivation
        # over this new generation and the predecessor's immutable intent ID.
        normalized = restored_policy(prior, route, generation_id=generation_id, key=key, task_id=task_id, now=now)
        presentation = cast(Callable[..., dict[str, Any]], rendering_authoring.resolve)(
            db, selection, policy=normalized.value, item_type="task", origin=origin
        )
        insert_notification_schedule_policy(db, normalized=normalized)
        select_presentation(db, str(normalized.value["notification_policy_id"]), presentation)
        policies.append((key if key is not None else old_id, normalized))
        by_prior[old_id] = normalized.value
        if key is not None:
            mappings.append({
                "assignment_id": assignment_id, "generation_id": generation_id, "task_item_id": task_id,
                "policy_key": key, "creation_token": generation_id + ":" + key,
                "notification_intent_id": normalized.value["notification_intent_id"],
                "notification_policy_id": normalized.value["notification_policy_id"],
            })
    application = snapshot.application
    if application is not None:
        origins, linked = [], []
        for origin in application["policies"]:
            policy = by_prior.get(origin["notification_intent_id"])
            if policy is None:
                continue
            key = origin["source_key"] if origin["policy_origin"] == "custom_addition" else "profile_" + origin["source_key"]
            origins.append({"policy_key": key, "policy_origin": origin["policy_origin"], "source_key": origin["source_key"]})
            linked.append((key, policy))
        insert_application(
            db, application_id=child_id(generation_id, "notification_profile_application", "/notification_plan"),
            item_id=task_id, item_version=1, profile=application["profile"], selection_mode=application["selection_mode"],
            scope_chain=application["scope_chain"], assignment_id=archetype_assignment_id,
            binding_id=application["notification_profile_binding_id"], suppress_template_keys=application["suppress_template_keys"],
            replacements=application["replacements"], additions=application["additions"],
            effective_hash=application["normalized_effective_policy_set_hash"], origins=origins, policies=linked,
            actor_subject_id=invocation.actor_subject_id, command_id=invocation.command_id, identity_seed=generation_id, created_at_utc=now,
        )
    return tuple(policies), mappings
