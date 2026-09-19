"""Offline, pinned contracts for independent authorized v2 reads."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError

READ_API = "spine.trusted-web-api.v2"
NORMALIZATION = "spine.trusted-web-read-normalization.v1"
# Exact package admission root; changes require matching source/package pin tests.
READ_PIN_MANIFEST_SHA256 = "f5dfa13d510cf227bb480c829f8c4d2b6b03cbc2d63f163dbbe0a884db733f10"
READ_RUNTIME_CONTRACTS = frozenset({
    READ_API, "spine.trusted-web-read-registry.v1", "spine.trusted-web-cursor.v2",
    "spine.trusted-web-schedule-view.v1", "spine.trusted-web-occurrences.v1", "spine.trusted-web-agenda.v2",
})
REQUEST_SCHEMAS = {
    "schedule.show": "trusted-web-read-schedule-request.schema.json",
    "item.occurrences": "trusted-web-read-occurrences-request.schema.json",
    "agenda": "trusted-web-read-agenda-request.schema.json",
}
FORMATS = FormatChecker()


@FORMATS.checks("spine-local-date-time", raises=ValueError)
def local_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True  # The schema's type assertion rejects non-strings.
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", value) is None:
        return False
    datetime.fromisoformat(value)
    return True


@FORMATS.checks("date-time", raises=ValueError)
def utc_datetime(value: object) -> bool:
    return not isinstance(value, str) or (value.endswith("Z") and local_datetime(value[:-1]))


@FORMATS.checks("date", raises=ValueError)
def local_date(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        return False
    date.fromisoformat(value)
    return True


def read_error(code: str) -> WebError:
    # V2 status differs from v1. Do not change the existing v1 error mapping.
    return WebError(code, status={"capacity_exceeded": 503, "version_changed": 409}.get(code))


class ReadContracts:
    """An explicitly loaded, offline, pinned set of independent-read assets."""

    def __init__(self, directory: Traversable) -> None:
        try:
            pins = json.loads((directory / "trusted-web-read-schema-pins.v1.json").read_bytes())
            self.schemas = self._load(directory / "schemas", pins["schemas"])
            self.artifacts = self._load(directory, pins["artifacts"])
            self.references = Registry().with_resources(
                (s["$id"], Resource.from_contents(s)) for s in self.schemas.values()
            )
            for schema in self.schemas.values():
                Draft202012Validator.check_schema(schema)
                self._check_formats(schema)
            self.normalization = self.artifacts["trusted-web-read-normalization.v1.json"]
            if self.normalization["contract_version"] != NORMALIZATION:
                raise ValueError("normalization contract mismatch")
            self.bounds = {k: int(v) for k, v in self.normalization["bounds"].items()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise read_error("admission_unavailable") from exc

    @classmethod
    def packaged(cls) -> ReadContracts:
        """Fail closed at startup; a request cannot select or repair package assets."""
        try:
            root = resources.files("spine.contracts").joinpath("web")
            raw = root.joinpath("trusted-web-read-schema-pins.v1.json").read_bytes()
            if hashlib.sha256(raw).hexdigest() != READ_PIN_MANIFEST_SHA256:
                raise ValueError("pin manifest mismatch")
            if not READ_RUNTIME_CONTRACTS <= IMPLEMENTED_CONTRACT_VERSIONS:
                raise ValueError("incomplete runtime declarations")
            result = cls(root)
            registry = result.artifacts["spine.trusted-web-read-registry.v1.json"]
            result.validate("trusted-web-read-registry.schema.json", registry, output=True)
            if registry["status"] != "implemented":
                raise ValueError("read registry not implemented")
            return result
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise read_error("admission_unavailable") from exc

    @staticmethod
    def _load(directory: Traversable, pins: dict[str, str]) -> dict[str, Any]:
        result = {}
        for name, digest in pins.items():
            if Path(name).name != name:
                raise ValueError("asset name is not local")
            raw = (directory / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("asset pin mismatch")
            result[name] = json.loads(raw)
        return result

    @classmethod
    def _check_formats(cls, value: Any) -> None:
        if isinstance(value, dict):
            if "format" in value and value["format"] not in FORMATS.checkers:
                raise ValueError("unasserted format")
            for child in value.values():
                cls._check_formats(child)
        elif isinstance(value, list):
            for child in value:
                cls._check_formats(child)

    def validate(self, name: str, value: Any, *, definition: str | None = None, output: bool = False) -> None:
        schema = self.schemas[name]
        ref = schema["$id"] + ("#/$defs/" + definition if definition else "")
        validator = Draft202012Validator({"$ref": ref}, registry=self.references, format_checker=FORMATS)
        if not validator.is_valid(value):
            raise read_error("admission_unavailable" if output else "invalid_request")

    def normalize(self, route: str, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Validate before defaults; return the exact hash preimage and its digest.

        Cursor transport fields remain in the caller's input, never in the preimage.
        Semantic range/tzdb resolution still belongs to the canonical time engine.
        """
        if route not in REQUEST_SCHEMAS:
            raise read_error("operation_unavailable")
        try:
            if len(canonical_json_bytes(body)) > self.bounds["request_bytes"]:
                raise read_error("invalid_request")
        except (SpineValidationError, UnicodeError, RecursionError) as exc:
            raise read_error("invalid_request") from exc
        self.validate(REQUEST_SCHEMAS[route], body)
        request = copy.deepcopy(body["request"])
        for key, value in self.normalization["request_defaults"][route].items():
            request.setdefault(key, copy.deepcopy(value))
        for key in self.normalization["set_arrays"]:
            if key in request:
                request[key] = sorted(request[key])
        if not set(request.get("section_cursors", {})) <= set(request.get("include", [])):
            raise read_error("invalid_request")
        for key in self.normalization["strip_request_fields"]:
            request.pop(key, None)
        preimage = {
            "contract_version": NORMALIZATION, "route": route, "request": request,
            **{key: body.get(key) for key in self.normalization["null_guard_defaults"]},
        }
        return preimage, hash_canonical_json(preimage)
