"""Private people read assembly and roster paging, shared by local/web adapters."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from spine.commands.facet_runtime import wire_time
from spine.commands.people_runtime import CONTRACT, CURSOR, PeopleCursorCodec, derivation, query_hash
from spine.ledger.people import read_people_snapshot
from spine.services.people_directory import PeopleDirectory, decimal_facts, unavailable


def ledger_instance(directory: PeopleDirectory) -> str:
    row = directory.db.execute('SELECT ledger_instance_id FROM ledger_instance_metadata WHERE singleton=1').fetchone()
    if row is None:
        unavailable('environment_failure', 'admission')
    return str(row[0])


def assemble(command: str, request: dict[str, Any], directory: PeopleDirectory) -> tuple[dict[str, Any], str]:
    if command == 'people.list':
        rows, sources = directory.roster(request['owner'], status=request['subject_status'], kind=request['subject_kind'])
        result = {'ok': True, 'command': command, 'response_contract': CONTRACT, 'owner': request['owner'],
                  'observed_at_utc': directory.now, 'subjects': rows, 'limit': request['limit']}
    else:
        snapshot = read_people_snapshot(directory.db, item_id=request['item_id'],
                                       version=int(request['version']) if 'version' in request else None)
        projection = directory.projection(snapshot)
        result = {'ok': True, 'command': command, 'response_contract': CONTRACT,
                  'current_version': str(snapshot.current_version), 'people': projection}
        sources = {'current_version': result['current_version'], 'people': projection, 'labels': directory.metadata}
    return result, derivation('source', route=command, sources=decimal_facts(sources))


def authorization(directory: PeopleDirectory, identity: dict[str, Any] | None = None,
                  *, permission_proofs: Any = None, valid_until: str | None = None) -> tuple[str, str | None]:
    deadline = min(filter(None, (directory.valid_until, valid_until)), default=None)
    context = ({'mode': 'trusted_local', 'ledger_instance_id': ledger_instance(directory)} if identity is None else {
        'mode': 'permission_enforced', **identity, 'proofs': directory.proof(),
        'item_proofs': permission_proofs or [], 'authorization_valid_until_utc': deadline,
    })
    return derivation('authorization', context=decimal_facts(context)), deadline


def page_roster(result: dict[str, Any], *, codec: PeopleCursorCodec, request: dict[str, Any],
                source_hash: str, authorization_hash: str, valid_until: str | None, identity: dict[str, Any] | None = None,
                guards: dict[str, Any] | None = None, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    now = result['observed_at_utc']
    query = query_hash('people.list', request, guards)
    binding = {'key_id': codec.config.key_id, 'key_generation': codec.config.key_generation,
               'ledger_instance_id': codec.config.ledger_instance_id, 'route': 'people.list', 'stream': 'roster',
               'mode': 'trusted_local' if identity is None else 'permission_enforced', 'owner': request['owner'],
               'query_hash': query, 'source_hash': source_hash, 'authorization_hash': authorization_hash,
               'authorization_valid_until_utc': valid_until,
               **(identity or {})}
    if previous is not None and any(previous.get(k) != v for k, v in binding.items()):
        unavailable('stale_cursor', 'cursor')
    rows = result['subjects']
    if previous is not None:
        # A signed key still has to exist in the re-established complete source.
        if previous['last_key'][0] not in {row['subject_id'] for row in rows}:
            unavailable('stale_cursor', 'cursor')
        rows = [row for row in rows if row['subject_id'] > previous['last_key'][0]]
    selected = rows[:int(request['limit'])]
    more = len(rows) > len(selected)
    token = None
    if more:
        from spine.commands.facet_runtime import parse_time

        token = codec.encode({'contract_version': CURSOR, **binding,
            'last_key': [selected[-1]['subject_id']],
            'issued_at_utc': previous['issued_at_utc'] if previous else now,
            'expires_at_utc': previous['expires_at_utc'] if previous else wire_time(parse_time(now) + timedelta(seconds=900)),
            'authorization_valid_until_utc': previous['authorization_valid_until_utc'] if previous else valid_until})
    return {**result, 'subjects': selected, 'has_more': more, 'next_cursor': token}
