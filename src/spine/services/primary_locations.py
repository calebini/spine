"""Primary-location normalization and projection for schedule surfaces."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from spine.core import SpineValidationError
from spine.ledger.supporting import ItemLocationInput, LocationInput

LOCATION_CONTRACT = "spine.schedule-primary-location.v1"
AUTHORING_CONTRACT = "spine.schedule-primary-location-authoring.v1"
VIEW_CONTRACT = "spine.schedule-primary-location-view.v1"
NORMALIZATION_VERSION = "spine.schedule-primary-location-normalization.v1"
CANONICAL_JSON_VERSION = "spine.canonical-json.v1"

_KINDS = {"address", "place", "virtual", "relative", "unknown"}
_CREATE_FIELDS = {
    "mode",
    "label",
    "kind",
    "address_text",
    "latitude",
    "longitude",
    "timezone",
    "provider_ref",
}
_REFERENCE_FIELDS = {"mode", "location_id"}
_OPTIONAL_CANONICAL_FIELDS = (
    "address_text",
    "latitude",
    "longitude",
    "timezone",
    "provider_ref",
)
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def normalize_primary_location(value: object, *, field: str) -> dict[str, str]:
    """Return the closed normalized create/reference authoring value."""

    if not isinstance(value, Mapping):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be an object")
    mode = value.get("mode")
    if mode == "create":
        _exact_fields(value, _CREATE_FIELDS, field)
        label = _non_blank(value.get("label"), f"{field}.label")
        kind = value.get("kind")
        if not isinstance(kind, str) or kind not in _KINDS:
            raise SpineValidationError(
                f"invalid_request:{field}.kind",
                f"{field}.kind must be address, place, virtual, relative, or unknown",
            )
        result = _version_facts()
        result.update({"mode": "create", "label": label, "kind": kind})
        for name in _OPTIONAL_CANONICAL_FIELDS:
            if name in value:
                result[name] = _non_blank(value[name], f"{field}.{name}")
        _validate_coordinates(result, field=field)
        return result
    if mode == "reference":
        _exact_fields(value, _REFERENCE_FIELDS, field)
        return {
            **_version_facts(),
            "mode": "reference",
            "location_id": _non_blank(value.get("location_id"), f"{field}.location_id"),
        }
    raise SpineValidationError(
        f"invalid_request:{field}.mode",
        f"{field}.mode must be create or reference",
    )


def load_referenced_location(
    connection: sqlite3.Connection,
    *,
    location_id: str,
    field: str,
) -> dict[str, Any]:
    """Load and validate an existing canonical location for schedule reference."""

    row = connection.execute(
        """
        SELECT location_id, label, kind, address_text, latitude, longitude,
               timezone, provider_ref, created_at_utc AS location_created_at_utc,
               updated_at_utc AS location_updated_at_utc
        FROM locations
        WHERE location_id = ?
        """,
        (location_id,),
    ).fetchone()
    if row is None:
        raise SpineValidationError(
            f"referenced_row_not_found:{field}",
            "referenced primary location does not exist",
        )
    result = dict(row)
    try:
        _canonical_facts(result, field=field)
    except SpineValidationError as exc:
        raise SpineValidationError(
            f"semantic_conflict:{field}",
            "referenced primary location cannot be represented by the schedule location view",
        ) from exc
    return result


def current_primary_location(item: Mapping[str, Any]) -> dict[str, Any] | None:
    values = item.get("locations", ())
    if not isinstance(values, (list, tuple)):
        return None
    for value in values:
        if isinstance(value, Mapping) and value.get("role") == "primary":
            return dict(value)
    return None


def canonical_location_facts(value: Mapping[str, Any]) -> dict[str, str]:
    """Return only immutable semantic location fields for exact comparison."""

    return _canonical_facts(value, field="primary_location")


def primary_location_view(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project a joined location/item-location row into the clean public view."""

    canonical = _canonical_facts(value, field="primary_location")
    result: dict[str, Any] = {
        "location_contract": LOCATION_CONTRACT,
        "view_contract": VIEW_CONTRACT,
        "location_id": str(value["location_id"]),
        "item_location_id": str(value["item_location_id"]),
        "role": "primary",
        **canonical,
        "item_location_created_at_utc": str(value["created_at_utc"]),
        "location_created_at_utc": str(value["location_created_at_utc"]),
        "location_updated_at_utc": str(value["location_updated_at_utc"]),
    }
    return result


