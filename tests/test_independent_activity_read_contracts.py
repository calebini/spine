"""Offline v2 wire/semantic oracles; no HTTP, permission or concurrency certification."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.hashing import hash_canonical_json

ROOT = Path(__file__).parents[1]
CONTRACTS = ROOT / "contracts"
SCHEMAS = CONTRACTS / "schemas"
FIXTURES = ROOT / "tests/fixtures/independent_activity_reads/contracts"
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("spine-local-date-time", raises=ValueError)
def calendar_local_datetime(value: object) -> bool:
    """Required v2 format assertion; no timezone conversion or rollover repair."""
    if not isinstance(value, str):
        return True  # JSON Schema's type keyword handles non-strings.
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", value) is None:
        return False
    datetime.fromisoformat(value)  # Rejects impossible dates, year zero and invalid clocks.
    return True


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def calendar_utc_datetime(value: object) -> bool:
    """Assert Spine's restricted UTC type without optional RFC3339 dependencies."""
    if not isinstance(value, str):
        return True
    return value.endswith("Z") and calendar_local_datetime(value[:-1])


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def normalize(route: str, envelope: dict, rules: dict) -> dict:
    """Test-only reference normalization; runtime must implement and reuse the contract."""
    request = copy.deepcopy(envelope["request"])
    for field in rules["strip_request_fields"]:
        request.pop(field, None)
    for field, value in rules["request_defaults"][route].items():
        request.setdefault(field, value)
    for field in rules["set_arrays"]:
        if field in request:
            assert len(request[field]) == len(set(request[field])), "duplicate set member"
            request[field] = sorted(request[field])
    return {
        "contract_version": rules["contract_version"], "route": route, "request": request,
        **{field: envelope.get(field) for field in rules["null_guard_defaults"]},
    }


def semantic_oracle(response: dict) -> None:
    """Cross-field fixture checks, not a substitute for domain or authorization logic."""
    def walk(value: object) -> None:
        if isinstance(value, list):
            for row in value:
                walk(row)
            return
        if not isinstance(value, dict):
            return
        if "has_more" in value:
            assert bool(value["next_cursor"]) == value["has_more"]
            rows = value.get("entries", value.get("occurrences", [])) + value.get("unplaced_items", [])
            if value["has_more"]:
                assert rows, "empty nonterminal page"
            if "limit" in value:
                assert len(rows) <= int(value["limit"]), "shared page limit exceeded"
        if "status_counts" in value:
            assert int(value["count"]) == sum(int(n) for n in value["status_counts"].values())
        if "anchors" in value:
            roles = [a["anchor_role"] for a in value["anchors"]]
            assert len(roles) == len(set(roles)), "duplicate role"
            order = ["event_start", "event_end", "task_due", "task_defer_until"]
            assert roles == sorted(roles, key=order.index)
        if "window_start_utc" in value:
            assert value["window_start_utc"] < value["window_end_utc"], "reversed window"
        if "local_date" in value:
            datetime.strptime(value["local_date"], "%Y-%m-%d")
        if "item_type" in value and "time" in value:
            anchors = value["time"].get("anchors", [])
            prefix = "event_" if value["item_type"] == "event" else "task_"
            assert all(a["anchor_role"].startswith(prefix) for a in anchors), "wrong item role"
            if value["item_type"] == "event" and value["time"]["availability"] == "available":
                assert any(a["anchor_role"] == "event_start" for a in anchors), "available event missing start"
        for name in ("policies", "work", "attempts"):
            section = value.get(name)
            if isinstance(section, dict) and section.get("availability") == "available" and "value" in section:
                assert isinstance(section["value"], dict), "available summary cannot be null"
        for child in value.values():
            walk(child)

    walk(response)
    if not response.get("ok"):
        return
    result = response["result"]
    if response["result_contract"] == "spine.trusted-web-occurrences.v1":
        root = result["activity"]
        assert root["recurrence"] is not None
        for occurrence in result["occurrences"]:
            for field in ("item_id", "item_type", "current_version"):
                assert occurrence[field] == root[field], "occurrence root mismatch"
            for field in ("recurrence_set_id", "recurrence_revision_id", "source_item_version"):
                assert occurrence[field] == root["recurrence"][field]
            assert occurrence["range_basis"] == result["range"]["range_basis"]
            if root["status"] == "archived":
                assert not occurrence["actionable"]
        basis = result["range"]["range_basis"]
        def key(row: dict) -> tuple:
            if basis == "original_schedule":
                return row["original_scheduled_fact"], row["occurrence_key"], row["occurrence_id"]
            return row["expressed_scheduled_fact"], row["expressed_schedule_key"], row["occurrence_key"], row["occurrence_id"]
        assert result["occurrences"] == sorted(result["occurrences"], key=key)
        assert len({row["occurrence_key"] for row in result["occurrences"]}) == len(result["occurrences"])
    if response["result_contract"] == "spine.trusted-web-agenda.v2":
        assert [row["activity"]["item_id"] for row in result["unplaced_items"]] == sorted(
            row["activity"]["item_id"] for row in result["unplaced_items"]
        )
        def agenda_key(row: dict) -> tuple:
            return (
                row["view_local_date"], not row["all_day"], row["sort_at_utc"], row["anchor_role"],
                row["activity"]["item_id"], (row["occurrence"] or {}).get("occurrence_key", ""),
            )
        assert result["entries"] == sorted(result["entries"], key=agenda_key)
        for row in result["entries"]:
            assert (row["occurrence"] is None) == (row["activity"]["recurrence"] is None)
            if row["occurrence"] is not None:
                assert row["activity"]["time"] == row["occurrence"]["time"]
            assert row["anchor_role"] == ("event_start" if row["activity"]["item_type"] == "event" else "task_due")
            assert any(
                a["anchor_role"] == row["anchor_role"] for a in row["activity"]["time"]["anchors"]
            ), "agenda entry missing primary anchor"


class IndependentActivityReadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {p.name: load(p) for p in SCHEMAS.glob("*.schema.json")}
        cls.references = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )
        cls.manifest = load(CONTRACTS / "independent-activity-read-fixture-manifest.json")
        cls.registry = load(CONTRACTS / "spine.trusted-web-read-registry.v1.json")

    def validator(self, name: str) -> Draft202012Validator:
        return Draft202012Validator(self.schemas[name], registry=self.references, format_checker=FORMAT_CHECKER)

    def test_required_formats_are_registered_and_calendar_valid(self) -> None:
        def formats(value: object) -> set[str]:
            if isinstance(value, dict):
                own = {value["format"]} if "format" in value else set()
                return own.union(*(formats(child) for child in value.values()))
            if isinstance(value, list):
                return set().union(*(formats(child) for child in value))
            return set()
        required = formats(self.schemas["trusted-web-read-types.schema.json"])
        self.assertIn("spine-local-date-time", required)
        self.assertTrue(required <= FORMAT_CHECKER.checkers.keys())
        local = self.schemas["trusted-web-read-types.schema.json"]["$defs"]["local_datetime"]
        validator = Draft202012Validator(local, format_checker=FORMAT_CHECKER)
        for value in ("2000-02-29T00:00:00", "2024-02-29T23:59:59", "0001-01-01T00:00:00", "9999-12-31T23:59:59"):
            with self.subTest(valid=value):
                self.assertTrue(validator.is_valid(value))
        for value in (
            "2026-02-31T09:00:00", "2026-02-29T09:00:00", "1900-02-29T09:00:00",
            "2026-04-31T09:00:00", "0000-01-01T00:00:00", "2026-09-21T24:00:00",
            "2026-09-21T09:00:60", "2026-09-21T09:00:00Z", "2026-09-21T09:00:00.1",
        ):
            with self.subTest(invalid=value):
                self.assertFalse(validator.is_valid(value))

    def test_schema_and_fixture_inventory(self) -> None:
        for name, schema in self.schemas.items():
            if name.startswith("trusted-web-read-"):
                Draft202012Validator.check_schema(schema)
        ids = set()
        for entry in self.manifest["fixtures"]:
            with self.subTest(fixture=entry["fixture_id"]):
                self.assertNotIn(entry["fixture_id"], ids)
                ids.add(entry["fixture_id"])
                errors = list(self.validator(Path(entry["schema"]).name).iter_errors(load(ROOT / entry["fixture"])))
                self.assertEqual(not errors, entry["valid"], [error.message for error in errors])
        self.assertEqual({ROOT / e["fixture"] for e in self.manifest["fixtures"]}, set(FIXTURES.glob("*.json")))

    def test_registry_and_discovery_are_closed_read_only_and_not_advertised(self) -> None:
        self.validator("trusted-web-read-registry.schema.json").validate(self.registry)
        self.assertEqual([e["command"] for e in self.registry["commands"]], ["item.occurrences", "schedule.show"])
        families = {self.registry["api_contract"], self.registry["cursor_contract"], self.registry["contract_version"]}
        for entry in [*self.registry["commands"], self.registry["agenda"]]:
            self.assertEqual(entry["access_mode"], "read")
            self.assertIn(entry["request_schema"], self.schemas)
            self.assertIn(entry["response_schema"], self.schemas)
            families.add(entry["result_contract"])
        self.assertFalse(families & IMPLEMENTED_CONTRACT_VERSIONS)
        extra = copy.deepcopy(self.registry)
        extra["commands"].append({"command": "schedule.update"})
        self.assertFalse(self.validator("trusted-web-read-registry.schema.json").is_valid(extra))
        capabilities = load(FIXTURES / "response_capabilities.json")["result"]
        self.assertEqual(capabilities["registry_contract"], self.registry["contract_version"])
        for actual, entry in zip(capabilities["commands"], self.registry["commands"], strict=True):
            self.assertEqual(actual, {key: entry[key] for key in actual})

    def test_route_specific_guards_and_closed_section_mapping(self) -> None:
        projection = load(CONTRACTS / "trusted-web-read-projection.v1.json")
        defs = self.schemas["trusted-web-read-types.schema.json"]["$defs"]
        for entry in [*self.registry["commands"], self.registry["agenda"]]:
            schema = self.schemas[entry["request_schema"]]
            self.assertEqual(set(schema["properties"]) - {"contract_version", "request"}, set(entry["optional_guards"]))
            properties = schema["properties"]["request"]["properties"]
            if entry["sections"]:
                self.assertEqual(set(properties["include"]["items"]["enum"]), set(entry["sections"]))
        self.assertEqual(set(projection["sections"]), set(defs["sections"]["properties"]))
        for section in projection["sections"].values():
            definition = "core" if section["definition"] == "related_item" else section["definition"]
            self.assertEqual(set(section["fields"]), set(defs[definition]["properties"]))
        self.assertEqual(set(projection["root"]["fields"]), set(defs["core"]["properties"]))

    def test_system_timezone_shorthand_is_not_a_concrete_v2_pin(self) -> None:
        request = load(FIXTURES / "request_agenda.json")
        request["request"]["timezone_database_version"] = "system_current"
        self.assertFalse(self.validator("trusted-web-read-agenda-request.schema.json").is_valid(request))

    def test_section_cursor_requires_the_matching_include(self) -> None:
        # Cross-field contract oracle; the runtime must enforce it before decoding a cursor.
        def valid(request: dict) -> bool:
            return set(request.get("section_cursors", {})) <= set(request.get("include", []))
        self.assertFalse(valid({"section_cursors": {"work": "opaque"}}))
        self.assertTrue(valid({"include": ["work"], "section_cursors": {"work": "opaque"}}))

    def test_positive_response_semantic_oracles(self) -> None:
        for entry in self.manifest["fixtures"]:
            if entry["valid"] and entry["fixture_id"].startswith("response_"):
                with self.subTest(fixture=entry["fixture_id"]):
                    semantic_oracle(load(ROOT / entry["fixture"]))

    def test_audit_summary_and_primary_anchor_failures_reach_semantic_oracle(self) -> None:
        for name in (
            "invalid_agenda_null_policies_summary", "invalid_agenda_null_work_summary",
            "invalid_agenda_null_attempts_summary", "invalid_available_event_missing_start",
            "invalid_occurrence_event_missing_start", "invalid_agenda_task_without_due",
        ):
            with self.subTest(fixture=name), self.assertRaises(AssertionError):
                semantic_oracle(load(FIXTURES / f"{name}.json"))

    def test_absent_location_and_receipt_singletons_remain_nullable(self) -> None:
        response = load(FIXTURES / "response_schedule_no_context.json")
        for name in ("primary_location", "authoring_receipt"):
            response["result"]["sections"][name] = {
                "availability": "available", "scope": "authorized_only", "coverage": "complete", "value": None,
            }
        self.validator("trusted-web-read-schedule-response.schema.json").validate(response)
        semantic_oracle(response)

    def test_calendar_assertions_follow_request_response_and_cursor_references(self) -> None:
        cases = [
            ("request_agenda", "agenda-request", ("request", field))
            for field in ("range_start_local", "range_end_local")
        ] + [
            ("request_occurrences", "occurrences-request", ("request", field))
            for field in ("range_start", "range_end")
        ] + [
            ("response_occurrences", "occurrences-response", ("result", "range", field))
            for field in ("range_start", "range_end")
        ] + [
            ("response_occurrences", "occurrences-response", ("result", "occurrences", 0, field))
            for field in ("original_scheduled_fact", "expressed_scheduled_fact")
        ] + [("cursor_occurrences", "cursor", ("last_key", 0))]
        for fixture, schema, path in cases:
            for invalid in ("2026-02-31T09:00:00", "2026-02-31", "2026-02-31T09:00:00Z"):
                with self.subTest(fixture=fixture, path=path, invalid=invalid):
                    value = load(FIXTURES / f"{fixture}.json")
                    parent = value
                    for part in path[:-1]:
                        parent = parent[part]
                    parent[path[-1]] = invalid
                    self.assertFalse(self.validator(f"trusted-web-read-{schema}.schema.json").is_valid(value))

    def test_cross_field_failures_not_expressible_in_schema(self) -> None:
        summary = load(FIXTURES / "response_agenda_authorized_work_summary.json")
        summary["result"]["entries"][0]["sections"]["work"]["value"]["count"] = "2"
        shared_limit = load(FIXTURES / "response_agenda_resolved_and_unplaced.json")
        shared_limit["result"]["limit"] = "1"
        window = load(FIXTURES / "response_schedule_utc_window.json")
        window["result"]["activity"]["time"]["anchors"][0]["window_end_utc"] = "2026-09-21T06:00:00Z"
        occurrence = load(FIXTURES / "response_occurrences.json")
        occurrence["result"]["occurrences"][0]["current_version"] = "99"
        for value in (summary, shared_limit, window, occurrence):
            with self.assertRaises(AssertionError):
                semantic_oracle(value)

    def test_normalization_and_hash_vectors(self) -> None:
        rules = load(CONTRACTS / "trusted-web-read-normalization.v1.json")
        vectors = load(CONTRACTS / "trusted-web-read-normalization-vectors.v1.json")["vectors"]
        for vector in vectors:
            with self.subTest(vector=vector["name"]):
                actual = normalize(vector["route"], vector["input"], rules)
                self.assertEqual(actual, vector["preimage"])
                self.assertEqual(canonical_json_text(actual), vector["canonical_json"])
                self.assertEqual(hash_canonical_json(actual), vector["sha256"])
        self.assertEqual(vectors[0]["sha256"], vectors[1]["sha256"])
        changed = copy.deepcopy(vectors[0]["input"])
        changed["request"]["section_limit"] = "51"
        self.assertNotEqual(hash_canonical_json(normalize("schedule.show", changed, rules)), vectors[0]["sha256"])
        changed["request"]["include"] = ["work", "work"]
        with self.assertRaises(AssertionError):
            normalize("schedule.show", changed, rules)

    def test_cursor_mac_vector_tamper_and_fixed_expiry(self) -> None:
        vector = load(CONTRACTS / "trusted-web-read-cursor-vectors.v2.json")
        payload = vector["payload"]
        self.validator("trusted-web-read-cursor.schema.json").validate(payload)
        raw = canonical_json_bytes(payload)
        self.assertEqual(raw.decode(), vector["canonical_json"])
        key = vector["public_test_key"].encode()
        signature = hmac.new(key, b"spine.trusted-web-cursor.v2\x00" + raw, hashlib.sha256).digest()
        def encode(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        self.assertEqual(vector["wire"], f"v2.{encode(raw)}.{encode(signature)}")
        modified = dict(payload, selection_id="other-selection")
        altered = hmac.new(key, b"spine.trusted-web-cursor.v2\x00" + canonical_json_bytes(modified), hashlib.sha256).digest()
        self.assertFalse(hmac.compare_digest(signature, altered))
        issued = datetime.fromisoformat(payload["issued_at_utc"])
        expires = datetime.fromisoformat(payload["expires_at_utc"])
        transition = datetime.fromisoformat(payload["authorization_valid_until_utc"])
        self.assertLessEqual(expires - issued, timedelta(seconds=900))
        self.assertLess(transition, expires)
        # Test-only lifetime oracle: source/identity release fencing still requires runtime tests.
        def live(now: datetime) -> bool:
            return issued <= now < min(expires, transition)
        self.assertTrue(live(issued))
        self.assertFalse(live(transition))
        self.assertFalse(live(expires))
        self.assertFalse(live(issued - timedelta(seconds=1)))

    def test_schema_pin_closure_and_artifact_bytes(self) -> None:
        pins = load(CONTRACTS / "trusted-web-read-schema-pins.v1.json")
        pending = list(pins["schema_roots"])
        visited = set()
        def refs(value: object) -> set[str]:
            if isinstance(value, dict):
                result = {value["$ref"].split("#")[0]} if "$ref" in value and not value["$ref"].startswith("#") else set()
                return result.union(*(refs(child) for child in value.values()))
            if isinstance(value, list):
                return set().union(*(refs(child) for child in value))
            return set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            pending.extend(refs(self.schemas[name]) - visited)
        self.assertEqual(visited, set(pins["schemas"]))
        for name, expected in pins["schemas"].items():
            self.assertEqual(hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest(), expected)
        for name, expected in pins["artifacts"].items():
            self.assertEqual(hashlib.sha256((CONTRACTS / name).read_bytes()).hexdigest(), expected)

    def test_behavioral_matrix_is_explicitly_pending(self) -> None:
        self.assertEqual(self.manifest["status"], "contract_only")
        self.assertEqual(self.manifest["runtime_acceptance"], "not_implemented")
        cases = self.manifest["behavioral_cases"]
        self.assertEqual([case["id"] for case in cases], [f"IR-{i:02d}" for i in range(1, 17)])
        fixture_ids = {entry["fixture_id"] for entry in self.manifest["fixtures"]}
        for case in cases:
            self.assertEqual(case["status"], "runtime_pending")
            self.assertTrue(case["setup"] and case["action"] and case["oracle"] and case["fixture_ids"])
            self.assertTrue(set(case["fixture_ids"]) <= fixture_ids)


if __name__ == "__main__":
    unittest.main()
