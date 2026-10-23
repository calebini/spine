"""Private source-contract loader and authenticated people-cursor primitives.

No package declarations or public route registration are changed here. Source
contracts are explicitly supplied by the internal caller until family activation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from referencing import Registry, Resource

from spine.commands.facet_runtime import FacetBudget, parse_time
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.hashing import hash_canonical_json
from spine.core.people import people_id
from spine.services.people_directory import unavailable
from spine.web.read_contracts import FORMATS

CONTRACT = 'spine.people-and-responsibility.v1'
API = 'spine.trusted-web-people.v1'
CURSOR = 'spine.people-cursor.v1'
PREFIX = 'https://cortext.local/spine/contracts/schemas/people/'


@dataclass
class PeopleBudget(FacetBudget):
    maximum_steps: int = 100_000
    maximum_seconds: float = 5

    def check(self) -> None:
        if self.steps > self.maximum_steps or time.monotonic() - self.started >= self.maximum_seconds:
            unavailable('environment_failure', 'capacity')

    def progress(self) -> int:
        self.steps += min(100, self.maximum_steps)
        return int(self.steps > self.maximum_steps or time.monotonic() - self.started >= self.maximum_seconds)


class PeopleContracts:
    """Offline exact dependency closure, not an installed-runtime qualification."""

    def __init__(self, root: Path) -> None:
        manifest = json.loads((root / 'contracts/people-and-responsibility-fixture-manifest.json').read_bytes())
        paths = manifest['schemas'] + manifest['schema_dependencies']
        self.schemas = {p: json.loads((root / p).read_bytes()) for p in paths}
        self.registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in self.schemas.values())
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def validate(self, name: str, value: Any, *, definition: str | None = None, output: bool = False) -> None:
        ref = PREFIX + name + '.schema.json' + ('#/$defs/' + definition if definition else '')
        validator = Draft202012Validator({'$ref': ref}, registry=self.registry, format_checker=FORMATS)
        if not validator.is_valid(value):
            unavailable('environment_failure' if output else 'invalid_request', 'response' if output else 'request')


@dataclass(frozen=True)
class PeopleCursorConfig:
    key_id: str
    key_generation: str
    ledger_instance_id: str
    secret: bytes = field(repr=False)

    def validate(self) -> None:
        if (not isinstance(self.secret, bytes) or not 32 <= len(self.secret) <= 64
                or any(not isinstance(x, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', x) is None
                       for x in (self.key_id, self.key_generation))
                or not isinstance(self.ledger_instance_id, str) or not 1 <= len(self.ledger_instance_id) <= 256):
            unavailable('environment_failure', 'cursor_config')
        try:
            people_id(self.ledger_instance_id)
        except SpineValidationError as exc:
            raise SpineValidationError('environment_failure:cursor_config', 'People cursor configuration unavailable.') from exc


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def load_cursor_config(path: str) -> PeopleCursorConfig:
    try:
        descriptor = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()} or info.st_mode & 0o077:
                raise ValueError('permissions')
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError('size')
        value = json.loads(raw, object_pairs_hook=_object)
        if set(value) != {'contract_version', 'key_id', 'key_generation', 'ledger_instance_id', 'secret_hex'}:
            raise ValueError('shape')
        if (value['contract_version'] != 'spine.people-cursor-config.v1' or not isinstance(value['secret_hex'], str)
                or re.fullmatch(r'(?:[0-9a-f]{2}){32,64}', value['secret_hex']) is None):
            raise ValueError('key')
        config = PeopleCursorConfig(value['key_id'], value['key_generation'], value['ledger_instance_id'],
                                    bytes.fromhex(value['secret_hex']))
        config.validate()
        return config
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, SpineValidationError) as exc:
        raise SpineValidationError('environment_failure:cursor_config', 'People cursor configuration unavailable.') from exc


def derivation(kind: str, **value: Any) -> str:
    return hash_canonical_json({'derivation_version': f'spine.people-{kind}.v1',
                               'canonical_json_version': 'spine.canonical-json.v1', **value})


def query_hash(route: str, request: dict[str, Any], guards: dict[str, Any] | None = None) -> str:
    return derivation('query', route=route, request={k: v for k, v in request.items() if k not in {'cursor', 'section_cursors'}},
                      guards={k: (guards or {}).get(k) for k in (
                          'expected_access_epoch', 'expected_item_version', 'expected_recurrence_revision_id')})


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _unb64(value: str) -> bytes:
    if re.fullmatch(r'[A-Za-z0-9_-]+', value) is None:
        raise ValueError('encoding')
    raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if _b64(raw) != value:
        raise ValueError('encoding')
    return raw


class PeopleCursorCodec:
    def __init__(self, contracts: PeopleContracts, config: PeopleCursorConfig) -> None:
        config.validate()
        self.contracts, self.config = contracts, config

    def times(self, value: dict[str, Any], now: str) -> None:
        issued, expires, current = (parse_time(v) for v in (value['issued_at_utc'], value['expires_at_utc'], now))
        if not issued < expires <= issued + timedelta(seconds=900):
            unavailable('invalid_request', 'cursor')
        deadline = value['authorization_valid_until_utc']
        if deadline is not None and parse_time(deadline) <= issued:
            unavailable('invalid_request', 'cursor')
        if current < issued or current >= expires or (deadline is not None and current >= parse_time(deadline)):
            unavailable('stale_cursor', 'cursor')

    def encode(self, payload: dict[str, Any]) -> str:
        self.contracts.validate('cursor', payload, output=True)
        self.times(payload, payload['issued_at_utc'])
        raw = canonical_json_bytes(payload)
        token = 'pc1.' + _b64(raw) + '.' + _b64(hmac.digest(self.config.secret, CURSOR.encode() + b'\0' + raw, hashlib.sha256))
        if len(token) > 8192:
            unavailable('environment_failure', 'capacity')
        return token

    def decode(self, token: Any, *, now: str) -> dict[str, Any]:
        try:
            if not isinstance(token, str) or len(token) > 8192 or not token.isascii():
                raise ValueError('token')
            prefix, body, signature = token.split('.')
            if prefix != 'pc1':
                raise ValueError('family')
            raw, mac = _unb64(body), _unb64(signature)
            if not hmac.compare_digest(mac, hmac.digest(self.config.secret, CURSOR.encode() + b'\0' + raw, hashlib.sha256)):
                raise ValueError('mac')
            value: dict[str, Any] = json.loads(raw, object_pairs_hook=_object)
            if canonical_json_bytes(value) != raw:
                raise ValueError('canonical')
            self.contracts.validate('cursor', value)
            self.times(value, now)
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, RecursionError, OverflowError) as exc:
            raise SpineValidationError('invalid_request:cursor', 'Invalid people cursor.') from exc
        if (value['key_id'], value['key_generation'], value['ledger_instance_id']) != (
            self.config.key_id, self.config.key_generation, self.config.ledger_instance_id
        ):
            unavailable('stale_cursor', 'cursor')
        return value
