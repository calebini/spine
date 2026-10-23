"""Private protected people candidate; deliberately absent from HTTP/registries.

Uses the canonical local mutation's transaction body, but never its trusted-local
admission path. Source-only contracts must be explicitly supplied by the caller.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from spine.commands import people_candidate
from spine.commands.facet_runtime import install_budget, utc_now, wire_time
from spine.commands.people_runtime import API, CONTRACT, PeopleBudget, PeopleContracts, PeopleCursorCodec, PeopleCursorConfig
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.services.people_directory import PeopleDirectory, decimal_facts
from spine.services.people_reads import assemble, authorization, ledger_instance, page_roster
from spine.web.errors import WebError
from spine.web.permissions import owner
from spine.web.read_authorization import ReadPermissions, authorization_deadline
from spine.web.read_cursor import cursor_identity
from spine.web.service import WebService, _id

COMMANDS = frozenset({'people.list', 'item.people.show', 'item.people.update'})


def domain_error(exc):
    code, _, field = exc.code.partition(':')
    if code == 'environment_failure' and field == 'cursor_config':
        return WebError('admission_unavailable')
    if code in {'capacity_exceeded'} or code == 'environment_failure' and field == 'capacity':
        return WebError('capacity_exceeded')
    if code == 'referenced_row_not_found':
        return WebError('resource_unavailable')
    if code in {'stale_item_version', 'stale_version'}:
        return WebError('version_changed', 409)
    if code == 'stale_cursor':
        return WebError('access_changed')
    if code in {'semantic_conflict', 'command_id_reuse', 'incompatible_replay'}:
        return WebError('domain_conflict')
    if code in {'wrong_item_type', 'invalid_state_transition', 'environment_failure'}:
        return WebError('domain_failure')
    return WebError('invalid_request')


def principal(db, p, selection):
    subject = dict(db.execute('SELECT * FROM subjects WHERE subject_id=?', (p.subject,)).fetchone())
    value = cursor_identity({**p.identity, 'subject': subject, 'selection_id': selection})
    return {k: v for k, v in value.items() if k != 'ledger_id'}


def permission_proof(db, p, budget):
    """Only resources actually consulted; never hash other people's metadata."""
    checks, grants, groups = [], [], set()
    for kind, identity, operation in sorted(p.checked):
        if kind != 'item':
            raise WebError('admission_unavailable')
        row = dict(db.execute('SELECT * FROM item_access_owners WHERE item_id=?', (identity,)).fetchone())
        budget.resolve('item', identity)
        checks.append({'item_id': identity, 'operation': operation, 'owner': row})
        if row['owner_kind'] == 'subject_group' and row['owner_group_id'] in p.groups:
            groups.add(row['owner_group_id'])
    for identity in sorted(p.matched_grants):
        row = dict(db.execute('SELECT * FROM access_grants WHERE grant_id=?', (identity,)).fetchone())
        operations = [dict(r) for r in db.execute(
            'SELECT * FROM access_grant_operations WHERE grant_id=? AND revision=? ORDER BY operation LIMIT 101',
            (identity, row['current_revision']),
        )]
        if len(operations) > 100:
            raise WebError('capacity_exceeded')
        grants.append({'grant': row, 'operations': operations})
        if row['grantee_group_id'] is not None:
            groups.add(row['grantee_group_id'])
    memberships = []
    for group in sorted(groups):
        rows = db.execute(
            "SELECT * FROM subject_memberships WHERE group_id=? AND status='active' AND subject_id=? "
            'AND starts_at_utc<=? ORDER BY membership_id LIMIT 2', (group, p.subject, p.now),
        ).fetchall()
        if len(rows) != 1:
            raise WebError('domain_failure')
        memberships.append({'membership': dict(rows[0]), 'group': dict(db.execute(
            'SELECT group_id,status FROM subject_groups WHERE group_id=?', (group,)).fetchone())})
    if len(checks) + len(grants) + sum(len(g['operations']) for g in grants) + len(memberships) > 100:
        raise WebError('capacity_exceeded')
    return decimal_facts({'items': checks, 'grants': grants, 'memberships': memberships})


