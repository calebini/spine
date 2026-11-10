"""Internal R2 command tests: exact source schemas, disposable ledgers, no sends."""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from spine.commands import handle
from spine.commands.facet_runtime import FacetCursorConfig
from spine.commands.recurring_task_runtime import PREFIX, RecurringTaskContracts, sign_cursor, verify_cursor
from spine.commands.recurring_tasks import execute
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.recurring_task_migration import install_candidate
from tests import test_recurrence_commands as recurrence_tests
from tests import test_recurring_task_storage as storage_tests
from tests import test_rendering_successor_authoring as rendering_tests

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-07T18:00:00Z"


def contracts():
    closure = json.loads((ROOT / "contracts/recurring-related-task-schema-closure.v1.json").read_text())
    documents = {r["path"]: json.loads((ROOT / r["path"]).read_text()) for r in closure["resources"]}
    return RecurringTaskContracts(documents, json.loads((ROOT / "contracts/recurring-related-tasks.v1.json").read_text()))


def dump(db):
    return "\n".join(db.iterdump())


class RecurringTaskCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = contracts()

    def setUp(self):
        helper = recurrence_tests.RecurrenceCommandTests()
        helper.setUp()
        self.addCleanup(helper.tearDown)
        self.db = helper.connection
        self.event, self.set_id, self.revision = helper._create_daily_event("r2-source", count="6")
        route = handle(
            "delivery_target.upsert",
            {
                "command_id": "r2-route",
                "actor_subject_id": "owner",
                "delivery_target_id": "owner-route",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "test",
                "adapter_name": "capture",
                "target_ref": "test://never-send",
                "updated_at_utc": NOW,
            },
            helper.context,
        )
        self.assertTrue(route["ok"], route)
        self.scope = {"owner_kind": "subject", "owner_subject_id": "owner"}
        self.profile = handle(
            "notification_profile.create",
            {
                "contract_version": "spine.notification-profiles.v2",
                "command_id": "r2-profile",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.scope,
                "profile_key": "pickup_standard",
                "display_name": "Pickup standard",
                "description": None,
                "revision": {
                    "compatible_item_types": ["task"],
                    "templates": [
                        {
                            "template_key": "ten_minutes",
                            "schedule": {
                                "kind": "once",
                                "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"},
                            },
                            "late_handling": {"kind": "skip"},
                            "rendering": {"kind": "ordinary"},
                        }
                    ],
                },
            },
            helper.context,
        )
        self.assertTrue(self.profile["ok"], self.profile)
        self.archetype = handle(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "r2-archetype",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.scope,
                "archetype_key": "pickup",
                "revision": {"display_name": "Pickup", "description": None, "compatible_item_types": ["task"]},
            },
            helper.context,
        )
        self.assertTrue(self.archetype["ok"], self.archetype)
        binding = handle(
            "notification_profile.binding.set",
            {
                "contract_version": "spine.notification-profile-bindings.v1",
                "command_id": "r2-profile-binding",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.scope,
                "item_archetype_id": self.archetype["item_archetype_id"],
                "notification_profile_id": self.profile["notification_profile_id"],
            },
            helper.context,
        )
        self.assertTrue(binding["ok"], binding)
        self.context = replace(
            helper.context,
            facet_cursor_config=FacetCursorConfig(b"r2-tests-only-key-not-deployable!!!", read_ledger_instance_id(self.db), "test-key"),
        )
        install_candidate(self.db, disposable_test_ledger=True)
        self.now = NOW

    def request(self, key="pickup"):
        return {
            "contract_version": "spine.recurring-related-tasks.v1",
            "command_id": "r2-create-" + key,
            "actor_subject_id": "owner",
            "requested_at_utc": NOW,
            "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
            "rule_key": key,
            "source": {
                "item_id": self.event["item_id"],
                "item_version": "1",
                "recurrence_set_id": self.set_id,
                "recurrence_revision_id": self.revision,
            },
            "enrollment": {"kind": "upcoming"},
            "configuration": {
                "task_owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "task_template": {
                    "item": {"item_type": "task", "title": "Pick up Joe", "task_detail": {}},
                    "people": {"assignees": ["owner", "owner"]},
                },
                "offset_basis": "elapsed",
                "offset_seconds": "5400",
                "notification_plan": None,
                "delivery": None,
                "materialization": {"mode": "none"},
            },
        }

    def run_command(self, name, request, *, context=None, fault=None):
        result = execute(PREFIX + name, request, context or self.context, contracts=self.contracts, clock=lambda: self.now, fault=fault)
        if result["ok"]:
            self.contracts.response(PREFIX + name, result)
        return result

    def created(self, key="pickup"):
        value = self.run_command("create", self.request(key))
        self.assertTrue(value["ok"], value)
        return value

    def write(self, name, rule, **fields):
        return {
            "contract_version": "spine.recurring-related-tasks.v1",
            "command_id": "r2-" + name,
            "actor_subject_id": "owner",
            "requested_at_utc": NOW,
            "related_task_rule_id": rule["related_task_rule_id"],
            "expected": {
                "rule_change_version": rule["change_version"],
                "rule_revision_id": rule["rule_revision_id"],
                "source_item_version": rule["source_snapshot"]["source_item_version"],
                "recurrence_revision_id": rule["source_snapshot"]["recurrence_revision_id"],
                "catalog_generation": rule["catalog_generation"],
            },
            **fields,
        }

    def test_create_is_atomic_source_only_and_schema_exact(self):
        item_count = self.db.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0]
        result = self.created()
        rule = result["result"]["rule"]
        self.assertFalse(result["result"]["generation_started"])
        self.assertEqual(rule["configuration"]["task_template"]["people"]["assignees"], ["owner"])
        self.assertEqual(rule["configuration"]["generation_horizon_seconds"], "4838400")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], item_count)
        for table in ["work_instances", "related_task_assignments", "item_access_owners", "access_grants"]:
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_all_valid_wire_requests_normalize_idempotently_without_lookups(self):
        manifest = json.loads((ROOT / "contracts/recurring-related-task-fixture-manifest.json").read_text())
        commands = {entry["request_schema"]: name for name, entry in self.contracts.descriptor["commands"].items()}
        before = dump(self.db)
        count = 0
        for fixture in manifest["fixtures"]:
            if fixture["valid"] and fixture["schema"] in commands:
                value = json.loads((ROOT / fixture["fixture"]).read_text())
                name = commands[fixture["schema"]]
                with self.subTest(fixture=fixture["fixture_id"]):
                    normalized = self.contracts.request(name, value)
                    self.assertEqual(self.contracts.request(name, normalized), normalized)
                    count += 1
        self.assertGreater(count, 10)
        self.assertEqual(dump(self.db), before)

    def test_all_published_cursor_vectors_match_runtime_codec(self):
        vectors = json.loads((ROOT / "tests/fixtures/recurring_related_tasks/cursors.json").read_text())["vectors"]
        for vector in vectors:
            payload = vector["payload"]
            config = FacetCursorConfig(bytes.fromhex(vector["key_hex"]), payload["query"]["ledger_instance_id"], payload["key_id"])
            with self.subTest(purpose=vector["purpose"]):
                self.assertEqual(sign_cursor(config, payload, self.contracts), vector["wire"])
                self.assertEqual(
                    verify_cursor(
                        config,
                        vector["wire"],
                        payload["query"],
                        vector["purpose"],
                        payload["issued_at_utc"],
                        payload["catalog_generation"],
                        self.contracts,
                    ),
                    payload,
                )

    def test_replay_precedes_fresh_actor_source_and_clock_checks(self):
        request = self.request()
        first = self.created()
        before = dump(self.db)
        result = execute(
            PREFIX + "create",
            request,
            replace(self.context, dry_run=True),
            contracts=self.contracts,
            clock=lambda: self.fail("replay sampled clock"),
        )
        self.assertTrue(result["replayed"], result)
        self.assertNotIn("dry_run", result)
        self.assertEqual(result["command_receipt_id"], first["command_receipt_id"])
        self.assertEqual(dump(self.db), before)
        bad = self.request()
        bad["configuration"]["offset_seconds"] = "6000"
        self.assertEqual(self.run_command("create", bad)["error"]["code"], "command_id_conflict")

    def test_faults_and_preview_leave_no_domain_audit_or_receipt_rows(self):
        before = dump(self.db)
        for stage in ["audit", "receipt"]:

            def fault(actual, stage=stage):
                if actual == stage:
                    raise RuntimeError(stage)

            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, stage):
                self.run_command("create", self.request(), fault=fault)
            self.assertEqual(dump(self.db), before)
        preview = self.run_command("create", self.request(), context=replace(self.context, dry_run=True))
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(preview["dry_run"])
        self.assertIsNone(preview["command_receipt_id"])
        self.assertEqual(dump(self.db), before)

    def test_show_list_are_read_only_and_cursors_are_query_bound(self):
        self.created("first")
        last = self.created("second")
        before = dump(self.db)
        request = {
            "contract_version": "spine.recurring-related-tasks.v1",
            "related_task_rule_id": last["result"]["rule"]["related_task_rule_id"],
        }
        shown = self.run_command("show", request)
        self.assertTrue(shown["ok"], shown)
        listed = self.run_command("list", {"contract_version": request["contract_version"], "limit": "1"})
        self.assertTrue(listed["ok"], listed)
        self.assertTrue(listed["result"]["has_more"])
        second = self.run_command(
            "list", {"contract_version": request["contract_version"], "limit": "1", "cursor": listed["result"]["next_cursor"]}
        )
        self.assertTrue(second["ok"], second)
        self.assertFalse(second["result"]["has_more"])
        changed = self.run_command(
            "list", {"contract_version": request["contract_version"], "limit": "2", "cursor": listed["result"]["next_cursor"]}
        )
        self.assertEqual(changed["error"]["code"], "invalid_request", changed)
        self.now = "2026-08-07T19:00:00Z"
        expired = self.run_command(
            "list", {"contract_version": request["contract_version"], "limit": "1", "cursor": listed["result"]["next_cursor"]}
        )
        self.assertEqual(expired["error"]["code"], "stale_cursor", expired)
        self.assertEqual(dump(self.db), before)

    def test_update_and_retire_keep_ordinary_items_untouched(self):
        rule = self.created()["result"]["rule"]
        config = copy.deepcopy(self.request()["configuration"])
        config["generation_horizon_seconds"] = "4838400"
        config["offset_seconds"] = "6000"
        request = self.write("update", rule, configuration=config, adoption_scope="new_assignments_only")
        updated = self.run_command("update", request)
        self.assertTrue(updated["ok"], updated)
        self.assertEqual(updated["effect"], "rule_configuration_updated")
        rule = updated["result"]["rule"]
        request = self.write("update", rule, configuration=config, adoption_scope="new_assignments_only")
        request["command_id"] = "r2-update-noop"
        noop = self.run_command("update", request)
        self.assertTrue(noop["ok"], noop)
        self.assertFalse(noop["changed"])
        retired = self.run_command("retire", self.write("retire", rule, disposition="keep_following"))
        self.assertTrue(retired["ok"], retired)
        self.assertEqual(retired["result"]["cleanup_status"], "complete")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_assignments").fetchone()[0], 0)

    def test_custom_policy_snapshot_has_no_future_item_specific_artifacts(self):
        request = self.request()
        request["configuration"]["notification_plan"] = {
            "mode": "none",
            "custom_additions": [
                {
                    "policy_key": "ten_minutes",
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
                    "late_handling": {"kind": "skip"},
                }
            ],
        }
        request["configuration"]["delivery"] = {
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        created = self.run_command("create", request)
        self.assertTrue(created["ok"], created)
        config = created["result"]["rule"]["configuration"]
        self.assertEqual(config["notification_plan"]["resolved"]["effective_templates"][0]["policy_key"], "ten_minutes")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_policies").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_profile_applications").fetchone()[0], 0)

    def test_closed_validation_actor_reference_and_stale_precedence(self):
        before = dump(self.db)
        value = self.request()
        value["actor_subject_id"] = "missing"
        value["surprise"] = True
        response = self.run_command("create", value)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), ("unsupported_field", "surprise"), response)
        del value["surprise"]
        self.assertEqual(self.run_command("create", value)["error"]["field"], "actor_subject_id")
        value = self.request()
        value["configuration"]["task_owner"] = {"owner_kind": "system"}
        response = self.run_command("create", value)
        self.assertEqual(
            (response["error"]["code"], response["error"]["field"]), ("invalid_request", "configuration.task_owner.owner_kind"), response
        )
        self.assertEqual(dump(self.db), before)
        rule = self.created()["result"]["rule"]
        request = self.write("retire", rule, disposition="keep_following")
        request["expected"]["rule_change_version"] = "9"
        request["expected"]["source_item_version"] = "9"
        response = self.run_command("retire", request)
        self.assertEqual(response["error"]["field"], "expected.rule_change_version", response)

    def test_catalog_stale_cursor_missing_key_and_wrong_purpose_are_read_only(self):
        self.created("first")
        self.created("second")
        request = {"contract_version": "spine.recurring-related-tasks.v1", "limit": "1"}
        before = dump(self.db)
        missing_key = self.run_command("list", request, context=replace(self.context, facet_cursor_config=None))
        self.assertEqual(
            (missing_key["error"]["code"], missing_key["error"]["field"]), ("environment_failure", "cursor_configuration"), missing_key
        )
        page = self.run_command("list", request)
        token = page["result"]["next_cursor"]
        tampered = self.run_command("list", {**request, "cursor": token[:-1] + ("A" if token[-1] != "A" else "B")})
        self.assertEqual(tampered["error"]["code"], "invalid_request", tampered)
        self.assertEqual(dump(self.db), before)
        rule = self.created("third")["result"]["rule"]
        stale = self.run_command("list", {**request, "cursor": token})
        self.assertEqual(stale["error"]["code"], "stale_cursor", stale)
        wrong = self.run_command(
            "show",
            {
                "contract_version": request["contract_version"],
                "related_task_rule_id": rule["related_task_rule_id"],
                "view": "assignments",
                "limit": "1",
                "cursor": token,
            },
        )
        self.assertEqual(wrong["error"]["code"], "invalid_request", wrong)

    def test_read_all_stored_witness_views_without_repairing_anything(self):
        fixture = storage_tests.RecurringTaskStorageTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        with fixture.db.atomic_command(write=True):
            assignment, _, _, proof = fixture.seed_assignment()
        context = replace(
            self.context,
            ledger=fixture.db,
            facet_cursor_config=FacetCursorConfig(
                b"separate-test-key-only-xxxxxxxxxxx", read_ledger_instance_id(fixture.db), "other-test-key"
            ),
        )
        before = dump(fixture.db)
        for view in ["rule", "assignment", "assignments", "generations", "states", "proof"]:
            request = {"contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": fixture.root_id, "view": view}
            if view in {"assignment", "generations", "states"}:
                request["assignment_id"] = assignment
            if view == "proof":
                request["proof_id"] = proof
            with self.subTest(view=view):
                response = self.run_command("show", request, context=context)
                self.assertTrue(response["ok"], response)
        self.assertEqual(dump(fixture.db), before)

    def test_replay_after_retirement_and_normalized_duplicate_inputs(self):
        request = self.request()
        first = self.created()
        rule = first["result"]["rule"]
        retired = self.run_command("retire", self.write("retire", rule, disposition="cancel_open"))
        self.assertTrue(retired["ok"], retired)
        request["configuration"]["task_template"]["people"]["assignees"] = ["owner"]
        request["configuration"]["generation_horizon_seconds"] = "4838400"
        self.now = "2026-12-01T00:00:00Z"
        replay = self.run_command("create", request)
        self.assertTrue(replay["ok"], replay)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["result"]["rule"]["status"], "active")

    def test_backward_commit_clock_rolls_back_and_preview_requires_no_second_sample(self):
        before = dump(self.db)
        samples = iter([NOW, "2026-08-07T17:59:59Z"])
        result = execute(PREFIX + "create", self.request(), self.context, contracts=self.contracts, clock=lambda: next(samples))
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["error"]["code"], result["error"]["field"]), ("environment_failure", "clock"))
        self.assertEqual(dump(self.db), before)
        samples = iter([NOW])
        result = execute(
            PREFIX + "create", self.request(), replace(self.context, dry_run=True), contracts=self.contracts, clock=lambda: next(samples)
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(dump(self.db), before)

    def test_explicit_and_archetype_profile_snapshots_are_pinned_without_applications(self):
        for mode in ["explicit", "archetype_default"]:
            with self.subTest(mode=mode):
                request = self.request(mode)
                config = request["configuration"]
                config["notification_plan"] = (
                    {
                        "mode": "explicit",
                        "notification_profile_id": self.profile["notification_profile_id"],
                        "revision_resolution": "current",
                    }
                    if mode == "explicit"
                    else {"mode": "archetype_default", "scope_chain": [self.scope], "on_no_match": "fail"}
                )
                config["task_template"]["item"]["archetype"] = {
                    "item_archetype_id": self.archetype["item_archetype_id"],
                    "revision_resolution": "current",
                    "selection_source": "operator_explicit",
                }
                config["delivery"] = {
                    "recipient_kind": "subject",
                    "recipient_subject_id": "owner",
                    "channel": "test",
                    "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
                }
                response = self.run_command("create", request)
                self.assertTrue(response["ok"], response)
                actual = response["result"]["rule"]["configuration"]
                self.assertEqual(actual["task_template"]["item"]["archetype"]["revision_resolution"], "exact")
                resolved = actual["notification_plan"]["resolved"]
                self.assertEqual(resolved["profile"]["notification_profile_id"], self.profile["notification_profile_id"])
                self.assertEqual(resolved["effective_templates"][0]["policy_key"], "profile_ten_minutes")
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_profile_applications").fetchone()[0], 0)
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_access_owners").fetchone()[0], 0)

    def test_missing_disclosure_does_not_fabricate_an_owner_or_grant(self):
        request = self.request()
        request["configuration"]["notification_plan"] = {
            "mode": "none",
            "custom_additions": [
                {
                    "policy_key": "notice",
                    "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-600"}},
                    "late_handling": {"kind": "skip"},
                }
            ],
            "rendering_applications": [
                {
                    "source_kind": "custom_addition",
                    "source_key": "notice",
                    "selection": {
                        "kind": "definition",
                        "definition": {
                            "notification_rendering_definition_id": "notification_rendering_definition_" + "a" * 64,
                            "notification_rendering_definition_revision_id": "notification_rendering_definition_revision_" + "b" * 64,
                        },
                        "effective_selection_keys": ["flight"],
                        "authorization": {"resolution": "unique_match"},
                    },
                }
            ],
        }
        request["configuration"]["delivery"] = {
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "test",
            "target": {"resolution": "explicit", "delivery_target_id": "owner-route"},
        }
        before = dump(self.db)
        response = self.run_command("create", request)
        self.assertFalse(response["ok"], response)
        self.assertEqual(
            (response["error"]["code"], response["error"]["field"]),
            ("rendering_disclosure_unavailable", "configuration.notification_plan"),
            response,
        )
        self.assertEqual(dump(self.db), before)

    def test_prospective_owner_reuses_real_approval_without_future_item_evidence(self):
        from spine.services.rendering_authoring import resolve

        rendering_tests.RenderingSuccessorTests.setUpClass()
        fixture = rendering_tests.RenderingSuccessorTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        root = fixture.create()["record"]
        grant = fixture.disclosure(root)
        before = dump(fixture.db)
        policy = {
            "item_id": None,
            "recipient_kind": "subject",
            "recipient_subject_id": "owner",
            "channel": "whatsapp",
            "delivery_target_id": "whatsapp-owner",
        }
        resolved = resolve(
            fixture.db,
            fixture.selection(grant),
            policy=policy,
            item_type="event",
            origin={"kind": "custom_addition"},
            prospective_owner=fixture.scope,
        )
        self.assertEqual(resolved["disclosure_authorization_id"], grant["disclosure_authorization_id"])
        self.assertEqual(dump(fixture.db), before)
        self.assertEqual(fixture.db.execute("SELECT COUNT(*) FROM item_access_owners").fetchone()[0], 0)

    def test_pending_adoption_is_retained_and_cancel_retirement_supersedes_it_without_fanout(self):
        fixture = storage_tests.RecurringTaskStorageTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        with fixture.db.atomic_command(write=True):
            fixture.seed_assignment()
        context = replace(self.context, ledger=fixture.db)
        self.now = "2026-08-18T00:00:00Z"
        shown = self.run_command(
            "show", {"contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": fixture.root_id}, context=context
        )
        rule = shown["result"]["rule"]
        config = copy.deepcopy(self.request()["configuration"])
        config.update(offset_seconds="6000", generation_horizon_seconds="4838400")
        first = self.run_command(
            "update", self.write("adoption-1", rule, configuration=config, adoption_scope="upcoming_open"), context=context
        )
        self.assertTrue(first["ok"], first)
        rule = first["result"]["rule"]
        intent = first["result"]["intent_id"]
        self.assertEqual(first["result"]["assignment_high_water"], "1")
        retained = self.run_command(
            "update", self.write("adoption-2", rule, configuration=config, adoption_scope="upcoming_open"), context=context
        )
        self.assertTrue(retained["ok"], retained)
        self.assertFalse(retained["changed"])
        self.assertEqual(retained["result"]["intent_id"], intent)
        bad = copy.deepcopy(config)
        bad["offset_seconds"] = "7000"
        conflict = self.run_command(
            "update", self.write("adoption-conflict", rule, configuration=bad, adoption_scope="new_assignments_only"), context=context
        )
        self.assertEqual((conflict["error"]["code"], conflict["error"]["field"]), ("semantic_conflict", "configuration"), conflict)
        before_task = [tuple(r) for r in fixture.db.execute("SELECT * FROM task_details ORDER BY item_id,version")]
        retired = self.run_command("retire", self.write("retire-pending", rule, disposition="cancel_open"), context=context)
        self.assertTrue(retired["ok"], retired)
        self.assertEqual(retired["result"]["cleanup_status"], "pending")
        self.assertEqual(
            fixture.db.execute("SELECT status FROM related_task_intents WHERE intent_id=?", (intent,)).fetchone()[0], "superseded"
        )
        self.assertEqual([tuple(r) for r in fixture.db.execute("SELECT * FROM task_details ORDER BY item_id,version")], before_task)


if __name__ == "__main__":
    unittest.main()
