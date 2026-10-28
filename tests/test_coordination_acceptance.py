"""Operator stories across public commands, durable work, and protected reads.

Run with unittest discovery or pytest. All ledgers are temporary, clocks are
explicit, and delivery is an in-process fake; no daemon or network is required.
Expected times and people are authored here, not calculated by production helpers.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from spine.adapters import NormalizedOpenClawResult, OpenClawNotificationProcessor
from spine.commands import CommandContext, handle
from spine.commands.people_runtime import API, CONTRACT, PeopleContracts
from spine.core import SpineValidationError
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, get_notification_rendering, get_side_effect_attempt, get_work_instance, initialize_schema
from spine.services import list_eligible_work, retry_work, start_work, succeed_work
from spine.web.errors import WebError
from spine.web.people_service import PeopleService
from spine.web.provisioning import apply, plan
from spine.web.service import WebConfig

NOW = "2026-08-17T10:00:00Z"
EVENT_TIME = "2026-08-22T14:00:00Z"
FIRST_SEND = "2026-08-22T12:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


class CoordinationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "coordination.sqlite"
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        initialize_schema(self.db)
        self.context = CommandContext(ledger=self.db, ledger_path=str(self.path))
        self.sent = []
        for subject in ("author", "owner", "attendee", "assignee", "recipient", "observer"):
            self.command("subject.upsert", {
                "command_id": "seed-" + subject, "actor_subject_id": "author", "subject_id": subject,
                "subject_kind": "agent" if subject == "author" else "person", "display_name": subject,
                "updated_at_utc": NOW,
            })
        self.command("delivery_target.upsert", {
            "command_id": "seed-route", "actor_subject_id": "author", "delivery_target_id": "reminder-route",
            "owner_kind": "subject", "owner_subject_id": "recipient", "channel": "whatsapp",
            "adapter_name": "openclaw", "target_ref": "synthetic-recipient", "updated_at_utc": NOW,
        })

    def command(self, command, request):
        response = handle(command, request, self.context)
        self.assertTrue(response.get("ok"), response)
        return response

    def cli(self, command, request, *, ok=True):
        # Each invocation is a fresh interpreter. No fixture object or item ID
        # cache is available to it, and user-specific runtime config is excluded.
        environment = {key: value for key, value in os.environ.items() if not key.startswith("SPINE_")}
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-m", "spine.commands.cli", "--db", str(self.path), "--input", "-", *command.split(".")],
            input=json.dumps(request), text=True, capture_output=True, timeout=30, cwd=self.path.parent, env=environment,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["ok"], ok, response)
        return response

    @staticmethod
    def delivery():
        return {"recipient_kind": "subject", "recipient_subject_id": "recipient", "channel": "whatsapp",
                "target": {"resolution": "explicit", "delivery_target_id": "reminder-route"}}

    @staticmethod
    def reminder(key, offset):
        return {"policy_key": key, "schedule": {"kind": "once", "at": {
            "kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": str(offset)}},
            "late_handling": {"kind": "skip"}}

    @staticmethod
    def scheduled_time(date):
        # The scheduling command accepts local instants. UTC makes the expected
        # instant independent of DST rules; retain the required explicit tzdb pin.
        return {"time_basis": "local_instant", "local_date": date, "local_time": "14:00:00", "timezone": "UTC",
                "timezone_database_version": {"kind": "explicit", "version": system_timezone_database_version()}}

    @staticmethod
    def materialization():
        return {"mode": "bounded", "evaluated_at_utc": NOW,
                "range": {"kind": "item_relative", "start_offset_seconds": "-7200", "end_offset_seconds": "1"},
                "limit": "10"}

    def event_request(self):
        return {"contract_version": "spine.schedule-create.v4", "command_id": "appointment",
                "actor_subject_id": "author", "created_at_utc": NOW,
                "item": {"item_type": "event", "title": "Medical appointment", "event_detail": {"all_day": False}},
                "scheduled_time": self.scheduled_time("2026-08-22"),
                "people": {"participants": ["attendee"]}, "delivery": self.delivery(),
                "notification_plan": {"mode": "none", "custom_additions": [
                    self.reminder("early", -7200), self.reminder("final", -3600)]},
                "materialization": self.materialization()}

    def related_request(self, event, mode):
        binding = {"binding_mode": mode, "offset_basis": "elapsed", "offset_seconds": "-3600"}
        if mode == "follow_source":
            binding["source_terminal_behavior"] = "detach_at_last_value"
        return {"contract_version": "spine.schedule-related-task-create.v1", "command_id": "preparation-" + mode,
                "actor_subject_id": "author", "created_at_utc": NOW,
                "source": {"item_id": event["item_id"], "target_version": event["current_version"],
                           "anchor_role": "event_start", "scope": "item"},
                "task": {"title": "Prepare forms " + mode, "priority": "high",
                         "subject_roles": [{"subject_id": "assignee", "role": "assignee"}]},
                "relationship": {"relation_type": "part_of"}, "temporal_binding": binding,
                "delivery": self.delivery(), "reminders": [self.reminder("preparation", -1800)],
                "materialization": self.materialization()}

    def update_request(self, event, patch, *, command_id="edit-appointment", materialize=False):
        return {"contract_version": "spine.schedule-update.v4", "command_id": command_id,
                "actor_subject_id": "author", "item_id": event["item_id"], "target_version": event["current_version"],
                "updated_at_utc": "2026-08-22T12:05:00Z", "patch": patch,
                "materialization": self.materialization() if materialize else {"mode": "none"}}

    def show(self, item):
        return self.command("schedule.show", {"item_id": item})

    def people(self, item, *, version=None):
        request = {"contract_version": CONTRACT, "item_id": item}
        if version is not None:
            request["version"] = version
        return self.command("item.people.show", request)["people"]["associations"]

    def work(self, item):
        return sorted(self.show(item)["work_instances"], key=lambda row: (row["eligible_at_utc"], row["work_instance_id"]))

    def state(self):
        return "\n".join(self.db.iterdump())

    def process(self, work_id, at, *, result=None):
        result = result or NormalizedOpenClawResult.delivered(provider_ref="fake-receipt")
        start_work(self.db, work_instance_id=work_id, started_at_utc=at)
        captured = []

        def sender(message):
            # A second connection proves evidence is committed before transport.
            witness = connect(self.path)
            try:
                attempt = get_side_effect_attempt(witness, message.attempt_id)
                rendering = get_notification_rendering(witness, attempt_id=message.attempt_id)
            finally:
                witness.close()
            in_flight = self.show(get_work_instance(self.db, work_id)["item_id"])
            captured.append((message, attempt, rendering, in_flight))
            self.sent.append(message)
            return result

        outcome = OpenClawNotificationProcessor(sender=sender)(self.db, get_work_instance(self.db, work_id), SimpleNamespace(
            trace_id="acceptance", causation_id="ROOT:acceptance", actual_start_ts=datetime.fromisoformat(at),
        ))
        # Assert outside the processor so it cannot normalize a test assertion
        # into a generic adapter-exception outcome and hide the useful failure.
        self.assertEqual(len(captured), 1, outcome)
        message, attempt, rendering, in_flight = captured[0]
        self.assertEqual(attempt["attempt_status"], "started")
        self.assertEqual(rendering["body_text"], message.body_text)
        pending = next(a for a in in_flight["side_effect_attempts"] if a["attempt_id"] == message.attempt_id)
        self.assertEqual(pending["attempt_status"], "started")
        self.assertIn(in_flight["lifecycle"]["delivery"]["outcome_state"], ("pending", "mixed"))
        if outcome.status == "succeeded":
            succeed_work(self.db, work_instance_id=work_id, succeeded_at_utc=at, reason_code=outcome.reason_code)
        elif outcome.status == "retry":
            retry_work(self.db, work_instance_id=work_id, next_attempt_at_utc=outcome.next_attempt_at_utc,
                       updated_at_utc=at, reason_code=outcome.reason_code)
        else:
            self.fail(outcome)
        return outcome

    def provision(self, **operations):
        row = self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()
        epoch = str(row[0] if row else 0)
        proposed = plan(self.db, {"contract_version": "spine.trusted-web-provisioning.v1", "ledger_id": "acceptance",
                                 "expected_access_epoch": epoch, **operations})
        self.assertTrue(proposed["can_apply"], proposed)
        return apply(self.db, {"contract_version": "spine.trusted-web-provisioning.v1", "command_id": "provision-" + epoch,
                              "actor_subject_id": "owner", "action_timestamp_utc": NOW,
                              "expected_access_epoch": epoch, "plan": proposed})

    def test_plan_can_be_discovered_and_continued_by_fresh_processes(self):
        # Authors exit after every command; the successor receives only the ledger.
        event = self.cli("schedule.create", self.event_request())
        self.cli("schedule.related_task.create", self.related_request(event, "follow_source"))
        before = self.state()
        discovered = self.cli("item.list", {"limit": "10"})
        items = discovered["items"]
        self.assertEqual(len(items), 2)
        self.assertFalse(discovered["truncated"])
        by_type = {item["item_type"]: item for item in items}
        event_id, task_id = by_type["event"]["item_id"], by_type["task"]["item_id"]
        for item_id, expected_time, role, subject in (
            (event_id, EVENT_TIME, "participant", "attendee"),
            (task_id, "2026-08-22T13:00:00Z", "assignee", "assignee"),
        ):
            shown = self.cli("schedule.show", {"item_id": item_id})
            self.assertEqual(shown["scheduled_times"][0]["utc_instant"], expected_time)
            self.assertEqual(shown["lifecycle"]["delivery"]["attempt_state"], "not_attempted")
            roles = self.cli("item.people.show", {"contract_version": CONTRACT, "item_id": item_id})
            self.assertEqual([(r["subject_id"], r["role"]) for r in roles["people"]["associations"]], [(subject, role)])
        self.assertEqual(self.state(), before, "discovering a plan must not write it")
        task = self.cli("schedule.show", {"item_id": task_id, "include": ["relations", "temporal_bindings"]})
        self.assertEqual(task["temporal_bindings"][0]["source_item_id"], event_id)
        self.assertEqual(task["temporal_bindings"][0]["binding_state"], "current")
        self.assertEqual(task["relations"][0]["relation_type"], "part_of")
        completed = self.cli("task.complete", {"command_id": "successor-completes-preparation", "actor_subject_id": "assignee",
            "item_id": task_id, "target_version": by_type["task"]["current_version"], "completed_at_utc": FIRST_SEND})
        self.assertTrue(completed["completed"])
        after = self.cli("schedule.show", {"item_id": task_id})
        self.assertEqual(after["item"]["task_detail"]["task_status"], "done")
        self.assertNotIn(task_id, {w["item_id"] for w in list_eligible_work(self.db, now_utc="2026-08-22T13:00:00Z")})
        self.assertEqual(self.cli("schedule.show", {"item_id": event_id})["scheduled_times"][0]["utc_instant"], EVENT_TIME)

    def test_rescheduling_changes_followers_but_preserves_snapshots_and_delivery_history(self):
        event = self.command("schedule.create", self.event_request())
        follow = self.command("schedule.related_task.create", self.related_request(event, "follow_source"))["task"]["item_id"]
        snapshot = self.command("schedule.related_task.create", self.related_request(event, "snapshot"))["task"]["item_id"]
        original_people = {item: self.people(item) for item in (event["item_id"], follow, snapshot)}
        old_work = self.work(event["item_id"])
        self.assertEqual(len(old_work), 2)
        self.process(old_work[0]["work_instance_id"], FIRST_SEND)
        evidence = self.show(event["item_id"])["side_effect_attempts"]
        snapshot_work = self.work(snapshot)
        follow_work = self.work(follow)
        self.command("schedule.update", self.update_request(event, {
            "scheduled_time": self.scheduled_time("2026-08-23")}, materialize=True))
        binding = self.command("schedule.binding.list", {"contract_version": "spine.schedule-binding-list.v1",
            "target_item_id": follow, "limit": "10"})["bindings"][0]
        self.assertEqual(binding["binding_state"], "stale")
        with self.assertRaisesRegex(SpineValidationError, "stale_work_instance"):
            start_work(self.db, work_instance_id=follow_work[0]["work_instance_id"], started_at_utc="2026-08-22T12:30:00Z")
        repaired = self.command("schedule.binding.reconcile", {
            "contract_version": "spine.schedule-binding-reconcile.v1", "command_id": "refresh-preparation",
            "actor_subject_id": "author", "reconciled_at_utc": "2026-08-22T12:06:00Z",
            **binding["reconcile_inputs"], "materialization": self.materialization()})
        self.assertEqual(repaired["resolution_outcome"], "target_rescheduled")
        self.assertEqual(self.show(follow)["scheduled_times"][0]["utc_instant"], "2026-08-23T13:00:00Z")
        self.assertEqual(self.show(snapshot)["scheduled_times"][0]["utc_instant"], "2026-08-22T13:00:00Z")
        self.assertEqual(self.work(snapshot), snapshot_work)
        self.assertEqual(self.show(event["item_id"])["side_effect_attempts"], evidence)
        self.assertEqual(get_work_instance(self.db, old_work[0]["work_instance_id"])["status"], "succeeded")
        self.assertEqual(get_work_instance(self.db, old_work[1]["work_instance_id"])["status"], "cancelled")
        for item, previous in original_people.items():
            self.assertEqual([(p["subject_id"], p["role"]) for p in self.people(item)],
                             [(p["subject_id"], p["role"]) for p in previous])
        eligible = list_eligible_work(self.db, now_utc="2026-08-23T13:00:00Z")
        self.assertEqual(sorted(w["eligible_at_utc"] for w in eligible if w["item_id"] == event["item_id"]),
                         ["2026-08-23T12:00:00Z", "2026-08-23T13:00:00Z"])
        # Relative bindings §7.6: bounded replacement work uses successor truth,
        # so a window relative to yesterday's due time cannot satisfy the story.
        self.assertEqual([w["eligible_at_utc"] for w in eligible if w["item_id"] == follow], ["2026-08-23T12:30:00Z"])
        self.assertNotIn(old_work[1]["work_instance_id"], {w["work_instance_id"] for w in eligible})
        self.assertNotIn(follow_work[0]["work_instance_id"], {w["work_instance_id"] for w in eligible})
        self.assertEqual(len(self.sent), 1)

    def test_people_access_and_delivery_remain_independent_through_changes(self):
        event = self.command("schedule.create", self.event_request())
        task = self.command("schedule.related_task.create", self.related_request(event, "snapshot"))["task"]["item_id"]
        self.provision(operators=[{"operation": "create", "subject_id": s, "display_name": s,
                                   "activation_basis": "trusted_local_approval"}
                                  for s in ("owner", "attendee", "assignee", "recipient", "observer")],
                       item_adoptions=[{"operation": "create", "item_id": item, "expected_item_version": "1",
                                        "owner_scope": {"owner_kind": "subject", "owner_subject_id": "owner"}}
                                       for item in (event["item_id"], task)])
        accounts = {r["subject_id"]: r["account_id"] for r in self.db.execute("SELECT * FROM account_subject_bindings")}
        service = PeopleService(WebConfig(str(self.path), "acceptance"), contracts=PeopleContracts.packaged(), now=lambda: NOW)

        def read(item, subject):
            return service.execute("item.people.show", {"contract_version": API,
                "request": {"contract_version": CONTRACT, "item_id": item}}, accounts[subject], "selection")

        for item, subject in ((event["item_id"], "attendee"), (task, "assignee"), (event["item_id"], "recipient")):
            before = self.state()
            with self.assertRaises(WebError) as caught:
                read(item, subject)
            self.assertEqual(caught.exception.code, "resource_unavailable")
            self.assertEqual(self.state(), before)
        self.assertTrue(read(event["item_id"], "owner")["ok"])
        work_before = {item: self.work(item) for item in (event["item_id"], task)}
        self.command("item.people.update", {"contract_version": CONTRACT, "command_id": "change-attendance",
            "actor_subject_id": "author", "item_id": event["item_id"], "target_version": "1", "updated_at_utc": NOW,
            "people": {"participants": ["observer"]}})
        self.command("item.people.update", {"contract_version": CONTRACT, "command_id": "change-assignee",
            "actor_subject_id": "author", "item_id": task, "target_version": "1", "updated_at_utc": NOW,
            "people": {"assignees": ["attendee"]}})
        with self.assertRaises(WebError) as caught:
            read(event["item_id"], "observer")
        self.assertEqual(caught.exception.code, "resource_unavailable")
        with self.assertRaises(WebError) as caught:
            read(task, "attendee")
        self.assertEqual(caught.exception.code, "resource_unavailable")
        granted = self.provision(grants=[{"operation": "create", "resource_kind": "item", "resource_id": event["item_id"],
            "resource_owner_revision": "1", "grantee": {"owner_kind": "subject", "owner_subject_id": "assignee"},
            "operations": ["item.read"], "starts_at_utc": NOW, "ends_at_utc": None}])
        self.assertTrue(read(event["item_id"], "assignee")["ok"])
        self.assertEqual([p["subject_id"] for p in self.people(event["item_id"])], ["observer"])
        self.assertEqual([p["subject_id"] for p in self.people(task)], ["attendee"])
        self.provision(grants=[{"operation": "revoke", "grant_id": granted["results"][0]["row_ids"][0], "expected_revision": "1"}])
        with self.assertRaises(WebError):
            read(event["item_id"], "assignee")
        for item, before in work_before.items():
            self.assertEqual(self.work(item), before)
        self.process(work_before[event["item_id"]][0]["work_instance_id"], FIRST_SEND)
        self.process(work_before[task][0]["work_instance_id"], "2026-08-22T12:30:00Z")
        self.assertEqual([m.target_ref for m in self.sent], ["synthetic-recipient", "synthetic-recipient"])
        self.assertEqual([p["subject_id"] for p in self.people(event["item_id"], version="1")], ["attendee"])

    def test_lost_response_replay_preserves_later_truth_and_refuses_conflicting_instructions(self):
        request = self.event_request()
        original = self.cli("schedule.create", request)
        changed = self.command("schedule.update", self.update_request(original, {"people": {"participants": ["observer"]}}))
        before = self.state()
        replay = self.cli("schedule.create", request)
        self.assertEqual(replay["command_receipt_id"], original["command_receipt_id"])
        self.assertEqual(replay["item_id"], original["item_id"])
        self.assertEqual(replay["people"], original["people"])
        self.assertEqual(self.state(), before)
        conflicting = copy.deepcopy(request)
        conflicting["item"]["title"] = "Different instruction"
        refused = self.cli("schedule.create", conflicting, ok=False)
        self.assertEqual(refused["error"]["code"], "semantic_conflict")
        stale = self.cli("schedule.update", self.update_request(original, {"people": {"participants": []}},
                                                                  command_id="stale-agent-edit"), ok=False)
        self.assertEqual(stale["error"]["code"], "stale_version")
        self.assertEqual(self.state(), before)
        self.assertEqual(self.show(original["item_id"])["item"]["current_version"], changed["current_version"])
        self.assertEqual([p["subject_id"] for p in self.people(original["item_id"])], ["observer"])
        self.assertEqual(len(self.work(original["item_id"])), 2)
        self.assertEqual(self.show(original["item_id"])["side_effect_attempts"], [])

    def test_readback_distinguishes_planning_failure_retry_and_confirmed_delivery(self):
        request = self.event_request()
        request["materialization"] = {"mode": "none"}
        event = self.command("schedule.create", request)
        planned = self.show(event["item_id"])
        self.assertEqual(planned["work_instances"], [])
        self.assertEqual(planned["lifecycle"]["delivery"]["attempt_state"], "not_attempted")
        self.command("schedule.update", self.update_request(event, {"item": {"title": "Bring medical forms"}}, materialize=True)
                     | {"updated_at_utc": "2026-08-17T10:05:00Z"})
        work_id = self.work(event["item_id"])[0]["work_instance_id"]
        self.assertEqual(self.show(event["item_id"])["side_effect_attempts"], [])
        retry_at = "2026-08-22T12:05:00Z"
        failed = self.process(work_id, FIRST_SEND, result=NormalizedOpenClawResult.transient_failure(
            reason_code="synthetic_timeout", next_attempt_at_utc=retry_at))
        self.assertEqual(failed.status, "retry")
        first = self.show(event["item_id"])["side_effect_attempts"][0]
        self.assertEqual(first["attempt_status"], "failed")
        self.assertNotIn("provider_ref", first)
        self.assertEqual(self.show(event["item_id"])["lifecycle"]["delivery"]["outcome_state"], "failed")
        self.assertNotIn(work_id, {w["work_instance_id"] for w in list_eligible_work(self.db, now_utc=FIRST_SEND)})
        self.assertIn(work_id, {w["work_instance_id"] for w in list_eligible_work(self.db, now_utc=retry_at)})
        self.process(work_id, retry_at)
        final = self.show(event["item_id"])
        attempts = {a["attempt_id"]: a for a in final["side_effect_attempts"]}
        self.assertEqual(attempts[first["attempt_id"]], first)
        self.assertEqual(sorted(a["attempt_status"] for a in attempts.values()), ["failed", "succeeded"])
        self.assertEqual(final["lifecycle"]["delivery"]["status_counts"],
                         {"started": "0", "failed": "1", "succeeded": "1", "rejected": "0"})
        self.assertEqual(final["lifecycle"]["delivery"]["outcome_state"], "mixed")
        self.assertEqual(get_work_instance(self.db, work_id)["status"], "succeeded")
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0].provider_idempotency_key, self.sent[1].provider_idempotency_key)
        self.assertNotEqual(self.sent[0].attempt_id, self.sent[1].attempt_id)
        self.assertNotIn(work_id, {w["work_instance_id"] for w in list_eligible_work(self.db, now_utc=retry_at)})
        before = self.state()
        self.assertEqual(self.cli("schedule.show", {"item_id": event["item_id"]}), final)
        self.assertEqual(self.state(), before)
