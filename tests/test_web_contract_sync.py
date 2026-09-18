"""The offline package tracks current assets without activating deferred reads."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync_web_contracts.py"


class WebContractSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.script = self.root / "scripts/sync_web_contracts.py"
        self.script.parent.mkdir()
        shutil.copyfile(SCRIPT, self.script)
        self.source = self.root / "contracts"
        self.target = self.root / "src/spine/contracts/web"
        (self.source / "schemas").mkdir(parents=True)
        # Include a future schema to ensure the deferred-family exception does
        # not turn synchronization into a frozen inventory of today's files.
        self.current = (
            "trusted-web-schema-pins.v1.json",
            "spine.trusted-web-command-registry.v1.json",
            "schemas/archetype-facet-types.schema.json",
            "schemas/future-current.schema.json",
        )
        self.deferred = (
            "trusted-web-read-cursor.v2.json",
            "trusted-web-read-projection.v1.json",
            "spine.trusted-web-read-registry.v1.json",
            "schemas/trusted-web-read-types.schema.json",
        )
        for name in (*self.current, *self.deferred):
            (self.source / name).write_text('{"fixture": "' + name + '"}\n')

    def run_sync(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True, text=True, check=False)

    def test_repository_package_is_synchronized(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generation_preserves_deferred_activation_boundary(self) -> None:
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({str(path.relative_to(self.target)) for path in self.target.rglob("*.json")}, set(self.current))
        for name in self.current:
            self.assertEqual((self.target / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(self.run_sync("--check").returncode, 0)

    def test_check_detects_missing_and_changed_assets_without_writing(self) -> None:
        missing = self.run_sync("--check")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("schemas/future-current.schema.json", missing.stdout)
        self.assertNotIn("trusted-web-read-", missing.stdout)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.run_sync().returncode, 0)
        changed = self.target / self.current[0]
        changed.write_text("stale\n")
        result = self.run_sync("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(self.current[0], result.stdout)
        self.assertEqual(changed.read_text(), "stale\n")

    def test_check_rejects_unexpected_and_prematurely_packaged_assets(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        for name in ("unexpected.json", *self.deferred):
            with self.subTest(asset=name):
                extra = self.target / name
                extra.write_text("{}\n")
                result = self.run_sync("--check")
                self.assertEqual(result.returncode, 1)
                self.assertIn(name, result.stdout)
                self.assertTrue(extra.exists())
                extra.unlink()


if __name__ == "__main__":
    unittest.main()
