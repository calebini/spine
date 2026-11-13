"""Actual disposable SQLite ownership bootstrap tests; no public activation/sends."""

from __future__ import annotations

import copy
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core.errors import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.ownership import MAX_EPOCH, advance_ownership_epoch, project_access_state, read_access_state
from spine.ledger.recurring_task_migration import attach_candidate, install_candidate, verify_candidate_schema
from spine.web.errors import WebError
from spine.web.ownership_provisioning import OwnershipProvisioningContracts
from spine.web.provisioning import apply, plan
from spine.web.service import WebConfig, WebService
from tests import test_local_ownership_bootstrap_contracts as offline
from tests import test_recurring_task_commands as r2
from tests import test_recurring_task_reconcile as pages

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-11-10T12:00:00Z"
CONTRACT = "spine.trusted-web-provisioning.v3"


def contracts(fault=None):
    offline.LocalOwnershipBootstrapContractTests.setUpClass()
    return OwnershipProvisioningContracts(offline.LocalOwnershipBootstrapContractTests.schemas, fault=fault)


def dump(db):
    return "\n".join(db.iterdump())


class OwnershipBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        initialize_schema(self.db)
        for subject in ("owner", "other"):
            result = handle("subject.upsert", dict(command_id="seed-" + subject, actor_subject_id="owner",
                            subject_id=subject, subject_kind="person", display_name=subject, updated_at_utc=AT),
                            CommandContext(ledger=self.db))
            self.assertTrue(result["ok"], result)
        self.contracts = contracts()

    def install(self, **kwargs):
        install_candidate(self.db, disposable_test_ledger=True, **kwargs)

    def proposed(self, *, db=None, **overrides):
        db = db or self.db
        state = read_access_state(db)
        request = dict(contract_version=CONTRACT, ledger_id=state["ledger_id"] if state else read_ledger_instance_id(db),
                       realm_id="explicit-realm", expected_access_epoch=str(state["access_epoch"] if state else 0),
                       operators=[dict(operation="create", subject_id="owner", display_name="Owner",
                                       activation_basis="trusted_local_approval")])
        request.update(overrides)
        with db.atomic_command(write=False):
            return plan(db, request, bootstrap=self.contracts)

    def request(self, proposal, cid="promote"):
        return dict(contract_version=CONTRACT, command_id=cid, actor_subject_id="owner", action_timestamp_utc=AT,
                    expected_access_epoch=proposal["normalized_plan"]["expected_access_epoch"], plan=proposal)

    def test_first_owner_once_savepoint_rollback_and_configured_preservation(self):
        self.install()
        identity = read_ledger_instance_id(self.db)
        self.assertIsNone(read_access_state(self.db))
        with self.db.atomic_command():
            with self.assertRaisesRegex(RuntimeError, "unit"), self.db.command_unit():
                self.assertEqual(advance_ownership_epoch(self.db), 1)
                raise RuntimeError("unit")
            self.assertIsNone(read_access_state(self.db))
            self.assertFalse(self.db.mutation_state.ownership.epoch_consumed)
            self.assertEqual(advance_ownership_epoch(self.db), 1)
            with self.assertRaises(RuntimeError), self.db.command_unit():
                self.assertEqual(advance_ownership_epoch(self.db), 1)
                raise RuntimeError("later unit")
            self.assertTrue(self.db.mutation_state.ownership.epoch_consumed)
        state = read_access_state(self.db)
        self.assertEqual(project_access_state(state), dict(singleton_id="1", ledger_id=identity, realm_id=None,
                         mode="trusted_local", identity_mode=None, access_epoch="1", recovery_epoch="1"))
        with self.db.atomic_command():
            self.assertEqual(advance_ownership_epoch(self.db), 2)
            self.assertEqual(advance_ownership_epoch(self.db), 2)
        before = dump(self.db)
        with self.assertRaises(RuntimeError), self.db.atomic_command():
            advance_ownership_epoch(self.db)
            raise RuntimeError("outer rollback")
        self.assertEqual(dump(self.db), before)

    def test_nested_unit_opt_in_rolls_back_only_its_own_epoch_and_finalizer_state(self):
        self.install()
        with self.db.atomic_command(), self.db.command_unit():
            with self.assertRaisesRegex(RuntimeError, "cannot nest"), self.db.command_unit():
                self.fail("ordinary unit nesting must remain forbidden")
            with self.assertRaisesRegex(RuntimeError, "inner"), self.db.command_unit(nested=True):
                advance_ownership_epoch(self.db)
                raise RuntimeError("inner")
            self.assertIsNone(read_access_state(self.db))
            self.assertFalse(self.db.mutation_state.ownership.epoch_consumed)
            self.assertEqual(self.db._command_unit_depth, 1)
            advance_ownership_epoch(self.db)
            with self.assertRaisesRegex(RuntimeError, "second"), self.db.command_unit(nested=True):
                self.assertEqual(advance_ownership_epoch(self.db), 1)
                raise RuntimeError("second")
            self.assertEqual(read_access_state(self.db)["access_epoch"], 1)
            self.assertTrue(self.db.mutation_state.ownership.epoch_consumed)
        self.assertEqual(self.db._command_unit_depth, 0)
        self.assertFalse(self.db._command_unit_active)
        self.assertFalse(self.db.mutation_state.ownership.epoch_consumed)
        for table in ("login_accounts", "web_operators", "subject_memberships", "access_grants"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_routine_access_is_bounded_readonly_and_requires_writer_scope(self):
        self.install()
        statements = []
        self.db.set_trace_callback(statements.append)
        with self.db.atomic_command(write=False):
            self.assertIsNone(read_access_state(self.db))
            with self.assertRaises(SpineValidationError):
                advance_ownership_epoch(self.db)
        with self.assertRaises(SpineValidationError):
            advance_ownership_epoch(self.db)
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        self.db.set_trace_callback(None)
        self.assertFalse(any(any(term in s.lower() for term in ("integrity_check", "foreign_key_check", "quick_check",
                                                              "item_access_owners", "revisions")) for s in statements))
        self.assertTrue(any("LIMIT 2" in s for s in statements))

    def test_explicit_promotion_retains_identity_recovery_and_exact_replay(self):
        self.install()
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        before = read_access_state(self.db)
        proposal = self.proposed()
        self.assertTrue(proposal["can_apply"], proposal)
        request = self.request(proposal)
        response = apply(self.db, request, bootstrap=self.contracts)
        state = read_access_state(self.db)
        self.assertEqual((state["ledger_id"], state["recovery_epoch"], state["access_epoch"]),
                         (before["ledger_id"], before["recovery_epoch"], 2))
        self.assertEqual((state["mode"], state["realm_id"], state["identity_mode"]),
                         ("multi_user", "explicit-realm", "trusted_identity"))
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        snapshot = dump(self.db)
        self.assertEqual(apply(self.db, request, bootstrap=self.contracts), {**response, "replayed": True})
        self.assertEqual(dump(self.db), snapshot)
        changed = copy.deepcopy(request)
        changed["action_timestamp_utc"] = "2026-11-10T12:00:01Z"
        with self.assertRaisesRegex(WebError, "command_id_unavailable"):
            apply(self.db, changed, bootstrap=self.contracts)

    def test_stale_promotion_no_lockout_and_noop_at_maximum_epoch(self):
        self.install()
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        proposal = self.proposed()
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        with self.assertRaisesRegex(WebError, "access_changed"):
            apply(self.db, self.request(proposal), bootstrap=self.contracts)
        proposal = self.proposed()
        apply(self.db, self.request(proposal), bootstrap=self.contracts)
        binding = dict(self.db.execute("SELECT * FROM account_subject_bindings").fetchone())
        operator = dict(operation="set", account_id=binding["account_id"], expected_account_revision="1",
                        binding_id=binding["binding_id"], expected_binding_revision="1", eligible=False)
        denied = self.proposed(operators=[operator])
        self.assertFalse(denied["can_apply"])
        self.assertIn(dict(code="eligible_operator_required", operation_path="/operators"), denied["conflicts"])
        before = dump(self.db)
        with self.assertRaisesRegex(WebError, "domain_conflict"):
            apply(self.db, self.request(denied, "lockout"), bootstrap=self.contracts)
        self.assertEqual(dump(self.db), before)
        with self.db.atomic_command():
            self.db.execute("UPDATE ledger_access_state SET access_epoch=?", (MAX_EPOCH,))
        noop = self.proposed(operators=[])
        result = apply(self.db, self.request(noop, "max-noop"), bootstrap=self.contracts)
        self.assertEqual((result["changed"], result["effect"], result["access_epoch"]),
                         (False, "web_access_noop", str(MAX_EPOCH)))
        before = dump(self.db)
        for operation in (lambda: advance_ownership_epoch(self.db),):
            with self.assertRaises(SpineValidationError), self.db.atomic_command():
                operation()
        changed = self.proposed(operators=[dict(operation="create", subject_id="other", display_name="Other",
                                               activation_basis="trusted_local_approval")])
        with self.assertRaisesRegex(WebError, "admission_unavailable"):
            apply(self.db, self.request(changed, "overflow"), bootstrap=self.contracts)
        self.assertEqual(dump(self.db), before)

    def test_promotion_faults_rollback_state_operations_audit_and_receipt(self):
        self.install()
        for local in (False, True):
            if local:
                with self.db.atomic_command():
                    advance_ownership_epoch(self.db)
            request = self.request(self.proposed())
            before = dump(self.db)
            for stage in ("state", "operations", "audit", "receipt"):
                def fault(actual, expected=stage):
                    if actual == expected:
                        raise RuntimeError(expected)
                with self.subTest(local=local, stage=stage), self.assertRaisesRegex(RuntimeError, stage):
                    apply(self.db, request, bootstrap=contracts(fault))
                self.assertEqual(dump(self.db), before)
                self.assertFalse(self.db.mutation_state.ownership.epoch_consumed)

    def test_migration_preserves_real_configured_accounts_and_triggers(self):
        legacy = dict(contract_version="spine.trusted-web-provisioning.v2", ledger_id="separate-logical-ledger",
                      expected_access_epoch="0", operators=[dict(operation="create", subject_id="owner",
                      display_name="Owner", activation_basis="trusted_local_approval")])
        proposal = plan(self.db, legacy, realm="old-realm")
        apply(self.db, dict(contract_version=legacy["contract_version"], command_id="legacy", actor_subject_id="owner",
                           action_timestamp_utc=AT, expected_access_epoch="0", plan=proposal), realm="old-realm")
        before = {r[0]: list(map(tuple, self.db.execute(f'SELECT * FROM "{r[0]}"')))
                  for r in self.db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()}
        triggers = list(map(tuple, self.db.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' ORDER BY name")))
        self.install()
        for table, rows in before.items():
            if table != "ledger_schema":
                self.assertEqual(list(map(tuple, self.db.execute(f'SELECT * FROM "{table}"'))), rows, table)
        for name, sql in triggers:
            self.assertEqual(self.db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0], sql)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.db.atomic_command():
            self.assertEqual(advance_ownership_epoch(self.db), 2)
        self.assertEqual(read_access_state(self.db)["ledger_id"], "separate-logical-ledger")

    def test_every_rebuild_fault_restores_predecessor_and_fk_enforcement(self):
        before = dump(self.db)
        for stage in ("preflight", "ownership_created", "ownership_copied", "ownership_dropped", "ownership_rebuilt",
                      "ddl", "verified", "activation"):
            def fault(actual, expected=stage):
                if actual == expected:
                    raise RuntimeError(expected)
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, stage):
                self.install(fault=fault)
            self.assertEqual(dump(self.db), before)
            self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_invalid_stored_identifiers_and_extra_dependents_abort_migration(self):
        with self.db.atomic_command():
            self.db.execute("INSERT INTO ledger_access_state VALUES(1,'invalid\nledger','realm','multi_user','trusted_identity',1,1)")
        before = dump(self.db)
        with self.assertRaises(SpineValidationError):
            self.install()
        self.assertEqual(dump(self.db), before)
        with self.db.atomic_command():
            self.db.execute("DELETE FROM ledger_access_state")
        self.db.execute("CREATE VIEW extra_state_view AS SELECT * FROM ledger_access_state")
        with self.assertRaisesRegex(SpineValidationError, "dependent object"):
            self.install()
        self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_local_posture_cannot_admit_web_or_legacy_provisioning(self):
        self.install()
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        request = self.proposed()["normalized_plan"]
        with self.assertRaisesRegex(WebError, "invalid_request"):
            plan(self.db, request)  # no injected successor contracts
        legacy = {k: v for k, v in request.items() if k != "realm_id"}
        for version in ("v1", "v2"):
            legacy["contract_version"] = "spine.trusted-web-provisioning." + version
            with self.assertRaisesRegex(WebError, "admission_unavailable"):
                plan(self.db, legacy)
        service = WebService(WebConfig("unused", read_ledger_instance_id(self.db)))
        with patch("spine.web.service.verify_runtime_schema", verify_candidate_schema), \
                self.assertRaisesRegex(WebError, "admission_unavailable"):
            service.preflight(self.db)  # reach posture check behind future schema admission

    def test_corrupt_state_and_missing_identity_fail_without_repair(self):
        self.install()
        before = dump(self.db)
        for ledger, realm in (("bad\nledger", "realm"), ("ledger", "realm\n")):
            with self.subTest(ledger=ledger, realm=realm), self.assertRaises(SpineValidationError), self.db.atomic_command():
                self.db.execute("INSERT INTO ledger_access_state VALUES(1,?,?,'multi_user','trusted_identity',1,1)",
                                (ledger, realm))
                read_access_state(self.db)
            self.assertEqual(dump(self.db), before)
        with self.assertRaisesRegex(SpineValidationError, "ledger instance"), self.db.atomic_command():
            self.db.execute("DROP TRIGGER ledger_instance_metadata_no_delete")
            self.db.execute("DELETE FROM ledger_instance_metadata")
            advance_ownership_epoch(self.db)
        self.assertEqual(dump(self.db), before)
        for values in (("realm", None), (None, "trusted_identity")):
            with self.subTest(values=values), self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
                self.db.execute("INSERT INTO ledger_access_state VALUES(1,'ledger',?,'multi_user',?,1,1)", values)
        self.assertEqual(dump(self.db), before)

    def test_fresh_witness_recovery_change_and_ledger_mismatch_are_not_replay(self):
        self.install()
        with self.db.atomic_command():
            advance_ownership_epoch(self.db)
        proposal = self.proposed()
        with self.db.atomic_command():
            self.db.execute("UPDATE ledger_access_state SET recovery_epoch=2")
        before = dump(self.db)
        with self.assertRaisesRegex(WebError, "domain_conflict"):
            apply(self.db, self.request(proposal), bootstrap=self.contracts)
        self.assertEqual(dump(self.db), before)
        with self.assertRaisesRegex(WebError, "admission_unavailable"):
            self.proposed(ledger_id="replacement-ledger")

    def test_owner_provisioning_interleavings_serialize_and_preserve_freshness(self):
        self.install()
        proposal = self.proposed()
        with tempfile.TemporaryDirectory() as directory:
            for first in ("owner", "provisioning"):
                path = str(Path(directory) / (first + ".sqlite"))
                target = connect(path)
                self.db.backup(target)
                target.close()
                held, started, release = threading.Event(), threading.Event(), threading.Event()

                def fault(stage, held=held, release=release):
                    if stage == "state":
                        held.set()
                        if not release.wait(timeout=10):
                            raise RuntimeError("race release timed out")

                def owner(path=path, first=first, started=started, held=held, release=release):
                    db = connect(path)
                    try:
                        attach_candidate(db)
                        if first != "owner":
                            started.set()
                        with db.atomic_command():
                            advance_ownership_epoch(db)
                            if first == "owner":
                                held.set()
                                if not release.wait(timeout=10):
                                    raise RuntimeError("race release timed out")
                    finally:
                        db.close()

                def provision(path=path, first=first, started=started, fault=fault):
                    db = connect(path)
                    try:
                        attach_candidate(db)
                        if first != "provisioning":
                            started.set()
                        try:
                            return apply(db, self.request(proposal), bootstrap=contracts(fault if first == "provisioning" else None))
                        except WebError as exc:
                            return {"error": exc.code}
                    finally:
                        db.close()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    a = pool.submit(owner if first == "owner" else provision)
                    self.assertTrue(held.wait(timeout=10))
                    b = pool.submit(provision if first == "owner" else owner)
                    self.assertTrue(started.wait(timeout=10))
                    release.set()
                    results = (a.result(timeout=20), b.result(timeout=20))
                db = connect(path)
                try:
                    state = read_access_state(db)
                    if first == "owner":
                        self.assertEqual(state["mode"], "trusted_local")
                        self.assertEqual(state["access_epoch"], 1)
                        self.assertEqual(results[1], {"error": "access_changed"})
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM login_accounts").fetchone()[0], 0)
                    else:
                        self.assertEqual(state["mode"], "multi_user")
                        self.assertEqual(state["access_epoch"], 2)
                        self.assertTrue(results[0]["ok"])
                    self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                finally:
                    db.close()


class R2LocalOwnershipTests(unittest.TestCase):
    request = r2.RecurringTaskCommandTests.request
    write = r2.RecurringTaskCommandTests.write
    created = r2.RecurringTaskCommandTests.created
    run_command = r2.RecurringTaskCommandTests.run_command
    reconcile = pages.RecurringTaskReconcileTests.reconcile
    rule = pages.RecurringTaskReconcileTests.rule
    def test_local_budget_rollback_preserves_one_epoch(self):
        pages.RecurringTaskReconcileTests.test_work_budget_stops_between_units_and_rolls_back_finalizer_trackers(self)
        self.assertEqual(read_access_state(self.db)["access_epoch"], 1)

    @classmethod
    def setUpClass(cls):
        cls.contracts = r2.contracts()

    def setUp(self):
        r2.RecurringTaskCommandTests.setUp(self)

    def test_real_ownerless_ledger_generates_owned_tasks_without_web_setup(self):
        rule = self.created()["result"]["rule"]
        self.assertIsNone(read_access_state(self.db))
        response = self.reconcile(rule)
        self.assertEqual(len(response["result"]["results"]), 6)
        self.assertEqual(read_access_state(self.db)["access_epoch"], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_access_owners").fetchone()[0], 6)
        for table in ("login_accounts", "web_operators", "access_grants", "side_effect_attempts"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        before = dump(self.db)
        replay = self.run_command("reconcile", self.write("reconcile", rule, limits={}) | {"command_id": "page"})
        self.assertTrue(replay["replayed"])
        self.assertEqual(dump(self.db), before)

    def test_real_first_generation_faults_and_dry_run_leave_no_bootstrap(self):
        rule = self.created()["result"]["rule"]
        request = self.write("reconcile", rule, limits={})
        before = dump(self.db)
        for stage in ("task", "ownership_state", "owner", "binding", "policies", "work", "audit", "receipt"):
            def fault(actual, expected=stage):
                if actual == expected:
                    raise RuntimeError(expected)
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, stage):
                self.run_command("reconcile", request, fault=fault)
            self.assertEqual(dump(self.db), before)
        response = self.run_command("reconcile", request, context=replace(self.context, dry_run=True))
        self.assertTrue(response["ok"], response)
        self.assertEqual(dump(self.db), before)

    def test_two_first_owner_commands_serialize_without_lost_epoch(self):
        first = self.created()["result"]["rule"]
        second = self.run_command("create", self.request("second"))["result"]["rule"]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "disposable.sqlite")
            target = connect(path)
            self.db.backup(target)
            target.close()
            barrier = threading.Barrier(2)
            def run(rule, cid):
                db = connect(path)
                try:
                    attach_candidate(db)
                    context = replace(self.context, ledger=db)
                    rule = self.run_command("show", dict(contract_version="spine.recurring-related-tasks.v1",
                                            related_task_rule_id=rule["related_task_rule_id"]), context=context)["result"]["rule"]
                    request = self.write("reconcile", rule, limits={"mutations": "1"}) | {"command_id": cid}
                    barrier.wait(timeout=10)
                    initial = self.run_command("reconcile", request, context=context)
                    result = initial
                    if not initial["ok"]:
                        self.assertEqual(initial["error"]["code"], "stale_version", initial)
                        rule = self.run_command("show", dict(contract_version="spine.recurring-related-tasks.v1",
                                                related_task_rule_id=rule["related_task_rule_id"]), context=context)["result"]["rule"]
                        request = self.write("reconcile", rule, limits={"mutations": "1"}) | {"command_id": cid}
                        result = self.run_command("reconcile", request, context=context)
                    return initial, result
                finally:
                    db.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, rule, cid) for rule, cid in ((first, "race-one"), (second, "race-two"))]
                outcomes = [future.result(timeout=20) for future in futures]
                self.assertEqual(sum(not initial["ok"] for initial, _ in outcomes), 1)
                for _, result in outcomes:
                    self.assertTrue(result["ok"], result)
            db = connect(path)
            try:
                self.assertEqual(read_access_state(db)["access_epoch"], 2)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger_access_state").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM item_access_owners").fetchone()[0], 2)
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                db.close()
