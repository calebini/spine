"""Restoration composes actual predecessor truth on disposable candidate ledgers."""

import copy
import unittest

from spine.commands import core, handle
from spine.commands.facets import CONTRACTS
from spine.core.hashing import command_derived_id
from spine.ledger import facets
from spine.ledger.items import create_next_item_version
from spine.ledger.supporting import ItemSubjectRoleInput
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


class RecurringTaskRestorationTests(unittest.TestCase):
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

    def authored(self, *, reminders=True, archetype=False):
        request = self.request()
        config = request["configuration"]
        if archetype:
            config["task_template"]["item"]["primary_location"] = {"mode": "create", "kind": "place", "label": "Side door"}
            config["task_template"]["item"]["archetype"] = {
                "item_archetype_id": self.archetype["item_archetype_id"], "revision_resolution": "current",
                "selection_source": "operator_explicit", "source_ref": "explicit-selection",
            }
        if reminders:
            config["notification_plan"] = {
                "mode": "explicit", "notification_profile_id": self.profile["notification_profile_id"],
                "revision_resolution": "current", "custom_additions": [], "rendering_applications": [],
            }
            config["delivery"] = {
                "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
            }
            config["materialization"] = {
                "mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100",
            }
        result = self.run_command("create", request)
        self.assertTrue(result["ok"], result)
        initial = self.reconcile(result["result"]["rule"])
        return initial, initial["result"]["results"][0]

    def cycle(self, rule, selected, key="cycle"):
        self.source_change(exdates=[self.excluded(selected)])
        cancelled = self.reconcile(self.rule(rule["related_task_rule_id"]), key + "-cancel")
        old = copy.deepcopy(core._hydrated_item(self.db, selected["after"]["task_item_id"]))
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(rule["related_task_rule_id"]), key + "-restore")
        result = next(v for v in restored["result"]["results"] if v["assignment_id"] == selected["assignment_id"])
        self.assertEqual(result["outcome"], "restored", result)
        self.assertEqual(core._hydrated_item(self.db, selected["after"]["task_item_id"]), old)
        self.assertTrue(cancelled["ok"])
        return restored, result, core._hydrated_item(self.db, result["after"]["task_item_id"])

    def route(self):
        result = handle("delivery_target.upsert", {
            "command_id": "independent-route", "actor_subject_id": "owner", "delivery_target_id": "independent-route",
            "owner_kind": "subject", "owner_subject_id": "owner", "channel": "whatsapp", "adapter_name": "openclaw",
            "target_ref": "test://never-send", "updated_at_utc": self.now,
        }, self.context)
        self.assertTrue(result["ok"], result)

    def facet_call(self, command, **fields):
        self.facet_counter = getattr(self, "facet_counter", 0) + 1
        result = handle(command, {
            "contract_version": CONTRACTS[command], "command_id": f"restore-{command}-{self.facet_counter}",
            "actor_subject_id": "owner", "action_timestamp_utc": self.now, **fields,
        }, self.context)
        self.assertTrue(result["ok"], result)
        return result

    def test_custom_family_and_independent_reminders_survive_repeated_generations_without_relabeling(self):
        initial, first = self.authored()
        task = first["after"]["task_item_id"]
        self.route()
        extra = handle("reminder.create", {
            "command_id": "independent-reminder", "actor_subject_id": "owner", "item_id": task, "target_version": "1",
            "created_at_utc": self.now, "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "whatsapp",
            "delivery_target_id": "independent-route", "notification": {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "task_due", "application_scope": "item"},
                "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-1200"}},
                "late_handling": {"kind": "deliver_within", "grace_seconds": "3600"},
            },
        }, self.context)
        self.assertTrue(extra["ok"], extra)
        current = core._hydrated_item(self.db, task)
        family_id = next(p["notification_intent_id"] for p in initial["result"]["policy_mappings"] if p["task_item_id"] == task)
        family = next(p for p in current["notification_policies"] if p["notification_intent_id"] == family_id)
        edited = handle("reminder.edit", {
            "command_id": "individual-family-edit", "actor_subject_id": "owner", "item_id": task,
            "target_version": current["current_version"], "notification_intent_id": family_id,
            "notification_policy_id": family["notification_policy_id"], "updated_at_utc": self.now,
            "patch": {"channel": "whatsapp", "delivery_target_id": "independent-route", "schedule": {
                "kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-900"},
            }},
        }, self.context)
        self.assertTrue(edited["ok"], edited)
        prior_intents = {p["notification_intent_id"] for p in core._hydrated_item(self.db, task)["notification_policies"]}
        prior_independent = extra["notification_intent_id"]
        self.now = "2026-08-08T19:15:00Z"
        result, selected, child = self.cycle(initial["result"]["rule"], first)
        for index in range(2):
            active = [p for p in child["notification_policies"] if p["status"] == "active"]
            self.assertEqual({p["schedule"]["at"]["offset_seconds"] for p in active}, {"-900", "-1200"})
            self.assertEqual({p["delivery_target_id"] for p in active}, {"independent-route"})
            intents = {p["notification_intent_id"] for p in active}
            self.assertTrue(prior_intents.isdisjoint(intents))
            mapped = [m for m in result["result"]["policy_mappings"] if m["task_item_id"] == child["item_id"]]
            self.assertEqual(len(mapped), 1)
            self.assertEqual(mapped[0]["policy_key"], "profile_ten_minutes")
            self.assertEqual(mapped[0]["creation_token"], selected["generation_id"] + ":profile_ten_minutes")
            independent = next(p for p in active if p["schedule"]["at"]["offset_seconds"] == "-1200")
            expected_token = command_derived_id(
                prefix="notification", command="schedule.related_task_rule.reconcile", command_id=selected["generation_id"],
                row_role="notification", request_path="/restored/independent/" + prior_independent,
            )
            self.assertEqual(independent["intent_created_by_command_id"], expected_token)
            late_work = self.db.execute(
                "SELECT eligible_at_utc FROM work_instances WHERE item_id=? AND notification_intent_id=?",
                (child["item_id"], independent["notification_intent_id"]),
            ).fetchall()
            self.assertEqual([r[0] for r in late_work], ["2026-08-08T19:10:00Z"])
            repeat = self.reconcile(result["result"]["rule"], f"restored-noop-{index}")
            self.assertFalse(repeat["changed"], repeat)
            self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
            if index == 0:
                prior_intents = intents
                prior_independent = independent["notification_intent_id"]
                result, selected, child = self.cycle(repeat["result"]["rule"], selected, "second-cycle")

    def test_disabled_family_policy_is_not_silently_reintroduced(self):
        initial, first = self.authored()
        mapping = next(p for p in initial["result"]["policy_mappings"] if p["task_item_id"] == first["after"]["task_item_id"])
        disabled = handle("reminder.disable", {
            "command_id": "disable-family", "actor_subject_id": "owner", "item_id": mapping["task_item_id"],
            "target_version": "1", "notification_intent_id": mapping["notification_intent_id"],
            "notification_policy_id": mapping["notification_policy_id"], "disabled_at_utc": self.now,
        }, self.context)
        self.assertTrue(disabled["ok"], disabled)
        restored, _, child = self.cycle(initial["result"]["rule"], first)
        self.assertFalse(any(p["status"] == "active" for p in child["notification_policies"]))
        self.assertFalse(any(p["task_item_id"] == child["item_id"] for p in restored["result"]["policy_mappings"]))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances WHERE item_id=?", (child["item_id"],)).fetchone()[0], 0)

    def test_restoration_ignores_newer_rule_and_profile_defaults(self):
        initial, first = self.authored()
        revised = handle("notification_profile.revise", {
            "contract_version": "spine.notification-profiles.v2", "command_id": "new-profile-default",
            "actor_subject_id": "owner", "action_timestamp_utc": self.now,
            "notification_profile_id": self.profile["notification_profile_id"],
            "expected_current_revision_id": self.profile["notification_profile_revision_id"],
            "revision": {"compatible_item_types": ["task"], "templates": [{
                "template_key": "five_minutes", "schedule": {
                    "kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-300"},
                }, "late_handling": {"kind": "skip"}, "rendering": {"kind": "ordinary"},
            }]},
        }, self.context)
        self.assertTrue(revised["ok"], revised)
        desired = self.request()["configuration"]
        desired["generation_horizon_seconds"] = "4838400"
        desired["task_template"]["item"]["title"] = "Only future assignments"
        updated = self.run_command("update", self.write(
            "update", initial["result"]["rule"], configuration=desired, adoption_scope="new_assignments_only"
        ))
        self.assertTrue(updated["ok"], updated)
        restored, selected, child = self.cycle(updated["result"]["rule"], first)
        self.assertEqual(child["version"]["title"], "Pick up Joe")
        self.assertEqual(selected["after"]["adopted_rule_revision_id"], initial["result"]["rule"]["rule_revision_id"])
        self.assertNotEqual(restored["result"]["rule"]["rule_revision_id"], selected["after"]["adopted_rule_revision_id"])
        active = [p for p in child["notification_policies"] if p["status"] == "active"]
        self.assertEqual([p["schedule"]["at"]["offset_seconds"] for p in active], ["-600"])
        app = self.db.execute("SELECT notification_profile_revision_id FROM notification_profile_applications WHERE item_id=?",
                              (child["item_id"],)).fetchone()
        self.assertEqual(app[0], self.profile["notification_profile_revision_id"])

    def test_facets_roles_archetype_and_primary_location_copy_without_new_versions_or_catalog_resolution(self):
        initial, first = self.authored(reminders=False, archetype=True)
        task = first["after"]["task_item_id"]
        schema = self.facet_call("facet_schema.create", owner=self.scope, schema_key="pickup_details", definition={
            "display_name": "Pickup details", "description": None, "compatible_item_types": ["task"],
            "fields": [{"key": "instruction", "type": "text", "required": True, "queryable": True, "max_length": "128"}],
        })
        binding = self.facet_call("item_archetype.facet_binding.set", item_archetype_id=self.archetype["item_archetype_id"],
                                  facet_key="pickup_details", facet_schema_revision_id=schema["facet_schema_revision_id"],
                                  expected_binding_id=None)
        self.facet_call("item.facets.update", item_id=task, expected_item_version="1", changes=[{
            "op": "set", "facet_key": "pickup_details", "facet_schema_revision_id": schema["facet_schema_revision_id"],
            "expected_binding_id": binding["facet_binding_id"], "values": {"instruction": "Meet at the side door"},
        }])
        # An independently selected participant is not an assignee or an owner.
        with self.db.atomic_command(write=True):
            create_next_item_version(self.db, item_id=task, target_version=2, created_at_utc=self.now,
                                     created_by_subject_id="owner", subject_role_replacement_roles=("participant",),
                                     subject_roles=(ItemSubjectRoleInput(subject_id="owner", role="participant"),),
                                     supporting_command_id="individual-participant")
        prior_entries = facets.load_snapshot(self.db, task, 3)
        location_id = core._hydrated_item(self.db, task)["locations"][0]["location_id"]
        _, _, child = self.cycle(initial["result"]["rule"], first)
        self.assertEqual(child["current_version"], 1)
        roles = {(r["subject_id"], r["role"]) for r in child["subject_roles"] if r["status"] == "active"}
        self.assertEqual(roles, {("owner", "assignee"), ("owner", "participant")})
        self.assertEqual(child["locations"][0]["location_id"], location_id)
        self.assertEqual(child["locations"][0]["label"], "Side door")
        copied = facets.load_snapshot(self.db, child["item_id"], 1)
        self.assertEqual(len(copied), 1)
        for field in facets.ENTRY_COLUMNS:
            if field != "source_command_receipt_id":
                self.assertEqual(copied[0][field], prior_entries[0][field], field)
        assignment = self.db.execute("SELECT selection_source,source_ref FROM item_archetype_assignments WHERE item_id=?",
                                     (child["item_id"],)).fetchone()
        self.assertEqual(tuple(assignment), ("operator_explicit", "explicit-selection"))
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_invalid_restored_facet_is_a_decision_without_a_partial_successor(self):
        initial, first = self.authored(reminders=False, archetype=True)
        task = first["after"]["task_item_id"]
        schema = self.facet_call("facet_schema.create", owner=self.scope, schema_key="pickup_details", definition={
            "display_name": "Details", "description": None, "compatible_item_types": ["task"],
            "fields": [{"key": "note", "type": "text", "required": True, "queryable": False, "max_length": "64"}],
        })
        binding = self.facet_call("item_archetype.facet_binding.set", item_archetype_id=self.archetype["item_archetype_id"],
                                  facet_key="pickup_details", facet_schema_revision_id=schema["facet_schema_revision_id"],
                                  expected_binding_id=None)
        self.facet_call("item.facets.update", item_id=task, expected_item_version="1", changes=[{
            "op": "set", "facet_key": "pickup_details", "facet_schema_revision_id": schema["facet_schema_revision_id"],
            "expected_binding_id": binding["facet_binding_id"], "values": {"note": "Remember the bag"},
        }])
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "facet-cancel")
        self.facet_call("facet_schema.retire", facet_schema_id=schema["facet_schema_id"],
                        expected_current_revision_id=schema["facet_schema_revision_id"])
        self.source_change(exdates=[])
        result = self.reconcile(self.rule(cancelled["result"]["rule"]["related_task_rule_id"]), "facet-blocked")
        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual((selected["outcome"], selected["reason"]), ("decision_required", "configuration_invalid"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_restoration_faults_roll_back_policies_owner_epoch_and_profile_application(self):
        initial, first = self.authored()
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "fault-cancel")
        self.source_change(exdates=[])
        rule = self.rule(cancelled["result"]["rule"]["related_task_rule_id"])
        request = self.write("reconcile", rule, limits={}) | {"command_id": "fault-restore"}
        before = base.dump(self.db)
        for stage in ("task", "ownership_state", "owner", "binding", "policies", "work", "audit", "receipt"):
            def fault(current, selected=stage):
                if current == selected:
                    raise RuntimeError("injected " + selected)

            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, "injected"):
                self.run_command("reconcile", request, fault=fault)
            self.assertEqual(base.dump(self.db), before)
            self.assertEqual(self.db._command_unit_depth, 0)

    def test_eight_facet_snapshot_and_typed_index_are_installed_in_the_new_task_first_version(self):
        initial, first = self.authored(reminders=False, archetype=True)
        task = first["after"]["task_item_id"]
        schema = self.facet_call("facet_schema.create", owner=self.scope, schema_key="pickup_details", definition={
            "display_name": "Details", "description": None, "compatible_item_types": ["task"],
            "fields": [{"key": "note", "type": "text", "required": True, "queryable": True, "max_length": "64"}],
        })
        changes = []
        for index in range(8):
            key = f"details_{index}"
            binding = self.facet_call("item_archetype.facet_binding.set", item_archetype_id=self.archetype["item_archetype_id"],
                                      facet_key=key, facet_schema_revision_id=schema["facet_schema_revision_id"], expected_binding_id=None)
            changes.append({"op": "set", "facet_key": key, "facet_schema_revision_id": schema["facet_schema_revision_id"],
                            "expected_binding_id": binding["facet_binding_id"], "values": {"note": "Keep " + str(index)}})
        self.facet_call("item.facets.update", item_id=task, expected_item_version="1", changes=changes)
        _, _, child = self.cycle(initial["result"]["rule"], first)
        copied = facets.load_snapshot(self.db, child["item_id"], 1)
        self.assertEqual(len(copied), 8)
        self.assertEqual(child["current_version"], 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM item_facet_current_values WHERE item_id=? AND item_version=1", (child["item_id"],)
        ).fetchone()[0], 8)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
