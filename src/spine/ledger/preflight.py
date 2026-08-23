"""Bounded runtime admission for Spine SQLite ledgers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from importlib import resources
from typing import Any

from spine import IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.core import SpineValidationError

SCHEMA_OBJECT_MANIFEST_ID = "spine.sqlite-schema-object-manifest.v1"
CURRENT_SCHEMA_VERSION = IMPLEMENTED_LEDGER_SCHEMA_VERSION


@dataclass(frozen=True)
class SchemaObjectExpectation:
    object_type: str
    name: str
    definition_sha256: str


@dataclass(frozen=True)
class RuntimeSchemaVerificationResult:
    schema_version: int
    table_count: int
    index_count: int
    trigger_count: int


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest recorded schema version using bounded metadata access."""

    row = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'ledger_schema'"
    ).fetchone()
    if row is None:
        return 0
    version_row = connection.execute("SELECT MAX(schema_version) AS schema_version FROM ledger_schema").fetchone()
    if version_row is None or version_row["schema_version"] is None:
        return 0
    return int(version_row["schema_version"])


def expected_schema_objects() -> tuple[SchemaObjectExpectation, ...]:
    """Load the checked-in manifest shipped with this runtime."""

    payload: Any = json.loads(
        resources.files("spine.ledger").joinpath("schema_object_manifest.v1.json").read_text(encoding="utf-8")
    )
    if payload.get("manifest_version") != SCHEMA_OBJECT_MANIFEST_ID:
        raise RuntimeError("compiled schema-object manifest identity mismatch")
    schema_key = str(CURRENT_SCHEMA_VERSION)
    schemas = payload.get("schemas")
    if not isinstance(schemas, dict) or set(schemas) != {schema_key}:
        raise RuntimeError("compiled schema-object manifest version mismatch")
    schema_manifest = schemas[schema_key]
    objects = tuple(
        SchemaObjectExpectation(
            object_type=str(item["object_type"]),
            name=str(item["name"]),
            definition_sha256=str(item["definition_sha256"]),
        )
        for item in schema_manifest["objects"]
    )
    if objects != tuple(sorted(objects, key=lambda item: (item.object_type, item.name))):
        raise RuntimeError("compiled schema-object manifest is not deterministically ordered")
    return objects


def verify_runtime_schema(connection: sqlite3.Connection) -> RuntimeSchemaVerificationResult:
    """Verify current schema identity without scanning domain rows."""

    schema_version = current_schema_version(connection)
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise SpineValidationError(
            "ledger_schema_version_mismatch",
            f"database schema version {schema_version} does not match expected version {CURRENT_SCHEMA_VERSION}",
        )

    expected = expected_schema_objects()
    names = tuple(item.name for item in expected)
    placeholders = ",".join("?" for _ in names)
    rows = connection.execute(
        f"SELECT type, name, sql FROM sqlite_schema WHERE name IN ({placeholders})",
        names,
    ).fetchall()
    actual = {str(row["name"]): row for row in rows}

    counts = {"table": 0, "index": 0, "trigger": 0}
    for item in expected:
        row = actual.get(item.name)
        if row is None:
            raise SpineValidationError(
                "ledger_schema_missing_indexes" if item.object_type == "index" else f"ledger_schema_missing_{item.object_type}s",
                f"missing required {item.object_type} {item.name}",
            )
        actual_type = str(row["type"])
        if actual_type != item.object_type:
            raise SpineValidationError(
                "ledger_schema_object_type_mismatch",
                f"required {item.object_type} {item.name} is stored as {actual_type}",
            )
        sql = row["sql"]
        if sql is None:
            raise SpineValidationError(
                "ledger_schema_object_definition_null",
                f"required {item.object_type} {item.name} has a null definition",
            )
        digest = hashlib.sha256(str(sql).encode("utf-8")).hexdigest()
        if digest != item.definition_sha256:
            raise SpineValidationError(
                "ledger_schema_object_definition_mismatch",
                f"definition mismatch for required {item.object_type} {item.name}",
            )
        counts[item.object_type] += 1

    return RuntimeSchemaVerificationResult(
        schema_version=schema_version,
        table_count=counts["table"],
        index_count=counts["index"],
        trigger_count=counts["trigger"],
    )
