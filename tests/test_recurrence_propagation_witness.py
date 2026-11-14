"""Public recurrence envelopes and SQL fixed before RF3 recurrence extraction."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.canonical_json import canonical_json_bytes
from tests import test_recurrence_commands as commands
from tests.schema19_witness_support import schema19

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf3_recurrence_witness.json"


def collect():
    result = {}
    for scenario in ("add_remove_and_override_create_complete_successor_revisions",
                     "series_edit_whole_replaces_collections_and_records_lineage",
                     "series_edit_this_and_following_splits_and_preserves_count_total",
                     "event_reschedule_can_attach_recurrence_once_and_then_defers_to_series_commands"):
        with patch("spine.ledger.identity.secrets.token_hex", return_value="47" * 32):
            h = commands.RecurrenceCommandTests()
            h.setUp()
            observations = []
            original = commands.handle

            def observe(*args, original=original, observations=observations, h=h, **kwargs):
                response = original(*args, **kwargs)
                encoded = canonical_json_bytes(response)
                observations.append(dict(command=args[0], response_sha256=hashlib.sha256(encoded).hexdigest(),
                    response_bytes=len(encoded), ledger_sha256=hashlib.sha256("\n".join(h.connection.iterdump()).encode()).hexdigest()))
                return response

            try:
                with patch.object(commands, "handle", side_effect=observe):
                    getattr(h, "test_" + scenario)()
                assert not h.connection.execute("PRAGMA foreign_key_check").fetchall()
                assert h.connection.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0] == 0
                result[scenario] = observations
            finally:
                h.tearDown()
    return result


class RecurrencePropagationWitnessTests(unittest.TestCase):
    def test_recurrence_envelopes_and_sql_match_checkpoint(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source_commit"], "a4b3790")
        with schema19():
            self.assertEqual(collect(), fixture["cases"])
