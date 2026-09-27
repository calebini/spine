from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core import facets as codec
from spine.core.canonical_json import canonical_json_text
from spine.ledger import ItemVersionDraft, connect, create_item_version_from_draft, create_task_v1, facets, initialize_schema
from spine.ledger.migrate import verify_schema
from spine.ledger.preflight import verify_runtime_schema
from tests.facet_storage_support import DEFINITION, NORMALIZED, NOW, all_rows, receipt, seeded_snapshot

ROOT = Path(__file__).parents[1]


class FacetStorageTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        initialize_schema(self.db)
        response = handle(
            "subject.upsert",
            {
                "command_id": "owner",
                "actor_subject_id": "owner",
                "subject_id": "owner",
                "subject_kind": "person",
                "display_name": "Owner",
                "updated_at_utc": NOW,
            },
            CommandContext(ledger=self.db),
        )
        self.assertTrue(response["ok"], response)

    def tearDown(self):
        self.db.close()

    def create(self, item="task", *, seeded=True):
        with patch("spine.ledger.items.insert_snapshot", seeded_snapshot if seeded else facets.insert_snapshot):
            return create_task_v1(self.db, item_id=item, title="Flight", created_at_utc=NOW, created_by_subject_id="owner")

    def next(self, item="task", **kwargs):
        version = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (item,)).fetchone()[0]
        return create_item_version_from_draft(
            self.db, ItemVersionDraft(item_id=item, target_version=version, created_at_utc=NOW, created_by_subject_id="owner", **kwargs)
        )

    def test_empty_and_eight_entry_copy_forward_and_last_removal(self):
        self.create()
        first = facets.load_snapshot(self.db, "task", 1)
        self.assertEqual(len(first), 8)
        self.next(title="New title")
        self.assertEqual(facets.load_snapshot(self.db, "task", 2), first)
        self.next(facet_entries=())
        self.assertEqual(facets.load_snapshot(self.db, "task", 3), [])
        self.assertEqual(
            tuple(self.db.execute("SELECT entry_count,values_bytes FROM item_facet_snapshots WHERE item_version=3").fetchone()), (0, 2)
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_facet_current_values").fetchone()[0], 0)
        self.next(title="Empty copied")
        self.assertEqual(facets.load_snapshot(self.db, "task", 4), [])
        verify_schema(self.db)

    def test_pinned_history_publish_replace_retire_and_reference_inactivation(self):
        self.create()
        before = facets.load_snapshot(self.db, "task", 1)
        with self.db.atomic_command():
            rid = receipt(self.db, "retire")
            revised = copy.deepcopy(DEFINITION)
            revised["fields"][0]["max_length"] = "1"
            facets.insert_revision(
                self.db, schema_id="schema", revision_id="revision2", definition=revised, receipt_id=rid, expected_revision_id="revision"
            )
            archetype = self.db.execute("SELECT item_archetype_id FROM archetype_facet_bindings LIMIT 1").fetchone()[0]
            facets.set_binding(
                self.db,
                binding_id="replacement",
                archetype_id=archetype,
                facet_key="details0",
                revision_id="revision2",
                expected_binding_id="binding0",
                receipt_id=rid,
            )
            facets.retire_schema(self.db, schema_id="schema", expected_revision_id="revision2", receipt_id=rid)
            facets.remove_binding(self.db, binding_id="binding1", receipt_id=rid)
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='owner'")
        self.next(title="Preserve history")
        self.assertEqual(facets.load_snapshot(self.db, "task", 2), before)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            facets.prepare_entry(
                self.db,
                item_id="task",
                item_version=2,
                binding_id="binding2",
                values={"flight": "AC1"},
                receipt_id=receipt(self.db, "fresh-denied"),
            )
        verify_schema(self.db)

    def test_typed_queries_and_reference_integrity(self):
        self.create()
        for field, value in (("flight", "AC123"), ("confirmed", True), ("seats", "2"), ("day", "2036-02-29"), ("class", "economy")):
            self.assertTrue(facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key=field, value=value))
        self.assertFalse(facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="flight", value="ac123"))
        self.assertFalse(facets.probe(self.db, item_id="task", version=2, revision_id="revision", field_key="flight", value="AC123"))
        with self.assertRaises(SpineValidationError):
            facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="confirmed", value="1")
        with self.assertRaises(SpineValidationError):
            facets.probe(self.db, item_id="task", version=1, revision_id="revision", field_key="person", value="owner")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_facet_references").fetchone()[0], 8)
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            self.db.execute("DELETE FROM subjects WHERE subject_id='owner'")

    def test_missing_marker_finalizer_touch_projection_and_multiversion_rollback(self):
        self.create()
        before = all_rows(self.db)
        failures = [
            patch("spine.ledger.items.insert_snapshot", lambda *a: None),
            patch("spine.ledger.facets.finalize", return_value=None),
        ]
        for fault in failures:
            with self.subTest(fault=fault), self.assertRaises(SpineValidationError), fault:
                self.next(title="Must roll back")
            self.assertEqual(all_rows(self.db), before)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.next(title="First")
            self.create("second", seeded=False)
            receipt(self.db, "rollback-receipt")
            self.db._facet_versions.remove(("second", 1))
        self.assertEqual(all_rows(self.db), before)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.next(title="Index mismatch")
            self.db.execute("DELETE FROM item_facet_current_values WHERE item_id='task'")
        self.assertEqual(all_rows(self.db), before)

    def test_unregistered_allocation_raw_commit_and_early_helper_commit_rejected(self):
        self.create()
        before = all_rows(self.db)
        with self.assertRaises(sqlite3.OperationalError), self.db.atomic_command():
            self.db.execute(
                "INSERT INTO coordination_item_versions SELECT item_id,2,title,summary,intent_hash,"
                "normalized_fields_hash,source_ref,created_at_utc,created_by_subject_id FROM coordination_item_versions"
            )
        with self.assertRaises(SpineValidationError), self.db.version_allocation("unregistered"):
            pass
        with self.assertRaises(sqlite3.DatabaseError), self.db.atomic_command():
            self.next(title="Attempt commit")
            self.db.execute("COMMIT")
        with self.assertRaises(RuntimeError), self.db.atomic_command():
            self.db.commit()
        with self.db.atomic_command(write=False):
            self.db.execute("SAVEPOINT cached_read")
            self.db.execute("RELEASE cached_read")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("SAVEPOINT cached_read")
        self.assertEqual(all_rows(self.db), before)

    def test_archetype_clear_and_snapshot_mismatch_are_atomic(self):
        self.create()
        before = all_rows(self.db)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.next(title="Keep values")
            self.db.execute("DELETE FROM item_archetype_assignments WHERE item_id='task' AND item_version=2")
        self.assertEqual(all_rows(self.db), before)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            invalid = facets.load_snapshot(self.db, "task", 1)
            invalid[0]["values_json"] = '{"flight":"AC123","unknown":true}'
            self.next(facet_entries=tuple(invalid))
        self.assertEqual(all_rows(self.db), before)

    def test_constraints_immutability_foreign_identity_and_catalog_cas(self):
        self.create()
        before = all_rows(self.db)
        statements = [
            "UPDATE facet_schema_revisions SET definition_hash='" + "0" * 64 + "'",
            "DELETE FROM item_facet_entries",
            "DELETE FROM item_facet_snapshots",
            "DELETE FROM facet_schema_fields",
            "UPDATE facet_schemas SET current_revision_id='missing'",
            "UPDATE item_facet_current_values SET value_integer=NULL WHERE value_type='boolean'",
        ]
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises((sqlite3.IntegrityError, SpineValidationError)), self.db.atomic_command():
                self.db.execute(sql)
            self.assertEqual(all_rows(self.db), before)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            facets.insert_revision(
                self.db,
                schema_id="schema",
                revision_id="new",
                definition=DEFINITION,
                receipt_id=receipt(self.db, "stale"),
                expected_revision_id="wrong",
            )
        self.assertEqual(all_rows(self.db), before)

    def test_bounded_preflight_and_explicit_repair_and_deep_verification(self):
        self.create()
        with patch("spine.ledger.facets.verify_all", side_effect=AssertionError("deep scan")):
            verify_runtime_schema(self.db)
            self.next(title="Still bounded")
        before = all_rows(self.db)
        with self.db.atomic_command():
            self.db.execute("DELETE FROM item_facet_current_values")
            facets.rebuild_current_index(self.db, "task")
        self.assertEqual(all_rows(self.db), before)
        with (
            patch("spine.ledger.facets.verify_all", side_effect=RuntimeError("explicit deep verification")),
            self.assertRaisesRegex(RuntimeError, "explicit deep"),
        ):
            verify_schema(self.db)
        with self.db:
            self.db.execute("DROP INDEX item_facet_current_text_idx")
        with self.assertRaises(SpineValidationError):
            verify_runtime_schema(self.db)

    def test_published_definition_vector_is_persisted_byte_exact(self):
        vector = json.loads((ROOT / "tests/fixtures/archetype_facets/vectors/definition_normalization.json").read_text())
        with self.db.atomic_command():
            facets.insert_schema(
                self.db,
                schema_id="vector",
                revision_id="vector-r1",
                owner={"owner_kind": "system"},
                schema_key="flight",
                definition=vector["input"],
                receipt_id=receipt(self.db, "vector"),
            )
        stored = self.db.execute("SELECT definition_json,definition_hash FROM facet_schema_revisions").fetchone()
        self.assertEqual(stored[0], canonical_json_text(vector["normalized_definition"]))
        self.assertEqual(stored[1], vector["sha256"])
        self.assertEqual(codec.normalize_definition(vector["equivalent_input"]), facets.load_definition(self.db, "vector-r1"))

    def test_maximum_field_reference_and_current_index_cardinality(self):
        self.create()
        definition = {
            "display_name": "Wide",
            "description": None,
            "compatible_item_types": ["task"],
            "fields": [
                {"key": f"f{i:02}", "type": "reference", "target_kind": "subject", "required": True, "queryable": True} for i in range(32)
            ],
        }
        with self.db.atomic_command():
            rid = receipt(self.db, "wide")
            facets.insert_schema(
                self.db,
                schema_id="wide",
                revision_id="wide-r1",
                owner={"owner_kind": "subject", "owner_subject_id": "owner"},
                schema_key="wide",
                definition=definition,
                receipt_id=rid,
            )
            archetype = self.db.execute("SELECT item_archetype_id FROM archetype_facet_bindings LIMIT 1").fetchone()[0]
            entries = []
            for i in range(8):
                facets.set_binding(
                    self.db,
                    binding_id=f"wide{i}",
                    archetype_id=archetype,
                    facet_key=f"details{i}",
                    revision_id="wide-r1",
                    expected_binding_id=f"binding{i}",
                    receipt_id=rid,
                )
                entries.append(
                    facets.prepare_entry(
                        self.db,
                        item_id="task",
                        item_version=1,
                        binding_id=f"wide{i}",
                        values={f"f{k:02}": "owner" for k in range(32)},
                        receipt_id=rid,
                    )
                )
            self.next(facet_entries=tuple(entries))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_facet_current_values").fetchone()[0], 256)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_facet_references WHERE item_version=2").fetchone()[0], 256)
        self.next(title="Wide copied")
        self.assertEqual(facets.load_snapshot(self.db, "task", 2), facets.load_snapshot(self.db, "task", 3))

    def test_location_reference_and_inactive_subject_fresh_attachment(self):
        self.create()
        with self.db.atomic_command():
            self.db.execute("INSERT INTO subjects VALUES ('passenger','person','Passenger','inactive',?,?)", (NOW, NOW))
            self.db.execute(
                "INSERT INTO locations (location_id,label,kind,created_at_utc,updated_at_utc) VALUES ('airport','Airport','place',?,?)",
                (NOW, NOW),
            )
            rid = receipt(self.db, "location-reference")
            entry = facets.prepare_entry(
                self.db,
                item_id="task",
                item_version=1,
                binding_id="binding0",
                values={"flight": "AC1", "airport": "airport"},
                receipt_id=rid,
            )
            self.next(facet_entries=(entry,))
        self.assertTrue(facets.probe(self.db, item_id="task", version=2, revision_id="revision", field_key="airport", value="airport"))
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            self.db.execute("DELETE FROM locations WHERE location_id='airport'")
        for value in ("passenger", "missing", "airport"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(SpineValidationError, "facet_reference_unavailable"),
                self.db.atomic_command(),
            ):
                facets.prepare_entry(
                    self.db,
                    item_id="task",
                    item_version=2,
                    binding_id="binding0",
                    values={"flight": "AC1", "person": value},
                    receipt_id=rid,
                )

    def test_command_missing_marker_is_environment_failure_and_rolls_back_receipt(self):
        before = all_rows(self.db)
        request = {"command_id": "broken-task", "actor_subject_id": "owner", "created_at_utc": NOW, "title": "Not committed"}
        with patch("spine.ledger.items.insert_snapshot", lambda *args: None):
            result = handle("task.create", request, CommandContext(ledger=self.db))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "environment_failure")
        self.assertEqual(all_rows(self.db), before)

    def test_duplicate_owner_keys_active_binding_and_noncontiguous_revision_fail(self):
        self.create()
        before = all_rows(self.db)
        statements = [
            "INSERT INTO facet_schemas SELECT 'duplicate',owner_kind,owner_subject_id,owner_group_id,schema_key,status,"
            "current_revision_id,created_command_receipt_id,retired_command_receipt_id FROM facet_schemas",
            "INSERT INTO archetype_facet_bindings SELECT 'duplicate',item_archetype_id,facet_key,facet_schema_revision_id,status,"
            "created_command_receipt_id,ended_command_receipt_id FROM archetype_facet_bindings WHERE facet_binding_id='binding0'",
            "INSERT INTO facet_schema_revisions SELECT 'gap',facet_schema_id,3,definition_contract_version,canonical_json_version,"
            "definition_json,definition_hash,created_command_receipt_id FROM facet_schema_revisions",
        ]
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
                self.db.execute(sql)
            self.assertEqual(all_rows(self.db), before)

    def test_system_retired_keys_and_cross_root_pointer_are_not_reusable(self):
        with self.db.atomic_command():
            rid = receipt(self.db, "systems")
            for key in ("system1", "system2"):
                facets.insert_schema(
                    self.db,
                    schema_id=key,
                    revision_id=key + "-r1",
                    owner={"owner_kind": "system"},
                    schema_key=key,
                    definition=DEFINITION,
                    receipt_id=rid,
                )
            facets.retire_schema(self.db, schema_id="system1", expected_revision_id="system1-r1", receipt_id=rid)
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            facets.insert_schema(
                self.db,
                schema_id="replacement",
                revision_id="replacement-r1",
                owner={"owner_kind": "system"},
                schema_key="system1",
                definition=DEFINITION,
                receipt_id=rid,
            )
        # Exercise the deferred composite FK itself without the stronger runtime
        # finalizer masking the relational rejection.
        raw = sqlite3.connect(":memory:")
        try:
            self.db.backup(raw)
            raw.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.IntegrityError), raw:
                raw.execute("UPDATE facet_schemas SET current_revision_id='system1-r1' WHERE facet_schema_id='system2'")
        finally:
            raw.close()

    def test_composite_binding_and_typed_field_foreign_keys(self):
        self.create()
        for kind in ("binding", "typed_field"):
            with self.subTest(kind=kind):
                raw = sqlite3.connect(":memory:")
                try:
                    self.db.backup(raw)
                    raw.execute("PRAGMA foreign_keys=ON")
                    with self.assertRaises(sqlite3.IntegrityError), raw:
                        if kind == "binding":
                            raw.execute(
                                "INSERT INTO coordination_item_versions SELECT item_id,2,title,summary,intent_hash,"
                                "normalized_fields_hash,source_ref,created_at_utc,created_by_subject_id FROM coordination_item_versions"
                            )
                            raw.execute("INSERT INTO item_facet_snapshots VALUES ('task',2,1,2)")
                            raw.execute(
                                "INSERT INTO item_facet_entries SELECT item_id,2,facet_key,facet_schema_revision_id,'binding1',"
                                "item_archetype_id,item_archetype_revision_id,archetype_selection_source,archetype_source_ref,"
                                "value_contract_version,values_json,source_command_receipt_id "
                                "FROM item_facet_entries WHERE facet_key='details0'"
                            )
                        else:
                            raw.execute("DELETE FROM item_facet_current_values WHERE facet_key='details0' AND field_key='flight'")
                            raw.execute(
                                "INSERT INTO item_facet_current_values VALUES ('task','details0','flight',1,'revision','integer',1,NULL,1)"
                            )
                finally:
                    raw.close()


