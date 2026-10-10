"""Public CLI regressions for successor profile catalogs on disposable ledgers."""

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine.commands.cli import main
from spine.ledger.migrate import main as migrate_main

ROOT = Path(__file__).parents[1]
V1 = "spine.notification-profiles.v1"
V2 = "spine.notification-profiles.v2"
NOW = "2035-02-01T12:00:00Z"


class ProfileV2ListingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text()) for p in (ROOT / "contracts/schemas").glob("*.schema.json")]
        cls.registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="spine-profile-list-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "disposable.sqlite"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(migrate_main(["--db", str(self.path), "--initialize-if-empty"]), 0)
        self.counter = 0
        self.subject("operator")

    def cli(self, command, request, *, expected=0):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request))), redirect_stdout(output):
            code = main(["--db", str(self.path), "--input", "-", *command.split(".")])
        response = json.loads(output.getvalue())
        self.assertEqual(code, expected, response)
        self.assertEqual(response["ok"], expected == 0, response)
        if code == 0 and response.get("response_contract") == V2:
            uri = "https://cortext.local/spine/contracts/schemas/notification-profile-responses-v2.schema.json"
            Draft202012Validator(
                {"$ref": uri + "#/$defs/" + command.rsplit(".", 1)[1]}, registry=self.registry, format_checker=FormatChecker()
            ).validate(response)
        return response

    def write(self, command, contract, **fields):
        self.counter += 1
        return self.cli(
            command,
            {
                "contract_version": contract,
                "command_id": f"list-test-{self.counter}",
                "actor_subject_id": "operator",
                "action_timestamp_utc": NOW,
                **fields,
            },
        )

    def subject(self, name):
        self.cli(
            "subject.upsert",
            {
                "command_id": "subject-" + name,
                "actor_subject_id": "operator",
                "subject_id": name,
                "subject_kind": "person",
                "display_name": name,
                "updated_at_utc": NOW,
            },
        )

    def owner(self, subject="operator"):
        return {"owner_kind": "subject", "owner_subject_id": subject}

    def revision(self, version, rendering=None):
        template = {
            "template_key": "hour_before",
            "schedule": {"kind": "once", "at": {"kind": "target_offset", "offset_basis": "elapsed", "offset_seconds": "-3600"}},
            "late_handling": {"kind": "skip"},
        }
        if version == V2:
            template["rendering"] = rendering or {"kind": "ordinary"}
        return {"compatible_item_types": ["event"], "templates": [template]}

    def create(self, key, version=V2, *, subject="operator", rendering=None):
        return self.write(
            "notification_profile.create",
            version,
            owner=self.owner(subject),
            profile_key=key,
            display_name=key,
            description=None,
            revision=self.revision(version, rendering),
        )

    def show(self, created, *, version=V2, revision_id=None, expected=0):
        request = {"contract_version": version, "notification_profile_id": created["notification_profile_id"]}
        if revision_id:
            request["notification_profile_revision_id"] = revision_id
        return self.cli("notification_profile.show", request, expected=expected)

    def listing(self, *, version=V2, limit="500", subject="operator", status="active", cursor=None, expected=0):
        request = {"contract_version": version, "owner": self.owner(subject), "limit": limit}
        if status is not None:
            request["status"] = status
        if cursor is not None:
            request["cursor"] = cursor
        return self.cli("notification_profile.list", request, expected=expected)

    def snapshot(self):
        with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as db:
            return tuple(db.iterdump())

    def test_empty_and_single_ordinary_v2_list_are_schema_valid_and_read_only(self):
        self.assertEqual(self.listing()["entries"], [])
        profile = self.create("ordinary")
        shown = self.show(profile)["notification_profile"]
        before = self.snapshot()
        page = self.listing()
        self.assertEqual(page["entries"], [shown])
        self.assertEqual(page["count"], "1")
        self.assertFalse(page["has_more"])
        self.assertIsNone(page["next_cursor"])
        self.assertEqual(self.listing(limit="1"), page)
        for response in (self.show(profile, version=V1, expected=2), self.listing(version=V1, expected=2)):
            self.assertEqual(response["error"]["code"], "unsupported_contract_version")
            self.assertEqual(response["error"]["field"], "contract_version")
        self.assertEqual(self.snapshot(), before)

    def test_mixed_catalogs_traverse_every_page_without_loss_or_hash_changes(self):
        profiles = [
            self.create(key, version)
            for key, version in (
                ("a_v1", V1),
                ("b_v2", V2),
                ("c_v1", V1),
                ("d_v2", V2),
            )
        ]
        expected = [self.show(profile)["notification_profile"] for profile in profiles]
        before = self.snapshot()
        for limit in ("1", "2", "500"):
            with self.subTest(limit=limit):
                entries, cursor, snapshots = [], None, set()
                while True:
                    page = self.listing(limit=limit, cursor=cursor)
                    self.assertEqual(page["count"], str(len(page["entries"])))
                    entries.extend(page["entries"])
                    snapshots.add(page["catalog_snapshot_hash"])
                    if not page["has_more"]:
                        self.assertIsNone(page["next_cursor"])
                        break
                    self.assertIsNotNone(page["next_cursor"])
                    cursor = page["next_cursor"]
                    self.assertLess(len(entries), len(profiles))
                self.assertEqual(entries, expected)
                self.assertEqual(len(snapshots), 1)
        self.assertEqual(self.snapshot(), before)

    def test_v1_only_catalog_keeps_frozen_projection_and_successor_historical_decoder(self):
        self.create("a_v1", V1)
        self.create("b_v1", V1)
        old_before = self.listing(version=V1)
        successor = self.listing()
        self.assertEqual(successor["catalog_snapshot_hash"], old_before["catalog_snapshot_hash"])
        for entry in successor["entries"]:
            self.assertEqual(entry["revision"]["revision_contract"], V1)
            self.assertNotIn("rendering", entry["revision"]["content"]["templates"][0])
        self.subject("other")
        self.create("other_v2", subject="other")
        self.assertEqual(self.listing(version=V1), old_before)
        first = self.listing(limit="1")
        second = self.listing(limit="1", cursor=first["next_cursor"])
        self.assertEqual(first["entries"] + second["entries"], successor["entries"])
        self.assertFalse(second["has_more"])

    def test_v1_to_v2_revision_history_is_not_rehashed_or_downgraded(self):
        profile = self.create("upgraded", V1)
        old_show = self.show(profile, version=V1)["notification_profile"]
        old_revision = profile["notification_profile_revision_id"]
        self.write(
            "notification_profile.revise",
            V2,
            notification_profile_id=profile["notification_profile_id"],
            expected_current_revision_id=old_revision,
            revision=self.revision(V2),
        )
        before = self.snapshot()
        current = self.show(profile)["notification_profile"]
        self.assertEqual(self.listing()["entries"], [current])
        self.assertEqual(current["revision"]["revision_contract"], V2)
        historical = self.show(profile, revision_id=old_revision)["notification_profile"]["revision"]
        self.assertEqual(historical["revision_contract"], V1)
        self.assertEqual(historical["normalized_revision_hash"], old_show["revision"]["normalized_revision_hash"])
        self.assertEqual(
            historical["content"]["templates"][0]["normalized_template_hash"],
            old_show["revision"]["templates"][0]["normalized_template_hash"],
        )
        self.assertNotIn("rendering", historical["content"]["templates"][0])
        self.assertEqual(self.show(profile, version=V1, expected=2)["error"]["code"], "unsupported_contract_version")
        self.assertEqual(self.snapshot(), before)

    def test_owner_status_filters_limits_and_snapshot_cursor_validation_are_preserved(self):
        retired = self.create("a_v1", V1)
        self.create("b_v2")
        self.create("c_v2")
        self.subject("other")
        self.create("other", subject="other")
        self.write("notification_profile.retire", V1, notification_profile_id=retired["notification_profile_id"], reason_code="test")
        self.assertEqual([e["profile_key"] for e in self.listing(status="retired")["entries"]], ["a_v1"])
        self.assertEqual([e["profile_key"] for e in self.listing(status=None)["entries"]], ["a_v1", "b_v2", "c_v2"])
        self.assertEqual([e["profile_key"] for e in self.listing(subject="other")["entries"]], ["other"])
        for limit in ("0", "501"):
            response = self.listing(limit=limit, expected=1)
            self.assertEqual(response["error"]["code"], "limit_exceeded")
            self.assertEqual(response["error"]["field"], "limit")
        first = self.listing(limit="1")
        for overrides in ({"limit": "2"}, {"status": "retired"}, {"subject": "other"}):
            with self.subTest(overrides=overrides):
                response = self.listing(**({"limit": "1", "cursor": first["next_cursor"], "expected": 2} | overrides))
                self.assertEqual(response["error"]["code"], "invalid_request")
                self.assertEqual(response["error"]["field"], "cursor")
        self.create("d_v1", V1)
        stale = self.listing(limit="1", cursor=first["next_cursor"], expected=6)
        self.assertEqual(stale["error"]["code"], "stale_cursor")
        self.assertEqual(stale["error"]["field"], "cursor")

    def test_definition_pins_survive_successor_list_projection(self):
        schema = self.write(
            "facet_schema.create",
            "spine.facet-schemas.v1",
            owner=self.owner(),
            schema_key="flight",
            definition={
                "display_name": "Flight",
                "description": None,
                "compatible_item_types": ["event"],
                "fields": [{"key": "flight_number", "type": "text", "max_length": "32", "required": True, "queryable": True}],
            },
        )
        definition = self.write(
            "notification_rendering_definition.create",
            "spine.notification-rendering-definitions.v1",
            owner=self.owner(),
            definition_key="flight",
            revision={
                "display_name": "Flight details",
                "description": None,
                "compatible_item_types": ["event"],
                "base_rendering_contract": "spine.notification-rendering.v1",
                "base_rendering_profile": "spine.notification-rendering.concise-en-ca.v1",
                "selections": [
                    {
                        "selection_key": "flight",
                        "facet_key": "flight",
                        "facet_schema_revision_id": schema["facet_schema_revision_id"],
                        "field_key": "flight_number",
                        "label": "Flight",
                        "projection": "value",
                    }
                ],
            },
        )["record"]
        rendering = {
            "kind": "definition",
            "definition": {
                "notification_rendering_definition_id": definition["notification_rendering_definition_id"],
                "notification_rendering_definition_revision_id": definition["current_revision_id"],
            },
        }
        profile = self.create("flight", rendering=rendering)
        shown = self.show(profile)["notification_profile"]
        before = self.snapshot()
        page = self.listing()
        self.assertEqual(page["entries"], [shown])
        self.assertEqual(page["entries"][0]["revision"]["content"]["templates"][0]["rendering"], rendering)
        self.assertEqual(self.snapshot(), before)
