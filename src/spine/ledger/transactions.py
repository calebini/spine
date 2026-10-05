"""An outer command transaction that absorbs existing helper context managers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import Literal

from spine.core.errors import SpineValidationError

REGISTERED_VERSION_PRODUCERS = frozenset({"item_create", "item_version_from_draft"})


class LedgerConnection(sqlite3.Connection):
    """Normal SQLite behavior locally; an explicit service scope owns commit."""

    _command_transaction: bool = False

    def enable_renderings(self) -> None:
        """Candidate storage tracking, armed only when explicitly installed."""
        if getattr(self, "_renderings_enabled", False):
            return
        self.enable_facets()
        self._renderings_enabled = True
        self._rendering_pending: dict[str, dict] = {}
        self._rendering_versions: set[tuple[str, int]] = set()
        self._rendering_catalog: set[tuple[str, str]] = set()
        self._rendering_profiles: set[str] = set()
        self.create_function("spine_touch_policy", 2, self._touch_policy)
        self.create_function("spine_touch_rendering", 2, self._touch_rendering)
        self.create_function("spine_touch_rendering_profile", 1, lambda identity: self._rendering_profiles.add(identity) or 0)
        self.execute("""CREATE TEMP TRIGGER spine_rendering_profile_insert AFTER INSERT ON main.notification_profile_revisions
            BEGIN SELECT spine_touch_rendering_profile(NEW.notification_profile_revision_id); END""")
        self.execute("""CREATE TEMP TRIGGER spine_rendering_profile_marker AFTER INSERT ON main.notification_profile_rendering_revisions
            BEGIN SELECT spine_touch_rendering_profile(NEW.notification_profile_revision_id); END""")
        self.execute("""CREATE TEMP TRIGGER spine_rendering_profile_template AFTER INSERT ON main.notification_profile_template_renderings
            BEGIN SELECT spine_touch_rendering_profile(notification_profile_revision_id)
              FROM notification_profile_templates WHERE notification_profile_template_id=NEW.notification_profile_template_id; END""")
        for operation in ("INSERT", "UPDATE", "DELETE"):
            record = "OLD" if operation == "DELETE" else "NEW"
            self.execute(f"""CREATE TEMP TRIGGER spine_rendering_policy_{operation} AFTER {operation} ON main.notification_policies
                BEGIN SELECT spine_touch_policy({record}.item_id,{record}.version); END""")
        for table, kind, column, operations in (
            ("notification_rendering_definitions", "root", "notification_rendering_definition_id", ("INSERT", "UPDATE")),
            ("notification_rendering_definition_revisions", "revision", "notification_rendering_definition_revision_id", ("INSERT",)),
            ("notification_rendering_disclosures", "disclosure", "disclosure_authorization_id", ("INSERT", "UPDATE")),
        ):
            for operation in operations:
                self.execute(f"""CREATE TEMP TRIGGER spine_rendering_{table}_{operation} AFTER {operation} ON main.{table}
                    BEGIN SELECT spine_touch_rendering('{kind}',NEW.{column}); END""")

    def _touch_policy(self, item_id: str, version: int) -> int:
        self._rendering_versions.add((item_id, version))
        return 0

    def _touch_rendering(self, kind: str, identity: str) -> int:
        self._rendering_catalog.add((kind, identity))
        return 0

    def enable_facets(self) -> None:
        """Install connection-local write tracking; no persistent runtime tables."""
        if getattr(self, "_facets_enabled", False):
            return
        self._facets_enabled = True
        self._facet_versions: set[tuple[str, int]] = set()
        self._facet_allocations: set[tuple[str, int]] = set()
        self._facet_roots: set[str] = set()
        self._facet_items: set[str] = set()
        self._facet_bindings: set[str] = set()
        self._facet_definitions: set[str] = set()
        self._facet_producer: str | None = None
        self._allow_commit = False
        self.create_function("spine_track_version", 2, self._track_version)
        self.create_function("spine_track_facet", 2, self._track_facet)
        self.create_function("spine_touch_snapshot", 2, self._touch_snapshot)
        self.execute("""CREATE TEMP TRIGGER spine_track_version_insert AFTER INSERT ON main.coordination_item_versions
                        BEGIN SELECT spine_track_version(NEW.item_id, NEW.version); END""")
        for table, kind, column in (
            ("facet_schemas", "root", "facet_schema_id"),
            ("facet_schema_revisions", "root", "facet_schema_id"),
            ("archetype_facet_bindings", "binding", "facet_binding_id"),
            ("item_facet_current_values", "item", "item_id"),
            ("item_archetype_assignments", "item", "item_id"),
        ):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                record = "OLD" if operation == "DELETE" else "NEW"
                self.execute(f"""CREATE TEMP TRIGGER spine_track_{table}_{operation} AFTER {operation} ON main.{table}
                    BEGIN SELECT spine_track_facet('{kind}', {record}.{column}); END""")
        self.set_authorizer(self._authorize_commit)
        for table in ("item_facet_snapshots", "item_facet_entries", "item_facet_references"):
            self.execute(f"""CREATE TEMP TRIGGER spine_touch_{table} AFTER INSERT ON main.{table}
                BEGIN SELECT spine_touch_snapshot(NEW.item_id,NEW.item_version); END""")
        self.execute("""CREATE TEMP TRIGGER spine_touch_fields AFTER INSERT ON main.facet_schema_fields
            BEGIN SELECT spine_track_facet('definition',NEW.facet_schema_revision_id);
            SELECT spine_track_facet('root',facet_schema_id) FROM facet_schema_revisions
            WHERE facet_schema_revision_id=NEW.facet_schema_revision_id; END""")
        self.execute("""CREATE TEMP TRIGGER spine_touch_shell AFTER UPDATE OF current_version ON main.coordination_items
            BEGIN SELECT spine_track_facet('item',NEW.item_id); END""")

    def _authorize_commit(self, action: int, first: str | None, second: str | None, database: str | None, trigger: str | None) -> int:
        if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT" and not self._allow_commit:
            return sqlite3.SQLITE_DENY
        # Releasing an outermost savepoint is an implicit commit. Savepoints are
        # therefore allowed only inside the transaction whose finalizer owns commit.
        if action == sqlite3.SQLITE_SAVEPOINT and not self._command_transaction:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _track_version(self, item_id: str, version: int) -> int:
        if self._facet_producer is None:
            raise SpineValidationError("environment_failure:facets", "unregistered item version allocation")
        self._facet_versions.add((item_id, version))
        self._facet_allocations.add((item_id, version))
        self._facet_items.add(item_id)
        return 0

    def _touch_snapshot(self, item_id: str, version: int) -> int:
        self._facet_versions.add((item_id, version))
        self._facet_items.add(item_id)
        return 0

    def _track_facet(self, kind: str, identity: str) -> int:
        {"root": self._facet_roots, "item": self._facet_items, "binding": self._facet_bindings, "definition": self._facet_definitions}[
            kind
        ].add(identity)
        return 0

    @contextmanager
    def version_allocation(self, producer: str) -> Iterator[None]:
        if producer not in REGISTERED_VERSION_PRODUCERS or self._facet_producer is not None:
            raise SpineValidationError("environment_failure:facets", "unregistered or nested item version allocation")
        self._facet_producer = producer
        try:
            yield
        finally:
            self._facet_producer = None

    def _clear_facets(self) -> None:
        if getattr(self, "_renderings_enabled", False):
            self._rendering_pending.clear()
            self._rendering_versions.clear()
            self._rendering_catalog.clear()
            self._rendering_profiles.clear()
        if getattr(self, "_facets_enabled", False):
            self._facet_versions.clear()
            self._facet_allocations.clear()
            self._facet_roots.clear()
            self._facet_items.clear()
            self._facet_bindings.clear()
            self._facet_definitions.clear()

    def _commit_checked(self) -> None:
        try:
            if getattr(self, "_renderings_enabled", False):
                from spine.ledger.rendering_definitions import finalize as finalize_renderings

                finalize_renderings(self)
            if getattr(self, "_facets_enabled", False):
                from spine.ledger.facets import finalize

                if not self._facet_allocations <= self._facet_versions:
                    raise SpineValidationError("environment_failure:facets", "unfinalized item version")
                expected = (
                    frozenset(self._facet_versions),
                    frozenset(self._facet_items),
                    frozenset(self._facet_roots),
                    frozenset(self._facet_bindings),
                    frozenset(self._facet_definitions),
                )
                proof = finalize(self, *expected)
                if proof != expected:
                    raise SpineValidationError("environment_failure:facets", "facet finalization incomplete")
                self._allow_commit = True
                self.set_authorizer(self._authorize_commit)
            super().commit()
        except BaseException:
            super().rollback()
            raise
        finally:
            if getattr(self, "_facets_enabled", False):
                self._allow_commit = False
                self.set_authorizer(self._authorize_commit)
                self._clear_facets()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if self._command_transaction:
            return False
        if getattr(self, "_facets_enabled", False):
            if exc_type is not None:
                self.rollback()
            else:
                self._commit_checked()
            return False
        return super().__exit__(exc_type, exc, traceback)

    def commit(self) -> None:
        if self._command_transaction:
            raise RuntimeError("only the outer command transaction may commit")
        self._commit_checked()

    def rollback(self) -> None:
        if self._command_transaction:
            raise RuntimeError("only the outer command transaction may roll back")
        super().rollback()
        self._clear_facets()

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        if self._command_transaction or (getattr(self, "_facets_enabled", False) and self.in_transaction):
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
            self._commit_checked()
        except BaseException:
            super().rollback()
            self._clear_facets()
            raise
        finally:
            self._command_transaction = False
