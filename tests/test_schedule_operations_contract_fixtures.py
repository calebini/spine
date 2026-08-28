from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST_PATH = ROOT / "contracts" / "schedule-operations-fixture-manifest.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "schedule_operations" / "contracts"


class ScheduleOperationsContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )

    def test_manifest_is_complete_and_all_structural_fixtures_validate(self) -> None:
        manifest = _load(MANIFEST_PATH)
        self.assertEqual(manifest["schema_version"], "spine.schedule-operations-contract-fixtures.v1")
        self.assertEqual(manifest["fixture_scope"], "structural_examples")

        fixture_ids: list[str] = []
        fixture_paths: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            fixture_paths.append(entry["fixture"])
            schema = _load(ROOT / entry["schema"])
            fixture = _load(ROOT / entry["fixture"])
            Draft202012Validator(schema, registry=self.registry).validate(fixture)
            if "work_reconciliation" in fixture:
                self.assertTrue(_work_reconciliation_arrays_are_disjoint(fixture))

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in FIXTURE_DIR.glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_update_schema_rejects_partial_intent_identity_and_hidden_fields(self) -> None:
        schema = self.schemas["schedule-update-request.schema.json"]
        request = _load(FIXTURE_DIR / "request_update_recurring_event.json")

        partial_identity = copy.deepcopy(request)
        del partial_identity["patch"]["notification_plan"]["custom_additions"][0][
            "notification_policy_id"
        ]
        self.assertFalse(_valid(schema, partial_identity, self.registry))

        hidden_route = copy.deepcopy(request)
        hidden_route["patch"]["delivery"]["target"]["target_ref"] = "not-canonical"
        self.assertFalse(_valid(schema, hidden_route, self.registry))

        cross_type = copy.deepcopy(request)
        cross_type["patch"]["item"]["event_detail"] = {"visibility": "private"}
        cross_type["patch"]["item"]["task_detail"] = {"priority": "high"}
        self.assertFalse(_valid(schema, cross_type, self.registry))

    def test_agenda_and_cancel_schemas_are_closed(self) -> None:
        agenda_schema = self.schemas["schedule-agenda-request.schema.json"]
        agenda = _load(FIXTURE_DIR / "request_agenda_local_day.json")
        agenda["raw_sql"] = "SELECT *"
        self.assertFalse(_valid(agenda_schema, agenda, self.registry))

        cancel_schema = self.schemas["schedule-cancel-request.schema.json"]
        cancel = _load(FIXTURE_DIR / "request_cancel_event.json")
        cancel["deliver"] = True
        self.assertFalse(_valid(cancel_schema, cancel, self.registry))

    def test_agenda_response_cursor_and_diagnostic_shapes_are_deterministic(self) -> None:
        schema = self.schemas["schedule-agenda-response.schema.json"]
        response = _load(FIXTURE_DIR / "response_agenda_local_day.json")
        self.assertTrue(_valid(schema, response, self.registry))

        missing_terminal_cursor = copy.deepcopy(response)
        del missing_terminal_cursor["next_cursor"]
        self.assertFalse(_valid(schema, missing_terminal_cursor, self.registry))

        continued_page = copy.deepcopy(response)
        continued_page["has_more"] = True
        self.assertFalse(_valid(schema, continued_page, self.registry))
        continued_page["next_cursor"] = "opaque.cursor"
        self.assertTrue(_valid(schema, continued_page, self.registry))

        missing_field = copy.deepcopy(response)
        missing_field["diagnostics"] = [
            {"diagnostic_code": "agenda_item_unscheduled", "item_id": "item_unscheduled"}
        ]
        self.assertFalse(_valid(schema, missing_field, self.registry))

        wrong_field = copy.deepcopy(response)
        wrong_field["diagnostics"] = [
            {
                "diagnostic_code": "agenda_item_unscheduled",
                "item_id": "item_unscheduled",
                "field": "recurrence",
            }
        ]
        self.assertFalse(_valid(schema, wrong_field, self.registry))

        valid_diagnostic = copy.deepcopy(response)
        valid_diagnostic["diagnostics"] = [
            {
                "diagnostic_code": "agenda_item_unscheduled",
                "item_id": "item_unscheduled",
                "field": "primary_schedule",
            }
        ]
        self.assertTrue(_valid(schema, valid_diagnostic, self.registry))

    def test_work_reconciliation_arrays_are_semantically_disjoint(self) -> None:
        schema = self.schemas["schedule-update-response.schema.json"]
        response = _load(
            FIXTURE_DIR / "response_update_title_with_work_classifications.json"
        )
        reconciliation = response["work_reconciliation"]

        self.assertTrue(_valid(schema, response, self.registry))
        self.assertTrue(_work_reconciliation_arrays_are_disjoint(response))
        self.assertTrue(reconciliation["retained_work_instance_ids"])
        self.assertTrue(reconciliation["protected_stale_work_instance_ids"])

        overlapping = copy.deepcopy(response)
        duplicate_id = overlapping["work_reconciliation"]["retained_work_instance_ids"][0]
        overlapping["work_reconciliation"]["protected_stale_work_instance_ids"].append(
            duplicate_id
        )

        # Draft 2020-12 cannot compare values across sibling arrays, so the
        # structural schema accepts this and the explicit semantic oracle rejects it.
        self.assertTrue(_valid(schema, overlapping, self.registry))
        self.assertFalse(_work_reconciliation_arrays_are_disjoint(overlapping))

    def test_semantic_failure_scenarios_pin_error_fields_and_validation_order(self) -> None:
        manifest = _load(MANIFEST_PATH)
        failure_schema = self.schemas["schedule-operation-failure-response.schema.json"]
        scenario_entries = [
            entry
            for entry in manifest["fixtures"]
            if entry["kind"] == "semantic_failure_scenario"
        ]

        self.assertEqual(len(scenario_entries), 12)
        for entry in scenario_entries:
            with self.subTest(fixture_id=entry["fixture_id"]):
                scenario = _load(ROOT / entry["fixture"])
                expected_response = scenario["expected_response"]
                expected_error = expected_response["error"]

                self.assertTrue(_valid(failure_schema, expected_response, self.registry))
                self.assertEqual(scenario["command"], expected_response["command"])
                self.assertEqual(
                    _request_command(scenario["request"]),
                    scenario["command"],
                )
                self.assertEqual(
                    _schedule_operation_semantic_error(scenario),
                    {
                        "phase": scenario["expected_validation_phase"],
                        "code": expected_error["code"],
                        "field": expected_error.get("field"),
                    },
                )
                self.assertEqual(scenario["mutation"], "none")
                self.assertFalse(scenario["command_receipt_written"])

    def test_end_anchored_event_remains_eligible_for_non_time_patch(self) -> None:
        scenario = _load(
            FIXTURE_DIR / "failure_update_end_anchored_scheduled_time.json"
        )
        scenario["request"]["patch"] = {"item": {"title": "Allowed title update"}}

        self.assertIsNone(_schedule_operation_semantic_error(scenario))

    def test_wrong_item_type_precedes_stale_version_for_schedule_writes(self) -> None:
        for fixture_name in (
            "failure_update_wrong_item_type.json",
            "failure_cancel_wrong_item_type.json",
        ):
            with self.subTest(fixture=fixture_name):
                scenario = _load(FIXTURE_DIR / fixture_name)
                scenario["request"]["target_version"] = "99"

                self.assertEqual(
                    _schedule_operation_semantic_error(scenario),
                    _semantic_error("6", "wrong_item_type", "item_id"),
                )

    def test_operational_contract_family_is_declared_as_implemented(self) -> None:
        implemented = {
            "spine.schedule-operations-normalization.v1",
            "spine.schedule-agenda.v1",
            "spine.schedule-agenda-response.v1",
            "spine.schedule-update.v2",
            "spine.schedule-update-response.v2",
            "spine.schedule-update-receipt.v2",
            "spine.schedule-cancel.v1",
            "spine.schedule-cancel-response.v1",
            "spine.schedule-cancel-receipt.v1",
        }
        self.assertTrue(implemented.issubset(IMPLEMENTED_CONTRACT_VERSIONS))


