"""Pure deterministic rendering for ordinary notification reminders."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from spine.core.canonical_json import canonical_json_text
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.schedule import system_timezone_database_version

RENDERING_CONTRACT = "spine.notification-rendering.v1"
RENDERING_PROFILE = "spine.notification-rendering.concise-en-ca.v1"
INPUT_NORMALIZATION_VERSION = "spine.notification-rendering-input.v1"
CANONICAL_JSON_VERSION = "spine.canonical-json.v1"

NEAR_NOW_SECONDS = 30
RELATIVE_WINDOW_SECONDS = 21_600
MAX_BODY_SCALARS = 1_024

_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_WHITESPACE = re.compile(r"\s+", re.UNICODE)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_PHRASE_KINDS = {
    "future_relative",
    "future_calendar",
    "now",
    "past_relative",
    "past_calendar",
    "date_calendar",
}


@dataclass(frozen=True)
class NotificationRendering:
    """One deterministic immutable rendering prepared for an attempt."""

    notification_rendering_id: str
    attempt_id: str
    work_instance_id: str
    rendering_input_hash: str
    rendered_content_hash: str
    body_text: str
    phrase_kind: str
    source_input: dict[str, Any]
    phrase_facts: dict[str, str]
    input_hash_preimage: dict[str, Any]
    content_hash_preimage: dict[str, Any]
    id_preimage: dict[str, Any]

    @property
    def attempted_at_utc(self) -> str:
        return str(self.source_input["attempted_at_utc"])

    @property
    def item_id(self) -> str:
        return str(self.source_input["item_id"])

    @property
    def rendered_item_version(self) -> int:
        return int(str(self.source_input["rendered_item_version"]))

    def as_persistence(self) -> dict[str, Any]:
        """Return the exact immutable row facts used by the ledger adapter."""

        return {
            "notification_rendering_id": self.notification_rendering_id,
            "attempt_id": self.attempt_id,
            "work_instance_id": self.work_instance_id,
            "notification_opportunity_id": self.source_input["notification_opportunity_id"],
            "notification_intent_id": self.source_input["notification_intent_id"],
            "item_id": self.item_id,
            "rendered_item_version": self.rendered_item_version,
            "rendering_contract": RENDERING_CONTRACT,
            "rendering_profile": RENDERING_PROFILE,
            "input_normalization_version": INPUT_NORMALIZATION_VERSION,
            "canonical_json_version": CANONICAL_JSON_VERSION,
            "rendering_input_hash": self.rendering_input_hash,
            "rendered_content_hash": self.rendered_content_hash,
            "body_text": self.body_text,
            "phrase_kind": self.phrase_kind,
            "attempted_at_utc": self.attempted_at_utc,
            "target_scheduled_fact": self.source_input["target_scheduled_fact"],
            "target_at_utc": self.source_input.get("target_at_utc"),
            "display_time_basis": self.source_input["display_time_basis"],
            "display_timezone": self.source_input["display_timezone"],
            "timezone_database_version": self.source_input["timezone_database_version"],
            "delta_seconds": self.phrase_facts.get("delta_seconds"),
            "occurrence_provenance_id": self.source_input.get("occurrence_provenance_id"),
            "recurrence_revision_id": self.source_input.get("recurrence_revision_id"),
            "occurrence_key": self.source_input.get("occurrence_key"),
            "temporal_binding_id": self.source_input.get("temporal_binding_id"),
            "temporal_binding_revision_id": self.source_input.get("temporal_binding_revision_id"),
            "location_id": _location_fact(self.source_input, "location_id"),
            "item_location_id": _location_fact(self.source_input, "item_location_id"),
            "location_kind": _location_fact(self.source_input, "location_kind"),
            "location_label": _location_fact(self.source_input, "location_label"),
            "source_input_json": canonical_json_text(self.source_input),
            "phrase_facts_json": canonical_json_text(self.phrase_facts),
            "created_at_utc": self.attempted_at_utc,
        }


def render_notification(source: object) -> NotificationRendering:
    """Normalize one resolved source object and render exact v1 reminder prose."""

    normalized = normalize_rendering_source(source)
    phrase_kind, phrase_facts, body_text = _render(normalized)
    if len(body_text) > MAX_BODY_SCALARS:
        raise SpineValidationError(
            "notification_rendering_output_too_large",
            "rendered notification exceeds 1024 Unicode scalar values",
        )

    input_preimage = {
        "derivation_version": "spine.notification-rendering-input-hash.v1",
        **_version_facts(),
        "source_input": normalized,
    }
    input_hash = hash_canonical_json(input_preimage)
    content_preimage = {
        "derivation_version": "spine.notification-rendering-content-hash.v1",
        **_version_facts(),
        "rendering_input_hash": input_hash,
        "phrase_kind": phrase_kind,
        "phrase_facts": phrase_facts,
        "body_text": body_text,
    }
    content_hash = hash_canonical_json(content_preimage)
    id_preimage = {
        "derivation_version": "spine.notification-rendering-id.v1",
        **_version_facts(),
        "attempt_id": normalized["attempt_id"],
        "rendering_input_hash": input_hash,
        "rendered_content_hash": content_hash,
    }
    rendering_id = f"notification_rendering_{hash_canonical_json(id_preimage)}"
    return NotificationRendering(
        notification_rendering_id=rendering_id,
        attempt_id=str(normalized["attempt_id"]),
        work_instance_id=str(normalized["work_instance_id"]),
        rendering_input_hash=input_hash,
        rendered_content_hash=content_hash,
        body_text=body_text,
        phrase_kind=phrase_kind,
        source_input=normalized,
        phrase_facts=phrase_facts,
        input_hash_preimage=input_preimage,
        content_hash_preimage=content_preimage,
        id_preimage=id_preimage,
    )


def normalize_rendering_source(source: object) -> dict[str, Any]:
    """Validate and normalize the closed rendering source-input object."""

    if not isinstance(source, dict):
        _source_error("rendering source must be an object")
    required = {
        "attempt_id",
        "attempted_at_utc",
        "work_instance_id",
        "notification_opportunity_id",
        "notification_intent_id",
        "item_id",
        "rendered_item_version",
        "item_type",
        "title",
        "anchor_role",
        "target_scheduled_fact",
        "display_time_basis",
        "display_timezone",
        "timezone_database_version",
        "primary_location",
    }
    optional = {
        "target_at_utc",
        "recurrence_revision_id",
        "occurrence_key",
        "occurrence_provenance_id",
        "temporal_binding_id",
        "temporal_binding_revision_id",
    }
    if set(source) - required - optional:
        _source_error(f"unsupported rendering source field: {sorted(set(source) - required - optional)[0]}")
    missing = sorted(required - set(source))
    if missing:
        _source_error(f"missing rendering source field: {missing[0]}")

    normalized = dict(source)
    for name in (
        "attempt_id",
        "work_instance_id",
        "notification_opportunity_id",
        "notification_intent_id",
        "item_id",
        "target_scheduled_fact",
        "display_timezone",
    ):
        normalized[name] = _non_empty_string(source[name], name)
    normalized["attempted_at_utc"] = _utc(source["attempted_at_utc"], "attempted_at_utc")
    normalized["rendered_item_version"] = _positive_decimal(source["rendered_item_version"], "rendered_item_version")
    item_type = source["item_type"]
    if item_type not in {"event", "task"}:
        _source_error("item_type must be event or task")
    normalized["item_type"] = item_type
    anchor_role = source["anchor_role"]
    if anchor_role not in {"event_start", "task_due"}:
        _source_error("anchor_role must be event_start or task_due")
    if (item_type, anchor_role) not in {("event", "event_start"), ("task", "task_due")}:
        _source_error("anchor_role does not match item_type")
    normalized["anchor_role"] = anchor_role
    basis = source["display_time_basis"]
    if basis not in {"local_date", "local_instant", "instant_utc"}:
        _source_error("display_time_basis is unsupported")
    normalized["display_time_basis"] = basis
    normalized["title"] = _normalized_text(source["title"], "title")

    target_at = source.get("target_at_utc")
    timezone_database_version = source["timezone_database_version"]
    if basis == "instant_utc":
        if normalized["display_timezone"] != "UTC" or timezone_database_version is not None:
            _source_error("instant_utc display authority must be UTC without a timezone database version")
        normalized["target_at_utc"] = _utc(target_at, "target_at_utc")
        _parse_utc_scheduled_fact(normalized["target_scheduled_fact"])
    elif basis == "local_instant":
        normalized["timezone_database_version"] = _non_empty_string(timezone_database_version, "timezone_database_version")
        normalized["target_at_utc"] = _utc(target_at, "target_at_utc")
        _parse_local_instant(normalized["target_scheduled_fact"])
        _display_zone(normalized["display_timezone"], normalized["timezone_database_version"])
    else:
        if target_at is not None:
            _source_error("local_date rendering forbids target_at_utc")
        normalized.pop("target_at_utc", None)
        normalized["timezone_database_version"] = _non_empty_string(timezone_database_version, "timezone_database_version")
        _parse_local_date(normalized["target_scheduled_fact"])
        _display_zone(normalized["display_timezone"], normalized["timezone_database_version"])

    for name in optional - {"target_at_utc"}:
        if name in source:
            normalized[name] = _non_empty_string(source[name], name)
    occurrence_names = {"recurrence_revision_id", "occurrence_key", "occurrence_provenance_id"}
    occurrence_present = occurrence_names & set(normalized)
    if occurrence_present and occurrence_present != occurrence_names:
        _source_error("occurrence rendering facts must be supplied together")

    location = source["primary_location"]
    if location is None:
        normalized["primary_location"] = None
    elif isinstance(location, dict) and set(location) == {
        "location_id",
        "item_location_id",
        "location_kind",
        "location_label",
    }:
        kind = location["location_kind"]
        if kind not in {"address", "place", "virtual", "relative", "unknown"}:
            _source_error("primary_location.location_kind is unsupported")
        normalized["primary_location"] = {
            "location_id": _non_empty_string(location["location_id"], "primary_location.location_id"),
            "item_location_id": _non_empty_string(location["item_location_id"], "primary_location.item_location_id"),
            "location_kind": kind,
            "location_label": _normalized_text(location["location_label"], "primary_location.location_label"),
        }
    else:
        _source_error("primary_location must be null or the closed location snapshot")
    return normalized


def _render(source: dict[str, Any]) -> tuple[str, dict[str, str], str]:
    basis = str(source["display_time_basis"])
    title = str(source["title"])
    item_type = str(source["item_type"])
    location_clause = _location_clause(source.get("primary_location"))
    facts: dict[str, str] = {
        "normalized_title": title,
        "location_clause": location_clause,
    }

    attempted = _parse_utc(str(source["attempted_at_utc"]))
    if basis == "local_date":
        zone = _display_zone(str(source["display_timezone"]), str(source["timezone_database_version"]))
        reference_date = attempted.astimezone(zone).date()
        target_date = _parse_local_date(str(source["target_scheduled_fact"]))
        label = _calendar_label(reference_date, target_date)
        facts.update(
            {
                "reference_date": reference_date.isoformat(),
                "target_date": target_date.isoformat(),
                "calendar_label": label,
            }
        )
        body = _template(item_type, "date_calendar", title, location_clause, facts)
        return "date_calendar", facts, body

    target = _parse_utc(str(source["target_at_utc"]))
    delta = int((target - attempted).total_seconds())
    facts["delta_seconds"] = str(delta)
    magnitude = abs(delta)
    if magnitude <= NEAR_NOW_SECONDS:
        phrase_kind = "now"
    elif magnitude <= RELATIVE_WINDOW_SECONDS:
        phrase_kind = "future_relative" if delta > 0 else "past_relative"
    else:
        phrase_kind = "future_calendar" if delta > 0 else "past_calendar"

    if phrase_kind.endswith("relative"):
        display_minutes = (magnitude + 30) // 60
        duration = _duration_text(display_minutes)
        facts.update({"display_minutes": str(display_minutes), "duration": duration})
    elif phrase_kind.endswith("calendar"):
        zone = UTC if basis == "instant_utc" else _display_zone(str(source["display_timezone"]), str(source["timezone_database_version"]))
        reference_local = attempted.astimezone(zone)
        target_local = target.astimezone(zone)
        target_fact = str(source["target_scheduled_fact"])
        clock_source = target_local if basis == "instant_utc" else _parse_local_instant(target_fact).replace(tzinfo=zone)
        facts.update(
            {
                "reference_date": reference_local.date().isoformat(),
                "target_date": target_local.date().isoformat(),
                "calendar_label": _calendar_label(reference_local.date(), target_local.date()),
                "clock": _clock(clock_source),
            }
        )
    body = _template(item_type, phrase_kind, title, location_clause, facts)
    return phrase_kind, facts, body


def _template(item_type: str, phrase_kind: str, title: str, location: str, facts: dict[str, str]) -> str:
    if phrase_kind not in _PHRASE_KINDS:
        raise AssertionError(phrase_kind)
    prefix = f"Reminder: {title}{location}"
    if item_type == "event":
        suffix = {
            "future_relative": f" in {facts.get('duration', '')}",
            "future_calendar": f" at {facts.get('clock', '')} {facts.get('calendar_label', '')}",
            "now": " is starting now",
            "past_relative": f" started {facts.get('duration', '')} ago",
            "past_calendar": f" started at {facts.get('clock', '')} {facts.get('calendar_label', '')}",
            "date_calendar": f" {facts.get('calendar_label', '')}",
        }[phrase_kind]
    else:
        suffix = {
            "future_relative": f" is due in {facts.get('duration', '')}",
            "future_calendar": f" is due at {facts.get('clock', '')} {facts.get('calendar_label', '')}",
            "now": " is due now",
            "past_relative": f" was due {facts.get('duration', '')} ago",
            "past_calendar": f" was due at {facts.get('clock', '')} {facts.get('calendar_label', '')}",
            "date_calendar": f" is due {facts.get('calendar_label', '')}",
        }[phrase_kind]
    return prefix + suffix


def _duration_text(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hours, remainder = divmod(minutes, 60)
    hour_text = f"{hours} hour" + ("" if hours == 1 else "s")
    if remainder == 0:
        return hour_text
    return f"{hour_text} {remainder} minute" + ("" if remainder == 1 else "s")


def _calendar_label(reference: date, target: date) -> str:
    days = (target - reference).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if 2 <= abs(days) <= 6:
        return _WEEKDAYS[target.weekday()]
    month_day = f"{_MONTHS[target.month - 1]} {target.day}"
    return f"on {month_day}" if target.year == reference.year else f"on {month_day}, {target.year:04d}"


def _clock(value: datetime) -> str:
    hour = value.hour % 12 or 12
    marker = "AM" if value.hour < 12 else "PM"
    minute = "" if value.minute == 0 else f":{value.minute:02d}"
    return f"{hour}{minute} {marker}"


def _location_clause(value: object) -> str:
    if value is None:
        return ""
    assert isinstance(value, dict)
    connector = "via" if value["location_kind"] == "virtual" else "@"
    return f" {connector} {value['location_label']}"


def _normalized_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise SpineValidationError("notification_rendering_invalid_text", f"{field} must be text")
    result = _WHITESPACE.sub(" ", value.strip())
    if not result:
        raise SpineValidationError("notification_rendering_invalid_text", f"{field} normalizes to empty")
    if any(unicodedata.category(char).startswith("C") for char in result):
        raise SpineValidationError("notification_rendering_invalid_text", f"{field} contains a control character")
    return result


def _display_zone(timezone: str, version: str) -> ZoneInfo:
    if system_timezone_database_version() != version:
        raise SpineValidationError(
            "notification_rendering_timezone_database_unavailable",
            f"pinned timezone database is unavailable: {version}",
        )
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise SpineValidationError(
            "notification_rendering_timezone_database_unavailable",
            f"display timezone is unavailable: {timezone}",
        ) from exc


def _utc(value: object, field: str) -> str:
    if not isinstance(value, str):
        _source_error(f"{field} must be a canonical UTC instant")
    try:
        parsed = _parse_utc(value)
    except ValueError:
        _source_error(f"{field} must be a canonical UTC instant")
    return parsed.strftime(_UTC_FORMAT)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.strptime(value, _UTC_FORMAT).replace(tzinfo=UTC)
    if parsed.strftime(_UTC_FORMAT) != value:
        raise ValueError(value)
    return parsed


def _parse_utc_scheduled_fact(value: str) -> datetime:
    try:
        return _parse_utc(value)
    except ValueError:
        _source_error("target_scheduled_fact is not a canonical UTC instant")


def _parse_local_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _source_error("target_scheduled_fact is not a canonical local date")
    if parsed.isoformat() != value:
        _source_error("target_scheduled_fact is not a canonical local date")
    return parsed


def _parse_local_instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _source_error("target_scheduled_fact is not a canonical local instant")
    if parsed.tzinfo is not None or parsed.isoformat(timespec="seconds") != value:
        _source_error("target_scheduled_fact is not a canonical local instant")
    return parsed


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        _source_error(f"{field} must be a non-empty string")
    return value


def _positive_decimal(value: object, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
        _source_error(f"{field} must be a canonical positive decimal string")
    return value


def _source_error(message: str) -> None:
    raise SpineValidationError("notification_rendering_source_unresolved", message)


def _version_facts() -> dict[str, str]:
    return {
        "rendering_contract": RENDERING_CONTRACT,
        "rendering_profile": RENDERING_PROFILE,
        "input_normalization_version": INPUT_NORMALIZATION_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
    }


def _location_fact(source: dict[str, Any], name: str) -> str | None:
    location = source.get("primary_location")
    return None if location is None else str(location[name])
