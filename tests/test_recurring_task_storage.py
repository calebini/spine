"""R1 actual SQLite tests; no new public commands or automatic task generation."""

from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands import CommandContext, handle
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import command_derived_id, hash_canonical_json
from spine.core.notifications import notification_id
from spine.core.recurring_tasks import IDENTITIES, decode, derive, integer, occurrence_key, payload_hash, validate_proof
from spine.ledger import connect, initialize_schema
from spine.ledger.migrate import migrate_schema
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.recurring_task_migration import attach_candidate, install_candidate, verify_candidate_schema
from spine.ledger.recurring_task_sources import ProofBudget, candidate, require_candidate, verify_proof
from spine.ledger.recurring_tasks import (
    TABLE_KEYS,
    compare_and_swap,
    ensure_selector,
    insert_record,
    read_record,
    reserve_selector,
    verify_deep,
)
from tests import test_relative_temporal_bindings_command as binding_tests

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-08-17T12:00:00Z"


def canonical(value):
    return canonical_json_bytes(value).decode()


def snapshot(db):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name!='ledger_schema' ORDER BY name")]
    return {table: [tuple(r) for r in db.execute(f'SELECT * FROM "{table}"')] for table in tables}


class RecurringTaskCanonicalTests(unittest.TestCase):
    def test_all_published_new_family_preimages_and_delegated_occurrence_keys(self):
        vectors = json.loads((ROOT / "tests/fixtures/recurring_related_tasks/computed.json").read_text())["vectors"]
        count = 0
        for vector in vectors:
            preimage = vector["preimage"]
            prefix = vector["prefix"]
            kinds = [kind for kind, entry in IDENTITIES.items() if entry[0] == prefix]
            if kinds:
                fields = {
                    k: v for k, v in preimage.items() if k not in {"derivation_version", "contract_version", "canonical_json_version"}
                }
                actual, actual_preimage = derive(kinds[0], fields)
                self.assertEqual(actual, vector["value"], vector["case_id"])
                self.assertEqual(actual_preimage, preimage)
                if kinds[0] == "proof":
                    validate_proof(preimage["proof_kind"], preimage["proof_payload"])
                count += 1
            elif preimage["derivation_version"] in {"spine.related-task-rule-configuration.v1", "spine.related-task-assignment-state.v1"}:
                field = "configuration" if "configuration" in preimage else "state"
                self.assertEqual(payload_hash(field, preimage[field]), (vector["value"], preimage))
                count += 1
            elif preimage["derivation_version"] == "spine.recurrence-occurrence-key.v2":
                self.assertEqual(occurrence_key(preimage["target_occurrence_selector"]), vector["value"])
                count += 1
            elif preimage["derivation_version"] == "spine.command-id.v1":
                self.assertEqual(
                    command_derived_id(prefix=prefix, **{k: v for k, v in preimage.items() if k != "derivation_version"}), vector["value"]
                )
                count += 1
            elif preimage["derivation_version"].startswith(("spine.notification-", "spine.normalized-notification-")):
                fields = {
                    k: v
                    for k, v in preimage.items()
                    if k not in {"derivation_version", "contract_version", "normalization_version", "canonical_json_version"}
                }
                result, actual_preimage = notification_id(prefix or "", preimage["derivation_version"], fields)
                self.assertEqual(actual_preimage, preimage)
                self.assertEqual(result if prefix else result[1:], vector["value"])
                count += 1
            else:
                self.assertEqual(preimage["derivation_version"], "spine.recurrence-target-occurrence-selector.v1")
                self.assertEqual("recurrence_target_selector_" + hash_canonical_json(preimage), vector["value"])
                count += 1
        self.assertEqual(count, len(vectors))

    def test_canonical_decoder_rejects_duplicate_noncanonical_or_numeric_bytes(self):
        self.assertEqual(decode(canonical({"unicode": "é", "clear": None, "enabled": True}))["unicode"], "é")
        for text in ['{"a":"1","a":"2"}', '{ "a":"1"}', '{"a":1}', '{"a":1.2}', "[]", '{"a":NaN}']:
            with self.subTest(text=text), self.assertRaises(SpineValidationError):
                decode(text)
        for value in [True, 1, "01", "-1", "1.0", "١", "9223372036854775808"]:
            with self.subTest(value=value), self.assertRaises(SpineValidationError):
                integer(value)


class RecurringTaskMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        with patch("spine.ledger.sqlite.IMPLEMENTED_LEDGER_SCHEMA_VERSION", 19):
            initialize_schema(self.db)

    def test_explicit_candidate_fresh_install_idempotency_and_old_writer_refusal(self):
        self.assertEqual(IMPLEMENTED_LEDGER_SCHEMA_VERSION, 20)
        with patch("spine.ledger.migrate.CURRENT_SCHEMA_VERSION", 19), \
             patch("spine.ledger.migrate.verify_schema"):
            self.assertEqual(migrate_schema(self.db).after_version, 19)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sqlite_schema WHERE name='related_task_rules'").fetchone()[0], 0)
        with self.assertRaises(SpineValidationError):
            install_candidate(self.db)
        install_candidate(self.db, disposable_test_ledger=True)
        install_candidate(self.db, disposable_test_ledger=True)
        verify_candidate_schema(self.db)
        self.assertEqual(self.db.execute("SELECT MAX(schema_version) FROM ledger_schema").fetchone()[0], 20)
        for table in TABLE_KEYS:
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], int(table == "related_task_catalog_state"))
        self.assertEqual(tuple(self.db.execute("SELECT * FROM related_task_catalog_state").fetchone()), (1, 0))
        with self.assertRaises(SpineValidationError):
            verify_runtime_schema(self.db, expected_version=19)
        response = handle("system.info", {}, CommandContext(ledger=self.db))
        self.assertTrue(response["ok"], response)

    def test_every_migration_fault_rolls_back_schema_data_and_version(self):
        before = snapshot(self.db)
        for stage in ["preflight", "ddl", "verified", "activation"]:
            with self.subTest(stage=stage):

                def fail(actual, stage=stage):
                    if actual == stage:
                        raise RuntimeError(stage)

                with self.assertRaisesRegex(RuntimeError, stage):
                    install_candidate(self.db, disposable_test_ledger=True, fault=fail)
                self.assertFalse(self.db.in_transaction)
                self.assertEqual(snapshot(self.db), before)
                verify_runtime_schema(self.db, expected_version=19)
        install_candidate(self.db, disposable_test_ledger=True)

    def test_metadata_only_checks_detect_missing_or_drifted_objects_ignore_extras(self):
        install_candidate(self.db, disposable_test_ledger=True)
        statements = []
        self.db.set_trace_callback(statements.append)
        verify_candidate_schema(self.db)
        self.db.set_trace_callback(None)
        self.assertFalse(any("integrity_check" in s or "foreign_key_check" in s for s in statements))
        self.db.execute("CREATE TABLE extra_operator_notes(note TEXT)")
        verify_candidate_schema(self.db)
        self.db.execute("DROP INDEX related_task_rules_source_idx")
        with self.assertRaisesRegex(SpineValidationError, "schema-object mismatch"):
            verify_candidate_schema(self.db)
        self.db.execute("CREATE INDEX related_task_rules_source_idx ON related_task_rules(related_task_rule_id,source_item_id)")
        with self.assertRaisesRegex(SpineValidationError, "schema-object mismatch"):
            verify_candidate_schema(self.db)
        self.db.rollback()


