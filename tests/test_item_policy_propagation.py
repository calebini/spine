"""RF3 item/policy composition, omission guards and retained proof ownership."""

import ast
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ChangeCategory
from spine.core.notifications import normalize_notification_policy
from spine.ledger import item_effects, items
from spine.ledger.mutation_state import TransactionMutationState
from spine.ledger.notifications import insert_notification_schedule_policy
from spine.ledger.supporting import ItemSubjectRoleInput
from spine.services import item_mutations, mutation_propagation
from tests import test_schedule_operations_command as schedules


def dump(db):
    return "\n".join(db.iterdump())


class ItemPolicyPropagationTests(unittest.TestCase):
    def setUp(self):
        self.h = schedules.ScheduleOperationsCommandTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db, self.ctx = self.h.connection, self.h.context

    def observe(self, calls):
        original = mutation_propagation.propagate

        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            if result.items:
                calls.append(result)
            return result
        return patch.object(mutation_propagation, "propagate", side_effect=capture)

    def create(self):
        response = handle("schedule.create", self.h.event_request("item-effects"), self.ctx)
        self.assertTrue(response["ok"], response)
        return response

    def update(self, identity, version="1", title="New title"):
        return dict(contract_version="spine.schedule-update.v2", command_id="item-update-" + version,
            actor_subject_id="owner", item_id=identity, target_version=version,
            updated_at_utc="2026-08-13T13:00:00Z", patch={"item": {"title": title}}, materialization={"mode": "none"})

    def test_exact_item_and_policy_copy_facts_without_false_time_or_lifecycle(self):
        calls = []
        with self.observe(calls):
            event = self.create()
            changed = handle("schedule.update", self.update(event["item_id"]), self.ctx)
        self.assertTrue(changed["ok"], changed)
        self.assertEqual(len(calls), 2)
        created, updated = calls
        initial, successor = created.items[0], updated.items[0]
        self.assertIsNone(initial.before)
        self.assertEqual(successor.before, initial.after)
        self.assertEqual(successor.after.version, 2)
        self.assertEqual(successor.categories, {ChangeCategory.ITEM})
        self.assertEqual(successor.after.detail_bytes, successor.before.detail_bytes)
        self.assertEqual(len(updated.policies), 1)
        self.assertEqual(updated.policies[0].source_policy_id, created.policies[0].policy_id)
        self.assertEqual(updated.policies[0].item_version, 2)
        self.assertNotEqual(updated.policies[0].policy_id, created.policies[0].policy_id)
        definition = json.loads(updated.policies[0].definition_bytes)
        self.assertEqual(definition["source_notification_policy_id"], created.policies[0].policy_id)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_noop_and_replay_add_no_item_or_policy_propagation(self):
        event = self.create()
        request = self.update(event["item_id"])
        changed = handle("schedule.update", request, self.ctx)
        self.assertTrue(changed["ok"], changed)
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("unexpected propagation")):
            replay = handle("schedule.update", request, self.ctx)
            noop = handle("schedule.update", self.update(event["item_id"], "2"), self.ctx)
        self.assertTrue(replay["ok"], replay)
        self.assertTrue(noop["ok"], noop)
        self.assertEqual(self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?",
                                        (event["item_id"],)).fetchone()[0], 2)

    def test_lifecycle_and_archive_are_distinct_from_temporal_change(self):
        event = self.create()
        calls = []
        with self.observe(calls):
            cancelled = handle("event.cancel", dict(command_id="cancel-effect", actor_subject_id="owner",
                item_id=event["item_id"], target_version="1", cancelled_at_utc="2026-08-13T13:00:00Z"), self.ctx)
            archived = handle("item.archive", dict(command_id="archive-effect", actor_subject_id="owner",
                item_id=event["item_id"], target_version="2", archived_at_utc="2026-08-13T14:00:00Z"), self.ctx)
        self.assertTrue(cancelled["ok"], cancelled)
        self.assertTrue(archived["ok"], archived)
        for result in calls:
            self.assertEqual(result.items[0].categories, {ChangeCategory.ITEM, ChangeCategory.LIFECYCLE})
        self.assertEqual(calls[1].items[0].before.version, calls[1].items[0].after.version)
        self.assertEqual(calls[1].policies, ())

    def test_temporary_copied_policy_is_not_reported_as_a_committed_successor(self):
        calls = []
        schedules.ScheduleOperationsCommandTests.setUpClass()
        with self.observe(calls):
            self.h.test_update_replaces_reminder_and_reconciles_then_materializes_atomically()
        self.assertEqual(len(calls), 2)  # replay does not propagate
        successor = calls[1]
        persisted = {r[0] for r in self.db.execute("SELECT policy_id FROM notification_policies WHERE version=2")}
        self.assertEqual({p.policy_id for p in successor.policies}, persisted)
        self.assertEqual(len(persisted), 1)

    def test_missing_application_propagation_rolls_back_create_and_update(self):
        original = mutation_propagation.propagate
        def omit(*args, **kwargs):
            return None if "item_id" in kwargs else original(*args, **kwargs)
        before = dump(self.db)
        with patch.object(mutation_propagation, "propagate", side_effect=omit):
            refused = handle("schedule.create", self.h.event_request("item-effects"), self.ctx)
        self.assertFalse(refused["ok"], refused)
        self.assertEqual(dump(self.db), before)
        event = self.create()
        before = dump(self.db)
        with patch.object(mutation_propagation, "propagate", side_effect=omit):
            refused = handle("schedule.update", self.update(event["item_id"]), self.ctx)
        self.assertFalse(refused["ok"], refused)
        self.assertEqual(dump(self.db), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def native_create(self, identity):
        return items.create_task_v1(self.db, item_id=identity, audit_id=identity, created_at_utc="2026-08-13T12:00:00Z",
            created_by_subject_id="owner", title="Native task")

    def test_native_composition_cannot_omit_or_duplicate_acknowledgement(self):
        before = dump(self.db)
        with self.assertRaisesRegex(SpineValidationError, "unpropagated item"), self.db.atomic_command():
            self.native_create("native")
        self.assertEqual(dump(self.db), before)
        with self.assertRaisesRegex(SpineValidationError, "already propagated"), self.db.atomic_command():
            self.native_create("native")
            mutation_propagation.propagate(self.db, item_id="native")
            mutation_propagation.propagate(self.db, item_id="native")
        self.assertEqual(dump(self.db), before)
        # The native standalone helper still owns and finishes its local transaction.
        self.native_create("standalone")
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_nested_trial_restores_pending_and_acknowledged_effects_then_retries(self):
        with self.db.atomic_command():
            for acknowledge in (False, True):
                with self.assertRaisesRegex(RuntimeError, "trial"), self.db.command_unit():
                    self.native_create("trial")
                    if acknowledge:
                        mutation_propagation.propagate(self.db, item_id="trial")
                    raise RuntimeError("trial")
                self.assertFalse(self.db.mutation_state.propagation.items)
            self.native_create("trial")
            mutation_propagation.propagate(self.db, item_id="trial")
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_wrong_policy_version_and_late_finalizer_failure_leave_no_partial_truth(self):
        original = item_effects.record_policy
        def wrong(db, value):
            original(db, {**value, "item_version": "999"})
        before = dump(self.db)
        with patch.object(item_effects, "record_policy", side_effect=wrong):
            refused = handle("schedule.create", self.h.event_request("item-effects"), self.ctx)
        self.assertFalse(refused["ok"], refused)
        self.assertEqual(dump(self.db), before)
        with (patch("spine.ledger.rendering_definitions.finalize", side_effect=RuntimeError("later finalizer")),
              self.assertRaisesRegex(RuntimeError, "later finalizer")):
            handle("schedule.create", self.h.event_request("item-effects"), self.ctx)
        self.assertEqual(dump(self.db), before)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_composed_policy_cannot_escape_without_an_item_application(self):
        event = self.create()
        policy = normalize_notification_policy({
            "authoring_contract": "spine.notification-schedule-authoring.v1",
            "target": {"anchor_role": "event_start", "application_scope": "item"},
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-60"}},
            "late_handling": {"kind": "skip"},
        }, item_id=event["item_id"], item_version="1", command_id="native-policy",
            created_at_utc="2026-08-13T12:00:00Z", recipient_kind="subject", recipient_id="owner",
            channel="whatsapp", delivery_target_id="whatsapp-owner")
        before = dump(self.db)
        with self.assertRaisesRegex(SpineValidationError, "unpropagated policy"), self.db.atomic_command():
            insert_notification_schedule_policy(self.db, normalized=policy)
        self.assertEqual(dump(self.db), before)
        # Explicit standalone native seeding still uses the checked local commit.
        with self.db:
            insert_notification_schedule_policy(self.db, normalized=policy)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_closed_sql_writer_and_application_adapter_inventory(self):
        root = Path(__file__).parents[1] / "src/spine"
        found = {}
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for match in re.finditer(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
                        r"(coordination_items|coordination_item_versions|event_details|task_details|notification_policies)\b",
                        node.value, re.I):
                        key = (str(path.relative_to(root)), match[1].lower())
                        found[key] = found.get(key, 0) + 1
        self.assertEqual(found, {("ledger/items.py", "coordination_items"): 3,
            ("ledger/items.py", "coordination_item_versions"): 1, ("ledger/items.py", "event_details"): 2,
            ("ledger/items.py", "task_details"): 2, ("ledger/notifications.py", "notification_policies"): 2})
        names = {"create_event_v1", "create_task_v1", "create_next_item_version", "create_item_version_from_draft",
                 "cancel_event", "cancel_task", "complete_task", "archive_item"}
        self.assertEqual({n for n in vars(item_mutations) if hasattr(getattr(item_mutations, n), "__wrapped__")}, names)
        for name in names:
            self.assertIs(getattr(item_mutations, name).__wrapped__, getattr(items, name))

    def test_people_clear_proves_only_selected_role_changed(self):
        calls = []
        with self.observe(calls), self.db.atomic_command():
            item_mutations.create_task_v1(self.db, item_id="roles", audit_id="roles", title="Roles",
                created_at_utc="2026-08-13T12:00:00Z", created_by_subject_id="owner",
                subject_roles=(ItemSubjectRoleInput("owner", "participant"), ItemSubjectRoleInput("owner", "assignee")))
            item_mutations.create_next_item_version(self.db, item_id="roles", target_version=1,
                created_at_utc="2026-08-13T13:00:00Z", created_by_subject_id="owner",
                subject_roles=(), subject_role_replacement_roles=("assignee",))
            item_mutations.create_next_item_version(self.db, item_id="roles", target_version=2,
                created_at_utc="2026-08-13T14:00:00Z", created_by_subject_id="owner", title="Copy")
        change = calls[1].items[0]
        self.assertEqual(change.categories, {ChangeCategory.ITEM, ChangeCategory.PEOPLE})
        self.assertEqual(change.after_people, (("owner", "participant", "active"),))
        self.assertEqual(calls[2].items[0].categories, {ChangeCategory.ITEM})

    def test_facet_only_changes_keep_time_and_work_consequences_separate(self):
        from tests.test_facet_commands import FacetCommandTests
        FacetCommandTests.setUpClass()
        h = FacetCommandTests()
        h.setUp()
        self.addCleanup(h.tearDown)
        calls = []
        with self.observe(calls):
            h.test_local_lifecycle_and_successive_copy_forward()
        changes = [r.items[0] for r in calls if ChangeCategory.FACETS in r.items[0].categories]
        self.assertEqual(len(changes), 4)
        for effect in changes:
            self.assertEqual(effect.categories, {ChangeCategory.ITEM, ChangeCategory.FACETS})

    def test_presentation_changes_and_copy_keep_exact_policy_specific_evidence(self):
        from tests.test_rendering_successor_authoring import RenderingSuccessorTests
        RenderingSuccessorTests.setUpClass()
        h = RenderingSuccessorTests()
        h.setUp()
        self.addCleanup(h.tearDown)
        calls = []
        with self.observe(calls):
            h.test_presentation_only_edit_noop_dryrun_copy_forward_and_work_preservation()
        changed = [r for r in calls if any(ChangeCategory.PRESENTATIONS in p.categories for p in r.policies)]
        self.assertEqual(len(changed), 2)  # rolled-back preview and real application
        for result in changed:
            self.assertEqual(result.items[0].categories, {ChangeCategory.ITEM})
            self.assertEqual(len(result.policies), 1)
        self.assertEqual(calls[-1].policies[0].before_presentation, calls[-1].policies[0].after_presentation)

    def test_lost_staged_presentation_is_environment_failure_and_rolls_back(self):
        from spine.commands import rendering_candidate
        from tests.test_rendering_successor_authoring import NOW, RenderingSuccessorTests
        RenderingSuccessorTests.setUpClass()
        h = RenderingSuccessorTests()
        h.setUp()
        self.addCleanup(h.tearDown)
        original = mutation_propagation.propagate

        def lose_presentation(db, **kwargs):
            if kwargs.get("item_id") is not None:
                db.mutation_state.renderings.pending.clear()
            return original(db, **kwargs)

        before = dump(h.db)
        with patch.object(mutation_propagation, "propagate", side_effect=lose_presentation):
            result = rendering_candidate.execute("schedule.create",
                h.fixture.event_request("lost-presentation", materialize=False)
                | {"contract_version": "spine.schedule-create.v3"}, h.context, now=NOW)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["error"]["code"], "environment_failure")
        self.assertEqual(dump(h.db), before)
        self.assertEqual(h.db.mutation_state, TransactionMutationState())
