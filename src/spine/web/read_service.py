"""Selected-identity v2 reads in the existing trusted web backend."""

from __future__ import annotations

import time

from spine.web.read_authorization import authorization_identity
from spine.web.read_context import ReadBudget, read_snapshot
from spine.web.read_contracts import READ_API, ReadContracts, read_error
from spine.web.read_cursor import cursor_identity, service_time
from spine.web.read_pages import ReadPager
from spine.web.read_release import _selected
from spine.web.service import _now


class ReadService:
    def __init__(self, config):
        self.config = config
        self.contracts = ReadContracts.packaged()
        self.pager = ReadPager(config, self.contracts)
        self.now, self.clock = _now, time.monotonic
        # Trusted deterministic test seam; never populated by HTTP/request data.
        self.before_release = None

    def execute(self, route, body, *, selection, encode=None):
        return self.pager.read(
            route, body, selection=selection, now=self.now, clock=self.clock, before_release=self.before_release,
            encode=encode,
        )

    def capabilities(self, *, selection, encode=None):
        budget = ReadBudget(self.contracts, clock=self.clock, sql_steps=self.config.sql_steps)
        budget.deadline = min(budget.deadline, self.clock() + self.config.request_seconds)
        account, selected = _selected(selection)
        evaluated = self.now()
        with read_snapshot(self.config, self.contracts, account, evaluated_at_utc=evaluated, budget=budget) as snapshot:
            identity = authorization_identity(snapshot, selected)
            public = cursor_identity(identity)
            response = {
                "contract_version": READ_API, "ok": True, "identity_basis": "self_selected",
                **{k: v for k, v in public.items() if k not in {"ledger_id", "realm_id", "recovery_epoch"}},
                "result_contract": "spine.trusted-web-read-registry.v1",
                "result": self.contracts.schemas["trusted-web-read-capabilities.schema.json"]["properties"]["result"]["const"],
            }
            self.contracts.validate("trusted-web-read-capabilities.schema.json", response, output=True)
            budget.check_response(response)
            if encode is not None:
                response = encode(response)
                if not isinstance(response, bytes) or len(response) > self.contracts.bounds["response_bytes"]:
                    raise read_error("capacity_exceeded")
        if self.before_release is not None:
            self.before_release()
        account, selected = _selected(selection)
        with read_snapshot(self.config, self.contracts, account, evaluated_at_utc=self.now(), budget=budget) as fresh:
            if identity != authorization_identity(fresh, selected):
                raise read_error("access_changed")
            if _selected(selection) != (account, selected) or service_time(self.now()) < service_time(evaluated):
                raise read_error("access_changed")
        return response
