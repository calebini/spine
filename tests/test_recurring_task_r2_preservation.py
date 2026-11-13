"""R2 individual-offset and restoration admission boundaries; no external sends."""

import copy
import unittest
from unittest.mock import patch

from spine.commands import core, handle
from spine.core import rendering_definitions as rendering
from spine.core import temporal_bindings as binding_facts
from spine.ledger.common import TemporalAnchorInput, insert_temporal_anchor
from spine.ledger.items import create_next_item_version
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.recurring_tasks import verify_deep
from spine.ledger.supporting import ItemSubjectRoleInput
from spine.ledger.temporal_bindings import (
    insert_temporal_binding_revision,
    load_temporal_binding,
    retire_temporal_binding,
    target_from_source,
)
from spine.services.mutation_propagation import propagate
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages
from tests import test_recurring_task_restoration as restoration
from tests.facet_storage_support import DEFINITION


class RecurringTaskPreservationTests(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    setUpClass = classmethod(lambda cls: setattr(cls, "contracts", base.contracts()))
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    run_command = base.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    rule = pages.RecurringTaskReconcileTests.rule
    source_change = pages.RecurringTaskReconcileTests.source_change
    excluded = pages.RecurringTaskReconcileTests.excluded
    authored = restoration.RecurringTaskRestorationTests.authored
    cycle = restoration.RecurringTaskRestorationTests.cycle
    facet_call = restoration.RecurringTaskRestorationTests.facet_call

    def binding(self, selected):
        return load_temporal_binding(self.db, selected["after"]["temporal_binding_id"])

    def individual_offset(self, selected, seconds):
        # Canonical lower-owner state setup, not a new public offset-edit command.
        binding = self.binding(selected)
        prior = binding["latest_revision"]
        task = selected["after"]["task_item_id"]
        current = core._hydrated_item(self.db, task)
        version = int(current["current_version"])
        source = binding_facts.source_from_prior(prior)
        source["target_occurrence_selector"] = selected["selector"]
        target = target_from_source(source, seconds)
        anchor_id = "individual-offset-" + str(version)
        revision = binding_facts.revision_value(
            command="fixture.individual_offset", command_id=anchor_id, revision_id=anchor_id,
            binding=binding, prior=prior, revision_index=int(prior["revision_index"]) + 1,
            source=source, source_scope="selected_occurrence", offset=seconds, target=target,
            target_item_version=version + 1, target_anchor_id=anchor_id,
            resolution_kind="target_rescheduled", created_at=self.now,
        )
        with self.db.atomic_command(write=True):
            insert_temporal_anchor(self.db, anchor=TemporalAnchorInput(
                anchor_kind="local_instant", local_date=target["local_date"], local_time=target["local_time"],
                timezone=target["timezone"], timezone_database_version=target["timezone_database_version"],
            ), anchor_id=anchor_id, default_created_at_utc=self.now)
            def extension(db, _):
                insert_temporal_binding_revision(db, value=revision)
                propagate(db, binding_id=str(binding["temporal_binding_id"]))

            create_next_item_version(
                self.db, item_id=task, target_version=version, created_at_utc=self.now,
                created_by_subject_id="owner", task_detail={"due_anchor_id": anchor_id},
                supporting_command_id=anchor_id,
                insert_canonical_extension=extension,
            )

    def test_source_refresh_and_restoration_preserve_individual_offset(self):
        initial, first = self.authored(reminders=False)
        self.individual_offset(first, 7200)
        self.source_change()
        refreshed = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "refresh-offset")
        self.assertEqual(self.binding(first)["latest_revision"]["offset_seconds"], "7200")
        self.assertEqual(self.binding(first)["latest_revision"]["resolved_target_utc"], "2026-08-08T20:00:00Z")
        selected = next(v for v in refreshed["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.source_change(overrides=[{
            "target_occurrence_key": selected["occurrence_key"], "target_occurrence_selector": selected["selector"],
            "expressed_scheduled_fact": "2026-08-08T21:00:00Z", "reason_code": "move",
        }])
        moved = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "move-offset")
        selected = next(v for v in moved["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "followed")
        self.assertEqual(self.binding(selected)["latest_revision"]["offset_seconds"], "7200")
        self.assertEqual(self.binding(selected)["latest_revision"]["resolved_target_utc"], "2026-08-08T23:00:00Z")
        _, restored, _ = self.cycle(moved["result"]["rule"], selected)
        self.assertEqual(self.binding(restored)["latest_revision"]["offset_seconds"], "7200")
        self.assertEqual(self.binding(restored)["latest_revision"]["resolved_target_utc"], "2026-08-08T23:00:00Z")
        with self.db.atomic_command(write=False):
            verify_deep(self.db)

    def test_restore_rejects_binding_offset_that_does_not_match_cancellation_witness(self):
        initial, first = self.authored(reminders=False)
        self.individual_offset(first, 7200)
        self.cancel_for_restoration(initial, first)
        request = self.write("reconcile", self.rule(initial["result"]["rule"]["related_task_rule_id"]), limits={})
        before = base.dump(self.db)
        revision_value = binding_facts.revision_value

        def incorrect_offset(**kwargs):
            value = revision_value(**kwargs)
            if kwargs["prior"] is None:
                value["offset_seconds"] = "5400"
            return value

        with patch.object(binding_facts, "revision_value", side_effect=incorrect_offset):
            failed = self.run_command("reconcile", request)
        self.assertFalse(failed["ok"], failed)
        self.assertEqual(failed["error"]["code"], "environment_failure")
        self.assertIn("generation creation binding mismatch", failed["error"]["message"])
        self.assertEqual(base.dump(self.db), before)

    def test_offset_adoption_preserves_individual_exception_and_detects_conflict(self):
        initial, first = self.authored(reminders=False)
        self.individual_offset(first, 7200)
        desired = self.request()["configuration"]
        desired["generation_horizon_seconds"] = "4838400"
        desired["task_template"]["item"]["title"] = "Pickup with kit"
        updated = self.run_command("update", self.write("update", initial["result"]["rule"],
            configuration=desired, adoption_scope="upcoming_open"))
        self.assertTrue(updated["ok"], updated)
        adopted = self.reconcile(updated["result"]["rule"], "preserve-offset")
        self.assertEqual(self.binding(first)["latest_revision"]["offset_seconds"], "7200")
        desired["offset_seconds"] = "10800"
        update = self.write("update", adopted["result"]["rule"], configuration=desired, adoption_scope="upcoming_open")
        update["command_id"] = "change-offset"
        updated = self.run_command("update", update)
        self.assertTrue(updated["ok"], updated)
        before = copy.deepcopy(core._hydrated_item(self.db, first["after"]["task_item_id"]))
        blocked = self.reconcile(updated["result"]["rule"], "conflicting-offset")
        selected = next(v for v in blocked["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual((selected["outcome"], selected["reason"]), ("decision_required", "configuration_conflict"))
        self.assertEqual(core._hydrated_item(self.db, first["after"]["task_item_id"]), before)
        # Uncustomized siblings adopt the requested offset normally.
        for sibling in blocked["result"]["results"]:
            if sibling["assignment_id"] != first["assignment_id"]:
                self.assertEqual(self.binding(sibling)["latest_revision"]["offset_seconds"], "10800")

    def cancel_for_restoration(self, initial, first):
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "cancel-reference")
        self.assertTrue(cancelled["ok"], cancelled)
        self.source_change(exdates=[])

    def assert_blocked_restoration(self, initial, first, reason):
        task = first["after"]["task_item_id"]
        before = copy.deepcopy(core._hydrated_item(self.db, task))
        generations = self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0]
        tasks = self.db.execute("SELECT COUNT(*) FROM coordination_items WHERE item_type='task'").fetchone()[0]
        result = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "blocked-reference")
        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual((selected["outcome"], selected["reason"]), ("decision_required", reason))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], generations)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items WHERE item_type='task'").fetchone()[0], tasks)
        self.assertEqual(core._hydrated_item(self.db, task), before)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        return result

    def catalog_call(self, command, **fields):
        self.catalog_counter = getattr(self, "catalog_counter", 0) + 1
        response = handle(command, {
            "contract_version": rendering.DEFINITIONS if "definition." in command else rendering.DISCLOSURES,
            "command_id": f"guard-{self.catalog_counter}", "actor_subject_id": "owner",
            "action_timestamp_utc": self.now, **fields,
        }, self.context)
        self.assertTrue(response["ok"], response)
        return response["record"]

    def rendered_rule(self):
        schema = self.facet_call("facet_schema.create", owner=self.scope, schema_key="flight", definition=DEFINITION)
        definition = self.catalog_call("notification_rendering_definition.create", owner=self.scope,
            definition_key="pickup", revision={
                "display_name": "Pickup details", "description": None, "compatible_item_types": ["task"],
                "base_rendering_contract": "spine.notification-rendering.v1",
                "base_rendering_profile": "spine.notification-rendering.concise-en-ca.v1",
                "selections": [{"selection_key": "flight", "facet_key": "flight", "field_key": "flight",
                    "facet_schema_revision_id": schema["facet_schema_revision_id"], "projection": "value", "label": "Flight"}],
            })
        grant = self.catalog_call("notification_rendering_disclosure.provision", scope={
            "item_owner": self.scope,
            "definition": {k: definition[k] for k in (
                "notification_rendering_definition_id", "notification_rendering_definition_revision_id")},
            "approved_selection_keys": ["flight"],
            "use_scope": {"kind": "profile", "notification_profile_id": self.profile["notification_profile_id"]},
            "destination": {"recipient": {"kind": "subject", "subject_id": "owner"},
                "delivery_target_id": "owner-route", "channel": "test", "adapter_name": "capture",
                "destination_source": "delivery_target", "target_ref": "test://never-send"},
            "permitted_location_ids": [],
        })
        revised = handle("notification_profile.revise", {
            "contract_version": "spine.notification-profiles.v2", "command_id": "pin-rendering",
            "actor_subject_id": "owner", "action_timestamp_utc": self.now,
            "notification_profile_id": self.profile["notification_profile_id"],
            "expected_current_revision_id": self.profile["notification_profile_revision_id"],
            "revision": {"compatible_item_types": ["task"], "templates": [{
                "template_key": "ten_minutes", "schedule": {"kind": "once", "at": {
                    "kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
                "late_handling": {"kind": "skip"}, "rendering": {"kind": "definition", "definition": grant["scope"]["definition"]},
            }]},
        }, self.context)
        self.assertTrue(revised["ok"], revised)
        request = self.request()
        config = request["configuration"]
        config["notification_plan"] = {"mode": "explicit", "notification_profile_id": self.profile["notification_profile_id"],
            "revision_resolution": "current", "custom_additions": [], "rendering_applications": [{
                "source_kind": "profile_template", "source_key": "ten_minutes", "selection": {
                    "kind": "definition", "definition": grant["scope"]["definition"], "effective_selection_keys": ["flight"],
                    "authorization": {"resolution": "exact", "disclosure_authorization_id": grant["disclosure_authorization_id"]},
                }}]}
        config["delivery"] = {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}}
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        initial = self.reconcile(created["result"]["rule"])
        return initial, initial["result"]["results"][0], grant

    def test_revoked_disclosure_blocks_restoration_without_regrant_or_ordinary_substitution(self):
        initial, first, grant = self.rendered_rule()
        self.cancel_for_restoration(initial, first)
        self.catalog_call("notification_rendering_disclosure.revoke",
            disclosure_authorization_id=grant["disclosure_authorization_id"],
            expected_scope_hash=grant["scope_hash"], reason_code="withdrawn")
        self.assert_blocked_restoration(initial, first, "disclosure_unavailable")

    def test_referenced_destination_cannot_be_retargeted_under_existing_disclosure(self):
        initial, first, _ = self.rendered_rule()
        self.cancel_for_restoration(initial, first)
        before = base.dump(self.db)
        result = handle("delivery_target.upsert", {
            "command_id": "retarget-route", "actor_subject_id": "owner", "delivery_target_id": "owner-route",
            "owner_kind": "subject", "owner_subject_id": "owner", "channel": "test", "adapter_name": "capture",
            "target_ref": "test://different-audience-never-send", "updated_at_utc": self.now,
        }, self.context)
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["error"]["code"], result["error"]["field"]), ("semantic_conflict", "delivery_target_id"))
        self.assertEqual(base.dump(self.db), before)
        restored = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "restore-original-destination")
        selected = next(v for v in restored["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "restored")

    def test_valid_disclosure_is_copied_exactly_without_new_grants(self):
        from spine.ledger.rendering_definitions import load_presentation

        initial, first, grant = self.rendered_rule()
        grants = list(self.db.execute("SELECT * FROM notification_rendering_disclosures"))
        _, _, child = self.cycle(initial["result"]["rule"], first)
        self.assertEqual(list(self.db.execute("SELECT * FROM notification_rendering_disclosures")), grants)
        active = [p for p in child["notification_policies"] if p["status"] == "active"]
        self.assertEqual(len(active), 1)
        presentation = load_presentation(self.db, active[0]["notification_policy_id"])
        self.assertEqual(presentation["disclosure_authorization_id"], grant["disclosure_authorization_id"])
        self.assertEqual(presentation["definition"], grant["scope"]["definition"])
        self.assertEqual(presentation["effective_selection_keys"], ["flight"])

    def subject(self, status):
        result = handle("subject.upsert", {"command_id": "person-" + status, "actor_subject_id": "owner",
            "subject_id": "helper", "subject_kind": "person", "display_name": "Helper", "status": status,
            "updated_at_utc": self.now}, self.context)
        self.assertTrue(result["ok"], result)

    def test_inactive_individual_participant_blocks_restoration(self):
        self.subject("active")
        initial, first = self.authored(reminders=False)
        with self.db.atomic_command(write=True):
            create_next_item_version(self.db, item_id=first["after"]["task_item_id"], target_version=1,
                created_at_utc=self.now, created_by_subject_id="owner", supporting_command_id="individual-participant",
                subject_role_replacement_roles=("participant",),
                subject_roles=(ItemSubjectRoleInput(subject_id="helper", role="participant"),))
        self.cancel_for_restoration(initial, first)
        self.subject("inactive")
        self.assert_blocked_restoration(initial, first, "configuration_invalid")

    def test_inactive_nonqueryable_facet_reference_blocks_restoration(self):
        self.subject("active")
        initial, first = self.authored(reminders=False, archetype=True)
        schema = self.facet_call("facet_schema.create", owner=self.scope, schema_key="helper", definition={
            "display_name": "Helper", "description": None, "compatible_item_types": ["task"],
            "fields": [{"key": "person", "type": "reference", "target_kind": "subject", "required": True, "queryable": False}],
        })
        binding = self.facet_call("item_archetype.facet_binding.set", item_archetype_id=self.archetype["item_archetype_id"],
            facet_key="helper", facet_schema_revision_id=schema["facet_schema_revision_id"], expected_binding_id=None)
        self.facet_call("item.facets.update", item_id=first["after"]["task_item_id"], expected_item_version="1", changes=[{
            "op": "set", "facet_key": "helper", "facet_schema_revision_id": schema["facet_schema_revision_id"],
            "expected_binding_id": binding["facet_binding_id"], "values": {"person": "helper"},
        }])
        self.cancel_for_restoration(initial, first)
        self.subject("inactive")
        self.assert_blocked_restoration(initial, first, "configuration_invalid")

    def test_inactive_route_blocks_restoration_without_creating_replacement(self):
        initial, first = self.authored()
        self.cancel_for_restoration(initial, first)
        response = handle("delivery_target.upsert", {
            "command_id": "disable-route", "actor_subject_id": "owner", "delivery_target_id": "owner-route",
            "owner_kind": "subject", "owner_subject_id": "owner", "channel": "test", "adapter_name": "capture",
            "target_ref": "test://never-send", "status": "inactive", "updated_at_utc": self.now,
        }, self.context)
        self.assertTrue(response["ok"], response)
        self.assert_blocked_restoration(initial, first, "route_unavailable")

    def test_late_enrollment_includes_started_source_only_while_due_is_future(self):
        for offset, now, expected in (
            ("5400", "2026-08-08T18:30:00Z", 6),
            ("5400", "2026-08-08T19:30:00Z", 5),
            ("-3600", "2026-08-08T17:30:00Z", 5),
        ):
            with self.subTest(offset=offset, now=now):
                self.now = now
                request = self.request("catchup-" + offset + now)
                # Catalog keys cannot contain time punctuation.
                request["rule_key"] = "catchup_" + str(expected) + ("_negative" if offset.startswith("-") else "_positive")
                request["configuration"]["offset_seconds"] = offset
                created = self.run_command("create", request)
                self.assertTrue(created["ok"], created)
                result = self.reconcile(created["result"]["rule"], "page-" + request["rule_key"])
                self.assertEqual(len(result["result"]["results"]), expected)
                self.assertTrue(all(v["outcome"] == "created" for v in result["result"]["results"]))
                self.assertEqual(result["result"]["results"][0]["selector"]["scheduled_fact"],
                    "2026-08-08T18:00:00Z" if expected == 6 else "2026-08-09T18:00:00Z")

    def test_selected_enrollment_boundary_is_inclusive_and_survives_source_copy(self):
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        from spine.core.occurrences import expand_recurrence_set

        occurrence = expand_recurrence_set(recurrence, range_start="2026-08-10T00:00:00Z",
            range_end="2026-08-11T00:00:00Z", range_basis="original_schedule").occurrences[0]
        request = self.request()
        request["enrollment"] = {"kind": "selected_occurrence", "occurrence_key": occurrence["occurrence_key"]}
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        self.source_change()
        result = self.reconcile(self.rule(created["result"]["rule"]["related_task_rule_id"]), "selected-start")
        self.assertEqual([v["selector"]["scheduled_fact"] for v in result["result"]["results"]],
            [f"2026-08-{day:02}T18:00:00Z" for day in range(10, 14)])
        self.assertTrue(all(v["outcome"] == "created" for v in result["result"]["results"]))

    def test_group_task_owner_does_not_change_assignee_destination_or_create_grants(self):
        self.subject("active")
        group = handle("subject_group.upsert", {"command_id": "pickup-group", "actor_subject_id": "owner",
            "group_id": "pickup-group", "display_name": "Pickup scope", "updated_at_utc": self.now}, self.context)
        self.assertTrue(group["ok"], group)
        request = self.request()
        config = request["configuration"]
        config["task_owner"] = {"owner_kind": "subject_group", "owner_group_id": "pickup-group"}
        config["task_template"]["people"]["assignees"] = ["helper"]
        config["notification_plan"] = {"mode": "none", "custom_additions": [{
            "policy_key": "notice", "schedule": {"kind": "once", "at": {
                "kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
            "late_handling": {"kind": "skip"},
        }]}
        config["delivery"] = {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}}
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        result = self.reconcile(created["result"]["rule"], "group-owner")
        self.assertEqual(len(result["result"]["results"]), 6)
        for selected in result["result"]["results"]:
            task = selected["after"]["task_item_id"]
            owner = self.db.execute("SELECT * FROM item_access_owners WHERE item_id=?", (task,)).fetchone()
            self.assertEqual((owner["owner_kind"], owner["owner_group_id"], owner["creator_entitlement_subject_id"]),
                ("subject_group", "pickup-group", None))
            child = core._hydrated_item(self.db, task)
            self.assertEqual({r["subject_id"] for r in child["subject_roles"] if r["role"] == "assignee"}, {"helper"})
            self.assertEqual({p["recipient_subject_id"] for p in child["notification_policies"]}, {"owner"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM access_grants").fetchone()[0], 0)

    def test_manual_cancel_and_detach_remain_consumed_across_source_return(self):
        for mode, reason in (("cancel", "task_manually_cancelled"), ("detach", "binding_detached")):
            with self.subTest(mode=mode):
                request = self.request(mode)
                recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
                request["source"].update(item_version=recurrence["source_item_version"],
                    recurrence_revision_id=recurrence["recurrence_revision_id"])
                created = self.run_command("create", request)
                self.assertTrue(created["ok"], created)
                initial = self.reconcile(created["result"]["rule"], "initial-" + mode)
                first = initial["result"]["results"][0]
                task = first["after"]["task_item_id"]
                # Exercise observed ordinary state; automatic all-writer
                # invalidation/attempt gating belongs to the later R3 slice.
                with self.db.atomic_command(write=True):
                    if mode == "cancel":
                        create_next_item_version(self.db, item_id=task, target_version=1, created_at_utc=self.now,
                            created_by_subject_id="owner", task_detail={"task_status": "cancelled"},
                            supporting_command_id="manual-cancel")
                    else:
                        retire_temporal_binding(self.db, temporal_binding_id=first["after"]["temporal_binding_id"],
                            command_id="manual-detach", retired_at_utc=self.now)
                        propagate(self.db, binding_id=first["after"]["temporal_binding_id"])
                before = copy.deepcopy(core._hydrated_item(self.db, task))
                consumed = self.reconcile(initial["result"]["rule"], "consume-" + mode)
                selected = next(v for v in consumed["result"]["results"] if v["assignment_id"] == first["assignment_id"])
                self.assertEqual((selected["outcome"], selected["reason"]), ("consumed", reason))
                self.source_change(exdates=[self.excluded(first)])
                self.source_change(exdates=[])
                repeated = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "return-" + mode)
                selected = next(v for v in repeated["result"]["results"] if v["assignment_id"] == first["assignment_id"])
                self.assertEqual((selected["outcome"], selected["reason"]), ("consumed", reason))
                self.assertEqual(core._hydrated_item(self.db, task), before)
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations WHERE assignment_id=?",
                    (first["assignment_id"],)).fetchone()[0], 1)

    def cancel_and_return(self, *, whole_series):
        initial, first = self.authored(reminders=False)
        if whole_series:
            self.source_change(event_detail={"event_status": "cancelled"})
        else:
            self.source_change(overrides=[{"target_occurrence_key": first["occurrence_key"],
                "target_occurrence_selector": first["selector"], "lifecycle": "cancelled", "reason_code": "no_class"}])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "source-cancelled")
        selected = [v for v in cancelled["result"]["results"] if v["outcome"] == "cancelled"]
        self.assertEqual(len(selected), 6 if whole_series else 1)
        self.assertEqual({v["reason"] for v in selected}, {"source_cancelled" if whole_series else "source_occurrence_cancelled"})
        old = {v["after"]["task_item_id"]: copy.deepcopy(core._hydrated_item(self.db, v["after"]["task_item_id"])) for v in selected}
        if whole_series:
            # Whole-event cancellation is terminal in the ordinary event model;
            # R2 must not invent a reopen operation to obtain restoration.
            repeated = self.reconcile(cancelled["result"]["rule"], "source-still-cancelled")
            self.assertFalse(repeated["changed"])
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)
        else:
            self.source_change(overrides=[])
            restored = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "source-returned")
            self.assertEqual(sum(v["outcome"] == "restored" for v in restored["result"]["results"]), len(selected))
        for identity, snapshot in old.items():
            self.assertEqual(core._hydrated_item(self.db, identity), snapshot)
        with self.db.atomic_command(write=False):
            verify_deep(self.db)

    def test_whole_event_cancellation_cancels_each_open_assignment_without_reopening(self):
        self.cancel_and_return(whole_series=True)

    def test_occurrence_lifecycle_cancellation_and_return_preserve_other_tasks(self):
        self.cancel_and_return(whole_series=False)