class RecurringTaskStorageTests(unittest.TestCase):
    def setUp(self):
        # Real existing public producers create the source, selected occurrence,
        # ordinary task, relation and follow-source binding before candidate 20.
        helper = binding_tests.RelativeTemporalBindingCommandTests()
        helper.setUp()
        self.db = helper.connection
        self.addCleanup(helper.tearDown)
        request = helper._event_request()
        request["command_id"] = "rrt-source"
        request["scheduled_time"]["recurrence"] = {
            "rules": [
                {
                    "frequency": "DAILY",
                    "interval": "1",
                    "seed": "2026-08-22T10:00:00",
                    "start_bound": "2026-08-22T10:00:00",
                    "end_condition": {"kind": "count", "count": "3"},
                }
            ]
        }
        self.source = handle("schedule.create", request, helper.context)
        self.assertTrue(self.source["ok"], self.source)
        self.revision = self.source["recurrence"]["recurrence_revision_id"]
        with self.db.atomic_command(write=False):
            self.source_candidate = candidate(self.db, self.revision, "2026-08-22T10:00:00", ProofBudget())
        self.selector = self.source_candidate["selector"]
        self.key = self.source_candidate["occurrence_key"]
        request = helper._related_request("follow_source")
        request["temporal_binding"]["source_terminal_behavior"] = "require_decision"
        request["temporal_binding"]["offset_seconds"] = "5400"
        request["source"] = {
            "item_id": self.source["item_id"],
            "target_version": "1",
            "anchor_role": "event_start",
            "scope": "selected_occurrence",
            "source_recurrence_revision_id": self.revision,
            "target_occurrence_key": self.key,
            "target_occurrence_selector": self.selector,
        }
        self.task = handle("schedule.related_task.create", request, helper.context)
        self.assertTrue(self.task["ok"], self.task)
        self.task_id = self.task["task"]["item_id"]
        self.owner_id = "item_access_owner_r1_test"
        self.extra_tasks = []
        for number in [1, 2]:
            extra = copy.deepcopy(request)
            extra["command_id"] = f"r1-extra-related-{number}"
            result = handle("schedule.related_task.create", extra, helper.context)
            self.assertTrue(result["ok"], result)
            self.extra_tasks.append((result, f"item_access_owner_r1_extra_{number}", extra["command_id"]))
        with self.db.atomic_command(write=True):
            for task, owner_id, command in [(self.task, self.owner_id, request["command_id"]), *self.extra_tasks]:
                self.db.execute(
                    "INSERT INTO item_access_owners VALUES(?,?,1,'subject','owner',NULL,NULL,?)",
                    (task["task"]["item_id"], owner_id, command),
                )
                self.db.execute(
                    "INSERT INTO item_access_owner_revisions VALUES(?,?,1,'subject','owner',NULL,NULL,?,?,?,?)",
                    (task["task"]["item_id"], owner_id, command, AT, "owner", task["command_receipt_id"]),
                )
        self.before = snapshot(self.db)
        install_candidate(self.db, disposable_test_ledger=True)
        self.config = copy.deepcopy(
            json.loads((ROOT / "tests/fixtures/recurring_related_tasks/computed.json").read_text())["vectors"][3]["preimage"][
                "configuration"
            ]
        )
        self.config.update(
            task_owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            notification_plan=None,
            delivery=None,
            materialization={"mode": "none"},
        )
        self.config["task_template"]["people"] = {"assignees": ["owner"]}
        self.root_id = derive("rule", {"owner": {"owner_kind": "subject", "owner_subject_id": "owner"}, "rule_key": "pickup"})[0]
        self.config_hash = payload_hash("configuration", self.config)[0]
        self.config_id = derive(
            "rule_revision", {"related_task_rule_id": self.root_id, "revision_index": "1", "configuration_hash": self.config_hash}
        )[0]

    def seed_root(self, db=None):
        db = db or self.db
        insert_record(
            db,
            "related_task_rules",
            {
                "related_task_rule_id": self.root_id,
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "owner_group_id": None,
                "owner_key": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "rule_key": "pickup",
                "source_item_id": self.source["item_id"],
                "recurrence_set_id": self.selector["recurrence_set_id"],
                "enrolled_source_version": 1,
                "enrolled_recurrence_revision_id": self.revision,
                "enrolled_at_utc": AT,
                "enrollment_json": {"kind": "upcoming"},
                "current_revision_id": self.config_id,
                "change_version": 1,
                "next_assignment_seq": 1,
                "status": "active",
                "retirement_intent_id": None,
                "created_by_subject_id": "owner",
                "created_by_command_id": "rrt-test",
                "created_at_utc": AT,
            },
        )
        insert_record(db, "related_task_rule_revisions", self.configuration_record(self.config, 1))

    def configuration_record(self, config, index, prior=None):
        digest = payload_hash("configuration", config)[0]
        fields = {"related_task_rule_id": self.root_id, "revision_index": str(index), "configuration_hash": digest}
        if prior:
            fields["prior_revision_id"] = prior
        return {
            "related_task_rule_revision_id": derive("rule_revision", fields)[0],
            "related_task_rule_id": self.root_id,
            "revision_index": index,
            "prior_revision_id": prior,
            "configuration_json": config,
            "configuration_hash": digest,
            "created_by_subject_id": "owner",
            "created_by_command_id": "rrt-test",
            "created_at_utc": AT,
        }

    def proof_record(self):
        payload = {
            "source_item_id": self.source["item_id"],
            "source_item_version": "1",
            "recurrence_set_id": self.selector["recurrence_set_id"],
            "recurrence_revision_id": self.revision,
            "normalized_recurrence_set_hash": self.source_candidate["header"]["normalized_recurrence_set_hash"],
            "selector": self.selector,
            "occurrence_key": self.key,
            "lineage_ids": [],
            "enrolled_recurrence_revision_id": self.revision,
        }
        identity = derive("proof", {"related_task_rule_id": self.root_id, "proof_kind": "enrollment", "proof_payload": payload})[0]
        return {
            "proof_id": identity,
            "related_task_rule_id": self.root_id,
            "proof_kind": "enrollment",
            "source_item_version": 1,
            "recurrence_revision_id": self.revision,
            "prior_recurrence_revision_id": None,
            "proof_json": payload,
            "proof_hash": identity.rsplit("_", 1)[1],
            "created_by_command_id": "rrt-test",
            "created_at_utc": AT,
        }

    def seed_assignment(self):
        self.seed_root()
        proof = self.proof_record()
        insert_record(self.db, "related_task_source_proofs", proof)
        assignment = derive("assignment", {"related_task_rule_id": self.root_id, "initial_selector": self.selector})[0]
        generation = derive("generation", {"assignment_id": assignment, "generation_index": "1"})[0]
        binding = self.task["temporal_binding"]["latest_revision"]["temporal_binding_revision_id"]
        state = {
            "generation_id": generation,
            "selector": self.selector,
            "occurrence_key": self.key,
            "source_item_version": "1",
            "recurrence_revision_id": self.revision,
            "proof_id": proof["proof_id"],
            "task_item_id": self.task_id,
            "task_item_version": "1",
            "temporal_binding_revision_id": binding,
            "adopted_rule_revision_id": self.config_id,
            "managed_baseline": {k: v for k, v in self.config.items() if k not in {"task_owner", "generation_horizon_seconds"}},
            "disposition": "governed",
            "restoration_veto": False,
            "reason": "new_source_slot",
        }
        digest = payload_hash("state", state)[0]
        state_id = derive("assignment_revision", {"assignment_id": assignment, "change_version": "1", "state_hash": digest})[0]
        reference = ensure_selector(self.db, revision_id=self.revision, selector=self.selector, budget=ProofBudget())
        insert_record(
            self.db,
            "related_task_assignments",
            {
                "assignment_id": assignment,
                "related_task_rule_id": self.root_id,
                "assignment_seq": 1,
                "initial_selector_ref": reference,
                "initial_selector_json": self.selector,
                "initial_occurrence_key": self.key,
                "created_rule_revision_id": self.config_id,
                "created_at_utc": AT,
                "created_by_command_id": "rrt-test",
                "current_assignment_revision_id": state_id,
                "change_version": 1,
                "current_generation_id": generation,
            },
        )
        insert_record(
            self.db,
            "related_task_generations",
            {
                "generation_id": generation,
                "assignment_id": assignment,
                "generation_index": 1,
                "predecessor_generation_id": None,
                "task_item_id": self.task_id,
                "created_task_version": 1,
                "relationship_id": self.task["relationship"]["relation_id"],
                "temporal_binding_id": self.task["temporal_binding"]["temporal_binding_id"],
                "item_access_owner_id": self.owner_id,
                "created_rule_revision_id": self.config_id,
                "creation_proof_id": proof["proof_id"],
                "created_by_command_id": "rrt-test",
                "created_at_utc": AT,
            },
        )
        insert_record(
            self.db,
            "related_task_assignment_revisions",
            {
                "assignment_revision_id": state_id,
                "assignment_id": assignment,
                "change_version": 1,
                "prior_assignment_revision_id": None,
                "state_json": state,
                "state_hash": digest,
                "source_item_version": 1,
                "recurrence_revision_id": self.revision,
                "task_item_id": self.task_id,
                "task_item_version": 1,
                "adopted_rule_revision_id": self.config_id,
                "generation_id": generation,
                "selector_ref": reference,
                "temporal_binding_revision_id": binding,
                "proof_id": proof["proof_id"],
                "command_id": "rrt-test",
                "created_at_utc": AT,
            },
        )
        reserve_selector(
            self.db,
            rule_id=self.root_id,
            assignment_id=assignment,
            proof_id=proof["proof_id"],
            selector=self.selector,
            revision_id=self.revision,
            budget=ProofBudget(),
        )
        compare_and_swap(self.db, "related_task_rules", self.root_id, 1, {"next_assignment_seq": 2})
        return assignment, generation, state_id, proof["proof_id"]

    def test_populated_migration_preserves_every_old_table_and_enrolls_nothing(self):
        after = snapshot(self.db)
        self.assertEqual({k: after[k] for k in self.before}, self.before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_rules").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM relative_temporal_bindings").fetchone()[0], 3)

    def test_complete_assignment_deferred_pointer_graph_and_explicit_deep_verification(self):
        with self.db.atomic_command(write=True):
            assignment, generation, state, proof = self.seed_assignment()
        with self.db.atomic_command(write=False):
            verify_deep(self.db)
        self.assertEqual(read_record(self.db, "related_task_assignments", assignment)["current_generation_id"], generation)
        self.assertEqual(read_record(self.db, "related_task_assignment_revisions", state)["state_json"]["proof_id"], proof)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_items").fetchone()[0], len(self.before["coordination_items"]))

    def test_immutable_history_cas_and_historical_decoding_after_config_change(self):
        with self.db.atomic_command(write=True):
            self.seed_root()
        changed = copy.deepcopy(self.config)
        changed["offset_seconds"] = "6000"
        second = self.configuration_record(changed, 2, self.config_id)
        with self.db.atomic_command(write=True):
            insert_record(self.db, "related_task_rule_revisions", second)
            compare_and_swap(
                self.db, "related_task_rules", self.root_id, 1, {"current_revision_id": second["related_task_rule_revision_id"]}
            )
        self.assertEqual(read_record(self.db, "related_task_rule_revisions", self.config_id)["configuration_json"], self.config)
        with self.assertRaisesRegex(SpineValidationError, "stale_version"), self.db.atomic_command(write=True):
            compare_and_swap(self.db, "related_task_rules", self.root_id, 1, {"next_assignment_seq": 2})
        for sql in [
            "UPDATE related_task_rule_revisions SET configuration_hash='bad'",
            "DELETE FROM related_task_rule_revisions",
            "UPDATE related_task_rules SET change_version=1",
            "DELETE FROM related_task_rules",
        ]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command(write=True):
                self.db.execute(sql)

    def test_preimage_and_cross_root_corruption_roll_back_whole_transaction(self):
        for field, bad in [
            ("configuration_hash", "bad"),
            ("configuration_json", {**self.config, "extra": None}),
            ("configuration_json", {**self.config, "task_owner": {"owner_kind": "system"}}),
        ]:
            with self.subTest(field=field), self.assertRaises(SpineValidationError), self.db.atomic_command(write=True):
                self.seed_root()
                # Insert an invalid unpublished successor, rather than mutating history.
                record = self.configuration_record(self.config, 2, self.config_id)
                record[field] = bad
                insert_record(self.db, "related_task_rule_revisions", record)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_rules").fetchone()[0], 0)
        self.assertEqual(self.db.mutation_state.recurring.rows, set())
        with self.db.atomic_command(write=True):
            self.seed_root()

    def test_selector_reuse_checks_children_and_full_candidate_union(self):
        with self.db.atomic_command(write=True):
            reference = ensure_selector(self.db, revision_id=self.revision, selector=self.selector, budget=ProofBudget())
            self.assertEqual(ensure_selector(self.db, revision_id=self.revision, selector=self.selector, budget=ProofBudget()), reference)
        before = snapshot(self.db)
        wrong = copy.deepcopy(self.selector)
        wrong["source_rule_selectors"][0]["seed"] = "2026-08-21T10:00:00"
        with self.assertRaisesRegex(SpineValidationError, "source_continuity_unresolved"), self.db.atomic_command(write=True):
            ensure_selector(self.db, revision_id=self.revision, selector=wrong, budget=ProofBudget())
        self.assertEqual(snapshot(self.db), before)
        # Old producer's INSERT OR IGNORE must not hide a corrupted relational selector.
        with self.db.atomic_command(write=True):
            self.db.execute("DELETE FROM recurrence_target_rule_source_selectors WHERE target_occurrence_selector_ref=?", (reference,))
            self.db.execute("DELETE FROM recurrence_target_rule_sources WHERE target_occurrence_selector_ref=?", (reference,))
        with self.assertRaises(SpineValidationError), self.db.atomic_command(write=True):
            ensure_selector(self.db, revision_id=self.revision, selector=self.selector, budget=ProofBudget())

    def test_source_proofs_require_actual_membership_snapshot_and_budgets(self):
        with self.db.atomic_command(write=True):
            self.seed_root()
            root = read_record(self.db, "related_task_rules", self.root_id)
            proof = self.proof_record()["proof_json"]
            validate_proof("enrollment", proof)
            verify_proof(self.db, root, "enrollment", proof, ProofBudget())
            for change in [{"normalized_recurrence_set_hash": "bad"}, {"source_item_version": "2"}, {"lineage_ids": ["missing"]}]:
                with self.subTest(change=change), self.assertRaises(SpineValidationError):
                    verify_proof(self.db, root, "enrollment", {**proof, **change}, ProofBudget())
            with self.assertRaisesRegex(SpineValidationError, "source_continuity_unresolved"):
                require_candidate(self.db, self.revision, self.selector, ProofBudget(steps=1))
            self.assertIsNone(candidate(self.db, self.revision, "2026-08-25T10:00:00", ProofBudget()))
        with self.assertRaisesRegex(SpineValidationError, "pinned"):
            candidate(self.db, self.revision, self.selector["scheduled_fact"], ProofBudget())

    def test_named_indexes_support_keyset_source_target_and_history_plans(self):
        with self.db.atomic_command(write=True):
            self.seed_assignment()
        queries = [
            (
                "related_task_rules_owner_idx",
                "SELECT related_task_rule_id FROM related_task_rules WHERE owner_key=? AND status=? "
                "AND related_task_rule_id>? ORDER BY related_task_rule_id",
                (canonical({"owner_kind": "subject", "owner_subject_id": "owner"}), "active", ""),
            ),
            (
                "related_task_rules_source_idx",
                "SELECT related_task_rule_id FROM related_task_rules WHERE source_item_id=? ORDER BY related_task_rule_id",
                (self.source["item_id"],),
            ),
            (
                "related_task_assignments_page_idx",
                "SELECT assignment_seq FROM related_task_assignments WHERE related_task_rule_id=? "
                "AND assignment_seq>? ORDER BY assignment_seq LIMIT 10",
                (self.root_id, 0),
            ),
            (
                "related_task_generations_assignment_idx",
                "SELECT generation_index FROM related_task_generations WHERE assignment_id=? ORDER BY generation_index",
                ("a",),
            ),
            (
                "related_task_assignment_revisions_history_idx",
                "SELECT change_version FROM related_task_assignment_revisions WHERE assignment_id=? "
                "AND change_version>? ORDER BY change_version",
                ("a", 0),
            ),
            (
                "related_task_reservations_assignment_idx",
                "SELECT selector_ref FROM related_task_selector_reservations WHERE assignment_id=? ORDER BY selector_ref",
                ("a",),
            ),
            (
                "related_task_proofs_revision_idx",
                "SELECT proof_id FROM related_task_source_proofs WHERE related_task_rule_id=? "
                "AND recurrence_revision_id=? ORDER BY proof_id",
                (self.root_id, self.revision),
            ),
            (
                "related_task_intents_pending_idx",
                "SELECT intent_id FROM related_task_intents WHERE related_task_rule_id=? "
                "AND intent_kind=? AND status='pending' ORDER BY intent_id",
                (self.root_id, "adopt"),
            ),
            (
                "related_task_outcomes_assignment_idx",
                "SELECT intent_id FROM related_task_intent_outcomes WHERE assignment_id=? ORDER BY intent_id",
                ("a",),
            ),
        ]
        for index, sql, args in queries:
            with self.subTest(index=index):
                plan = " ".join(r[3] for r in self.db.execute("EXPLAIN QUERY PLAN " + sql, args))
                self.assertIn(index, plan)
                self.assertNotIn("TEMP B-TREE", plan)
        plan = " ".join(
            r[3]
            for r in self.db.execute(
                "EXPLAIN QUERY PLAN SELECT assignment_id FROM related_task_generations WHERE task_item_id=?", (self.task_id,)
            )
        )
        self.assertIn("SEARCH related_task_generations USING INDEX", plan)
        self.assertNotIn("SCAN", plan)
        plan = " ".join(
            r[3]
            for r in self.db.execute(
                "EXPLAIN QUERY PLAN SELECT lineage_id FROM recurrence_lineage WHERE prior_recurrence_revision_id=? "
                "AND new_recurrence_revision_id=? AND prior_child_id=? AND effect='copied'",
                ("old", "new", "child"),
            )
        )
        self.assertIn("related_task_source_lineage_copy_idx", plan)

    def test_intent_outcome_progress_catalog_and_dirty_queue_records(self):
        with self.db.atomic_command(write=True):
            assignment, _, state, _ = self.seed_assignment()
            payload = {"configuration_revision_id": self.config_id, "assignment_high_water": "1", "scope": "upcoming_open"}
            intent = derive(
                "intent",
                {"related_task_rule_id": self.root_id, "rule_change_version": "2", "intent_kind": "adopt", "intent_payload": payload},
            )[0]
            insert_record(
                self.db,
                "related_task_intents",
                {
                    "intent_id": intent,
                    "related_task_rule_id": self.root_id,
                    "rule_change_version": 2,
                    "intent_kind": "adopt",
                    "intent_json": payload,
                    "status": "pending",
                    "created_by_command_id": "r1-intent",
                    "created_at_utc": AT,
                },
            )
            insert_record(
                self.db,
                "related_task_intent_outcomes",
                {
                    "intent_id": intent,
                    "assignment_id": assignment,
                    "assignment_revision_id": state,
                    "outcome": "retained_equal",
                    "reason": "retained_equal",
                    "command_id": "r1-intent",
                    "created_at_utc": AT,
                },
            )
            insert_record(
                self.db,
                "related_task_rule_progress",
                {
                    "related_task_rule_id": self.root_id,
                    "progress_version": 0,
                    "source_scan_version": 1,
                    "recurrence_revision_id": self.revision,
                    "coverage_json": {
                        "range_start_utc": "2026-08-22T00:00:00Z",
                        "range_end_utc": "2026-08-25T00:00:00Z",
                        "source_after": None,
                        "complete": True,
                    },
                    "assignment_after_seq": 1,
                    "pending_intent_id": intent,
                },
            )
            insert_record(
                self.db,
                "related_task_dirty_rules",
                {
                    "related_task_rule_id": self.root_id,
                    "dirty_generation": 1,
                    "source_dirty": 0,
                    "target_dirty": 0,
                    "intent_dirty": 1,
                    "assignment_after_seq": 0,
                },
            )
            self.db.execute("UPDATE related_task_catalog_state SET catalog_generation=1")
        with self.db.atomic_command(write=True):
            self.db.execute("UPDATE related_task_intents SET status='complete' WHERE intent_id=?", (intent,))
            compare_and_swap(self.db, "related_task_rule_progress", self.root_id, 0, {"pending_intent_id": None})
            self.db.execute("DELETE FROM related_task_dirty_rules WHERE related_task_rule_id=? AND dirty_generation=1", (self.root_id,))
        with self.db.atomic_command(write=False):
            verify_deep(self.db)
        for sql in [
            "UPDATE related_task_intent_outcomes SET reason='changed'",
            "DELETE FROM related_task_intent_outcomes",
            "UPDATE related_task_intents SET status='pending'",
            "UPDATE related_task_catalog_state SET catalog_generation=0",
        ]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command(write=True):
                self.db.execute(sql)

    def test_source_proof_fk_and_positive_counter_constraints(self):
        with self.db.atomic_command(write=True):
            self.seed_root()
        bad = self.proof_record()
        bad["source_item_version"] = 2
        with self.assertRaises(SpineValidationError), self.db.atomic_command(write=True):
            insert_record(self.db, "related_task_source_proofs", bad)
        for change in [{"related_task_rule_revision_id": None}, {"revision_index": 0}, {"configuration_json": "{} "}]:
            with (
                self.subTest(change=change),
                self.assertRaises((SpineValidationError, sqlite3.IntegrityError)),
                self.db.atomic_command(write=True),
            ):
                record = self.configuration_record(self.config, 2, self.config_id)
                insert_record(self.db, "related_task_rule_revisions", {**record, **change})
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command(write=True):
            self.db.execute("INSERT INTO related_task_dirty_rules VALUES('missing-root',1,1,0,0,0)")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_source_proofs").fetchone()[0], 0)

    def test_separate_connections_serialize_duplicate_reservation_and_stale_cas(self):
        with self.db.atomic_command(write=True):
            assignment, _, _, proof = self.seed_assignment()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "candidate.sqlite")
            # Backup requires no pending transaction; destination is disposable.
            with closing(sqlite3.connect(path)) as destination:
                self.db.backup(destination)
                destination.execute("PRAGMA journal_mode=WAL")
            gate = threading.Barrier(2)

            def writer(number):
                db = connect(path)
                try:
                    attach_candidate(db)
                    gate.wait(timeout=10)
                    with db.atomic_command(write=True):
                        reserve_selector(
                            db,
                            rule_id=self.root_id,
                            assignment_id=assignment,
                            proof_id=proof,
                            selector=self.selector,
                            revision_id=self.revision,
                            budget=ProofBudget(),
                        )
                        compare_and_swap(db, "related_task_rules", self.root_id, 2, {"next_assignment_seq": 3})
                    return "committed"
                except SpineValidationError as exc:
                    return exc.code
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(writer, [1, 2]))
            self.assertEqual(sorted(results), ["committed", "stale_version"])
            db = connect(path)
            self.addCleanup(db.close)
            attach_candidate(db)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM related_task_selector_reservations").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT change_version FROM related_task_rules").fetchone()[0], 3)

    def test_sql_predecessor_uniqueness_race_with_real_foreign_keys(self):
        """SQL constraint isolation, not restoration admission (R2 owns that).

        Raw SQLite intentionally omits the domain finalizer here, while retaining
        every FK, to prove the physical UNIQUE predecessor gate independently of
        the source-cancellation and current-pointer admission checks.
        """
        with self.db.atomic_command(write=True):
            assignment, generation, _, _ = self.seed_assignment()
        original = dict(self.db.execute("SELECT * FROM related_task_generations WHERE generation_id=?", (generation,)).fetchone())
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "predecessor.sqlite")
            with closing(sqlite3.connect(path)) as destination:
                self.db.backup(destination)
                destination.execute("PRAGMA journal_mode=WAL")
            gate = threading.Barrier(2)

            def writer(number):
                db = sqlite3.connect(path, timeout=10)
                db.execute("PRAGMA foreign_keys=ON")
                task, owner, _ = self.extra_tasks[number]
                record = {
                    **original,
                    "generation_id": derive("generation", {"assignment_id": assignment, "generation_index": str(number + 2)})[0],
                    "generation_index": number + 2,
                    "predecessor_generation_id": generation,
                    "task_item_id": task["task"]["item_id"],
                    "relationship_id": task["relationship"]["relation_id"],
                    "temporal_binding_id": task["temporal_binding"]["temporal_binding_id"],
                    "item_access_owner_id": owner,
                }
                try:
                    gate.wait(timeout=10)
                    with db:
                        db.execute(
                            "INSERT INTO related_task_generations(" + ",".join(record) + ") VALUES(" + ",".join("?" for _ in record) + ")",
                            tuple(record.values()),
                        )
                    return "committed"
                except sqlite3.IntegrityError as exc:
                    return str(exc)
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(writer, [0, 1]))
            self.assertEqual(results.count("committed"), 1)
            self.assertIn("UNIQUE constraint failed: related_task_generations.predecessor_generation_id", results)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM related_task_generations WHERE predecessor_generation_id=?", (generation,)).fetchone()[
                        0
                    ],
                    1,
                )


if __name__ == "__main__":
    unittest.main()