def inline_location_inputs(
    normalized: Mapping[str, str],
    *,
    location_id: str,
    item_location_id: str,
    created_at_utc: str,
) -> ItemLocationInput:
    return ItemLocationInput(
        role="primary",
        item_location_id=item_location_id,
        created_at_utc=created_at_utc,
        location=LocationInput(
            location_id=location_id,
            label=normalized["label"],
            kind=normalized["kind"],
            address_text=normalized.get("address_text"),
            latitude=normalized.get("latitude"),
            longitude=normalized.get("longitude"),
            timezone=normalized.get("timezone"),
            provider_ref=normalized.get("provider_ref"),
            created_at_utc=created_at_utc,
            updated_at_utc=created_at_utc,
        ),
    )


def reference_location_input(
    *,
    location_id: str,
    item_location_id: str,
    created_at_utc: str,
) -> ItemLocationInput:
    return ItemLocationInput(
        role="primary",
        location_id=location_id,
        item_location_id=item_location_id,
        created_at_utc=created_at_utc,
    )


def predicted_inline_view(
    normalized: Mapping[str, str],
    *,
    location_id: str,
    item_location_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    return primary_location_view(
        {
            "location_id": location_id,
            "item_location_id": item_location_id,
            "role": "primary",
            "created_at_utc": created_at_utc,
            "location_created_at_utc": created_at_utc,
            "location_updated_at_utc": created_at_utc,
            **{name: normalized[name] for name in ("label", "kind", *_OPTIONAL_CANONICAL_FIELDS) if name in normalized},
        }
    )


def referenced_view(
    row: Mapping[str, Any],
    *,
    item_location_id: str,
    item_location_created_at_utc: str,
) -> dict[str, Any]:
    return primary_location_view(
        {
            **dict(row),
            "item_location_id": item_location_id,
            "role": "primary",
            "created_at_utc": item_location_created_at_utc,
        }
    )


def _version_facts() -> dict[str, str]:
    return {
        "location_contract": LOCATION_CONTRACT,
        "authoring_contract": AUTHORING_CONTRACT,
        "normalization_version": NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
    }


def _canonical_facts(value: Mapping[str, Any], *, field: str) -> dict[str, str]:
    label = _non_blank(value.get("label"), f"{field}.label")
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise SpineValidationError(f"invalid_request:{field}.kind", f"{field}.kind is invalid")
    result = {"label": label, "kind": kind}
    for name in _OPTIONAL_CANONICAL_FIELDS:
        if value.get(name) is not None:
            result[name] = _non_blank(value[name], f"{field}.{name}")
    _validate_coordinates(result, field=field)
    return result


def _validate_coordinates(value: Mapping[str, str], *, field: str) -> None:
    has_latitude = "latitude" in value
    has_longitude = "longitude" in value
    if has_latitude != has_longitude:
        missing = "longitude" if has_latitude else "latitude"
        raise SpineValidationError(
            f"invalid_request:{field}.{missing}",
            "latitude and longitude must be supplied together",
        )
    if not has_latitude:
        return
    _coordinate(value["latitude"], minimum=Decimal("-90"), maximum=Decimal("90"), field=f"{field}.latitude")
    _coordinate(
        value["longitude"],
        minimum=Decimal("-180"),
        maximum=Decimal("180"),
        field=f"{field}.longitude",
    )


def _coordinate(value: str, *, minimum: Decimal, maximum: Decimal, field: str) -> None:
    if _DECIMAL.fullmatch(value) is None:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a non-exponent decimal string")
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} is not decimal") from exc
    if decimal == 0 and value.startswith("-"):
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must not encode negative zero")
    if decimal < minimum or decimal > maximum:
        raise SpineValidationError(f"invalid_request:{field}", f"{field} is outside its coordinate range")


def _exact_fields(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise SpineValidationError(
            f"unsupported_field:{field}.{extra[0]}",
            f"unsupported field: {field}.{extra[0]}",
        )


def _non_blank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise SpineValidationError(f"invalid_request:{field}", f"{field} must be a non-blank string")
    return value
