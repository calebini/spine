from __future__ import annotations

import sqlite3

from spine.commands import CommandContext, handle
from spine.runtime.canonical_seed import seed_canonical_notification_work


def ensure_subject_and_route(
    connection: sqlite3.Connection,
    *,
    prefix: str,
    subject_id: str,
    delivery_target_id: str,
    at_utc: str = "2026-08-01T00:00:00Z",
) -> None:
    context = CommandContext(ledger=connection)
    if connection.execute(
        "SELECT 1 FROM subjects WHERE subject_id = ?", (subject_id,)
    ).fetchone() is None:
        response = handle(
            "subject.upsert",
            {
                "command_id": f"{prefix}-subject-upsert",
                "actor_subject_id": subject_id,
                "subject_id": subject_id,
                "subject_kind": "person",
                "display_name": "Canonical test recipient",
                "updated_at_utc": at_utc,
            },
            context,
        )
        assert response["ok"], response
    if connection.execute(
        "SELECT 1 FROM delivery_targets WHERE delivery_target_id = ?",
        (delivery_target_id,),
    ).fetchone() is None:
        response = handle(
            "delivery_target.upsert",
            {
                "command_id": f"{prefix}-delivery-target-upsert",
                "actor_subject_id": subject_id,
                "delivery_target_id": delivery_target_id,
                "owner_kind": "subject",
                "owner_subject_id": subject_id,
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": f"{subject_id}+{delivery_target_id}@example",
                "updated_at_utc": at_utc,
            },
            context,
        )
        assert response["ok"], response


def seed_notification_work(
    connection: sqlite3.Connection,
    *,
    prefix: str,
    subject_id: str = "test-owner",
    delivery_target_id: str | None = None,
    now_utc: str = "2026-08-01T00:00:00Z",
    eligible_at_utc: str = "2026-08-01T01:00:00Z",
    title: str = "Canonical notification test",
) -> dict[str, object]:
    target_id = delivery_target_id or f"{prefix}-delivery-target"
    ensure_subject_and_route(
        connection,
        prefix=prefix,
        subject_id=subject_id,
        delivery_target_id=target_id,
        at_utc=now_utc,
    )
    return seed_canonical_notification_work(
        connection,
        prefix=prefix,
        actor_subject_id=subject_id,
        title=title,
        delivery_target_id=target_id,
        channel="whatsapp",
        recipient_kind="subject",
        recipient_id=subject_id,
        now_utc=now_utc,
        eligible_at_utc=eligible_at_utc,
    )
