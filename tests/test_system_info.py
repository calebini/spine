from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from spine import IMPLEMENTED_CONTRACT_VERSIONS, IMPLEMENTED_LEDGER_SCHEMA_VERSION, __version__
from spine.commands import CommandContext, handle
from spine.commands.cli import main as cli_main
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect, initialize_schema

ROOT = Path(__file__).parents[1]
SYSTEM_INFO_SCHEMA = ROOT / "contracts" / "schemas" / "system-info-response.schema.json"


class SystemInfoCommandTests(unittest.TestCase):
    def test_handler_reports_exact_authoring_environment_without_mutation(self) -> None:
        connection = connect()
        try:
            initialize_schema(connection)
            changes_before = connection.total_changes

            response = handle("system.info", {}, CommandContext(ledger=connection))

            self.assertEqual(connection.total_changes, changes_before)
            self.assertEqual(response["runtime_version"], __version__)
            self.assertEqual(response["ledger_schema_version"], str(IMPLEMENTED_LEDGER_SCHEMA_VERSION))
            self.assertEqual(response["implemented_ledger_schema_version"], str(IMPLEMENTED_LEDGER_SCHEMA_VERSION))
            self.assertEqual(response["timezone_database_version"], system_timezone_database_version())
            self.assertEqual(response["implemented_contract_versions"], sorted(IMPLEMENTED_CONTRACT_VERSIONS))
            schema = json.loads(SYSTEM_INFO_SCHEMA.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(response)
        finally:
            connection.close()

    def test_handler_rejects_request_fields(self) -> None:
        connection = connect()
        try:
            initialize_schema(connection)
            response = handle("system.info", {"timezone": "UTC"}, CommandContext(ledger=connection))
            self.assertEqual(response["error"]["code"], "unsupported_field")
            self.assertEqual(response["error"]["field"], "timezone")
        finally:
            connection.close()

    def test_handler_rejects_an_uninitialized_ledger(self) -> None:
        connection = connect()
        try:
            response = handle("system.info", {}, CommandContext(ledger=connection))
            self.assertEqual(response["error"]["code"], "environment_failure")
            self.assertEqual(response["error"]["field"], "ledger_schema_version")
        finally:
            connection.close()

    def test_cli_exposes_system_info_with_stable_option_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "spine.sqlite"
            connection = connect(database)
            initialize_schema(connection)
            connection.close()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["--db", str(database), "--pretty", "system", "info"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0, payload)
            self.assertEqual(payload["command"], "system.info")
            self.assertEqual(payload["timezone_database_version"], system_timezone_database_version())


if __name__ == "__main__":
    unittest.main()
