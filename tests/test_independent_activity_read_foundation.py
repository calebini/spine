from __future__ import annotations

import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import handle
from spine.core.canonical_json import canonical_json_text
from spine.core.schedule import system_timezone_database_version
from spine.ledger.recurrence import current_recurrence_header_sql, load_current_recurrence_set
from spine.web.contracts import API
from spine.web.errors import WebError
from spine.web.http import create_app
from spine.web.read_context import OptionalReadUnavailable, ReadBudget, read_snapshot
from spine.web.read_contracts import FORMATS, READ_API, ReadContracts
from spine.web.read_projection import UNAVAILABLE_TIME, candidate_ids, core, project_anchor
from tests import test_trusted_web_runtime as web_helpers

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures/independent_activity_reads/contracts"


class ReadContractFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = ReadContracts(ROOT / "contracts")

    def test_runtime_normalization_matches_all_published_vectors(self):
        vectors = self.contracts.artifacts["trusted-web-read-normalization-vectors.v1.json"]["vectors"]
        for vector in vectors:
            with self.subTest(vector=vector["name"]):
                original = copy.deepcopy(vector["input"])
                preimage, digest = self.contracts.normalize(vector["route"], original)
                self.assertEqual(preimage, vector["preimage"])
                self.assertEqual(canonical_json_text(preimage), vector["canonical_json"])
                self.assertEqual(digest, vector["sha256"])
                self.assertEqual(original, vector["input"])

    def test_invalid_request_shapes_and_formats_fail_closed(self):
        base = {"contract_version": READ_API, "request": {"item_id": "event"}}
        bad = [
            {**base, "contract_version": API},
            {**base, "actor_subject_id": "owner"},
            {**base, "request": {"item_id": "event", "section_limit": 50}},
            {**base, "request": {"item_id": "event", "include": ["work", "work"]}},
            {**base, "request": {"item_id": "event", "section_cursors": {"work": "cursor"}}},
            {**base, "request": {"item_id": "\ud800"}},
        ]
        for request in bad:
            with self.subTest(request=repr(request)), self.assertRaises(WebError) as caught:
                self.contracts.normalize("schedule.show", request)
            self.assertEqual(caught.exception.code, "invalid_request")
        for fixture, route in (("invalid_agenda_gregorian_date", "agenda"), ("invalid_occurrences_gregorian_date", "item.occurrences")):
            with self.assertRaises(WebError):
                self.contracts.normalize(route, json.loads((FIXTURES / (fixture + ".json")).read_text()))
        self.contracts.normalize("agenda", json.loads((FIXTURES / "request_agenda_leap_day.json").read_text()))
        for name, value in (("date", "1900-02-29"), ("date-time", "2026-02-31T10:00:00Z"),
                            ("spine-local-date-time", "0000-01-01T00:00:00")):
            self.assertFalse(FORMATS.conforms(value, name))
        self.assertTrue(FORMATS.conforms("2000-02-29T23:59:59", "spine-local-date-time"))

    def test_pins_and_unknown_formats_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in self.contracts.artifacts:
                shutil.copyfile(ROOT / "contracts" / name, directory / name)
            shutil.copyfile(ROOT / "contracts/trusted-web-read-schema-pins.v1.json", directory / "trusted-web-read-schema-pins.v1.json")
            (directory / "schemas").mkdir()
            for name in self.contracts.schemas:
                shutil.copyfile(ROOT / "contracts/schemas" / name, directory / "schemas" / name)
            target = directory / "schemas/trusted-web-read-types.schema.json"
            original = Path.read_bytes
            with (
                patch.object(Path, "read_bytes", autospec=True, side_effect=lambda p: b"{}" if p == target else original(p)),
                self.assertRaises(WebError) as caught,
            ):
                ReadContracts(directory)
            self.assertEqual(caught.exception.code, "admission_unavailable")
        with self.assertRaises(ValueError):
            ReadContracts._check_formats({"format": "unimplemented-calendar"})

    def test_separate_budget_reserves_and_deadline(self):
        now = [0.0]
        budget = ReadBudget(self.contracts, clock=lambda: now[0])
        with self.assertRaises(OptionalReadUnavailable), budget.optional():
            budget.charge("x" * budget.bounds["section_bytes"])
        self.assertEqual(budget.bytes["core"], 0)
        budget.charge({"readable": True})
        with self.assertRaises(OptionalReadUnavailable), budget.optional():
            budget.charge([], authorized_rows=1001)
        budget.check()
        now[0] = 5.0
        with self.assertRaises(WebError) as caught:
            budget.check()
        self.assertEqual((caught.exception.code, caught.exception.status), ("capacity_exceeded", 503))

    def test_sql_budget_optional_exhaustion_preserves_core(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        budget = ReadBudget(self.contracts)
        budget.bounds = {**budget.bounds, "optional_sql_vm_steps": 100}
        with budget.active(db):
            with self.assertRaises(OptionalReadUnavailable), budget.optional():
                db.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT SUM(x) FROM n").fetchone()
            self.assertEqual(db.execute("SELECT 1").fetchone()[0], 1)
            budget.check()
        self.assertLess(budget.steps["core"], 1000)

    def test_core_sql_and_byte_limits_fail_whole_read(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        budget = ReadBudget(self.contracts)
        budget.bounds = {**budget.bounds, "core_sql_vm_steps": 100}
        with self.assertRaises(WebError) as caught, budget.active(db):
            db.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT SUM(x) FROM n").fetchone()
        self.assertEqual(caught.exception.code, "capacity_exceeded")
        budget = ReadBudget(self.contracts)
        budget.bounds = {**budget.bounds, "core_reserved_bytes": 10}
        with self.assertRaises(WebError):
            budget.charge("1234567890")  # Encoded quotes are bytes too.
        now = [0.0]
        budget = ReadBudget(self.contracts, clock=lambda: now[0])
        with self.assertRaises(WebError), budget.optional():
            now[0] = 5.0
            budget.check()  # Outer deadline must never become optional degradation.


class ReadCoreFoundationTests(unittest.TestCase):
    # Reuse the real v1 provisioner/commands without inheriting its tests.
    setUp = web_helpers.TrustedWebRuntimeTests.setUp
    ok = web_helpers.TrustedWebRuntimeTests.ok
    provision = web_helpers.TrustedWebRuntimeTests.provision
    event = web_helpers.TrustedWebRuntimeTests.event
    run_command = web_helpers.TrustedWebRuntimeTests.run_command

    @classmethod
    def setUpClass(cls):
        cls.contracts = ReadContracts(ROOT / "contracts")

    def snapshot(self, subject="owner"):
        return read_snapshot(self.service.config, self.contracts, self.accounts[subject], evaluated_at_utc=web_helpers.AT)

    def related(self, event, mode="follow_source", command_id="related"):
        request = {
            "contract_version": "spine.schedule-related-task-create.v1", "command_id": command_id,
            "actor_subject_id": "owner", "created_at_utc": web_helpers.AT,
            "source": {"item_id": event, "target_version": "1", "anchor_role": "event_start", "scope": "item"},
            "task": {"title": "Drive to Science", "priority": "normal", "subject_roles": [{"subject_id": "owner", "role": "assignee"}]},
            "relationship": {"relation_type": "part_of"},
            "temporal_binding": {"binding_mode": mode, "offset_basis": "elapsed", "offset_seconds": "-3600"},
            "reminders": [], "materialization": {"mode": "none"},
        }
        if mode == "follow_source":
            request["temporal_binding"]["source_terminal_behavior"] = "detach_at_last_value"
        return self.ok(handle("schedule.related_task.create", request, self.ctx))["task"]["item_id"]

    def adopt(self, item, subject="owner"):
        return self.provision(item_adoptions=[{
            "operation": "create", "item_id": item, "expected_item_version": "1",
            "owner_scope": {"owner_kind": "subject", "owner_subject_id": subject},
        }])

    def test_event_core_ignores_unowned_followers_and_v1_still_denies(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        with self.snapshot() as snapshot:
            before = core(snapshot, item)
        self.related(item)
        trace = []
        with self.snapshot() as snapshot:
            snapshot.db.set_trace_callback(trace.append)
            self.assertEqual(before, core(snapshot, item))
        self.assertFalse(any("relative_temporal" in statement or "coordination_item_relations" in statement for statement in trace))
        with self.assertRaises(WebError) as caught:
            self.run_command("schedule.show", {"contract_version": API, "request": {"item_id": item}})
        self.assertEqual(caught.exception.code, "resource_unavailable")

    def test_follow_source_is_authorized_and_current_before_due_time_can_escape(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(event)
        self.adopt(task)
        with self.snapshot() as snapshot:
            self.assertEqual(core(snapshot, task)["time"]["availability"], "available")
        self.ok(handle("event.update", {
            "command_id": "source-move", "actor_subject_id": "owner", "item_id": event,
            "target_version": "1", "updated_at_utc": web_helpers.AT, "patch": {"title": "Changed source"},
        }, self.ctx))
        with self.snapshot() as snapshot:
            result = core(snapshot, task)
        self.assertEqual(result["time"], UNAVAILABLE_TIME)
        self.assertNotIn(event, json.dumps(result))
        self.assertNotIn("source", result["time"])

    def test_inaccessible_source_is_not_resolved_and_snapshot_time_is_independent(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        follow, copied = self.related(event), self.related(event, "snapshot", "copied")
        self.adopt(follow, "other")
        self.adopt(copied, "other")
        with (
            self.snapshot("other") as snapshot,
            patch("spine.web.read_projection.binding_state", side_effect=AssertionError("hidden source read")),
        ):
            self.assertEqual(core(snapshot, follow)["time"], UNAVAILABLE_TIME)
            self.assertEqual(core(snapshot, copied)["time"]["availability"], "available")

    def test_root_denial_precedes_guards_and_missing_is_generic(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        for identity in (event, "missing"):
            with self.snapshot("other") as snapshot, self.assertRaises(WebError) as caught:
                core(snapshot, identity, guards={"expected_item_version": "999"})
            self.assertEqual(caught.exception.code, "resource_unavailable")
        with self.snapshot() as snapshot, self.assertRaises(WebError) as caught:
            core(snapshot, event, guards={"expected_item_version": "999"})
        self.assertEqual((caught.exception.code, caught.exception.status), ("version_changed", 409))

    def test_reused_permission_failure_has_v2_status_without_details(self):
        with (
            patch("spine.web.permissions.Permissions.item", side_effect=WebError("capacity_exceeded", field="private")),
            self.assertRaises(WebError) as caught,
            self.snapshot() as snapshot,
        ):
            core(snapshot, "any")
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.details), ("capacity_exceeded", 503, {}))

    def test_snapshot_is_consistent_and_cannot_mutate(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        before = "\n".join(self.db.iterdump())
        with self.snapshot() as snapshot:
            self.assertEqual(core(snapshot, item)["current_version"], "1")
            with self.assertRaises(sqlite3.OperationalError):
                snapshot.db.execute("DELETE FROM coordination_items")
        self.assertEqual(before, "\n".join(self.db.iterdump()))
        with self.snapshot() as snapshot:
            first = core(snapshot, item)
            self.ok(handle("event.update", {
                "command_id": "concurrent", "actor_subject_id": "owner", "item_id": item,
                "target_version": "1", "updated_at_utc": web_helpers.AT, "patch": {"title": "New"},
            }, self.ctx))
            self.assertEqual(first, core(snapshot, item))
        with self.snapshot() as snapshot:
            self.assertEqual(core(snapshot, item)["title"], "New")

    def test_unscheduled_and_defer_only_task_time_remain_distinct(self):
        for name, anchor in (("unscheduled", None), ("deferred", {
            "anchor_kind": "instant_utc", "utc_instant": "2026-09-01T10:00:00Z",
        })):
            request = {"command_id": name, "actor_subject_id": "owner", "created_at_utc": web_helpers.AT, "title": name}
            if anchor:
                request["defer_until_anchor"] = anchor
            task = self.ok(handle("task.create", request, self.ctx))["item_id"]
            self.adopt(task)
            with self.snapshot() as snapshot:
                result = core(snapshot, task)
            if anchor:
                self.assertEqual(result["time"], {"availability": "available", "anchors": [{
                    "anchor_role": "task_defer_until", **anchor,
                }]})
            else:
                self.assertEqual(result["time"], {"availability": "not_scheduled"})

    def test_preflight_is_bounded_and_failed_reads_write_nothing(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        before = "\n".join(self.db.iterdump())
        trace = []
        connect = sqlite3.connect

        def observed(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_trace_callback(trace.append)
            return db

        with patch("spine.web.read_context.sqlite3.connect", side_effect=observed):
            with self.snapshot() as snapshot:
                core(snapshot, item)
            with self.assertRaises(WebError), self.snapshot("other") as snapshot:
                core(snapshot, item)
        self.assertFalse(any(
            name in statement.lower() for statement in trace for name in ("integrity_check", "quick_check", "foreign_key_check")
        ))
        self.assertEqual(before, "\n".join(self.db.iterdump()))

    def test_candidate_selection_excludes_unowned_and_foreign_items(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(event)
        with self.snapshot() as snapshot:
            self.assertEqual(candidate_ids(snapshot, {}), [event])
            with self.assertRaises(WebError):
                candidate_ids(snapshot, {"item_ids": [task], "item_types": ["event"]})
        self.adopt(task, "other")
        with self.snapshot() as snapshot:
            self.assertEqual(candidate_ids(snapshot, {}), [event])
        with self.snapshot("other") as snapshot:
            self.assertEqual(candidate_ids(snapshot, {}), [task])

    def test_candidate_grant_time_boundaries_precede_selection(self):
        items = {}
        for name, start, end in (
            ("active", "2026-09-01T08:00:00Z", "2026-09-01T10:00:00Z"),
            ("expired", "2026-09-01T08:00:00Z", web_helpers.AT),
            ("future", "2026-09-01T10:00:00Z", None),
        ):
            item = self.run_command("schedule.create", self.event(name))["result"]["item_id"]
            items[name] = item
            self.provision(grants=[{
                "operation": "create", "resource_kind": "item", "resource_id": item, "resource_owner_revision": "1",
                "grantee": {"owner_kind": "subject", "owner_subject_id": "other"}, "operations": ["item.read"],
                "starts_at_utc": start, "ends_at_utc": end,
            }])
        with self.snapshot("other") as snapshot:
            self.assertEqual(candidate_ids(snapshot, {}), [items["active"]])
            self.assertEqual(core(snapshot, items["active"])["time"]["availability"], "available")
            with self.assertRaises(WebError):
                candidate_ids(snapshot, {"item_ids": [items["expired"]]})
        with read_snapshot(
            self.service.config, self.contracts, self.accounts["other"], evaluated_at_utc="2026-09-01T10:00:00Z",
        ) as snapshot:
            self.assertEqual(candidate_ids(snapshot, {}), [items["future"]])

    def test_recurrence_identity_is_canonical_and_lookup_rooted(self):
        request = self.event()
        request["request"]["scheduled_time"]["recurrence"] = {"rules": [{
            "frequency": "DAILY", "interval": "1", "seed": "2026-08-14T10:00:00", "start_bound": "2026-08-14T10:00:00",
            "end_condition": {"kind": "count", "count": "3"},
        }]}
        item = self.run_command("schedule.create", request)["result"]["item_id"]
        expected = load_current_recurrence_set(self.db, item_id=item)
        for version in ("1", "2"):
            with self.snapshot() as snapshot:
                result = core(snapshot, item)
                self.assertEqual(result["recurrence"], {
                    k: expected[k] for k in ("recurrence_set_id", "recurrence_revision_id", "source_item_version")
                })
                plan = "\n".join(r[3] for r in snapshot.db.execute(
                    "EXPLAIN QUERY PLAN " + current_recurrence_header_sql("event"), (item, version),
                ))
                self.assertNotIn("SCAN rs", plan)
                self.assertIn("SEARCH rs USING INDEX", plan)
                self.assertIn("SEARCH d USING INDEX", plan)
                # Compare with the previous canonical selection SQL, not just the new helper.
                old = snapshot.db.execute("""SELECT rs.recurrence_set_id,rr.recurrence_revision_id,rr.source_item_version
                    FROM coordination_items i JOIN recurrence_sets rs ON rs.source_item_id=i.item_id
                    JOIN recurrence_revisions rr ON rr.recurrence_set_id=rs.recurrence_set_id AND rr.source_item_version<=i.current_version
                    WHERE i.item_id=? ORDER BY rr.source_item_version DESC,rr.revision_number DESC LIMIT 1""", (item,)).fetchone()
                self.assertEqual(result["recurrence"], {k: str(v) for k, v in dict(old).items()})
            if version == "1":
                self.ok(handle("event.update", {"command_id": "recurring-edit", "actor_subject_id": "owner", "item_id": item,
                    "target_version": "1", "updated_at_utc": web_helpers.AT, "patch": {"title": "Other title"}}, self.ctx))
                expected = load_current_recurrence_set(self.db, item_id=item)

    def test_canonical_anchor_projection_strips_provenance_and_resolves_dst(self):
        base = {"anchor_kind": "local_instant", "anchor_id": "secret", "source": "hidden provenance",
                "local_date": "2026-11-01", "local_time": "01:30:00", "timezone": "America/Toronto",
                "timezone_database_version": system_timezone_database_version()}
        result = project_anchor(base, "event_start")
        self.assertEqual(result["resolution_kind"], "ambiguous_earliest_instant")
        self.assertEqual(result["utc_instant"], "2026-11-01T05:30:00Z")
        self.assertNotIn("secret", json.dumps(result))
        window = project_anchor({**base, "anchor_kind": "local_window", "local_date": "2026-03-08"}, "task_due")
        self.assertEqual(window["window_start_utc"], "2026-03-08T05:00:00Z")
        self.assertEqual(window["window_end_utc"], "2026-03-09T04:00:00Z")
        with self.assertRaises(ValueError):
            project_anchor({**base, "local_date": "2026-03-08", "local_time": "02:30:00"}, "event_start")
        for anchor in (
            {"anchor_kind": "instant_utc", "utc_instant": "2026-09-01T10:00:00Z"},
            {**base, "anchor_kind": "local_date"},
            {"anchor_kind": "utc_window", "window_start_utc": "2026-09-01T10:00:00Z", "window_end_utc": "2026-09-01T11:00:00Z"},
        ):
            self.contracts.validate("trusted-web-read-types.schema.json", project_anchor(anchor, "task_due"), definition="anchor")
        with self.assertRaises(ValueError):
            project_anchor({"anchor_kind": "utc_window", "window_start_utc": "2026-09-01T10:00:00Z",
                            "window_end_utc": "2026-09-01T10:00:00Z"}, "task_due")

    def test_public_v2_requires_selected_identity(self):
        self.assertIn(READ_API, IMPLEMENTED_CONTRACT_VERSIONS)
        client = create_app(self.service.config).test_client()
        for path in ("/api/v2/read-capabilities", "/api/v2/agenda", "/api/v2/commands/schedule.show", "/api/v2/commands/item.occurrences"):
            response = client.open(path, method="GET" if path.endswith("capabilities") else "POST", headers={"Host": "127.0.0.1:8090"})
            self.assertNotEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
