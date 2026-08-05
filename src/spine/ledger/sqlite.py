"""SQLite bootstrap helpers for Spine's canonical local ledger."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from spine.core.errors import SpineValidationError
from spine.core.recurrence import validate_daily_local_recurrence_anchor

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
    _assert_recurrence_contract(connection, item_id=item_id)


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


def _assert_recurrence_contract(connection: sqlite3.Connection, *, item_id: str | None) -> None:
    where_event = "AND e.item_id = ?" if item_id is not None else ""
    where_task = "AND t.item_id = ?" if item_id is not None else ""
    where_policy = "AND p.item_id = ?" if item_id is not None else ""
    params = (item_id,) if item_id is not None else ()

    invalid_event = connection.execute(
        f"""
        SELECT e.item_id, e.version
        FROM event_details AS e
        JOIN temporal_anchors AS start ON start.anchor_id = e.start_anchor_id
        LEFT JOIN temporal_anchors AS finish ON finish.anchor_id = e.end_anchor_id
        WHERE (
          (start.recurrence_rule IS NOT NULL AND start.anchor_kind NOT IN ('local_date', 'local_instant'))
          OR finish.recurrence_rule IS NOT NULL
        )
        {where_event}
        LIMIT 1
        """,
        params,
    ).fetchone()
    if invalid_event is not None:
        raise SpineValidationError(
            "ledger_invalid_recurrence",
            f"event {invalid_event['item_id']} v{invalid_event['version']} has invalid recurrence placement",
        )

    invalid_task = connection.execute(
        f"""
        SELECT t.item_id, t.version
        FROM task_details AS t
        LEFT JOIN temporal_anchors AS due ON due.anchor_id = t.due_anchor_id
        LEFT JOIN temporal_anchors AS deferred ON deferred.anchor_id = t.defer_until_anchor_id
        WHERE (
          (due.recurrence_rule IS NOT NULL AND due.anchor_kind NOT IN ('local_date', 'local_instant'))
          OR deferred.recurrence_rule IS NOT NULL
        )
        {where_task}
        LIMIT 1
        """,
        params,
    ).fetchone()
    if invalid_task is not None:
        raise SpineValidationError(
            "ledger_invalid_recurrence",
            f"task {invalid_task['item_id']} v{invalid_task['version']} has invalid recurrence placement",
        )

    invalid_policy = connection.execute(
        f"""
        SELECT p.item_id, p.version, p.policy_id
        FROM notification_policies AS p
        JOIN temporal_anchors AS trigger ON trigger.anchor_id = p.trigger_anchor_id
        WHERE trigger.recurrence_rule IS NOT NULL
        {where_policy}
        LIMIT 1
        """,
        params,
    ).fetchone()
    if invalid_policy is not None:
        raise SpineValidationError(
            "ledger_invalid_recurrence",
            f"notification policy {invalid_policy['policy_id']} has a recurring trigger anchor",
        )

    recurring_rows = connection.execute(
        f"""
        SELECT DISTINCT anchor.anchor_id, anchor.anchor_kind, anchor.local_date,
                        anchor.local_time, anchor.timezone, anchor.recurrence_rule
        FROM temporal_anchors AS anchor
        LEFT JOIN event_details AS e ON e.start_anchor_id = anchor.anchor_id
        LEFT JOIN task_details AS t ON t.due_anchor_id = anchor.anchor_id
        WHERE anchor.recurrence_rule IS NOT NULL
          AND (e.item_id IS NOT NULL OR t.item_id IS NOT NULL)
          {"AND (e.item_id = ? OR t.item_id = ?)" if item_id is not None else ""}
        ORDER BY anchor.anchor_id
        """,
        (item_id, item_id) if item_id is not None else (),
    )
    for row in recurring_rows:
        try:
            validate_daily_local_recurrence_anchor(
                anchor_kind=row["anchor_kind"],
                local_date_value=row["local_date"],
                local_time_value=row["local_time"],
                timezone=row["timezone"],
                recurrence_rule=row["recurrence_rule"],
            )
        except SpineValidationError as exc:
            raise SpineValidationError(
                "ledger_invalid_recurrence",
                f"anchor {row['anchor_id']} has invalid recurrence: {exc.message}",
            ) from exc
