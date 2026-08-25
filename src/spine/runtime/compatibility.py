"""Exact, bounded Tickerd runtime compatibility admission."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module, metadata, resources
from typing import Any


@dataclass(frozen=True)
class TickerdCompatibilityInfo:
    package_version: str
    capability_id: str
    descriptor_sha256: str
    compatibility_contract: str = "spine.tickerd-compatibility.v1"
    status: str = "compatible"

    def as_system_info(self) -> dict[str, str]:
        return {
            "name": "tickerd",
            "package_version": self.package_version,
            "capability_id": self.capability_id,
            "descriptor_sha256": self.descriptor_sha256,
            "compatibility_contract": self.compatibility_contract,
            "status": self.status,
        }


class TickerdCompatibilityError(RuntimeError):
    def __init__(self, diagnostic: Mapping[str, Any]) -> None:
        super().__init__("installed Tickerd runtime does not satisfy spine.tickerd-compatibility.v1")
        self.diagnostic = dict(diagnostic)


def compatibility_contract() -> dict[str, Any]:
    resource = resources.files("spine.contracts").joinpath("spine-tickerd-compatibility.v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def resolve_tickerd_compatibility() -> TickerdCompatibilityInfo:
    contract = compatibility_contract()
    provider = contract["provider"]
    mismatch: set[str] = set()
    installed_version: str | None = None
    installed_capability_id: str | None = None
    installed_descriptor_sha256: str | None = None

    try:
        installed_version = metadata.version(provider["distribution_name"])
    except Exception:
        mismatch.add("package_version")
    if installed_version != provider["required_package_version"]:
        mismatch.add("package_version")

    modules: dict[str, Any] = {}
    api = provider["required_public_api"]
    for role in ("descriptor_module", "consumer_module", "protocol_module"):
        try:
            modules[role] = import_module(api[role])
        except Exception:
            mismatch.add("package_import")

    if len(modules) == 3:
        for role, exports_key in (
            ("descriptor_module", "descriptor_exports"),
            ("consumer_module", "consumer_exports"),
            ("protocol_module", "protocol_exports"),
        ):
            if any(not hasattr(modules[role], name) for name in api[exports_key]):
                mismatch.add("public_api")
        descriptor_module = modules["descriptor_module"]
        consumer_module = modules["consumer_module"]
        if not mismatch.intersection({"public_api"}):
            for name in api["descriptor_exports"]:
                if getattr(descriptor_module, name) is not getattr(consumer_module, name):
                    mismatch.add("public_api")
        installed_capability_id = getattr(descriptor_module, "RUNTIME_CAPABILITY_ID", None)
        if installed_capability_id != provider["required_capability_id"]:
            mismatch.add("capability_id")

    descriptor_bytes: bytes | None = None
    parsed_descriptor: dict[str, Any] | None = None
    try:
        descriptor_bytes = (
            resources.files(provider["descriptor_package"]).joinpath(*provider["descriptor_resource"].split("/")).read_bytes()
        )
        installed_descriptor_sha256 = hashlib.sha256(descriptor_bytes).hexdigest()
        if installed_descriptor_sha256 != provider["required_descriptor_sha256"]:
            mismatch.add("descriptor_sha256")
        parsed = json.loads(descriptor_bytes)
        if isinstance(parsed, dict):
            parsed_descriptor = parsed
        else:
            mismatch.add("descriptor_shape")
    except Exception:
        mismatch.update({"descriptor_sha256", "descriptor_shape"})

    if parsed_descriptor is not None:
        declared_api = parsed_descriptor.get("public_python_api")
        declared_exports = (
            []
            if not isinstance(declared_api, dict)
            else [
                declared_api.get("descriptor_name"),
                declared_api.get("identity_name"),
                declared_api.get("required_identity_function"),
            ]
        )
        declared_exports_match = (
            all(isinstance(item, str) for item in declared_exports) and sorted(declared_exports) == api["descriptor_exports"]
        )
        if (
            parsed_descriptor.get("capability_id") != provider["required_capability_id"]
            or parsed_descriptor.get("schema_version") != provider["required_descriptor_schema_version"]
            or not isinstance(declared_api, dict)
            or declared_api.get("module") != api["descriptor_module"]
            or not declared_exports_match
        ):
            mismatch.add("descriptor_shape")
        claims = parsed_descriptor.get("claims")
        claims_are_objects = isinstance(claims, list) and all(isinstance(claim, dict) for claim in claims)
        claim_ids = [claim.get("id") for claim in claims] if claims_are_objects else []
        if claim_ids != provider["required_claim_ids"]:
            mismatch.add("required_claims")

    if len(modules) == 3 and parsed_descriptor is not None and "public_api" not in mismatch:
        descriptor_module = modules["descriptor_module"]
        try:
            resolved = descriptor_module.require_runtime_capability(provider["required_capability_id"])
            if _thaw(resolved) != parsed_descriptor or _thaw(descriptor_module.RUNTIME_CAPABILITY_DESCRIPTOR) != parsed_descriptor:
                mismatch.add("descriptor_shape")
        except Exception:
            mismatch.add("capability_id")

    if mismatch:
        raise TickerdCompatibilityError(
            {
                "event": "ledger_runtime_preflight_failed",
                "reason": "runtime_dependency_mismatch",
                "dependency": "tickerd",
                "compatibility_contract": contract["contract_id"],
                "required_package_version": provider["required_package_version"],
                "installed_package_version": installed_version,
                "required_capability_id": provider["required_capability_id"],
                "installed_capability_id": installed_capability_id,
                "required_descriptor_sha256": provider["required_descriptor_sha256"],
                "installed_descriptor_sha256": installed_descriptor_sha256,
                "mismatch_fields": sorted(mismatch),
            }
        )

    return TickerdCompatibilityInfo(
        package_version=str(installed_version),
        capability_id=str(installed_capability_id),
        descriptor_sha256=str(installed_descriptor_sha256),
    )


def _thaw(value: Any) -> Any:
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value
