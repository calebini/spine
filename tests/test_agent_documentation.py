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
DEPLOYMENT_RUNBOOK = ROOT / "docs" / "OPENCLAW_DEPLOYMENT_RUNBOOK.md"
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

    def test_all_operational_bash_examples_parse(self) -> None:
        for path in (QUICKSTART, OPERATOR_GUIDE, DEPLOYMENT_RUNBOOK):
            document = path.read_text(encoding="utf-8")
            examples = re.findall(r"```bash\n(.*?)\n```", document, flags=re.DOTALL)
            self.assertTrue(examples, path)
            for index, example in enumerate(examples, start=1):
                with self.subTest(path=path.name, example=index):
                    subprocess.run(["bash", "-n"], input=example, text=True, check=True)

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
        for document in (quickstart, guide):
            self.assertIn('"timezone_database_version":{"kind":"system_current"}', document)
            self.assertIn("concrete", document)
            self.assertIn("omission", document.lower())

    def test_operator_schedule_verification_uses_public_schema_7_surface(self) -> None:
        guide = OPERATOR_GUIDE.read_text(encoding="utf-8")
        self.assertIn("schedule show", guide)
        self.assertIn("lifecycle.delivery.attempt_state", guide)
        self.assertIn("notification_policies.policy_id", guide)
        self.assertIn("work_instances.notification_policy_id", guide)
        self.assertNotIn("FROM items", guide)
        self.assertNotIn("JOIN items", guide)

    def test_operational_docs_use_host_neutral_checkout_local_entrypoints(self) -> None:
        documents = [
            path.read_text(encoding="utf-8")
            for path in (QUICKSTART, OPERATOR_GUIDE, DEPLOYMENT_RUNBOOK)
        ]
        for document in documents:
            self.assertIn("SPINE_CHECKOUT", document)
            self.assertIn('.venv/bin/spine-ledger-migrate', document)
            self.assertNotIn("/home/agent/", document)
            self.assertNotIn("cortext1", document.lower())
            self.assertNotRegex(document, r"(?m)^spine --db ")
            self.assertNotRegex(document, r"(?m)^spine-ledger-migrate ")
            self.assertNotRegex(document, r'PYTHONPATH="\$TICKERD_SRC" spine-worker')
        for document in documents[:2]:
            self.assertIn('.venv/bin/spine-command', document)
        for document in documents[1:]:
            self.assertIn("EXPECTED_SPINE_REVISION", document)
        self.assertNotIn("schema version 5", documents[2].lower())
        self.assertNotIn("pre-v5", documents[2].lower())

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
            "schedule.build",
            "schedule.show",
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
