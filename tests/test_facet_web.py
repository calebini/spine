"""Real-ledger facet admission, disclosure, replay, pagination and HTTP boundaries."""

import copy
import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.commands.facet_runtime import FacetCursorConfig, decode_cursor
from spine.commands.facets import CONTRACTS, WRITES
from spine.web.contracts import validate
from spine.web.errors import WebError
from spine.web.facet_service import FacetService
from spine.web.http import create_app
from spine.web.provisioning import apply, plan
from spine.web.service import WebConfig
from tests import test_trusted_web_runtime as helper
from tests.facet_storage_support import DEFINITION, all_rows

AT = "2026-09-27T10:00:00Z"


class FacetWebTests(unittest.TestCase):
    def setUp(self):
        self.h = helper.TrustedWebRuntimeTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.db, self.config = self.h.db, WebConfig(self.h.path, "test-ledger")
        self.cursor = FacetCursorConfig(b"f" * 32, "facet-ledger", "1")
        self.service = FacetService(self.config, cursor_config=self.cursor, now=lambda: AT)
        self.number = 0
        self.archetype = self.local(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "facet-archetype",
                "actor_subject_id": "owner",
                "action_timestamp_utc": AT,
                "owner": self.owner(),
                "archetype_key": "flight",
                "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event", "task"]},
            },
        )

    def owner(self, subject="owner"):
        return {"owner_kind": "subject", "owner_subject_id": subject}

    def local(self, command, request):
        result = handle(command, request, self.h.ctx)
        self.assertTrue(result["ok"], result)
        return result

    def body(self, command, **request):
        self.number += 1
        body = {"request": {"contract_version": CONTRACTS[command], **request}}
        if command in WRITES:
            body["expected_access_epoch"] = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
            body["request"].update(command_id=f"facet-web-{self.number}", actor_subject_id="owner", action_timestamp_utc=AT)
        return body

    def run_command(self, command, body=None, *, subject="owner", service=None, selection="selection", **request):
        body = body or self.body(command, **request)
        return (service or self.service).execute(command, body, self.h.accounts[subject], selection)["result"]

    def denied(self, code, command, body, *, subject="owner", service=None):
        before = all_rows(self.db)
        with self.assertRaises(WebError) as caught:
            self.run_command(command, body, subject=subject, service=service)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(all_rows(self.db), before)

    def catalog(self, key="flight"):
        schema = self.run_command("facet_schema.create", owner=self.owner(), schema_key=key, definition=DEFINITION)
        binding = self.run_command(
            "item_archetype.facet_binding.set",
            item_archetype_id=self.archetype["item_archetype_id"],
            facet_key=key,
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            expected_binding_id=None,
        )
        return schema, binding

    def event(self):
        body = self.h.event()
        body["request"]["item"]["archetype"] = {
            "item_archetype_id": self.archetype["item_archetype_id"],
            "item_archetype_revision_id": self.archetype["item_archetype_revision_id"],
            "selection_source": "operator_explicit",
            "revision_resolution": "exact",
        }
        return self.h.run_command("schedule.create", body)["result"]

    def update(self, event, schema, binding, **values):
        version = str(self.db.execute("SELECT current_version FROM coordination_items WHERE item_id=?", (event["item_id"],)).fetchone()[0])
        return self.body(
            "item.facets.update",
            item_id=event["item_id"],
            expected_item_version=version,
            changes=[
                {
                    "op": "set",
                    "facet_key": binding["facet_key"],
                    "expected_binding_id": binding["facet_binding_id"],
                    "facet_schema_revision_id": schema["facet_schema_revision_id"],
                    "values": {"flight": "AB123", **values},
                }
            ],
        )

    def grant(self, kind, resource, operations, *, subject="other", starts="2026-01-01T00:00:00Z", ends=None):
        if "catalog.use" in operations and "catalog.read" not in operations:
            operations = ["catalog.read", *operations]
        self.number += 1
        epoch = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        request = {
            "contract_version": "spine.trusted-web-provisioning.v2",
            "ledger_id": "test-ledger",
            "expected_access_epoch": epoch,
            "grants": [
                {
                    "operation": "create",
                    "resource_kind": kind,
                    "resource_id": resource,
                    "resource_owner_revision": "1",
                    "grantee": self.owner(subject),
                    "operations": operations,
                    "starts_at_utc": starts,
                    "ends_at_utc": ends,
                }
            ],
        }
        planned = plan(self.db, request)
        self.assertTrue(planned["can_apply"], planned)
        validate("trusted-web-provisioning-plan-response.v2.schema.json", planned)
        result = apply(
            self.db,
            {
                "contract_version": request["contract_version"],
                "command_id": f"grant-{self.number}",
                "actor_subject_id": "owner",
                "action_timestamp_utc": AT,
                "expected_access_epoch": epoch,
                "plan": planned,
            },
        )
        validate("trusted-web-provisioning-apply-response.v2.schema.json", result)
        return result

    def test_local_and_web_contracts_keep_separate_admission(self):
        schema, binding = self.catalog()
        event = self.event()
        write = self.update(event, schema, binding, person="owner")
        first = self.run_command("item.facets.update", write)
        self.assertTrue(first["changed"])
        before = all_rows(self.db)
        replay = self.run_command("item.facets.update", write, selection="new-session")
        self.assertTrue(replay["replayed"])
        shown = self.run_command("item.facets.show", item_id=event["item_id"])
        self.assertEqual(shown["entries"][0]["values"]["person"], "owner")
        self.assertEqual(all_rows(self.db), before)
        self.denied("resource_unavailable", "item.facets.show", self.body("item.facets.show", item_id=event["item_id"]), subject="other")
        foreign = copy.deepcopy(write)
        foreign["request"]["actor_subject_id"] = "other"
        self.denied("command_id_unavailable", "item.facets.update", foreign, subject="other")

    def test_nonpredicate_reference_query_and_full_show_denial(self):
        schema, binding = self.catalog()
        event = self.event()
        request = self.update(event, schema, binding, person="other")
        self.denied("resource_unavailable", "item.facets.update", request)
        self.local("item.facets.update", request["request"])
        self.denied("resource_unavailable", "item.facets.show", self.body("item.facets.show", item_id=event["item_id"]))
        query = self.body(
            "item.facets.query",
            owner=self.owner(),
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            field="flight",
            value="AB123",
        )
        result = self.run_command("item.facets.query", query)
        self.assertEqual(result["items"], [{"item_id": event["item_id"], "item_version": "2"}])
        query["request"].update(field="airport", value="hidden-airport")
        self.denied("resource_unavailable", "item.facets.query", query)
        removal = self.body(
            "item.facets.update", item_id=event["item_id"], expected_item_version="2", changes=[{"op": "remove", "facet_key": "flight"}]
        )
        self.assertTrue(self.run_command("item.facets.update", removal)["changed"])

    def test_foreign_catalog_subset_and_item_definition_publication(self):
        schema, binding = self.catalog()
        self.catalog("secret")
        event = self.event()
        self.run_command("item.facets.update", self.update(event, schema, binding))
        self.grant("facet_schema", schema["facet_schema_id"], ["catalog.read"])
        listed = self.run_command("facet_schema.list", subject="other", owner=self.owner())
        self.assertEqual([r["facet_schema_id"] for r in listed["schemas"]], [schema["facet_schema_id"]])
        self.grant("item", event["item_id"], ["item.read"])
        self.run_command("item.facets.show", subject="other", item_id=event["item_id"], item_version="2")
        # Catalog read is not needed for item-published definitions.
        with self.db:
            self.db.execute("UPDATE access_grants SET status='revoked' WHERE resource_kind='facet_schema'")
        self.run_command("item.facets.show", subject="other", item_id=event["item_id"])
        self.denied(
            "resource_unavailable",
            "facet_schema.show",
            self.body("facet_schema.show", facet_schema_id=schema["facet_schema_id"]),
            subject="other",
        )

    def test_replay_retained_read_after_edit_and_catalog_use_revocation(self):
        schema, binding = self.catalog()
        event = self.event()
        self.grant("item", event["item_id"], ["item.read", "item.edit"])
        self.grant("item_archetype", self.archetype["item_archetype_id"], ["catalog.use"])
        self.grant("facet_schema", schema["facet_schema_id"], ["catalog.use"])
        request = self.update(event, schema, binding)
        request["request"]["actor_subject_id"] = "other"
        self.run_command("item.facets.update", request, subject="other")
        # Fixture revocation preserves an independent read grant.
        self.grant("item", event["item_id"], ["item.read"])
        with self.db:
            self.db.execute(
                "UPDATE access_grants SET status='revoked' WHERE resource_kind!='item' OR grant_id IN "
                "(SELECT grant_id FROM access_grant_operations WHERE operation='item.edit')"
            )
        before = all_rows(self.db)
        self.assertTrue(self.run_command("item.facets.update", request, subject="other")["replayed"])
        self.assertEqual(all_rows(self.db), before)
        with self.db:
            self.db.execute("UPDATE access_grants SET status='revoked'")
        self.denied("resource_unavailable", "item.facets.update", request, subject="other")

    def test_page_source_race_revocation_timing_and_context(self):
        a, _ = self.catalog("a")
        b, _ = self.catalog("b")
        request = self.body("facet_schema.list", owner=self.owner(), limit="1")
        page = self.run_command("facet_schema.list", request)
        cursor = {"request": {**request["request"], "cursor": page["next_cursor"]}}
        with self.assertRaises(WebError) as caught:
            self.run_command("facet_schema.list", cursor, selection="switched")
        self.assertEqual(caught.exception.code, "access_changed")

        def change(_):
            self.local(
                "facet_schema.publish",
                self.body(
                    "facet_schema.publish",
                    facet_schema_id=a["facet_schema_id"],
                    expected_current_revision_id=a["facet_schema_revision_id"],
                    definition={**DEFINITION, "display_name": "changed"},
                )["request"],
            )

        service = FacetService(self.config, cursor_config=self.cursor, now=lambda: AT, before_release=change)
        with self.assertRaises(WebError) as caught:
            self.run_command("facet_schema.list", request, service=service)
        self.assertEqual(caught.exception.code, "access_changed")
        self.grant("facet_schema", a["facet_schema_id"], ["catalog.read"], ends="2026-09-27T10:01:00Z")
        self.grant("facet_schema", b["facet_schema_id"], ["catalog.read"], starts="2026-09-27T10:01:00Z")
        # A relevant future grant must make even the first page fail if its boundary passes at release.
        clock = [AT]
        service = FacetService(
            self.config,
            cursor_config=self.cursor,
            now=lambda: clock[0],
            before_release=lambda _: clock.__setitem__(0, "2026-09-27T10:01:00Z"),
        )
        before = all_rows(self.db)
        with self.assertRaises(WebError) as caught:
            self.run_command("facet_schema.list", request, subject="other", service=service)
        self.assertEqual(caught.exception.code, "access_changed")
        self.assertEqual(all_rows(self.db), before)

    def test_http_closed_routes_and_configuration(self):
        client = create_app(self.config, facet_cursor_config=self.cursor).test_client()
        headers = {
            "Host": self.config.host,
            "Origin": self.config.origin,
            "Content-Type": "application/json",
            "X-Spine-Account-ID": self.h.accounts["owner"],
            "X-Spine-Selection-ID": "s",
        }
        body = self.body("facet_schema.create", owner=self.owner(), schema_key="http", definition=DEFINITION)
        result = client.post("/api/v1/facets/commands/facet_schema.create", headers=headers, json=body)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertEqual(client.post("/api/v1/commands/facet_schema.create", headers=headers, json=body).status_code, 404)
        self.assertEqual(client.post("/api/v1/facets/commands/web_access.apply", headers=headers, json=body).status_code, 404)
        self.assertEqual(
            client.post(
                "/api/v1/facets/commands/facet_schema.create", headers={**headers, "Origin": "https://evil"}, json=body
            ).status_code,
            403,
        )
        self.assertEqual(client.get("/api/v1/facets/capabilities", headers=headers).status_code, 200)
        service = FacetService(self.config)
        self.denied("admission_unavailable", "facet_schema.list", self.body("facet_schema.list", owner=self.owner()), service=service)

    def test_protected_precommit_failure_rolls_back_all_evidence(self):
        request = self.body("facet_schema.create", owner=self.owner(), schema_key="fail", definition=DEFINITION)
        service = FacetService(self.config, before_release=lambda db: db.execute("UPDATE web_operators SET eligible=0"))
        self.denied("access_changed", "facet_schema.create", request, service=service)

    def test_catalog_write_matrix_replays_after_admin_demotion_and_retirement(self):
        self.local(
            "subject_group.upsert",
            {"command_id": "facet-group", "actor_subject_id": "owner", "group_id": "group", "display_name": "Group", "updated_at_utc": AT},
        )
        self.h.provision(
            memberships=[
                {"operation": "create", "group_id": "group", "subject_id": s, "role": role, "starts_at_utc": helper.AT}
                for s, role in (("owner", "owner"), ("other", "admin"))
            ]
        )
        group = {"owner_kind": "subject_group", "owner_group_id": "group"}
        archetype = self.local(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "group-archetype",
                "actor_subject_id": "owner",
                "action_timestamp_utc": AT,
                "owner": group,
                "archetype_key": "flight",
                "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event"]},
            },
        )
        recorded = []

        def execute(command, **kw):
            body = self.body(command, **kw)
            body["request"]["actor_subject_id"] = "other"
            result = self.run_command(command, body, subject="other")
            recorded.append((command, body, result))
            return result

        schema = execute("facet_schema.create", owner=group, schema_key="flight", definition=DEFINITION)
        for name in (DEFINITION["display_name"], "Revised"):
            schema = execute(
                "facet_schema.publish",
                facet_schema_id=schema["facet_schema_id"],
                expected_current_revision_id=schema["facet_schema_revision_id"],
                definition={**DEFINITION, "display_name": name},
            )
        binding = execute(
            "item_archetype.facet_binding.set",
            item_archetype_id=archetype["item_archetype_id"],
            facet_key="flight",
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            expected_binding_id=None,
        )
        execute(
            "item_archetype.facet_binding.set",
            item_archetype_id=archetype["item_archetype_id"],
            facet_key="flight",
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            expected_binding_id=binding["facet_binding_id"],
        )
        for expected in (binding["facet_binding_id"], None):
            execute(
                "item_archetype.facet_binding.remove",
                item_archetype_id=archetype["item_archetype_id"],
                facet_key="flight",
                expected_binding_id=expected,
            )
        for _ in range(2):
            execute(
                "facet_schema.retire",
                facet_schema_id=schema["facet_schema_id"],
                expected_current_revision_id=schema["facet_schema_revision_id"],
            )
        membership = self.db.execute("SELECT * FROM subject_memberships WHERE subject_id='other'").fetchone()
        self.h.provision(
            memberships=[{"operation": "set", "membership_id": membership["membership_id"], "expected_revision": "1", "role": "member"}]
        )
        before = all_rows(self.db)
        for command, body, original in recorded:
            replay = self.run_command(command, body, subject="other", selection="new-session")
            self.assertTrue(replay["replayed"])
            self.assertFalse(replay["changed"])
            self.assertEqual(replay["command_receipt_id"], original["command_receipt_id"])
        self.assertEqual(all_rows(self.db), before)
        request = self.body("facet_schema.create", owner=group, schema_key="member_mutation", definition=DEFINITION)
        request["request"]["actor_subject_id"] = "other"
        self.denied("resource_unavailable", "facet_schema.create", request, subject="other")
        # Member still reads catalog data; creator status does not imply administration.
        self.run_command("facet_schema.show", subject="other", facet_schema_id=schema["facet_schema_id"])

    def test_hidden_binding_schema_denies_complete_list_and_query_honors_foreign_item_grant(self):
        schema, binding = self.catalog()
        event = self.event()
        self.run_command("item.facets.update", self.update(event, schema, binding))
        self.grant("item_archetype", self.archetype["item_archetype_id"], ["catalog.read"])
        self.denied(
            "resource_unavailable",
            "item_archetype.facet_binding.list",
            self.body("item_archetype.facet_binding.list", item_archetype_id=self.archetype["item_archetype_id"]),
            subject="other",
        )
        self.grant("facet_schema", schema["facet_schema_id"], ["catalog.read"])
        self.grant("item", event["item_id"], ["item.read"])
        query = self.body(
            "item.facets.query",
            owner=self.owner(),
            facet_schema_revision_id=schema["facet_schema_revision_id"],
            field="flight",
            value="AB123",
        )
        self.assertEqual(len(self.run_command("item.facets.query", query, subject="other")["items"]), 1)
        self.run_command("item_archetype.facet_binding.list", subject="other", item_archetype_id=self.archetype["item_archetype_id"])

    def test_replay_noop_foreign_local_receipt_and_semantic_mismatch_precedence(self):
        schema, binding = self.catalog()
        event = self.event()
        self.run_command("item.facets.update", self.update(event, schema, binding))
        noop = self.update(event, schema, binding)
        self.assertFalse(self.run_command("item.facets.update", noop)["changed"])
        self.assertTrue(self.run_command("item.facets.update", noop)["replayed"])
        mismatch = copy.deepcopy(noop)
        mismatch["request"]["changes"][0]["values"]["flight"] = "different"
        self.denied("domain_conflict", "item.facets.update", mismatch)
        foreign = copy.deepcopy(mismatch)
        foreign["request"]["actor_subject_id"] = "other"
        self.denied("command_id_unavailable", "item.facets.update", foreign, subject="other")
        local = self.body("facet_schema.create", owner=self.owner(), schema_key="local", definition=DEFINITION)
        self.local("facet_schema.create", local["request"])
        self.denied("command_id_unavailable", "facet_schema.create", local)

    def test_real_revocation_release_and_shared_proof_capacity(self):
        schema, _ = self.catalog()
        self.grant("facet_schema", schema["facet_schema_id"], ["catalog.read"])

        def revoke(_):
            with self.db:
                self.db.execute("UPDATE access_grants SET status='revoked'")

        service = FacetService(self.config, cursor_config=self.cursor, now=lambda: AT, before_release=revoke)
        with self.assertRaises(WebError) as caught:
            self.run_command("facet_schema.show", subject="other", service=service, facet_schema_id=schema["facet_schema_id"])
        self.assertEqual(caught.exception.code, "access_changed")
        from spine.web.facet_authorization import FacetPermissions

        calls = []
        original = FacetPermissions.proof

        def exhaust(p, selection):
            calls.append(p.budget)
            if len(calls) == 2:
                p.budget.steps = 100001
            return original(p, selection)

        before = all_rows(self.db)
        with patch.object(FacetPermissions, "proof", exhaust), self.assertRaises(WebError) as caught:
            self.run_command("facet_schema.list", owner=self.owner())
        self.assertEqual(caught.exception.code, "capacity_exceeded")
        self.assertIs(calls[0], calls[1])
        self.assertEqual(all_rows(self.db), before)

    def test_cursor_continuation_keeps_deadline_and_rejects_rotation_expiry_and_grant_changes(self):
        schemas = [self.catalog(key)[0] for key in ("a", "b", "c")]
        for schema in schemas:
            self.grant("facet_schema", schema["facet_schema_id"], ["catalog.read"], ends="2026-09-27T10:10:00Z")
        request = self.body("facet_schema.list", owner=self.owner(), limit="1")
        first = self.run_command("facet_schema.list", request, subject="other")
        continuation = {"request": {**request["request"], "cursor": first["next_cursor"]}}
        later = FacetService(self.config, cursor_config=self.cursor, now=lambda: "2026-09-27T10:01:00Z")
        second = self.run_command("facet_schema.list", continuation, subject="other", service=later)
        a, b = (decode_cursor(self.cursor, token) for token in (first["next_cursor"], second["next_cursor"]))
        for field in ("issued_at_utc", "expires_at_utc", "authorization_valid_until_utc"):
            self.assertEqual(a[field], b[field])
        self.assertEqual(a["authorization_valid_until_utc"], "2026-09-27T10:10:00Z")
        for config, code in (
            (FacetCursorConfig(b"x" * 32, "facet-ledger", "1"), "invalid_request"),
            (FacetCursorConfig(b"f" * 32, "facet-ledger", "2"), "access_changed"),
            (FacetCursorConfig(b"f" * 32, "clone-ledger", "1"), "access_changed"),
        ):
            self.denied(
                code,
                "facet_schema.list",
                continuation,
                subject="other",
                service=FacetService(self.config, cursor_config=config, now=lambda: AT),
            )
        self.denied(
            "access_changed",
            "facet_schema.list",
            continuation,
            subject="other",
            service=FacetService(self.config, cursor_config=self.cursor, now=lambda: "2026-09-27T10:10:00Z"),
        )
        # Proof includes granted facts even when a redundant grant changes no candidate.
        self.grant("facet_schema", schemas[0]["facet_schema_id"], ["catalog.read"])
        self.denied("access_changed", "facet_schema.list", continuation, subject="other")
        # Hidden authority is checked before malformed cursor contents.
        hidden = self.body(
            "item.facets.query",
            owner=self.owner(),
            facet_schema_revision_id=schemas[0]["facet_schema_revision_id"],
            field="flight",
            value="AB123",
            cursor="not-a-token",
        )
        with self.db:
            self.db.execute("UPDATE access_grants SET status='revoked'")
        self.denied("resource_unavailable", "item.facets.query", hidden, subject="other")

    def test_system_mutation_denied_and_access_proof_row_limit_is_not_a_partial_page(self):
        self.denied(
            "resource_unavailable",
            "facet_schema.create",
            self.body("facet_schema.create", owner={"owner_kind": "system"}, schema_key="system", definition=DEFINITION),
        )
        schema, _ = self.catalog()
        # Five identity rows plus 48 grant/operation pairs exceeds the combined 100-row limit.
        for _ in range(48):
            self.grant("facet_schema", schema["facet_schema_id"], ["catalog.read"])
        self.denied("capacity_exceeded", "facet_schema.list", self.body("facet_schema.list", owner=self.owner()), subject="other")

    def test_provisioning_v2_is_local_replay_safe_and_v1_remains_closed(self):
        schema, _ = self.catalog()
        epoch = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        request = {
            "contract_version": "spine.trusted-web-provisioning.v2",
            "ledger_id": "test-ledger",
            "expected_access_epoch": epoch,
            "grants": [
                {
                    "operation": "create",
                    "resource_kind": "facet_schema",
                    "resource_id": schema["facet_schema_id"],
                    "resource_owner_revision": "1",
                    "grantee": self.owner("other"),
                    "operations": ["catalog.read"],
                    "starts_at_utc": AT,
                    "ends_at_utc": None,
                }
            ],
        }
        self.assertFalse(handle("web_access.plan", {**request, "contract_version": "spine.trusted-web-provisioning.v1"}, self.h.ctx)["ok"])
        planned = self.local("web_access.plan", request)
        self.assertTrue(planned["can_apply"])
        write = {
            "contract_version": request["contract_version"],
            "command_id": "local-grant-v2",
            "actor_subject_id": "owner",
            "action_timestamp_utc": AT,
            "expected_access_epoch": epoch,
            "plan": planned,
        }
        self.local("web_access.apply", write)
        before = all_rows(self.db)
        self.assertTrue(self.local("web_access.apply", write)["replayed"])
        self.assertEqual(all_rows(self.db), before)
        self.run_command("facet_schema.show", subject="other", facet_schema_id=schema["facet_schema_id"])
        # Wrong catalog owner generation is rejected by planning, before mutation.
        request["expected_access_epoch"] = str(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0])
        request["grants"][0]["resource_owner_revision"] = "2"
        self.assertFalse(self.local("web_access.plan", request)["can_apply"])
