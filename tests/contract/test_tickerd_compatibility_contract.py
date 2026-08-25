from __future__ import annotations

import hashlib
import importlib
import json
import unittest
from copy import deepcopy
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parents[2]
CONTRACT_PATH = ROOT / "contracts" / "spine-tickerd-compatibility.v1.json"
CONTRACT_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "spine-tickerd-compatibility.schema.json"
DEPENDENCY_FAILURE_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "runtime-dependency-failure.schema.json"
STORAGE_FACTS_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "storage-safety-facts.schema.json"
SYSTEM_INFO_V2_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "system-info-response-v2.schema.json"

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False

try:
    TICKERD_DISTRIBUTION_VERSION = metadata.version("tickerd")
except metadata.PackageNotFoundError:
    TICKERD_DISTRIBUTION_VERSION = None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def thaw(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(item) for item in value]
    return value


def validate_with_spine_annotations(schema: dict[str, Any], instance: dict[str, Any]) -> None:
    Draft202012Validator(schema).validate(instance)
    for property_name, property_schema in schema.get("properties", {}).items():
        if property_schema.get("x-spine-order") != "lexicographic" or property_name not in instance:
            continue
        if instance[property_name] != sorted(instance[property_name]):
            raise ValidationError(f"{property_name} must be lexicographically sorted")


class SpineTickerdCompatibilityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_json(CONTRACT_PATH)

    def test_contract_and_planned_public_shapes_validate(self) -> None:
        Draft202012Validator(load_json(CONTRACT_SCHEMA_PATH)).validate(self.contract)

        provider = self.contract["provider"]
        dependency_failure = {
            "event": "ledger_runtime_preflight_failed",
            "reason": "runtime_dependency_mismatch",
            "dependency": "tickerd",
            "compatibility_contract": self.contract["contract_id"],
            "required_package_version": provider["required_package_version"],
            "installed_package_version": None,
            "required_capability_id": provider["required_capability_id"],
            "installed_capability_id": None,
            "required_descriptor_sha256": provider["required_descriptor_sha256"],
            "installed_descriptor_sha256": None,
            "mismatch_fields": ["package_import"],
        }
        dependency_failure_schema = load_json(DEPENDENCY_FAILURE_SCHEMA_PATH)
        validate_with_spine_annotations(dependency_failure_schema, dependency_failure)
        unsorted_failure = deepcopy(dependency_failure)
        unsorted_failure["mismatch_fields"] = ["public_api", "package_version"]
        with self.assertRaises(ValidationError):
            validate_with_spine_annotations(dependency_failure_schema, unsorted_failure)

        storage_facts = {
            "reason_facts_contract": "spine.storage-safety-facts.v1",
            "primary_reason": "critical_storage_pressure",
            "pressure_state": "critical",
            "critical_storage_action": "exit_nonzero",
            "measured_at_utc": "2026-08-25T12:00:00Z",
            "measurements": [
                {
                    "roles": ["ledger", "worker_state"],
                    "filesystem_id": "42",
                    "free_bytes": "1024",
                    "warning_free_bytes": "4096",
                    "critical_free_bytes": "2048",
                    "reserve_bytes": "512",
                }
            ],
        }
        Draft202012Validator(load_json(STORAGE_FACTS_SCHEMA_PATH)).validate(storage_facts)

        system_info = {
            "ok": True,
            "command": "system.info",
            "response_contract": "spine.system-info.v2",
            "runtime_version": "0.2.0",
            "implemented_ledger_schema_version": "9",
            "ledger_schema_version": "9",
            "timezone_database_version": "2026c",
            "implemented_contract_versions": [
                "spine.canonical-json.v1",
                "spine.system-info.v2",
                "spine.tickerd-compatibility.v1",
            ],
            "runtime_dependencies": [
                {
                    "name": "tickerd",
                    "package_version": provider["required_package_version"],
                    "capability_id": provider["required_capability_id"],
                    "descriptor_sha256": provider["required_descriptor_sha256"],
                    "compatibility_contract": self.contract["contract_id"],
                    "status": "compatible",
                }
            ],
        }
        system_info_schema = load_json(SYSTEM_INFO_V2_SCHEMA_PATH)
        Draft202012Validator(system_info_schema).validate(system_info)
        missing_compatibility_declaration = deepcopy(system_info)
        missing_compatibility_declaration["implemented_contract_versions"].remove(
            "spine.tickerd-compatibility.v1"
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(system_info_schema).validate(missing_compatibility_declaration)

    def test_contract_sets_are_sorted_unique_and_bounded(self) -> None:
        provider = self.contract["provider"]
        self.assertEqual(provider["required_claim_ids"], sorted(set(provider["required_claim_ids"])))
        public_api = provider["required_public_api"]
        for key in ("descriptor_exports", "consumer_exports", "protocol_exports"):
            self.assertEqual(public_api[key], sorted(set(public_api[key])))

        mismatch_fields = self.contract["runtime_admission"]["mismatch_fields"]
        self.assertEqual(mismatch_fields, sorted(set(mismatch_fields)))
        declared_contracts = self.contract["system_info"]["required_implemented_contract_versions"]
        self.assertEqual(declared_contracts, sorted(set(declared_contracts)))
        self.assertEqual(self.contract["safety_mapping"]["filesystem_roles"], ["ledger", "worker_state"])
        self.assertEqual(self.contract["safety_mapping"]["maximum_measurements"], 2)

        failure_schema = load_json(DEPENDENCY_FAILURE_SCHEMA_PATH)
        self.assertEqual(
            failure_schema["properties"]["mismatch_fields"]["x-spine-order"],
            "lexicographic",
        )
        self.assertEqual(
            failure_schema["properties"]["mismatch_fields"]["items"]["enum"],
            mismatch_fields,
        )

    @unittest.skipUnless(TICKERD_AVAILABLE, "Tickerd is not importable")
    def test_importable_tickerd_matches_the_capability_contract(self) -> None:
        import tickerd

        provider = self.contract["provider"]
        public_api = provider["required_public_api"]
        descriptor_module = importlib.import_module(public_api["descriptor_module"])
        consumer_module = importlib.import_module(public_api["consumer_module"])
        protocol_module = importlib.import_module(public_api["protocol_module"])
        self.assertEqual(tickerd.RUNTIME_CAPABILITY_ID, provider["required_capability_id"])

        for export_name in public_api["descriptor_exports"]:
            self.assertTrue(hasattr(descriptor_module, export_name), export_name)
        for export_name in public_api["consumer_exports"]:
            self.assertTrue(hasattr(consumer_module, export_name), export_name)
        for export_name in public_api["protocol_exports"]:
            self.assertTrue(hasattr(protocol_module, export_name), export_name)
        for export_name in public_api["descriptor_exports"]:
            self.assertIs(
                getattr(consumer_module, export_name),
                getattr(descriptor_module, export_name),
                export_name,
            )

        descriptor_resource = resources.files(provider["descriptor_package"]).joinpath(
            *provider["descriptor_resource"].split("/")
        )
        descriptor_bytes = descriptor_resource.read_bytes()
        self.assertEqual(hashlib.sha256(descriptor_bytes).hexdigest(), provider["required_descriptor_sha256"])
        parsed_descriptor = json.loads(descriptor_bytes)
        self.assertEqual(parsed_descriptor["capability_id"], provider["required_capability_id"])
        self.assertEqual(parsed_descriptor["schema_version"], provider["required_descriptor_schema_version"])
        descriptor_public_api = parsed_descriptor["public_python_api"]
        self.assertEqual(descriptor_public_api["module"], public_api["descriptor_module"])
        self.assertEqual(
            sorted(
                [
                    descriptor_public_api["descriptor_name"],
                    descriptor_public_api["identity_name"],
                    descriptor_public_api["required_identity_function"],
                ]
            ),
            public_api["descriptor_exports"],
        )
        self.assertEqual(
            [claim["id"] for claim in parsed_descriptor["claims"]],
            provider["required_claim_ids"],
        )
        self.assertEqual(thaw(tickerd.RUNTIME_CAPABILITY_DESCRIPTOR), parsed_descriptor)
        self.assertEqual(
            thaw(descriptor_module.require_runtime_capability(provider["required_capability_id"])),
            parsed_descriptor,
        )
        self.assertEqual(
            thaw(consumer_module.require_runtime_capability(provider["required_capability_id"])),
            parsed_descriptor,
        )

    @unittest.skipUnless(TICKERD_DISTRIBUTION_VERSION, "Tickerd distribution metadata is unavailable")
    def test_installed_tickerd_distribution_version_matches(self) -> None:
        provider = self.contract["provider"]
        self.assertEqual(TICKERD_DISTRIBUTION_VERSION, provider["required_package_version"])


if __name__ == "__main__":
    unittest.main()
