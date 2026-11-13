"""Exact item-owner/header history writes; no grants or epoch policy selection."""

import sqlite3
from dataclasses import astuple, replace

from spine.core.errors import SpineValidationError
from spine.core.mutation_effects import OwnerHistory, OwnerMutation, OwnerSnapshot
from spine.ledger.mutation_effects import require_transaction


def insert_item_owner(db: sqlite3.Connection, owner: OwnerSnapshot) -> None:
    connection = require_transaction(db)
    if owner.revision != 1:
        raise SpineValidationError("environment_failure:propagation", "owner creation requires initial revision")
    db.execute("INSERT INTO item_access_owners VALUES(?,?,?,?,?,?,?,?)", astuple(owner))
    connection.mutation_state.propagation.owners[owner.owner_id] = OwnerMutation(owner)


def record_item_owner_history(db: sqlite3.Connection, identity: str, actor: str, at: str, receipt: str) -> None:
    pending = require_transaction(db).mutation_state.propagation.owners
    effect = pending.get(identity)
    if effect is None or effect.history is not None:
        raise SpineValidationError("environment_failure:propagation", "missing or duplicate owner history mutation")
    db.execute("INSERT INTO item_access_owner_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (*astuple(effect.after), at, actor, receipt))
    pending[identity] = replace(effect, history=OwnerHistory(actor, at, receipt))


def verify_item_owner(db: sqlite3.Connection, effect: OwnerMutation) -> None:
    # Bounded exact header/history equality; neither catalog scans nor discovery.
    row = db.execute(
        "SELECT o.*,h.* "
        "FROM item_access_owners o JOIN item_access_owner_revisions h "
        "ON h.item_access_owner_id=o.item_access_owner_id AND h.revision=o.current_revision "
        "WHERE o.item_access_owner_id=?",
        (effect.after.owner_id,),
    ).fetchone()
    history = effect.history
    if history is None or row is None or tuple(row) != (
        *astuple(effect.after), *astuple(effect.after), history.at, history.actor, history.receipt_id,
    ):
        raise SpineValidationError("environment_failure:propagation", "owner header/history consequence incomplete")


def access_epoch(db: sqlite3.Connection) -> int | None:
    row = db.execute("SELECT access_epoch FROM ledger_access_state WHERE singleton_id=1").fetchone()
    return None if row is None else int(row[0])


def advance_configured_epoch(db: sqlite3.Connection, expected: int) -> None:
    # Protected admission owns configured-state validation. Never bootstrap here.
    if db.execute("UPDATE ledger_access_state SET access_epoch=access_epoch+1 "
                  "WHERE singleton_id=1 AND mode='multi_user' AND access_epoch=?", (expected,)).rowcount != 1:
        raise SpineValidationError("environment_failure:propagation", "configured owner epoch differs")
