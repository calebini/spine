"""Existing command value checks shared without changing family error precedence.

These are scalar checks, not a request codec or an admission boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spine.core.errors import SpineValidationError


def object_value(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an object")
    return dict(value)


def exact_fields(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SpineValidationError(
            f"unsupported_field:{field}.{unknown[0]}",
            f"unsupported field for {field}: {unknown[0]}",
        )


def required_string(value: Mapping[str, Any], key: str, field: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or result == "":
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a non-empty string")
    return result


def optional_string(value: Mapping[str, Any], key: str, field: str) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    if not isinstance(result, str):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a string")
    return result


def enum_value(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SpineValidationError(f"unsupported_{field}", f"{field} must be one of {sorted(allowed)}")
    return value
