"""Installed-wheel public CLI canary; only disposable data, never real sends.

Run with the new wheel's Python, -I, outside the source tree. Requires the pinned
Tickerd runtime just as the ordinary CLI does. Includes the science-class lifecycle,
not a substitute for the RRT witness matrix and full regression suite.
"""

import copy
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
                    "owner_kind": "subject", "owner_subject_id": "owner", "channel": "test", "adapter_name": "openclaw",
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
                "generation_horizon_seconds": "4838400",
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
        lifecycle = verify_lifecycle(command, authoring, identity, event["item_id"], fact, first, at, tmp, db)
        invoke("spine.ledger.migrate", ["--db", db, "--verify-only"])
        print(json.dumps({"ok": True, "version": spine.__version__, "schema": "20", "unique_pickups": "4",
                          "materialized_reminders": "4", "worker_generated_pickups": "4",
                          "scope": "public-cli-lifecycle-canary", "lifecycle": lifecycle, "real_sends": "0"}))


def verify_lifecycle(command, authoring, identity, event_id, fact, first, at, tmp, db):
    """Public CLI writes; only a file-backed fake uses the normal attempt path."""
    sequence = 0

    def unique(label):
        nonlocal sequence
        sequence += 1
        return f"lifecycle-{sequence}-{label}"

    def read(rule_id=identity, **extra):
        return command("schedule.related_task_rule.show", {
            "contract_version": CONTRACT, "related_task_rule_id": rule_id, **extra})["result"]

    def write(action, rule_id=identity, **extra):
        root = read(rule_id)["rule"]
        source = root["source_snapshot"]
        return {"contract_version": CONTRACT, "command_id": unique(action), "actor_subject_id": "owner",
                "requested_at_utc": at, "related_task_rule_id": rule_id,
                "expected": {"rule_change_version": root["change_version"], "rule_revision_id": root["rule_revision_id"],
                             "source_item_version": source["source_item_version"],
                             "recurrence_revision_id": source["recurrence_revision_id"],
                             "catalog_generation": root["catalog_generation"]}, **extra}

    def reconcile(rule_id=identity):
        cursor, rows = {}, []
        for _ in range(24):
            response = command("schedule.related_task_rule.reconcile", write(
                "reconcile", rule_id, limits={"assignments": "2", "source_candidates": "2"}, **cursor))["result"]
            rows.extend(response["results"])
            if not response["has_more"]:
                return rows
            cursor = {"cursor": response["next_cursor"]}
        raise AssertionError("lifecycle exceeded 24 bounded pages")

    def occurrences():
        return command("item.occurrences", {"item_id": event_id, "range_basis": "original_schedule",
                       "range_start": fact, "range_end": (first + timedelta(days=30)).isoformat().replace("+00:00", "Z")})

    def mutate(action, original=None, **extra):
        current = occurrences()
        value = {"command_id": unique(action), "actor_subject_id": "owner", "item_id": event_id,
                 "target_version": current["current_version"], "recurrence_set_id": current["recurrence_set_id"],
                 "recurrence_revision_id": current["recurrence_revision_id"], **extra}
        if original is not None:
            selected = next(v for v in current["occurrences"] if v["original_scheduled_fact"] == original)
            value["target_occurrence_key"] = selected["occurrence_key"]
        return command(action, value)

    def task_read(task):
        return command("schedule.show", {"item_id": task, "include": ["policies", "work", "attempts", "temporal_bindings"]})

    def assignment(assignment_id):
        return read(view="assignment", assignment_id=assignment_id)["assignment"]

    def check(condition, label):
        if not condition:
            raise AssertionError(label)

    initial = sorted(read(view="assignments", limit="100")["rows"], key=lambda r: r["current_selector"]["scheduled_fact"])
    check(len(initial) == 4, "four assignment slots")
    one, two, three, four = [assignment(row["assignment_id"]) for row in initial]
    facts = [row["current_selector"]["scheduled_fact"] for row in initial]
    old_work = task_read(one["task_item_id"])["work_instances"]
    mutate("recurrence.instance.override", facts[0], overridden_at_utc=at,
           expressed_scheduled_fact=(first + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"), reason_code="move_once")
    reconcile()
    check(assignment(one["assignment_id"])["task_item_id"] == one["task_item_id"], "move retains identity")
    shown = task_read(one["task_item_id"])
    check(shown["item"]["task_detail"]["due_anchor"]["local_time"] == "13:30:00", "follow moved class")
    check(all(next(v for v in shown["work_instances"] if v["work_instance_id"] == old["work_instance_id"])["status"]
              == "cancelled" for old in old_work), "old unattempted work cancelled")
    check(any(v["status"] == "eligible" for v in shown["work_instances"]), "replacement reminder exists")
    replacement = next(v for v in shown["work_instances"] if v["status"] == "eligible")
    check(datetime.fromisoformat(replacement["target_at_utc"]) - datetime.fromisoformat(replacement["eligible_at_utc"])
          == timedelta(minutes=10), "replacement remains ten minutes before pickup")
    for index in (1, 2):
        mutate("recurrence.instance.remove", facts[index], removed_at_utc=at, reason_code="no_class")
    reconcile()
    check(task_read(two["task_item_id"])["item"]["task_detail"]["task_status"] == "cancelled", "excluded pickup cancelled")
    suppressed = assignment(three["assignment_id"])
    request = write("suppress", assignment_id=three["assignment_id"], target_generation_id=suppressed["generation_id"],
                    target_task_item_id=suppressed["task_item_id"])
    request["expected"]["assignment_change_version"] = suppressed["change_version"]
    command("schedule.related_task_rule.assignment.suppress", request)
    mutate("recurrence.series.edit", edited_at_utc=at, edit_scope="whole_series", recurrence_patch={"exdates": []})
    reconcile()
    restored = assignment(two["assignment_id"])
    check(restored["task_item_id"] != two["task_item_id"] and
          restored["predecessor_generation_id"] == two["generation_id"], "one linked successor, no reopening")
    reconcile()
    check(assignment(two["assignment_id"])["generation_id"] == restored["generation_id"], "no duplicate restoration")
    check(assignment(three["assignment_id"])["task_item_id"] == three["task_item_id"], "suppression vetoes restoration")
    shown = task_read(four["task_item_id"])
    command("task.complete", {"command_id": unique("complete"), "actor_subject_id": "owner", "item_id": four["task_item_id"],
                             "target_version": shown["item"]["current_version"], "completed_at_utc": at})
    reconcile()
    check(task_read(four["task_item_id"])["item"]["task_detail"]["task_status"] == "done", "completed task consumed")

    def title_edit(task, title):
        shown = task_read(task)
        command("task.update", {"command_id": unique("customize"), "actor_subject_id": "owner", "item_id": task,
                                "target_version": shown["item"]["current_version"], "updated_at_utc": at, "patch": {"title": title}})

    title_edit(one["task_item_id"], "Individual pickup wording")
    config = copy.deepcopy(authoring["configuration"])
    config["task_template"]["item"]["title"] = "New managed wording"
    command("schedule.related_task_rule.update", write("update", configuration=config, adoption_scope="upcoming_open"))
    rows = reconcile()
    check(any(v["assignment_id"] == one["assignment_id"] and v["outcome"] == "decision_required" for v in rows),
          "overlapping customization requires decision")
    title_edit(one["task_item_id"], "New managed wording")
    reconcile()
    check(read()["rule"]["adoption_intent"] is None, "explicit resolution discharges adoption")
    verify_fake_attempt(task_read, one["task_item_id"], tmp, db)
    mutate("recurrence.instance.remove", facts[0], removed_at_utc=at, reason_code="after_delivery")
    reconcile()
    check(len(task_read(one["task_item_id"])["side_effect_attempts"]) == 1, "cancellation preserves attempt history")
    profile = command("notification_profile.create", {
        "contract_version": "spine.notification-profiles.v2", "command_id": unique("profile"),
        "actor_subject_id": "owner", "action_timestamp_utc": at,
        "owner": {"owner_kind": "subject", "owner_subject_id": "owner"}, "profile_key": "pickup_standard",
        "display_name": "Pickup standard", "description": None,
        "revision": {"compatible_item_types": ["task"], "templates": [{"template_key": "ten_minutes",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
            "late_handling": {"kind": "skip"}, "rendering": {"kind": "ordinary"}}]}})
    retired = []
    for disposition in ("keep_following", "detach_open", "cancel_open"):
        current = occurrences()
        request = copy.deepcopy(authoring)
        request.update(command_id=unique(disposition), rule_key=disposition,
                       source={"item_id": event_id, "item_version": current["current_version"],
                               "recurrence_set_id": current["recurrence_set_id"],
                               "recurrence_revision_id": current["recurrence_revision_id"]})
        if disposition == "keep_following":
            request["configuration"]["notification_plan"] = {
                "mode": "explicit", "notification_profile_id": profile["notification_profile_id"], "revision_resolution": "current"}
        else:
            request["configuration"].update(notification_plan=None, delivery=None, materialization={"mode": "none"})
        rule_id = command("schedule.related_task_rule.create", request)["result"]["rule"]["related_task_rule_id"]
        reconcile(rule_id)
        before = read(rule_id, view="assignments", limit="100")["rows"]
        check(len(before) == 3, "three remaining source classes")
        for row in before:
            shown = task_read(row["task_item_id"])
            expected = 1 if disposition == "keep_following" else 0
            check(len(shown["work_instances"]) == expected, "profile/zero-reminder generation")
        command("schedule.related_task_rule.retire", write("retire", rule_id, disposition=disposition))
        reconcile(rule_id)
        check(read(rule_id)["rule"]["retirement_intent"]["status"] == "complete", "retirement cleanup complete")
        for row in before:
            shown = task_read(row["task_item_id"])
            check(shown["item"]["task_detail"]["task_status"] == ("cancelled" if disposition == "cancel_open" else "open"),
                  "retirement preserves or cancels task as selected")
            binding = next(v for v in shown["temporal_bindings"] if v["temporal_binding_id"] == row["temporal_binding_id"])
            check(binding["binding_status"] == ("active" if disposition == "keep_following" else "retired"),
                  "retirement preserves or detaches binding as selected")
        retired.append(disposition)
    return {"move": True, "restoration": True, "suppression": True, "completion": True,
            "adoption_conflict_and_resolution": True, "reminder_modes": ["null", "explicit", "custom_additions"],
            "fake_attempts": "1", "retirements": retired}


def verify_fake_attempt(task_read, task, tmp, db):
    # Synthetic Tickerd time, normal attempt-backed processor, file-only sender.
    from tickerd import CycleEnvelope, RuntimeMode

    from spine.adapters.openclaw import OpenClawNotificationProcessor
    from spine.adapters.tickerd import SpineTickerdWorkAdapter
    from spine.core.errors import SpineValidationError
    from spine.ledger import connect
    from spine.runtime.worker import FakeOpenClawSender

    queued = next(v for v in task_read(task)["work_instances"] if v["status"] == "eligible")
    eligible = datetime.fromisoformat(queued["eligible_at_utc"].replace("Z", "+00:00"))
    envelope = CycleEnvelope(trace_id="release-fake", cycle_id="release-fake", causation_id="ROOT:release-fake",
                             scheduled_tick_ts=eligible, actual_start_ts=eligible, runtime_mode=RuntimeMode.ACTIVE)
    sends = Path(tmp) / "fake-sends.jsonl"
    connection = connect(db)
    try:
        adapter = SpineTickerdWorkAdapter(connection, runtime_mode="active",
                                         processor=OpenClawNotificationProcessor(FakeOpenClawSender(sends), channel_hint="test"))
        selected = next(v for v in adapter.list_work_items(envelope, 100) if v.item_id == queued["work_instance_id"])
        adapter.process_work_item(selected, envelope, side_effects_allowed=True)
        try:
            adapter.process_work_item(selected, envelope, side_effects_allowed=True)
        except SpineValidationError as exc:
            if exc.code != "work_outcome_rejected":
                raise
    finally:
        connection.close()
    shown = task_read(task)
    if not sends.exists() or len(sends.read_text().splitlines()) != 1 or len(shown["side_effect_attempts"]) != 1:
        raise AssertionError("expected one fake delivery: " + json.dumps({
            "work": shown["work_instances"], "attempts": shown["side_effect_attempts"], "send_log_exists": sends.exists()}))


if __name__ == "__main__":
    main()
