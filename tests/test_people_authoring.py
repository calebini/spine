"""Disposable-ledger checks for private transactional role replacement."""

import sqlite3
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

import test_people_ledger as foundation

from spine.core.errors import SpineValidationError
from spine.ledger import ItemSubjectRoleInput
from spine.ledger.people import read_people_snapshot
from spine.ledger.people_authoring import capture_role_edge, replace_people, verify_role_edge

NOW = foundation.NOW


class PeopleAuthoringTests(unittest.TestCase):
    def setUp(self):
        foundation.PeopleLedgerTests.setUp(self)
        self.connection = self.db
        self.admit = Mock()

    task = foundation.PeopleLedgerTests.task

    def replace(self, subjects, **kwargs):
        return replace_people(self.db, item_id='task', target_version=1,
            people={'assignees': subjects}, command_id='people-change', actor_subject_id='s0',
            updated_at_utc=NOW, audit_id='people-audit', admit_additions=self.admit, **kwargs)

    def durable_state(self):
        return '\n'.join(self.db.iterdump())

    def test_changed_replacement_one_version_preserves_history_and_other_roles(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=subject, role=role, item_subject_role_id=f'row-{index}')
            for index, (subject, role) in enumerate([
                ('s1', 'assignee'), ('s2', 'owner'), ('s3', 'participant'),
                ('s4', 'watcher'), ('s5', 'recipient'),
            ])))
        old = read_people_snapshot(self.db, item_id='task')
        with self.db.atomic_command():
            result = self.replace(['s7', 's6'])
            self.assertTrue(self.db.in_transaction)
        self.assertTrue(result.changed)
        self.assertEqual(result.snapshot.current_version, 2)
        self.assertEqual([r.subject_id for r in result.snapshot.associations], ['s6', 's7'])
        self.assertEqual(read_people_snapshot(self.db, item_id='task', version=1).associations, old.associations)
        self.admit.assert_called_once_with(('s6', 's7'))
        for role in ('owner', 'participant', 'watcher', 'recipient'):
            rows = self.db.execute('SELECT subject_id,role,status FROM item_subject_roles '
                'WHERE item_id=? AND version=? AND role=?', ('task', 2, role)).fetchall()
            self.assertEqual(len(rows), 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM coordination_item_versions').fetchone()[0], 2)

    def test_noop_retains_ids_and_has_no_writes_or_admission(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee', item_subject_role_id='original'),))
        before = self.durable_state()
        with self.db.atomic_command():
            result = self.replace(['s1'])
        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertEqual(result.snapshot.associations[0].item_subject_role_id, 'original')
        self.assertEqual(self.durable_state(), before)
        self.admit.assert_not_called()

    def test_inactive_row_removal_is_change_not_noop(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee', status='inactive'),))
        with self.db.atomic_command():
            result = self.replace([])
        self.assertTrue(result.changed)
        self.assertEqual(result.snapshot.associations, ())
        self.admit.assert_not_called()

    def test_retaining_ineligible_subject_does_not_rerequire_fresh_admission(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee'),))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s1'")
        with self.db.atomic_command():
            self.replace(['s1', 's2'])
        self.admit.assert_called_once_with(('s2',))

    def test_no_outer_transaction_is_rejected_without_writes(self):
        self.task()
        before = self.durable_state()
        with self.assertRaisesRegex(RuntimeError, 'outer command'):
            self.replace(['s1'])
        self.assertEqual(self.durable_state(), before)

    def test_admission_failure_rolls_back_all_facts(self):
        self.task()
        before = self.durable_state()
        self.admit.side_effect = SpineValidationError('invalid_reference:people', 'Unavailable people reference.')
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.replace(['s1'])
        self.assertEqual(self.durable_state(), before)

    def test_failure_after_role_audit_and_pointer_writes_rolls_back(self):
        self.task()
        before = self.durable_state()
        with (patch('spine.ledger.people_authoring.verify_role_edge', side_effect=RuntimeError('injected')),
              self.assertRaisesRegex(RuntimeError, 'injected'), self.db.atomic_command()):
            self.replace(['s1'])
            self.fail('must not reach outer commit')
        self.assertEqual(self.durable_state(), before)

    def test_outer_failure_after_receipt_write_rolls_back_successful_mutation(self):
        from spine.commands.receipts import command_receipt, insert_command_receipt

        self.task()
        before = self.durable_state()
        with self.assertRaisesRegex(RuntimeError, 'receipt failure'), self.db.atomic_command():
            result = self.replace(['s1'])
            insert_command_receipt(self.db, command_receipt(command='item.people.update',
                command_id='people-change', actor_subject_id='s0', action_timestamp_utc=NOW,
                effect='item_people_updated', semantic_facts={'fixture': 'outer rollback'},
                result_identity_facts={'item_version': str(result.snapshot.current_version)}))
            raise RuntimeError('receipt failure')
        self.assertEqual(self.durable_state(), before)

    def test_audit_and_policy_copy_failures_roll_back(self):
        self.task()
        before = self.durable_state()
        for owner in ('spine.ledger.items._insert_mutation_audit',
                      'spine.ledger.notifications.copy_forward_notification_policies'):
            with (self.subTest(owner=owner), patch(owner, side_effect=RuntimeError('injected')),
                  self.assertRaisesRegex(RuntimeError, 'injected'), self.db.atomic_command()):
                self.replace(['s1'])
            self.assertEqual(self.durable_state(), before)

    def test_stale_target_wrong_role_and_terminal_refuse(self):
        self.task()
        before = self.durable_state()
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            replace_people(self.db, item_id='task', target_version=2, people={'assignees': ['s1']},
                command_id='stale', actor_subject_id='s0', updated_at_utc=NOW,
                audit_id='a', admit_additions=self.admit)
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            replace_people(self.db, item_id='task', target_version=1, people={'participants': []},
                command_id='wrong', actor_subject_id='s0', updated_at_utc=NOW,
                audit_id='a', admit_additions=self.admit)
        self.assertEqual(self.durable_state(), before)
        with self.db:
            self.db.execute("UPDATE coordination_items SET status='archived', archived_at_utc=? WHERE item_id='task'", (NOW,))
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.replace(['s1'])

    def test_distinct_role_proof_rejects_unmanaged_or_other_fact_changes(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='owner'),))
        before = capture_role_edge(self.db, 'task', 1)
        for dimension in ('item', 'item_subject_roles', 'people_facets', 'anchors'):
            after = deepcopy(before)
            if dimension == 'item':
                after['item']['source_ref'] = 'unexpected'
            elif dimension == 'item_subject_roles':
                after[dimension][0]['subject_id'] = 's2'
            else:
                after[dimension].append({'unexpected': 'change'})
            with self.subTest(dimension=dimension), self.assertRaises(SpineValidationError):
                verify_role_edge(before, after, role='assignee')

    def test_role_overflow_and_finalizer_failure_roll_back_the_entire_outer_transaction(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=f's{i}', role='watcher') for i in range(100)))
        before = self.durable_state()
        with self.assertRaises(SpineValidationError), self.db.atomic_command():
            self.replace(['s101'])
        self.assertEqual(self.durable_state(), before)
        # The failed command must leave tracking reusable by the next command.
        with self.db.atomic_command():
            noop = self.replace([])
        self.assertFalse(noop.changed)
        with (patch('spine.ledger.facets.finalize', side_effect=RuntimeError('finalizer')),
              self.assertRaisesRegex(RuntimeError, 'finalizer'), self.db.atomic_command()):
            self.db.execute("UPDATE subjects SET display_name='temporary' WHERE subject_id='s1'")
        self.assertEqual(self.durable_state(), before)

    def test_deferred_foreign_key_and_lost_cas_roll_back(self):
        self.task()
        before = self.durable_state()
        with self.assertRaises(sqlite3.IntegrityError), self.db.atomic_command():
            self.replace(['missing-subject'])
        self.assertEqual(self.durable_state(), before)
        from spine.ledger import items

        original = items.create_item_version_from_draft

        def competing_write(db, draft, **kwargs):
            items.create_next_item_version(db, item_id='task', target_version=1, title='interleaved',
                created_at_utc=NOW, created_by_subject_id='s0', audit_id='interleaved-audit')
            return original(db, draft, **kwargs)

        with (patch('spine.ledger.people_authoring.create_item_version_from_draft', side_effect=competing_write),
              self.assertRaises(SpineValidationError), self.db.atomic_command()):
            self.replace(['s1'])
        self.assertEqual(self.durable_state(), before)

    def test_event_policies_facets_and_existing_work_survive_repeated_role_edits(self):
        from spine.ledger import facets
        from spine.ledger.work import assert_work_instance_not_stale
        from tests.test_facet_commands import FacetCommandTests

        FacetCommandTests.setUpClass()
        fixture = FacetCommandTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        db = fixture.db
        schema, binding = fixture.catalog()
        event = fixture.event(materialize=True)
        response = fixture.call('item.facets.update', fixture.update(event['item_id'], schema, binding))
        version = int(response['item_version'])
        original_facets = facets.load_snapshot(db, event['item_id'], version)
        original_work = [tuple(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]
        self.assertTrue(original_work)
        original_attempts = [tuple(r) for r in db.execute('SELECT * FROM side_effect_attempts')]
        for n, subjects in enumerate((['owner'], [], ['owner'])):
            admit = Mock()
            with db.atomic_command():
                result = replace_people(db, item_id=event['item_id'], target_version=version + n,
                    people={'participants': subjects}, command_id=f'event-people-{n}', actor_subject_id='owner',
                    updated_at_utc=NOW, audit_id=f'event-people-audit-{n}', admit_additions=admit)
            self.assertTrue(result.changed)
            self.assertEqual(facets.load_snapshot(db, event['item_id'], version + n + 1), original_facets)
            for row in db.execute('SELECT work_instance_id FROM work_instances'):
                assert_work_instance_not_stale(db, row[0])
        self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')], original_work)
        self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM side_effect_attempts')], original_attempts)


class PeopleContinuityTests(unittest.TestCase):
    """Private transaction/worker seam; no people handlers or real adapters."""

    def setUp(self):
        from tests.test_facet_commands import FacetCommandTests

        FacetCommandTests.setUpClass()
        self.fixture = FacetCommandTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.schema, self.binding = self.fixture.catalog()
        self.event = self.fixture.event(materialize=True)
        self.item_id = self.event['item_id']
        self.number = 0

    def replace(self, subjects):
        self.number += 1
        version = self.db.execute('SELECT current_version FROM coordination_items WHERE item_id=?', (self.item_id,)).fetchone()[0]
        with self.db.atomic_command():
            return replace_people(self.db, item_id=self.item_id, target_version=version,
                people={'participants': subjects}, command_id=f'people-{self.number}', actor_subject_id='owner',
                updated_at_utc=NOW, audit_id=f'people-audit-{self.number}', admit_additions=Mock())

    def work(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]

    def resolve(self):
        from spine.ledger.notifications import NotificationPolicyResolver, load_current_notification_policies

        resolver = NotificationPolicyResolver(self.db, load_current_notification_policies(self.db, item_id=self.item_id))
        for work in self.work():
            self.assertIsNotNone(resolver.resolve(work['notification_policy_id']))
        return resolver

    def test_historical_policy_capture_and_mixed_edges_are_exact_and_read_only(self):
        from spine.ledger.facet_continuity import capture
        from spine.ledger.work import assert_work_instance_not_stale
        from spine.services.scheduling import materialize_notification_horizon
        from spine.services.work import list_eligible_work

        prior = self.work()
        self.replace(['owner'])
        self.fixture.call('item.facets.update', self.fixture.update(self.item_id, self.schema, self.binding))
        self.replace([])
        old = capture(self.db, self.item_id, 1)
        self.assertEqual({p['policy_id'] for p in old['policies']}, {w['notification_policy_id'] for w in prior})
        resolver = self.resolve()
        self.assertEqual(set(resolver._verified_edges.values()), {'people', 'facets'})
        self.assertTrue(resolver._checked_copy_edges)
        before = '\n'.join(self.db.iterdump())
        for work in prior:
            assert_work_instance_not_stale(self.db, work['work_instance_id'])
        at = max(w['eligible_at_utc'] for w in prior)
        self.assertEqual(len(list_eligible_work(self.db, now_utc=at)), len(prior))
        cycle = materialize_notification_horizon(self.db, evaluated_at_utc=at, horizon_seconds=3600, max_items=10)
        self.assertEqual(cycle.failures, ())
        self.assertEqual(cycle.items_repaired, 0)
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        self.assertEqual(self.work(), prior)

    def test_invalid_intermediate_role_edge_fails_closed_without_cancelling_work(self):
        from spine.ledger.work import assert_work_instance_not_stale
        from spine.services.scheduling import materialize_notification_horizon

        first = self.replace(['owner'])
        self.replace([])
        # Synthetic corruption in a disposable ledger: endpoints/policies still match.
        self.db.execute('BEGIN')
        try:
            self.db.execute('UPDATE coordination_item_versions SET summary=? WHERE item_id=? AND version=?',
                ('unexpected intermediate detail', self.item_id, first.snapshot.current_version))
            before = '\n'.join(self.db.iterdump())
            work = self.work()[0]
            with self.assertRaisesRegex(SpineValidationError, 'Role-only continuity failed'):
                assert_work_instance_not_stale(self.db, work['work_instance_id'])
            cycle = materialize_notification_horizon(self.db, evaluated_at_utc=work['eligible_at_utc'],
                horizon_seconds=3600, max_items=10)
            self.assertTrue(cycle.failures)
            self.assertEqual(cycle.items_repaired, 0)
            self.assertEqual('\n'.join(self.db.iterdump()), before)
        finally:
            self.db.rollback()

    def test_facet_edge_in_people_lineage_cannot_relax_role_equality(self):
        self.replace(['owner'])
        edit = self.fixture.call('item.facets.update', self.fixture.update(self.item_id, self.schema, self.binding))
        self.replace([])
        self.db.execute('BEGIN')
        try:
            self.db.execute("UPDATE item_subject_roles SET status='inactive' WHERE item_id=? AND version=? AND role='participant'",
                (self.item_id, int(edit['item_version'])))
            with self.assertRaisesRegex(SpineValidationError, 'facet-only notification equivalence failed'):
                self.resolve()
        finally:
            self.db.rollback()

    def test_noop_does_not_add_a_lineage_edge_or_new_role_ids(self):
        self.replace(['owner'])
        before = self.work()
        edges = dict(self.resolve()._verified_edges)
        unchanged = self.replace(['owner'])
        self.assertFalse(unchanged.changed)
        self.assertEqual(self.resolve()._verified_edges, edges)
        self.assertEqual(self.work(), before)

    def test_legacy_gap_cannot_skip_a_declared_people_edge(self):
        from spine.ledger.notifications import NotificationPolicyResolver, load_current_notification_policies

        original = self.work()[0]['notification_policy_id']
        self.replace(['owner'])
        self.replace([])
        policy = load_current_notification_policies(self.db, item_id=self.item_id)[0]
        resolver = NotificationPolicyResolver(self.db, [{**policy, 'notification_policy_id': 'prospective',
            'item_version': '4', 'source_notification_policy_id': original}])
        before = self.work()
        with self.assertRaisesRegex(SpineValidationError, 'skips a people edge'):
            resolver.resolve(original)
        self.assertEqual(self.work(), before)

    def test_active_and_completed_attempt_history_is_unchanged_by_roles(self):
        from spine.services.attempts import prepare_work_attempt, record_attempt_failure
        from spine.services.work import fail_work, retry_work, start_work

        work = self.work()[0]
        key, at = work['work_instance_id'], work['eligible_at_utc']
        start_work(self.db, work_instance_id=key, started_at_utc=at)
        prepare_work_attempt(self.db, work_instance_id=key, adapter_name='openclaw', idempotency_key='private-test',
            request_envelope={'message': 'synthetic'}, attempted_at_utc=at, attempt_id='private-test')
        for state in ('started', 'retry', 'terminal'):
            if state == 'retry':
                record_attempt_failure(self.db, attempt_id='private-test', completed_at_utc=at, reason_code='adapter_failure')
                retry_work(self.db, work_instance_id=key, next_attempt_at_utc=at, updated_at_utc=at, reason_code='adapter_failure')
            elif state == 'terminal':
                fail_work(self.db, work_instance_id=key, failed_at_utc=at, reason_code='adapter_failure')
            before_work = self.work()
            before_attempts = [tuple(r) for r in self.db.execute('SELECT * FROM side_effect_attempts ORDER BY attempt_id')]
            with self.subTest(state=state):
                self.replace(['owner'] if state != 'retry' else [])
                self.resolve()
                self.assertEqual(self.work(), before_work)
                self.assertEqual(
                    [tuple(r) for r in self.db.execute('SELECT * FROM side_effect_attempts ORDER BY attempt_id')], before_attempts)

    def test_independent_route_staleness_is_not_revived_by_role_edits(self):
        from spine.ledger.work import assert_work_instance_not_stale

        self.replace(['owner'])
        with self.db:
            self.db.execute("UPDATE delivery_targets SET status='inactive' WHERE delivery_target_id='whatsapp-owner'")
        with self.assertRaisesRegex(SpineValidationError, 'item_mutation_rejected'):
            self.replace([])
        before = self.work()
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            assert_work_instance_not_stale(self.db, before[0]['work_instance_id'])
        self.assertEqual(self.work(), before)

    def test_ancestry_limit_refuses_without_work_mutation(self):
        from spine.ledger.notifications import NotificationPolicyResolver, load_current_notification_policies

        original = self.work()[0]['notification_policy_id']
        policy = load_current_notification_policies(self.db, item_id=self.item_id)[0]
        resolver = NotificationPolicyResolver(self.db, [{**policy, 'notification_policy_id': 'future',
            'item_version': '103', 'source_notification_policy_id': 'prior-102'}])
        source = dict(resolver._load(original))
        for version in range(2, 103):
            resolver._history[f'prior-{version}'] = {**source, 'policy_id': f'prior-{version}', 'version': version,
                'source_notification_policy_id': original if version == 2 else f'prior-{version - 1}'}
        before = self.work()
        with self.assertRaisesRegex(SpineValidationError, 'ancestry capacity'):
            resolver.resolve(original)
        self.assertEqual(self.work(), before)
        allowed = NotificationPolicyResolver(self.db, [{**policy, 'notification_policy_id': 'future-allowed',
            'item_version': '101', 'source_notification_policy_id': 'prior-100'}])
        allowed._history.update(resolver._history)
        self.assertIsNotNone(allowed.resolve(original))

    def test_people_and_presentation_edges_use_separate_unchanged_proofs(self):
        from spine.ledger.notifications import NotificationPolicyResolver, load_current_notification_policies
        from tests.test_rendering_successor_authoring import RenderingSuccessorTests

        RenderingSuccessorTests.setUpClass()
        fixture = RenderingSuccessorTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        root = fixture.create()['record']
        request = fixture.fixture.event_request('people-presentation', materialize=True)
        request['contract_version'] = 'spine.schedule-create.v3'
        event = fixture.candidate('schedule.create', request)
        fixture.adopt(event['item_id'])
        grant = fixture.disclosure(root)
        db, item = fixture.db, event['item_id']
        original_work = [dict(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]

        def roles(version, subjects):
            with db.atomic_command():
                replace_people(db, item_id=item, target_version=version, people={'participants': subjects},
                    command_id=f'mixed-{version}', actor_subject_id='owner', updated_at_utc=NOW,
                    audit_id=f'mixed-audit-{version}', admit_additions=Mock())

        roles(1, ['owner'])
        edited = fixture.candidate('schedule.update', fixture.edit(event, fixture.selection(grant)))
        self.assertEqual(edited['changed_dimensions'], ['policy_presentations'])
        roles(3, [])

        def resolve():
            resolver = NotificationPolicyResolver(db, load_current_notification_policies(db, item_id=item))
            self.assertIsNotNone(resolver.resolve(original_work[0]['notification_policy_id']))
            return resolver

        self.assertEqual(set(resolve()._verified_edges.values()), {'people', 'presentations'})
        self.assertEqual([dict(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')], original_work)
        db.execute('BEGIN')
        try:
            db.execute("UPDATE item_subject_roles SET status='inactive' WHERE item_id=? AND version=3 AND role='participant'", (item,))
            with self.assertRaisesRegex(SpineValidationError, 'facet-only notification equivalence failed'):
                resolve()
        finally:
            db.rollback()

    def test_following_task_is_not_blessed_by_its_sources_people_edge(self):
        from types import SimpleNamespace

        from spine.commands import handle
        from spine.ledger.temporal_bindings import active_follow_binding_current
        from spine.ledger.work import assert_work_instance_not_stale
        from tests.test_relative_temporal_bindings_command import RelativeTemporalBindingCommandTests

        request = RelativeTemporalBindingCommandTests._related_request(
            SimpleNamespace(event=self.event), 'follow_source', with_reminder=True)
        request['created_at_utc'] = '2026-08-13T12:00:00Z'
        request['materialization']['evaluated_at_utc'] = '2026-08-13T12:00:00Z'
        related = handle('schedule.related_task.create', request, self.fixture.context)
        self.assertTrue(related['ok'], related)
        task = related['task']['item_id']
        key = related['work_instance_ids'][0]
        with self.db.atomic_command():
            replace_people(self.db, item_id=task, target_version=1, people={'assignees': ['owner']},
                command_id='following-people', actor_subject_id='owner', updated_at_utc=NOW,
                audit_id='following-audit', admit_additions=Mock())
        self.assertTrue(active_follow_binding_current(self.db, item_id=task))
        assert_work_instance_not_stale(self.db, key)
        bindings = [tuple(r) for r in self.db.execute('SELECT * FROM relative_temporal_binding_revisions')]
        self.replace(['owner'])
        self.assertFalse(active_follow_binding_current(self.db, item_id=task))
        with self.assertRaisesRegex(SpineValidationError, 'stale_work_instance'):
            assert_work_instance_not_stale(self.db, key)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM relative_temporal_binding_revisions')], bindings)
