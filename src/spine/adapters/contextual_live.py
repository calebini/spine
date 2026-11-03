"""Private format-2 capture storage and an explicitly configured worker launcher."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from spine.adapters.contextual_experiment import CaptureStore, LocalImpetus, dump, require


def compact(value):
    """The owner's insertion-order encoding, deliberately distinct from dump()."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, "nonfinite"))


class LiveCaptureStore(CaptureStore):
    @staticmethod
    def initialize(path, namespace):
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        conn = sqlite3.connect(path)
        try:
            conn.executescript("""PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
                PRAGMA user_version=2;
                CREATE TABLE metadata(namespace TEXT NOT NULL);
                CREATE TABLE exports(opportunity TEXT PRIMARY KEY, work_instance_id TEXT NOT NULL UNIQUE,
                    request BLOB NOT NULL, fingerprint TEXT NOT NULL, binding BLOB NOT NULL,
                    launched INTEGER NOT NULL DEFAULT 0 CHECK(launched IN (0,1)));
                CREATE TABLE captures(id INTEGER PRIMARY KEY, opportunity TEXT NOT NULL,
                    record TEXT NOT NULL, UNIQUE(opportunity,record));
                CREATE TRIGGER exports_immutable BEFORE UPDATE ON exports WHEN
                    NEW.opportunity IS NOT OLD.opportunity OR NEW.work_instance_id IS NOT OLD.work_instance_id OR
                    NEW.request IS NOT OLD.request OR NEW.fingerprint IS NOT OLD.fingerprint OR
                    NEW.binding IS NOT OLD.binding OR NEW.launched < OLD.launched
                    BEGIN SELECT RAISE(ABORT, 'immutable export'); END;
                CREATE TRIGGER exports_no_delete BEFORE DELETE ON exports
                    BEGIN SELECT RAISE(ABORT, 'immutable export'); END;
                CREATE TRIGGER captures_no_update BEFORE UPDATE ON captures
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER captures_no_delete BEFORE DELETE ON captures
                    BEGIN SELECT RAISE(ABORT, 'append only'); END;""")
            with conn:
                conn.execute("INSERT INTO metadata VALUES (?)", (namespace,))
        finally:
            conn.close()

    def __init__(self, path, namespace):
        self.conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=1)
        try:
            self.conn.execute("PRAGMA synchronous=FULL")
            require(self.conn.execute("PRAGMA user_version").fetchone()[0] == 2, "live_capture_format")
            require(self.conn.execute("SELECT namespace FROM metadata").fetchone()[0] == namespace, "capture_namespace")
            self.namespace = namespace
        except BaseException:
            self.conn.close()
            raise

    def get(self, opportunity):
        row = self.conn.execute(
            "SELECT work_instance_id,request,fingerprint,binding,launched FROM exports WHERE opportunity=?", (opportunity,)
        ).fetchone()
        return None if row is None else dict(
            work_instance_id=row[0], request=row[1], fingerprint=row[2], binding=decode(row[3]), launched=bool(row[4])
        )

    def put(self, opportunity, work_id, raw, fingerprint, binding):
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO exports(opportunity,work_instance_id,request,fingerprint,binding) VALUES (?,?,?,?,?)",
                (opportunity, work_id, raw, fingerprint, dump(binding)),
            )
        return self.get(opportunity)


class LiveLauncher:
    """OS-trusted command; credentials and invocation options never enter capture."""

    def __init__(self, command, *, provider_configuration_path=None, enabled=False, environment=None, timeout=35):
        command = tuple(str(arg) for arg in command)
        require(not any(arg.split("=", 1)[0] in ("--enable-live", "--provider-config") for arg in command),
                "base_command_has_live_options")
        self.enabled = enabled
        self.configuration_path = None if provider_configuration_path is None else Path(provider_configuration_path)
        env = dict(os.environ if environment is None else environment)
        read_env = {k: v for k, v in env.items() if k not in {
            "IMPETUS_OPENAI_API_KEY", "IMPETUS_OPENAI_API_KEY_FILE", "OPENAI_API_KEY"
        }}
        self.reader = LocalImpetus(command, environment=read_env, timeout=timeout)
        options = [] if self.configuration_path is None else ["--provider-config", str(self.configuration_path), "--enable-live"]
        self.invoker = LocalImpetus([*command, *options], environment=env, timeout=timeout)

    def prepare(self, binding):
        require(self.enabled is True and self.configuration_path is not None, "live_launcher_not_enabled")
        # Non-secret artifact only. The trusted operator must keep it immutable
        # until worker entry; this comparison is not a lock across processes.
        raw = self.configuration_path.read_bytes()
        require(len(raw) <= 65536, "configuration_size")
        require(compact(decode(raw)).decode() == binding["configuration_encoding"], "launcher_configuration_drift")

    def exchange(self, operation, raw):
        require(operation in ("invoke", "read"), "operation")
        if operation == "invoke":
            require(self.enabled is True, "live_launcher_not_enabled")
            return self.invoker.exchange(operation, raw)
        return self.reader.exchange(operation, raw)
