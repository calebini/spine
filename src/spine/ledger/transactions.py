"""An outer command transaction that absorbs existing helper context managers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager


class LedgerConnection(sqlite3.Connection):
    """Normal SQLite behavior locally; an explicit service scope owns commit."""

    _command_transaction: bool = False

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._command_transaction:
            return False
        return super().__exit__(exc_type, exc, traceback)

    def commit(self) -> None:
        if self._command_transaction:
            raise RuntimeError("only the outer command transaction may commit")
        super().commit()

    def rollback(self) -> None:
        if self._command_transaction:
            raise RuntimeError("only the outer command transaction may roll back")
        super().rollback()

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        if self._command_transaction:
            raise RuntimeError("scripts are forbidden inside command transactions")
        return super().executescript(sql_script)

    @contextmanager
    def atomic_command(self, *, write: bool = True) -> Iterator[None]:
        if self.in_transaction or self._command_transaction:
            raise RuntimeError("command transaction requires an idle connection")
        self.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        self._command_transaction = True
        try:
            yield
            # A deferred foreign key failure here also rolls the whole command back.
            super().commit()
        except BaseException:
            super().rollback()
            raise
        finally:
            self._command_transaction = False
