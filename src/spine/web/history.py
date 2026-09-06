"""Complete normalized access revisions alongside canonical command receipts."""

from __future__ import annotations

from typing import Any

# Table and column names are compiled, never request-selected.
SOURCES = {
    "account": ("login_accounts", "account_id", "revision", "login_account_revisions"),
    "binding": ("account_subject_bindings", "binding_id", "revision", "account_subject_binding_revisions"),
    "operator": ("web_operators", "account_id", "revision", "web_operator_revisions"),
    "owner": ("item_access_owners", "item_access_owner_id", "current_revision", "item_access_owner_revisions"),
    "grant": ("access_grants", "grant_id", "current_revision", "access_grant_revisions"),
    "route": ("route_member_use_approvals", "delivery_target_id", "current_revision", "route_member_use_approval_revisions"),
}


def record(db: Any, kind: str, identity: str, actor: str, at: str, receipt: str) -> None:
    source, key, revision_column, destination = SOURCES[kind]
    row = dict(db.execute(f"SELECT * FROM {source} WHERE {key}=?", (identity,)).fetchone())
    row["revision"] = row.pop(revision_column)
    row.update(changed_at_utc=at, changed_by_subject_id=actor, command_receipt_id=receipt)
    columns = list(row)
    db.execute(f"INSERT INTO {destination} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[k] for k in columns])
