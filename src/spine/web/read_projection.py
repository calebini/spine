"""Private authorized core/time assembly, not a release-ready web response."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.schedule import parse_scheduled_fact, resolve_local_instant, validate_timezone_context
from spine.ledger.recurrence import load_current_recurrence_header
from spine.ledger.temporal_bindings import active_binding_for_target, binding_state
from spine.web.errors import WebError
from spine.web.read_context import ReadSnapshot
from spine.web.read_contracts import read_error

UNAVAILABLE_TIME = {"availability": "unavailable", "reason_code": "temporal_facts_unavailable"}


def candidate_ids(snapshot: ReadSnapshot, request: dict[str, Any]) -> list[str]:
    """Select authorized roots before type/lifecycle filtering or time expansion.

    This is the full bounded candidate set, not a page; caller applies the v2 stream
    protocol later. Explicit IDs are all admitted even when a filter would omit one.
    No relationship or binding graph participates in discovery.
    """
    db, p = snapshot.db, snapshot.permissions
    if "item_ids" in request:
        identities = request["item_ids"]
        for identity in identities:
            p.item(identity)
    else:
        groups = sorted(p.groups)
        marks = ",".join("?" for _ in groups) or "NULL"
        grant_tail = """
            JOIN item_access_owners a ON a.item_id=g.resource_id AND a.current_revision=g.resource_owner_revision
            WHERE g.resource_kind='item' AND g.status='active' AND g.starts_at_utc<=?
              AND (g.ends_at_utc IS NULL OR g.ends_at_utc>?)
              AND EXISTS (SELECT 1 FROM access_grant_operations o
                WHERE o.grant_id=g.grant_id AND o.revision=g.current_revision AND o.operation IN ('item.read','item.edit'))
        """
        identities = [row[0] for row in db.execute(
            f"""SELECT item_id FROM item_access_owners WHERE owner_subject_id=?
            UNION SELECT item_id FROM item_access_owners WHERE owner_group_id IN ({marks})
            UNION SELECT g.resource_id FROM access_grants g INDEXED BY access_grants_subject
              {grant_tail} AND g.grantee_subject_id=?
            UNION SELECT g.resource_id FROM access_grants g INDEXED BY access_grants_group
              {grant_tail} AND g.grantee_group_id IN ({marks})
            ORDER BY item_id""",
            (p.subject, *groups, p.now, p.now, p.subject, p.now, p.now, *groups),
        )]
    selected = []
    for identity in identities:
        snapshot.budget.check()
        row = db.execute(
            """SELECT i.item_type,i.status,e.event_status,t.task_status FROM coordination_items i
            LEFT JOIN event_details e ON e.item_id=i.item_id AND e.version=i.current_version
            LEFT JOIN task_details t ON t.item_id=i.item_id AND t.version=i.current_version WHERE i.item_id=?""",
            (identity,),
        ).fetchone()
        if row is None or row["item_type"] not in request.get("item_types", ["event", "task"]):
            continue
        if not request.get("include_terminal", False) and (
            row["status"] != "active" or row["event_status"] == "cancelled" or row["task_status"] in {"done", "cancelled"}
        ):
            continue
        selected.append(identity)
    return sorted(selected)


def core(snapshot: ReadSnapshot, item_id: str, *, guards: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble a closed core in the caller's snapshot; no followers, hydration or writes.

    Caller must still collect authorized proof facts and perform the release fence.
    Do not expose this function directly as an HTTP/CLI read endpoint.
    """
    snapshot.permissions.item(item_id)  # Before any existence/version disclosure.
    guards = guards or {}
    if "expected_access_epoch" in guards and guards["expected_access_epoch"] != str(snapshot.permissions.identity["access_epoch"]):
        raise read_error("access_changed")
    db = snapshot.db
    row = db.execute(
        """SELECT i.item_id,i.item_type,i.current_version,i.status,v.title
        FROM coordination_items i JOIN coordination_item_versions v
        ON v.item_id=i.item_id AND v.version=i.current_version WHERE i.item_id=?""", (item_id,),
    ).fetchone()
    if row is None:
        raise read_error("admission_unavailable")
    if row["item_type"] not in {"event", "task"}:
        raise read_error("resource_unavailable")
    kind = row["item_type"]
    table = "event_details" if kind == "event" else "task_details"
    detail = db.execute(f"SELECT * FROM {table} WHERE item_id=? AND version=?", (item_id, row["current_version"])).fetchone()
    if detail is None:
        raise read_error("admission_unavailable")
    recurrence = load_current_recurrence_header(db, item_id=item_id)
    recurrence_value = None if recurrence is None else {
        "recurrence_set_id": recurrence["recurrence_set_id"],
        "recurrence_revision_id": recurrence["recurrence_revision_id"],
        "source_item_version": str(recurrence["source_item_version"]),
    }
    for field, actual in (
        ("expected_item_version", str(row["current_version"])),
        ("expected_recurrence_revision_id", None if recurrence_value is None else recurrence_value["recurrence_revision_id"]),
    ):
        if field in guards and guards[field] != actual:
            raise read_error("version_changed")
    value = {
        "item_id": item_id, "item_type": kind, "current_version": str(row["current_version"]),
        "title": row["title"], "status": row["status"], "detail_status": detail[kind + "_status"],
        "time": _time(snapshot, item_id, kind, dict(detail)), "recurrence": recurrence_value,
    }
    snapshot.contracts.validate("trusted-web-read-types.schema.json", value, definition="core", output=True)
    snapshot.budget.charge(value)
    return value


