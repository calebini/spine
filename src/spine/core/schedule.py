"""Pure canonical calendar scheduling primitives shared by recurrence and notifications."""

from __future__ import annotations

import calendar
import re
import struct
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from math import gcd
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError

from spine.core.errors import SpineValidationError

RECURRENCE_CONTRACT_VERSION = "spine.recurrence.contract.v1"
RECURRENCE_NORMALIZATION_VERSION = "spine.recurrence.normalization.v1"
CANONICAL_JSON_VERSION = "spine.canonical-json.v1"

MAX_DECIMAL = 2_147_483_647
MAX_RANGE_DAYS = 3_660
MAX_RANGE_SECONDS = 316_224_000

TIME_BASES = frozenset({"local_date", "local_instant", "instant_utc"})
FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WEEKDAY_INDEX = {value: index for index, value in enumerate(WEEKDAYS)}

_POSITIVE_DECIMAL = re.compile(r"^[1-9][0-9]*$")
_SIGNED_DECIMAL = re.compile(r"^-?[1-9][0-9]*$")
_LOCAL_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_LOCAL_INSTANT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$")
_UTC_INSTANT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


@dataclass(frozen=True)
class CanonicalRule:
    """One normalized recurrence/local-calendar cadence rule."""

    frequency: str
    interval: int
    seed: str
    start_bound: str
    end_kind: str
    count: int | None = None
    until: str | None = None
    by_month: tuple[int, ...] = ()
    by_month_day: tuple[int, ...] = ()
    by_weekday: tuple[str, ...] = ()
    by_set_position: tuple[int, ...] = ()
    week_start: str | None = None

    def as_contract(self) -> dict[str, object]:
        end_condition: dict[str, str] = {"kind": self.end_kind}
        if self.count is not None:
            end_condition["count"] = str(self.count)
        if self.until is not None:
            end_condition["until"] = self.until
        result: dict[str, object] = {
            "frequency": self.frequency,
            "interval": str(self.interval),
            "seed": self.seed,
            "start_bound": self.start_bound,
            "end_condition": end_condition,
        }
        if self.by_month:
            result["by_month"] = [str(value) for value in self.by_month]
        if self.by_month_day:
            result["by_month_day"] = [str(value) for value in self.by_month_day]
        if self.by_weekday:
            result["by_weekday"] = list(self.by_weekday)
        if self.by_set_position:
            result["by_set_position"] = [str(value) for value in self.by_set_position]
        if self.week_start is not None:
            result["week_start"] = self.week_start
        return result


@dataclass(frozen=True)
class TimezoneResolution:
    timezone: str
    timezone_database_version: str
    resolution_kind: str
    local_datetime: str
    utc_instant: str
    offset_seconds: str

    def as_contract(self) -> dict[str, str]:
        return {
            "timezone": self.timezone,
            "timezone_database_version": self.timezone_database_version,
            "resolution_kind": self.resolution_kind,
            "local_datetime": self.local_datetime,
            "utc_instant": self.utc_instant,
            "offset_seconds": self.offset_seconds,
        }


@dataclass(frozen=True)
class RuleCandidate:
    scheduled_fact: str
    rule_local_index: str
    timezone_resolution: TimezoneResolution | None = None


@dataclass(frozen=True)
class OmittedLocalCandidate:
    scheduled_fact: str
    resolution_kind: str = "nonexistent_omitted"


@dataclass(frozen=True)
class ExpandedRule:
    candidates: tuple[RuleCandidate, ...]
    omitted_local_candidates: tuple[OmittedLocalCandidate, ...]


