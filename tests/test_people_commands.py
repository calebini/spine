"""Private local handlers on disposable ledgers; no public family activation."""

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_people_ledger as foundation
import test_schedule_operations_command as scheduling
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands import CommandContext, handle, people_candidate
from spine.commands.registry import MVP_COMMANDS
from spine.core.hashing import command_derived_id, hash_canonical_json
from spine.ledger import ItemSubjectRoleInput, create_next_item_version
from spine.ledger.people import read_people_snapshot
from spine.ledger.work import assert_work_instance_not_stale

NOW = foundation.NOW
ROOT = Path(__file__).parents[1]


class _PeopleCommandSupport:
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text()) for p in (ROOT / 'contracts/schemas').rglob('*.schema.json')]
        cls.registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)

    def setUp(self):
        foundation.PeopleLedgerTests.setUp(self)
        self.connection = self.db
        self.context = CommandContext(ledger=self.db)

    task = foundation.PeopleLedgerTests.task

    def request(self, **facts):
        return {'contract_version': people_candidate.CONTRACT, 'command_id': 'people-command',
                'actor_subject_id': 's0', 'item_id': 'task', 'target_version': '1', 'updated_at_utc': NOW,
                'people': {'assignees': ['s2', 's1']}} | facts

    def run_command(self, command, request, *, context=None, ok=True):
        response = people_candidate.execute(command, request, context or self.context)
        self.assertEqual(response['ok'], ok, response)
        uri = ('responses' if ok else 'failures') + '.schema.json#/$defs/' + (command if ok else 'local')
        Draft202012Validator({'$ref': 'https://cortext.local/spine/contracts/schemas/people/' + uri},
                            registry=self.registry, format_checker=FormatChecker()).validate(response)
        return response

    def state(self):
        return '\n'.join(self.db.iterdump())

    def show(self, version=None):
        request = {'contract_version': people_candidate.CONTRACT, 'item_id': 'task'}
        if version is not None:
            request['version'] = str(version)
        return self.run_command('item.people.show', request)


