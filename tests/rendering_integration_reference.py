"""Pure, test-only fixture construction. No DB, service, key provisioning or file writes."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path

from spine.core.notification_profiles import normalize_profile_revision
from spine.core.notification_rendering import render_notification
from spine.ledger.notification_renderings import notification_rendering_view

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "tests/fixtures/notification_rendering_integration/"
CANON = "spine.canonical-json.v1"


def load(path):
    return json.loads((ROOT / path).read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def preimage(domain, **facts):
    return {"derivation_version": domain, "canonical_json_version": CANON, **facts}


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def normalized_v2_revision(value):
    """Reference ordering/default/hash calculation only; not a live authoring validator."""
    revision = copy.deepcopy(value)
    revision["compatible_item_types"].sort()
    revision["templates"].sort(key=lambda template: template["template_key"])
    for template in revision["templates"]:
        template.setdefault("rendering", {"kind": "ordinary"})
        template["normalized_template_hash"] = digest(preimage("spine.notification-profile-template-hash.v2", template=template))
    return revision


def reference_suffix(base_body, candidates):
    """Pure budget check over already normalized/authorized candidate evidence.

    Does not resolve facets, grants or locations. Overflowing values and sources
    are removed before returning final evidence; other omissions are preserved.
    """
    suffix = "".join(f" · {s['label']}: {s['value']}" for s in candidates if s["outcome"] == "included")
    overflow = len(base_body + suffix) > 1024
    selections = []
    for candidate in candidates:
        evidence = {k: v for k, v in candidate.items() if k != "label"}
        if overflow and candidate["outcome"] == "included":
            evidence = {"selection_key": candidate["selection_key"], "outcome": "suffix_overflow"}
        selections.append(evidence)
    return {
        "candidate_suffix": suffix,
        "body_text": base_body if overflow else base_body + suffix,
        "outcome": "suffix_overflow" if overflow else "details_included" if suffix else "ordinary_only",
        "selections": selections,
    }


def build():
    files, cases, hashes, cursors = {}, [], [], []

    def emit(name, value, schema, definition=None, valid=True):
        path = PREFIX + name + ".json"
        files[path] = copy.deepcopy(value)
        cases.append(
            {
                "fixture_id": name,
                "fixture": path,
                "schema": "contracts/schemas/" + schema + ".schema.json",
                "schema_ref": "#/$defs/" + definition if definition else "#",
                "valid": valid,
                "kind": "wire",
            }
        )

    def hashed(name, value):
        result = digest(value)
        hashes.append({"case_id": name, "preimage": value, "canonical_json": canonical(value), "sha256": result})
        return result

    logical = "tests/fixtures/notification_rendering_definitions/contracts/"
    details_source = load(logical + "evidence_flight_details.json")
    definition = details_source["definition"]
    selection = {
        "kind": "definition",
        "definition": definition,
        "authorization": {"resolution": "exact", "disclosure_authorization_id": details_source["disclosure_authorization_id"]},
        "effective_selection_keys": ["departure", "flight", "terminal"],
    }
    presentation = {
        "kind": "definition",
        "definition": definition,
        "disclosure_authorization_id": details_source["disclosure_authorization_id"],
        "disclosure_scope_hash": details_source["disclosure_scope_hash"],
        "effective_selection_keys": selection["effective_selection_keys"],
        "origin": {"kind": "direct"},
    }
    ordinary = {"kind": "ordinary"}
    presentation_hash = hashed(
        "presentation_definition", preimage("spine.notification-policy-presentation-hash.v1", presentation=presentation)
    )
    ordinary_hash = hashed("presentation_ordinary", preimage("spine.notification-policy-presentation-hash.v1", presentation=ordinary))
    empty = {**presentation, "effective_selection_keys": []}
    hashed("presentation_empty_subset", preimage("spine.notification-policy-presentation-hash.v1", presentation=empty))
    create = load("tests/fixtures/notification_profiles/contracts/request_notification_profile_create.json")
    create["contract_version"] = "spine.notification-profiles.v2"
    create["revision"]["templates"][0]["rendering"] = {"kind": "definition", "definition": definition}
    emit("request_profile_create", create, "notification-profile-commands-v2", "profileCreate")
    omitted = copy.deepcopy(create)
    del omitted["revision"]["templates"][0]["rendering"]
    emit("request_profile_ordinary_omitted", omitted, "notification-profile-commands-v2", "profileCreate")
    ordinary_revision = normalized_v2_revision(omitted["revision"])
    emit("normalized_ordinary_revision", ordinary_revision, "notification-profile-types-v2", "normalizedRevision")
    hashed("profile_ordinary_revision", preimage("spine.notification-profile-revision-hash.v2", revision=ordinary_revision))
    revision = copy.deepcopy(create["revision"])
    template = revision["templates"][0]
    template["normalized_template_hash"] = hashed(
        "profile_template", preimage("spine.notification-profile-template-hash.v2", template=copy.deepcopy(template))
    )
    revision_hash = hashed("profile_revision", preimage("spine.notification-profile-revision-hash.v2", revision=revision))
    identity = {k: create[k] for k in ("contract_version", "command_id", "actor_subject_id", "action_timestamp_utc")}
    emit(
        "request_profile_revise",
        {
            **identity,
            "notification_profile_id": "profile-example",
            "expected_current_revision_id": "revision-old",
            "revision": create["revision"],
        },
        "notification-profile-commands-v2",
        "profileRevise",
    )
    emit(
        "request_profile_show",
        {"contract_version": create["contract_version"], "notification_profile_id": "profile-example"},
        "notification-profile-commands-v2",
        "profileShow",
    )
    emit(
        "request_profile_list",
        {"contract_version": create["contract_version"], "owner": create["owner"], "limit": "10"},
        "notification-profile-commands-v2",
        "profileList",
    )
    emit(
        "request_profile_list_101",
        {"contract_version": create["contract_version"], "owner": create["owner"], "limit": "101"},
        "notification-profile-commands-v2",
        "profileList",
    )
    profile = {
        "notification_profile_id": "profile-example",
        "owner": create["owner"],
        "profile_key": create["profile_key"],
        "display_name": create["display_name"],
        "description": create["description"],
        "status": "active",
        "current_revision_id": "revision-example",
        "revision": {
            "notification_profile_revision_id": "revision-example",
            "revision_number": "2",
            "revision_contract": create["contract_version"],
            "normalized_revision_hash": revision_hash,
            "content": revision,
        },
    }
    emit(
        "response_profile_show",
        {
            "ok": True,
            "command": "notification_profile.show",
            "response_contract": create["contract_version"],
            "notification_profile": profile,
        },
        "notification-profile-responses-v2",
        "show",
    )
    historical = copy.deepcopy(profile)
    old = normalize_profile_revision(omitted["revision"])
    historical["revision"] = {
        "notification_profile_revision_id": "revision-old",
        "revision_number": "1",
        "revision_contract": "spine.notification-profiles.v1",
        "normalized_revision_hash": old.normalized_revision_hash,
        "content": {"compatible_item_types": list(old.compatible_item_types), "templates": list(old.templates)},
    }
    emit(
        "response_profile_historical_v1",
        {
            "ok": True,
            "command": "notification_profile.show",
            "response_contract": create["contract_version"],
            "notification_profile": historical,
        },
        "notification-profile-responses-v2",
        "show",
    )
    emit(
        "response_profile_list",
        {
            "ok": True,
            "command": "notification_profile.list",
            "response_contract": create["contract_version"],
            "entries": [profile],
            "count": "1",
            "catalog_snapshot_hash": digest(profile),
            "has_more": False,
            "next_cursor": None,
        },
        "notification-profile-responses-v2",
        "list",
    )
    for command, effect in (("create", "notification_profile_created"), ("revise", "notification_profile_revised")):
        response = {
            "ok": True,
            "command": "notification_profile." + command,
            "response_contract": create["contract_version"],
            "effect": effect,
            "notification_profile_id": "profile-example",
            "notification_profile_revision_id": "revision-example",
            "revision_number": "2",
            "status": "active",
            "normalized_revision_hash": revision_hash,
            "receipt": {
                "command_receipt_id": "receipt-example",
                "command_id": "command-example",
                "effect": effect,
                "semantic_facts_hash": digest(create),
                "created_at_utc": create["action_timestamp_utc"],
            },
        }
        if command == "create":
            response.update(profile_key=create["profile_key"], revision_number="1")
        emit("response_profile_" + command, response, "notification-profile-responses-v2", command)
    schedule = load("tests/fixtures/notification_profiles/contracts/request_schedule_create_profile_default.json")
    schedule["contract_version"] = "spine.schedule-create.v3"
    schedule["notification_plan"]["rendering_applications"] = [
        {"source_kind": "profile_template", "source_key": "day_before", "selection": ordinary}
    ]
    emit("request_schedule_create_ordinary", schedule, "schedule-create-request-v3")
    update = {
        "contract_version": "spine.schedule-update.v3",
        "command_id": "presentation-edit",
        "actor_subject_id": "subject_agent",
        "item_id": "item-example",
        "target_version": "2",
        "updated_at_utc": create["action_timestamp_utc"],
        "patch": {"policy_presentations": [{"notification_policy_id": "policy-old", "selection": selection}]},
        "materialization": {"mode": "none"},
    }
    emit("request_presentation_edit", update, "schedule-update-request-v3")
    unique = copy.deepcopy(update)
    unique["patch"]["policy_presentations"][0]["selection"]["authorization"] = {"resolution": "unique_match"}
    emit("request_presentation_unique_match", unique, "schedule-update-request-v3")
    clear = copy.deepcopy(update)
    clear["patch"]["policy_presentations"][0]["selection"] = ordinary
    emit("request_presentation_clear", clear, "schedule-update-request-v3")
    emit(
        "request_show_v2",
        {
            "contract_version": "spine.schedule-show.v2",
            "item_id": "item-example",
            "include": ["policies", "attempts", "notification_profile"],
        },
        "schedule-show-request-v2",
    )
    authoring = {
        "authoring_contract": "spine.notification-schedule-authoring.v2",
        "target": {"anchor_role": "event_start", "application_scope": "item"},
        "schedule": template["schedule"],
        "late_handling": template["late_handling"],
        "presentation": selection,
    }
    emit("direct_authoring", authoring, "notification-authoring-v2")
    direct_create = {
        "command": "reminder.create",
        "request": {
            "command_id": "direct-create-example",
            "actor_subject_id": "subject_agent",
            "item_id": "item-example",
            "target_version": "2",
            "created_at_utc": create["action_timestamp_utc"],
            "recipient_kind": "subject",
            "recipient_subject_id": "subject_owner",
            "channel": "whatsapp",
            "delivery_target_id": "delivery-target-example",
            "notification": authoring,
        },
    }
    emit("request_direct_create", direct_create, "notification-command-v2")
    direct_edit = {
        "command": "reminder.edit",
        "request": {
            "command_id": "direct-edit-example",
            "actor_subject_id": "subject_agent",
            "item_id": "item-example",
            "target_version": "2",
            "updated_at_utc": create["action_timestamp_utc"],
            "notification_intent_id": "intent-example",
            "notification_policy_id": "policy-old",
            "patch": {"notification": {"authoring_contract": "spine.notification-schedule-authoring.v2", "presentation": ordinary}},
        },
    }
    emit("request_direct_edit_clear", direct_edit, "notification-command-v2")
    invalid_direct = copy.deepcopy(direct_edit)
    invalid_direct["request"]["patch"]["schedule"] = template["schedule"]
    emit("invalid_direct_edit_mixed_timing", invalid_direct, "notification-command-v2", valid=False)
    emit(
        "failure_unadopted_create",
        {
            "ok": False,
            "command": "schedule.create",
            "dry_run": True,
            "error": {
                "code": "rendering_disclosure_unavailable",
                "field": "rendering_applications",
                "message": "Selected details require an adopted item owner.",
            },
        },
        "notification-rendering-integration-failure",
    )
    emit(
        "failure_schedule_create_permission_denied",
        {"ok": False, "command": "schedule.create", "error": {"code": "permission_denied", "message": "Item creation denied."}},
        "schedule-create-response-v3",
    )
    mapping = {
        "policy_origin": "custom_addition",
        "source_key": "custom",
        "notification_intent_id": "intent-example",
        "notification_policy_id": "policy-example",
        "presentation": {**presentation, "origin": {"kind": "custom_addition"}},
    }
    mapping["presentation_hash"] = hashed(
        "application_policy_presentation", preimage("spine.notification-policy-presentation-hash.v1", presentation=mapping["presentation"])
    )
    set_hash = hashed(
        "presentation_set",
        preimage(
            "spine.notification-presentation-set-hash.v1",
            entries=[{k: mapping[k] for k in ("notification_policy_id", "presentation_hash")}],
        ),
    )
    application = {
        "application_contract": "spine.notification-profile-application.v2",
        "notification_profile_application_id": "application-example",
        "notification_profile_id": "profile-example",
        "notification_profile_revision_id": "revision-example",
        "selection_mode": "explicit",
        "notification_profile_binding_id": None,
        "scope_chain": [],
        "normalized_profile_revision_hash": revision_hash,
        "suppress_template_keys": ["day_before"],
        "replacements": [],
        "custom_additions": [{"policy_key": "custom", "schedule": template["schedule"], "late_handling": template["late_handling"]}],
        "normalized_effective_policy_set_hash": digest({"example": "unchanged-ordinary-plan"}),
        "effective_presentation_set_hash": set_hash,
        "policies": [mapping],
    }
    emit("application_v2", application, "notification-profile-application-v2")
    readback = {
        "readback_contract": "spine.notification-profile-readback.v2",
        "archetype_assignment": None,
        "application": application,
        "pinned_notification_profile_revision_id": "revision-example",
        "current_notification_profile_revision_id": "revision-example",
        "upgrade_available": False,
        "effective_policy_diverged": False,
    }
    emit("readback_v2", readback, "notification-profile-readback-v2")
    # Default resolution through two owners, with suppression, replacement and addition.
    overlay_revision = copy.deepcopy(create["revision"])
    suppressed_template = {**copy.deepcopy(overlay_revision["templates"][0]), "template_key": "suppressed"}
    suppressed_template["schedule"]["at"]["offset_seconds"] = "-172800"
    overlay_revision["templates"].append(suppressed_template)
    overlay_revision = normalized_v2_revision(overlay_revision)
    overlay_hash = hashed("overlay_profile_revision", preimage("spine.notification-profile-revision-hash.v2", revision=overlay_revision))
    overlay_profile = copy.deepcopy(profile)
    overlay_profile["revision"].update(content=overlay_revision, normalized_revision_hash=overlay_hash)
    emit(
        "response_profile_overlay_revision",
        {
            "ok": True,
            "command": "notification_profile.show",
            "response_contract": create["contract_version"],
            "notification_profile": overlay_profile,
        },
        "notification-profile-responses-v2",
        "show",
    )
    replacement = {
        "template_key": "day_before",
        "schedule": copy.deepcopy(template["schedule"]),
        "late_handling": template["late_handling"],
    }
    replacement["schedule"]["at"]["offset_seconds"] = "-3600"
    replacement_mapping = {
        "policy_origin": "profile_replacement",
        "source_key": "day_before",
        "notification_intent_id": "intent-replacement",
        "notification_policy_id": "policy-replacement",
        "presentation": ordinary,
        "presentation_hash": ordinary_hash,
    }
    overlay_application = copy.deepcopy(application)
    overlay_application.update(
        selection_mode="archetype_default",
        notification_profile_binding_id="binding-example",
        scope_chain=[create["owner"], {"owner_kind": "system"}],
        normalized_profile_revision_hash=overlay_hash,
        suppress_template_keys=["suppressed"],
        replacements=[replacement],
        policies=[mapping, replacement_mapping],
        normalized_effective_policy_set_hash=digest({"example": "illustrative-overlay-policy-set"}),
    )
    overlay_application["effective_presentation_set_hash"] = hashed(
        "overlay_presentation_set",
        preimage(
            "spine.notification-presentation-set-hash.v1",
            entries=[{k: p[k] for k in ("notification_policy_id", "presentation_hash")} for p in overlay_application["policies"]],
        ),
    )
    emit("application_archetype_default_overlays", overlay_application, "notification-profile-application-v2")
    overlay_assignment = {
        "item_archetype_assignment_id": "assignment-example",
        "item_id": "item-example",
        "item_version": "1",
        "item_archetype_id": "item_archetype_example",
        "item_archetype_revision_id": "archetype-revision-example",
        "selection_source": "agent_selected",
        "source_ref": None,
        "created_by_subject_id": create["actor_subject_id"],
        "created_by_command_id": schedule["command_id"],
        "created_at_utc": schedule["created_at_utc"],
    }
    emit(
        "readback_archetype_default_overlays",
        {**readback, "application": overlay_application, "archetype_assignment": overlay_assignment},
        "notification-profile-readback-v2",
    )
    for field in ("application", "pinned_notification_profile_revision_id", "current_notification_profile_revision_id"):
        readback[field] = None
    emit("readback_no_profile", readback, "notification-profile-readback-v2")
    change = {
        "source_policy_id": "policy-old",
        "policy_id": "policy-example",
        "before_hash": ordinary_hash,
        "after_hash": presentation_hash,
    }
    emit("presentation_change", change, "notification-rendering-integration-types", "presentationChange")
    create_response = load("tests/fixtures/schedule_create/contracts/response_event_repeat_window_materialized.json")
    create_response["response_contract"] = "spine.schedule-create-response.v3"
    create_response["receipt"]["receipt_contract"] = "spine.schedule-create-receipt.v3"
    create_response["notification_profile"] = None
    for policy in create_response["policies"]:
        policy.update(presentation=ordinary, presentation_hash=ordinary_hash)
    emit("response_schedule_create", create_response, "schedule-create-response-v3")
    update_response = load("tests/fixtures/schedule_operations/contracts/response_update_title_with_work_classifications.json")
    update_response.update(response_contract="spine.schedule-update-response.v3", presentation_changes=[], notification_profile=None)
    update_response["receipt"]["receipt_contract"] = "spine.schedule-update-receipt.v3"
    for policy in update_response["policies"]:
        policy.update(presentation=ordinary, presentation_hash=ordinary_hash)
    emit("response_schedule_update_copy_forward", update_response, "schedule-update-response-v3")
    presentation_response = copy.deepcopy(update_response)
    presentation_response.update(effect="schedule_updated", work_changed=False, changed_dimensions=["policy_presentations"])
    presentation_response["receipt"]["effect"] = "schedule_updated"
    presentation_response["policies"][0].update(presentation=presentation, presentation_hash=presentation_hash)
    presentation_response["presentation_changes"] = [
        {
            **change,
            "source_policy_id": "notification_policy_countdown_v4",
            "policy_id": presentation_response["policies"][0]["notification_policy_id"],
        }
    ]
    presentation_response["work_reconciliation"]["cancelled_work_instance_ids"] = []
    presentation_response["work_reconciliation"]["protected_stale_work_instance_ids"] = []
    emit("response_presentation_edit", presentation_response, "schedule-update-response-v3")
    show = {
        "ok": True,
        "command": "schedule.show",
        "response_contract": "spine.schedule-show.v2",
        "item": {
            "item_id": "item-example",
            "item_type": "event",
            "current_version": "1",
            "status": "active",
            "created_at_utc": create["action_timestamp_utc"],
            "updated_at_utc": create["action_timestamp_utc"],
            "current_common": {"title": "Unscheduled event"},
        },
        "scheduled_times": [],
        "delivery_targets": [],
        "included": ["notification_profile"],
        "notification_profile": readback,
        "lifecycle": {
            "authored": {"state": "committed", "item_version": "1", "policy_count": "0"},
            "opportunities": {"state": "not_requested", "count": "0"},
            "work": {
                "state": "none",
                "count": "0",
                "status_counts": {k: "0" for k in ("eligible", "in_progress", "succeeded", "failed", "cancelled")},
            },
            "delivery": {
                "attempt_state": "not_attempted",
                "outcome_state": "none",
                "attempt_count": "0",
                "status_counts": {k: "0" for k in ("started", "succeeded", "failed", "rejected")},
            },
        },
    }
    emit("response_schedule_show", show, "schedule-show-response-v2")
    source = load("tests/fixtures/notification_rendering/vectors/event_tomorrow_physical.json")["source_input"]
    source.update(
        title="Flight to Paris",
        target_scheduled_fact="2026-08-23T20:00:00Z",
        target_at_utc="2026-08-23T20:00:00Z",
        primary_location=None,
        display_time_basis="instant_utc",
        display_timezone="UTC",
    )
    source["timezone_database_version"] = None
    rendered = render_notification(source)
    row = rendered.as_persistence()
    row.update(source_input=rendered.source_input, phrase_facts=rendered.phrase_facts, rendered_item_version="3")
    base = notification_rendering_view(row)
    emit("ordinary_v1", base, "notification-rendering")
    ordinary_base = base
    overflow_source = {**source, "title": "Flight " + "x" * 870}
    overflow_rendered = render_notification(overflow_source)
    overflow_row = overflow_rendered.as_persistence()
    overflow_row.update(source_input=overflow_rendered.source_input, phrase_facts=overflow_rendered.phrase_facts, rendered_item_version="3")
    overflow_base = notification_rendering_view(overflow_row)
    emit("ordinary_overflow_base_v1", overflow_base, "notification-rendering")
    overflow_candidates = [
        {**copy.deepcopy(s), "label": label, "value": letter * 120}
        for s, label, letter in zip(details_source["selections"], ("Flight", "Terminal", "Departure"), ("A", "B", "C"), strict=True)
    ]
    overflow_result = reference_suffix(overflow_base["body_text"], overflow_candidates)
    overflow_reference = {
        "base_body": overflow_base["body_text"],
        "candidate_selections": overflow_candidates,
        "candidate_suffix": overflow_result["candidate_suffix"],
        "candidate_scalars": len(overflow_base["body_text"] + overflow_result["candidate_suffix"]),
        "outcome": overflow_result["outcome"],
    }
    for kind in ("included", "revoked", "empty_subset", "overflow"):
        base = overflow_base if kind == "overflow" else ordinary_base
        details = copy.deepcopy(details_source)
        details.update(
            attempt_id=base["attempt_id"],
            base_rendering_input_hash=base["rendering_input_hash"],
            base_rendered_content_hash=base["rendered_content_hash"],
        )
        if kind == "overflow":
            details.update({k: overflow_result[k] for k in ("body_text", "outcome", "selections")})
        elif kind != "included":
            details["body_text"] = base["body_text"]
            details["outcome"] = "ordinary_only"
            reason = {"revoked": "disclosure_unavailable", "empty_subset": "not_selected"}[kind]
            details["selections"] = [{"selection_key": s["selection_key"], "outcome": reason} for s in details["selections"]]
            if kind == "revoked":
                details["authorization_state"] = "revoked"
            if kind == "empty_subset":
                details["effective_selection_keys"] = []
        input_facts = {k: v for k, v in details.items() if k not in ("input_hash", "content_hash", "body_text")}
        details["input_hash"] = hashed(kind + "_details_input", {**input_facts, "canonical_json_version": CANON})
        details["content_hash"] = hashed(
            kind + "_details_content",
            {"contract_version": details["contract_version"], "canonical_json_version": CANON, "body_text": details["body_text"]},
        )
        input_hash = hashed(
            kind + "_rendering_input",
            preimage(
                "spine.notification-rendering-input-hash.v2",
                base_rendering_input_hash=base["rendering_input_hash"],
                details_input_hash=details["input_hash"],
            ),
        )
        content_hash = hashed(
            kind + "_rendering_content",
            preimage("spine.notification-rendering-content-hash.v2", rendering_input_hash=input_hash, body_text=details["body_text"]),
        )
        identity_hash = hashed(
            kind + "_rendering_identity",
            preimage(
                "spine.notification-rendering-id.v2",
                attempt_id=base["attempt_id"],
                rendering_input_hash=input_hash,
                rendered_content_hash=content_hash,
            ),
        )
        envelope = {
            "rendering_contract": "spine.notification-rendering.v2",
            "notification_rendering_id": "notification_rendering_" + identity_hash,
            "base_rendering": base,
            "details": details,
            "rendering_input_hash": input_hash,
            "rendered_content_hash": content_hash,
            "body_text": details["body_text"],
        }
        emit("rendering_" + kind, envelope, "notification-rendering-v2")
    base = ordinary_base
    attempt = {
        "attempt_id": base["attempt_id"],
        "work_instance_id": base["work_instance_id"],
        "item_id": base["item_id"],
        "adapter_name": "openclaw",
        "idempotency_key": "unchanged-provider-key",
        "attempt_status": "started",
        "request_payload_hash": "a" * 64,
        "request_hash": "b" * 64,
        "attempted_at_utc": base["attempted_at_utc"],
    }
    for version, rendering in (("v1", base), ("v2", files[PREFIX + "rendering_included.json"])):
        emit("readback_attempt_" + version, {**attempt, "notification_rendering": rendering}, "schedule-show-response-v2", "attempt")
    config = {
        "contract_version": "spine.notification-rendering-cursor-config.v1",
        "key_id": "public-test-key",
        "key_generation": "generation-test-1",
        "ledger_instance_id": "ledger-test",
        "secret_hex": bytes(range(32)).hex(),
    }
    emit("cursor_config_test_only", config, "notification-rendering-cursor-config")
    for mode in ("trusted_local", "permission_enforced"):
        query = {"owner": create["owner"], "status": "active", "limit": "10"}
        context = {
            "mode": mode,
            "account_id": None if mode == "trusted_local" else "account-test",
            "subject_id": None if mode == "trusted_local" else "subject-test",
            "audience": "trusted_local_full_scope" if mode == "trusted_local" else "web-test",
            "ledger_instance_id": config["ledger_instance_id"],
        }
        access = {
            "access_epoch": None if mode == "trusted_local" else "3",
            "valid_until_utc": None if mode == "trusted_local" else "2026-10-04T12:05:00Z",
        }
        payload = {
            "contract_version": "spine.notification-rendering-cursor.v1",
            "ledger_instance_id": config["ledger_instance_id"],
            "key_generation": config["key_generation"],
            "command": "notification_rendering_definition.list",
            "catalog_generation": "7",
            "last_id": "definition-test",
            "issued_at_utc": "2026-10-04T12:00:00Z",
            "expires_at_utc": access["valid_until_utc"] or "2026-10-04T12:15:00Z",
            "access_epoch": access["access_epoch"],
            "access_valid_until_utc": access["valid_until_utc"],
        }
        for name, value in (("query", query), ("context", context), ("access", access)):
            payload[name + "_hash"] = hashed(mode + "_cursor_" + name, preimage("spine.rendering-cursor-" + name + ".v1", **{name: value}))
        raw = canonical(payload).encode()
        signed = b"spine.notification-rendering-cursor.v1\0" + config["key_id"].encode() + b"\0" + raw
        mac = hmac.new(bytes.fromhex(config["secret_hex"]), signed, hashlib.sha256).digest()
        token = "nrc1." + config["key_id"] + "." + b64(raw) + "." + b64(mac)
        cursors.append(
            {
                "case_id": mode,
                "config": config,
                "query": query,
                "context": context,
                "access": access,
                "payload": payload,
                "canonical_payload": raw.decode(),
                "signed_bytes_hex": signed.hex(),
                "mac_hex": mac.hex(),
                "token": token,
            }
        )
        emit("cursor_" + mode, payload, "notification-rendering-cursor")
    # Structural invalids are distinct from stateful rejection scenarios.
    bad = copy.deepcopy(update)
    bad["patch"]["item"] = {"title": "also change title"}
    emit("invalid_mixed_presentation_patch", bad, "schedule-update-request-v3", valid=False)
    bad = copy.deepcopy(create)
    bad["revision"]["templates"][0]["rendering"]["disclosure_authorization_id"] = "client-grant"
    emit("invalid_template_grant", bad, "notification-profile-commands-v2", "profileCreate", False)
    bad = copy.deepcopy(update)
    bad["patch"]["policy_presentations"][0]["selection"]["origin"] = {"kind": "direct"}
    emit("invalid_client_origin", bad, "schedule-update-request-v3", valid=False)
    bad = copy.deepcopy(config)
    bad["secret_hex"] += "\n"
    emit("invalid_cursor_secret_newline", bad, "notification-rendering-cursor-config", valid=False)
    files[PREFIX + "computed_vectors.json"] = {
        "contract_version": "spine.notification-rendering-integration-vectors.v1",
        "hashes": hashes,
        "cursors": cursors,
        "overflow_reference": overflow_reference,
        "runtime_verified": False,
    }
    matrix = load("contracts/notification-rendering-integration.v1.json")
    # Copy release metadata from its authority; generating reference vectors
    # never executes or certifies the runtime (computed_vectors stays false).
    verified = matrix["verification"]["runtime_verified"]
    files[PREFIX + "stateful_obligations.json"] = {
        "runtime_verified": verified,
        "families": [
            {"family": k, "oracle": v, "status": "passed_local" if verified else "pending_runtime"}
            for k, v in matrix["verification"]["required_families"].items()
        ],
    }
    files["contracts/notification-rendering-integration-fixture-manifest.json"] = {
        "contract_version": "spine.notification-rendering-integration-fixtures.v1",
        "status": matrix["status"],
        "registry": "contracts/notification-rendering-integration-contract-registry.v1.json",
        "fixtures": cases,
        "computed_vectors": PREFIX + "computed_vectors.json",
        "stateful_obligations": PREFIX + "stateful_obligations.json",
        "runtime_verified": verified,
    }
    return files


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
