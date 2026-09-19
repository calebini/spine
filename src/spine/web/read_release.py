"""Internal first-read and retained-proof release fences. No HTTP or cursor codec.

The result remains an unpaged assembly. A future transport must not serialize the
private proof or skip these checks when introducing pagination and public routes.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError
from spine.web.read_assembly import assemble_agenda, assemble_occurrences
from spine.web.read_authorization import authorization_deadline, authorization_evidence, authorization_identity
from spine.web.read_context import OptionalReadUnavailable, ReadBudget, read_snapshot
from spine.web.read_contracts import read_error
from spine.web.read_projection import candidate_ids
from spine.web.read_sections import assemble_detail


@dataclass(frozen=True)
class ReadProof:
    route: str
    query_hash: str
    source_snapshot_hash: str
    facts: tuple[dict[str, str], ...]
    authorization_evaluated_at_utc: str
    authorization_valid_until_utc: str | None
    identity: dict[str, Any]
    probes: dict[str, Any]
    core_probe_keys: frozenset[str]
    authorization_hash: str
    assembly_hash: str
    discovered: tuple[str, ...] | None


@dataclass(frozen=True)
class FencedRead:
    assembly: Any
    proof: ReadProof
    page: Any = None


def _selected(selection):
    value = selection()
    if (not isinstance(value, tuple) or len(value) != 2
            or any(not isinstance(v, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}", v) is None for v in value)):
        raise read_error("identity_unavailable")
    return value


def _plain(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _assemble(snapshot, route, normalized):
    request = normalized["request"]
    guards = {k: normalized[k] for k in snapshot.contracts.normalization["null_guard_defaults"] if normalized[k] is not None}
    if route == "agenda":
        roots = candidate_ids(snapshot, request)
        if guards.get("expected_access_epoch", str(snapshot.permissions.identity["access_epoch"])) != str(
            snapshot.permissions.identity["access_epoch"]
        ):
            raise read_error("access_changed")
        result = assemble_agenda(snapshot, request)
        sections = result.sections
        for value in result.unplaced_items:
            snapshot.proof.cores[value["activity"]["item_id"]] = value["activity"]
    elif route == "item.occurrences":
        result = assemble_occurrences(snapshot, request, guards=guards)
        roots, sections = [request["item_id"]], {}
        snapshot.proof.cores[request["item_id"]] = result.activity
    else:
        result = assemble_detail(snapshot, request["item_id"], request["include"], guards=guards)
        roots, sections = [request["item_id"]], {request["item_id"]: result[1]}
    for identity in roots:
        snapshot.proof.add("item", identity, snapshot.proof.cores[identity])
    rules = snapshot.contracts.artifacts["trusted-web-read-projection.v1.json"]["sections"]
    for identity, values in sections.items():
        for name, section in values.items():
            snapshot.proof.section(identity, name, section, rules)
    return result


def _fence(snapshot, previous, selection, route, query_hash):
    if previous.route != route or previous.query_hash != query_hash:
        raise read_error("invalid_request")
    if authorization_identity(snapshot, selection) != previous.identity:
        raise read_error("access_changed")
    deadline = previous.authorization_valid_until_utc
    if snapshot.evaluated_at_utc < previous.authorization_evaluated_at_utc or (
        deadline is not None and snapshot.evaluated_at_utc >= deadline
    ):
        raise read_error("access_changed")
    if authorization_evidence(snapshot, previous.probes, previous.core_probe_keys) != previous.authorization_hash:
        raise read_error("access_changed")


def read_authorized(
    config, contracts, route, body, *, selection, now, clock=time.monotonic, before_release=None, previous=None,
    budget=None, continuation=None, project=None, release_check=None,
):
    """Assemble, close the transaction, and fence in a fresh read-only snapshot.

    selection/now are trusted service callbacks, not request fields. previous is a
    retained private ReadProof, never a decoded or caller-supplied cursor payload.
    The deterministic hook is for internal tests and runs after assembly closes.
    One budget/deadline covers both transactions and all mandatory proof work.
    Internal paging callbacks run after admission and before the fresh fence;
    none is request-controlled. The transport adapter owns the optional budget.
    """
    normalized, query_hash = contracts.normalize(route, copy.deepcopy(body))
    if "cursor" in body["request"] or "section_cursors" in body["request"]:
        raise read_error("invalid_request")  # Wire continuation is a subsequent slice.
    if budget is None:
        budget = ReadBudget(contracts, clock=clock, sql_steps=config.sql_steps)
        budget.deadline = min(budget.deadline, clock() + config.request_seconds)
    account, selected = _selected(selection)
    try:
        with read_snapshot(config, contracts, account, evaluated_at_utc=now(), budget=budget, collect_proof=True) as snapshot:
            if continuation is not None:
                previous = continuation(snapshot, selected)
            if previous is not None:
                _fence(snapshot, previous, selected, route, query_hash)
            try:
                assembly = _assemble(snapshot, route, normalized)
            except WebError as exc:
                if previous is not None and exc.code in {"version_changed", "domain_failure"}:
                    raise read_error("access_changed") from exc
                raise
            source_hash = snapshot.proof.digest(route, query_hash)
            assembly_hash = hash_canonical_json(_plain(assembly))
            if previous is not None and (
                source_hash != previous.source_snapshot_hash or assembly_hash != previous.assembly_hash
                or snapshot.permissions.discovered != previous.discovered
            ):
                raise read_error("access_changed")
            deadline = authorization_deadline(snapshot)
            if previous is not None and previous.authorization_valid_until_utc is not None:
                deadline = min(deadline or previous.authorization_valid_until_utc, previous.authorization_valid_until_utc)
            proof = ReadProof(
                route, query_hash, source_hash, tuple(snapshot.proof.records()),
                snapshot.evaluated_at_utc if previous is None else previous.authorization_evaluated_at_utc,
                deadline, authorization_identity(snapshot, selected),
                copy.deepcopy(snapshot.permissions.probes), frozenset(snapshot.permissions.core_probe_keys),
                authorization_evidence(snapshot, snapshot.permissions.probes, snapshot.permissions.core_probe_keys), assembly_hash,
                snapshot.permissions.discovered,
            )
            page = None if project is None else project(assembly, proof)
            budget.check()
        if before_release is not None:
            before_release()
        fresh_account, fresh_selection = _selected(selection)
        with read_snapshot(config, contracts, fresh_account, evaluated_at_utc=now(), budget=budget, collect_proof=True) as fresh:
            _fence(fresh, proof, fresh_selection, route, query_hash)
            # Guards were checked after root admission in the first transaction;
            # now source differences have route/continuation-specific errors.
            unguarded = {**normalized, **dict.fromkeys(contracts.normalization["null_guard_defaults"])}
            try:
                rebuilt = _assemble(fresh, route, unguarded)
            except WebError as exc:
                if exc.code == "resource_unavailable":
                    raise read_error("access_changed") from exc
                if exc.code == "domain_failure":
                    raise read_error("access_changed" if route == "agenda" or previous else "version_changed") from exc
                raise
            if proof.discovered != fresh.permissions.discovered:
                raise read_error("access_changed")
            fresh_deadline = authorization_deadline(fresh)
            if fresh_deadline != deadline:
                raise read_error("access_changed")
            if (fresh.proof.digest(route, query_hash) != proof.source_snapshot_hash
                    or hash_canonical_json(_plain(rebuilt)) != proof.assembly_hash):
                if (budget.steps["optional"] >= budget.bounds["optional_sql_vm_steps"]
                        or budget.bytes["optional"] > budget.bounds["optional_total_bytes"]):
                    raise read_error("capacity_exceeded")
                raise read_error("access_changed" if route == "agenda" or previous else "version_changed")
            budget.check()
            released_at = now()
            if release_check is not None:
                release_check(released_at)
            if (_selected(selection) != (fresh_account, fresh_selection)
                    or released_at < fresh.evaluated_at_utc
                    or (proof.authorization_valid_until_utc is not None and released_at >= proof.authorization_valid_until_utc)):
                raise read_error("access_changed")
        return FencedRead(assembly, proof, page)
    except OptionalReadUnavailable as exc:
        # A mandatory release proof cannot degrade into an optional section.
        raise read_error("capacity_exceeded") from exc
