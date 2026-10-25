"""People-v4/public-read seams retain timezone evidence across provider upgrades."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spine import timezones
from spine.commands.people_runtime import API, PeopleContracts
from spine.runtime.timezone_baselines import provision
from spine.web.http import PEOPLE_PATHS, create_app
from tests import test_people_web as helpers

FIXTURES = Path(__file__).parent / 'fixtures/timezones'


class TimezonePeopleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.PeopleWebTests.setUpClass()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='spine-tz-people-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'provider'
        self.catalog = Path(temporary.name) / 'baselines.json'
        shutil.copytree(FIXTURES / '2026c', self.root)
        provision(root=self.root, expected_version='2026c', zones=['Europe/Paris', 'America/Winnipeg'],
                  catalog=self.catalog, build_id='synthetic-fixture', origin='test-only TZif fixture',
                  artifact_sha256='a' * 64)
        provider = patch.object(timezones, 'TZPATH', (str(self.root),))
        provider.start()
        self.addCleanup(provider.stop)
        environment = patch.dict('os.environ', {'SPINE_TIMEZONE_BASELINES': str(self.catalog)})
        environment.start()
        self.addCleanup(environment.stop)
        self.seed = helpers.PeopleWebTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.db = self.seed.db
        self.contracts = PeopleContracts.packaged()
        self.app = create_app(self.seed.config, people_cursor_config=self.seed.cursor)
        self.app.extensions['spine_people_service'].now = lambda: helpers.AT
        self.client = self.app.test_client()

    def upgrade(self):
        shutil.copytree(FIXTURES / '2026e', self.root, dirs_exist_ok=True)

    def post(self, command, request):
        return self.client.post(PEOPLE_PATHS[command], data=json.dumps(request), headers={
            'Host': self.seed.config.host, 'Origin': self.seed.config.origin,
            'Content-Type': 'application/json', 'X-Spine-Account-ID': self.seed.h.accounts['owner'],
            'X-Spine-Selection-ID': 'selection'})

    def success(self, command, body):
        response = self.post(command, body)
        self.assertEqual(response.status_code, 200, response.json)
        self.contracts.validate('web-responses', response.json, definition=command, output=True)
        return response.json['result']

    def create_body(self, command_id, *, participants=('owner',), zone='Europe/Paris', recurring=False):
        body = self.seed.h.event(command_id)
        body['contract_version'] = API
        request = body['request']
        request.update(contract_version='spine.schedule-create.v4', created_at_utc=helpers.AT,
                       people={'participants': list(participants)}, materialization={'mode': 'none'})
        request['scheduled_time'] = {
            'time_basis': 'local_instant', 'local_date': '2026-10-24', 'local_time': '12:00:00',
            'timezone': zone, 'timezone_database_version': {'kind': 'explicit', 'version': '2026c'}}
        if recurring:
            request['scheduled_time']['recurrence'] = {'rules': [{
                'frequency': 'DAILY', 'interval': '1', 'seed': '2026-10-24T12:00:00',
                'start_bound': '2026-10-24T12:00:00', 'end_condition': {'kind': 'count', 'count': '3'}}]}
        return body

    def agenda_body(self):
        return {'contract_version': API, 'request': {
            'evaluated_at_utc': helpers.AT, 'range_start_local': '2026-10-24T00:00:00',
            'range_end_local': '2026-10-28T00:00:00', 'timezone': 'Europe/Paris',
            'timezone_database_version': '2026c', 'include': ['people'], 'limit': '25',
            'person_filter': {'subject_id': 'owner', 'roles': ['participant']}}}

    def dump(self):
        return '\n'.join(self.db.iterdump())

    def test_v4_create_replay_and_people_only_update_retain_authored_zone_pin(self):
        body = self.create_body('timezone-people-exact')
        created = self.success('schedule.create', body)
        self.upgrade()
        before = self.dump()
        replay = self.success('schedule.create', body)
        self.assertEqual(replay['command_receipt_id'], created['command_receipt_id'])
        self.assertEqual(replay['people'], created['people'])
        self.assertEqual(replay['scheduled_time'], created['scheduled_time'])
        self.assertEqual(self.dump(), before)
        after_upgrade = self.success('schedule.create', self.create_body('timezone-people-compatible'))
        self.assertEqual(after_upgrade['scheduled_time']['timezone_database_version'], '2026c')
        self.assertEqual(after_upgrade['scheduled_time']['utc_instant'], '2026-10-24T10:00:00Z')
        updated = self.success('schedule.update', {
            'contract_version': API,
            'expected_access_epoch': str(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0]),
            'request': {'contract_version': 'spine.schedule-update.v4', 'command_id': 'timezone-people-clear',
                        'actor_subject_id': 'owner', 'updated_at_utc': helpers.AT,
                        'item_id': after_upgrade['item_id'], 'target_version': '1',
                        'patch': {'people': {'participants': []}}, 'materialization': {'mode': 'none'}}})
        self.assertEqual(updated['changed_dimensions'], ['people'])
        self.assertEqual(updated['scheduled_time']['timezone_database_version'], '2026c')
        self.assertEqual(updated['people'], [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM work_instances').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)

    def test_person_filter_precedes_timezone_expansion_and_preserves_agenda_across_upgrade(self):
        selected = self.success('schedule.create', self.create_body('timezone-selected'))
        # This decoy has changed TZif bytes after upgrade. A nonmatching role set
        # must exclude it before time expansion rather than poisoning the page.
        self.success('schedule.create', self.create_body('timezone-not-selected', participants=(), zone='America/Winnipeg'))
        body = self.agenda_body()
        exact = self.success('agenda.show', body)
        self.assertEqual([row['activity']['item_id'] for row in exact['entries']], [selected['item_id']])
        self.assertEqual(exact['coverage'], 'complete')
        self.upgrade()
        before = self.dump()
        self.assertEqual(self.success('agenda.show', body), exact)
        self.assertEqual(self.dump(), before)
        anchor = exact['entries'][0]['activity']['time']['anchors'][0]
        self.assertEqual(anchor['timezone_database_version'], '2026c')

    def test_recurring_person_filter_and_pc1_continuation_keep_original_occurrences(self):
        created = self.success('schedule.create', self.create_body('timezone-recurring-people', recurring=True))
        body = {'contract_version': API, 'request': {
            'item_id': created['item_id'], 'range_basis': 'expressed_time',
            'range_start': '2026-10-24T00:00:00', 'range_end': '2026-10-28T00:00:00',
            'person_filter': {'subject_id': 'owner', 'roles': ['participant']}, 'limit': '1'}}
        first = self.success('item.occurrences', body)
        self.assertTrue(first['has_more'])
        second_body = copy.deepcopy(body)
        second_body['request']['cursor'] = first['next_cursor']
        exact_second = self.success('item.occurrences', second_body)
        self.upgrade()
        before = self.dump()
        self.assertEqual(self.success('item.occurrences', body), first)
        compatible_second = self.success('item.occurrences', second_body)
        self.assertEqual(compatible_second, exact_second)
        self.assertNotEqual(first['occurrences'][0]['occurrence_key'], compatible_second['occurrences'][0]['occurrence_key'])
        for result in (first, compatible_second):
            for anchor in result['occurrences'][0]['time']['anchors']:
                self.assertEqual(anchor['timezone_database_version'], '2026c')
        filtered_out = copy.deepcopy(body)
        filtered_out['request']['person_filter']['subject_id'] = 'other'
        self.assertEqual(self.success('item.occurrences', filtered_out)['occurrences'], [])
        self.assertEqual(self.dump(), before)

    def test_fresh_v4_creation_fails_closed_without_baseline_or_with_changed_zone(self):
        self.upgrade()
        original_catalog = self.catalog.read_bytes()
        self.catalog.unlink()
        before = self.dump()
        missing = self.post('schedule.create', self.create_body('timezone-missing-baseline'))
        self.assertEqual(missing.status_code, 422, missing.json)
        self.assertEqual(missing.json['error']['code'], 'domain_failure')
        self.assertEqual(self.dump(), before)
        self.catalog.write_bytes(original_catalog)
        changed = self.post('schedule.create', self.create_body('timezone-changed-zone', zone='America/Winnipeg'))
        self.assertEqual(changed.status_code, 422, changed.json)
        self.assertEqual(changed.json['error']['code'], 'domain_failure')
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
