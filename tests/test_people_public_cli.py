"""Actual public CLI and installed-resource admission on disposable ledgers."""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import test_schedule_operations_command as scheduling

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import CommandContext, handle
from spine.commands.cli import main
from spine.commands.people_runtime import CONTRACT, PeopleContracts
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY, frozen_web_required_contract_versions
from spine.core.errors import SpineValidationError
from spine.ledger import connect
from spine.ledger.identity import read_ledger_instance_id

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src/spine/contracts/people"
AT = "2026-10-24T10:00:00Z"


class PeopleInstalledContractTests(unittest.TestCase):
    def test_complete_packaged_closure_matches_source_and_compiled_local_registry(self):
        from scripts.sync_people_contracts import expected

        expected_files = expected()
        actual = {str(path.relative_to(PACKAGE)): path.read_bytes() for path in PACKAGE.rglob("*.json")}
        self.assertEqual(actual, expected_files)
        installed, source = PeopleContracts.packaged(), PeopleContracts(ROOT)
        self.assertEqual(installed.schemas, source.schemas)
        self.assertEqual(installed.companion, source.companion)
        self.assertEqual(len(installed.schemas), 36)
        for name, entry in installed.companion["commands"].items():
            if entry["local"]:
                self.assertEqual(COMMAND_RUNTIME_CONTRACT_REGISTRY[name].required_contract_versions,
                                 tuple(entry["required_contract_versions"]))
        self.assertIn("spine.schedule-create.v4", COMMAND_RUNTIME_CONTRACT_REGISTRY["schedule.create"].required_contract_versions)
        self.assertNotIn("spine.schedule-create.v4", frozen_web_required_contract_versions("schedule.create"))
        self.assertNotIn(CONTRACT, frozen_web_required_contract_versions("schedule.create"))

    def test_missing_tampered_and_incomplete_declarations_fail_closed_without_source_fallback(self):
        for damage in ("missing", "asset", "pins", "declaration"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "people"
                shutil.copytree(PACKAGE, directory)
                if damage == "missing":
                    (directory / "schemas/types.schema.json").unlink()
                elif damage == "asset":
                    with (directory / "schemas/types.schema.json").open("ab") as stream:
                        stream.write(b" ")
                elif damage == "pins":
                    (directory / "pins.v1.json").write_text("{}")
                versions = IMPLEMENTED_CONTRACT_VERSIONS - {CONTRACT} if damage == "declaration" else IMPLEMENTED_CONTRACT_VERSIONS
                with patch("spine.IMPLEMENTED_CONTRACT_VERSIONS", versions), self.assertRaises(SpineValidationError) as caught:
                    PeopleContracts._packaged_from(directory)
                self.assertEqual(caught.exception.code, "environment_failure:runtime_contracts")

    def test_every_family_selector_result_and_cursor_config_requires_compiled_declaration(self):
        companion = PeopleContracts.packaged().companion
        required = {entry[field] for entry in companion["commands"].values() for field in ("selector", "response_contract")}
        required.add("spine.people-cursor-config.v1")
        for version in sorted(required):
            with self.subTest(version=version), patch("spine.IMPLEMENTED_CONTRACT_VERSIONS", IMPLEMENTED_CONTRACT_VERSIONS - {version}):
                with self.assertRaises(SpineValidationError) as caught:
                    PeopleContracts.packaged()
                self.assertEqual(caught.exception.code, "environment_failure:runtime_contracts")


class PeoplePublicCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scheduling.ScheduleOperationsCommandTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        for person in ("alice", "bob"):
            result = handle("subject.upsert", {"command_id": "seed-" + person, "actor_subject_id": "owner",
                "subject_id": person, "subject_kind": "person", "display_name": person.title(), "updated_at_utc": AT},
                self.fixture.context)
            self.assertTrue(result["ok"], result)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "disposable.sqlite"
        with closing(connect(self.path)) as target:
            self.fixture.connection.backup(target)
        self.cursor_path = self.directory / "cursor.json"
        with closing(connect(self.path)) as db:
            ledger_id = read_ledger_instance_id(db)
        self.cursor_path.write_text(json.dumps({"contract_version": "spine.people-cursor-config.v1", "key_id": "test-key",
            "key_generation": "1", "ledger_instance_id": ledger_id, "secret_hex": "ab" * 32}))
        self.cursor_path.chmod(0o600)

    def cli(self, command, request, *, flags=(), ok=True, environment=None, raw=None):
        output = StringIO()
        text = json.dumps(request) if raw is None else raw
        env = {"SPINE_PEOPLE_CURSOR_CONFIG": str(self.cursor_path)} if environment is None else environment
        with patch.dict(os.environ, env), patch("sys.stdin", StringIO(text)), redirect_stdout(output):
            status = main(["--db", str(self.path), *flags, *command.split(".")])
        result = json.loads(output.getvalue())
        self.assertEqual(result["ok"], ok, result)
        self.assertEqual(status, 0 if ok else {"environment_failure": 7, "stale_version": 5,
            "semantic_conflict": 6, "referenced_row_not_found": 4, "stale_cursor": 6}.get(result["error"]["code"], 2), result)
        return result

    def create(self, *, command="create-v4", task=False, people=None):
        request = self.fixture.task_request(command) if task else self.fixture.event_request(command)
        request["contract_version"] = "spine.schedule-create.v4"
        if task:
            request["item"]["task_detail"].pop("subject_roles", None)
        if people is not None:
            request["people"] = people
        return request

    def state(self):
        with closing(connect(self.path)) as db:
            return "\n".join(db.iterdump())

    def update(self, item, **facts):
        return {"contract_version": CONTRACT, "command_id": "update-people", "actor_subject_id": "owner",
            "item_id": item["item_id"], "target_version": item["current_version"], "updated_at_utc": AT,
            "people": {"participants": ["bob"]}} | facts

    def test_public_create_update_show_history_replay_and_clear(self):
        created = self.cli("schedule.create", self.create(people={"participants": ["bob", "alice"]}))
        self.assertEqual([person["subject_id"] for person in created["people"]], ["alice", "bob"])
        updated = self.cli("item.people.update", self.update(created))
        self.assertEqual(updated["current_version"], "2")
        self.assertFalse(updated["work_changed"])
        before = self.state()
        shown = self.cli("item.people.show", {"contract_version": CONTRACT, "item_id": created["item_id"], "version": "1"})
        self.assertEqual([row["subject_id"] for row in shown["people"]["associations"]], ["alice", "bob"])
        replay = self.cli("item.people.update", self.update(created))
        self.assertEqual(replay["effect"], "item_people_replay")
        self.assertEqual(replay["receipt"], updated["receipt"])
        self.assertEqual(self.state(), before)
        cleared = self.cli("schedule.update", {"contract_version": "spine.schedule-update.v4", "command_id": "clear",
            "actor_subject_id": "owner", "item_id": created["item_id"], "target_version": "2", "updated_at_utc": AT,
            "patch": {"people": {"participants": []}}, "materialization": {"mode": "none"}})
        self.assertEqual(cleared["changed_dimensions"], ["people"])
        self.assertEqual(cleared["people"], [])

    def test_public_dry_run_preserves_state_and_deterministic_ids(self):
        request = self.create(task=True, people={"assignees": ["alice"]})
        before = self.state()
        preview = self.cli("schedule.create", request, flags=("--dry-run",))
        self.assertTrue(preview["dry_run"])
        self.assertEqual(self.state(), before)
        committed = self.cli("schedule.create", request)
        self.assertEqual({key: value for key, value in preview.items() if key != "dry_run"}, committed)
        before = self.state()
        update = self.update(committed, people={"assignees": ["bob"]})
        preview = self.cli("item.people.update", update, flags=("--dry-run",))
        self.assertTrue(preview["dry_run"])
        self.assertEqual(self.state(), before)

    def test_listing_requires_protected_config_and_is_read_only(self):
        request = {"contract_version": CONTRACT, "owner": {"owner_kind": "subject", "owner_subject_id": "alice"}}
        before = self.state()
        result = self.cli("people.list", request)
        self.assertEqual(result["subjects"][0]["subject_id"], "alice")
        self.assertFalse(result["has_more"])
        self.assertEqual(self.state(), before)
        failed = self.cli("people.list", request, environment={"SPINE_PEOPLE_CURSOR_CONFIG": ""}, ok=False)
        self.assertEqual(failed["error"]["field"], "cursor_config")
        self.cursor_path.chmod(0o644)
        failed = self.cli("people.list", request, ok=False)
        self.assertNotIn("ab" * 32, str(failed))
        self.assertEqual(self.state(), before)

    def test_public_group_listing_continues_statelessly_without_durable_read_rows(self):
        with closing(connect(self.path)) as db:
            result = handle("subject_group.upsert", {"command_id": "test-group", "actor_subject_id": "owner",
                "group_id": "test-group", "display_name": "Arbitrary scope", "updated_at_utc": AT}, CommandContext(ledger=db))
            self.assertTrue(result["ok"], result)
            with db:
                db.executemany("INSERT INTO subject_memberships VALUES (?,?,?,?,?,?,?,1)",
                    [("m-" + person, "test-group", person, "member", "active", "2026-01-01T00:00:00Z", None)
                     for person in ("alice", "bob")])
        before = self.state()
        request = {"contract_version": CONTRACT, "owner": {"owner_kind": "subject_group", "owner_group_id": "test-group"},
                   "limit": "1"}
        first = self.cli("people.list", request)
        self.assertEqual(first["subjects"][0]["subject_id"], "alice")
        self.assertTrue(first["next_cursor"].startswith("pc1."))
        second = self.cli("people.list", request | {"cursor": first["next_cursor"]})
        self.assertEqual(second["subjects"][0]["subject_id"], "bob")
        self.assertFalse(second["has_more"])
        self.assertEqual(self.state(), before)

    def test_local_reads_remain_frozen_and_compact_has_no_new_people_fields(self):
        created = self.cli("schedule.create", self.create(people={"participants": ["alice"]}), flags=("--compact",))
        self.assertEqual(created["projection_contract"], "spine.schedule-compact.v1")
        self.assertNotIn("people", created)
        shown = self.cli("schedule.show", {"item_id": created["item_id"], "include": []})
        self.assertNotIn("people", shown)
        request = self.fixture.agenda_request(limit="25")
        request["person_filter"] = {"subject_id": "alice"}
        self.cli("agenda.show", request, ok=False)
        self.cli("item.people.show", {"contract_version": CONTRACT, "item_id": created["item_id"],
            "people_cursor_config": {"secret": "not accepted"}}, ok=False)

    def test_new_family_runtime_assets_fail_before_any_mutation(self):
        before = self.state()
        failure = SpineValidationError("environment_failure:runtime_contracts", "private")
        with patch.object(PeopleContracts, "packaged", side_effect=failure):
            result = self.cli("schedule.create", self.create(), ok=False)
        self.assertEqual(result["error"]["message"], "People operation unavailable.")
        self.assertNotIn("private", str(result))
        self.assertEqual(self.state(), before)

    def test_duplicate_json_and_oversized_new_requests_fail_before_ledger_open(self):
        with patch("spine.commands.cli._open_ledger", side_effect=AssertionError("opened database")):
            self.cli("item.people.show", {}, raw='{"contract_version":"x","contract_version":"y"}', ok=False)
            self.cli("item.people.show", {}, raw='{"padding":"' + "x" * 1048576 + '"}', ok=False)

    def test_old_selectors_and_task_subject_roles_remain_usable(self):
        old = copy.deepcopy(self.fixture.task_request("legacy-task"))
        old["item"]["task_detail"]["subject_roles"] = [{"subject_id": "owner", "role": "assignee"}]
        created = self.cli("schedule.create", old)
        shown = self.cli("item.people.show", {"contract_version": CONTRACT, "item_id": created["item_id"]})
        self.assertEqual(shown["people"]["associations"][0]["subject_id"], "owner")
        v3 = self.fixture.event_request("v3-event")
        v3["contract_version"] = "spine.schedule-create.v3"
        self.assertEqual(self.cli("schedule.create", v3)["response_contract"], "spine.schedule-create-response.v3")
