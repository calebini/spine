"""S1d: observe real allocators/commands, not a second people writer.

Existing test scenarios supply public command transactions and actual finalizers.
Selected legacy scenarios receive legal historical role fixtures at v1, so copy
tests are not vacuous empty-set proofs. No command/allocator result is mocked.
"""

import importlib
import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from spine.core.errors import SpineValidationError
from spine.core.hashing import command_derived_id
from spine.ledger import items, supporting
from spine.ledger.common import copy_id, enum_value
from spine.ledger.item_drafts import _UNSET
from tests.test_facet_writers import CASES

ROOT = Path(__file__).parents[1]
INVENTORY = json.loads((ROOT / 'src/spine/ledger/facet_writer_inventory.v1.json').read_text())
MORE_CASES = [
    ('test_facet_commands', 'FacetCommandTests', 'test_explicit_writer_retains_unchanged_seven_entries'),
    ('test_agent_command_contract_mvp', 'AgentCommandContractMvpTests', 'test_task_create_and_update_author_assignee_and_owner_roles'),
]


def rows(db, item_id, version):
    return [dict(r) for r in db.execute('SELECT * FROM item_subject_roles WHERE item_id=? AND version=? '
        'ORDER BY role COLLATE BINARY,subject_id COLLATE BINARY', (item_id, version))]


def seed_roles(db, **kwargs):
    """Historical fixture injection only; preserve the scenario's authored rows."""
    supporting.insert_supporting_sets(db, **kwargs)
    at = kwargs['default_created_at_utc']
    for suffix, kind, status in (('active', 'person', 'active'), ('inactive', 'agent', 'inactive')):
        subject = 'parity-subject-' + suffix
        db.execute('INSERT OR IGNORE INTO subjects(subject_id,subject_kind,display_name,status,created_at_utc,updated_at_utc) '
                   'VALUES (?,?,?,?,?,?)', (subject, kind, 'Parity ' + suffix, status, at, at))
        for role in ('participant', 'assignee', 'owner', 'watcher', 'recipient'):
            supporting.insert_item_subject_role(db, item_id=kwargs['item_id'], version=kwargs['version'],
                subject_role=supporting.ItemSubjectRoleInput(subject_id=subject, role=role, status=status,
                    item_subject_role_id=f"parity-{kwargs['item_id']}-{role}-{suffix}"), default_created_at_utc=at)


