"""Offline schemas and exact runtime contract pins for the web adapter."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError

API = "spine.trusted-web-api.v1"
REGISTRY = "spine.trusted-web-command-registry.v1"


@lru_cache(maxsize=1)
def bundle() -> tuple[dict[str, Any], Registry]:
    root = resources.files("spine.contracts").joinpath("web")
    schemas = {p.name: json.loads(p.read_text()) for p in root.joinpath("schemas").iterdir() if p.name.endswith(".json")}
    refs = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return schemas, refs


def artifact(name: str) -> dict[str, Any]:
    return json.loads(resources.files("spine.contracts").joinpath("web", name).read_text())


def validate(name: str, value: Any, fragment: str = "") -> None:
    schemas, refs = bundle()
    validator = Draft202012Validator({"$ref": schemas[name]["$id"] + fragment}, registry=refs, format_checker=FormatChecker())
    if not validator.is_valid(value):
        raise WebError("invalid_request")


def registry() -> tuple[dict[str, dict[str, Any]], str]:
    payload = artifact("spine.trusted-web-command-registry.v1.json")
    validate("trusted-web-command-registry.schema.json", payload)
    entries = {e["command"]: e for e in payload["commands"]}
    if len(entries) != 13:
        raise WebError("admission_unavailable")
    for command, entry in entries.items():
        actual = COMMAND_RUNTIME_CONTRACT_REGISTRY.get(command)
        resolvers = {
            "item.occurrences": "item_read_all_returned_references",
            "item_archetype.list": "catalog_scope_and_returned_references",
            "item_archetype.show": "catalog_scope_and_returned_references",
            "notification_profile.binding.list": "catalog_scope_and_returned_references",
            "notification_profile.list": "catalog_scope_and_returned_references",
            "notification_profile.resolve": "catalog_scope_chain_read_use",
            "notification_profile.show": "catalog_scope_and_returned_references",
            "schedule.build": "create_scope_and_references",
            "schedule.create": "create_scope_and_references",
            "schedule.show": "item_read_all_returned_references",
            "schedule.update": "item_edit_and_resulting_release",
            "schedule.cancel": "item_edit_stop_intent",
            "task.complete": "item_edit_stop_intent",
        }
        if actual is None or list(actual.required_contract_versions) != entry["required_contract_versions"]:
            raise WebError("admission_unavailable")
        if (
            entry["resolver"] != resolvers[command]
            or entry["access_mode"] != actual.access_mode
            or entry["projection"] != "canonical_complete_or_deny"
            or entry["requires_create_owner_scope"] != (command in {"schedule.build", "schedule.create"})
            or entry["requires_expected_access_epoch"] != (actual.access_mode == "write")
        ):
            raise WebError("admission_unavailable")
        if not set(entry["required_contract_versions"]) <= IMPLEMENTED_CONTRACT_VERSIONS:
            raise WebError("admission_unavailable")
    for name, digest in artifact("trusted-web-schema-pins.v1.json")["files"].items():
        raw = resources.files("spine.contracts").joinpath("web", "schemas", name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise WebError("admission_unavailable")
    return entries, hash_canonical_json(payload)


def json_object(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("non-JSON constant")

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WebError("invalid_request") from exc
    if not isinstance(result, dict):
        raise WebError("invalid_request")
    return result
