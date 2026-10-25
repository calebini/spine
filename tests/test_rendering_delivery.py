"""SPINE-052: real candidate ledger and deterministic attempt/adapter boundaries."""

import copy
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from spine.adapters import (
    NormalizedOpenClawResult,
    OpenClawGatewayConfig,
    OpenClawGatewaySender,
    OpenClawNotificationProcessor,
    build_openclaw_outbound_message,
)
from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.core.notification_details import decode_detailed
from spine.core.notifications import normalize_notification_policy
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, get_notification_rendering, get_work_instance
from spine.ledger.notifications import insert_notification_schedule_policy
from spine.ledger.rendering_definitions import verify_deep
from spine.ledger.work import assert_work_instance_not_stale
from spine.services.attempts import prepare_work_attempt, record_attempt_failure, record_attempt_success
from spine.services.scheduling import materialize_notification_horizon
from spine.services.work import retry_work, start_work, succeed_work
from tests import test_rendering_successor_authoring as successor
from tests.facet_storage_support import DEFINITION, NOW
from tests.openclaw_helpers import IdempotentGatewayRunner

ROOT = Path(__file__).parents[1]


class RenderingDeliveryTests(successor.RenderingSuccessorTests):
    def setUp(self):
        super().setUp()
        self.archetype = self.command(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "delivery-archetype",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.scope,
                "archetype_key": "flight",
                "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event", "task"]},
            },
        )
        self.schema_revision = self.revision["selections"][0]["facet_schema_revision_id"]
        self.binding = self.command(
            "item_archetype.facet_binding.set",
            {
                "contract_version": "spine.archetype-facet-bindings.v1",
                "command_id": "delivery-binding",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "item_archetype_id": self.archetype["item_archetype_id"],
                "facet_key": "flight",
                "facet_schema_revision_id": self.schema_revision,
                "expected_binding_id": None,
            },
        )

    def command(self, name, request):
        result = handle(name, request, self.context)
        self.assertTrue(result["ok"], result)
        return result

    def event(self, *, selected=True, materialize=True, value="AC872", title="Flight to Paris", task=False, recurrence=False):
        root = self.create()["record"] if selected else None
        request = (
            self.fixture.task_request("delivery-task") if task else self.fixture.event_request("delivery-event", materialize=materialize)
        )
        request["contract_version"] = "spine.schedule-create.v3"
        if task:
            request["materialization"] = self.fixture.materialization() if materialize else {"mode": "none"}
        if recurrence and not task:
            request["scheduled_time"]["recurrence"] = copy.deepcopy(self.fixture.task_request("unused")["scheduled_time"]["recurrence"])
            rule = request["scheduled_time"]["recurrence"]["rules"][0]
            rule["seed"] = rule["start_bound"] = "2026-08-14T10:00:00"
        request["item"]["title"] = title
        request["item"]["archetype"] = {
            "item_archetype_id": self.archetype["item_archetype_id"],
            "item_archetype_revision_id": self.archetype["item_archetype_revision_id"],
            "selection_source": "operator_explicit",
            "revision_resolution": "exact",
        }
        event = self.candidate("schedule.create", request)
        if value is not None:
            self.facet(event, {"flight": value})
        self.adopt(event["item_id"])
        grant = self.disclosure(root) if selected else None
        if selected:
            self.candidate("schedule.update", self.edit(event, self.selection(grant)))
        return event, grant

    def facet(self, event, values):
        self.counter += 1
        version = self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0]
        change = (
            {"op": "remove", "facet_key": "flight"}
            if values is None
            else {
                "op": "set",
                "facet_key": "flight",
                "expected_binding_id": self.binding["facet_binding_id"],
                "facet_schema_revision_id": self.schema_revision,
                "values": values,
            }
        )
        return self.command(
            "item.facets.update",
            {
                "contract_version": "spine.item-facets.v1",
                "command_id": f"delivery-values-{self.counter}",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "item_id": event["item_id"],
                "expected_item_version": str(version),
                "changes": [change],
            },
        )

    def work(self, event, *, start=False):
        row = self.db.execute(
            "SELECT * FROM work_instances WHERE item_id=? ORDER BY eligible_at_utc LIMIT 1", (event["item_id"],)
        ).fetchone()
        self.assertIsNotNone(row)
        if start:
            start_work(self.db, work_instance_id=row["work_instance_id"], started_at_utc=row["eligible_at_utc"])
        return get_work_instance(self.db, row["work_instance_id"])

    def message(self, work, at=None):
        return build_openclaw_outbound_message(
            self.db,
            work_row=work,
            trace_id="test",
            causation_id="ROOT:test",
            created_at_utc=at or work["eligible_at_utc"],
        )

    def prepare(self, message):
        return prepare_work_attempt(
            self.db,
            attempt_id=message.attempt_id,
            work_instance_id=message.delivery_id,
            adapter_name="openclaw",
            idempotency_key=message.dedupe_key,
            request_envelope=message.request_envelope(),
            attempted_at_utc=message.created_at_utc,
            notification_rendering=message.notification_rendering,
        )

    def revoke(self, grant):
        return self.call(
            "notification_rendering_disclosure.revoke",
            disclosure_authorization_id=grant["disclosure_authorization_id"],
            expected_scope_hash=grant["scope_hash"],
            reason_code="withdrawn",
        )

    def configure_fields(self, event, fields, *, permitted=()):
        revision = copy.deepcopy(self.revision)
        revision["selections"] = [
            revision["selections"][0]
            | {
                "selection_key": key,
                "field_key": key,
                "projection": "location_label" if key == "airport" else "value",
                "label": key.title(),
            }
            for key in fields
        ]
        root = self.call("notification_rendering_definition.create", owner=self.scope, definition_key="multiple", revision=revision)[
            "record"
        ]
        scope = {
            "item_owner": self.scope,
            "definition": {k: root[k] for k in ("notification_rendering_definition_id", "notification_rendering_definition_revision_id")},
            "approved_selection_keys": sorted(fields),
            "use_scope": {"kind": "direct_policy"},
            "permitted_location_ids": list(permitted),
            "destination": {
                "recipient": {"kind": "subject", "subject_id": "owner"},
                "delivery_target_id": "whatsapp-owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "destination_source": "delivery_target",
                "target_ref": "owner@example",
            },
        }
        grant = self.call("notification_rendering_disclosure.provision", scope=scope)["record"]
        selection = self.selection(grant) | {"effective_selection_keys": sorted(fields)}
        self.candidate("schedule.update", self.edit(event, selection, "select-fields"))
        return grant

    def test_typed_scalar_order_and_approved_location_label_only(self):
        from spine.ledger import LocationInput
        from spine.ledger.supporting import insert_location

        event, _ = self.event(selected=False)
        with self.db.atomic_command():
            insert_location(
                self.db,
                location=LocationInput(label="  Pearson   Airport  ", kind="place", address_text="SECRET address"),
                location_id="airport",
                default_created_at_utc=NOW,
            )
        self.facet(
            event, {"flight": " AC872 ", "confirmed": False, "seats": "-2", "day": "2036-02-29", "class": "economy", "airport": "airport"}
        )
        self.configure_fields(event, ["flight", "confirmed", "seats", "day", "class", "airport"], permitted=["airport"])
        message = self.message(self.work(event, start=True))
        self.assertTrue(
            message.body_text.endswith(
                " · Flight: AC872 · Confirmed: false · Seats: -2 · Day: 2036-02-29 · Class: economy · Airport: Pearson Airport"
            )
        )
        self.assertNotIn("SECRET", json.dumps(message.notification_rendering.as_view()))
        self.assertEqual(message.notification_rendering.details["selections"][-1]["source"]["location_id"], "airport")
        self.prepare(message)
        verify_deep(self.db)

    def test_unapproved_location_not_looked_up_or_retained_in_evidence(self):
        from spine.ledger import LocationInput
        from spine.ledger.supporting import insert_location

        event, _ = self.event(selected=False)
        with self.db.atomic_command():
            insert_location(
                self.db,
                location=LocationInput(label="Private airport", kind="place"),
                location_id="private-airport",
                default_created_at_utc=NOW,
            )
        self.facet(event, {"flight": "AC872", "airport": "private-airport"})
        self.configure_fields(event, ["airport"])
        queries = []
        self.db.set_trace_callback(queries.append)
        try:
            message = self.message(self.work(event, start=True))
        finally:
            self.db.set_trace_callback(None)
        self.assertEqual(
            message.notification_rendering.details["selections"], [{"selection_key": "airport", "outcome": "reference_unavailable"}]
        )
        self.assertNotIn("private-airport", json.dumps(message.notification_rendering.details))
        self.assertNotIn("Private airport", message.body_text)
        self.assertFalse(any("SELECT label FROM locations" in q for q in queries))
        self.prepare(message)

    def test_owner_and_route_changes_are_rechecked_at_attempt_fence(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        prepared = self.message(work)
        # There is no deployed transfer command. Simulate a future writer's
        # committed owner projection in this disposable ledger only.
        self.command(
            "subject.upsert",
            {
                "command_id": "other-owner",
                "actor_subject_id": "owner",
                "subject_id": "other",
                "subject_kind": "person",
                "display_name": "Other",
                "updated_at_utc": NOW,
            },
        )
        with self.db.atomic_command():
            self.db.execute("UPDATE item_access_owners SET owner_subject_id='other' WHERE item_id=?", (event["item_id"],))
        with self.assertRaises(SpineValidationError):
            self.prepare(prepared)
        fresh = self.message(work)
        self.assertEqual(fresh.notification_rendering.details["authorization_state"], "scope_mismatch")
        self.assertNotIn("AC872", fresh.body_text)
        rejected = handle(
            "delivery_target.upsert",
            {
                "command_id": "change-route",
                "actor_subject_id": "owner",
                "delivery_target_id": "whatsapp-owner",
                "owner_kind": "subject",
                "owner_subject_id": "owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "different@example",
                "updated_at_utc": NOW,
            },
            self.context,
        )
        self.assertEqual(rejected["error"]["code"], "semantic_conflict")
        # The current public route command forbids this referenced-route edit.
        # Inject drift to verify the independent attempt fence as well.
        with self.db.atomic_command():
            self.db.execute("UPDATE delivery_targets SET target_ref='different@example' WHERE delivery_target_id='whatsapp-owner'")
        with self.assertRaises(SpineValidationError):
            self.prepare(fresh)
        final = self.message(work)
        self.assertEqual(final.target_ref, "different@example")
        self.assertNotIn("AC872", final.body_text)
        self.prepare(final)

    def test_optional_field_missing_and_explicit_schema_upgrade_use_current_snapshot(self):
        event, _ = self.event(selected=False)
        self.configure_fields(event, ["seats"])
        work = self.work(event, start=True)
        self.assertEqual(self.message(work).notification_rendering.details["selections"][0]["outcome"], "field_missing")
        self.upgrade_schema()
        self.facet(event, {"flight": "AC999", "seats": "3"})
        message = self.message(work)
        self.assertEqual(message.notification_rendering.details["selections"][0]["outcome"], "schema_mismatch")
        self.assertNotIn("AC999", json.dumps(message.notification_rendering.details))
        self.prepare(message)

    def upgrade_schema(self):
        root = self.db.execute(
            "SELECT facet_schema_id FROM facet_schema_revisions WHERE facet_schema_revision_id=?", (self.schema_revision,)
        ).fetchone()[0]
        definition = copy.deepcopy(DEFINITION)
        definition["fields"][0]["max_length"] = "1024"
        changed = self.command(
            "facet_schema.publish",
            {
                "contract_version": "spine.facet-schemas.v1",
                "command_id": "upgrade-schema",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "facet_schema_id": root,
                "expected_current_revision_id": self.schema_revision,
                "definition": definition,
            },
        )
        self.schema_revision = changed["facet_schema_revision_id"]
        self.binding = self.command(
            "item_archetype.facet_binding.set",
            {
                "contract_version": "spine.archetype-facet-bindings.v1",
                "command_id": "upgrade-binding",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "item_archetype_id": self.archetype["item_archetype_id"],
                "facet_key": "flight",
                "facet_schema_revision_id": self.schema_revision,
                "expected_binding_id": self.binding["facet_binding_id"],
            },
        )
        self.revision["selections"][0]["facet_schema_revision_id"] = self.schema_revision

    def test_value_size_boundary_omits_whole_value_and_removed_facet_has_no_history_fallback(self):
        self.upgrade_schema()
        event, _ = self.event(value="x" * 120)
        work = self.work(event, start=True)
        self.assertTrue(self.message(work).body_text.endswith("x" * 120))
        self.facet(event, {"flight": "PRIVATE" + "x" * 120})
        message = self.message(work)
        self.assertEqual(message.notification_rendering.details["selections"][0]["outcome"], "value_too_long")
        self.assertNotIn("PRIVATE", json.dumps(message.notification_rendering.details))
        self.facet(event, None)
        self.assertEqual(self.message(work).notification_rendering.details["selections"][0]["outcome"], "facet_missing")
        self.prepare(self.message(work))

    def test_recurring_delivery_uses_series_facets_and_occurrence_time(self):
        event, _ = self.event(recurrence=True)
        before = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        self.facet(event, {"flight": "AC-series"})
        self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")])
        message = self.message(self.work(event, start=True))
        self.assertIn("AC-series", message.body_text)
        self.assertIn("occurrence_provenance_id", message.notification_rendering.base.source_input)
        self.prepare(message)

    def test_evidence_capacity_failure_stops_adapter_without_ordinary_fallback(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        sent = []
        envelope = SimpleNamespace(
            trace_id="test",
            causation_id="ROOT:test",
            actual_start_ts=datetime.fromisoformat(work["eligible_at_utc"].replace("Z", "+00:00")),
        )
        processor = OpenClawNotificationProcessor(sender=lambda msg: sent.append(msg))
        with patch("spine.core.notification_details.canonical_json_bytes", return_value=b"x" * 32769):
            result = processor(self.db, work, envelope)
        self.assertEqual(result.status, "failed")
        self.assertEqual(sent, [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_tickerd_selected_work_survives_edit_before_processing(self):
        from dataclasses import replace

        from spine.adapters import SpineTickerdWorkAdapter
        from tests.test_tickerd_adapter import cycle_envelope

        event, _ = self.event()
        work = self.work(event)
        now = datetime.fromisoformat(work["eligible_at_utc"].replace("Z", "+00:00"))
        envelope = replace(cycle_envelope(), actual_start_ts=now, scheduled_tick_ts=now)
        sent = []
        adapter = SpineTickerdWorkAdapter(
            self.db,
            runtime_mode="active",
            processor=OpenClawNotificationProcessor(
                sender=lambda msg: sent.append(msg) or NormalizedOpenClawResult.delivered(provider_ref="synthetic")
            ),
        )
        acquired = adapter.list_work_items(envelope, limit=1)[0]
        self.facet(event, {"flight": "AC-current"})
        outcome = adapter.process_work_item(acquired, envelope, side_effects_allowed=True)
        self.assertEqual(outcome.status.value, "processed")
        self.assertEqual(len(sent), 1)
        self.assertIn("AC-current", sent[0].body_text)
        self.assertEqual(get_work_instance(self.db, acquired.item_id)["status"], "succeeded")

    def test_real_sqlite_attempt_writer_excludes_concurrent_revocation(self):
        from spine.commands import CommandContext
        from spine.commands.rendering_catalog import execute
        from spine.services import attempts

        event, grant = self.event()
        work = self.work(event, start=True)
        with tempfile.TemporaryDirectory() as directory:
            disk = connect(Path(directory) / "ledger.sqlite")
            self.db.backup(disk)
            # backup copies schema/data, not connection-local tracking.
            disk.enable_renderings()
            second = connect(Path(directory) / "ledger.sqlite", busy_timeout_ms=1)
            self.addCleanup(second.close)
            original_db = self.db
            self.db = disk
            try:
                message = self.message(work)
                request = self.request(
                    "notification_rendering_disclosure.revoke",
                    disclosure_authorization_id=grant["disclosure_authorization_id"],
                    expected_scope_hash=grant["scope_hash"],
                    reason_code="race",
                )
                original = attempts.insert_notification_rendering
                outcomes = []

                def interleave(*args, **kwargs):
                    outcomes.append(execute("notification_rendering_disclosure.revoke", request, CommandContext(ledger=second), now=NOW))
                    original(*args, **kwargs)

                with patch.object(attempts, "insert_notification_rendering", side_effect=interleave):
                    self.prepare(message)
                self.assertFalse(outcomes[0]["ok"])
                self.assertEqual(outcomes[0]["error"]["code"], "environment_failure")
                revoked = execute("notification_rendering_disclosure.revoke", request, CommandContext(ledger=second), now=NOW)
                self.assertTrue(revoked["ok"], revoked)
                self.assertEqual(get_notification_rendering(disk, attempt_id=message.attempt_id)["body_text"], message.body_text)
                self.assertFalse(self.prepare(self.message(work)).may_start_external_write)
            finally:
                second.close()
                disk.close()
                self.db = original_db

    def test_unregistered_corrupt_evidence_writer_is_caught_by_commit_finalizer(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        message = self.message(work)

        def raw_writer(db, *, rendering, **unused):
            values = rendering.as_persistence() | {"body_text": "wrong"}
            if values["delta_seconds"] is not None:
                values["delta_seconds"] = int(values["delta_seconds"])
            columns = ",".join(values)
            placeholders = ",".join("?" for _ in values)
            db.execute(f"INSERT INTO notification_renderings ({columns}) VALUES ({placeholders})", tuple(values.values()))

        with (
            patch("spine.services.attempts.insert_notification_rendering", side_effect=raw_writer),
            self.assertRaises(SpineValidationError),
        ):
            self.prepare(message)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        self.assertIsNone(get_notification_rendering(self.db, attempt_id=message.attempt_id))

    def test_follow_source_task_uses_own_facets_and_blocks_stale_source(self):
        from tests.test_relative_temporal_bindings_command import RelativeTemporalBindingCommandTests

        source, _ = self.event(selected=False)
        helper = RelativeTemporalBindingCommandTests()
        helper.event = source
        request = helper._related_request("follow_source", with_reminder=True)
        request["created_at_utc"] = "2026-08-13T12:00:00Z"
        request["source"]["target_version"] = "2"
        request["materialization"]["evaluated_at_utc"] = "2026-08-13T12:00:00Z"
        created = self.command("schedule.related_task.create", request)
        task = created["task"]
        self.command(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "task-archetype",
                "actor_subject_id": "owner",
                "item_id": task["item_id"],
                "target_version": "1",
                "updated_at_utc": NOW,
                "patch": {
                    "archetype": {
                        "action": "select",
                        "item_archetype_id": self.archetype["item_archetype_id"],
                        "item_archetype_revision_id": self.archetype["item_archetype_revision_id"],
                        "selection_source": "operator_explicit",
                        "revision_resolution": "exact",
                    }
                },
                "materialization": {"mode": "none"},
            },
        )
        self.facet(task, {"flight": "TASK-own"})
        self.adopt(task["item_id"])
        self.revision["compatible_item_types"] = ["event", "task"]
        self.configure_fields(task, ["flight"])
        work = self.work(task, start=True)
        message = self.message(work)
        self.assertIn("TASK-own", message.body_text)
        self.assertNotIn("AC872", message.body_text)
        self.assertIn("temporal_binding_revision_id", message.notification_rendering.base.source_input)
        self.command(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "move-source",
                "actor_subject_id": "owner",
                "item_id": source["item_id"],
                "target_version": "2",
                "updated_at_utc": NOW,
                "patch": {
                    "scheduled_time": {
                        "time_basis": "local_instant",
                        "local_date": "2026-08-15",
                        "local_time": "10:00:00",
                        "timezone": "America/Toronto",
                        "timezone_database_version": {
                            "kind": "explicit",
                            "version": system_timezone_database_version(),
                        },
                    }
                },
                "materialization": {"mode": "none"},
            },
        )
        with self.assertRaises(SpineValidationError):
            self.prepare(message)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_scheduler_can_start_ordinary_between_setup_steps_but_exclusion_orders_detail(self):
        # No worker/materializer is run during the first item's setup. That is
        # this fixture's explicit operational exclusion, not an item hold.
        event, _ = self.event(materialize=False)
        evaluated = "2026-08-14T11:55:00Z"
        result = materialize_notification_horizon(self.db, evaluated_at_utc=evaluated, horizon_seconds=3600, max_items=100)
        self.assertEqual(result.failures, ())
        self.assertTrue(self.message(self.work(event, start=True)).body_text.endswith(" · Flight: AC872"))
        # A second item is committed ordinary with no work. Allow an automatic
        # scheduler/attempt before ownership adoption/presentation selection.
        root = self.create("second")["record"]
        request = self.fixture.event_request("interleaved", materialize=False) | {"contract_version": "spine.schedule-create.v3"}
        ordinary = self.candidate("schedule.create", request)
        cycle = materialize_notification_horizon(self.db, evaluated_at_utc=evaluated, horizon_seconds=3600, max_items=100)
        self.assertEqual(cycle.failures, ())
        work = self.work(ordinary, start=True)
        message = self.message(work)
        self.prepare(message)
        self.assertFalse(hasattr(message.notification_rendering, "details"))
        self.adopt(ordinary["item_id"])
        grant = self.disclosure(root)
        self.candidate("schedule.update", self.edit(ordinary, self.selection(grant), "late-setup"))
        self.assertEqual(self.message(work).notification_rendering, message.notification_rendering)
        before = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
        materialize_notification_horizon(self.db, evaluated_at_utc=evaluated, horizon_seconds=3600, max_items=100)
        self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")])

    def test_due_within_grace_setup_interleavings_failure_and_expiry(self):
        for mode in ("without_exclusion", "through_explicit_materialization", "expired"):
            with self.subTest(mode=mode):
                request = self.fixture.event_request("due-" + mode, materialize=False)
                request["contract_version"] = "spine.schedule-create.v3"
                request["created_at_utc"] = "2026-08-14T12:05:00Z"
                request["notification_plan"]["custom_additions"][0].update(
                    schedule={
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-7200",
                        },
                    },
                    late_handling={"kind": "deliver_within", "grace_seconds": "600"},
                )
                event = self.candidate("schedule.create", request)
                root = self.create(mode)["record"]
                if mode == "without_exclusion":
                    # Opportunity is already due, but still inside its original
                    # grace. No item hold is implied by materialization=none.
                    result = materialize_notification_horizon(
                        self.db,
                        evaluated_at_utc="2026-08-14T12:05:00Z",
                        horizon_seconds=3600,
                        max_items=100,
                    )
                    self.assertEqual(result.failures, ())
                    work = self.work(event, start=True)
                    ordinary = self.message(work, "2026-08-14T12:05:00Z")
                    self.prepare(ordinary)
                    self.assertFalse(hasattr(ordinary.notification_rendering, "details"))
                else:
                    # Operational exclusion is explicit in this deterministic
                    # fixture: no scheduler/worker call before setup completes.
                    self.assertEqual(
                        self.db.execute(
                            "SELECT COUNT(*) FROM work_instances WHERE item_id=?",
                            (event["item_id"],),
                        ).fetchone()[0],
                        0,
                    )
                self.adopt(event["item_id"])
                grant = self.disclosure(root)
                invalid = self.edit(event, self.selection(grant), "failed-" + mode)
                invalid["patch"]["policy_presentations"][0]["selection"]["authorization"]["disclosure_authorization_id"] = "absent"
                failed = __import__("spine.commands.rendering_candidate", fromlist=["execute"]).execute(
                    "schedule.update",
                    invalid,
                    self.context,
                    now=NOW,
                )
                self.assertFalse(failed["ok"])
                # Failed setup is not a rollback of separately committed creation
                # or ownership adoption, and must not fabricate work.
                self.assertEqual(
                    self.db.execute(
                        "SELECT current_version FROM coordination_items WHERE item_id=?",
                        (event["item_id"],),
                    ).fetchone()[0],
                    1,
                )
                self.assertIsNotNone(
                    self.db.execute(
                        "SELECT 1 FROM item_access_owners WHERE item_id=?",
                        (event["item_id"],),
                    ).fetchone()
                )
                self.candidate("schedule.update", self.edit(event, self.selection(grant), "finish-" + mode))
                if mode == "through_explicit_materialization":
                    self.command(
                        "notification_work.materialize",
                        {
                            "command_id": "explicit-due",
                            "actor_subject_id": "owner",
                            "item_id": event["item_id"],
                            "target_version": "2",
                            "materialized_at_utc": "2026-08-14T12:05:00Z",
                            "range_start_utc": "2026-08-14T11:55:00Z",
                            "range_end_utc": "2026-08-14T14:00:00Z",
                            "limit": "100",
                        },
                    )
                    work = self.work(event, start=True)
                    detailed = self.message(work, "2026-08-14T12:05:00Z")
                    self.assertTrue(hasattr(detailed.notification_rendering, "details"))
                    self.prepare(detailed)
                evaluated = "2026-08-14T12:11:00Z" if mode == "expired" else "2026-08-14T12:05:00Z"
                before = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
                result = materialize_notification_horizon(self.db, evaluated_at_utc=evaluated, horizon_seconds=3600, max_items=100)
                self.assertEqual(result.failures, ())
                self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")])
                if mode == "without_exclusion":
                    self.assertEqual(self.message(work, evaluated).body_text, ordinary.body_text)
                if mode == "expired":
                    self.assertEqual(
                        self.db.execute(
                            "SELECT COUNT(*) FROM work_instances WHERE item_id=?",
                            (event["item_id"],),
                        ).fetchone()[0],
                        0,
                    )

    def test_v2_body_current_descendant_one_atomic_attempt_and_closed_schema(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        message = self.message(work)
        rendering = message.notification_rendering
        self.assertTrue(message.body_text.endswith(" · Flight: AC872"))
        self.assertNotEqual(rendering.details["policy_id"], work["notification_policy_id"])
        self.assertEqual(rendering.details["policy_version"], "3")
        gate = self.prepare(message)
        self.assertTrue(gate.may_start_external_write)
        stored = get_notification_rendering(self.db, attempt_id=message.attempt_id)
        self.assertEqual(stored, rendering.as_view())
        uri = "https://cortext.local/spine/contracts/schemas/notification-rendering-v2.schema.json"
        Draft202012Validator({"$ref": uri}, registry=self.registry).validate(stored)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 1)
        verify_deep(self.db)

    def test_precomputed_v2_reference_vectors_decode_byte_identically(self):
        for name in ("included", "revoked", "empty_subset", "overflow"):
            value = json.loads((ROOT / f"tests/fixtures/notification_rendering_integration/rendering_{name}.json").read_text())
            with self.subTest(name=name):
                self.assertEqual(decode_detailed(value).as_view(), value)
        value["details"]["content_hash"] = "0" * 64
        with self.assertRaises(SpineValidationError):
            decode_detailed(value)

    def test_unselected_v1_and_transport_facts_remain_identical(self):
        event, _ = self.event(selected=False)
        work = self.work(event, start=True)
        message = self.message(work)
        with patch.object(type(self.db), "_renderings_enabled", False, create=True):
            # Instance flag takes precedence; avoid touching actual data/schema.
            enabled = self.db._renderings_enabled
            self.db._renderings_enabled = False
            try:
                before = self.message(work)
            finally:
                self.db._renderings_enabled = enabled
        self.assertEqual(before.request_envelope(), message.request_envelope())
        self.assertEqual(before.notification_rendering, message.notification_rendering)
        self.prepare(message)
        row = self.db.execute("SELECT * FROM notification_renderings").fetchone()
        self.assertEqual(row["rendering_contract"], "spine.notification-rendering.v1")
        self.assertIsNone(row["details_evidence_json"])

    def test_revocation_omits_without_any_facet_or_location_reads(self):
        event, grant = self.event()
        work = self.work(event, start=True)
        self.revoke(grant)
        queries = []
        self.db.set_trace_callback(queries.append)
        try:
            message = self.message(work)
        finally:
            self.db.set_trace_callback(None)
        details = message.notification_rendering.details
        self.assertEqual(details["authorization_state"], "revoked")
        self.assertEqual(details["selections"], [{"selection_key": "flight", "outcome": "disclosure_unavailable"}])
        self.assertFalse(any("item_facet_entries" in q or "item_facet_references" in q for q in queries))
        self.assertNotIn("AC872", json.dumps(details))
        self.assertEqual(message.body_text, message.notification_rendering.base.body_text)
        self.prepare(message)

    def test_prepared_revocation_race_fails_then_fresh_attempt_omits(self):
        event, grant = self.event()
        work = self.work(event, start=True)
        prepared = self.message(work)
        self.revoke(grant)
        with self.assertRaisesRegex(SpineValidationError, "changed before"):
            self.prepare(prepared)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        fresh = self.message(work)
        self.prepare(fresh)
        self.assertNotIn("AC872", fresh.body_text)

    def test_started_replay_survives_edits_revocation_and_new_clock(self):
        event, grant = self.event()
        work = self.work(event, start=True)
        message = self.message(work)
        self.prepare(message)
        self.facet(event, {"flight": "AX999"})
        self.revoke(grant)
        rebuilt = self.message(work, at="2026-08-14T12:05:00Z")
        self.assertEqual(rebuilt.notification_rendering.as_view(), message.notification_rendering.as_view())
        # Attempt envelope time must remain stored too, not the new caller clock.
        self.assertEqual(rebuilt.created_at_utc, message.created_at_utc)
        self.assertFalse(self.prepare(rebuilt).may_start_external_write)

    def test_shared_intent_siblings_keep_distinct_presentations_after_facet_copy(self):
        event, _ = self.event(selected=False, materialize=False)
        root = self.create()["record"]
        grant = self.disclosure(root)
        siblings = []
        with self.db.atomic_command():
            for offset in ("-3600", "-1800"):
                policy = normalize_notification_policy(
                    {
                        "authoring_contract": "spine.notification-schedule-authoring.v1",
                        "target": {"anchor_role": "event_start", "application_scope": "item"},
                        "schedule": {
                            "kind": "once",
                            "at": {
                                "kind": "target_offset",
                                "offset_basis": "elapsed",
                                "offset_seconds": offset,
                            },
                        },
                        "late_handling": {"kind": "skip"},
                    },
                    item_id=event["item_id"],
                    item_version="2",
                    command_id="shared-intent-fixture",
                    created_at_utc=NOW,
                    recipient_kind="subject",
                    recipient_id="owner",
                    channel="whatsapp",
                    delivery_target_id="whatsapp-owner",
                )
                insert_notification_schedule_policy(self.db, normalized=policy)
                siblings.append(policy.value)
        self.assertEqual(siblings[0]["notification_intent_id"], siblings[1]["notification_intent_id"])
        request = self.edit(event, self.selection(grant), "one-sibling")
        request["patch"]["policy_presentations"][0]["notification_policy_id"] = siblings[0]["notification_policy_id"]
        self.candidate("schedule.update", request)
        self.facet(event, {"flight": "AC-current"})
        result = materialize_notification_horizon(
            self.db,
            evaluated_at_utc="2026-08-14T11:55:00Z",
            horizon_seconds=14400,
            max_items=100,
        )
        self.assertEqual(result.failures, ())
        rows = self.db.execute(
            "SELECT * FROM work_instances WHERE item_id=? AND notification_intent_id=? ORDER BY eligible_at_utc",
            (event["item_id"], siblings[0]["notification_intent_id"]),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        for index, row in enumerate(rows):
            start_work(self.db, work_instance_id=row["work_instance_id"], started_at_utc=row["eligible_at_utc"])
            message = self.message(get_work_instance(self.db, row["work_instance_id"]))
            self.assertEqual(hasattr(message.notification_rendering, "details"), index == 0)
            self.assertEqual("AC-current" in message.body_text, index == 0)
            self.prepare(message)
        verify_deep(self.db)

    def test_gateway_timeout_retry_keeps_one_provider_delivery_with_current_details(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        gateway = IdempotentGatewayRunner(timeout_after_first_delivery=True)
        transport = OpenClawGatewaySender(OpenClawGatewayConfig(), command_runner=gateway)
        sent = []

        def sender(message):
            stored = get_notification_rendering(self.db, attempt_id=message.attempt_id)
            self.assertEqual(stored["body_text"], message.body_text)
            sent.append(message)
            return transport(message)

        processor = OpenClawNotificationProcessor(sender=sender)
        at = work["eligible_at_utc"]
        envelope = SimpleNamespace(
            trace_id="test", causation_id="ROOT:test", actual_start_ts=datetime.fromisoformat(at.replace("Z", "+00:00"))
        )
        first = processor(self.db, work, envelope)
        self.assertEqual(first.status, "retry")
        retry_work(
            self.db,
            work_instance_id=work["work_instance_id"],
            next_attempt_at_utc=first.next_attempt_at_utc,
            updated_at_utc=at,
            reason_code=first.reason_code,
        )
        self.facet(event, {"flight": "AC-new"})
        start_work(self.db, work_instance_id=work["work_instance_id"], started_at_utc=first.next_attempt_at_utc)
        envelope.actual_start_ts = datetime.fromisoformat(first.next_attempt_at_utc.replace("Z", "+00:00"))
        retry = get_work_instance(self.db, work["work_instance_id"])
        self.assertEqual(processor(self.db, retry, envelope).status, "succeeded")
        self.assertEqual(processor(self.db, retry, envelope).reason_code, "side_effect_attempt_replay_suppressed")
        self.assertEqual(len(sent), 2)
        self.assertIn("AC872", sent[0].body_text)
        self.assertIn("AC-new", sent[1].body_text)
        self.assertNotEqual(sent[0].attempt_id, sent[1].attempt_id)
        self.assertEqual(sent[0].provider_idempotency_key, sent[1].provider_idempotency_key)
        self.assertEqual(len(gateway.visible_deliveries), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 2)

    def test_new_retry_observes_current_values_preserving_provider_identity(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        first = self.message(work)
        self.prepare(first)
        record_attempt_failure(self.db, attempt_id=first.attempt_id, completed_at_utc=first.created_at_utc, reason_code="uncertain")
        at = (datetime.fromisoformat(first.created_at_utc.replace("Z", "+00:00")) + timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
        retry_work(
            self.db,
            work_instance_id=work["work_instance_id"],
            next_attempt_at_utc=at,
            updated_at_utc=first.created_at_utc,
            reason_code="uncertain",
        )
        self.facet(event, {"flight": "AX999"})
        start_work(self.db, work_instance_id=work["work_instance_id"], started_at_utc=at)
        second = self.message(get_work_instance(self.db, work["work_instance_id"]), at=at)
        self.prepare(second)
        self.assertIn("AX999", second.body_text)
        self.assertIn("AC872", get_notification_rendering(self.db, attempt_id=first.attempt_id)["body_text"])
        self.assertEqual(first.provider_idempotency_key, second.provider_idempotency_key)
        self.assertNotEqual(first.attempt_id, second.attempt_id)

    def test_facet_edit_race_rejected_without_residue_then_current_body(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        prepared = self.message(work)
        self.facet(event, {"flight": "AX999"})
        with self.assertRaises(SpineValidationError):
            self.prepare(prepared)
        self.assertIsNone(get_notification_rendering(self.db, attempt_id=prepared.attempt_id))
        self.prepare(self.message(work))

    def test_retired_definition_and_binding_do_not_reinterpret_snapshot(self):
        event, grant = self.event()
        self.call(
            "notification_rendering_definition.retire",
            notification_rendering_definition_id=grant["scope"]["definition"]["notification_rendering_definition_id"],
            expected_current_revision_id=grant["scope"]["definition"]["notification_rendering_definition_revision_id"],
            reason_code="retired",
        )
        self.command(
            "item_archetype.facet_binding.remove",
            {
                "contract_version": "spine.archetype-facet-bindings.v1",
                "command_id": "remove-binding",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "item_archetype_id": self.archetype["item_archetype_id"],
                "facet_key": "flight",
                "expected_binding_id": self.binding["facet_binding_id"],
            },
        )
        message = self.message(self.work(event, start=True))
        self.assertIn("AC872", message.body_text)
        self.prepare(message)

    def test_absent_removed_empty_and_invalid_text_omit_without_private_evidence(self):
        event, grant = self.event(value=None)
        work = self.work(event, start=True)
        self.assertEqual(self.message(work).notification_rendering.details["selections"][0]["outcome"], "facet_missing")
        self.facet(event, {"flight": "x\u200bsecret"})
        message = self.message(work)
        self.assertEqual(message.notification_rendering.details["selections"][0]["outcome"], "invalid_text")
        self.assertNotIn("secret", json.dumps(message.notification_rendering.details))
        empty = self.selection(grant) | {"effective_selection_keys": []}
        self.candidate("schedule.update", self.edit(event, empty, "empty-subset"))
        message = self.message(work)
        self.assertEqual(message.notification_rendering.details["selections"], [{"selection_key": "flight", "outcome": "not_selected"}])
        self.prepare(message)

    def test_suffix_overflow_discards_values_and_sources_not_selected_fact(self):
        event, _ = self.event(title="T" * 1000)
        message = self.message(self.work(event, start=True))
        details = message.notification_rendering.details
        self.assertEqual(details["outcome"], "suffix_overflow")
        self.assertEqual(details["selections"], [{"selection_key": "flight", "outcome": "suffix_overflow"}])
        self.assertNotIn("AC872", json.dumps(details))
        self.prepare(message)

    def test_rendering_insert_and_commit_faults_never_invoke_adapter(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        envelope = SimpleNamespace(
            trace_id="test",
            causation_id="ROOT:test",
            actual_start_ts=datetime.fromisoformat(work["eligible_at_utc"].replace("Z", "+00:00")),
        )
        sender = []
        processor = OpenClawNotificationProcessor(
            sender=lambda msg: sender.append(msg) or NormalizedOpenClawResult.delivered(provider_ref="test")
        )
        original = __import__("spine.services.attempts", fromlist=["insert_notification_rendering"]).insert_notification_rendering

        def fault(*args, **kw):
            original(*args, **kw)
            raise RuntimeError("interrupted after insert")

        with patch("spine.services.attempts.insert_notification_rendering", side_effect=fault), self.assertRaises(RuntimeError):
            processor(self.db, work, envelope)
        self.assertEqual(sender, [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notification_renderings").fetchone()[0], 0)
        with (
            patch("spine.ledger.rendering_definitions.finalize", side_effect=RuntimeError("commit validation interrupted")),
            self.assertRaises(RuntimeError),
        ):
            processor(self.db, work, envelope)
        self.assertEqual(sender, [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
        self.assertEqual(processor(self.db, work, envelope).status, "succeeded")
        self.assertEqual(len(sender), 1)
        self.assertEqual(processor(self.db, work, envelope).reason_code, "side_effect_attempt_replay_suppressed")
        self.assertEqual(len(sender), 1)

    def test_work_state_matrix_retains_complete_rows_after_facet_and_presentation_edits(self):
        event, grant = self.event()
        work = self.work(event)
        for state in ("eligible", "in_progress", "retry", "started", "terminal"):
            with self.subTest(state=state):
                if state == "in_progress":
                    start_work(self.db, work_instance_id=work["work_instance_id"], started_at_utc=work["eligible_at_utc"])
                elif state == "retry":
                    retry_work(
                        self.db,
                        work_instance_id=work["work_instance_id"],
                        next_attempt_at_utc=work["eligible_at_utc"],
                        updated_at_utc=work["eligible_at_utc"],
                        reason_code="retry",
                    )
                elif state == "started":
                    start_work(self.db, work_instance_id=work["work_instance_id"], started_at_utc=work["eligible_at_utc"])
                    message = self.message(get_work_instance(self.db, work["work_instance_id"]))
                    self.prepare(message)
                elif state == "terminal":
                    record_attempt_success(self.db, attempt_id=message.attempt_id, completed_at_utc=message.created_at_utc)
                    succeed_work(self.db, work_instance_id=work["work_instance_id"], succeeded_at_utc=message.created_at_utc)
                before = [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")]
                self.facet(event, {"flight": "AX" + state})
                subset = self.selection(grant) | {
                    "effective_selection_keys": [] if state in {"eligible", "retry", "terminal"} else ["flight"]
                }
                self.candidate("schedule.update", self.edit(event, subset, "state-" + state))
                self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM work_instances ORDER BY work_instance_id")])
                assert_work_instance_not_stale(self.db, work["work_instance_id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 1)

    def test_absent_work_is_not_materialized_by_setup_and_stale_work_is_not_rescued(self):
        event, _ = self.event(materialize=False)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 0)
        result = self.command(
            "notification_work.materialize",
            {
                "command_id": "materialize-after-setup",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "3",
                "materialized_at_utc": "2026-08-13T12:00:00Z",
                "range_start_utc": "2026-08-14T00:00:00Z",
                "range_end_utc": "2026-08-15T00:00:00Z",
                "limit": "100",
            },
        )
        self.assertTrue(result["changed"])
        work = self.work(event, start=True)
        message = self.message(work)
        self.command(
            "event.cancel",
            {
                "command_id": "cancel-before-attempt",
                "actor_subject_id": "owner",
                "item_id": event["item_id"],
                "target_version": "3",
                "cancelled_at_utc": NOW,
            },
        )
        with self.assertRaises(SpineValidationError):
            self.prepare(message)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)

    def test_corrupt_support_never_becomes_ordinary_fallback(self):
        event, _ = self.event()
        work = self.work(event, start=True)
        # Disposable-ledger corruption injection, not a supported mutation.
        trigger = self.db.execute(
            "SELECT name FROM sqlite_schema WHERE type='trigger' AND tbl_name='notification_policy_presentations' AND sql LIKE '%DELETE%'"
        ).fetchone()[0]
        self.db.execute(f'DROP TRIGGER "{trigger}"')
        self.db.execute(
            "DELETE FROM notification_policy_presentations WHERE notification_policy_id="
            "(SELECT policy_id FROM notification_policies WHERE item_id=? AND version=3)",
            (event["item_id"],),
        )
        self.db.commit()
        with self.assertRaises(SpineValidationError):
            self.message(work)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM side_effect_attempts").fetchone()[0], 0)