def normalize_rule(rule: object, *, time_basis: str, field: str = "rule") -> CanonicalRule:
    """Validate one rule and apply every selector default from the v1 contract."""

    _require_time_basis(time_basis)
    if not isinstance(rule, dict):
        _invalid(field, "must be an object")
    allowed = {
        "frequency",
        "interval",
        "seed",
        "start_bound",
        "end_condition",
        "by_month",
        "by_month_day",
        "by_weekday",
        "by_set_position",
        "week_start",
        "segment_label",
        "segment_id",
        "status",
    }
    unknown = sorted(set(rule) - allowed)
    if unknown:
        _invalid(f"{field}.{unknown[0]}", "is not supported")

    frequency = _required_token(rule, "frequency", FREQUENCIES, field)
    interval = _positive_decimal(rule.get("interval", "1"), f"{field}.interval")
    seed = _required_scheduled_fact(rule, "seed", time_basis, field)
    start_bound = _required_scheduled_fact(rule, "start_bound", time_basis, field)
    if start_bound < seed:
        _invalid(f"{field}.start_bound", "must be greater than or equal to seed")

    end_kind, count, until = _normalize_end_condition(
        rule.get("end_condition"),
        time_basis=time_basis,
        start_bound=start_bound,
        field=f"{field}.end_condition",
    )
    seed_date = _calendar_date(parse_scheduled_fact(seed, time_basis=time_basis, field=f"{field}.seed"))

    by_month = _integer_array(rule.get("by_month"), 1, 12, f"{field}.by_month")
    by_month_day = _integer_array(rule.get("by_month_day"), -31, 31, f"{field}.by_month_day", forbid_zero=True)
    by_weekday = _weekday_array(rule.get("by_weekday"), f"{field}.by_weekday")
    by_set_position = _integer_array(
        rule.get("by_set_position"),
        -366,
        366,
        f"{field}.by_set_position",
        forbid_zero=True,
    )
    week_start = rule.get("week_start")
    if week_start is not None and week_start not in WEEKDAY_INDEX:
        _invalid(f"{field}.week_start", "must be one of MO, TU, WE, TH, FR, SA, SU")

    if by_set_position and not by_weekday:
        _invalid(f"{field}.by_set_position", "requires by_weekday")
    if by_month_day and by_weekday:
        _invalid(field, "by_month_day and by_weekday are mutually exclusive")

    if frequency == "DAILY":
        if by_month or by_month_day or by_weekday or by_set_position or week_start is not None:
            _invalid(field, "DAILY forbids selector fields and week_start")
    elif frequency == "WEEKLY":
        if by_month or by_month_day or by_set_position:
            _invalid(field, "WEEKLY permits only by_weekday and week_start")
        if not by_weekday:
            by_weekday = (WEEKDAYS[seed_date.weekday()],)
        if week_start is None:
            week_start = "MO"
    elif frequency == "MONTHLY":
        if by_month or week_start is not None:
            _invalid(field, "MONTHLY forbids by_month and week_start")
        if not by_month_day and not by_weekday:
            by_month_day = (seed_date.day,)
    else:
        if week_start is not None:
            _invalid(field, "YEARLY forbids week_start")
        if not by_month:
            by_month = (seed_date.month,)
        if not by_month_day and not by_weekday:
            by_month_day = (seed_date.day,)

    return CanonicalRule(
        frequency=frequency,
        interval=interval,
        seed=seed,
        start_bound=start_bound,
        end_kind=end_kind,
        count=count,
        until=until,
        by_month=by_month,
        by_month_day=by_month_day,
        by_weekday=by_weekday,
        by_set_position=by_set_position,
        week_start=week_start,
    )


