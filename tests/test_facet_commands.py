"""FS-07/08/12/13: public local commands, not pure fixture oracles."""

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.commands.facet_runtime import FacetCursorConfig
from spine.commands.facets import CONTRACTS
from spine.ledger import facets
from spine.ledger.work import assert_work_instance_not_stale
from tests import test_schedule_operations_command as schedule_tests
from tests.facet_storage_support import DEFINITION, NOW, all_rows


class FacetCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text()) for p in (Path(__file__).parents[1] / "contracts/schemas").glob("*.schema.json")]
        cls.registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)

    def setUp(self):
        self.fixture = schedule_tests.ScheduleOperationsCommandTests()
        self.fixture.setUp()
        self.db = self.fixture.connection
        self.context = CommandContext(ledger=self.db, facet_cursor_config=FacetCursorConfig(b"t" * 32, "ledger", "generation"))
        self.counter = 0
        self.archetype = handle(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "flight-archetype",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                "archetype_key": "flight",
                "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event", "task"]},
            },
            self.context,
        )
        self.assertTrue(self.archetype["ok"], self.archetype)

    def tearDown(self):
        self.fixture.tearDown()

    def request(self, command, **kw):
        self.counter += 1
        result = {"contract_version": CONTRACTS[command]}
        if command.rsplit(".", 1)[1] in {"create", "publish", "retire", "set", "remove", "update"}:
            result.update(command_id=f"facet-{self.counter}", actor_subject_id="owner", action_timestamp_utc=NOW)
        return {**result, **kw}

    def call(self, command, request=None, *, context=None, **kw):
        response = handle(command, request or self.request(command, **kw), context or self.context)
        self.assertTrue(response["ok"], response)
        uri = f"https://cortext.local/spine/contracts/schemas/archetype-facet-responses.schema.json#/$defs/{command}"
        Draft202012Validator({"$ref": uri}, registry=self.registry).validate(response)
        return response

    def catalog(self, key="flight", definition=None):
        schema = self.call(
            "facet_schema.create",
            owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            schema_key=key,
            definition=definition or DEFINITION,
        )
        binding = self.call(
            "item_archetype.facet_binding.set",
            item_archetype_id=self.archetype["item_archetype_id"],
            facet_key=key,
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            expected_binding_id=None,
        )
        return schema, binding

    def event(self, command="event", *, materialize=False, task=False):
        request = self.fixture.task_request(command) if task else self.fixture.event_request(command, materialize=materialize)
        request["item"]["archetype"] = {
            "item_archetype_id": self.archetype["item_archetype_id"],
            "item_archetype_revision_id": self.archetype["item_archetype_revision_id"],
            "selection_source": "operator_explicit",
            "revision_resolution": "exact",
        }
        response = handle("schedule.create", request, self.context)
        self.assertTrue(response["ok"], response)
        return response

    def update(self, item, schema, binding, value="AX123", version=None):
        if version is None:
            version = str(self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (item,)).fetchone()[0])
        return self.request(
            "item.facets.update",
            item_id=item,
            expected_item_version=version,
            changes=[
                {
                    "op": "set",
                    "facet_key": binding["facet_key"],
                    "expected_binding_id": binding["facet_binding_id"],
                    "facet_schema_revision_id": schema["facet_schema_revision_id"],
                    "values": {"flight": value},
                }
            ],
        )

    def test_local_lifecycle_and_successive_copy_forward(self):
        schema, binding = self.catalog()
        event = self.event(materialize=True)
        work = [dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        self.assertTrue(work)
        for value in ("AX123", "AX456", "AX789"):
            response = self.call("item.facets.update", self.update(event["item_id"], schema, binding, value))
            self.assertTrue(response["reconciliation_performed"])
            for row in work:
                assert_work_instance_not_stale(self.db, row["work_instance_id"])
        self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")], work)
        current = self.call("item.facets.show", item_id=event["item_id"])
        self.assertEqual(current["entries"][0]["values"], {"flight": "AX789"})
        old = self.call("item.facets.show", item_id=event["item_id"], item_version="2")
        self.assertEqual(old["entries"][0]["values"], {"flight": "AX123"})
        retired = self.call(
            "facet_schema.retire",
            facet_schema_id=schema["facet_schema_id"],
            expected_current_revision_id=schema["facet_schema_revision_id"],
        )
        self.assertTrue(retired["changed"])
        self.call("item.facets.show", item_id=event["item_id"])
        denied = handle("item.facets.update", self.update(event["item_id"], schema, binding), self.context)
        self.assertEqual(denied["error"]["code"], "facet_schema_retired")
        self.call(
            "item.facets.update", item_id=event["item_id"], expected_item_version="4", changes=[{"op": "remove", "facet_key": "flight"}]
        )
        self.assertEqual(self.call("item.facets.show", item_id=event["item_id"])["entries"], [])
        facets.verify_all(self.db)

    def test_six_writes_preview_noop_replay_and_atomic_failures(self):
        preview = replace(self.context, dry_run=True)

        def exercise(command, request):
            before = all_rows(self.db)
            result = self.call(command, request, context=preview)
            self.assertTrue(result.pop("dry_run"))
            self.assertEqual(all_rows(self.db), before)
            committed = self.call(command, request)
            expected = committed.copy()
            if command == "item.facets.update":
                expected["reconciliation_performed"] = False
            self.assertEqual(result, expected)
            rows = all_rows(self.db)
            replay = self.call(command, request)
            self.assertFalse(replay["changed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(all_rows(self.db), rows)
            replay_preview = self.call(command, request, context=preview)
            self.assertEqual({k: v for k, v in replay_preview.items() if k != "dry_run"}, replay)
            self.assertEqual(all_rows(self.db), rows)
            conflict = {**request, "action_timestamp_utc": "2035-01-02T00:00:00Z"}
            self.assertEqual(handle(command, conflict, preview)["error"]["code"], "semantic_conflict")
            self.assertEqual(all_rows(self.db), rows)
            return committed

        schema = exercise(
            "facet_schema.create",
            self.request(
                "facet_schema.create",
                owner={"owner_kind": "subject", "owner_subject_id": "owner"},
                schema_key="flight",
                definition=DEFINITION,
            ),
        )
        publish = self.request(
            "facet_schema.publish",
            facet_schema_id=schema["facet_schema_id"],
            expected_current_revision_id=schema["facet_schema_revision_id"],
            definition=DEFINITION,
        )
        self.assertFalse(exercise("facet_schema.publish", publish)["changed"])
        definition = copy.deepcopy(DEFINITION)
        definition["display_name"] = "Flight changed"
        schema = exercise("facet_schema.publish", {**publish, "command_id": "changed-publish", "definition": definition})
        binding_request = self.request(
            "item_archetype.facet_binding.set",
            item_archetype_id=self.archetype["item_archetype_id"],
            facet_key="flight",
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            expected_binding_id=None,
        )
        binding = exercise("item_archetype.facet_binding.set", binding_request)
        exercise(
            "item_archetype.facet_binding.set",
            {**binding_request, "command_id": "noop-binding", "expected_binding_id": binding["facet_binding_id"]},
        )
        event = self.event(materialize=True)
        exercise("item.facets.update", self.update(event["item_id"], schema, binding))
        exercise("item.facets.update", self.update(event["item_id"], schema, binding))
        remove = self.request(
            "item_archetype.facet_binding.remove",
            item_archetype_id=self.archetype["item_archetype_id"],
            facet_key="flight",
            expected_binding_id=binding["facet_binding_id"],
        )
        exercise("item_archetype.facet_binding.remove", remove)
        exercise("item_archetype.facet_binding.remove", {**remove, "command_id": "noop-remove", "expected_binding_id": None})
        retire = self.request(
            "facet_schema.retire",
            facet_schema_id=schema["facet_schema_id"],
            expected_current_revision_id=schema["facet_schema_revision_id"],
        )
        exercise("facet_schema.retire", retire)
        exercise("facet_schema.retire", {**retire, "command_id": "noop-retire"})

    def test_two_key_failure_and_equivalence_failure_roll_back_everything(self):
        schema, binding = self.catalog()
        event = self.event(materialize=True)
        request = self.update(event["item_id"], schema, binding)
        bad = copy.deepcopy(request)
        bad["changes"].append({**bad["changes"][0], "facet_key": "wrong_key"})
        before = all_rows(self.db)
        self.assertFalse(handle("item.facets.update", bad, self.context)["ok"])
        self.assertEqual(all_rows(self.db), before)
        from spine.ledger import facet_continuity

        original = facet_continuity.capture

        def changed(db, item_id, version):
            result = original(db, item_id, version)
            if version == 2:
                result["policies"] = []
            return result

        with patch("spine.ledger.facet_continuity.capture", changed):
            result = handle("item.facets.update", request, self.context)
        self.assertEqual(result["error"]["code"], "environment_failure")
        self.assertEqual(all_rows(self.db), before)

    def test_bound_lists_cursor_and_no_durable_reads(self):
        self.catalog("a")
        self.catalog("b")
        request = self.request("facet_schema.list", owner={"owner_kind": "subject", "owner_subject_id": "owner"}, limit="1")
        before = all_rows(self.db)
        page = self.call("facet_schema.list", request)
        self.assertTrue(page["has_more"])
        second = self.call("facet_schema.list", {**request, "cursor": page["next_cursor"]})
        self.assertFalse(second["has_more"])
        self.assertNotEqual(page["schemas"], second["schemas"])
        self.call("item_archetype.facet_binding.list", item_archetype_id=self.archetype["item_archetype_id"])
        self.call("facet_schema.show", facet_schema_id=page["schemas"][0]["facet_schema_id"])
        self.assertEqual(all_rows(self.db), before)
        missing = handle("facet_schema.list", request, replace(self.context, facet_cursor_config=None))
        self.assertEqual(missing["error"]["code"], "environment_failure")
        for token in (page["next_cursor"] + "x", "fc1.invalid.signature"):
            self.assertEqual(handle("facet_schema.list", {**request, "cursor": token}, self.context)["error"]["code"], "invalid_request")
        self.catalog("c")
        stale = handle("facet_schema.list", {**request, "cursor": page["next_cursor"]}, self.context)
        self.assertEqual(stale["error"]["code"], "stale_cursor")

    def test_wrong_concrete_type_before_values(self):
        definition = {**DEFINITION, "compatible_item_types": ["event"]}
        schema, binding = self.catalog(definition=definition)
        task = self.event(task=True)
        request = self.update(task["item_id"], schema, binding)
        result = handle("item.facets.update", request, self.context)
        self.assertEqual(result["error"]["code"], "wrong_item_type")
        self.assertEqual(result["error"]["field"], "item_id")

    def test_malformed_enums_fail_structurally_without_writes(self):
        schema, binding = self.catalog()
        event = self.event()
        update = self.update(event["item_id"], schema, binding)
        update["changes"][0]["op"] = ["set"]
        listing = self.request("facet_schema.list", owner={"owner_kind": "subject", "owner_subject_id": "owner"}, status={})
        before = all_rows(self.db)
        for command, request in (("item.facets.update", update), ("facet_schema.list", listing)):
            response = handle(command, request, self.context)
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertEqual(all_rows(self.db), before)

    def adopt(self, item, receipt_id):
        # Fixture-only provisioning of an item owner, not inferred from participants.
        with self.db.atomic_command():
            self.db.execute("INSERT INTO item_access_owners VALUES (?,?,1,'subject','owner',NULL,'owner','fixture')", (item, "own-" + item))
            self.db.execute(
                "INSERT INTO item_access_owner_revisions VALUES (?,?,1,'subject','owner',NULL,'owner','fixture',?,'owner',?)",
                (item, "own-" + item, NOW, receipt_id),
            )

    def test_typed_query_owner_isolation_and_version_binding(self):
        schema, binding = self.catalog()
        event = self.event()
        self.call("item.facets.update", self.update(event["item_id"], schema, binding))
        request = self.request(
            "item.facets.query",
            owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            field="flight",
            value="AX123",
        )
        self.assertEqual(self.call("item.facets.query", request)["items"], [])
        self.adopt(event["item_id"], schema["command_receipt_id"])
        self.assertEqual(self.call("item.facets.query", request)["items"], [{"item_id": event["item_id"], "item_version": "2"}])
        self.assertEqual(self.call("item.facets.query", {**request, "value": "ax123"})["items"], [])
        before = all_rows(self.db)
        self.call("item.facets.query", request)
        self.assertEqual(all_rows(self.db), before)

    def test_retained_entry_source_and_noop_revalidation(self):
        schema, binding = self.catalog()
        event = self.event()
        req = self.update(event["item_id"], schema, binding)
        req["changes"][0]["values"]["person"] = "owner"
        first = self.call("item.facets.update", req)
        snapshot = facets.load_snapshot(self.db, event["item_id"], 2)
        req2 = {**req, "command_id": "same-values", "expected_item_version": "2"}
        self.assertFalse(self.call("item.facets.update", req2)["changed"])
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='owner'")
        denied = handle("item.facets.update", {**req2, "command_id": "inactive-reference"}, self.context)
        self.assertEqual(denied["error"]["code"], "facet_reference_unavailable")
        self.assertTrue(self.call("item.facets.update", req)["replayed"])
        shown = self.call("item.facets.show", item_id=event["item_id"])
        self.assertEqual(shown["entries"][0]["references"][0]["status"], "inactive")
        self.assertEqual(facets.load_snapshot(self.db, event["item_id"], 2), snapshot)
        self.assertEqual(shown["entries"][0]["source_command_receipt_id"], first["command_receipt_id"])

    def test_flight_reference_query_and_explicit_schema_upgrade(self):
        from spine.ledger import LocationInput
        from spine.ledger.supporting import insert_location

        with self.db.atomic_command():
            insert_location(
                self.db, location=LocationInput(label="Departure airport", kind="place"), location_id="airport", default_created_at_utc=NOW
            )
        schema, binding = self.catalog()
        event = self.event()
        req = self.update(event["item_id"], schema, binding)
        req["changes"][0]["values"].update(airport="airport", person="owner")
        self.call("item.facets.update", req)
        self.adopt(event["item_id"], schema["command_receipt_id"])
        query = self.request(
            "item.facets.query",
            owner={"owner_kind": "subject", "owner_subject_id": "owner"},
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            field="airport",
            value="airport",
        )
        self.assertEqual(len(self.call("item.facets.query", query)["items"]), 1)
        updated = self.call(
            "facet_schema.publish",
            facet_schema_id=schema["facet_schema_id"],
            expected_current_revision_id=schema["facet_schema_revision_id"],
            definition={**DEFINITION, "display_name": "Flight details revised"},
        )
        new_binding = self.call(
            "item_archetype.facet_binding.set",
            item_archetype_id=self.archetype["item_archetype_id"],
            facet_key="flight",
            facet_schema_revision_id=updated["facet_schema_revision_id"],
            expected_binding_id=binding["facet_binding_id"],
        )
        old = self.call("item.facets.show", item_id=event["item_id"])
        self.assertEqual(old["entries"][0]["facet_schema_revision_id"], schema["facet_schema_revision_id"])
        req2 = self.update(event["item_id"], updated, new_binding)
        req2["changes"][0]["values"] = req["changes"][0]["values"]
        self.call("item.facets.update", req2)
        self.assertEqual(self.call("item.facets.query", query)["items"], [])
        self.assertEqual(
            len(self.call("item.facets.query", {**query, "facet_schema_revision_id": updated["facet_schema_revision_id"]})["items"]), 1
        )
        historical = self.call("item.facets.show", item_id=event["item_id"], item_version="2")
        self.assertEqual(historical["entries"], old["entries"])

    def test_attempt_history_and_materialization_after_multiple_edits(self):
        from spine.services.attempts import prepare_work_attempt
        from spine.services.work import start_work

        schema, binding = self.catalog()
        event = self.event(materialize=True)
        work = [dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        selected = work[0]
        start_work(self.db, work_instance_id=selected["work_instance_id"], started_at_utc=selected["eligible_at_utc"])
        gate = prepare_work_attempt(
            self.db,
            work_instance_id=selected["work_instance_id"],
            adapter_name="openclaw",
            idempotency_key="facet-attempt",
            request_envelope={"message": "Flight"},
            attempted_at_utc=selected["eligible_at_utc"],
            attempt_id="facet-attempt",
        )
        self.assertTrue(gate.may_start_external_write)
        before_work = [dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        before_attempt = [dict(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")]
        for value in ("A", "B", "C"):
            self.call("item.facets.update", self.update(event["item_id"], schema, binding, value))
            assert_work_instance_not_stale(self.db, selected["work_instance_id"])
        self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")], before_work)
        self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")], before_attempt)
        materialized = handle(
            "notification_work.materialize",
            {
                "command_id": "after-facets",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "4",
                "materialized_at_utc": "2026-08-13T12:00:00Z",
                "range_start_utc": "2026-08-14T00:00:00Z",
                "range_end_utc": "2026-08-15T00:00:00Z",
                "limit": "100",
            },
            self.context,
        )
        self.assertTrue(materialized["ok"], materialized)
        self.assertEqual(materialized["created_work_instance_ids"], [])
        self.assertEqual(materialized["cancelled_work_instance_ids"], [])
        self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")], before_work)

    def test_retry_and_terminal_work_are_retained_byte_for_byte(self):
        from spine.services.attempts import prepare_work_attempt, record_attempt_failure
        from spine.services.work import fail_work, retry_work, start_work

        schema, binding = self.catalog()
        event = self.event(materialize=True)
        work = dict(self.db.execute("SELECT * FROM work_instances ORDER BY eligible_at_utc LIMIT 1").fetchone())
        work_id, at = work["work_instance_id"], work["eligible_at_utc"]
        start_work(self.db, work_instance_id=work_id, started_at_utc=at)
        prepare_work_attempt(
            self.db,
            work_instance_id=work_id,
            adapter_name="openclaw",
            idempotency_key="retry",
            request_envelope={"message": "Flight"},
            attempted_at_utc=at,
            attempt_id="retry",
        )
        record_attempt_failure(self.db, attempt_id="retry", completed_at_utc=at, reason_code="adapter_failure")
        retry_work(self.db, work_instance_id=work_id, next_attempt_at_utc=at, updated_at_utc=at, reason_code="adapter_failure")
        for value in ("retry", "terminal"):
            if value == "terminal":
                fail_work(self.db, work_instance_id=work_id, failed_at_utc=at, reason_code="adapter_failure")
            before_work = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
            before_attempts = [tuple(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")]
            self.call("item.facets.update", self.update(event["item_id"], schema, binding, value))
            self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")], before_work)
            self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM side_effect_attempts ORDER BY attempt_id")], before_attempts)

    def test_recurring_work_keeps_original_provenance(self):
        schema, binding = self.catalog()
        request = self.fixture.task_request("recurring-facet")
        request["item"]["archetype"] = {
            "item_archetype_id": self.archetype["item_archetype_id"],
            "revision_resolution": "current",
            "selection_source": "operator_explicit",
        }
        request["materialization"] = {
            "mode": "bounded",
            "evaluated_at_utc": "2026-08-13T12:00:00Z",
            "range": {"kind": "local", "range_start_local": "2026-08-14T00:00:00", "range_end_local": "2026-08-15T00:00:00"},
            "limit": "100",
        }
        # Reuse the valid item-relative range supported by schedule authoring.
        request["materialization"] = self.fixture.materialization()
        event = handle("schedule.create", request, self.context)
        self.assertTrue(event["ok"], event)
        rows = [dict(r) for r in self.db.execute("SELECT * FROM work_instances")]
        self.assertTrue(rows)
        self.assertTrue(rows[0]["occurrence_provenance_id"])
        provenance = [dict(r) for r in self.db.execute("SELECT * FROM occurrence_provenance")]
        for value in ("A", "B"):
            self.call("item.facets.update", self.update(event["item_id"], schema, binding, value))
            for row in rows:
                assert_work_instance_not_stale(self.db, row["work_instance_id"])
        self.assertEqual([dict(r) for r in self.db.execute("SELECT * FROM occurrence_provenance")], provenance)

    def test_explicit_writer_retains_unchanged_seven_entries(self):
        schema, binding = self.catalog()
        bindings = [binding]
        for i in range(1, 8):
            bindings.append(
                self.call(
                    "item_archetype.facet_binding.set",
                    item_archetype_id=self.archetype["item_archetype_id"],
                    facet_key=f"flight{i}",
                    facet_schema_revision_id=schema["facet_schema_revision_id"],
                    expected_binding_id=None,
                )
            )
        event = self.event()
        request = self.update(event["item_id"], schema, binding)
        request["changes"] = [self.update(event["item_id"], schema, b)["changes"][0] for b in bindings]
        self.call("item.facets.update", request)
        before = facets.load_snapshot(self.db, event["item_id"], 2)
        self.call("item.facets.update", self.update(event["item_id"], schema, binding, "Changed"))
        after = facets.load_snapshot(self.db, event["item_id"], 3)
        self.assertEqual(before[1:], after[1:])
        self.assertNotEqual(before[0]["source_command_receipt_id"], after[0]["source_command_receipt_id"])

    def test_follow_source_target_edit_retains_work_source_edit_requires_reconcile(self):
        from types import SimpleNamespace

        from spine.core.errors import SpineValidationError
        from spine.ledger.temporal_bindings import active_follow_binding_current
        from tests.facet_storage_support import assign
        from tests.test_relative_temporal_bindings_command import RelativeTemporalBindingCommandTests

        schema, binding = self.catalog()
        event = self.event()
        related = RelativeTemporalBindingCommandTests._related_request(SimpleNamespace(event=event), "follow_source", with_reminder=True)
        related["created_at_utc"] = "2026-08-13T12:00:00Z"
        related["materialization"]["evaluated_at_utc"] = "2026-08-13T12:00:00Z"
        task = handle("schedule.related_task.create", related, self.context)
        self.assertTrue(task["ok"], task)
        target = task["task"]["item_id"]
        with self.db.atomic_command():
            assign(self.db, target, 1, self.archetype["item_archetype_id"])
        work_id = task["work_instance_ids"][0]
        bindings_before = [tuple(r) for r in self.db.execute("SELECT * FROM relative_temporal_binding_revisions")]
        self.call("item.facets.update", self.update(target, schema, binding))
        self.assertTrue(active_follow_binding_current(self.db, item_id=target))
        assert_work_instance_not_stale(self.db, work_id)
        self.call("item.facets.update", self.update(event["item_id"], schema, binding))
        self.assertFalse(active_follow_binding_current(self.db, item_id=target))
        with self.assertRaises(SpineValidationError):
            assert_work_instance_not_stale(self.db, work_id)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM relative_temporal_binding_revisions")], bindings_before)
        listed = handle(
            "schedule.binding.list", {"contract_version": "spine.schedule-binding-list.v1", "target_item_id": target}, self.context
        )
        self.assertTrue(listed["ok"], listed)
        reconciled = handle(
            "schedule.binding.reconcile",
            {
                "contract_version": "spine.schedule-binding-reconcile.v1",
                "command_id": "facet-source-reconcile",
                "actor_subject_id": "owner",
                "reconciled_at_utc": NOW,
                **listed["bindings"][0]["reconcile_inputs"],
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(reconciled["ok"], reconciled)
        self.assertTrue(active_follow_binding_current(self.db, item_id=target))
        assert_work_instance_not_stale(self.db, work_id)

    def test_facet_render_race_rejects_unpersisted_render_and_replay_cannot_send(self):
        from spine.core.errors import SpineValidationError
        from spine.services.attempts import prepare_work_attempt
        from spine.services.notification_rendering import resolve_notification_rendering
        from spine.services.work import start_work

        schema, binding = self.catalog()
        event = self.event(materialize=True)
        work = dict(self.db.execute("SELECT * FROM work_instances ORDER BY eligible_at_utc LIMIT 1").fetchone())
        start_work(self.db, work_instance_id=work["work_instance_id"], started_at_utc=work["eligible_at_utc"])
        render = resolve_notification_rendering(self.db, work_row=work, attempt_id="render-race", attempted_at_utc=work["eligible_at_utc"])
        self.call("item.facets.update", self.update(event["item_id"], schema, binding))
        arguments = {
            "work_instance_id": work["work_instance_id"],
            "attempt_id": "render-race",
            "adapter_name": "openclaw",
            "idempotency_key": "render-race",
            "attempted_at_utc": work["eligible_at_utc"],
            "request_envelope": {"body": render.body_text},
            "notification_rendering": render,
        }
        before = all_rows(self.db)
        with self.assertRaisesRegex(SpineValidationError, "notification_rendering_persistence_conflict"):
            prepare_work_attempt(self.db, **arguments)
        self.assertEqual(all_rows(self.db), before)
        arguments["notification_rendering"] = resolve_notification_rendering(
            self.db, work_row=work, attempt_id="render-race", attempted_at_utc=work["eligible_at_utc"]
        )
        first = prepare_work_attempt(self.db, **arguments)
        self.assertTrue(first.may_start_external_write)
        renderings = [tuple(r) for r in self.db.execute("SELECT * FROM notification_renderings")]
        self.call("item.facets.update", self.update(event["item_id"], schema, binding, "Another value"))
        replay = prepare_work_attempt(self.db, **arguments)
        self.assertFalse(replay.may_start_external_write)
        self.assertEqual(self.db.execute("SELECT count(*) FROM side_effect_attempts").fetchone()[0], 1)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM notification_renderings")], renderings)


if __name__ == "__main__":
    unittest.main()
