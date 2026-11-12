"""R2 immutable configuration snapshots over existing composition authorities."""

from __future__ import annotations

import copy
from typing import Any

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.notification_profiles import compose_notification_plan, normalize_catalog_key
from spine.core.notifications import normalize_notification_policy
from spine.core.recurring_task_runtime import fail
from spine.ledger.notification_profiles import load_archetype, load_profile, require_owner_exists, resolve_default_profile
from spine.services import schedule_delivery
from spine.services.primary_locations import load_referenced_location, normalize_primary_location
from spine.services.recurring_task_leads import validate_reminder_lead
from spine.services.rendering_authoring import resolve


def normalize_configuration(value: dict[str, Any], context: Any, contracts: Any, *, source_time: dict[str, Any]) -> dict[str, Any]:
    """Resolve once; no task, application, approval, audit or receipt is created."""
    result = copy.deepcopy(value)
    db, owner = context.ledger, result["task_owner"]
    require_owner_exists(db, owner)
    template = result["task_template"]
    item = template["item"]
    for key in ("summary", "source_ref", "primary_location", "archetype"):
        item.setdefault(key, None)
    item["task_detail"].setdefault("priority", None)
    for subject in template["people"]["assignees"]:
        row = db.execute("SELECT status FROM subjects WHERE subject_id=?", (subject,)).fetchone()
        if row is None or row[0] != "active":
            fail("referenced_row_not_found", "configuration.task_template.people.assignees")
    if item["primary_location"] is not None:
        location = normalize_primary_location(item["primary_location"], field="configuration.task_template.item.primary_location")
        # Version facts belong to the stored location model, not its authoring union.
        item["primary_location"] = {k: v for k, v in location.items() if k in item["primary_location"]}
        if location["mode"] == "reference":
            load_referenced_location(db, location_id=location["location_id"], field="configuration.task_template.item.primary_location")
    archetype = None
    if item["archetype"] is not None:
        selection = item["archetype"]
        archetype = load_archetype(
            db, selection["item_archetype_id"], revision_id=selection.get("item_archetype_revision_id"), active_required=True
        )
        if "task" not in archetype["revision"]["compatible_item_types"]:
            fail("semantic_conflict", "configuration.task_template.item.archetype")
        selection.update(revision_resolution="exact", item_archetype_revision_id=archetype["revision"]["item_archetype_revision_id"])
    plan = result["notification_plan"]
    if plan is None:
        if result["delivery"] is not None or result["materialization"] != {"mode": "none"}:
            fail("invalid_request", "configuration.delivery")
    else:
        route = schedule_delivery.resolve_delivery(result["delivery"], ledger=db, defaults=context.delivery_target_defaults)
        snapshot = {k: v for k, v in route["snapshot"].items() if k != "delivery_state"}
        result["delivery"] = {"requested": result["delivery"], "resolved": snapshot}
        profile, binding, scopes = None, None, []
        if plan["mode"] == "explicit":
            profile = load_profile(
                db, plan["notification_profile_id"], revision_id=plan.get("notification_profile_revision_id"), active_required=True
            )
        elif plan["mode"] == "archetype_default":
            if archetype is None:
                fail("semantic_conflict", "configuration.task_template.item.archetype")
            scopes = plan["scope_chain"]
            for scope in scopes:
                require_owner_exists(db, scope)
            matched = resolve_default_profile(db, item_archetype_id=archetype["item_archetype_id"], item_type="task", scope_chain=scopes)
            if matched is None:
                if plan["on_no_match"] != "use_custom_only":
                    fail("referenced_row_not_found", "configuration.notification_plan.scope_chain")
            else:
                profile = matched["profile"]
                binding = matched["binding"]["notification_profile_binding_id"]
        if profile is not None and "task" not in profile["revision"]["compatible_item_types"]:
            fail("semantic_conflict", "configuration.notification_plan")
        composed = compose_notification_plan(
            profile["revision"]["templates"] if profile else [],
            suppress_template_keys=plan.get("suppress_template_keys", []),
            replacements=plan.get("replacements", []),
            custom_additions=plan["custom_additions"],
        )
        by_address = {}
        for entry in plan["rendering_applications"]:
            address = (entry["source_kind"], entry["source_key"])
            if address in by_address:
                fail("semantic_conflict", "configuration.notification_plan.rendering_applications")
            by_address[address] = entry["selection"]
        effective: list[dict[str, Any]] = []
        used: set[tuple[str, str]] = set()
        hashes: set[object] = set()
        for reminder, origin in zip(composed.reminders, composed.origins, strict=True):
            kind, source = origin["policy_origin"], origin["source_key"]
            key = reminder["policy_key"]
            try:
                normalize_catalog_key(key, "configuration.notification_plan")
            except SpineValidationError:
                fail("semantic_conflict", "configuration.notification_plan")
            if any(v["policy_key"] == key for v in effective):
                fail("semantic_conflict", "configuration.notification_plan")
            normalized = normalize_notification_policy(
                {
                    "authoring_contract": "spine.notification-schedule-authoring.v1",
                    "target": {"anchor_role": "task_due", "application_scope": "item"},
                    "schedule": reminder["schedule"],
                    "late_handling": reminder["late_handling"],
                },
                item_id="rrt-template-validation",
                item_version="1",
                command_id="rrt-template-validation-" + key,
                created_at_utc="2000-01-01T00:00:00Z",
                recipient_kind="subject",
                recipient_id="validation",
                channel="validation",
                delivery_target_id="validation",
            ).value
            if normalized["normalized_notification_schedule_hash"] in hashes:
                fail("semantic_conflict", "configuration.notification_plan")
            hashes.add(normalized["normalized_notification_schedule_hash"])
            pinned = {"kind": "ordinary"}
            if kind != "custom_addition":
                assert profile is not None
                pinned = next(t for t in profile["revision"]["templates"] if t["template_key"] == source).get("rendering", pinned)
            address = ("custom_addition" if kind == "custom_addition" else "profile_template", source)
            selection = by_address.get(address, {"kind": "ordinary"})
            if address in by_address:
                used.add(address)
            elif pinned["kind"] == "definition":
                fail("rendering_disclosure_unavailable", "configuration.notification_plan")
            if kind == "profile_template" and selection.get("kind") == "definition" and selection["definition"] != pinned.get("definition"):
                fail("rendering_disclosure_unavailable", "configuration.notification_plan")
            policy_origin = {"kind": kind}
            if kind != "custom_addition":
                assert profile is not None
                policy_origin.update(
                    notification_profile_id=profile["notification_profile_id"],
                    notification_profile_revision_id=profile["revision"]["notification_profile_revision_id"],
                    template_key=source,
                )
            try:
                presentation = resolve(  # type: ignore[no-untyped-call]  # Existing rendering-authoring boundary.
                    db, selection, policy={"item_id": None, **route}, item_type="task", origin=policy_origin, prospective_owner=owner
                )
            except SpineValidationError:
                fail("rendering_disclosure_unavailable", "configuration.notification_plan")
            effective.append(
                {
                    "policy_origin": kind,
                    "source_key": source,
                    "policy_key": key,
                    "template": {
                        "template_key": source,
                        "schedule": normalized["schedule"],
                        "late_handling": normalized["late_handling"],
                        "rendering": pinned
                        if kind == "profile_template"
                        else (
                            {"kind": "definition", "definition": selection["definition"]}
                            if selection["kind"] == "definition"
                            else {"kind": "ordinary"}
                        ),
                    },
                    "presentation": presentation,
                }
            )
        if used != set(by_address):
            fail("semantic_conflict", "configuration.notification_plan.rendering_applications")
        result["notification_plan"] = {
            "requested": plan,
            "resolved": {
                "selection_mode": plan["mode"],
                "profile": None
                if profile is None
                else {
                    "notification_profile_id": profile["notification_profile_id"],
                    "notification_profile_revision_id": profile["revision"]["notification_profile_revision_id"],
                    "normalized_profile_revision_hash": profile["revision"]["normalized_revision_hash"],
                },
                "notification_profile_binding_id": binding,
                "scope_chain": scopes,
                "effective_templates": sorted(effective, key=lambda v: v["policy_key"]),
            },
        }
        validate_reminder_lead(result, source_time)
    if len(canonical_json_bytes(result)) > 65536:
        fail("capacity_exceeded", "configuration")
    contracts.validate("types", result, definition="normalizedConfiguration", output=True)
    return result
