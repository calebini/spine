"""Explicit real-source disclosure and a continuous, profile-marked capture store."""

import sqlite3
from contextlib import closing, nullcontext
from datetime import datetime
from pathlib import Path

from spine.adapters.contextual_experiment import Source, digest, dump, require
from spine.adapters.contextual_live import LiveCaptureStore, decode
from spine.ledger.transactions import LedgerConnection

CONTRACT = "spine.notification-enrichment.v1"


def open_source(path):
    """Open only an existing ledger; no journal change, seed or migration."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, factory=LedgerConnection, timeout=1)
    try:
        db.row_factory = sqlite3.Row
        require(db.execute("SELECT max(schema_version) FROM ledger_schema").fetchone()[0] == 19, "enrichment_schema")
        db.enable_renderings()
        db.execute("PRAGMA query_only=ON")
        return EnrichmentSource(db)
    except BaseException:
        db.close()
        raise


class EnrichmentSource(Source):
    def preview(self, work_id, config):
        require(config["synthetic_only"] is False and work_id == config["work_instance_id"], "enrichment_not_enrolled")
        require(config["permit_ordinary_text"] is True, "ordinary_text_disclosure_required")
        db = self.ledger
        with nullcontext() if db.in_transaction else db.atomic_command(write=False):
            owner = db.execute("""SELECT o.owner_subject_id FROM work_instances w
                JOIN item_access_owners o ON o.item_id=w.item_id
                JOIN subjects s ON s.subject_id=o.owner_subject_id
                JOIN coordination_items i ON i.item_id=w.item_id
                JOIN event_details e ON e.item_id=i.item_id AND e.version=i.current_version
                WHERE w.work_instance_id=? AND o.owner_kind='subject' AND s.status='active' AND e.all_day=0""", (work_id,)).fetchone()
            require(owner is not None and owner[0] == config["actor_subject_id"], "enrichment_owner")
            snapshot = self._snapshot(work_id, config, transactional=False, allow_in_progress=True)
            context = snapshot["context"]
            seconds = (datetime.fromisoformat(context["event"]["starts_at_utc"]) -
                       datetime.fromisoformat(context["notification"]["eligible_at_utc"])).total_seconds()
            require(seconds.is_integer(), "relative_time")
            context["notification"]["seconds_before_event"] = int(seconds)
            return snapshot

    def snapshot(self, work_id, config):
        snapshot = self.preview(work_id, config)
        require(digest(snapshot["context"]) == config["approved_context_sha256"], "enrichment_disclosure_drift")
        return snapshot


class EnrichmentStore(LiveCaptureStore):
    @staticmethod
    def initialize(path, namespace):
        LiveCaptureStore.initialize(path, namespace)
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE enrichment_profile(contract TEXT PRIMARY KEY);
                CREATE TABLE enrichment_choices(work_id TEXT PRIMARY KEY, record BLOB NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)));
                CREATE TABLE enrichment_receipts(attempt_id TEXT PRIMARY KEY, envelope BLOB NOT NULL,
                    payload_hash TEXT NOT NULL);
                CREATE TRIGGER choices_immutable BEFORE UPDATE ON enrichment_choices WHEN
                    NEW.work_id IS NOT OLD.work_id OR NEW.record IS NOT OLD.record OR NEW.disabled < OLD.disabled
                    BEGIN SELECT RAISE(ABORT,'immutable choice'); END;
                CREATE TRIGGER choices_no_delete BEFORE DELETE ON enrichment_choices
                    BEGIN SELECT RAISE(ABORT,'immutable choice'); END;
                CREATE TRIGGER receipts_no_update BEFORE UPDATE ON enrichment_receipts
                    BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
                CREATE TRIGGER receipts_no_delete BEFORE DELETE ON enrichment_receipts
                    BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
                CREATE TRIGGER profile_no_update BEFORE UPDATE ON enrichment_profile
                    BEGIN SELECT RAISE(ABORT,'immutable profile'); END;
                CREATE TRIGGER profile_no_delete BEFORE DELETE ON enrichment_profile
                    BEGIN SELECT RAISE(ABORT,'immutable profile'); END;
            """)
            db.execute("INSERT INTO enrichment_profile VALUES (?)", (CONTRACT,))
            db.commit()

    def __init__(self, path, namespace):
        super().__init__(path, namespace)
        try:
            require(self.conn.execute("SELECT contract FROM enrichment_profile").fetchall() == [(CONTRACT,)], "enrichment_profile")
            self.conn.execute("PRAGMA busy_timeout=100")
        except BaseException:
            self.close()
            raise

    def choice(self, work):
        row = self.conn.execute("SELECT record,disabled FROM enrichment_choices WHERE work_id=?", (work,)).fetchone()
        return None if row is None else (decode(row[0]), bool(row[1]))

    def choose(self, work, record):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO enrichment_choices(work_id,record) VALUES (?,?)", (work, dump(record)))
        return self.choice(work)

    def disable(self, work):
        with self.conn:
            self.conn.execute("UPDATE enrichment_choices SET disabled=1 WHERE work_id=?", (work,))

    def receipt(self, attempt):
        row = self.conn.execute("SELECT envelope,payload_hash FROM enrichment_receipts WHERE attempt_id=?", (attempt,)).fetchone()
        return None if row is None else (decode(row[0]), row[1])

    def prepare_receipt(self, attempt, envelope, payload_hash):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO enrichment_receipts VALUES (?,?,?)", (attempt, dump(envelope), payload_hash))
        require(self.receipt(attempt) == (envelope, payload_hash), "enrichment_receipt_conflict")
