"""Bounded binding repair materializes against the selected resulting target."""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from spine.commands import CommandContext, handle
from spine.core import SpineValidationError
from spine.core.schedule import system_timezone_database_version
from tests import test_relative_temporal_bindings_command as helpers


class BindingSuccessorMaterializationTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture; do not inherit or re-export its TestCase.
        self.h = helpers.RelativeTemporalBindingCommandTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.db = self.h.connection
        self.context = self.h.context
        request = self.h._event_request()
        request['command_id'] = 'materialization-source'
        request['scheduled_time'].update(timezone='UTC', local_time='14:00:00')
        self.h.event = self.ok('schedule.create', request)

    def ok(self, command, request, *, context=None):
        response = handle(command, request, context or self.context)
        self.assertTrue(response['ok'], response)
        return response

    @staticmethod
    def bounded(range_=None):
        return {'mode': 'bounded', 'evaluated_at_utc': '2026-08-17T12:00:00Z',
                'range': range_ or {'kind': 'item_relative', 'start_offset_seconds': '-3600',
                                    'end_offset_seconds': '1'}, 'limit': '10'}

    def create(self, *, mode='follow_source', materialize=True, behavior='detach_at_last_value', key='follow'):
        request = self.h._related_request(mode, with_reminder=True)
        request['command_id'] = 'materialization-' + key
        if mode == 'follow_source':
            request['temporal_binding']['source_terminal_behavior'] = behavior
        request['materialization'] = self.bounded() if materialize else {'mode': 'none'}
        return self.ok('schedule.related_task.create', request)

    def move(self, date, *, zone='UTC', key='move-source'):
        request = {'contract_version': 'spine.schedule-update.v2', 'command_id': key,
                   'actor_subject_id': 'owner', 'item_id': self.h.event['item_id'],
                   'target_version': self.h.event['current_version'], 'updated_at_utc': '2026-08-17T12:00:00Z',
                   'patch': {'scheduled_time': {'time_basis': 'local_instant', 'local_date': date,
                             'local_time': '14:00:00', 'timezone': zone,
                             'timezone_database_version': {'kind': 'explicit', 'version': system_timezone_database_version()}}},
                   'materialization': {'mode': 'none'}}
        self.h.event = self.ok('schedule.update', request)

    def request(self, created, *, materialization=None, key='reconcile', operator=None):
        binding = self.h._binding_for(created['task']['item_id'])
        request = {'contract_version': 'spine.schedule-binding-reconcile.v1', 'command_id': key,
                   'actor_subject_id': 'owner', 'reconciled_at_utc': '2026-08-17T12:01:00Z',
                   **binding['reconcile_inputs'], 'materialization': materialization or self.bounded()}
        if operator is not None:
            request['operator_resolution'] = operator
        return request

    def shown(self, created):
        return self.ok('schedule.show', {'item_id': created['task']['item_id']})

    def dump(self):
        return '\n'.join(self.db.iterdump())

    def assert_relative_move(self, date):
        created = self.create()
        prior_work = created['work_instance_ids']
        self.assertEqual(len(prior_work), 1)
        self.move(date)
        repaired = self.ok('schedule.binding.reconcile', self.request(created))
        self.assertEqual(repaired['resolution_outcome'], 'target_rescheduled')
        self.assertEqual(repaired['target_item_version'], '2')
        self.assertEqual(repaired['materialization']['range_start_utc'], date + 'T12:00:00Z')
        self.assertEqual(repaired['materialization']['range_end_utc'], date + 'T13:00:01Z')
        work = repaired['work_reconciliation']
        self.assertEqual(work['cancelled_work_instance_ids'], prior_work)
        self.assertEqual(len(work['created_work_instance_ids']), 1)
        shown = self.shown(created)
        self.assertEqual(shown['scheduled_times'][0]['utc_instant'], date + 'T13:00:00Z')
        replacement = [row for row in shown['work_instances'] if row['work_instance_id'] in work['created_work_instance_ids']]
        self.assertEqual([row['eligible_at_utc'] for row in replacement], [date + 'T12:30:00Z'])
        self.assertEqual(shown['side_effect_attempts'], [])

    def test_move_later_uses_successor_due_for_item_relative_window(self):
        self.assert_relative_move('2026-08-23')

    def test_move_earlier_uses_successor_due_for_item_relative_window(self):
        self.assert_relative_move('2026-08-21')

    def test_explicit_utc_local_range_is_not_shifted_with_due_time(self):
        created = self.create()
        self.move('2026-08-23')
        materialization = self.bounded({'kind': 'local_range', 'range_start_local': '2026-08-22T12:00:00',
                                       'range_end_local': '2026-08-22T14:00:00'})
        repaired = self.ok('schedule.binding.reconcile', self.request(created, materialization=materialization))
        self.assertEqual(repaired['materialization']['range_start_utc'], '2026-08-22T12:00:00Z')
        self.assertEqual(repaired['materialization']['range_end_utc'], '2026-08-22T14:00:00Z')
        self.assertEqual(repaired['materialization']['state'], 'completed_zero_selected')
        self.assertEqual(repaired['work_reconciliation']['created_work_instance_ids'], [])
        self.assertEqual(repaired['work_reconciliation']['cancelled_work_instance_ids'], created['work_instance_ids'])
        self.assertEqual(self.shown(created)['scheduled_times'][0]['utc_instant'], '2026-08-23T13:00:00Z')

    def test_local_range_uses_successor_timezone_without_changing_explicit_boundaries(self):
        created = self.create()
        self.move('2026-08-23', zone='America/Los_Angeles')
        materialization = self.bounded({'kind': 'local_range', 'range_start_local': '2026-08-23T12:00:00',
                                       'range_end_local': '2026-08-23T14:00:00'})
        repaired = self.ok('schedule.binding.reconcile', self.request(created, materialization=materialization))
        self.assertEqual(repaired['materialization']['range_start_utc'], '2026-08-23T19:00:00Z')
        self.assertEqual(repaired['materialization']['range_end_utc'], '2026-08-23T21:00:00Z')
        shown = self.shown(created)
        self.assertEqual(shown['scheduled_times'][0]['timezone'], 'America/Los_Angeles')
        self.assertEqual(shown['scheduled_times'][0]['utc_instant'], '2026-08-23T20:00:00Z')
        ids = repaired['work_reconciliation']['created_work_instance_ids']
        self.assertEqual([row['eligible_at_utc'] for row in shown['work_instances'] if row['work_instance_id'] in ids],
                         ['2026-08-23T19:30:00Z'])

    def test_current_binding_repairs_missing_work_then_returns_noop_without_version(self):
        created = self.create(materialize=False)
        original_revision = created['temporal_binding']['latest_revision']['temporal_binding_revision_id']
        repaired = self.ok('schedule.binding.reconcile', self.request(created))
        self.assertEqual(repaired['resolution_outcome'], 'source_unchanged')
        self.assertFalse(repaired['truth_changed'])
        self.assertTrue(repaired['work_changed'])
        self.assertEqual(repaired['target_item_version'], '1')
        self.assertEqual(repaired['current_temporal_binding_revision_id'], original_revision)
        self.assertEqual(repaired['materialization']['range_start_utc'], '2026-08-22T12:00:00Z')
        repeated = self.ok('schedule.binding.reconcile', self.request(created, key='current-again'))
        self.assertEqual(repeated['resolution_outcome'], 'source_unchanged')
        self.assertFalse(repeated['truth_changed'])
        self.assertFalse(repeated['work_changed'])
        self.assertEqual(repeated['target_item_version'], '1')
        self.assertEqual(repeated['work_reconciliation']['created_work_instance_ids'], [])

    def test_source_only_change_refreshes_evidence_and_materializes_at_same_due(self):
        created = self.create(materialize=False)
        self.h.event = self.ok('schedule.update', {
            'contract_version': 'spine.schedule-update.v2', 'command_id': 'source-title-change',
            'actor_subject_id': 'owner', 'item_id': self.h.event['item_id'], 'target_version': '1',
            'updated_at_utc': '2026-08-17T12:00:00Z', 'patch': {'item': {'title': 'Updated source title'}},
            'materialization': {'mode': 'none'}})
        repaired = self.ok('schedule.binding.reconcile', self.request(created))
        self.assertEqual(repaired['resolution_outcome'], 'source_refreshed')
        self.assertTrue(repaired['truth_changed'])
        self.assertEqual(repaired['target_item_version'], '1')
        self.assertEqual(repaired['materialization']['range_start_utc'], '2026-08-22T12:00:00Z')
        self.assertEqual(len(repaired['work_reconciliation']['created_work_instance_ids']), 1)

    def test_dry_run_computes_replacement_window_without_persisting_any_rows(self):
        created = self.create()
        self.move('2026-08-23')
        request = self.request(created)
        before = self.dump()
        preview = self.ok('schedule.binding.reconcile', request, context=CommandContext(ledger=self.db, dry_run=True))
        self.assertTrue(preview['dry_run'])
        self.assertEqual(preview['materialization']['range_start_utc'], '2026-08-23T12:00:00Z')
        self.assertEqual(len(preview['work_reconciliation']['created_work_instance_ids']), 1)
        self.assertEqual(self.dump(), before)
        committed = self.ok('schedule.binding.reconcile', request)
        self.assertEqual(committed['work_reconciliation'], preview['work_reconciliation'])
        self.assertEqual(committed['materialization'], preview['materialization'])

    def test_replay_returns_original_window_after_another_source_move_without_writes(self):
        created = self.create()
        self.move('2026-08-23')
        request = self.request(created)
        repaired = self.ok('schedule.binding.reconcile', request)
        self.move('2026-08-24', key='second-source-move')
        before = self.dump()
        replay = self.ok('schedule.binding.reconcile', request)
        self.assertEqual(replay['command_receipt_id'], repaired['command_receipt_id'])
        self.assertEqual(replay['materialization'], repaired['materialization'])
        self.assertEqual(replay['work_reconciliation'], repaired['work_reconciliation'])
        self.assertEqual(self.dump(), before)

    def test_receipt_failure_rolls_back_successor_anchor_policies_work_and_binding(self):
        created = self.create()
        self.move('2026-08-23')
        request = self.request(created)
        before = self.dump()
        with patch('spine.commands.core.insert_command_receipt',
                   side_effect=SpineValidationError('runtime_failure:injected_receipt', 'injected receipt failure')):
            failed = handle('schedule.binding.reconcile', request, self.context)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['error']['code'], 'runtime_failure')
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.ok('schedule.binding.reconcile', request)['resolution_outcome'], 'target_rescheduled')

    def test_explicit_detach_preserves_current_target_despite_resolved_successor(self):
        created = self.create()
        self.move('2026-08-23', zone='America/Los_Angeles')
        detached = self.ok('schedule.binding.reconcile', self.request(
            created, materialization={'mode': 'none'}, operator='detach_at_current_target'))
        self.assertEqual(detached['resolution_outcome'], 'binding_detached')
        self.assertEqual(detached['target_item_version'], '1')
        self.assertEqual(detached['binding_state_after'], 'retired')
        self.assertEqual(detached['work_reconciliation']['created_work_instance_ids'], [])
        shown = self.shown(created)
        self.assertEqual(shown['scheduled_times'][0]['utc_instant'], '2026-08-22T13:00:00Z')
        self.assertEqual(shown['side_effect_attempts'], [])

    def test_snapshot_reconcile_remains_rejected_without_mutating_work(self):
        created = self.create(mode='snapshot')
        self.move('2026-08-23')
        request = self.request(created, materialization={'mode': 'none'})
        before = self.dump()
        refused = handle('schedule.binding.reconcile', request, self.context)
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error']['code'], 'invalid_state_transition')
        self.assertEqual(refused['error']['field'], 'temporal_binding_id')
        self.assertEqual(self.dump(), before)

    def test_source_terminal_behaviors_preserve_their_none_materialization_outcomes(self):
        created = {behavior: self.create(behavior=behavior, key=behavior) for behavior in
                   ('cancel_target', 'detach_at_last_value', 'require_decision')}
        self.ok('schedule.cancel', {
            'contract_version': 'spine.schedule-cancel.v1', 'command_id': 'cancel-source',
            'actor_subject_id': 'owner', 'item_id': self.h.event['item_id'], 'target_version': '1',
            'cancelled_at_utc': '2026-08-17T12:00:00Z', 'reason_code': 'source_cancelled'})
        outcomes = {'cancel_target': 'target_cancelled', 'detach_at_last_value': 'binding_detached',
                    'require_decision': 'decision_required'}
        for behavior, target in created.items():
            with self.subTest(behavior=behavior):
                response = self.ok('schedule.binding.reconcile', self.request(
                    target, materialization={'mode': 'none'}, key='terminal-' + behavior))
                self.assertEqual(response['resolution_outcome'], outcomes[behavior])
                self.assertEqual(response['materialization']['state'], 'not_requested')
                self.assertEqual(response['work_reconciliation']['created_work_instance_ids'], [])
                self.assertEqual(self.shown(target)['side_effect_attempts'], [])

    def test_terminal_target_is_retired_without_replacement_materialization(self):
        created = self.create()
        self.ok('task.complete', {'command_id': 'complete-bound-target', 'actor_subject_id': 'owner',
                                 'item_id': created['task']['item_id'], 'target_version': '1',
                                 'completed_at_utc': '2026-08-17T12:00:00Z'})
        response = self.ok('schedule.binding.reconcile', self.request(created, materialization={'mode': 'none'}))
        self.assertEqual(response['resolution_outcome'], 'target_terminal_retired')
        self.assertEqual(response['target_item_version'], '2')
        self.assertEqual(response['materialization']['state'], 'not_requested')
        self.assertEqual(response['work_reconciliation']['created_work_instance_ids'], [])

    def test_excluded_selected_occurrence_requires_decision_without_rescheduling(self):
        request = self.h._event_request()
        request['command_id'] = 'selected-window-source'
        request['scheduled_time'].update(timezone='UTC', local_time='14:00:00', recurrence={'rules': [{
            'frequency': 'DAILY', 'interval': '1', 'seed': '2026-08-22T14:00:00',
            'start_bound': '2026-08-22T14:00:00', 'end_condition': {'kind': 'count', 'count': '3'}}]})
        self.h.event = self.ok('schedule.create', request)
        recurring = self.h.event
        occurrence = self.ok('item.occurrences', {'item_id': recurring['item_id'],
            'range_start': '2026-08-22T00:00:00', 'range_end': '2026-08-23T00:00:00', 'limit': '10'})['occurrences'][0]
        encoded = occurrence['occurrence_key'].split('.', 1)[0]
        selector = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))['target_occurrence_selector']
        related = self.h._related_request('follow_source', with_reminder=True)
        related['command_id'] = 'selected-window-target'
        related['source'] = {'item_id': recurring['item_id'], 'target_version': '1', 'anchor_role': 'event_start',
                             'scope': 'selected_occurrence',
                             'source_recurrence_revision_id': recurring['recurrence']['recurrence_revision_id'],
                             'target_occurrence_key': occurrence['occurrence_key'], 'target_occurrence_selector': selector}
        created = self.ok('schedule.related_task.create', related)
        removed = self.ok('recurrence.instance.remove', {
            'command_id': 'exclude-bound-occurrence', 'actor_subject_id': 'owner', 'item_id': recurring['item_id'],
            'target_version': '1', 'recurrence_set_id': recurring['recurrence']['recurrence_set_id'],
            'recurrence_revision_id': recurring['recurrence']['recurrence_revision_id'],
            'removed_at_utc': '2026-08-17T12:00:00Z', 'target_occurrence_key': occurrence['occurrence_key'],
            'reason_code': 'skip_bound_occurrence'})
        request = self.request(created, materialization={'mode': 'none'})
        request['source_recurrence_revision_id'] = removed['recurrence_revision_id']
        self.assertEqual(request['expected_binding_state'], 'source_unresolved')
        response = self.ok('schedule.binding.reconcile', request)
        self.assertEqual(response['resolution_outcome'], 'decision_required')
        self.assertEqual(response['target_item_version'], '1')
        self.assertEqual(response['materialization']['state'], 'not_requested')
        self.assertEqual(response['work_reconciliation']['created_work_instance_ids'], [])
        self.assertEqual(self.shown(created)['scheduled_times'][0]['utc_instant'], '2026-08-22T13:00:00Z')


if __name__ == '__main__':
    unittest.main()
