"""Deterministic schedule-based recurrence primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json

MAX_DAILY_INTERVAL = 366
MAX_DAILY_COUNT = 100_000
MAX_EXPANSION_DAYS = 3_660
MAX_EXPANSION_LIMIT = 366
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True)
class DailyRecurrenceRule:
    """Validated RFC 5545-compatible daily recurrence subset."""

    interval: int = 1
    count: int | None = None

    @property
    def canonical_text(self) -> str:
        parts = ["FREQ=DAILY", f"INTERVAL={self.interval}"]
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        return ";".join(parts)


@dataclass(frozen=True)
class LocalOccurrence:
    """One deterministic virtual occurrence in a local schedule."""

    occurrence_id: str
    occurrence_key: str
    ordinal: int
    local_date: str
    local_time: str | None
    timezone: str


@dataclass(frozen=True)
class ExpandedOccurrences:
    """Bounded occurrence expansion result."""

    occurrences: tuple[LocalOccurrence, ...]
    truncated: bool


def parse_daily_recurrence_rule(value: str) -> DailyRecurrenceRule:
    """Parse and validate Spine's first schedule-based recurrence subset."""

    if not isinstance(value, str) or not value:
        raise SpineValidationError("invalid_recurrence_rule", "recurrence_rule must be a non-empty string")
    if len(value) > 512 or any(character.isspace() for character in value):
        raise SpineValidationError(
            "invalid_recurrence_rule",
            "recurrence_rule must be at most 512 characters and contain no whitespace",
        )

    parts: dict[str, str] = {}
    for component in value.split(";"):
        if component.count("=") != 1:
            raise SpineValidationError(
                "invalid_recurrence_rule",
                "each recurrence_rule component must be KEY=VALUE",
            )
        key, raw = component.split("=", 1)
        key = key.upper()
        raw = raw.upper()
        if not key or not raw:
            raise SpineValidationError(
                "invalid_recurrence_rule",
                "recurrence_rule keys and values must be non-empty",
            )
        if key in parts:
            raise SpineValidationError(
                "invalid_recurrence_rule",
                f"recurrence_rule contains duplicate {key}",
            )
        parts[key] = raw

    unsupported = sorted(set(parts) - {"FREQ", "INTERVAL", "COUNT"})
    if unsupported:
        raise SpineValidationError(
            "unsupported_recurrence_rule",
            f"unsupported recurrence_rule components: {', '.join(unsupported)}",
        )
    if parts.get("FREQ") != "DAILY":
        raise SpineValidationError(
            "unsupported_recurrence_rule",
            "the current recurrence contract requires FREQ=DAILY",
        )

    interval = _positive_integer("INTERVAL", parts.get("INTERVAL", "1"), maximum=MAX_DAILY_INTERVAL)
    count = None
    if "COUNT" in parts:
        count = _positive_integer("COUNT", parts["COUNT"], maximum=MAX_DAILY_COUNT)
    return DailyRecurrenceRule(interval=interval, count=count)


def normalize_daily_recurrence_rule(value: str) -> str:
    """Return the canonical text for a valid daily recurrence rule."""

    return parse_daily_recurrence_rule(value).canonical_text


def validate_daily_local_recurrence_anchor(
    *,
    anchor_kind: str,
    local_date_value: str,
    local_time_value: str | None,
    timezone: str,
    recurrence_rule: str,
) -> str:
    """Validate one local recurrence seed and return its canonical rule."""

    if anchor_kind not in {"local_date", "local_instant"}:
        raise SpineValidationError(
            "unsupported_recurrence_anchor",
            "daily recurrence requires a local_date or local_instant anchor",
        )
    seed_date = parse_local_date("anchor.local_date", local_date_value)
    zone = parse_timezone(timezone)
    if anchor_kind == "local_instant":
        if local_time_value is None:
            raise SpineValidationError(
                "invalid_recurrence_anchor",
                "local_instant recurrence requires local_time",
            )
        seed_time = parse_local_time("anchor.local_time", local_time_value)
        if not _local_time_exists(seed_date, seed_time, zone):
            raise SpineValidationError(
                "invalid_recurrence_anchor",
                "the recurrence seed local time does not exist in its timezone",
            )
    elif local_time_value is not None:
        raise SpineValidationError(
            "invalid_recurrence_anchor",
            "local_date recurrence must not define local_time",
        )
    return normalize_daily_recurrence_rule(recurrence_rule)


