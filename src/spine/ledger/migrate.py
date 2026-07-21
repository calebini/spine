"""SQLite schema migration and verification for Spine's ledger."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from spine.core import SpineValidationError
from spine.ledger.common import utc_z_from_datetime
from spine.ledger.sqlite import assert_ledger_invariants, connect, initialize_schema

CURRENT_SCHEMA_VERSION = 5

EXPECTED_SCHEMA_TABLES = frozenset(
    {
        "audit_log",
        "candidate_actions",
        "command_receipts",
        "coordination_item_relations",
        "coordination_item_versions",
        "coordination_items",
        "delivery_targets",
        "event_details",
        "external_projections",
        "item_locations",
        "item_subject_roles",
        "ledger_schema",
        "locations",
        "notification_policies",
        "side_effect_attempts",
        "subject_groups",
        "subject_memberships",
        "subjects",
        "task_details",
        "temporal_anchors",
        "work_instances",
    }
)

EXPECTED_SCHEMA_INDEXES = frozenset(
    {
        "audit_log_causation_idx",
        "audit_log_correlation_idx",
        "audit_log_item_created_idx",
        "candidate_actions_item_status_idx",
        "candidate_actions_open_kind_idx",
        "command_receipts_item_created_idx",
        "coordination_item_relations_active_source_idx",
        "coordination_item_relations_active_target_idx",
        "coordination_item_relations_active_unique",
        "external_projections_item_adapter_status_idx",
        "external_projections_status_updated_idx",
        "item_locations_location_idx",
        "item_subject_roles_subject_idx",
        "delivery_targets_active_account_unique",
        "delivery_targets_active_no_account_unique",
        "delivery_targets_owner_status_idx",
        "notification_policies_item_version_status_idx",
        "notification_policies_delivery_target_idx",
        "notification_policies_group_status_idx",
        "notification_policies_group_unique",
        "notification_policies_recipient_status_idx",
        "notification_policies_subject_unique",
        "side_effect_attempts_candidate_action_idx",
        "side_effect_attempts_item_adapter_status_idx",
        "side_effect_attempts_projection_idx",
        "side_effect_attempts_work_instance_idx",
        "subject_memberships_group_status_idx",
        "subject_memberships_subject_status_idx",
        "work_instances_delivery_target_idx",
        "work_instances_eligible_due_idx",
        "work_instances_item_version_status_idx",
        "work_instances_source_work_idx",
    }
)


@dataclass(frozen=True)
class MigrationResult:
    """Summary of a migration pass."""

    before_version: int
    after_version: int
    applied_versions: tuple[int, ...]
    initialized: bool
    verified: bool


@dataclass(frozen=True)
class SchemaVerificationResult:
    """Summary of a schema verification pass."""

    schema_version: int
    table_count: int
    index_count: int
    foreign_key_errors: int
    integrity_check: str
    ledger_invariants_ok: bool


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest recorded ledger schema version, or 0 before initialization."""

    if not _table_exists(connection, "ledger_schema"):
        return 0
    row = connection.execute("SELECT MAX(schema_version) AS schema_version FROM ledger_schema").fetchone()
    if row is None or row["schema_version"] is None:
        return 0
    return int(row["schema_version"])


def migrate_schema(
    connection: sqlite3.Connection,
    *,
    initialize_if_empty: bool = False,
    verify: bool = True,
) -> MigrationResult:
    """Apply pending SQLite schema migrations and optionally verify the ledger."""

    connection.execute("PRAGMA foreign_keys = ON")
    before_version = current_schema_version(connection)
    initialized = False

    if before_version == 0:
        if not initialize_if_empty or not _database_is_empty(connection):
            raise SpineValidationError(
                "ledger_schema_uninitialized",
                "database has no ledger_schema version; pass initialize_if_empty for an empty ledger",
            )
        initialize_schema(connection)
        initialized = True
        before_version = current_schema_version(connection)

    if before_version > CURRENT_SCHEMA_VERSION:
        raise SpineValidationError(
            "ledger_schema_unsupported",
            f"database schema version {before_version} is newer than supported version {CURRENT_SCHEMA_VERSION}",
        )

    applied_versions: list[int] = []
    for version, migration_name in _available_migrations():
        if version <= before_version:
            continue
        if version > CURRENT_SCHEMA_VERSION:
            continue
        _apply_migration(connection, version=version, migration_name=migration_name)
        applied_versions.append(version)

    after_version = current_schema_version(connection)
    if after_version != CURRENT_SCHEMA_VERSION:
        raise SpineValidationError(
            "ledger_schema_not_current",
            f"database schema version {after_version} does not match expected version {CURRENT_SCHEMA_VERSION}",
        )

    if verify:
        verify_schema(connection)

    return MigrationResult(
        before_version=0 if initialized else before_version,
        after_version=after_version,
        applied_versions=tuple(applied_versions),
        initialized=initialized,
        verified=verify,
    )


