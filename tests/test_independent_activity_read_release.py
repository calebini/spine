from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError
from spine.web.read_authorization import transition_query
from spine.web.read_contracts import READ_API
from spine.web.read_projection import UNAVAILABLE_TIME
from spine.web.read_release import read_authorized
from tests import test_independent_activity_read_assembly as assembly_helpers
from tests import test_independent_activity_read_foundation as helpers
from tests.test_trusted_web_runtime import AT


class IndependentReadReleaseTests(unittest.TestCase):
    setUpClass = helpers.ReadCoreFoundationTests.__dict__["setUpClass"]
    setUp = helpers.ReadCoreFoundationTests.setUp
    ok, provision, event, run_command = (
        helpers.ReadCoreFoundationTests.ok, helpers.ReadCoreFoundationTests.provision,
        helpers.ReadCoreFoundationTests.event, helpers.ReadCoreFoundationTests.run_command,
    )
    snapshot, related, adopt = (
        helpers.ReadCoreFoundationTests.snapshot, helpers.ReadCoreFoundationTests.related, helpers.ReadCoreFoundationTests.adopt,
    )
    recurring = assembly_helpers.IndependentReadAssemblyTests.recurring
    agenda_request = assembly_helpers.IndependentReadAssemblyTests.agenda_request

    def create(self, command="release-event"):
        return self.run_command("schedule.create", self.event(command))["result"]["item_id"]

    def read(self, identity=None, *, route="schedule.show", request=None, subject="owner", **kwargs):
        if request is None:
            request = {"item_id": identity}
        kwargs.setdefault("now", lambda: AT)
        kwargs.setdefault("selection", lambda: (self.accounts[subject], "selection"))
        return read_authorized(
            self.service.config, self.contracts, route, {"contract_version": READ_API, "request": request}, **kwargs,
        )

    def changed(self, code, operation):
        with self.assertRaises(WebError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.details, {})

    def mutate(self, sql, params=()):
        with self.db:
            self.db.execute(sql, params)

    def update(self, identity, command="race"):
        return self.ok(handle("event.update", {
            "command_id": command, "actor_subject_id": "owner", "item_id": identity,
            "target_version": "1", "updated_at_utc": AT, "patch": {"title": "Changed"},
        }, self.ctx))

    def test_exact_authorized_hash_and_no_durable_effects(self):
        identity = self.create()
        before = "\n".join(self.db.iterdump())
        value = self.read(identity)
        expected = [{"kind": "item", "id": identity, "value_hash": hash_canonical_json(value.assembly[0])}]
        self.assertEqual(list(value.proof.facts), expected)
        self.assertEqual(value.proof.source_snapshot_hash, hash_canonical_json({
            "contract_version": "spine.trusted-web-read-snapshot.v1", "route": "schedule.show",
            "query_hash": value.proof.query_hash, "facts": expected,
        }))
        self.assertEqual(value.proof.authorization_evaluated_at_utc, AT)
        self.assertIsNone(value.proof.authorization_valid_until_utc)
        self.assertEqual(before, "\n".join(self.db.iterdump()))

    def test_direct_source_race_uses_fresh_snapshot(self):
        identity = self.create()
        self.changed("version_changed", lambda: self.read(identity, before_release=lambda: self.update(identity)))

    def test_agenda_first_read_fences_off_range_candidates(self):
        identity = self.create()
        request = {**self.agenda_request(), "range_start_local": "2026-08-15T00:00:00"}
        before = self.read(route="agenda", request=request)
        self.assertEqual(before.assembly.entries, [])
        self.assertIn(identity, {f["id"] for f in before.proof.facts if f["kind"] == "item"})
        self.changed("access_changed", lambda: self.read(route="agenda", request=request, before_release=lambda: self.update(identity)))

    def test_hidden_followers_do_not_change_source_hash(self):
        identity = self.create()
        first = self.read(identity)
        second = self.read(identity, before_release=lambda: self.related(identity))
        self.assertEqual(first.proof.source_snapshot_hash, second.proof.source_snapshot_hash)
        self.assertEqual(first.proof.facts, second.proof.facts)

    def test_follow_source_proofs_and_denied_source_non_disclosure(self):
        event = self.create()
        task = self.related(event)
        self.adopt(task)
        visible = self.read(task)
        kinds = {f["kind"] for f in visible.proof.facts}
        self.assertEqual(kinds, {"item", "temporal_source", "temporal_binding"})
        self.changed("version_changed", lambda: self.read(task, before_release=lambda: self.update(event)))

    def test_denied_source_and_snapshot_time_are_independent(self):
        event = self.create()
        task = self.related(event)
        copied = self.related(event, "snapshot", "snapshot-task")
        self.adopt(task, "other")
        self.adopt(copied, "other")
        result = self.read(task, subject="other")
        self.assertEqual(result.assembly[0]["time"], UNAVAILABLE_TIME)
        self.assertEqual({r["kind"] for r in result.proof.facts}, {"item"})
        self.assertNotIn(event, json.dumps(result.proof.facts))
        snapshot_result = self.read(copied, subject="other", before_release=lambda: self.update(event))
        self.assertEqual(snapshot_result.assembly[0]["time"]["availability"], "available")

    def test_selection_identity_and_subject_races_are_not_optional(self):
        identity = self.create()
        selection = [(self.accounts["owner"], "selection")]
        self.changed("access_changed", lambda: self.read(
            identity, selection=lambda: selection[0], before_release=lambda: selection.__setitem__(0, (self.accounts["owner"], "new")),
        ))
        self.changed("identity_unavailable", lambda: self.read(
            identity, before_release=lambda: self.mutate("UPDATE subjects SET status='inactive' WHERE subject_id='owner'"),
        ))

    def test_subject_row_change_is_fenced_without_fabricating_revision(self):
        identity = self.create()
        self.changed("access_changed", lambda: self.read(
            identity, before_release=lambda: self.mutate("UPDATE subjects SET display_name='New name' WHERE subject_id='owner'"),
        ))

    def test_access_epoch_change_discards_whole_read(self):
        identity = self.create()
        self.changed("access_changed", lambda: self.read(
            identity, request={"item_id": identity, "include": ["work"]},
            before_release=lambda: self.mutate("UPDATE ledger_access_state SET access_epoch=access_epoch+1"),
        ))

    def test_retained_proof_changes_are_access_changed(self):
        identity = self.create()
        original = self.read(identity)
        self.update(identity)
        self.changed("access_changed", lambda: self.read(identity, previous=original.proof))

    def test_root_denial_precedes_version_guard(self):
        identity = self.create()
        self.changed("resource_unavailable", lambda: read_authorized(
            self.service.config, self.contracts, "schedule.show",
            {"contract_version": READ_API, "request": {"item_id": identity}, "expected_item_version": "99"},
            selection=lambda: (self.accounts["other"], "selection"), now=lambda: AT,
        ))

    def test_sections_use_rows_and_only_requested_sections(self):
        identity = self.create()
        plain = self.read(identity)
        detail = self.read(identity, request={"item_id": identity, "include": ["policies"]})
        policy_rows = detail.assembly[1]["policies"].rows
        self.assertTrue(policy_rows)
        actual = [f for f in detail.proof.facts if f["kind"] == "policies"]
        self.assertEqual(len(actual), len(policy_rows))
        self.assertEqual(actual[0]["value_hash"], hash_canonical_json(policy_rows[0]))
        self.assertFalse(any(f["kind"] == "policies" for f in plain.proof.facts))

    def test_canonical_recurrence_hash_and_occurrence_fence(self):
        identity = self.recurring()
        request = dict(
            item_id=identity, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00", range_basis="original_schedule",
        )
        result = self.read(route="item.occurrences", request=request)
        self.assertEqual(len(result.assembly.occurrences), 3)
        self.assertIn("recurrence", {f["kind"] for f in result.proof.facts})
        self.changed("version_changed", lambda: self.read(
            route="item.occurrences", request=request, before_release=lambda: self.update(identity),
        ))

    def test_protected_reference_is_not_hashed_as_redaction(self):
        identity = self.recurring()
        from spine.ledger.recurrence import load_current_recurrence_set
        canonical = load_current_recurrence_set(self.db, item_id=identity)
        canonical["extra_item_id"] = "hidden-proof"
        with patch("spine.web.read_proof.load_current_recurrence_set", return_value=canonical):
            result = self.read(identity)
        self.assertEqual(result.assembly[0]["time"], UNAVAILABLE_TIME)
        self.assertEqual({f["kind"] for f in result.proof.facts}, {"item"})
        self.assertNotIn("hidden-proof", json.dumps(result.proof.facts))

    def test_one_outer_budget_covers_assembly_and_release(self):
        identity = self.create()
        ticks = [0.0]
        self.changed("capacity_exceeded", lambda: self.read(
            identity, clock=lambda: ticks[0], before_release=lambda: ticks.__setitem__(0, 6.0),
        ))

    def test_query_plan_uses_existing_grantee_and_primary_indexes(self):
        sql, params = transition_query("grantee_subject_id", "access_grants_subject", "item", None, "owner", AT)
        plan = "\n".join(str(tuple(r)) for r in self.db.execute("EXPLAIN QUERY PLAN " + sql, params))
        self.assertIn("access_grants_subject", plan)
        self.assertIn("sqlite_autoindex_item_access_owners", plan)
        self.assertIn("sqlite_autoindex_access_grant_operations", plan)
        self.assertNotIn("SCAN g", plan)

    def grant(self, identity, *, starts=AT, ends=None, subject="other"):
        return self.provision(grants=[{
            "operation": "create", "resource_kind": "item", "resource_id": identity, "resource_owner_revision": "1",
            "grantee": {"owner_kind": "subject", "owner_subject_id": subject}, "operations": ["item.read"],
            "starts_at_utc": starts, "ends_at_utc": ends,
        }])

    def test_grant_expiry_invalidates_at_deadline_without_epoch_write(self):
        identity = self.create()
        end = "2026-09-01T09:01:00Z"
        self.grant(identity, ends=end)
        current = [AT]
        first = self.read(identity, subject="other", now=lambda: current[0])
        self.assertEqual(first.proof.authorization_valid_until_utc, end)
        epoch = self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]
        self.changed("access_changed", lambda: self.read(
            identity, subject="other", now=lambda: current[0], before_release=lambda: current.__setitem__(0, end),
        ))
        self.assertEqual(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0], epoch)

    def test_future_grant_activation_fences_gained_agenda_candidate(self):
        identity = self.create()
        start = "2026-09-01T09:01:00Z"
        self.grant(identity, starts=start)
        request = self.agenda_request()
        first = self.read(route="agenda", request=request, subject="other")
        self.assertEqual(first.proof.authorization_valid_until_utc, start)
        self.assertFalse(first.proof.facts)
        self.assertNotIn(identity, json.dumps(first.proof.facts))
        current = [AT]
        self.changed("access_changed", lambda: self.read(
            route="agenda", request=request, subject="other", now=lambda: current[0],
            before_release=lambda: current.__setitem__(0, start),
        ))

    def test_denied_temporal_source_gained_without_epoch_invalidates(self):
        event = self.create()
        task = self.related(event)
        self.adopt(task, "other")
        start = "2026-09-01T09:01:00Z"
        self.grant(event, starts=start)
        current = [AT]
        result = self.read(task, subject="other")
        self.assertEqual(result.assembly[0]["time"], UNAVAILABLE_TIME)
        self.assertEqual(result.proof.authorization_valid_until_utc, start)
        self.changed("access_changed", lambda: self.read(
            task, subject="other", now=lambda: current[0], before_release=lambda: current.__setitem__(0, start),
        ))

    def test_future_membership_activation_fences_group_visibility(self):
        self.ok(handle("subject_group.upsert", {
            "command_id": "new-group", "actor_subject_id": "owner", "group_id": "group", "display_name": "Group",
            "updated_at_utc": AT,
        }, self.ctx))
        start = "2026-09-01T09:01:00Z"
        self.provision(memberships=[
            {"operation": "create", "group_id": "group", "subject_id": "owner", "role": "owner", "starts_at_utc": AT},
            {"operation": "create", "group_id": "group", "subject_id": "other", "role": "member", "starts_at_utc": start},
        ])
        first = self.read(route="agenda", request=self.agenda_request(), subject="other")
        self.assertEqual(first.proof.authorization_valid_until_utc, start)
        current = [AT]
        self.changed("access_changed", lambda: self.read(
            route="agenda", request=self.agenda_request(), subject="other", now=lambda: current[0],
            before_release=lambda: current.__setitem__(0, start),
        ))

    def test_expiry_during_fresh_proof_cannot_release_old_authorization(self):
        identity = self.create()
        end = "2026-09-01T09:01:00Z"
        self.grant(identity, ends=end)
        times = iter([AT, AT, end])
        self.changed("access_changed", lambda: self.read(identity, subject="other", now=lambda: next(times)))

    def test_optional_failure_does_not_mask_root_revocation(self):
        identity = self.create()
        self.grant(identity)
        from spine.web.read_context import OptionalReadUnavailable
        with patch("spine.web.read_sections.Evidence.work", side_effect=OptionalReadUnavailable):
            first = self.read(identity, subject="other", request={"item_id": identity, "include": ["work"]})
            self.assertEqual(first.assembly[1]["work"].state["availability"], "unavailable")
            self.changed("access_changed", lambda: self.read(
                identity, subject="other", request={"item_id": identity, "include": ["work"]},
                before_release=lambda: self.mutate("UPDATE access_grants SET status='revoked'"),
            ))

    def test_section_content_race_cannot_be_downgraded(self):
        identity = self.create()
        self.changed("version_changed", lambda: self.read(
            identity, request={"item_id": identity, "include": ["policies"]},
            before_release=lambda: self.mutate(
                "UPDATE notification_policies SET status='disabled',disabled_at_utc=? WHERE item_id=?", (AT, identity),
            ),
        ))

    def test_hidden_follower_mutation_ignores_unrelated_version_changes(self):
        identity = self.create()
        follower = self.related(identity)
        before = self.read(identity, request={"item_id": identity, "include": ["related_items", "temporal_bindings"]})
        after = self.read(
            identity, request={"item_id": identity, "include": ["related_items", "temporal_bindings"]}, before_release=lambda: self.ok(
            handle("task.update", {
                "command_id": "hidden-update", "actor_subject_id": "owner", "item_id": follower,
                "target_version": "1", "updated_at_utc": AT, "patch": {"title": "Hidden changed"},
            }, self.ctx)
        ))
        self.assertEqual(before.proof.source_snapshot_hash, after.proof.source_snapshot_hash)

    def test_retained_proof_preserves_original_authorization_time(self):
        identity = self.create()
        original = self.read(identity)
        later = self.read(identity, previous=original.proof, now=lambda: "2026-09-01T09:00:01Z")
        self.assertEqual(later.proof.authorization_evaluated_at_utc, AT)
        self.changed("invalid_request", lambda: self.read(
            identity, request={"item_id": identity, "include": ["work"]}, previous=original.proof,
        ))

    def test_account_binding_and_recovery_revisions_are_fenced(self):
        identity = self.create()
        def bump(table, history, field):
            columns = [r[1] for r in self.db.execute(f"PRAGMA table_info({history})")]
            selected = ["revision+1" if c == "revision" else c for c in columns]
            with self.db:
                self.db.execute(f"INSERT INTO {history} SELECT {','.join(selected)} FROM {history} WHERE revision=1")
                self.db.execute(f"UPDATE {table} SET {field}={field}+1")
        self.changed("access_changed", lambda: self.read(
            identity, before_release=lambda: bump("login_accounts", "login_account_revisions", "revision"),
        ))
        self.changed("access_changed", lambda: self.read(
            identity, before_release=lambda: bump("account_subject_bindings", "account_subject_binding_revisions", "revision"),
        ))
        self.changed("access_changed", lambda: self.read(
            identity, before_release=lambda: self.mutate("UPDATE ledger_access_state SET recovery_epoch=recovery_epoch+1"),
        ))

    def test_agenda_summaries_hash_authorized_rows_not_only_counts(self):
        identity = self.create()
        result = self.read(route="agenda", request=self.agenda_request(include=["policies"]))
        rows = result.assembly.sections[identity]["policies"].rows
        self.assertTrue(rows)
        hashes = {f["value_hash"] for f in result.proof.facts if f["kind"] == "policies"}
        self.assertEqual(hashes, {hash_canonical_json(row) for row in rows})
        summary = result.assembly.entries[0]["sections"]["policies"]["value"]
        self.assertNotIn(hash_canonical_json(summary), hashes)

    def test_optional_sql_exhaustion_retains_fenced_core(self):
        identity = self.create()
        def expensive(evidence):
            evidence.db.execute(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT SUM(x) FROM n"
            ).fetchone()
            yield from ()
        with (
            patch.dict(self.contracts.bounds, {"optional_sql_vm_steps": 100}),
            patch("spine.web.read_sections.Evidence.related_items", expensive),
        ):
            result = self.read(identity, request={"item_id": identity, "include": ["related_items", "policies"]})
        self.assertEqual(result.assembly[0]["item_id"], identity)
        self.assertEqual(result.assembly[1]["policies"].state["availability"], "unavailable")
        self.assertEqual({f["kind"] for f in result.proof.facts}, {"item"})

    def test_selected_occurrence_binding_hashes_canonical_proofs(self):
        from spine.core.occurrences import expand_recurrence_set
        from spine.ledger.recurrence import load_current_recurrence_set
        from spine.ledger.temporal_bindings import active_binding_for_target

        identity = self.recurring()
        recurrence = load_current_recurrence_set(self.db, item_id=identity)
        occurrence = expand_recurrence_set(
            recurrence, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00",
        ).occurrences[0]
        result = self.ok(handle("schedule.related_task.create", {
            "contract_version": "spine.schedule-related-task-create.v1", "command_id": "selected-follower",
            "actor_subject_id": "owner", "created_at_utc": AT,
            "source": {
                "item_id": identity, "target_version": "1", "anchor_role": "event_start", "scope": "selected_occurrence",
                "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
                "target_occurrence_key": occurrence["occurrence_key"],
                "target_occurrence_selector": occurrence["target_occurrence_selector"],
            },
            "task": {"title": "Follower", "priority": "normal", "subject_roles": [{"subject_id": "owner", "role": "assignee"}]},
            "relationship": {"relation_type": "part_of"},
            "temporal_binding": {
                "binding_mode": "follow_source", "offset_basis": "elapsed", "offset_seconds": "-3600",
                "source_terminal_behavior": "detach_at_last_value",
            },
            "reminders": [], "materialization": {"mode": "none"},
        }, self.ctx))
        task = result["task"]["item_id"]
        self.adopt(task)
        binding = active_binding_for_target(self.db, item_id=task)
        read = self.read(task)
        self.assertEqual(read.assembly[0]["time"]["availability"], "available")
        records = {f["kind"]: f for f in read.proof.facts}
        self.assertEqual(records["recurrence"]["value_hash"], hash_canonical_json(recurrence))
        self.assertEqual(records["temporal_binding"]["value_hash"], hash_canonical_json(binding["latest_revision"]))
        self.assertEqual(records["temporal_binding"]["id"], binding["temporal_binding_id"])

    def test_new_future_transition_during_assembly_invalidates_authorization_proof(self):
        identity = self.create()
        self.grant(identity)
        # A synthetic no-epoch timing change must still be fenced before release.
        self.changed("access_changed", lambda: self.read(
            identity, subject="other", before_release=lambda: self.mutate(
                "UPDATE access_grants SET ends_at_utc='2026-09-01T09:10:00Z'",
            ),
        ))

    def test_group_grant_and_membership_queries_have_indexed_plans(self):
        sql, params = transition_query("grantee_group_id", "access_grants_group", "item", "root", "group", AT)
        plan = "\n".join(str(tuple(r)) for r in self.db.execute("EXPLAIN QUERY PLAN " + sql, params))
        self.assertIn("access_grants_group", plan)
        self.assertNotIn("SCAN g", plan)
        plan = "\n".join(str(tuple(r)) for r in self.db.execute(
            """EXPLAIN QUERY PLAN SELECT MIN(m.starts_at_utc) FROM subject_memberships m
            JOIN adopted_access_groups a USING(group_id) JOIN subject_groups g USING(group_id)
            WHERE m.subject_id=? AND m.status='active' AND g.status='active' AND m.starts_at_utc>?""", ("owner", AT),
        ))
        self.assertIn("subject_memberships_subject_status_idx", plan)
        self.assertNotIn("SCAN m", plan)
