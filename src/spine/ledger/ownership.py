"""Bounded ownership state; no realm, account or authority is inferred."""

from __future__ import annotations

import sqlite3
from typing import Any, NoReturn

from spine.core.errors import SpineValidationError
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.transactions import LedgerConnection

MAX_EPOCH = 9223372036854775807
STATE_CONTRACT = "spine.ownership-access-state.v1"


def invalid() -> NoReturn:
    raise SpineValidationError("environment_failure:ownership", "invalid ownership access state or exhausted epoch")


def valid_identifier(value: Any) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 256
            and all(ord(c) >= 32 and ord(c) != 127 and not 0xD800 <= ord(c) <= 0xDFFF for c in value))


def read_access_state(db: sqlite3.Connection) -> dict[str, Any] | None:
    """Read at most two rows; never initialize or repair state."""
    rows = db.execute("SELECT * FROM ledger_access_state LIMIT 2").fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        invalid()
    value = dict(rows[0])
    if (set(value) != {"singleton_id", "ledger_id", "realm_id", "mode", "identity_mode", "access_epoch", "recovery_epoch"}
            or value["singleton_id"] != 1 or not valid_identifier(value["ledger_id"])
            or any(type(value[k]) is not int or not 1 <= value[k] <= MAX_EPOCH for k in ("access_epoch", "recovery_epoch"))):
        invalid()
    if value["mode"] == "trusted_local":
        if (value["realm_id"] is not None or value["identity_mode"] is not None
                or value["ledger_id"] != read_ledger_instance_id(db)):
            invalid()
    elif (value["mode"] != "multi_user" or value["identity_mode"] != "trusted_identity"
          or not valid_identifier(value["realm_id"])):
        invalid()
    return value


def project_access_state(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else {k: str(v) if type(v) is int else v for k, v in value.items()}


def advance_ownership_epoch(db: LedgerConnection) -> int:
    """One advance under the caller's writer transaction, before its owner write."""
    if not db.in_transaction or not db._command_transaction or not db._command_write:
        invalid()
    identity = read_ledger_instance_id(db)
    state = read_access_state(db)
    if db.mutation_state.ownership.epoch_consumed:
        if state is None:
            invalid()
        assert state is not None
        return int(state["access_epoch"])
    if state is None:
        db.execute("INSERT INTO ledger_access_state VALUES(1,?,NULL,'trusted_local',NULL,1,1)", (identity,))
        epoch = 1
    else:
        if state["access_epoch"] == MAX_EPOCH:
            invalid()
        epoch = int(state["access_epoch"]) + 1
        if db.execute("UPDATE ledger_access_state SET access_epoch=? WHERE singleton_id=1 AND access_epoch=?",
                      (epoch, state["access_epoch"])).rowcount != 1:
            invalid()
    db.mutation_state.ownership.epoch_consumed = True
    db.mutation_state.ownership.epoch_before = 0 if state is None else int(state["access_epoch"])
    db.mutation_state.ownership.epoch_after = epoch
    return epoch