def _valid(schema: dict[str, object], value: dict[str, object], registry: Registry) -> bool:
    return not list(Draft202012Validator(schema, registry=registry).iter_errors(value))


def _work_reconciliation_arrays_are_disjoint(value: dict[str, object]) -> bool:
    reconciliation = value.get("work_reconciliation")
    if not isinstance(reconciliation, dict):
        return True

    fields = (
        "cancelled_work_instance_ids",
        "retained_work_instance_ids",
        "protected_stale_work_instance_ids",
        "created_work_instance_ids",
    )
    seen: set[str] = set()
    for field in fields:
        identities = reconciliation.get(field)
        if not isinstance(identities, list) or not all(
            isinstance(identity, str) for identity in identities
        ):
            return False
        for identity in identities:
            if identity in seen:
                return False
            seen.add(identity)
    return True


def _request_command(request: object) -> str | None:
    if not isinstance(request, dict):
        return None
    return {
        "spine.schedule-agenda.v1": "agenda.show",
        "spine.schedule-update.v2": "schedule.update",
        "spine.schedule-cancel.v1": "schedule.cancel",
    }.get(request.get("contract_version"))


def _schedule_operation_semantic_error(
    scenario: dict[str, object],
) -> dict[str, str | None] | None:
    command = scenario.get("command")
    request = scenario.get("request")
    context = scenario.get("ledger_context")
    if not isinstance(request, dict) or not isinstance(context, dict):
        return None

    if command == "agenda.show":
        if "cursor" in request and context.get("cursor_query_matches") is False:
            return _semantic_error("A3", "invalid_request", "cursor")
        if context.get("timezone_database_available") is False:
            return _semantic_error("A4", "environment_failure", "timezone_database_version")
        if context.get("range_start_resolution") in {"ambiguous", "nonexistent"}:
            return _semantic_error("A5", "invalid_request", "range_start_local")
        if context.get("range_end_resolution") in {"ambiguous", "nonexistent"}:
            return _semantic_error("A5", "invalid_request", "range_end_local")
        if "cursor" in request and context.get("cursor_snapshot_matches") is False:
            return _semantic_error("A6", "stale_cursor", "cursor")
        return None

    if command not in {"schedule.update", "schedule.cancel"}:
        return None

    if context.get("shell_status") == "archived":
        return _semantic_error("6", "invalid_state_transition", "status")

    item_type = context.get("item_type")
    if item_type not in {"event", "task"}:
        return _semantic_error("6", "wrong_item_type", "item_id")

    detail_status = context.get("detail_status")
    if (item_type == "event" and detail_status != "scheduled") or (
        item_type == "task" and detail_status != "open"
    ):
        return _semantic_error("6", "invalid_state_transition", "detail_status")
    if request.get("target_version") != context.get("current_version"):
        return _semantic_error("6", "stale_version", "target_version")

    if command == "schedule.cancel":
        return None

    if context.get("primary_anchor_kind") != "local_instant":
        return _semantic_error("7", "invalid_request", "primary_schedule.anchor_kind")

    patch = request.get("patch")
    if not isinstance(patch, dict):
        return None
    if context.get("event_has_end_anchor") is True and "scheduled_time" in patch:
        return _semantic_error("7", "invalid_request", "patch.scheduled_time")
    if (
        context.get("has_recurrence") is True
        and "scheduled_time" in patch
        and "recurrence" not in patch
    ):
        return _semantic_error("7", "missing_required_field", "patch.recurrence")

    notification_plan = patch.get("notification_plan")
    additions = (
        notification_plan.get("custom_additions")
        if isinstance(notification_plan, dict)
        else None
    )
    if isinstance(additions, list) and context.get("policy_key_mapping_matches") is False:
        return _semantic_error(
            "7",
            "semantic_conflict",
            "patch.notification_plan.custom_additions[0].policy_key",
        )

    normalized_hashes = context.get("normalized_policy_hashes")
    if isinstance(normalized_hashes, list) and len(normalized_hashes) != len(
        set(normalized_hashes)
    ):
        return _semantic_error("9", "semantic_conflict", "patch.notification_plan")
    return None


def _semantic_error(phase: str, code: str, field: str | None) -> dict[str, str | None]:
    return {"phase": phase, "code": code, "field": field}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