def verify_schema(connection: sqlite3.Connection) -> SchemaVerificationResult:
    """Run structural, SQLite, and ledger-domain verification checks."""

    schema_version = current_schema_version(connection)
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise SpineValidationError(
            "ledger_schema_version_mismatch",
            f"database schema version {schema_version} does not match expected version {CURRENT_SCHEMA_VERSION}",
        )

    table_names = _object_names(connection, object_type="table")
    missing_tables = sorted(EXPECTED_SCHEMA_TABLES - table_names)
    if missing_tables:
        raise SpineValidationError("ledger_schema_missing_tables", ", ".join(missing_tables))

    index_names = _object_names(connection, object_type="index")
    missing_indexes = sorted(EXPECTED_SCHEMA_INDEXES - index_names)
    if missing_indexes:
        raise SpineValidationError("ledger_schema_missing_indexes", ", ".join(missing_indexes))

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise SpineValidationError(
            "ledger_schema_foreign_key_check_failed",
            f"foreign_key_check returned {len(foreign_key_errors)} errors",
        )

    integrity_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity_check != "ok":
        raise SpineValidationError("ledger_schema_integrity_check_failed", str(integrity_check))

    assert_ledger_invariants(connection)
    return SchemaVerificationResult(
        schema_version=schema_version,
        table_count=len(table_names),
        index_count=len(index_names),
        foreign_key_errors=0,
        integrity_check=integrity_check,
        ledger_invariants_ok=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for applying or verifying Spine ledger migrations."""

    args = _parse_args(argv)
    connection = connect(Path(args.db))
    try:
        if args.verify_only:
            verification_result = verify_schema(connection)
            payload = {
                "schema_version": verification_result.schema_version,
                "table_count": verification_result.table_count,
                "index_count": verification_result.index_count,
                "foreign_key_errors": verification_result.foreign_key_errors,
                "integrity_check": verification_result.integrity_check,
                "ledger_invariants_ok": verification_result.ledger_invariants_ok,
                "verified": True,
            }
        else:
            migration_result = migrate_schema(
                connection,
                initialize_if_empty=args.initialize_if_empty,
                verify=not args.no_verify,
            )
            payload = {
                "before_version": migration_result.before_version,
                "after_version": migration_result.after_version,
                "applied_versions": list(migration_result.applied_versions),
                "initialized": migration_result.initialized,
                "verified": migration_result.verified,
            }
    finally:
        connection.close()
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _apply_migration(connection: sqlite3.Connection, *, version: int, migration_name: str) -> None:
    if version == 4 and _delivery_target_schema_present(connection):
        with connection:
            _ensure_delivery_target_schema_indexes(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO ledger_schema (schema_version, applied_at_utc)
                VALUES (?, ?)
                """,
                (version, _utc_now()),
            )
        return
    sql = _migration_sql(migration_name)
    with connection:
        connection.executescript(sql)
        connection.execute(
            """
            INSERT OR IGNORE INTO ledger_schema (schema_version, applied_at_utc)
            VALUES (?, ?)
            """,
            (version, _utc_now()),
        )


def _available_migrations() -> tuple[tuple[int, str], ...]:
    migration_names = [
        child.name
        for child in resources.files("spine.ledger.migrations").iterdir()
        if child.name.endswith(".sql")
    ]
    migrations: list[tuple[int, str]] = []
    for name in migration_names:
        prefix = name.split("_", 1)[0]
        if not prefix.isdigit():
            raise SpineValidationError("ledger_migration_name_invalid", f"invalid migration filename: {name}")
        migrations.append((int(prefix), name))

    migrations = sorted(migrations)
    seen_versions: set[int] = set()
    for version, name in migrations:
        if version in seen_versions:
            raise SpineValidationError("ledger_migration_duplicate_version", f"duplicate migration version: {name}")
        seen_versions.add(version)

    expected_versions = set(range(2, CURRENT_SCHEMA_VERSION + 1))
    missing_versions = sorted(expected_versions - seen_versions)
    if missing_versions:
        raise SpineValidationError(
            "ledger_migration_missing_versions",
            f"missing migration versions: {missing_versions}",
        )
    return tuple(migrations)


