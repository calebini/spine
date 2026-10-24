"""Atomic private protected scheduling-v4 and people admission/receipt integration."""

import copy
import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.commands.people_runtime import API
from spine.core import rendering_definitions as rendering_codec
from spine.core.errors import SpineValidationError
from spine.services.rendering_authoring import RenderingAuthoring
from tests import test_people_web as helper
from tests.facet_storage_support import DEFINITION

AT, GROUP = helper.AT, helper.GROUP


class PeopleScheduleIntegrationTests(unittest.TestCase):
    setUpClass = helper.PeopleWebTests.__dict__['setUpClass']
    setUp = helper.PeopleWebTests.setUp
    service_with, subject, group, run_command, denied = (helper.PeopleWebTests.service_with, helper.PeopleWebTests.subject,
        helper.PeopleWebTests.group, helper.PeopleWebTests.run_command, helper.PeopleWebTests.denied)

    def epoch(self):
        return str(self.db.execute('SELECT access_epoch FROM ledger_access_state').fetchone()[0])

    def create_body(self, *, group=False, people=None, command_id='schedule-people', materialize=False):
        body = self.h.event(command_id)
        body['contract_version'] = API
        request = body['request']
        request['contract_version'] = 'spine.schedule-create.v4'
        if not materialize:
            request['materialization'] = {'mode': 'none'}
        if people is not None:
            request['people'] = {'participants': people}
        if group:
            body['create_owner_scope'] = GROUP
            request['delivery'] = {'recipient_kind': 'subject_group', 'recipient_group_id': 'group', 'channel': 'whatsapp',
                                   'target': {'resolution': 'explicit', 'delivery_target_id': 'group-route'}}
        body['expected_access_epoch'] = self.epoch()
        return body

    def group_route(self):
        self.group()
        response = handle('delivery_target.upsert', {'command_id': 'group-route', 'actor_subject_id': 'owner',
            'delivery_target_id': 'group-route', 'owner_kind': 'subject_group', 'owner_group_id': 'group',
            'channel': 'whatsapp', 'adapter_name': 'openclaw', 'target_ref': 'test-only-group', 'updated_at_utc': AT}, self.h.ctx)
        self.assertTrue(response['ok'], response)

    def update(self, created, patch, **kwargs):
        return {'contract_version': API, 'expected_access_epoch': self.epoch(), 'request': {
            'contract_version': 'spine.schedule-update.v4', 'command_id': 'update-people', 'actor_subject_id': 'owner',
            'item_id': created['item_id'], 'target_version': created['current_version'], 'updated_at_utc': AT,
            'patch': patch, 'materialization': {'mode': 'none'}, **kwargs}}

    def test_private_owner_create_one_atomic_owner_people_policy_and_receipt(self):
        body = self.create_body(people=['owner'])
        epoch = int(self.epoch())
        result = self.run_command('schedule.create', body)['result']
        self.assertEqual([row['subject_id'] for row in result['people']], ['owner'])
        self.assertEqual(result['phases']['delivery'], 'not_attempted')
        self.assertEqual(int(self.epoch()), epoch + 1)
        self.assertEqual(self.db.execute('SELECT owner_subject_id FROM item_access_owners WHERE item_id=?',
                                         (result['item_id'],)).fetchone()[0], 'owner')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM command_receipts WHERE command='schedule.create'").fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)
        before = '\n'.join(self.db.iterdump())
        replay = self.run_command('schedule.create', body)['result']
        self.assertEqual(replay['people'], result['people'])
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_cross_subject_fresh_add_denied_without_partial_item_or_owner(self):
        self.denied('resource_unavailable', 'schedule.create', self.create_body(people=['other']))

    def test_group_people_create_and_people_only_update_preserve_work(self):
        self.group_route()
        result = self.run_command('schedule.create', self.create_body(group=True, people=['other'], materialize=True))['result']
        work = [tuple(r) for r in self.db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')]
        self.assertTrue(work)
        changed = self.run_command('schedule.update', self.update(result, {'people': {'participants': ['owner', 'other']}}))['result']
        self.assertEqual(changed['changed_dimensions'], ['people'])
        self.assertEqual(changed['current_version'], '2')
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM work_instances ORDER BY work_instance_id')], work)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM side_effect_attempts').fetchone()[0], 0)

    def test_mixed_item_and_people_update_creates_one_version(self):
        self.group_route()
        created = self.run_command('schedule.create', self.create_body(group=True, people=['owner']))['result']
        body = self.update(created, {'item': {'title': 'Changed title'}, 'people': {'participants': ['other']}})
        changed = self.run_command('schedule.update', body)['result']
        self.assertEqual(changed['changed_dimensions'], ['item', 'people'])
        self.assertEqual(changed['current_version'], '2')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM coordination_item_versions WHERE item_id=?',
                                         (created['item_id'],)).fetchone()[0], 2)

    def test_owner_and_people_creation_roll_back_on_failed_release(self):
        self.group_route()
        body = self.create_body(group=True, people=['other'])
        def revoke(db):
            db.execute("UPDATE subject_memberships SET status='ended',ends_at_utc=? WHERE subject_id='other'", (AT,))
        self.denied('access_changed', 'schedule.create', body, service=self.service_with(before_release=revoke))

    def test_replay_retains_original_people_after_newer_version_and_lost_fresh_reference(self):
        self.group_route()
        body = self.create_body(group=True, people=['other'])
        created = self.run_command('schedule.create', body)['result']
        self.run_command('schedule.update', self.update(created, {'people': {'participants': []}}))
        with self.db:
            self.db.execute("UPDATE subjects SET status='inactive' WHERE subject_id='other'")
        before = '\n'.join(self.db.iterdump())
        replay = self.run_command('schedule.create', body)['result']
        self.assertEqual(replay['people'], created['people'])
        self.assertEqual(replay['current_version'], '1')
        self.assertEqual('\n'.join(self.db.iterdump()), before)
        changed = copy.deepcopy(body)
        changed['request']['people']['participants'] = []
        self.denied('domain_conflict', 'schedule.create', changed)

    def test_update_omission_keeps_people_and_legacy_role_input_remains_closed(self):
        created = self.run_command('schedule.create', self.create_body(people=['owner']))['result']
        changed = self.run_command('schedule.update', self.update(created, {'item': {'title': 'Updated'}}))['result']
        self.assertEqual([row['subject_id'] for row in changed['people']], ['owner'])
        self.assertNotIn('people', changed['changed_dimensions'])
        body = self.create_body(command_id='legacy-input')
        body['request']['item'] = {'item_type': 'task', 'title': 'Task', 'task_detail': {
            'task_status': 'open', 'priority': 'normal', 'subject_roles': []}}
        self.denied('invalid_request', 'schedule.create', body)

    def rendering_selection(self):
        scope = {'owner_kind': 'subject', 'owner_subject_id': 'owner'}
        def local(command, **request):
            value = handle(command, {'command_id': command + '-fixture', 'actor_subject_id': 'owner',
                'action_timestamp_utc': AT, **request}, self.h.ctx)
            self.assertTrue(value['ok'], value)
            return value
        schema = local('facet_schema.create', contract_version='spine.facet-schemas.v1', owner=scope,
                       schema_key='flight', definition=DEFINITION)
        definition = local('notification_rendering_definition.create', contract_version=rendering_codec.DEFINITIONS,
            owner=scope, definition_key='flight', revision={
                'display_name': 'Flight', 'description': None, 'compatible_item_types': ['event'],
                'base_rendering_contract': 'spine.notification-rendering.v1',
                'base_rendering_profile': 'spine.notification-rendering.concise-en-ca.v1', 'selections': [{
                    'selection_key': 'flight', 'facet_key': 'flight', 'facet_schema_revision_id': schema['facet_schema_revision_id'],
                    'field_key': 'flight', 'projection': 'value', 'label': 'Flight'}]})['record']
        ref = {k: definition[k] for k in ('notification_rendering_definition_id', 'notification_rendering_definition_revision_id')}
        disclosure = local('notification_rendering_disclosure.provision', contract_version=rendering_codec.DISCLOSURES,
            scope={'item_owner': scope, 'definition': ref, 'approved_selection_keys': ['flight'],
                'use_scope': {'kind': 'direct_policy'}, 'destination': {
                    'recipient': {'kind': 'subject', 'subject_id': 'owner'}, 'delivery_target_id': 'whatsapp-owner',
                    'channel': 'whatsapp', 'adapter_name': 'openclaw', 'destination_source': 'delivery_target', 'target_ref': 'test-only'},
                'permitted_location_ids': []})['record']
        return {'kind': 'definition', 'definition': ref, 'effective_selection_keys': ['flight'],
                'authorization': {'resolution': 'exact', 'disclosure_authorization_id': disclosure['disclosure_authorization_id']}}

    def test_definition_selection_and_explicit_owner_commit_with_people(self):
        selection = self.rendering_selection()
        body = self.create_body(people=['owner'])
        body['request']['notification_plan']['rendering_applications'] = [
            {'source_kind': 'custom_addition', 'source_key': 'countdown', 'selection': selection}]
        result = self.run_command('schedule.create', body)['result']
        self.assertEqual(result['policies'][0]['presentation']['kind'], 'definition')
        self.assertEqual(result['policies'][0]['presentation']['disclosure_authorization_id'],
                         selection['authorization']['disclosure_authorization_id'])
        self.assertEqual(len(result['people']), 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notification_rendering_disclosures').fetchone()[0], 1)
        before = '\n'.join(self.db.iterdump())
        replay = self.run_command('schedule.create', body)['result']
        self.assertEqual(result['policies'], replay['policies'])
        self.assertEqual('\n'.join(self.db.iterdump()), before)

    def test_failure_after_owner_insert_but_before_receipt_rolls_back_everything(self):
        body = self.create_body(people=['owner'], materialize=True)
        with patch.object(RenderingAuthoring, 'persist', side_effect=SpineValidationError(
                'environment_failure:rendering', 'Injected failure after protected owner insert')):
            self.denied('domain_failure', 'schedule.create', body)

    def test_equal_people_update_is_noop_with_original_association_ids(self):
        created = self.run_command('schedule.create', self.create_body(people=['owner']))['result']
        body = self.update(created, {'people': {'participants': ['owner']}})
        result = self.run_command('schedule.update', body)['result']
        self.assertEqual(result['changed_dimensions'], [])
        self.assertEqual(result['current_version'], '1')
        self.assertEqual(result['people'], created['people'])

    def test_task_assignees_create_and_clear_through_same_protected_owner_boundary(self):
        body = self.create_body(people=None)
        body['request']['item'] = {'item_type': 'task', 'title': 'Assigned task', 'task_detail': {'priority': 'normal'}}
        body['request']['people'] = {'assignees': ['owner']}
        created = self.run_command('schedule.create', body)['result']
        self.assertEqual(created['people'][0]['role'], 'assignee')
        changed = self.run_command('schedule.update', self.update(created, {'people': {'assignees': []}}))['result']
        self.assertEqual(changed['changed_dimensions'], ['people'])
        self.assertEqual(changed['people'], [])