def expand_rule(
    rule: CanonicalRule | object,
    *,
    time_basis: str,
    range_start: str,
    range_end: str,
    timezone: str | None = None,
    timezone_database_version: str | None = None,
    segment_start: str | None = None,
    segment_end: str | None = None,
) -> ExpandedRule:
    """Expand one normalized rule into a bounded original candidate stream."""

    normalized = rule if isinstance(rule, CanonicalRule) else normalize_rule(rule, time_basis=time_basis)
    validate_range(range_start, range_end, time_basis=time_basis)
    _validate_timezone_context(
        time_basis=time_basis,
        timezone=timezone,
        timezone_database_version=timezone_database_version,
    )
    if segment_start is not None:
        parse_scheduled_fact(segment_start, time_basis=time_basis, field="segment_start")
    if segment_end is not None:
        parse_scheduled_fact(segment_end, time_basis=time_basis, field="segment_end")
        if segment_start is not None and segment_end <= segment_start:
            _invalid("segment_end", "must be greater than segment_start")

    lower_semantic_bound = max(value for value in (normalized.seed, normalized.start_bound, segment_start) if value is not None)
    seek_bound = max(lower_semantic_bound, range_start)
    generation_end = range_end
    if segment_end is not None and segment_end < generation_end:
        generation_end = segment_end
    if normalized.until is not None and normalized.until < generation_end:
        generation_end = normalized.until
    if (segment_end is not None and segment_end <= seek_bound) or (normalized.until is not None and normalized.until < seek_bound):
        return ExpandedRule(candidates=(), omitted_local_candidates=())

    candidates: list[RuleCandidate] = []
    omitted: list[OmittedLocalCandidate] = []
    local_index = _valid_candidate_count_between(
        normalized,
        start=lower_semantic_bound,
        end=seek_bound,
        time_basis=time_basis,
        timezone=timezone,
    )
    if normalized.count is not None and local_index >= normalized.count:
        return ExpandedRule(candidates=(), omitted_local_candidates=())
    stop_for_count = False
    for period in _active_periods(normalized, seek_bound, generation_end, time_basis):
        for scheduled_fact in _period_candidates(normalized, period, time_basis):
            if scheduled_fact >= range_end or scheduled_fact > generation_end:
                continue
            if scheduled_fact < normalized.seed or scheduled_fact < normalized.start_bound:
                continue
            if segment_start is not None and scheduled_fact < segment_start:
                continue
            if scheduled_fact < seek_bound:
                continue
            if segment_end is not None and scheduled_fact >= segment_end:
                continue
            if normalized.until is not None and scheduled_fact > normalized.until:
                continue

            if normalized.count is not None and local_index >= normalized.count:
                stop_for_count = True
                break

            resolution: TimezoneResolution | None = None
            if time_basis == "local_instant":
                assert timezone is not None
                assert timezone_database_version is not None
                resolution = resolve_local_instant(
                    scheduled_fact,
                    timezone=timezone,
                    timezone_database_version=timezone_database_version,
                )
                if resolution is None:
                    if range_start <= scheduled_fact < range_end:
                        omitted.append(OmittedLocalCandidate(scheduled_fact=scheduled_fact))
                    continue

            candidate_index = local_index
            local_index += 1
            if range_start <= scheduled_fact < range_end:
                candidates.append(
                    RuleCandidate(
                        scheduled_fact=scheduled_fact,
                        rule_local_index=str(candidate_index),
                        timezone_resolution=resolution,
                    )
                )
        if stop_for_count:
            break

    return ExpandedRule(candidates=tuple(candidates), omitted_local_candidates=tuple(omitted))


def _valid_candidate_count_between(
    rule: CanonicalRule,
    *,
    start: str,
    end: str,
    time_basis: str,
    timezone: str | None,
) -> int:
    """Count prior rule candidates without walking prior recurrence periods."""

    if end <= start:
        return 0
    nominal = _raw_nominal_count_before(rule, end, time_basis) - _raw_nominal_count_before(rule, start, time_basis)
    if time_basis != "local_instant":
        return nominal
    assert timezone is not None
    omitted = 0
    for gap_start, gap_end in _nonexistent_local_ranges(timezone, start=start, end=end):
        overlap_start = max(start, gap_start)
        overlap_end = min(end, gap_end)
        if overlap_start < overlap_end:
            omitted += _raw_nominal_count_before(rule, overlap_end, time_basis)
            omitted -= _raw_nominal_count_before(rule, overlap_start, time_basis)
    return nominal - omitted


def _raw_nominal_count_before(rule: CanonicalRule, bound: str, time_basis: str) -> int:
    """Count selector candidates in active periods before one exclusive bound."""

    seed_value = parse_scheduled_fact(rule.seed, time_basis=time_basis, field="rule.seed")
    bound_value = parse_scheduled_fact(bound, time_basis=time_basis, field="bound")
    seed_date = _calendar_date(seed_value)
    bound_date = _calendar_date(bound_value)
    seed_clock = _clock_time(seed_value)

    if rule.frequency == "DAILY":
        delta = (bound_date - seed_date).days
        if delta < 0:
            return 0
        count = delta // rule.interval + 1
        last_date = seed_date + timedelta(days=(count - 1) * rule.interval)
        if _format_scheduled_fact(last_date, seed_clock, time_basis) >= bound:
            count -= 1
        return max(0, count)

    if rule.frequency == "WEEKLY":
        assert rule.week_start is not None
        week_start = WEEKDAY_INDEX[rule.week_start]
        base_week = seed_date - timedelta(days=(seed_date.weekday() - week_start) % 7)
        step_days = rule.interval * 7
        total = 0
        for token in rule.by_weekday:
            first_date = base_week + timedelta(days=(WEEKDAY_INDEX[token] - week_start) % 7)
            delta = (bound_date - first_date).days
            if delta < 0:
                continue
            count = delta // step_days + 1
            last_date = first_date + timedelta(days=(count - 1) * step_days)
            if _format_scheduled_fact(last_date, seed_clock, time_basis) >= bound:
                count -= 1
            total += max(0, count)
        return total

    if rule.frequency == "MONTHLY":
        seed_month = seed_date.year * 12 + seed_date.month - 1
        bound_month = bound_date.year * 12 + bound_date.month - 1
        difference = bound_month - seed_month
        if difference < 0:
            return 0
        full_periods = (difference + rule.interval - 1) // rule.interval
        total = _sum_repeating_counts(_monthly_cycle_counts(rule), full_periods)
        if difference % rule.interval == 0:
            total += sum(
                _format_scheduled_fact(candidate, seed_clock, time_basis) < bound
                for candidate in _monthly_candidates(bound_date.year, bound_date.month, rule)
            )
        return total

    difference = bound_date.year - seed_date.year
    if difference < 0:
        return 0
    full_periods = (difference + rule.interval - 1) // rule.interval
    total = _sum_repeating_counts(_yearly_cycle_counts(rule), full_periods)
    if difference % rule.interval == 0:
        total += sum(
            _format_scheduled_fact(candidate, seed_clock, time_basis) < bound for candidate in _yearly_candidates(bound_date.year, rule)
        )
    return total


