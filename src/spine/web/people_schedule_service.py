"""Private atomic scheduling-v4 adapter with scoped people/rendering admission."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from spine.commands import core, people_candidate
from spine.commands.context import CommandContext
from spine.commands.facet_runtime import install_budget
from spine.commands.people_runtime import API, CONTRACT, PeopleBudget
from spine.commands.rendering_runtime import RenderingPermissions
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import command_derived_id, hash_canonical_json
from spine.services.people_authoring import PeopleAuthoring
from spine.services.people_directory import PeopleDirectory
from spine.services.rendering_authoring import RenderingAuthoring
from spine.web.errors import WebError
from spine.web.history import record
from spine.web.people_service import domain_error, principal
from spine.web.permissions import owner
from spine.web.read_authorization import ReadPermissions
from spine.web.service import _id


class PeopleSchedulePermissions(RenderingPermissions, ReadPermissions):
    """Rendering predicates plus the independent owner's tracked item predicates."""

    def __init__(self, db, account, now, budget, *, prospective=None):
        super().__init__(db, account, now, budget)
        self.prospective = prospective

    def prospective_owner_for(self, item_id):
        if self.prospective is None or item_id != self.prospective['item_id'] or not self.scope(self.prospective):
            return None
        return self.prospective

    def item(self, item_id, *, edit=False):
        if self.db.execute('SELECT 1 FROM item_access_owners WHERE item_id=?', (item_id,)).fetchone() is None:
            planned = self.prospective_owner_for(item_id)
            if planned is not None:
                self.touch('item', item_id, 'edit' if edit else 'read')
                self.remember('item', item_id, {'edit': edit})
                self.checked.add(('item', item_id, 'edit' if edit else 'read'))
                return planned
        return super().item(item_id, edit=edit)

    def rendering(self, identity, *, use=False, admin=False):
        result = super().rendering(identity, use=use, admin=admin)
        operation = 'admin' if admin else 'use' if use else 'read'
        self.checked.add(('notification_rendering_definition', identity, operation))
        self.remember('notification_rendering_definition', identity, {'use': use, 'admin': admin})
        return result

    def schema(self, revision_id, *, use=False):
        super().schema(revision_id, use=use)
        identity = self.db.execute('SELECT facet_schema_id FROM facet_schema_revisions WHERE facet_schema_revision_id=?',
                                   (revision_id,)).fetchone()[0]
        self.checked.add(('facet_schema', identity, 'use' if use else 'read'))
        self.remember('facet_schema', identity, {'use': use})


class ProtectedScheduleRendering(RenderingAuthoring):
    def __init__(self, db, command, request, permissions, budget, *, create_scope=None):
        super().__init__(db, command, request, permissions, budget)
        self.create_scope, self.owner_created = create_scope, False

    def persist(self, item_id, version):
        if self.command == 'schedule.create' and not self.owner_created:
            scope, p, request = self.create_scope, self.permissions, self.request
            identity = command_derived_id(prefix='item_access_owner', command='schedule.create', command_id=request['command_id'],
                                          row_role='item_access_owner', request_path='/create_owner_scope')
            self.db.execute('INSERT INTO item_access_owners VALUES(?,?,1,?,?,?,?,?)', (
                item_id, identity, scope['owner_kind'], scope.get('owner_subject_id'), scope.get('owner_group_id'),
                p.subject if scope['owner_kind'] == 'subject_group' else None, request['command_id']))
            record(self.db, 'owner', identity, p.subject, request['created_at_utc'],
                   core._receipt_id('schedule.create', request['command_id']))
            self.db.execute('UPDATE ledger_access_state SET access_epoch=access_epoch+1')
            p.identity['access_epoch'] += 1
            self.owner_created = True
        super().persist(item_id, version)


def _recheck(db, original, account, now, budget):
    fresh = PeopleSchedulePermissions(db, account, now, budget)
    for kind, identity, operation in sorted(original.checked):
        if kind == 'item':
            fresh.item(identity, edit=operation == 'edit')
        elif kind == 'route':
            fresh.route(identity, release_owner=original.release_scopes.get(identity))
        elif kind == 'notification_rendering_definition':
            fresh.rendering(identity, use=operation == 'use', admin=operation == 'admin')
        elif kind == 'facet_schema':
            revision = db.execute('SELECT current_revision_id FROM facet_schemas WHERE facet_schema_id=?', (identity,)).fetchone()
            # The permission check uses the root, not whichever current definition
            # happens to be installed. An exact historical revision stays pinned.
            if revision is None:
                raise WebError('resource_unavailable')
            row = db.execute('SELECT facet_schema_revision_id FROM facet_schema_revisions WHERE facet_schema_id=? '
                             'ORDER BY facet_schema_revision_id LIMIT 1', (identity,)).fetchone()
            fresh.schema(row[0], use=operation == 'use')
        else:
            fresh.catalog(kind, identity, use=operation == 'use')
    return fresh


