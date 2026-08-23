from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import core as command_core
from spine.commands.temporal_bindings import _encode_cursor
from spine.core.canonical_json import canonical_json_text
from spine.core.hashing import hash_canonical_json
from spine.core.notifications import expand_notification_policy, normalize_notification_policy
from spine.core.occurrences import expand_recurrence_set
from spine.core.recurrence_set import normalize_initial_recurrence_set
from spine.core.temporal_bindings import binding_revision_preimage

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "contracts" / "vector-manifest.json"


class ComputedContractVectorTests(unittest.TestCase):
    def test_manifest_has_one_computed_vector_per_contract_family(self) -> None:
        manifest = _load(MANIFEST)
        self.assertEqual(manifest["manifest_version"], "spine.computed-contract-vectors.v1")
        self.assertEqual(manifest["canonical_json_version"], "spine.canonical-json.v1")
        self.assertEqual(
            {entry["vector_id"] for entry in manifest["vectors"]},
            {
                "recurrence.every_three_days_0800.v1",
                "notification.every_hour_six_hours_before.v1",
                "notification_rendering.event_tomorrow_physical.v1",
                "relative_temporal_binding.selected_occurrence_follow_source.v1",
            },
        )
        for entry in manifest["vectors"]:
            self.assertTrue((ROOT / entry["fixture"]).is_file())

    def test_recurrence_vector_pins_bytes_digests_ids_and_expansion(self) -> None:
        vector = _load(ROOT / "tests/fixtures/recurrence/vectors/every_three_days_0800.json")
        context = vector["normalization_context"]
        normalized = normalize_initial_recurrence_set(
            vector["authoring"],
            source_item_id=context["source_item_id"],
            seed_anchor_id=context["seed_anchor_id"],
            seed_scheduled_fact=context["seed_scheduled_fact"],
            created_item_version=context["created_item_version"],
            source_item_version=context["source_item_version"],
            command_id=context["command_id"],
            require_available_timezone_data=False,
        )
        expected = vector["expected"]
        self.assertEqual(normalized.value["recurrence_set_id"], expected["recurrence_set_id"])
        self.assertEqual(
            normalized.value["normalized_recurrence_set_hash"],
            expected["normalized_recurrence_set_hash"],
        )
        self.assertEqual(normalized.value["recurrence_revision_id"], expected["recurrence_revision_id"])
        self.assertEqual(
            [row["segment_id"] for row in normalized.value["segments"]],
            expected["segment_ids"],
        )
        self.assertEqual([row["rule_id"] for row in normalized.value["rules"]], expected["rule_ids"])
        self.assertEqual([row["rdate_id"] for row in normalized.value["rdates"]], expected["rdate_ids"])
        preimages = vector["canonical_preimage_bytes"]
        self.assertEqual(
            canonical_json_text(normalized.recurrence_set_id_preimage),
            preimages["recurrence_set_id"],
        )
        self.assertEqual(
            canonical_json_text(normalized.normalized_hash_preimage),
            preimages["normalized_recurrence_set_hash"],
        )
        self.assertEqual(
            canonical_json_text(normalized.recurrence_revision_id_preimage),
            preimages["recurrence_revision_id"],
        )
        self.assertEqual(
            [canonical_json_text(value) for value in normalized.segment_id_preimages],
            preimages["segment_ids"],
        )
        self.assertEqual(
            [canonical_json_text(value) for value in normalized.rule_id_preimages],
            preimages["rule_ids"],
        )
        self.assertEqual(
            [canonical_json_text(value) for value in normalized.rdate_id_preimages],
            preimages["rdate_ids"],
        )
        with patch("spine.core.schedule.system_timezone_database_version", return_value="2026a"):
            expanded = expand_recurrence_set(
                normalized.value,
                range_start="2026-08-03T00:00:00",
                range_end="2026-08-15T00:00:00",
            )
        self.assertEqual(
            [row["original_scheduled_fact"] for row in expanded.occurrences],
            expected["scheduled_facts"],
        )
        self.assertEqual(
            [row["timezone_resolution"]["utc_instant"] for row in expanded.occurrences],
            expected["utc_instants"],
        )

    def test_notification_vector_pins_bytes_digests_ids_and_expansion(self) -> None:
        vector = _load(ROOT / "tests/fixtures/notifications/vectors/every_hour_six_hours_before.json")
        context = vector["normalization_context"]
        policy = normalize_notification_policy(
            vector["authoring"],
            item_id=context["item_id"],
            item_version=context["item_version"],
            command_id=context["command_id"],
            created_at_utc=context["created_at_utc"],
            recipient_kind=context["recipient_kind"],
            recipient_id=context["recipient_id"],
            channel=context["channel"],
            delivery_target_id=context["delivery_target_id"],
        )
        expected = vector["expected"]
        for field in (
            "notification_intent_id",
            "normalized_notification_schedule_hash",
            "notification_schedule_id",
            "notification_policy_id",
        ):
            self.assertEqual(policy.value[field], expected[field])
        preimages = vector["canonical_preimage_bytes"]
        self.assertEqual(canonical_json_text(policy.intent_id_preimage), preimages["notification_intent_id"])
        self.assertEqual(
            canonical_json_text(policy.schedule_hash_preimage),
            preimages["normalized_notification_schedule_hash"],
        )
        self.assertEqual(canonical_json_text(policy.schedule_id_preimage), preimages["notification_schedule_id"])
        self.assertEqual(canonical_json_text(policy.policy_id_preimage), preimages["notification_policy_id"])
        expansion = vector["expansion_context"]
        result = expand_notification_policy(
            policy.value,
            targets=expansion["targets"],
            evaluated_at_utc=expansion["evaluated_at_utc"],
            range_start_utc=expansion["range_start_utc"],
            range_end_utc=expansion["range_end_utc"],
            include_diagnostics=True,
            candidate_limit=100,
        )
        self.assertEqual(
            [
                [
                    row["eligible_at_utc"],
                    row["notification_schedule_slot_key"],
                    row["notification_opportunity_id"],
                ]
                for row in result.opportunities
            ],
            expected["opportunities"],
        )
        self.assertEqual(list(result.diagnostics), expected["diagnostics"])

    def test_temporal_binding_vector_pins_revision_hash_ids_and_cursor(self) -> None:
        vector = _load(
            ROOT
            / "tests/fixtures/relative_temporal_bindings/vectors/selected_occurrence_follow_source.json"
        )
        context = vector["normalization_context"]
        preimage = binding_revision_preimage(
            binding=vector["binding"],
            source=vector["source"],
            source_scope=context["source_scope"],
            offset_seconds=int(context["offset_seconds"]),
            target=vector["target"],
            target_item_version=int(context["target_item_version"]),
            resolution_kind=context["resolution_kind"],
        )
        expected = vector["expected"]
        self.assertEqual(canonical_json_text(preimage), vector["canonical_preimage_bytes"])
        self.assertEqual(
            hash_canonical_json(preimage),
            expected["normalized_temporal_binding_revision_hash"],
        )

        command = vector["command_context"]["command"]
        command_id = vector["command_context"]["command_id"]
        paths = {
            "item_id": ("item", "/task"),
            "due_anchor_id": ("due_anchor", "/temporal_binding/resolved_target"),
            "relation_id": ("relation", "/relationship"),
            "temporal_binding_id": ("temporal_binding", "/temporal_binding"),
            "temporal_binding_revision_id": (
                "temporal_binding_revision",
                "/temporal_binding/revisions/0",
            ),
            "audit_id": ("audit", "/audit"),
        }
        for field, (role, path) in paths.items():
            self.assertEqual(
                command_core._derived_id(command, command_id, role, path),
                expected[field],
            )
        self.assertEqual(command_core._receipt_id(command, command_id), expected["command_receipt_id"])
        self.assertEqual(_encode_cursor(vector["cursor_payload"]), expected["cursor"])


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
