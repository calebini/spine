"""Shared D-01 directory admission and D-02 current-label disclosure.

The adapter supplies the admitted subject and service time. Neither is selected
by request JSON. Item permission is deliberately not directory permission. This
resolver writes nothing and does not traverse items, routes or relationships.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Any, NoReturn, Protocol

from spine.commands.facet_runtime import parse_time
from spine.core.errors import SpineValidationError
from spine.core.people import managed_facts, people_id
from spine.ledger.people import PeopleSnapshot


def unavailable(code: str = 'referenced_row_not_found', field: str = 'people') -> NoReturn:
    raise SpineValidationError(f'{code}:{field}', 'People operation unavailable.')


def decimal_facts(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return {k: decimal_facts(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimal_facts(v) for v in value]
    return value


class DirectoryBudget(Protocol):
    """The same resolver can consume an independent-read adapter's shared budget."""

    def check(self) -> None: ...

    def resolve(self, kind: str, identity: str) -> None: ...


class PeopleDirectory:
    def __init__(self, db: sqlite3.Connection, budget: DirectoryBudget, *, observed_at_utc: str,
                 subject: str | None = None) -> None:
        parse_time(observed_at_utc)
        self.db, self.budget, self.now, self.subject = db, budget, observed_at_utc, subject
        self.proofs: dict[tuple[str, str], Any] = {}
        self.metadata: dict[str, Any] = {}
        self.transitions: set[str] = set()

    def remember(self, kind: str, identity: str, value: Any) -> None:
        self.proofs[kind, identity] = decimal_facts(value)
        if len(self.proofs) > 100:
            unavailable('environment_failure', 'capacity')
        self.budget.check()

    def _subject(self, identity: str) -> dict[str, Any]:
        self.budget.resolve('subject', identity)
        row = self.db.execute('SELECT subject_id,subject_kind,display_name,status,updated_at_utc '
                              'FROM subjects WHERE subject_id=?', (identity,)).fetchone()
        if row is None:
            # An existing role's missing FK is not label nondisclosure.
            unavailable('environment_failure', 'people')
        value = dict(row)
        if (value['status'] not in {'active', 'inactive'} or value['subject_kind'] not in {'person', 'agent'}
                or not isinstance(value['display_name'], str) or not 1 <= len(value['display_name']) <= 512):
            unavailable('environment_failure', 'people')
        people_id(value['subject_id'])
        return value

    def _group(self, identity: str) -> dict[str, Any] | None:
        self.budget.resolve('subject_group', identity)
        row = self.db.execute('SELECT group_id,status FROM subject_groups WHERE group_id=?', (identity,)).fetchone()
        return None if row is None else dict(row)

    def _membership(self, group: str, subject: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM subject_memberships WHERE group_id=? AND status='active' AND subject_id=? "
            'AND starts_at_utc<=? ORDER BY membership_id LIMIT 2', (group, subject, self.now),
        ).fetchall()
        if len(rows) > 1:
            unavailable('environment_failure', 'people')
        future = self.db.execute(
            "SELECT MIN(starts_at_utc) FROM subject_memberships WHERE group_id=? AND status='active' "
            'AND subject_id=? AND starts_at_utc>?', (group, subject, self.now),
        ).fetchone()[0]
        if future is not None:
            self.transitions.add(future)
        return [dict(row) for row in rows]

    def scope(self, owner: dict[str, str]) -> None:
        """Admit the directory before looking up potential choices."""
        if owner['owner_kind'] == 'subject':
            identity = owner['owner_subject_id']
            if self.subject is not None and identity != self.subject:
                unavailable()
            row = self.db.execute('SELECT subject_id,status FROM subjects WHERE subject_id=?', (identity,)).fetchone()
            if row is None or row['status'] != 'active':
                unavailable()
            self.budget.resolve('subject', identity)
            self.remember('scope', 'subject:' + identity, dict(row))
        else:
            group = owner['owner_group_id']
            row = self._group(group)
            if row is None or row['status'] != 'active':
                unavailable()
            membership = [] if self.subject is None else self._membership(group, self.subject)
            if self.subject is not None and not membership:
                unavailable()
            self.remember('scope', 'subject_group:' + group, {'group': row, 'membership': membership})

    def roster(self, owner: dict[str, str], *, status: str = 'active', kind: str = 'all') -> tuple[list[dict[str, Any]], Any]:
        self.scope(owner)
        records: list[tuple[dict[str, Any], list[dict[str, Any]]]]
        if owner['owner_kind'] == 'subject':
            row = self._subject(owner['owner_subject_id'])
            records = [(row, [])] if status in {'all', row['status']} and kind in {'all', row['subject_kind']} else []
        else:
            group = owner['owner_group_id']
            # Scope-indexed, ceiling+1, never enumerate the global subject table.
            rows = self.db.execute(
                "SELECT m.*,s.subject_id AS choice_id FROM subject_memberships m LEFT JOIN subjects s USING(subject_id) "
                "WHERE m.group_id=? AND m.status='active' AND m.starts_at_utc<=? "
                "AND (s.subject_id IS NULL OR ((?='all' OR s.status=?) AND (?='all' OR s.subject_kind=?))) "
                'ORDER BY m.subject_id,m.membership_id LIMIT 1001', (group, self.now, status, status, kind, kind),
            ).fetchall()
            if len(rows) > 1000 or len({row['subject_id'] for row in rows}) != len(rows):
                unavailable('environment_failure', 'capacity' if len(rows) > 1000 else 'people')
            records = []
            for row in rows:
                if row['choice_id'] is None:
                    unavailable('environment_failure', 'people')
                membership = dict(row)
                membership.pop('choice_id')
                records.append((self._subject(row['subject_id']), [membership]))
            future = self.db.execute(
                "SELECT MIN(m.starts_at_utc) FROM subject_memberships m JOIN subjects s USING(subject_id) "
                "WHERE m.group_id=? AND m.status='active' AND m.starts_at_utc>? "
                "AND (?='all' OR s.status=?) AND (?='all' OR s.subject_kind=?)",
                (group, self.now, status, status, kind, kind),
            ).fetchone()[0]
            if future is not None:
                self.transitions.add(future)
        choices = [{k: row[k] for k in ('subject_id', 'display_name', 'subject_kind', 'status')} |
                   {'eligible_for_fresh_selection': row['status'] == 'active'} for row, _ in records]
        sources = {'owner': owner, 'scope': self.proof(), 'subjects': [
            {'subject': row, 'memberships': membership} for row, membership in records]}
        return choices, decimal_facts(sources)

    def admit(self, subjects: tuple[str, ...], *, owner: dict[str, str] | None = None) -> None:
        """Only additions/reactivations reach this method; retained rows do not."""
        if not subjects:
            return
        if self.subject is not None:
            if owner is None:
                unavailable()
            self.scope(owner)  # Before target existence: no roster probing via writes.
        for identity in subjects:
            self.budget.resolve('subject', identity)
            row = self.db.execute('SELECT subject_id,status FROM subjects WHERE subject_id=?', (identity,)).fetchone()
            if row is None or row['status'] != 'active':
                unavailable()
            if self.subject is not None:
                assert owner is not None
                if owner['owner_kind'] == 'subject':
                    if identity != owner['owner_subject_id']:
                        unavailable()
                    membership = []
                else:
                    membership = self._membership(owner['owner_group_id'], identity)
                    if not membership:
                        unavailable()
                self.remember('fresh_reference', identity, {'subject': dict(row), 'memberships': membership})

    def label(self, identity: str) -> dict[str, Any]:
        # Check the FK without loading protected label metadata first.
        if self.db.execute('SELECT 1 FROM subjects WHERE subject_id=?', (identity,)).fetchone() is None:
            unavailable('environment_failure', 'people')
        allowed = self.subject is None or identity == self.subject
        if not allowed:
            groups = self.db.execute(
                "SELECT m.group_id FROM subject_memberships m JOIN subject_groups g USING(group_id) "
                "WHERE m.subject_id=? AND m.status='active' AND g.status='active' AND m.starts_at_utc<=? "
                'ORDER BY m.group_id LIMIT 101', (self.subject, self.now),
            ).fetchall()
            if len(groups) > 100:
                unavailable('environment_failure', 'capacity')
            if len({row[0] for row in groups}) != len(groups):
                unavailable('environment_failure', 'people')
            evidence = []
            for group in groups:
                assert self.subject is not None
                caller = self._membership(group[0], self.subject)
                target = self._membership(group[0], identity)
                if target:
                    evidence.append({'group': self._group(group[0]), 'caller': caller, 'target': target})
            allowed = bool(evidence)
            # Only used directory evidence is retained, never hidden subject metadata.
            self.remember('label', identity, evidence)
            future = self.db.execute(
                "SELECT MIN(m.starts_at_utc) FROM subject_memberships m JOIN subject_groups g USING(group_id) "
                "WHERE m.subject_id=? AND m.status='active' AND g.status='active' AND m.starts_at_utc>?",
                (self.subject, self.now),
            ).fetchone()[0]
            if future is not None:
                self.transitions.add(future)
        if not allowed:
            return {'availability': 'not_disclosed'}
        row = self._subject(identity)
        self.metadata[identity] = row
        return {'availability': 'available', **{k: row[k] for k in ('display_name', 'subject_kind', 'status')}}

    def projection(self, snapshot: PeopleSnapshot) -> dict[str, Any]:
        managed_facts(snapshot.item_type, snapshot.associations)
        subjects = []
        for identity in sorted({row.subject_id for row in snapshot.associations}):
            self.budget.resolve('subject', identity)
            subjects.append({'subject_id': identity, 'label': self.label(identity)})
        return {'item_id': snapshot.item_id, 'item_type': snapshot.item_type, 'item_version': str(snapshot.item_version),
                'associations': [asdict(row) for row in snapshot.associations], 'subjects': subjects}

    def proof(self) -> list[dict[str, Any]]:
        return [{'kind': kind, 'id': identity, 'value': value} for (kind, identity), value in sorted(self.proofs.items())]

    @property
    def valid_until(self) -> str | None:
        return min(self.transitions, default=None)
