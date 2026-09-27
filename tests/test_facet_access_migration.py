"""Schema-16 grant history preservation and atomic schema-17 activation."""

import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.core.errors import SpineValidationError
from spine.ledger.facet_access_migration import install_facet_access
from spine.ledger.migrate import migrate_schema, verify_schema
from spine.ledger.preflight import current_schema_version, verify_runtime_schema
from tests import test_trusted_web_runtime as helper
from tests.facet_storage_support import DEFINITION, all_rows


class FacetAccessMigrationTests(unittest.TestCase):
    def setUp(self):
        self.h = helper.TrustedWebRuntimeTests()
        with patch("spine.ledger.facet_access_migration.install_facet_access"):
            self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.db = self.h.db
        self.assertEqual(current_schema_version(self.db), 16)
        catalog = self.h.ok(
            handle(
                "item_archetype.create",
                {
                    "contract_version": "spine.item-archetypes.v1",
                    "command_id": "old-catalog",
                    "actor_subject_id": "owner",
                    "action_timestamp_utc": helper.AT,
                    "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                    "archetype_key": "flight",
                    "revision": {"display_name": "Flight", "description": None, "compatible_item_types": ["event"]},
                },
                self.h.ctx,
            )
        )
        self.h.ok(
            handle(
                "facet_schema.create",
                {
                    "contract_version": "spine.facet-schemas.v1",
                    "command_id": "old-schema",
                    "actor_subject_id": "owner",
                    "action_timestamp_utc": helper.AT,
                    "owner": {"owner_kind": "subject", "owner_subject_id": "owner"},
                    "schema_key": "flight",
                    "definition": DEFINITION,
                },
                self.h.ctx,
            )
        )
        self.h.provision(
            grants=[
                {
                    "operation": "create",
                    "resource_kind": "item_archetype",
                    "resource_id": catalog["item_archetype_id"],
                    "resource_owner_revision": "1",
                    "grantee": {"owner_kind": "subject", "owner_subject_id": "other"},
                    "operations": ["catalog.read", "catalog.use"],
                    "starts_at_utc": helper.AT,
                    "ends_at_utc": None,
                }
            ]
        )
        grant = self.db.execute("SELECT grant_id FROM access_grants").fetchone()[0]
        self.h.provision(grants=[{"operation": "revoke", "grant_id": grant, "expected_revision": "1"}])
        self.db.execute("CREATE INDEX custom_grant_owner ON access_grants(resource_owner_revision)")
        self.db.execute("CREATE TRIGGER custom_grant_guard BEFORE DELETE ON access_grants BEGIN SELECT RAISE(ABORT,'keep grants'); END")
        self.db.commit()

    def test_success_keeps_every_old_row_and_runtime_fails_closed_before_migration(self):
        before = all_rows(self.db)
        with self.assertRaises(SpineValidationError):
            verify_runtime_schema(self.db)
        result = migrate_schema(self.db)
        self.assertEqual(result.applied_versions, (17,))
        after = all_rows(self.db)
        for table, rows in before.items():
            if table != "ledger_schema":
                self.assertEqual(rows, after[table], table)
        self.assertEqual(verify_schema(self.db).schema_version, 17)
        self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_schema WHERE name LIKE 'custom_grant_%'").fetchone()[0], 2)

    def test_post_ddl_failure_restores_schema_data_extensions_and_fk_mode(self):
        before = all_rows(self.db)
        objects = [tuple(r) for r in self.db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name")]

        def failure(db, **kw):
            if current_schema_version(db) == 17:
                raise RuntimeError("injected activation failure")
            return verify_runtime_schema(db, **kw)

        with patch("spine.ledger.facet_access_migration.verify_runtime_schema", failure), self.assertRaisesRegex(RuntimeError, "injected"):
            install_facet_access(self.db, applied_at_utc=helper.AT)
        self.assertEqual(all_rows(self.db), before)
        self.assertEqual(objects, [tuple(r) for r in self.db.execute("SELECT type,name,sql FROM sqlite_schema ORDER BY type,name")])
        self.assertEqual(self.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
