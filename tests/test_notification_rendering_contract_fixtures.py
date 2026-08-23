from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core.canonical_json import canonical_json_text
from spine.core.notification_rendering import render_notification

ROOT = Path(__file__).parents[1]


class NotificationRenderingContractFixtureTests(unittest.TestCase):
    def test_manifest_declares_the_computed_rendering_vector(self) -> None:
        manifest = self._load(ROOT / "contracts/notification-rendering-fixture-manifest.json")
        self.assertEqual(manifest["schema_version"], "spine.notification-rendering-fixtures.v1")
        self.assertEqual(
            [entry["fixture_id"] for entry in manifest["fixtures"]],
            [
                "notification_rendering.event_tomorrow_physical.v1",
                "notification_rendering.closed_failures.v1",
            ],
        )
        for entry in manifest["fixtures"]:
            self.assertTrue((ROOT / entry["fixture"]).is_file())

    def test_failure_oracles_cover_the_closed_error_enum(self) -> None:
        fixture = self._load(ROOT / "tests/fixtures/notification_rendering/failures/closed_failure_oracles.json")
        self.assertEqual(
            {entry["error_code"] for entry in fixture["failures"]},
            {
                "notification_rendering_unsupported_work",
                "notification_rendering_source_unresolved",
                "notification_rendering_timezone_database_unavailable",
                "notification_rendering_invalid_text",
                "notification_rendering_output_too_large",
                "notification_rendering_persistence_conflict",
            },
        )
        self.assertTrue(all(entry["external_contact"] is False for entry in fixture["failures"]))
        self.assertTrue(all(entry["attempt_persisted"] is False for entry in fixture["failures"]))

    def test_vector_pins_exact_body_hashes_identity_and_preimage_bytes(self) -> None:
        vector = self._load(ROOT / "tests/fixtures/notification_rendering/vectors/event_tomorrow_physical.json")
        with patch(
            "spine.core.notification_rendering.system_timezone_database_version",
            return_value="2026a",
        ):
            rendered = render_notification(vector["source_input"])
        expected = vector["expected"]
        for field in (
            "notification_rendering_id",
            "rendering_input_hash",
            "rendered_content_hash",
            "body_text",
            "phrase_kind",
            "phrase_facts",
        ):
            self.assertEqual(getattr(rendered, field), expected[field])
        self.assertEqual(canonical_json_text(rendered.input_hash_preimage), expected["canonical_preimage_bytes"]["rendering_input_hash"])
        self.assertEqual(canonical_json_text(rendered.content_hash_preimage), expected["canonical_preimage_bytes"]["rendered_content_hash"])
        self.assertEqual(canonical_json_text(rendered.id_preimage), expected["canonical_preimage_bytes"]["notification_rendering_id"])

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
