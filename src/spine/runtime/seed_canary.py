"""Seed a controlled Spine canary reminder."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence

from spine.adapters import build_openclaw_outbound_message
from spine.ledger import (
    NotificationPolicyInput,
    TemporalAnchorInput,
    connect,
    create_task_v1,
    get_work_instance,
    initialize_schema,
)
from spine.ledger.common import require_utc_z, utc_z_from_datetime
from spine.services import generate_notification_reminder_work

DEFAULT_CANARY_PREFIX = "operator-canary"


def seed_canary_reminder(
    connection: sqlite3.Connection,
    *,
    target_ref: str,
    title: str,
    prefix: str = DEFAULT_CANARY_PREFIX,
    now_utc: str | None = None,
    eligible_at_utc: str | None = None,
    if_absent: bool = False,
) -> dict[str, object]:
    """Seed a controlled canary reminder and return its predicted OpenClaw envelope."""

    now_utc = now_utc or utc_z_from_datetime(datetime.now(UTC))
    eligible_at_utc = eligible_at_utc or now_utc
    _require_non_empty("target_ref", target_ref)
    require_utc_z("now_utc", now_utc)
    require_utc_z("eligible_at_utc", eligible_at_utc)
    ids = _canary_ids(prefix)

    initialize_schema(connection)
    existing_work = _work_exists(connection, ids["work_instance_id"])
    if existing_work and not if_absent:
        raise SystemExit(f"canary work already exists: {ids['work_instance_id']}; pass --if-absent to reuse it")
    if existing_work:
        work = get_work_instance(connection, ids["work_instance_id"])
        seeded = False
    else:
        _insert_canary_subject(connection, subject_id=target_ref, created_at_utc=now_utc)
        create_task_v1(
            connection,
            item_id=ids["item_id"],
            audit_id=ids["audit_id"],
            created_at_utc=now_utc,
            created_by_subject_id=target_ref,
            title=title,
            summary="Controlled Spine/OpenClaw canary reminder.",
            notification_policies=(
                NotificationPolicyInput(
                    policy_id=ids["policy_id"],
                    recipient_subject_id=target_ref,
                    trigger_anchor=TemporalAnchorInput(
                        anchor_id=ids["anchor_id"],
                        anchor_kind="instant_utc",
                        utc_instant=eligible_at_utc,
                    ),
                ),
            ),
        )
        generate_notification_reminder_work(
            connection,
            work_instance_id=ids["work_instance_id"],
            notification_policy_id=ids["policy_id"],
            eligible_at_utc=eligible_at_utc,
            created_at_utc=now_utc,
        )
        work = get_work_instance(connection, ids["work_instance_id"])
        seeded = True

    preview = _predicted_openclaw_envelope(
        connection,
        work,
        trace_id=f"{prefix}-preview",
        causation_id=f"ROOT:{prefix}-preview",
        created_at_utc=now_utc,
    )
    return {
        **ids,
        "target_ref": target_ref,
        "title": title,
        "eligible_at_utc": eligible_at_utc,
        "seeded": seeded,
        "work_status": work["status"],
        "attempt_count": work["attempt_count"],
        "predicted_openclaw_envelope": preview,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    try:
        result = seed_canary_reminder(
            connection,
            target_ref=args.target_ref,
            title=args.title,
            prefix=args.prefix,
            now_utc=args.now_utc,
            eligible_at_utc=args.eligible_at_utc,
            if_absent=args.if_absent,
        )
    finally:
        connection.close()

    payload = {"database": str(db_path), **result}
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _canary_ids(prefix: str) -> dict[str, str]:
    _require_identifier("prefix", prefix)
    return {
        "item_id": f"{prefix}-task",
        "audit_id": f"{prefix}-audit-task-v1",
        "policy_id": f"{prefix}-policy",
        "anchor_id": f"{prefix}-anchor",
        "work_instance_id": f"{prefix}-work",
    }


def _require_identifier(name: str, value: str) -> None:
    if not value or any(character.isspace() for character in value):
        raise SystemExit(f"{name} must be non-empty and contain no whitespace")


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise SystemExit(f"{name} must be non-empty")


def _insert_canary_subject(connection: sqlite3.Connection, *, subject_id: str, created_at_utc: str) -> None:
    with connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO subjects (
              subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
            )
            VALUES (?, 'person', ?, 'active', ?, ?)
            """,
            (subject_id, subject_id, created_at_utc, created_at_utc),
        )


def _work_exists(connection: sqlite3.Connection, work_instance_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM work_instances WHERE work_instance_id = ?",
        (work_instance_id,),
    ).fetchone()
    return row is not None


def _predicted_openclaw_envelope(
    connection: sqlite3.Connection,
    work: Mapping[str, object],
    *,
    trace_id: str,
    causation_id: str,
    created_at_utc: str,
) -> dict[str, str]:
    preview_work = dict(work)
    preview_work["attempt_count"] = int(preview_work["attempt_count"]) + 1
    return build_openclaw_outbound_message(
        connection,
        work_row=preview_work,
        trace_id=trace_id,
        causation_id=causation_id,
        created_at_utc=created_at_utc,
    ).request_envelope()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a controlled Spine/OpenClaw canary reminder.")
    parser.add_argument("db_path", help="Path to the Spine SQLite ledger.")
    parser.add_argument("--target-ref", required=True, help="OpenClaw target reference that will become gateway param `to`.")
    parser.add_argument("--title", required=True, help="Task title used to build the reminder body.")
    parser.add_argument("--prefix", default=DEFAULT_CANARY_PREFIX, help="Stable ID prefix for the canary rows.")
    parser.add_argument("--now-utc", help="Creation timestamp. Defaults to current UTC.")
    parser.add_argument("--eligible-at-utc", help="Eligibility timestamp. Defaults to now-utc.")
    parser.add_argument("--if-absent", action="store_true", help="Reuse the canary if its work row already exists.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
