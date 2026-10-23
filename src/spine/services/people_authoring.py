"""Private scheduling hook for a single atomic version with people.

The command owner supplies admission inside its outer write transaction. This
does not register a command, change ownership, or grant notification routing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from spine.core.errors import SpineValidationError
from spine.core.people import (
    RoleAssociation,
    managed_role,
    normalize_people,
    replacement_is_noop,
    replacement_rows,
    subjects_needing_admission,
)
from spine.ledger.people import read_people_snapshot
from spine.ledger.people_authoring import capture_role_edge, verify_role_edge
from spine.ledger.supporting import ItemSubjectRoleInput
from spine.ledger.transactions import LedgerConnection


def role_inputs(rows: tuple[RoleAssociation, ...]) -> tuple[ItemSubjectRoleInput, ...]:
    return tuple(ItemSubjectRoleInput(**asdict(row)) for row in rows)


class PeopleAuthoring:
    """Only the private candidate constructs this hook, never an adapter body."""

    def __init__(self, db: LedgerConnection, command: str, request: dict[str, Any],
                 admit_additions: Callable[[tuple[str, ...]], None]) -> None:
        self.db, self.command, self.request = db, command, request
        self.admit_additions = admit_additions
        self.changed = False
        self.role_only = command == 'schedule.update' and set(request['patch']) == {'people'}
        self.before: dict[str, Any] | None = None
        self.expected: tuple[RoleAssociation, ...] | None = None

    def create(self, item_type: str) -> tuple[ItemSubjectRoleInput, ...]:
        subjects = normalize_people(item_type=item_type, value=self.request['people'], creating=True)
        assert subjects is not None
        self.admit_additions(subjects)
        self.expected = replacement_rows(item_type=item_type, subjects=subjects,
                                         command=self.command, command_id=self.request['command_id'])
        return role_inputs(self.expected)

    def update(self, item: Mapping[str, Any]) -> tuple[ItemSubjectRoleInput, ...] | None:
        snapshot = read_people_snapshot(self.db, item_id=item['item_id'])
        if 'people' not in self.request['patch']:
            return None
        subjects = normalize_people(item_type=snapshot.item_type, value=self.request['patch']['people'])
        assert subjects is not None
        self.changed = not replacement_is_noop(snapshot.item_type, snapshot.associations, subjects)
        if self.changed:
            self.admit_additions(subjects_needing_admission(snapshot.item_type, snapshot.associations, subjects))
        self.expected = replacement_rows(item_type=snapshot.item_type, subjects=subjects,
                                         command=self.command, command_id=self.request['command_id'])
        if self.role_only and self.changed:
            self.before = capture_role_edge(self.db, snapshot.item_id, snapshot.item_version)
        return role_inputs(self.expected)

    def augment(self, facts: dict[str, Any], item_id: str, version: int) -> None:
        # Creation's canonical extension runs before supporting rows are inserted;
        # return the exact precomputed rows and verify them before outer commit.
        rows = self.expected if self.command == 'schedule.create' else read_people_snapshot(
            self.db, item_id=item_id, version=version).associations
        assert rows is not None
        facts['people'] = [asdict(row) for row in rows]

    def verify_successor(self, item_id: str, version: int) -> None:
        snapshot = read_people_snapshot(self.db, item_id=item_id, version=version)
        allocated = self.command == 'schedule.create' or version > int(self.request['target_version'])
        if allocated and self.expected is not None and snapshot.associations != self.expected:
            raise SpineValidationError('environment_failure:people', 'People replacement verification failed.')
        if self.before is not None:
            verify_role_edge(self.before, capture_role_edge(self.db, item_id, version),
                             role=managed_role(snapshot.item_type))
