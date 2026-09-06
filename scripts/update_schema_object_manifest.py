"""Regenerate the compiled DDL manifest from an empty migrated in-memory ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from spine import IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.ledger.sqlite import connect, initialize_schema


def main() -> None:
    db = connect()
    initialize_schema(db)
    objects = [
        {"object_type": r["type"], "name": r["name"], "definition_sha256": hashlib.sha256(r["sql"].encode()).hexdigest()}
        for r in db.execute(
            "SELECT type,name,sql FROM sqlite_schema WHERE type IN ('table','index','trigger') AND sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    db.close()
    path = Path(__file__).resolve().parents[1] / "src/spine/ledger/schema_object_manifest.v1.json"
    value = {
        "manifest_version": "spine.sqlite-schema-object-manifest.v1",
        "schemas": {str(IMPLEMENTED_LEDGER_SCHEMA_VERSION): {"objects": objects}},
    }
    path.write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
