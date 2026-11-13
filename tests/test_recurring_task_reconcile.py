"""Real manual-page transactions on disposable candidate ledgers, never sends."""

import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from spine.commands import core as command_core
from spine.commands import handle
from spine.commands.recurring_task_runtime import PREFIX
from spine.commands.recurring_tasks import execute
from spine.core.canonical_json import canonical_json_bytes
from spine.core.recurrence_mutations import build_successor_recurrence_revision, derive_recurrence_lineage
from spine.ledger import connect
from spine.ledger.recurrence import insert_initial_recurrence_set, insert_recurrence_lineage, load_current_recurrence_set
from spine.ledger.recurring_task_migration import attach_candidate
from spine.services.item_mutations import create_next_item_version
from tests import test_recurring_task_commands as base


class RecurringTaskReconcileTests(unittest.TestCase):
    def setUp(self):
        base.RecurringTaskCommandTests.setUp(self)
        self.connection = self.db
        # An explicit pre-provisioned synthetic access realm; generation must not
        # fabricate realms, accounts, membership or grants.
        with self.db.atomic_command(write=True):
            self.db.execute("INSERT INTO ledger_access_state VALUES(1,'r2-ledger','r2-realm','multi_user','trusted_identity',1,1)")

    def tearDown(self):
        self.doCleanups()

    request = base.RecurringTaskCommandTests.request
    run_command = base.RecurringTaskCommandTests.run_command
    created = base.RecurringTaskCommandTests.created
    write = base.RecurringTaskCommandTests.write

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def rule(self, identity):
        return self.run_command(
            "show",
            {
                "contract_version": base.CONTRACT if hasattr(base, "CONTRACT") else "spine.recurring-related-tasks.v1",
                "related_task_rule_id": identity,
            },
        )["result"]["rule"]

    def reconcile(self, rule, key="page", **limits):
        # Happy-path helper rereads after ordinary child edits now invalidate the
        # catalog. Stale/race tests submit explicit write() requests instead.
        rule = self.rule(rule["related_task_rule_id"])
        request = self.write("reconcile", rule, limits=limits)
        request["command_id"] = key
        result = self.run_command("reconcile", request)
        self.assertTrue(result["ok"], result)
        return result

    def source_change(self, *, exdates=None, overrides=None, event_detail=None):
        current = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        version = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (self.event["item_id"],)).fetchone()[0]
        command = "source-change-" + str(version)
        if overrides is not None:
            normalized_overrides = []
            for override in overrides:
                command_core._replace_or_add_override(
                    normalized_overrides,
                    recurrence=current,
                    occurrence={
                        "target_occurrence_selector": override["target_occurrence_selector"],
                        "occurrence_key": override["target_occurrence_key"],
                    },
                    segment=current["segments"][0],
                    command_id=command,
                    patch_fields={k: override[k] for k in ("expressed_scheduled_fact", "lifecycle") if k in override},
                    reason_code=override.get("reason_code"),
                    created_effect="override_created",
                    replaced_effect="override_replaced",
                )
            overrides = normalized_overrides
        normalized = build_successor_recurrence_revision(
            current, source_item_version=str(version + 1), command_id=command, exdates=exdates, overrides=overrides
        )
        lines = derive_recurrence_lineage(
            current, normalized.value, command_id=command, effect="series_edit_whole_applied", include_stream_copies=True
        )

        def extension(db, _version):
            insert_initial_recurrence_set(db, normalized=normalized, command_id=command, created_at_utc=self.now)
            insert_recurrence_lineage(db, lineage=lines)
            from spine.services.mutation_propagation import propagate

            propagate(db, recurrence_revision_id=str(normalized.value["recurrence_revision_id"]))

        with self.db.atomic_command(write=True):
            create_next_item_version(
                self.db,
                item_id=self.event["item_id"],
                target_version=version,
                created_at_utc=self.now,
                created_by_subject_id="owner",
                event_detail=event_detail,
                insert_canonical_extension=extension,
                supporting_command_id=command,
            )
        return normalized.value

    def excluded(self, first):
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        return {
            "segment_id": recurrence["segments"][0]["segment_id"],
            "target_occurrence_key": first["occurrence_key"],
            "target_occurrence_selector": first["selector"],
            "scheduled_fact": first["selector"]["scheduled_fact"],
            "status": "active",
            "reason_code": "no_class",
        }

    def test_real_generation_ownership_identity_epoch_replay_and_no_duplicates(self):
        rule = self.created()["result"]["rule"]
        epoch = self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]
        first = self.reconcile(rule)
        self.assertEqual(len(first["result"]["results"]), 6)
        self.assertEqual(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0], epoch + 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM access_grants").fetchone()[0], 0)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM item_access_owners WHERE creator_entitlement_subject_id IS NOT NULL").fetchone()[0], 0
        )
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        before = base.dump(self.db)
        replay = self.run_command("reconcile", self.write("reconcile", rule, limits={}) | {"command_id": "page"})
        self.assertTrue(replay["replayed"])
        self.assertEqual(base.dump(self.db), before)
        second = self.reconcile(first["result"]["rule"], "second")
        self.assertFalse(second["changed"])
        self.assertEqual(second["effect"], "rule_page_noop")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_generation_faults_rollback_every_child_stage_and_preview(self):
        rule = self.created()["result"]["rule"]
        request = self.write("reconcile", rule, limits={})
        before = base.dump(self.db)
        for stage in ("task", "owner", "binding", "policies", "work", "audit", "receipt"):

            def fault(current, selected=stage):
                if current == selected:
                    raise RuntimeError("injected " + selected)

            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, "injected"):
                self.run_command("reconcile", request, fault=fault)
            self.assertEqual(base.dump(self.db), before)
        preview = self.run_command("reconcile", request, context=replace(self.context, dry_run=True))
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(preview["dry_run"])
        self.assertIsNone(preview["command_receipt_id"])
        self.assertEqual(base.dump(self.db), before)

    def test_committing_at_first_due_rolls_back_whole_page(self):
        rule = self.created()["result"]["rule"]
        request = self.write("reconcile", rule, limits={})
        before = base.dump(self.db)
        times = iter([base.NOW, "2026-08-08T19:30:00Z"])
        value = execute(PREFIX + "reconcile", request, self.context, contracts=self.contracts, clock=lambda: next(times))
        self.assertEqual(value["error"]["code"], "stale_evaluation", value)
        self.assertEqual(base.dump(self.db), before)

    def test_moved_source_follows_same_task_and_binding(self):
        request = self.request()
        request["configuration"]["generation_horizon_seconds"] = "90000"
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        initial = self.reconcile(authored["result"]["rule"])
        first = initial["result"]["results"][0]
        recurrence = load_current_recurrence_set(self.db, item_id=self.event["item_id"])
        self.source_change(
            overrides=[
                {
                    "segment_id": recurrence["segments"][0]["segment_id"],
                    "target_occurrence_key": first["occurrence_key"],
                    "target_occurrence_selector": first["selector"],
                    "status": "active",
                    "expressed_scheduled_fact": "2026-08-08T20:00:00Z",
                    "reason_code": "move",
                }
            ]
        )
        moved = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "move-page")
        changed = next(v for v in moved["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(changed["outcome"], "followed")
        self.assertEqual(changed["after"]["task_item_id"], first["after"]["task_item_id"])
        self.assertEqual(changed["after"]["task_item_version"], "2")

    def test_exclusion_and_restoration_make_one_linked_successor(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "exclude-page")
        selected = next(v for v in cancelled["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "cancelled")
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "restore-page")
        selected = next(v for v in restored["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "restored")
        self.assertNotEqual(selected["after"]["task_item_id"], first["after"]["task_item_id"])
        self.assertEqual(selected["after"]["predecessor_generation_id"], first["generation_id"])
        final = self.reconcile(restored["result"]["rule"], "restore-again")
        self.assertFalse(final["changed"])

    def test_restoration_retains_original_managed_baseline_for_later_three_way_adoption(self):
        from spine.ledger.recurring_tasks import read_record

        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.edit_task(first["after"]["task_item_id"], "Individual pickup title")
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "custom-cancel")
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(cancelled["result"]["rule"]["related_task_rule_id"]), "custom-restore")
        selected = next(v for v in restored["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "restored")
        task = selected["after"]["task_item_id"]
        self.assertEqual(command_core._hydrated_item(self.db, task)["version"]["title"], "Individual pickup title")
        assignment = read_record(self.db, "related_task_assignments", first["assignment_id"])
        state = read_record(self.db, "related_task_assignment_revisions", assignment["current_assignment_revision_id"])["state_json"]
        self.assertEqual(state["managed_baseline"]["task_template"]["item"]["title"], "Pick up Joe")
        # D=B for title must preserve C, even after the new generation. A priority
        # edit must not silently reset an individual title to the rule template.
        updated = self.update_rule(restored["result"]["rule"], priority="high")
        adopted = self.reconcile(updated, "after-restoration-adoption")
        selected = next(v for v in adopted["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "adopted")
        item = command_core._hydrated_item(self.db, task)
        self.assertEqual(item["version"]["title"], "Individual pickup title")
        self.assertEqual(item["detail"]["priority"], "high")

    def test_suppression_changes_only_assignment_and_vetoes_restoration(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "exclude-page")
        rule = cancelled["result"]["rule"]
        view = self.run_command(
            "show",
            {
                "contract_version": "spine.recurring-related-tasks.v1",
                "related_task_rule_id": rule["related_task_rule_id"],
                "view": "assignment",
                "assignment_id": first["assignment_id"],
            },
        )["result"]["assignment"]
        request = self.write(
            "assignment.suppress",
            rule,
            assignment_id=first["assignment_id"],
            target_generation_id=view["generation_id"],
            target_task_item_id=view["task_item_id"],
        )
        request["expected"]["assignment_change_version"] = view["change_version"]
        count = self.db.execute("SELECT COUNT(*) FROM coordination_item_versions").fetchone()[0]
        suppressed = self.run_command("assignment.suppress", request)
        self.assertTrue(suppressed["ok"], suppressed)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_item_versions").fetchone()[0], count)
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(rule["related_task_rule_id"]), "no-restore")
        selected = next(v for v in restored["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "suppressed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_source_pages_bind_post_commit_versions(self):
        rule = self.created()["result"]["rule"]
        current, count = self.reconcile(rule, source_candidates="2"), 2
        self.assertTrue(current["result"]["has_more"])
        while current["result"]["has_more"]:
            request = self.write(
                "reconcile", current["result"]["rule"], limits={"source_candidates": "2"}, cursor=current["result"]["next_cursor"]
            )
            request["command_id"] = "page-" + str(count)
            current = self.run_command("reconcile", request)
            self.assertTrue(current["ok"], current)
            count += 2
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_profile_multiple_tasks_have_distinct_intents_and_real_attribution(self):
        request = self.request()
        config = request["configuration"]
        config["notification_plan"] = {
            "mode": "explicit",
            "notification_profile_id": self.profile["notification_profile_id"],
            "revision_resolution": "current",
            "custom_additions": [],
            "rendering_applications": [],
        }
        config["delivery"] = {
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        first = self.reconcile(authored["result"]["rule"])
        self.assertEqual(len(first["result"]["policy_mappings"]), 6)
        self.assertEqual(len(first["result"]["work"]["created"]), 6)
        self.assertEqual(len({p["notification_intent_id"] for p in first["result"]["policy_mappings"]}), 6)
        self.assertEqual({r[0] for r in self.db.execute("SELECT created_by_command_id FROM notification_profile_applications")}, {"page"})
        second = self.reconcile(first["result"]["rule"], "second")
        self.assertEqual(first["result"]["policy_mappings"], second["result"]["policy_mappings"])
        self.assertFalse(second["changed"])

    def update_rule(self, rule, *, title=None, priority=None, scope="upcoming_open"):
        rule = self.rule(rule["related_task_rule_id"])
        config = copy.deepcopy(self.request()["configuration"])
        config["generation_horizon_seconds"] = "4838400"
        if title is not None:
            config["task_template"]["item"]["title"] = title
        if priority is not None:
            config["task_template"]["item"]["task_detail"]["priority"] = priority
        value = self.run_command("update", self.write("update", rule, configuration=config, adoption_scope=scope))
        self.assertTrue(value["ok"], value)
        return value["result"]["rule"]

    def edit_task(self, identity, title):
        version = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (identity,)).fetchone()[0]
        with self.db.atomic_command(write=True):
            create_next_item_version(
                self.db,
                item_id=identity,
                target_version=version,
                created_at_utc=self.now,
                created_by_subject_id="owner",
                title=title,
                supporting_command_id="manual-edit-" + str(version),
            )

    def test_three_way_adoption_preserves_d_equals_b_individual_exception(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.edit_task(first["after"]["task_item_id"], "My own pickup wording")
        rule = self.update_rule(initial["result"]["rule"], priority="high")
        adopted = self.reconcile(rule, "adopt-priority")
        selected = next(v for v in adopted["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "adopted")
        current = command_core._hydrated_item(self.db, first["after"]["task_item_id"])
        self.assertEqual(current["version"]["title"], "My own pickup wording")
        self.assertEqual(current["detail"]["priority"], "high")
        self.assertIsNone(adopted["result"]["rule"]["adoption_intent"])

    def test_overlap_conflict_is_non_destructive_and_explicit_edit_resolves_it(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        identity = first["after"]["task_item_id"]
        self.edit_task(identity, "Manual custom title")
        rule = self.update_rule(initial["result"]["rule"], title="Desired title")
        blocked = self.reconcile(rule, "adopt-conflict")
        selected = next(v for v in blocked["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "decision_required")
        self.assertEqual(selected["reason"], "configuration_conflict")
        self.assertEqual(command_core._hydrated_item(self.db, identity)["version"]["title"], "Manual custom title")
        self.assertIsNotNone(blocked["result"]["rule"]["adoption_intent"])
        self.edit_task(identity, "Desired title")
        resolved = self.reconcile(blocked["result"]["rule"], "adopt-resolved")
        self.assertIsNone(resolved["result"]["rule"]["adoption_intent"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes WHERE outcome='conflict'").fetchone()[0], 1)

    def test_new_only_update_leaves_existing_adopted_configuration_unchanged(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        rule = self.update_rule(initial["result"]["rule"], title="Future tasks only", scope="new_assignments_only")
        result = self.reconcile(rule, "new-only-page")
        self.assertFalse(result["changed"])
        self.assertEqual(
            {
                r[0]
                for r in self.db.execute(
                    "SELECT v.title FROM related_task_generations g "
                    "JOIN coordination_items i ON i.item_id=g.task_item_id "
                    "JOIN coordination_item_versions v ON v.item_id=i.item_id AND v.version=i.current_version"
                )
            },
            {"Pick up Joe"},
        )

    def test_all_retirement_dispositions_cleanup_existing_outside_generation_horizon(self):
        for disposition in ("keep_following", "detach_open", "cancel_open"):
            with self.subTest(disposition=disposition):
                rule = self.created(disposition)["result"]["rule"]
                initial = self.reconcile(rule, "initial-" + disposition)
                self.now = "2027-08-07T18:00:00Z"
                request = self.write("retire", initial["result"]["rule"], disposition=disposition)
                request["command_id"] = "retire-" + disposition
                retired = self.run_command("retire", request)
                self.assertTrue(retired["ok"], retired)
                result = self.reconcile(retired["result"]["rule"], "cleanup-" + disposition)
                self.assertEqual(result["result"]["rule"]["retirement_intent"]["status"], "complete")
                self.assertEqual(result["result"]["future_generation"], "rule_retired")
                self.assertEqual(len(result["result"]["results"]), 6)
                self.now = base.NOW

    def test_adoption_replaces_complete_reminder_set_with_new_intents_once(self):
        request = self.request()
        config = request["configuration"]
        reminder = {
            "policy_key": "ten_minutes",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
            "late_handling": {"kind": "skip"},
        }
        config["notification_plan"] = {"mode": "none", "custom_additions": [reminder], "rendering_applications": []}
        config["delivery"] = {
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        initial = self.reconcile(authored["result"]["rule"])
        desired = copy.deepcopy(config)
        desired["generation_horizon_seconds"] = "4838400"
        added = copy.deepcopy(reminder)
        added["policy_key"] = "one_hour"
        added["schedule"]["at"]["offset_seconds"] = "-3600"
        desired["notification_plan"]["custom_additions"].append(added)
        updated = self.run_command(
            "update", self.write("update", initial["result"]["rule"], configuration=desired, adoption_scope="upcoming_open")
        )
        self.assertTrue(updated["ok"], updated)
        adopted = self.reconcile(updated["result"]["rule"], "adopt-reminders")
        self.assertEqual(len(adopted["result"]["policy_mappings"]), 12)
        old = {p["task_item_id"]: p["notification_intent_id"] for p in initial["result"]["policy_mappings"]}
        for mapping in adopted["result"]["policy_mappings"]:
            if mapping["policy_key"] == "ten_minutes":
                self.assertEqual(mapping["notification_intent_id"], old[mapping["task_item_id"]])
            else:
                self.assertEqual(mapping["creation_token"], "adopt-reminders:one_hour")
        self.assertIsNone(adopted["result"]["rule"]["adoption_intent"])
        repeated = self.reconcile(adopted["result"]["rule"], "adopt-again")
        self.assertFalse(repeated["changed"])
        self.assertEqual(adopted["result"]["policy_mappings"], repeated["result"]["policy_mappings"])

    def test_completed_task_is_consumed_not_reopened_by_source_changes(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        with self.db.atomic_command(write=True):
            create_next_item_version(
                self.db,
                item_id=first["after"]["task_item_id"],
                target_version=1,
                created_at_utc=self.now,
                created_by_subject_id="owner",
                task_detail={"task_status": "done", "completed_at_utc": self.now, "completed_by_subject_id": "owner"},
                supporting_command_id="complete",
            )
        result = self.reconcile(initial["result"]["rule"], "consume")
        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "consumed")
        self.source_change(exdates=[self.excluded(first)])
        self.source_change(exdates=[])
        result = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "no-reopen")
        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "consumed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_whole_unit_proof_and_response_overflow_roll_back_page(self):
        rule = self.created()["result"]["rule"]
        before = base.dump(self.db)
        for limits, expected in (({"proof_steps": "1"}, "limits.proof_steps"), ({"response_bytes": "1"}, "limits.response_bytes")):
            with self.subTest(limits=limits):
                result = self.run_command("reconcile", self.write("reconcile", rule, limits=limits))
                self.assertFalse(result["ok"], result)
                self.assertEqual((result["error"]["code"], result["error"]["field"]), ("capacity_exceeded", expected))
                self.assertEqual(base.dump(self.db), before)

    def test_generation_bootstraps_epoch_without_inventing_access_realm(self):
        with self.db.atomic_command(write=True):
            self.db.execute("DELETE FROM ledger_access_state")
        rule = self.created()["result"]["rule"]
        result = self.run_command("reconcile", self.write("reconcile", rule, limits={}))
        self.assertTrue(result["ok"], result)
        state = self.db.execute("SELECT mode,realm_id,identity_mode,access_epoch FROM ledger_access_state").fetchone()
        self.assertEqual(tuple(state), ("trusted_local", None, None, 1))
        for table in ("login_accounts", "web_operators", "subject_memberships", "access_grants"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_work_budget_stops_between_units_and_rolls_back_finalizer_trackers(self):
        request = self.request()
        config = request["configuration"]
        config["notification_plan"] = {
            "mode": "explicit",
            "notification_profile_id": self.profile["notification_profile_id"],
            "revision_resolution": "current",
            "custom_additions": [],
            "rendering_applications": [],
        }
        config["delivery"] = {
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        first = self.reconcile(authored["result"]["rule"], work_rows="1")
        self.assertEqual(len(first["result"]["work"]["created"]), 1)
        self.assertTrue(first["result"]["has_more"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 1)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        # An unrelated ordinary transaction still finalizes cleanly: no rolled-
        # back task/version/presentation can remain in the Python tracker sets.
        with self.db.atomic_command(write=True):
            self.assertFalse(self.db.mutation_state.facets.versions)
            self.assertFalse(self.db.mutation_state.renderings.pending)

    def test_response_byte_pages_commit_only_whole_units_and_continue_without_duplicates(self):
        rule = self.created()["result"]["rule"]
        preview = self.run_command(
            "reconcile", self.write("reconcile", rule, limits={}), context=replace(self.context, dry_run=True)
        )
        self.assertTrue(preview["ok"], preview)
        cap = len(canonical_json_bytes(preview)) * 3 // 4
        limits = {"response_bytes": str(cap)}
        request = self.write("reconcile", rule, limits=limits)
        request["command_id"] = "byte-page-0"
        seen = []
        for index in range(10):
            response = self.run_command("reconcile", request)
            self.assertTrue(response["ok"], response)
            self.assertLessEqual(len(canonical_json_bytes(response)), cap)
            values = response["result"]["results"]
            self.assertTrue(values)
            seen.extend(value["assignment_id"] for value in values if value["outcome"] == "created")
            if index == 0:
                self.assertTrue(response["result"]["has_more"])
                self.assertLess(len(values), 6)
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], len(values))
                # Suffix rollback includes owner/history, epoch, audit, and every
                # finalizer tracker, not only the assignment result array.
                self.assertEqual(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0], 2)
                self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
                before = base.dump(self.db)
                replay = self.run_command("reconcile", request)
                self.assertTrue(replay["replayed"])
                self.assertEqual(base.dump(self.db), before)
            if not response["result"]["has_more"]:
                break
            request = self.write("reconcile", response["result"]["rule"], limits=limits)
            request.update(command_id=f"byte-page-{index + 1}", cursor=response["result"]["next_cursor"])
        else:
            self.fail("byte pagination failed to make bounded progress")
        self.assertEqual(len(seen), 6)
        self.assertEqual(len(set(seen)), 6)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)
        with self.db.atomic_command(write=True):
            self.assertFalse(self.db.mutation_state.facets.versions)
            self.assertFalse(self.db.mutation_state.recurring.rows)

    def test_byte_boundary_existing_lane_and_dry_run_leave_no_partial_intent(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        config = self.request()["configuration"]
        config["generation_horizon_seconds"] = "4838400"
        config["task_template"]["item"]["title"] = "New pickup title"
        updated = self.run_command(
            "update", self.write("update", initial["result"]["rule"], configuration=config, adoption_scope="upcoming_open")
        )
        self.assertTrue(updated["ok"], updated)
        rule = updated["result"]["rule"]
        full = self.run_command(
            "reconcile", self.write("reconcile", rule, limits={}), context=replace(self.context, dry_run=True)
        )
        self.assertTrue(full["ok"], full)
        cap = len(canonical_json_bytes(full)) * 3 // 4
        request = self.write("reconcile", rule, limits={"response_bytes": str(cap)})
        request["command_id"] = "byte-adoption"
        before = base.dump(self.db)
        dry = self.run_command("reconcile", request, context=replace(self.context, dry_run=True))
        self.assertTrue(dry["ok"], dry)
        self.assertEqual(base.dump(self.db), before)
        result = self.run_command("reconcile", request)
        self.assertTrue(result["ok"], result)
        self.assertLessEqual(len(canonical_json_bytes(result)), cap)
        self.assertTrue(result["result"]["has_more"])
        count = len(result["result"]["results"])
        self.assertGreater(count, 0)
        self.assertLess(count, 6)
        self.assertEqual(result["result"]["coverage"]["assignments"]["processed_count"], str(count))
        self.assertEqual(result["result"]["rule"]["adoption_intent"]["status"], "pending")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_intent_outcomes").fetchone()[0], count)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items WHERE current_version=2").fetchone()[0], count)

    def test_response_cap_counts_receipt_envelope_and_oversized_unit_rolls_back(self):
        rule = self.created()["result"]["rule"]
        preview = self.run_command(
            "reconcile", self.write("reconcile", rule, limits={"source_candidates": "1"}),
            context=replace(self.context, dry_run=True),
        )
        self.assertTrue(preview["ok"], preview)
        # The result alone fits, but its audit/receipt/command envelope does not.
        cap = len(canonical_json_bytes(preview["result"]))
        before = base.dump(self.db)
        response = self.run_command(
            "reconcile", self.write("reconcile", rule, limits={"source_candidates": "1", "response_bytes": str(cap)})
        )
        self.assertFalse(response["ok"], response)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), ("capacity_exceeded", "limits.response_bytes"))
        self.assertEqual(base.dump(self.db), before)
        self.assertEqual(self.db._command_unit_depth, 0)

    def test_combined_candidate_mutation_work_and_byte_limits_preserve_complete_reminder_sets(self):
        request = self.request()
        config = request["configuration"]
        config["notification_plan"] = {
            "mode": "none", "custom_additions": [
                {
                    "policy_key": key,
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": seconds}},
                    "late_handling": {"kind": "skip"},
                }
                for key, seconds in (("ten_minutes", "-600"), ("one_hour", "-3600"))
            ], "rendering_applications": [],
        }
        config["delivery"] = {
            "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        response = self.reconcile(
            authored["result"]["rule"], "combined-budget", source_candidates="2", mutations="2", work_rows="3",
            assignments="1", response_bytes="20000", proof_steps="10000", lineage_hops="64",
        )
        self.assertTrue(response["result"]["has_more"])
        self.assertEqual(len(response["result"]["results"]), 1)
        self.assertEqual(len(response["result"]["policy_mappings"]), 2)
        self.assertEqual(len(response["result"]["work"]["created"]), 2)
        self.assertLessEqual(len(canonical_json_bytes(response)), 20000)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(DISTINCT notification_intent_id) FROM notification_policies").fetchone()[0], 2)

    def test_restoration_and_adoption_recheck_exact_due_at_commit(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "cutoff-cancel")
        self.source_change(exdates=[])
        rule = self.rule(cancelled["result"]["rule"]["related_task_rule_id"])
        before = base.dump(self.db)
        times = iter([base.NOW, "2026-08-08T19:30:00Z"])
        result = execute(
            PREFIX + "reconcile", self.write("reconcile", rule, limits={}), self.context,
            contracts=self.contracts, clock=lambda: next(times),
        )
        self.assertEqual(result["error"]["code"], "stale_evaluation", result)
        self.assertEqual(base.dump(self.db), before)
        restored = self.reconcile(rule, "cutoff-restore")
        rule = self.update_rule(restored["result"]["rule"], priority="high")
        before = base.dump(self.db)
        times = iter([base.NOW, "2026-08-08T19:30:00Z"])
        result = execute(
            PREFIX + "reconcile", self.write("reconcile", rule, limits={}), self.context,
            contracts=self.contracts, clock=lambda: next(times),
        )
        self.assertEqual(result["error"]["code"], "stale_evaluation", result)
        self.assertEqual(base.dump(self.db), before)
        # A fresh execution at equality records skipped-overdue, not permission
        # carried over from a preview or the old source-relative due.
        self.now = "2026-08-08T19:30:00Z"
        result = self.reconcile(rule, "cutoff-fresh")
        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual((selected["outcome"], selected["reason"]), ("skipped_due", "due_not_future"))

    def test_adoption_empty_clears_preserve_independent_policy_and_history(self):
        request = self.request()
        config = request["configuration"]
        config["task_template"]["item"].update(
            summary="Initial summary", source_ref="initial-source",
            primary_location={"mode": "create", "kind": "place", "label": "Pickup spot"},
            archetype={
                "item_archetype_id": self.archetype["item_archetype_id"], "revision_resolution": "current",
                "selection_source": "operator_explicit",
            },
        )
        config["task_template"]["item"]["task_detail"]["priority"] = "high"
        config["notification_plan"] = {
            "mode": "explicit", "notification_profile_id": self.profile["notification_profile_id"],
            "revision_resolution": "current", "custom_additions": [], "rendering_applications": [],
        }
        config["delivery"] = {
            "recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        config["materialization"] = {"mode": "bounded", "lookback_seconds": "0", "horizon_seconds": "604800", "opportunity_limit": "100"}
        authored = self.run_command("create", request)
        self.assertTrue(authored["ok"], authored)
        initial = self.reconcile(authored["result"]["rule"])
        first = initial["result"]["results"][0]
        task = first["after"]["task_item_id"]
        route = handle("delivery_target.upsert", {
            "command_id": "independent-route", "actor_subject_id": "owner", "delivery_target_id": "independent-route",
            "owner_kind": "subject", "owner_subject_id": "owner", "channel": "whatsapp", "adapter_name": "openclaw",
            "target_ref": "test://never-send", "updated_at_utc": self.now,
        }, self.context)
        self.assertTrue(route["ok"], route)
        extra = handle("reminder.create", {
            "command_id": "independent-reminder", "actor_subject_id": "owner", "item_id": task,
            "target_version": "1", "created_at_utc": self.now, "recipient_kind": "subject", "recipient_subject_id": "owner",
            "channel": "whatsapp", "delivery_target_id": "independent-route",
            "notification": {
                "authoring_contract": "spine.notification-schedule-authoring.v1",
                "target": {"anchor_role": "task_due", "application_scope": "item"},
                "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-1200"}},
                "late_handling": {"kind": "skip"},
            },
        }, self.context)
        self.assertTrue(extra["ok"], extra)
        desired = self.request()["configuration"]
        desired["generation_horizon_seconds"] = "4838400"
        desired["task_template"]["people"]["assignees"] = []
        updated = self.run_command(
            "update", self.write("update", self.rule(initial["result"]["rule"]["related_task_rule_id"]),
                                 configuration=desired, adoption_scope="upcoming_open")
        )
        self.assertTrue(updated["ok"], updated)
        adopted = self.reconcile(updated["result"]["rule"], "clear-all-managed")
        selected = next(v for v in adopted["result"]["results"] if v["assignment_id"] == first["assignment_id"])
        self.assertEqual(selected["outcome"], "adopted")
        current = command_core._hydrated_item(self.db, task)
        self.assertIsNone(current["version"]["summary"])
        self.assertIsNone(current["version"]["source_ref"])
        self.assertIsNone(current["detail"]["priority"])
        self.assertEqual(current["locations"], [])
        self.assertFalse(any(r["role"] == "assignee" and r["status"] == "active" for r in current["subject_roles"]))
        self.assertEqual(adopted["result"]["policy_mappings"], [])
        active = [p for p in current["notification_policies"] if p["status"] == "active"]
        self.assertEqual([p["notification_intent_id"] for p in active], [extra["notification_intent_id"]])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_locations WHERE item_id=? AND version=1", (task,)).fetchone()[0], 1)
        self.assertIsNone(adopted["result"]["rule"]["adoption_intent"])

    def test_physical_connection_restoration_race_has_one_successor_and_replay(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "race-cancel")
        self.source_change(exdates=[])
        rule = self.rule(cancelled["result"]["rule"]["related_task_rule_id"])
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "race.sqlite")
            target = connect(path)
            self.db.backup(target)
            target.close()
            barrier = threading.Barrier(2)

            def run(cid):
                db = connect(path)
                try:
                    attach_candidate(db)
                    context = replace(self.context, ledger=db)
                    request = self.write("reconcile", rule, limits={}) | {"command_id": cid}
                    barrier.wait(timeout=10)
                    result = self.run_command("reconcile", request, context=context)
                    if result["ok"]:
                        replay = self.run_command("reconcile", request, context=context)
                        self.assertTrue(replay["replayed"], replay)
                    return result
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, "restore-racer-a"), pool.submit(run, "restore-racer-b")]
                outcomes = [future.result(timeout=20) for future in futures]
            self.assertEqual(sum(result["ok"] for result in outcomes), 1, outcomes)
            loser = next(result for result in outcomes if not result["ok"])
            self.assertEqual(loser["error"]["code"], "stale_version", loser)
            db = connect(path)
            try:
                successors = db.execute(
                    "SELECT COUNT(*) FROM related_task_generations WHERE predecessor_generation_id=?", (first["generation_id"],)
                ).fetchone()[0]
                self.assertEqual(successors, 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 7)
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                db.close()

    def test_two_connection_suppression_and_restoration_interleavings_fail_stale_without_retargeting(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[self.excluded(first)])
        cancelled = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "interleave-cancel")
        self.source_change(exdates=[])
        rule = self.rule(cancelled["result"]["rule"]["related_task_rule_id"])
        view = self.run_command("show", {
            "contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": rule["related_task_rule_id"],
            "view": "assignment", "assignment_id": first["assignment_id"],
        })["result"]["assignment"]
        suppress = self.write(
            "assignment.suppress", rule, assignment_id=first["assignment_id"],
            target_generation_id=view["generation_id"], target_task_item_id=view["task_item_id"],
        )
        suppress["expected"]["assignment_change_version"] = view["change_version"]
        restore = self.write("reconcile", rule, limits={})
        for first_name, first_request, second_name, second_request, count in (
            ("assignment.suppress", suppress, "reconcile", restore, 6),
            ("reconcile", restore, "assignment.suppress", suppress, 7),
        ):
            with self.subTest(first=first_name), tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory) / "interleave.sqlite")
                target = connect(path)
                self.db.backup(target)
                target.close()
                a, b = connect(path), connect(path)
                try:
                    attach_candidate(a)
                    attach_candidate(b)
                    context_a, context_b = replace(self.context, ledger=a), replace(self.context, ledger=b)
                    winner = self.run_command(first_name, first_request, context=context_a)
                    self.assertTrue(winner["ok"], winner)
                    before = base.dump(b)
                    loser = self.run_command(second_name, second_request, context=context_b)
                    self.assertEqual(loser["error"]["code"], "stale_version", loser)
                    self.assertEqual(base.dump(b), before)
                    self.assertEqual(b.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], count)
                    if first_name == "assignment.suppress":
                        fresh_rule = self.run_command("show", {
                            "contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": rule["related_task_rule_id"],
                        }, context=context_b)["result"]["rule"]
                        fresh = self.write("reconcile", fresh_rule, limits={}) | {"command_id": "fresh-after-suppress"}
                        result = self.run_command("reconcile", fresh, context=context_b)
                        self.assertTrue(result["ok"], result)
                        selected = next(v for v in result["result"]["results"] if v["assignment_id"] == first["assignment_id"])
                        self.assertEqual(selected["outcome"], "suppressed")
                        self.assertEqual(b.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)
                finally:
                    a.close()
                    b.close()
