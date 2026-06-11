"""SQLite bootstrap helpers for Spine's canonical local ledger."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from spine.core.errors import SpineValidationError

DEFAULT_BUSY_TIMEOUT_MS = 5000


def connect(path: str | Path = ":memory:", *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    """Open a SQLite connection with Spine-required connection settings."""

    database = str(path)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    if _is_file_backed_database(database):
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


def schema_sql() -> str:
    """Return the bundled schema SQL text."""

    return resources.files("spine.ledger").joinpath("schema.sql").read_text(encoding="utf-8")


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Initialize the schema on an open SQLite connection."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_sql())


def _is_file_backed_database(database: str) -> bool:
    return database not in {":memory:", ""}


def assert_ledger_invariants(connection: sqlite3.Connection, *, item_id: str | None = None) -> None:
    """Validate cross-row invariants that SQLite cannot fully express.

    SQLite enforces many field, foreign-key, enum, and trigger constraints
    directly. This function covers the item/version/detail bundle rules that
    need cross-table counting or max-version checks. Passing ``item_id`` scopes
    the validation to one item for transactional write paths; omitting it keeps
    the full-ledger sweep for startup or periodic integrity passes.
    """

    _assert_current_version_is_max(connection, item_id=item_id)
    _assert_versions_are_contiguous(connection, item_id=item_id)
    _assert_detail_rows_match_item_type(connection, item_id=item_id)


def _assert_current_version_is_max(connection: sqlite3.Connection, *, item_id: str | None) -> None:
    where_clause = "WHERE i.item_id = ?" if item_id is not None else ""
    params = (item_id,) if item_id is not None else ()
    row = connection.execute(
        f"""
        SELECT i.item_id, i.current_version, MAX(v.version) AS max_version
        FROM coordination_items AS i
        LEFT JOIN coordination_item_versions AS v ON v.item_id = i.item_id
        {where_clause}
        GROUP BY i.item_id
        HAVING max_version IS NULL OR i.current_version != max_version
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row is not None:
        raise SpineValidationError(
            "ledger_current_version_mismatch",
            (
                f"item {row['item_id']} current_version={row['current_version']} "
                f"does not match max version {row['max_version']}"
            ),
        )


def _assert_versions_are_contiguous(connection: sqlite3.Connection, *, item_id: str | None) -> None:
    if item_id is None:
        item_ids = [
            row["item_id"]
            for row in connection.execute(
                "SELECT DISTINCT item_id FROM coordination_item_versions ORDER BY item_id"
            )
        ]
    else:
        item_ids = [item_id]
    for item_id in item_ids:
        versions = [
            row["version"]
            for row in connection.execute(
                """
                SELECT version
                FROM coordination_item_versions
                WHERE item_id = ?
                ORDER BY version
                """,
                (item_id,),
            )
        ]
        for expected, observed in enumerate(versions, start=1):
            if observed != expected:
                raise SpineValidationError(
                    "ledger_non_contiguous_versions",
                    f"item {item_id} has version {observed}; expected {expected}",
                )


def _assert_detail_rows_match_item_type(connection: sqlite3.Connection, *, item_id: str | None) -> None:
    where_clause = "WHERE i.item_id = ?" if item_id is not None else ""
    params = (item_id,) if item_id is not None else ()
    rows = connection.execute(
        f"""
        SELECT i.item_id, i.item_type, v.version,
          (SELECT COUNT(*)
           FROM event_details AS e
           WHERE e.item_id = v.item_id AND e.version = v.version) AS event_detail_count,
          (SELECT COUNT(*)
           FROM task_details AS t
           WHERE t.item_id = v.item_id AND t.version = v.version) AS task_detail_count
        FROM coordination_items AS i
        JOIN coordination_item_versions AS v ON v.item_id = i.item_id
        {where_clause}
        ORDER BY i.item_id, v.version
        """,
        params,
    )
    for row in rows:
        _assert_detail_count(
            item_id=row["item_id"],
            item_type=row["item_type"],
            version=row["version"],
            event_detail_count=row["event_detail_count"],
            task_detail_count=row["task_detail_count"],
        )


def _assert_detail_count(
    *,
    item_id: str,
    item_type: str,
    version: int,
    event_detail_count: int,
    task_detail_count: int,
) -> None:
    expected_counts: dict[str, tuple[int, int]] = {
        "event": (1, 0),
        "task": (0, 1),
        "project": (0, 0),
        "collection": (0, 0),
    }
    expected = expected_counts[item_type]
    observed = (event_detail_count, task_detail_count)
    if observed != expected:
        raise SpineValidationError(
            "ledger_detail_row_mismatch",
            (
                f"item {item_id} v{version} type={item_type} has "
                f"event_details={event_detail_count}, task_details={task_detail_count}"
            ),
        )