class FacetCodecTests(unittest.TestCase):
    def test_canonical_bytes_hash_and_malformed_input(self):
        reversed_fields = copy.deepcopy(DEFINITION)
        reversed_fields["fields"].reverse()
        self.assertEqual(codec.normalize_definition(reversed_fields), NORMALIZED)
        encoded = canonical_json_text(NORMALIZED)
        self.assertEqual(
            codec.decode_definition(
                encoded, codec.definition_hash(NORMALIZED), contract=codec.DEFINITION_VERSION, canonical=codec.CANONICAL_VERSION
            ),
            NORMALIZED,
        )
        for value in ('{"flight":"a","flight":"b"}', '{"flight":"\\ud800"}', '{"flight":NaN}', "[]", '"x"', "\ud800"):
            with self.subTest(value=repr(value)), self.assertRaises(SpineValidationError):
                codec.decode_values(NORMALIZED, value, contract=codec.VALUE_VERSION)
        for version in ("unknown", "spine.item-facets.v2"):
            with self.assertRaises(SpineValidationError):
                codec.decode_values(NORMALIZED, '{"flight":"AC1"}', contract=version)

    def test_value_and_definition_capacity_and_domains(self):
        self.assertEqual(codec.normalize_values(NORMALIZED, {"flight": "Cafe\u0301"}), {"flight": "Café"})
        for values in (
            {"flight": "x", "seats": "-0"},
            {"flight": "x", "seats": "9223372036854775808"},
            {"flight": "x", "confirmed": 1},
            {"flight": "x", "day": "2035-02-29"},
            {"flight": "\x00"},
            {"flight": "x", "class": "premium"},
            {},
        ):
            with self.subTest(values=values), self.assertRaises(SpineValidationError):
                codec.normalize_values(NORMALIZED, values)
        for n in ("-9223372036854775808", "9223372036854775807"):
            self.assertEqual(codec.normalize_values(NORMALIZED, {"flight": "x", "seats": n})["seats"], n)
        large = {**DEFINITION, "fields": [{"key": f"x{i}", "type": "text", "required": False, "max_length": "1024"} for i in range(32)]}
        normal = codec.normalize_definition(large)
        with self.assertRaises(SpineValidationError):
            codec.normalize_values(normal, {f"x{i}": "x" * 1024 for i in range(16)})
        with self.assertRaises(SpineValidationError):
            codec.snapshot_size({f"k{i}": {"x": "x" * 9000} for i in range(8)})
        with self.assertRaises(SpineValidationError):
            codec.snapshot_size({f"k{i}": {} for i in range(9)})