def _sum_repeating_counts(cycle: tuple[int, ...], periods: int) -> int:
    if periods <= 0:
        return 0
    cycles, remainder = divmod(periods, len(cycle))
    return cycles * sum(cycle) + sum(cycle[:remainder])


@lru_cache(maxsize=512)
def _monthly_cycle_counts(rule: CanonicalRule) -> tuple[int, ...]:
    seed = parse_scheduled_fact(rule.seed, time_basis=_rule_time_basis(rule.seed), field="rule.seed")
    seed_date = _calendar_date(seed)
    seed_month = seed_date.year * 12 + seed_date.month - 1
    cycle_length = 4_800 // gcd(rule.interval, 4_800)
    counts: list[int] = []
    for index in range(cycle_length):
        year, month_zero = divmod(seed_month + index * rule.interval, 12)
        equivalent_year = 2_000 + year % 400
        counts.append(len(_monthly_candidates(equivalent_year, month_zero + 1, rule)))
    return tuple(counts)


@lru_cache(maxsize=512)
def _yearly_cycle_counts(rule: CanonicalRule) -> tuple[int, ...]:
    seed = parse_scheduled_fact(rule.seed, time_basis=_rule_time_basis(rule.seed), field="rule.seed")
    seed_year = _calendar_date(seed).year
    cycle_length = 400 // gcd(rule.interval, 400)
    return tuple(len(_yearly_candidates(2_000 + (seed_year + index * rule.interval) % 400, rule)) for index in range(cycle_length))


def _yearly_candidates(year: int, rule: CanonicalRule) -> list[date]:
    dates: list[date] = []
    for month in rule.by_month:
        dates.extend(_monthly_candidates(year, month, rule, apply_positions=False))
    return _apply_positions(sorted(set(dates)), rule.by_set_position)


def _rule_time_basis(seed: str) -> str:
    if seed.endswith("Z"):
        return "instant_utc"
    return "local_instant" if "T" in seed else "local_date"


def _nonexistent_local_ranges(timezone: str, *, start: str, end: str) -> tuple[tuple[str, str], ...]:
    zone = _timezone(timezone)
    explicit, has_future_rules = _tzif_transition_data(timezone)
    if not explicit and not has_future_rules:
        return ()
    parsed_start = parse_scheduled_fact(start, time_basis="local_instant", field="start")
    parsed_end = parse_scheduled_fact(end, time_basis="local_instant", field="end")
    assert isinstance(parsed_start, datetime) and isinstance(parsed_end, datetime)
    probe_start = parsed_start.replace(tzinfo=zone, fold=0).astimezone(UTC)
    probe_end = parsed_end.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if probe_start > datetime.min.replace(tzinfo=UTC) + timedelta(days=2):
        probe_start -= timedelta(days=2)
    if probe_end < datetime.max.replace(tzinfo=UTC) - timedelta(days=2):
        probe_end += timedelta(days=2)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    transitions = [epoch + timedelta(seconds=value) for value in explicit if probe_start <= epoch + timedelta(seconds=value) < probe_end]
    if has_future_rules and (not explicit or probe_end > epoch + timedelta(seconds=explicit[-1])):
        scan_start = probe_start
        if explicit:
            scan_start = max(scan_start, epoch + timedelta(seconds=explicit[-1]) + timedelta(seconds=1))
        transitions.extend(_discover_offset_transitions(zone, start=scan_start, end=probe_end))
    transitions = sorted(set(transitions))

    gaps: list[tuple[str, str]] = []
    for transition in transitions:
        before = (transition - timedelta(seconds=1)).astimezone(zone).utcoffset()
        after = transition.astimezone(zone).utcoffset()
        if before is None or after is None or after <= before:
            continue
        gap_start = (transition + before).replace(tzinfo=None).isoformat(timespec="seconds")
        gap_end = (transition + after).replace(tzinfo=None).isoformat(timespec="seconds")
        if gap_start < end and start < gap_end:
            gaps.append((gap_start, gap_end))
    return tuple(gaps)


