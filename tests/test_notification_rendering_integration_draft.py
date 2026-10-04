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

    def test_fresh_local_details_require_separate_explicit_adoption(self):
        authoring = self.matrix["authoring"]
        self.assertEqual(
            authoring["fresh_trusted_local_create"],
            "ordinary_only_then_explicit_adoption_and_presentation_edit",
        )
        self.assertFalse(authoring["fresh_create_establishes_owner"])
        self.assertEqual(authoring["unadopted_item_detail_selection"], "rendering_disclosure_unavailable")
        self.assertEqual(authoring["detail_setup_steps"], [
            "ordinary_create_materialization_none",
            "explicit_owner_adoption",
            "presentation_only_edit_materialization_none",
            "explicit_bounded_materialization_when_delivery_wanted",
        ])
        self.assertFalse(authoring["detail_setup_atomic_across_steps"])
        self.assertTrue(authoring["detail_setup_failure_preserves_prior_commits"])
        self.assertIn("Fresh trusted-local creation is therefore **ordinary-only**", self.spec)
        self.assertIn("These are separately receipted transactions, not one atomic composite", self.spec)

    def test_old_profile_revision_guard_preserves_history(self):
        rule = self.matrix["authoring"]["legacy_profile_revise"]
        self.assertEqual(rule["current_v1"], "existing_v1_rules")
        self.assertEqual(rule["current_v2"], "reject_including_all_ordinary_and_noop")
        self.assertEqual((rule["error"], rule["field"]), ("unsupported_field", "revision"))
        self.assertEqual(
            rule["order"],
            "compatible_replay_then_existing_reference_and_freshness_checks_then_decoder_guard",
        )
        self.assertEqual(rule["historical_hashes_and_replay"], "unchanged")
        self.assertIn(rule["diagnostic"], self.spec)
        self.assertIn("This includes v2 revisions whose templates are all ordinary", self.spec)

    def test_cursor_status_agrees_with_closed_list_requests(self):
        cursor = self.matrix["cursor"]
        commands = json.loads(
            (ROOT / "contracts/schemas/notification-rendering-definition-commands.schema.json").read_text()
        )["$defs"]
        self.assertTrue(cursor["status_required"])
        self.assertTrue(cursor["invalid_status_precedes_cursor_processing"])
        self.assertFalse(cursor["unfiltered_lists"])
        for command, statuses in cursor["status_domains"].items():
            with self.subTest(command=command):
                self.assertIn("status", commands[command]["required"])
                self.assertEqual(commands[command]["properties"]["status"]["enum"], statuses)
        self.assertIn("there is no unfiltered-list mode or null-status normalization", self.spec)

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
