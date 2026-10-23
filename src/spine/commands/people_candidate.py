"""Unadvertised trusted-local people handlers and scheduling-v4 candidate.

Not called by the dispatcher or web adapters. Protected admission, directory
pagination and public activation remain separate delivery gates. A caller must
already hold the trusted-local ledger authority; JSON cannot select that mode.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
from dataclasses import asdict, replace
from typing import Any, NoReturn

from spine.commands import core, rendering_candidate
from spine.commands.context import CommandContext
from spine.commands.facet_runtime import FacetBudget, install_budget
from spine.commands.receipts import command_receipt, get_command_receipt, insert_command_receipt
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import audit_log_payload_hash, hash_canonical_json
from spine.core.people import managed_facts, normalize_people, people_id, replacement_is_noop, replacement_rows
from spine.ledger.common import require_utc_z
from spine.ledger.items import mutation_audit_payload
from spine.ledger.people import PeopleSnapshot, read_people_snapshot
from spine.ledger.people_authoring import replace_people
from spine.ledger.transactions import LedgerConnection
from spine.services.people_authoring import PeopleAuthoring
from spine.services.rendering_authoring import RenderingAuthoring

CONTRACT = 'spine.people-and-responsibility.v1'
_FIELDS = {
    'item.people.show': {'contract_version', 'item_id', 'version'},
    'item.people.update': {'contract_version', 'command_id', 'actor_subject_id', 'item_id',
                           'target_version', 'updated_at_utc', 'people'},
}


def fail(code: str, field: str = 'people') -> NoReturn:
    raise SpineValidationError(f'{code}:{field}', 'People operation unavailable.')


def _version(value: object, field: str) -> int:
    if not isinstance(value, str) or not re.fullmatch('[1-9][0-9]*', value):
        fail('invalid_request', field)
    if len(value) > 19 or int(value) > 9223372036854775807:
        fail('invalid_request', field)
    return int(value)


def _people(value: object, field: str) -> dict[str, list[str]]:
    # Shape precedes item lookup; the item-type-specific role check comes after
    # replay/root admission, not by probing a subject or item directory here.
    if not isinstance(value, dict) or len(value) != 1 or not set(value) <= {'participants', 'assignees'}:
        fail('invalid_request', field)
    key = next(iter(value))
    ids = normalize_people(item_type='event' if key == 'participants' else 'task', value=value)
    assert ids is not None
    return {key: list(ids)}


def normalize_request(command: str, request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        fail('invalid_request', 'request')
    value = copy.deepcopy(request)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 1048576:
        fail('invalid_request', 'request')
    if command in _FIELDS:
        extras = sorted(set(value) - _FIELDS[command])
        if isinstance(value.get('people'), dict):
            extras += ['people.' + key for key in set(value['people']) - {'participants', 'assignees'}]
            extras.sort(key=lambda field: '/' + field.replace('.', '/'))
        required = _FIELDS[command] - ({'version'} if command.endswith('.show') else set())
        missing = sorted(required - set(value))
        if extras:
            fail('unsupported_field', extras[0])
        if missing:
            fail('missing_required_field', missing[0])
        if value['contract_version'] != CONTRACT:
            fail('unsupported_contract_version', 'contract_version')
        for key in sorted(set(value) & {'item_id', 'command_id', 'actor_subject_id'}):
            people_id(value[key])
        for key in ('version', 'target_version'):
            if key in value:
                _version(value[key], key)
        if 'updated_at_utc' in value:
            if not isinstance(value['updated_at_utc'], str) or not re.fullmatch(
                r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value['updated_at_utc']
            ):
                fail('invalid_request', 'updated_at_utc')
            require_utc_z('updated_at_utc', value['updated_at_utc'])
        if 'people' in value:
            value['people'] = _people(value['people'], 'people')
        return value
    if command not in {'schedule.create', 'schedule.update'}:
        fail('invalid_request', 'command')
    expected = 'spine.schedule-create.v4' if command.endswith('create') else 'spine.schedule-update.v4'
    if value.get('contract_version') != expected:
        fail('unsupported_contract_version', 'contract_version')
    creating = command.endswith('create')
    if not creating and not isinstance(value.get('patch'), dict):
        fail('invalid_request', 'patch')
    item = value.get('item') if creating else value['patch'].get('item')
    if isinstance(item, dict) and isinstance(item.get('task_detail'), dict) and 'subject_roles' in item['task_detail']:
        fail('unsupported_field', 'item.task_detail.subject_roles' if creating else 'patch.item.task_detail.subject_roles')
    if creating:
        if not isinstance(item, dict):
            fail('invalid_request', 'item')
        item_type = item.get('item_type')
        if not isinstance(item_type, str):
            fail('invalid_request', 'item.item_type')
        subjects = normalize_people(item_type=item_type, value=value['people'], creating=True) if 'people' in value else (
            normalize_people(item_type=item_type, creating=True))
        assert subjects is not None
        value['people'] = {'participants' if item_type == 'event' else 'assignees': list(subjects)}
    else:
        patch = value.get('patch')
        if not isinstance(patch, dict):
            fail('invalid_request', 'patch')
        if 'people' in patch:
            patch['people'] = _people(patch['people'], 'patch.people')
        if set(patch) == {'people'} and value.get('materialization') != {'mode': 'none'}:
            fail('invalid_request', 'materialization')
        if 'policy_presentations' in patch and (len(patch) != 1 or value.get('materialization') != {'mode': 'none'}):
            fail('invalid_request', 'patch.policy_presentations')
    result: dict[str, Any] = rendering_candidate.normalized_request(command, value)
    return result


def admit_subjects(db: LedgerConnection, subjects: tuple[str, ...]) -> None:
    """Trusted-local reference authority: exact active IDs, not inferred owners."""
    for subject in subjects:
        row = db.execute('SELECT status FROM subjects WHERE subject_id=?', (subject,)).fetchone()
        if row is None or row['status'] != 'active':
            fail('referenced_row_not_found', 'people')


def local_projection(db: LedgerConnection, snapshot: PeopleSnapshot, budget: FacetBudget) -> dict[str, Any]:
    """Current local labels; Slice 2 supplies protected per-subject disclosure."""
    subjects = []
    managed_facts(snapshot.item_type, snapshot.associations)  # Reject corrupt stored semantics.
    for subject in sorted({row.subject_id for row in snapshot.associations}):
        budget.resolve('subject', subject)
        row = db.execute('SELECT display_name,subject_kind,status FROM subjects WHERE subject_id=?', (subject,)).fetchone()
        if (row is None or not isinstance(row['display_name'], str) or not 1 <= len(row['display_name']) <= 512
                or row['subject_kind'] not in {'person', 'agent'} or row['status'] not in {'active', 'inactive'}):
            fail('environment_failure', 'people')
        subjects.append({'subject_id': subject, 'label': {'availability': 'available', **dict(row)}})
    return {'item_id': snapshot.item_id, 'item_type': snapshot.item_type, 'item_version': str(snapshot.item_version),
            'associations': [asdict(row) for row in snapshot.associations], 'subjects': subjects}


def semantic_facts(request: dict[str, Any]) -> dict[str, Any]:
    return {'derivation_version': 'spine.item-people-semantic-facts.v1',
            'canonical_json_version': 'spine.canonical-json.v1', 'request': request}


def _response(receipt: dict[str, Any], *, replay: bool = False) -> dict[str, Any]:
    facts = receipt['result_identity_facts']
    return {'ok': True, 'command': 'item.people.update', 'response_contract': CONTRACT,
            'effect': 'item_people_replay' if replay else receipt['effect'], **facts,
            'receipt': {'receipt_contract': 'spine.item-people-receipt.v1',
                        **{key: receipt[key] for key in ('command_receipt_id', 'effect', 'semantic_facts_hash', 'created_at_utc')}}}


def _stored_receipt(db: LedgerConnection, command_id: str) -> dict[str, Any] | None:
    size = db.execute('SELECT length(CAST(semantic_facts_json AS BLOB)),length(CAST(result_identity_facts_json AS BLOB)) '
                      'FROM command_receipts WHERE command_id=?', (command_id,)).fetchone()
    if size is not None and any(value > 4194304 for value in size):
        fail('environment_failure', 'receipt')
    try:
        return get_command_receipt(db, command_id)
    except (ValueError, TypeError):
        fail('environment_failure', 'receipt')


def _verify_receipt(db: LedgerConnection, command: str, request: dict[str, Any], receipt: dict[str, Any]) -> None:
    try:
        _verify_retained(db, command, request, receipt)
    except SpineValidationError as exc:
        if exc.code.startswith(('semantic_conflict:', 'environment_failure:')):
            raise
        fail('environment_failure', 'receipt')
    except (KeyError, TypeError, ValueError):
        fail('environment_failure', 'receipt')


def _verify_retained(db: LedgerConnection, command: str, request: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Refuse malformed retained evidence; do not re-author or re-admit history."""
    if receipt['command'] != command:
        fail('semantic_conflict', 'command_id')
    semantic, facts = receipt['semantic_facts'], receipt['result_identity_facts']
    if not isinstance(semantic, dict) or not isinstance(facts, dict):
        fail('environment_failure', 'receipt')
    if hash_canonical_json(semantic) != receipt['semantic_facts_hash']:
        fail('environment_failure', 'receipt')
    if command == 'item.people.update':
        if semantic != semantic_facts(request):
            fail('semantic_conflict', 'command_id')
        version = _version(facts['current_version'], 'receipt')
        snapshot = read_people_snapshot(db, item_id=request['item_id'], version=version)
        changed = receipt['effect'] == 'item_people_updated'
        expected_version = int(request['target_version']) + int(changed)
        expected_receipt_id = core._receipt_id(command, request['command_id'])
        expected_keys = {'command_id', 'command_receipt_id', 'item_id', 'item_type', 'target_version', 'current_version',
                         'truth_changed', 'work_changed', 'associations'} | ({'audit_id'} if changed else set())
        subjects = normalize_people(item_type=snapshot.item_type, value=request['people'])
        assert subjects is not None
        identities_match = (snapshot.associations == replacement_rows(item_type=snapshot.item_type,
            subjects=subjects, command=command, command_id=request['command_id']) if changed else
            replacement_is_noop(snapshot.item_type, snapshot.associations, subjects))
        if (set(facts) != expected_keys or not identities_match
                or receipt['effect'] not in {'item_people_updated', 'item_people_noop'}
                or facts['current_version'] != str(expected_version)
                or facts['command_id'] != request['command_id'] or facts['target_version'] != request['target_version']
                or facts['item_id'] != request['item_id'] or facts['item_type'] != snapshot.item_type
                or facts['truth_changed'] is not changed or facts['work_changed'] is not False
                or facts['command_receipt_id'] != expected_receipt_id or receipt['command_receipt_id'] != expected_receipt_id
                or receipt.get('item_id') != request['item_id'] or receipt.get('target_version') != request['target_version']
                or receipt['actor_subject_id'] != request['actor_subject_id']
                or receipt['action_timestamp_utc'] != request['updated_at_utc']
                or facts['associations'] != [asdict(row) for row in snapshot.associations]
                or ('audit_id' in facts) != changed):
            fail('environment_failure', 'receipt')
        if changed and facts['audit_id'] != core._derived_id(command, request['command_id'], 'audit', '/audit'):
            fail('environment_failure', 'receipt')
        if changed:
            audit = db.execute('SELECT item_id,stage,action,reason_code,actor_ref,payload_hash,created_at_utc '
                               'FROM audit_log WHERE audit_id=?', (facts['audit_id'],)).fetchone()
            payload = mutation_audit_payload(action='item_people_updated', item_id=snapshot.item_id,
                item_type=snapshot.item_type, previous_version=int(request['target_version']), version=version)
            if audit is None or tuple(audit) != (snapshot.item_id, 'item', 'item_people_updated', 'item_people_updated',
                    request['actor_subject_id'], audit_log_payload_hash(payload), request['updated_at_utc']):
                fail('environment_failure', 'receipt')
    else:
        # Existing schedule replay owns normalization/environment facts. Verify
        # its retained people evidence at the original version, never current.
        if semantic.get('contract_version') != request['contract_version']:
            fail('semantic_conflict', 'command_id')
        if (facts.get('item_id') != receipt.get('item_id')
                or semantic.get('normalized_result') != facts):
            fail('environment_failure', 'receipt')
        snapshot = read_people_snapshot(db, item_id=facts['item_id'], version=_version(facts['current_version'], 'receipt'))
        if facts.get('people') != [asdict(row) for row in snapshot.associations]:
            fail('environment_failure', 'receipt')


