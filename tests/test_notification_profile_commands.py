from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.core.notification_profiles import DYNAMIC_CATALOG_RECEIPT_EFFECTS
from spine.ledger import connect, initialize_schema

ROOT = Path(__file__).parents[1]


class NotificationProfileCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self._subject("subject_agent", "Agent")
        self._subject("subject_owner", "Owner")
        response = handle(
            "delivery_target.upsert",
            {
                "command_id": "profile-route",
                "actor_subject_id": "subject_agent",
                "delivery_target_id": "delivery_target_owner_whatsapp",
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
                "channel": "whatsapp",
                "adapter_name": "openclaw",
                "target_ref": "owner@example",
                "updated_at_utc": "2035-02-01T11:59:00Z",
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)

    def tearDown(self) -> None:
        self.connection.close()

    def test_dynamic_catalog_receipt_effect_vocabulary_is_normative(self) -> None:
        specification = (ROOT / "specs/notification-profiles.md").read_text(
            encoding="utf-8"
        )
        for effect in DYNAMIC_CATALOG_RECEIPT_EFFECTS:
            self.assertIn(f"`{effect}`", specification)

    def test_dynamic_catalog_resolution_revision_and_replay(self) -> None:
        archetype = self._create_archetype()
        profile = self._create_profile()
        binding = self._bind(archetype, profile)

        resolution = handle(
            "notification_profile.resolve",
            {
                "contract_version": "spine.notification-profile-bindings.v1",
                "item_type": "event",
                "item_archetype_id": archetype["item_archetype_id"],
                "scope_chain": [
                    {
                        "owner_kind": "subject",
                        "owner_subject_id": "subject_owner",
                    }
                ],
            },
            self.context,
        )
        self.assertTrue(resolution["ok"], resolution)
        self.assertEqual(resolution["effect"], "notification_profile_resolved")
        self.assertEqual(
            resolution["binding"]["notification_profile_binding_id"],
            binding["notification_profile_binding_id"],
        )

        replay = self._create_profile()
        self.assertEqual(
            replay["notification_profile_id"], profile["notification_profile_id"]
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profiles"
            ).fetchone()[0],
            1,
        )

        revised = handle(
            "notification_profile.revise",
            {
                "contract_version": "spine.notification-profiles.v1",
                "command_id": "profile-revise",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:04Z",
                "notification_profile_id": profile["notification_profile_id"],
                "expected_current_revision_id": profile[
                    "notification_profile_revision_id"
                ],
                "revision": {
                    "compatible_item_types": ["event"],
                    "templates": [
                        self._template("two_days", "-172800"),
                        self._template("day_before", "-86400"),
                    ],
                },
            },
            self.context,
        )
        self.assertTrue(revised["ok"], revised)
        self.assertEqual(revised["revision_number"], "2")

    def test_profile_metadata_update_preserves_revision_binding_and_replays(self) -> None:
        archetype = self._create_archetype()
        profile = self._create_profile()
        binding = self._bind(archetype, profile)
        request = {
            "contract_version": "spine.notification-profile-metadata-update.v1",
            "command_id": "profile-metadata-update",
            "actor_subject_id": "subject_agent",
            "action_timestamp_utc": "2035-02-01T12:00:03Z",
            "notification_profile_id": profile["notification_profile_id"],
            "expected_metadata": {
                "display_name": "Appointment standard",
                "description": "One day before",
            },
            "metadata": {
                "display_name": "Medical appointment standard",
                "description": "One day before",
            },
        }

        updated = handle(
            "notification_profile.metadata.update", request, self.context
        )
        self.assertTrue(updated["ok"], updated)
        self.assertEqual(
            updated["effect"], "notification_profile_metadata_updated"
        )
        self.assertEqual(
            updated["notification_profile_revision_id"],
            profile["notification_profile_revision_id"],
        )
        self.assertEqual(updated["display_name"], "Medical appointment standard")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profile_revisions"
            ).fetchone()[0],
            1,
        )
        audit_payload = json.loads(
            self.connection.execute(
                """SELECT payload_json FROM coordination_catalog_audit_log
                   WHERE resource_kind = 'notification_profile'
                     AND resource_id = ? AND action = 'metadata_updated'""",
                (profile["notification_profile_id"],),
            ).fetchone()[0]
        )
        self.assertEqual(audit_payload["expected_metadata"], request["expected_metadata"])
        self.assertEqual(audit_payload["metadata"], request["metadata"])

        shown = handle(
            "notification_profile.show",
            {
                "contract_version": "spine.notification-profiles.v1",
                "notification_profile_id": profile["notification_profile_id"],
            },
            self.context,
        )
        self.assertEqual(
            shown["notification_profile"]["display_name"],
            "Medical appointment standard",
        )
        self.assertEqual(
            shown["notification_profile"]["current_revision_id"],
            profile["notification_profile_revision_id"],
        )

        resolved = handle(
            "notification_profile.resolve",
            {
                "contract_version": "spine.notification-profile-bindings.v1",
                "item_type": "event",
                "item_archetype_id": archetype["item_archetype_id"],
                "scope_chain": [
                    {
                        "owner_kind": "subject",
                        "owner_subject_id": "subject_owner",
                    }
                ],
            },
            self.context,
        )
        self.assertEqual(
            resolved["binding"]["notification_profile_binding_id"],
            binding["notification_profile_binding_id"],
        )
        self.assertEqual(
            resolved["profile"]["revision"]["notification_profile_revision_id"],
            profile["notification_profile_revision_id"],
        )

        replay = handle(
            "notification_profile.metadata.update", request, self.context
        )
        self.assertEqual(
            replay["receipt"]["command_receipt_id"],
            updated["receipt"]["command_receipt_id"],
        )
        self.assertEqual(
            self.connection.execute(
                """SELECT COUNT(*) FROM coordination_catalog_audit_log
                   WHERE resource_kind = 'notification_profile'
                     AND resource_id = ? AND action = 'metadata_updated'""",
                (profile["notification_profile_id"],),
            ).fetchone()[0],
            1,
        )

        noop = handle(
            "notification_profile.metadata.update",
            {
                **request,
                "command_id": "profile-metadata-noop",
                "action_timestamp_utc": "2035-02-01T12:00:04Z",
                "expected_metadata": dict(request["metadata"]),
            },
            self.context,
        )
        self.assertEqual(
            noop["effect"], "notification_profile_metadata_update_noop"
        )
        self.assertEqual(
            self.connection.execute(
                """SELECT COUNT(*) FROM coordination_catalog_audit_log
                   WHERE resource_kind = 'notification_profile'
                     AND resource_id = ? AND action = 'metadata_updated'""",
                (profile["notification_profile_id"],),
            ).fetchone()[0],
            1,
        )

        stale = handle(
            "notification_profile.metadata.update",
            {
                **request,
                "command_id": "profile-metadata-stale",
                "action_timestamp_utc": "2035-02-01T12:00:05Z",
            },
            self.context,
        )
        self.assertFalse(stale["ok"], stale)
        self.assertEqual(stale["error"]["code"], "stale_version")
        self.assertEqual(stale["error"]["field"], "expected_metadata")

    def test_profile_metadata_update_invalidates_catalog_cursor(self) -> None:
        first = self._create_profile()
        second_request = {
            "contract_version": "spine.notification-profiles.v1",
            "command_id": "profile-create-second",
            "actor_subject_id": "subject_agent",
            "action_timestamp_utc": "2035-02-01T12:00:02Z",
            "owner": {
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
            },
            "profile_key": "appointment_second",
            "display_name": "Appointment second",
            "description": None,
            "revision": {
                "compatible_item_types": ["event"],
                "templates": [self._template("day_before", "-86400")],
            },
        }
        second = handle(
            "notification_profile.create", second_request, self.context
        )
        self.assertTrue(second["ok"], second)
        list_request = {
            "contract_version": "spine.notification-profiles.v1",
            "owner": {
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
            },
            "limit": "1",
        }
        page_one = handle("notification_profile.list", list_request, self.context)
        self.assertTrue(page_one["has_more"])

        updated = handle(
            "notification_profile.metadata.update",
            {
                "contract_version": "spine.notification-profile-metadata-update.v1",
                "command_id": "profile-metadata-cursor",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:03Z",
                "notification_profile_id": first["notification_profile_id"],
                "expected_metadata": {
                    "display_name": "Appointment standard",
                    "description": "One day before",
                },
                "metadata": {
                    "display_name": "Appointment standard corrected",
                    "description": "One day before",
                },
            },
            self.context,
        )
        self.assertTrue(updated["ok"], updated)
        stale = handle(
            "notification_profile.list",
            {**list_request, "cursor": page_one["next_cursor"]},
            self.context,
        )
        self.assertFalse(stale["ok"], stale)
        self.assertEqual(stale["error"]["code"], "stale_cursor")

    def test_profile_aware_schedule_create_is_atomic_and_pinned(self) -> None:
        archetype = self._create_archetype()
        profile = self._create_profile()
        self._bind(archetype, profile)
        request = json.loads(
            (
                ROOT
                / "tests/fixtures/schedule_create/contracts/request_event_repeat_window_materialized.json"
            ).read_text(encoding="utf-8")
        )
        request["contract_version"] = "spine.schedule-create.v2"
        request["command_id"] = "profile-schedule-create"
        request["item"]["archetype"] = {
            "item_archetype_id": archetype["item_archetype_id"],
            "revision_resolution": "current",
            "selection_source": "agent_selected",
            "source_ref": "operator utterance",
        }
        request["notification_plan"] = {
            "mode": "archetype_default",
            "scope_chain": [
                {
                    "owner_kind": "subject",
                    "owner_subject_id": "subject_owner",
                }
            ],
            "on_no_match": "fail",
            "suppress_template_keys": [],
            "replacements": [],
            "custom_additions": [
                {
                    "policy_key": "arrival",
                    "schedule": {
                        "kind": "once",
                        "at": {
                            "kind": "target_offset",
                            "offset_basis": "elapsed",
                            "offset_seconds": "-3600",
                        },
                    },
                    "late_handling": {"kind": "skip"},
                }
            ],
        }

        response = handle("schedule.create", request, self.context)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["response_contract"], "spine.schedule-create-response.v2")
        self._validate_schema("schedule-create-response.schema.json", response)
        self.assertEqual(
            response["notification_profile"]["notification_profile_id"],
            profile["notification_profile_id"],
        )
        self.assertEqual(len(response["policies"]), 2)
        self.assertEqual(
            {
                value["policy_origin"]
                for value in response["notification_profile"]["policy_origins"]
            },
            {"profile_template", "custom_addition"},
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profile_applications"
            ).fetchone()[0],
            1,
        )

        revised = handle(
            "notification_profile.revise",
            {
                "contract_version": "spine.notification-profiles.v1",
                "command_id": "profile-upgrade-source",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:10:00Z",
                "notification_profile_id": profile["notification_profile_id"],
                "expected_current_revision_id": profile[
                    "notification_profile_revision_id"
                ],
                "revision": {
                    "compatible_item_types": ["event"],
                    "templates": [
                        self._template("two_days", "-172800"),
                        self._template("day_before", "-86400"),
                    ],
                },
            },
            self.context,
        )
        self.assertTrue(revised["ok"], revised)
        update = handle(
            "schedule.update",
            {
                "contract_version": "spine.schedule-update.v2",
                "command_id": "profile-schedule-upgrade",
                "actor_subject_id": "subject_agent",
                "item_id": response["item_id"],
                "target_version": "1",
                "updated_at_utc": "2035-02-01T12:11:00Z",
                "patch": {
                    "notification_plan": {
                        "action": "upgrade_current_revision",
                        "suppress_template_keys": [],
                        "replacements": [],
                        "custom_additions": [],
                    }
                },
                "materialization": {"mode": "none"},
            },
            self.context,
        )
        self.assertTrue(update["ok"], update)
        self.assertEqual(update["response_contract"], "spine.schedule-update-response.v2")
        self._validate_schema("schedule-update-response.schema.json", update)
        self.assertEqual(update["current_version"], "2")
        self.assertIn("notification_profile", update["changed_dimensions"])
        upgraded = handle(
            "schedule.show",
            {
                "item_id": response["item_id"],
                "include": ["notification_profile"],
            },
            self.context,
        )
        self.assertEqual(
            upgraded["notification_profile"][
                "pinned_notification_profile_revision_id"
            ],
            revised["notification_profile_revision_id"],
        )
        self.assertFalse(upgraded["notification_profile"]["upgrade_available"])
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profile_application_policies"
            ).fetchone()[0],
            4,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM side_effect_attempts"
            ).fetchone()[0],
            0,
        )
        readback = handle(
            "schedule.show",
            {
                "item_id": response["item_id"],
                "include": ["policies", "notification_profile"],
            },
            self.context,
        )
        self.assertTrue(readback["ok"], readback)
        profile_view = readback["notification_profile"]
        self.assertEqual(
            profile_view["pinned_notification_profile_revision_id"],
            revised["notification_profile_revision_id"],
        )
        self.assertFalse(profile_view["upgrade_available"])
        self.assertFalse(profile_view["effective_policy_diverged"])

        replay = handle("schedule.create", request, self.context)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(replay["effect"], "schedule_create_replay")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profile_applications"
            ).fetchone()[0],
            2,
        )

    def test_direct_schedule_create_remains_profile_free(self) -> None:
        request = json.loads(
            (
                ROOT
                / "tests/fixtures/schedule_create/contracts/request_event_repeat_window_materialized.json"
            ).read_text(encoding="utf-8")
        )
        request["command_id"] = "direct-profile-free-test"
        response = handle("schedule.create", request, self.context)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["response_contract"], "spine.schedule-create-response.v2")
        self.assertEqual(response["notification_profile"]["selection_mode"], "none")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profile_applications"
            ).fetchone()[0],
            0,
        )

    def test_profile_authoring_rejects_duplicate_normalized_templates(self) -> None:
        request = {
            "contract_version": "spine.notification-profiles.v1",
            "command_id": "profile-duplicate-template",
            "actor_subject_id": "subject_agent",
            "action_timestamp_utc": "2035-02-01T12:00:01Z",
            "owner": {
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
            },
            "profile_key": "invalid_duplicate",
            "display_name": "Invalid duplicate",
            "description": None,
            "revision": {
                "compatible_item_types": ["event", "task"],
                "templates": [
                    self._template("first", "-3600"),
                    self._template("second", "-3600"),
                ],
            },
        }
        response = handle(
            "notification_profile.create", request, self.context
        )
        self.assertFalse(response["ok"], response)
        self.assertEqual(response["error"]["code"], "semantic_conflict")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM notification_profiles"
            ).fetchone()[0],
            0,
        )

    def test_catalog_list_cursor_is_snapshot_bound(self) -> None:
        first = self._create_archetype()
        second_request = {
            "contract_version": "spine.item-archetypes.v1",
            "command_id": "archetype-create-second",
            "actor_subject_id": "subject_agent",
            "action_timestamp_utc": "2035-02-01T12:00:01Z",
            "owner": {
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
            },
            "archetype_key": "social_event",
            "revision": {
                "display_name": "Social event",
                "description": None,
                "compatible_item_types": ["event"],
            },
        }
        second = handle(
            "item_archetype.create", second_request, self.context
        )
        self.assertTrue(second["ok"], second)
        list_request = {
            "contract_version": "spine.item-archetypes.v1",
            "owner": {
                "owner_kind": "subject",
                "owner_subject_id": "subject_owner",
            },
            "limit": "1",
        }
        page_one = handle(
            "item_archetype.list", list_request, self.context
        )
        self.assertTrue(page_one["has_more"])
        self.assertIsNotNone(page_one["next_cursor"])
        page_two = handle(
            "item_archetype.list",
            {**list_request, "cursor": page_one["next_cursor"]},
            self.context,
        )
        self.assertTrue(page_two["ok"], page_two)
        self.assertFalse(page_two["has_more"])
        self.assertNotEqual(
            page_one["entries"][0]["item_archetype_id"],
            page_two["entries"][0]["item_archetype_id"],
        )
        revised = handle(
            "item_archetype.revise",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "archetype-revise-cursor",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:03Z",
                "item_archetype_id": first["item_archetype_id"],
                "expected_current_revision_id": first[
                    "item_archetype_revision_id"
                ],
                "revision": {
                    "display_name": "Medical appointment revised",
                    "description": None,
                    "compatible_item_types": ["event"],
                },
            },
            self.context,
        )
        self.assertTrue(revised["ok"], revised)
        stale = handle(
            "item_archetype.list",
            {**list_request, "cursor": page_one["next_cursor"]},
            self.context,
        )
        self.assertFalse(stale["ok"], stale)
        self.assertEqual(stale["error"]["code"], "stale_cursor")

    def _subject(self, subject_id: str, name: str) -> None:
        actor = (
            "subject_agent"
            if self.connection.execute(
                "SELECT 1 FROM subjects WHERE subject_id = 'subject_agent'"
            ).fetchone()
            else subject_id
        )
        response = handle(
            "subject.upsert",
            {
                "command_id": f"seed-{subject_id}",
                "actor_subject_id": actor,
                "subject_id": subject_id,
                "subject_kind": "person",
                "display_name": name,
                "updated_at_utc": "2035-02-01T11:58:00Z",
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)

    def _create_archetype(self) -> dict[str, object]:
        response = handle(
            "item_archetype.create",
            {
                "contract_version": "spine.item-archetypes.v1",
                "command_id": "archetype-create",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:00Z",
                "owner": {
                    "owner_kind": "subject",
                    "owner_subject_id": "subject_owner",
                },
                "archetype_key": "medical_appointment",
                "revision": {
                    "display_name": "Medical appointment",
                    "description": "Reusable appointment classification",
                    "compatible_item_types": ["event"],
                },
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)
        return response

    def _create_profile(self) -> dict[str, object]:
        response = handle(
            "notification_profile.create",
            {
                "contract_version": "spine.notification-profiles.v1",
                "command_id": "profile-create",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:01Z",
                "owner": {
                    "owner_kind": "subject",
                    "owner_subject_id": "subject_owner",
                },
                "profile_key": "appointment_standard",
                "display_name": "Appointment standard",
                "description": "One day before",
                "revision": {
                    "compatible_item_types": ["event"],
                    "templates": [self._template("day_before", "-86400")],
                },
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)
        return response

    def _bind(
        self, archetype: dict[str, object], profile: dict[str, object]
    ) -> dict[str, object]:
        response = handle(
            "notification_profile.binding.set",
            {
                "contract_version": "spine.notification-profile-bindings.v1",
                "command_id": "profile-binding-set",
                "actor_subject_id": "subject_agent",
                "action_timestamp_utc": "2035-02-01T12:00:02Z",
                "owner": {
                    "owner_kind": "subject",
                    "owner_subject_id": "subject_owner",
                },
                "item_archetype_id": archetype["item_archetype_id"],
                "notification_profile_id": profile["notification_profile_id"],
            },
            self.context,
        )
        self.assertTrue(response["ok"], response)
        return response

    @staticmethod
    def _template(key: str, offset_seconds: str) -> dict[str, object]:
        return {
            "template_key": key,
            "schedule": {
                "kind": "once",
                "at": {
                    "kind": "target_offset",
                    "offset_basis": "elapsed",
                    "offset_seconds": offset_seconds,
                },
            },
            "late_handling": {"kind": "skip"},
        }

    @staticmethod
    def _validate_schema(name: str, value: object) -> None:
        schema_dir = ROOT / "contracts/schemas"
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in schema_dir.glob("*.schema.json")
        }
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas.values()
        )
        Draft202012Validator(schemas[name], registry=registry).validate(value)


if __name__ == "__main__":
    unittest.main()