def expand_daily_local_occurrences(
    *,
    item_id: str,
    anchor_kind: str,
    seed_local_date: str,
    seed_local_time: str | None,
    timezone: str,
    recurrence_rule: str,
    range_start_local_date: str,
    range_end_local_date: str,
    limit: int,
) -> ExpandedOccurrences:
    """Expand bounded local-date or local-instant daily occurrences."""

    if anchor_kind not in {"local_date", "local_instant"}:
        raise SpineValidationError(
            "unsupported_recurrence_anchor",
            "daily recurrence requires a local_date or local_instant anchor",
        )
    if not isinstance(item_id, str) or not item_id:
        raise SpineValidationError("invalid_recurrence_item", "item_id must be a non-empty string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_EXPANSION_LIMIT:
        raise SpineValidationError(
            "invalid_recurrence_limit",
            f"limit must be between 1 and {MAX_EXPANSION_LIMIT}",
        )

    seed_date = parse_local_date("seed_local_date", seed_local_date)
    range_start = parse_local_date("range_start_local_date", range_start_local_date)
    range_end = parse_local_date("range_end_local_date", range_end_local_date)
    if range_end <= range_start:
        raise SpineValidationError(
            "invalid_recurrence_range",
            "range_end_local_date must be after range_start_local_date",
        )
    if (range_end - range_start).days > MAX_EXPANSION_DAYS:
        raise SpineValidationError(
            "invalid_recurrence_range",
            f"recurrence expansion range must not exceed {MAX_EXPANSION_DAYS} days",
        )
    if (range_end - seed_date).days > MAX_EXPANSION_DAYS:
        raise SpineValidationError(
            "invalid_recurrence_range",
            f"recurrence expansion must end within {MAX_EXPANSION_DAYS} days of the schedule seed",
        )

    zone = parse_timezone(timezone)
    normalized_time: str | None = None
    parsed_time: time | None = None
    if anchor_kind == "local_instant":
        if seed_local_time is None:
            raise SpineValidationError(
                "invalid_recurrence_anchor",
                "local_instant recurrence requires local_time",
            )
        parsed_time = parse_local_time("seed_local_time", seed_local_time)
        normalized_time = parsed_time.strftime("%H:%M:%S")
        if not _local_time_exists(seed_date, parsed_time, zone):
            raise SpineValidationError(
                "invalid_recurrence_anchor",
                "the recurrence seed local time does not exist in its timezone",
            )
    elif seed_local_time is not None:
        raise SpineValidationError(
            "invalid_recurrence_anchor",
            "local_date recurrence must not define local_time",
        )

    rule = parse_daily_recurrence_rule(recurrence_rule)
    occurrences: list[LocalOccurrence] = []
    valid_ordinal = 0
    candidate_date = seed_date
    truncated = False

    while candidate_date < range_end:
        valid = parsed_time is None or _local_time_exists(candidate_date, parsed_time, zone)
        if valid:
            valid_ordinal += 1
            if rule.count is not None and valid_ordinal > rule.count:
                break
            if candidate_date >= range_start:
                if len(occurrences) == limit:
                    truncated = True
                    break
                key = occurrence_key(
                    anchor_kind=anchor_kind,
                    local_date_value=candidate_date.isoformat(),
                    local_time_value=normalized_time,
                    timezone=timezone,
                )
                occurrences.append(
                    LocalOccurrence(
                        occurrence_id=occurrence_id(item_id=item_id, occurrence_key_value=key),
                        occurrence_key=key,
                        ordinal=valid_ordinal,
                        local_date=candidate_date.isoformat(),
                        local_time=normalized_time,
                        timezone=timezone,
                    )
                )
        candidate_date += timedelta(days=rule.interval)

    return ExpandedOccurrences(occurrences=tuple(occurrences), truncated=truncated)


def occurrence_key(
    *,
    anchor_kind: str,
    local_date_value: str,
    local_time_value: str | None,
    timezone: str,
) -> str:
    """Build the stable original-schedule identity key for an occurrence."""

    if anchor_kind == "local_date":
        return f"local_date:{local_date_value}[{timezone}]"
    if anchor_kind == "local_instant" and local_time_value is not None:
        return f"local_instant:{local_date_value}T{local_time_value}[{timezone}]"
    raise SpineValidationError("invalid_recurrence_anchor", "cannot build occurrence key")


def occurrence_id(*, item_id: str, occurrence_key_value: str) -> str:
    """Derive a stable occurrence ID independent of the current item version."""

    digest = hash_canonical_json(
        {
            "item_id": item_id,
            "occurrence_key": occurrence_key_value,
        }
    )
    return f"occurrence-{digest}"


def parse_local_date(field: str, value: str) -> date:
    """Parse Spine's canonical local date."""

    if not isinstance(value, str):
        raise SpineValidationError("invalid_local_date", f"{field} must be formatted as YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SpineValidationError("invalid_local_date", f"{field} must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise SpineValidationError("invalid_local_date", f"{field} must be formatted as YYYY-MM-DD")
    return parsed


def parse_local_time(field: str, value: str) -> time:
    """Parse an HH:MM or HH:MM:SS local time."""

    if not isinstance(value, str):
        raise SpineValidationError("invalid_local_time", f"{field} must be formatted as HH:MM or HH:MM:SS")
    formats = ("%H:%M", "%H:%M:%S")
    for format_string in formats:
        try:
            return datetime.strptime(value, format_string).time()
        except ValueError:
            continue
    raise SpineValidationError("invalid_local_time", f"{field} must be a valid HH:MM or HH:MM:SS time")


def parse_timezone(value: str) -> ZoneInfo:
    """Resolve an IANA timezone or fail closed."""

    if not isinstance(value, str) or not value:
        raise SpineValidationError("invalid_timezone", "timezone must be a non-empty IANA timezone name")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise SpineValidationError("invalid_timezone", f"unknown IANA timezone: {value}") from exc


def _positive_integer(field: str, value: str, *, maximum: int) -> int:
    if _POSITIVE_INTEGER.fullmatch(value) is None:
        raise SpineValidationError(
            "invalid_recurrence_rule",
            f"{field} must be a canonical positive integer",
        )
    parsed = int(value)
    if parsed > maximum:
        raise SpineValidationError(
            "invalid_recurrence_rule",
            f"{field} must not exceed {maximum}",
        )
    return parsed


def _local_time_exists(local_date_value: date, local_time_value: time, timezone: ZoneInfo) -> bool:
    naive = datetime.combine(local_date_value, local_time_value)
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=timezone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
        if round_trip == naive:
            return True
    return False