class PeopleWriterParityTests(unittest.TestCase):
    def test_existing_inventory_and_every_successor_use_real_role_copy_or_replacement(self):
        expected = {entry['producer_key'] for entry in INVENTORY['producers']}
        code_keys = {(str(ROOT / key.split(':')[0]), key.split(':')[1]): key for key in expected}
        visited, nonempty, observed, pending = set(), set(), [], {}
        seed = False

        def ancestry(frame):
            keys = set()
            while frame:
                key = code_keys.get((frame.f_code.co_filename, frame.f_code.co_name))
                if key:
                    keys.add(key)
                frame = frame.f_back
            return keys

        def observe(frame, event, result):
            if event == 'call':
                key = code_keys.get((frame.f_code.co_filename, frame.f_code.co_name))
                if key:
                    visited.add(key)
                if frame.f_code is items.create_item_version_from_draft.__code__:
                    db, draft = frame.f_locals['connection'], frame.f_locals['draft']
                    before = rows(db, draft.item_id, draft.target_version)
                    pending[id(frame)] = (db, draft, frame.f_locals['supporting_command_id'], before, ancestry(frame))
            elif event == 'return' and id(frame) in pending:
                db, draft, command_id, before, producers = pending.pop(id(frame))
                if not isinstance(result, items.MutatedItem):
                    return  # Refused allocations are covered by transaction tests.
                if before:
                    nonempty.update(producers)
                # Existing history must stay byte-identical, including row IDs/times.
                self.assertEqual(rows(db, draft.item_id, draft.target_version), before)
                next_version = draft.target_version + 1
                actual = rows(db, draft.item_id, next_version)
                replacement_roles = set(draft.subject_role_replacement_roles) if draft.subject_roles is not _UNSET else set()
                copied = [r for r in before if r['role'] not in replacement_roles]
                wanted = {(r['subject_id'], r['role']): dict(r, version=next_version,
                    created_at_utc=draft.created_at_utc, item_subject_role_id=(
                        command_derived_id(prefix='item_subject_role', command=draft.subject_role_copy_command,
                            command_id=command_id, row_role='item_subject_role',
                            request_path='/copy_forward/item_subject_role/' + r['item_subject_role_id'])
                        if draft.subject_role_copy_command is not None else copy_id(r['item_subject_role_id'], next_version)))
                    for r in copied}
                for row in (() if draft.subject_roles is _UNSET else draft.subject_roles):
                    value = asdict(row)
                    key = (row.subject_id, enum_value(row.role))
                    matching = next(r for r in actual if (r['subject_id'], r['role']) == key)
                    # Legacy input may intentionally allocate random IDs. New
                    # people rows always carry explicit canonical IDs, checked here.
                    wanted[key] = {'item_id': draft.item_id, 'version': next_version,
                        'subject_id': row.subject_id, 'role': enum_value(row.role), 'status': enum_value(row.status),
                        'created_at_utc': value['created_at_utc'] or draft.created_at_utc,
                        'item_subject_role_id': value['item_subject_role_id'] or matching['item_subject_role_id']}
                self.assertEqual({(r['subject_id'], r['role']): r for r in actual}, wanted)
                observed.append((draft.item_id, next_version, seed, draft.subject_role_copy_command))

        for module, cls, method in CASES + MORE_CASES:
            # Exact-output people/legacy-role witnesses already provide their own
            # nonempty rows. Other legacy writers get active+inactive historical
            # facts for every role, without changing their request JSON.
            seed = (module not in {'test_people_commands', 'test_people_authoring', 'test_ledger_item_workflows'}
                    and (module, cls, method) not in MORE_CASES[1:]) or method == 'test_task_cancellation_creates_v2'
            case = getattr(importlib.import_module('tests.' + module), cls)(method)
            with self.subTest(case=method, seeded=seed):
                try:
                    type(case).setUpClass()
                    case.setUp()
                    sys.setprofile(observe)
                    with patch('spine.ledger.items.insert_supporting_sets', seed_roles if seed else supporting.insert_supporting_sets):
                        getattr(case, method)()
                    db = case.connection if hasattr(case, 'connection') else case.db
                    self.assertFalse(db.in_transaction)
                finally:
                    sys.setprofile(None)
                    case.tearDown()
                    case.doCleanups()
        self.assertEqual(pending, {})
        self.assertEqual(visited, expected)
        successor_names = {'replace_people', '_handle_schedule_update', '_handle_schedule_cancel', '_handle_common_update',
            '_handle_event_reschedule', '_handle_reminder_create', '_handle_recurrence_instance_mutation',
            '_persist_series_edit_success', '_persist_notification_successor', '_versioned_reconcile',
            'cancel_event', 'cancel_task', 'complete_task', 'item_write'}
        self.assertTrue({key for key in expected if key.split(':')[1] in successor_names} <= nonempty)
        self.assertGreater(len(observed), 25)
        self.assertEqual({row[3] for row in observed}, {None, 'item.people.update', 'schedule.update'})

    def test_canonical_copy_requires_explicit_owner_and_legacy_default_is_unchanged(self):
        from tests.test_people_commands import PeopleCommandsTests

        case = PeopleCommandsTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.task((supporting.ItemSubjectRoleInput(subject_id='s1', role='owner', item_subject_role_id='prior'),))
        before = rows(case.db, 'task', 1)
        for command, command_id in (('task.update', 'not-people'), ('schedule.update', None)):
            with self.subTest(command=command), self.assertRaisesRegex(SpineValidationError, 'owning command'):
                items.create_next_item_version(case.db, item_id='task', target_version=1, audit_id='refused',
                    created_at_utc=before[0]['created_at_utc'], created_by_subject_id='s0',
                    subject_role_copy_command=command, supporting_command_id=command_id)
        self.assertEqual(rows(case.db, 'task', 1), before)
        self.assertEqual(case.db.execute('SELECT COUNT(*) FROM coordination_item_versions').fetchone()[0], 1)
        items.create_next_item_version(case.db, item_id='task', target_version=1, audit_id='legacy',
            created_at_utc=before[0]['created_at_utc'], created_by_subject_id='s0')
        self.assertEqual(rows(case.db, 'task', 2)[0]['item_subject_role_id'], 'prior-v2')
