"""Pure, version-pinned facet codecs. No catalog, reference or permission I/O."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any, NoReturn

from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.errors import SpineValidationError

DEFINITION_VERSION = "spine.facet-schemas.v1"
VALUE_VERSION = "spine.item-facets.v1"
CANONICAL_VERSION = "spine.canonical-json.v1"
KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z", re.ASCII)


def fail(code: str = "facet_value_invalid") -> NoReturn:
    raise SpineValidationError(code, "facet facts do not satisfy the pinned contract")


def nfc(value: str) -> str:
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        fail()
    return unicodedata.normalize("NFC", value)


def key(value: object) -> str:
    if not isinstance(value, str) or not KEY.fullmatch(value):
        fail()
    return str(value)


def integer(value: object) -> int:
    if not isinstance(value, str) or len(value) > 20 or not INTEGER.fullmatch(value):
        fail()
    result = int(value)
    if not -(2**63) <= result < 2**63:
        fail()
    return result


def _text(value: object, maximum: int, *, controls: bool = False) -> str:
    if not isinstance(value, str):
        fail()
    value = nfc(str(value))
    if not 1 <= len(value) <= maximum or (controls and any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        fail()
    return value


def _object(value: object, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - required - (optional or set()) or required - set(value):
        fail()
    return dict(value)


def normalize_definition(value: object) -> dict[str, Any]:
    try:
        result = _object(value, {"display_name", "description", "compatible_item_types", "fields"})
        result["display_name"] = _text(result["display_name"], 160)
        if result["description"] is not None:
            result["description"] = _text(result["description"], 2000)
        types = result["compatible_item_types"]
        if not isinstance(types, list) or not 1 <= len(types) <= 2 or any(t not in ("event", "task") for t in types):
            fail()
        if len(set(types)) != len(types):
            fail()
        result["compatible_item_types"] = sorted(types)
        fields = result["fields"]
        if not isinstance(fields, list) or not 1 <= len(fields) <= 32:
            fail()
        normalized = []
        for raw in fields:
            if not isinstance(raw, dict):
                fail()
            extras = {
                "text": {"max_length"},
                "enum": {"choices"},
                "integer": {"min", "max"},
                "boolean": set(),
                "date": set(),
                "reference": {"target_kind"},
            }
            kind = raw.get("type")
            if not isinstance(kind, str) or kind not in extras:
                fail()
            field = _object(raw, {"key", "type", "required"} | extras[kind], {"queryable"})
            field["key"] = key(field["key"])
            field.setdefault("queryable", False)
            if type(field["required"]) is not bool or type(field["queryable"]) is not bool:
                fail()
            if kind == "text" and not 1 <= integer(field["max_length"]) <= 1024:
                fail()
            if kind == "integer" and integer(field["min"]) > integer(field["max"]):
                fail()
            if kind == "reference" and field["target_kind"] not in ("subject", "location"):
                fail()
            if kind == "enum":
                choices = field["choices"]
                if not isinstance(choices, list) or not 1 <= len(choices) <= 64:
                    fail()
                choices = [_text(c, 128) for c in choices]
                if len(set(choices)) != len(choices):
                    fail()
                field["choices"] = sorted(choices)
            normalized.append(field)
        if len({f["key"] for f in normalized}) != len(normalized):
            fail()
        result["fields"] = sorted(normalized, key=lambda f: f["key"])
        if len(canonical_json_bytes(result)) > 32768:
            fail()
        return result
    except SpineValidationError as exc:
        raise SpineValidationError("facet_schema_invalid", "invalid facet definition") from exc


def definition_hash(definition: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "derivation_version": "spine.facet-definition.v1",
                "definition": definition,
            }
        )
    ).hexdigest()


def normalize_scalar(field: dict[str, Any], value: object) -> str | bool:
    kind = field["type"]
    if kind == "boolean":
        if type(value) is not bool:
            fail()
        return bool(value)
    if not isinstance(value, str):
        fail()
    value = nfc(str(value))
    if kind == "text":
        return _text(value, integer(field["max_length"]), controls=True)
    if kind == "enum":
        if value not in field["choices"]:
            fail()
    elif kind == "integer":
        if not integer(field["min"]) <= integer(value) <= integer(field["max"]):
            fail()
    elif kind == "date":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            fail()
        try:
            date.fromisoformat(value)
        except ValueError:
            fail()
    elif kind == "reference":
        if not value:
            fail()
        # Existence, lifecycle and authorization are resolved by the caller.
    else:
        fail()
    return value


def normalize_values(definition: dict[str, Any], value: object) -> dict[str, str | bool]:
    if not isinstance(value, dict):
        fail()
    fields = {f["key"]: f for f in definition["fields"]}
    values = _object(value, {k for k, f in fields.items() if f["required"]}, set(fields))
    normalized = {k: normalize_scalar(fields[k], v) for k, v in values.items()}
    if len(canonical_json_bytes(normalized)) > 16384:
        fail()
    return normalized


def snapshot_size(values: dict[str, dict[str, str | bool]]) -> int:
    if len(values) > 8:
        fail()
    for k in values:
        key(k)
    size = len(canonical_json_bytes(values))
    if size > 65536:
        fail()
    return size


def parse_object(text: str, *, maximum: int) -> dict[str, Any]:
    """Reject duplicate keys, invalid scalars and oversized input before decoding."""
    if any(0xD800 <= ord(c) <= 0xDFFF for c in text) or len(text.encode("utf-8")) > maximum:
        fail()

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in items:
            if k in result:
                fail()
            result[k] = v
        return result

    try:
        value = json.loads(text, object_pairs_hook=pairs)
    except (ValueError, RecursionError) as exc:
        raise SpineValidationError("facet_value_invalid", "invalid facet JSON") from exc
    if not isinstance(value, dict):
        fail()
    return value


def decode_definition(text: str, digest: str, *, contract: str, canonical: str) -> dict[str, Any]:
    try:
        if contract != DEFINITION_VERSION or canonical != CANONICAL_VERSION:
            fail()
        definition = normalize_definition(parse_object(text, maximum=32768))
        if canonical_json_text(definition) != text or definition_hash(definition) != digest:
            fail()
        return definition
    except SpineValidationError as exc:
        raise SpineValidationError("environment_failure:facets", "invalid persisted facet definition") from exc


def decode_values(definition: dict[str, Any], text: str, *, contract: str) -> dict[str, str | bool]:
    try:
        if contract != VALUE_VERSION:
            fail()
        values = normalize_values(definition, parse_object(text, maximum=16384))
        if canonical_json_text(values) != text:
            fail()
        return values
    except SpineValidationError as exc:
        raise SpineValidationError("environment_failure:facets", "invalid persisted facet values") from exc