@lru_cache(maxsize=256)
def _tzif_transition_data(timezone: str) -> tuple[tuple[int, ...], bool]:
    for root in TZPATH:
        path = Path(root) / timezone
        try:
            data = path.read_bytes()
        except OSError:
            continue
        return _parse_tzif_transition_data(data)
    # ZoneInfo may have resolved the name from a package resource. In that
    # uncommon environment, bounded probing remains exact for installed
    # future rules and avoids making persistence depend on package internals.
    return (), True


def _parse_tzif_transition_data(data: bytes) -> tuple[tuple[int, ...], bool]:
    def header(offset: int) -> tuple[int, tuple[int, int, int, int, int, int], int]:
        if data[offset : offset + 4] != b"TZif" or len(data) < offset + 44:
            raise SpineValidationError("environment_failure:timezone_database_version", "installed TZif data is malformed")
        version = data[offset + 4]
        counts = struct.unpack(">6I", data[offset + 20 : offset + 44])
        return version, counts, offset + 44

    version, counts, body = header(0)
    isut, isstd, leap, time_count, type_count, char_count = counts
    time_size = 4
    if version != 0:
        first_size = time_count * 5 + type_count * 6 + char_count + leap * 8 + isstd + isut
        version, counts, body = header(body + first_size)
        isut, isstd, leap, time_count, type_count, char_count = counts
        time_size = 8
    if len(data) < body + time_count * time_size:
        raise SpineValidationError("environment_failure:timezone_database_version", "installed TZif data is truncated")
    if time_count:
        code = "q" if time_size == 8 else "l"
        transitions = struct.unpack(f">{time_count}{code}", data[body : body + time_count * time_size])
    else:
        transitions = ()
    block_size = time_count * time_size + time_count + type_count * 6 + char_count + leap * (time_size + 4) + isstd + isut
    tail = data[body + block_size :].strip(b"\n")
    return tuple(int(value) for value in transitions), b"," in tail


def _discover_offset_transitions(zone: ZoneInfo, *, start: datetime, end: datetime) -> list[datetime]:
    transitions: list[datetime] = []
    current = start
    current_offset = current.astimezone(zone).utcoffset()
    while current < end:
        probe = min(current + timedelta(days=7), end)
        probe_offset = probe.astimezone(zone).utcoffset()
        if probe_offset == current_offset:
            current = probe
            continue
        transition = _first_offset_change(zone, start=current, end=probe, prior_offset=current_offset)
        transitions.append(transition)
        current = transition
        current_offset = current.astimezone(zone).utcoffset()
    return transitions


def _first_offset_change(
    zone: ZoneInfo,
    *,
    start: datetime,
    end: datetime,
    prior_offset: timedelta | None,
) -> datetime:
    low = start
    high = end
    while high - low > timedelta(seconds=1):
        seconds = int((high - low).total_seconds()) // 2
        middle = low + timedelta(seconds=seconds)
        if middle.astimezone(zone).utcoffset() == prior_offset:
            low = middle
        else:
            high = middle
    return high.replace(microsecond=0)


def validate_range(range_start: str, range_end: str, *, time_basis: str) -> None:
    start = parse_scheduled_fact(range_start, time_basis=time_basis, field="range_start")
    end = parse_scheduled_fact(range_end, time_basis=time_basis, field="range_end")
    if end <= start:
        _invalid("range_end", "must be strictly greater than range_start")
    delta = end - start
    if time_basis == "instant_utc":
        if not isinstance(delta, timedelta) or delta.total_seconds() > MAX_RANGE_SECONDS:
            _invalid("range_end", "range_too_large")
    elif not isinstance(delta, timedelta) or delta > timedelta(days=MAX_RANGE_DAYS):
        _invalid("range_end", "range_too_large")


