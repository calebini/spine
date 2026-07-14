import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from spine.core import SpineValidationError
from spine.ledger import (
    connect,
    initialize_schema,
)
from spine.ledger.migrate import (
    CURRENT_SCHEMA_VERSION,
    current_schema_version,
    EXPECTED_SCHEMA_INDEXES,
    main as migrate_main,
    migrate_schema,
    verify_schema,
)


class LedgerMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()

    def tearDown(self) -> None:
        self.connection.close()

    def test_migrate_empty_database_initializes_latest_when_allowed(self) -> None:
        result = migrate_schema(self.connection, initialize_if_empty=True)

        self.assertEqual(result.before_version, 0)
        self.assertEqual(result.after_version, CURRENT_SCHEMA_VERSION)
        self.assertTrue(result.initialized)
        self.assertTrue(result.verified)
        self.assertEqual(current_schema_version(self.connection), CURRENT_SCHEMA_VERSION)

    def test_migrate_empty_database_rejects_without_initialization_opt_in(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_uninitialized"):
            migrate_schema(self.connection)

    def test_migrate_v1_database_applies_pending_migrations(self) -> None:
        initialize_schema(self.connection)
        rewind_to_v1_without_access_indexes(self.connection)
        self.assertEqual(current_schema_version(self.connection), 1)
        self.assertNotIn("work_instances_eligible_due_idx", index_names(self.connection))
        self.connection.execute("DROP TABLE command_receipts")

        result = migrate_schema(self.connection)

        self.assertEqual(result.before_version, 1)
        self.assertEqual(result.after_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(result.applied_versions, (2, 3, 4))
        self.assertIn("work_instances_eligible_due_idx", index_names(self.connection))
        self.assertIn("command_receipts_item_created_idx", index_names(self.connection))
        self.assertIn("delivery_targets_active_no_account_unique", index_names(self.connection))
        self.assertIn("work_instances_delivery_target_idx", index_names(self.connection))

    def test_verify_schema_rejects_missing_required_index(self) -> None:
        initialize_schema(self.connection)
        self.connection.execute("DROP INDEX work_instances_eligible_due_idx")

        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_missing_indexes"):
            verify_schema(self.connection)

    def test_verify_schema_rejects_old_schema_version(self) -> None:
        initialize_schema(self.connection)
        with self.connection:
            self.connection.execute("DELETE FROM ledger_schema")
            self.connection.execute(
                """
                INSERT INTO ledger_schema (schema_version, applied_at_utc)
                VALUES (1, '1970-01-01T00:00:00Z')
                """
            )

        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_version_mismatch"):
            verify_schema(self.connection)

    def test_migration_cli_initializes_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "spine.sqlite"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = migrate_main(["--db", str(db_path), "--initialize-if-empty"])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["before_version"], 0)
            self.assertEqual(payload["after_version"], CURRENT_SCHEMA_VERSION)
            self.assertTrue(payload["initialized"])
            connection = connect(db_path)
            try:
                self.assertEqual(current_schema_version(connection), CURRENT_SCHEMA_VERSION)
            finally:
                connection.close()


def rewind_to_v1_without_access_indexes(connection: sqlite3.Connection) -> None:
    with connection:
        for index_name in sorted(EXPECTED_SCHEMA_INDEXES - {"coordination_item_relations_active_unique"}):
            connection.execute(f"DROP INDEX IF EXISTS {index_name}")
        connection.execute("DELETE FROM ledger_schema")
        connection.execute(
            """
            INSERT INTO ledger_schema (schema_version, applied_at_utc)
            VALUES (1, '1970-01-01T00:00:00Z')
            """
        )


def index_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }


if __name__ == "__main__":
    unittest.main()
