"""People successors over the existing independent temporal/read owners.

Each page is fully reassembled and fenced in a fresh read-only snapshot under one
shared budget, without a durable cursor or proof cache.
"""

from __future__ import annotations

import copy
import sqlite3
import time
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, cast

from spine.commands.core import _occurrence_ordering_tuple
from spine.commands.facet_runtime import parse_time, utc_now, wire_time
from spine.commands.people_runtime import API, CURSOR, PeopleCursorCodec, PeopleCursorConfig, derivation, query_hash
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.ledger.people import read_people_snapshot
from spine.services.people_directory import PeopleDirectory
from spine.services.people_reads import authorization, ledger_instance
from spine.web.errors import WebError
from spine.web.people_service import domain_error, principal
from spine.web.read_assembly import assemble_agenda, assemble_occurrences
from spine.web.read_authorization import ReadPermissions, authorization_deadline, authorization_facts
from spine.web.read_context import OptionalReadUnavailable, ReadBudget, _OptionalPermissions, optional_snapshot, read_snapshot
from spine.web.read_contracts import READ_API, ReadContracts
from spine.web.read_pages import _agenda_key, _page
from spine.web.read_projection import candidate_ids
from spine.web.read_release import _plain, _selected
from spine.web.read_sections import SectionAssembly, _state, assemble_detail

RESULTS = {'schedule.show': 'spine.people-schedule-view.v1', 'agenda.show': 'spine.people-agenda-view.v1',
           'item.occurrences': 'spine.people-occurrences-view.v1'}


class PeopleReadBudget(ReadBudget):
    def __init__(self, contracts, *, clock, config):
        super().__init__(contracts, clock=clock, sql_steps=config.sql_steps)
        self.deadline = min(self.deadline, clock() + config.request_seconds)
        self.resources = set()

    def resolve(self, kind, identity):
        self.check()
        key = kind, identity
        if key not in self.resources:
            if len(self.resources) >= 100:
                if self.phase == 'optional':
                    raise OptionalReadUnavailable
                raise WebError('capacity_exceeded')
            self.resources.add(key)


class _OptionalPeoplePermissions(_OptionalPermissions):
    people_budget: PeopleReadBudget

    def touch(self, kind, resource, operation):
        self.people_budget.resolve(kind, resource)
        super().touch(kind, resource, operation)


class PeopleReadPermissions(ReadPermissions):
    optional_permissions_type = _OptionalPeoplePermissions

    def __init__(self, db, account, now, budget):
        self.people_budget = budget
        super().__init__(db, account, now)

    def touch(self, kind, resource, operation):
        self.people_budget.resolve(kind, resource)
        super().touch(kind, resource, operation)


class PeopleSection(SectionAssembly):
    def complete_value(self):
        if self.state['availability'] != 'available':
            return dict(self.state)
        return {**self.state, 'people': self.value}


def role_match(snapshot, item_id, predicate):
    """Admit before role access, never resolve the filter ID as a subject."""
    snapshot.permissions.item(item_id)
    selected = read_people_snapshot(snapshot.db, item_id=item_id)  # Includes the total-role sentinel.
    rows = [dict(row) for row in snapshot.db.execute(
        "SELECT item_subject_role_id,subject_id,role,status FROM item_subject_roles "
        "WHERE item_id=? AND version=? AND role IN ('participant','assignee') ORDER BY role,subject_id LIMIT 101",
        (item_id, selected.item_version),
    )]
    matches = any(row['subject_id'] == predicate['subject_id'] and row['role'] in predicate['roles']
                  and row['status'] == 'active' for row in rows)
    return matches, rows


