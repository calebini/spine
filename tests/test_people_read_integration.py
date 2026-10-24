"""Private successor reads reuse real independent-read/time owners and released pins."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from spine.commands import handle, people_candidate
from spine.commands.people_runtime import API, CONTRACT, PeopleCursorCodec
from spine.core.errors import SpineValidationError
from spine.core.schedule import system_timezone_database_version
from spine.ledger import ItemSubjectRoleInput, TemporalAnchorInput, create_event_v1, create_task_v1
from spine.services.people_directory import PeopleDirectory
from spine.web.errors import WebError
from spine.web.people_read_service import PeopleReadBudget, PeopleReadPermissions, PeopleReadService
from spine.web.read_contracts import ReadContracts
from tests import test_independent_activity_read_foundation as old_helpers
from tests import test_people_web as helper

AT = helper.AT


class PeopleReadIntegrationTests(unittest.TestCase):
    setUpClass = helper.PeopleWebTests.__dict__['setUpClass']
    subject, group, task, grant, body = (helper.PeopleWebTests.subject, helper.PeopleWebTests.group,
        helper.PeopleWebTests.task, helper.PeopleWebTests.grant, helper.PeopleWebTests.body)

    def setUp(self):
        helper.PeopleWebTests.setUp(self)
        self.reads = ReadContracts.packaged()
        self.reader = self.reader_with()

    service_with = helper.PeopleWebTests.service_with

    def reader_with(self, **kwargs):
        return PeopleReadService(self.config, contracts=self.contracts, cursor_config=self.cursor, reads=self.reads,
                                 now=lambda: AT, **kwargs)

    def event(self, identity='event', *, who='other', scope=None, when='2026-10-24T12:00:00Z'):
        roles = () if who is None else (ItemSubjectRoleInput(subject_id=who, role='participant'),)
        create_event_v1(self.db, item_id=identity, audit_id='create-' + identity, created_at_utc=AT,
            created_by_subject_id='owner', title=identity, all_day=False,
            start_anchor=TemporalAnchorInput(anchor_id='start-' + identity, anchor_kind='instant_utc', utc_instant=when),
            subject_roles=roles)
        self.adopt(identity, scope)
        return identity

    def adopt(self, identity, scope=None):
        self.h.provision(item_adoptions=[{'operation': 'create', 'item_id': identity,
            'expected_item_version': '1', 'owner_scope': scope or {'owner_kind': 'subject', 'owner_subject_id': 'owner'}}])

    def agenda(self, **kwargs):
        return {'evaluated_at_utc': AT, 'range_start_local': '2026-10-24T00:00:00',
                'range_end_local': '2026-10-28T00:00:00', 'timezone': 'UTC',
                'timezone_database_version': system_timezone_database_version(), **kwargs}

    def read(self, command, request, *, reader=None, subject='owner', **kwargs):
        result = (reader or self.reader).read(command, {'contract_version': API, 'request': request},
            selection=lambda: (self.h.accounts[subject], 'selection'), **kwargs)
        self.contracts.validate('web-responses', result, definition=command, output=True)
        return result

    def rejected(self, code, command, request, **kwargs):
        with self.assertRaises(WebError) as caught:
            self.read(command, request, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def recurring(self):
        result = handle('event.create', {'command_id': 'series', 'actor_subject_id': 'owner', 'created_at_utc': AT,
            'title': 'Series', 'all_day': False, 'start_anchor': {'anchor_kind': 'local_instant',
                'local_date': '2026-10-24', 'local_time': '12:00:00', 'timezone': 'UTC',
                'timezone_database_version': system_timezone_database_version(), 'recurrence_set': {
                    'time_basis': 'local_instant', 'timezone': 'UTC',
                    'timezone_database_version': system_timezone_database_version(), 'rules': [{
                        'frequency': 'DAILY', 'seed': '2026-10-24T12:00:00', 'start_bound': '2026-10-24T12:00:00',
                        'end_condition': {'kind': 'count', 'count': '3'}}]}}}, self.h.ctx)
        self.assertTrue(result['ok'], result)
        self.adopt(result['item_id'])
        return result['item_id']

    def test_people_is_additive_complete_and_legacy_subject_roles_stays_self_only(self):
        self.group()
        identity = self.event()
        before = '\n'.join(self.db.iterdump())
        result = self.read('schedule.show', {'item_id': identity, 'include': ['subject_roles', 'people']})['result']
        self.assertEqual(len(result['sections']), 12)
        self.assertEqual(result['sections']['subject_roles']['entries'], [])
        people = result['sections']['people']
        self.assertEqual(people['availability'], 'available')
        self.assertEqual(people['people']['subjects'][0]['label']['display_name'], 'other')
        self.assertEqual(people['people']['associations'][0]['role'], 'participant')
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        omitted = self.read('schedule.show', {'item_id': identity})['result']['sections']['people']
        self.assertEqual(omitted, {'availability': 'not_requested', 'scope': 'authorized_only'})

    def test_tuple_visibility_does_not_disclose_private_labels(self):
        identity = self.event()
        result = self.read('schedule.show', {'item_id': identity, 'include': ['people']})['result']
        self.assertEqual(result['sections']['people']['people']['subjects'], [
            {'subject_id': 'other', 'label': {'availability': 'not_disclosed'}}])

    def test_agenda_filter_precedes_expansion_and_never_validates_target_existence(self):
        self.event('matching')
        self.event('nonmatching', who='owner')
        request = self.agenda(person_filter={'subject_id': 'other'})
        sql = []
        from spine.web import read_projection
        original = read_projection.core
        calls = []
        def observed(snapshot, identity, **kwargs):
            calls.append(identity)
            snapshot.db.set_trace_callback(sql.append)
            return original(snapshot, identity, **kwargs)
        with patch('spine.web.read_assembly.core', side_effect=observed):
            response = self.read('agenda.show', request)['result']
        self.assertEqual([row['activity']['item_id'] for row in response['entries']], ['matching'])
        self.assertNotIn('nonmatching', calls)
        self.assertFalse(any("FROM subjects WHERE subject_id='other'" in statement for statement in sql))
        for identity in ('absent-person', 'hidden-person'):
            empty = self.read('agenda.show', self.agenda(person_filter={'subject_id': identity}))['result']
            self.assertEqual((empty['entries'], empty['unplaced_items'], empty['coverage']), ([], [], 'complete'))

    def test_inactive_subject_retained_active_role_still_matches(self):
        self.event()
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='other'")
        result = self.read('agenda.show', self.agenda(person_filter={'subject_id': 'other', 'roles': ['participant']}))['result']
        self.assertEqual(len(result['entries']), 1)
        result = self.read('agenda.show', self.agenda(person_filter={'subject_id': 'other', 'roles': ['assignee']}))['result']
        self.assertEqual(result['entries'], [])

    def test_nonmatch_occurrence_retains_activity_time_and_never_expands(self):
        identity = self.recurring()
        request = {'item_id': identity, 'range_basis': 'expressed_time', 'range_start': '2026-10-24T00:00:00',
                   'range_end': '2026-10-28T00:00:00', 'person_filter': {'subject_id': 'absent'}}
        with patch('spine.web.read_assembly._expanded', side_effect=AssertionError('must not expand nonmatches')):
            result = self.read('item.occurrences', request)['result']
        self.assertEqual(result['coverage'], 'complete')
        self.assertEqual(result['occurrences'], [])
        self.assertEqual(result['activity']['time']['availability'], 'available')

    def test_missing_or_denied_root_is_not_hidden_by_nonmatching_filter(self):
        identity = self.recurring()
        request = {'item_id': identity, 'range_basis': 'original_schedule', 'range_start': '2026-10-24T00:00:00',
                   'range_end': '2026-10-28T00:00:00', 'person_filter': {'subject_id': 'absent'}}
        self.rejected('resource_unavailable', 'item.occurrences', request, subject='other')
        self.rejected('resource_unavailable', 'item.occurrences', {**request, 'item_id': 'missing'})

    def test_people_failure_is_optional_unavailability_not_nondisclosure(self):
        identity = self.event()
        failure = SpineValidationError('environment_failure:people', 'test integrity failure')
        with patch.object(PeopleDirectory, 'projection', side_effect=failure):
            result = self.read('schedule.show', {'item_id': identity, 'include': ['people']})['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people'], {'availability': 'unavailable', 'scope': 'authorized_only',
                                                       'coverage': 'incomplete', 'reason_code': 'context_unavailable'})

    def test_stateless_agenda_pages_bound_query_source_and_identity(self):
        self.event('event-a')
        self.event('event-b')
        request = self.agenda(limit='1', person_filter={'subject_id': 'other'})
        first = self.read('agenda.show', request)['result']
        token = first['next_cursor']
        self.assertTrue(first['has_more'])
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(token, now=AT)
        self.assertEqual((payload['route'], payload['stream']), ('agenda.show', 'resolved'))
        second = self.read('agenda.show', {**request, 'cursor': token}, reader=self.reader_with())['result']
        self.assertEqual(second['entries'][0]['activity']['item_id'], 'event-b')
        self.assertFalse(second['has_more'])
        self.rejected('access_changed', 'agenda.show', {**request, 'cursor': token, 'limit': '2'})
        self.rejected('access_changed', 'agenda.show', {**request, 'cursor': token}, subject='other')

    def test_hidden_label_rename_does_not_break_cursor_or_release(self):
        self.event('event-a')
        self.event('event-b')
        request = self.agenda(limit='1', include=['people'])
        first = self.read('agenda.show', request)['result']
        def rename():
            with self.db:
                self.db.execute("UPDATE subjects SET display_name='Hidden rename' WHERE subject_id='other'")
        second = self.read('agenda.show', {**request, 'cursor': first['next_cursor']},
                           reader=self.reader_with(before_release=rename))['result']
        self.assertEqual(second['entries'][0]['sections']['people']['people']['subjects'][0]['label'],
                         {'availability': 'not_disclosed'})

    def test_visible_label_and_role_change_refuse_at_fresh_release(self):
        self.group()
        identity = self.event()
        def rename():
            with self.db:
                self.db.execute("UPDATE subjects SET display_name='Visible rename' WHERE subject_id='other'")
        self.rejected('access_changed', 'schedule.show', {'item_id': identity, 'include': ['people']},
                      reader=self.reader_with(before_release=rename))
        def change_roles():
            result = people_candidate.execute('item.people.update', {'contract_version': CONTRACT,
                'command_id': 'release-people', 'actor_subject_id': 'owner', 'updated_at_utc': AT,
                'item_id': identity, 'target_version': '1', 'people': {'participants': []}}, self.h.ctx)
            self.assertTrue(result['ok'], result)
        self.rejected('access_changed', 'agenda.show', self.agenda(person_filter={'subject_id': 'other'}),
                      reader=self.reader_with(before_release=change_roles))

    def test_old_and_new_cursor_families_do_not_mix(self):
        self.event('event-a')
        self.event('event-b')
        request = self.agenda(limit='1')
        first = self.read('agenda.show', request)['result']
        self.rejected('invalid_request', 'agenda.show', {**request, 'cursor': first['next_cursor'].replace('pc1.', 'v2.')})

    def test_stricter_global_budget_refuses_and_read_ledger_is_unchanged(self):
        self.event()
        before = '\n'.join(self.db.iterdump())
        reader = PeopleReadService(replace(self.config, sql_steps=100), contracts=self.contracts,
            cursor_config=self.cursor, reads=self.reads, now=lambda: AT)
        self.rejected('capacity_exceeded', 'agenda.show', self.agenda(), reader=reader)
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def related(self, identity, key):
        fixture = type('Fixture', (), {'ctx': self.h.ctx, 'ok': self.h.ok})()
        result = old_helpers.ReadCoreFoundationTests.related(fixture, identity, command_id=key)
        self.adopt(result)
        return result

    def test_existing_section_ordering_uses_new_cursor_family(self):
        identity = self.event()
        self.related(identity, 'child-one')
        self.related(identity, 'child-two')
        request = {'item_id': identity, 'include': ['related_items', 'people'], 'section_limit': '1'}
        first = self.read('schedule.show', request)['result']['sections']['related_items']
        self.assertTrue(first['has_more'])
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(first['next_cursor'], now=AT)
        self.assertEqual((payload['route'], payload['stream']), ('schedule.show', 'related_items'))
        second = self.read('schedule.show', {**request, 'section_cursors': {'related_items': first['next_cursor']}})['result']
        self.assertNotEqual(first['entries'][0]['item_id'], second['sections']['related_items']['entries'][0]['item_id'])
        self.assertFalse(second['sections']['related_items']['has_more'])
        self.assertEqual(second['sections']['people']['availability'], 'available')

    def test_occurrence_streams_retain_engine_order_and_original_lifetime(self):
        identity = self.recurring()
        changed = people_candidate.execute('item.people.update', {'contract_version': CONTRACT,
            'command_id': 'series-people', 'actor_subject_id': 'owner', 'updated_at_utc': AT, 'item_id': identity,
            'target_version': '1', 'people': {'participants': ['other']}}, self.h.ctx)
        self.assertTrue(changed['ok'], changed)
        for basis in ('original_schedule', 'expressed_time'):
            request = {'item_id': identity, 'range_basis': basis, 'range_start': '2026-10-24T00:00:00',
                       'range_end': '2026-10-28T00:00:00', 'person_filter': {'subject_id': 'other'}, 'limit': '1'}
            a = self.read('item.occurrences', request)['result']
            b = self.read('item.occurrences', {**request, 'cursor': a['next_cursor']})['result']
            c = self.read('item.occurrences', {**request, 'cursor': b['next_cursor']})['result']
            self.assertEqual(len({r['occurrences'][0]['occurrence_key'] for r in (a, b, c)}), 3)
            self.assertFalse(c['has_more'])
            x, y = (PeopleCursorCodec(self.contracts, self.cursor).decode(r['next_cursor'], now=AT) for r in (a, b))
            self.assertEqual(x['issued_at_utc'], y['issued_at_utc'])
            self.assertEqual(x['expires_at_utc'], y['expires_at_utc'])

    def test_unavailable_follow_source_task_stays_unplaced_after_person_filter(self):
        identity = self.event(scope={'owner_kind': 'subject', 'owner_subject_id': 'other'})
        task = self.related(identity, 'hidden-source-task')
        request = self.agenda(person_filter={'subject_id': 'owner', 'roles': ['assignee']}, include=['people'], limit='1')
        result = self.read('agenda.show', request)['result']
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['unplaced_items'][0]['activity']['item_id'], task)
        self.assertEqual(result['coverage'], 'incomplete')
        self.assertEqual(result['unplaced_items'][0]['sections']['people']['availability'], 'available')

    def test_nonmatching_authorized_edit_does_not_enter_cursor_source(self):
        self.event('match-a')
        self.event('match-b')
        ignored = self.event('nonmatching', who='owner')
        request = self.agenda(limit='1', person_filter={'subject_id': 'other'})
        first = self.read('agenda.show', request)['result']
        def mutate():
            result = handle('event.update', {'command_id': 'ignored-edit', 'actor_subject_id': 'owner',
                'item_id': ignored, 'target_version': '1', 'updated_at_utc': AT, 'patch': {'title': 'Not in source'}}, self.h.ctx)
            self.assertTrue(result['ok'], result)
        second = self.read('agenda.show', {**request, 'cursor': first['next_cursor']},
                           reader=self.reader_with(before_release=mutate))['result']
        self.assertEqual(second['entries'][0]['activity']['item_id'], 'match-b')

    def test_people_resource_ceiling_degrades_only_optional_context(self):
        with self.db:
            self.db.executemany("INSERT INTO subjects VALUES(?,'person','Hidden','active',?,?)",
                                [(f'person-{i:03}', AT, AT) for i in range(100)])
        create_event_v1(self.db, item_id='large-people', audit_id='large-create', created_at_utc=AT,
            created_by_subject_id='owner', title='Large roster', all_day=False,
            start_anchor=TemporalAnchorInput(anchor_id='large-start', anchor_kind='instant_utc', utc_instant=AT),
            subject_roles=tuple(ItemSubjectRoleInput(subject_id=f'person-{i:03}', role='participant') for i in range(100)))
        self.adopt('large-people')
        result = self.read('schedule.show', {'item_id': 'large-people', 'include': ['people']})['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people']['availability'], 'unavailable')

    def test_optional_sql_exhaustion_preserves_core_and_outer_deadline_does_not(self):
        identity = self.event()
        reads = ReadContracts.packaged()
        reads.bounds = {**reads.bounds, 'optional_sql_vm_steps': 1}
        reader = PeopleReadService(self.config, contracts=self.contracts, reads=reads, cursor_config=self.cursor, now=lambda: AT)
        result = self.read('schedule.show', {'item_id': identity, 'include': ['people']}, reader=reader)['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people']['availability'], 'unavailable')
        clock = [0.0]
        reader = self.reader_with(clock=lambda: clock[0], before_release=lambda: clock.__setitem__(0, 5.1))
        self.rejected('capacity_exceeded', 'schedule.show', {'item_id': identity, 'include': ['people']}, reader=reader)

    def test_hidden_dense_growth_does_not_enter_authorized_paging(self):
        self.event('visible-a')
        self.event('visible-b')
        request = self.agenda(limit='1', person_filter={'subject_id': 'other'})
        first = self.read('agenda.show', request)['result']
        def hidden():
            for index in range(150):
                create_task_v1(self.db, item_id=f'hidden-{index}', audit_id=f'hidden-audit-{index}',
                    created_at_utc=AT, created_by_subject_id='other', title='Not an authorized source',
                    subject_roles=(ItemSubjectRoleInput(subject_id='other', role='assignee'),))
        hidden()  # Fixture growth is outside the request's five-second budget.
        second = self.read('agenda.show', {**request, 'cursor': first['next_cursor']})['result']
        self.assertEqual(second['entries'][0]['activity']['item_id'], 'visible-b')

    def test_actual_selection_queries_are_indexed_and_request_budget_is_shared(self):
        self.event('one')
        self.event('two')
        statements, budgets = [], []
        def permissions(db, account, now, budget):
            db.set_trace_callback(statements.append)
            return PeopleReadPermissions(db, account, now, budget)
        def resource_budget(*args, **kwargs):
            result = PeopleReadBudget(*args, **kwargs)
            budgets.append(result)
            return result
        with patch('spine.web.people_read_service.PeopleReadPermissions', side_effect=permissions), patch(
                'spine.web.people_read_service.PeopleReadBudget', side_effect=resource_budget):
            self.read('agenda.show', self.agenda(person_filter={'subject_id': 'other'}, include=['people']))
        self.assertEqual(len(budgets), 1)
        budget = budgets[0]
        self.assertLessEqual(sum(budget.steps.values()), 100000)
        self.assertLessEqual(len(budget.resources), 100)
        actual = [sql for sql in statements if 'UNION SELECT item_id FROM item_access_owners' in sql]
        self.assertTrue(actual)
        plans = '\n'.join(str(tuple(row)) for row in self.db.execute('EXPLAIN QUERY PLAN ' + actual[0]))
        self.assertIn('item_access_owners_subject', plans)
        self.assertIn('access_grants_subject', plans)
        self.assertNotIn('SCAN coordination_items', plans)

    def test_operator_revocation_and_lost_selection_are_release_conflicts(self):
        identity = self.event()
        def revoke():
            with self.db:
                self.db.execute('UPDATE web_operators SET eligible=0 WHERE account_id=?', (self.h.accounts['owner'],))
        self.rejected('access_changed', 'schedule.show', {'item_id': identity}, reader=self.reader_with(before_release=revoke))
        with self.db:
            self.db.execute('UPDATE web_operators SET eligible=1 WHERE account_id=?', (self.h.accounts['owner'],))
        selected = [(self.h.accounts['owner'], 'selection')]
        reader = self.reader_with(before_release=lambda: selected.__setitem__(0, None))
        with self.assertRaises(WebError) as caught:
            reader.read('schedule.show', {'contract_version': API, 'request': {'item_id': identity}}, selection=lambda: selected[0])
        self.assertEqual(caught.exception.code, 'access_changed')

    def test_optional_byte_ceiling_preserves_activity_and_not_disclosed_is_not_used(self):
        identity = self.event(who='owner')
        with self.db:
            self.db.execute('UPDATE subjects SET display_name=? WHERE subject_id=?', ('🙂' * 512, 'owner'))
        reads = ReadContracts.packaged()
        reads.bounds = {**reads.bounds, 'section_bytes': 512}
        reader = PeopleReadService(self.config, contracts=self.contracts, reads=reads, cursor_config=self.cursor, now=lambda: AT)
        result = self.read('schedule.show', {'item_id': identity, 'include': ['people']}, reader=reader)['result']
        self.assertEqual(result['activity']['time']['availability'], 'available')
        self.assertEqual(result['sections']['people']['availability'], 'unavailable')
        self.assertNotIn('not_disclosed', str(result))

    def test_general_private_service_dispatches_read_successors_without_public_activation(self):
        identity = self.event()
        response = self.service.execute('schedule.show', {'contract_version': API, 'request': {
            'item_id': identity, 'include': ['people']}}, self.h.accounts['owner'], 'selection')
        self.assertEqual(response['result_contract'], 'spine.people-schedule-view.v1')
        self.assertEqual(response['result']['sections']['people']['availability'], 'available')

    def test_future_label_roster_activation_binds_read_cursor_without_epoch_change(self):
        self.event('one')
        self.event('two')
        value = handle('subject_group.upsert', {'command_id': 'label-group', 'actor_subject_id': 'owner',
            'group_id': 'label-group', 'display_name': 'Labels only', 'updated_at_utc': AT}, self.h.ctx)
        self.assertTrue(value['ok'], value)
        with self.db:
            self.db.execute("INSERT INTO subject_memberships VALUES('target-member','label-group','other','member','active',?,NULL,1)",
                            ('2026-01-01T00:00:00Z',))
            self.db.execute("INSERT INTO subject_memberships VALUES('future-member','label-group','owner','member','active',?,NULL,1)",
                            ('2026-10-24T10:05:00Z',))
        now = [AT]
        reader = PeopleReadService(self.config, contracts=self.contracts, reads=self.reads, cursor_config=self.cursor, now=lambda: now[0])
        request = self.agenda(limit='1', include=['people'])
        first = self.read('agenda.show', request, reader=reader)['result']
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(first['next_cursor'], now=AT)
        self.assertEqual(payload['authorization_valid_until_utc'], '2026-10-24T10:05:00Z')
        epoch = self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0]
        now[0] = '2026-10-24T10:05:00Z'
        self.rejected('access_changed', 'agenda.show', {**request, 'cursor': first['next_cursor']}, reader=reader)
        self.assertEqual(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0], epoch)
