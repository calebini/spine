"""RR-01–11 executable proofs on disposable ledgers; no external adapters/sends."""

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS, __version__
from spine.commands import CommandContext, handle
from spine.commands import facet_revision_readback as readback
from spine.commands.cli import main
from spine.commands.facet_runtime import FacetBudget
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY, missing_runtime_contract_versions
from spine.ledger import connect
from spine.ledger import facets as storage
from spine.ledger.migrate import main as migrate_main
from tests.facet_storage_support import DEFINITION, NOW, all_rows

ROOT = Path(__file__).parents[1]
COMMAND = readback.COMMAND
CONTRACT = readback.CONTRACT


class FacetSchemaRevisionReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text()) for p in (ROOT / "contracts/schemas").glob("*.schema.json")]
        cls.registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="spine-revision-readback-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "disposable.sqlite"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(migrate_main(["--db", str(self.path), "--initialize-if-empty"]), 0)
        self.counter = 0
        self.cli("subject.upsert", {
            "command_id": "owner", "actor_subject_id": "owner", "subject_id": "owner", "subject_kind": "person",
            "display_name": "Owner", "updated_at_utc": NOW,
        })
        self.a = self.create("a")
        self.b = self.create("b")
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        self.context = CommandContext(ledger=self.db)

    def cli(self, command, request, *, expected=0, dry_run=False):
        output = io.StringIO()
        args = ["--db", str(self.path), "--input", "-", *command.split(".")]
        if dry_run:
            args.append("--dry-run")
        with patch("sys.stdin", io.StringIO(json.dumps(request))), redirect_stdout(output):
            code = main(args)
        response = json.loads(output.getvalue())
        self.assertEqual(code, expected, response)
        self.assertEqual(response["ok"], expected == 0, response)
        if command == COMMAND:
            name = "response" if response["ok"] else "failure"
            uri = f"https://cortext.local/spine/contracts/schemas/facet-schema-revision-show-{name}.schema.json"
            Draft202012Validator({"$ref": uri}, registry=self.registry).validate(response)
        return response

    def write(self, command, **fields):
        self.counter += 1
        return self.cli(command, {
            "contract_version": "spine.facet-schemas.v1", "command_id": f"revision-{self.counter}",
            "actor_subject_id": "owner", "action_timestamp_utc": NOW, **fields,
        })

    def create(self, key):
        return self.write("facet_schema.create", owner={"owner_kind": "subject", "owner_subject_id": "owner"},
                          schema_key=key, definition=DEFINITION)

    def publish(self, created):
        return self.write("facet_schema.publish", facet_schema_id=created["facet_schema_id"],
                          expected_current_revision_id=created["facet_schema_revision_id"],
                          definition={**DEFINITION, "display_name": "Revised"})

    def request(self, identity=None):
        return {"contract_version": CONTRACT, "facet_schema_revision_id": identity or self.b["facet_schema_revision_id"]}

    def snapshot(self):
        return all_rows(self.db)

    def direct(self, request=None, *, context=None):
        before = self.snapshot()
        response = handle(COMMAND, self.request() if request is None else request, context or self.context)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.db.in_transaction)
        return response

    def assert_failure(self, response, code, field):
        self.assertFalse(response["ok"], response)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), (code, field))
        self.assertNotIn("root", response)
        self.assertNotIn("revision", response)
        self.assertNotIn(self.b["facet_schema_revision_id"], response["error"]["message"])

    def test_public_cli_cross_root_history_retirement_and_zero_writes(self):
        owner = {"owner_kind": "subject", "owner_subject_id": "owner"}
        archetype = self.cli("item_archetype.create", {
            "contract_version": "spine.item-archetypes.v1", "command_id": "archetype", "actor_subject_id": "owner",
            "action_timestamp_utc": NOW, "owner": owner, "archetype_key": "flight",
            "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event"]},
        })
        binding = self.cli("item_archetype.facet_binding.set", {
            "contract_version": "spine.archetype-facet-bindings.v1", "command_id": "binding", "actor_subject_id": "owner",
            "action_timestamp_utc": NOW, "item_archetype_id": archetype["item_archetype_id"], "facet_key": "flight",
            "facet_schema_revision_id": self.b["facet_schema_revision_id"], "expected_binding_id": None,
        })
        rendering = self.cli("notification_rendering_definition.create", {
            "contract_version": "spine.notification-rendering-definitions.v1", "command_id": "rendering", "actor_subject_id": "owner",
            "action_timestamp_utc": NOW, "owner": owner, "definition_key": "flight_details",
            "revision": {
                "display_name": "Flight", "description": None, "compatible_item_types": ["event"],
                "base_rendering_contract": "spine.notification-rendering.v1",
                "base_rendering_profile": "spine.notification-rendering.concise-en-ca.v1",
                "selections": [{"selection_key": "flight", "facet_key": "flight", "field_key": "flight", "label": "Flight",
                                "projection": "value", "facet_schema_revision_id": self.b["facet_schema_revision_id"]}],
            },
        })
        b1 = self.cli(COMMAND, self.request())
        self.assertEqual(b1["revision"]["revision_number"], "1")
        self.publish(self.a)
        b2 = self.publish(self.b)
        before = self.snapshot()
        old = self.cli(COMMAND, self.request())
        current = self.cli(COMMAND, self.request(b2["facet_schema_revision_id"]))
        self.assertEqual(old["revision"], b1["revision"])
        self.assertEqual(binding["facet_schema_revision_id"], old["revision"]["facet_schema_revision_id"])
        selection = rendering["record"]["revision"]["selections"][0]
        self.assertEqual(selection["facet_schema_revision_id"], old["revision"]["facet_schema_revision_id"])
        self.assertEqual(old["root"]["facet_schema_id"], self.b["facet_schema_id"])
        self.assertNotEqual(old["root"]["facet_schema_id"], self.a["facet_schema_id"])
        self.assertEqual(old["root"]["current_revision_id"], b2["facet_schema_revision_id"])
        self.assertEqual(current["revision"]["revision_number"], "2")
        preview = self.cli(COMMAND, self.request(), dry_run=True)
        self.assertEqual(preview, {**old, "dry_run": True})
        self.assertEqual(self.snapshot(), before)
        self.write("facet_schema.retire", facet_schema_id=self.b["facet_schema_id"],
                   expected_current_revision_id=b2["facet_schema_revision_id"])
        before = self.snapshot()
        retired = self.cli(COMMAND, self.request())
        self.assertEqual(retired["root"]["status"], "retired")
        self.assertEqual(retired["revision"], b1["revision"])
        legacy = self.cli("facet_schema.show", {
            "contract_version": "spine.facet-schemas.v1", "facet_schema_id": self.b["facet_schema_id"],
            "facet_schema_revision_id": self.b["facet_schema_revision_id"],
        })
        self.assertEqual((legacy["root"], legacy["revision"]), (retired["root"], retired["revision"]))
        self.assertEqual(self.snapshot(), before)

    def test_cli_combined_error_precedence_missing_opaque_and_dry_run(self):
        witness = json.loads((ROOT / "tests/fixtures/facet_schema_revision_readback/validation_precedence_witness.json").read_text())
        before = self.snapshot()
        for case in witness["cases"]:
            with self.subTest(case=case["case_id"]):
                expected = case["expected"]
                for request in (case["request"], dict(reversed(list(case["request"].items())))):
                    result = self.cli(COMMAND, request, expected=expected["cli_exit"], dry_run=True)
                    self.assert_failure(result, expected["code"], expected["field"])
                    self.assertTrue(result["dry_run"])
        for identity in ("missing", self.b["facet_schema_revision_id"] + " ", "é", "e\u0301"):
            result = self.cli(COMMAND, self.request(identity), expected=4)
            self.assert_failure(result, "referenced_row_not_found", "facet_schema_revision_id")
        for identity in (17, False, [], {}, "\ud800"):
            result = self.cli(COMMAND, {**self.request(), "facet_schema_revision_id": identity}, expected=2)
            self.assert_failure(result, "invalid_request", "facet_schema_revision_id")
        self.assertEqual(self.snapshot(), before)

    def test_corrupt_historical_evidence_fails_closed_without_repair(self):
        identity = self.b["facet_schema_revision_id"]
        # Fault injection is confined to disposable copies, never a client workaround.
        for column, value in (
            ("definition_hash", "0" * 64), ("definition_json", "{}"),
            ("definition_json", json.dumps({**DEFINITION, "display_name": "x" * 32769})),
            ("definition_json", json.dumps({**DEFINITION, "fields": DEFINITION["fields"] * 5})),
            ("definition_contract_version", "future"), ("canonical_json_version", "future"),
            ("facet_schema_id", "missing-root"),
        ):
            with self.subTest(column=column), closing(sqlite3.connect(":memory:")) as raw:
                self.db.backup(raw)
                for row in raw.execute("SELECT name FROM sqlite_schema WHERE type='trigger'").fetchall():
                    raw.execute(f'DROP TRIGGER "{row[0]}"')
                raw.execute("PRAGMA ignore_check_constraints=ON")
                raw.execute(f"UPDATE facet_schema_revisions SET {column}=? WHERE facet_schema_revision_id=?", (value, identity))
                raw.commit()
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / "corrupt.sqlite"
                    with closing(sqlite3.connect(target)) as destination:
                        raw.backup(destination)
                    with closing(connect(target)) as damaged:
                        before = all_rows(damaged)
                        result = handle(COMMAND, self.request(), CommandContext(ledger=damaged))
                        self.assert_failure(result, "environment_failure", "facets")
                        self.assertEqual(all_rows(damaged), before)
        for sql, args in (
            ("DELETE FROM facet_schema_fields WHERE facet_schema_revision_id=? AND field_key='flight'", (identity,)),
            ("UPDATE facet_schema_fields SET queryable=1 WHERE facet_schema_revision_id=? AND field_key='person'", (identity,)),
            ("UPDATE facet_schemas SET current_revision_id=? WHERE facet_schema_id=?",
             (self.a["facet_schema_revision_id"], self.b["facet_schema_id"])),
            ("DELETE FROM facet_schemas WHERE facet_schema_id=?", (self.b["facet_schema_id"],)),
        ):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "bad-projection.sqlite"
                with closing(sqlite3.connect(target)) as raw:
                    self.db.backup(raw)
                    for row in raw.execute("SELECT name FROM sqlite_schema WHERE type='trigger'").fetchall():
                        raw.execute(f'DROP TRIGGER "{row[0]}"')
                    raw.execute(sql, args)
                    raw.commit()
                with closing(connect(target)) as damaged:
                    before = all_rows(damaged)
                    self.assert_failure(handle(COMMAND, self.request(), CommandContext(ledger=damaged)), "environment_failure", "facets")
                    self.assertEqual(all_rows(damaged), before)

    def test_indexed_point_reads_no_deep_checks_no_reference_dereference(self):
        statements = []
        before = self.snapshot()
        self.db.set_trace_callback(statements.append)
        try:
            result = handle(COMMAND, self.request(), self.context)
        finally:
            self.db.set_trace_callback(None)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(result["ok"], result)
        selects = [s for s in statements if s.startswith("SELECT") and "facet_schema" in s]
        self.assertEqual(len(selects), 5)
        for sql in selects:
            self.assertIn("WHERE", sql)
            plan = [r[3] for r in self.db.execute("EXPLAIN QUERY PLAN " + sql)]
            self.assertTrue(any("SEARCH" in r for r in plan), plan)
            self.assertFalse(any("SCAN" in r for r in plan), plan)
        self.assertTrue(any("LIMIT 33" in s for s in selects))
        self.assertFalse(any(term in s.lower() for s in statements for term in (
            "integrity_check", "foreign_key_check", "quick_check", "from subjects", "from locations",
        )))
        # SQL authorizer makes an accidental durable write a hard failure.
        denied = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE}
        self.db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK)
        try:
            self.assertTrue(handle(COMMAND, self.request(), self.context)["ok"])
        finally:
            self.db.set_authorizer(None)

    def test_capacity_byte_sql_time_resource_and_lock_limits(self):
        self.assert_failure(self.direct(self.request("x" * (1024 * 1024))), "environment_failure", "capacity")
        with patch.object(readback, "RESPONSE_BYTES", 1):
            self.assert_failure(self.direct(), "environment_failure", "capacity")
        for budget in (
            FacetBudget(started=time.monotonic() - 6), FacetBudget(steps=100_001),
            FacetBudget(resources={("test", str(i)) for i in range(100)}),
        ):
            with self.subTest(budget=budget), patch.object(readback, "FacetBudget", return_value=budget):
                self.assert_failure(self.direct(), "environment_failure", "capacity")
        def expensive(db, identity):
            db.execute("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT sum(x) FROM n").fetchone()
            return storage.load_definition(db, identity)
        with patch.object(storage, "load_definition", side_effect=expensive):
            self.assert_failure(self.direct(), "environment_failure", "capacity")
        # Read lock wait uses the same operation timeout and leaves no open transaction.
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA busy_timeout=10")
        with closing(sqlite3.connect(self.path)) as locker:
            locker.execute("BEGIN EXCLUSIVE")
            response = handle(COMMAND, self.request(), self.context)
            self.assert_failure(response, "environment_failure", "capacity")
            locker.rollback()
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute("PRAGMA busy_timeout").fetchone()[0], 10)
        self.assertTrue(self.direct()["ok"])

    def test_concurrent_publish_retire_uses_one_snapshot_and_next_read_observes_change(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        before = self.direct()
        decoder = storage.load_definition
        for action in ("facet_schema.publish", "facet_schema.retire"):
            def interleave(db, identity, action=action):
                if db is not self.db:
                    return decoder(db, identity)
                if action.endswith("publish"):
                    self.latest = self.publish(self.b)
                else:
                    self.write(action, facet_schema_id=self.b["facet_schema_id"],
                               expected_current_revision_id=self.latest["facet_schema_revision_id"])
                return decoder(db, identity)
            with patch.object(storage, "load_definition", side_effect=interleave):
                # The concurrent writer legitimately mutates the catalog; not direct()'s no-write harness.
                result = handle(COMMAND, self.request(), self.context)
            self.assertEqual(result, before)
            after = self.direct()
            self.assertEqual(after["revision"], before["revision"])
            self.assertNotEqual(after["root"], before["root"])
            before = after

    def test_admission_registry_and_no_cursor_configuration(self):
        entry = COMMAND_RUNTIME_CONTRACT_REGISTRY[COMMAND]
        self.assertEqual(entry.access_mode, "read")
        expected = json.loads((ROOT / "contracts/facet-schema-revision-readback.v1.json").read_text())["commands"][COMMAND]
        self.assertEqual(list(entry.required_contract_versions), expected["required_contract_versions"])
        self.assertTrue(set(entry.required_contract_versions) <= IMPLEMENTED_CONTRACT_VERSIONS)
        for version in entry.required_contract_versions:
            missing = IMPLEMENTED_CONTRACT_VERSIONS - {version}
            self.assertEqual(missing_runtime_contract_versions(COMMAND, missing), (version,))
        output = io.StringIO()
        with patch("spine.commands.registry.IMPLEMENTED_CONTRACT_VERSIONS", IMPLEMENTED_CONTRACT_VERSIONS - {CONTRACT}), \
                redirect_stdout(output):
            code = main(["--db", str(self.path), "facet_schema", "revision", "show"])
        self.assertEqual(code, 7)
        self.assert_failure(json.loads(output.getvalue()), "environment_failure", "runtime_contracts")
        self.assertIsNone(self.context.facet_cursor_config)
        self.assertTrue(self.direct()["ok"])
        with patch.dict(os.environ, {"SPINE_FACET_CURSOR_CONFIG": "/unused/nonexistent-cursor.json"}):
            self.assertTrue(self.cli(COMMAND, self.request())["ok"])
        for adapter in ("web", "mcp", "http"):
            response = self.direct(context=replace(self.context, transport_metadata={"adapter": adapter}))
            self.assert_failure(response, "environment_failure", "admission")

    def test_installed_wheel_public_cli_and_exact_local_schema_closure(self):
        build_python = os.environ.get("SPINE_WHEEL_BUILD_PYTHON", sys.executable)
        backend = subprocess.run([build_python, "-c", "import setuptools.build_meta"], capture_output=True, timeout=15)
        if backend.returncode:
            self.skipTest("wheel check needs local setuptools; set SPINE_WHEEL_BUILD_PYTHON to a prepared interpreter")
        with tempfile.TemporaryDirectory(prefix="spine-readback-wheel-") as tmp:
            work = Path(tmp)
            clean_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
            source = work / "source"
            source.mkdir()
            for name in ("pyproject.toml", "README.md"):
                shutil.copy2(ROOT / name, source / name)
            shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            def run(*args):
                result = subprocess.run(args, cwd=work, env=clean_env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            run(build_python, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index", "-w", str(work), str(source))
            wheel, = work.glob("spine_ledger-*.whl")
            environment = work / "runtime"
            run(sys.executable, "-m", "venv", "--without-pip", str(environment))
            python = environment / "bin/python"
            run(sys.executable, "-m", "pip", "--python", str(python), "install", "--no-index", "--no-deps", str(wheel))
            facts = json.loads(run(str(python), "-I", "-c", """
import hashlib, json, sys, spine
from importlib import resources
from pathlib import Path
from spine import __version__, IMPLEMENTED_LEDGER_SCHEMA_VERSION
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
assert Path(spine.__file__).is_relative_to(Path(sys.prefix))
root = resources.files('spine.contracts').joinpath('revision_readback')
pins = json.loads(root.joinpath('pins.v1.json').read_text())
for name, expected in pins['files'].items():
    assert hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() == expected
entry = COMMAND_RUNTIME_CONTRACT_REGISTRY['facet_schema.revision.show']
print(json.dumps({'version': __version__, 'schema': IMPLEMENTED_LEDGER_SCHEMA_VERSION,
                 'requirements': entry.required_contract_versions, 'files': sorted(pins['files'])}))
"""))
            self.assertEqual((facts["version"], facts["schema"]), (__version__, 19))
            self.assertEqual(facts["requirements"], list(COMMAND_RUNTIME_CONTRACT_REGISTRY[COMMAND].required_contract_versions))
            self.assertEqual(set(facts["files"]), {
                "facet-schema-revision-readback.v1.json",
                *("schemas/" + name for name in (
                    "facet-schema-revision-show-request.schema.json", "facet-schema-revision-show-response.schema.json",
                    "facet-schema-revision-show-failure.schema.json", "archetype-facet-types.schema.json",
                    "notification-profile-types.schema.json", "notification-types.schema.json",
                )),
            })
            result = subprocess.run([str(environment / "bin/spine-command"), "--db", str(self.path), "--input", "-",
                                     "facet_schema", "revision", "show"], input=json.dumps(self.request()), cwd=work,
                                    env=clean_env, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout), self.direct())
