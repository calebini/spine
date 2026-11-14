"""Trusted-local public admission; the shared handler owns all transactions."""

from typing import Any

from spine.commands.context import CommandContext
from spine.commands.recurring_task_package import packaged
from spine.commands.recurring_tasks import execute
from spine.commands.registry import missing_runtime_contract_versions
from spine.core.errors import SpineValidationError
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.transactions import LedgerConnection


def execute_public(command: str, request: Any, context: CommandContext) -> dict[str, Any]:
    try:
        if context.transport_metadata not in ({}, {"adapter": "cli"}) or not isinstance(context.ledger, LedgerConnection):
            raise SpineValidationError("environment_failure:admission", "recurring tasks require trusted-local admission")
        verify_runtime_schema(context.ledger)
        if missing_runtime_contract_versions(command):
            raise SpineValidationError("environment_failure:runtime_contracts", "required recurring-task contracts unavailable")
        return execute(command, request, context, contracts=packaged())
    except SpineValidationError as exc:
        code, _, field = exc.code.partition(":")
        return {"ok": False, "command": command, "changed": False,
                "response_contract": "spine.recurring-related-tasks-response.v1",
                "error": {"code": code, "field": field or "admission", "message": exc.message}}
