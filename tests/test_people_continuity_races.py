"""Slice 3: real freshness/transaction boundaries, disposable ledgers only."""

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spine.commands import CommandContext, handle, people_candidate
from spine.core.errors import SpineValidationError
from spine.ledger import connect, get_notification_rendering, get_work_instance
from spine.ledger.work import assert_work_instance_not_stale
from spine.services.work import start_work
from tests import test_relative_temporal_bindings_command as relative
from tests import test_rendering_delivery as delivery
from tests.facet_storage_support import NOW


class PeopleContinuityRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        delivery.RenderingDeliveryTests.setUpClass()

    def setUp(self):
        self.fixture = delivery.RenderingDeliveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.counter = 0

    def version(self, item):
        return str(self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?', (item,)).fetchone()[0])

    def people_request(self, item, subjects, *, role='participants', version=None, command=None):
        self.counter += 1
        return {'contract_version': people_candidate.CONTRACT, 'command_id': command or f'race-people-{self.counter}',
                'actor_subject_id': 'owner', 'item_id': item, 'target_version': version or self.version(item),
                'updated_at_utc': NOW, 'people': {role: subjects}}

    def people(self, item, subjects, **kw):
        response = people_candidate.execute('item.people.update', self.people_request(item, subjects, **kw),
                                            CommandContext(ledger=self.db))
        self.assertTrue(response['ok'], response)
        return response

    def rows(self, table):
        return [tuple(r) for r in self.db.execute(f'SELECT * FROM {table} ORDER BY 1')]

    def test_prepared_body_is_fenced_after_people_edit_then_fresh_body_is_safe(self):
        event, _ = self.fixture.event()
        work = self.fixture.work(event, start=True)
        prepared = self.fixture.message(work)
        self.people(event['item_id'], ['owner'])
        state = self.rows('work_instances'), self.rows('side_effect_attempts'), self.rows('notification_renderings')
        with self.assertRaises(SpineValidationError) as refused:
            self.fixture.prepare(prepared)
        self.assertEqual(refused.exception.code, 'notification_rendering_persistence_conflict')
        self.assertEqual(state, (self.rows('work_instances'), self.rows('side_effect_attempts'),
                                 self.rows('notification_renderings')))
        current = self.fixture.message(work)
        self.assertEqual(current.body_text, prepared.body_text)
        self.assertNotEqual(current.notification_rendering.rendering_input_hash,
                            prepared.notification_rendering.rendering_input_hash)
        gate = self.fixture.prepare(current)
        self.assertTrue(gate.may_start_external_write)
        self.assertFalse(self.fixture.prepare(current).may_start_external_write)

    def test_started_rendering_replay_stays_exact_after_several_people_edges(self):
        event, _ = self.fixture.event()
        work = self.fixture.work(event, start=True)
        message = self.fixture.message(work)
        self.fixture.prepare(message)
        immutable = self.rows('side_effect_attempts'), self.rows('notification_renderings')
        for subjects in (['owner'], [], ['owner']):
            self.people(event['item_id'], subjects)
        self.assertFalse(self.fixture.prepare(message).may_start_external_write)
        self.assertEqual(immutable, (self.rows('side_effect_attempts'), self.rows('notification_renderings')))
        self.assertEqual(get_notification_rendering(self.db, attempt_id=message.attempt_id)['body_text'], message.body_text)

    def test_attempt_transaction_excludes_a_competing_people_writer(self):
        from spine.services import attempts

        event, _ = self.fixture.event()
        work = self.fixture.work(event, start=True)
        with tempfile.TemporaryDirectory() as directory:
            disk = connect(Path(directory) / 'ledger.sqlite')
            self.db.backup(disk)
            disk.enable_renderings()
            second = connect(Path(directory) / 'ledger.sqlite', busy_timeout_ms=1)
            original_db = self.db
            self.db = self.fixture.db = disk
            try:
                request = self.people_request(event['item_id'], ['owner'], command='competing-people')
                outcomes = []
                writer = attempts.insert_notification_rendering

                def interleave(*args, **kwargs):
                    outcomes.append(people_candidate.execute('item.people.update', request, CommandContext(ledger=second)))
                    writer(*args, **kwargs)

                message = self.fixture.message(work)
                with patch.object(attempts, 'insert_notification_rendering', side_effect=interleave):
                    self.fixture.prepare(message)
                self.assertFalse(outcomes[0]['ok'], outcomes)
                self.assertEqual(outcomes[0]['error']['code'], 'environment_failure')
                self.assertEqual(self.version(event['item_id']), request['target_version'])
                success = people_candidate.execute('item.people.update', request, CommandContext(ledger=second))
                self.assertTrue(success['ok'], success)
                self.assertFalse(self.fixture.prepare(message).may_start_external_write)
                self.assertEqual(len(self.rows('side_effect_attempts')), 1)
                self.assertEqual(len(self.rows('notification_renderings')), 1)
            finally:
                self.db = self.fixture.db = original_db
                second.close()
                disk.close()

    def test_competing_role_writers_commit_once_and_stale_retry_has_no_residue(self):
        from spine.ledger import people_authoring

        event, _ = self.fixture.event()
        item = event['item_id']
        with tempfile.TemporaryDirectory() as directory:
            disk = connect(Path(directory) / 'ledger.sqlite')
            self.db.backup(disk)
            disk.enable_renderings()
            second = connect(Path(directory) / 'ledger.sqlite', busy_timeout_ms=1)
            original_db = self.db
            self.db = disk
            try:
                first = self.people_request(item, ['owner'], command='winner')
                loser = self.people_request(item, ['owner'], command='loser')
                verify = people_authoring.verify_role_edge
                outcomes = []

                def interleave(*args, **kwargs):
                    outcomes.append(people_candidate.execute('item.people.update', loser, CommandContext(ledger=second)))
                    return verify(*args, **kwargs)

                with patch.object(people_authoring, 'verify_role_edge', side_effect=interleave):
                    result = people_candidate.execute('item.people.update', first, CommandContext(ledger=disk))
                self.assertTrue(result['ok'], result)
                self.assertTrue(outcomes)
                self.assertTrue(all(not r['ok'] and r['error']['code'] == 'environment_failure' for r in outcomes), outcomes)
                before = '\n'.join(disk.iterdump())
                refused = people_candidate.execute('item.people.update', loser, CommandContext(ledger=second))
                self.assertEqual(refused['error']['code'], 'stale_version')
                self.assertEqual('\n'.join(disk.iterdump()), before)
                self.assertEqual(int(self.version(item)), int(first['target_version']) + 1)
                receipts = disk.execute("SELECT COUNT(*) FROM command_receipts WHERE command_id IN ('winner','loser')").fetchone()[0]
                self.assertEqual(receipts, 1)
            finally:
                self.db = original_db
                second.close()
                disk.close()

    def test_recurring_people_and_facet_edges_preserve_exact_provenance(self):
        event, _ = self.fixture.event(recurrence=True)
        work, provenance = self.rows('work_instances'), self.rows('occurrence_provenance')
        self.assertTrue(provenance)
        for subjects in (['owner'], [], ['owner']):
            self.people(event['item_id'], subjects)
            self.fixture.facet(event, {'flight': 'AC-' + str(self.counter)})
        self.assertEqual(self.rows('work_instances'), work)
        self.assertEqual(self.rows('occurrence_provenance'), provenance)
        for row in self.db.execute('SELECT work_instance_id FROM work_instances'):
            assert_work_instance_not_stale(self.db, row[0])
        started = self.fixture.work(event, start=True)
        message = self.fixture.message(started)
        self.fixture.prepare(message)
        self.assertEqual(message.notification_rendering.base.source_input['occurrence_provenance_id'],
                         started['occurrence_provenance_id'])

    def test_actual_recurrence_change_is_not_a_role_only_edge(self):
        event, _ = self.fixture.event(recurrence=True)
        item, work = event['item_id'], self.fixture.work(event, start=True)
        self.people(item, ['owner'])
        prepared = self.fixture.message(work)
        schedule = self.fixture.fixture.scheduled_time('2026-08-14', '10:00:00')
        recurrence = copy.deepcopy(self.fixture.fixture.task_request('unused')['scheduled_time']['recurrence'])
        rule = recurrence['rules'][0]
        rule['seed'] = rule['start_bound'] = '2026-08-14T10:00:00'
        rule['interval'] = '1'
        response = people_candidate.execute('schedule.update', {
            'contract_version': 'spine.schedule-update.v4', 'command_id': 'actual-recurrence-change',
            'actor_subject_id': 'owner', 'item_id': item, 'target_version': self.version(item),
            'updated_at_utc': NOW, 'patch': {'people': {'participants': []}, 'scheduled_time': schedule,
                                          'recurrence': {'mode': 'replace', **recurrence}},
            'materialization': {'mode': 'none'}}, CommandContext(ledger=self.db))
        self.assertTrue(response['ok'], response)
        self.assertIn('people', response['changed_dimensions'])
        self.assertIn('recurrence', response['changed_dimensions'])
        with self.assertRaises(SpineValidationError) as stale:
            assert_work_instance_not_stale(self.db, work['work_instance_id'])
        self.assertEqual(stale.exception.code, 'stale_work_instance')
        with self.assertRaises(SpineValidationError):
            self.fixture.prepare(prepared)
        self.assertEqual(self.rows('side_effect_attempts'), [])
        self.assertEqual(self.rows('notification_renderings'), [])

    def related(self, event, mode='follow_source'):
        request = relative.RelativeTemporalBindingCommandTests._related_request(
            SimpleNamespace(event=event), mode, with_reminder=True)
        request['source']['target_version'] = self.version(event['item_id'])
        request['created_at_utc'] = request['materialization']['evaluated_at_utc'] = '2026-08-13T12:00:00Z'
        result = handle('schedule.related_task.create', request, CommandContext(ledger=self.db))
        self.assertTrue(result['ok'], result)
        return result

    def test_follow_source_role_edit_blocks_prepared_attempt_until_explicit_refresh(self):
        event, _ = self.fixture.event(selected=False, value=None)
        related = self.related(event)
        item, key = related['task']['item_id'], related['work_instance_ids'][0]
        changed = self.people(item, [], role='assignees')
        self.assertTrue(changed['truth_changed'])
        row = get_work_instance(self.db, key)
        start_work(self.db, work_instance_id=key, started_at_utc=row['eligible_at_utc'])
        row = get_work_instance(self.db, key)
        message = self.fixture.message(row)
        self.people(event['item_id'], ['owner'])
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            self.fixture.prepare(message)
        self.assertEqual(self.rows('side_effect_attempts'), [])
        # Editing the target's people must not silently refresh its source pin.
        before = self.rows('work_instances'), self.rows('relative_temporal_binding_revisions')
        self.people(item, ['owner'], role='assignees')
        self.assertEqual(before, (self.rows('work_instances'), self.rows('relative_temporal_binding_revisions')))
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            assert_work_instance_not_stale(self.db, key)
        roles = [tuple(r) for r in self.db.execute('SELECT * FROM item_subject_roles WHERE item_id=? ORDER BY 1', (item,))]
        listing = handle('schedule.binding.list', {'contract_version': 'spine.schedule-binding-list.v1',
            'target_item_id': item, 'binding_mode': 'follow_source', 'limit': '10'}, CommandContext(ledger=self.db))
        self.assertTrue(listing['ok'], listing)
        binding = listing['bindings'][0]
        self.assertEqual(binding['binding_state'], 'stale')
        refreshed = handle('schedule.binding.reconcile', {'contract_version': 'spine.schedule-binding-reconcile.v1',
            'command_id': 'refresh-after-source-people', 'actor_subject_id': 'owner', 'reconciled_at_utc': NOW,
            **binding['reconcile_inputs'], 'materialization': {'mode': 'none'}}, CommandContext(ledger=self.db))
        self.assertTrue(refreshed['ok'], refreshed)
        self.assertEqual(refreshed['resolution_outcome'], 'source_refreshed')
        self.assertEqual(refreshed['target_item_version'], self.version(item))
        self.assertEqual(roles, [tuple(r) for r in self.db.execute('SELECT * FROM item_subject_roles WHERE item_id=? ORDER BY 1', (item,))])
        assert_work_instance_not_stale(self.db, key)
        current = self.fixture.message(row)
        self.fixture.prepare(current)

    def test_selected_occurrence_source_people_edit_requires_explicit_binding_refresh(self):
        event, _ = self.fixture.event(recurrence=True, selected=False, value=None)
        occurrences = handle('item.occurrences', {'item_id': event['item_id'], 'range_start': '2026-08-14T00:00:00',
            'range_end': '2026-08-15T00:00:00', 'limit': '10'}, CommandContext(ledger=self.db))
        self.assertTrue(occurrences['ok'], occurrences)
        occurrence = occurrences['occurrences'][0]
        encoded = occurrence['occurrence_key'].split('.', 1)[0]
        selector = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))['target_occurrence_selector']
        request = relative.RelativeTemporalBindingCommandTests._related_request(
            SimpleNamespace(event=event), 'follow_source', with_reminder=True)
        request['source'] = {'item_id': event['item_id'], 'target_version': self.version(event['item_id']),
            'anchor_role': 'event_start', 'scope': 'selected_occurrence', 'target_occurrence_key': occurrence['occurrence_key'],
            'target_occurrence_selector': selector, 'source_recurrence_revision_id': event['recurrence']['recurrence_revision_id']}
        request['created_at_utc'] = request['materialization']['evaluated_at_utc'] = '2026-08-13T12:00:00Z'
        related = handle('schedule.related_task.create', request, CommandContext(ledger=self.db))
        self.assertTrue(related['ok'], related)
        item, key = related['task']['item_id'], related['work_instance_ids'][0]
        original = related['temporal_binding']['latest_revision']
        before = self.rows('work_instances'), self.rows('occurrence_provenance')
        self.people(item, [], role='assignees')
        self.people(event['item_id'], ['owner'])
        self.assertEqual(before, (self.rows('work_instances'), self.rows('occurrence_provenance')))
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            assert_work_instance_not_stale(self.db, key)
        listing = handle('schedule.binding.list', {'contract_version': 'spine.schedule-binding-list.v1',
            'target_item_id': item, 'limit': '10'}, CommandContext(ledger=self.db))
        self.assertTrue(listing['ok'], listing)
        binding = listing['bindings'][0]
        self.assertEqual(binding['binding_state'], 'stale')
        before_version = self.version(item)
        result = handle('schedule.binding.reconcile', {'contract_version': 'spine.schedule-binding-reconcile.v1',
            'command_id': 'refresh-occurrence-source-people', 'actor_subject_id': 'owner', 'reconciled_at_utc': NOW,
            **binding['reconcile_inputs'], 'materialization': {'mode': 'none'}}, CommandContext(ledger=self.db))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['resolution_outcome'], 'source_refreshed')
        self.assertEqual(self.version(item), before_version)
        current = self.db.execute('SELECT * FROM relative_temporal_binding_revisions WHERE temporal_binding_id=? '
            'ORDER BY revision_index DESC LIMIT 1', (original['temporal_binding_id'],)).fetchone()
        self.assertEqual(current['source_occurrence_key'], original['source_occurrence_key'])
        self.assertEqual(current['source_target_version'], int(self.version(event['item_id'])))
        assert_work_instance_not_stale(self.db, key)

    def test_snapshot_bound_task_does_not_follow_source_people_change(self):
        event, _ = self.fixture.event(selected=False, value=None)
        related = self.related(event, 'snapshot')
        key = related['work_instance_ids'][0]
        before = self.rows('work_instances'), self.rows('relative_temporal_binding_revisions')
        self.people(event['item_id'], ['owner'])
        self.assertEqual(before, (self.rows('work_instances'), self.rows('relative_temporal_binding_revisions')))
        assert_work_instance_not_stale(self.db, key)


if __name__ == '__main__':
    unittest.main()
