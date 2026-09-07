"""Persisted ledger identity; expensive deterministic backfill is migration-only."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from importlib import resources

from spine.core import SpineValidationError

CONTRACT = "spine.ledger-instance.v1"
PREFIX = "ledger_instance_"
ORIGINS = {"initialized_random_v1", "schema13_logical_backfill_v1"}


def read_ledger_instance_id(connection: sqlite3.Connection) -> str:
    """Bounded, read-only validation. Never create or repair missing identity."""
    try:
        rows = connection.execute(
            "SELECT singleton, identity_contract, ledger_instance_id, origin FROM ledger_instance_metadata LIMIT 2"
        ).fetchall()
    except sqlite3.Error as exc:
        raise SpineValidationError("ledger_instance_invalid", "ledger instance metadata unavailable") from exc
    if len(rows) != 1:
        raise SpineValidationError("ledger_instance_invalid", "expected one ledger instance identity")
    singleton, contract, identity, origin = rows[0]
    if (singleton != 1 or contract != CONTRACT or origin not in ORIGINS
            or not isinstance(identity, str) or re.fullmatch(r"ledger_instance_[0-9a-f]{64}", identity) is None):
        raise SpineValidationError("ledger_instance_invalid", "invalid ledger instance metadata")
    return identity


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _cell(value: object) -> list[str]:
    if value is None:
        return ["null"]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        return ["real", (0.0 if value == 0 else value).hex()]
    if isinstance(value, bytes):
        return ["blob", value.hex()]
    if isinstance(value, str):
        return ["text", value]
    raise SpineValidationError("ledger_instance_backfill_unsupported", "unsupported SQLite value")


def schema13_identity(connection: sqlite3.Connection) -> str:
    """Hash framed logical rows in deterministic SQLite storage-class/value order."""
    digest = hashlib.sha256()

    def feed(value: object) -> None:
        data = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
        digest.update(str(len(data)).encode("ascii") + b":" + data)

    feed("spine.ledger-instance.schema13-logical.v1")
    objects = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE name NOT GLOB 'sqlite_*' AND sql IS NOT NULL ORDER BY type COLLATE BINARY, name COLLATE BINARY"
    ).fetchall()
    for row in objects:
        feed(["object", *row])
    for row in sorted((r for r in objects if r[0] == "table"), key=lambda r: r[1]):
        name, ddl = row[1], row[3]
        if re.match(r"\s*CREATE\s+VIRTUAL\s+TABLE", ddl, re.IGNORECASE):
            raise SpineValidationError("ledger_instance_backfill_unsupported", "virtual tables require separate migration review")
        table = _quoted(name)
        columns = [r[1] for r in connection.execute(f"PRAGMA table_xinfo({table})")]
        names = ",".join(_quoted(c) for c in columns)
        order = ",".join(f"typeof({_quoted(c)}) COLLATE BINARY, {_quoted(c)} COLLATE BINARY" for c in columns)
        feed(["table", name, columns])
        count = 0
        for values in connection.execute(f"SELECT {names} FROM {table} ORDER BY {order}"):
            feed(["row", [_cell(value) for value in values]])
            count += 1
        feed(["end_table", str(count)])
    return PREFIX + digest.hexdigest()


def install_identity(connection: sqlite3.Connection, *, fresh: bool, applied_at_utc: str) -> None:
    """Atomically commit schema 14, its identity, and migration history."""
    if connection.in_transaction:
        raise SpineValidationError("ledger_instance_migration_transaction", "identity migration requires a quiescent connection")
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0]
        if version != 13:
            raise SpineValidationError("ledger_schema_version_mismatch", "identity migration requires schema 13")
        identity = PREFIX + secrets.token_hex(32) if fresh else schema13_identity(connection)
        sql = resources.files("spine.ledger.migrations").joinpath("0014_ledger_instance_identity.sql").read_text()
        statement = ""
        for line in sql.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
        if statement.strip():
            raise RuntimeError("incomplete identity migration SQL")
        connection.execute(
            "INSERT INTO ledger_instance_metadata VALUES (1, ?, ?, ?)",
            (CONTRACT, identity, "initialized_random_v1" if fresh else "schema13_logical_backfill_v1"),
        )
        read_ledger_instance_id(connection)
        connection.execute("INSERT INTO ledger_schema VALUES (14, ?)", (applied_at_utc,))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
