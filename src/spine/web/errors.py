"""Non-disclosing errors at the trusted web boundary."""

from __future__ import annotations


class WebError(Exception):
    def __init__(self, code: str, status: int | None = None, *, domain_code: str | None = None, field: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = {k: v for k, v in {"domain_code": domain_code, "field": field}.items() if v is not None}
        self.status = (
            status
            or {
                "invalid_request": 400,
                "identity_unavailable": 403,
                "operation_unavailable": 404,
                "resource_unavailable": 404,
                "access_changed": 409,
                "command_id_unavailable": 409,
                "domain_conflict": 409,
                "domain_failure": 422,
                "capacity_exceeded": 429,
                "admission_unavailable": 503,
            }[code]
        )
