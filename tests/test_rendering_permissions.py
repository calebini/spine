"""Selected-account role boundaries; requests never choose their admission."""

import copy
from dataclasses import replace
from datetime import timedelta

from spine.commands import handle, rendering_candidate
from spine.commands.facet_runtime import parse_time, wire_time
from spine.commands.rendering_runtime import RenderingAdmission
from spine.web.provisioning import apply, plan
from tests import test_rendering_authoring_foundation as foundation
from tests.facet_storage_support import DEFINITION, NOW


class RenderingPermissionTests(foundation.RenderingFoundationTests):
    def setUp(self):
        super().setUp()
        for command, fields in (
            ("subject.upsert", {"subject_id": "member", "subject_kind": "person", "display_name": "Member"}),
            ("subject_group.upsert", {"group_id": "test-group", "display_name": "Test group"}),
        ):
            result = handle(command, {"command_id": command, "actor_subject_id": "owner", "updated_at_utc": NOW} | fields, self.context)
            self.assertTrue(result["ok"], result)
        proposed = plan(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "ledger_id": "test-ledger",
                "expected_access_epoch": "0",
                "operators": [
                    {"operation": "create", "subject_id": s, "display_name": s, "activation_basis": "trusted_local_approval"}
                    for s in ("owner", "member")
                ],
                "memberships": [
                    {"operation": "create", "subject_id": s, "group_id": "test-group", "role": role, "starts_at_utc": NOW}
                    for s, role in (("owner", "owner"), ("member", "member"))
                ],
            },
        )
        self.assertTrue(proposed["can_apply"], proposed)
        apply(
            self.db,
            {
                "contract_version": "spine.trusted-web-provisioning.v1",
                "command_id": "accounts",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "expected_access_epoch": "0",
                "plan": proposed,
            },
        )
        self.accounts = {r["subject_id"]: r["account_id"] for r in self.db.execute("SELECT * FROM account_subject_bindings")}
        self.group_scope = {"owner_kind": "subject_group", "owner_group_id": "test-group"}
        schema = handle(
            "facet_schema.create",
            {
                "contract_version": "spine.facet-schemas.v1",
                "command_id": "group-schema",
                "actor_subject_id": "owner",
                "action_timestamp_utc": NOW,
                "owner": self.group_scope,
                "schema_key": "flight",
                "definition": DEFINITION,
            },
            self.context,
        )
        self.group_revision = copy.deepcopy(self.revision)
        self.group_revision["selections"][0]["facet_schema_revision_id"] = schema["facet_schema_revision_id"]

    def execute_as(self, subject, command, request):
        return rendering_candidate.execute(
            command,
            request,
            self.context,
            now=NOW,
            cursor_config=self.config,
            admission=RenderingAdmission("permission_enforced", self.accounts[subject], "trusted-web"),
        )

    def test_member_reads_group_catalog_but_cannot_author_or_spoof_actor(self):
        request = self.request(
            "notification_rendering_definition.create", owner=self.group_scope, definition_key="group-flight", revision=self.group_revision
        )
        created = self.execute_as("owner", "notification_rendering_definition.create", request)
        self.assertTrue(created["ok"], created)
        root = created["record"]
        shown = self.execute_as(
            "member",
            "notification_rendering_definition.show",
            self.request(
                "notification_rendering_definition.show", notification_rendering_definition_id=root["notification_rendering_definition_id"]
            ),
        )
        self.assertTrue(shown["ok"], shown)
        denied = self.execute_as(
            "member",
            "notification_rendering_definition.create",
            request | {"command_id": "member-create", "actor_subject_id": "member", "definition_key": "other"},
        )
        self.assertEqual(denied["error"]["code"], "permission_denied")
        spoofed = self.execute_as("member", "notification_rendering_definition.create", request | {"command_id": "spoofed"})
        self.assertEqual(spoofed["error"]["code"], "permission_denied")
        private = self.create("private-flight")["record"]
        denied = self.execute_as(
            "member",
            "notification_rendering_definition.show",
            self.request(
                "notification_rendering_definition.show",
                notification_rendering_definition_id=private["notification_rendering_definition_id"],
            ),
        )
        self.assertEqual(denied["error"]["code"], "permission_denied")
        page = self.execute_as(
            "member",
            "notification_rendering_definition.list",
            self.request("notification_rendering_definition.list", owner=self.scope, status="active", limit="1"),
        )
        self.assertTrue(page["ok"], page)
        self.assertEqual(page["records"], [])
        self.assertFalse(page["has_more"])

    def test_protected_location_authoring_denied_and_private_cursor_config_required(self):
        revision = copy.deepcopy(self.group_revision)
        revision["selections"][0].update(field_key="airport", projection="location_label", label="Airport")
        request = self.request(
            "notification_rendering_definition.create", owner=self.group_scope, definition_key="airport", revision=revision
        )
        denied = self.execute_as("owner", "notification_rendering_definition.create", request)
        self.assertEqual(denied["error"]["code"], "permission_denied")
        # The same exact model is allowed in explicitly trusted-local mode.
        local = rendering_candidate.execute("notification_rendering_definition.create", request, self.context, now=NOW)
        self.assertTrue(local["ok"], local)
        for limit in ("0", "101", "01", 1):
            bad = self.execute_as(
                "owner",
                "notification_rendering_definition.list",
                self.request("notification_rendering_definition.list", owner=self.group_scope, status="active", limit=limit),
            )
            self.assertFalse(bad["ok"])
        bad_config = replace(self.config, secret=b"short")
        bad = rendering_candidate.execute(
            "notification_rendering_definition.list",
            self.request("notification_rendering_definition.list", owner=self.scope, status="active", limit="1"),
            self.context,
            cursor_config=bad_config,
            now=NOW,
        )
        self.assertEqual(bad["error"]["code"], "environment_failure")

    def test_cursor_cannot_cross_account_expiry_or_key_rotation(self):
        for key in ("a", "b"):
            self.call("notification_rendering_definition.create", owner=self.group_scope, definition_key=key, revision=self.group_revision)
        request = self.request("notification_rendering_definition.list", owner=self.group_scope, status="active", limit="1")
        first = self.execute_as("owner", "notification_rendering_definition.list", request)
        continued = request | {"cursor": first["next_cursor"]}
        crossed = self.execute_as("member", "notification_rendering_definition.list", continued)
        self.assertEqual(crossed["error"]["code"], "stale_cursor")
        later = wire_time(parse_time(NOW) + timedelta(seconds=901))
        expired = rendering_candidate.execute(
            "notification_rendering_definition.list",
            continued,
            self.context,
            cursor_config=self.config,
            now=later,
            admission=RenderingAdmission("permission_enforced", self.accounts["owner"], "trusted-web"),
        )
        self.assertEqual(expired["error"]["code"], "stale_cursor")
        rotated = rendering_candidate.execute(
            "notification_rendering_definition.list",
            continued,
            self.context,
            cursor_config=replace(self.config, key_generation="new"),
            now=NOW,
            admission=RenderingAdmission("permission_enforced", self.accounts["owner"], "trusted-web"),
        )
        self.assertEqual(rotated["error"]["code"], "stale_cursor")
