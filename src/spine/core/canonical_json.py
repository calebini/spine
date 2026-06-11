"""Canonical JSON encoding for Spine hash payloads."""

from collections.abc import Mapping, Sequence
from numbers import Number

from spine.core.errors import SpineValidationError

type CanonicalJsonValue = None | bool | str | Mapping[str, CanonicalJsonValue] | Sequence[CanonicalJsonValue]


def canonical_json_text(value: object) -> str:
    """Return Spine's canonical JSON text for a hash payload.

    This follows the MVP canonicalization contract in ``specs/ontology.md``:
    no insignificant whitespace, object keys sorted by Unicode codepoint,
    preserved array order, no JSON numbers, UTF-8-safe strings, and canonical
    escaping only for quotes, backslashes, and control characters.
    """

    return _encode(value)


def canonical_json_bytes(value: object) -> bytes:
    """Return Spine's canonical JSON UTF-8 bytes for a hash payload."""

    return canonical_json_text(value).encode("utf-8")


def _encode(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, Number):
        raise SpineValidationError(
            "canonical_json_number_not_allowed",
            "numbers are not allowed in Spine MVP hash payloads",
        )
    if isinstance(value, Mapping):
        return _encode_object(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise SpineValidationError(
        "canonical_json_unsupported_type",
        f"unsupported canonical JSON value type: {type(value).__name__}",
    )


def _encode_object(value: Mapping[object, object]) -> str:
    encoded_items: list[str] = []
    for key in sorted(value.keys(), key=_sort_key):
        if not isinstance(key, str):
            raise SpineValidationError(
                "canonical_json_non_string_key",
                "canonical JSON object keys must be strings",
            )
        encoded_items.append(f"{_encode_string(key)}:{_encode(value[key])}")
    return "{" + ",".join(encoded_items) + "}"


def _sort_key(key: object) -> str:
    if not isinstance(key, str):
        raise SpineValidationError(
            "canonical_json_non_string_key",
            "canonical JSON object keys must be strings",
        )
    _reject_surrogates(key)
    return key


def _encode_string(value: str) -> str:
    _reject_surrogates(value)
    parts = ['"']
    for char in value:
        codepoint = ord(char)
        if char == '"':
            parts.append('\\"')
        elif char == "\\":
            parts.append("\\\\")
        elif codepoint <= 0x1F:
            parts.append(f"\\u{codepoint:04x}")
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise SpineValidationError(
            "canonical_json_invalid_surrogate",
            "strings in Spine hash payloads must not contain surrogate code points",
        )
