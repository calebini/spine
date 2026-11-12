"""R2 validation order, historical replay and bounded coherent read envelopes."""

import copy
import hashlib
import hmac
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from spine.commands import handle
from spine.commands.recurring_task_runtime import CURSOR, DEFAULTS, PREFIX, _b64, verify_cursor
from spine.commands.recurring_tasks import execute, stored_projection
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.ledger.items import create_next_item_version
from spine.ledger.recurring_task_sources import ProofBudget
from tests import test_recurring_task_commands as base
from tests import test_recurring_task_reconcile as pages


class RecurringTaskAdmissionReadTests(unittest.TestCase):
    setUp = pages.RecurringTaskReconcileTests.setUp
    tearDown = pages.RecurringTaskReconcileTests.tearDown
    request = base.RecurringTaskCommandTests.request
    write = base.RecurringTaskCommandTests.write
    created = base.RecurringTaskCommandTests.created
    run_command = base.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    source_change = pages.RecurringTaskReconcileTests.source_change
    rule = pages.RecurringTaskReconcileTests.rule

    @classmethod
    def setUpClass(cls):
        cls.contracts = base.contracts()

    def assert_error(self, command, request, code, field):
        before = base.dump(self.db)
        result = self.run_command(command, request)
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["error"]["code"], result["error"]["field"]), (code, field), result)
        self.assertEqual(base.dump(self.db), before)

    def test_nested_syntax_paths_are_lexicographic_not_deepest_first(self):
        request = self.request()
        request["configuration"]["generation_horizon_seconds"] = "0"
        request["configuration"]["task_template"]["people"]["assignees"] = [""]
        self.assert_error("create", request, "invalid_request", "configuration.generation_horizon_seconds")
        request = self.request()
        request["configuration"]["offset_basis"] = "calendar_days"
        request["configuration"]["z_extra"] = True
        self.assert_error("create", request, "invalid_request", "configuration.offset_basis")

    def test_missing_top_level_fields_and_unknown_view_preserve_syntax_order(self):
        request = self.request()
        del request["command_id"], request["actor_subject_id"]
        self.assert_error("create", request, "invalid_request", "command_id")
        request = {"contract_version": "spine.recurring-related-tasks.v1", "view": "unknown"}
        self.assert_error("show", request, "invalid_request", "related_task_rule_id")
        request["related_task_rule_id"] = "related_task_rule_" + "f" * 64
        self.assert_error("show", request, "invalid_request", "view")
        request["assignment_id"] = "malformed"
        self.assert_error("show", request, "invalid_request", "assignment_id")

    def test_every_page_limit_has_closed_syntax_bounds_before_references(self):
        rule = self.created()["result"]["rule"]
        before = base.dump(self.db)
        for field, (_, maximum) in DEFAULTS.items():
            for value in ("0", str(maximum + 1), "01", 1):
                with self.subTest(field=field, value=value):
                    request = self.write("reconcile", rule, limits={field: value})
                    request["actor_subject_id"] = "missing"
                    self.assert_error("reconcile", request, "invalid_request", "limits." + field)
            request = self.write("reconcile", rule, limits={field: str(maximum)})
            normalized = self.contracts.request(PREFIX + "reconcile", request)
            self.assertEqual(normalized["limits"][field], str(maximum))
        for command, request in (
            ("list", {"contract_version": "spine.recurring-related-tasks.v1"}),
            ("show", {"contract_version": "spine.recurring-related-tasks.v1", "view": "assignments",
                      "related_task_rule_id": rule["related_task_rule_id"]}),
        ):
            for limit in ("0", "201", "01", 1):
                self.assert_error(command, request | {"limit": limit}, "invalid_request", "limit")
            self.assertEqual(self.contracts.request(PREFIX + command, request | {"limit": "200"})["limit"], "200")
        self.assertEqual(base.dump(self.db), before)

    def test_internal_admission_precedes_syntax_and_remains_local_only(self):
        before = base.dump(self.db)
        request = {"contract_version": "wrong"}
        for metadata in ({"adapter": "http"}, {"adapter": "cli", "claimed_permission": "all"}):
            result = self.run_command("create", request, context=replace(self.context, transport_metadata=metadata))
            self.assertEqual((result["error"]["code"], result["error"]["field"]), ("environment_failure", "admission"))
        with patch.object(self.db, "_recurring_tasks_enabled", False):
            self.assert_error("create", request, "environment_failure", "admission")
        with patch("spine.commands.recurring_tasks.IMPLEMENTED_CONTRACT_VERSIONS", ()):
            self.assert_error("create", request, "environment_failure", "contract_version")
        with self.db.atomic_command(write=True):
            self.assert_error("create", request, "environment_failure", "admission")
        self.assert_error("not_a_command", request, "unsupported_command", "command")
        self.assert_error("create", request, "unsupported_contract_version", "contract_version")
        self.assertEqual(base.dump(self.db), before)

    def test_every_expected_fact_precedes_semantics_in_contract_order(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        request = self.write("assignment.suppress", initial["result"]["rule"], assignment_id=first["assignment_id"],
                             target_generation_id=first["generation_id"], target_task_item_id=first["after"]["task_item_id"])
        shown = self.run_command("show", {"contract_version": request["contract_version"],
                                          "related_task_rule_id": request["related_task_rule_id"],
                                          "view": "assignment", "assignment_id": first["assignment_id"]})
        request["expected"]["assignment_change_version"] = shown["result"]["assignment"]["change_version"]
        valid = copy.deepcopy(request)
        for field, value in request["expected"].items():
            request["expected"][field] = "999" if value.isdigit() else value[:-1] + ("a" if value[-1] != "a" else "b")
        request["target_generation_id"] = "related_task_generation_" + "f" * 64
        request["target_task_item_id"] = "missing"
        for field in valid["expected"]:
            self.assert_error("assignment.suppress", request, "stale_version", "expected." + field)
            request["expected"][field] = valid["expected"][field]
        self.assert_error("assignment.suppress", request, "stale_version", "target_generation_id")
        request["target_generation_id"] = valid["target_generation_id"]
        self.assert_error("assignment.suppress", request, "stale_version", "target_task_item_id")
        request["target_task_item_id"] = valid["target_task_item_id"]
        self.assert_error("assignment.suppress", request, "semantic_conflict", "target_generation_id")

    def test_all_cursor_purposes_reject_signed_noncanonical_or_rebound_payloads(self):
        vectors = json.loads((base.ROOT / "tests/fixtures/recurring_related_tasks/cursors.json").read_text())["vectors"]
        before = base.dump(self.db)
        for vector in vectors:
            payload = vector["payload"]
            config = base.FacetCursorConfig(bytes.fromhex(vector["key_hex"]), payload["query"]["ledger_instance_id"], payload["key_id"])

            def signed(raw, config=config):
                mac = hmac.new(config.secret, CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()
                return _b64(raw) + "." + _b64(mac)

            def rejected(token, query=None, now=None, catalog=None, code="invalid_request:cursor", key=None,
                         config=config, payload=payload):
                with self.assertRaises(SpineValidationError) as caught:
                    verify_cursor(key or config, token, query or payload["query"], payload["purpose"],
                                  now or payload["issued_at_utc"], catalog or payload["catalog_generation"], self.contracts)
                self.assertEqual(caught.exception.code, code)

            with self.subTest(purpose=payload["purpose"]):
                raw = canonical_json_bytes(payload)
                rejected(signed(b" " + raw))
                rejected(signed(b'{"key_id":' + json.dumps(payload["key_id"]).encode() + b"," + raw[1:]))
                rejected(signed(canonical_json_bytes(payload | {"unexpected": True})))
                rejected(signed(canonical_json_bytes(payload | {"expires_at_utc": payload["issued_at_utc"]})))
                rejected(signed(canonical_json_bytes(payload | {
                    "issued_at_utc": "9999-12-31T23:59:59Z", "expires_at_utc": "9999-12-31T23:59:59Z",
                })))
                rejected(vector["wire"], query=payload["query"] | {"ledger_instance_id": "different-ledger"},
                         key=replace(config, ledger_id="different-ledger"))
                rejected(vector["wire"], key=replace(config, generation="rotated-key"))
                rejected(vector["wire"], now=payload["expires_at_utc"], code="stale_cursor:cursor")
                rejected(vector["wire"], catalog=str(int(payload["catalog_generation"]) + 1), code="stale_cursor:cursor")
        self.assertEqual(base.dump(self.db), before)

    def test_read_filters_are_queries_and_terminal_reads_need_no_cursor_key(self):
        active = self.created("active")["result"]["rule"]
        retired = self.created("retired")["result"]["rule"]
        result = self.run_command("retire", self.write("retire", retired, disposition="keep_following"))
        self.assertTrue(result["ok"], result)
        context = replace(self.context, facet_cursor_config=None)
        request = {"contract_version": "spine.recurring-related-tasks.v1"}
        before = base.dump(self.db)
        cases = [({}, [active["related_task_rule_id"]]),
                 ({"status": "retired"}, [retired["related_task_rule_id"]]),
                 ({"status": "all"}, sorted([active["related_task_rule_id"], retired["related_task_rule_id"]])),
                 ({"owner": {"owner_kind": "subject", "owner_subject_id": "missing"}}, []),
                 ({"source_item_id": "missing"}, [])]
        for filters, identities in cases:
            result = self.run_command("list", request | filters, context=context)
            self.assertTrue(result["ok"], result)
            self.assertEqual([r["related_task_rule_id"] for r in result["result"]["rows"]], identities)
            self.assertFalse(result["result"]["has_more"])
            self.assertIsNone(result["result"]["next_cursor"])
            self.assertTrue(all("configuration" not in r for r in result["result"]["rows"]))
        self.assertEqual(base.dump(self.db), before)

    def test_actual_history_pages_are_complete_and_cross_root_targets_are_rejected(self):
        other = self.created("other")["result"]["rule"]
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        self.source_change(exdates=[pages.RecurringTaskReconcileTests.excluded(self, first)])
        self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "read-cancel")
        self.source_change(exdates=[])
        restored = self.reconcile(self.rule(initial["result"]["rule"]["related_task_rule_id"]), "read-restore")
        request = {"contract_version": "spine.recurring-related-tasks.v1",
                   "related_task_rule_id": restored["result"]["rule"]["related_task_rule_id"]}
        before = base.dump(self.db)
        for view, key in (("assignments", "assignment_seq"), ("generations", "generation_index"), ("states", "change_version")):
            selected = request | {"view": view}
            if view != "assignments":
                selected["assignment_id"] = first["assignment_id"]
            all_rows = self.run_command("show", selected | {"limit": "200"})
            self.assertTrue(all_rows["ok"], all_rows)
            rows, cursor, tokens = [], None, set()
            for _ in range(20):
                page = self.run_command("show", selected | {"limit": "1"} | ({"cursor": cursor} if cursor else {}))
                self.assertTrue(page["ok"], page)
                rows.extend(page["result"]["rows"])
                cursor = page["result"]["next_cursor"]
                if not page["result"]["has_more"]:
                    self.assertIsNone(cursor)
                    break
                self.assertNotIn(cursor, tokens)
                tokens.add(cursor)
                self.assert_error("show", selected | {"limit": "2", "cursor": cursor}, "invalid_request", "cursor")
            else:
                self.fail("bounded history pagination did not terminate")
            self.assertEqual(rows, all_rows["result"]["rows"])
            self.assertGreater(len(rows), 1)
            self.assertEqual([int(r[key]) for r in rows], sorted({int(r[key]) for r in rows}))
        for view in ("assignment", "generations", "states"):
            self.assert_error("show", request | {"view": view, "related_task_rule_id": other["related_task_rule_id"],
                                                  "assignment_id": first["assignment_id"]},
                              "referenced_row_not_found", "assignment_id")
        assignment = self.run_command("show", request | {"view": "assignment", "assignment_id": first["assignment_id"]})
        proof_id = assignment["result"]["assignment"]["source_proof_id"]
        self.assert_error("show", request | {"view": "proof", "proof_id": proof_id,
                                              "related_task_rule_id": other["related_task_rule_id"]},
                          "referenced_row_not_found", "proof_id")
        self.assertEqual(base.dump(self.db), before)

    def test_observed_task_and_source_changes_do_not_repair_stored_history(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        request = {"contract_version": "spine.recurring-related-tasks.v1",
                   "related_task_rule_id": initial["result"]["rule"]["related_task_rule_id"],
                   "assignment_id": first["assignment_id"]}
        shown = self.run_command("show", request | {"view": "assignment"})["result"]["assignment"]
        history = self.run_command("show", request | {"view": "states"})["result"]["rows"]
        self.assertEqual(shown["freshness"], "current")
        with self.db.atomic_command(write=True):
            create_next_item_version(self.db, item_id=shown["task_item_id"], target_version=1,
                                     created_at_utc=self.now, created_by_subject_id="owner",
                                     task_detail={"task_status": "done", "completed_at_utc": self.now,
                                                  "completed_by_subject_id": "owner"}, supporting_command_id="read-complete")
        self.source_change(exdates=[])
        before = base.dump(self.db)
        changed = self.run_command("show", request | {"view": "assignment"})["result"]["assignment"]
        self.assertEqual(changed["freshness"], "needs_reconcile")
        self.assertEqual(changed["task_status"], "done")
        self.assertEqual(changed["observed_task_item_version"], "2")
        self.assertEqual(changed["observed_source_item_version"], "2")
        for field in ("assignment_revision_id", "source_proof_id", "source_snapshot", "task_item_version"):
            self.assertEqual(changed[field], shown[field])
        self.assertEqual(self.run_command("show", request | {"view": "states"})["result"]["rows"], history)
        self.assertEqual(base.dump(self.db), before)

    def test_single_read_and_single_row_envelope_overflow_never_writes_or_truncates(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        request = {"contract_version": "spine.recurring-related-tasks.v1",
                   "related_task_rule_id": initial["result"]["rule"]["related_task_rule_id"]}
        assignment = self.run_command("show", request | {"view": "assignment", "assignment_id": first["assignment_id"]})
        cases = [request, request | {"view": "assignment", "assignment_id": first["assignment_id"]},
                 request | {"view": "proof", "proof_id": assignment["result"]["assignment"]["source_proof_id"]},
                 request | {"view": "states", "assignment_id": first["assignment_id"]}]
        before = base.dump(self.db)
        for selected in cases:
            result = self.run_command("show", selected)
            self.assertTrue(result["ok"], result)
            size = len(canonical_json_bytes(result))
            with patch("spine.commands.recurring_tasks.READ_RESPONSE_BYTES", size):
                self.assertEqual(self.run_command("show", selected), result)
            with patch("spine.commands.recurring_tasks.READ_RESPONSE_BYTES", size - 1):
                self.assert_error("show", selected, "capacity_exceeded", "response_bytes")
        self.assertEqual(base.dump(self.db), before)

    def test_invalid_unicode_is_a_closed_input_failure_not_a_canonicalization_error(self):
        request = self.request()
        request["configuration"]["task_template"]["item"]["title"] = "invalid\ud800title"
        self.assert_error("create", request, "invalid_request", "configuration.task_template.item.title")
        request["configuration"]["generation_horizon_seconds"] = "0"
        self.assert_error("create", request, "invalid_request", "configuration.generation_horizon_seconds")
        request = self.request()
        request["\ud800"] = True
        self.assert_error("create", request, "invalid_request", "request")

    def test_nonrecurring_or_wrong_type_source_is_a_semantic_failure_not_missing_environment(self):
        for command, fields in (("event.create", {"all_day": False, "start_anchor": {
            "anchor_kind": "instant_utc", "utc_instant": "2026-08-08T18:00:00Z",
        }}), ("task.create", {})):
            with self.subTest(command=command):
                created = handle(command, {
                    "command_id": "bad-source-" + command, "actor_subject_id": "owner", "created_at_utc": self.now,
                    "title": "Not a recurring source", **fields,
                }, self.context)
                self.assertTrue(created["ok"], created)
                request = self.request()
                request["source"]["item_id"] = created["item_id"]
                self.assert_error("create", request, "semantic_conflict", "source.item_id")

    def test_explicit_configuration_reference_failures_precede_stale_expected_facts(self):
        rule = self.created()["result"]["rule"]
        missing = "missing-reference"
        cases = [
            ({"task_owner": {"owner_kind": "subject", "owner_subject_id": missing}}, "configuration.task_owner.owner_subject_id"),
            ({"task_template": {"item": {"item_type": "task", "title": "Pickup", "task_detail": {}},
                                 "people": {"assignees": [missing]}}}, "configuration.task_template.people.assignees"),
            ({"task_template": {"item": {"item_type": "task", "title": "Pickup", "task_detail": {},
                                          "primary_location": {"mode": "reference", "location_id": missing}},
                                 "people": {"assignees": []}}}, "configuration.task_template.item.primary_location.location_id"),
            ({"task_template": {"item": {"item_type": "task", "title": "Pickup", "task_detail": {}, "archetype": {
                "item_archetype_id": missing, "revision_resolution": "current", "selection_source": "operator_explicit",
            }}, "people": {"assignees": []}}}, "configuration.task_template.item.archetype.item_archetype_id"),
        ]
        for changes, field in cases:
            with self.subTest(field=field):
                config = self.request()["configuration"] | changes | {"generation_horizon_seconds": "4838400"}
                request = self.write("update", rule, configuration=config, adoption_scope="new_assignments_only")
                request["expected"]["rule_change_version"] = "999"
                self.assert_error("update", request, "referenced_row_not_found", field)

    def test_missing_assignment_beats_stale_suppression_facts(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        first = initial["result"]["results"][0]
        request = self.write(
            "assignment.suppress", initial["result"]["rule"], assignment_id="related_task_assignment_" + "f" * 64,
            target_generation_id=first["generation_id"], target_task_item_id=first["after"]["task_item_id"],
        )
        request["expected"].update(assignment_change_version="999", rule_change_version="999")
        self.assert_error("assignment.suppress", request, "referenced_row_not_found", "assignment_id")

    def test_catalog_revision_membership_and_delivery_references_precede_staleness(self):
        rule = self.created()["result"]["rule"]
        delivery = {"recipient_kind": "subject", "recipient_subject_id": "owner", "channel": "test",
                    "target": {"resolution": "explicit", "delivery_target_id": "owner-route"}}
        explicit = {"mode": "explicit", "notification_profile_id": self.profile["notification_profile_id"],
                    "revision_resolution": "current", "custom_additions": []}
        archetype = {"item_archetype_id": self.archetype["item_archetype_id"], "revision_resolution": "exact",
                     "item_archetype_revision_id": "missing", "selection_source": "operator_explicit"}
        cases = [
            ({"notification_plan": explicit | {"notification_profile_id": "missing"}, "delivery": delivery},
             "configuration.notification_plan.notification_profile_id"),
            ({"notification_plan": explicit | {"revision_resolution": "exact", "notification_profile_revision_id": "missing"},
              "delivery": delivery}, "configuration.notification_plan.notification_profile_revision_id"),
            ({"notification_plan": explicit, "delivery": delivery | {"recipient_subject_id": "missing"}},
             "configuration.delivery.recipient_subject_id"),
            ({"notification_plan": explicit, "delivery": delivery | {"target": {
                "resolution": "explicit", "delivery_target_id": "missing"}}},
             "configuration.delivery.target.delivery_target_id"),
            ({"notification_plan": explicit, "delivery": delivery | {"target": {
                "resolution": "context_default", "default_key": "missing"}}},
             "configuration.delivery.target.default_key"),
            ({"task_template": {"item": {"item_type": "task", "title": "Pickup", "task_detail": {}, "archetype": archetype},
                                 "people": {"assignees": []}}}, "configuration.task_template.item.archetype.item_archetype_revision_id"),
        ]
        for changes, field in cases:
            with self.subTest(field=field):
                config = self.request()["configuration"] | changes | {"generation_horizon_seconds": "4838400"}
                request = self.write("update", rule, configuration=config, adoption_scope="upcoming_open")
                request["expected"]["rule_change_version"] = "999"
                self.assert_error("update", request, "referenced_row_not_found", field)

    def test_actor_and_rule_references_then_cursor_then_expected_facts(self):
        rule = self.created()["result"]["rule"]
        request = self.write("reconcile", rule, limits={}, cursor="e30." + "A" * 43)
        request["expected"]["rule_change_version"] = "999"
        self.assert_error("reconcile", request | {"actor_subject_id": "missing"}, "referenced_row_not_found", "actor_subject_id")
        self.assert_error("reconcile", request | {"related_task_rule_id": "related_task_rule_" + "f" * 64},
                          "referenced_row_not_found", "related_task_rule_id")
        self.assert_error("reconcile", request, "invalid_request", "cursor")

    def test_read_assignment_reference_precedes_cursor_without_repair(self):
        rule = self.created()["result"]["rule"]
        request = {
            "contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": rule["related_task_rule_id"],
            "view": "states", "assignment_id": "related_task_assignment_" + "f" * 64, "limit": "1", "cursor": "e30." + "A" * 43,
        }
        self.assert_error("show", request, "referenced_row_not_found", "assignment_id")

    def test_historical_reconcile_replay_ignores_expired_cursor_and_later_source_retirement(self):
        rule = self.created()["result"]["rule"]
        request = self.write("reconcile", rule, limits={"mutations": "1"}) | {"command_id": "historical-page"}
        original = self.run_command("reconcile", request)
        self.assertTrue(original["ok"], original)
        self.assertTrue(original["result"]["has_more"])
        self.source_change(exdates=[])
        current = self.rule(rule["related_task_rule_id"])
        retired = self.run_command("retire", self.write("retire", current, disposition="keep_following"))
        self.assertTrue(retired["ok"], retired)
        before = base.dump(self.db)

        def no_clock():
            self.fail("compatible replay must not sample execution time or refresh an expired cursor")

        self.now = "2026-12-01T00:00:00Z"
        replay = execute(PREFIX + "reconcile", request, self.context, contracts=self.contracts, clock=no_clock)
        self.assertEqual(replay, original | {"replayed": True})
        self.assertEqual(base.dump(self.db), before)
        invalid = copy.deepcopy(request)
        invalid["limits"]["mutations"] = "129"
        self.assert_error("reconcile", invalid, "invalid_request", "limits.mutations")
        conflict = copy.deepcopy(request)
        conflict["limits"]["mutations"] = "2"
        self.assert_error("reconcile", conflict, "command_id_conflict", "command_id")

    def test_cross_ledger_cursor_and_missing_key_are_nonmutating(self):
        self.created("one")
        self.created("two")
        request = {"contract_version": "spine.recurring-related-tasks.v1", "limit": "1"}
        result = self.run_command("list", request)
        self.assertTrue(result["ok"], result)
        token = result["result"]["next_cursor"]
        before = base.dump(self.db)
        context = replace(self.context, facet_cursor_config=replace(self.context.facet_cursor_config, ledger_id="another-ledger"))
        failed = self.run_command("list", request | {"cursor": token}, context=context)
        self.assertEqual((failed["error"]["code"], failed["error"]["field"]), ("environment_failure", "cursor_configuration"))
        self.assertEqual(base.dump(self.db), before)
        invalid_key = replace(self.context, facet_cursor_config=replace(self.context.facet_cursor_config, generation="\ud800"))
        failed = self.run_command("list", request, context=invalid_key)
        self.assertEqual((failed["error"]["code"], failed["error"]["field"]), ("environment_failure", "cursor_configuration"))
        self.assertEqual(base.dump(self.db), before)

    def test_large_actual_state_history_uses_exact_success_envelope_then_continues_between_rows(self):
        def change(rule, title, cid):
            config = self.request()["configuration"]
            config["generation_horizon_seconds"] = "4838400"
            config["task_template"]["item"]["title"] = title
            request = self.write("update", rule, configuration=config, adoption_scope="upcoming_open") | {"command_id": cid}
            result = self.run_command("update", request)
            self.assertTrue(result["ok"], result)
            return result["result"]["rule"]

        initial = self.reconcile(self.created()["result"]["rule"], mutations="1")
        first = initial["result"]["results"][0]
        rule = initial["result"]["rule"]
        for index in range(18):
            rule = change(rule, f"{index:02d}" + "x" * 50000, f"large-update-{index:02d}")
            rule = self.reconcile(rule, f"large-history-{index:02d}")["result"]["rule"]
        rule = change(rule, "probe", "large-update-probe")
        rule = self.reconcile(rule, "large-history-probe")["result"]["rule"]

        def history():
            identities = self.db.execute(
                "SELECT assignment_revision_id FROM related_task_assignment_revisions WHERE assignment_id=? ORDER BY change_version",
                (first["assignment_id"],),
            ).fetchall()
            return [stored_projection(self.db, "related_task_assignment_revisions", row[0]) for row in identities]

        with self.db.atomic_command(write=False):
            rows = history()
        # Tune a real final adoption into the gap left by the former fixed 8-KiB
        # reservation: all complete rows and their actual terminal envelope fit.
        target = 1043000
        length = target - len(canonical_json_bytes(rows)) - len(canonical_json_bytes(rows[-1])) - 1 + len("probe")
        self.assertGreater(length, 1)
        self.assertLess(length, 60000)
        rule = change(rule, "z" * length, "large-update-final")
        rule = self.reconcile(rule, "large-history-final")["result"]["rule"]
        with self.db.atomic_command(write=False):
            rows = history()
        self.assertGreater(len(canonical_json_bytes(rows)), 1040384)
        self.assertLess(len(canonical_json_bytes(rows)), 1045000)
        request = {
            "contract_version": "spine.recurring-related-tasks.v1", "related_task_rule_id": rule["related_task_rule_id"],
            "view": "states", "assignment_id": first["assignment_id"], "limit": "200",
        }
        before = base.dump(self.db)
        complete = self.run_command("show", request)
        self.assertTrue(complete["ok"], complete)
        self.assertFalse(complete["result"]["has_more"])
        self.assertEqual(complete["result"]["rows"], rows)
        self.assertLessEqual(len(canonical_json_bytes(complete)), 1048576)
        self.assertEqual(base.dump(self.db), before)

        # One more actual transition now exceeds the full-envelope cap. The read
        # must return complete rows with a precise continuation and no repair.
        rule = change(rule, "tail" * 4000, "large-update-tail")
        self.reconcile(rule, "large-history-tail")
        before = base.dump(self.db)
        first_page = self.run_command("show", request)
        self.assertTrue(first_page["ok"], first_page)
        self.assertTrue(first_page["result"]["has_more"])
        self.assertLessEqual(len(canonical_json_bytes(first_page)), 1048576)
        second_page = self.run_command("show", request | {"cursor": first_page["result"]["next_cursor"]})
        self.assertTrue(second_page["ok"], second_page)
        self.assertFalse(second_page["result"]["has_more"])
        self.assertLessEqual(len(canonical_json_bytes(second_page)), 1048576)
        with self.db.atomic_command(write=False):
            self.assertEqual(first_page["result"]["rows"] + second_page["result"]["rows"], history())
        self.assertEqual(base.dump(self.db), before)

    def test_low_lineage_budget_fails_without_cancellation_or_partial_refresh(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        split = handle("recurrence.series.edit", {
            "command_id": "budget-count-split", "actor_subject_id": "owner", "item_id": self.event["item_id"],
            "target_version": "1", "recurrence_set_id": self.set_id, "recurrence_revision_id": self.revision,
            "edited_at_utc": self.now, "edit_scope": "this_and_following",
            "target_occurrence_key": initial["result"]["results"][2]["occurrence_key"], "recurrence_patch": {"rdates": []},
        }, self.context)
        self.assertTrue(split["ok"], split)
        self.assertEqual(split["effect"], "series_edit_following_applied")
        rule = self.rule(initial["result"]["rule"]["related_task_rule_id"])
        request = self.write("reconcile", rule, limits={"lineage_hops": "1", "proof_steps": "50000"})
        self.assert_error("reconcile", request, "capacity_exceeded", "limits.lineage_hops")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM task_details WHERE task_status='cancelled'").fetchone()[0], 0)
        refreshed = self.reconcile(rule, "sufficient-proof", lineage_hops="256", proof_steps="50000")
        self.assertTrue(refreshed["changed"], refreshed)
        self.assertEqual({v["outcome"] for v in refreshed["result"]["results"]}, {"refreshed"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM related_task_generations").fetchone()[0], 6)

    def test_mid_page_proof_exhaustion_rolls_back_earlier_unit_writes(self):
        initial = self.reconcile(self.created()["result"]["rule"])
        for _ in range(2):
            self.source_change(exdates=[])
        rule = self.rule(initial["result"]["rule"]["related_task_rule_id"])
        active, first_unit_cost = [], []
        real_spend = ProofBudget.spend

        def observed_spend(budget, amount=1, *, hop=False):
            active[:] = [budget]
            return real_spend(budget, amount, hop=hop)

        def measured_fault(stage):
            if stage == "binding" and not first_unit_cost:
                first_unit_cost.append(50000 - active[0].steps)

        preview = self.write("reconcile", rule, limits={"proof_steps": "50000", "lineage_hops": "256"})
        with patch.object(ProofBudget, "spend", observed_spend):
            result = self.run_command("reconcile", preview, context=replace(self.context, dry_run=True), fault=measured_fault)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(first_unit_cost), 1)
        stages = []
        limited = self.write("reconcile", rule, limits={"proof_steps": str(first_unit_cost[0] + 1), "lineage_hops": "256"})
        before = base.dump(self.db)
        result = self.run_command("reconcile", limited, fault=stages.append)
        self.assertFalse(result["ok"], result)
        self.assertEqual((result["error"]["code"], result["error"]["field"]), ("capacity_exceeded", "limits.proof_steps"))
        self.assertIn("binding", stages)
        self.assertEqual(base.dump(self.db), before)
