"""Private capture-only storage; ordinary delivery cannot open this profile."""

import sqlite3
from contextlib import closing

from spine.adapters.contextual_experiment import require
from spine.adapters.contextual_live import LiveCaptureStore

PROFILE_ID = 0x53505031


class PilotStore(LiveCaptureStore):
    @staticmethod
    def initialize(path, namespace):
        LiveCaptureStore.initialize(path, namespace)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(f"PRAGMA application_id={PROFILE_ID}")
            db.execute("""CREATE TABLE pilot_approval(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                preview_sha256 TEXT NOT NULL, owner_approval_ref TEXT NOT NULL, approved_at_utc TEXT NOT NULL)""")

    def __init__(self, path, namespace):
        super().__init__(path, namespace)
        try:
            require(self.conn.execute("PRAGMA application_id").fetchone()[0] == PROFILE_ID, "pilot_profile")
        except BaseException:
            self.close()
            raise

    def approve_and_mark(self, opportunity, preview_sha256, owner_approval_ref, approved_at):
        """Consume the sole launch before subprocess entry; concurrent calls cannot reopen it."""
        with self.conn:
            changed = self.conn.execute("UPDATE exports SET launched=1 WHERE opportunity=? AND launched=0", (opportunity,))
            if not changed.rowcount:
                return False
            self.conn.execute("INSERT INTO pilot_approval VALUES (1,?,?,?)", (preview_sha256, owner_approval_ref, approved_at))
        return True

    def approval_digest(self):
        row = self.conn.execute("SELECT preview_sha256 FROM pilot_approval WHERE singleton=1").fetchone()
        return row[0] if row else None
