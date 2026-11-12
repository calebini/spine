"""Bounded explicit-reference admission, after replay and before freshness checks."""

from __future__ import annotations

from typing import Any

from spine.commands.recurring_task_runtime import fail


def exists(db: Any, table: str, key: str, value: str, field: str, *, parent: tuple[str, str] | None = None) -> None:
    # Identifiers are code-owned constants; only values come from the request.
    sql, args = f"SELECT 1 FROM {table} WHERE {key}=?", [value]
    if parent:
        sql += f" AND {parent[0]}=?"
        args.append(parent[1])
    if db.execute(sql, args).fetchone() is None:
        fail("referenced_row_not_found", field)


def owner(db: Any, value: dict[str, Any], field: str) -> None:
    if value["owner_kind"] == "system":
        return
    subject = value["owner_kind"] == "subject"
    name = "owner_subject_id" if subject else "owner_group_id"
    exists(db, "subjects" if subject else "subject_groups", "subject_id" if subject else "group_id", value[name], field + "." + name)


def validate(db: Any, request: dict[str, Any], context: Any) -> None:
    """Existence only: retirement, compatibility and authority remain semantics.

    Expected-version and target-generation/task comparison facts are not fresh
    references to resolve. Rendering selections retain their delegated disclosure
    failure contract, and catalog-default resolution remains with its owner.
    List filters are queries, not authoring references, and do not call this path.
    """
    exists(db, "subjects", "subject_id", request["actor_subject_id"], "actor_subject_id")
    if "owner" in request:
        owner(db, request["owner"], "owner")
    if "source" in request:
        exists(db, "coordination_items", "item_id", request["source"]["item_id"], "source.item_id")
    if "related_task_rule_id" in request:
        exists(db, "related_task_rules", "related_task_rule_id", request["related_task_rule_id"], "related_task_rule_id")
    if "assignment_id" in request:
        exists(db, "related_task_assignments", "assignment_id", request["assignment_id"], "assignment_id",
               parent=("related_task_rule_id", request["related_task_rule_id"]))
    config = request.get("configuration")
    if config is None:
        return
    owner(db, config["task_owner"], "configuration.task_owner")
    item = config["task_template"]["item"]
    location = item.get("primary_location")
    if location and location["mode"] == "reference":
        exists(db, "locations", "location_id", location["location_id"], "configuration.task_template.item.primary_location.location_id")
    archetype = item.get("archetype")
    if archetype:
        prefix = "configuration.task_template.item.archetype."
        exists(db, "item_archetypes", "item_archetype_id", archetype["item_archetype_id"], prefix + "item_archetype_id")
        if archetype["revision_resolution"] == "exact":
            exists(db, "item_archetype_revisions", "item_archetype_revision_id", archetype["item_archetype_revision_id"],
                   prefix + "item_archetype_revision_id", parent=("item_archetype_id", archetype["item_archetype_id"]))
    for subject in config["task_template"]["people"]["assignees"]:
        exists(db, "subjects", "subject_id", subject, "configuration.task_template.people.assignees")
    plan = config["notification_plan"]
    if plan is not None:
        if plan["mode"] == "explicit":
            prefix = "configuration.notification_plan."
            exists(db, "notification_profiles", "notification_profile_id", plan["notification_profile_id"],
                   prefix + "notification_profile_id")
            if plan["revision_resolution"] == "exact":
                exists(db, "notification_profile_revisions", "notification_profile_revision_id", plan["notification_profile_revision_id"],
                       prefix + "notification_profile_revision_id", parent=("notification_profile_id", plan["notification_profile_id"]))
        for scope in plan.get("scope_chain", []):
            owner(db, scope, "configuration.notification_plan.scope_chain")
    delivery = config["delivery"]
    if delivery is not None:
        name = "recipient_subject_id" if delivery["recipient_kind"] == "subject" else "recipient_group_id"
        exists(db, "subjects" if name == "recipient_subject_id" else "subject_groups",
               "subject_id" if name == "recipient_subject_id" else "group_id", delivery[name], "configuration.delivery." + name)
        target = delivery["target"]
        field = ("configuration.delivery.target.delivery_target_id" if target["resolution"] == "explicit"
                 else "configuration.delivery.target.default_key")
        identity = target.get("delivery_target_id")
        if target["resolution"] == "context_default":
            value = context.delivery_target_defaults.get(target["default_key"])
            if value is None or value == []:
                fail("referenced_row_not_found", field)
            if isinstance(value, str):
                identity = value
            elif isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], str):
                identity = value[0]
            # Ambiguous/invalid default shapes are semantic failures, not absent
            # rows; the owning resolver rejects them after freshness admission.
        if identity is not None:
            exists(db, "delivery_targets", "delivery_target_id", identity, field)