def _migration_sql(migration_name: str) -> str:
    return (
        resources.files("spine.ledger.migrations")
        .joinpath(migration_name)
        .read_text(encoding="utf-8")
    )


def _database_is_empty(connection: sqlite3.Connection) -> bool:
    return not _object_names(connection, object_type="table")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(connection, table_name):
        return False
    return any(row["name"] == column_name for row in connection.execute(f"PRAGMA table_info({table_name})"))


def _delivery_target_schema_present(connection: sqlite3.Connection) -> bool:
    return (
        _table_exists(connection, "subject_groups")
        and _table_exists(connection, "delivery_targets")
        and _column_exists(connection, "notification_policies", "recipient_kind")
        and _column_exists(connection, "notification_policies", "delivery_target_id")
        and _column_exists(connection, "work_instances", "delivery_target_id")
    )


def _ensure_delivery_target_schema_indexes(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS subject_memberships_group_status_idx
        ON subject_memberships (group_id, status, subject_id);

        CREATE INDEX IF NOT EXISTS subject_memberships_subject_status_idx
        ON subject_memberships (subject_id, status, group_id);

        CREATE UNIQUE INDEX IF NOT EXISTS delivery_targets_active_no_account_unique
        ON delivery_targets (adapter_name, channel, target_ref)
        WHERE status = 'active' AND account_id IS NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS delivery_targets_active_account_unique
        ON delivery_targets (adapter_name, account_id, channel, target_ref)
        WHERE status = 'active' AND account_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS delivery_targets_owner_status_idx
        ON delivery_targets (owner_kind, owner_subject_id, owner_group_id, status);

        CREATE UNIQUE INDEX IF NOT EXISTS notification_policies_subject_unique
        ON notification_policies (item_id, version, recipient_subject_id, trigger_anchor_id)
        WHERE recipient_kind = 'subject';

        CREATE UNIQUE INDEX IF NOT EXISTS notification_policies_group_unique
        ON notification_policies (item_id, version, recipient_group_id, trigger_anchor_id)
        WHERE recipient_kind = 'subject_group';

        CREATE INDEX IF NOT EXISTS notification_policies_item_version_status_idx
        ON notification_policies (item_id, version, status, policy_id);

        CREATE INDEX IF NOT EXISTS notification_policies_recipient_status_idx
        ON notification_policies (recipient_subject_id, status, item_id, version);

        CREATE INDEX IF NOT EXISTS notification_policies_group_status_idx
        ON notification_policies (recipient_group_id, status, item_id, version)
        WHERE recipient_kind = 'subject_group';

        CREATE INDEX IF NOT EXISTS notification_policies_delivery_target_idx
        ON notification_policies (delivery_target_id, status, item_id, version)
        WHERE delivery_target_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS work_instances_delivery_target_idx
        ON work_instances (delivery_target_id, status, work_instance_id)
        WHERE delivery_target_id IS NOT NULL;
        """
    )


def _object_names(connection: sqlite3.Connection, *, object_type: str) -> frozenset[str]:
    return frozenset(
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = ? AND name NOT LIKE 'sqlite_%'
            """,
            (object_type,),
        )
    )


def _utc_now() -> str:
    return utc_z_from_datetime(datetime.now(UTC))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate or verify a Spine SQLite ledger.")
    parser.add_argument("--db", required=True, help="Path to a Spine SQLite ledger database.")
    parser.add_argument(
        "--initialize-if-empty",
        action="store_true",
        help="Create the latest schema when the target database has no user tables.",
    )
    parser.add_argument("--verify-only", action="store_true", help="Verify without applying migrations.")
    parser.add_argument("--no-verify", action="store_true", help="Skip post-migration verification.")
    args = parser.parse_args(argv)
    if args.verify_only and args.no_verify:
        raise SystemExit("--verify-only cannot be combined with --no-verify")
    if args.verify_only and args.initialize_if_empty:
        raise SystemExit("--verify-only cannot initialize an empty database")
    return args


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