def _time(snapshot: ReadSnapshot, item_id: str, kind: str, detail: dict[str, Any]) -> dict[str, Any]:
    try:
        if kind == "task":
            binding = active_binding_for_target(snapshot.db, item_id=item_id)
            if binding is not None and binding["binding_mode"] == "follow_source":
                # Authorize the source BEFORE resolving/reading its temporal evidence.
                snapshot.permissions.item(str(binding["source_item_id"]))
                state, _ = binding_state(snapshot.db, binding)
                if state != "current":
                    return dict(UNAVAILABLE_TIME)
        fields = (("event_start", "start_anchor_id"), ("event_end", "end_anchor_id")) if kind == "event" else (
            ("task_due", "due_anchor_id"), ("task_defer_until", "defer_until_anchor_id"),
        )
        if kind == "event" and detail["start_anchor_id"] is None:
            return dict(UNAVAILABLE_TIME)
        anchors = []
        for role, field in fields:
            if detail[field] is None:
                continue
            row = snapshot.db.execute("SELECT * FROM temporal_anchors WHERE anchor_id=?", (detail[field],)).fetchone()
            if row is None:
                return dict(UNAVAILABLE_TIME)
            value = project_anchor(dict(row), role)
            snapshot.contracts.validate("trusted-web-read-types.schema.json", value, definition="anchor")
            anchors.append(value)
        return {"availability": "available", "anchors": anchors} if anchors else {"availability": "not_scheduled"}
    except WebError as exc:
        if exc.code not in {"resource_unavailable", "invalid_request"}:
            raise
        return dict(UNAVAILABLE_TIME)
    except (SpineValidationError, ValueError, KeyError, TypeError):
        return dict(UNAVAILABLE_TIME)


def project_anchor(anchor: dict[str, Any], role: str) -> dict[str, Any]:
    """Canonical resolution into the closed public allowlist; never provenance IDs."""
    kind = anchor["anchor_kind"]
    value = {"anchor_role": role, "anchor_kind": kind}
    if kind in {"local_date", "local_instant", "local_window"}:
        zone, version = anchor.get("timezone"), anchor.get("timezone_database_version")
        validate_timezone_context(time_basis="local_instant", timezone=zone, timezone_database_version=version)
        value.update(timezone=zone, timezone_database_version=version)
    if kind == "local_date":
        parse_scheduled_fact(anchor["local_date"], time_basis="local_date", field="local_date")
        value["local_date"] = anchor["local_date"]
    elif kind == "local_instant":
        resolution = resolve_local_instant(
            f"{anchor['local_date']}T{anchor['local_time']}", timezone=zone, timezone_database_version=version,
        )
        if resolution is None:
            raise ValueError("unresolved local time")
        value.update(local_date=anchor["local_date"], local_time=anchor["local_time"],
                     utc_instant=resolution.utc_instant, resolution_kind=resolution.resolution_kind)
    elif kind == "instant_utc":
        parse_scheduled_fact(anchor["utc_instant"], time_basis="instant_utc", field="utc_instant")
        value["utc_instant"] = anchor["utc_instant"]
    elif kind in {"utc_window", "local_window"}:
        if kind == "utc_window":
            start, end = anchor["window_start_utc"], anchor["window_end_utc"]
        else:
            # Canonical local_window means a local calendar day, not 24 elapsed hours.
            from spine.commands.core import _agenda_local_midnight, _schedule_utc_text

            local = date.fromisoformat(anchor["local_date"])
            start, end = (
                _schedule_utc_text(_agenda_local_midnight(d.isoformat(), timezone=zone, timezone_database_version=version))
                for d in (local, local + timedelta(days=1))
            )
        parse_scheduled_fact(start, time_basis="instant_utc", field="window_start_utc")
        parse_scheduled_fact(end, time_basis="instant_utc", field="window_end_utc")
        if start >= end:
            raise ValueError("non-positive window")
        value.update(window_start_utc=start, window_end_utc=end)
    else:
        raise ValueError("unsupported temporal anchor")
    return value
