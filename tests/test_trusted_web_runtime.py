from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_schedule_create_command as schedule_helpers

from spine.commands import CommandContext, handle
from spine.ledger import connect, initialize_schema
from spine.web.contracts import API, validate
from spine.web.errors import WebError
from spine.web.http import create_app
from spine.web.provisioning import apply, plan
from spine.web.service import WebConfig, WebService

AT = "2026-09-01T09:00:00Z"


class TrustedWebRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "ledger.sqlite")
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        initialize_schema(self.db)
        self.ctx = CommandContext(ledger=self.db, ledger_path=self.path)
        for subject in ("owner", "other"):
            self.ok(
                handle(
                    "subject.upsert",
                    dict(
                        command_id="seed-" + subject,
                        actor_subject_id="owner",
                        subject_id=subject,
                        subject_kind="person",
                        display_name=subject,
                        updated_at_utc=AT,
                    ),
                    self.ctx,
                )
            )
        self.ok(
            handle(
                "delivery_target.upsert",
                dict(
                    command_id="route",
                    actor_subject_id="owner",
                    delivery_target_id="whatsapp-owner",
                    owner_kind="subject",
                    owner_subject_id="owner",
                    channel="whatsapp",
                    adapter_name="openclaw",
                    target_ref="test-only",
                    updated_at_utc=AT,
                ),
                self.ctx,
            )
        )
        self.bootstrap = self.provision(
            operators=[
                dict(operation="create", subject_id=s, display_name=s, activation_basis="trusted_local_approval")
                for s in ("owner", "other")
            ]
        )
        self.accounts = {r["subject_id"]: r["account_id"] for r in self.db.execute("SELECT * FROM account_subject_bindings")}
        self.service = WebService(WebConfig(self.path, "test-ledger"), cursor_key="test-key")

    def ok(self, result):
        self.assertTrue(result.get("ok"), result)
        return result

    def provision(self, **operations):
        old = self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()
        epoch = str(old[0] if old else 0)
        proposed = plan(
            self.db,
            dict(contract_version="spine.trusted-web-provisioning.v1", ledger_id="test-ledger", expected_access_epoch=epoch, **operations),
        )
        self.assertTrue(proposed["can_apply"], proposed)
        validate("trusted-web-provisioning-plan-response.schema.json", proposed)
        req = dict(
            contract_version="spine.trusted-web-provisioning.v1",
            command_id="provision-" + epoch,
            actor_subject_id="owner",
            action_timestamp_utc=AT,
            expected_access_epoch=epoch,
            plan=proposed,
        )
        result = apply(self.db, req)
        validate("trusted-web-provisioning-apply-response.schema.json", result)
        self.last_apply = req
        return result

    def event(self, cid="web-event"):
        request = schedule_helpers.ScheduleCreateCommandTests.event_request(self, command_id=cid)
        return dict(
            contract_version=API,
            request=request,
            create_owner_scope=dict(owner_kind="subject", owner_subject_id="owner"),
            expected_access_epoch=str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]),
        )

    def run_command(self, command, body, subject="owner"):
        return self.service.execute(command, body, self.accounts[subject], "selection")

    def test_provision_replay_and_read_only_surfaces(self):
        replay = apply(self.db, self.last_apply)
        self.assertTrue(replay["replayed"])
        before = self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
        for kind in ("ready", "info", "operators"):
            self.assertTrue(self.service.public(kind))
        self.run_command("context", {})
        self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"})
        self.assertEqual(before, self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0])

    def test_create_read_replay_and_foreign_denial(self):
        body = self.event()
        created = self.run_command("schedule.create", body)
        identity = created["result"]["item_id"]
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM web_receipt_links").fetchone()[0], 1)
        shown = self.run_command("schedule.show", dict(contract_version=API, request={"item_id": identity}))
        self.assertEqual(shown["result"]["item"]["item_id"], identity)
        replay = self.run_command("schedule.create", body)
        self.assertEqual(replay["result"]["command_receipt_id"], created["result"]["command_receipt_id"])
        with self.assertRaises(WebError) as caught:
            self.run_command("schedule.show", dict(contract_version=API, request={"item_id": identity}), "other")
        self.assertEqual(caught.exception.code, "resource_unavailable")
        with self.assertRaises(WebError):
            self.run_command("schedule.create", body, "other")
        items = self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"})
        self.assertEqual([e["item_id"] for e in items["result"]["entries"]], [identity])

    def test_late_failure_rolls_back_domain_ownership_and_receipts(self):
        before = {
            t: self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("coordination_items", "command_receipts", "work_instances", "audit_log", "item_access_owners")
        }
        original = self.service.command

        def fail_after(*args):
            original(*args)
            raise WebError("capacity_exceeded")

        with patch.object(self.service, "command", side_effect=fail_after), self.assertRaises(WebError):
            self.run_command("schedule.create", self.event())
        for table, count in before.items():
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count, table)
        self.ok(self.run_command("schedule.create", self.event()))

    def test_http_boundary(self):
        client = create_app(WebConfig(self.path, "test-ledger")).test_client()
        headers = {
            "Host": "127.0.0.1:8090",
            "Origin": "http://127.0.0.1:8090",
            "X-Spine-Account-ID": self.accounts["owner"],
            "X-Spine-Selection-ID": "selection",
            "Content-Type": "application/json",
        }
        good = client.post("/api/v1/context", headers=headers, data="{}")
        self.assertEqual(good.status_code, 200, good.json)
        self.assertEqual(good.headers["Cache-Control"], "no-store")
        for raw in ('{"x":1,"x":2}', "[1]", '{"bad":NaN}'):
            self.assertEqual(client.post("/api/v1/context", headers=headers, data=raw).status_code, 400)
        self.assertEqual(client.post("/api/v1/context", headers={**headers, "Origin": "https://evil.invalid"}, data="{}").status_code, 403)
        self.assertEqual(client.post("/api/v1/commands/web_access.apply", headers=headers, data="{}").status_code, 404)
        self.assertEqual(client.post("/api/v1/context", headers=headers, data=" " * 1048577).status_code, 413)

    def test_unauthorized_and_failed_reads_have_no_receipts(self):
        before = self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
        for account in ("unknown", self.accounts["other"]):
            with self.assertRaises(WebError):
                self.service.execute("schedule.show", {"contract_version": API, "request": {"item_id": "hidden"}}, account, "s")
        self.assertEqual(before, self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0])

    def agenda(self, limit="50"):
        return dict(
            contract_version="spine.trusted-web-agenda.v1",
            evaluated_at_utc="2026-08-14T09:00:00Z",
            range_start_local="2026-08-14T00:00:00",
            range_end_local="2026-08-15T00:00:00",
            timezone="America/Toronto",
            timezone_database_version={"kind": "system_current"},
            limit=limit,
        )

    def test_items_agenda_pagination_tampering_and_stale_snapshot(self):
        first = self.run_command("schedule.create", self.event("first"))["result"]["item_id"]
        self.run_command("schedule.create", self.event("second"))
        for target, query in (("items", {"contract_version": "spine.trusted-web-items.v1", "limit": "1"}), ("agenda", self.agenda("1"))):
            page = self.run_command(target, query)["result"]
            self.assertTrue(page["has_more"], page)
            last = self.run_command(target, {**query, "cursor": page["next_cursor"]})["result"]
            self.assertFalse(last["has_more"])
            self.assertNotEqual(page["entries"][0]["item_id"], last["entries"][0]["item_id"])
            with self.assertRaises(WebError) as caught:
                self.run_command(target, {**query, "cursor": page["next_cursor"] + "tamper"})
            self.assertEqual(caught.exception.code, "access_changed")
            with self.assertRaises(WebError):
                self.run_command(target, {**query, "cursor": page["next_cursor"]}, "other")
        cursor = self.run_command("items", {"contract_version": "spine.trusted-web-items.v1", "limit": "1"})["result"]["next_cursor"]
        self.ok(
            handle(
                "event.update",
                {
                    "command_id": "local-edit",
                    "actor_subject_id": "owner",
                    "item_id": first,
                    "target_version": "1",
                    "updated_at_utc": AT,
                    "patch": {"title": "Changed locally"},
                },
                self.ctx,
            )
        )
        with self.assertRaises(WebError) as caught:
            self.run_command("items", {"contract_version": "spine.trusted-web-items.v1", "limit": "1", "cursor": cursor})
        self.assertEqual(caught.exception.code, "access_changed")

    def test_update_cancel_stale_version_and_task_completion(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        epoch = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        update = dict(
            contract_version=API,
            expected_access_epoch=epoch,
            request={
                "contract_version": "spine.schedule-update.v2",
                "command_id": "web-update",
                "actor_subject_id": "owner",
                "item_id": item,
                "target_version": "1",
                "updated_at_utc": AT,
                "patch": {"item": {"title": "New title"}},
                "materialization": {"mode": "none"},
            },
        )
        self.ok(self.run_command("schedule.update", update))
        stale = copy.deepcopy(update)
        stale["request"]["command_id"] = "stale-update"
        with self.assertRaises(WebError) as caught:
            self.run_command("schedule.update", stale)
        self.assertEqual(caught.exception.code, "domain_conflict")
        cancel = dict(
            contract_version=API,
            expected_access_epoch=epoch,
            request={
                "contract_version": "spine.schedule-cancel.v1",
                "command_id": "web-cancel",
                "actor_subject_id": "owner",
                "item_id": item,
                "target_version": "2",
                "cancelled_at_utc": AT,
                "reason_code": "operator_cancelled",
            },
        )
        self.ok(self.run_command("schedule.cancel", cancel))
        body = self.event("task")
        body["request"]["item"] = {"item_type": "task", "title": "Test task", "task_detail": {}}
        task = self.run_command("schedule.create", body)["result"]["item_id"]
        complete = dict(
            contract_version=API,
            expected_access_epoch=str(int(epoch) + 1),
            request={
                "command_id": "web-complete",
                "actor_subject_id": "owner",
                "item_id": task,
                "target_version": "1",
                "completed_at_utc": AT,
            },
        )
        completed = self.run_command("task.complete", complete)
        self.assertEqual(completed["work_reconciliation"], "not_performed_by_this_command")
        self.assertEqual(
            self.db.execute("SELECT task_status FROM task_details WHERE item_id=? ORDER BY version DESC", (task,)).fetchone()[0], "done"
        )

    def test_group_roles_creator_rights_and_approval_revocation(self):
        self.ok(
            handle(
                "subject_group.upsert",
                {
                    "command_id": "group",
                    "actor_subject_id": "owner",
                    "group_id": "group",
                    "display_name": "Our group",
                    "updated_at_utc": AT,
                },
                self.ctx,
            )
        )
        self.provision(
            memberships=[
                {"operation": "create", "group_id": "group", "subject_id": s, "role": r, "starts_at_utc": AT}
                for s, r in (("owner", "owner"), ("other", "member"))
            ]
        )
        self.ok(
            handle(
                "delivery_target.upsert",
                {
                    "command_id": "group-route",
                    "actor_subject_id": "owner",
                    "delivery_target_id": "group-route",
                    "owner_kind": "subject_group",
                    "owner_group_id": "group",
                    "channel": "whatsapp",
                    "adapter_name": "openclaw",
                    "target_ref": "test-group",
                    "updated_at_utc": AT,
                },
                self.ctx,
            )
        )
        body = self.event("member-event")
        body["request"]["actor_subject_id"] = "other"
        body["create_owner_scope"] = {"owner_kind": "subject_group", "owner_group_id": "group"}
        body["request"]["delivery"] = {
            "recipient_kind": "subject_group",
            "recipient_group_id": "group",
            "channel": "whatsapp",
            "target": {"resolution": "explicit", "delivery_target_id": "group-route"},
        }
        with self.assertRaises(WebError):
            self.run_command("schedule.create", body, "other")
        self.provision(
            route_approvals=[
                {
                    "operation": "set",
                    "delivery_target_id": "group-route",
                    "owner_group_id": "group",
                    "expected_route_security_revision": "1",
                    "expected_approval_revision": "0",
                    "status": "approved",
                }
            ]
        )
        body["expected_access_epoch"] = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        item = self.run_command("schedule.create", body, "other")["result"]["item_id"]
        from spine.web.permissions import Permissions

        p = Permissions(self.db, self.accounts["other"], AT)
        self.assertEqual(p.item(item, edit=True)["creator_entitlement_subject_id"], "other")
        own = self.event("owner-event")
        own["create_owner_scope"] = body["create_owner_scope"]
        own["request"]["delivery"] = body["request"]["delivery"]
        second = self.run_command("schedule.create", own)["result"]["item_id"]
        with self.assertRaises(WebError):
            Permissions(self.db, self.accounts["other"], AT).item(second, edit=True)
        self.ok(
            handle(
                "delivery_target.upsert",
                {
                    "command_id": "route-retarget",
                    "actor_subject_id": "owner",
                    "delivery_target_id": "group-route",
                    "owner_kind": "subject_group",
                    "owner_group_id": "group",
                    "channel": "whatsapp",
                    "adapter_name": "openclaw",
                    "target_ref": "test-group",
                    "status": "inactive",
                    "updated_at_utc": AT,
                },
                self.ctx,
            )
        )
        with self.assertRaises(WebError):
            Permissions(self.db, self.accounts["other"], AT).route("group-route", release_owner=body["create_owner_scope"])

    def test_grant_adoption_revoke_and_local_cli_stays_privileged(self):
        item = self.ok(handle("schedule.create", self.event()["request"], self.ctx))["item_id"]
        with self.assertRaises(WebError):
            self.run_command("schedule.show", dict(contract_version=API, request={"item_id": item}))
        self.provision(
            item_adoptions=[
                {
                    "operation": "create",
                    "item_id": item,
                    "expected_item_version": "1",
                    "owner_scope": {"owner_kind": "subject", "owner_subject_id": "owner"},
                }
            ]
        )
        granted = self.provision(
            grants=[
                {
                    "operation": "create",
                    "resource_kind": "item",
                    "resource_id": item,
                    "resource_owner_revision": "1",
                    "grantee": {"owner_kind": "subject", "owner_subject_id": "other"},
                    "operations": ["item.read"],
                    "starts_at_utc": AT,
                    "ends_at_utc": None,
                }
            ]
        )
        # A shared item with an independently private route fails complete readback disclosure.
        with self.assertRaises(WebError):
            self.run_command("schedule.show", dict(contract_version=API, request={"item_id": item}), "other")
        listed = self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"}, "other")
        self.assertEqual(len(listed["result"]["entries"]), 1)
        grant = granted["results"][0]["row_ids"][0]
        self.provision(grants=[{"operation": "revoke", "grant_id": grant, "expected_revision": "1"}])
        self.assertEqual(self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"}, "other")["result"]["entries"], [])
        self.ok(handle("schedule.show", {"item_id": item}, self.ctx))

    def test_budgets_and_runtime_preflight_fail_closed(self):
        tiny = WebService(WebConfig(self.path, "test-ledger", sql_steps=1))
        with self.assertRaises(WebError) as caught:
            tiny.execute("items", {"contract_version": "spine.trusted-web-items.v1"}, self.accounts["owner"], "s")
        self.assertEqual(caught.exception.code, "capacity_exceeded")
        traced = []
        original = self.service.connection

        def connection():
            db = original()
            db.set_trace_callback(traced.append)
            return db

        with patch.object(self.service, "connection", side_effect=connection):
            self.service.public("ready")
            self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"})
        self.assertFalse(any(any(s in q.lower() for s in ("integrity_check", "quick_check", "foreign_key_check")) for q in traced))
        with self.db:
            self.db.execute("DROP INDEX item_access_owners_subject")
        client = create_app(WebConfig(self.path, "test-ledger")).test_client()
        self.assertEqual(client.get("/health/ready", headers={"Host": "127.0.0.1:8090"}).status_code, 503)

    def test_catalog_registry_commands_and_profile_application(self):
        scope = {"owner_kind": "subject", "owner_subject_id": "owner"}
        common = {"actor_subject_id": "owner", "action_timestamp_utc": AT, "owner": scope}
        archetype = self.ok(
            handle(
                "item_archetype.create",
                {
                    **common,
                    "contract_version": "spine.item-archetypes.v1",
                    "command_id": "archetype",
                    "archetype_key": "lesson",
                    "revision": {"display_name": "Lesson", "description": None, "compatible_item_types": ["event"]},
                },
                self.ctx,
            )
        )
        profile = self.ok(
            handle(
                "notification_profile.create",
                {
                    **common,
                    "contract_version": "spine.notification-profiles.v1",
                    "command_id": "profile",
                    "profile_key": "lesson_standard",
                    "display_name": "Lesson standard",
                    "description": None,
                    "revision": {
                        "compatible_item_types": ["event"],
                        "templates": [
                            {
                                "template_key": "hour",
                                "schedule": {
                                    "kind": "once",
                                    "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"},
                                },
                                "late_handling": {"kind": "skip"},
                            }
                        ],
                    },
                },
                self.ctx,
            )
        )
        aid, pid = archetype["item_archetype_id"], profile["notification_profile_id"]
        self.ok(
            handle(
                "notification_profile.binding.set",
                {
                    **common,
                    "contract_version": "spine.notification-profile-bindings.v1",
                    "command_id": "bind",
                    "item_archetype_id": aid,
                    "notification_profile_id": pid,
                },
                self.ctx,
            )
        )
        cases = {
            "item_archetype.list": {"contract_version": "spine.item-archetypes.v1", "owner": scope},
            "item_archetype.show": {"contract_version": "spine.item-archetypes.v1", "item_archetype_id": aid},
            "notification_profile.list": {"contract_version": "spine.notification-profiles.v1", "owner": scope},
            "notification_profile.show": {"contract_version": "spine.notification-profiles.v1", "notification_profile_id": pid},
            "notification_profile.binding.list": {"contract_version": "spine.notification-profile-bindings.v1", "owner": scope},
            "notification_profile.resolve": {
                "contract_version": "spine.notification-profile-bindings.v1",
                "item_type": "event",
                "item_archetype_id": aid,
                "scope_chain": [scope],
            },
        }
        for cmd, request in cases.items():
            if cmd.endswith(".list"):
                request["limit"] = "50"
            self.ok(self.run_command(cmd, {"contract_version": API, "request": request}))
            with self.assertRaises(WebError):
                self.run_command(cmd, {"contract_version": API, "request": request}, "other")
        body = self.event("profile-event")
        body["request"]["item"]["archetype"] = {
            "item_archetype_id": aid,
            "revision_resolution": "current",
            "selection_source": "agent_selected",
        }
        body["request"]["notification_plan"] = {
            "mode": "archetype_default",
            "scope_chain": [scope],
            "on_no_match": "fail",
            "suppress_template_keys": [],
            "replacements": [],
            "custom_additions": [],
        }
        self.ok(self.run_command("schedule.create", body))

    def test_countdown_builder_and_recurring_occurrences(self):
        body = json.loads((Path(__file__).parent / "fixtures/trusted_web/contracts/request_schedule_build.json").read_text())
        body["request"]["actor_subject_id"] = "owner"
        body["request"]["delivery"] = self.event()["request"]["delivery"]
        body["create_owner_scope"] = {"owner_kind": "subject", "owner_subject_id": "owner"}
        self.ok(self.run_command("schedule.build", body))
        body = self.event("recurring-event")
        body["request"]["scheduled_time"]["recurrence"] = {
            "rules": [
                {
                    "frequency": "DAILY",
                    "interval": "1",
                    "seed": "2026-08-14T10:00:00",
                    "start_bound": "2026-08-14T10:00:00",
                    "end_condition": {"kind": "count", "count": "3"},
                }
            ]
        }
        body["request"]["materialization"] = {"mode": "none"}
        created = self.run_command("schedule.create", body)
        self.ok(
            self.run_command(
                "item.occurrences",
                {
                    "contract_version": API,
                    "request": {
                        "item_id": created["result"]["item_id"],
                        "range_start": "2026-08-14T00:00:00",
                        "range_end": "2026-08-17T00:00:00",
                        "limit": "100",
                    },
                },
            )
        )

    def test_atomic_deferred_constraint_and_busy_local_writer(self):
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command(), self.db:
            self.db.execute("INSERT INTO subject_memberships VALUES('bad','missing','owner','member','active',?,NULL,1)", (AT,))
        self.assertIsNone(self.db.execute("SELECT 1 FROM subject_memberships WHERE membership_id='bad'").fetchone())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            service = WebService(WebConfig(self.path, "test-ledger", busy_milliseconds=10))
            with self.assertRaises(WebError) as caught:
                service.execute("schedule.create", self.event(), self.accounts["owner"], "s")
            self.assertEqual(caught.exception.code, "capacity_exceeded")
        finally:
            self.db.rollback()
        self.ok(self.run_command("schedule.create", self.event()))

    def test_revocation_after_read_and_before_write_noop_and_history(self):
        row = dict(self.db.execute("SELECT * FROM account_subject_bindings WHERE subject_id='owner'").fetchone())
        operation = {
            "operation": "set",
            "account_id": row["account_id"],
            "binding_id": row["binding_id"],
            "expected_account_revision": "1",
            "expected_binding_revision": "1",
            "eligible": True,
        }
        no_op = self.provision(operators=[operation])
        self.assertFalse(no_op["changed"])
        operation["eligible"] = False
        proposed = plan(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "ledger_id": "test-ledger",
                "expected_access_epoch": "1",
                "operators": [operation],
            },
        )
        req = {
            "contract_version": "spine.trusted-web-provisioning.v1",
            "command_id": "revoke-operator",
            "actor_subject_id": "owner",
            "action_timestamp_utc": AT,
            "expected_access_epoch": "1",
            "plan": proposed,
        }
        original = self.service.query

        def query(*args):
            result = original(*args)
            apply(self.db, req)
            return result

        with patch.object(self.service, "query", side_effect=query), self.assertRaises(WebError) as caught:
            self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"})
        self.assertEqual(caught.exception.code, "identity_unavailable")
        with self.assertRaises(WebError):
            self.run_command("schedule.create", self.event())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 0)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM web_operator_revisions WHERE account_id=?", (row["account_id"],)).fetchone()[0], 2
        )
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.db.execute("UPDATE web_operator_revisions SET eligible=1")

    def test_same_id_simultaneous_web_writers(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        barrier = Barrier(2)
        body = self.event()

        def invoke():
            barrier.wait()
            return self.run_command("schedule.create", copy.deepcopy(body))

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: invoke(), range(2)))
        self.assertEqual(results[0]["result"]["item_id"], results[1]["result"]["item_id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM web_receipt_links").fetchone()[0], 1)

    def test_unreadable_bad_timezone_is_not_hydrated_and_unscheduled_tasks_list(self):
        visible = self.run_command("schedule.create", self.event("visible"))["result"]["item_id"]
        hidden = self.ok(handle("schedule.create", self.event("hidden")["request"], self.ctx))["item_id"]
        import spine.commands.core as core

        original = core._hydrated_item
        seen = []

        def hydrate(db, item, *args, **kwargs):
            seen.append(item)
            if item == hidden:
                raise AssertionError("hidden item was hydrated")
            return original(db, item, *args, **kwargs)

        with patch.object(core, "_hydrated_item", side_effect=hydrate):
            self.run_command("agenda", self.agenda())
        self.assertIn(visible, seen)
        self.assertNotIn(hidden, seen)
        task = self.ok(
            handle(
                "task.create",
                {"command_id": "unscheduled", "actor_subject_id": "owner", "title": "Unscheduled", "created_at_utc": AT},
                self.ctx,
            )
        )["item_id"]
        self.provision(
            item_adoptions=[
                {
                    "operation": "create",
                    "item_id": task,
                    "expected_item_version": "1",
                    "owner_scope": {"owner_kind": "subject", "owner_subject_id": "owner"},
                }
            ]
        )
        entries = self.run_command("items", {"contract_version": "spine.trusted-web-items.v1"})["result"]["entries"]
        self.assertIn(task, [e["item_id"] for e in entries])

    def test_stale_adoption_plan_and_failed_batch_do_not_consume_command_id(self):
        item = self.ok(handle("schedule.create", self.event()["request"], self.ctx))["item_id"]
        proposed = plan(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "ledger_id": "test-ledger",
                "expected_access_epoch": "1",
                "item_adoptions": [
                    {
                        "operation": "create",
                        "item_id": item,
                        "expected_item_version": "1",
                        "owner_scope": {"owner_kind": "subject", "owner_subject_id": "owner"},
                    }
                ],
            },
        )
        req = {
            "contract_version": "spine.trusted-web-provisioning.v1",
            "command_id": "adoption",
            "actor_subject_id": "owner",
            "action_timestamp_utc": AT,
            "expected_access_epoch": "1",
            "plan": proposed,
        }
        self.ok(apply(self.db, req))
        req["command_id"] = "second-adoption"
        with self.assertRaises(WebError):
            apply(self.db, req)
        self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id='second-adoption'").fetchone())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_access_owners").fetchone()[0], 1)

    def test_thousand_idle_reads_and_large_unrelated_receipt_ledger(self):
        import time

        before = self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0]
        started = time.monotonic()
        # Real read path, not a mocked no-op. No per-read receipt/audit/last-seen row.
        for _ in range(500):
            self.service.public("ready")
            self.run_command("context", {})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0], before)
        columns = [r[1] for r in self.db.execute("PRAGMA table_info(command_receipts)")]
        row = dict(self.db.execute("SELECT * FROM command_receipts LIMIT 1").fetchone())

        def values():
            for i in range(100000):
                data = {**row, "command_id": f"pressure-{i}", "command_receipt_id": f"pressure-receipt-{i}"}
                yield [data[k] for k in columns]

        with self.db:
            self.db.executemany("INSERT INTO command_receipts VALUES(" + ",".join("?" for _ in columns) + ")", values())
        read_started = time.monotonic()
        self.service.public("ready")
        self.run_command("context", {})
        self.assertLess(time.monotonic() - read_started, 5)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM command_receipts").fetchone()[0], before + 100000)
        self.idle_elapsed = time.monotonic() - started

    def test_signed_wire_fixture_expiry_and_exact_contract_mismatch(self):
        from spine.web.contracts import artifact

        vector = artifact("trusted-web-cursor-vectors.v1.json")
        signer = WebService(WebConfig(self.path, "test-ledger"), cursor_key=vector["test_key"]).signer
        self.assertEqual(signer.dumps(vector["payload"]), vector["wire"])
        self.assertEqual(signer.loads(vector["wire"]), vector["payload"])
        self.run_command("schedule.create", self.event("cursor-a"))
        self.run_command("schedule.create", self.event("cursor-b"))
        query = {"contract_version": "spine.trusted-web-items.v1", "limit": "1"}
        page = self.run_command("items", query)["result"]
        with patch("spine.web.service._now", return_value="2099-01-01T00:00:00Z"), self.assertRaises(WebError) as caught:
            self.run_command("items", {**query, "cursor": page["next_cursor"]})
        self.assertEqual(caught.exception.code, "access_changed")
        with patch("spine.web.contracts.IMPLEMENTED_CONTRACT_VERSIONS", frozenset()), self.assertRaises(WebError):
            WebService(WebConfig(self.path, "test-ledger"))

    def test_inline_location_and_unsupported_reference_rollbacks(self):
        body = self.event("with-place")
        body["request"]["item"]["primary_location"] = {"mode": "create", "kind": "place", "label": "Test venue"}
        response = self.run_command("schedule.create", body)
        self.assertEqual(response["result"]["primary_location"]["label"], "Test venue")
        bad = self.event("reuse-place")
        bad["request"]["item"]["primary_location"] = {
            "mode": "reference",
            "location_id": response["result"]["primary_location"]["location_id"],
        }
        with self.assertRaises(WebError) as caught:
            self.run_command("schedule.create", bad)
        self.assertEqual(caught.exception.code, "operation_unavailable")
        self.assertIsNone(self.db.execute("SELECT 1 FROM command_receipts WHERE command_id='reuse-place'").fetchone())

    def test_local_provisioning_dispatch_is_not_a_web_command(self):
        request = {"contract_version": "spine.trusted-web-provisioning.v1", "ledger_id": "test-ledger", "expected_access_epoch": "1"}
        planned = self.ok(handle("web_access.plan", request, self.ctx))
        self.assertTrue(planned["can_apply"])
        request = {
            "contract_version": "spine.trusted-web-provisioning.v1",
            "command_id": "dispatch-noop",
            "actor_subject_id": "owner",
            "action_timestamp_utc": AT,
            "expected_access_epoch": "1",
            "plan": planned,
        }
        self.assertFalse(self.ok(handle("web_access.apply", request, self.ctx))["changed"])
        with self.assertRaises(WebError) as caught:
            self.run_command("web_access.apply", request)
        self.assertEqual(caught.exception.code, "operation_unavailable")

    def test_admin_rights_owner_handoff_and_private_boundary(self):
        from spine.web.permissions import Permissions

        self.ok(
            handle(
                "subject_group.upsert",
                {"command_id": "group", "actor_subject_id": "owner", "group_id": "group", "display_name": "Group", "updated_at_utc": AT},
                self.ctx,
            )
        )
        self.provision(
            memberships=[
                {"operation": "create", "group_id": "group", "subject_id": s, "role": r, "starts_at_utc": AT}
                for s, r in (("owner", "owner"), ("other", "admin"))
            ]
        )
        item = self.ok(handle("schedule.create", self.event()["request"], self.ctx))["item_id"]
        self.provision(
            item_adoptions=[
                {
                    "operation": "create",
                    "item_id": item,
                    "expected_item_version": "1",
                    "owner_scope": {"owner_kind": "subject_group", "owner_group_id": "group"},
                }
            ]
        )
        self.assertTrue(Permissions(self.db, self.accounts["other"], AT).item(item, edit=True))
        private = self.run_command("schedule.create", self.event("private"))["result"]["item_id"]
        with self.assertRaises(WebError):
            Permissions(self.db, self.accounts["other"], AT).item(private)
        rows = {r["subject_id"]: dict(r) for r in self.db.execute("SELECT * FROM subject_memberships")}
        no_owner = plan(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "ledger_id": "test-ledger",
                "expected_access_epoch": str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]),
                "memberships": [
                    {"operation": "revoke", "membership_id": rows["owner"]["membership_id"], "expected_revision": "1", "ends_at_utc": AT}
                ],
            },
        )
        self.assertFalse(no_owner["can_apply"])
        self.provision(
            memberships=[
                {"operation": "set", "membership_id": rows[s]["membership_id"], "expected_revision": "1", "role": r}
                for s, r in (("owner", "member"), ("other", "owner"))
            ]
        )
        self.assertEqual(Permissions(self.db, self.accounts["other"], AT).groups["group"], "owner")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM subject_membership_revisions").fetchone()[0], 4)
