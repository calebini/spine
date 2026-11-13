"""Fixed public scheduling envelopes and ledger bytes before RF3 item extraction."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.canonical_json import canonical_json_bytes
from tests import test_schedule_operations_command as schedules

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf3_item_policy_witness.json"


def collect():
    result = {}
    schedules.ScheduleOperationsCommandTests.setUpClass()
    for name in (
        "update_replaces_reminder_and_reconciles_then_materializes_atomically",
        "cancel_terminalizes_item_and_cancels_only_never_started_work",
        "update_dry_run_matches_identities_and_persists_nothing",
        "agenda_combines_singleton_and_recurrence_and_invalidates_cursor",
    ):
        with patch("spine.ledger.identity.secrets.token_hex", return_value="63" * 32):
            h = schedules.ScheduleOperationsCommandTests()
            h.setUp()
            observations = []
            original = schedules.handle

            def observe(*args, original=original, h=h, observations=observations, **kwargs):
                value = original(*args, **kwargs)
                encoded = canonical_json_bytes(value)
                observations.append(dict(command=args[0], response_sha256=hashlib.sha256(encoded).hexdigest(),
                    response_bytes=len(encoded), ledger_sha256=hashlib.sha256("\n".join(h.connection.iterdump()).encode()).hexdigest()))
                return value

            try:
                with patch.object(schedules, "handle", side_effect=observe):
                    getattr(h, "test_" + name)()
                result[name] = observations
            finally:
                h.tearDown()
    return result


class ItemPolicyWitnessTests(unittest.TestCase):
    def test_item_policy_envelopes_and_sql_match_checkpoint(self):
        baseline = json.loads(FIXTURE.read_text())
        self.assertEqual(baseline["source_commit"], "5a212a6")
        self.assertEqual(collect(), baseline["cases"])