class PeopleReadService:
    def __init__(self, config, *, contracts, cursor_config, reads=None, now=None, before_release=None, clock=time.monotonic):
        self.config, self.contracts, self.cursor_config = config, contracts, cursor_config
        self.reads = reads if reads is not None else ReadContracts.packaged()
        self.now, self.before_release, self.clock = now or (lambda: wire_time(utc_now())), before_release, clock

    @contextmanager
    def snapshot(self, account, budget, factory, *, releasing=False):
        try:
            with read_snapshot(self.config, self.reads, account, evaluated_at_utc=self.now(), budget=budget,
                               collect_proof=True, permissions_factory=factory) as snapshot:
                # Convert successor-domain failures inside the frozen boundary.
                try:
                    yield snapshot
                except SpineValidationError as exc:
                    raise domain_error(exc) from exc
        except WebError as exc:
            if releasing and exc.code in {'identity_unavailable', 'resource_unavailable', 'version_changed'}:
                raise WebError('access_changed') from exc
            raise

    def normalize(self, command, body):
        if len(canonical_json_bytes(body)) > 1048576:
            raise WebError('invalid_request')
        self.contracts.validate('web-requests', body, definition=command)
        request = copy.deepcopy(body['request'])
        legacy = copy.deepcopy(body)
        legacy['contract_version'] = READ_API
        legacy['request'].pop('person_filter', None)
        if command != 'item.occurrences':
            legacy['request']['include'] = sorted(set(request.get('include', [])) - {'people'})
        key = 'section_limit' if command == 'schedule.show' else 'limit'
        legacy['request'].setdefault(key, '25')
        route = 'agenda' if command == 'agenda.show' else command
        normalized, _ = self.reads.normalize(route, legacy)
        request = normalized['request']
        if command != 'item.occurrences':
            request['include'] = sorted(body['request'].get('include', []))
        if 'person_filter' in body['request']:
            predicate = body['request']['person_filter']
            request['person_filter'] = {**predicate, 'roles': sorted(predicate.get('roles', ['assignee', 'participant']))}
        guards = {k: body.get(k) for k in ('expected_access_epoch', 'expected_item_version', 'expected_recurrence_revision_id')}
        return request, guards

    def people_section(self, snapshot, identity, include, aggregate):
        if 'people' not in include:
            return PeopleSection(_state('not_requested'))
        try:
            with optional_snapshot(snapshot) as optional:
                budget = cast(PeopleReadBudget, optional.budget)
                directory = PeopleDirectory(optional.db, budget, observed_at_utc=optional.evaluated_at_utc,
                                            subject=optional.permissions.subject)
                value = directory.projection(read_people_snapshot(optional.db, item_id=identity))
                optional.budget.charge(value, authorized_rows=len(value['associations']))
                self.contracts.validate('types', value, definition='projection', output=True)
                existing = sum(len(rows) for rows in aggregate.proofs.values())
                if 5 + len(snapshot.permissions.probes) + existing + len(directory.proofs) > 100:
                    raise OptionalReadUnavailable
                # Only successful optional evidence is merged by optional_snapshot.
                assert optional.proof is not None
                optional.proof.add('people', identity, value)
                optional.proof.add('people_labels', identity, directory.metadata)
            aggregate.remember('directory', identity, directory.proof())
            aggregate.transitions.update(directory.transitions)
            return PeopleSection(_state('available'), value=value)
        except (OptionalReadUnavailable, SpineValidationError, ValueError, TypeError, KeyError, sqlite3.DatabaseError):
            # Failure is unavailability, never a fabricated not_disclosed label.
            snapshot.budget.check()
            return PeopleSection(_state('unavailable'))

    def assemble(self, snapshot, command, request, guards):
        assembly: Any
        p = snapshot.permissions
        actual = {k: v for k, v in guards.items() if v is not None}
        aggregate = PeopleDirectory(snapshot.db, snapshot.budget, observed_at_utc=snapshot.evaluated_at_utc, subject=p.subject)
        if command == 'agenda.show':
            preliminary = candidate_ids(snapshot, request, maximum=1000, admit_candidates=True)
        if actual.get('expected_access_epoch', str(p.identity['access_epoch'])) != str(p.identity['access_epoch']):
            # Direct roots must still be admitted before guard disclosure.
            if command != 'agenda.show':
                p.item(request['item_id'])
            raise WebError('access_changed')
        legacy = {k: copy.deepcopy(v) for k, v in request.items() if k != 'person_filter'}
        if 'include' in legacy:
            legacy['include'] = [name for name in legacy['include'] if name != 'people']
        sections = {}
        if command == 'schedule.show':
            activity, values = assemble_detail(snapshot, request['item_id'], legacy['include'], guards=actual)
            values['people'] = self.people_section(snapshot, request['item_id'], request['include'], aggregate)
            assembly, roots, sections = (activity, values), [request['item_id']], {request['item_id']: values}
        elif command == 'agenda.show':
            roots = preliminary
            if 'person_filter' in request:
                matched = []
                for identity in roots:
                    allowed, facts = role_match(snapshot, identity, request['person_filter'])
                    if allowed:
                        matched.append(identity)
                        snapshot.proof.add('people_filter', identity, facts)
                roots = matched
            assembly = assemble_agenda(snapshot, legacy, selected_ids=roots)
            sections = assembly.sections
            for identity, values in sections.items():
                values['people'] = self.people_section(snapshot, identity, request['include'], aggregate)
            for row in assembly.entries + assembly.unplaced_items:
                identity = row['activity']['item_id']
                row['sections'] = {name: section.complete_value() for name, section in sections[identity].items()}
                if 'occurrence' not in row:
                    snapshot.proof.cores[identity] = row['activity']
        else:
            p.item(request['item_id'])
            selected = True
            if 'person_filter' in request:
                selected, facts = role_match(snapshot, request['item_id'], request['person_filter'])
                snapshot.proof.add('people_filter', request['item_id'], facts)
            assembly = assemble_occurrences(snapshot, legacy, guards=actual, selected=selected)
            roots = [request['item_id']]
            snapshot.proof.cores[request['item_id']] = assembly.activity
        for identity in roots:
            snapshot.proof.add('item', identity, snapshot.proof.cores[identity])
        rules = self.reads.artifacts['trusted-web-read-projection.v1.json']['sections']
        for identity, values in sections.items():
            for name, section in values.items():
                if name != 'people':
                    snapshot.proof.section(identity, name, section, rules)
        return assembly, aggregate

    def evidence(self, snapshot, aggregate, identity, command):
        facts = authorization_facts(snapshot, snapshot.permissions.probes, snapshot.permissions.core_probe_keys)
        size = (len(facts['checks']) + len(facts['grants']) + len(facts['memberships']) + 5
                + sum(len(row['operations']) for row in facts['grants'].values())
                + sum(len(rows) for rows in aggregate.proofs.values()))
        if size > 100:
            raise WebError('capacity_exceeded')
        access, deadline = authorization(aggregate, identity, permission_proofs=facts, valid_until=authorization_deadline(snapshot))
        source = derivation('source', route=command, sources=snapshot.proof.records())
        return source, access, deadline

    def page(self, assembly, command, request, identity, family, previous, codec):
        def token(stream, last):
            return codec.encode({**family, 'stream': stream, 'last_key': last})
        if command == 'schedule.show':
            activity, sections = assembly
            values = {}
            order = self.reads.artifacts['trusted-web-read-cursor.v2.json']['section_order']
            for name, section in sections.items():
                if not section.collection or section.state['availability'] != 'available':
                    values[name] = section.complete_value()
                    continue
                def section_key(row, name=name):
                    return name, [row[field] for field in order[name]]
                rows, more = _page(section.rows, int(request['section_limit']), previous.get(name), section_key)
                values[name] = {**section.state, 'entries': rows, 'has_more': more,
                                'next_cursor': token(*section_key(rows[-1])) if more else None}
            result = {'activity': activity, 'sections': values}
        elif command == 'item.occurrences':
            def occurrence_key(row):
                return 'occurrences', list(_occurrence_ordering_tuple(row, request['range_basis']))
            rows, more = _page(assembly.occurrences, int(request['limit']), previous.get('page'), occurrence_key)
            result = {'activity': assembly.activity, 'coverage': assembly.coverage,
                      'range': {k: request[k] for k in ('range_start', 'range_end', 'range_basis')},
                      'occurrences': rows, 'limit': request['limit'], 'has_more': more,
                      'next_cursor': token(*occurrence_key(rows[-1])) if more else None}
        else:
            combined = [('resolved', row) for row in assembly.entries] + [('unplaced', row) for row in assembly.unplaced_items]
            def agenda_key(pair):
                stream, row = pair
                return stream, _agenda_key(row) if stream == 'resolved' else [row['activity']['item_id']]
            rows, more = _page(combined, int(request['limit']), previous.get('page'), agenda_key)
            result = {'range': {k: request[k] for k in ('evaluated_at_utc', 'range_start_local', 'range_end_local',
                                                       'timezone', 'timezone_database_version')},
                      'coverage': assembly.coverage, 'entries': [r for s, r in rows if s == 'resolved'],
                      'unplaced_items': [r for s, r in rows if s == 'unplaced'], 'limit': request['limit'], 'has_more': more,
                      'next_cursor': token(*agenda_key(rows[-1])) if more else None}
        response = {'contract_version': API, 'ok': True, 'identity_basis': 'self_selected',
                    **{k: v for k, v in identity.items() if k not in {'realm_id', 'recovery_epoch'}},
                    'result_contract': RESULTS[command], 'result': result}
        self.contracts.validate('web-responses', response, definition=command, output=True)
        return response

    def read(self, command, body, *, selection, encode=None, started=None):
        if command not in RESULTS:
            raise WebError('operation_unavailable')
        budget = PeopleReadBudget(self.reads, clock=self.clock, config=self.config)
        if started is not None:
            budget.deadline = min(budget.deadline, started + self.config.request_seconds)
        try:
            request, guards = self.normalize(command, body)
            budget.check()
            if not isinstance(self.cursor_config, PeopleCursorConfig):
                raise WebError('admission_unavailable')
            codec = PeopleCursorCodec(self.contracts, self.cursor_config)
            account, selected = _selected(selection)
            def factory(db, account, now):
                return PeopleReadPermissions(db, account, now, budget)
            tokens = body['request'].get('section_cursors', {}) if command == 'schedule.show' else (
                {'page': body['request']['cursor']} if 'cursor' in body['request'] else {})
            previous, prior_family = {}, None
            with self.snapshot(account, budget, factory) as snapshot:
                instance = ledger_instance(PeopleDirectory(snapshot.db, budget, observed_at_utc=snapshot.evaluated_at_utc))
                if instance != codec.config.ledger_instance_id:
                    raise WebError('admission_unavailable')
                identity = principal(snapshot.db, snapshot.permissions, selected)
                for name, wire in tokens.items():
                    payload = codec.decode(wire, now=snapshot.evaluated_at_utc)
                    family = {k: v for k, v in payload.items() if k not in {'stream', 'last_key'}}
                    if prior_family is not None and family != prior_family:
                        raise WebError('invalid_request')
                    if command == 'schedule.show' and payload['stream'] != name:
                        raise WebError('invalid_request')
                    previous[name], prior_family = payload, family
                assembly, aggregate = self.assemble(snapshot, command, request, guards)
                source, access, deadline = self.evidence(snapshot, aggregate, identity, command)
                binding = {'contract_version': CURSOR, 'key_id': codec.config.key_id,
                    'key_generation': codec.config.key_generation, 'ledger_instance_id': codec.config.ledger_instance_id,
                    'route': command, 'mode': 'permission_enforced', **identity, 'query_hash': query_hash(command, request, guards),
                    'source_hash': source, 'authorization_hash': access, 'authorization_valid_until_utc': deadline,
                    **({'item_id': request['item_id']} if command != 'agenda.show' else {}),
                    **({'range_basis': request['range_basis']} if command == 'item.occurrences' else {})}
                if prior_family is not None and any(prior_family.get(k) != v for k, v in binding.items()):
                    raise WebError('access_changed')
                issue = prior_family['issued_at_utc'] if prior_family else snapshot.evaluated_at_utc
                family = {**binding, 'issued_at_utc': issue, 'expires_at_utc': prior_family['expires_at_utc'] if prior_family else
                          wire_time(parse_time(issue) + timedelta(seconds=900))}
                response = self.page(assembly, command, request, identity, family, previous, codec)
                assembly_hash = hash_canonical_json(_plain(assembly))
                budget.check_response(response)
                if encode is not None:
                    response = encode(response)
                    if not isinstance(response, bytes) or len(response) > 4194304:
                        raise WebError('capacity_exceeded')
                evaluated = snapshot.evaluated_at_utc
            if self.before_release:
                self.before_release()
            def selection_is_current():
                try:
                    return _selected(selection) == (account, selected)
                except WebError:
                    return False
            if not selection_is_current() or self.cursor_config != codec.config:
                raise WebError('access_changed')
            with self.snapshot(account, budget, factory, releasing=True) as fresh:
                fresh_identity = principal(fresh.db, fresh.permissions, selected)
                try:
                    current, authority = self.assemble(fresh, command, request, guards)
                    fresh_source, fresh_access, fresh_deadline = self.evidence(fresh, authority, fresh_identity, command)
                except WebError as exc:
                    if exc.code in {'resource_unavailable', 'identity_unavailable', 'version_changed'}:
                        raise WebError('access_changed') from exc
                    raise
                if (fresh_identity != identity or (source, access, deadline) != (fresh_source, fresh_access, fresh_deadline)
                        or assembly_hash != hash_canonical_json(_plain(current)) or fresh.evaluated_at_utc < evaluated):
                    raise WebError('access_changed')
                codec.times(family, fresh.evaluated_at_utc)
                budget.check()
                if not selection_is_current():
                    raise WebError('access_changed')
            budget.check()
            codec.times(family, self.now())
            return response
        except SpineValidationError as exc:
            raise domain_error(exc) from exc
        except WebError as exc:
            # Keep the frozen v2 status owner unchanged; this family's reviewed
            # capacity response is 429, with the same non-disclosing envelope.
            raise WebError(exc.code, 409 if exc.code == 'version_changed' else None) from exc
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
            raise WebError('domain_failure') from exc
