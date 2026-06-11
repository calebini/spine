import unittest

from spine.core import SpineValidationError
from spine.ledger import (
    TemporalAnchorInput,
    connect,
    create_task_v1,
    create_work_instance,
    initialize_schema,
    require_utc_z,
)
from spine.services import list_eligible_work


NOW = "2026-06-06T10:00:00Z"
SUBJECT_ID = "subject-1"


class LedgerTimestampTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def test_require_utc_z_accepts_canonical_second_precision_timestamp(self) -> None:
        self.assertEqual(require_utc_z("created_at_utc", NOW), NOW)

    def test_require_utc_z_rejects_offsets_fractional_seconds_and_invalid_dates(self) -> None:
        invalid_values = (
            "2026-06-06T10:00:00+00:00",
            "2026-06-06T10:00:00.123456Z",
            "2026-02-31T10:00:00Z",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
                    require_utc_z("created_at_utc", value)

    def test_item_creation_rejects_non_canonical_created_at_utc(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
            create_task_v1(
                self.connection,
                item_id="task-bad-created-at",
                audit_id="audit-bad-created-at",
                created_at_utc="2026-06-06T10:00:00+00:00",
                created_by_subject_id=SUBJECT_ID,
                title="Submit forms",
            )

    def test_temporal_anchor_rejects_fractional_utc_instant(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
            create_task_v1(
                self.connection,
                item_id="task-bad-anchor",
                audit_id="audit-bad-anchor",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Submit forms",
                due_anchor=TemporalAnchorInput(
                    anchor_kind="instant_utc",
                    utc_instant="2026-06-06T09:00:00.1Z",
                ),
            )

    def test_work_creation_rejects_non_canonical_eligible_and_retry_timestamps(self) -> None:
        create_task(self.connection)

        with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
            create_work_instance(
                self.connection,
                work_instance_id="work-bad-eligible",
                item_id="task-timestamps",
                item_version=1,
                eligible_at_utc="2026-06-06T09:00:00+00:00",
                created_at_utc=NOW,
            )

        with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
            create_work_instance(
                self.connection,
                work_instance_id="work-bad-retry",
                item_id="task-timestamps",
                item_version=1,
                eligible_at_utc="2026-06-06T09:00:00Z",
                created_at_utc=NOW,
                next_attempt_at_utc="2026-06-06T09:30:00.000001Z",
            )

    def test_list_eligible_work_rejects_non_canonical_now(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "invalid_utc_timestamp"):
            list_eligible_work(self.connection, now_utc="2026-06-06T10:00:00+00:00")


def create_task(connection) -> None:
    create_task_v1(
        connection,
        item_id="task-timestamps",
        audit_id="audit-task-timestamps",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Submit forms",
    )


def insert_subject(connection) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO subjects (
              subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
            )
            VALUES (?, 'person', 'Chris', 'active', ?, ?)
            """,
            (SUBJECT_ID, NOW, NOW),
        )


if __name__ == "__main__":
    unittest.main()
