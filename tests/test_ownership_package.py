"""Exact packaged local provisioning-v3 resources, without frozen web changes."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib import resources
from pathlib import Path

from spine.core.errors import SpineValidationError
from spine.web.ownership_package import load_from, packaged


class OwnershipPackageTests(unittest.TestCase):
    def test_offline_package_and_sync(self):
        loaded = packaged()
        self.assertEqual(len(loaded.documents), 15)
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "scripts/sync_ownership_bootstrap_contracts.py", "--check"], cwd=root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_missing_or_changed_asset_is_rejected(self):
        directory = resources.files("spine.contracts").joinpath("ownership")
        pins = json.loads(directory.joinpath("pins.v1.json").read_bytes())
        for name in ["pins.v1.json", *pins["files"]]:
            for missing in (True, False):
                with self.subTest(name=name, missing=missing), tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "package"
                    shutil.copytree(str(directory), dest)
                    path = dest / name
                    if missing:
                        path.unlink()
                    else:
                        path.write_bytes(path.read_bytes() + b" ")
                    with self.assertRaisesRegex(SpineValidationError, "environment_failure:runtime_contracts"):
                        load_from(dest)
