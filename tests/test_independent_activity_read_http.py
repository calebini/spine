"""Real-ledger HTTP gates for the complete independent read registry."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import handle
from spine.core.canonical_json import canonical_json_bytes
from spine.core.occurrences import expand_recurrence_set
from spine.ledger.recurrence import load_current_recurrence_set
from spine.web.errors import WebError
from spine.web.http import create_app
from spine.web.read_context import OptionalReadUnavailable
from spine.web.read_contracts import READ_API, READ_PIN_MANIFEST_SHA256, READ_RUNTIME_CONTRACTS, ReadContracts
from spine.web.read_sections import Evidence
from tests import test_independent_activity_read_contracts as contracts_helpers
from tests import test_independent_activity_read_pages as helpers
from tests.test_trusted_web_runtime import AT

ROOT = Path(__file__).parents[1]
PATHS = {"schedule.show": "/api/v2/commands/schedule.show", "item.occurrences": "/api/v2/commands/item.occurrences",
         "agenda": "/api/v2/agenda"}


class IndependentReadPackageTests(unittest.TestCase):
    def test_exact_package_pins_declarations_and_source_parity(self):
        contracts = ReadContracts.packaged()
        pins = ROOT / "contracts/trusted-web-read-schema-pins.v1.json"
        self.assertEqual(hashlib.sha256(pins.read_bytes()).hexdigest(), READ_PIN_MANIFEST_SHA256)
        self.assertTrue(READ_RUNTIME_CONTRACTS <= IMPLEMENTED_CONTRACT_VERSIONS)
        for folder, files in (("schemas/", contracts.schemas), ("", contracts.artifacts)):
            for name in files:
                self.assertEqual((ROOT / "contracts" / folder / name).read_bytes(),
                                 (ROOT / "src/spine/contracts/web" / folder / name).read_bytes())

    def test_each_missing_or_corrupt_required_asset_denies_admission(self):
        pins = json.loads((ROOT / "contracts/trusted-web-read-schema-pins.v1.json").read_text())
        names = ["trusted-web-read-schema-pins.v1.json", *pins["artifacts"], *("schemas/" + n for n in pins["schemas"])]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "src/spine/contracts/web", root / "web")
            with patch("spine.web.read_contracts.resources.files", return_value=root):
                for name in names:
                    target = root / "web" / name
                    raw = target.read_bytes()
                    for mode in ("missing", "corrupt"):
                        with self.subTest(asset=name, mode=mode):
                            if mode == "missing":
                                target.unlink()
                            else:
                                target.write_bytes(b"{}\n")
                            with self.assertRaises(WebError) as caught:
                                ReadContracts.packaged()
                            self.assertEqual(caught.exception.code, "admission_unavailable")
                            target.write_bytes(raw)

    def test_incomplete_runtime_declarations_deny_admission(self):
        with patch("spine.web.read_contracts.IMPLEMENTED_CONTRACT_VERSIONS", IMPLEMENTED_CONTRACT_VERSIONS - {READ_API}):
            with self.assertRaises(WebError) as caught:
                ReadContracts.packaged()
            self.assertEqual(caught.exception.code, "admission_unavailable")


class IndependentReadHTTPTests(unittest.TestCase):
    setUpClass = helpers.IndependentReadPageTests.__dict__["setUpClass"]
    ok, provision, event, run_command = (
        helpers.IndependentReadPageTests.ok, helpers.IndependentReadPageTests.provision,
        helpers.IndependentReadPageTests.event, helpers.IndependentReadPageTests.run_command,
    )
    snapshot, related, adopt, recurring, agenda_request = (
        helpers.IndependentReadPageTests.snapshot, helpers.IndependentReadPageTests.related,
        helpers.IndependentReadPageTests.adopt, helpers.IndependentReadPageTests.recurring, helpers.IndependentReadPageTests.agenda_request,
    )
    create, changed, mutate, update, grant = (
        helpers.IndependentReadPageTests.create, helpers.IndependentReadPageTests.changed,
        helpers.IndependentReadPageTests.mutate, helpers.IndependentReadPageTests.update, helpers.IndependentReadPageTests.grant,
    )
    detail_query, next_detail, occurrence_query = (
        helpers.IndependentReadPageTests.detail_query, helpers.IndependentReadPageTests.next_detail,
        helpers.IndependentReadPageTests.occurrence_query,
    )

    def setUp(self):
        helpers.IndependentReadPageTests.setUp(self)
        self.app = create_app(self.service.config)
        self.reader = self.app.extensions["spine_read_service"]
        self.reader.now = lambda: self.at
        self.pager = self.reader.pager
        self.client = self.app.test_client()

    def headers(self, subject="owner"):
        return {"Host": self.service.config.host, "Origin": self.service.config.origin, "Content-Type": "application/json",
                "X-Spine-Account-ID": self.accounts[subject], "X-Spine-Selection-ID": "selection"}

    def read(self, identity=None, *, route="schedule.show", request=None, subject="owner", guards=None, **kwargs):
        headers = self.headers(subject)
        if "selection" in kwargs:
            headers["X-Spine-Account-ID"], headers["X-Spine-Selection-ID"] = kwargs["selection"]()
        with patch.object(self.reader, "before_release", kwargs.get("before_release")):
            response = self.client.post(PATHS[route], json={
                "contract_version": READ_API, "request": request or {"item_id": identity}, **(guards or {}),
            }, headers=headers)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        value = response.get_json()
        if response.status_code != 200:
            self.contracts.validate("trusted-web-read-error.schema.json", value)
            raise WebError(value["error"]["code"], status=response.status_code)
        contracts_helpers.semantic_oracle(value)
        return value

    # Run the real paging/race oracles through Flask as well as the internal pager.
    test_http_section_pages_no_writes = helpers.IndependentReadPageTests.test_detail_pagination_has_no_duplicates_and_no_durable_effects
    test_http_canonical_occurrence_pages = helpers.IndependentReadPageTests.test_occurrence_pages_reuse_engine_order_and_ids_both_bases
    test_http_combined_stream_and_coverage = (
        helpers.IndependentReadPageTests.test_agenda_shared_limit_resolved_then_unplaced_and_global_coverage
    )
    test_http_mixed_section_families = helpers.IndependentReadPageTests.test_multiple_section_cursors_share_family_and_can_repeat_pages
    test_http_expiry_during_release = helpers.IndependentReadPageTests.test_expiry_is_not_renewed_and_checked_after_fresh_proof
    test_http_source_and_identity_fences = helpers.IndependentReadPageTests.test_source_subject_and_access_changes_reject_continuation
    test_http_time_triggered_revocation = (
        helpers.IndependentReadPageTests.test_time_triggered_grant_expiry_blocks_next_page_without_epoch_change
    )
    test_http_future_activation = helpers.IndependentReadPageTests.test_future_candidate_grant_and_membership_activation_bound_pages
    test_http_dst_exclusions_overrides = helpers.IndependentReadPageTests.test_dst_occurrence_pages_match_canonical_overrides_and_exclusions
    test_http_terminal_and_resolved_empty = helpers.IndependentReadPageTests.test_terminal_series_pages_and_resolved_empty_do_not_claim_more
    test_http_stale_source_unplaced = helpers.IndependentReadPageTests.test_stale_follow_source_stays_unplaced_on_later_agenda_page
    test_http_hidden_follower_cursor_stability = (
        helpers.IndependentReadPageTests.test_hidden_follower_changes_do_not_invalidate_continuation
    )

    def test_complete_registry_discovery_is_selected_and_independent_of_items(self):
        before = "\n".join(self.db.iterdump())
        results = []
        for subject in ("owner", "other"):
            response = self.client.get("/api/v2/read-capabilities", headers=self.headers(subject))
            self.assertEqual(response.status_code, 200)
            value = response.get_json()
            self.contracts.validate("trusted-web-read-capabilities.schema.json", value)
            self.assertEqual(value["subject_id"], subject)
            results.append(value["result"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(before, "\n".join(self.db.iterdump()))
        routes = {r.rule for r in self.app.url_map.iter_rules() if r.rule.startswith("/api/v2/")}
        self.assertEqual(routes, {*PATHS.values(), "/api/v2/read-capabilities"})
        self.assertEqual(self.client.get("/api/v2/read-capabilities", headers={"Host": self.service.config.host}).status_code, 400)
        self.reader.before_release = lambda: self.mutate("UPDATE subjects SET display_name='Changed' WHERE subject_id='owner'")
        response = self.client.get("/api/v2/read-capabilities", headers=self.headers())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "access_changed")

    def follower(self, identity):
        recurrence = load_current_recurrence_set(self.db, item_id=identity)
        occurrence = expand_recurrence_set(recurrence, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00").occurrences[0]
        result = self.ok(handle("schedule.related_task.create", {
            "contract_version": "spine.schedule-related-task-create.v1", "command_id": "selected-follower",
            "actor_subject_id": "owner", "created_at_utc": AT,
            "source": {"item_id": identity, "target_version": "1", "anchor_role": "event_start", "scope": "selected_occurrence",
                       "source_recurrence_revision_id": recurrence["recurrence_revision_id"],
                       "target_occurrence_key": occurrence["occurrence_key"],
                       "target_occurrence_selector": occurrence["target_occurrence_selector"]},
            "task": {"title": "PRIVATE FOLLOWER", "priority": "normal", "subject_roles": [{"subject_id": "owner", "role": "assignee"}]},
            "relationship": {"relation_type": "part_of"},
            "temporal_binding": {"binding_mode": "follow_source", "offset_basis": "elapsed", "offset_seconds": "-3600",
                                 "source_terminal_behavior": "detach_at_last_value"},
            "reminders": [], "materialization": {"mode": "none"},
        }, self.ctx))
        return result["task"]["item_id"]

    def test_science_series_read_independent_of_unowned_and_hidden_follower(self):
        identity = self.recurring()
        request = {"item_id": identity, "include": ["related_items", "relations", "temporal_bindings"]}
        before = self.read(request=request)["result"]
        task = self.follower(identity)
        for owned in (False, True):
            if owned:
                self.adopt(task, "other")
            snapshot = "\n".join(self.db.iterdump())
            detail = self.read(request=request)
            self.assertEqual(detail["result"], before)
            occurrences = self.read(route="item.occurrences", request=self.occurrence_query(identity))
            agenda = self.read(route="agenda", request=self.agenda_request(item_ids=[identity]))
            for value in (detail, occurrences, agenda):
                self.assertNotIn(task, json.dumps(value))
                self.assertNotIn("PRIVATE FOLLOWER", json.dumps(value))
            self.assertEqual(len(agenda["result"]["entries"]), 3)
            self.assertEqual(snapshot, "\n".join(self.db.iterdump()))
        legacy = self.client.post("/api/v1/commands/schedule.show", json={
            "contract_version": "spine.trusted-web-api.v1", "request": {"item_id": identity},
        }, headers=self.headers())
        self.assertEqual(legacy.status_code, 404)
        self.assertEqual(legacy.get_json()["contract_version"], "spine.trusted-web-api.v1")

    def test_visible_cross_owner_related_row_requires_its_own_time_authority(self):
        identity = self.create()
        task = self.related(identity)
        self.adopt(task, "other")
        self.grant(task, subject="owner")
        shown = self.read(request={"item_id": identity, "include": ["related_items"]})
        related = shown["result"]["sections"]["related_items"]["entries"]
        self.assertEqual([r["item_id"] for r in related], [task])
        self.assertEqual(related[0]["time"]["availability"], "available")
        other = self.read(task, subject="other")["result"]["activity"]
        self.assertEqual(other["time"]["availability"], "unavailable")
        self.assertNotIn("anchors", other["time"])

    def test_optional_failure_and_root_denial_are_independent(self):
        identity = self.create()
        with patch.object(Evidence, "work", side_effect=OptionalReadUnavailable):
            result = self.read(request={"item_id": identity, "include": ["work"]})["result"]
            self.assertEqual(result["activity"]["time"]["availability"], "available")
            self.assertEqual(result["sections"]["work"]["availability"], "unavailable")
            self.changed("resource_unavailable", lambda: self.read(identity, subject="other"))

    def test_absent_unowned_and_denied_roots_have_identical_errors(self):
        owned = self.create()
        unowned = self.related(owned)
        errors = []
        for identity in ("absent", unowned, owned):
            for route, request in (("schedule.show", {"item_id": identity}),
                                   ("agenda", self.agenda_request(item_ids=[identity]))):
                response = self.client.post(PATHS[route], json={"contract_version": READ_API, "request": request},
                                            headers=self.headers("other"))
                self.assertEqual(response.status_code, 404)
                value = response.get_json()
                self.assertNotIn("result", value)
                errors.append(value["error"])
        self.assertTrue(all(error == {"code": "resource_unavailable", "message": "Read unavailable."} for error in errors))

    def test_transport_and_generic_error_boundary(self):
        identity = self.create()
        base = {"contract_version": READ_API, "request": {"item_id": identity}}
        for headers, body, status in (
            ({**self.headers(), "Host": "evil.test"}, json.dumps(base), 403),
            ({**self.headers(), "Origin": "https://evil.test"}, json.dumps(base), 403),
            ({**self.headers(), "X-Forwarded-Subject": "owner"}, json.dumps(base), 400),
            ({**self.headers(), "Content-Type": "text/plain"}, json.dumps(base), 400),
            ({**self.headers(), "X-Spine-Account-ID": self.accounts["owner"] + ",other"}, json.dumps(base), 400),
            (self.headers(), '{"request":{},"request":{}}', 400),
            (self.headers(), '{"contract_version":NaN}', 400),
            (self.headers(), "[", 400),
            (self.headers(), " " * 1048577, 413),
            (self.headers(), json.dumps({**base, "actor_subject_id": "owner"}), 400),
            (self.headers(), json.dumps({**base, "contract_version": "spine.trusted-web-api.v99"}), 400),
        ):
            with self.subTest(status=status, headers=headers):
                response = self.client.post(PATHS["schedule.show"], data=body, headers=headers)
                self.assertEqual(response.status_code, status, response.get_json())
                value = response.get_json()
                self.contracts.validate("trusted-web-read-error.schema.json", value)
                self.assertEqual(set(value["error"]), {"code", "message"})
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        with patch.object(self.reader, "execute", side_effect=RuntimeError("PRIVATE SQL/provider payload")):
            response = self.client.post(PATHS["schedule.show"], json=base, headers=self.headers())
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("PRIVATE", response.get_data(as_text=True))

    def test_discovery_rejects_cross_origin_injection_query_and_body(self):
        for headers, suffix, body in (
            ({**self.headers(), "Origin": "https://evil.test"}, "", None),
            ({**self.headers(), "X-Spine-Subject-ID": "owner"}, "", None),
            (self.headers(), "?subject=owner", None),
            (self.headers(), "", "{}"),
        ):
            response = self.client.get("/api/v2/read-capabilities" + suffix, headers=headers, data=body)
            self.assertNotEqual(response.status_code, 200)
            self.contracts.validate("trusted-web-read-error.schema.json", response.get_json())

    def test_v2_has_no_write_routes_and_read_success_does_not_authorize_v1_write(self):
        identity = self.create()
        self.related(identity)
        self.read(identity)
        before = "\n".join(self.db.iterdump())
        for command in ("schedule.create", "schedule.update", "schedule.cancel", "task.complete"):
            response = self.client.post("/api/v2/commands/" + command, json={"contract_version": READ_API, "request": {}},
                                        headers=self.headers())
            self.assertEqual(response.status_code, 404)
        response = self.client.post("/api/v1/commands/schedule.cancel", json={
            "contract_version": "spine.trusted-web-api.v1",
            "expected_access_epoch": str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]),
            "request": {"contract_version": "spine.schedule-cancel.v1", "command_id": "deny-cancel",
                        "actor_subject_id": "owner", "item_id": identity, "target_version": "1",
                        "cancelled_at_utc": AT, "reason_code": "operator_cancelled"},
        }, headers=self.headers())
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertEqual(before, "\n".join(self.db.iterdump()))
        response = self.client.post("/api/v1/commands/schedule.update", json={
            "contract_version": "spine.trusted-web-api.v1",
            "expected_access_epoch": str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]),
            "request": {"contract_version": "spine.schedule-update.v2", "command_id": "deny-update",
                        "actor_subject_id": "owner", "item_id": identity, "target_version": "1", "updated_at_utc": AT,
                        "patch": {"item": {"title": "Changed"}}, "materialization": {"mode": "none"}},
        }, headers=self.headers())
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertEqual(before, "\n".join(self.db.iterdump()))
        task = self.related(identity, command_id="readable-task")
        self.adopt(task, "other")
        self.read(task, subject="other")
        before = "\n".join(self.db.iterdump())
        response = self.client.post("/api/v1/commands/task.complete", json={
            "contract_version": "spine.trusted-web-api.v1",
            "expected_access_epoch": str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]),
            "request": {"command_id": "deny-complete", "actor_subject_id": "other", "item_id": task,
                        "target_version": "1", "completed_at_utc": AT},
        }, headers=self.headers("other"))
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertEqual(before, "\n".join(self.db.iterdump()))

    def test_requested_receipt_is_closed_and_hidden_growth_does_not_change_read(self):
        identity = self.create()
        request = {"item_id": identity, "include": ["authoring_receipt", "related_items"]}
        original = self.read(request=request)["result"]
        for n in range(5):
            self.related(identity, command_id=f"hidden-{n}")
        result = self.read(request=request)["result"]
        self.assertEqual(result, original)
        receipt = result["sections"]["authoring_receipt"]["value"]
        self.assertNotIn("response_json", receipt)
        self.assertNotIn("request_json", receipt)
        self.assertNotIn("target_ref", json.dumps(result))

    def test_capacity_status_and_response_limit_are_v2_specific(self):
        identity = self.create()
        with patch.object(self.reader, "execute", side_effect=WebError("capacity_exceeded")):
            response = self.client.post(PATHS["schedule.show"], json={"contract_version": READ_API, "request": {"item_id": identity}},
                                        headers=self.headers())
        self.assertEqual(response.status_code, 503)
        with patch.dict(self.reader.contracts.bounds, response_bytes=1):
            self.changed("capacity_exceeded", lambda: self.read(identity))

    def test_version_guards_and_agenda_guard_rejection(self):
        identity = self.create()
        self.changed("version_changed", lambda: self.read(identity, guards={"expected_item_version": "2"}))
        self.changed("resource_unavailable", lambda: self.read(identity, subject="other", guards={"expected_item_version": "2"}))
        self.changed("invalid_request", lambda: self.read(route="agenda", request=self.agenda_request(item_ids=[identity]),
                                                          guards={"expected_item_version": "1"}))

    def test_all_sections_have_valid_wire_shapes(self):
        identity = self.create()
        include = list(self.contracts.artifacts["trusted-web-read-projection.v1.json"]["sections"])
        result = self.read(request={"item_id": identity, "include": include})
        self.contracts.validate("trusted-web-read-schedule-response.schema.json", result)
        self.assertEqual(set(result["result"]["sections"]), set(include))
        self.assertTrue(all(section["availability"] == "available" for section in result["result"]["sections"].values()))

    def test_http_serialization_is_bounded_and_precedes_fresh_fence(self):
        identity = self.create()
        self.mutate("UPDATE coordination_item_versions SET title=? WHERE item_id=?", ("é" * 400, identity))
        body = {"contract_version": READ_API, "request": {"item_id": identity}}
        first = self.client.post(PATHS["schedule.show"], json=body, headers=self.headers())
        wire_bytes = len(first.data)
        canonical_bytes = len(canonical_json_bytes(first.get_json()))
        self.assertGreater(wire_bytes, canonical_bytes)
        with patch.dict(self.reader.contracts.bounds, response_bytes=canonical_bytes + 1):
            response = self.client.post(PATHS["schedule.show"], json=body, headers=self.headers())
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["error"]["code"], "capacity_exceeded")
        dumps = self.app.json.dumps
        changed = False
        def serialize(value, **kwargs):
            nonlocal changed
            encoded = dumps(value, **kwargs)
            if isinstance(value, dict) and value.get("ok") and not changed:
                changed = True
                self.mutate("UPDATE coordination_item_versions SET title='Changed at serialization' WHERE item_id=?", (identity,))
            return encoded
        with patch.object(self.app.json, "dumps", side_effect=serialize):
            response = self.client.post(PATHS["schedule.show"], json=body, headers=self.headers())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "version_changed")

    def test_http_concurrency_exhaustion_is_generic_and_does_not_write(self):
        with patch("spine.web.http.threading.BoundedSemaphore") as slots:
            slots.return_value.acquire.return_value = False
            client = create_app(self.service.config).test_client()
        before = "\n".join(self.db.iterdump())
        response = client.get("/api/v2/read-capabilities", headers=self.headers())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], {"code": "capacity_exceeded", "message": "Read unavailable."})
        self.assertEqual(before, "\n".join(self.db.iterdump()))


if __name__ == "__main__":
    unittest.main()
