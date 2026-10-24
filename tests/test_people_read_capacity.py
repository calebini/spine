"""Real-query people capacity/privacy boundaries on disposable file-backed ledgers.

Large fixtures are explicit test-only row copies of valid ledger writers' output;
no production ledger or alternate operator/client SQL path is involved. These
tests intentionally compose helper methods rather than inherit their test cases.
"""

import unittest
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

from spine.commands.people_runtime import API
from spine.core.errors import SpineValidationError
from spine.ledger.facets import insert_snapshot
from spine.ledger.people import read_people_snapshot
from spine.web.errors import WebError
from spine.web.people_read_service import PeopleReadBudget, PeopleReadPermissions, PeopleReadService
from spine.web.read_context import read_snapshot
from spine.web.read_projection import candidate_ids
from tests import test_people_read_integration as helper

AT = helper.AT


class PeopleReadCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helper.PeopleReadIntegrationTests.setUpClass()

    def setUp(self):
        self.f = helper.PeopleReadIntegrationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db = self.f.db

    def rows(self, table):
        return [tuple(row) for row in self.db.execute(f'SELECT * FROM {table}')]

    @contextmanager
    def observed(self):
        """Observe actual SQL and the one request-global progress accumulator."""
        evidence = {'budgets': [], 'statements': [], 'snapshots': []}
        def budget(*args, **kwargs):
            value = PeopleReadBudget(*args, **kwargs)
            evidence['budgets'].append(value)
            return value
        def permissions(db, account, now, resource_budget):
            evidence['snapshots'].append((id(resource_budget), sum(resource_budget.steps.values())))
            db.set_trace_callback(evidence['statements'].append)
            return PeopleReadPermissions(db, account, now, resource_budget)
        with patch('spine.web.people_read_service.PeopleReadBudget', side_effect=budget), patch(
                'spine.web.people_read_service.PeopleReadPermissions', side_effect=permissions):
            yield evidence

    def clone_rows(self, table, records, identities, *, replacements=None):
        if not records:
            return
        names = tuple(records[0])
        rows = []
        for identity in identities:
            for record in records:
                value = dict(record)
                for name in ('item_id', 'resource_id'):
                    if name in value:
                        value[name] = identity
                for name in ('item_access_owner_id', 'item_subject_role_id', 'grant_id'):
                    if name in value:
                        value[name] = str(value[name]) + '-' + identity
                value.update(replacements or {})
                rows.append(tuple(value[name] for name in names))
        self.db.executemany(f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join("?" for _ in names)})', rows)

    def clone_events(self, template, identities, *, grants=False, grantee=None):
        """Scale valid sparse/dense fixtures without counting setup as request cost."""
        tables = ['coordination_items', 'coordination_item_versions', 'event_details', 'item_subject_roles',
                  'item_access_owners', 'item_access_owner_revisions']
        if grants:
            tables += ['access_grants', 'access_grant_revisions', 'access_grant_operations']
        data = {}
        for table in tables:
            column = 'item_id'
            if table in {'access_grants', 'access_grant_revisions'}:
                column = 'resource_id'
            if table == 'access_grant_operations':
                records = self.db.execute('SELECT * FROM access_grant_operations WHERE grant_id IN '
                    '(SELECT grant_id FROM access_grants WHERE resource_id=?)', (template,))
            else:
                records = self.db.execute(f'SELECT * FROM {table} WHERE {column}=?', (template,))
            data[table] = [dict(row) for row in records]
        with self.db:
            self.db.execute('PRAGMA defer_foreign_keys=ON')
            # Honor the shared version writer/finalizer even for scale fixtures.
            with self.db.version_allocation('item_create'):
                for table, records in data.items():
                    changes = ({'grantee_subject_id': grantee} if grantee is not None
                               and table in {'access_grants', 'access_grant_revisions'} else {})
                    self.clone_rows(table, records, identities, replacements=changes)
                for identity in identities:
                    insert_snapshot(self.db, identity, 1, ())
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def grant(self, identity, *, group=False):
        self.f.h.provision(grants=[{'operation': 'create', 'resource_kind': 'item', 'resource_id': identity,
            'resource_owner_revision': '1', 'grantee': ({'owner_kind': 'subject_group', 'owner_group_id': 'group'}
                if group else {'owner_kind': 'subject', 'owner_subject_id': 'owner'}),
            'operations': ['item.read'], 'starts_at_utc': '2026-01-01T00:00:00Z', 'ends_at_utc': None}])

    def selection(self, maximum, *, admit=False, capture=None):
        budget = PeopleReadBudget(self.f.reads, clock=lambda: 0.0, config=self.f.config)
        with read_snapshot(self.f.config, self.f.reads, self.f.h.accounts['owner'], evaluated_at_utc=AT,
                budget=budget, collect_proof=True,
                permissions_factory=lambda db, account, now: PeopleReadPermissions(db, account, now, budget)) as snapshot:
            try:
                return candidate_ids(snapshot, self.f.agenda(), maximum=maximum, admit_candidates=admit), budget
            finally:
                if capture is not None:
                    capture.append(snapshot)

    def test_total_role_ceiling_counts_unmanaged_rows_and_preserves_history(self):
        identity = self.f.event(who='owner')
        with self.db:
            self.db.executemany("INSERT INTO subjects VALUES(?,'person',?,'active',?,?)",
                [(f'watcher-{i}', f'Watcher {i}', AT, AT) for i in range(100)])
            self.db.executemany("INSERT INTO item_subject_roles VALUES(?,?,1,?,'watcher','active',?)",
                [(f'watcher-role-{i}', identity, f'watcher-{i}', AT) for i in range(99)])
        exact = read_people_snapshot(self.db, item_id=identity)
        self.assertEqual(len(exact.associations), 1)
        with self.observed() as evidence:
            result = self.f.read('schedule.show', {'item_id': identity, 'include': ['people']})['result']
        self.assertEqual(result['sections']['people']['availability'], 'available')
        sql = next(sql for sql in evidence['statements'] if 'LEFT JOIN item_subject_roles AS r' in sql)
        self.assertTrue(sql.rstrip().endswith('LIMIT 101'))
        plan = '\n'.join(str(tuple(row)) for row in self.db.execute('EXPLAIN QUERY PLAN ' + sql))
        self.assertIn('SEARCH r USING INDEX', plan)
        self.assertIn('(item_id=? AND version=?)', plan)
        self.assertNotIn('SCAN r', plan)
        with self.db:
            self.db.execute("INSERT INTO item_subject_roles VALUES('overflow',?,1,'watcher-99','watcher','inactive',?)", (identity, AT))
        before = self.rows('item_subject_roles')
        with self.assertRaises(SpineValidationError) as caught:
            read_people_snapshot(self.db, item_id=identity)
        self.assertEqual(caught.exception.code, 'capacity_exceeded:people')
        result = self.f.read('schedule.show', {'item_id': identity, 'include': ['people']})['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people']['availability'], 'unavailable')
        self.f.rejected('capacity_exceeded', 'agenda.show', self.f.agenda(person_filter={'subject_id': 'owner'}))
        self.assertEqual(self.rows('item_subject_roles'), before)

    def test_authorized_candidate_sentinel_refuses_without_truncation_or_mutation(self):
        seed = self.f.event('candidate-0000', who=None)
        self.clone_events(seed, [f'candidate-{i:04}' for i in range(1, 1000)])
        observed = []
        with self.assertRaises(WebError) as caught:
            self.selection(1000, capture=observed)
        self.assertEqual(caught.exception.code, 'capacity_exceeded')
        self.assertEqual(len(observed[0].permissions.discovered), 1000)
        # The whole candidate list is selected, but processing all 1000 roots
        # is not promised by the separate request-global VM/resource ceilings.
        self.assertGreaterEqual(sum(observed[0].budget.steps.values()), 75000)
        # A candidate allowance does not bypass the stricter 100-resource ceiling.
        self.f.rejected('capacity_exceeded', 'agenda.show', self.f.agenda(limit='1'))
        self.clone_events(seed, ['candidate-1000'])
        counts = tuple(self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('coordination_items', 'command_receipts', 'audit_log'))
        with self.assertRaises(WebError) as caught:
            self.selection(1000)
        self.assertEqual(caught.exception.code, 'capacity_exceeded')
        with self.observed() as evidence:
            self.f.rejected('capacity_exceeded', 'agenda.show', self.f.agenda(limit='1'))
        statements = [sql for sql in evidence['statements'] if 'UNION SELECT item_id FROM item_access_owners' in sql]
        self.assertTrue(statements)
        self.assertTrue(all(statement.rstrip().endswith('LIMIT 1001') for statement in statements))
        self.assertEqual(counts, tuple(self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('coordination_items', 'command_receipts', 'audit_log')))

    def test_group_roster_sentinel_is_not_a_hidden_offset_traversal(self):
        self.f.group()
        with self.db:
            self.db.executemany("INSERT INTO subjects VALUES(?,'person','Roster member','active',?,?)",
                [(f'roster-{i:04}', AT, AT) for i in range(999)])
            self.db.executemany("INSERT INTO subject_memberships VALUES(?,'group',?,'member','active',?,NULL,1)",
                [(f'roster-membership-{i}', f'roster-{i:04}', AT) for i in range(999)])
            self.db.executemany("INSERT INTO subject_membership_revisions VALUES(?,1,'member','active',?,NULL,NULL,NULL,NULL,NULL)",
                [(f'roster-membership-{i}', AT) for i in range(999)])
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        before = tuple(self.db.iterdump())
        body = {'contract_version': API, 'request': {'contract_version': 'spine.people-and-responsibility.v1',
            'owner': {'owner_kind': 'subject_group', 'owner_group_id': 'group'}, 'limit': '1'}}
        with self.assertRaises(WebError) as caught:
            self.f.service.execute('people.list', body, self.f.h.accounts['owner'], 'selection')
        self.assertEqual(caught.exception.code, 'capacity_exceeded')
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_sparse_dense_owner_group_and_grant_queries_ignore_hidden_ledger_growth(self):
        self.f.group()
        self.f.event('owned', who='other')
        self.f.event('group-owned', who='other', scope={'owner_kind': 'subject_group', 'owner_group_id': 'group'})
        granted = self.f.event('granted', who='other', scope={'owner_kind': 'subject', 'owner_subject_id': 'other'})
        self.grant(granted)
        group_granted = self.f.event('group-granted', who='other',
            scope={'owner_kind': 'subject', 'owner_subject_id': 'other'})
        self.grant(group_granted, group=True)
        request = self.f.agenda(limit='2', person_filter={'subject_id': 'other'})
        with self.observed() as sparse:
            first = self.f.read('agenda.show', request)['result']
        self.clone_events('owned', [f'owned-{i}' for i in range(3)])
        self.clone_events('group-owned', [f'group-{i}' for i in range(3)])
        self.clone_events(granted, [f'granted-{i}' for i in range(3)], grants=True)
        self.clone_events(group_granted, [f'group-granted-{i}' for i in range(3)], grants=True)
        with self.observed() as dense:
            before = self.f.read('agenda.show', request)['result']
        self.clone_events(granted, [f'hidden-{i:04}' for i in range(3000)], grants=True, grantee='other')
        with self.observed() as hidden:
            after = self.f.read('agenda.show', request)['result']
        self.assertEqual(before, after)
        self.assertTrue(first['has_more'])
        for evidence in (sparse, dense, hidden):
            self.assertEqual(len(evidence['budgets']), 1)
            budget = evidence['budgets'][0]
            self.assertEqual(len(evidence['snapshots']), 2)
            self.assertEqual({identity for identity, _ in evidence['snapshots']}, {id(budget)})
            self.assertGreater(evidence['snapshots'][1][1], evidence['snapshots'][0][1])
            self.assertLess(sum(budget.steps.values()), 100000)
            self.assertLess(len(budget.resources), 100)
            sql = next(sql for sql in evidence['statements'] if 'UNION SELECT item_id FROM item_access_owners' in sql)
            plan = '\n'.join(str(tuple(row)) for row in self.db.execute('EXPLAIN QUERY PLAN ' + sql))
            for index in ('item_access_owners_subject', 'item_access_owners_group', 'access_grants_subject', 'access_grants_group'):
                self.assertIn(index, plan)
            self.assertNotIn('SCAN coordination_items', plan)
            self.assertNotIn('SCAN item_access_owners', plan)
            self.assertNotIn('SCAN g', plan)
        dense_steps = sum(dense['budgets'][0].steps.values())
        hidden_steps = sum(hidden['budgets'][0].steps.values())
        # B-tree depth may add a few instructions. 3000 unrelated roots/grants
        # must not add linear VM work to either assembly or the fresh fence.
        self.assertLessEqual(hidden_steps, dense_steps + 2000)

    def test_filter_precedes_expansion_and_page_count_without_subject_discovery(self):
        mismatch = self.f.recurring()
        self.f.event('matching-a', who='owner')
        self.f.event('matching-b', who='owner')
        statements = []
        def permissions(db, account, now, budget):
            db.set_trace_callback(statements.append)
            return PeopleReadPermissions(db, account, now, budget)
        with patch('spine.web.people_read_service.PeopleReadPermissions', side_effect=permissions), patch(
                'spine.web.read_assembly._expanded', side_effect=AssertionError('nonmatching series must not expand')):
            first = self.f.read('agenda.show', self.f.agenda(limit='1', person_filter={'subject_id': 'owner'}))['result']
        self.assertEqual([row['activity']['item_id'] for row in first['entries']], ['matching-a'])
        self.assertTrue(first['has_more'])
        second = self.f.read('agenda.show', self.f.agenda(limit='1', person_filter={'subject_id': 'owner'},
                                                       cursor=first['next_cursor']))['result']
        self.assertEqual([row['activity']['item_id'] for row in second['entries']], ['matching-b'])
        self.assertFalse(second['has_more'])
        self.assertNotIn(mismatch, str(first['entries']))
        self.assertFalse(any('FROM subjects WHERE subject_id=' in sql and "='owner'" in sql
                             and ('display_name' in sql or sql.startswith('SELECT 1')) for sql in statements))
        for subject in ('not-present', 'other'):
            # The recurring item is authorized and has no roles. Existing private
            # 'other' and absent opaque ID have identical empty match semantics.
            result = self.f.read('agenda.show', self.f.agenda(item_ids=[mismatch],
                person_filter={'subject_id': subject}))['result']
            self.assertEqual((result['entries'], result['unplaced_items'], result['has_more']), ([], [], False))

    def test_stricter_sql_limit_is_not_reset_for_current_authority_snapshot(self):
        identity = self.f.event(who='owner')
        request = {'item_id': identity, 'include': ['people']}
        with self.observed() as baseline:
            self.f.read('schedule.show', request)
        total = sum(baseline['budgets'][0].steps.values())
        first = baseline['snapshots'][1][1]
        self.assertGreater(total, first)
        # Enough for the initial complete response, deliberately insufficient
        # for both snapshots. A per-snapshot reset would incorrectly succeed.
        ceiling = total
        reader = PeopleReadService(replace(self.f.config, sql_steps=ceiling), contracts=self.f.contracts,
            cursor_config=self.f.cursor, reads=self.f.reads, now=lambda: AT)
        before = tuple(self.db.iterdump())
        with self.observed() as limited:
            self.f.rejected('capacity_exceeded', 'schedule.show', request, reader=reader)
        self.assertEqual(len(limited['budgets']), 1)
        self.assertEqual(limited['budgets'][0].maximum_steps, ceiling)
        self.assertEqual(len(limited['snapshots']), 2,
            (baseline['snapshots'], total, ceiling, limited['snapshots'], limited['budgets'][0].steps))
        self.assertGreater(sum(limited['budgets'][0].steps.values()), first)
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_optional_failure_keeps_time_but_hard_serialization_budget_rejects(self):
        identity = self.f.event(who='owner')
        request = {'item_id': identity, 'include': ['people']}
        with patch('spine.web.people_read_service.read_people_snapshot', side_effect=SpineValidationError(
                'capacity_exceeded:people', 'Too many historical role rows.')):
            result = self.f.read('schedule.show', request)['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people'], {'availability': 'unavailable', 'scope': 'authorized_only',
            'coverage': 'incomplete', 'reason_code': 'context_unavailable'})
        clock = [0.0]
        reader = PeopleReadService(self.f.config, contracts=self.f.contracts, cursor_config=self.f.cursor,
            reads=self.f.reads, now=lambda: AT, clock=lambda: clock[0])
        def encode(response):
            clock[0] = 5.0
            return b'not released'
        with self.assertRaises(WebError) as caught:
            reader.read('schedule.show', {'contract_version': API, 'request': request},
                selection=lambda: (self.f.h.accounts['owner'], 'selection'), encode=encode)
        self.assertEqual(caught.exception.code, 'capacity_exceeded')
