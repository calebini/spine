"""Seed a small local Spine demo ledger."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

from spine.ledger import NotificationPolicyInput, TemporalAnchorInput, connect, create_task_v1, initialize_schema
from spine.services import generate_notification_reminder_work

DEMO_NOW = "2026-06-07T10:00:00Z"
DEMO_SUBJECT_ID = "demo-subject-chris"
DEMO_TASK_ID = "demo-task-submit-forms"
DEMO_AUDIT_ID = "demo-audit-task-submit-forms-v1"
DEMO_POLICY_ID = "demo-policy-submit-forms-reminder"
DEMO_POLICY_ANCHOR_ID = "demo-anchor-submit-forms-reminder"
DEMO_WORK_INSTANCE_ID = "demo-work-submit-forms-reminder"


def seed_demo_ledger(connection: sqlite3.Connection) -> dict[str, object]:
    """Initialize and seed a deterministic demo ledger with one eligible work row."""

    initialize_schema(connection)
    _insert_demo_subject(connection)
    create_task_v1(
        connection,
        item_id=DEMO_TASK_ID,
        audit_id=DEMO_AUDIT_ID,
        created_at_utc=DEMO_NOW,
        created_by_subject_id=DEMO_SUBJECT_ID,
        title="Submit school forms",
        summary="Demo task used to show Tickerd observing eligible Spine work.",
        notification_policies=(
            NotificationPolicyInput(
                policy_id=DEMO_POLICY_ID,
                recipient_subject_id=DEMO_SUBJECT_ID,
                trigger_anchor=TemporalAnchorInput(
                    anchor_id=DEMO_POLICY_ANCHOR_ID,
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-07T09:00:00Z",
                ),
            ),
        ),
    )
    work = generate_notification_reminder_work(
        connection,
        work_instance_id=DEMO_WORK_INSTANCE_ID,
        notification_policy_id=DEMO_POLICY_ID,
        eligible_at_utc="2026-06-07T09:00:00Z",
        created_at_utc=DEMO_NOW,
    )
    return {
        "subject_id": DEMO_SUBJECT_ID,
        "item_id": DEMO_TASK_ID,
        "notification_policy_id": DEMO_POLICY_ID,
        "work_instance_id": work.work_instance_id,
        "eligible_at_utc": "2026-06-07T09:00:00Z",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db_path)
    if db_path.exists():
        raise SystemExit(f"database already exists: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    try:
        result = seed_demo_ledger(connection)
    finally:
        connection.close()

    payload = {"database": str(db_path), **result}
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _insert_demo_subject(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO subjects (
              subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
            )
            VALUES (?, 'person', 'Chris', 'active', ?, ?)
            """,
            (DEMO_SUBJECT_ID, DEMO_NOW, DEMO_NOW),
        )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a deterministic local Spine demo ledger.")
    parser.add_argument("db_path", help="Path where the demo SQLite ledger should be created.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
