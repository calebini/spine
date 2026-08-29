"""Seed a controlled Spine canary reminder."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from spine.adapters import DEFAULT_OPENCLAW_CHANNEL, build_openclaw_outbound_message
from spine.commands import CommandContext, handle
from spine.ledger import connect, get_work_instance, initialize_schema
from spine.ledger.common import require_utc_z, utc_z_from_datetime
from spine.runtime.canonical_seed import seed_canonical_notification_work

DEFAULT_CANARY_PREFIX = "operator-canary"


def seed_canary_reminder(
    connection: sqlite3.Connection,
    *,
    target_ref: str,
    title: str,
    prefix: str = DEFAULT_CANARY_PREFIX,
    now_utc: str | None = None,
    eligible_at_utc: str | None = None,
    openclaw_channel: str = DEFAULT_OPENCLAW_CHANNEL,
    if_absent: bool = False,
) -> dict[str, object]:
    """Seed a controlled canary reminder and return its predicted OpenClaw envelope."""

    now_utc = now_utc or utc_z_from_datetime(datetime.now(UTC))
    eligible_at_utc = eligible_at_utc or now_utc
    _require_non_empty("target_ref", target_ref)
    _require_non_empty("openclaw_channel", openclaw_channel)
    require_utc_z("now_utc", now_utc)
    require_utc_z("eligible_at_utc", eligible_at_utc)
    ids = _canary_ids(prefix)

    initialize_schema(connection)
    existing = _existing_canary_work(connection, prefix)
    existing_work = existing is not None
    if existing_work and not if_absent:
        raise SystemExit(f"canary work already exists: {existing['work_instance_id']}; pass --if-absent to reuse it")
    if existing_work:
        assert existing is not None
        work = get_work_instance(connection, str(existing["work_instance_id"]))
        seeded_ids = existing
        seeded = False
    else:
        _insert_canary_subject(connection, subject_id=ids["actor_subject_id"], created_at_utc=now_utc)
        context = CommandContext(ledger=connection)
        group = handle(
            "subject_group.upsert",
            {
                "command_id": f"{prefix}-group-upsert",
                "actor_subject_id": ids["actor_subject_id"],
                "group_id": ids["group_id"],
                "display_name": f"{prefix} delivery group",
                "updated_at_utc": now_utc,
            },
            context,
        )
        if not group["ok"]:
            raise RuntimeError(group)
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": f"{prefix}-target-upsert",
                "actor_subject_id": ids["actor_subject_id"],
                "delivery_target_id": ids["delivery_target_id"],
                "owner_kind": "subject_group",
                "owner_group_id": ids["group_id"],
                "channel": openclaw_channel,
                "adapter_name": "openclaw",
                "target_ref": target_ref,
                "display_name": f"{prefix} OpenClaw target",
                "updated_at_utc": now_utc,
            },
            context,
        )
        if not route["ok"]:
            raise RuntimeError(route)
        seeded_ids = seed_canonical_notification_work(
            connection,
            prefix=prefix,
            actor_subject_id=ids["actor_subject_id"],
            title=title,
            delivery_target_id=ids["delivery_target_id"],
            channel=openclaw_channel,
            recipient_kind="subject_group",
            recipient_id=ids["group_id"],
            now_utc=now_utc,
            eligible_at_utc=eligible_at_utc,
        )
        work = get_work_instance(connection, str(seeded_ids["work_instance_id"]))
        seeded = True

    preview = _predicted_openclaw_envelope(
        connection,
        work,
        trace_id=f"{prefix}-preview",
        causation_id=f"ROOT:{prefix}-preview",
        created_at_utc=now_utc,
        channel_hint=openclaw_channel,
    )
    return {
        **ids,
        **seeded_ids,
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
            openclaw_channel=args.openclaw_channel,
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
        "actor_subject_id": f"{prefix}-actor",
        "group_id": f"{prefix}-group",
        "delivery_target_id": f"{prefix}-openclaw-target",
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


def _existing_canary_work(connection: sqlite3.Connection, prefix: str) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT w.item_id, w.work_instance_id, w.notification_policy_id,
               w.notification_intent_id, w.eligible_at_utc
        FROM work_instances AS w
        JOIN notification_policies AS p ON p.policy_id = w.notification_policy_id
        WHERE p.intent_created_by_command_id = ?
        ORDER BY w.work_instance_id LIMIT 1
        """,
        (f"{prefix}-reminder-create",),
    ).fetchone()
    return dict(row) if row is not None else None


def _predicted_openclaw_envelope(
    connection: sqlite3.Connection,
    work: Mapping[str, object],
    *,
    trace_id: str,
    causation_id: str,
    created_at_utc: str,
    channel_hint: str,
) -> dict[str, str]:
    preview_work = dict(work)
    preview_work["attempt_count"] = int(preview_work["attempt_count"]) + 1
    return build_openclaw_outbound_message(
        connection,
        work_row=preview_work,
        trace_id=trace_id,
        causation_id=causation_id,
        created_at_utc=created_at_utc,
        channel_hint=channel_hint,
    ).request_envelope()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a controlled Spine/OpenClaw canary reminder.")
    parser.add_argument("db_path", help="Path to the Spine SQLite ledger.")
    parser.add_argument("--target-ref", required=True, help="OpenClaw target reference that will become gateway param `to`.")
    parser.add_argument("--title", required=True, help="Task title used to build the reminder body.")
    parser.add_argument("--prefix", default=DEFAULT_CANARY_PREFIX, help="Stable ID prefix for the canary rows.")
    parser.add_argument("--now-utc", help="Creation timestamp. Defaults to current UTC.")
    parser.add_argument("--eligible-at-utc", help="Eligibility timestamp. Defaults to now-utc.")
    parser.add_argument(
        "--openclaw-channel",
        default=DEFAULT_OPENCLAW_CHANNEL,
        help="OpenClaw gateway channel preview value. Default: whatsapp.",
    )
    parser.add_argument("--if-absent", action="store_true", help="Reuse the canary if its work row already exists.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
