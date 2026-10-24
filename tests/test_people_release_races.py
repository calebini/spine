"""PR-16: people successor access transitions on real disposable file ledgers."""

import copy
import sqlite3
import unittest

from spine.commands.people_runtime import PeopleCursorCodec
from spine.ledger import connect
from spine.web.errors import WebError
from spine.web.people_read_service import PeopleReadService
from spine.web.provisioning import apply, plan
from tests import test_people_read_integration as reads
from tests import test_people_web as web

AT = web.AT
TRANSITION = '2026-10-24T10:05:00Z'


class PeopleReleaseRaceTests(unittest.TestCase):
    setUpClass = reads.PeopleReadIntegrationTests.__dict__['setUpClass']
    setUp = reads.PeopleReadIntegrationTests.setUp
    service_with = reads.PeopleReadIntegrationTests.service_with
    reader_with = reads.PeopleReadIntegrationTests.reader_with
    event, adopt, agenda, read, rejected = (reads.PeopleReadIntegrationTests.event, reads.PeopleReadIntegrationTests.adopt,
        reads.PeopleReadIntegrationTests.agenda, reads.PeopleReadIntegrationTests.read, reads.PeopleReadIntegrationTests.rejected)
    subject, group, task, body, run_command = (web.PeopleWebTests.subject, web.PeopleWebTests.group, web.PeopleWebTests.task,
        web.PeopleWebTests.body, web.PeopleWebTests.run_command)

    def external(self):
        second = connect(self.h.path, busy_timeout_ms=1)
        self.addCleanup(second.close)
        return second

    def external_provision(self, second, **operations):
        epoch = str(second.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0])
        proposed = plan(second, {'contract_version': 'spine.trusted-web-provisioning.v1',
            'ledger_id': 'test-ledger', 'expected_access_epoch': epoch, **operations})
        self.assertTrue(proposed['can_apply'], proposed)
        result = apply(second, {'contract_version': 'spine.trusted-web-provisioning.v1',
            'command_id': 'external-people-release-' + epoch, 'actor_subject_id': 'owner',
            'action_timestamp_utc': AT, 'expected_access_epoch': epoch, 'plan': proposed})
        self.assertTrue(result['ok'], result)
        return result

    def grant_item(self, identity, *, operations=('item.read',), starts='2026-01-01T00:00:00Z', ends=None):
        result = self.h.provision(grants=[{'operation': 'create', 'resource_kind': 'item', 'resource_id': identity,
            'resource_owner_revision': '1', 'grantee': {'owner_kind': 'subject', 'owner_subject_id': 'other'},
            'operations': list(operations), 'starts_at_utc': starts, 'ends_at_utc': ends}])
        return result['results'][0]['row_ids'][0]

    def reader_at(self, now, **kwargs):
        return PeopleReadService(self.config, contracts=self.contracts, reads=self.reads, cursor_config=self.cursor,
                                 now=lambda: now[0], **kwargs)

    def test_separate_connection_revocation_discards_buffered_people_read(self):
        identity = self.event()
        grant = self.grant_item(identity)
        second, after = self.external(), []

        def revoke():
            self.external_provision(second, grants=[{'operation': 'revoke', 'grant_id': grant, 'expected_revision': '1'}])
            after.append('\n'.join(second.iterdump()))

        self.rejected('access_changed', 'schedule.show', {'item_id': identity, 'include': ['people']},
            subject='other', reader=self.reader_with(before_release=revoke))
        self.assertEqual(len(after), 1)
        self.assertEqual('\n'.join(self.db.iterdump()), after[0])
        self.rejected('resource_unavailable', 'schedule.show', {'item_id': identity, 'include': ['people']}, subject='other')

    def test_grant_expiry_fences_both_release_and_cursor_without_epoch_write(self):
        for identity in ('one', 'two'):
            self.event(identity)
            self.grant_item(identity, ends=TRANSITION)
        now = [AT]
        reader = self.reader_at(now)
        request = self.agenda(limit='1', include=['people'], person_filter={'subject_id': 'other'})
        first = self.read('agenda.show', request, subject='other', reader=reader)['result']
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(first['next_cursor'], now=AT)
        self.assertEqual(payload['authorization_valid_until_utc'], TRANSITION)
        epoch = self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0]
        expiring = self.reader_at(now, before_release=lambda: now.__setitem__(0, TRANSITION))
        self.rejected('access_changed', 'schedule.show', {'item_id': 'one', 'include': ['people']},
            subject='other', reader=expiring)
        self.rejected('access_changed', 'agenda.show', {**request, 'cursor': first['next_cursor']}, subject='other', reader=reader)
        fresh = self.read('agenda.show', request, subject='other', reader=reader)['result']
        self.assertEqual(fresh['entries'], [])
        self.assertEqual(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0], epoch)

    def test_future_item_grant_activation_invalidates_cursor_before_new_candidate_disclosure(self):
        for identity in ('one', 'two', 'future'):
            self.event(identity)
            self.grant_item(identity, starts=TRANSITION if identity == 'future' else '2026-01-01T00:00:00Z')
        now = [AT]
        reader = self.reader_at(now)
        request = self.agenda(limit='1', include=['people'], person_filter={'subject_id': 'other'})
        first = self.read('agenda.show', request, subject='other', reader=reader)['result']
        self.assertEqual(first['entries'][0]['activity']['item_id'], 'one')
        payload = PeopleCursorCodec(self.contracts, self.cursor).decode(first['next_cursor'], now=AT)
        self.assertEqual(payload['authorization_valid_until_utc'], TRANSITION)
        epoch = self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0]
        now[0] = TRANSITION
        self.rejected('access_changed', 'agenda.show', {**request, 'cursor': first['next_cursor']}, subject='other', reader=reader)
        fresh = self.read('agenda.show', {**request, 'limit': '10'}, subject='other', reader=reader)['result']
        self.assertEqual({row['activity']['item_id'] for row in fresh['entries']}, {'one', 'two', 'future'})
        self.assertEqual(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0], epoch)

    def test_roster_revocation_serializes_with_write_and_replay_requires_only_retained_read(self):
        self.subject('child')
        self.group(extra=('child',))
        self.task(scope=web.GROUP)
        read_grant = self.grant_item('task')
        edit_grant = self.grant_item('task', operations=('item.read', 'item.edit'))
        memberships = {row['subject_id']: row['membership_id'] for row in self.db.execute('SELECT * FROM subject_memberships')}
        revoke_child = {'operation': 'revoke', 'membership_id': memberships['child'],
                        'expected_revision': '1', 'ends_at_utc': AT}
        second, attempted = self.external(), []

        def revoke_during_release(_):
            # SQLite linearizes this real second writer after the protected
            # people transaction; it cannot invalidate the roster mid-commit.
            with self.assertRaises(sqlite3.OperationalError):
                self.external_provision(second, memberships=[revoke_child])
            self.assertFalse(second.in_transaction)
            attempted.append(True)

        body = self.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['child']})
        body['request']['actor_subject_id'] = 'other'
        first = self.run_command('item.people.update', body, subject='other',
            service=self.service_with(before_release=revoke_during_release))['result']
        self.assertEqual(attempted, [True])
        self.assertEqual(first['current_version'], '2')
        self.assertEqual(self.db.execute("SELECT status FROM subject_memberships WHERE membership_id=?",
            (memberships['child'],)).fetchone()[0], 'active')
        self.external_provision(second, memberships=[revoke_child, {
            'operation': 'revoke', 'membership_id': memberships['other'], 'expected_revision': '1', 'ends_at_utc': AT}],
            grants=[{'operation': 'revoke', 'grant_id': edit_grant, 'expected_revision': '1'}])
        before = '\n'.join(self.db.iterdump())
        replay = self.run_command('item.people.update', body, subject='other')['result']
        self.assertEqual(replay['effect'], 'item_people_replay')
        self.assertEqual(replay['associations'], first['associations'])
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        fresh = copy.deepcopy(body)
        fresh['request'].update(command_id='new-after-edit-revocation', target_version='2', people={'assignees': []})
        fresh['expected_access_epoch'] = str(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0])
        with self.assertRaises(WebError) as caught:
            self.run_command('item.people.update', fresh, subject='other')
        self.assertEqual(caught.exception.code, 'resource_unavailable')
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        self.external_provision(second, grants=[{'operation': 'revoke', 'grant_id': read_grant, 'expected_revision': '1'}])
        with self.assertRaises(WebError) as caught:
            self.run_command('item.people.update', body, subject='other')
        self.assertEqual(caught.exception.code, 'resource_unavailable')
