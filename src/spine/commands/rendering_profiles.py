"""Candidate profile v2 over the same canonical profile authoring handlers."""

from spine.commands import notification_profiles as shared
from spine.commands.facet_runtime import FacetBudget, utc_now, wire_time
from spine.commands.rendering_catalog import _Preview, row
from spine.commands.rendering_runtime import RenderingAdmission
from spine.core import rendering_definitions as codec
from spine.ledger.notification_profiles import load_profile
from spine.ledger.rendering_definitions import invariant, load_revision, root_owner
from spine.ledger.rendering_profiles import project


def validate_pins(db, request, owning_scope, budget, permissions):
    normalized = codec.normalize_profile_v2(request["revision"])
    for template in normalized.templates:
        rendering = template["rendering"]
        if rendering["kind"] == "ordinary":
            continue
        ref = rendering["definition"]
        root = row(
            db,
            "notification_rendering_definitions",
            "notification_rendering_definition_id",
            ref["notification_rendering_definition_id"],
            budget,
        )
        if permissions:
            permissions.rendering(root["notification_rendering_definition_id"], use=True)
        if root["status"] != "active":
            codec.fail("rendering_definition_retired", "revision.templates.rendering")
        definition = load_revision(db, ref["notification_rendering_definition_revision_id"])
        if (
            definition["notification_rendering_definition_id"] != root["notification_rendering_definition_id"]
            or root_owner(root) != owning_scope
            or not set(normalized.compatible_item_types) <= set(definition["revision"]["compatible_item_types"])
        ):
            codec.fail("rendering_definition_invalid", "revision.templates.rendering")
    return normalized


def execute(command, request, context, *, admission=None, now=None, budget=None):
    db = context.ledger
    invariant(getattr(db, "_renderings_enabled", False) and not db.in_transaction)
    codec.bounded(request, 32768, "request")
    if request.get("contract_version") != codec.PROFILE_V2:
        codec.fail("unsupported_contract_version", "contract_version")
    admission, budget = admission or RenderingAdmission(), budget or FacetBudget()
    now = now or wire_time(utc_now())
    if command.endswith(".create"):
        codec.exact(
            request,
            {
                "contract_version",
                "command_id",
                "actor_subject_id",
                "action_timestamp_utc",
                "owner",
                "profile_key",
                "display_name",
                "revision",
            },
            {"description"},
        )
    elif command.endswith(".revise"):
        codec.exact(
            request,
            {
                "contract_version",
                "command_id",
                "actor_subject_id",
                "action_timestamp_utc",
                "notification_profile_id",
                "expected_current_revision_id",
                "revision",
            },
        )
    with db.atomic_command(write=command in {"notification_profile.create", "notification_profile.revise"}):
        permissions = admission.permissions(db, now, budget)
        if command in {"notification_profile.create", "notification_profile.revise"}:
            replay = shared._compatible_replay(db, command, request["command_id"], request)
            if permissions and request["actor_subject_id"] != permissions.subject:
                codec.fail("permission_denied", "actor_subject_id")
            if replay:
                if permissions:
                    permissions.catalog("notification_profile", replay["result_identity_facts"]["notification_profile_id"])
                result = shared._success(command, replay)
            else:
                if command.endswith(".create"):
                    own = codec.owner(request["owner"])
                    if permissions:
                        permissions.owner_admin(own)
                else:
                    root = row(db, "notification_profiles", "notification_profile_id", request["notification_profile_id"], budget)
                    own = root_owner(root)
                    if permissions:
                        permissions.owner_admin(own)
                    if request["expected_current_revision_id"] != root["current_revision_id"]:
                        codec.fail("stale_version", "expected_current_revision_id")
                    if root["status"] != "active":
                        codec.fail("semantic_conflict", "notification_profile_id")
                validate_pins(db, request, own, budget, permissions)
                result = (shared._profile_create if command.endswith(".create") else shared._profile_revise)(
                    request, context, candidate_v2=True
                )
            if context.dry_run:
                from spine.ledger.rendering_definitions import finalize

                finalize(db)
                raise _Preview(result)
        elif command == "notification_profile.show":
            codec.exact(request, {"contract_version", "notification_profile_id"}, {"notification_profile_revision_id"})
            if permissions:
                permissions.catalog("notification_profile", request["notification_profile_id"])
            result = {
                "ok": True,
                "command": command,
                "response_contract": codec.PROFILE_V2,
                "notification_profile": project(
                    load_profile(db, request["notification_profile_id"], revision_id=request.get("notification_profile_revision_id"))
                ),
            }
        elif command == "notification_profile.list":
            # Preserve the profile family's fixed 1..500, snapshot/key cursor semantics.
            old = dict(request, contract_version="spine.notification-profiles.v1")
            if permissions and not permissions.scope(codec.owner(request["owner"])):
                codec.fail("permission_denied", "owner")
            result = shared._list_roots(old, context, kind="notification_profile")
            result["response_contract"] = codec.PROFILE_V2
            result["entries"] = [project(load_profile(db, r["notification_profile_id"])) for r in result["entries"]]
        else:
            codec.fail("invalid_request", "command")
        codec.bounded(result, 4 * 1024 * 1024, "capacity")
    return result | ({"dry_run": True} if context.dry_run else {})
