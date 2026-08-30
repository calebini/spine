import ast
import inspect
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import core as command_core
from spine.commands.cli import main as command_main
from spine.commands.notification_profiles import PROFILE_COMMANDS
from spine.commands.registry import (
    CANONICAL_JSON_CONTRACT,
    COMMAND_RUNTIME_CONTRACT_REGISTRY,
    COMMAND_RUNTIME_CONTRACT_REGISTRY_ID,
    WORKER_REQUIRED_CONTRACT_VERSIONS,
    missing_runtime_contract_versions,
)
from spine.core import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.migrate import verify_schema
from spine.ledger.preflight import SCHEMA_OBJECT_MANIFEST_ID, expected_schema_objects, verify_runtime_schema
from spine.runtime.compatibility import TickerdCompatibilityError, TickerdCompatibilityInfo
from spine.runtime.tickerd_runner import SpineRunnerPaths, run_foreground

try:
    import tickerd  # noqa: F401

    TICKERD_AVAILABLE = True
except ImportError:
    TICKERD_AVAILABLE = False

TICKERD_INFO = TickerdCompatibilityInfo(
    package_version="0.2.0",
    capability_id="tickerd.runtime-capabilities.v1",
    descriptor_sha256="215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b",
)


def _dispatch_commands() -> set[str]:
    tree = ast.parse(inspect.getsource(command_core._dispatch))
    commands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name) or node.left.id != "command":
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                commands.add(comparator.value)
            elif isinstance(comparator, (ast.Set, ast.Tuple)):
                commands.update(
                    element.value for element in comparator.elts if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    return commands


class CommandRuntimeContractRegistryTests(unittest.TestCase):
    def test_registry_is_complete_sorted_and_exact(self) -> None:
        self.assertEqual(COMMAND_RUNTIME_CONTRACT_REGISTRY_ID, "spine.command-runtime-contract-registry.v1")
        self.assertEqual(len(COMMAND_RUNTIME_CONTRACT_REGISTRY), 53)
        self.assertEqual(
            set(COMMAND_RUNTIME_CONTRACT_REGISTRY),
            _dispatch_commands() | set(PROFILE_COMMANDS),
        )
        expected_read_commands = {
            "agenda.show",
            "item.list",
            "item.occurrences",
            "item.show",
            "item_archetype.list",
            "item_archetype.show",
            "notification.opportunities",
            "notification_profile.binding.list",
            "notification_profile.list",
            "notification_profile.resolve",
            "notification_profile.show",
            "owner_scope.list",
            "relation.list",
            "schedule.binding.list",
            "schedule.build",
            "schedule.show",
            "system.info",
        }
        self.assertEqual(
            {command for command, entry in COMMAND_RUNTIME_CONTRACT_REGISTRY.items() if entry.access_mode == "read"},
            expected_read_commands,
        )
        for command, entry in COMMAND_RUNTIME_CONTRACT_REGISTRY.items():
            self.assertEqual(entry.command, command)
            self.assertIn(entry.access_mode, {"read", "write"})
            self.assertEqual(entry.required_contract_versions, tuple(sorted(set(entry.required_contract_versions))))
            self.assertIn(CANONICAL_JSON_CONTRACT, entry.required_contract_versions)
            self.assertEqual(missing_runtime_contract_versions(command), ())

    def test_exact_version_mismatch_is_sorted_and_fail_closed(self) -> None:
        implemented = frozenset(
            IMPLEMENTED_CONTRACT_VERSIONS
            - {
                "spine.canonical-json.v1",
                "spine.schedule-show.v1",
            }
        )
        self.assertEqual(
            missing_runtime_contract_versions("schedule.show", implemented),
            ("spine.canonical-json.v1", "spine.schedule-show.v1"),
        )

    def test_cli_runtime_contract_mismatch_fails_before_database_open(self) -> None:
        with patch(
            "spine.commands.registry.IMPLEMENTED_CONTRACT_VERSIONS",
            frozenset(IMPLEMENTED_CONTRACT_VERSIONS - {"spine.system-info.v2"}),
        ):
            output = StringIO()
            with redirect_stdout(output):
                exit_code = command_main(["--db", "/definitely/not/a/ledger.sqlite", "system", "info"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 7)
        self.assertEqual(payload["error"]["code"], "environment_failure")
        self.assertEqual(payload["error"]["field"], "runtime_contracts")
        self.assertIn("spine.system-info.v2", payload["error"]["message"])


class BoundedSchemaPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect(":memory:")
        initialize_schema(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_manifest_identity_and_fresh_schema_match(self) -> None:
        self.assertEqual(SCHEMA_OBJECT_MANIFEST_ID, "spine.sqlite-schema-object-manifest.v1")
        expected = expected_schema_objects()
        result = verify_runtime_schema(self.connection)
        self.assertEqual(result.table_count, sum(item.object_type == "table" for item in expected))
        self.assertEqual(result.index_count, sum(item.object_type == "index" for item in expected))
        self.assertEqual(result.trigger_count, sum(item.object_type == "trigger" for item in expected))

    def test_runtime_preflight_uses_no_deep_or_domain_scan(self) -> None:
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        verify_runtime_schema(self.connection)
        normalized = "\n".join(statements).lower()
        self.assertNotIn("integrity_check", normalized)
        self.assertNotIn("foreign_key_check", normalized)
        self.assertNotIn("quick_check", normalized)
        self.assertNotIn("from coordination_items", normalized)
        self.assertNotIn("from work_instances", normalized)
        self.assertNotIn("from command_receipts", normalized)

    def test_noncolliding_extra_object_is_ignored(self) -> None:
        self.connection.execute("CREATE TABLE operator_extension (value TEXT)")
        verify_runtime_schema(self.connection)

    def test_definition_drift_fails_closed(self) -> None:
        self.connection.execute("PRAGMA writable_schema = ON")
        self.connection.execute(
            "UPDATE sqlite_schema SET sql = sql || ' ' WHERE type = 'index' AND name = ?",
            ("work_instances_eligible_due_idx",),
        )
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_object_definition_mismatch"):
            verify_runtime_schema(self.connection)

    def test_explicit_deep_verifier_retains_expensive_checks(self) -> None:
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        verify_schema(self.connection)
        normalized = "\n".join(statements).lower()
        self.assertIn("pragma foreign_key_check", normalized)
        self.assertIn("pragma integrity_check", normalized)

    def test_command_preflight_does_not_call_deep_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spine.sqlite"
            connection = connect(path)
            try:
                initialize_schema(connection)
            finally:
                connection.close()
            output = StringIO()
            with (
                patch("spine.ledger.migrate.verify_schema", side_effect=AssertionError("deep verifier invoked")),
                patch("spine.runtime.compatibility.resolve_tickerd_compatibility", return_value=TICKERD_INFO),
                redirect_stdout(output),
            ):
                exit_code = command_main(["--db", str(path), "system", "info"])
            self.assertEqual(exit_code, 0, output.getvalue())


@unittest.skipUnless(TICKERD_AVAILABLE, "tickerd is not importable")
class WorkerRuntimePreflightTests(unittest.TestCase):
    def test_runtime_dependency_mismatch_is_down_and_stops_before_tickerd_construction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            connection = connect(":memory:")
            initialize_schema(connection)
            diagnostic = {
                "event": "ledger_runtime_preflight_failed",
                "reason": "runtime_dependency_mismatch",
                "dependency": "tickerd",
                "compatibility_contract": "spine.tickerd-compatibility.v1",
                "required_package_version": "0.2.0",
                "installed_package_version": "0.1.0",
                "required_capability_id": "tickerd.runtime-capabilities.v1",
                "installed_capability_id": None,
                "required_descriptor_sha256": "215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b",
                "installed_descriptor_sha256": None,
                "mismatch_fields": ["capability_id", "package_version"],
            }
            try:
                with (
                    patch(
                        "spine.runtime.preflight.resolve_tickerd_compatibility",
                        side_effect=TickerdCompatibilityError(diagnostic),
                    ),
                    patch("spine.runtime.tickerd_runner._tickerd_runner_types") as runtime_types,
                    patch("spine.runtime.tickerd_runner.SpineTickerdWorkAdapter") as adapter,
                ):
                    result = run_foreground(connection, state_dir=state_dir, install_signal_handlers=False)
            finally:
                connection.close()
            self.assertEqual(result.exit_code, 3)
            runtime_types.assert_not_called()
            adapter.assert_not_called()
            paths = SpineRunnerPaths.from_state_dir(state_dir)
            record = json.loads(paths.events_path.read_text(encoding="utf-8"))
            self.assertEqual(record, diagnostic)

    def test_runtime_contract_mismatch_is_sorted_down_and_stops_before_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            connection = connect(":memory:")
            initialize_schema(connection)
            missing = {
                "spine.notification-opportunities.v1",
                "spine.schedule-binding-reconcile.v1",
            }
            implemented = frozenset(IMPLEMENTED_CONTRACT_VERSIONS - missing)
            try:
                with (
                    patch("spine.runtime.preflight.IMPLEMENTED_CONTRACT_VERSIONS", implemented),
                    patch("spine.runtime.tickerd_runner.SpineTickerdWorkAdapter") as adapter,
                ):
                    result = run_foreground(connection, state_dir=state_dir, install_signal_handlers=False)
            finally:
                connection.close()

            self.assertNotEqual(result.exit_code, 0)
            adapter.assert_not_called()
            paths = SpineRunnerPaths.from_state_dir(state_dir)
            health = json.loads(paths.health_path.read_text(encoding="utf-8"))
            self.assertEqual(health["state"], "DOWN")
            self.assertFalse(health["is_ready"])
            records = [json.loads(line) for line in paths.events_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["event"], "ledger_runtime_preflight_failed")
            self.assertEqual(records[0]["reason"], "runtime_contract_mismatch")
            self.assertEqual(records[0]["required_contract_versions"], sorted(missing))
            self.assertNotIn("required_contract_version", records[0])

    def test_schema_object_failure_stops_before_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            connection = connect(":memory:")
            initialize_schema(connection)
            connection.execute("DROP INDEX work_instances_eligible_due_idx")
            try:
                with patch("spine.runtime.tickerd_runner.SpineTickerdWorkAdapter") as adapter:
                    result = run_foreground(connection, state_dir=state_dir, install_signal_handlers=False)
            finally:
                connection.close()

            self.assertNotEqual(result.exit_code, 0)
            adapter.assert_not_called()
            paths = SpineRunnerPaths.from_state_dir(state_dir)
            records = [json.loads(line) for line in paths.events_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                records,
                [
                    {
                        "event": "ledger_runtime_preflight_failed",
                        "object_name": "work_instances_eligible_due_idx",
                        "object_type": "index",
                        "reason": "schema_object_mismatch",
                    }
                ],
            )

    def test_worker_preflight_does_not_call_deep_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            connection = connect(":memory:")
            initialize_schema(connection)
            try:
                with patch("spine.ledger.migrate.verify_schema", side_effect=AssertionError("deep verifier invoked")):
                    result = run_foreground(
                        connection,
                        state_dir=state_dir,
                        max_cycles=1,
                        tick_interval_ms=1,
                        reconcile_interval_ms=1,
                        install_signal_handlers=False,
                    )
            finally:
                connection.close()
            self.assertEqual(result.exit_code, 0)

    def test_worker_required_contract_set_is_sorted_unique(self) -> None:
        self.assertEqual(WORKER_REQUIRED_CONTRACT_VERSIONS, tuple(sorted(set(WORKER_REQUIRED_CONTRACT_VERSIONS))))
        self.assertTrue(WORKER_REQUIRED_CONTRACT_VERSIONS)


if __name__ == "__main__":
    unittest.main()
