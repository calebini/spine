"""Exact installed-resource closure without prematurely declaring public support."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands import recurring_task_package as package
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.errors import SpineValidationError

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = resources.files("spine.contracts").joinpath("recurring_tasks")


class RecurringPackageTests(unittest.TestCase):
    def test_exact_source_parity_complete_offline_and_trusted_local_activation(self):
        loaded = package.packaged()
        closure = json.loads((ROOT / "contracts" / package.CLOSURE).read_bytes())
        self.assertEqual(set(loaded.documents), {e["path"] for e in closure["resources"]})
        for entry in closure["resources"]:
            name = entry["path"].removeprefix("contracts/")
            self.assertEqual(DIRECTORY.joinpath(name).read_bytes(), (ROOT / entry["path"]).read_bytes())
        self.assertEqual(loaded.descriptor, json.loads((ROOT / "contracts" / package.DESCRIPTOR).read_bytes()))
        self.assertTrue(set(loaded.descriptor["required_existing_contract_versions"]) <= IMPLEMENTED_CONTRACT_VERSIONS)
        self.assertTrue(set(loaded.descriptor["commands"]) <= set(COMMAND_RUNTIME_CONTRACT_REGISTRY))
        self.assertEqual(IMPLEMENTED_LEDGER_SCHEMA_VERSION, 20)

    def test_missing_or_changed_each_required_asset_fails_closed(self):
        pins = json.loads(DIRECTORY.joinpath("pins.v1.json").read_bytes())
        for name in ["pins.v1.json", *pins["files"]]:
            for corrupt in (False, True):
                with self.subTest(name=name, corrupt=corrupt), tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "assets"
                    shutil.copytree(str(DIRECTORY), dest)
                    selected = dest / name
                    if corrupt:
                        selected.write_bytes(selected.read_bytes() + b" ")
                    else:
                        selected.unlink()
                    with self.assertRaisesRegex(SpineValidationError, "environment_failure:runtime_contracts"):
                        package.load_from(dest)

    def test_successful_load_does_not_cache_past_resource_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "assets"
            shutil.copytree(str(DIRECTORY), dest)
            with patch.object(package.resources, "files", return_value=Path(tmp)), \
                 patch("socket.create_connection", side_effect=AssertionError("offline resources only")):
                package.load_from(dest)
                (dest / package.CLOSURE).unlink()
                with self.assertRaises(SpineValidationError):
                    package.load_from(dest)

    def test_schema_validation_uses_only_the_pinned_closure(self):
        loaded = package.packaged()
        request = {"contract_version": "spine.recurring-related-tasks.v1", "limit": "10"}
        with patch("socket.create_connection", side_effect=AssertionError("no remote resolution")):
            normalized = loaded.request("schedule.related_task_rule.list", request)
        self.assertEqual(normalized["limit"], "10")

    def test_sync_is_current(self):
        result = subprocess.run([sys.executable, "scripts/sync_recurring_task_contracts.py", "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(hashlib.sha256(DIRECTORY.joinpath("pins.v1.json").read_bytes()).hexdigest(), package.PIN_SHA256)

    def test_missing_exact_existing_runtime_contract_denies_loading(self):
        for version in package.packaged().descriptor["required_existing_contract_versions"]:
            with self.subTest(version=version), \
                 patch("spine.IMPLEMENTED_CONTRACT_VERSIONS", IMPLEMENTED_CONTRACT_VERSIONS - {version}), \
                 self.assertRaisesRegex(SpineValidationError, "environment_failure:runtime_contracts"):
                package.packaged()
