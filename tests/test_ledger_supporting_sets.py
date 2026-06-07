import sqlite3
import unittest

from spine.core import SpineValidationError
from spine.core.hashing import (
    coordination_item_version_intent_hash,
    coordination_item_version_normalized_fields_hash,
)
from spine.ledger import (
    ItemLocationInput,
    ItemSubjectRoleInput,
    LocationInput,
    NotificationPolicyInput,
    TemporalAnchorInput,
    assert_ledger_invariants,
    connect,
    create_event_v1,
    create_item_relation,
    create_next_item_version,
    create_task_v1,
    get_active_relations,
    get_current_item,
    get_derived_relations,
    initialize_schema,
)


NOW = "2026-06-06T10:00:00Z"
SUBJECT_ID = "subject-1"
OTHER_SUBJECT_ID = "subject-2"


class LedgerSupportingSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        insert_subject(self.connection, SUBJECT_ID, "Chris")
        insert_subject(self.connection, OTHER_SUBJECT_ID, "Dana")

    def tearDown(self) -> None:
        self.connection.close()

    def test_create_event_with_primary_location(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-location",
            audit_id="audit-event-location",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=instant_anchor("event-location-start"),
            item_locations=(
                ItemLocationInput(
                    item_location_id="item-location-1",
                    role="primary",
                    location=LocationInput(
                        location_id="location-1",
                        label="Main Street Dental",
                        kind="place",
                        timezone="America/New_York",
                    ),
                ),
            ),
        )

        current = get_current_item(self.connection, "event-location")
        self.assertEqual(len(current["locations"]), 1)
        self.assertEqual(current["locations"][0]["role"], "primary")
        self.assertEqual(current["locations"][0]["label"], "Main Street Dental")
        self.assertEqual(current["locations"][0]["kind"], "place")
        assert_ledger_invariants(self.connection)

    def test_reject_duplicate_location_role_for_same_item_version_atomically(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "item_create_rejected"):
            create_event_v1(
                self.connection,
                item_id="event-duplicate-location",
                audit_id="audit-event-duplicate-location",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
                title="Dentist",
                all_day=False,
                start_anchor=instant_anchor("event-duplicate-location-start"),
                item_locations=(
                    ItemLocationInput(
                        item_location_id="item-location-a",
                        role="primary",
                        location=LocationInput(
                            location_id="location-a",
                            label="Main Street Dental",
                            kind="place",
                        ),
                    ),
                    ItemLocationInput(
                        item_location_id="item-location-b",
                        role="primary",
                        location=LocationInput(
                            location_id="location-b",
                            label="Backup Dental",
                            kind="place",
                        ),
                    ),
                ),
            )

        self.assert_item_absent("event-duplicate-location")
        self.assert_location_absent("location-a")
        self.assert_location_absent("location-b")

    def test_referenced_location_canonical_fields_are_immutable(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-immutable-location",
            audit_id="audit-event-immutable-location",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=instant_anchor("event-immutable-location-start"),
            item_locations=(
                ItemLocationInput(
                    item_location_id="item-location-immutable",
                    role="primary",
                    location=LocationInput(
                        location_id="location-immutable",
                        label="Main Street Dental",
                        kind="place",
                    ),
                ),
            ),
        )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
            self.connection.execute(
                "UPDATE locations SET label = 'Changed Dental' WHERE location_id = 'location-immutable'"
            )

        with self.connection:
            self.connection.execute(
                """
                UPDATE locations
                SET metadata_json = '{"note":"parking behind building"}',
                    updated_at_utc = '2026-06-06T11:00:00Z'
                WHERE location_id = 'location-immutable'
                """
            )
        row = self.connection.execute(
            "SELECT metadata_json FROM locations WHERE location_id = 'location-immutable'"
        ).fetchone()
        self.assertEqual(row["metadata_json"], '{"note":"parking behind building"}')

    def test_create_task_with_assignee(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-assignee",
            audit_id="audit-task-assignee",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
            subject_roles=(
                ItemSubjectRoleInput(
                    item_subject_role_id="role-task-assignee",
                    subject_id=OTHER_SUBJECT_ID,
                    role="assignee",
                ),
            ),
        )

        current = get_current_item(self.connection, "task-assignee")
        self.assertEqual(len(current["subject_roles"]), 1)
        self.assertEqual(current["subject_roles"][0]["subject_id"], OTHER_SUBJECT_ID)
        self.assertEqual(current["subject_roles"][0]["role"], "assignee")
        assert_ledger_invariants(self.connection)

    def test_create_notification_policy_as_inert_versioned_intent(self) -> None:
        create_event_v1(
            self.connection,
            item_id="event-notification",
            audit_id="audit-event-notification",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Dentist",
            all_day=False,
            start_anchor=instant_anchor("event-notification-start"),
            notification_policies=(
                NotificationPolicyInput(
                    policy_id="policy-event-notification",
                    recipient_subject_id=OTHER_SUBJECT_ID,
                    trigger_anchor=instant_anchor("policy-event-notification-trigger"),
                    channel_preference_ref="sms",
                ),
            ),
        )

        current = get_current_item(self.connection, "event-notification")
        self.assertEqual(len(current["notification_policies"]), 1)
        policy = current["notification_policies"][0]
        self.assertEqual(policy["recipient_subject_id"], OTHER_SUBJECT_ID)
        self.assertEqual(policy["trigger_anchor_id"], "policy-event-notification-trigger")
        self.assertEqual(policy["status"], "active")

    def test_relation_depends_on_and_derived_blocks(self) -> None:
        create_task_pair(self.connection)

        create_item_relation(
            self.connection,
            relation_id="relation-depends-on",
            source_item_id="task-dependent",
            target_item_id="task-prerequisite",
            relation_type="depends_on",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
        )

        stored = get_active_relations(self.connection, source_item_id="task-dependent")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["relation_type"], "depends_on")

        derived = get_derived_relations(
            self.connection,
            source_item_id="task-prerequisite",
            relation_type="blocks",
        )
        self.assertEqual(
            derived,
            [
                {
                    "source_item_id": "task-prerequisite",
                    "target_item_id": "task-dependent",
                    "relation_type": "blocks",
                    "stored_relation_id": "relation-depends-on",
                    "stored_relation_type": "depends_on",
                }
            ],
        )

    def test_part_of_relation_derives_contains(self) -> None:
        create_task_pair(self.connection)

        create_item_relation(
            self.connection,
            relation_id="relation-part-of",
            source_item_id="task-dependent",
            target_item_id="task-prerequisite",
            relation_type="part_of",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
        )

        derived = get_derived_relations(
            self.connection,
            source_item_id="task-prerequisite",
            relation_type="contains",
        )
        self.assertEqual(derived[0]["target_item_id"], "task-dependent")
        self.assertEqual(derived[0]["stored_relation_type"], "part_of")

    def test_reject_stored_blocks_relation(self) -> None:
        create_task_pair(self.connection)

        with self.assertRaisesRegex(SpineValidationError, "reserved_relation_type"):
            create_item_relation(
                self.connection,
                relation_id="relation-blocks",
                source_item_id="task-prerequisite",
                target_item_id="task-dependent",
                relation_type="blocks",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
            )

    def test_reject_active_duplicate_relation(self) -> None:
        create_task_pair(self.connection)
        create_item_relation(
            self.connection,
            relation_id="relation-duplicate-a",
            source_item_id="task-dependent",
            target_item_id="task-prerequisite",
            relation_type="depends_on",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
        )

        with self.assertRaisesRegex(SpineValidationError, "item_relation_rejected"):
            create_item_relation(
                self.connection,
                relation_id="relation-duplicate-b",
                source_item_id="task-dependent",
                target_item_id="task-prerequisite",
                relation_type="depends_on",
                created_at_utc=NOW,
                created_by_subject_id=SUBJECT_ID,
            )

    def test_supporting_sets_copy_forward_into_v2(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-copy-forward",
            audit_id="audit-task-copy-forward-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
            item_locations=(
                ItemLocationInput(
                    item_location_id="copy-forward-location-role",
                    role="primary",
                    location=LocationInput(
                        location_id="copy-forward-location",
                        label="Home",
                        kind="place",
                    ),
                ),
            ),
            subject_roles=(
                ItemSubjectRoleInput(
                    item_subject_role_id="copy-forward-subject-role",
                    subject_id=OTHER_SUBJECT_ID,
                    role="assignee",
                ),
            ),
            notification_policies=(
                NotificationPolicyInput(
                    policy_id="copy-forward-policy",
                    recipient_subject_id=OTHER_SUBJECT_ID,
                    trigger_anchor=instant_anchor("copy-forward-policy-trigger"),
                ),
            ),
        )

        create_next_item_version(
            self.connection,
            item_id="task-copy-forward",
            target_version=1,
            audit_id="audit-task-copy-forward-v2",
            created_at_utc="2026-06-06T11:00:00Z",
            created_by_subject_id=SUBJECT_ID,
            title="Submit updated forms",
        )

        current = get_current_item(self.connection, "task-copy-forward")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["locations"][0]["item_location_id"], "copy-forward-location-role-v2")
        self.assertEqual(current["locations"][0]["location_id"], "copy-forward-location")
        self.assertEqual(current["subject_roles"][0]["item_subject_role_id"], "copy-forward-subject-role-v2")
        self.assertEqual(current["notification_policies"][0]["policy_id"], "copy-forward-policy-v2")
        self.assertEqual(current["notification_policies"][0]["trigger_anchor_id"], "copy-forward-policy-trigger")
        assert_ledger_invariants(self.connection)

    def test_current_reads_do_not_fallback_to_prior_supporting_sets(self) -> None:
        create_task_v1(
            self.connection,
            item_id="task-no-fallback",
            audit_id="audit-task-no-fallback-create",
            created_at_utc=NOW,
            created_by_subject_id=SUBJECT_ID,
            title="Submit forms",
            subject_roles=(
                ItemSubjectRoleInput(
                    item_subject_role_id="no-fallback-role",
                    subject_id=OTHER_SUBJECT_ID,
                    role="assignee",
                ),
            ),
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO coordination_item_versions (
                  item_id, version, title, intent_hash, normalized_fields_hash,
                  created_at_utc, created_by_subject_id
                )
                VALUES (?, 2, ?, ?, ?, ?, ?)
                """,
                (
                    "task-no-fallback",
                    "Submit forms v2",
                    coordination_item_version_intent_hash(title="Submit forms v2"),
                    coordination_item_version_normalized_fields_hash(title="Submit forms v2"),
                    "2026-06-06T11:00:00Z",
                    SUBJECT_ID,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO task_details (
                  item_id, version, task_status
                )
                VALUES ('task-no-fallback', 2, 'open')
                """
            )
            self.connection.execute(
                """
                UPDATE coordination_items
                SET current_version = 2, updated_at_utc = '2026-06-06T11:00:00Z'
                WHERE item_id = 'task-no-fallback'
                """
            )

        current = get_current_item(self.connection, "task-no-fallback")
        self.assertEqual(current["current_version"], 2)
        self.assertEqual(current["subject_roles"], [])

    def assert_item_absent(self, item_id: str) -> None:
        count = self.connection.execute(
            "SELECT COUNT(*) FROM coordination_items WHERE item_id = ?",
            (item_id,),
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def assert_location_absent(self, location_id: str) -> None:
        count = self.connection.execute(
            "SELECT COUNT(*) FROM locations WHERE location_id = ?",
            (location_id,),
        ).fetchone()[0]
        self.assertEqual(count, 0)


def create_task_pair(connection: sqlite3.Connection) -> None:
    create_task_v1(
        connection,
        item_id="task-dependent",
        audit_id="audit-task-dependent",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Dependent task",
    )
    create_task_v1(
        connection,
        item_id="task-prerequisite",
        audit_id="audit-task-prerequisite",
        created_at_utc=NOW,
        created_by_subject_id=SUBJECT_ID,
        title="Prerequisite task",
    )


def insert_subject(connection: sqlite3.Connection, subject_id: str, display_name: str) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO subjects (
              subject_id, subject_kind, display_name, status, created_at_utc, updated_at_utc
            )
            VALUES (?, 'person', ?, 'active', ?, ?)
            """,
            (subject_id, display_name, NOW, NOW),
        )


def instant_anchor(anchor_id: str) -> TemporalAnchorInput:
    return TemporalAnchorInput(
        anchor_id=anchor_id,
        anchor_kind="instant_utc",
        utc_instant="2026-06-06T14:00:00Z",
    )


if __name__ == "__main__":
    unittest.main()
