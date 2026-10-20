"""Real disposable-ledger checks for the private bounded people reader."""

import unittest

from spine.core.errors import SpineValidationError
from spine.ledger import (
    ItemSubjectRoleInput,
    TemporalAnchorInput,
    connect,
    create_event_v1,
    create_next_item_version,
    create_task_v1,
    initialize_schema,
)
from spine.ledger.people import read_people_snapshot

NOW = "2026-10-20T10:00:00Z"


class PeopleLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        initialize_schema(self.db)
        with self.db:
            self.db.executemany(
                "INSERT INTO subjects(subject_id,subject_kind,display_name,status,created_at_utc,updated_at_utc) "
                "VALUES (?, 'person', 'Private display label', 'active', ?, ?)",
                [(f"s{index}", NOW, NOW) for index in range(102)],
            )

    def task(self, roles=()):
        create_task_v1(self.db, item_id="task", audit_id="create-task", created_at_utc=NOW,
                       created_by_subject_id="s0", title="Unscheduled", subject_roles=roles)

    def test_current_empty_unscheduled_task_is_read_only(self):
        self.task()
        before = self.db.total_changes
        statements = []
        self.db.execute("PRAGMA query_only=ON")
        self.db.set_trace_callback(statements.append)
        snapshot = read_people_snapshot(self.db, item_id="task")
        self.assertEqual((snapshot.item_type, snapshot.item_version, snapshot.current_version), ("task", 1, 1))
        self.assertEqual(snapshot.associations, ())
        self.assertEqual(self.db.total_changes, before)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].lstrip().startswith("SELECT"))

    def test_history_retains_original_id_and_separate_current_version(self):
        self.task((ItemSubjectRoleInput(subject_id="s1", role="assignee", status="inactive", item_subject_role_id="original"),))
        create_next_item_version(self.db, item_id="task", target_version=1, title="Later",
            audit_id="later", created_at_utc=NOW, created_by_subject_id="s0")
        before = self.db.total_changes
        self.db.execute("PRAGMA query_only=ON")
        historical = read_people_snapshot(self.db, item_id="task", version=1)
        current = read_people_snapshot(self.db, item_id="task")
        self.assertEqual((historical.item_version, historical.current_version), (1, 2))
        self.assertEqual(historical.associations[0].item_subject_role_id, "original")
        self.assertEqual(historical.associations[0].status, "inactive")
        self.assertNotEqual(current.associations[0].item_subject_role_id, "original")
        self.assertEqual(self.db.total_changes, before)

    def test_projection_selects_only_managed_role_and_sorts_subjects(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=subject, role=role, item_subject_role_id=f"row-{index}")
                        for index, (subject, role) in enumerate([
                            ("s2", "assignee"), ("s1", "assignee"), ("s3", "owner"),
                            ("s4", "participant"), ("s5", "watcher"), ("s6", "recipient"),
                        ])))
        snapshot = read_people_snapshot(self.db, item_id="task")
        self.assertEqual([row.subject_id for row in snapshot.associations], ["s1", "s2"])
        self.assertTrue(all(row.role == "assignee" for row in snapshot.associations))
        self.assertNotIn("Private display label", repr(snapshot))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_subject_roles").fetchone()[0], 6)

    def test_event_selects_participants_not_assignees(self):
        create_event_v1(self.db, item_id="event", audit_id="create-event", created_at_utc=NOW,
            created_by_subject_id="s0", title="Event", all_day=False,
            start_anchor=TemporalAnchorInput(anchor_id="start", anchor_kind="instant_utc", utc_instant=NOW),
            subject_roles=(ItemSubjectRoleInput(subject_id="s1", role="participant", item_subject_role_id="p"),
                           ItemSubjectRoleInput(subject_id="s2", role="assignee", item_subject_role_id="a")))
        self.assertEqual([row.item_subject_role_id for row in read_people_snapshot(self.db, item_id="event").associations], ["p"])

    def test_missing_item_and_version_fail_without_echoing_hidden_id(self):
        self.task()
        for item, version in (("hidden-identifier", None), ("task", 999)):
            with self.subTest(item=item), self.assertRaises(SpineValidationError) as caught:
                read_people_snapshot(self.db, item_id=item, version=version)
            self.assertEqual(caught.exception.code, "referenced_row_not_found:item_id")
            self.assertNotIn("hidden-identifier", caught.exception.message)

    def test_invalid_versions_refuse_before_query(self):
        self.task()
        for version in (True, 0, -1, 1.0, "1", 2**63):
            statements = []
            self.db.set_trace_callback(statements.append)
            with self.subTest(version=version), self.assertRaises(SpineValidationError):
                read_people_snapshot(self.db, item_id="task", version=version)
            self.assertEqual(statements, [])

    def test_exact_bound_succeeds_but_overlimit_roles_are_not_truncated(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=f"s{i}", role="assignee", item_subject_role_id=f"role-{i}")
                        for i in range(100)))
        self.assertEqual(len(read_people_snapshot(self.db, item_id="task").associations), 100)
        # Existing oversized facts may be present; the reader never repairs them.
        with self.db:
            self.db.execute(
                "INSERT INTO item_subject_roles VALUES ('extra-owner', 'task', 1, 's101', 'owner', 'active', ?)", (NOW,))
        before = self.db.total_changes
        with self.assertRaises(SpineValidationError) as caught:
            read_people_snapshot(self.db, item_id="task")
        self.assertEqual(caught.exception.code, "capacity_exceeded:people")
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM item_subject_roles").fetchone()[0], 101)

    def test_terminal_item_remains_readable(self):
        self.task()
        from spine.ledger import complete_task
        complete_task(self.db, item_id="task", target_version=1, audit_id="complete", completed_at_utc=NOW,
                      completed_by_subject_id="s0")
        self.assertEqual(read_people_snapshot(self.db, item_id="task").current_version, 2)