def validate_timezone_context(
    *,
    time_basis: str,
    timezone: str | None,
    timezone_database_version: str | None,
) -> None:
    """Validate one canonical schedule's timezone and pinned data version."""

    _validate_timezone_context(
        time_basis=time_basis,
        timezone=timezone,
        timezone_database_version=timezone_database_version,
    )


def parse_scheduled_fact(value: object, *, time_basis: str, field: str) -> date | datetime:
    _require_time_basis(time_basis)
    if not isinstance(value, str):
        _invalid(field, f"must be a canonical {time_basis} scheduled fact")
    try:
        if time_basis == "local_date":
            if _LOCAL_DATE.fullmatch(value) is None:
                raise ValueError
            parsed_date = date.fromisoformat(value)
            if parsed_date.isoformat() != value:
                raise ValueError
            return parsed_date
        if time_basis == "local_instant":
            if _LOCAL_INSTANT.fullmatch(value) is None:
                raise ValueError
            parsed_local = datetime.fromisoformat(value)
            if parsed_local.isoformat(timespec="seconds") != value:
                raise ValueError
            return parsed_local
        if _UTC_INSTANT.fullmatch(value) is None:
            raise ValueError
        parsed_utc = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        if parsed_utc.isoformat(timespec="seconds").removesuffix("+00:00") + "Z" != value:
            raise ValueError
        return parsed_utc
    except ValueError as exc:
        raise SpineValidationError(
            f"invalid_request:{field}",
            f"{field} must be a canonical {time_basis} scheduled fact",
        ) from exc


def resolve_local_instant(
    local_datetime: str,
    *,
    timezone: str,
    timezone_database_version: str,
) -> TimezoneResolution | None:
    """Resolve one local wall-clock value, returning None for a DST gap."""

    parsed = parse_scheduled_fact(local_datetime, time_basis="local_instant", field="local_datetime")
    assert isinstance(parsed, datetime)
    zone = _timezone(timezone)
    installed_version = system_timezone_database_version()
    if installed_version != timezone_database_version:
        raise SpineValidationError(
            "environment_failure:timezone_database_version",
            f"requested timezone database {timezone_database_version!r}; installed {installed_version!r}",
        )

    valid: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = parsed.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(UTC)
        round_trip = utc_value.astimezone(zone).replace(tzinfo=None)
        if round_trip == parsed:
            valid[utc_value] = aware
    if not valid:
        return None

    selected_utc = min(valid)
    selected = valid[selected_utc]
    offset = selected.utcoffset()
    if offset is None:
        raise SpineValidationError(
            "environment_failure:timezone_database_version",
            "timezone provider returned no UTC offset",
        )
    resolution_kind = "ambiguous_earliest_instant" if len(valid) > 1 else "unambiguous"
    return TimezoneResolution(
        timezone=timezone,
        timezone_database_version=timezone_database_version,
        resolution_kind=resolution_kind,
        local_datetime=local_datetime,
        utc_instant=selected_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        offset_seconds=str(int(offset.total_seconds())),
    )


@lru_cache(maxsize=1)
def system_timezone_database_version() -> str:
    """Return the exact IANA version advertised by the installed TZif database."""

    for root in TZPATH:
        version_file = Path(root) / "tzdata.zi"
        try:
            first_line = version_file.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError, UnicodeError):
            continue
        if first_line.startswith("# version "):
            return first_line.removeprefix("# version ").strip()
    raise SpineValidationError(
        "environment_failure:timezone_database_version",
        "installed timezone database does not expose an exact IANA version",
    )


