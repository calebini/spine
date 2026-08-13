from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
QUICKSTART = ROOT / "docs" / "AGENT_QUICKSTART.md"
OPERATOR_GUIDE = ROOT / "docs" / "AGENT_OPERATOR_GUIDE.md"
EXAMPLE = ROOT / "examples" / "agent-first-success.sh"


class AgentDocumentationTests(unittest.TestCase):
    def test_all_fenced_json_examples_parse(self) -> None:
        for path in (QUICKSTART, OPERATOR_GUIDE):
            document = path.read_text(encoding="utf-8")
            examples = re.findall(r"```json\n(.*?)\n```", document, flags=re.DOTALL)
            self.assertTrue(examples, path)
            for index, example in enumerate(examples, start=1):
                with self.subTest(path=path.name, example=index):
                    json.loads(example)

    def test_first_success_example_is_executable_fake_only_shell(self) -> None:
        self.assertTrue(os.access(EXAMPLE, os.X_OK))
        subprocess.run(["bash", "-n", str(EXAMPLE)], check=True)
        source = EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("--mode observe_only", source)
        self.assertIn("--mode active", source)
        self.assertIn("--openclaw-sender fake", source)
        self.assertNotIn("--openclaw-sender gateway", source)
        self.assertNotIn("--allow-real-send", source)
        self.assertLess(source.index("occurrence_provenance regenerate"), source.index("notification opportunities"))
        self.assertLess(source.index("notification opportunities"), source.index("notification_work materialize"))

    def test_docs_discover_timezone_version_and_do_not_pin_one_host(self) -> None:
        quickstart = QUICKSTART.read_text(encoding="utf-8")
        guide = OPERATOR_GUIDE.read_text(encoding="utf-8")
        for document in (quickstart, guide):
            self.assertIn("system info", document)
            self.assertIn("timezone_database_version", document)
            self.assertNotIn('"timezone_database_version": "2026a"', document)
        self.assertIn("<SPINE_TZ_VERSION>", guide)

    def test_quickstart_covers_entry_paths_and_scheduling_command_family(self) -> None:
        document = QUICKSTART.read_text(encoding="utf-8")
        for heading in (
            "### New disposable ledger",
            "### Existing current ledger",
            "### Existing older ledger that requires migration",
        ):
            self.assertIn(heading, document)
        for command in (
            "system.info",
            "schedule.create",
            "event.create",
            "task.create",
            "item.occurrences",
            "recurrence.instance.add",
            "recurrence.instance.remove",
            "recurrence.instance.override",
            "recurrence.series.edit",
            "occurrence_provenance.regenerate",
            "reminder.create",
            "reminder.edit",
            "reminder.disable",
            "notification.opportunities",
            "notification_work.materialize",
        ):
            self.assertIn(f"`{command}`", document)


if __name__ == "__main__":
    unittest.main()
