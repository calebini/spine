"""Internal paged reads with private, bounded continuation proofs.

No HTTP registration, package admission or capability advertisement. Instances
are service-owned, never request-owned. A lost proof requires a fresh query.
Only proofs are retained in memory; every page reassembles and reauthorizes data.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import asdict
from datetime import timedelta

from spine.commands.core import _occurrence_ordering_tuple
from spine.core.hashing import hash_canonical_json
from spine.web.read_authorization import authorization_identity
from spine.web.read_context import ReadBudget
from spine.web.read_contracts import READ_API, read_error
from spine.web.read_cursor import CURSOR, IDENTITY_FIELDS, CursorCodec, cursor_identity, service_time
from spine.web.read_release import read_authorized

RESPONSES = {
    "schedule.show": ("trusted-web-read-schedule-response.schema.json", "spine.trusted-web-schedule-view.v1"),
    "item.occurrences": ("trusted-web-read-occurrences-response.schema.json", "spine.trusted-web-occurrences.v1"),
    "agenda": ("trusted-web-read-agenda-response.schema.json", "spine.trusted-web-agenda.v2"),
}


def _family(payload):
    return {k: v for k, v in payload.items() if k not in {"stream", "last_key"}}


def _proof_size(proof):
    # Private accounting only. This encoding never enters a public hash or token.
    return len(json.dumps(asdict(proof), default=sorted, ensure_ascii=True).encode("ascii"))


def _agenda_key(row):
    return [
        row["view_local_date"], "0" if row["all_day"] else "1", row["sort_at_utc"],
        row["anchor_role"], row["activity"]["item_id"], (row["occurrence"] or {}).get("occurrence_key", ""),
    ]


def _page(rows, limit, previous, key):
    start = 0
    if previous is not None:
        # Rows already follow the canonical engine / projection ordering. Locate
        # the exact authenticated boundary without deriving occurrence identities.
        for index, row in enumerate(rows):
            if key(row) == (previous["stream"], previous["last_key"]):
                start = index + 1
                break
        else:
            raise read_error("invalid_request")
    selected = rows[start:start + limit]
    more = start + len(selected) < len(rows)
    return selected, more


class ReadPager:
    def __init__(self, config, contracts, *, cursor_key=None, max_proofs=128, max_proof_bytes=8 * 1024 * 1024):
        if not 1 <= max_proofs <= 128 or not 1 <= max_proof_bytes <= 8 * 1024 * 1024:
            raise read_error("admission_unavailable")
        self.config, self.contracts = config, contracts
        self.codec = CursorCodec(contracts, key=cursor_key)
        self.max_proofs, self.max_proof_bytes = max_proofs, max_proof_bytes
        self._proofs = {}
        self._proof_bytes = 0
        self._lock = threading.Lock()

    def _prune(self, now):
        for key, (_, deadline, size) in list(self._proofs.items()):
            if now >= deadline:
                del self._proofs[key]
                self._proof_bytes -= size

    def _recall(self, family, now):
        with self._lock:
            self._prune(now)
            entry = self._proofs.get(hash_canonical_json(family))
            if entry is None:
                raise read_error("access_changed")
            return copy.deepcopy(entry[0])

    def _remember(self, family, proof, now):
        size, key = _proof_size(proof), hash_canonical_json(family)
        deadline = min(family["expires_at_utc"], family["authorization_valid_until_utc"] or family["expires_at_utc"])
        with self._lock:
            self._prune(now)
            if key in self._proofs:
                if self._proofs[key][0] != proof:
                    # A same-second query must not overwrite an earlier proof
                    # with identical public fields but changed private authority.
                    raise read_error("access_changed")
                return
            if len(self._proofs) >= self.max_proofs or self._proof_bytes + size > self.max_proof_bytes:
                raise read_error("capacity_exceeded")
            self._proofs[key] = (copy.deepcopy(proof), deadline, size)
            self._proof_bytes += size

    def read(self, route, body, *, selection, now, clock=time.monotonic, before_release=None):
        budget = ReadBudget(self.contracts, clock=clock, sql_steps=self.config.sql_steps)
        budget.deadline = min(budget.deadline, clock() + self.config.request_seconds)
        normalized, query_hash = self.contracts.normalize(route, copy.deepcopy(body))
        request = normalized["request"]
        transport = body["request"]
        tokens = transport.get("section_cursors", {}) if route == "schedule.show" else (
            {"page": transport["cursor"]} if "cursor" in transport else {}
        )
        state = {"cursors": {}, "family": None, "retain": False}

        def continuation(snapshot, selected):
            identity = cursor_identity(authorization_identity(snapshot, selected))
            for name, token in tokens.items():
                payload = self.codec.decode(token, now=snapshot.evaluated_at_utc)
                if (payload["route"] != route or payload["query_hash"] != query_hash
                        or payload.get("item_id") != request.get("item_id")
                        or (route == "schedule.show" and payload["stream"] != name)
                        or (route == "item.occurrences" and payload["range_basis"] != request["range_basis"])):
                    raise read_error("invalid_request")
                if any(payload[field] != identity[field] for field in IDENTITY_FIELDS):
                    raise read_error("access_changed")
                family = _family(payload)
                if state["family"] is not None and family != state["family"]:
                    raise read_error("invalid_request")
                state["family"] = family
                state["cursors"][name] = payload
            if state["family"] is None:
                return None
            return self._recall(state["family"], snapshot.evaluated_at_utc)

        def project(assembly, proof):
            identity = cursor_identity(proof.identity)
            if state["family"] is None:
                issued = proof.authorization_evaluated_at_utc
                try:
                    expires = (service_time(issued) + timedelta(
                        seconds=self.contracts.bounds["cursor_seconds_max"],
                    )).isoformat().replace("+00:00", "Z")
                except OverflowError as exc:
                    raise read_error("admission_unavailable") from exc
                state["family"] = {
                    "contract_version": CURSOR, **identity, "route": route, "query_hash": query_hash,
                    "source_snapshot_hash": proof.source_snapshot_hash,
                    "issued_at_utc": issued, "expires_at_utc": expires,
                    "authorization_evaluated_at_utc": proof.authorization_evaluated_at_utc,
                    "authorization_valid_until_utc": proof.authorization_valid_until_utc,
                    **({"item_id": request["item_id"]} if route != "agenda" else {}),
                    **({"range_basis": request["range_basis"]} if route == "item.occurrences" else {}),
                }
            family = state["family"]
            if family["source_snapshot_hash"] != proof.source_snapshot_hash:
                raise read_error("access_changed")

            def token(stream, last):
                state["retain"] = True
                return self.codec.encode({**family, "stream": stream, "last_key": last})

            if route == "schedule.show":
                activity, sections = assembly
                projected = {}
                rules = self.contracts.artifacts["trusted-web-read-cursor.v2.json"]["section_order"]
                for name, section in sections.items():
                    if not section.collection or section.state["availability"] != "available":
                        projected[name] = section.complete_value()
                        continue
                    def key(row, name=name):
                        return name, [row[field] for field in rules[name]]
                    rows, more = _page(section.rows, int(request["section_limit"]), state["cursors"].get(name), key)
                    projected[name] = {**section.state, "entries": rows, "has_more": more,
                                       "next_cursor": token(*key(rows[-1])) if more else None}
                result = {"activity": activity, "sections": projected}
            elif route == "item.occurrences":
                def key(row):
                    return "occurrences", list(_occurrence_ordering_tuple(row, request["range_basis"]))
                rows, more = _page(assembly.occurrences, int(request["limit"]), state["cursors"].get("page"), key)
                result = {
                    "activity": assembly.activity, "coverage": assembly.coverage,
                    "range": {k: request[k] for k in ("range_start", "range_end", "range_basis")},
                    "occurrences": rows, "limit": request["limit"], "has_more": more,
                    "next_cursor": token(*key(rows[-1])) if more else None,
                }
            else:
                combined = [("resolved", row) for row in assembly.entries] + [("unplaced", row) for row in assembly.unplaced_items]
                def key(pair):
                    stream, row = pair
                    return stream, _agenda_key(row) if stream == "resolved" else [row["activity"]["item_id"]]
                rows, more = _page(combined, int(request["limit"]), state["cursors"].get("page"), key)
                result = {
                    "range": {k: request[k] for k in (
                        "evaluated_at_utc", "range_start_local", "range_end_local", "timezone", "timezone_database_version",
                    )},
                    "coverage": assembly.coverage, "entries": [r for s, r in rows if s == "resolved"],
                    "unplaced_items": [r for s, r in rows if s == "unplaced"], "limit": request["limit"],
                    "has_more": more, "next_cursor": token(*key(rows[-1])) if more else None,
                }
            schema, contract = RESPONSES[route]
            response = {
                "contract_version": READ_API, "ok": True, "identity_basis": "self_selected",
                **{k: v for k, v in identity.items() if k not in {"ledger_id", "realm_id", "recovery_epoch"}},
                "result_contract": contract, "result": result,
            }
            self.contracts.validate(schema, response, output=True)
            budget.check_response(response)
            return response

        def release_check(at):
            self.codec.check_times(state["family"], at)

        clean_body = {**body, "request": {k: v for k, v in transport.items() if k not in {"cursor", "section_cursors"}}}
        fenced = read_authorized(
            self.config, self.contracts, route, clean_body, selection=selection, now=now, clock=clock,
            budget=budget, continuation=continuation, project=project, release_check=release_check, before_release=before_release,
        )
        if state["retain"]:
            self._remember(state["family"], fenced.proof, now())
        budget.check()
        release_check(now())
        # Return only the closed page. Neither assembly nor private proof escapes.
        return fenced.page
