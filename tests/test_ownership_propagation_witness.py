"""Fixed-input public owner effects captured from the pre-extraction checkpoint."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.core.canonical_json import canonical_json_bytes
from spine.web.provisioning import apply
from tests import test_people_schedule_integration as people
from tests import test_trusted_web_runtime as web

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf3_owner_witness.json"


def collect():
    evidence = {}

    def capture(name, db, result):
        data = canonical_json_bytes(result)
        evidence[name] = dict(response_sha256=hashlib.sha256(data).hexdigest(), response_bytes=len(data),
            ledger_sha256=hashlib.sha256("\n".join(db.iterdump()).encode()).hexdigest(),
            epoch=db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0] == 0

    with patch("spine.ledger.identity.secrets.token_hex", return_value="31" * 32), patch("spine.web.service._now", return_value=web.AT):
        h = web.TrustedWebRuntimeTests()
        h.setUp()
        try:
            request = h.event()
            capture("configured_create", h.db, h.run_command("schedule.create", request))
            capture("configured_replay", h.db, h.run_command("schedule.create", request))
            item = h.ok(handle("schedule.create", h.event("adopted-event")["request"], h.ctx))["item_id"]
            capture("adoption", h.db, h.provision(item_adoptions=[dict(operation="create", item_id=item,
                expected_item_version="1", owner_scope=dict(owner_kind="subject", owner_subject_id="owner"))]))
            capture("adoption_replay", h.db, apply(h.db, h.last_apply))
        finally:
            h.doCleanups()
        people.PeopleScheduleIntegrationTests.setUpClass()
        h = people.PeopleScheduleIntegrationTests()
        h.setUp()
        try:
            h.group_route()
            request = h.create_body(group=True, people=["owner", "other"], materialize=True)
            capture("people_group_create", h.db, h.run_command("schedule.create", request))
            capture("people_group_replay", h.db, h.run_command("schedule.create", request))
        finally:
            h.doCleanups()
    return evidence


class OwnershipPropagationWitnessTests(unittest.TestCase):
    def test_owner_header_history_epochs_and_wire_bytes_match_checkpoint(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source_commit"], "0135a68")
        self.assertEqual(collect(), fixture["cases"])