def _update(db: LedgerConnection, request: dict[str, Any]) -> dict[str, Any]:
    command = 'item.people.update'
    existing = _stored_receipt(db, request['command_id'])
    if existing:
        _verify_receipt(db, command, request, existing)
        return _response(existing, replay=True)
    # Actor is an audit reference, not a fresh managed selection. Preserve the
    # ordinary local actor-existence rule without inventing an active-actor rule.
    if db.execute('SELECT 1 FROM subjects WHERE subject_id=?', (request['actor_subject_id'],)).fetchone() is None:
        fail('referenced_row_not_found', 'actor_subject_id')
    result = replace_people(db, item_id=request['item_id'], target_version=int(request['target_version']),
        people=request['people'], command_id=request['command_id'], actor_subject_id=request['actor_subject_id'],
        updated_at_utc=request['updated_at_utc'], audit_id=core._derived_id(command, request['command_id'], 'audit', '/audit'),
        admit_additions=lambda subjects: admit_subjects(db, subjects))
    facts = {'command_id': request['command_id'], 'command_receipt_id': core._receipt_id(command, request['command_id']),
             'item_id': request['item_id'], 'item_type': result.snapshot.item_type,
             'target_version': request['target_version'], 'current_version': str(result.snapshot.item_version),
             'truth_changed': result.changed, 'work_changed': False,
             'associations': [asdict(row) for row in result.snapshot.associations]}
    if result.audit_id:
        facts['audit_id'] = result.audit_id
    receipt = command_receipt(command=command, command_id=request['command_id'], actor_subject_id=request['actor_subject_id'],
        action_timestamp_utc=request['updated_at_utc'], effect='item_people_updated' if result.changed else 'item_people_noop',
        item_id=request['item_id'], target_version=request['target_version'],
        semantic_facts=semantic_facts(request), result_identity_facts=facts)
    insert_command_receipt(db, receipt)
    _verify_receipt(db, command, request, receipt)
    return _response(receipt)


