"""Run with the installed 0.9.1 wheel's Python, outside the checkout/PYTHONPATH.

    <wheel-python> /absolute/path/scripts/verify_rendering_wheel.py --old-python <0.8.3-wheel-python>

Creates disposable ledgers only; never invokes a real delivery adapter.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

import spine
from spine.commands import CommandContext, handle
from spine.ledger import connect, initialize_schema
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.runtime.compatibility import resolve_tickerd_compatibility
from spine.web.contracts import registry as web_registry
from spine.web.facet_service import registry as facet_registry


def run(python, module, args, request=None, *, success=True):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [python, "-m", module, *args],
        input=json.dumps(request) if request else None,
        text=True,
        capture_output=True,
        env=environment,
        timeout=30,
        check=False,
    )
    assert (result.returncode == 0) == success, (result.returncode, result.stdout, result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-python", required=True)
    args = parser.parse_args()
    assert spine.__version__ == "0.9.1"
    assert "site-packages" in str(Path(spine.__file__))
    dependency = resolve_tickerd_compatibility()
    assert dependency.descriptor_sha256 == "215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b"
    package = resources.files("spine.contracts").joinpath("rendering")
    pins = json.loads(package.joinpath("pins.v1.json").read_text())
    for name, digest in pins["files"].items():
        assert hashlib.sha256(package.joinpath(*name.split("/")).read_bytes()).hexdigest() == digest, name
    web_registry()
    facet_registry()
    with tempfile.TemporaryDirectory(prefix="spine-rendering-wheel-") as directory:
        root = Path(directory)
        fresh = connect(root / "fresh.sqlite")
        try:
            initialize_schema(fresh)
            assert verify_schema(fresh).schema_version == 19
        finally:
            fresh.close()
        old = root / "old.sqlite"
        run(args.old_python, "spine.ledger.migrate", ["--db", str(old), "--initialize-if-empty"])
        now = "2035-01-01T00:00:00Z"
        common = {"actor_subject_id": "owner", "updated_at_utc": now}
        run(
            args.old_python,
            "spine.commands.cli",
            ["--db", str(old), "subject", "upsert"],
            common | {"command_id": "owner", "subject_id": "owner", "subject_kind": "person", "display_name": "Wheel owner"},
        )
        run(
            args.old_python,
            "spine.commands.cli",
            ["--db", str(old), "delivery_target", "upsert"],
            common
            | {
                "command_id": "route",
                "delivery_target_id": "route",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "wheel-fixture-never-send",
            },
        )
        event_request = {
            "contract_version": "spine.schedule-create.v2",
            "command_id": "event",
            "actor_subject_id": "owner",
            "created_at_utc": now,
            "item": {"item_type": "event", "title": "Wheel flight", "event_detail": {"all_day": False}},
            "scheduled_time": {
                "time_basis": "local_instant",
                "local_date": "2035-01-02",
                "local_time": "10:00:00",
                "timezone": "UTC",
                "timezone_database_version": {"kind": "system_current"},
            },
            "delivery": {
                "recipient_kind": "subject",
                "recipient_subject_id": "owner",
                "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "route"},
            },
            "notification_plan": {
                "mode": "none",
                "custom_additions": [
                    {
                        "policy_key": "before",
                        "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
                        "late_handling": {"kind": "skip"},
                    }
                ],
            },
            "materialization": {"mode": "none"},
        }
        created = json.loads(run(args.old_python, "spine.commands.cli", ["--db", str(old), "schedule", "create"], event_request).stdout)
        backup = root / "schema18-backup.sqlite"
        source, target = sqlite3.connect(old), sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        db = connect(old)
        try:
            policies = [tuple(r) for r in db.execute("SELECT * FROM notification_policies")]
            receipts = [tuple(r) for r in db.execute("SELECT * FROM command_receipts ORDER BY command_id")]
            assert migrate_schema(db).applied_versions == (19,)
            assert verify_schema(db).schema_version == 19
            assert policies == [tuple(r) for r in db.execute("SELECT * FROM notification_policies")]
            assert receipts == [tuple(r) for r in db.execute("SELECT * FROM command_receipts ORDER BY command_id")]
            context = CommandContext(ledger=db)
            shown = handle("schedule.show", {"contract_version": "spine.schedule-show.v2", "item_id": created["item_id"]}, context)
            assert shown["ok"] and shown["response_contract"] == "spine.schedule-show.v2", shown
            schema = handle(
                "facet_schema.create",
                {
                    "contract_version": "spine.facet-schemas.v1",
                    "command_id": "schema",
                    "actor_subject_id": "owner",
                    "action_timestamp_utc": now,
                    "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                    "schema_key": "flight",
                    "definition": {
                        "display_name": "Flight",
                        "description": None,
                        "compatible_item_types": ["event"],
                        "fields": [{"key": "flight", "type": "text", "max_length": "64", "required": True, "queryable": True}],
                    },
                },
                context,
            )
            assert schema["ok"], schema
            definition = handle(
                "notification_rendering_definition.create",
                {
                    "contract_version": "spine.notification-rendering-definitions.v1",
                    "command_id": "definition",
                    "actor_subject_id": "owner",
                    "action_timestamp_utc": now,
                    "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                    "definition_key": "flight",
                    "revision": {
                        "display_name": "Flight details",
                        "description": None,
                        "compatible_item_types": ["event"],
                        "base_rendering_contract": "spine.notification-rendering.v1",
                        "base_rendering_profile": "spine.notification-rendering.concise-en-ca.v1",
                        "selections": [
                            {
                                "selection_key": "flight",
                                "facet_key": "flight",
                                "facet_schema_revision_id": schema["facet_schema_revision_id"],
                                "field_key": "flight",
                                "projection": "value",
                                "label": "Flight",
                            }
                        ],
                    },
                },
                context,
            )
            assert definition["ok"], definition
        finally:
            db.close()
        run(sys.executable, "spine.commands.cli", ["--db", str(old), "system", "info"])
        # Exercise the installed public successor list, not only its show path.
        for version, key in (("spine.notification-profiles.v1", "a_legacy"), ("spine.notification-profiles.v2", "b_successor")):
            template = {
                "template_key": "before",
                "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
                "late_handling": {"kind": "skip"},
            }
            if version.endswith(".v2"):
                template["rendering"] = {"kind": "ordinary"}
            run(sys.executable, "spine.commands.cli", ["--db", str(old), "notification_profile", "create"], {
                "contract_version": version, "command_id": "wheel-profile-" + key,
                "actor_subject_id": "owner", "action_timestamp_utc": now,
                "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "profile_key": key, "display_name": key,
                "revision": {"compatible_item_types": ["event"], "templates": [template]},
            })
        query = {
            "contract_version": "spine.notification-profiles.v2",
            "owner": {"owner_kind": "subject", "owner_subject_id": "owner"}, "status": "active", "limit": "1",
        }
        first = json.loads(run(sys.executable, "spine.commands.cli", ["--db", str(old), "notification_profile", "list"], query).stdout)
        second = json.loads(run(sys.executable, "spine.commands.cli", ["--db", str(old), "notification_profile", "list"],
                                query | {"cursor": first["next_cursor"]}).stdout)
        assert first["entries"][0]["revision"]["revision_contract"] == "spine.notification-profiles.v1"
        assert second["entries"][0]["revision"]["revision_contract"] == "spine.notification-profiles.v2"
        assert first["has_more"] and not second["has_more"]
        assert first["catalog_snapshot_hash"] == second["catalog_snapshot_hash"]
        run(args.old_python, "spine.commands.cli", ["--db", str(old), "system", "info"], success=False)
        state = root / "old-worker"
        run(args.old_python, "spine.runtime.worker", ["--db", str(old), "--state-dir", str(state), "--max-cycles", "1"], success=False)
        health = json.loads((state / "health.json").read_text())
        assert health["state"] == "DOWN" and health["is_ready"] is False
        assert not (state / "openclaw_sends.jsonl").exists()
        events = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
        assert len(events) == 1 and events[0]["event"] == "ledger_runtime_preflight_failed", events
        # Matching predecessor runtime verifies the independent backup, not a
        # destructive restore over the upgraded ledger.
        run(args.old_python, "spine.ledger.migrate", ["--db", str(backup), "--verify-only"])
        run(args.old_python, "spine.commands.cli", ["--db", str(backup), "system", "info"])
    print(
        json.dumps(
            {
                "result": "PASS",
                "version": spine.__version__,
                "schema": 19,
                "local_resources": len(pins["files"]),
                "tickerd_descriptor_sha256": dependency.descriptor_sha256,
                "old_worker_refused": True,
                "paired_backup_verified": True,
                "mixed_profile_v2_listing_verified": True,
                "real_sends": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
