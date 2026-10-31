"""Spine-owned synthetic export/store and trusted local Impetus process adapter."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

from spine.core import facets as facet_codec
from spine.ledger.facets import load_definition, load_snapshot
from spine.ledger.identity import read_ledger_instance_id
from spine.ledger.items import get_current_item
from spine.ledger.notification_profiles import current_assignment
from spine.ledger.recurrence import load_current_recurrence_set
from spine.ledger.work import assert_work_instance_not_stale, get_work_instance
from spine.services.notification_rendering import resolve_notification_rendering


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(dump(value)).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


class Source:
    def __init__(self, ledger):
        self.ledger = ledger
        self.namespace = read_ledger_instance_id(ledger)

    def snapshot(self, work_id, config):
        db = self.ledger
        with db.atomic_command(write=False):
            work = dict(get_work_instance(db, work_id))
            require(work["item_id"] in config["opted_in_item_ids"] and config["synthetic_only"] is True, "experiment_not_opted_in")
            require(work["work_kind"] == "notification_reminder" and work["status"] == "eligible", "work_not_eligible")
            assert_work_instance_not_stale(db, work_id)
            item = get_current_item(db, work["item_id"])
            require(item["item_type"] == "event" and item["status"] == "active", "unsupported_item")
            require(load_current_recurrence_set(db, item_id=work["item_id"]) is None, "recurrence_unsupported")
            require(work["occurrence_provenance_id"] is None, "recurrence_unsupported")
            assignment = current_assignment(db, item_id=work["item_id"], item_version=item["current_version"])
            require(assignment is not None, "archetype_required")
            # Use the exact ordinary rendering at nominal notification time. This is
            # a preview identifier, never persisted as an attempt or delivery fact.
            rendering = resolve_notification_rendering(
                db, work_row=work, attempt_id="experiment-preview:" + work_id, attempted_at_utc=work["eligible_at_utc"], use_stored=False
            )
            require(config["permit_ordinary_text"] is True, "ordinary_text_disclosure_required")
            facets = []
            for entry in load_snapshot(db, work["item_id"], item["current_version"]):
                definition = load_definition(db, entry["facet_schema_revision_id"])
                values = facet_codec.decode_values(definition, entry["values_json"], contract=entry["value_contract_version"])
                selected = {}
                for field in config["facet_fields"].get(entry["facet_key"], []):
                    if field in values:
                        declared = next((f for f in definition["fields"] if f["key"] == field), None)
                        require(declared is not None and declared["type"] != "reference", "reference_disclosure_unsupported")
                        require(type(values[field]) in (str, bool, int), "unsupported_facet_projection")
                        selected[field] = values[field]
                if selected:
                    facets.append({"schema_revision": entry["facet_schema_revision_id"], "values": selected})
            # Do not export recipient, route, notes, summary, unrelated facets or full location.
            context = {
                "archetype": assignment["archetype"]["archetype_key"],
                "event": {
                    "title": item["version"]["title"],
                    "starts_at_utc": work["target_at_utc"],
                    "timezone": rendering.source_input["display_timezone"],
                },
                "facets": facets,
                "notification": {"eligible_at_utc": work["eligible_at_utc"], "ordinary_text": rendering.body_text},
            }
            return {
                "work_instance_id": work_id,
                "item_id": item["item_id"],
                "item_version": item["current_version"],
                "opportunity": work["notification_opportunity_id"],
                "policy": work["notification_policy_id"],
                "context": context,
                "rendering_contract": rendering.rendering_contract
                if hasattr(rendering, "rendering_contract")
                else "spine.notification-rendering.v1",
                "rendering_hash": rendering.rendered_content_hash,
                "archetype_revision": assignment["item_archetype_revision_id"],
                "config_hash": digest(config),
            }


class CaptureStore:
    @staticmethod
    def initialize(path, namespace):
        path = Path(path)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        conn = sqlite3.connect(path)
        try:
            conn.executescript("""PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
                PRAGMA user_version=1;
                CREATE TABLE metadata(namespace TEXT NOT NULL);
                CREATE TABLE exports(opportunity TEXT PRIMARY KEY, work_instance_id TEXT NOT NULL,
                    request BLOB NOT NULL, fingerprint TEXT NOT NULL, launched INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE captures(id INTEGER PRIMARY KEY, opportunity TEXT NOT NULL,
                    record TEXT NOT NULL, UNIQUE(opportunity,record));""")
            with conn:
                conn.execute("INSERT INTO metadata VALUES (?)", (namespace,))
        finally:
            conn.close()

    def __init__(self, path, namespace):
        self.conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=1)
        try:
            self.conn.execute("PRAGMA synchronous=FULL")
            require(self.conn.execute("PRAGMA user_version").fetchone()[0] == 1, "capture_format")
            require(self.conn.execute("SELECT namespace FROM metadata").fetchone()[0] == namespace, "capture_namespace")
        except BaseException:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def get(self, opportunity):
        row = self.conn.execute(
            "SELECT work_instance_id,request,fingerprint,launched FROM exports WHERE opportunity=?", (opportunity,)
        ).fetchone()
        return None if row is None else dict(work_instance_id=row[0], request=row[1], fingerprint=row[2], launched=bool(row[3]))

    def for_work(self, work_id):
        row = self.conn.execute("SELECT opportunity FROM exports WHERE work_instance_id=?", (work_id,)).fetchone()
        return None if row is None else (row[0], self.get(row[0]))

    def put(self, opportunity, work_id, raw, fingerprint):
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO exports(opportunity,work_instance_id,request,fingerprint) VALUES (?,?,?,?)",
                (opportunity, work_id, raw, fingerprint),
            )
        return self.get(opportunity)

    def mark_launched(self, opportunity):
        with self.conn:
            return self.conn.execute("UPDATE exports SET launched=1 WHERE opportunity=? AND launched=0", (opportunity,)).rowcount == 1

    def capture(self, opportunity, record):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO captures(opportunity,record) VALUES (?,?)", (opportunity, dump(record).decode()))

    def history(self, opportunity):
        return [json.loads(r[0]) for r in self.conn.execute("SELECT record FROM captures WHERE opportunity=? ORDER BY id", (opportunity,))]


class LocalImpetus:
    """Trusted executable/environment supplied by operator, never by event data."""

    def __init__(self, command, *, environment=None, timeout=35):
        self.command = tuple(command)
        self.environment = environment
        self.timeout = timeout

    def exchange(self, operation, raw):
        require(operation in ("invoke", "read"), "operation")
        try:
            proc = subprocess.run(
                [*self.command, operation],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                env=self.environment,
            )
            if len(proc.stdout) > 1048576:
                return None

            def pairs(items):
                value = {}
                for k, v in items:
                    require(k not in value, "duplicate_response_key")
                    value[k] = v
                return value

            return json.loads(
                proc.stdout.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
            )
        except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError, RecursionError):
            return None