class PeopleCommandsTests(_PeopleCommandSupport, unittest.TestCase):
    def test_changed_canonical_receipt_exact_history_and_current_labels(self):
        self.task((ItemSubjectRoleInput(subject_id='s3', role='owner'),
                   ItemSubjectRoleInput(subject_id='s4', role='participant')))
        request = self.request()
        response = self.run_command('item.people.update', request)
        self.assertEqual((response['effect'], response['current_version']), ('item_people_updated', '2'))
        self.assertTrue(response['truth_changed'])
        self.assertFalse(response['work_changed'])
        normalized = copy.deepcopy(request)
        normalized['people']['assignees'].sort()
        self.assertEqual(response['receipt']['semantic_facts_hash'], hash_canonical_json(people_candidate.semantic_facts(normalized)))
        for index, row in enumerate(response['associations']):
            self.assertEqual(row['item_subject_role_id'], command_derived_id(prefix='item_subject_role',
                command='item.people.update', command_id=request['command_id'], row_role='item_subject_role',
                request_path=f'/people/assignees/{index}'))
        self.assertEqual(self.show(1)['people']['associations'], [])
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Renamed',status='inactive' WHERE subject_id='s1'")
        before = self.state()
        shown = self.show(2)
        self.assertEqual(shown['people']['subjects'][0]['label']['display_name'], 'Renamed')
        self.assertEqual(shown['people']['associations'], response['associations'])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit_log WHERE item_id=?', ('task',)).fetchone()[0], 2)
        self.assertEqual({row[0] for row in self.db.execute("SELECT role FROM item_subject_roles WHERE version=2")},
                         {'assignee', 'owner', 'participant'})

    def test_noop_receipt_keeps_old_ids_and_replay_after_later_edits_has_no_writes(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee', item_subject_role_id='original'),))
        request = self.request(people={'assignees': ['s1']})
        first = self.run_command('item.people.update', request)
        self.assertEqual(first['effect'], 'item_people_noop')
        self.assertEqual(first['associations'][0]['item_subject_role_id'], 'original')
        self.assertNotIn('audit_id', first)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM coordination_item_versions').fetchone()[0], 1)
        self.run_command('item.people.update', self.request(command_id='later', people={'assignees': []}))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s1'")
        before, changes = self.state(), self.db.total_changes
        replay = self.run_command('item.people.update', request)
        self.assertEqual(replay['effect'], 'item_people_replay')
        self.assertEqual(replay['receipt'], first['receipt'])
        self.assertEqual(replay['associations'], first['associations'])
        self.assertEqual(replay['current_version'], '1')
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(self.state(), before)

    def test_changed_replay_is_original_truth_not_fresh_admission_or_stale_check(self):
        self.task()
        request = self.request()
        first = self.run_command('item.people.update', request)
        self.run_command('item.people.update', self.request(command_id='later', target_version='2', people={'assignees': []}))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id IN ('s0','s1','s2')")
        before = self.state()
        with patch('spine.commands.people_candidate.admit_subjects', side_effect=AssertionError('fresh check during replay')):
            replay = self.run_command('item.people.update', request)
        self.assertTrue(replay['truth_changed'])
        self.assertEqual(replay['current_version'], '2')
        self.assertEqual(replay['receipt'], first['receipt'])
        self.assertEqual(replay['associations'], first['associations'])
        self.assertEqual(self.state(), before)

    def test_changed_and_failed_dry_runs_use_real_writes_and_rollback(self):
        self.task()
        request = self.request()
        before, changes = self.state(), self.db.total_changes
        preview = self.run_command('item.people.update', request, context=replace(self.context, dry_run=True))
        self.assertTrue(preview['dry_run'])
        self.assertGreater(self.db.total_changes, changes)
        self.assertEqual(self.state(), before)
        committed = self.run_command('item.people.update', request)
        self.assertEqual({k: v for k, v in preview.items() if k != 'dry_run'}, committed)
        before = self.state()
        failure = self.run_command('item.people.update', self.request(command_id='bad', target_version='2',
            people={'assignees': ['not-present']}), context=replace(self.context, dry_run=True), ok=False)
        self.assertTrue(failure['dry_run'])
        self.assertEqual(failure['error']['field'], 'people')
        self.assertNotIn('not-present', str(failure))
        self.assertEqual(self.state(), before)

    def test_conflict_stale_inactive_terminal_and_wrong_role_refuse_atomically(self):
        self.task()
        request = self.request()
        self.run_command('item.people.update', request)
        before = self.state()
        for bad, code in (
            (self.request(people={'assignees': []}), 'semantic_conflict'),
            (self.request(command_id='stale'), 'stale_version'),
            (self.request(command_id='wrong', target_version='2', people={'participants': []}), 'invalid_request'),
        ):
            with self.subTest(code=code):
                failed = self.run_command('item.people.update', bad, ok=False)
                self.assertEqual(failed['error']['code'], code)
                self.assertEqual(self.state(), before)
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s3'")
        self.run_command('item.people.update', self.request(command_id='inactive', target_version='2',
            people={'assignees': ['s3']}), ok=False)
        with self.db:
            self.db.execute("UPDATE coordination_items SET status='archived',archived_at_utc=? WHERE item_id='task'", (NOW,))
        self.run_command('item.people.update', self.request(command_id='terminal', target_version='2'), ok=False)

    def test_noop_retained_inactive_and_clear_never_readmit_old_subjects(self):
        self.task((ItemSubjectRoleInput(subject_id='s1', role='assignee'),))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='s1'")
        noop = self.run_command('item.people.update', self.request(people={'assignees': ['s1']}))
        self.assertEqual(noop['effect'], 'item_people_noop')
        changed = self.run_command('item.people.update', self.request(command_id='retain', people={'assignees': ['s1', 's2']}))
        self.assertEqual(changed['current_version'], '2')
        cleared = self.run_command('item.people.update', self.request(command_id='clear', target_version='2', people={'assignees': []}))
        self.assertEqual(cleared['associations'], [])

    def test_receipt_write_and_dry_run_finalizer_failures_rollback(self):
        self.task()
        before = self.state()
        for owner, context in (
            ('spine.commands.people_candidate.insert_command_receipt', self.context),
            ('spine.ledger.facets.finalize', replace(self.context, dry_run=True)),
            ('spine.ledger.rendering_definitions.finalize', self.context),
        ):
            with self.subTest(owner=owner), patch(owner, side_effect=sqlite_error()):
                self.run_command('item.people.update', self.request(), context=context, ok=False)
            self.assertEqual(self.state(), before)
        self.assertFalse(self.db._command_transaction)
        self.run_command('item.people.update', self.request())

    def test_shape_order_and_closed_request_refuse_without_ledger_queries(self):
        self.task()
        statements = []
        self.db.set_trace_callback(statements.append)
        failed = self.run_command('item.people.update', {'z': 1, 'a': 2}, ok=False)
        self.assertEqual(failed['error'], {'code': 'unsupported_field', 'field': 'a', 'message': 'Invalid people request.'})
        self.assertEqual(statements, [])
        for patch_value in (None, {}, {'assignees': ['s1', 's1']}, {'assignees': ['bad\ud800']}, {'assignees': [1]}):
            self.run_command('item.people.update', self.request(people=patch_value), ok=False)
        self.assertEqual(statements, [])

    def test_candidate_not_public_and_protected_context_cannot_use_local_path(self):
        self.task()
        self.assertNotIn('item.people.update', MVP_COMMANDS)
        self.assertNotIn(people_candidate.CONTRACT, IMPLEMENTED_CONTRACT_VERSIONS)
        self.assertFalse(handle('item.people.update', self.request(), self.context)['ok'])
        before = self.state()
        failed = self.run_command('item.people.update', self.request(),
            context=replace(self.context, transport_metadata={'mode': 'permission_enforced'}), ok=False)
        self.assertEqual(failed['error']['field'], 'admission')
        self.assertEqual(self.state(), before)

    def test_corrupt_retained_receipt_and_audit_refuse_without_repair(self):
        self.task()
        request = self.request()
        self.run_command('item.people.update', request)
        original = dict(self.db.execute('SELECT * FROM command_receipts WHERE command_id=?', (request['command_id'],)).fetchone())
        for column, value in (
            ('semantic_facts_hash', '0' * 64),
            ('result_identity_facts_json', '{}'),
            ('result_identity_facts_json', '[]'),
            ('semantic_facts_json', '{broken'),
        ):
            with self.subTest(column=column):
                with self.db:
                    self.db.execute(f'UPDATE command_receipts SET {column}=? WHERE command_id=?', (value, request['command_id']))
                before = self.state()
                refused = self.run_command('item.people.update', request, ok=False)
                self.assertEqual(refused['error']['code'], 'environment_failure')
                self.assertEqual(self.state(), before)
                with self.db:
                    self.db.execute(f'UPDATE command_receipts SET {column}=? WHERE command_id=?',
                                    (original[column], request['command_id']))
        with self.db:
            self.db.execute("UPDATE audit_log SET payload_hash=? WHERE action='item_people_updated'", ('0' * 64,))
        before = self.state()
        self.run_command('item.people.update', request, ok=False)
        self.assertEqual(self.state(), before)

    def test_total_role_capacity_and_missing_actor_fail_before_receipt(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=f's{i}', role='watcher') for i in range(100)))
        before = self.state()
        failed = self.run_command('item.people.update', self.request(), ok=False)
        self.assertEqual(failed['error']['code'], 'environment_failure')
        self.run_command('item.people.update', self.request(actor_subject_id='missing'), ok=False)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.show()['people']['associations'], [])

    def test_frozen_computed_semantic_vector_is_used_by_runtime(self):
        vectors = json.loads((ROOT / 'tests/fixtures/people_and_responsibility/computed-vectors.json').read_text())['vectors']
        vector = next(v for v in vectors if v['id'] == 'update_semantic_facts')
        request = people_candidate.normalize_request('item.people.update', vector['preimage']['request'])
        self.assertEqual(people_candidate.semantic_facts(request), vector['preimage'])
        self.assertEqual(hash_canonical_json(people_candidate.semantic_facts(request)), vector['sha256'])

    def test_standalone_copy_forward_ids_are_canonical_for_every_omitted_role(self):
        self.task(tuple(ItemSubjectRoleInput(subject_id=f's{i}', role=role, item_subject_role_id=f'prior-{role}',
            status='inactive' if role == 'watcher' else 'active')
            for i, role in enumerate(('owner', 'participant', 'watcher', 'recipient'), 3)))
        result = self.run_command('item.people.update', self.request(people={'assignees': ['s1']}))
        rows = self.db.execute("SELECT * FROM item_subject_roles WHERE item_id='task' AND version=2 AND role!='assignee'").fetchall()
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row['item_subject_role_id'], command_derived_id(prefix='item_subject_role',
                command='item.people.update', command_id=result['command_id'], row_role='item_subject_role',
                request_path='/copy_forward/item_subject_role/prior-' + row['role']))
        self.assertEqual(self.db.execute("SELECT status FROM item_subject_roles WHERE version=2 AND role='watcher'").fetchone()[0],
                         'inactive')

    def test_active_agent_and_accountless_person_selection_needs_no_accounts(self):
        self.task()
        with self.db:
            self.db.execute("UPDATE subjects SET subject_kind='agent' WHERE subject_id='s2'")
        result = self.run_command('item.people.update', self.request())
        self.assertEqual([r['subject_id'] for r in result['associations']], ['s1', 's2'])
        self.assertEqual([s['label']['subject_kind'] for s in self.show()['people']['subjects']], ['person', 'agent'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM login_accounts').fetchone()[0], 0)


def sqlite_error():
    import sqlite3

    return sqlite3.OperationalError('injected transaction failure')


class PeopleScheduleTests(_PeopleCommandSupport, unittest.TestCase):
    def setUp(self):
        self.fixture = scheduling.ScheduleOperationsCommandTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.connection
        self.connection = self.db
        self.context = self.fixture.context
        with self.db:
            self.db.executemany("INSERT INTO subjects(subject_id,subject_kind,display_name,status,created_at_utc,updated_at_utc) "
                "VALUES (?,'person',?,'active',?,?)", [('alice', 'Alice', NOW, NOW), ('bob', 'Bob', NOW, NOW)])

    def create(self, *, task=False, people=None, materialize=True, command_id='people-schedule'):
        request = self.fixture.task_request(command_id) if task else self.fixture.event_request(command_id, materialize=materialize)
        request['contract_version'] = 'spine.schedule-create.v4'
        if task:
            request['item']['task_detail'].pop('subject_roles', None)
        if people is not None:
            request['people'] = people
        return request

    def update(self, item, patch_value, **facts):
        return {'contract_version': 'spine.schedule-update.v4', 'command_id': 'people-schedule-update',
                'actor_subject_id': 'owner', 'item_id': item['item_id'], 'target_version': item['current_version'],
                'updated_at_utc': '2026-08-13T12:00:00Z', 'patch': patch_value, 'materialization': {'mode': 'none'}} | facts

    def schedule(self, command, request, *, context=None, ok=True):
        response = people_candidate.execute(command, request, context or self.context)
        self.assertEqual(response['ok'], ok, response)
        if ok:
            filename = 'schedule-create-response-v4' if command == 'schedule.create' else 'schedule-update-response-v4'
            Draft202012Validator({'$ref': f'https://cortext.local/spine/contracts/schemas/people/{filename}.schema.json'},
                                registry=self.registry, format_checker=FormatChecker()).validate(response)
        return response

    def test_v4_create_event_and_task_people_share_transaction_and_normalized_ids(self):
        for task in (False, True):
            key = 'assignees' if task else 'participants'
            with self.subTest(task=task):
                request = self.create(task=task, people={key: ['bob', 'alice']}, command_id='create-' + key)
                result = self.schedule('schedule.create', request)
                rows = read_people_snapshot(self.db, item_id=result['item_id'])
                self.assertEqual([as_row.subject_id for as_row in rows.associations], ['alice', 'bob'])
                self.assertEqual([r['item_subject_role_id'] for r in result['people']], [r.item_subject_role_id for r in rows.associations])
                self.assertEqual(result['current_version'], '1')
                self.assertEqual(result['receipt']['receipt_contract'], 'spine.schedule-create-receipt.v4')
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM coordination_item_versions WHERE item_id=?',
                    (result['item_id'],)).fetchone()[0], 1)
                replay = self.schedule('schedule.create', request | {'people': {key: ['alice', 'bob']}})
                self.assertEqual(replay['effect'], 'schedule_create_replay')
                self.assertEqual(replay['receipt'], result['receipt'])

    def test_omitted_create_is_empty_no_actor_inference_and_replays_with_explicit_empty(self):
        request = self.create(materialize=False)
        result = self.schedule('schedule.create', request)
        self.assertEqual(result['people'], [])
        replay = self.schedule('schedule.create', request | {'people': {'participants': []}})
        self.assertEqual(replay['receipt'], result['receipt'])

    def test_role_only_update_preserves_work_and_actual_resolver_continuity(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}))
        work = [tuple(r) for r in self.db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]
        request = self.update(item, {'people': {'participants': ['bob']}})
        changed = self.schedule('schedule.update', request)
        self.assertEqual(changed['changed_dimensions'], ['people'])
        self.assertFalse(changed['work_changed'])
        self.assertEqual(changed['current_version'], '2')
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')], work)
        for row in self.db.execute('SELECT work_instance_id FROM work_instances'):
            assert_work_instance_not_stale(self.db, row[0])
        before = self.state()
        replay = self.schedule('schedule.update', request)
        self.assertEqual(replay['people'], changed['people'])
        self.assertEqual(self.state(), before)

    def test_mixed_update_commits_one_version_and_one_audit_and_retains_other_roles(self):
        item = self.schedule('schedule.create', self.create(task=True, people={'assignees': ['alice']}))
        # Existing unmanaged and opposite roles belong to the preceding version.
        create_next_item_version(self.db, item_id=item['item_id'], target_version=1, created_at_utc=NOW,
            created_by_subject_id='owner', audit_id='unmanaged', subject_roles=(
                ItemSubjectRoleInput(subject_id='alice', role='assignee'), ItemSubjectRoleInput(subject_id='owner', role='owner'),
                ItemSubjectRoleInput(subject_id='bob', role='participant'), ItemSubjectRoleInput(subject_id='bob', role='watcher')),
            subject_role_replacement_roles=('assignee', 'owner', 'participant', 'watcher'), supporting_command_id='unmanaged')
        item['current_version'] = '2'
        result = self.schedule('schedule.update', self.update(item, {'item': {'title': 'Changed title'}, 'people': {'assignees': ['bob']}}))
        self.assertEqual(result['current_version'], '3')
        self.assertEqual(result['changed_dimensions'], ['item', 'people'])
        self.assertEqual({(r['subject_id'], r['role']) for r in self.db.execute(
            'SELECT * FROM item_subject_roles WHERE item_id=? AND version=3',
            (item['item_id'],))}, {('bob', 'assignee'), ('owner', 'owner'), ('bob', 'participant'), ('bob', 'watcher')})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit_log WHERE item_id=? AND action='schedule_updated'",
            (item['item_id'],)).fetchone()[0], 1)

    def test_omitted_update_copies_people_but_equal_patch_noop_keeps_prior_ids(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}, materialize=False))
        noop = self.schedule('schedule.update', self.update(item, {'people': {'participants': ['alice']}}))
        self.assertEqual(noop['changed_dimensions'], [])
        self.assertEqual(noop['people'], item['people'])
        copied = self.schedule('schedule.update', self.update(item, {'item': {'title': 'Changed'}}, command_id='copy-people'))
        self.assertEqual(copied['changed_dimensions'], ['item'])
        self.assertEqual(copied['people'][0]['subject_id'], 'alice')
        self.assertEqual(copied['people'][0]['item_subject_role_id'], command_derived_id(prefix='item_subject_role',
            command='schedule.update', command_id='copy-people', row_role='item_subject_role',
            request_path='/copy_forward/item_subject_role/' + item['people'][0]['item_subject_role_id']))

    def test_equal_people_in_changed_composite_uses_replacement_not_copy_paths(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}, materialize=False))
        request = self.update(item, {'item': {'title': 'Changed'}, 'people': {'participants': ['alice']}})
        result = self.schedule('schedule.update', request)
        self.assertEqual(result['changed_dimensions'], ['item'])
        self.assertEqual(result['people'][0]['item_subject_role_id'], command_derived_id(prefix='item_subject_role',
            command='schedule.update', command_id=request['command_id'], row_role='item_subject_role',
            request_path='/patch/people/participants/0'))

    def test_v4_rejects_competing_legacy_roles_role_only_materialization_and_presentation_mix(self):
        legacy = self.create(task=True)
        legacy['item']['task_detail']['subject_roles'] = []
        self.schedule('schedule.create', legacy, ok=False)
        item = self.schedule('schedule.create', self.create(materialize=False))
        before = self.state()
        self.schedule('schedule.update', self.update(item, {'people': {'participants': []}}, materialization={'mode': 'bounded'}), ok=False)
        self.schedule('schedule.update', self.update(item, {'people': {'participants': []}, 'policy_presentations': []}), ok=False)
        self.schedule('schedule.update', self.update(item, {'item': {'task_detail': {'subject_roles': []}}}), ok=False)
        self.assertEqual(self.state(), before)

    def test_v4_create_preview_and_failure_after_receipt_leave_no_orphans(self):
        request = self.create(people={'participants': ['alice']})
        before, changes = self.state(), self.db.total_changes
        preview = self.schedule('schedule.create', request, context=replace(self.context, dry_run=True))
        self.assertTrue(preview['dry_run'])
        self.assertGreater(self.db.total_changes, changes)
        self.assertEqual(self.state(), before)
        committed = self.schedule('schedule.create', request)
        self.assertEqual(committed['people'], preview['people'])
        self.assertEqual(committed['receipt'], preview['receipt'])
        bad = self.create(people={'participants': ['missing']}, command_id='missing')
        before = self.state()
        self.schedule('schedule.create', bad, ok=False)
        self.assertEqual(self.state(), before)

    def test_create_and_update_post_receipt_and_finalization_failures_roll_back_all_dimensions(self):
        from spine.commands.receipts import insert_command_receipt

        def post_receipt(db, receipt):
            insert_command_receipt(db, receipt)
            raise sqlite_error()

        request = self.create(people={'participants': ['alice']})
        before = self.state()
        for owner in ('spine.commands.core.insert_command_receipt', 'spine.ledger.facets.finalize'):
            with self.subTest(owner=owner), patch(owner, side_effect=post_receipt if owner.endswith('receipt') else sqlite_error()):
                self.schedule('schedule.create', request, ok=False)
            self.assertEqual(self.state(), before)
        item = self.schedule('schedule.create', request)
        update = self.update(item, {'people': {'participants': ['bob']}, 'item': {'title': 'Failed title'}})
        before = self.state()
        with patch('spine.commands.core.insert_command_receipt', side_effect=post_receipt):
            self.schedule('schedule.update', update, ok=False)
        self.assertEqual(self.state(), before)
        preview = self.schedule('schedule.update', update, context=replace(self.context, dry_run=True))
        self.assertTrue(preview['dry_run'])
        self.assertEqual(self.state(), before)
        committed = self.schedule('schedule.update', update)
        self.assertEqual(preview | {'dry_run': True}, committed | {'dry_run': True})

    def test_people_and_time_move_uses_ordinary_work_reconciliation_in_one_version(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}))
        patch_value = {'people': {'participants': ['bob']}, 'item': {'title': 'Moved'},
                       'scheduled_time': {'time_basis': 'local_instant', 'local_date': '2026-08-14', 'local_time': '11:00:00',
                                          'timezone': item['scheduled_time']['timezone'],
                                          'timezone_database_version': {'kind': 'explicit',
                                              'version': item['scheduled_time']['timezone_database_version']}}}
        result = self.schedule('schedule.update', self.update(item, patch_value))
        self.assertEqual(result['changed_dimensions'], ['item', 'people', 'scheduled_time'])
        self.assertEqual(result['current_version'], '2')
        self.assertTrue(result['work_changed'])
        self.assertTrue(result['work_reconciliation']['cancelled_work_instance_ids'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)

    def test_v4_replay_after_other_edits_and_subject_inactivation_uses_original_rows(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}))
        request = self.update(item, {'people': {'participants': ['bob']}})
        first = self.schedule('schedule.update', request)
        self.schedule('schedule.update', self.update(first, {'people': {'participants': []}}, command_id='later'))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='bob'")
        before = self.state()
        with patch('spine.commands.people_candidate.admit_subjects', side_effect=AssertionError('replay readmission')):
            replay = self.schedule('schedule.update', request)
        self.assertEqual(replay['current_version'], '2')
        self.assertEqual(replay['people'], first['people'])
        self.assertEqual(self.state(), before)

    def test_v4_presentation_only_branch_retains_exclusivity_and_people(self):
        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}, materialize=False))
        policy_id = item['policies'][0]['notification_policy_id']
        result = self.schedule('schedule.update', self.update(item, {'policy_presentations': [
            {'notification_policy_id': policy_id, 'selection': {'kind': 'ordinary'}}]}))
        self.assertEqual(result['changed_dimensions'], [])
        self.assertEqual(result['people'], item['people'])

    def test_v4_not_accepted_by_public_dispatch_and_v2_task_roles_still_work(self):
        request = self.create(people={'participants': ['alice']})
        before = self.state()
        self.assertFalse(handle('schedule.create', request, self.context)['ok'])
        self.assertEqual(self.state(), before)
        old = self.fixture.task_request('legacy-task')
        old['item']['task_detail']['subject_roles'] = [{'subject_id': 'owner', 'role': 'assignee'}]
        created = handle('schedule.create', old, self.context)
        self.assertTrue(created['ok'], created)
        self.assertEqual(read_people_snapshot(self.db, item_id=created['item_id']).associations[0].subject_id, 'owner')

    def test_selected_rendering_and_mixed_exclusive_edges_preserve_facets_people_and_work(self):
        from spine.ledger.facets import load_snapshot
        from spine.ledger.rendering_definitions import load_presentation
        from tests.test_rendering_delivery import RenderingDeliveryTests

        fixture = RenderingDeliveryTests()
        fixture.setUpClass()
        fixture.setUp()
        try:
            item, _ = fixture.event()
            db = fixture.db
            item['current_version'] = str(db.execute('SELECT current_version FROM coordination_items WHERE item_id=?',
                (item['item_id'],)).fetchone()[0])
            facets = load_snapshot(db, item['item_id'], int(item['current_version']))
            original_work = [tuple(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]
            result = people_candidate.execute('schedule.update',
                self.update(item, {'people': {'participants': ['owner']}}), fixture.context)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['changed_dimensions'], ['people'])
            self.assertEqual(load_snapshot(db, item['item_id'], int(result['current_version'])), facets)
            self.assertEqual(load_presentation(db, result['policies'][0]['notification_policy_id'])['kind'], 'definition')
            edit = self.update(result, {'policy_presentations': [{
                'notification_policy_id': result['policies'][0]['notification_policy_id'], 'selection': {'kind': 'ordinary'}}]},
                command_id='ordinary-presentation')
            presented = people_candidate.execute('schedule.update', edit, fixture.context)
            self.assertTrue(presented['ok'], presented)
            self.assertEqual(presented['changed_dimensions'], ['policy_presentations'])
            self.assertEqual(presented['people'][0]['subject_id'], 'owner')
            cleared = people_candidate.execute('schedule.update', self.update(presented,
                {'people': {'participants': []}}, command_id='clear-after-presentation'), fixture.context)
            self.assertTrue(cleared['ok'], cleared)
            for row in db.execute('SELECT work_instance_id FROM work_instances'):
                assert_work_instance_not_stale(db, row[0])
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')], original_work)
        finally:
            fixture.tearDown()

    def test_role_changes_do_not_change_ownership_membership_routing_or_deliver(self):
        from spine.ledger.notifications import load_current_notification_policies
        from spine.web.provisioning import apply, plan

        item = self.schedule('schedule.create', self.create(people={'participants': ['alice']}))
        state = self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()
        epoch = str(state[0]) if state else '0'
        proposed = plan(self.db, {'contract_version': 'spine.trusted-web-provisioning.v1', 'ledger_id': 'test-ledger',
            'expected_access_epoch': epoch, 'item_adoptions': [{'operation': 'create', 'item_id': item['item_id'],
                'owner_scope': {'owner_kind': 'subject', 'owner_subject_id': 'owner'}, 'expected_item_version': '1'}]})
        self.assertTrue(proposed['can_apply'], proposed)
        adopted = apply(self.db, {'contract_version': 'spine.trusted-web-provisioning.v1', 'command_id': 'adopt-people-parity',
            'actor_subject_id': 'owner', 'action_timestamp_utc': NOW, 'expected_access_epoch': epoch, 'plan': proposed})
        self.assertTrue(adopted['ok'], adopted)
        tables = ('item_access_owners', 'access_grants', 'subjects', 'subject_groups', 'subject_memberships',
                  'delivery_targets', 'ledger_access_state', 'work_instances', 'side_effect_attempts')

        def independent():
            return {table: sorted(tuple(row) for row in self.db.execute(f'SELECT * FROM {table}')) for table in tables}

        before = independent()
        self.assertTrue(before['item_access_owners'])
        self.assertTrue(before['work_instances'])
        policy_before = load_current_notification_policies(self.db, item_id=item['item_id'])
        changed = people_candidate.execute('item.people.update', {'contract_version': people_candidate.CONTRACT,
            'command_id': 'standalone-participants', 'actor_subject_id': 'owner', 'item_id': item['item_id'],
            'target_version': '1', 'updated_at_utc': NOW, 'people': {'participants': ['bob']}}, self.context)
        self.assertTrue(changed['ok'], changed)
        self.schedule('schedule.update', self.update(changed, {'people': {'participants': []}}))
        self.assertEqual(independent(), before)
        policy_after = load_current_notification_policies(self.db, item_id=item['item_id'])
        self.assertEqual([p['notification_intent_id'] for p in policy_after], [p['notification_intent_id'] for p in policy_before])
        self.assertEqual([p['recipient_subject_id'] for p in policy_after], ['owner'])
