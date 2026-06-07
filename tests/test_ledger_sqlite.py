import sqlite3
import unittest

from spine.core import SpineValidationError
from spine.core.hashing import (
    audit_log_payload_hash,
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.ledger import assert_ledger_invariants, connect, initialize_schema, schema_sql


NOW = "2026-06-06T10:00:00Z"


class LedgerSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_schema_initializes_expected_tables_and_foreign_keys(self) -> None:
        table_names = {
            row["name"]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertIn("subjects", table_names)
        self.assertIn("temporal_anchors", table_names)
        self.assertIn("coordination_items", table_names)
        self.assertIn("coordination_item_versions", table_names)
        self.assertIn("event_details", table_names)
        self.assertIn("task_details", table_names)
        self.assertIn("locations", table_names)
        self.assertIn("item_locations", table_names)
        self.assertIn("item_subject_roles", table_names)
        self.assertIn("notification_policies", table_names)
        self.assertIn("coordination_item_relations", table_names)
        self.assertIn("audit_log", table_names)
        self.assertIn("ledger_schema", table_names)
        self.assertEqual(self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertIn("CREATE TABLE IF NOT EXISTS subjects", schema_sql())

    def test_insert_subject(self) -> None:
        insert_subject(self.connection)

        row = self.connection.execute("SELECT * FROM subjects WHERE subject_id = 'subject-1'").fetchone()
        self.assertEqual(row["subject_kind"], "person")
        self.assertEqual(row["status"], "active")

    def test_valid_temporal_anchor_shapes(self) -> None:
        with self.connection:
            insert_instant_anchor(self.connection, "anchor-instant")
            insert_local_date_anchor(self.connection, "anchor-date")
            insert_local_instant_anchor(self.connection, "anchor-local-instant")
            insert_utc_window_anchor(self.connection, "anchor-window")
            insert_local_window_anchor(self.connection, "anchor-local-window")

        count = self.connection.execute("SELECT COUNT(*) FROM temporal_anchors").fetchone()[0]
        self.assertEqual(count, 5)

    def test_invalid_temporal_anchor_shape_is_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO temporal_anchors (
                  anchor_id, anchor_kind, local_date, utc_instant, created_at_utc
                )
                VALUES ('bad-anchor', 'instant_utc', '2026-06-06', '2026-06-06T10:00:00Z', ?)
                """,
                (NOW,),
            )

    def test_valid_event_v1_bundle_satisfies_invariants(self) -> None:
        insert_valid_event_bundle(self.connection)

        assert_ledger_invariants(self.connection)

    def test_valid_task_v1_bundle_satisfies_invariants(self) -> None:
        insert_valid_task_bundle(self.connection)

        assert_ledger_invariants(self.connection)

    def test_event_bundle_missing_event_detail_fails_invariant_validation(self) -> None:
        insert_event_bundle_without_detail(self.connection)

        with self.assertRaisesRegex(SpineValidationError, "ledger_detail_row_mismatch"):
            assert_ledger_invariants(self.connection)

    def test_event_bundle_with_task_detail_is_rejected_by_trigger(self) -> None:
        with self.assertRaisesRegex(sqlite3.IntegrityError, "task_details requires"):
            with self.connection:
                insert_subject(self.connection)
                insert_instant_anchor(self.connection, "task-anchor")
                insert_item_shell(
                    self.connection,
                    item_id="event-with-task-detail",
                    item_type="event",
                )
                insert_item_version(
                    self.connection,
                    item_id="event-with-task-detail",
                    title="Wrong detail",
                )
                self.connection.execute(
                    """
                    INSERT INTO task_details (
                      item_id, version, task_status, due_anchor_id
                    )
                    VALUES ('event-with-task-detail', 1, 'open', 'task-anchor')
                    """
                )

    def test_non_contiguous_version_is_rejected_by_trigger(self) -> None:
        insert_valid_event_bundle(self.connection)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "contiguous"):
            self.connection.execute(
                """
                INSERT INTO coordination_item_versions (
                  item_id, version, title, intent_hash, normalized_fields_hash,
                  created_at_utc, created_by_subject_id
                )
                VALUES (?, 3, ?, ?, ?, ?, 'subject-1')
                """,
                (
                    "event-1",
                    "Skipped version",
                    coordination_item_version_intent_hash(title="Skipped version"),
                    coordination_item_version_normalized_fields_hash(title="Skipped version"),
                    NOW,
                ),
            )

    def test_current_version_not_max_fails_invariant_validation(self) -> None:
        insert_valid_event_bundle(self.connection)
        with self.connection:
            insert_instant_anchor(self.connection, "event-1-v2-start")
            insert_item_version(
                self.connection,
                item_id="event-1",
                version=2,
                title="Dentist updated",
            )
            self.connection.execute(
                """
                INSERT INTO event_details (
                  item_id, version, event_status, all_day, start_anchor_id
                )
                VALUES ('event-1', 2, 'scheduled', 0, 'event-1-v2-start')
                """
            )

        with self.assertRaisesRegex(SpineValidationError, "ledger_current_version_mismatch"):
            assert_ledger_invariants(self.connection)

    def test_event_time_shape_is_rejected_by_trigger(self) -> None:
        with self.assertRaisesRegex(sqlite3.IntegrityError, "event_details time shape"):
            with self.connection:
                insert_subject(self.connection)
                insert_instant_anchor(self.connection, "event-start")
                insert_item_shell(self.connection, item_id="bad-event", item_type="event")
                insert_item_version(self.connection, item_id="bad-event", title="Bad event")
                self.connection.execute(
                    """
                    INSERT INTO event_details (
                      item_id, version, event_status, all_day, start_anchor_id
                    )
                    VALUES ('bad-event', 1, 'scheduled', 1, 'event-start')
                    """
                )


def insert_subject(connection: sqlite3.Connection, subject_id: str = "subject-1") -> None:
    connection.execute(
        """
        INSERT INTO subjects (
          subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
        )
        VALUES (?, 'person', 'Chris', 'active', ?, ?)
        """,
        (subject_id, NOW, NOW),
    )


def insert_instant_anchor(connection: sqlite3.Connection, anchor_id: str) -> None:
    connection.execute(
        """
        INSERT INTO temporal_anchors (anchor_id, anchor_kind, utc_instant, created_at_utc)
        VALUES (?, 'instant_utc', ?, ?)
        """,
        (anchor_id, NOW, NOW),
    )


def insert_local_instant_anchor(connection: sqlite3.Connection, anchor_id: str) -> None:
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, local_time, timezone, created_at_utc
        )
        VALUES (?, 'local_instant', '2026-06-06', '10:00:00', 'America/New_York', ?)
        """,
        (anchor_id, NOW),
    )


def insert_local_date_anchor(connection: sqlite3.Connection, anchor_id: str) -> None:
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, timezone, created_at_utc
        )
        VALUES (?, 'local_date', '2026-06-06', 'America/New_York', ?)
        """,
        (anchor_id, NOW),
    )


def insert_utc_window_anchor(connection: sqlite3.Connection, anchor_id: str) -> None:
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, window_start_utc, window_end_utc, created_at_utc
        )
        VALUES (?, 'utc_window', '2026-06-06T10:00:00Z', '2026-06-06T11:00:00Z', ?)
        """,
        (anchor_id, NOW),
    )


