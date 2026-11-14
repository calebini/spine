"""Relation responses and SQL captured from the pre-extraction checkpoint."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core.canonical_json import canonical_json_bytes
from tests import test_binding_successor_materialization as bindings
from tests import test_ledger_supporting_sets as ledger
from tests.schema19_witness_support import schema19

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf3_relation_witness.json"


def collect():
    evidence = {}

    def capture(name, db, result):
        assert result["ok"], result
        encoded = canonical_json_bytes(result)
        evidence[name] = dict(response_sha256=hashlib.sha256(encoded).hexdigest(), response_bytes=len(encoded),
            ledger_sha256=hashlib.sha256("\n".join(db.iterdump()).encode()).hexdigest())
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0] == 0

    with patch("spine.ledger.identity.secrets.token_hex", return_value="43" * 32):
        h = ledger.LedgerSupportingSetTests()
        h.setUp()
        try:
            ledger.create_task_pair(h.connection)
            ctx = CommandContext(ledger=h.connection)
            request = dict(command_id="relation-witness", actor_subject_id=ledger.SUBJECT_ID,
                source_item_id="task-dependent", source_target_version="1", target_item_id="task-prerequisite",
                target_target_version="1", relation_type="depends_on", created_at_utc=ledger.NOW)
            capture("direct", h.connection, handle("relation.create", request, ctx))
            capture("direct_replay", h.connection, handle("relation.create", request, ctx))
        finally:
            h.tearDown()
        h = bindings.BindingSuccessorMaterializationTests()
        h.setUp()
        try:
            related = h.create(materialize=True)
            capture("related", h.db, related)
            capture("related_replay", h.db, h.create(materialize=True))
            request = dict(command_id="bound-relation-witness", actor_subject_id="owner",
                source_item_id=related["task"]["item_id"], source_target_version="1", target_item_id=h.h.event["item_id"],
                target_target_version="1", relation_type="depends_on", created_at_utc="2026-08-17T12:00:00Z")
            capture("bound_direct", h.db, handle("relation.create", request, h.context))
            capture("bound_direct_replay", h.db, handle("relation.create", request, h.context))
        finally:
            h.doCleanups()
    return evidence


class RelationPropagationWitnessTests(unittest.TestCase):
    def test_responses_audits_catalog_and_sql_match_checkpoint(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source_commit"], "a4b3790")
        with schema19():
            self.assertEqual(collect(), fixture["cases"])
