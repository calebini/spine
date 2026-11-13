"""RF2 complete child composition with narrow inputs and no page mutation API."""

from __future__ import annotations

import ast
import inspect
import sqlite3
import unittest
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.ledger import facets, item_reads
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.supporting import ItemSubjectRoleInput
from spine.ledger.work import start_work_instance
from spine.services import recurring_task_adoption, recurring_task_children, recurring_task_restoration
from spine.services.item_mutations import create_next_item_version
from spine.services.recurring_task_operations import (
    ChangeChild,
    ChangedChild,
    ChildDisposition,
    ChildInvocation,
    ChildWorkOverflow,
    CreateChild,
    LocalAuthority,
    RestoreChild,
    WorkEvidence,
)
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_restoration as restoration


class RecurringChildOperationTests(unittest.TestCase):
    def setUp(self):
        self.h = restoration.RecurringTaskRestorationTests()
        self.h.contracts = base.contracts()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def invocation(self):
        return ChildInvocation(
            authority=LocalAuthority.TRUSTED_LOCAL, command_id="child-operation", actor_subject_id="owner",
            now=self.h.now, delivery_target_defaults={}, fault=lambda stage: None,
        )

    def test_inputs_are_closed_no_page_request_context_or_caller_assembly_callbacks(self):
        self.assertEqual({f.name for f in fields(ChildInvocation)}, {
            "authority", "command_id", "actor_subject_id", "now", "delivery_target_defaults", "fault",
        })
        self.assertEqual(ChildInvocation.command, "schedule.related_task_rule.reconcile")
        self.assertEqual(ChildInvocation.contract_version, "spine.recurring-related-tasks.v1")
        for module in (recurring_task_children, recurring_task_restoration, recurring_task_adoption):
            source = Path(inspect.getfile(module)).read_text()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.FunctionDef):
                    names = {a.arg for a in (*node.args.args, *node.args.kwonlyargs)}
                    self.assertFalse(names & {"page", "request", "context", "insert_canonical_extension", "insert_prerequisites"})
                if isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func).rsplit(".", 1)[-1], {"commit", "atomic_command", "handle"})

    def test_authority_and_outer_transaction_are_required_before_any_child_write(self):
        db, invocation = self.h.db, self.invocation()
        before = base.dump(db)
        operations = (
            lambda inv: recurring_task_children.create(db, inv, None),
            lambda inv: recurring_task_children.restore(db, inv, None),
            lambda inv: recurring_task_children.change(db, inv, None),
            lambda inv: recurring_task_children.reconcile_work(db, inv, "missing", 1, {}, work_limit=1),
        )
        for operation in operations:
            with self.assertRaisesRegex(SpineValidationError, "environment_failure:transaction"):
                operation(invocation)
            with db.atomic_command(), self.assertRaisesRegex(SpineValidationError, "environment_failure:authority"):
                operation(replace(invocation, authority=None))
        self.assertEqual(base.dump(db), before)
        with db.atomic_command():
            invocation.require_transaction(db)
        raw = sqlite3.connect(":memory:")
        self.addCleanup(raw.close)
        with self.assertRaisesRegex(SpineValidationError, "environment_failure:transaction"):
            invocation.require_transaction(raw)

    def test_terminal_intents_cannot_also_move_or_adopt(self):
        common = dict(assignment_id="a", generation={}, binding={}, current={}, source={}, configuration={}, work_limit=1)
        for disposition in (ChildDisposition.CANCEL, ChildDisposition.DETACH):
            for edit in ({"target": {}}, {"managed": {"assignees": []}}):
                with self.subTest(disposition=disposition, edit=edit), self.assertRaises(ValueError):
                    ChangeChild(**common, disposition=disposition, **edit)
        with self.assertRaises(ValueError):
            ChangeChild(**common, disposition="cancel")

    def test_create_composes_complete_facts_under_one_outer_command_and_replay_does_not_reenter(self):
        original, calls = recurring_task_children.create, []

        def observe(db, invocation, plan):
            self.assertIsInstance(plan, CreateChild)
            self.assertIsInstance(invocation, ChildInvocation)
            self.assertTrue(db.in_transaction)
            before = db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
            child = original(db, invocation, plan)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0], before)
            item = item_reads.hydrated_item(db, child["task_item_id"])
            self.assertEqual(item["current_version"], 1)
            self.assertEqual(len(item["notification_policies"]), 1)
            self.assertEqual(len(item["locations"]), 1)
            self.assertEqual({r["role"] for r in item["subject_roles"]}, {"assignee"})
            for table in ("item_access_owners", "item_access_owner_revisions", "notification_profile_applications"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table} WHERE item_id=?", (child["task_item_id"],)).fetchone()[0], 1)
            self.assertTrue(child["work"])
            self.assertEqual(child["policy_mappings"][0]["creation_token"], plan.generation_id + ":profile_ten_minutes")
            calls.append((invocation, plan))
            return child

        with patch.object(recurring_task_children, "create", side_effect=observe):
            initial, _ = self.h.authored(archetype=True)
        self.assertEqual(len(calls), len(initial["result"]["results"]))
        request = self.h.write("reconcile", initial["result"]["rule"], limits={})
        request["command_id"] = "child-replay"
        first = self.h.run_command("reconcile", request)
        self.assertTrue(first["ok"], first)
        before = base.dump(self.h.db)
        with patch.object(recurring_task_children, "create", side_effect=AssertionError("replayed child")), \
                patch.object(recurring_task_children, "change", side_effect=AssertionError("replayed change")):
            replay = self.h.run_command("reconcile", request)
        self.assertTrue(replay["replayed"], replay)
        self.assertEqual(base.dump(self.h.db), before)
        self.assertEqual(self.h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def move(self, first):
        recurrence = load_current_recurrence_set(self.h.db, item_id=self.h.event["item_id"])
        self.h.source_change(overrides=[{
            "segment_id": recurrence["segments"][0]["segment_id"], "target_occurrence_key": first["occurrence_key"],
            "target_occurrence_selector": first["selector"], "status": "active",
            "expressed_scheduled_fact": "2026-08-08T20:00:00Z", "reason_code": "move",
        }])

    def test_change_returns_evidence_only_after_complete_allocator_and_work_composition(self):
        initial, first = self.h.authored(archetype=True)
        self.move(first)
        original, observed = recurring_task_children.change, []

        def observe(db, invocation, plan):
            result = original(db, invocation, plan)
            self.assertIsInstance(plan, ChangeChild)
            self.assertIsInstance(result, ChangedChild)
            self.assertIsInstance(result.work, WorkEvidence)
            if plan.target is not None:
                self.assertEqual(result.task_item_version, "2")
                self.assertTrue(result.work.cancelled)
                self.assertTrue(result.work.created)
                self.assertEqual(len(result.audit_ids), 1)
                item = item_reads.hydrated_item(db, plan.generation["task_item_id"])
                self.assertEqual(item["current_version"], 2)
                self.assertEqual(len(item["locations"]), 1)
                self.assertEqual(len(item["notification_policies"]), 1)
            observed.append(result)
            return result

        with patch.object(recurring_task_children, "change", side_effect=observe):
            result = self.h.reconcile(self.h.rule(initial["result"]["rule"]["related_task_rule_id"]), "typed-change")
        self.assertTrue(observed)
        self.assertTrue(result["changed"])

    def test_change_faults_restore_complete_sql_and_transaction_state(self):
        initial, first = self.h.authored(archetype=True)
        self.move(first)
        request = self.h.write("reconcile", self.h.rule(initial["result"]["rule"]["related_task_rule_id"]), limits={})
        before = base.dump(self.h.db)
        for stage in ("binding", "work", "task", "audit", "receipt"):
            def fault(at, selected=stage):
                if at == selected:
                    raise RuntimeError("change fault " + selected)

            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, "change fault"):
                self.h.run_command("reconcile", request, fault=fault)
            self.assertEqual(base.dump(self.h.db), before)
            self.assertEqual(self.h.db._command_unit_depth, 0)
            self.assertFalse(self.h.db.in_transaction)

    def test_restore_is_separate_and_pins_actual_predecessor_not_catalog_defaults(self):
        initial, first = self.h.authored(archetype=True)
        original, observed = recurring_task_children.restore, []

        def observe(db, invocation, plan):
            self.assertIsInstance(plan, RestoreChild)
            self.assertEqual(plan.creation.configuration, plan.predecessor.configuration)
            result = original(db, invocation, plan)
            self.assertNotEqual(result["task_item_id"], plan.predecessor.current["item_id"])
            self.assertEqual(result["task_item_version"], "1")
            observed.append(plan)
            return result

        with patch.object(recurring_task_children, "restore", side_effect=observe):
            self.h.cycle(initial["result"]["rule"], first)
        self.assertEqual(len(observed), 1)
        mismatched = replace(observed[0].creation, configuration={})
        with self.h.db.atomic_command(), self.assertRaisesRegex(ValueError, "actual predecessor"):
            recurring_task_children.restore(
                self.h.db, self.invocation(), RestoreChild(creation=mismatched, predecessor=observed[0].predecessor),
            )

    def test_child_create_charges_its_indivisible_work_bound_before_returning_evidence(self):
        original = recurring_task_children.create

        def narrow(db, invocation, plan):
            return original(db, invocation, replace(plan, work_limit=0))

        request = self.h.request()
        request["configuration"].update(
            notification_plan={
                "mode": "explicit", "notification_profile_id": self.h.profile["notification_profile_id"],
                "revision_resolution": "current", "custom_additions": [], "rendering_applications": [],
            },
            delivery={
                "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
            },
            materialization={"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"},
        )
        rule = self.h.run_command("create", request)["result"]["rule"]
        before = base.dump(self.h.db)
        with patch.object(recurring_task_children, "create", side_effect=narrow):
            result = self.h.run_command("reconcile", self.h.write("reconcile", rule, limits={}))
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["error"]["code"], result["error"]["field"]), ("capacity_exceeded", "limits.work_rows"))
        self.assertEqual(base.dump(self.h.db), before)
        self.assertEqual(self.h.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 0)
        self.assertEqual(self.h.db.execute("SELECT COUNT(*) FROM coordination_items WHERE item_type='task'").fetchone()[0], 0)

    def test_adoption_empty_assignee_clear_preserves_opposite_role(self):
        initial, first = self.h.authored(reminders=False)
        task = first["after"]["task_item_id"]
        with self.h.db.atomic_command():
            create_next_item_version(
                self.h.db, item_id=task, target_version=1, created_at_utc=self.h.now, created_by_subject_id="owner",
                subject_role_replacement_roles=("participant",),
                subject_roles=(ItemSubjectRoleInput(subject_id="owner", role="participant"),),
                supporting_command_id="independent-participant",
            )
        rule = self.h.rule(initial["result"]["rule"]["related_task_rule_id"])
        config = self.h.request()["configuration"]
        config["generation_horizon_seconds"] = "4838400"
        config["task_template"]["people"]["assignees"] = []
        request = self.h.write("update", rule, configuration=config, adoption_scope="upcoming_open")
        updated = self.h.run_command("update", request)
        self.assertTrue(updated["ok"], updated)
        self.h.reconcile(updated["result"]["rule"], "clear-assignees")
        current = item_reads.hydrated_item(self.h.db, task)
        self.assertEqual({r["role"] for r in current["subject_roles"] if r["status"] == "active"}, {"participant"})

    def test_individual_work_overflow_has_exact_existing_error_identity(self):
        error = ChildWorkOverflow()
        self.assertEqual(error.code, "capacity_exceeded:limits.work_rows")
        self.assertEqual(error.message, "recurring-task request could not complete")

    def test_move_preserves_started_work_and_returns_it_as_protected_evidence(self):
        initial, first = self.h.authored()
        task = first["after"]["task_item_id"]
        work = self.h.db.execute("SELECT work_instance_id FROM work_instances WHERE item_id=?", (task,)).fetchone()[0]
        start_work_instance(self.h.db, work_instance_id=work, started_at_utc="2026-08-08T19:20:00Z")
        prior = dict(self.h.db.execute("SELECT * FROM work_instances WHERE work_instance_id=?", (work,)).fetchone())
        self.move(first)
        original, evidence = recurring_task_children.change, []

        def observe(*args):
            result = original(*args)
            evidence.append(result.work)
            return result

        with patch.object(recurring_task_children, "change", side_effect=observe):
            result = self.h.reconcile(self.h.rule(initial["result"]["rule"]["related_task_rule_id"]), "protect-started")
        self.assertTrue(result["ok"], result)
        self.assertTrue(any(work in e.protected_stale for e in evidence))
        self.assertFalse(any(work in e.cancelled for e in evidence))
        self.assertEqual(dict(self.h.db.execute("SELECT * FROM work_instances WHERE work_instance_id=?", (work,)).fetchone()), prior)
        self.assertEqual(self.h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_nonqueryable_location_reference_survives_change_and_restore_without_migration(self):
        initial, first = self.h.authored(reminders=False, archetype=True)
        task = first["after"]["task_item_id"]
        location = item_reads.hydrated_item(self.h.db, task)["locations"][0]["location_id"]
        schema = self.h.facet_call("facet_schema.create", owner=self.h.scope, schema_key="pickup_place", definition={
            "display_name": "Pickup place", "description": None, "compatible_item_types": ["task"],
            "fields": [{"key": "place", "type": "reference", "target_kind": "location", "required": True, "queryable": False}],
        })
        binding = self.h.facet_call(
            "item_archetype.facet_binding.set", item_archetype_id=self.h.archetype["item_archetype_id"],
            facet_key="pickup_place", facet_schema_revision_id=schema["facet_schema_revision_id"], expected_binding_id=None,
        )
        self.h.facet_call("item.facets.update", item_id=task, expected_item_version="1", changes=[{
            "op": "set", "facet_key": "pickup_place", "facet_schema_revision_id": schema["facet_schema_revision_id"],
            "expected_binding_id": binding["facet_binding_id"], "values": {"place": location},
        }])
        before = facets.load_snapshot(self.h.db, task, 2)
        self.move(first)
        moved = self.h.reconcile(self.h.rule(initial["result"]["rule"]["related_task_rule_id"]), "move-with-reference")
        self.assertEqual(facets.load_snapshot(self.h.db, task, 3), before)
        selected = next(r for r in moved["result"]["results"] if r["assignment_id"] == first["assignment_id"])
        _, _, child = self.h.cycle(moved["result"]["rule"], selected)
        restored = facets.load_snapshot(self.h.db, child["item_id"], 1)
        for key in facets.ENTRY_COLUMNS:
            if key != "source_command_receipt_id":
                self.assertEqual(restored[0][key], before[0][key])
        self.assertEqual(self.h.db.execute(
            "SELECT COUNT(*) FROM item_facet_references WHERE item_id=? AND location_id=?", (child["item_id"], location)
        ).fetchone()[0], 1)
        self.assertEqual(self.h.db.execute(
            "SELECT COUNT(*) FROM item_facet_current_values WHERE item_id=?", (child["item_id"],)
        ).fetchone()[0], 0)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"), self.h.db.atomic_command():
            self.h.db.execute("UPDATE locations SET label='Rewritten' WHERE location_id=?", (location,))


if __name__ == "__main__":
    unittest.main()
