from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
MANIFEST_PATH = ROOT / "contracts" / "schedule-create-fixture-manifest.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "schedule_create" / "contracts"


class ScheduleCreateContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: _load(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )
        cls.request_schema = cls.schemas["schedule-create-request.schema.json"]
        cls.response_schema = cls.schemas["schedule-create-response.schema.json"]

    def test_manifest_is_complete_and_all_fixtures_validate(self) -> None:
        manifest = _load(MANIFEST_PATH)
        self.assertEqual(manifest["schema_version"], "spine.schedule-create-contract-fixtures.v1")
        self.assertEqual(manifest["fixture_scope"], "structural_examples")

        fixture_ids: list[str] = []
        fixture_paths: list[str] = []
        for entry in manifest["fixtures"]:
            fixture_ids.append(entry["fixture_id"])
            fixture_paths.append(entry["fixture"])
            schema = _load(ROOT / entry["schema"])
            fixture = _load(ROOT / entry["fixture"])
            Draft202012Validator(schema, registry=self.registry).validate(fixture)

        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))
        self.assertEqual(len(fixture_paths), len(set(fixture_paths)))
        self.assertEqual(
            sorted(path.as_posix() for path in FIXTURE_DIR.glob("*.json")),
            sorted((ROOT / path).as_posix() for path in fixture_paths),
        )

    def test_request_schema_rejects_cross_type_and_hidden_route_shapes(self) -> None:
        request = _load(FIXTURE_DIR / "request_event_repeat_window_materialized.json")

        cross_type = copy.deepcopy(request)
        cross_type["item"]["task_detail"] = {}
        self.assertFalse(self._request_valid(cross_type))

        inline_route = copy.deepcopy(request)
        inline_route["delivery"]["target"]["target_ref"] = "hidden-destination"
        self.assertFalse(self._request_valid(inline_route))

        inherited_timezone_override = copy.deepcopy(request)
        inherited_timezone_override["scheduled_time"]["recurrence"] = {
            "time_basis": "local_instant",
            "rules": [],
        }
        self.assertFalse(self._request_valid(inherited_timezone_override))

    def test_request_schema_rejects_unbounded_or_partial_materialization_shapes(self) -> None:
        request = _load(FIXTURE_DIR / "request_event_repeat_window_materialized.json")

        missing_range = copy.deepcopy(request)
        del missing_range["materialization"]["range"]
        self.assertFalse(self._request_valid(missing_range))

        excessive_limit = copy.deepcopy(request)
        excessive_limit["materialization"]["limit"] = "1001"
        self.assertFalse(self._request_valid(excessive_limit))

        no_mode_with_range = copy.deepcopy(request)
        no_mode_with_range["materialization"] = {
            "mode": "none",
            "range": request["materialization"]["range"],
        }
        self.assertFalse(self._request_valid(no_mode_with_range))

    def test_task_role_status_matches_task_create_contract(self) -> None:
        request = _load(FIXTURE_DIR / "request_recurring_task_policy_only.json")

        inactive_role = copy.deepcopy(request)
        inactive_role["item"]["task_detail"]["subject_roles"][0]["status"] = "inactive"
        self.assertTrue(self._request_valid(inactive_role))

        omitted_status = copy.deepcopy(request)
        del omitted_status["item"]["task_detail"]["subject_roles"][0]["status"]
        self.assertTrue(self._request_valid(omitted_status))

        unsupported_status = copy.deepcopy(request)
        unsupported_status["item"]["task_detail"]["subject_roles"][0]["status"] = "pending"
        self.assertFalse(self._request_valid(unsupported_status))

    def test_duplicate_task_role_pair_is_rejected_semantically_regardless_of_status(self) -> None:
        manifest = _load(MANIFEST_PATH)
        entry = next(
            value
            for value in manifest["fixtures"]
            if value["fixture_id"] == "failure.duplicate_task_subject_role"
        )
        request = _load(ROOT / entry["fixture"])

        self.assertTrue(self._request_valid(request))
        self.assertEqual(_task_subject_role_semantic_error(request), entry["expected_error"])

        exact_duplicate = copy.deepcopy(request)
        exact_duplicate["item"]["task_detail"]["subject_roles"][1]["status"] = "active"
        self.assertFalse(self._request_valid(exact_duplicate))

    def test_response_schema_never_represents_delivery_by_this_command(self) -> None:
        response = _load(FIXTURE_DIR / "response_event_repeat_window_materialized.json")
        response["delivery"]["delivery_state"] = "delivered"
        self.assertFalse(self._response_valid(response))

    def test_replay_response_effect_does_not_change_stored_receipt_effect(self) -> None:
        response = _load(FIXTURE_DIR / "response_event_repeat_window_materialized.json")
        response["effect"] = "schedule_create_replay"
        self.assertEqual(response["receipt"]["effect"], "schedule_created")
        self.assertTrue(self._response_valid(response))

        response["receipt"]["effect"] = "schedule_create_replay"
        self.assertFalse(self._response_valid(response))

    def _request_valid(self, value: object) -> bool:
        return not list(Draft202012Validator(self.request_schema, registry=self.registry).iter_errors(value))

    def _response_valid(self, value: object) -> bool:
        return not list(Draft202012Validator(self.response_schema, registry=self.registry).iter_errors(value))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _task_subject_role_semantic_error(value: dict[str, object]) -> dict[str, str] | None:
    item = value.get("item")
    if not isinstance(item, dict):
        return None
    task_detail = item.get("task_detail")
    if not isinstance(task_detail, dict):
        return None
    subject_roles = task_detail.get("subject_roles")
    if not isinstance(subject_roles, list):
        return None

    seen: set[tuple[object, object]] = set()
    for subject_role in subject_roles:
        if not isinstance(subject_role, dict):
            continue
        key = (subject_role.get("subject_id"), subject_role.get("role"))
        if key in seen:
            return {
                "code": "invalid_request",
                "field": "item.task_detail.subject_roles",
            }
        seen.add(key)
    return None


if __name__ == "__main__":
    unittest.main()
