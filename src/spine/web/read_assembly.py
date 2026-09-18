"""Private, bounded occurrence/agenda assembly. No release fence or public cursors.

All rows are prepared before pagination. These objects must never be serialized as
HTTP results: the service still owes fresh authorization/source checks and cursors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from spine.commands.core import (
    _agenda_ordering_tuple,
    _agenda_recurrence_range,
    _agenda_resolve_anchor,
    _agenda_resolve_boundary,
    _decorate_occurrence,
    _occurrence_ordering_tuple,
)
from spine.core.errors import SpineValidationError
from spine.core.occurrences import expand_recurrence_set
from spine.core.schedule import validate_range, validate_timezone_context
from spine.ledger.recurrence import load_current_recurrence_set
from spine.web.read_context import ReadSnapshot
from spine.web.read_contracts import READ_API, read_error
from spine.web.read_projection import UNAVAILABLE_TIME, candidate_ids, core, project_anchor
from spine.web.read_sections import SectionAssembly, assemble_sections


@dataclass
class OccurrenceAssembly:
    activity: dict[str, Any]
    occurrences: list[dict[str, Any]]
    coverage: str


@dataclass
class AgendaAssembly:
    entries: list[dict[str, Any]]
    unplaced_items: list[dict[str, Any]]
    coverage: str
    # Optional sections retain their fully authorized evidence for later snapshot hashing.
    sections: dict[str, dict[str, SectionAssembly]]


def _request(snapshot: ReadSnapshot, route: str, request: dict[str, Any]) -> dict[str, Any]:
    normalized, _ = snapshot.contracts.normalize(route, {"contract_version": READ_API, "request": request})
    if "cursor" in request or "section_cursors" in request:
        raise read_error("invalid_request")  # Continuation belongs to the later service, never silently ignored.
    return normalized["request"]


def temporal_item(snapshot: ReadSnapshot, activity: dict[str, Any]) -> dict[str, Any]:
    """Minimal canonical decorator input; never hydrate policies, roles or followers."""
    kind = activity["item_type"]
    detail = dict(
        snapshot.db.execute(
            f"SELECT * FROM {kind}_details WHERE item_id=? AND version=?",
            (activity["item_id"], activity["current_version"]),
        ).fetchone()
    )
    roles = {"event_start": "start_anchor", "event_end": "end_anchor", "task_due": "due_anchor", "task_defer_until": "defer_until_anchor"}
    for anchor in activity["time"].get("anchors", []):
        detail[roles[anchor["anchor_role"]]] = anchor
    return {**activity, "version": {"title": activity["title"]}, "detail": detail}


def _expanded(snapshot, activity, recurrence, start, end, basis):
    item = temporal_item(snapshot, activity)
    values = []
    for raw in expand_recurrence_set(recurrence, range_start=start, range_end=end, range_basis=basis).occurrences:
        snapshot.budget.check()
        title = raw.get("common_detail_patch", {}).get("title", activity["title"])
        decorated = _decorate_occurrence(item, recurrence, dict(raw))
        kind = activity["item_type"]
        detail = decorated[f"occurrence_{kind}_detail"]
        fields = (
            (("event_start", "start_anchor"), ("event_end", "end_anchor"))
            if kind == "event"
            else (("task_due", "due_anchor"), ("task_defer_until", "defer_until_anchor"))
        )
        anchors = [
            project_anchor({**detail[field], "timezone_database_version": recurrence.get("timezone_database_version")}, role)
            for role, field in fields
            if detail.get(field) is not None
        ]
        lifecycle = {"scheduled": "active", "open": "active", "done": "completed", "cancelled": "cancelled"}[detail[f"{kind}_status"]]
        value = {
            k: decorated[k]
            for k in ("occurrence_id", "occurrence_key", "original_scheduled_fact", "expressed_scheduled_fact", "expressed_schedule_key")
        }
        value.update({k: activity[k] for k in ("item_id", "item_type", "current_version")})
        value.update({k: recurrence[k] for k in ("recurrence_set_id", "recurrence_revision_id", "source_item_version")})
        value.update(
            title=title,
            lifecycle=lifecycle,
            actionable=decorated["actionable"],
            range_basis=basis,
            time={"availability": "available", "anchors": anchors},
        )
        snapshot.contracts.validate("trusted-web-read-types.schema.json", value, definition="occurrence", output=True)
        snapshot.budget.charge(value)
        values.append((value, bool(detail.get("all_day", recurrence["time_basis"] == "local_date"))))
    values.sort(key=lambda v: _occurrence_ordering_tuple(v[0], basis))
    return values


def assemble_occurrences(snapshot: ReadSnapshot, request: dict[str, Any], *, guards=None) -> OccurrenceAssembly:
    request = _request(snapshot, "item.occurrences", request)
    activity = core(snapshot, request["item_id"], guards=guards)
    if activity["recurrence"] is None:
        raise read_error("domain_failure")
    recurrence = load_current_recurrence_set(snapshot.db, item_id=activity["item_id"])
    try:
        validate_range(request["range_start"], request["range_end"], time_basis=recurrence["time_basis"])
    except SpineValidationError as exc:
        raise read_error("invalid_request") from exc
    if activity["time"]["availability"] != "available":
        return OccurrenceAssembly(activity, [], "incomplete")
    try:
        values = _expanded(snapshot, activity, recurrence, request["range_start"], request["range_end"], request["range_basis"])
    except (SpineValidationError, ValueError, KeyError, TypeError):
        activity = {**activity, "time": dict(UNAVAILABLE_TIME)}
        return OccurrenceAssembly(activity, [], "incomplete")
    return OccurrenceAssembly(activity, [v[0] for v in values], "complete")


def _entry(snapshot, activity, occurrence, all_day, start, end, request):
    anchors = {a["anchor_role"]: a for a in activity["time"]["anchors"]}
    role = "event_start" if activity["item_type"] == "event" else "task_due"
    if role not in anchors:
        return None
    args = dict(
        range_start=start, range_end=end, view_timezone=request["timezone"], view_timezone_version=request["timezone_database_version"]
    )
    # Projected local windows already carry canonical resolved UTC bounds.
    anchor = anchors[role]
    if anchor["anchor_kind"] == "local_window":
        anchor = {**anchor, "anchor_kind": "utc_window"}
    resolved = _agenda_resolve_anchor(anchor, **args)
    if resolved is None:
        return None
    end_at = resolved.get("end_at_utc")
    if "event_end" in anchors:
        end_anchor = anchors["event_end"]
        if end_anchor["anchor_kind"] == "local_window":
            end_anchor = {**end_anchor, "anchor_kind": "utc_window"}
        end_value = _agenda_resolve_anchor(end_anchor, **args, require_overlap=False)
        if end_value is None:
            raise ValueError("unresolved end")
        end_at = end_value["start_at_utc"]
    view = datetime.fromisoformat(resolved["start_at_utc"]).astimezone(ZoneInfo(request["timezone"]))
    return {
        "activity": activity,
        "occurrence": occurrence,
        "anchor_role": role,
        "view_local_date": view.date().isoformat(),
        "view_local_time": view.strftime("%H:%M:%S"),
        "all_day": all_day,
        "sort_at_utc": resolved["start_at_utc"],
        "start_at_utc": resolved["start_at_utc"],
        "end_at_utc": end_at,
    }


def assemble_agenda(snapshot: ReadSnapshot, request: dict[str, Any]) -> AgendaAssembly:
    request = _request(snapshot, "agenda", request)
    # Explicit root admission precedes optional work, range resolution or expansion.
    activities = [core(snapshot, identity) for identity in candidate_ids(snapshot, request)]
    try:
        validate_timezone_context(
            time_basis="local_instant", timezone=request["timezone"], timezone_database_version=request["timezone_database_version"]
        )
        start, end = (
            _agenda_resolve_boundary(
                request[field], field=field, timezone=request["timezone"], timezone_database_version=request["timezone_database_version"]
            )
            for field in ("range_start_local", "range_end_local")
        )
        if end <= start or (
            datetime.fromisoformat(request["range_end_local"]) - datetime.fromisoformat(request["range_start_local"])
        ) > timedelta(days=31):
            raise ValueError("invalid range")
    except (SpineValidationError, ValueError) as exc:
        raise read_error("invalid_request") from exc
    entries, unplaced = [], []
    for activity in activities:
        if activity["status"] == "archived":
            continue
        if activity["time"]["availability"] == "not_scheduled":
            continue
        if activity["time"]["availability"] == "unavailable":
            unplaced.append({"activity": activity})
            continue
        try:
            staged = []
            if activity["recurrence"] is not None:
                recurrence = load_current_recurrence_set(snapshot.db, item_id=activity["item_id"])
                # Validate pinned source data before the engine's zone conversion.
                validate_timezone_context(
                    time_basis=recurrence["time_basis"],
                    timezone=recurrence.get("timezone"),
                    timezone_database_version=recurrence.get("timezone_database_version"),
                )
                lo, hi = _agenda_recurrence_range(recurrence, range_start=start, range_end=end)
                for occurrence, all_day in _expanded(snapshot, activity, recurrence, lo, hi, "expressed_time"):
                    if not request["include_terminal"] and occurrence["lifecycle"] != "active":
                        continue
                    entry = _entry(snapshot, {**activity, "time": occurrence["time"]}, occurrence, all_day, start, end, request)
                    if entry is not None:
                        staged.append(entry)
            else:
                detail = temporal_item(snapshot, activity)["detail"]
                all_day = bool(detail.get("all_day", activity["time"]["anchors"][0]["anchor_kind"] in {"local_date", "local_window"}))
                entry = _entry(snapshot, activity, None, all_day, start, end, request)
                if entry is not None:
                    staged.append(entry)
            for entry in staged:
                snapshot.budget.charge(entry)
            entries.extend(staged)
        except (SpineValidationError, ValueError, KeyError, TypeError):
            unplaced.append({"activity": {**activity, "time": dict(UNAVAILABLE_TIME)}})
    entries.sort(
        key=lambda e: _agenda_ordering_tuple(
            {**e, "item_id": e["activity"]["item_id"], "occurrence_key": (e["occurrence"] or {}).get("occurrence_key", "")}
        )
    )
    unplaced.sort(key=lambda e: e["activity"]["item_id"])
    sections = {}
    # Finish every root first: optional failures cannot hide a later root denial.
    for value in entries + unplaced:
        activity = value["activity"]
        identity = activity["item_id"]
        if identity not in sections:
            sections[identity] = assemble_sections(snapshot, identity, request["include"], agenda=True)
        value["sections"] = {name: section.complete_value() for name, section in sections[identity].items()}
        snapshot.contracts.validate(
            "trusted-web-read-types.schema.json",
            value,
            definition="agenda_entry" if "occurrence" in value else "unplaced_item",
            output=True,
        )
    return AgendaAssembly(entries, unplaced, "incomplete" if unplaced else "complete", sections)
