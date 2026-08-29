from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine.commands import CommandContext, handle
from spine.commands.cli import main as command_main
from spine.ledger import connect, initialize_schema

ROOT = Path(__file__).parents[1]


class OwnerScopeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = connect()
        initialize_schema(self.connection)
        self.context = CommandContext(ledger=self.connection)
        self._subject("actor", "agent", "Actor", "active", "subject-actor")
        self._subject("caleb", "person", "Caleb", "active", "subject-caleb")
        self._subject("lynn", "person", "Lynn", "inactive", "subject-lynn")
        self._group(
            "family-household",
            "household",
            "Family household",
            "active",
            "group-family",
        )
        self._group(
            "stage-whatsapp-group",
            "transport_group",
            "stage-ops",
            "active",
            "group-stage",
        )
        self._group(
            "work-project",
            "project",
            "Work project",
            "inactive",
            "group-project",
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_default_active_projection_is_ordered_normalized_and_read_only(self) -> None:
        receipts_before = self._count("command_receipts")
        audits_before = self._count("audit_log")
        response = self._list(limit="50")

        self.assertTrue(response["ok"], response)
        self.assertEqual(
            response["response_contract"], "spine.owner-scope-list-response.v1"
        )
        self.assertEqual(
            response["owner_kinds"], ["system", "subject", "subject_group"]
        )
        self.assertEqual(response["statuses"], ["active"])
        self.assertEqual(response["subject_kinds"], ["person", "agent"])
        self.assertEqual(
            response["group_kinds"],
            ["household", "project", "team", "transport_group"],
        )
        self.assertEqual(
            [entry["owner_scope_key"] for entry in response["entries"]],
            [
                "system",
                "subject:actor",
                "subject:caleb",
                "subject_group:family-household",
                "subject_group:stage-whatsapp-group",
            ],
        )
        self.assertEqual(response["source_generation"], "6")
        self.assertFalse(response["has_more"])
        self.assertIsNone(response["next_cursor"])
        self.assertEqual(self._count("command_receipts"), receipts_before)
        self.assertEqual(self._count("audit_log"), audits_before)
        self._validate_response(response)

    def test_filters_are_set_semantic_and_return_inactive_groups_in_id_order(self) -> None:
        response = self._list(
            limit="20",
            owner_kinds=["subject_group"],
            statuses=["inactive", "active"],
            group_kinds=["transport_group", "project"],
        )
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["owner_kinds"], ["subject_group"])
        self.assertEqual(response["statuses"], ["active", "inactive"])
        self.assertEqual(response["subject_kinds"], [])
        self.assertEqual(response["group_kinds"], ["project", "transport_group"])
        self.assertEqual(
            [entry["owner_scope_key"] for entry in response["entries"]],
            [
                "subject_group:stage-whatsapp-group",
                "subject_group:work-project",
            ],
        )

    def test_pagination_accepts_page_size_change_and_covers_each_entry_once(self) -> None:
        first = self._list(limit="2")
        self.assertTrue(first["has_more"])
        self.assertIsInstance(first["next_cursor"], str)
        second = self._list(limit="3", cursor=first["next_cursor"])
        self.assertFalse(second["has_more"])
        self.assertEqual(first["query_hash"], second["query_hash"])
        self.assertEqual(first["source_generation"], second["source_generation"])
        keys = [entry["owner_scope_key"] for entry in first["entries"]]
        keys.extend(entry["owner_scope_key"] for entry in second["entries"])
        self.assertEqual(
            keys,
            [
                "system",
                "subject:actor",
                "subject:caleb",
                "subject_group:family-household",
                "subject_group:stage-whatsapp-group",
            ],
        )

    def test_query_mismatch_and_generation_change_fail_distinctly(self) -> None:
        first = self._list(limit="1")
        mismatched = self._list(
            limit="1", statuses=["inactive"], cursor=first["next_cursor"]
        )
        self.assertFalse(mismatched["ok"])
        self.assertEqual(mismatched["error"]["code"], "invalid_request")
        self.assertEqual(mismatched["error"]["field"], "cursor")

        changed = self._subject(
            "caleb", "person", "Caleb Updated", "active", "subject-caleb-update"
        )
        self.assertTrue(changed["updated"])
        stale = self._list(limit="1", cursor=first["next_cursor"])
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error"]["code"], "stale_cursor")
        self.assertEqual(stale["error"]["field"], "cursor")

    def test_generation_changes_once_for_semantic_changes_not_noop_or_replay(self) -> None:
        self.assertEqual(self._generation(), 6)
        replay = self._subject(
            "actor", "agent", "Actor", "active", "subject-actor"
        )
        self.assertFalse(replay["created"])
        self.assertFalse(replay["updated"])
        self.assertEqual(self._generation(), 6)

        noop = self._subject(
            "actor", "agent", "Actor", "active", "subject-actor-noop"
        )
        self.assertFalse(noop["created"])
        self.assertFalse(noop["updated"])
        self.assertEqual(self._generation(), 6)

        updated = self._group(
            "work-project",
            "team",
            "Work team",
            "active",
            "group-project-update",
        )
        self.assertTrue(updated["updated"])
        self.assertEqual(self._generation(), 7)

    def test_validation_is_closed_and_requires_canonical_decimal_limit(self) -> None:
        unknown = self._list(limit="10", actor_subject_id="actor")
        self.assertEqual(unknown["error"]["code"], "unsupported_field")
        self.assertEqual(unknown["error"]["field"], "actor_subject_id")

        numeric = handle(
            "owner_scope.list",
            {"contract_version": "spine.owner-scope-discovery.v1", "limit": 10},
            self.context,
        )
        self.assertEqual(numeric["error"]["field"], "limit")

        missing_contract = handle(
            "owner_scope.list", {"limit": "10"}, self.context
        )
        self.assertEqual(missing_contract["error"]["code"], "missing_required_field")
        self.assertEqual(missing_contract["error"]["field"], "contract_version")

        scoped = self._list(
            limit="10", owner_kinds=["system"], subject_kinds=["person"]
        )
        self.assertEqual(scoped["error"]["field"], "subject_kinds")

    def test_required_indexes_support_each_bounded_identity_stream(self) -> None:
        subject_plan = self.connection.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT subject_id, subject_kind, display_name, status
            FROM subjects
            WHERE status = ? AND subject_kind = ? AND subject_id > ?
            ORDER BY subject_id LIMIT ?
            """,
            ("active", "person", "", 51),
        ).fetchall()
        group_plan = self.connection.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT group_id, group_kind, display_name, status
            FROM subject_groups
            WHERE status = ? AND group_kind = ? AND group_id > ?
            ORDER BY group_id LIMIT ?
            """,
            ("active", "household", "", 51),
        ).fetchall()
        self.assertIn(
            "subjects_owner_scope_list_idx",
            " ".join(str(row["detail"]) for row in subject_plan),
        )
        self.assertIn(
            "subject_groups_owner_scope_list_idx",
            " ".join(str(row["detail"]) for row in group_plan),
        )

    def test_cli_maps_stale_cursor_to_semantic_conflict_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spine.sqlite"
            connection = connect(path)
            try:
                initialize_schema(connection)
                context = CommandContext(ledger=connection)
                self._subject_on(context, "actor", "agent", "Actor", "subject-actor")
                first = handle(
                    "owner_scope.list",
                    {
                        "contract_version": "spine.owner-scope-discovery.v1",
                        "limit": "1",
                    },
                    context,
                )
                self._subject_on(
                    context, "caleb", "person", "Caleb", "subject-caleb"
                )
            finally:
                connection.close()

            request_path = Path(directory) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "contract_version": "spine.owner-scope-discovery.v1",
                        "limit": "1",
                        "cursor": first["next_cursor"],
                    }
                ),
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                exit_code = command_main(
                    [
                        "--db",
                        str(path),
                        "--input",
                        str(request_path),
                        "owner_scope",
                        "list",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 6)
            self.assertEqual(payload["error"]["code"], "stale_cursor")

    def _list(self, *, limit: object, **facts: object) -> dict[str, object]:
        return handle(
            "owner_scope.list",
            {
                "contract_version": "spine.owner-scope-discovery.v1",
                "limit": limit,
                **facts,
            },
            self.context,
        )

    def _subject(
        self,
        subject_id: str,
        subject_kind: str,
        display_name: str,
        status: str,
        command_id: str,
    ) -> dict[str, object]:
        return self._subject_on(
            self.context,
            subject_id,
            subject_kind,
            display_name,
            command_id,
            status=status,
        )

    @staticmethod
    def _subject_on(
        context: CommandContext,
        subject_id: str,
        subject_kind: str,
        display_name: str,
        command_id: str,
        *,
        status: str = "active",
    ) -> dict[str, object]:
        return handle(
            "subject.upsert",
            {
                "command_id": command_id,
                "actor_subject_id": "actor",
                "subject_id": subject_id,
                "subject_kind": subject_kind,
                "display_name": display_name,
                "status": status,
                "updated_at_utc": "2035-02-01T12:00:00Z",
            },
            context,
        )

    def _group(
        self,
        group_id: str,
        group_kind: str,
        display_name: str,
        status: str,
        command_id: str,
    ) -> dict[str, object]:
        return handle(
            "subject_group.upsert",
            {
                "command_id": command_id,
                "actor_subject_id": "actor",
                "group_id": group_id,
                "group_kind": group_kind,
                "display_name": display_name,
                "status": status,
                "updated_at_utc": "2035-02-01T12:00:01Z",
            },
            self.context,
        )

    def _generation(self) -> int:
        return int(
            self.connection.execute(
                "SELECT owner_scope_generation FROM owner_scope_catalog_state"
            ).fetchone()[0]
        )

    def _count(self, table: str) -> int:
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _validate_response(value: object) -> None:
        schema_dir = ROOT / "contracts/schemas"
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in schema_dir.glob("*.schema.json")
        }
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas.values()
        )
        Draft202012Validator(
            schemas["owner-scope-list-response.schema.json"], registry=registry
        ).validate(value)


if __name__ == "__main__":
    unittest.main()