def insert_local_window_anchor(connection: sqlite3.Connection, anchor_id: str) -> None:
    connection.execute(
        """
        INSERT INTO temporal_anchors (
          anchor_id, anchor_kind, local_date, timezone, created_at_utc
        )
        VALUES (?, 'local_window', '2026-06-06', 'America/New_York', ?)
        """,
        (anchor_id, NOW),
    )


def insert_item_shell(connection: sqlite3.Connection, *, item_id: str, item_type: str) -> None:
    connection.execute(
        """
        INSERT INTO coordination_items (
          item_id, item_type, current_version, status, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, 1, 'active', ?, ?)
        """,
        (item_id, item_type, NOW, NOW),
    )


def insert_item_version(
    connection: sqlite3.Connection,
    *,
    item_id: str,
    title: str,
    version: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO coordination_item_versions (
          item_id, version, title, intent_hash, normalized_fields_hash,
          created_at_utc, created_by_subject_id
        )
        VALUES (?, ?, ?, ?, ?, ?, 'subject-1')
        """,
        (
            item_id,
            version,
            title,
            coordination_item_version_intent_hash(title=title),
            coordination_item_version_normalized_fields_hash(title=title),
            NOW,
        ),
    )


def insert_audit_log(connection: sqlite3.Connection, *, item_id: str, audit_id: str) -> None:
    connection.execute(
        """
        INSERT INTO audit_log (
          audit_id, item_id, stage, action, payload_hash, created_at_utc
        )
        VALUES (?, ?, 'item', 'created', ?, ?)
        """,
        (
            audit_id,
            item_id,
            audit_log_payload_hash({"action": "created", "item_id": item_id}),
            NOW,
        ),
    )


def insert_valid_event_bundle(connection: sqlite3.Connection) -> None:
    with connection:
        insert_subject(connection)
        insert_instant_anchor(connection, "event-1-start")
        insert_item_shell(connection, item_id="event-1", item_type="event")
        insert_item_version(connection, item_id="event-1", title="Dentist")
        connection.execute(
            """
            INSERT INTO event_details (
              item_id, version, event_status, all_day, start_anchor_id
            )
            VALUES ('event-1', 1, 'scheduled', 0, 'event-1-start')
            """
        )
        insert_audit_log(connection, item_id="event-1", audit_id="audit-event-1")


def insert_valid_task_bundle(connection: sqlite3.Connection) -> None:
    with connection:
        insert_subject(connection)
        insert_local_date_anchor(connection, "task-1-due")
        insert_item_shell(connection, item_id="task-1", item_type="task")
        insert_item_version(connection, item_id="task-1", title="Submit forms")
        connection.execute(
            """
            INSERT INTO task_details (
              item_id, version, task_status, due_anchor_id
            )
            VALUES ('task-1', 1, 'open', 'task-1-due')
            """
        )
        insert_audit_log(connection, item_id="task-1", audit_id="audit-task-1")


def insert_event_bundle_without_detail(connection: sqlite3.Connection) -> None:
    with connection:
        insert_subject(connection)
        insert_item_shell(connection, item_id="event-missing-detail", item_type="event")
        insert_item_version(connection, item_id="event-missing-detail", title="Incomplete event")
        insert_audit_log(connection, item_id="event-missing-detail", audit_id="audit-missing-detail")


if __name__ == "__main__":
    unittest.main()
