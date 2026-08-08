"""CLI adapter for the Spine agent command contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from spine.commands.context import CommandContext
from spine.commands.core import MVP_COMMANDS, WRITE_COMMANDS, handle
from spine.ledger.migrate import verify_schema
from spine.ledger.sqlite import connect

EXIT_BY_ERROR = {
    "invalid_request": 2,
    "unsupported_command": 2,
    "unsupported_field": 2,
    "missing_required_field": 2,
    "invalid_timestamp": 2,
    "wrong_item_type": 2,
    "invalid_state_transition": 2,
    "referenced_row_not_found": 4,
    "stale_version": 5,
    "semantic_conflict": 6,
    "environment_failure": 7,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.db:
        _dump({"ok": False, "error": {"code": "invalid_request", "message": "--db is required", "field": "db"}}, pretty=args.pretty)
        return 3
    if not args.command_words:
        _dump(
            {"ok": False, "error": {"code": "unsupported_command", "message": "command is required", "field": "command"}},
            pretty=args.pretty,
        )
        return 2
    command = ".".join(args.command_words)
    if command not in MVP_COMMANDS:
        response = {"ok": False, "error": {"code": "unsupported_command", "message": f"unsupported command: {command}", "field": "command"}}
        if _is_dotted_command(command):
            response["command"] = command
        _dump(response, pretty=args.pretty)
        return 2
    if args.if_absent and command != "reminder.create":
        _dump(
            {
                "ok": False,
                "command": command,
                "error": {
                    "code": "unsupported_field",
                    "message": "--if-absent is only supported for reminder.create",
                    "field": "if_absent",
                },
            },
            pretty=args.pretty,
        )
        return 2
    try:
        request = {} if command == "system.info" and args.input == "-" else _load_request(args.input)
        if args.if_absent:
            request = {**request, "if_absent": True}
        if args.generate_command_id:
            if "command_id" in request:
                _dump(
                    {
                        "ok": False,
                        "command": command,
                        "error": {
                            "code": "invalid_request",
                            "message": "--generate-command-id requires command_id to be omitted",
                            "field": "command_id",
                        },
                    },
                    pretty=args.pretty,
                )
                return 2
            request = {**request, "command_id": _generated_command_id(command, request, args.db)}
        connection = _open_ledger(args.db, writable=not args.dry_run and command in WRITE_COMMANDS)
    except CliPreflightError as exc:
        _dump(
            {"ok": False, "command": command, "error": {"code": exc.code, "message": exc.message, "field": exc.field}}, pretty=args.pretty
        )
        return 3
    try:
        context = CommandContext(
            ledger=connection,
            ledger_path=str(Path(args.db).expanduser()),
            dry_run=args.dry_run,
            transport_metadata={"adapter": "cli"},
            adapter_bindings=_adapter_bindings(args),
        )
        response = handle(command, request, context)
    except Exception as exc:  # pragma: no cover - final transport fallback
        response = {"ok": False, "command": command, "error": {"code": "runtime_failure", "message": str(exc)}}
    finally:
        connection.close()
    _dump(response, pretty=args.pretty)
    if response.get("ok") is True:
        return 0
    error = response.get("error")
    code = error.get("code") if isinstance(error, Mapping) else "runtime_failure"
    return EXIT_BY_ERROR.get(str(code), 1)


class CliPreflightError(Exception):
    def __init__(self, code: str, message: str, field: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spine-command")
    parser.add_argument("command_words", nargs="*")
    parser.add_argument("--db")
    parser.add_argument("--input", default="-")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--if-absent", action="store_true")
    parser.add_argument("--generate-command-id", action="store_true")
    parser.add_argument("--openclaw-whatsapp", action="store_true")
    return parser


def _load_request(input_ref: str) -> dict[str, Any]:
    try:
        text = sys.stdin.read() if input_ref == "-" else Path(input_ref).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliPreflightError("invalid_request", str(exc), "input") from exc
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise CliPreflightError("invalid_request", str(exc), "input") from exc
    if not isinstance(value, dict):
        raise CliPreflightError("invalid_request", "input JSON must be an object", "input")
    return value


def _open_ledger(db: str, *, writable: bool):
    path = Path(db).expanduser()
    if not path.exists():
        raise CliPreflightError("invalid_request", "ledger database does not exist", "db")
    if writable:
        if not os.access(path, os.W_OK) or not os.access(path.parent, os.W_OK):
            raise CliPreflightError("invalid_request", "ledger database is not writable", "db")
    else:
        if not os.access(path, os.R_OK):
            raise CliPreflightError("invalid_request", "ledger database is not readable", "db")
    connection = connect(path)
    try:
        verify_schema(connection)
    except Exception as exc:
        connection.close()
        raise CliPreflightError("invalid_request", str(exc), "db") from exc
    return connection


def _adapter_bindings(args: argparse.Namespace) -> dict[str, object]:
    if not args.openclaw_whatsapp:
        return {}
    return {"openclaw": {"binding_name": "openclaw", "channel": "whatsapp", "configured": True}}


def _is_dotted_command(command: str) -> bool:
    parts = command.split(".")
    return len(parts) == 2 and all(part.isalpha() for part in parts)


def _generated_command_id(command: str, request: Mapping[str, Any], db: str) -> str:
    from spine.core.hashing import hash_canonical_json

    payload = {
        "derivation_version": "spine.cli-command-id.v1",
        "command": command,
        "db_path": _lexical_db_path(db),
        "request": {key: value for key, value in request.items() if key != "command_id"},
    }
    return "cmd_" + hash_canonical_json(payload)


def _lexical_db_path(db: str) -> str:
    expanded = os.path.expanduser(db)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(os.getcwd(), expanded))


def _dump(response: Mapping[str, Any], *, pretty: bool) -> None:
    json.dump(response, sys.stdout, indent=2 if pretty else None, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