def _active_periods(
    rule: CanonicalRule,
    lower_bound: str,
    generation_end: str,
    time_basis: str,
) -> list[date | tuple[int, int] | int]:
    seed_value = parse_scheduled_fact(rule.seed, time_basis=time_basis, field="rule.seed")
    lower_value = parse_scheduled_fact(lower_bound, time_basis=time_basis, field="lower_bound")
    end_value = parse_scheduled_fact(generation_end, time_basis=time_basis, field="generation_end")
    seed_date = _calendar_date(seed_value)
    lower_date = _calendar_date(lower_value)
    end_date = _calendar_date(end_value)

    periods: list[date | tuple[int, int] | int] = []
    if rule.frequency == "DAILY":
        first_index = max(0, (lower_date - seed_date).days // rule.interval)
        candidate = seed_date + timedelta(days=first_index * rule.interval)
        while candidate < lower_date:
            first_index += 1
            candidate = seed_date + timedelta(days=first_index * rule.interval)
        while candidate <= end_date:
            periods.append(candidate)
            if candidate >= end_date:
                break
            candidate += timedelta(days=rule.interval)
        return periods

    if rule.frequency == "WEEKLY":
        assert rule.week_start is not None
        week_start = WEEKDAY_INDEX[rule.week_start]
        base_week = seed_date - timedelta(days=(seed_date.weekday() - week_start) % 7)
        lower_week = lower_date - timedelta(days=(lower_date.weekday() - week_start) % 7)
        week_index = max(0, (lower_week - base_week).days // 7)
        if week_index % rule.interval:
            week_index += rule.interval - (week_index % rule.interval)
        candidate_week = base_week + timedelta(weeks=week_index)
        while candidate_week <= end_date:
            periods.append(candidate_week)
            if candidate_week >= end_date:
                break
            candidate_week += timedelta(weeks=rule.interval)
        return periods

    if rule.frequency == "MONTHLY":
        seed_month_index = seed_date.year * 12 + seed_date.month - 1
        lower_month_index = lower_date.year * 12 + lower_date.month - 1
        period_index = max(0, lower_month_index - seed_month_index)
        if period_index % rule.interval:
            period_index += rule.interval - (period_index % rule.interval)
        month_index = seed_month_index + period_index
        while month_index <= end_date.year * 12 + end_date.month - 1:
            periods.append(divmod(month_index, 12))
            month_index += rule.interval
        return periods

    period_index = max(0, lower_date.year - seed_date.year)
    if period_index % rule.interval:
        period_index += rule.interval - (period_index % rule.interval)
    year = seed_date.year + period_index
    while year <= end_date.year:
        periods.append(year)
        year += rule.interval
    return periods


def _period_candidates(
    rule: CanonicalRule,
    period: date | tuple[int, int] | int,
    time_basis: str,
) -> tuple[str, ...]:
    seed_value = parse_scheduled_fact(rule.seed, time_basis=time_basis, field="rule.seed")
    seed_clock = _clock_time(seed_value)
    dates: list[date]
    if rule.frequency == "DAILY":
        assert isinstance(period, date)
        dates = [period]
    elif rule.frequency == "WEEKLY":
        assert isinstance(period, date)
        assert rule.week_start is not None
        week_start = WEEKDAY_INDEX[rule.week_start]
        dates = [period + timedelta(days=(WEEKDAY_INDEX[token] - week_start) % 7) for token in rule.by_weekday]
    elif rule.frequency == "MONTHLY":
        assert isinstance(period, tuple)
        dates = _monthly_candidates(period[0], period[1] + 1, rule)
    else:
        assert isinstance(period, int)
        dates = []
        for month in rule.by_month:
            dates.extend(_monthly_candidates(period, month, rule, apply_positions=False))
        dates = _apply_positions(sorted(set(dates)), rule.by_set_position)
    return tuple(_format_scheduled_fact(value, seed_clock, time_basis) for value in sorted(set(dates)))


def _monthly_candidates(
    year: int,
    month: int,
    rule: CanonicalRule,
    *,
    apply_positions: bool = True,
) -> list[date]:
    last_day = calendar.monthrange(year, month)[1]
    candidates: list[date] = []
    if rule.by_month_day:
        for value in rule.by_month_day:
            day = value if value > 0 else last_day + value + 1
            if 1 <= day <= last_day:
                candidates.append(date(year, month, day))
    else:
        selected = {WEEKDAY_INDEX[value] for value in rule.by_weekday}
        candidates.extend(date(year, month, day) for day in range(1, last_day + 1) if date(year, month, day).weekday() in selected)
    ordered = sorted(set(candidates))
    return _apply_positions(ordered, rule.by_set_position) if apply_positions else ordered


def _apply_positions(values: list[date], positions: tuple[int, ...]) -> list[date]:
    if not positions:
        return values
    selected: set[date] = set()
    for position in positions:
        index = position - 1 if position > 0 else len(values) + position
        if 0 <= index < len(values):
            selected.add(values[index])
    return sorted(selected)


def _normalize_end_condition(
    value: object,
    *,
    time_basis: str,
    start_bound: str,
    field: str,
) -> tuple[str, int | None, str | None]:
    if not isinstance(value, dict):
        _invalid(field, "must be an object")
    kind = value.get("kind")
    if kind == "unbounded" and set(value) == {"kind"}:
        return kind, None, None
    if kind == "count" and set(value) == {"kind", "count"}:
        return kind, _positive_decimal(value.get("count"), f"{field}.count"), None
    if kind == "until" and set(value) == {"kind", "until"}:
        until = value.get("until")
        parse_scheduled_fact(until, time_basis=time_basis, field=f"{field}.until")
        assert isinstance(until, str)
        if until < start_bound:
            _invalid(f"{field}.until", "must be greater than or equal to start_bound")
        return kind, None, until
    _invalid(field, "must be exactly unbounded, count, or until")


def _integer_array(
    value: object,
    minimum: int,
    maximum: int,
    field: str,
    *,
    forbid_zero: bool = False,
) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value:
        _invalid(field, "must be a non-empty array")
    parsed: list[int] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or _SIGNED_DECIMAL.fullmatch(item) is None:
            _invalid(f"{field}[{index}]", "must be a canonical signed decimal string")
        number = int(item)
        if (forbid_zero and number == 0) or not minimum <= number <= maximum:
            _invalid(f"{field}[{index}]", f"must be in {minimum}..{maximum} excluding zero")
        parsed.append(number)
    if len(set(parsed)) != len(parsed):
        _invalid(field, "must contain unique values")
    return tuple(sorted(parsed))


def _weekday_array(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value:
        _invalid(field, "must be a non-empty array")
    if any(not isinstance(item, str) or item not in WEEKDAY_INDEX for item in value):
        _invalid(field, "contains an unsupported weekday")
    if len(set(value)) != len(value):
        _invalid(field, "must contain unique values")
    return tuple(sorted(value, key=WEEKDAY_INDEX.__getitem__))


def _required_token(value: dict[str, Any], key: str, allowed: frozenset[str], field: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or result not in allowed:
        _invalid(f"{field}.{key}", f"must be one of {', '.join(sorted(allowed))}")
    return result


def _required_scheduled_fact(value: dict[str, Any], key: str, time_basis: str, field: str) -> str:
    result = value.get(key)
    parse_scheduled_fact(result, time_basis=time_basis, field=f"{field}.{key}")
    assert isinstance(result, str)
    return result


def _positive_decimal(value: object, field: str) -> int:
    if not isinstance(value, str) or _POSITIVE_DECIMAL.fullmatch(value) is None:
        _invalid(field, "must be a canonical positive decimal string")
    parsed = int(value)
    if parsed > MAX_DECIMAL:
        _invalid(field, f"must not exceed {MAX_DECIMAL}")
    return parsed


def _validate_timezone_context(
    *,
    time_basis: str,
    timezone: str | None,
    timezone_database_version: str | None,
) -> None:
    _require_time_basis(time_basis)
    if time_basis == "instant_utc":
        if timezone is not None or timezone_database_version is not None:
            _invalid("timezone", "instant_utc forbids timezone facts")
        return
    if not isinstance(timezone, str) or not timezone:
        _invalid("timezone", "local recurrence requires timezone")
    if not isinstance(timezone_database_version, str) or not timezone_database_version:
        _invalid("timezone_database_version", "local recurrence requires timezone database version")
    _timezone(timezone)
    installed = system_timezone_database_version()
    if installed != timezone_database_version:
        raise SpineValidationError(
            "environment_failure:timezone_database_version",
            f"requested timezone database {timezone_database_version!r}; installed {installed!r}",
        )


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise SpineValidationError("invalid_request:timezone", f"unknown IANA timezone: {value}") from exc


def _require_time_basis(value: str) -> None:
    if value not in TIME_BASES:
        _invalid("time_basis", "must be local_date, local_instant, or instant_utc")


def _calendar_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _clock_time(value: date | datetime) -> time | None:
    return value.timetz().replace(tzinfo=None) if isinstance(value, datetime) else None


def _format_scheduled_fact(value: date, clock: time | None, time_basis: str) -> str:
    if time_basis == "local_date":
        return value.isoformat()
    assert clock is not None
    combined = datetime.combine(value, clock)
    if time_basis == "local_instant":
        return combined.isoformat(timespec="seconds")
    return combined.replace(tzinfo=UTC).isoformat(timespec="seconds").removesuffix("+00:00") + "Z"


def _invalid(field: str, message: str) -> NoReturn:
    raise SpineValidationError(f"invalid_request:{field}", f"{field} {message}")
