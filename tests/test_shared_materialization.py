"""Caller-owned successor materialization: no dispatch, commit, or duplicate work."""

import unittest
from unittest.mock import Mock

from spine.ledger.notifications import load_notification_policies_at_version
from spine.services.schedule_materialization import materialize_successor
from tests import test_binding_successor_materialization as helpers


class SharedMaterializationTests(unittest.TestCase):
    def test_none_mode_does_not_read_or_write(self):
        db = Mock()
        result = materialize_successor(
            db, item_id="unused", item_version=1, recurrence=None, policies=[],
            policy_key_by_intent={}, materialization={"mode": "none"}, command_id="outer", created_at="unused",
        )
        self.assertEqual(result, ([], [], 0))
        self.assertEqual(db.mock_calls, [])

    def test_materialization_is_idempotent_and_rolls_back_with_its_caller(self):
        h = helpers.BindingSuccessorMaterializationTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        created = h.create(materialize=False)
        item_id = created["task"]["item_id"]
        policies = load_notification_policies_at_version(h.db, item_id=item_id, item_version=1)
        arguments = {
            "item_id": item_id, "item_version": 1, "recurrence": None, "policies": policies,
            "policy_key_by_intent": {p["notification_intent_id"]: "task_notice" for p in policies},
            "materialization": {
                "mode": "bounded", "evaluated_at_utc": "2026-08-17T12:00:00Z",
                "range_start_utc": "2026-08-22T00:00:00Z", "range_end_utc": "2026-08-23T00:00:00Z", "limit": "10",
            },
            "command_id": "outer", "created_at": "2026-08-17T12:00:00Z",
        }
        before = h.dump()
        with self.assertRaisesRegex(RuntimeError, "outer failure"), h.db.atomic_command(write=True):
            first = materialize_successor(h.db, **arguments)
            self.assertEqual(len(first[0]), 1)
            self.assertEqual(first[2], 1)
            self.assertEqual(first[1][0]["eligible_at_utc"], "2026-08-22T12:30:00Z")
            self.assertEqual(materialize_successor(h.db, **arguments), ([], [], 1))
            raise RuntimeError("outer failure")
        self.assertEqual(h.dump(), before)
        with h.db.atomic_command(write=True):
            self.assertEqual(materialize_successor(h.db, **arguments), first)
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
