"""Draft integration matrix consistency, not runtime or stateful conformance."""

import json
import unittest
from pathlib import Path

from spine import IMPLEMENTED_CONTRACT_VERSIONS

ROOT = Path(__file__).resolve().parents[1]


class RenderingIntegrationDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(
            (ROOT / "contracts/notification-rendering-integration.v1.json").read_text()
        )
        cls.spec = (ROOT / cls.matrix["normative_source"]).read_text()

    def test_draft_has_no_runtime_or_packaged_activation(self):
        self.assertEqual(self.matrix["status"], "draft_specification_only")
        self.assertFalse(self.matrix["runtime_activation"])
        self.assertFalse(self.matrix["verification"]["runtime_verified"])
        versions = {self.matrix["contract_version"], *self.matrix["proposed_successors"].values()}
        self.assertFalse(versions & IMPLEMENTED_CONTRACT_VERSIONS)
        self.assertFalse(
            (ROOT / "src/spine/contracts/web/notification-rendering-integration.v1.json").exists()
        )

    def test_all_existing_gates_have_an_explicit_status(self):
        registry = json.loads(
            (ROOT / "contracts/notification-rendering-definition-contract-registry.v1.json").read_text()
        )
        self.assertEqual(set(registry["implementation_gates"]), set(self.matrix["gate_status"]))
        for field in ("normative_source", "logical_owner", "storage_owner"):
            self.assertTrue((ROOT / self.matrix[field]).is_file())
        for version in self.matrix["proposed_successors"].values():
            self.assertIn(version, self.spec)

    def test_delivery_identity_and_historical_evidence_are_preserved(self):
        work = self.matrix["work"]
        self.assertFalse(work["intent_is_policy_identity"])
        self.assertFalse(work["presentation_in_delivery_preimages"])
        self.assertFalse(work["presentation_only_materialize"])
        self.assertFalse(work["presentation_only_retry"])
        self.assertEqual(work["states"]["started"], "preserve_body_and_attempt")
        self.assertFalse(self.matrix["persistence"]["historical_attempt_rewrite"])
        self.assertEqual(self.matrix["persistence"]["extended_tables"], ["notification_renderings"])

    def test_all_obligations_are_in_the_spec_not_claimed_as_executed(self):
        families = self.matrix["verification"]["required_families"]
        self.assertEqual(set(families), {f"RI-{n:02}" for n in range(1, 15)})
        for family in families:
            self.assertIn(f"| {family} |", self.spec)
        for table in self.matrix["persistence"]["new_tables"]:
            self.assertIn(table, self.spec)
        self.assertIn("complete_successor_wire_schemas", self.matrix["verification"]["pending_before_runtime"])


if __name__ == "__main__":
    unittest.main()
