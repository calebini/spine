"""Additive wire contracts, packaged pins and generated artifact parity."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine.commands.facets import CONTRACTS, WRITES
from spine.web.contracts import artifact, bundle, validate
from spine.web.errors import WebError
from spine.web.facet_service import API, REGISTRY, registry

ROOT = Path(__file__).parents[1]


class FacetWebContractTests(unittest.TestCase):
    def test_closed_registry_schemas_pins_and_all_canonical_requests(self):
        schemas, _ = bundle()
        self.assertEqual(len(registry()["commands"]), 11)
        for name, value in schemas.items():
            if name.startswith("trusted-web-facet-") or ".v2.schema" in name and "provisioning" in name:
                Draft202012Validator.check_schema(value)
        for name, digest in artifact("trusted-web-facet-pins.v1.json")["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / "contracts" / name).read_bytes()).hexdigest(), digest)
        for command in CONTRACTS:
            with self.subTest(command=command):
                path = ROOT / "tests/fixtures/archetype_facets/contracts" / ("request_" + command.replace(".", "_") + ".json")
                body = {"request": json.loads(path.read_text())}
                if command in WRITES:
                    body["expected_access_epoch"] = "1"
                validate("trusted-web-facet-request.schema.json", body, "#/$defs/" + command)
                with self.assertRaises(WebError):
                    validate("trusted-web-facet-request.schema.json", {**body, "actor_subject_id": "forged"}, "#/$defs/" + command)
        manifest = artifact("trusted-web-facet-fixture-manifest.json")
        for case in manifest["fixtures"]:
            validate(case["schema"], json.loads((ROOT / case["path"]).read_text()), case["fragment"])

    def test_missing_runtime_pin_or_changed_registry_fails_closed(self):
        from spine import IMPLEMENTED_CONTRACT_VERSIONS

        for contract in (API, REGISTRY, "spine.item-facets.v1"):
            with (
                patch("spine.web.facet_service.IMPLEMENTED_CONTRACT_VERSIONS", IMPLEMENTED_CONTRACT_VERSIONS - {contract}),
                self.assertRaises(WebError),
            ):
                registry()
        changed = copy.deepcopy(artifact("spine.trusted-web-facet-registry.v1.json"))
        changed["commands"][0]["resolvers"] = []
        with (
            patch("spine.web.facet_service.artifact", side_effect=lambda name: changed if "registry" in name else artifact(name)),
            self.assertRaises(WebError),
        ):
            registry()

    def test_generator_check_and_frozen_families_remain_disjoint(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/sync_facet_web_contracts.py"), "--check"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for family in ("command", "read"):
            self.assertTrue(
                set(CONTRACTS).isdisjoint(e["command"] for e in artifact(f"spine.trusted-web-{family}-registry.v1.json")["commands"])
            )
