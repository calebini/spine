"""The release inventory must name actual tests, not source-only fixture labels."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.recurring_task_release_obligations import resolved_obligations


class ReleaseEvidenceTests(unittest.TestCase):
    def test_all_eighteen_obligations_have_unique_executable_witnesses(self):
        rows = resolved_obligations()
        self.assertEqual(set(rows), {f"RRT-{i:02}" for i in range(1, 19)})
        root = Path(__file__).resolve().parents[1]
        recorded = json.loads((root / "docs/design-notes/recurring-related-task-r4-runtime-evidence.json").read_text())
        self.assertTrue(recorded["ok"])
        self.assertEqual(recorded["skipped"], 0)
        self.assertEqual(recorded["tests_run"], len({test.id() for tests in rows.values() for test in tests}))
        self.assertEqual(set(recorded["obligations"]), set(rows))
        for key, tests in rows.items():
            with self.subTest(obligation=key):
                ids = [test.id() for test in tests]
                self.assertGreaterEqual(len(ids), 4)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all("_FailedTest" not in identity for identity in ids))
                self.assertEqual(recorded["obligations"][key], {"status": "pass", "tests": ids})

    def test_missing_witness_cannot_be_treated_as_release_evidence(self):
        with patch("tests.recurring_task_release_obligations.OBLIGATIONS", {"RRT-01": ["storage:test_does_not_exist"]}), \
                self.assertRaisesRegex(ValueError, "expected exactly one executable witness"):
            resolved_obligations()