class PeopleService:
    def __init__(self, config, *, contracts: PeopleContracts, cursor_config=None,
                 now=None, before_release=None):
        self.base, self.config, self.contracts = WebService(config), config, contracts
        self.cursor_config, self.now = cursor_config, now or (lambda: wire_time(utc_now()))
        self.before_release = before_release

    def admit(self, db, account, selection, budget):
        self.base.preflight(db)
        p = ReadPermissions(db, account, self.now())
        directory = PeopleDirectory(db, budget, observed_at_utc=p.now, subject=p.subject)
        identity = principal(db, p, selection)
        return p, directory, identity

    def proof(self, db, p, directory, identity, budget):
        snapshot = SimpleNamespace(permissions=p, db=db, budget=budget, evaluated_at_utc=p.now)
        # All these item probes are mandatory core probes, never optional sections.
        deadline = authorization_deadline(snapshot) if p.checked else None
        facts = permission_proof(db, p, budget)
        count = (len(facts['items']) + len(facts['grants']) + len(facts['memberships']) + len(directory.proofs)
                 + sum(len(row['operations']) for row in facts['grants']) + 5)
        if count > 100:
            raise WebError('capacity_exceeded')
        return authorization(directory, identity, permission_proofs=facts, valid_until=deadline)

    def response(self, command, result, identity, budget):
        value = {'contract_version': API, 'ok': True, 'identity_basis': 'self_selected',
                 **{k: identity[k] for k in ('account_id', 'subject_id', 'selection_id', 'account_revision',
                                            'subject_revision', 'account_subject_binding_revision', 'access_epoch')},
                 'result_contract': CONTRACT, 'result': result}
        self.contracts.validate('web-responses', value, definition=command, output=True)
        if len(canonical_json_bytes(value)) > 4194304:
            raise WebError('capacity_exceeded')
        budget.check()
        return value

    def execute(self, command, body, account, selection, *, current_selection=None):
        if command not in COMMANDS:
            raise WebError('operation_unavailable')
        budget = PeopleBudget(maximum_steps=self.config.sql_steps, maximum_seconds=self.config.request_seconds)
        db = None
        timeout = None
        try:
            if len(canonical_json_bytes(body)) > 1048576:
                raise WebError('invalid_request')
            budget.check()
            self.contracts.validate('web-requests', body, definition=command)
            budget.check()
            request = people_candidate.normalize_request(command, body['request'])
            if not _id(account) or not _id(selection):
                raise WebError('identity_unavailable')
            selected = current_selection if current_selection is not None else (lambda: (account, selection))
            if selected() != (account, selection):
                raise WebError('identity_unavailable')
            db = self.base.connection()
            timeout = install_budget(db, budget)
            db.set_progress_handler(budget.progress, min(100, budget.maximum_steps))
            if command == 'item.people.update':
                return self.write(db, request, body, account, selection, selected, budget)
            # Both evaluation and release are read-only transactions. The fresh
            # transaction is not permitted to retry and silently choose new facts.
            db.execute('PRAGMA query_only=ON')
            with db.atomic_command(write=False):
                p, directory, identity = self.admit(db, account, selection, budget)
                codec, previous = None, None
                if command == 'people.list':
                    if not isinstance(self.cursor_config, PeopleCursorConfig):
                        raise WebError('admission_unavailable')
                    codec = PeopleCursorCodec(self.contracts, self.cursor_config)
                    if ledger_instance(directory) != codec.config.ledger_instance_id:
                        raise WebError('admission_unavailable')
                    previous = codec.decode(request['cursor'], now=p.now) if 'cursor' in request else None
                    directory.scope(request['owner'])
                else:
                    budget.resolve('item', request['item_id'])
                    p.item(request['item_id'])  # Authority before version/association existence.
                if body.get('expected_access_epoch', identity['access_epoch']) != identity['access_epoch']:
                    raise WebError('access_changed')
                result, source = assemble(command, request, directory)
                access, deadline = self.proof(db, p, directory, identity, budget)
                if codec is not None:
                    result = page_roster(result, codec=codec, request=request, source_hash=source, authorization_hash=access,
                                         valid_until=deadline, identity=identity,
                                         guards=body, previous=previous)
                response = self.response(command, result, identity, budget)
            if self.before_release:
                self.before_release(db)
            if selected() != (account, selection):
                raise WebError('access_changed')
            if codec is not None and self.cursor_config != codec.config:
                raise WebError('access_changed')
            with db.atomic_command(write=False):
                try:
                    fresh, current, fresh_identity = self.admit(db, account, selection, budget)
                    if command == 'item.people.show':
                        fresh.item(request['item_id'])
                    _, fresh_source = assemble(command, request, current)
                    fresh_access, fresh_deadline = self.proof(db, fresh, current, fresh_identity, budget)
                except WebError as exc:
                    if exc.code in {'identity_unavailable', 'resource_unavailable'}:
                        raise WebError('access_changed') from exc
                    raise
                except SpineValidationError as exc:
                    if exc.code.startswith('referenced_row_not_found:'):
                        raise WebError('access_changed') from exc
                    raise
                if (fresh_identity != identity or fresh_source != source or fresh_access != access or deadline != fresh_deadline
                        or current.now < directory.now or deadline is not None and current.now >= deadline):
                    raise WebError('access_changed')
                if previous is not None:
                    codec.times(previous, current.now)
                if selected() != (account, selection):
                    raise WebError('access_changed')
                budget.check()
            return response
        except SpineValidationError as exc:
            raise domain_error(exc) from exc
        except sqlite3.IntegrityError as exc:
            raise WebError('domain_conflict') from exc
        except sqlite3.Error as exc:
            raise WebError('capacity_exceeded' if 'locked' in str(exc) or 'interrupt' in str(exc) else 'admission_unavailable') from exc
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            raise WebError('invalid_request' if db is None else 'domain_failure') from exc
        finally:
            if db is not None:
                db.set_progress_handler(None, 0)
                if timeout is not None:
                    db.execute(f'PRAGMA busy_timeout={timeout}')
                db.close()

    def write(self, db, request, body, account, selection, selected, budget):
        with db.atomic_command(write=True):
            p, directory, identity = self.admit(db, account, selection, budget)
            admitted, replayed, target = [], False, None

            def before_fresh():
                nonlocal target
                if request['actor_subject_id'] != p.subject:
                    raise WebError('identity_unavailable')
                budget.resolve('item', request['item_id'])
                target = owner(p.item(request['item_id'], edit=True))
                if body['expected_access_epoch'] != identity['access_epoch']:
                    raise WebError('access_changed')

            def before_replay(receipt):
                nonlocal replayed
                link = db.execute('SELECT * FROM web_receipt_links WHERE command_id=?', (request['command_id'],)).fetchone()
                if (link is None or link['account_id'] != account or link['subject_id'] != p.subject
                        or link['api_version'] != API or link['registry_version'] != CONTRACT
                        or link['command_receipt_id'] != receipt['command_receipt_id']
                        or request['actor_subject_id'] != p.subject):
                    raise WebError('command_id_unavailable')
                if not isinstance(receipt.get('item_id'), str):
                    raise WebError('domain_failure')
                p.item(receipt['item_id'])
                replayed = True

            def admit_additions(subjects):
                directory.admit(subjects, owner=target)
                admitted.extend(subjects)

            result = people_candidate._update(db, request, before_fresh=before_fresh,
                before_replay=before_replay, admit_additions=admit_additions)
            access, deadline = self.proof(db, p, directory, identity, budget)
            if not replayed:
                db.execute("INSERT INTO web_receipt_links VALUES(?,?,?,?,?,?,'self_selected',?,?,?,NULL,NULL,NULL,?)", (
                    result['command_receipt_id'], request['command_id'], account, p.subject,
                    p.identity['binding_id'], p.identity['binding_revision'], p.identity['access_epoch'], API, CONTRACT,
                    hash_canonical_json({'api_version': API, 'request': request, 'account_id': account, 'subject_id': p.subject}),
                ))
            response = self.response('item.people.update', result, identity, budget)
            if self.before_release:
                self.before_release(db)
            if selected() != (account, selection):
                raise WebError('access_changed')
            try:
                fresh, current, fresh_identity = self.admit(db, account, selection, budget)
                fresh.item(request['item_id'], edit=not replayed)
                if admitted:
                    current.admit(tuple(admitted), owner=target)
                fresh_access, fresh_deadline = self.proof(db, fresh, current, fresh_identity, budget)
                if (identity != fresh_identity or access != fresh_access or deadline != fresh_deadline
                        or current.now < directory.now or deadline is not None and current.now >= deadline):
                    raise WebError('access_changed')
            except WebError as exc:
                if exc.code in {'identity_unavailable', 'resource_unavailable'}:
                    raise WebError('access_changed') from exc
                raise
            except SpineValidationError as exc:
                if exc.code.startswith('referenced_row_not_found:'):
                    raise WebError('access_changed') from exc
                raise
            if selected() != (account, selection):
                raise WebError('access_changed')
            budget.check()
        return response
