"""Bounded read projection for canonical owner scopes."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.registry import missing_runtime_contract_versions
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import hash_canonical_json
from spine.ledger.preflight import verify_runtime_schema

COMMAND = "owner_scope.list"
CONTRACT_VERSION = "spine.owner-scope-discovery.v1"
RESPONSE_CONTRACT = "spine.owner-scope-list-response.v1"
CURSOR_CONTRACT = "spine.owner-scope-list-cursor.v1"

_OWNER_KIND_ORDER = ("system", "subject", "subject_group")
_STATUS_ORDER = ("active", "inactive")
_SUBJECT_KIND_ORDER = ("person", "agent")
_GROUP_KIND_ORDER = ("household", "project", "team", "transport_group")
_OWNER_KIND_RANK = {kind: index for index, kind in enumerate(_OWNER_KIND_ORDER)}


def handle_owner_scope_list(
    request: Mapping[str, Any], context: CommandContext
) -> dict[str, Any]:
    """Return one deterministic page of canonical owner identities."""

    _check_fields(
        request,
        {
            "contract_version",
            "owner_kinds",
            "statuses",
            "subject_kinds",
            "group_kinds",
            "limit",
            "cursor",
        },
    )
    _require_contract(request)
    owner_kinds = _normalize_filter(
        request,
        "owner_kinds",
        allowed=_OWNER_KIND_ORDER,
        default=_OWNER_KIND_ORDER,
    )
    statuses = _normalize_filter(
        request,
        "statuses",
        allowed=_STATUS_ORDER,
        default=("active",),
    )
    subject_kinds = _normalize_scoped_filter(
        request,
        field="subject_kinds",
        owner_kind="subject",
        selected_owner_kinds=owner_kinds,
        allowed=_SUBJECT_KIND_ORDER,
    )
    group_kinds = _normalize_scoped_filter(
        request,
        field="group_kinds",
        owner_kind="subject_group",
        selected_owner_kinds=owner_kinds,
        allowed=_GROUP_KIND_ORDER,
    )
    limit_text, limit = _limit(request.get("limit"))
    query_hash = hash_canonical_json(
        {
            "contract_version": CONTRACT_VERSION,
            "owner_kinds": list(owner_kinds),
            "statuses": list(statuses),
            "subject_kinds": list(subject_kinds),
            "group_kinds": list(group_kinds),
        }
    )
    connection = _connection(context)
    _require_runtime(connection)

    cursor = _decode_cursor(request.get("cursor"))
    if cursor is not None and cursor["query_hash"] != query_hash:
        raise SpineValidationError(
            "invalid_request:cursor", "cursor query facts do not match"
        )

    connection.execute("SAVEPOINT spine_owner_scope_list")
    try:
        source_generation = _source_generation(connection)
        last = None
        if cursor is not None:
            if cursor["source_generation"] != source_generation:
                raise SpineValidationError(
                    "stale_cursor:cursor", "owner-scope catalog changed"
                )
            last = _last_ordering_tuple(
                cursor["last_ordering_tuple"],
                owner_kinds=owner_kinds,
                statuses=statuses,
            )
        selected = _select_entries(
            connection,
            owner_kinds=owner_kinds,
            statuses=statuses,
            subject_kinds=subject_kinds,
            group_kinds=group_kinds,
            last=last,
            bound=limit + 1,
        )
    except Exception:
        connection.execute("ROLLBACK TO spine_owner_scope_list")
        connection.execute("RELEASE spine_owner_scope_list")
        raise
    else:
        connection.execute("RELEASE spine_owner_scope_list")

    has_more = len(selected) > limit
    page = selected[:limit]
    next_cursor = None
    if has_more:
        next_cursor = _encode_cursor(
            query_hash=query_hash,
            source_generation=source_generation,
            last_ordering_tuple=list(page[-1][0]),
        )
    return {
        "ok": True,
        "command": COMMAND,
        "response_contract": RESPONSE_CONTRACT,
        "owner_kinds": list(owner_kinds),
        "statuses": list(statuses),
        "subject_kinds": list(subject_kinds),
        "group_kinds": list(group_kinds),
        "limit": limit_text,
        "query_hash": query_hash,
        "source_generation": source_generation,
        "entries": [entry for _, entry in page],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _select_entries(
    connection: sqlite3.Connection,
    *,
    owner_kinds: tuple[str, ...],
    statuses: tuple[str, ...],
    subject_kinds: tuple[str, ...],
    group_kinds: tuple[str, ...],
    last: tuple[str, str, str] | None,
    bound: int,
) -> list[tuple[tuple[str, str, str], dict[str, Any]]]:
    selected: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
    last_rank = int(last[0]) if last is not None else -1

    system_tuple = ("0", "", "system")
    if (
        "system" in owner_kinds
        and "active" in statuses
        and (last is None or system_tuple > last)
    ):
        selected.append(
            (
                system_tuple,
                {
                    "owner_scope_key": "system",
                    "owner": {"owner_kind": "system"},
                    "identity_kind": "system",
                    "display_name": "Spine system",
                    "status": "active",
                    "source": "derived_system",
                },
            )
        )

    if "subject" in owner_kinds and last_rank <= 1 and len(selected) < bound:
        after_id = last[1] if last is not None and last_rank == 1 else None
        rows = _bounded_identity_rows(
            connection,
            table="subjects",
            id_field="subject_id",
            kind_field="subject_kind",
            statuses=statuses,
            identity_kinds=subject_kinds,
            after_id=after_id,
            bound=bound - len(selected),
        )
        selected.extend(
            (
                ("1", str(row["subject_id"]), f"subject:{row['subject_id']}"),
                {
                    "owner_scope_key": f"subject:{row['subject_id']}",
                    "owner": {
                        "owner_kind": "subject",
                        "owner_subject_id": str(row["subject_id"]),
                    },
                    "identity_kind": str(row["subject_kind"]),
                    "display_name": str(row["display_name"]),
                    "status": str(row["status"]),
                    "source": "subjects",
                },
            )
            for row in rows
        )

    if "subject_group" in owner_kinds and last_rank <= 2 and len(selected) < bound:
        after_id = last[1] if last is not None and last_rank == 2 else None
        rows = _bounded_identity_rows(
            connection,
            table="subject_groups",
            id_field="group_id",
            kind_field="group_kind",
            statuses=statuses,
            identity_kinds=group_kinds,
            after_id=after_id,
            bound=bound - len(selected),
        )
        selected.extend(
            (
                (
                    "2",
                    str(row["group_id"]),
                    f"subject_group:{row['group_id']}",
                ),
                {
                    "owner_scope_key": f"subject_group:{row['group_id']}",
                    "owner": {
                        "owner_kind": "subject_group",
                        "owner_group_id": str(row["group_id"]),
                    },
                    "identity_kind": str(row["group_kind"]),
                    "display_name": str(row["display_name"]),
                    "status": str(row["status"]),
                    "source": "subject_groups",
                },
            )
            for row in rows
        )
    return selected[:bound]


def _bounded_identity_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    id_field: str,
    kind_field: str,
    statuses: tuple[str, ...],
    identity_kinds: tuple[str, ...],
    after_id: str | None,
    bound: int,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for status in statuses:
        for identity_kind in identity_kinds:
            query = (
                f"SELECT {id_field}, {kind_field}, display_name, status "
                f"FROM {table} WHERE status = ? AND {kind_field} = ?"
            )
            params: list[Any] = [status, identity_kind]
            if after_id is not None:
                query += f" AND {id_field} > ?"
                params.append(after_id)
            query += f" ORDER BY {id_field} LIMIT ?"
            params.append(bound)
            rows.extend(connection.execute(query, tuple(params)).fetchall())
    rows.sort(key=lambda row: str(row[id_field]).encode("utf-8"))
    return rows[:bound]


def _normalize_scoped_filter(
    request: Mapping[str, Any],
    *,
    field: str,
    owner_kind: str,
    selected_owner_kinds: tuple[str, ...],
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    if owner_kind not in selected_owner_kinds:
        if field in request:
            raise SpineValidationError(
                f"invalid_request:{field}",
                f"{field} requires owner_kinds to include {owner_kind}",
            )
        return ()
    return _normalize_filter(request, field, allowed=allowed, default=allowed)


def _normalize_filter(
    request: Mapping[str, Any],
    field: str,
    *,
    allowed: tuple[str, ...],
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if field not in request:
        return default
    value = request[field]
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise SpineValidationError(
            f"invalid_request:{field}", f"{field} must be an array"
        )
    entries = list(value)
    if not entries or any(not isinstance(entry, str) for entry in entries):
        raise SpineValidationError(
            f"invalid_request:{field}",
            f"{field} must be a non-empty array of strings",
        )
    if len(entries) != len(set(entries)):
        raise SpineValidationError(
            f"invalid_request:{field}", f"{field} values must be unique"
        )
    unsupported = sorted(set(entries) - set(allowed))
    if unsupported:
        raise SpineValidationError(
            f"invalid_request:{field}",
            f"{field} contains unsupported values: {', '.join(unsupported)}",
        )
    return tuple(entry for entry in allowed if entry in entries)


def _limit(value: Any) -> tuple[str, int]:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or value.startswith("0")
    ):
        raise SpineValidationError(
            "invalid_request:limit", "limit must be a canonical decimal string"
        )
    parsed = int(value)
    if parsed < 1 or parsed > 500:
        raise SpineValidationError(
            "invalid_request:limit", "limit must be between 1 and 500"
        )
    return value, parsed


def _source_generation(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        """
        SELECT owner_scope_generation
        FROM owner_scope_catalog_state
        WHERE singleton_id = 1
        """
    ).fetchone()
    if row is None:
        raise SpineValidationError(
            "runtime_failure:owner_scope_generation",
            "owner-scope generation state is missing",
        )
    generation = row["owner_scope_generation"]
    if not isinstance(generation, int) or generation < 0:
        raise SpineValidationError(
            "runtime_failure:owner_scope_generation",
            "owner-scope generation state is invalid",
        )
    return str(generation)


def _encode_cursor(
    *,
    query_hash: str,
    source_generation: str,
    last_ordering_tuple: list[str],
) -> str:
    payload = {
        "cursor_contract": CURSOR_CONTRACT,
        "query_hash": query_hash,
        "source_generation": source_generation,
        "last_ordering_tuple": last_ordering_tuple,
    }
    envelope = {"payload": payload, "integrity_hash": hash_canonical_json(payload)}
    return base64.urlsafe_b64encode(canonical_json_bytes(envelope)).decode("ascii").rstrip("=")


def _decode_cursor(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, str) or value == "":
        raise SpineValidationError(
            "invalid_request:cursor", "cursor must be a non-empty string"
        )
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or canonical_json_bytes(envelope) != raw:
            raise ValueError("cursor encoding is not canonical")
        if set(envelope) != {"payload", "integrity_hash"}:
            raise ValueError("cursor envelope is invalid")
        payload = envelope["payload"]
        if not isinstance(payload, dict) or envelope["integrity_hash"] != hash_canonical_json(payload):
            raise ValueError("cursor integrity mismatch")
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SpineValidationError("invalid_request:cursor", "cursor is invalid") from exc
    if set(payload) != {
        "cursor_contract",
        "query_hash",
        "source_generation",
        "last_ordering_tuple",
    }:
        raise SpineValidationError("invalid_request:cursor", "cursor facts are invalid")
    if (
        payload.get("cursor_contract") != CURSOR_CONTRACT
        or not isinstance(payload.get("query_hash"), str)
        or not isinstance(payload.get("source_generation"), str)
        or not isinstance(payload.get("last_ordering_tuple"), list)
    ):
        raise SpineValidationError("invalid_request:cursor", "cursor facts are invalid")
    return dict(payload)


def _last_ordering_tuple(
    value: Any,
    *,
    owner_kinds: tuple[str, ...],
    statuses: tuple[str, ...],
) -> tuple[str, str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(not isinstance(entry, str) for entry in value)
        or value[0] not in {"0", "1", "2"}
    ):
        raise SpineValidationError(
            "invalid_request:cursor", "cursor ordering tuple is invalid"
        )
    result = (value[0], value[1], value[2])
    rank = int(result[0])
    owner_kind = _OWNER_KIND_ORDER[rank]
    expected_key = (
        "system"
        if rank == 0
        else f"subject:{result[1]}"
        if rank == 1
        else f"subject_group:{result[1]}"
    )
    if (
        owner_kind not in owner_kinds
        or result[2] != expected_key
        or (rank == 0 and (result[1] != "" or "active" not in statuses))
        or (rank != 0 and result[1] == "")
    ):
        raise SpineValidationError(
            "invalid_request:cursor", "cursor ordering tuple is invalid"
        )
    return result


def _require_contract(request: Mapping[str, Any]) -> None:
    value = request.get("contract_version")
    if value is None:
        raise SpineValidationError(
            "missing_contract_version", "contract_version is required"
        )
    if value != CONTRACT_VERSION:
        raise SpineValidationError(
            "invalid_request:contract_version",
            f"contract_version must be {CONTRACT_VERSION}",
        )


def _require_runtime(connection: sqlite3.Connection) -> None:
    missing = missing_runtime_contract_versions(COMMAND)
    if missing:
        raise SpineValidationError(
            "environment_failure:runtime_contracts",
            f"missing required runtime contracts: {', '.join(missing)}",
        )
    try:
        verify_runtime_schema(connection)
    except SpineValidationError as exc:
        raise SpineValidationError(
            "environment_failure:ledger_schema", exc.message
        ) from exc


def _check_fields(request: Mapping[str, Any], allowed: set[str]) -> None:
    for key in request:
        if key not in allowed:
            raise SpineValidationError(
                f"unsupported_field:{key}", f"unsupported field for {COMMAND}: {key}"
            )


def _connection(context: CommandContext) -> sqlite3.Connection:
    if context.ledger is None:
        raise SpineValidationError(
            "invalid_request:ledger", f"{COMMAND} requires CommandContext.ledger"
        )
    return context.ledger
