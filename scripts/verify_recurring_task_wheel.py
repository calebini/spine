"""R4 package-only proof: run with an installed-wheel Python using -I.

This preliminary check does not assert public command activation, migrate a
ledger, invoke internal handlers, or send notifications. R4's complete release
scenario remains a separate gate after runtime activation.
"""

import argparse
import json
import sys
from importlib import metadata, resources
from pathlib import Path

import spine
from spine.commands.recurring_task_package import packaged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration-core", action="store_true",
                        help="also exercise explicit schema-20 migration on a disposable in-memory ledger")
    args = parser.parse_args()
    prefix = Path(sys.prefix).resolve()
    installed = Path(spine.__file__).resolve()
    if prefix == Path(sys.base_prefix).resolve() or not installed.is_relative_to(prefix):
        raise RuntimeError("use a separate virtual environment with a non-editable installed wheel")
    distribution = metadata.distribution("spine-ledger")
    direct = distribution.read_text("direct_url.json")
    if direct is None or json.loads(direct).get("dir_info", {}).get("editable"):
        raise RuntimeError("non-editable local wheel evidence required")
    contracts = packaged()
    for entry in contracts.descriptor["commands"].values():
        for field in ("request_schema", "response_schema", "failure_schema"):
            if entry[field] not in contracts.documents:
                raise RuntimeError("incomplete command closure")
    raw_pins = resources.files("spine.contracts").joinpath("recurring_tasks", "pins.v1.json").read_bytes()
    if args.migration_core:
        from spine.ledger import connect, initialize_schema
        from spine.ledger.preflight import verify_runtime_schema
        from spine.ledger.recurring_task_migration import install_recurring_task_storage

        db = connect()
        try:
            initialize_schema(db)
            install_recurring_task_storage(db, applied_at_utc="2026-11-14T10:00:00Z")
            verify_runtime_schema(db, expected_version=20)
            if db.execute("SELECT count(*) FROM related_task_rules").fetchone()[0] != 0:
                raise RuntimeError("migration must not infer enrollment")
        finally:
            db.close()
    print(json.dumps({"scope": "recurring-task-package-only", "package_version": spine.__version__,
                      "schema": str(spine.IMPLEMENTED_LEDGER_SCHEMA_VERSION), "installed_module": str(installed),
                      "resource_count": str(len(json.loads(raw_pins)["files"]) + 1),
                      "schema_count": str(len(contracts.documents)), "command_count": str(len(contracts.descriptor["commands"])),
                      "migration_core_verified": args.migration_core,
                      "public_activation_verified": False, "ok": True}, indent=2))


if __name__ == "__main__":
    main()
