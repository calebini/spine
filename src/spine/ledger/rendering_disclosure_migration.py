"""Offline, data-preserving schema-21 rendering disclosure upgrade."""

from collections.abc import Callable
from importlib import resources

from spine.core.rendering_definitions import ATTACHED_FIELD_DISCLOSURES, DISCLOSURES
from spine.ledger.preflight import verify_runtime_schema
from spine.ledger.rendering_definitions import invariant, verify_deep
from spine.ledger.rendering_migration import _rebuild, statements
from spine.ledger.transactions import LedgerConnection


def _scope_table(sql: str) -> str:
    return sql.replace(
        f"CHECK(scope_contract_version='{DISCLOSURES}')",
        f"CHECK(scope_contract_version IN ('{DISCLOSURES}','{ATTACHED_FIELD_DISCLOSURES}'))",
    )


def install_attached_field_disclosures(
    db: LedgerConnection, *, applied_at_utc: str, fault: Callable[[str], None] | None = None,
) -> None:
    invariant(isinstance(db, LedgerConnection) and not db.in_transaction, "schema 21 requires an idle ledger")
    verify_runtime_schema(db, expected_version=20)
    invariant(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys must be enabled")
    inject = fault or (lambda stage: None)
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("BEGIN EXCLUSIVE")
        verify_runtime_schema(db, expected_version=20)
        _rebuild(db, "notification_rendering_disclosures", _scope_table)
        if getattr(db, "_renderings_enabled", False):
            db.arm_rendering_disclosure_tracking()
        sql = resources.files("spine.ledger.migrations").joinpath("0021_attached_field_disclosures.sql").read_text()
        for statement in statements(sql):
            db.execute(statement)
        inject("ddl")
        invariant(not db.execute("PRAGMA foreign_key_check").fetchone(), "migration foreign-key check failed")
        invariant(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "migration integrity check failed")
        verify_deep(db)
        db.execute("INSERT INTO ledger_schema VALUES (21,?)", (applied_at_utc,))
        verify_runtime_schema(db, expected_version=21)
        inject("verified")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")
        invariant(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys were not restored")
