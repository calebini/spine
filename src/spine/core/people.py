"""Private people foundation; no command, permission or capability activation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from spine.core.errors import SpineValidationError
from spine.core.hashing import command_derived_id, hash_canonical_json

MAX_ROLE_ROWS = 100
_MISSING = object()
_KINDS = {"event": ("participants", "participant"), "task": ("assignees", "assignee")}


@dataclass(frozen=True)
class RoleAssociation:
    item_subject_role_id: str
    subject_id: str
    role: str
    status: str


def people_id(value: object) -> str:
    """Validate an opaque scalar ID without trimming or normalizing it."""
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(
        ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        raise SpineValidationError("invalid_request:people", "Invalid people identifier.")
    return value


def managed_role(item_type: str) -> str:
    if item_type not in _KINDS:
        raise SpineValidationError("wrong_item_type:people", "People require an event or task.")
    return _KINDS[item_type][1]


def normalize_people(*, item_type: str, value: object = _MISSING, creating: bool = False) -> tuple[str, ...] | None:
    """None means update omission; an empty tuple is an explicit empty set."""
    managed_role(item_type)
    if value is _MISSING:
        return () if creating else None
    key = _KINDS[item_type][0]
    if not isinstance(value, dict) or set(value) != {key} or not isinstance(value[key], list):
        raise SpineValidationError("invalid_request:people", "Invalid people replacement.")
    raw = value[key]
    if len(raw) > MAX_ROLE_ROWS:
        raise SpineValidationError("invalid_request:people", "People replacement exceeds its limit.")
    identifiers = tuple(people_id(entry) for entry in raw)
    if len(set(identifiers)) != len(identifiers):
        raise SpineValidationError("invalid_request:people", "Duplicate people identifier.")
    return tuple(sorted(identifiers))


def managed_facts(item_type: str, rows: Iterable[RoleAssociation]) -> tuple[tuple[str, str, str], ...]:
    """Complete managed semantics, including inactive rows but excluding physical IDs."""
    role = managed_role(item_type)
    result = []
    seen = set()
    for row in rows:
        if row.role != role:
            continue
        subject = people_id(row.subject_id)
        if row.status not in {"active", "inactive"} or subject in seen:
            raise SpineValidationError("environment_failure:people", "Invalid stored people set.")
        seen.add(subject)
        result.append((subject, role, row.status))
    return tuple(sorted(result, key=lambda row: (row[1], row[0], row[2])))


def replacement_is_noop(item_type: str, current: Iterable[RoleAssociation], replacement: tuple[str, ...] | None) -> bool:
    role = managed_role(item_type)
    if replacement is None:
        return True
    normalized = normalize_people(item_type=item_type, value={_KINDS[item_type][0]: list(replacement)})
    assert normalized is not None
    return managed_facts(item_type, current) == tuple((subject, role, "active") for subject in normalized)


def subjects_needing_admission(
    item_type: str, current: Iterable[RoleAssociation], replacement: tuple[str, ...],
) -> tuple[str, ...]:
    """Select additions/reactivations; this does not authorize or resolve subjects."""
    active = {subject for subject, _, status in managed_facts(item_type, current) if status == "active"}
    normalized = normalize_people(item_type=item_type, value={_KINDS[item_type][0]: list(replacement)})
    assert normalized is not None
    return tuple(subject for subject in normalized if subject not in active)


def role_set_hash(item_type: str, rows: Iterable[RoleAssociation]) -> str:
    return hash_canonical_json({
        "derivation_version": "spine.people-role-set.v1", "canonical_json_version": "spine.canonical-json.v1",
        "item_type": item_type,
        "roles": [{"subject_id": subject, "role": role, "status": status}
                  for subject, role, status in managed_facts(item_type, rows)],
    })


def replacement_rows(
    *, item_type: str, subjects: tuple[str, ...], command: str, command_id: str,
) -> tuple[RoleAssociation, ...]:
    """Derive candidate replacement identities; callers must detect no-op first."""
    role = managed_role(item_type)
    paths = {"item.people.update": "/people", "schedule.create": "/people", "schedule.update": "/patch/people"}
    if command not in paths:
        raise SpineValidationError("invalid_request:command", "Unsupported people identity context.")
    people_id(command_id)
    key = _KINDS[item_type][0]
    normalized = normalize_people(item_type=item_type, value={key: list(subjects)})
    assert normalized is not None
    return tuple(RoleAssociation(
        item_subject_role_id=command_derived_id(prefix="item_subject_role", command=command,
            command_id=command_id, row_role="item_subject_role", request_path=f"{paths[command]}/{key}/{index}"),
        subject_id=subject, role=role, status="active",
    ) for index, subject in enumerate(normalized))
