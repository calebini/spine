from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine.core import SpineValidationError
from spine.ledger import connect, initialize_schema
from spine.ledger.migrate import (
    CURRENT_SCHEMA_VERSION,
    current_schema_version,
    migrate_schema,
    verify_schema,
)
from spine.ledger.migrate import (
    main as migrate_main,
)
from spine.ledger.sqlite import schema_sql


class LedgerMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()

    def tearDown(self) -> None:
        self.connection.close()

    def test_empty_database_initializes_and_verifies_latest_schema(self) -> None:
        result = migrate_schema(self.connection, initialize_if_empty=True)

        self.assertEqual(result.before_version, 0)
        self.assertEqual(result.after_version, CURRENT_SCHEMA_VERSION)
        self.assertTrue(result.initialized)
        self.assertTrue(result.verified)
        verification = verify_schema(self.connection)
        self.assertEqual(verification.schema_version, 12)
        self.assertEqual(verification.integrity_check, "ok")

    def test_empty_database_requires_explicit_initialization(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_uninitialized"):
            migrate_schema(self.connection)

    def test_true_v6_schema_crosses_the_one_shot_boundary(self) -> None:
        self._initialize_v6()

        result = migrate_schema(self.connection)

        self.assertEqual(result.before_version, 6)
        self.assertEqual(result.applied_versions, (7, 8, 9, 10, 11, 12))
        self.assertEqual(result.after_version, 12)
        self.assertTrue(result.verified)
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(temporal_anchors)")}
        self.assertNotIn("recurrence_rule", columns)
        self.assertIn("timezone_database_version", columns)
        self.assertIsNotNone(
            self.connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notification_schedules'").fetchone()
        )

    def test_schema_8_migrates_to_immutable_notification_rendering_evidence(self) -> None:
        self._initialize_v6()
        from spine.ledger.migrate import _apply_migration

        _apply_migration(
            self.connection,
            version=7,
            migration_name="0007_canonical_scheduling_notifications.sql",
        )
        _apply_migration(
            self.connection,
            version=8,
            migration_name="0008_relative_temporal_bindings.sql",
        )
        self.assertEqual(current_schema_version(self.connection), 8)

        result = migrate_schema(self.connection)

        self.assertEqual(result.applied_versions, (9, 10, 11, 12))
        self.assertEqual(result.after_version, 12)
        self.assertIsNotNone(
            self.connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notification_renderings'").fetchone()
        )
        self.assertIsNotNone(
            self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = 'notification_renderings_attempt_binding_insert'"
            ).fetchone()
        )
        self.assertIsNotNone(
            self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notification_profiles'"
            ).fetchone()
        )

    def test_schema_10_migration_starts_generation_after_existing_catalog_rows(self) -> None:
        self._initialize_v6()
        from spine.ledger.migrate import _apply_migration

        for version, migration_name in (
            (7, "0007_canonical_scheduling_notifications.sql"),
            (8, "0008_relative_temporal_bindings.sql"),
            (9, "0009_notification_rendering.sql"),
            (10, "0010_notification_profiles.sql"),
        ):
            _apply_migration(
                self.connection,
                version=version,
                migration_name=migration_name,
            )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO subjects (
                  subject_id, subject_kind, display_name, status,
                  created_at_utc, updated_at_utc
                ) VALUES (
                  'existing-subject', 'person', 'Existing subject', 'active',
                  '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'
                )
                """
            )
            self.connection.execute(
                """
                INSERT INTO subject_groups (
                  group_id, group_kind, display_name, status,
                  created_at_utc, updated_at_utc
                ) VALUES (
                  'existing-group', 'household', 'Existing group', 'active',
                  '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'
                )
                """
            )
            self.connection.execute(
                """
                INSERT INTO subject_memberships (
                  membership_id, group_id, subject_id, role, status, starts_at_utc
                ) VALUES (
                  'existing-membership', 'existing-group', 'existing-subject',
                  'owner', 'active', '2026-08-01T00:00:00Z'
                )
                """
            )

        result = migrate_schema(self.connection)

        self.assertEqual(result.applied_versions, (11, 12))
        generation = self.connection.execute(
            "SELECT owner_scope_generation FROM owner_scope_catalog_state"
        ).fetchone()[0]
        self.assertEqual(generation, 0)
        group_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(subject_groups)")}
        self.assertNotIn("group_kind", group_columns)
        group = self.connection.execute(
            "SELECT display_name, status FROM subject_groups WHERE group_id = ?",
            ("existing-group",),
        ).fetchone()
        self.assertEqual(dict(group), {"display_name": "Existing group", "status": "active"})
        membership = self.connection.execute(
            "SELECT group_id, subject_id, role, status FROM subject_memberships WHERE membership_id = ?",
            ("existing-membership",),
        ).fetchone()
        self.assertEqual(
            dict(membership),
            {
                "group_id": "existing-group",
                "subject_id": "existing-subject",
                "role": "owner",
                "status": "active",
            },
        )
        with self.connection:
            self.connection.execute(
                "UPDATE subjects SET display_name = ? WHERE subject_id = ?",
                ("Updated subject", "existing-subject"),
            )
        generation = self.connection.execute(
            "SELECT owner_scope_generation FROM owner_scope_catalog_state"
        ).fetchone()[0]
        self.assertEqual(generation, 1)

    def test_preflight_rejects_each_populated_provisional_scheduling_surface(self) -> None:
        for surface in ("recurrence_rule", "notification_policy", "work_instance"):
            with self.subTest(surface=surface):
                connection = connect()
                try:
                    connection.executescript(schema_sql())
                    if surface == "recurrence_rule":
                        connection.execute(
                            """
                            INSERT INTO temporal_anchors (
                              anchor_id, anchor_kind, local_date, local_time, timezone,
                              recurrence_rule, created_at_utc
                            ) VALUES (
                              'anchor-provisional', 'local_instant', '2026-08-08', '08:00:00',
                              'America/Los_Angeles', 'FREQ=DAILY', '2026-08-01T00:00:00Z'
                            )
                            """
                        )
                    else:
                        self._seed_v6_item(connection)
                        if surface == "notification_policy":
                            connection.execute(
                                """
                                INSERT INTO temporal_anchors (
                                  anchor_id, anchor_kind, utc_instant, created_at_utc
                                ) VALUES (
                                  'anchor-provisional', 'instant_utc',
                                  '2026-08-08T08:00:00Z', '2026-08-01T00:00:00Z'
                                )
                                """
                            )
                            connection.execute(
                                """
                                INSERT INTO notification_policies (
                                  policy_id, item_id, version, recipient_subject_id,
                                  trigger_anchor_id, status, created_at_utc
                                ) VALUES (
                                  'policy-provisional', 'item-migration', 1, 'subject-owner',
                                  'anchor-provisional', 'active', '2026-08-01T00:00:00Z'
                                )
                                """
                            )
                        else:
                            connection.execute(
                                """
                                INSERT INTO work_instances (
                                  work_instance_id, item_id, item_version, work_kind,
                                  eligible_at_utc, status, attempt_count,
                                  created_at_utc, updated_at_utc
                                ) VALUES (
                                  'work-provisional', 'item-migration', 1,
                                  'notification_reminder', '2026-08-08T08:00:00Z',
                                  'eligible', 0, '2026-08-01T00:00:00Z',
                                  '2026-08-01T00:00:00Z'
                                )
                                """
                            )
                    connection.commit()

                    with self.assertRaisesRegex(SpineValidationError, "ledger_migration_provisional_scheduling_data"):
                        migrate_schema(connection)
                    self.assertEqual(current_schema_version(connection), 6)
                    self.assertIn(
                        "recurrence_rule",
                        {row["name"] for row in connection.execute("PRAGMA table_info(temporal_anchors)")},
                    )
                finally:
                    connection.close()

    def test_failed_v7_ddl_rolls_back_every_schema_change(self) -> None:
        self._initialize_v6()
        from spine.ledger.migrate import _migration_sql

        migration = _migration_sql("0007_canonical_scheduling_notifications.sql")
        broken = migration.replace(
            "\nCOMMIT;\n",
            "\nCREATE TABLE recurrence_sets (duplicate TEXT);\nCOMMIT;\n",
        )
        with patch("spine.ledger.migrate._migration_sql", return_value=broken), self.assertRaises(sqlite3.OperationalError):
            migrate_schema(self.connection)

        self.assertEqual(current_schema_version(self.connection), 6)
        self.assertIn(
            "recurrence_rule",
            {row["name"] for row in self.connection.execute("PRAGMA table_info(temporal_anchors)")},
        )
        self.assertIsNone(
            self.connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recurrence_sets'").fetchone()
        )
        self.assertEqual(self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_latest_constraints_reject_noncanonical_rows(self) -> None:
        initialize_schema(self.connection)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO notification_schedules (
                  schedule_id, policy_id, schedule_kind,
                  normalized_notification_schedule_hash
                ) VALUES ('schedule-invalid', 'policy-missing', 'unbounded', ?)
                """,
                ("a" * 64,),
            )

    def test_verify_rejects_missing_required_object_and_old_version(self) -> None:
        initialize_schema(self.connection)
        self.connection.execute("DROP INDEX work_instances_eligible_due_idx")
        with self.assertRaisesRegex(SpineValidationError, "ledger_schema_missing_indexes"):
            verify_schema(self.connection)

        connection = connect()
        try:
            connection.executescript(schema_sql())
            with self.assertRaisesRegex(SpineValidationError, "ledger_schema_version_mismatch"):
                verify_schema(connection)
        finally:
            connection.close()

    def test_migration_cli_initializes_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "spine.sqlite"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = migrate_main(["--db", str(db_path), "--initialize-if-empty"])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["before_version"], 0)
            self.assertEqual(payload["after_version"], 12)
            self.assertTrue(payload["initialized"])

    def _initialize_v6(self) -> None:
        self.connection.executescript(schema_sql())
        self.assertEqual(current_schema_version(self.connection), 6)

    def _seed_v6_item(self, connection) -> None:
        with connection:
            connection.execute(
                """
                INSERT INTO subjects (
                  subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
                ) VALUES (
                  'subject-owner', 'person', 'Owner', 'active',
                  '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO coordination_items (
                  item_id, item_type, current_version, status, created_at_utc, updated_at_utc
                ) VALUES (
                  'item-migration', 'task', 1, 'active',
                  '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO coordination_item_versions (
                  item_id, version, title, intent_hash, normalized_fields_hash,
                  created_at_utc, created_by_subject_id
                ) VALUES (
                  'item-migration', 1, 'Migration fixture', ?, ?,
                  '2026-08-01T00:00:00Z', 'subject-owner'
                )
                """,
                ("a" * 64, "b" * 64),
            )
            connection.execute(
                """
                INSERT INTO task_details (item_id, version, task_status)
                VALUES ('item-migration', 1, 'open')
                """
            )


if __name__ == "__main__":
    unittest.main()
