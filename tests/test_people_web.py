"""Private protected standalone people paths on disposable file-backed ledgers."""

import copy
import unittest
from dataclasses import replace
from pathlib import Path

from spine.commands import handle
from spine.commands.people_runtime import API, CONTRACT, PeopleContracts, PeopleCursorCodec, PeopleCursorConfig
from spine.ledger import ItemSubjectRoleInput, create_task_v1
from spine.web.errors import WebError
from spine.web.people_service import PeopleService
from spine.web.service import WebConfig
from tests import test_trusted_web_runtime as helper

AT = '2026-10-24T10:00:00Z'
GROUP = {'owner_kind': 'subject_group', 'owner_group_id': 'group'}
ROOT = Path(__file__).parents[1]


class PeopleWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = PeopleContracts(ROOT)

    def setUp(self):
        self.h = helper.TrustedWebRuntimeTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.db = self.h.db
        self.config = WebConfig(self.h.path, 'test-ledger')
        instance = self.db.execute('SELECT ledger_instance_id FROM ledger_instance_metadata').fetchone()[0]
        self.cursor = PeopleCursorConfig('people_test', '1', instance, b'c' * 32)
        self.service = self.service_with()
        self.number = 0

    def service_with(self, **kwargs):
        return PeopleService(self.config, contracts=self.contracts, cursor_config=self.cursor, now=lambda: AT, **kwargs)

    def subject(self, subject, **kwargs):
        result = handle('subject.upsert', {'command_id': 'seed-' + subject, 'actor_subject_id': 'owner',
            'subject_id': subject, 'subject_kind': 'person', 'display_name': subject,
            'updated_at_utc': AT, **kwargs}, self.h.ctx)
        self.assertTrue(result['ok'], result)

    def group(self, *, extra=()):
        result = handle('subject_group.upsert', {'command_id': 'seed-group', 'actor_subject_id': 'owner',
            'group_id': 'group', 'display_name': 'Arbitrary group', 'updated_at_utc': AT}, self.h.ctx)
        self.assertTrue(result['ok'], result)
        self.h.provision(memberships=[{'operation': 'create', 'group_id': 'group', 'subject_id': subject,
            'role': 'owner' if subject == 'owner' else 'member', 'starts_at_utc': '2026-01-01T00:00:00Z'}
            for subject in ('owner', 'other', *extra)])

    def task(self, *, scope=None, roles=()):
        create_task_v1(self.db, item_id='task', audit_id='task-create', created_at_utc=AT, created_by_subject_id='owner',
                       title='Unscheduled task', subject_roles=roles)
        self.h.provision(item_adoptions=[{'operation': 'create', 'item_id': 'task', 'expected_item_version': '1',
                                         'owner_scope': scope or {'owner_kind': 'subject', 'owner_subject_id': 'owner'}}])

    def grant(self, operations):
        self.h.provision(grants=[{'operation': 'create', 'resource_kind': 'item', 'resource_id': 'task',
            'resource_owner_revision': '1', 'grantee': {'owner_kind': 'subject', 'owner_subject_id': 'other'},
            'operations': operations, 'starts_at_utc': '2026-01-01T00:00:00Z', 'ends_at_utc': None}])

    def body(self, command, **kwargs):
        request = {'contract_version': CONTRACT, **kwargs}
        body = {'contract_version': API, 'request': request}
        if command == 'item.people.update':
            self.number += 1
            request.update(command_id='people-web-' + str(self.number), actor_subject_id='owner', updated_at_utc=AT)
            body['expected_access_epoch'] = str(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0])
        return body

    def run_command(self, command, body, *, subject='owner', service=None, **kwargs):
        return (service or self.service).execute(command, body, self.h.accounts[subject], 'selection', **kwargs)

    def denied(self, code, command, body, **kwargs):
        before = '\n'.join(self.db.iterdump())
        with self.assertRaises(WebError) as caught:
            self.run_command(command, body, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_roster_member_current_labels_paging_and_no_durable_output(self):
        self.subject('child')
        self.group(extra=('child',))
        before = '\n'.join(self.db.iterdump())
        body = self.body('people.list', owner=GROUP, limit='1')
        pages, cursor = [], None
        while True:
            current = copy.deepcopy(body)
            if cursor:
                current['request']['cursor'] = cursor
            response = self.run_command('people.list', current, subject='other')
            self.contracts.validate('web-responses', response, definition='people.list', output=True)
            pages.extend(row['subject_id'] for row in response['result']['subjects'])
            cursor = response['result']['next_cursor']
            if not cursor:
                break
        self.assertEqual(pages, ['child', 'other', 'owner'])
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_item_grant_does_not_allow_roster_or_fresh_reference_probe(self):
        self.subject('private-person')
        self.task(roles=(ItemSubjectRoleInput(subject_id='private-person', role='assignee'),))
        self.grant(['item.read', 'item.edit'])
        shown = self.run_command('item.people.show', self.body('item.people.show', item_id='task'), subject='other')
        self.assertEqual(shown['result']['people']['subjects'], [
            {'subject_id': 'private-person', 'label': {'availability': 'not_disclosed'}}])
        self.denied('resource_unavailable', 'people.list', self.body('people.list',
            owner={'owner_kind': 'subject', 'owner_subject_id': 'owner'}), subject='other')
        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['other']})
        body['request']['actor_subject_id'] = 'other'
        self.denied('resource_unavailable', 'item.people.update', body, subject='other')
        # Exact retained reference is a no-op without directory admission.
        body['request']['people'] = {'assignees': ['private-person']}
        kept = self.run_command('item.people.update', body, subject='other')['result']
        self.assertEqual(kept['effect'], 'item_people_noop')
        clear = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': []})
        clear['request']['actor_subject_id'] = 'other'
        self.assertEqual(self.run_command('item.people.update', clear, subject='other')['result']['current_version'], '2')

    def test_group_addition_uses_real_owner_and_one_canonical_version(self):
        self.subject('child')
        self.group(extra=('child',))
        self.task(scope=GROUP)
        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['child', 'other']})
        result = self.run_command('item.people.update', body)['result']
        self.assertEqual((result['effect'], result['current_version']), ('item_people_updated', '2'))
        self.assertEqual([r['subject_id'] for r in result['associations']], ['child', 'other'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM coordination_item_versions WHERE item_id='task'").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM command_receipts WHERE command='item.people.update'").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM work_instances").fetchone()[0], 0)

    def test_private_task_cannot_add_another_subject_even_shared_group(self):
        self.group()
        self.task()
        self.denied('resource_unavailable', 'item.people.update', self.body('item.people.update',
            item_id='task', target_version='1', people={'assignees': ['other']}))

    def test_replay_requires_initiator_and_current_read_not_fresh_edit_or_reference(self):
        self.subject('child')
        self.group(extra=('child',))
        self.task(scope=GROUP)
        self.grant(['item.read', 'item.edit'])
        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['child']})
        body['request']['actor_subject_id'] = 'other'
        first = self.run_command('item.people.update', body, subject='other')['result']
        with self.db:
            self.db.execute("UPDATE subject_memberships SET status='ended',ends_at_utc=? WHERE subject_id='other'", (AT,))
            self.db.execute("DELETE FROM access_grant_operations WHERE operation='item.edit'")
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='child'")
        before = '\n'.join(self.db.iterdump())
        replay = self.run_command('item.people.update', body, subject='other')['result']
        self.assertEqual(replay['effect'], 'item_people_replay')
        self.assertEqual(replay['associations'], first['associations'])
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        altered = copy.deepcopy(body)
        altered['request']['actor_subject_id'] = 'owner'
        self.denied('command_id_unavailable', 'item.people.update', altered)
        with self.db:
            self.db.execute("UPDATE access_grants SET status='revoked'")
        self.denied('resource_unavailable', 'item.people.update', body, subject='other')

    def test_history_retains_ids_but_current_shared_roster_controls_labels(self):
        self.subject('child')
        self.task(roles=(ItemSubjectRoleInput(subject_id='child', role='assignee'),))
        body = self.body('item.people.show', item_id='task', version='1')
        shown = self.run_command('item.people.show', body)['result']
        self.assertEqual(shown['people']['subjects'][0]['label'], {'availability': 'not_disclosed'})
        self.group(extra=('child',))
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Current name',status='inactive' WHERE subject_id='child'")
        current = self.run_command('item.people.show', body)['result']
        self.assertEqual(current['people']['subjects'][0]['label']['display_name'], 'Current name')
        self.assertEqual(current['people']['associations'], shown['people']['associations'])

    def test_release_source_membership_and_selection_changes_fail_closed(self):
        self.group()
        body = self.body('people.list', owner=GROUP, limit='1')
        def rename(_):
            with self.db:
                self.db.execute("UPDATE subjects SET display_name='At release' WHERE subject_id='other'")
        with self.assertRaises(WebError) as caught:
            self.run_command('people.list', body, service=self.service_with(before_release=rename))
        self.assertEqual(caught.exception.code, 'access_changed')
        def revoke(_):
            with self.db:
                self.db.execute("UPDATE subject_memberships SET status='ended',ends_at_utc=? WHERE subject_id='owner'", (AT,))
        with self.assertRaises(WebError) as caught:
            self.run_command('people.list', body, service=self.service_with(before_release=revoke))
        self.assertEqual(caught.exception.code, 'access_changed')

    def test_hidden_label_rename_does_not_break_release(self):
        self.subject('hidden')
        self.task(roles=(ItemSubjectRoleInput(subject_id='hidden', role='assignee'),))
        def rename(_):
            with self.db:
                self.db.execute("UPDATE subjects SET display_name='Invisible rename' WHERE subject_id='hidden'")
        response = self.run_command('item.people.show', self.body('item.people.show', item_id='task'),
                                    service=self.service_with(before_release=rename))
        self.assertEqual(response['result']['people']['subjects'][0]['label'], {'availability': 'not_disclosed'})

    def test_cursor_query_identity_source_and_time_fences(self):
        self.group()
        body = self.body('people.list', owner=GROUP, limit='1')
        first = self.run_command('people.list', body)['result']
        cursor = first['next_cursor']
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(cursor, now=AT)
        self.assertEqual(payload['mode'], 'permission_enforced')
        continued = copy.deepcopy(body)
        continued['request']['cursor'] = cursor
        self.denied('access_changed', 'people.list', continued, subject='other')
        changed = copy.deepcopy(continued)
        changed['request']['limit'] = '2'
        self.denied('access_changed', 'people.list', changed)
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='New source' WHERE subject_id='other'")
        self.denied('access_changed', 'people.list', continued)

    def test_service_budget_missing_key_and_complete_public_activation(self):
        body = self.body('people.list', owner={'owner_kind': 'subject', 'owner_subject_id': 'owner'})
        self.denied('admission_unavailable', 'people.list', body, service=PeopleService(self.config,
            contracts=self.contracts, now=lambda: AT))
        self.denied('capacity_exceeded', 'people.list', body, service=PeopleService(
            replace(self.config, sql_steps=10), contracts=self.contracts, cursor_config=self.cursor, now=lambda: AT))
        from spine import IMPLEMENTED_CONTRACT_VERSIONS
        from spine.commands.registry import MVP_COMMANDS
        self.assertIn(CONTRACT, IMPLEMENTED_CONTRACT_VERSIONS)
        self.assertIn('people.list', MVP_COMMANDS)
        self.assertIn('item.people.show', MVP_COMMANDS)

    def test_failed_write_release_rolls_back_version_roles_audit_receipt_and_link(self):
        self.group()
        self.task(scope=GROUP)
        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['other']})
        before = '\n'.join(self.db.iterdump())
        def revoke(db):
            db.execute("UPDATE subject_memberships SET status='ended',ends_at_utc=? WHERE subject_id='other'", (AT,))
        with self.assertRaises(WebError) as caught:
            self.run_command('item.people.update', body, service=self.service_with(before_release=revoke))
        self.assertEqual(caught.exception.code, 'access_changed')
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_selected_identity_change_is_checked_again_at_release(self):
        self.task()
        selection = [self.h.accounts['owner'], 'selection']
        service = self.service_with(before_release=lambda _: selection.__setitem__(1, 'new-selection'))
        self.denied('access_changed', 'item.people.show', self.body('item.people.show', item_id='task'),
                    service=service, current_selection=lambda: tuple(selection))

    def test_membership_time_transition_invalidates_cursor_without_epoch_bump(self):
        self.subject('later')
        self.group()
        with self.db:
            self.db.execute("INSERT INTO subject_memberships VALUES ('future','group','later','member','active',?,NULL,1)",
                            ('2026-10-24T10:05:00Z',))
        time = [AT]
        service = PeopleService(self.config, contracts=self.contracts, cursor_config=self.cursor, now=lambda: time[0])
        body = self.body('people.list', owner=GROUP, limit='1')
        first = self.run_command('people.list', body, service=service)['result']
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(first['next_cursor'], now=AT)
        self.assertEqual(payload['authorization_valid_until_utc'], '2026-10-24T10:05:00Z')
        epoch = self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0]
        body['request']['cursor'] = first['next_cursor']
        time[0] = '2026-10-24T10:05:00Z'
        self.denied('access_changed', 'people.list', body, service=service)
        self.assertEqual(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0], epoch)

    def test_validation_root_and_fresh_epoch_precedence(self):
        self.task()
        body = self.body('item.people.update', item_id='task', target_version='99', people={'assignees': []})
        body['expected_access_epoch'] = '999999'
        self.denied('access_changed', 'item.people.update', body)
        body['request']['actor_subject_id'] = 'other'
        self.denied('resource_unavailable', 'item.people.update', body, subject='other')
        bad = copy.deepcopy(body)
        bad['request']['unexpected'] = 'field'
        self.denied('invalid_request', 'item.people.update', bad)

    def test_cursor_key_rotation_during_first_page_release_refuses(self):
        self.group()
        service = self.service_with()
        service.before_release = lambda _: setattr(service, 'cursor_config', replace(self.cursor, key_generation='2'))
        self.denied('access_changed', 'people.list', self.body('people.list', owner=GROUP, limit='1'), service=service)

    def test_request_actor_cannot_impersonate_a_different_subject(self):
        self.task()
        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': []})
        body['request']['actor_subject_id'] = 'other'
        self.denied('identity_unavailable', 'item.people.update', body)
