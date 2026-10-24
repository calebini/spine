"""PR-09/10: private people edits preserve real work/attempt state, not copies.

Tickerd selects an immutable WorkItem and Spine persists ``in_progress``; neither
owns a separate persisted lease record. The selected/unstarted checks below use
those actual boundaries rather than inventing a lease table for this contract.
All ledgers are disposable. A deterministic no-send processor exercises the real
Tickerd boundary; no sender or external side-effect adapter runs.
"""

import copy
import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from spine.adapters import SpineTickerdWorkAdapter, WorkProcessingOutcome
from spine.commands import handle, people_candidate
from spine.core.errors import SpineValidationError
from spine.core.notifications import normalize_notification_policy
from spine.ledger import get_notification_rendering, get_work_instance
from spine.ledger.notifications import (
    NotificationPolicyResolver,
    insert_notification_schedule_policy,
    load_current_notification_policies,
)
from spine.ledger.rendering_definitions import load_presentation, verify_deep
from spine.ledger.work import assert_work_instance_not_stale
from spine.services.attempts import record_attempt_failure, record_attempt_success
from spine.services.scheduling import materialize_notification_horizon
from spine.services.work import cancel_work, fail_work, list_eligible_work, retry_work, start_work, succeed_work
from tests import test_rendering_delivery as rendering
from tests import test_tickerd_adapter as tickerd
from tests.facet_storage_support import NOW


class PeopleWorkStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rendering.RenderingDeliveryTests.setUpClass()

    def setUp(self):
        self.fixture = rendering.RenderingDeliveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.context = self.fixture.context
        self.event, self.grant = self.fixture.event()
        self.item = self.event['item_id']
        self.work = self.fixture.work(self.event)
        self.key = self.work['work_instance_id']
        self.at = self.work['eligible_at_utc']
        self.number = 0

    def snapshot(self):
        return {
            table: [tuple(row) for row in self.db.execute(f'SELECT * FROM {table} ORDER BY 1')]
            for table in ('work_instances', 'side_effect_attempts', 'notification_renderings')
        }

    def roles(self, subjects, *, scheduling=False, ok=True):
        self.number += 1
        current = self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?', (self.item,)).fetchone()[0]
        request = {
            'contract_version': 'spine.schedule-update.v4' if scheduling else people_candidate.CONTRACT,
            'command_id': f'work-state-people-{self.number}', 'actor_subject_id': 'owner',
            'item_id': self.item, 'target_version': str(current), 'updated_at_utc': NOW,
        }
        if scheduling:
            request.update(patch={'people': {'participants': subjects}}, materialization={'mode': 'none'})
        else:
            request['people'] = {'participants': subjects}
        result = people_candidate.execute('schedule.update' if scheduling else 'item.people.update', request, self.context)
        self.assertEqual(result['ok'], ok, result)
        return result

    def repeated_roles(self):
        for index, subjects in enumerate((['owner'], [], ['owner'])):
            result = self.roles(subjects, scheduling=index == 1)
            self.assertTrue(result['changed'] if 'changed' in result else result['truth_changed'])

    def resolver(self):
        resolver = NotificationPolicyResolver(self.db, load_current_notification_policies(self.db, item_id=self.item))
        for row in self.db.execute('SELECT * FROM work_instances WHERE item_id=?', (self.item,)):
            self.assertIsNotNone(resolver.resolve(row['notification_policy_id']))
        return resolver

    def assert_retained(self, previous):
        self.assertEqual(self.snapshot(), previous)
        assert_work_instance_not_stale(self.db, self.key)
        self.resolver()
        self.assertEqual(self.snapshot(), previous)

    def test_eligible_multiple_role_edges_keep_every_work_field_and_do_not_repair(self):
        previous = self.snapshot()
        self.repeated_roles()
        self.assert_retained(previous)
        self.assertEqual(set(self.resolver()._verified_edges.values()), {'people', 'facets', 'presentations'})
        before = '\n'.join(self.db.iterdump())
        cycle = materialize_notification_horizon(self.db, evaluated_at_utc=self.at, horizon_seconds=3600, max_items=100)
        self.assertEqual(cycle.failures, ())
        self.assertEqual(cycle.items_repaired, 0)
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_selected_tickerd_item_retains_original_payload_before_processing(self):
        at = datetime.fromisoformat(self.at.replace('Z', '+00:00'))
        envelope = replace(tickerd.cycle_envelope(), actual_start_ts=at, scheduled_tick_ts=at)
        processed = []

        def no_send_processor(db, row, cycle):
            self.assertIs(db, self.db)
            self.assertIs(cycle, envelope)
            persisted = get_work_instance(db, row['work_instance_id'])
            self.assertEqual(dict(row), persisted)
            self.assertEqual((persisted['status'], persisted['attempt_count']), ('in_progress', 1))
            self.assertEqual(row['item_version'], selected.payload['item_version'])
            self.assertGreater(int(self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?',
                (self.item,)).fetchone()[0]), row['item_version'])
            assert_work_instance_not_stale(db, row['work_instance_id'])
            processed.append(dict(row))
            # This processor performs no external effect. Processing permission
            # alone must not fabricate a side-effect attempt or rendering row.
            return WorkProcessingOutcome.succeeded('no_send_test')

        adapter = SpineTickerdWorkAdapter(self.db, runtime_mode='active', processor=no_send_processor)
        selected = adapter.list_work_items(envelope, limit=1)[0]
        previous, payload = self.snapshot(), copy.deepcopy(selected.payload)
        self.repeated_roles()
        self.assert_retained(previous)
        self.assertEqual(selected.item_id, self.key)
        self.assertEqual(selected.payload, payload)
        fresh = adapter.list_work_items(envelope, limit=1)[0]
        self.assertEqual(fresh.item_id, selected.item_id)
        self.assertEqual(fresh.payload, payload)
        outcome = adapter.process_work_item(selected, envelope, side_effects_allowed=True)
        self.assertEqual(outcome.status.value, 'processed')
        self.assertEqual(len(processed), 1)
        completed = get_work_instance(self.db, self.key)
        self.assertEqual((completed['status'], completed['attempt_count']), ('succeeded', 1))
        self.assertEqual(completed['item_version'], selected.payload['item_version'])
        self.assertEqual(selected.payload, payload)
        self.assertEqual(self.rows_for_item('side_effect_attempts'), [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_renderings').fetchone()[0], 0)

    def rows_for_item(self, table):
        return [tuple(row) for row in self.db.execute(f'SELECT * FROM {table} WHERE work_instance_id=? ORDER BY 1', (self.key,))]

    def test_in_progress_unstarted_keeps_attempt_count_and_all_work_fields(self):
        start_work(self.db, work_instance_id=self.key, started_at_utc=self.at, reason_code='selected')
        self.assertEqual(get_work_instance(self.db, self.key)['status'], 'in_progress')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)
        previous = self.snapshot()
        self.repeated_roles()
        self.assert_retained(previous)
        self.assertEqual(get_work_instance(self.db, self.key)['attempt_count'], 1)

    def test_retry_preserves_backoff_provider_identity_and_prior_attempt_payload(self):
        start_work(self.db, work_instance_id=self.key, started_at_utc=self.at)
        first = self.fixture.message(get_work_instance(self.db, self.key))
        self.fixture.prepare(first)
        record_attempt_failure(self.db, attempt_id=first.attempt_id, completed_at_utc=self.at, reason_code='uncertain')
        retry_at = (datetime.fromisoformat(self.at.replace('Z', '+00:00')) + timedelta(seconds=300)).strftime('%Y-%m-%dT%H:%M:%SZ')
        retry_work(self.db, work_instance_id=self.key, next_attempt_at_utc=retry_at, updated_at_utc=self.at, reason_code='uncertain')
        previous = self.snapshot()
        self.repeated_roles()
        self.assert_retained(previous)
        row = get_work_instance(self.db, self.key)
        self.assertEqual((row['status'], row['attempt_count'], row['next_attempt_at_utc']), ('eligible', 1, retry_at))
        start_work(self.db, work_instance_id=self.key, started_at_utc=retry_at)
        second = self.fixture.message(get_work_instance(self.db, self.key), at=retry_at)
        self.assertEqual(first.provider_idempotency_key, second.provider_idempotency_key)
        self.assertEqual(first.delivery_id, second.delivery_id)
        self.assertNotEqual(first.attempt_id, second.attempt_id)
        # A later retry intentionally refreshes the countdown clock; roles do
        # not alter the selected details, route, or logical provider identity.
        self.assertTrue(first.body_text.endswith(' · Flight: AC872'))
        self.assertTrue(second.body_text.endswith(' · Flight: AC872'))
        self.assertEqual(first.target_ref, second.target_ref)
        self.assertEqual(get_notification_rendering(self.db, attempt_id=first.attempt_id)['body_text'], first.body_text)
        self.fixture.prepare(second)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 2)

    def test_started_attempt_replay_keeps_exact_evidence_clock_and_envelope(self):
        start_work(self.db, work_instance_id=self.key, started_at_utc=self.at)
        message = self.fixture.message(get_work_instance(self.db, self.key))
        self.fixture.prepare(message)
        previous = self.snapshot()
        self.repeated_roles()
        self.assert_retained(previous)
        rebuilt = self.fixture.message(get_work_instance(self.db, self.key), at='2026-08-14T12:05:00Z')
        self.assertEqual(rebuilt.request_envelope(), message.request_envelope())
        self.assertEqual(rebuilt.notification_rendering.as_view(), message.notification_rendering.as_view())
        self.assertFalse(self.fixture.prepare(rebuilt).may_start_external_write)
        self.assertEqual(self.snapshot(), previous)

    def terminal(self, status):
        start_work(self.db, work_instance_id=self.key, started_at_utc=self.at)
        message = self.fixture.message(get_work_instance(self.db, self.key))
        self.fixture.prepare(message)
        if status == 'succeeded':
            record_attempt_success(self.db, attempt_id=message.attempt_id, completed_at_utc=self.at)
            succeed_work(self.db, work_instance_id=self.key, succeeded_at_utc=self.at)
        else:
            record_attempt_failure(self.db, attempt_id=message.attempt_id, completed_at_utc=self.at, reason_code='stopped')
            if status == 'failed':
                fail_work(self.db, work_instance_id=self.key, failed_at_utc=self.at, reason_code='stopped')
            else:
                cancel_work(self.db, work_instance_id=self.key, cancelled_at_utc=self.at, reason_code='stopped')
        previous = self.snapshot()
        self.repeated_roles()
        self.assert_retained(previous)
        self.assertEqual(get_work_instance(self.db, self.key)['status'], status)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 1)
        self.assertNotIn(self.key, [row['work_instance_id'] for row in list_eligible_work(self.db, now_utc=self.at)])
        cycle = materialize_notification_horizon(self.db, evaluated_at_utc=self.at, horizon_seconds=3600, max_items=100)
        self.assertEqual(cycle.failures, ())
        self.assertEqual(cycle.items_repaired, 0)
        self.assertEqual(self.snapshot(), previous)

    def test_succeeded_is_not_reopened_or_resent(self):
        self.terminal('succeeded')

    def test_failed_is_not_reopened_or_resent(self):
        self.terminal('failed')

    def test_cancelled_is_not_reopened_or_resent(self):
        self.terminal('cancelled')

    def test_absent_work_stays_absent_after_standalone_and_composite_people_edits(self):
        request = self.fixture.fixture.event_request('no-people-work', materialize=False)
        request['contract_version'] = 'spine.schedule-create.v4'
        created = people_candidate.execute('schedule.create', request, self.context)
        self.assertTrue(created['ok'], created)
        self.item = created['item_id']
        before = self.snapshot()
        self.repeated_roles()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM work_instances WHERE item_id=?', (self.item,)).fetchone()[0], 0)

    def test_independently_stale_route_is_not_revived_and_failed_edit_rolls_back(self):
        self.roles(['owner'])
        with self.db:
            self.db.execute("UPDATE delivery_targets SET status='inactive' WHERE delivery_target_id='whatsapp-owner'")
        before = '\n'.join(self.db.iterdump())
        failed = self.roles([], ok=False)
        self.assertEqual(failed['error']['code'], 'invalid_request')
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            assert_work_instance_not_stale(self.db, self.key)
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_shared_intent_siblings_disabled_and_presentation_policies_have_exact_bijection(self):
        version = str(self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?', (self.item,)).fetchone()[0])
        seeded = []
        with self.db.atomic_command():
            for offset in ('-3600', '-1800', '-900'):
                normalized = normalize_notification_policy({
                    'authoring_contract': 'spine.notification-schedule-authoring.v1',
                    'target': {'anchor_role': 'event_start', 'application_scope': 'item'},
                    'schedule': {'kind': 'once', 'at': {'kind': 'target_offset', 'offset_basis': 'elapsed', 'offset_seconds': offset}},
                    'late_handling': {'kind': 'skip'},
                }, item_id=self.item, item_version=version,
                    command_id='sibling-state' if offset != '-900' else 'disabled-state', created_at_utc=NOW,
                    recipient_kind='subject', recipient_id='owner', channel='whatsapp', delivery_target_id='whatsapp-owner')
                insert_notification_schedule_policy(self.db, normalized=normalized)
                seeded.append(normalized.value)
        self.assertEqual(seeded[0]['notification_intent_id'], seeded[1]['notification_intent_id'])
        selection = self.fixture.edit(self.event, self.fixture.selection(self.grant), 'select-one-shared-sibling')
        selection['contract_version'] = 'spine.schedule-update.v4'
        selection['patch']['policy_presentations'][0]['notification_policy_id'] = seeded[0]['notification_policy_id']
        selected = people_candidate.execute('schedule.update', selection, self.context)
        self.assertTrue(selected['ok'], selected)
        self.assertEqual(selected['changed_dimensions'], ['policy_presentations'])
        current_policies = load_current_notification_policies(self.db, item_id=self.item)
        disable_policy = next(policy for policy in current_policies
            if policy['notification_intent_id'] == seeded[2]['notification_intent_id'])
        version = str(self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?', (self.item,)).fetchone()[0])
        disabled = handle('reminder.disable', {
            'command_id': 'disable-state', 'actor_subject_id': 'owner', 'item_id': self.item,
            'target_version': version, 'notification_intent_id': disable_policy['notification_intent_id'],
            'notification_policy_id': disable_policy['notification_policy_id'], 'disabled_at_utc': NOW,
        }, self.context)
        self.assertTrue(disabled['ok'], disabled)
        policies = load_current_notification_policies(self.db, item_id=self.item)
        self.assertEqual(len(policies), 4)
        self.assertEqual(sum(policy['status'] == 'disabled' for policy in policies), 1)
        presentations = {
            policy['notification_policy_id']: load_presentation(self.db, policy['notification_policy_id']) for policy in policies
        }
        self.assertTrue(any(value['kind'] == 'definition' for value in presentations.values()))
        shared = [policy for policy in policies if policy['notification_intent_id'] == seeded[0]['notification_intent_id']]
        self.assertEqual(len(shared), 2)
        self.assertEqual(sorted(presentations[policy['notification_policy_id']]['kind'] for policy in shared),
            ['definition', 'ordinary'])
        before = self.snapshot()
        self.repeated_roles()
        current = load_current_notification_policies(self.db, item_id=self.item)
        resolver = self.resolver()
        for policy in policies:
            descendant = resolver.resolve(policy['notification_policy_id'])
            self.assertIsNotNone(descendant)
            self.assertEqual(descendant['status'], policy['status'])
            self.assertEqual(descendant['normalized_notification_schedule_hash'], policy['normalized_notification_schedule_hash'])
            self.assertEqual(load_presentation(self.db, descendant['notification_policy_id']),
                presentations[policy['notification_policy_id']])
        descendants = {resolver.resolve(policy['notification_policy_id'])['notification_policy_id'] for policy in policies}
        self.assertEqual(len(descendants), len(current))
        self.assertEqual(self.snapshot(), before)
        verify_deep(self.db)