def execute_schedule(service, command, body, account, selection, *, current_selection=None):
    budget = PeopleBudget(maximum_steps=service.config.sql_steps, maximum_seconds=service.config.request_seconds)
    db, timeout = None, None
    selected = current_selection if current_selection is not None else (lambda: (account, selection))
    try:
        if len(canonical_json_bytes(body)) > 1048576:
            raise WebError('invalid_request')
        service.contracts.validate('web-requests', body, definition=command)
        request = people_candidate.normalize_request(command, body['request'])
        if not _id(account) or not _id(selection) or selected() != (account, selection):
            raise WebError('identity_unavailable')
        db = service.base.connection()
        timeout = install_budget(db, budget)
        db.set_progress_handler(budget.progress, min(100, budget.maximum_steps))
        with db.atomic_command(write=True):
            service.base.preflight(db)
            p = PeopleSchedulePermissions(db, account, service.now(), budget)
            directory = PeopleDirectory(db, budget, observed_at_utc=p.now, subject=p.subject)
            prior = people_candidate._stored_receipt(db, request['command_id'])
            creating, scope = command == 'schedule.create', body.get('create_owner_scope')
            target = None
            if prior:
                link = db.execute('SELECT * FROM web_receipt_links WHERE command_id=?', (request['command_id'],)).fetchone()
                if (link is None or link['api_version'] != API or link['registry_version'] != CONTRACT
                        or link['account_id'] != account or link['subject_id'] != p.subject or prior['command'] != command
                        or request['actor_subject_id'] != p.subject or (owner(dict(link)) if link['owner_kind'] else None) != scope):
                    raise WebError('command_id_unavailable')
                p.item(prior['item_id'])
                people_candidate._verify_receipt(db, command, request, prior)
            else:
                if request['actor_subject_id'] != p.subject:
                    raise WebError('identity_unavailable')
                if creating:
                    if not p.scope(scope):
                        raise WebError('resource_unavailable')
                    target = scope
                    p.prospective = {**scope, 'owner_subject_id': scope.get('owner_subject_id'),
                                     'owner_group_id': scope.get('owner_group_id'),
                                     'item_id': core._derived_id(command, request['command_id'], 'item', '/item'),
                                     'creator_entitlement_subject_id': p.subject, 'current_revision': 1}
                else:
                    target = owner(p.item(request['item_id'], edit=True))
                    service.base.bound_items(db, p, request['item_id'], edit=True)
                if body['expected_access_epoch'] != str(p.identity['access_epoch']):
                    raise WebError('access_changed')
                service.base.request_references(p, request, target)
            admitted = []
            def admit_additions(subjects):
                directory.admit(subjects, owner=target)
                admitted.extend(subjects)
            people = PeopleAuthoring(db, command, request, admit_additions)
            rendering = ProtectedScheduleRendering(db, command, request, p, budget, create_scope=scope)
            handler = core._handle_schedule_create if creating else core._handle_schedule_update
            result = handler(request, replace(CommandContext(ledger=db, ledger_path=service.config.database),
                                              people_authoring=people, rendering_authoring=rendering))
            if not result.get('ok'):
                error = result.get('error', {})
                raise SpineValidationError(error.get('code', 'runtime_failure') + ':' + error.get('field', 'request'),
                                           'Schedule operation unavailable.')
            if not prior:
                people.verify_successor(result['item_id'], int(result['current_version']))
                rendering.verify_successor(result['item_id'], int(result['current_version']))
            release = target if not prior else None
            p.references(result, release_owner=release)
            if release:
                policies = db.execute("SELECT delivery_target_id FROM notification_policies WHERE item_id=? AND version=? "
                                      "AND status='active' LIMIT 101", (result['item_id'], result['current_version'])).fetchall()
                if len(policies) > 100:
                    raise WebError('capacity_exceeded')
                for row in policies:
                    p.route(row[0], release_owner=release)
            if not prior:
                scope_fields = scope or {}
                db.execute("INSERT INTO web_receipt_links VALUES(?,?,?,?,?,?,'self_selected',?,?,?,?,?,?,?)", (
                    result['command_receipt_id'], request['command_id'], account, p.subject, p.identity['binding_id'],
                    p.identity['binding_revision'], p.identity['access_epoch'], API, CONTRACT,
                    scope_fields.get('owner_kind'), scope_fields.get('owner_subject_id'), scope_fields.get('owner_group_id'),
                    hash_canonical_json({'api_version': API, 'request': request, 'account_id': account, 'subject_id': p.subject,
                                         'create_owner_scope': scope})))
            identity = principal(db, p, selection)
            access, deadline = service.proof(db, p, directory, identity, budget)
            response = {'contract_version': API, 'ok': True, 'identity_basis': 'self_selected',
                **{k: v for k, v in identity.items() if k not in {'realm_id', 'recovery_epoch'}},
                'result_contract': 'spine.schedule-create-response.v4' if creating else 'spine.schedule-update-response.v4',
                'result': result}
            service.contracts.validate('web-responses', response, definition=command, output=True)
            if len(canonical_json_bytes(response)) > 4194304:
                raise WebError('capacity_exceeded')
            if service.before_release:
                service.before_release(db)
            if selected() != (account, selection):
                raise WebError('access_changed')
            try:
                fresh = _recheck(db, p, account, service.now(), budget)
                current = PeopleDirectory(db, budget, observed_at_utc=fresh.now, subject=fresh.subject)
                if admitted:
                    current.admit(tuple(admitted), owner=target)
                fresh_identity = principal(db, fresh, selection)
                fresh_access, fresh_deadline = service.proof(db, fresh, current, fresh_identity, budget)
                if (identity != fresh_identity or access != fresh_access or deadline != fresh_deadline
                        or fresh.now < p.now or deadline is not None and fresh.now >= deadline):
                    raise WebError('access_changed')
            except (WebError, SpineValidationError) as exc:
                if isinstance(exc, SpineValidationError) and exc.code.startswith('referenced_row_not_found:') or (
                        isinstance(exc, WebError) and exc.code in {'resource_unavailable', 'identity_unavailable'}):
                    raise WebError('access_changed') from exc
                raise
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
