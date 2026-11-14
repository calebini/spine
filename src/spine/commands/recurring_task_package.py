"""Pinned offline resources for R4 admission. Loading is not feature activation."""

import hashlib
import json
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urldefrag, urljoin

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from spine.commands.recurring_task_runtime import RecurringTaskContracts
from spine.core.errors import SpineValidationError

PIN_SHA256 = "6daa92da0ef83f9e6ef934d02ff894c088a01c7fe0aec4b6244a0bc7e83993bc"
DESCRIPTOR = "recurring-related-tasks.v1.json"
CLOSURE = "recurring-related-task-schema-closure.v1.json"


def _references(value: Any, base: str) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        base = urljoin(base, value.get("$id", ""))
        if "$ref" in value:
            result.add(urldefrag(urljoin(base, value["$ref"]))[0])
        for child in value.values():
            result.update(_references(child, base))
    elif isinstance(value, list):
        for child in value:
            result.update(_references(child, base))
    return result


def _read(directory: Traversable, name: str) -> bytes:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name or len(path.parts) > 3:
        raise ValueError("nonlocal packaged resource")
    with directory.joinpath(*path.parts).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("packaged resource capacity")
    return raw


def load_from(directory: Traversable) -> RecurringTaskContracts:
    """Protected test seam; public requests never choose this resource directory."""
    from spine import IMPLEMENTED_CONTRACT_VERSIONS

    try:
        raw = _read(directory, "pins.v1.json")
        if hashlib.sha256(raw).hexdigest() != PIN_SHA256:
            raise ValueError("pin manifest mismatch")
        pins = json.loads(raw)
        if pins["contract_version"] != "spine.recurring-task-package-pins.v1" or len(pins["files"]) > 128:
            raise ValueError("pin manifest contract/capacity")
        assets, size = {}, 0
        for name, digest in pins["files"].items():
            content = _read(directory, name)
            size += len(content)
            if size > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("resource hash/capacity mismatch")
            assets[name] = json.loads(content)
        closure = assets[CLOSURE]
        if closure["contract_version"] != "spine.recurring-related-task-schema-closure.v1":
            raise ValueError("closure version mismatch")
        documents = {}
        expected = {DESCRIPTOR, CLOSURE}
        identities = set()
        for entry in closure["resources"]:
            name = entry["path"].removeprefix("contracts/")
            schema = assets[name]
            if (not entry["path"].startswith("contracts/schemas/") or name in expected
                    or entry["uri"] in identities or schema["$id"] != entry["uri"]
                    or entry["sha256"] != pins["files"][name]):
                raise ValueError("closure member mismatch")
            Draft202012Validator.check_schema(schema)
            documents[entry["path"]] = schema
            expected.add(name)
            identities.add(entry["uri"])
        if expected != set(assets) or any(_references(doc, doc["$id"]) - identities for doc in documents.values()):
            raise ValueError("incomplete offline closure")
        result = RecurringTaskContracts(documents, assets[DESCRIPTOR])
        if result.descriptor.get("runtime_implemented") is not True or result.descriptor.get("ledger_schema_version") != "20":
            raise ValueError("recurring-task runtime descriptor is not activated")
        if not set(result.descriptor["required_existing_contract_versions"]) <= IMPLEMENTED_CONTRACT_VERSIONS:
            raise ValueError("required existing runtime contract unavailable")
        for spec in result.descriptor["commands"].values():
            for field in ("request_schema", "response_schema", "failure_schema"):
                if spec[field] not in documents:
                    raise ValueError("missing command schema")
        return result
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, SchemaError) as exc:
        raise SpineValidationError("environment_failure:runtime_contracts", "Recurring-task resources unavailable.") from exc


def packaged() -> RecurringTaskContracts:
    """Never fetch schemas or fall back to the source tree; no cached success."""
    return load_from(resources.files("spine.contracts").joinpath("recurring_tasks"))
