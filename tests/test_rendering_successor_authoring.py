"""Real authoring transactions for source-only successor contracts."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine.commands import handle, rendering_candidate
from spine.core import rendering_definitions as codec
from spine.ledger.rendering_definitions import load_presentation, verify_deep
from spine.web.provisioning import apply, plan
from tests.facet_storage_support import NOW
from tests.test_rendering_authoring_foundation import RenderingFoundationTests

ROOT = Path(__file__).parents[1]


class RenderingSuccessorTests(RenderingFoundationTests):
    def test_direct_v2_selector_noop_selection_and_retired_pin_retention(self):
        root = self.create()["record"]
        event = self.candidate(
            "schedule.create",
            self.fixture.event_request("direct-target", materialize=False) | {"contract_version": "spine.schedule-create.v3"},
        )
        self.adopt(event["item_id"])
        grant = self.disclosure(root)
        request = {
            "command_id": "direct-v2",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "1",
            "created_at_utc": NOW,
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "whatsapp",
            "delivery_target_id": "whatsapp-owner",
            "notification": {
                "authoring_contract": "spine.notification-schedule-authoring.v2",
                "target": {"anchor_role": "event_start", "application_scope": "item"},
                "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
                "late_handling": {"kind": "skip"},
                "presentation": self.selection(grant),
            },
        }
        created = self.candidate("reminder.create", request)
        selected = created["presentation"]
        self.assertEqual(selected["origin"], {"kind": "direct"})
        edit = {
            "command_id": "selector-only",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "2",
            "notification_policy_id": created["notification_policy_id"],
            "notification_intent_id": created["notification_intent_id"],
            "updated_at_utc": NOW,
            "patch": {"notification": {"authoring_contract": "spine.notification-schedule-authoring.v2"}},
        }
        noop = self.candidate("reminder.edit", edit)
        self.assertEqual(noop["presentation"], selected)
        self.assertEqual(
            self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0], 2
        )
        self.call(
            "notification_rendering_definition.retire",
            notification_rendering_definition_id=root["notification_rendering_definition_id"],
            expected_current_revision_id=root["current_revision_id"],
            reason_code="replacement",
        )
        edit["command_id"] = "edit-retired-pin"
        edit["patch"]["notification"]["late_handling"] = {"kind": "deliver_within", "grace_seconds": "60"}
        changed = self.candidate("reminder.edit", edit)
        self.assertEqual(changed["presentation"], selected)
        verify_deep(self.db)

    def candidate(self, command, request, *, context=None):
        result = rendering_candidate.execute(command, request, context or self.context, now=NOW)
        self.assertTrue(result["ok"], result)
        if command.startswith("schedule."):
            filename = "schedule-create-response-v3" if command.endswith(".create") else "schedule-update-response-v3"
            uri = f"https://cortext.local/spine/contracts/schemas/{filename}.schema.json"
            Draft202012Validator({"$ref": uri}, registry=self.registry).validate(result)
        elif command.startswith("notification_profile."):
            filename = "notification-profile-responses-v2"
            fragment = command.split(".")[1]
            uri = f"https://cortext.local/spine/contracts/schemas/{filename}.schema.json#/$defs/{fragment}"
            Draft202012Validator({"$ref": uri}, registry=self.registry).validate(result)
        return result

    def profile(self, *, pinned=True, key="flight_standard"):
        root = self.create()["record"] if pinned else None
        request = json.loads((ROOT / "tests/fixtures/notification_rendering_integration/request_profile_create.json").read_text())
        request.update(command_id="profile-" + key, actor_subject_id="owner", owner=self.scope, action_timestamp_utc=NOW, profile_key=key)
        for template in request["revision"]["templates"]:
            template["rendering"] = (
                {
                    "kind": "definition",
                    "definition": {
                        k: root[k] for k in ("notification_rendering_definition_id", "notification_rendering_definition_revision_id")
                    },
                }
                if pinned
                else {"kind": "ordinary"}
            )
        return self.candidate("notification_profile.create", request), request, root

    def adopt(self, item):
        state = self.db.execute("SELECT access_epoch FROM ledger_access_state WHERE singleton_id=1").fetchone()
        epoch = str(state[0]) if state else "0"
        proposed = plan(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "ledger_id": "test-ledger",
                "expected_access_epoch": epoch,
                "item_adoptions": [
                    {
                        "operation": "create",
                        "item_id": item,
                        "owner_scope": self.scope,
                        "expected_item_version": str(
                            self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (item,)).fetchone()[0]
                        ),
                    }
                ],
            },
        )
        self.assertTrue(proposed["can_apply"], proposed)
        return apply(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "command_id": "adopt-" + item,
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "expected_access_epoch": epoch,
                "plan": proposed,
            },
        )

    def disclosure(self, root, *, profile_id=None, command_id=None):
        scope = {
            "item_owner": self.scope,
            "definition": {k: root[k] for k in ("notification_rendering_definition_id", "notification_rendering_definition_revision_id")},
            "approved_selection_keys": ["flight"],
            "use_scope": {"kind": "profile", "notification_profile_id": profile_id} if profile_id else {"kind": "direct_policy"},
            "destination": {
                "recipient": {"kind": "subject", "subject_id": "owner"},
                "delivery_target_id": "whatsapp-owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "destination_source": "delivery_target",
                "target_ref": "owner@example",
            },
            "permitted_location_ids": [],
        }
        request = self.request("notification_rendering_disclosure.provision", scope=scope)
        if command_id:
            request["command_id"] = command_id
        return self.call("notification_rendering_disclosure.provision", request)["record"]

    def selection(self, grant, *, unique=False):
        return {
            "kind": "definition",
            "definition": grant["scope"]["definition"],
            "effective_selection_keys": ["flight"],
            "authorization": {"resolution": "unique_match"}
            if unique
            else {"resolution": "exact", "disclosure_authorization_id": grant["disclosure_authorization_id"]},
        }

    def edit(self, event, selection, command_id="select", *, version=None):
        current = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0]
        policies = self.db.execute(
            "SELECT policy_id FROM notification_policies WHERE item_id=? AND version=? AND status='active' ORDER BY policy_id",
            (event["item_id"], current),
        ).fetchall()
        return {
            "contract_version": "spine.schedule-update.v3",
            "command_id": command_id,
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": str(version or current),
            "updated_at_utc": NOW,
            "patch": {"policy_presentations": [{"notification_policy_id": policies[0][0], "selection": selection}]},
            "materialization": {"mode": "none"},
        }

    def test_profile_v2_decoder_history_old_guard_metadata_and_replay(self):
        profile, request, _ = self.profile(pinned=False)
        replay = self.candidate("notification_profile.create", request)
        self.assertEqual(profile, replay)
        shown = self.candidate(
            "notification_profile.show",
            {"contract_version": codec.PROFILE_V2, "notification_profile_id": profile["notification_profile_id"]},
        )
        self.assertEqual(shown["notification_profile"]["revision"]["revision_contract"], codec.PROFILE_V2)
        old = {
            "contract_version": "spine.notification-profiles.v1",
            "command_id": "lossy-profile",
            "actor_subject_id": "owner",
            "action_timestamp_utc": NOW,
            "notification_profile_id": profile["notification_profile_id"],
            "expected_current_revision_id": profile["notification_profile_revision_id"],
            "revision": {
                "compatible_item_types": ["event"],
                "templates": [{k: v for k, v in t.items() if k != "rendering"} for t in request["revision"]["templates"]],
            },
        }
        denied = handle("notification_profile.revise", old, self.context)
        self.assertEqual((denied["error"]["code"], denied["error"]["field"]), ("unsupported_field", "revision"))
        stale = handle("notification_profile.revise", old | {"expected_current_revision_id": "stale"}, self.context)
        self.assertEqual(stale["error"]["code"], "stale_version")
        preview = rendering_candidate.execute(
            "notification_profile.revise",
            old | {"contract_version": codec.PROFILE_V2, "command_id": "preview-profile"},
            replace(self.context, dry_run=True),
            now=NOW,
        )
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(preview["dry_run"])
        self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id='preview-profile'").fetchone())
        verify_deep(self.db)

    def test_pinned_profile_requires_application_and_fresh_create_is_ordinary(self):
        profile, _, root = self.profile()
        request = self.fixture.event_request("profile-event", materialize=False)
        request["contract_version"] = "spine.schedule-create.v3"
        request["notification_plan"] = {
            "mode": "explicit",
            "notification_profile_id": profile["notification_profile_id"],
            "revision_resolution": "exact",
            "notification_profile_revision_id": profile["notification_profile_revision_id"],
        }
        denied = rendering_candidate.execute("schedule.create", request, self.context, now=NOW)
        self.assertEqual(denied["error"]["code"], "missing_required_field")
        request["notification_plan"]["rendering_applications"] = [
            {"source_kind": "profile_template", "source_key": "day_before", "selection": {"kind": "ordinary"}}
        ]
        event = self.candidate("schedule.create", request)
        self.assertEqual(event["policies"][0]["presentation"], {"kind": "ordinary"})
        self.assertEqual(event["notification_profile"]["application_contract"], "spine.notification-profile-application.v2")
        grant = self.disclosure(root, profile_id=profile["notification_profile_id"])
        edit = self.edit(event, self.selection(grant))
        missing_owner = rendering_candidate.execute("schedule.update", edit, self.context, now=NOW)
        self.assertEqual(missing_owner["error"]["code"], "rendering_disclosure_unavailable")
        self.adopt(event["item_id"])
        updated = self.candidate("schedule.update", edit)
        self.assertEqual(updated["policies"][0]["presentation"]["origin"]["kind"], "profile_template")
        self.assertEqual(updated["notification_profile"]["notification_profile_revision_id"], profile["notification_profile_revision_id"])
        self.assertEqual(updated["changed_dimensions"], ["policy_presentations"])
        self.assertFalse(updated["work_changed"])
        verify_deep(self.db)

    def test_presentation_only_edit_noop_dryrun_copy_forward_and_work_preservation(self):
        root = self.create()["record"]
        request = self.fixture.event_request("selected-event", materialize=True)
        request["contract_version"] = "spine.schedule-create.v3"
        event = self.candidate("schedule.create", request)
        self.adopt(event["item_id"])
        grant = self.disclosure(root)
        before = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        request = self.edit(event, self.selection(grant))
        preview = self.candidate("schedule.update", request, context=replace(self.context, dry_run=True))
        self.assertTrue(preview["dry_run"])
        self.assertEqual(
            self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0], 1
        )
        result = self.candidate("schedule.update", request)
        self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")])
        self.assertEqual(result["changed_dimensions"], ["policy_presentations"])
        self.assertEqual(len(result["presentation_changes"]), 1)
        self.assertEqual(self.candidate("schedule.update", request)["effect"], "schedule_update_replay")
        noop = self.candidate("schedule.update", self.edit(event, self.selection(grant), "equal-presentation"))
        self.assertEqual(noop["effect"], "schedule_update_noop")
        self.assertEqual(noop["presentation_changes"], [])
        copied = handle(
            "event.update",
            {
                "command_id": "copy-title",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "2",
                "updated_at_utc": NOW,
                "patch": {"title": "New title"},
            },
            self.context,
        )
        self.assertTrue(copied["ok"], copied)
        latest = self.db.execute(
            "SELECT policy_id FROM notification_policies WHERE item_id=? AND version=3", (event["item_id"],)
        ).fetchone()[0]
        self.assertEqual(load_presentation(self.db, latest), result["policies"][0]["presentation"])
        verify_deep(self.db)

    def test_unique_disclosure_resolution_ambiguous_and_failure_is_atomic(self):
        root = self.create()["record"]
        event = self.candidate(
            "schedule.create", self.fixture.event_request("ambiguous", materialize=False) | {"contract_version": "spine.schedule-create.v3"}
        )
        self.adopt(event["item_id"])
        grant = self.disclosure(root)
        self.disclosure(root)
        before = self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
        result = rendering_candidate.execute("schedule.update", self.edit(event, self.selection(grant, unique=True)), self.context, now=NOW)
        self.assertEqual(result["error"]["code"], "rendering_disclosure_ambiguous")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0], before)
        self.assertEqual(
            self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0], 1
        )

    def test_old_full_plan_cannot_lossily_replace_a_selected_presentation(self):
        root = self.create()["record"]
        event = self.candidate(
            "schedule.create",
            self.fixture.event_request("guard-target", materialize=False) | {"contract_version": "spine.schedule-create.v3"},
        )
        self.adopt(event["item_id"])
        grant = self.disclosure(root)
        self.candidate("schedule.update", self.edit(event, self.selection(grant)))
        request = {
            "contract_version": "spine.schedule-update.v2",
            "command_id": "old-lossy-plan",
            "actor_subject_id": "owner",
            "item_id": event["item_id"],
            "target_version": "2",
            "updated_at_utc": NOW,
            "patch": {
                "notification_plan": {
                    "action": "clear",
                    "custom_additions": self.fixture.event_request("unused")["notification_plan"]["custom_additions"],
                }
            },
            "materialization": {"mode": "none"},
        }
        for dry_run in (False, True):
            denied = handle("schedule.update", request, replace(self.context, dry_run=dry_run))
            self.assertEqual((denied["error"]["code"], denied["error"]["field"]), ("unsupported_field", "notification_plan"))
        self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id='old-lossy-plan'").fetchone())
        cleared = self.candidate(
            "schedule.update", request | {"contract_version": "spine.schedule-update.v3", "command_id": "explicit-clear"}
        )
        self.assertEqual(cleared["current_version"], "3")
        self.assertEqual(cleared["policies"][0]["presentation"], {"kind": "ordinary"})
        self.assertIn("reminders", cleared["changed_dimensions"])

    def test_missing_staged_presentation_rolls_back_whole_authoring_transaction(self):
        with patch("spine.ledger.rendering_definitions.stage_policy"):
            result = rendering_candidate.execute(
                "schedule.create",
                self.fixture.event_request("missing-support", materialize=False) | {"contract_version": "spine.schedule-create.v3"},
                self.context,
                now=NOW,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "environment_failure")
        self.assertIsNone(self.db.execute("SELECT 1 FROM coordination_items").fetchone())
