"""Pinned local provisioning-v3 schemas; no source or remote resolution."""

import hashlib
import json
from importlib import resources
from importlib.resources.abc import Traversable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from spine.commands.recurring_task_package import _read, _references
from spine.core.errors import SpineValidationError
from spine.web.ownership_provisioning import OwnershipProvisioningContracts

PIN = "024725376d7df53b2c8134f3cff335198d4d39857f7792222b6df7dcca547385"


def load_from(directory: Traversable) -> OwnershipProvisioningContracts:
    from spine import IMPLEMENTED_CONTRACT_VERSIONS

    try:
        if not {"spine.trusted-web-provisioning.v3", "spine.ownership-access-state.v1"} <= IMPLEMENTED_CONTRACT_VERSIONS:
            raise ValueError("ownership prerequisite unavailable")
        raw = _read(directory, "pins.v1.json")
        if hashlib.sha256(raw).hexdigest() != PIN:
            raise ValueError("ownership pins mismatch")
        pins = json.loads(raw)
        if pins["contract_version"] != "spine.ownership-package-pins.v1" or len(pins["files"]) > 64:
            raise ValueError("ownership closure capacity/version")
        documents, size = {}, 0
        for name, digest in pins["files"].items():
            raw = _read(directory, name)
            size += len(raw)
            if size > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("ownership resource mismatch")
            document = json.loads(raw)
            if name.startswith("schemas/"):
                Draft202012Validator.check_schema(document)
                documents[name] = document
        ids = {s["$id"] for s in documents.values()}
        if len(ids) != len(documents) or any(_references(s, s["$id"]) - ids for s in documents.values()):
            raise ValueError("ownership closure incomplete")
        return OwnershipProvisioningContracts(documents)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, SchemaError) as exc:
        raise SpineValidationError("environment_failure:runtime_contracts", "Ownership provisioning resources unavailable.") from exc


def packaged() -> OwnershipProvisioningContracts:
    return load_from(resources.files("spine.contracts").joinpath("ownership"))
