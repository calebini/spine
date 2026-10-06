"""Version-selected local rendering commands over the shared command handlers.

The frozen web registries do not expose these successor families.
"""

from __future__ import annotations

import copy
import sqlite3
from dataclasses import replace

from spine.commands import core, rendering_catalog, rendering_profiles
from spine.commands.facet_runtime import FacetBudget, install_budget, utc_now, wire_time
from spine.commands.rendering_runtime import RenderingAdmission
from spine.core import rendering_definitions as codec
from spine.core.errors import SpineValidationError
from spine.ledger.rendering_definitions import finalize, invariant
from spine.services.rendering_authoring import RenderingAuthoring
from spine.web.errors import WebError


def accepts(command, request):
    if command.startswith(("notification_rendering_definition.", "notification_rendering_disclosure.")):
        return True
    selector = request.get("contract_version")
    if command in {"notification_profile.create", "notification_profile.revise", "notification_profile.show", "notification_profile.list"}:
        return selector == codec.PROFILE_V2
    if command in {"schedule.create", "schedule.update"}:
        return selector == ("spine.schedule-create.v3" if command.endswith("create") else "spine.schedule-update.v3")
    if command in {"reminder.create", "reminder.edit"}:
        patch = request.get("patch")
        notification = (
            request.get("notification") if command.endswith("create") else (patch.get("notification") if isinstance(patch, dict) else None)
        )
        return isinstance(notification, dict) and notification.get("authoring_contract") == "spine.notification-schedule-authoring.v2"
    return False


def normalized_request(command, request):
    value = copy.deepcopy(dict(request))
    codec.bounded(value, 32768, "request")
    if command in {"notification_profile.create", "notification_profile.revise"}:
        revision = codec.normalize_profile_v2(value.get("revision"))
        value["revision"] = {
            "compatible_item_types": list(revision.compatible_item_types),
            "templates": [{k: v for k, v in template.items() if k != "normalized_template_hash"} for template in revision.templates],
        }
    patch = value.get("patch", {})
    if not isinstance(patch, dict):
        codec.fail("invalid_request", "patch")
    plan = value.get("notification_plan") or patch.get("notification_plan")
    if isinstance(plan, dict) and "rendering_applications" in plan:
        apps = plan["rendering_applications"]
        if not isinstance(apps, list) or len(apps) > 32:
            codec.fail("invalid_request", "rendering_applications")
        for entry in apps:
            codec.exact(entry, {"source_kind", "source_key", "selection"})
            entry["selection"] = codec.normalize_selection(entry["selection"])
        apps.sort(key=lambda e: (e["source_kind"], e["source_key"]))
    presentations = patch.get("policy_presentations")
    if isinstance(presentations, list):
        for entry in presentations:
            codec.exact(entry, {"notification_policy_id", "selection"})
            entry["selection"] = codec.normalize_selection(entry["selection"])
        presentations.sort(key=lambda e: e["notification_policy_id"])
    notification = value.get("notification", patch.get("notification"))
    if isinstance(notification, dict) and "presentation" in notification:
        notification["presentation"] = codec.normalize_selection(notification["presentation"])
    return value


def execute(command, request, context, *, admission=None, cursor_config=None, now=None):
    db = context.ledger
    admission = admission or RenderingAdmission()
    timestamp = now or wire_time(utc_now())
    try:
        invariant(getattr(db, "_renderings_enabled", False) and not db.in_transaction, "candidate storage is required")
        if command.startswith(("notification_rendering_definition.", "notification_rendering_disclosure.")):
            return rendering_catalog.execute(command, request, context, admission=admission, cursor_config=cursor_config, now=timestamp)
        value = normalized_request(command, request)
        if command.startswith("notification_profile."):
            budget = FacetBudget()
            old_timeout = install_budget(db, budget)
            try:
                return rendering_profiles.execute(command, value, context, admission=admission, now=timestamp, budget=budget)
            finally:
                db.set_progress_handler(None, 0)
                db.execute(f"PRAGMA busy_timeout={old_timeout}")
        handlers = {
            "schedule.create": core._handle_schedule_create,
            "schedule.update": core._handle_schedule_update,
            "reminder.create": core._handle_reminder_create,
            "reminder.edit": core._handle_reminder_edit,
        }
        if command not in handlers:
            codec.fail("invalid_request", "command")
        budget = FacetBudget()
        old_timeout = install_budget(db, budget)
        try:
            with db.atomic_command():
                permissions = admission.permissions(db, timestamp, budget)
                if permissions:
                    if value["actor_subject_id"] != permissions.subject:
                        codec.fail("permission_denied", "actor_subject_id")
                    if "item_id" in value:
                        permissions.item(value["item_id"], edit=True)
                authoring = RenderingAuthoring(db, command, value, permissions, budget)
                result = handlers[command](value, replace(context, rendering_authoring=authoring))
                if not result["ok"]:
                    raise rendering_catalog._Preview(result)
                if authoring.before is not None:
                    authoring.verify_successor(value["item_id"], int(result["current_version"]))
                if context.dry_run:
                    finalize(db)
                    raise rendering_catalog._Preview(result)
            return result
        finally:
            db.set_progress_handler(None, 0)
            db.execute(f"PRAGMA busy_timeout={old_timeout}")
    except rendering_catalog._Preview as preview:
        return preview.response | ({"dry_run": True} if context.dry_run else {})
    except (SpineValidationError, WebError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, SpineValidationError):
            code, _, field = exc.code.partition(":")
        elif isinstance(exc, WebError):
            code, field = ("environment_failure", "capacity") if exc.code == "capacity_exceeded" else ("permission_denied", "resource")
        elif isinstance(exc, sqlite3.IntegrityError):
            code, field = "semantic_conflict", "request"
        elif isinstance(exc, sqlite3.Error):
            code, field = "environment_failure", "capacity"
        else:
            code, field = "invalid_request", "request"
        return {
            "ok": False,
            "command": command,
            "error": {"code": code, "field": field or "request", "message": "rendering request could not complete"},
            **({"dry_run": True} if context.dry_run else {}),
        }
