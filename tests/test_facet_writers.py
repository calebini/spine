"""Closed allocation inventory + real command regression scenarios with stored facets."""

import ast
import importlib
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.ledger import facets
from spine.ledger.transactions import REGISTERED_VERSION_PRODUCERS
from tests.facet_storage_support import seeded_snapshot

ROOT = Path(__file__).parents[1]
INVENTORY = json.loads((ROOT / "src/spine/ledger/facet_writer_inventory.v1.json").read_text())
CASES = [
    ("test_agent_command_contract_mvp", "AgentCommandContractMvpTests", "test_event_and_task_create_show_list_update_and_replay"),
    ("test_agent_command_contract_mvp", "AgentCommandContractMvpTests", "test_event_reschedule_and_lifecycle_archive_immutability"),
    ("test_agent_command_contract_mvp", "AgentCommandContractMvpTests", "test_task_complete_cancel_duplicate_and_dry_run_no_persistence"),
    ("test_notification_commands", "NotificationCommandTests", "test_create_structured_notification_persists_intent_without_work"),
    ("test_recurrence_commands", "RecurrenceCommandTests", "test_add_remove_and_override_create_complete_successor_revisions"),
    ("test_recurrence_commands", "RecurrenceCommandTests", "test_series_edit_whole_replaces_collections_and_records_lineage"),
    ("test_recurrence_commands", "RecurrenceCommandTests", "test_series_edit_this_and_following_splits_and_preserves_count_total"),
    (
        "test_schedule_operations_command",
        "ScheduleOperationsCommandTests",
        "test_cancel_terminalizes_item_and_cancels_only_never_started_work",
    ),
    (
        "test_schedule_operations_command",
        "ScheduleOperationsCommandTests",
        "test_update_replaces_reminder_and_reconciles_then_materializes_atomically",
    ),
    (
        "test_relative_temporal_bindings_command",
        "RelativeTemporalBindingCommandTests",
        "test_follow_source_blocks_delivery_then_reconciles_target",
    ),
    (
        "test_relative_temporal_bindings_command",
        "RelativeTemporalBindingCommandTests",
        "test_cancel_source_behavior_is_reconciled_by_scheduler",
    ),
    ("test_ledger_item_workflows", "LedgerItemWorkflowTests", "test_create_event_from_draft_with_instant_utc_start"),
    ("test_ledger_item_workflows", "LedgerItemWorkflowTests", "test_create_task_v1_with_no_due_anchor"),
    ("test_ledger_item_workflows", "LedgerItemWorkflowTests", "test_task_cancellation_creates_v2"),
]


class FacetWriterTests(unittest.TestCase):
    def test_inventory_matches_all_production_allocation_callsites(self):
        names = {
            "create_next_item_version",
            "create_item_version_from_draft",
            "_insert_item_version",
            "create_event_v1",
            "create_task_v1",
            "create_event_from_draft",
            "create_task_from_draft",
            "_create_item_v1",
            "cancel_event",
            "cancel_task",
            "complete_task",
        }
        actual = {}
        inserts = []
        for path in (ROOT / "src/spine").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for f in ast.walk(tree):
                if isinstance(f, ast.FunctionDef):
                    calls = sorted(
                        name
                        for n in ast.walk(f)
                        if isinstance(n, ast.Call)
                        for name in [getattr(n.func, "id", getattr(n.func, "attr", None))]
                        if name in names
                    )
                    if calls:
                        actual[f"{path.relative_to(ROOT)}:{f.name}"] = calls
                if (
                    isinstance(f, ast.Constant)
                    and isinstance(f.value, str)
                    and re.search(r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+coordination_item_versions\b", f.value, re.I)
                ):
                    inserts.append(str(path.relative_to(ROOT)))
        self.assertEqual(actual, {e["producer_key"]: e["allocation_calls"] for e in INVENTORY["producers"]})
        self.assertEqual(inserts, ["src/spine/ledger/items.py"])
        self.assertEqual(INVENTORY["ledger_schema_version"], str(IMPLEMENTED_LEDGER_SCHEMA_VERSION))
        self.assertEqual(set(INVENTORY["registered_allocators"]), REGISTERED_VERSION_PRODUCERS)

    def test_all_producers_preserve_empty_and_eight_entry_snapshots(self):
        # Explicit facet replacement is covered separately: it intentionally changes
        # one entry rather than retaining the entire original snapshot.
        expected = {e["producer_key"] for e in INVENTORY["producers"]} - {"src/spine/commands/facets.py:item_write"}
        code_keys = {(str(ROOT / key.split(":")[0]), key.split(":")[1]): key for key in expected}
        for seeded in (False, True):
            visited = set()

            def trace(frame, event, arg, visited=visited):
                if event == "call":
                    key = code_keys.get((frame.f_code.co_filename, frame.f_code.co_name))
                    if key:
                        visited.add(key)

            for module, cls, method in CASES:
                with self.subTest(seeded=seeded, case=method):
                    case = getattr(importlib.import_module(f"tests.{module}"), cls)(method)
                    try:
                        type(case).setUpClass()
                        with patch("spine.ledger.items.insert_snapshot", seeded_snapshot if seeded else facets.insert_snapshot):
                            case.setUp()
                        sys.setprofile(trace)
                        with patch("spine.ledger.items.insert_snapshot", seeded_snapshot if seeded else facets.insert_snapshot):
                            getattr(case, method)()
                        db = case.connection
                        versions = db.execute("SELECT item_id,version FROM coordination_item_versions ORDER BY item_id,version").fetchall()
                        originals = {}
                        for item, version in versions:
                            snapshot = facets.load_snapshot(db, item, version)
                            self.assertEqual(len(snapshot), 8 if seeded else 0)
                            if item in originals:
                                self.assertEqual(snapshot, originals[item])
                            originals[item] = snapshot
                        facets.verify_all(db)
                    finally:
                        sys.setprofile(None)
                        case.tearDown()
            self.assertEqual(visited, expected, "Every inventoried production path must execute against real SQLite")
