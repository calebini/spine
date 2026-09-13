"""Connection contexts preserve SQLite commit, rollback, and exception behavior."""

from __future__ import annotations

import sqlite3
import unittest

from spine.ledger.transactions import LedgerConnection


class LedgerTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:", factory=LedgerConnection)
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE values_for_test (value INTEGER)")

    def test_connection_context_commits_on_success(self) -> None:
        with self.db:
            self.db.execute("INSERT INTO values_for_test VALUES (1)")
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute("SELECT value FROM values_for_test").fetchall(), [(1,)])

    def test_connection_context_rolls_back_without_suppressing_exceptions(self) -> None:
        for error in (RuntimeError("failed"), KeyboardInterrupt("cancelled")):
            with self.subTest(error=type(error)), self.assertRaises(type(error)) as caught, self.db:
                self.db.execute("INSERT INTO values_for_test VALUES (1)")
                raise error
            self.assertIs(caught.exception, error)
            self.assertFalse(self.db.in_transaction)
            self.assertEqual(self.db.execute("SELECT value FROM values_for_test").fetchall(), [])

    def test_inner_connection_context_leaves_commit_to_atomic_command(self) -> None:
        with self.db.atomic_command():
            with self.db:
                self.db.execute("INSERT INTO values_for_test VALUES (1)")
            self.assertTrue(self.db.in_transaction)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute("SELECT value FROM values_for_test").fetchall(), [(1,)])

    def test_atomic_command_rolls_back_inner_context_without_suppressing_exceptions(self) -> None:
        for error in (RuntimeError("failed"), KeyboardInterrupt("cancelled")):
            with self.subTest(error=type(error)), self.assertRaises(type(error)) as caught, self.db.atomic_command():
                with self.db:
                    self.db.execute("INSERT INTO values_for_test VALUES (1)")
                raise error
            self.assertIs(caught.exception, error)
            self.assertFalse(self.db.in_transaction)
            self.assertEqual(self.db.execute("SELECT value FROM values_for_test").fetchall(), [])
        # The outer scope releases ownership even after an exceptional exit.
        with self.db:
            self.db.execute("INSERT INTO values_for_test VALUES (2)")
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute("SELECT value FROM values_for_test").fetchall(), [(2,)])


if __name__ == "__main__":
    unittest.main()
