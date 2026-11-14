"""Installed-wheel public CLI canary; only disposable data, never real sends.

Run with the new wheel's Python, -I, outside the source tree. Requires the pinned
Tickerd runtime just as the ordinary CLI does. This is activation proof, not all
R4 lifecycle/qualification obligations.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import spine

CONTRACT = "spine.recurring-related-tasks.v1"


def invoke(module, args, value=None):
    result = subprocess.run([sys.executable, "-I", "-m", module, *args],
                            input=json.dumps(value) if value is not None else None,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"{module} {args}: {result.stdout} {result.stderr}")
    return json.loads(result.stdout)


def main():
    if not Path(spine.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) or sys.prefix == sys.base_prefix:
        raise RuntimeError("require a non-editable installed wheel in a separate venv")
    if spine.IMPLEMENTED_LEDGER_SCHEMA_VERSION != 20:
        raise RuntimeError("require the schema-20 runtime")
    now = datetime.now(UTC).replace(microsecond=0)
    at = now.isoformat().replace("+00:00", "Z")
    first = (now + timedelta(days=2))
    first += timedelta(days=(5 - first.weekday()) % 7)
    first = first.replace(hour=11, minute=30, second=0)
    fact = first.isoformat().replace("+00:00", "Z")
    with tempfile.TemporaryDirectory(prefix="spine-public-recurring-") as tmp:
        db = str(Path(tmp) / "ledger.sqlite")

        def command(name, value):
            response = invoke("spine.commands.cli", ["--db", db, "--input", "-", *name.split(".")], value)
            if response.get("ok") is not True:
                raise RuntimeError(str(response))
            return response

        invoke("spine.ledger.migrate", ["--db", db, "--initialize-if-empty"])
        info = command("system.info", {})
        ledger_id = info["ledger_instance_id"]
        key = Path(tmp) / "cursor.json"
        key.write_text(json.dumps({"secret_hex": os.urandom(32).hex(), "cursor_ledger_id": ledger_id, "cursor_generation": "canary"}))
        key.chmod(0o600)
        os.environ["SPINE_FACET_CURSOR_CONFIG"] = str(key)
        command("subject.upsert", {"command_id": "owner", "actor_subject_id": "owner", "subject_id": "owner",
                                   "subject_kind": "person", "display_name": "Disposable owner", "updated_at_utc": at})
        command("delivery_target.upsert", {"command_id": "route", "actor_subject_id": "owner", "delivery_target_id": "route",
                    "owner_kind": "subject", "owner_subject_id": "owner", "channel": "test", "adapter_name": "capture",
                    "target_ref": "test://never-send", "updated_at_utc": at})
        event = command("event.create", {"command_id": "science", "actor_subject_id": "owner", "created_at_utc": at,
                    "title": "Joe's Science Class", "all_day": False,
                    "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": fact, "recurrence_set": {
                        "time_basis": "instant_utc", "rules": [{"frequency": "WEEKLY", "seed": fact, "start_bound": fact,
                                                                 "end_condition": {"kind": "count", "count": "4"}}]}}})
        occurrence = command("item.occurrences", {"item_id": event["item_id"], "range_basis": "original_schedule",
                              "range_start": fact, "range_end": (first + timedelta(days=30)).isoformat().replace("+00:00", "Z")})
        authoring = {
            "contract_version": CONTRACT, "command_id": "pickup-rule", "actor_subject_id": "owner", "requested_at_utc": at,
            "owner": {"owner_kind": "subject", "owner_subject_id": "owner"}, "rule_key": "pickup",
            "source": {"item_id": event["item_id"], "item_version": "1", "recurrence_set_id": occurrence["recurrence_set_id"],
                       "recurrence_revision_id": occurrence["recurrence_revision_id"]}, "enrollment": {"kind": "upcoming"},
            "configuration": {"task_owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "task_template": {"item": {"item_type": "task", "title": "Pick up Joe", "task_detail": {}},
                                  "people": {"assignees": ["owner"]}}, "offset_basis": "elapsed", "offset_seconds": "5400",
                "notification_plan": {"mode": "none", "custom_additions": [{"policy_key": "ten_minutes",
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
                    "late_handling": {"kind": "skip"}}]},
                "delivery": {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                             "target": {"resolution": "explicit", "delivery_target_id": "route"}},
                "materialization": {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "4838400",
                                    "opportunity_limit": "100"}}}
        created = command("schedule.related_task_rule.create", authoring)
        identity = created["result"]["rule"]["related_task_rule_id"]
        cursor, tasks, work = {}, set(), set()
        for index in range(12):
            rule = command("schedule.related_task_rule.show", {"contract_version": CONTRACT,
                                                               "related_task_rule_id": identity})["result"]["rule"]
            source = rule["source_snapshot"]
            request = {"contract_version": CONTRACT, "command_id": f"page-{index}", "actor_subject_id": "owner",
                       "requested_at_utc": at, "related_task_rule_id": identity,
                       "expected": {"rule_change_version": rule["change_version"], "rule_revision_id": rule["rule_revision_id"],
                                    "source_item_version": source["source_item_version"],
                                    "recurrence_revision_id": source["recurrence_revision_id"],
                                    "catalog_generation": rule["catalog_generation"]}, "limits": {"source_candidates": "2"}, **cursor}
            result = command("schedule.related_task_rule.reconcile", request)["result"]
            tasks.update(v["after"]["task_item_id"] for v in result["results"] if v["outcome"] == "created")
            work.update(result["work"]["created"])
            if not result["has_more"]:
                break
            cursor = {"cursor": result["next_cursor"]}
        if len(tasks) != 4 or len(work) != 4 or result["has_more"]:
            raise RuntimeError("bounded public generation did not produce four unique pickups/reminders")
        for task in tasks:
            shown = command("schedule.show", {"item_id": task})
            if shown.get("item", {}).get("item_id") != task:
                raise RuntimeError("missing task readback")
            due = shown["item"]["task_detail"]["due_anchor"]
            if due["local_time"] != "13:00:00" or due["timezone"] not in {"UTC", "Etc/UTC"}:
                raise RuntimeError("pickup is not due 90 minutes after the 11:30 UTC class")
        assignments = command("schedule.related_task_rule.show", {"contract_version": CONTRACT,
                                "related_task_rule_id": identity, "view": "assignments", "limit": "100"})["result"]
        if len(assignments["rows"]) != 4 or assignments["has_more"]:
            raise RuntimeError("assignment readback contains duplicate or missing slots")
        repeated = command("schedule.related_task_rule.reconcile", request)
        if repeated.get("replayed") is not True:
            raise RuntimeError("compatible public replay was not preserved")
        worker_rule = command("schedule.related_task_rule.create", dict(authoring, command_id="worker-rule", rule_key="worker-pickup"))
        worker_id = worker_rule["result"]["rule"]["related_task_rule_id"]
        invoke("spine.runtime.worker", ["--db", db, "--state-dir", str(Path(tmp) / "worker"), "--max-cycles", "12",
               "--tick-interval-ms", "1", "--reconcile-interval-ms", "1", "--scheduler-actor-subject-id", "owner",
               "--facet-cursor-config", str(key), "--openclaw-sender", "fake"])
        generated = command("schedule.related_task_rule.show", {"contract_version": CONTRACT,
                             "related_task_rule_id": worker_id, "view": "assignments", "limit": "100"})["result"]
        if len(generated["rows"]) != 4 or generated["has_more"] or (Path(tmp) / "worker/openclaw_sends.jsonl").exists():
            raise RuntimeError("unattended generation or no-send boundary failed")
        invoke("spine.ledger.migrate", ["--db", db, "--verify-only"])
        print(json.dumps({"ok": True, "version": spine.__version__, "schema": "20", "unique_pickups": "4",
                          "materialized_reminders": "4", "worker_generated_pickups": "4",
                          "scope": "public-cli-activation-canary", "real_sends": "0"}))


if __name__ == "__main__":
    main()
