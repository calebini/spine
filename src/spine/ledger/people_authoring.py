"""Private role-only successor primitive; callers own admission and receipts.

No public command, capability, work materialization or notification is enabled.
The existing outer command transaction and version/facet/rendering finalizers
remain the only commit boundary. Never call this as a standalone auto-commit.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.hashing import audit_log_payload_hash, command_derived_id, hash_canonical_json
from spine.core.people import (
    managed_role,
    normalize_people,
    people_id,
    replacement_is_noop,
    replacement_rows,
    subjects_needing_admission,
)
from spine.ledger import facet_continuity
from spine.ledger.common import require_utc_z
from spine.ledger.facets import load_snapshot
from spine.ledger.item_drafts import ItemVersionDraft
from spine.ledger.items import create_item_version_from_draft, mutation_audit_payload
from spine.ledger.people import PeopleSnapshot, read_people_snapshot
from spine.ledger.rendering_definitions import load_presentation
from spine.ledger.supporting import ItemSubjectRoleInput
from spine.ledger.transactions import LedgerConnection


@dataclass(frozen=True)
class PeopleMutation:
    previous_version: int
    snapshot: PeopleSnapshot
    changed: bool
    audit_id: str | None


def capture_role_edge(db: sqlite3.Connection, item_id: str, version: int) -> dict[str, Any]:
    """Reuse strict unchanged-fact capture, adding facet/presentation meaning."""
    proof = facet_continuity.capture(db, item_id, version)
    proof['people_facets'] = load_snapshot(db, item_id, version)
    for policy in proof['policies']:
        policy['meaning'] = dict(policy['meaning'],
            people_presentation=load_presentation(db, policy['policy_id']))
    return proof


def verify_role_edge(before: dict[str, Any], after: dict[str, Any], *, role: str) -> None:
    """Separate proof: exclude only the explicitly replaced managed role.

    The ordinary facet-only proof is unchanged and still requires role equality.
    Exact replacement semantics are checked by the writer before invoking this.
    """
    if role not in {'participant', 'assignee'}:
        raise SpineValidationError('environment_failure:people', 'Invalid role-only proof.')
    prior = dict(before, item_subject_roles=[r for r in before['item_subject_roles'] if r['role'] != role])
    current = dict(after, item_subject_roles=[r for r in after['item_subject_roles'] if r['role'] != role])
    try:
        facet_continuity.verify(prior, current)
    except SpineValidationError as exc:
        raise SpineValidationError('environment_failure:people', 'Role-only continuity failed.') from exc


def verify_retained_version_edge(
    db: sqlite3.Connection, *, item_id: str, previous_version: int, version: int,
    verify_copy_edge: bool = False,
) -> str:
    """Recheck a declared private people/facet edge from existing immutable facts.

    The existing indexed item/time audit and its exact version-bound payload hash
    select the owning proof, not policy semantic similarity or a broad allowlist.
    Other released mutations keep their ordinary work-reconciliation rules. This
    is read-only: no proof table, work rebinding or durable cache is introduced.
    """
    row = db.execute(
        'SELECT i.item_type,v.created_at_utc,v.created_by_subject_id FROM coordination_items i '
        'JOIN coordination_item_versions v ON v.item_id=i.item_id AND v.version=? WHERE i.item_id=?',
        (version, item_id),
    ).fetchone()
    if row is None:
        # Prospective schedule-update policies are resolved before persistence.
        return 'ordinary'
    actions = ('item_people_updated', 'item_facets_updated')
    expected = {audit_log_payload_hash(mutation_audit_payload(action=action, item_id=item_id,
        item_type=row['item_type'], previous_version=version - 1, version=version)): action for action in actions}
    audits = db.execute(
        "SELECT audit_id,action,payload_hash FROM audit_log WHERE item_id=? AND created_at_utc=? "
        "AND actor_ref=? AND stage='item' AND action IN ('item_people_updated','item_facets_updated') LIMIT 101",
        (item_id, row['created_at_utc'], row['created_by_subject_id']),
    ).fetchall()
    if len(audits) > 100:
        raise SpineValidationError('environment_failure:capacity', 'People edge audit capacity exceeded.')
    commands = db.execute(
        'SELECT DISTINCT created_by_command_id FROM notification_policies WHERE item_id=? AND version=? LIMIT 2',
        (item_id, version),
    ).fetchall()
    facet_audit = (command_derived_id(prefix='audit', command='item.facets.update', command_id=commands[0][0],
        row_role='audit', request_path='/audit') if len(commands) == 1 else None)
    # Facet command IDs bind their audit primary key to the copied policy's
    # creating command. Do not read facet content just to classify this edge:
    # legacy ordinary/revoked rendering paths must retain their no-content-read
    # boundary. Actual mixed-people proofs load snapshots only when required.
    declarations = [a['action'] for a in audits if (
        a['action'] == 'item_people_updated' and expected.get(a['payload_hash']) == a['action']
        or a['action'] == 'item_facets_updated' and a['audit_id'] == facet_audit)]
    schedule_edge = (_schedule_edge(db, commands[0][0], item_id, previous_version, version)
                     if not declarations and len(commands) == 1 else None)
    if schedule_edge:
        declarations = [schedule_edge]
    if not declarations:
        return 'ordinary'
    if len(declarations) != 1 or previous_version != version - 1:
        raise SpineValidationError('environment_failure:people', 'Invalid immediate version edge.')
    kind = {'item_facets_updated': 'facets', 'policy_presentations': 'presentations'}.get(declarations[0], 'people')
    if kind != 'people' and not verify_copy_edge:
        return kind
    before = capture_role_edge(db, item_id, previous_version)
    after = capture_role_edge(db, item_id, version)
    if kind == 'people':
        if commands:
            current = read_people_snapshot(db, item_id=item_id, version=version)
            rows = replacement_rows(item_type=current.item_type,
                subjects=tuple(r.subject_id for r in current.associations),
                command='schedule.update' if schedule_edge == 'people' else 'item.people.update', command_id=commands[0][0])
            if len(commands) != 1 or current.associations != rows:
                raise SpineValidationError('environment_failure:people', 'Invalid retained people replacement identity.')
        verify_role_edge(before, after, role=managed_role(row['item_type']))
        return 'people'
    if kind == 'facets':
        prior_facets = {e['facet_key']: {k: v for k, v in e.items() if k != 'source_command_receipt_id'}
                        for e in before['people_facets']}
        next_facets = {e['facet_key']: {k: v for k, v in e.items() if k != 'source_command_receipt_id'}
                       for e in after['people_facets']}
        changed_keys = sorted(k for k in prior_facets.keys() | next_facets.keys()
                              if prior_facets.get(k) != next_facets.get(k))
        if not any(a['audit_id'] == facet_audit
                   and a['payload_hash'] == audit_log_payload_hash({'changed_facet_keys': changed_keys}) for a in audits):
            raise SpineValidationError('environment_failure:people', 'Invalid retained facet audit evidence.')
        # Only facet values may differ; every role and presentation stays equal.
        before.pop('people_facets')
        after.pop('people_facets')
    else:
        # Only presentations may differ; facet values and all role facts stay equal.
        for proof in (before, after):
            for policy in proof['policies']:
                policy['meaning'].pop('people_presentation')
    facet_continuity.verify(before, after)
    return kind


def _schedule_edge(db: sqlite3.Connection, command_id: str, item_id: str, previous_version: int, version: int) -> str | None:
    """Existing indexed receipt evidence selects an exclusive schedule proof."""
    row = db.execute(
        "SELECT item_id,target_version,result_identity_facts_json,semantic_facts_json,semantic_facts_hash "
        "FROM command_receipts WHERE command_id=? AND command='schedule.update'", (command_id,),
    ).fetchone()
    if row is None:
        return None
    raw = (row['result_identity_facts_json'], row['semantic_facts_json'])
    if any(len(value.encode()) > 1_048_576 for value in raw):
        raise SpineValidationError('environment_failure:capacity', 'People lineage receipt capacity exceeded.')
    try:
        facts, semantic = (json.loads(value) for value in raw)
        if not isinstance(facts, dict) or not isinstance(semantic, dict):
            raise ValueError('invalid receipt object')
        dimensions = facts.get('changed_dimensions')
        if dimensions != ['policy_presentations'] and not (
            dimensions == ['people'] and semantic.get('contract_version') == 'spine.schedule-update.v4'
        ):
            return None
        if (row['item_id'] != item_id or row['target_version'] != str(previous_version)
                or facts.get('item_id') != item_id or facts.get('current_version') != str(version)
                or semantic.get('normalized_result') != facts
                or hash_canonical_json(semantic) != row['semantic_facts_hash']):
            raise ValueError('invalid schedule edge receipt')
    except (ValueError, TypeError) as exc:
        raise SpineValidationError('environment_failure:people', 'Invalid schedule edge evidence.') from exc
    return 'people' if dimensions == ['people'] else 'policy_presentations'


def replace_people(
    db: LedgerConnection, *, item_id: str, target_version: int, people: object,
    command_id: str, actor_subject_id: str, updated_at_utc: str, audit_id: str,
    admit_additions: Callable[[tuple[str, ...]], None],
) -> PeopleMutation:
    """Perform one role-only mutation inside an admitted command transaction.

    The mandatory admission callback resolves fresh additions/reactivations in
    the caller's authorized scope. It is not invoked for retained associations
    or removals. The caller must persist its canonical receipt before committing;
    replay, protected permissions and dry-run envelopes belong to that caller.
    """
    if not db.in_transaction or not db._command_transaction:
        raise RuntimeError('people mutation requires the outer command transaction')
    for identifier in (item_id, command_id, actor_subject_id, audit_id):
        people_id(identifier)
    require_utc_z('updated_at_utc', updated_at_utc)
    if type(target_version) is not int or not 1 <= target_version < 9223372036854775807:
        raise SpineValidationError('invalid_request:target_version', 'Invalid people target version.')
    snapshot = read_people_snapshot(db, item_id=item_id)
    if snapshot.current_version != target_version:
        raise SpineValidationError('stale_item_version', 'People target version is stale.')
    shell = db.execute('SELECT status FROM coordination_items WHERE item_id=?', (item_id,)).fetchone()
    table, status, expected = (('event_details', 'event_status', 'scheduled') if snapshot.item_type == 'event'
                               else ('task_details', 'task_status', 'open'))
    detail = db.execute(f'SELECT {status} FROM {table} WHERE item_id=? AND version=?',
                        (item_id, target_version)).fetchone()
    if shell is None or shell['status'] != 'active' or detail is None or detail[status] != expected:
        raise SpineValidationError('invalid_state_transition:people', 'People require an active nonterminal item.')
    subjects = normalize_people(item_type=snapshot.item_type, value=people)
    assert subjects is not None
    if replacement_is_noop(snapshot.item_type, snapshot.associations, subjects):
        return PeopleMutation(target_version, snapshot, False, None)
    additions = subjects_needing_admission(snapshot.item_type, snapshot.associations, subjects)
    if additions:
        admit_additions(additions)
    role = managed_role(snapshot.item_type)
    rows = replacement_rows(item_type=snapshot.item_type, subjects=subjects,
                            command='item.people.update', command_id=command_id)
    before = capture_role_edge(db, item_id, target_version)
    create_item_version_from_draft(db, ItemVersionDraft(
        item_id=item_id, target_version=target_version, created_at_utc=updated_at_utc,
        created_by_subject_id=actor_subject_id, audit_id=audit_id,
        subject_roles=tuple(ItemSubjectRoleInput(subject_id=r.subject_id, role=r.role,
            status=r.status, item_subject_role_id=r.item_subject_role_id) for r in rows),
        subject_role_replacement_roles=(role,), audit_action='item_people_updated',
        subject_role_copy_command='item.people.update',
        reason_code='item_people_updated',
    ), supporting_command_id=command_id)
    result = read_people_snapshot(db, item_id=item_id)
    if result.associations != rows:
        raise SpineValidationError('environment_failure:people', 'People replacement verification failed.')
    verify_role_edge(before, capture_role_edge(db, item_id, result.current_version), role=role)
    return PeopleMutation(target_version, result, True, audit_id)
