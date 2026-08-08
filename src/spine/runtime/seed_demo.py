"""Seed a small local Spine demo ledger."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from spine.commands import CommandContext, handle
from spine.ledger import connect, initialize_schema
from spine.runtime.canonical_seed import seed_canonical_notification_work

DEMO_NOW = "2026-06-07T10:00:00Z"
DEMO_SUBJECT_ID = "demo-subject-chris"
DEMO_TASK_ID = "demo-task"
DEMO_DELIVERY_TARGET_ID = "demo-openclaw-target"


def seed_demo_ledger(connection: sqlite3.Connection) -> dict[str, object]:
    """Initialize and seed a deterministic demo ledger with one eligible work row."""

    initialize_schema(connection)
    context = CommandContext(ledger=connection)
    subject = handle(
        "subject.upsert",
        {
            "command_id": "demo-subject-upsert",
            "actor_subject_id": DEMO_SUBJECT_ID,
            "subject_id": DEMO_SUBJECT_ID,
            "subject_kind": "person",
            "display_name": "Chris",
            "updated_at_utc": DEMO_NOW,
        },
        context,
    )
    if not subject["ok"]:
        raise RuntimeError(subject)
    route = handle(
        "delivery_target.upsert",
        {
            "command_id": "demo-delivery-target-upsert",
            "actor_subject_id": DEMO_SUBJECT_ID,
            "delivery_target_id": DEMO_DELIVERY_TARGET_ID,
            "owner_kind": "subject",
            "owner_subject_id": DEMO_SUBJECT_ID,
            "channel": "whatsapp",
            "adapter_name": "openclaw",
            "target_ref": "demo-subject",
            "updated_at_utc": DEMO_NOW,
        },
        context,
    )
    if not route["ok"]:
        raise RuntimeError(route)
    seeded = seed_canonical_notification_work(
        connection,
        prefix="demo",
        actor_subject_id=DEMO_SUBJECT_ID,
        title="Submit school forms",
        delivery_target_id=DEMO_DELIVERY_TARGET_ID,
        channel="whatsapp",
        recipient_kind="subject",
        recipient_id=DEMO_SUBJECT_ID,
        now_utc=DEMO_NOW,
        eligible_at_utc="2026-06-07T09:00:00Z",
    )
    return {
        "subject_id": DEMO_SUBJECT_ID,
        **seeded,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db_path)
    if db_path.exists() and not args.if_absent:
        raise SystemExit(f"database already exists: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    try:
        if args.if_absent:
            initialize_schema(connection)
            if _demo_work_exists(connection):
                result = _existing_demo_result(connection)
                seeded = False
            else:
                result = seed_demo_ledger(connection)
                seeded = True
        else:
            result = seed_demo_ledger(connection)
    finally:
        connection.close()

    payload = {"database": str(db_path), **result}
    if args.if_absent:
        payload["seeded"] = seeded
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _demo_work_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM work_instances AS w
        JOIN notification_policies AS p ON p.policy_id = w.notification_policy_id
        WHERE p.intent_created_by_command_id = 'demo-reminder-create'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _existing_demo_result(connection: sqlite3.Connection) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT w.item_id, w.work_instance_id, w.eligible_at_utc, w.notification_policy_id
        FROM work_instances AS w
        JOIN notification_policies AS p ON p.policy_id = w.notification_policy_id
        WHERE p.intent_created_by_command_id = 'demo-reminder-create'
        ORDER BY w.work_instance_id LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("demo item exists without canonical notification work")
    return {
        "subject_id": DEMO_SUBJECT_ID,
        "item_id": row["item_id"],
        "notification_policy_id": row["notification_policy_id"],
        "work_instance_id": row["work_instance_id"],
        "eligible_at_utc": row["eligible_at_utc"],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a deterministic local Spine demo ledger.")
    parser.add_argument("db_path", help="Path where the demo SQLite ledger should be created.")
    parser.add_argument(
        "--if-absent",
        action="store_true",
        help="Allow an existing ledger and seed only when the deterministic demo work row is absent.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
