"""Real disposable roster/label admission; item grants never imply directory access."""

import unittest

import test_people_ledger as foundation

from spine.commands import CommandContext, handle
from spine.commands.facet_runtime import FacetBudget
from spine.core.errors import SpineValidationError
from spine.ledger import ItemSubjectRoleInput
from spine.ledger.people import read_people_snapshot
from spine.services.people_directory import PeopleDirectory

AT = foundation.NOW
PAST = '2026-01-01T00:00:00Z'
FUTURE = '2026-11-01T00:00:00Z'
GROUP = {'owner_kind': 'subject_group', 'owner_group_id': 'group'}


class PeopleDirectoryTests(unittest.TestCase):
    def setUp(self):
        foundation.PeopleLedgerTests.setUp(self)
        result = handle('subject_group.upsert', {'command_id': 'group', 'actor_subject_id': 's0',
            'group_id': 'group', 'display_name': 'Any group', 'updated_at_utc': AT}, CommandContext(ledger=self.db))
        self.assertTrue(result['ok'], result)

    task = foundation.PeopleLedgerTests.task

    def member(self, subject, *, role='member', status='active', start=PAST, identity=None):
        with self.db:
            self.db.execute('INSERT INTO subject_memberships VALUES (?,?,?,?,?,?,?,1)',
                (identity or 'm-' + subject, 'group', subject, role, status, start, AT if status == 'ended' else None))

    def directory(self, subject='s0', **kwargs):
        return PeopleDirectory(self.db, FacetBudget(), observed_at_utc=AT, subject=subject, **kwargs)

    def test_all_group_roles_can_discover_without_adoption(self):
        self.member('s0')
        self.member('s1')
        for role in ('member', 'admin', 'owner'):
            with self.db:
                self.db.execute('UPDATE subject_memberships SET role=? WHERE subject_id=?', (role, 's0'))
            directory = self.directory()
            rows, source = directory.roster(GROUP)
            self.assertEqual([row['subject_id'] for row in rows], ['s0', 's1'])
            self.assertNotIn('account', repr(rows))
            self.assertTrue(source)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM adopted_access_groups').fetchone()[0], 0)

    def test_scope_denial_precedes_target_probe(self):
        self.member('s1')
        seen = []
        self.db.set_trace_callback(seen.append)
        with self.assertRaises(SpineValidationError) as caught:
            self.directory().admit(('s1',), owner=GROUP)
        self.assertEqual(caught.exception.code, 'referenced_row_not_found:people')
        self.assertFalse(any("FROM subjects WHERE subject_id='s1'" in sql for sql in seen))

    def test_roster_current_members_inactive_people_agent_and_future_transition(self):
        self.member('s0')
        self.member('s1')
        self.member('s2', status='ended')
        self.member('s3', start=FUTURE)
        self.member('s4')
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s1'")
            self.db.execute("UPDATE subjects SET subject_kind='agent' WHERE subject_id='s4'")
        directory = self.directory()
        all_rows, _ = directory.roster(GROUP, status='all')
        self.assertEqual([row['subject_id'] for row in all_rows], ['s0', 's1', 's4'])
        self.assertFalse(all_rows[1]['eligible_for_fresh_selection'])
        self.assertEqual(directory.valid_until, FUTURE)
        rows, _ = self.directory().roster(GROUP, status='inactive')
        self.assertEqual([row['subject_id'] for row in rows], ['s1'])
        rows, _ = self.directory().roster(GROUP, kind='agent')
        self.assertEqual([row['subject_id'] for row in rows], ['s4'])

    def test_private_scope_does_not_expand_via_shared_group(self):
        self.member('s0')
        self.member('s1')
        scope = {'owner_kind': 'subject', 'owner_subject_id': 's0'}
        self.directory().admit(('s0',), owner=scope)
        with self.assertRaises(SpineValidationError):
            self.directory().admit(('s1',), owner=scope)
        with self.assertRaises(SpineValidationError):
            self.directory().roster({'owner_kind': 'subject', 'owner_subject_id': 's1'})
        self.directory(subject=None).admit(('s1',))

    def test_group_fresh_selection_active_exact_current_members_only(self):
        self.member('s0')
        self.member('s1')
        self.member('s2', status='ended')
        self.member('s3', start=FUTURE)
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s1'")
        for subject in ('s1', 's2', 's3', 'missing'):
            with self.subTest(subject=subject), self.assertRaises(SpineValidationError):
                self.directory().admit((subject,), owner=GROUP)
        self.directory().admit(('s0',), owner=GROUP)
        self.directory().admit((), owner={'owner_kind': 'subject', 'owner_subject_id': 's99'})

    def test_current_labels_and_history_are_independent(self):
        self.member('s0')
        self.member('s1')
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee'),
                   ItemSubjectRoleInput(subject_id='s2', role='assignee', status='inactive')))
        snapshot = read_people_snapshot(self.db, item_id='task')
        before = self.directory().projection(snapshot)
        self.assertEqual(before['subjects'][0]['label']['availability'], 'available')
        self.assertEqual(before['subjects'][1]['label'], {'availability': 'not_disclosed'})
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Renamed',status='inactive' WHERE subject_id='s1'")
        after = self.directory().projection(snapshot)
        self.assertEqual(after['subjects'][0]['label']['display_name'], 'Renamed')
        self.assertEqual(after['subjects'][0]['label']['status'], 'inactive')
        self.assertEqual(after['associations'], before['associations'])

    def test_hidden_label_edits_never_enter_metadata_or_proof(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee'),))
        snapshot = read_people_snapshot(self.db, item_id='task')
        a = self.directory()
        first = a.projection(snapshot)
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Hidden rename',status='inactive' WHERE subject_id='s1'")
        b = self.directory()
        self.assertEqual(first, b.projection(snapshot))
        self.assertEqual((a.metadata, a.proof()), (b.metadata, b.proof()))
        self.assertNotIn('Hidden rename', repr(b.proof()))

    def test_inactive_or_missing_owner_scope_never_authorizes(self):
        self.member('s0')
        with self.db:
            self.db.execute("UPDATE subject_groups SET status='inactive' WHERE group_id='group'")
        with self.assertRaises(SpineValidationError):
            self.directory().roster(GROUP)
        with self.assertRaises(SpineValidationError):
            self.directory().admit(('s0',), owner=GROUP)

    def test_conflicting_effective_memberships_fail_closed(self):
        self.member('s0')
        self.member('s1')
        self.member('s1', role='admin', identity='duplicate')
        for op in (lambda: self.directory().roster(GROUP), lambda: self.directory().admit(('s1',), owner=GROUP),
                   lambda: self.directory().label('s1')):
            with self.assertRaises(SpineValidationError):
                op()

    def test_budget_overflow_is_not_nondisclosure_or_truncation(self):
        for index in range(100):
            self.member('s' + str(index))
        directory = self.directory()
        before = self.db.total_changes
        with self.assertRaises(SpineValidationError) as caught:
            directory.roster(GROUP)
        self.assertEqual(caught.exception.code, 'environment_failure:capacity')
        self.assertEqual(self.db.total_changes, before)
        budget = FacetBudget(resources={('item', str(i)) for i in range(100)})
        with self.assertRaises(SpineValidationError) as caught:
            PeopleDirectory(self.db, budget, observed_at_utc=AT, subject='s0').label('s0')
        self.assertEqual(caught.exception.code, 'environment_failure:capacity')

    def test_discovery_queries_use_scope_indexes_not_global_scans(self):
        queries = [
            ("SELECT * FROM subject_memberships WHERE group_id=? AND status='active' AND starts_at_utc<=?",
             ('group', AT), 'subject_memberships_group_status_idx'),
            ("SELECT * FROM subject_memberships WHERE subject_id=? AND status='active' AND starts_at_utc<=?",
             ('s0', AT), 'subject_memberships_subject_status_idx'),
        ]
        for sql, params, index in queries:
            plan = '\n'.join(str(tuple(r)) for r in self.db.execute('EXPLAIN QUERY PLAN ' + sql, params))
            self.assertIn('SEARCH', plan)
            self.assertIn(index, plan)
            self.assertNotIn('SCAN subject_memberships', plan)

    def test_missing_canonical_reference_is_integrity_failure_not_redaction(self):
        with self.assertRaises(SpineValidationError) as caught:
            self.directory().label('missing-subject')
        self.assertEqual(caught.exception.code, 'environment_failure:people')

    def test_local_projection_and_discovery_do_not_write(self):
        self.member('s0')
        self.member('s1')
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee'),))
        before = self.db.total_changes
        self.db.execute('PRAGMA query_only=ON')
        self.directory().roster(GROUP)
        self.directory().projection(read_people_snapshot(self.db, item_id='task'))
        self.assertEqual(self.db.total_changes, before)
