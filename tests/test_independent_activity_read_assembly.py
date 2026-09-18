from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.core.schedule import system_timezone_database_version
from spine.ledger.migrate import migrate_schema
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.recurrence import load_current_recurrence_set
from spine.web.errors import WebError
from spine.web.read_assembly import assemble_agenda, assemble_occurrences
from spine.web.read_context import OptionalReadUnavailable
from spine.web.read_projection import UNAVAILABLE_TIME
from spine.web.read_sections import Evidence, assemble_detail, assemble_sections
from tests import test_independent_activity_read_foundation as helpers
from tests.test_trusted_web_runtime import AT


class IndependentReadAssemblyTests(unittest.TestCase):
    setUpClass = helpers.ReadCoreFoundationTests.__dict__["setUpClass"]
    setUp = helpers.ReadCoreFoundationTests.setUp
    ok, provision, event, run_command = (
        helpers.ReadCoreFoundationTests.ok,
        helpers.ReadCoreFoundationTests.provision,
        helpers.ReadCoreFoundationTests.event,
        helpers.ReadCoreFoundationTests.run_command,
    )
    snapshot, related, adopt = (
        helpers.ReadCoreFoundationTests.snapshot,
        helpers.ReadCoreFoundationTests.related,
        helpers.ReadCoreFoundationTests.adopt,
    )

    def sections(self, item, include=None, subject="owner", agenda=False):
        with self.snapshot(subject) as snapshot:
            if include is None:
                include = list(snapshot.contracts.artifacts["trusted-web-read-projection.v1.json"]["sections"])
            values = assemble_sections(snapshot, item, include, agenda=agenda)
            result = {k: v.complete_value() for k, v in values.items()}
            self.contracts.validate("trusted-web-read-types.schema.json", result, definition="agenda_sections" if agenda else "sections")
            return result

    def agenda_request(self, **kw):
        return dict(
            evaluated_at_utc=AT,
            range_start_local="2026-08-14T00:00:00",
            range_end_local="2026-08-18T00:00:00",
            timezone="America/Toronto",
            timezone_database_version=system_timezone_database_version(),
            **kw,
        )

    def agenda(self, subject="owner", **kw):
        with self.snapshot(subject) as snapshot:
            return assemble_agenda(snapshot, self.agenda_request(**kw))

    def recurring(self, seed="2026-08-14T10:00:00", count="3", kind="event", end=None):
        anchor = {
            "anchor_kind": "local_instant",
            "local_date": seed[:10],
            "local_time": seed[11:],
            "timezone": "America/Toronto",
            "timezone_database_version": system_timezone_database_version(),
            "recurrence_set": {
                "time_basis": "local_instant",
                "timezone": "America/Toronto",
                "timezone_database_version": system_timezone_database_version(),
                "rules": [{"frequency": "DAILY", "seed": seed, "start_bound": seed, "end_condition": {"kind": "count", "count": count}}],
            },
        }
        request = {
            "command_id": "recurring",
            "actor_subject_id": "owner",
            "created_at_utc": AT,
            "title": "Series",
            "start_anchor" if kind == "event" else "due_anchor": anchor,
        }
        if kind == "event":
            request["all_day"] = False
            if end:
                request["end_anchor"] = {k: v for k, v in anchor.items() if k != "recurrence_set"}
                request["end_anchor"]["local_time"] = end
        identity = self.ok(handle(kind + ".create", request, self.ctx))["item_id"]
        self.adopt(identity)
        return identity

    def occurrences(self, identity, **kw):
        request = dict(item_id=identity, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00", range_basis="expressed_time")
        request.update(kw)
        with self.snapshot() as snapshot:
            return assemble_occurrences(snapshot, request)

    def test_all_eleven_states_and_absent_null_empty_not_requested(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        sections = self.sections(item, [])
        self.assertEqual(len(sections), 11)
        self.assertTrue(all(v == {"availability": "not_requested", "scope": "authorized_only"} for v in sections.values()))
        sections = self.sections(item)
        self.assertTrue(all(v["availability"] == "available" for v in sections.values()), sections)
        self.assertIsNone(sections["primary_location"]["value"])
        self.assertEqual(sections["related_items"]["entries"], [])
        self.assertEqual(sections["authoring_receipt"]["value"]["command"], "schedule.create")
        self.assertEqual(len(sections["policies"]["entries"]), 1)
        self.assertEqual(len(sections["work"]["entries"]), 6)
        with self.snapshot() as snapshot, self.assertRaises(WebError):
            assemble_sections(snapshot, item, ["unknown"])

    def test_mixed_owner_related_endpoints_require_grant_not_same_owner(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        baseline = self.sections(item, ["related_items", "relations", "temporal_bindings"])
        task = self.related(item)
        self.assertEqual(baseline, self.sections(item, ["related_items", "relations", "temporal_bindings"]))
        self.adopt(task, "other")
        self.assertEqual(baseline, self.sections(item, ["related_items", "relations", "temporal_bindings"]))
        self.provision(
            grants=[
                dict(
                    operation="create",
                    resource_kind="item",
                    resource_id=task,
                    resource_owner_revision="1",
                    grantee={"owner_kind": "subject", "owner_subject_id": "owner"},
                    operations=["item.read"],
                    starts_at_utc=AT,
                    ends_at_utc=None,
                )
            ]
        )
        result = self.sections(item, ["related_items", "relations", "temporal_bindings"])
        self.assertEqual(result["related_items"]["entries"][0]["item_id"], task)
        self.assertEqual(len(result["relations"]["entries"]), 1)
        self.assertEqual(len(result["temporal_bindings"]["entries"]), 1)
        # Existing v1 graph authorization remains complete-or-deny across owners.
        with self.assertRaises(WebError):
            self.run_command("schedule.show", {"contract_version": "spine.trusted-web-api.v1", "request": {"item_id": item}})

    def test_hidden_graph_growth_does_not_change_projection_or_budget_classification(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(item)
        self.adopt(task)
        include = ["related_items", "relations", "temporal_bindings"]
        before = self.sections(item, include)
        # Real unowned items, with many relation rows on the readable root.
        with self.db:
            for n in range(140):
                hidden = self.ok(
                    handle(
                        "task.create",
                        dict(command_id=f"hidden-{n}", actor_subject_id="owner", title=f"Hidden task {n}", created_at_utc=AT),
                        self.ctx,
                    )
                )["item_id"]
                self.db.execute(
                    """INSERT INTO coordination_item_relations
                    VALUES(?,?,?,'part_of','active',?,'owner',NULL)""",
                    (f"hidden-relation-{n}", hidden, item, AT),
                )
        self.assertEqual(before, self.sections(item, include))

    def test_optional_failure_isolated_and_root_denial_wins(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        with patch.object(Evidence, "work", side_effect=OptionalReadUnavailable):
            result = self.sections(item, ["work", "policies"])
            self.assertEqual(result["work"]["availability"], "unavailable")
            self.assertEqual(result["policies"]["availability"], "available")
            with self.snapshot("other") as snapshot, self.assertRaises(WebError) as caught:
                assemble_detail(snapshot, item, ["work"], guards={"expected_item_version": "999"})
            self.assertEqual(caught.exception.code, "resource_unavailable")
        with self.snapshot() as snapshot:
            snapshot.budget.bounds = {**snapshot.budget.bounds, "section_bytes": 20}
            activity, sections = assemble_detail(snapshot, item, ["work"])
            self.assertEqual(activity["time"]["availability"], "available")
            self.assertEqual(sections["work"].state["availability"], "unavailable")

    def test_agenda_four_states_authorized_counts_and_attempt_evidence(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        work = self.db.execute("SELECT work_instance_id FROM work_instances WHERE item_id=? LIMIT 1", (item,)).fetchone()[0]
        from spine.services.work import start_work

        start_work(self.db, work_instance_id=work, started_at_utc=AT)
        with self.db:
            self.db.execute(
                """INSERT INTO side_effect_attempts
                (attempt_id,work_instance_id,item_id,adapter_name,idempotency_key,attempt_status,
                 request_payload_hash,request_hash,attempted_at_utc,completed_at_utc,provider_ref)
                VALUES('attempt',?,?,'openclaw','attempt-key','succeeded',?,?,?,?,'PRIVATE_PROVIDER')""",
                (work, item, "a" * 64, "b" * 64, AT, AT),
            )
        include = ["primary_location", "policies", "work", "attempts"]
        values = self.sections(item, include, agenda=True)
        self.assertEqual(len(values), 4)
        for name, count in (("policies", 1), ("work", 6), ("attempts", 1)):
            self.assertEqual(int(values[name]["value"]["count"]), count)
            self.assertEqual(sum(map(int, values[name]["value"]["status_counts"].values())), count)
        self.assertEqual(values["attempts"]["value"]["status_counts"]["succeeded"], "1")
        self.assertNotIn("PRIVATE_PROVIDER", json.dumps(self.sections(item)))
        self.provision(
            grants=[
                dict(
                    operation="create",
                    resource_kind="item",
                    resource_id=item,
                    resource_owner_revision="1",
                    grantee={"owner_kind": "subject", "owner_subject_id": "other"},
                    operations=["item.read"],
                    starts_at_utc=AT,
                    ends_at_utc=None,
                )
            ]
        )
        hidden = self.sections(item, include, subject="other", agenda=True)
        for name in ("policies", "work", "attempts"):
            self.assertEqual(hidden[name]["value"]["count"], "0")
        self.assertIsNone(self.sections(item, ["authoring_receipt"], subject="other")["authoring_receipt"]["value"])

    def test_self_roles_inline_and_unmapped_shared_location(self):
        request = self.event()
        request["request"]["item"]["primary_location"] = {
            "mode": "create",
            "label": "School",
            "kind": "place",
            "provider_ref": "PRIVATE_LOCATION_PROVIDER",
        }
        item = self.run_command("schedule.create", request)["result"]["item_id"]
        task = self.related(item)
        self.adopt(task)
        self.assertEqual(self.sections(task, ["subject_roles"])["subject_roles"]["entries"], [{"subject_id": "owner", "role": "assignee"}])
        location = self.sections(item, ["primary_location"])["primary_location"]["value"]
        self.assertEqual(location["label"], "School")
        self.assertNotIn("provider_ref", location)
        second = self.event("reference")["request"]
        second["item"]["primary_location"] = {"mode": "reference", "location_id": location["location_id"]}
        shared = self.ok(handle("schedule.create", second, self.ctx))["item_id"]
        self.adopt(shared)
        self.assertIsNone(self.sections(shared, ["primary_location"])["primary_location"]["value"])

    def test_receipt_absence_undisclosable_and_unknown_reference_are_null(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        for protected in ("PRIVATE_REFERENCE", ["PRIVATE_REFERENCE"], {"label": "PRIVATE_REFERENCE"}):
            with self.db:
                row = self.db.execute("SELECT * FROM command_receipts WHERE item_id=?", (item,)).fetchone()
                facts = json.loads(row["semantic_facts_json"])
                facts["future_resource_ref"] = protected
                self.db.execute(
                    "UPDATE command_receipts SET semantic_facts_json=? WHERE command_receipt_id=?",
                    (json.dumps(facts), row["command_receipt_id"]),
                )
            self.assertIsNone(self.sections(item, ["authoring_receipt"])["authoring_receipt"]["value"])

    def test_occurrences_canonical_identity_no_writes_and_empty_range(self):
        item = self.recurring(end="11:00:00")
        before = "\n".join(self.db.iterdump())
        value = self.occurrences(item)
        canonical = self.ok(
            handle(
                "item.occurrences",
                dict(item_id=item, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00", range_basis="expressed_time"),
                self.ctx,
            )
        )["occurrences"]
        self.assertEqual([v["occurrence_id"] for v in value.occurrences], [v["occurrence_id"] for v in canonical])
        self.assertEqual([v["occurrence_key"] for v in value.occurrences], [v["occurrence_key"] for v in canonical])
        self.assertGreater(len(value.occurrences[0]["occurrence_key"]), 256)
        self.assertEqual(len(value.occurrences[0]["time"]["anchors"]), 2)
        self.agenda(include=["policies", "work", "attempts"])
        self.assertEqual(before, "\n".join(self.db.iterdump()))
        empty = self.occurrences(item, range_start="2027-01-01T00:00:00", range_end="2027-01-02T00:00:00")
        self.assertEqual((empty.coverage, empty.occurrences), ("complete", []))
        with self.assertRaises(WebError) as caught:
            self.occurrences(item, range_start="2026-08-14T00:00:00Z", range_end="2026-08-18T00:00:00Z")
        self.assertEqual(caught.exception.code, "invalid_request")

    def test_moves_exclusions_effective_title_end_and_terminal_overlay(self):
        item = self.recurring(end="11:00:00")
        first = self.occurrences(item).occurrences
        recurrence = load_current_recurrence_set(self.db, item_id=item)
        removed = self.ok(
            handle(
                "recurrence.instance.remove",
                dict(
                    command_id="exclude",
                    actor_subject_id="owner",
                    item_id=item,
                    target_version="1",
                    recurrence_set_id=recurrence["recurrence_set_id"],
                    recurrence_revision_id=recurrence["recurrence_revision_id"],
                    removed_at_utc=AT,
                    target_occurrence_key=first[1]["occurrence_key"],
                    reason_code="skip_one",
                ),
                self.ctx,
            )
        )
        self.ok(
            handle(
                "recurrence.instance.override",
                dict(
                    command_id="move",
                    actor_subject_id="owner",
                    item_id=item,
                    target_version="2",
                    recurrence_set_id=removed["recurrence_set_id"],
                    recurrence_revision_id=removed["recurrence_revision_id"],
                    overridden_at_utc=AT,
                    target_occurrence_key=first[2]["occurrence_key"],
                    expressed_scheduled_fact="2026-08-17T12:00:00",
                    common_detail_patch={"title": "Changed title", "source_ref": "PRIVATE_OVERLAY"},
                    event_detail_patch={"end_scheduled_fact": None},
                    lifecycle="cancelled",
                    reason_code="move_once",
                ),
                self.ctx,
            )
        )
        result = self.occurrences(item)
        self.assertEqual(len(result.occurrences), 2)
        moved = result.occurrences[-1]
        self.assertEqual((moved["title"], moved["lifecycle"], moved["actionable"]), ("Changed title", "cancelled", False))
        self.assertEqual(len(moved["time"]["anchors"]), 1)
        self.assertNotIn("PRIVATE_OVERLAY", json.dumps(result.occurrences))
        self.assertEqual(len(self.agenda().entries), 1)
        all_entries = self.agenda(include_terminal=True).entries
        self.assertEqual(len(all_entries), 2)
        self.assertIsNone(all_entries[-1]["end_at_utc"])
        self.assertEqual(all_entries[-1]["occurrence"]["occurrence_id"], moved["occurrence_id"])
        self.assertEqual(all_entries[-1]["activity"]["title"], "Series")

    def test_dst_canonical_omissions_and_ambiguous_earliest(self):
        item = self.recurring(seed="2026-03-07T02:30:00", count="3")
        result = self.occurrences(item, range_start="2026-03-07T00:00:00", range_end="2026-03-12T00:00:00")
        self.assertEqual([v["expressed_scheduled_fact"][:10] for v in result.occurrences], ["2026-03-07", "2026-03-09", "2026-03-10"])
        # A real authored local instant on the fall fold uses canonical earliest UTC.
        task = self.ok(
            handle(
                "task.create",
                dict(
                    command_id="fold",
                    actor_subject_id="owner",
                    title="Fold",
                    created_at_utc=AT,
                    due_anchor=dict(
                        anchor_kind="local_instant",
                        local_date="2026-11-01",
                        local_time="01:30:00",
                        timezone="America/Toronto",
                        timezone_database_version=system_timezone_database_version(),
                    ),
                ),
                self.ctx,
            )
        )["item_id"]
        self.adopt(task)
        request = self.agenda_request(item_ids=[task])
        request.update(range_start_local="2026-11-01T00:00:00", range_end_local="2026-11-02T00:00:00")
        with self.snapshot() as snapshot:
            entry = assemble_agenda(snapshot, request).entries[0]
        self.assertEqual(entry["start_at_utc"], "2026-11-01T05:30:00Z")
        self.assertEqual(entry["activity"]["time"]["anchors"][0]["resolution_kind"], "ambiguous_earliest_instant")

    def test_resolved_then_unplaced_and_whole_candidate_coverage_before_limit(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(event)
        self.adopt(task)
        self.ok(
            handle(
                "event.update",
                dict(
                    command_id="stale",
                    actor_subject_id="owner",
                    item_id=event,
                    target_version="1",
                    updated_at_utc=AT,
                    patch={"title": "Moved source version"},
                ),
                self.ctx,
            )
        )
        result = self.agenda(limit="1")
        self.assertEqual([v["activity"]["item_id"] for v in result.entries], [event])
        self.assertEqual([v["activity"]["item_id"] for v in result.unplaced_items], [task])
        self.assertEqual(result.coverage, "incomplete")
        self.assertEqual(result.unplaced_items[0]["activity"]["time"], UNAVAILABLE_TIME)
        self.assertNotIn("2026-08-14T13", json.dumps(result.unplaced_items))
        # Limit is deliberately not applied in internal assembly; the later shared
        # resolved/unplaced paginator must see both categories and whole coverage.
        self.assertEqual(len(result.entries) + len(result.unplaced_items), 2)
        related = self.sections(event, ["related_items"])["related_items"]["entries"]
        self.assertEqual(related[0]["time"], UNAVAILABLE_TIME)

    def test_denied_source_unplaced_snapshot_independent_and_unscheduled_omitted(self):
        event = self.run_command("schedule.create", self.event())["result"]["item_id"]
        follow = self.related(event)
        copied = self.related(event, "snapshot", "copied")
        self.adopt(follow, "other")
        self.adopt(copied, "other")
        unscheduled = self.ok(
            handle("task.create", dict(command_id="no-time", actor_subject_id="owner", title="No time", created_at_utc=AT), self.ctx)
        )["item_id"]
        self.adopt(unscheduled, "other")
        result = self.agenda(subject="other")
        self.assertEqual([v["activity"]["item_id"] for v in result.entries], [copied])
        self.assertEqual([v["activity"]["item_id"] for v in result.unplaced_items], [follow])
        with self.assertRaises(WebError) as caught:
            self.agenda(subject="other", item_ids=[copied, event])
        self.assertEqual(caught.exception.code, "resource_unavailable")
        with self.assertRaises(WebError) as caught:
            self.occurrences(unscheduled)
        self.assertEqual(caught.exception.code, "resource_unavailable")

    def test_terminal_base_lifecycle_and_unavailable_recurrence_are_distinct(self):
        item = self.recurring(kind="task")
        self.ok(
            handle(
                "task.complete",
                dict(command_id="done", actor_subject_id="owner", item_id=item, target_version="1", completed_at_utc=AT),
                self.ctx,
            )
        )
        values = self.occurrences(item).occurrences
        self.assertTrue(all(v["lifecycle"] == "completed" and not v["actionable"] for v in values))
        self.assertEqual(self.agenda().entries, [])
        self.assertEqual(len(self.agenda(include_terminal=True).entries), 3)
        with patch("spine.web.read_projection.project_anchor", side_effect=ValueError("unavailable pin")):
            result = self.occurrences(item)
        self.assertEqual((result.coverage, result.occurrences), ("incomplete", []))
        self.assertIsNotNone(result.activity["recurrence"])

    def test_actual_query_plans_probe_authorized_evidence_indexes(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(item)
        self.adopt(task)
        statements = []
        with self.snapshot() as snapshot:
            snapshot.db.set_trace_callback(statements.append)
            assemble_sections(snapshot, item, list(self.contracts.artifacts["trusted-web-read-projection.v1.json"]["sections"]))
            snapshot.db.set_trace_callback(None)
            plans = [
                row[3]
                for sql in statements
                if sql.lstrip().upper().startswith("SELECT")
                for row in snapshot.db.execute("EXPLAIN QUERY PLAN " + sql)
            ]
        joined = "\n".join(plans)
        for index in (
            "independent_read_relation_endpoints_idx",
            "independent_read_binding_endpoints_idx",
            "independent_read_work_policy_idx",
            "independent_read_creation_receipt_idx",
            "notification_policies_subject_unique",
            "side_effect_attempts_work_instance_idx",
        ):
            self.assertIn(index, joined)
        for table in ("coordination_item_relations", "relative_temporal_bindings", "work_instances", "command_receipts"):
            self.assertNotIn("SCAN " + table, joined)

    def test_schema14_upgrade_is_index_only_preserves_evidence_and_manifest(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        names = [r[0] for r in self.db.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'independent_read_%'")]
        with self.db:
            for name in names:
                self.db.execute("DROP INDEX " + name)
            self.db.execute("DELETE FROM ledger_schema WHERE schema_version=15")
        before = [line for line in self.db.iterdump() if line.startswith("INSERT") and "ledger_schema" not in line]
        result = migrate_schema(self.db)
        self.assertEqual(result.applied_versions, (15,))
        self.assertEqual(before, [line for line in self.db.iterdump() if line.startswith("INSERT") and "ledger_schema" not in line])
        self.assertEqual(verify_runtime_schema(self.db).schema_version, 15)
        self.assertTrue(self.sections(item)["work"]["entries"])

    def test_applied_profile_is_pinned_and_catalog_denial_omits_indivisible_evidence(self):
        template = {
            "template_key": "before",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
            "late_handling": {"kind": "skip"},
        }
        profile = self.ok(
            handle(
                "notification_profile.create",
                {
                    "contract_version": "spine.notification-profiles.v1",
                    "command_id": "profile",
                    "actor_subject_id": "owner",
                    "action_timestamp_utc": AT,
                    "owner": {"owner_kind": "subject", "owner_subject_id": "other"},
                    "profile_key": "private",
                    "display_name": "Private profile",
                    "revision": {"compatible_item_types": ["event"], "templates": [template]},
                },
                self.ctx,
            )
        )
        request = self.event()["request"]
        request["notification_plan"] = {
            "mode": "explicit",
            "notification_profile_id": profile["notification_profile_id"],
            "revision_resolution": "current",
        }
        request["materialization"] = {"mode": "none"}
        item = self.ok(handle("schedule.create", request, self.ctx))["item_id"]
        self.adopt(item)
        include = ["notification_profiles", "policies", "authoring_receipt"]
        denied = self.sections(item, include)
        self.assertEqual(denied["notification_profiles"]["entries"], [])
        self.assertEqual(denied["policies"]["entries"], [])
        self.assertIsNone(denied["authoring_receipt"]["value"])
        self.provision(
            grants=[
                dict(
                    operation="create",
                    resource_kind="notification_profile",
                    resource_id=profile["notification_profile_id"],
                    resource_owner_revision="1",
                    grantee={"owner_kind": "subject", "owner_subject_id": "owner"},
                    operations=["catalog.read"],
                    starts_at_utc=AT,
                    ends_at_utc=None,
                )
            ]
        )
        allowed = self.sections(item, include)
        self.assertEqual(
            allowed["notification_profiles"]["entries"],
            [
                {
                    "notification_profile_id": profile["notification_profile_id"],
                    "revision_id": profile["notification_profile_revision_id"],
                    "display_name": "Private profile",
                }
            ],
        )
        self.assertEqual(len(allowed["policies"]["entries"]), 1)

    def test_optional_sql_failure_and_row_limit_do_not_spend_core_permissions(self):
        import sqlite3

        from spine.web.read_projection import core

        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        with patch.object(Evidence, "work", side_effect=sqlite3.OperationalError("private diagnostic")):
            result = self.sections(item, ["work", "policies"])
        self.assertEqual(
            result["work"],
            {"availability": "unavailable", "scope": "authorized_only", "coverage": "incomplete", "reason_code": "context_unavailable"},
        )
        self.assertTrue(result["policies"]["entries"])
        with self.snapshot() as snapshot:
            core(snapshot, item)
            visited = set(snapshot.permissions.visited)
            snapshot.budget.bounds = {**snapshot.budget.bounds, "optional_authorized_rows_per_section": 1}
            sections = assemble_sections(snapshot, item, ["work", "policies"])
            self.assertEqual(sections["work"].state["availability"], "unavailable")
            self.assertEqual(sections["policies"].state["availability"], "available")
            self.assertEqual(snapshot.permissions.visited, visited)
            self.assertEqual(core(snapshot, item)["item_id"], item)

    def test_date_windows_point_end_and_defer_only_agenda(self):
        identities = {}
        for name, anchor in (
            (
                "date",
                {
                    "anchor_kind": "local_date",
                    "local_date": "2026-03-08",
                    "timezone": "America/Toronto",
                    "timezone_database_version": system_timezone_database_version(),
                },
            ),
            (
                "local-window",
                {
                    "anchor_kind": "local_window",
                    "local_date": "2026-03-08",
                    "timezone": "America/Toronto",
                    "timezone_database_version": system_timezone_database_version(),
                },
            ),
            (
                "utc-window",
                {"anchor_kind": "utc_window", "window_start_utc": "2026-03-08T03:00:00Z", "window_end_utc": "2026-03-08T06:00:00Z"},
            ),
            ("defer", {"anchor_kind": "instant_utc", "utc_instant": "2026-03-08T12:00:00Z"}),
        ):
            request = {
                "command_id": name,
                "actor_subject_id": "owner",
                "created_at_utc": AT,
                "title": name,
                "defer_until_anchor" if name == "defer" else "due_anchor": anchor,
            }
            identities[name] = self.ok(handle("task.create", request, self.ctx))["item_id"]
            self.adopt(identities[name])
        point = self.ok(
            handle(
                "event.create",
                {
                    "command_id": "point",
                    "actor_subject_id": "owner",
                    "created_at_utc": AT,
                    "title": "Point",
                    "all_day": False,
                    "start_anchor": {"anchor_kind": "instant_utc", "utc_instant": "2026-03-08T12:00:00Z"},
                },
                self.ctx,
            )
        )["item_id"]
        self.adopt(point)
        request = self.agenda_request()
        request.update(range_start_local="2026-03-08T00:00:00", range_end_local="2026-03-09T00:00:00")
        with self.snapshot() as snapshot:
            value = assemble_agenda(snapshot, request)
        entries = {entry["activity"]["item_id"]: entry for entry in value.entries}
        self.assertEqual(value.coverage, "complete")
        self.assertNotIn(identities["defer"], entries)
        for name in ("date", "local-window"):
            self.assertEqual(entries[identities[name]]["start_at_utc"], "2026-03-08T05:00:00Z")
            self.assertEqual(entries[identities[name]]["end_at_utc"], "2026-03-09T04:00:00Z")
        self.assertEqual(entries[identities["utc-window"]]["start_at_utc"], "2026-03-08T03:00:00Z")
        self.assertIsNone(entries[point]["end_at_utc"])

    def test_archived_recurrence_is_inspectable_but_not_actionable_or_in_agenda(self):
        item = self.recurring()
        self.ok(
            handle(
                "item.archive",
                {"command_id": "archive", "actor_subject_id": "owner", "item_id": item, "target_version": "1", "archived_at_utc": AT},
                self.ctx,
            )
        )
        self.assertTrue(all(not value["actionable"] for value in self.occurrences(item).occurrences))
        self.assertEqual(self.agenda(include_terminal=True).entries, [])

    def test_indivisible_relation_metadata_omission_and_retired_binding_revision(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(item)
        self.adopt(task)
        with self.db:
            self.db.execute(
                "UPDATE relative_temporal_bindings SET binding_status='retired',retired_at_utc=?,retired_by_command_id='retire'", (AT,)
            )
            self.db.execute("UPDATE coordination_item_relations SET relation_status='inactive'")
        result = self.sections(item, ["temporal_bindings", "relations"])
        self.assertEqual(result["temporal_bindings"]["entries"][0]["binding_status"], "retired")
        self.assertEqual(result["relations"]["entries"][0]["relation_status"], "inactive")
        with self.db:
            self.db.execute("UPDATE coordination_item_relations SET metadata_json=?", ('{"unknown_resource_id":"hidden"}',))
        result = self.sections(item, ["temporal_bindings", "relations", "related_items"])
        for name in ("temporal_bindings", "relations", "related_items"):
            self.assertEqual(result[name]["availability"], "available")
            self.assertEqual(result[name]["entries"], [])

    def test_nonrecurring_occurrence_denial_and_continuation_is_not_silently_accepted(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        with self.assertRaises(WebError) as caught:
            self.occurrences(item)
        self.assertEqual(caught.exception.code, "domain_failure")
        with self.assertRaises(WebError) as caught:
            self.agenda(cursor="not-implemented")
        self.assertEqual(caught.exception.code, "invalid_request")

    def test_current_inline_location_update_does_not_require_receipt_actor_visibility(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        self.ok(
            handle(
                "schedule.update",
                {
                    "contract_version": "spine.schedule-update.v2",
                    "command_id": "location-update",
                    "materialization": {"mode": "none"},
                    "actor_subject_id": "other",
                    "item_id": item,
                    "target_version": "1",
                    "updated_at_utc": AT,
                    "patch": {"primary_location": {"mode": "create", "label": "New place", "kind": "place"}},
                },
                self.ctx,
            )
        )
        self.assertEqual(self.sections(item, ["primary_location"])["primary_location"]["value"]["label"], "New place")
        # Location authority is item-local inline authoring, independent of receipt-summary disclosure.
        self.assertEqual(self.sections(item, ["authoring_receipt"])["authoring_receipt"]["value"]["command"], "schedule.create")

    def test_historical_work_survives_policy_copy_forward_and_inactive_route(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        before = self.sections(item, ["work"])["work"]["entries"]
        self.ok(
            handle(
                "event.update",
                {
                    "command_id": "title-update",
                    "actor_subject_id": "owner",
                    "item_id": item,
                    "target_version": "1",
                    "updated_at_utc": AT,
                    "patch": {"title": "New title"},
                },
                self.ctx,
            )
        )
        with self.db:
            self.db.execute("UPDATE delivery_targets SET status='inactive' WHERE delivery_target_id='whatsapp-owner'")
        after = self.sections(item, ["work", "delivery_targets"])
        self.assertEqual(after["work"]["entries"], before)
        self.assertEqual(after["delivery_targets"]["entries"], [])

    def test_recurring_event_ignores_hidden_selected_occurrence_follower(self):
        from spine.core.occurrences import expand_recurrence_set

        item = self.recurring()
        before_occurrences = self.occurrences(item)
        before_agenda = self.agenda()
        recurrence = load_current_recurrence_set(self.db, item_id=item)
        occurrence = expand_recurrence_set(recurrence, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00").occurrences[0]
        self.ok(
            handle(
                "schedule.related_task.create",
                {
                    "contract_version": "spine.schedule-related-task-create.v1",
                    "command_id": "selected-follower",
                    "actor_subject_id": "owner",
                    "created_at_utc": AT,
                    "source": {
                        "item_id": item,
                        "target_version": "1",
                        "anchor_role": "event_start",
                        "scope": "selected_occurrence",
                        "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
                        "target_occurrence_key": occurrence["occurrence_key"],
                        "target_occurrence_selector": occurrence["target_occurrence_selector"],
                    },
                    "task": {
                        "title": "PRIVATE_FOLLOWER",
                        "priority": "normal",
                        "subject_roles": [{"subject_id": "owner", "role": "assignee"}],
                    },
                    "relationship": {"relation_type": "part_of"},
                    "temporal_binding": {
                        "binding_mode": "follow_source",
                        "offset_basis": "elapsed",
                        "offset_seconds": "-3600",
                        "source_terminal_behavior": "detach_at_last_value",
                    },
                    "reminders": [],
                    "materialization": {"mode": "none"},
                },
                self.ctx,
            )
        )
        before_read = "\n".join(self.db.iterdump())
        self.assertEqual(before_occurrences, self.occurrences(item))
        self.assertEqual(before_agenda, self.agenda())
        for name in ("related_items", "relations", "temporal_bindings"):
            self.assertEqual(self.sections(item, [name])[name]["entries"], [])
        self.assertEqual(before_read, "\n".join(self.db.iterdump()))
        with self.assertRaises(WebError):
            self.run_command(
                "item.occurrences",
                {
                    "contract_version": "spine.trusted-web-api.v1",
                    "request": {"item_id": item, "range_start": "2026-08-14T00:00:00", "range_end": "2026-08-18T00:00:00"},
                },
            )

    def test_agenda_actual_plans_use_grantee_and_canonical_child_indexes(self):
        self.recurring()
        queries = []
        with self.snapshot() as snapshot:
            snapshot.db.set_trace_callback(queries.append)
            assemble_agenda(snapshot, self.agenda_request())
            snapshot.db.set_trace_callback(None)
            plan = "\n".join(
                row[3]
                for sql in queries
                if sql.lstrip().upper().startswith("SELECT")
                for row in snapshot.db.execute("EXPLAIN QUERY PLAN " + sql)
            )
        for index in (
            "access_grants_subject",
            "access_grants_group",
            "recurrence_rules_revision_status_idx",
            "recurrence_rdates_revision_status_idx",
            "recurrence_exdates_revision_status_idx",
        ):
            self.assertIn(index, plan)
        self.assertNotIn("access_grants_resource", plan)
        self.assertNotIn("SCAN ", plan)

    def test_corrupt_related_core_is_an_optional_failure_not_root_failure(self):
        item = self.run_command("schedule.create", self.event())["result"]["item_id"]
        task = self.related(item)
        self.adopt(task)
        with self.db:
            self.db.execute("DELETE FROM task_details WHERE item_id=?", (task,))
        with self.snapshot() as snapshot:
            activity, sections = assemble_detail(snapshot, item, ["related_items", "policies"])
            self.assertEqual(activity["time"]["availability"], "available")
            self.assertEqual(sections["related_items"].state["availability"], "unavailable")
            self.assertTrue(sections["policies"].rows)
        # The same corruption is a whole-read failure when that item is the root.
        with self.snapshot() as snapshot, self.assertRaises(WebError) as caught:
            assemble_detail(snapshot, task, ["policies"])
        self.assertEqual(caught.exception.code, "admission_unavailable")
