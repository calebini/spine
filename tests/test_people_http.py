"""Public successor HTTP routes with real disposable ledgers and packaged contracts."""

import copy
import json
import unittest
from contextlib import closing, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spine.commands import handle
from spine.commands.cli import main as command_main
from spine.commands.people_runtime import API, PeopleContracts
from spine.core.schedule import system_timezone_database_version
from spine.ledger import connect
from spine.web.http import PEOPLE_PATHS, create_app
from tests import test_people_web as helper

AT = helper.AT


class PeopleHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helper.PeopleWebTests.setUpClass()

    def setUp(self):
        self.seed = helper.PeopleWebTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.db = self.seed.db
        self.contracts = PeopleContracts.packaged()
        self.app = create_app(self.seed.config, people_cursor_config=self.seed.cursor)
        self.service = self.app.extensions['spine_people_service']
        self.service.now = lambda: AT
        self.client = self.app.test_client()

    def headers(self, subject='owner', **changes):
        return {'Host': self.seed.config.host, 'Origin': self.seed.config.origin, 'Content-Type': 'application/json',
                'X-Spine-Account-ID': self.seed.h.accounts[subject], 'X-Spine-Selection-ID': 'selection', **changes}

    def post(self, command, body, *, subject='owner', client=None, **changes):
        return (client or self.client).post(PEOPLE_PATHS[command], data=json.dumps(body), headers=self.headers(subject, **changes))

    def success(self, command, body, **kwargs):
        response = self.post(command, body, **kwargs)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.contracts.validate('web-responses', response.json, definition=command, output=True)
        return response.json['result']

    def failure(self, response, code, status):
        self.assertEqual(response.status_code, status, response.json)
        self.contracts.validate('failures', response.json, definition='protected', output=True)
        self.assertEqual(response.json['error'], {'code': code, 'message': 'People operation unavailable.'})

    def epoch(self):
        return str(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0])

    def create(self, *, command='http-create', people=None):
        body = self.seed.h.event(command)
        body['contract_version'] = API
        body['request']['contract_version'] = 'spine.schedule-create.v4'
        body['request']['materialization'] = {'mode': 'none'}
        body['request']['people'] = {'participants': ['owner'] if people is None else people}
        return body

    def update(self, item, patch):
        return {'contract_version': API, 'expected_access_epoch': self.epoch(), 'request': {
            'contract_version': 'spine.schedule-update.v4', 'command_id': 'http-update', 'actor_subject_id': 'owner',
            'updated_at_utc': AT, 'item_id': item['item_id'], 'target_version': item['current_version'],
            'patch': patch, 'materialization': {'mode': 'none'}}}

    def dump(self):
        return '\n'.join(self.db.iterdump())

    def test_exact_eight_routes_without_unreviewed_discovery(self):
        routes = {(rule.rule, method) for rule in self.app.url_map.iter_rules() if rule.rule.startswith('/api/v3/')
                  for method in rule.methods - {'HEAD', 'OPTIONS'}}
        self.assertEqual(routes, {(path, 'POST') for path in PEOPLE_PATHS.values()})
        self.failure(self.client.get('/api/v3/capabilities', headers=self.headers()), 'operation_unavailable', 404)

    def test_public_cli_http_mutation_and_replay_results_match_on_cloned_baseline(self):
        self.seed.group()
        self.seed.task(scope=helper.GROUP)
        clone = Path(self.seed.h.tmp.name) / 'cli-parity.sqlite'
        with closing(connect(clone)) as target:
            self.db.backup(target)
        def cli(command, request):
            output = StringIO()
            with patch('sys.stdin', StringIO(json.dumps(request))), redirect_stdout(output):
                status = command_main(['--db', str(clone), '--input', '-', *command.split('.')])
            value = json.loads(output.getvalue())
            self.assertEqual(status, 0, value)
            return value
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['other', 'owner']})
        for _ in range(2):
            self.assertEqual(self.success('item.people.update', body), cli('item.people.update', body['request']))
        create_body = self.create(command='http-cli-parity-create')
        for _ in range(2):
            self.assertEqual(self.success('schedule.create', create_body), cli('schedule.create', create_body['request']))

    def test_standalone_current_history_changed_noop_replay_and_no_sends(self):
        self.seed.group()
        self.seed.task(scope=helper.GROUP)
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['other']})
        first = self.success('item.people.update', body)
        self.assertEqual(first['effect'], 'item_people_updated')
        self.assertEqual(first['current_version'], '2')
        before = self.dump()
        replay = self.success('item.people.update', body)
        self.assertEqual(replay['effect'], 'item_people_replay')
        self.assertEqual(first['associations'], replay['associations'])
        self.assertEqual(self.dump(), before)
        noop_body = self.seed.body('item.people.update', item_id='task', target_version='2', people={'assignees': ['other']})
        noop = self.success('item.people.update', noop_body)
        self.assertEqual(noop['effect'], 'item_people_noop')
        self.assertEqual(noop['associations'], first['associations'])
        for version in ('1', '2'):
            shown = self.success('item.people.show', self.seed.body('item.people.show', item_id='task', version=version))
            self.assertEqual(shown['people']['item_version'], version)
            self.assertEqual(shown['current_version'], '2')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)

    def test_scheduling_successors_one_atomic_receipt_and_ordinary_read_surfaces(self):
        body = self.create()
        created = self.success('schedule.create', body)
        self.assertEqual(created['phases']['delivery'], 'not_attempted')
        self.assertEqual([p['subject_id'] for p in created['people']], ['owner'])
        updated = self.success('schedule.update', self.update(created, {'item': {'title': 'Changed'},
                                                                      'people': {'participants': []}}))
        self.assertEqual(updated['changed_dimensions'], ['item', 'people'])
        self.assertEqual(updated['current_version'], '2')
        shown = self.success('schedule.show', {'contract_version': API, 'request': {
            'item_id': created['item_id'], 'include': ['people']}})
        self.assertEqual(shown['sections']['people']['availability'], 'available')
        self.assertEqual(shown['sections']['people']['people']['associations'], [])
        agenda = self.seed.h.agenda()
        agenda.pop('contract_version')
        agenda['timezone_database_version'] = system_timezone_database_version()
        response = self.success('agenda.show', {'contract_version': API, 'request': agenda})
        self.assertEqual([r['activity']['item_id'] for r in response['entries']], [created['item_id']])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)

    def test_roster_pc1_continuation_tamper_query_identity_and_no_writes(self):
        self.seed.group()
        body = self.seed.body('people.list', owner=helper.GROUP, limit='1')
        before = self.dump()
        first = self.success('people.list', body)
        self.assertTrue(first['next_cursor'].startswith('pc1.'))
        current = copy.deepcopy(body)
        current['request']['cursor'] = first['next_cursor']
        second = self.success('people.list', current)
        self.assertNotEqual(first['subjects'][0]['subject_id'], second['subjects'][0]['subject_id'])
        self.failure(self.post('people.list', current, subject='other'), 'access_changed', 409)
        changed = copy.deepcopy(current)
        changed['request']['limit'] = '2'
        self.failure(self.post('people.list', changed), 'access_changed', 409)
        changed['request']['cursor'] += 'x'
        self.failure(self.post('people.list', changed), 'invalid_request', 400)
        self.assertEqual(self.dump(), before)

    def test_foreign_or_missing_roots_share_non_disclosing_failure(self):
        self.seed.task()
        before = self.dump()
        for identity in ('task', 'missing'):
            result = self.post('item.people.show', self.seed.body('item.people.show', item_id=identity), subject='other')
            self.failure(result, 'resource_unavailable', 404)
            self.assertNotIn(identity, result.json['error']['message'])
        self.assertEqual(self.dump(), before)

    def test_trusted_selection_actor_and_closed_body_identity_failures(self):
        self.seed.task()
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['owner']})
        body['request']['actor_subject_id'] = 'other'
        self.failure(self.post('item.people.update', body), 'identity_unavailable', 403)
        forged = self.seed.body('item.people.show', item_id='task')
        forged['account_id'] = self.seed.h.accounts['other']
        self.failure(self.post('item.people.show', forged), 'invalid_request', 400)
        self.failure(self.post('item.people.show', self.seed.body('item.people.show', item_id='task'),
                               **{'X-Spine-Account-ID': 'unknown'}), 'identity_unavailable', 403)

    def test_fresh_private_owner_cannot_add_unrelated_person_or_expose_reference_id(self):
        before = self.dump()
        for subject in ('other', 'does-not-exist'):
            self.failure(self.post('schedule.create', self.create(people=[subject])), 'resource_unavailable', 404)
        self.assertEqual(self.dump(), before)

    def test_access_guard_precedes_target_version_and_conflicts_do_not_mutate(self):
        self.seed.task()
        body = self.seed.body('item.people.update', item_id='task', target_version='9', people={'assignees': ['owner']})
        before = self.dump()
        stale = copy.deepcopy(body)
        stale['expected_access_epoch'] = '999'
        self.failure(self.post('item.people.update', stale), 'access_changed', 409)
        self.failure(self.post('item.people.update', body), 'version_changed', 409)
        self.assertEqual(self.dump(), before)

    def test_replay_checks_retained_read_not_fresh_directory_or_edit_authority(self):
        self.seed.group()
        self.seed.task(scope=helper.GROUP)
        self.seed.grant(['item.read', 'item.edit'])
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['owner']})
        body['request']['actor_subject_id'] = 'other'
        first = self.success('item.people.update', body, subject='other')
        with self.db:
            self.db.execute("UPDATE subject_memberships SET status='ended',ends_at_utc=? WHERE subject_id='other'", (AT,))
            self.db.execute("DELETE FROM access_grant_operations WHERE operation='item.edit'")
        before = self.dump()
        replay = self.success('item.people.update', body, subject='other')
        self.assertEqual((replay['effect'], replay['associations']), ('item_people_replay', first['associations']))
        self.assertEqual(self.dump(), before)
        self.failure(self.post('item.people.update', body), 'command_id_unavailable', 409)
        with self.db:
            self.db.execute("UPDATE access_grants SET status='revoked'")
        self.failure(self.post('item.people.update', body, subject='other'), 'resource_unavailable', 404)

    def test_transport_origin_forwarding_query_body_and_json_guards(self):
        self.seed.task()
        body = self.seed.body('item.people.show', item_id='task')
        before = self.dump()
        self.failure(self.post('item.people.show', body, Origin='https://other.invalid'), 'invalid_request', 403)
        self.failure(self.post('item.people.show', body, **{'X-Spine-Actor': 'owner'}), 'invalid_request', 400)
        self.failure(self.client.post(PEOPLE_PATHS['item.people.show'] + '?actor=owner', headers=self.headers(),
                                     data=json.dumps(body)), 'invalid_request', 400)
        for raw in ('{"request":{},"request":{}}', '[1]', '{"x":NaN}'):
            self.failure(self.client.post(PEOPLE_PATHS['item.people.show'], headers=self.headers(), data=raw), 'invalid_request', 400)
        self.failure(self.client.post(PEOPLE_PATHS['item.people.show'], headers=self.headers(), data=' ' * 1048577),
                     'invalid_request', 413)
        self.assertEqual(self.dump(), before)

    def test_missing_or_wrong_instance_configuration_disables_whole_successor_family_only(self):
        self.seed.task()
        for cursor in (None, replace(self.seed.cursor, ledger_instance_id='different-instance')):
            app = create_app(self.seed.config, people_cursor_config=cursor)
            app.extensions['spine_people_service'].now = lambda: AT
            client = app.test_client()
            for command, body in (
                ('item.people.show', self.seed.body('item.people.show', item_id='task')),
                ('schedule.create', self.create(command='config-guard')),
                ('schedule.show', {'contract_version': API, 'request': {'item_id': 'task'}}),
            ):
                self.failure(self.post(command, body, client=client), 'admission_unavailable', 503)
            self.assertEqual(client.get('/api/v1/info', headers=self.headers()).status_code, 200)
            self.assertEqual(client.get('/api/v2/read-capabilities', headers=self.headers()).status_code, 200)

    def test_serialization_is_bounded_and_happens_before_write_commit(self):
        self.seed.task()
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['owner']})
        original = self.app.json.dumps
        def inflated(value, **kwargs):
            return ' ' * 4194305 if isinstance(value, dict) and value.get('contract_version') == API and value.get('ok') else (
                original(value, **kwargs))
        before = self.dump()
        with patch.object(self.app.json, 'dumps', side_effect=inflated):
            self.failure(self.post('item.people.update', body), 'capacity_exceeded', 429)
        self.assertEqual(self.dump(), before)
        with patch.object(self.app.json, 'dumps', side_effect=inflated):
            self.failure(self.post('schedule.create', self.create()), 'capacity_exceeded', 429)
        self.assertEqual(self.dump(), before)

    def test_transport_elapsed_time_is_shared_with_mutation_budget(self):
        self.seed.task()
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['owner']})
        original = self.service.execute
        def spent(*args, **kwargs):
            self.assertIsNotNone(kwargs.get('started'))
            kwargs['started'] -= 6
            return original(*args, **kwargs)
        before = self.dump()
        with patch.object(self.service, 'execute', side_effect=spent):
            self.failure(self.post('item.people.update', body), 'capacity_exceeded', 429)
            self.failure(self.post('schedule.create', self.create()), 'capacity_exceeded', 429)
        self.assertEqual(self.dump(), before)

    def test_read_encoding_precedes_current_authority_release_fence(self):
        self.seed.task()
        original = self.app.json.dumps
        def revoked(value, **kwargs):
            if isinstance(value, dict) and value.get('contract_version') == API and value.get('ok'):
                with self.db:
                    self.db.execute("UPDATE web_operators SET eligible=0 WHERE account_id=?", (self.seed.h.accounts['owner'],))
            return original(value, **kwargs)
        with patch.object(self.app.json, 'dumps', side_effect=revoked):
            self.failure(self.post('item.people.show', self.seed.body('item.people.show', item_id='task')), 'access_changed', 409)

    def test_failed_write_fence_rolls_back_every_domain_and_access_row(self):
        self.seed.group()
        self.seed.task(scope=helper.GROUP)
        body = self.seed.body('item.people.update', item_id='task', target_version='1', people={'assignees': ['other']})
        before = self.dump()
        self.service.before_release = lambda db: db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='other'")
        self.failure(self.post('item.people.update', body), 'access_changed', 409)
        self.assertEqual(self.dump(), before)

    def test_public_recurring_occurrences_pagination_and_literal_person_filter(self):
        result = handle('event.create', {'command_id': 'series-http', 'actor_subject_id': 'owner', 'created_at_utc': AT,
            'title': 'Series', 'all_day': False, 'start_anchor': {'anchor_kind': 'local_instant', 'local_date': '2026-10-24',
                'local_time': '12:00:00', 'timezone': 'UTC', 'timezone_database_version': system_timezone_database_version(),
                'recurrence_set': {'time_basis': 'local_instant', 'timezone': 'UTC',
                    'timezone_database_version': system_timezone_database_version(), 'rules': [{
                        'frequency': 'DAILY', 'seed': '2026-10-24T12:00:00', 'start_bound': '2026-10-24T12:00:00',
                        'end_condition': {'kind': 'count', 'count': '3'}}]}}}, self.seed.h.ctx)
        self.assertTrue(result['ok'], result)
        self.seed.h.provision(item_adoptions=[{'operation': 'create', 'item_id': result['item_id'], 'expected_item_version': '1',
            'owner_scope': {'owner_kind': 'subject', 'owner_subject_id': 'owner'}}])
        request = {'item_id': result['item_id'], 'range_basis': 'original_schedule', 'range_start': '2026-10-24T00:00:00',
                   'range_end': '2026-10-28T00:00:00', 'limit': '1'}
        first = self.success('item.occurrences', {'contract_version': API, 'request': request})
        self.assertEqual(len(first['occurrences']), 1)
        self.assertTrue(first['has_more'])
        second = self.success('item.occurrences', {'contract_version': API, 'request': {**request, 'cursor': first['next_cursor']}})
        self.assertNotEqual(first['occurrences'][0]['occurrence_id'], second['occurrences'][0]['occurrence_id'])
        empty = self.success('item.occurrences', {'contract_version': API, 'request': {
            **request, 'person_filter': {'subject_id': 'never-existed'}}})
        self.assertEqual(empty['occurrences'], [])
        self.assertEqual(empty['activity']['time']['availability'], 'available')


if __name__ == '__main__':
    unittest.main()
