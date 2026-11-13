"""Recurrence propagation preserves aggregate, lineage and caller-owned consequences."""

import ast
import copy
import re
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import ChangeCategory
from spine.core.recurrence_mutations import build_successor_recurrence_revision, derive_recurrence_lineage
from spine.ledger import recurrence
from spine.ledger.mutation_state import TransactionMutationState
from spine.services import mutation_propagation
from tests import test_recurrence_commands as helpers
from tests import test_schedule_operations_command as schedules


def dump(db):
    return "\n".join(db.iterdump())


class RecurrencePropagationTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers.RecurrenceCommandTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db, self.ctx = self.h.connection, self.h.context

    def event_request(self, recurring=True):
        request = dict(command_id="effect-event", actor_subject_id="owner", created_at_utc="2026-08-07T17:01:00Z",
            title="Class", all_day=False, start_anchor=dict(anchor_kind="instant_utc", utc_instant="2026-08-08T18:00:00Z"))
        if recurring:
            request["start_anchor"]["recurrence_set"] = dict(time_basis="instant_utc", rules=[dict(frequency="DAILY",
                seed="2026-08-08T18:00:00Z", start_bound="2026-08-08T18:00:00Z", end_condition=dict(kind="count", count="3"))])
        return request

    def created(self):
        event = handle("event.create", self.event_request(), self.ctx)
        self.assertTrue(event["ok"], event)
        return event, recurrence.load_current_recurrence_set(self.db, item_id=event["item_id"])

    def add(self, event, current):
        return dict(command_id="effect-add", actor_subject_id="owner", item_id=event["item_id"], target_version="1",
            recurrence_set_id=current["recurrence_set_id"], recurrence_revision_id=current["recurrence_revision_id"],
            added_at_utc="2026-08-07T18:00:00Z", scheduled_fact="2026-08-20T18:00:00Z", reason_code="extra")

    def omit(self):
        original = mutation_propagation.propagate
        return patch.object(mutation_propagation, "propagate",
            side_effect=lambda *a, **kw: None if "recurrence_revision_id" in kw else original(*a, **kw))

    def assert_omission(self, command, request, context=None):
        context = context or self.ctx
        before = dump(context.ledger)
        with self.omit():
            result = handle(command, request, context)
        self.assertFalse(result["ok"], result)
        self.assertEqual(dump(context.ledger), before)
        self.assertEqual(context.ledger.mutation_state, TransactionMutationState())

    def test_exact_revision_lineage_and_prospective_pointer_then_replay(self):
        captured = []
        original = mutation_propagation.propagate

        def observe(db, **kwargs):
            result = original(db, **kwargs)
            if result.recurrences:
                effect = result.recurrences[0]
                version = db.execute("SELECT current_version FROM coordination_items WHERE item_id=?",
                                     (effect.after.source_item_id,)).fetchone()[0]
                captured.append((effect, version))
            return result

        with patch.object(mutation_propagation, "propagate", side_effect=observe):
            event, current = self.created()
            request = self.add(event, current)
            changed = handle("recurrence.instance.add", request, self.ctx)
        self.assertTrue(changed["ok"], changed)
        self.assertEqual(len(captured), 2)
        initial, _ = captured[0]
        successor, pointer = captured[1]
        self.assertIsNone(initial.before)
        self.assertEqual(successor.before, initial.after)
        self.assertEqual(successor.after.source_item_version, 2)
        self.assertEqual(pointer, 1)  # Extension runs before the owning item CAS.
        self.assertEqual(successor.categories, {ChangeCategory.RECURRENCE})
        self.assertTrue(successor.lineage)
        self.assertEqual({line.lineage_id for line in successor.lineage}, set(changed["lineage_ids"]))
        frozen = dump(self.db)
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("no replay writes")):
            self.assertTrue(handle("event.create", self.event_request(), self.ctx)["ok"])
            # Exact baseline a4b3790 rejects this legacy direct-mutation replay.
            # Record the defect, but do not silently change its public semantics
            # as part of a preservation-only internal refactor.
            replay = handle("recurrence.instance.add", request, self.ctx)
            self.assertEqual(replay["error"], dict(code="semantic_conflict", field="command_id",
                message="command_id replay facts do not match"))
        self.assertEqual(dump(self.db), frozen)

    def test_omission_aborts_initial_attachment_instance_and_series_composers(self):
        self.assert_omission("event.create", self.event_request())
        singleton = handle("event.create", self.event_request(False), self.ctx)
        self.assertTrue(singleton["ok"], singleton)
        attach = dict(command_id="effect-attach", actor_subject_id="owner", item_id=singleton["item_id"], target_version="1",
            rescheduled_at_utc="2026-08-07T18:00:00Z", all_day=False, start_anchor=self.event_request()["start_anchor"])
        self.assert_omission("event.reschedule", attach)
        request = self.event_request() | {"command_id": "second-event"}
        event = handle("event.create", request, self.ctx)
        self.assertTrue(event["ok"], event)
        current = recurrence.load_current_recurrence_set(self.db, item_id=event["item_id"])
        self.assert_omission("recurrence.instance.add", self.add(event, current))
        rule = copy.deepcopy(current["rules"][0])
        rule.pop("rule_id")
        rule.pop("status")
        rule["interval"] = "2"
        self.assert_omission("recurrence.series.edit", dict(command_id="effect-edit", actor_subject_id="owner",
            item_id=event["item_id"], target_version="1", recurrence_set_id=current["recurrence_set_id"],
            recurrence_revision_id=current["recurrence_revision_id"], edited_at_utc="2026-08-07T18:00:00Z",
            edit_scope="whole_series", recurrence_patch=dict(rules=[rule])))

    def test_omission_aborts_schedule_create_and_replacement(self):
        h = schedules.ScheduleOperationsCommandTests()
        h.setUp()
        self.addCleanup(h.tearDown)
        self.assert_omission("schedule.create", h.task_request("effect-schedule"), h.context)
        event = handle("schedule.create", h.task_request("effect-schedule"), h.context)
        self.assertTrue(event["ok"], event)
        replacement = h.task_request("unused")["scheduled_time"]["recurrence"]
        replacement["mode"] = "replace"
        replacement["rules"][0]["interval"] = "2"
        self.assert_omission("schedule.update", dict(contract_version="spine.schedule-update.v2", command_id="effect-update",
            actor_subject_id="owner", item_id=event["item_id"], target_version="1", updated_at_utc="2026-08-13T13:00:00Z",
            patch=dict(recurrence=replacement), materialization=dict(mode="none")), h.context)

    def test_noop_duplicate_add_does_not_propagate(self):
        event, current = self.created()
        request = self.add(event, current) | {"scheduled_fact": "2026-08-08T18:00:00Z"}
        with patch.object(mutation_propagation, "propagate", side_effect=AssertionError("noop must not propagate")):
            result = handle("recurrence.instance.add", request, self.ctx)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["changed"])

    def test_missing_lineage_and_missing_or_changed_children_abort(self):
        event, current = self.created()
        original = mutation_propagation.propagate
        for mode in ("lineage", "rule", "selector", "capture"):
            before = dump(self.db)

            def damaged(db, mode=mode, **kwargs):
                revision = kwargs["recurrence_revision_id"]
                effect = db.mutation_state.propagation.recurrences[revision]
                if mode == "lineage":
                    db.execute("DELETE FROM recurrence_lineage WHERE lineage_id=?", (effect.lineage[0].lineage_id,))
                elif mode == "rule":
                    db.execute("UPDATE recurrence_rules SET interval_value=9 WHERE recurrence_revision_id=?", (revision,))
                elif mode == "selector":
                    rule = db.execute("SELECT rule_id FROM recurrence_rules WHERE recurrence_revision_id=?", (revision,)).fetchone()[0]
                    db.execute("INSERT INTO recurrence_rule_selectors VALUES(?,'by_month',0,'12')", (rule,))
                else:
                    db.mutation_state.propagation.recurrences[revision] = replace(effect, definition_bytes=b"wrong")
                return original(db, **kwargs)

            with self.subTest(mode=mode), patch.object(mutation_propagation, "propagate", side_effect=damaged):
                result = handle("recurrence.instance.add", self.add(event, current), self.ctx)
            self.assertFalse(result["ok"], result)
            self.assertEqual(dump(self.db), before)

    def test_native_missing_duplicate_and_nested_rollback(self):
        event, current = self.created()
        successor = build_successor_recurrence_revision(current, source_item_version="2", command_id="native")
        lines = derive_recurrence_lineage(current, successor.value, command_id="native", effect="series_edit_whole_applied")
        revision = str(successor.value["recurrence_revision_id"])

        def write():
            recurrence.insert_initial_recurrence_set(self.db, normalized=successor, command_id="native",
                                                     created_at_utc="2026-08-07T18:00:00Z")
            recurrence.insert_recurrence_lineage(self.db, lineage=lines)

        before = dump(self.db)
        for mode in ("omitted", "duplicate", "lineage"):
            with self.subTest(mode=mode), self.assertRaises(SpineValidationError), self.db.atomic_command():
                write()
                if mode == "duplicate":
                    mutation_propagation.propagate(self.db, recurrence_revision_id=revision)
                    mutation_propagation.propagate(self.db, recurrence_revision_id=revision)
                elif mode == "lineage":
                    pending = self.db.mutation_state.propagation.recurrences
                    pending[revision] = replace(pending[revision], lineage=())
                    mutation_propagation.propagate(self.db, recurrence_revision_id=revision)
            self.assertEqual(dump(self.db), before)
        with self.db.atomic_command():
            for acknowledged in (False, True):
                with self.assertRaisesRegex(RuntimeError, "trial"), self.db.command_unit():
                    write()
                    if acknowledged:
                        mutation_propagation.propagate(self.db, recurrence_revision_id=revision)
                    raise RuntimeError("trial")
                self.assertEqual(self.db.mutation_state.propagation.recurrences, {})
                self.assertIsNone(recurrence.load_recurrence_revision(self.db, revision_id=revision))
            write()
            mutation_propagation.propagate(self.db, recurrence_revision_id=revision)
        self.assertEqual(self.db.mutation_state, TransactionMutationState())

    def test_closed_native_and_composer_inventory(self):
        root = Path(__file__).parents[1] / "src/spine"
        writers, calls = {}, {}
        tables = r"recurrence_(?:sets|revisions|segments|rules|rule_selectors|rdates|exdates|overrides|lineage)"
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                relative = str(path.relative_to(root))
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    pattern = r"\b(?:INSERT(?: OR IGNORE)? INTO|UPDATE|DELETE FROM)\s+(" + tables + r")\b"
                    for match in re.finditer(pattern, node.value, re.I):
                        key = (relative, match[1])
                        writers[key] = writers.get(key, 0) + 1
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func).rsplit(".", 1)[-1]
                    if name in {"insert_initial_recurrence_set", "insert_recurrence_lineage"}:
                        key = (relative, name)
                        calls[key] = calls.get(key, 0) + 1
        self.assertEqual(writers, {("ledger/recurrence.py", "recurrence_" + name): 1 for name in
            ("sets", "revisions", "segments", "rules", "rule_selectors", "rdates", "exdates", "overrides", "lineage")})
        self.assertEqual(calls, {("commands/core.py", "insert_initial_recurrence_set"): 6,
                                 ("commands/core.py", "insert_recurrence_lineage"): 3})