class _Preview(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result


def execute(command: str, request: Any, context: CommandContext) -> dict[str, Any]:
    """Execute a private local candidate, preserving actual transaction ownership."""
    db, budget, old_timeout = context.ledger, FacetBudget(), None
    try:
        if (not isinstance(db, LedgerConnection) or not getattr(db, '_renderings_enabled', False)
                or db.in_transaction or context.transport_metadata or context.people_authoring):
            fail('environment_failure', 'admission')
        value = normalize_request(command, request)
        old_timeout = install_budget(db, budget)
        result: dict[str, Any]
        with db.atomic_command(write=command != 'item.people.show'):
            if command == 'item.people.show':
                snapshot = read_people_snapshot(db, item_id=value['item_id'],
                    version=int(value['version']) if 'version' in value else None)
                result = {'ok': True, 'command': command, 'response_contract': CONTRACT,
                          'current_version': str(snapshot.current_version), 'people': local_projection(db, snapshot, budget)}
            elif command == 'item.people.update':
                result = _update(db, value)
            else:
                # No protected adapter is wired to this private local path. The
                # successor protected service must supply its own owner/receipt
                # admission and release fences before activation.
                authoring = PeopleAuthoring(db, command, value, lambda subjects: admit_subjects(db, subjects))
                rendering = RenderingAuthoring(db, command, value, None, budget)
                handler = core._handle_schedule_create if command == 'schedule.create' else core._handle_schedule_update
                prior = _stored_receipt(db, value['command_id'])
                if prior:
                    _verify_receipt(db, command, value, prior)
                result = handler(value, replace(context, people_authoring=authoring, rendering_authoring=rendering))
                if not result['ok']:
                    raise _Preview(result)
                if not prior:
                    authoring.verify_successor(result['item_id'], int(result['current_version']))
                    rendering.verify_successor(result['item_id'], int(result['current_version']))
            budget.check()
            if len(canonical_json_bytes(result)) > 4194304:
                fail('environment_failure', 'capacity')
            if context.dry_run and command != 'item.people.show':
                db._finalize_pending()
                raise _Preview(result)
        return result
    except _Preview as preview:
        return preview.result | ({'dry_run': True} if context.dry_run else {})
    except (SpineValidationError, sqlite3.Error, ValueError, TypeError, KeyError, UnicodeError) as exc:
        if isinstance(exc, SpineValidationError):
            code, _, field = exc.code.partition(':')
            code = {'stale_item_version': 'stale_version', 'capacity_exceeded': 'environment_failure',
                    'command_id_reuse': 'semantic_conflict', 'incompatible_replay': 'semantic_conflict'}.get(code, code)
        elif isinstance(exc, sqlite3.IntegrityError):
            code, field = 'semantic_conflict', 'request'
        elif isinstance(exc, sqlite3.Error):
            code, field = 'environment_failure', 'capacity'
        else:
            code, field = 'invalid_request', 'request'
        if code not in {'invalid_request', 'unsupported_field', 'missing_required_field', 'unsupported_contract_version',
                        'wrong_item_type', 'invalid_state_transition', 'referenced_row_not_found', 'stale_version',
                        'semantic_conflict', 'environment_failure', 'runtime_failure'}:
            code = 'invalid_request'
        message = {'invalid_request': 'Invalid people request.', 'unsupported_field': 'Invalid people request.',
                   'missing_required_field': 'Invalid people request.', 'unsupported_contract_version': 'Invalid people request.',
                   'referenced_row_not_found': 'People reference unavailable.', 'stale_version': 'People version changed.',
                   'semantic_conflict': 'People command conflicts.'}.get(code, 'People operation unavailable.')
        return {'ok': False, 'command': command, 'error': {'code': code, 'field': field or 'people', 'message': message},
                **({'dry_run': True} if context.dry_run else {})}
    finally:
        if old_timeout is not None:
            assert isinstance(db, LedgerConnection)
            db.set_progress_handler(None, 0)
            db.execute(f'PRAGMA busy_timeout={old_timeout}')
