"""Exact dependency ratchet and real-caller checks for incremental RF1 extraction."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "tests/fixtures/internal_operations/rf1_dependency_inventory.json"


def command_dependencies(source):
    """Count each named command import/call by lexical caller, never wildcard-allow a module."""
    tree = ast.parse(source)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("spine.commands"):
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module + "." + alias.name
        elif isinstance(node, ast.ImportFrom) and node.module == "spine":
            for alias in node.names:
                if alias.name == "commands":
                    aliases[alias.asname or alias.name] = "spine.commands"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("spine.commands"):
                    aliases[alias.asname or alias.name] = alias.name
    counts = Counter()

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []

        def named(self, kind, target):
            counts["|".join((".".join(self.scope) or "<module>", kind, target))] += 1

        def visit_FunctionDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_ImportFrom(self, node):
            if (node.module or "").startswith("spine.commands"):
                for alias in node.names:
                    self.named("import", node.module + "." + alias.name)
            elif node.module == "spine":
                for alias in node.names:
                    if alias.name == "commands":
                        self.named("import", "spine.commands")

        def visit_Import(self, node):
            for alias in node.names:
                if alias.name.startswith("spine.commands"):
                    self.named("import", alias.name)

        def visit_Call(self, node):
            name = ast.unparse(node.func)
            for alias, target in aliases.items():
                if name == alias or name.startswith(alias + "."):
                    self.named("call", target + name[len(alias):])
            self.generic_visit(node)

    Visitor().visit(tree)
    return dict(sorted(counts.items()))


class InternalOperationBoundaryTests(unittest.TestCase):
    def test_remaining_reverse_dependencies_are_exact_named_exceptions(self):
        inventory = json.loads(INVENTORY.read_text())
        actual = {}
        for path in sorted((ROOT / "src/spine/services").rglob("*.py")):
            edges = command_dependencies(path.read_text())
            if edges:
                actual[str(path.relative_to(ROOT))] = edges
        self.assertEqual(actual, {p: row["remaining"] for p, row in inventory["exceptions"].items()})
        for row in inventory["exceptions"].values():
            self.assertTrue(row["removal_gate"])

    def test_ratchet_detects_new_callers_targets_and_duplicate_calls(self):
        original = "from spine.commands import core as c\ndef a():\n c._schedule_normalize_policies()\n"
        before = command_dependencies(original)
        for added in (
            " c._schedule_normalize_policies()\n",
            " c._schedule_materialize_successor()\n",
            "def b():\n c._schedule_normalize_policies()\n",
            "from spine.commands import handle\n",
            "from spine import commands as commands\ncommands.handle()\n",
        ):
            self.assertNotEqual(before, command_dependencies(original + added))

    def test_recurring_services_have_no_command_imports_or_calls(self):
        for path in sorted((ROOT / "src/spine/services").glob("recurring_task*.py")):
            with self.subTest(path=path.name):
                self.assertEqual(command_dependencies(path.read_text()), {})

    def test_extracted_service_import_does_not_load_commands_or_scheduler(self):
        # A fresh interpreter catches package-level cycles hidden by test import order.
        program = (
            "import sys; from spine.services import schedule_delivery; "
            "assert not any(m.startswith('spine.commands') for m in sys.modules); "
            "assert 'spine.services.scheduling' not in sys.modules"
        )
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extracted_operations_never_dispatch_or_commit(self):
        paths = (
            "core/request_values.py", "core/temporal_bindings.py", "ledger/catalog_reads.py",
            "ledger/item_reads.py", "ledger/provenance.py", "services/schedule_delivery.py",
            "services/schedule_policies.py", "ledger/schedule_work.py",
            "services/schedule_materialization.py", "core/notification_targets.py",
            "core/recurring_task_runtime.py", "ledger/receipts.py", "ledger/recurring_task_catalog.py",
            "core/mutation_effects.py", "ledger/mutation_effects.py", "services/mutation_propagation.py",
            "ledger/owner_mutations.py", "ledger/relations.py", "ledger/recurrence_effects.py",
            "ledger/item_effects.py", "services/item_mutations.py",
        )
        for relative in paths:
            with self.subTest(path=relative):
                source = (ROOT / "src/spine" / relative).read_text()
                self.assertEqual(command_dependencies(source), {})
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.Call):
                        name = ast.unparse(node.func).rsplit(".", 1)[-1]
                        self.assertNotIn(name, {"commit", "rollback", "handle", "exec", "eval"})

    def test_forwarding_aliases_and_scheduler_exports_keep_one_implementation(self):
        from spine import services
        from spine.commands import core, temporal_bindings
        from spine.core import occurrence_details, request_values
        from spine.core import temporal_bindings as facts
        from spine.ledger import catalog_reads, item_reads, provenance, schedule_work
        from spine.services import schedule_materialization, schedule_policies, scheduling

        for name in ("revision_value", "source_from_occurrence", "source_from_prior"):
            self.assertIs(getattr(temporal_bindings, "_" + name), getattr(facts, name))
        self.assertIs(temporal_bindings._persist_provenance, provenance.persist_binding_provenance)
        self.assertIs(core._hydrated_item, item_reads.hydrated_item)
        self.assertIs(core._decorate_occurrence, occurrence_details.decorate_occurrence)
        self.assertIs(core._schedule_object, request_values.object_value)
        self.assertIs(core._delivery_target, catalog_reads.delivery_target)
        self.assertIs(core._schedule_normalize_policies, schedule_policies.normalize_policies)
        self.assertIs(core._schedule_update_normalize_policies, schedule_policies.update_policies)
        self.assertIs(core._schedule_disabled_policy, schedule_policies.disabled_policy)
        self.assertIs(core._schedule_reconcile_work_plan, schedule_work.reconcile_work_plan)
        self.assertIs(core._schedule_materialize_successor, schedule_materialization.materialize_successor)
        self.assertIs(services.materialize_notification_horizon, scheduling.materialize_notification_horizon)
        self.assertIs(services.SchedulingCycleResult, scheduling.SchedulingCycleResult)

    def test_schedule_binding_and_recurring_call_the_shared_route_operation(self):
        from spine.commands import handle
        from spine.services import schedule_delivery
        from tests import test_recurring_task_reconcile as recurring
        from tests import test_relative_temporal_bindings_command as binding
        from tests import test_schedule_create_command as schedule

        ordinary = schedule.ScheduleCreateCommandTests()
        ordinary.setUp()
        self.addCleanup(ordinary.tearDown)
        with patch.object(schedule_delivery, "resolve_delivery", wraps=schedule_delivery.resolve_delivery) as resolve:
            result = handle("schedule.create", ordinary.event_request(), ordinary.context)
            self.assertTrue(result["ok"], result)
            self.assertEqual(resolve.call_count, 1)

        related = binding.RelativeTemporalBindingCommandTests()
        related.setUp()
        self.addCleanup(related.tearDown)
        with patch.object(schedule_delivery, "resolve_delivery", wraps=schedule_delivery.resolve_delivery) as resolve:
            request = related._related_request("follow_source", with_reminder=True)
            result = handle("schedule.related_task.create", request, related.context)
            self.assertTrue(result["ok"], result)
            self.assertEqual(resolve.call_count, 1)

        recurring.RecurringTaskReconcileTests.setUpClass()
        repeated = recurring.RecurringTaskReconcileTests()
        repeated.setUp()
        self.addCleanup(repeated.tearDown)
        with patch.object(schedule_delivery, "resolve_delivery", wraps=schedule_delivery.resolve_delivery) as resolve:
            repeated.test_profile_multiple_tasks_have_distinct_intents_and_real_attribution()
            self.assertGreater(resolve.call_count, 1)
        for db in (ordinary.connection, related.connection, repeated.db):
            self.assertEqual(db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
