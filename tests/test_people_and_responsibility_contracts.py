"""Offline schemas and pure policy witnesses; NOT PR runtime acceptance tests."""

import base64
import copy
import hashlib
import hmac
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urljoin

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.commands.registry import COMMAND_RUNTIME_CONTRACT_REGISTRY
from spine.core.canonical_json import canonical_json_bytes

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures/people_and_responsibility"
BASE = "https://cortext.local/spine/"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_request(command, value):
    """Pure normalization witness, not a command validator or runtime adapter."""
    result = copy.deepcopy(value)
    if command == "people.list":
        for key, default in {"subject_status": "active", "subject_kind": "all", "limit": "25"}.items():
            result.setdefault(key, default)
    if command == "schedule.create" and "people" not in result:
        key = "participants" if result["item"]["item_type"] == "event" else "assignees"
        result["people"] = {key: []}
    if command in {"agenda.show", "item.occurrences"}:
        result.setdefault("limit", "25")
    if command in {"agenda.show", "schedule.show"}:
        result.setdefault("include", [])
    if command == "schedule.show":
        result.setdefault("section_limit", "25")
    if command == "agenda.show":
        result.setdefault("item_types", ["event", "task"])
        result.setdefault("include_terminal", False)
    if "person_filter" in result:
        result["person_filter"].setdefault("roles", ["assignee", "participant"])

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"participants", "assignees", "roles", "include", "item_ids", "item_types"} and isinstance(child, list):
                    if len(child) != len(set(child)):
                        raise ValueError("invalid_request")
                    value[key] = sorted(child)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result


def query_preimage(command, request, guards=None):
    normalized = normalize_request(command, request)
    normalized.pop("cursor", None)
    normalized.pop("section_cursors", None)
    guards = guards or {}
    return {
        "derivation_version": "spine.people-query.v1",
        "canonical_json_version": "spine.canonical-json.v1",
        "route": command,
        "request": normalized,
        "guards": {k: guards.get(k) for k in ("expected_access_epoch", "expected_item_version", "expected_recurrence_revision_id")},
    }


def role_facts(rows):
    return sorted(
        ({key: row[key] for key in ("subject_id", "role", "status")} for row in rows),
        key=lambda row: (row["role"], row["subject_id"], row["status"]),
    )


def replacement_model(case):
    before = role_facts(case["current"])
    if not case["provided"]:
        return before, False
    patch = case["patch"]
    if not isinstance(patch, dict) or len(patch) != 1 or next(iter(patch)) not in {"participants", "assignees"}:
        raise ValueError("invalid_request")
    key, ids = next(iter(patch.items()))
    expected_key = "participants" if case["item_type"] == "event" else "assignees"
    if key != expected_key:
        raise ValueError("wrong_item_type")
    if not isinstance(ids, list) or any(not isinstance(v, str) or not v for v in ids) or len(set(ids)) != len(ids):
        raise ValueError("invalid_request")
    role = "participant" if key == "participants" else "assignee"
    after = role_facts([row for row in before if row["role"] != role] + [{"subject_id": v, "role": role, "status": "active"} for v in ids])
    if len(after) > 100 or len(before) > 100:
        raise ValueError("capacity")
    return after, after != before


def admission_model(case):
    if not case["item_edit"]:
        return False
    if not case["fresh"]:
        return True
    if not case["target_active"]:
        return False
    if case["mode"] == "trusted_local":
        return True
    if not case["scope_active"]:
        return False
    if case["scope_kind"] == "subject":
        return case["caller"] == case["scope_subject"] == case["target"]
    return case["caller_group_role"] in {"member", "admin", "owner"} and case["target_member"]


def label_model(case):
    if not case["item_read"]:
        raise ValueError("resource_unavailable")
    if case["subject"] is None:
        raise ValueError("integrity")
    if not case["may_label"]:
        return {"availability": "not_disclosed"}
    return {"availability": "available", **{key: case["subject"][key] for key in ("display_name", "subject_kind", "status")}}


def filter_model(items, subject_id, roles):
    return sorted(
        item["id"]
        for item in items
        if item["authorized"]
        and any(
            row["subject_id"] == subject_id
            and row["role"] in roles
            and row["status"] == "active"
            and row["version"] == item["current_version"]
            for row in item["roles"]
        )
    )


def continuity_model(case):
    """Compare declared small semantic snapshots, never execute a ledger proof."""
    before, after = case["before"], case["after"]
    allowed = {"people": "roles", "facet": "facets", "presentation": "presentation"}[case["kind"]]
    if set(before) != set(after):
        return False
    for key in before.keys() - {"policies", allowed}:
        if before[key] != after[key]:
            return False
    if allowed == "roles":
        managed = case["replacement_role"]
        if managed not in {"participant", "assignee"} or any(row["role"] != managed for row in case["requested_roles"]):
            return False
        expected = [row for row in before["roles"] if row["role"] != managed] + case["requested_roles"]
        def canonical(rows):
            return sorted((row["role"], row["subject_id"], row["status"]) for row in rows)
        if canonical(after["roles"]) != canonical(expected):
            return False
    if len(before["policies"]) != len(after["policies"]):
        return False
    predecessors = {row["policy_id"]: row["meaning"] for row in before["policies"]}
    seen = set()
    for row in after["policies"]:
        source = row["source_policy_id"]
        if source not in predecessors or source in seen or row["meaning"] != predecessors[source]:
            return False
        seen.add(source)
    return seen == set(predecessors)


def token_for(payload, secret):
    raw = canonical_json_bytes(payload)
    signature = hmac.digest(secret, b"spine.people-cursor.v1\0" + raw, "sha256")

    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    return "pc1." + encode(raw) + "." + encode(signature)


class PeopleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load(ROOT / "contracts/people-and-responsibility-fixture-manifest.json")
        cls.contract = load(ROOT / cls.manifest["registry"])
        cls.models = load(ROOT / cls.manifest["model_witness"])
        closure = cls.manifest["schemas"] + cls.manifest["schema_dependencies"]
        cls.schemas = {s["$id"]: s for p in closure if (s := load(ROOT / p))}
        cls.resources = Registry().with_resources((uri, Resource.from_contents(s)) for uri, s in cls.schemas.items())
        cls.formats = FormatChecker()

        @cls.formats.checks("spine-local-date-time", raises=ValueError)
        def local_datetime(value):
            return not isinstance(value, str) or datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").isoformat() == value

    def validator(self, path):
        return Draft202012Validator({"$ref": BASE + path}, registry=self.resources, format_checker=self.formats)

    def test_all_schemas_and_wire_fixtures(self):
        for path in self.manifest["schemas"]:
            Draft202012Validator.check_schema(load(ROOT / path))
        paths, ids = set(), set()
        for row in self.manifest["fixtures"]:
            with self.subTest(row["fixture_id"]):
                self.assertNotIn(row["fixture_id"], ids)
                self.assertNotIn(row["fixture"], paths)
                ids.add(row["fixture_id"])
                paths.add(row["fixture"])
                errors = list(self.validator(row["schema"]).iter_errors(load(ROOT / row["fixture"])))
                self.assertEqual(not errors, row["valid"], "\n".join(e.message for e in errors))
        self.assertEqual(paths, {str(p.relative_to(ROOT)) for p in (FIXTURES / "contracts").glob("*.json")})

    def test_people_section_preserves_inherited_singleton_envelope(self):
        people = self.schemas[BASE + "contracts/schemas/people/types.schema.json"]["$defs"]["section"]
        inherited = self.schemas[BASE + "contracts/schemas/trusted-web-read-types.schema.json"]["$defs"]["primary_location_section"]
        inherited_states = {branch["properties"]["availability"]["const"]: branch for branch in inherited["oneOf"]}
        self.assertEqual({branch["properties"]["availability"]["const"] for branch in people["oneOf"]}, set(inherited_states))
        for branch in people["oneOf"]:
            state = branch["properties"]["availability"]["const"]
            with self.subTest(state=state):
                expected = inherited_states[state]
                # Payload names/types are domain-specific; the enclosing rules are inherited.
                self.assertEqual(
                    {k: v for k, v in branch["properties"].items() if k != "people"},
                    {k: v for k, v in expected["properties"].items() if k != "value"},
                )
                self.assertEqual(set(branch["required"]) - {"people"}, set(expected["required"]) - {"value"})
                self.assertIs(branch["additionalProperties"], False)

    def test_people_section_states_are_closed_and_complete(self):
        validator = self.validator("contracts/schemas/people/types.schema.json#/$defs/section")
        available = load(FIXTURES / "contracts/web_response_schedule.json")["result"]["sections"]["people"]
        sections = [available] + [load(FIXTURES / "contracts" / (name + ".json")) for name in
                                  ("section_people_not_requested", "section_people_unavailable")]
        for section in sections:
            state = section["availability"]
            with self.subTest(state=state):
                validator.validate(section)
                for key in section:
                    with self.subTest(missing=key):
                        self.assertFalse(validator.is_valid({k: v for k, v in section.items() if k != key}))
                for key, value in {"scope": "all", "coverage": "partial", "has_more": False, "next_cursor": None,
                                   "values": [], "has_hidden": True, "withheld_count": 0}.items():
                    with self.subTest(field=key):
                        self.assertFalse(validator.is_valid({**section, key: value}))
                for reason in ("capacity_exceeded", "section_unavailable", "ownership_missing", "hidden_resource"):
                    with self.subTest(reason=reason):
                        self.assertFalse(validator.is_valid({**section, "reason_code": reason}))
        for section in sections[1:]:
            self.assertFalse(validator.is_valid({**section, "people": available["people"]}))
        self.assertFalse(validator.is_valid({**sections[1], "coverage": "complete"}))
        self.assertFalse(validator.is_valid({**available, "coverage": "incomplete"}))
        self.assertFalse(validator.is_valid({**sections[2], "coverage": "complete"}))
        self.assertFalse(validator.is_valid({**sections[1], "reason_code": "context_unavailable"}))
        self.assertFalse(validator.is_valid({**available, "reason_code": "context_unavailable"}))
        self.assertFalse(validator.is_valid({**available, "people": None}))
        empty = copy.deepcopy(available)
        empty["people"]["associations"] = []
        empty["people"]["subjects"] = []
        validator.validate(empty)
        undisclosed = copy.deepcopy(available)
        undisclosed["people"]["subjects"][0]["label"] = {"availability": "not_disclosed"}
        validator.validate(undisclosed)

    def test_people_section_states_in_schedule_agenda_and_unplaced_views(self):
        for command in ("schedule", "agenda"):
            original = load(FIXTURES / "contracts" / ("web_response_" + command + ".json"))
            route = "schedule.show" if command == "schedule" else "agenda.show"
            validator = self.validator("contracts/schemas/people/web-responses.schema.json#/$defs/" + route)
            for state in ("available", "not_requested", "unavailable"):
                response = copy.deepcopy(original)
                result = response["result"]
                views = [result] if command == "schedule" else result["entries"] + result["unplaced_items"]
                for view in views:
                    if state != "available":
                        view["sections"]["people"] = load(FIXTURES / "contracts" / ("section_people_" + state + ".json"))
                with self.subTest(command=command, state=state):
                    validator.validate(response)
                    for view in views:
                        section = view["sections"]["people"]
                        scope = section.pop("scope")
                        self.assertFalse(validator.is_valid(response))
                        section["scope"] = scope

    def test_schema_references_are_local_offline_and_closed(self):
        def walk(value, base):
            if isinstance(value, dict):
                if "$ref" in value:
                    uri, _ = urldefrag(urljoin(base, value["$ref"]))
                    self.assertIn(uri, self.schemas)
                    self.resources.resolver().lookup(urljoin(base, value["$ref"]))
                if value.get("type") == "object" and "properties" in value:
                    if "additionalProperties" in value:
                        self.assertIs(value["additionalProperties"], False)
                    else:
                        # Reused anchor `contains` is a partial assertion, not a wire object.
                        self.assertEqual(set(value["properties"]), {"anchor_role"})
                for child in value.values():
                    walk(child, base)
            elif isinstance(value, list):
                for child in value:
                    walk(child, base)

        for path in self.manifest["schemas"]:
            schema = load(ROOT / path)
            walk(schema, schema["$id"])

    def test_registry_is_source_only_not_runtime_capability(self):
        self.assertFalse(self.contract["runtime_implemented"])
        self.assertFalse(self.contract["runtime_activation"])
        self.assertNotIn(self.contract["contract_version"], IMPLEMENTED_CONTRACT_VERSIONS)
        for row in self.contract["commands"].values():
            self.assertFalse(row["runtime_implemented"])
            versions = row["required_contract_versions"]
            self.assertEqual(versions, sorted(set(versions)))
            self.assertIn(self.contract["contract_version"], versions)
            web_versions = row["http"]["required_contract_versions"]
            self.assertEqual(web_versions, sorted(set(versions) | {self.contract["web_api_contract"]}))
            for key in ("request_schema", "response_schema", "web_request_schema", "web_response_schema"):
                if key in row:
                    path, fragment = urldefrag(row[key])
                    self.assertTrue((ROOT / path).exists())
                    self.resources.resolver().lookup(BASE + path + ("#" + fragment if fragment else ""))
        for command in ("people.list", "item.people.show", "item.people.update"):
            self.assertNotIn(command, COMMAND_RUNTIME_CONTRACT_REGISTRY)
        self.assertEqual(len(self.contract["commands"]), 8)
        self.assertEqual(set(self.contract["runtime_obligations"]), {f"PR-{i:02}" for i in range(1, 17)})
        self.assertEqual({v["status"] for v in self.contract["runtime_obligations"].values()}, {"pending_runtime"})
        self.assertFalse(self.manifest["runtime_verified"])
        self.assertFalse(self.models["runtime_verified"])
        self.assertEqual(len({v["http"]["path"] for v in self.contract["commands"].values()}), 8)
        self.assertIn("spine.item-people-receipt.v1", self.contract["commands"]["item.people.update"]["required_contract_versions"])

    def test_existing_web_bundles_and_schemas_are_not_extended(self):
        for name in self.manifest["schemas"]:
            self.assertFalse((ROOT / "src/spine/contracts/web" / Path(name).relative_to("contracts")).exists())
        for path in (ROOT / "contracts").glob("spine.trusted-web-*-registry.v1.json"):
            value = load(path)
            self.assertNotIn("spine.trusted-web-people.v1", json.dumps(value))
            self.assertNotIn("people.list", {v["command"] for v in value.get("commands", [])})
        create = load(FIXTURES / "contracts/request_schedule_create.json")
        self.assertFalse(self.validator("contracts/schemas/schedule-create-request-v3.schema.json").is_valid(create))
        old = copy.deepcopy(create)
        old["contract_version"] = "spine.schedule-create.v3"
        old.pop("people")
        self.validator("contracts/schemas/schedule-create-request-v3.schema.json").validate(old)
        old_read = load(FIXTURES / "contracts/web_request_schedule.json")
        old_read["contract_version"] = "spine.trusted-web-api.v2"
        self.assertFalse(self.validator("contracts/schemas/trusted-web-read-schedule-request.schema.json").is_valid(old_read))

    def test_pure_set_replacement_witnesses(self):
        for case in self.models["sets"]:
            with self.subTest(case["id"]):
                before = copy.deepcopy(case)
                if "error" in case:
                    with self.assertRaisesRegex(ValueError, "^" + case["error"] + "$"):
                        replacement_model(case)
                else:
                    after, changed = replacement_model(case)
                    self.assertEqual(after, role_facts(case["expected"]))
                    self.assertEqual(changed, case["changed"])
                self.assertEqual(case, before)

    def test_roster_and_selection_policy_witnesses(self):
        for case in self.models["admission"]:
            with self.subTest(case["id"]):
                self.assertEqual(admission_model(case), case["allowed"])
        denied = {c["id"]: c for c in self.models["admission"]}
        for name in ("nonmember_target", "inactive_target", "missing_target", "item_grantee_no_roster"):
            self.assertFalse(admission_model(denied[name]))

    def test_tuple_disclosure_is_not_directory_or_item_access(self):
        for case in self.models["disclosure"]:
            with self.subTest(case["id"]):
                if "error" in case:
                    with self.assertRaisesRegex(ValueError, case["error"]):
                        label_model(case)
                else:
                    self.assertEqual(label_model(case), case["expected"])
        show = load(FIXTURES / "contracts/response_label_not_disclosed.json")
        self.assertEqual(show["people"]["associations"][0]["subject_id"], "subject_lynn")
        self.assertEqual(show["people"]["subjects"][0]["label"], {"availability": "not_disclosed"})
        self.assertLess(int(show["people"]["item_version"]), int(show["current_version"]))

    def test_authorized_current_role_filters_and_hidden_rows(self):
        items = self.models["filter_items"]
        for case in self.models["filters"]:
            with self.subTest(case["id"]):
                self.assertEqual(filter_model(items, case["subject_id"], case["roles"]), case["expected"])
                hidden = {
                    "id": "another_hidden",
                    "authorized": False,
                    "current_version": "1",
                    "roles": [{"version": "1", "subject_id": case["subject_id"], "role": "assignee", "status": "active"}],
                }
                self.assertEqual(filter_model([*items, hidden], case["subject_id"], case["roles"]), case["expected"])
        # Unavailable time does not erase an otherwise matching authorized task.
        self.assertEqual(filter_model(items, "s1", ["assignee"]), ["visible_unplaced_task"])

    def test_edge_specific_policy_bijection_and_mixed_lineage(self):
        cases = {c["id"]: c for c in self.models["continuity"]}
        for case in cases.values():
            with self.subTest(case["id"]):
                self.assertEqual(continuity_model(case), case["valid"])
        self.assertTrue(all(continuity_model(cases[k]) for k in self.models["mixed_lineage_case_ids"]))
        self.assertFalse(continuity_model(cases["facet_cannot_allow_people_delta"]))
        work = self.contract["continuity"]
        for state in self.models["work_states"]:
            self.assertIn(state, work["states"])
        for flag in ("materialize", "cancel", "send", "new_attempt", "durable_proof_table"):
            self.assertFalse(work[flag])
        existing = load(ROOT / "contracts/archetype-facet-integration.v1.json")
        self.assertEqual(set(cases["people_edge"]["before"]["policies"][0]["meaning"]), set(existing["work"]["comparison_policy_fields"]))

    def test_people_continuity_preserves_unmanaged_roles(self):
        baseline = next(row for row in self.models["continuity"] if row["id"] == "people_edge")
        for role in ("owner", "watcher", "recipient"):
            with self.subTest(role=role):
                case = copy.deepcopy(baseline)
                preserved = {"subject_id": "unmanaged_subject", "role": role, "status": "active"}
                case["before"]["roles"].append(preserved)
                case["after"]["roles"].insert(0, copy.deepcopy(preserved))
                self.assertTrue(continuity_model(case))
                case["after"]["roles"][0]["status"] = "inactive"
                self.assertFalse(continuity_model(case))
                case["after"]["roles"].pop(0)
                self.assertFalse(continuity_model(case))

    def test_dry_run_failure_marker_is_true_only_and_not_required(self):
        validator = self.validator("contracts/schemas/people/failures.schema.json#/$defs/local")
        original = load(FIXTURES / "contracts/failure_private_reference.json")
        validator.validate(original)
        validator.validate({**original, "dry_run": True})
        for invalid in (False, None, "true", 1):
            with self.subTest(invalid=invalid):
                self.assertFalse(validator.is_valid({**original, "dry_run": invalid}))

    def test_people_continuity_replaces_only_explicit_role_including_clear(self):
        baseline = next(row for row in self.models["continuity"] if row["id"] == "people_edge")
        for managed, other in (("participant", "assignee"), ("assignee", "participant")):
            for clear in (False, True):
                with self.subTest(managed=managed, clear=clear):
                    case = copy.deepcopy(baseline)
                    case["replacement_role"] = managed
                    for rows in (case["before"]["roles"], case["after"]["roles"], case["requested_roles"]):
                        for row in rows:
                            row["role"] = managed
                    preserved = {"subject_id": "other_role_subject", "role": other, "status": "active"}
                    case["before"]["roles"].append(preserved)
                    if clear:
                        case["requested_roles"] = []
                        case["after"]["roles"] = []
                    case["after"]["roles"].append(copy.deepcopy(preserved))
                    self.assertTrue(continuity_model(case))
                    case["after"]["roles"].pop()
                    self.assertFalse(continuity_model(case))

    def test_v4_mixed_changed_dimensions_follow_declared_order(self):
        order = ["item", "people", "primary_location", "archetype", "scheduled_time",
                 "recurrence", "delivery", "notification_profile", "reminders", "policy_presentations"]
        witness = load(FIXTURES / "changed-dimensions-order.json")
        self.assertEqual(witness["order"], order)
        self.assertEqual(witness["mixed"], [dimension for dimension in order if dimension in witness["mixed"]])
        self.assertEqual(witness["presentation_changed"], ["policy_presentations"])
        self.assertEqual(witness["presentation_noop"], [])
        spec = (ROOT / "specs/people-and-responsibility.md").read_text()
        self.assertIn(", ".join('"' + dimension + '"' for dimension in witness["mixed"]), spec)

    def test_normalization_and_computed_hash_vectors(self):
        witness = load(ROOT / self.manifest["computed_witness"])
        self.assertFalse(witness["runtime_verified"])
        for row in witness["vectors"]:
            with self.subTest(row["id"]):
                self.assertEqual(digest(row["preimage"]), row["sha256"])
                self.assertEqual(canonical_json_bytes(row["preimage"]).decode(), row["canonical_json"])
        query = next(v for v in witness["vectors"] if v["id"] == "roster_query")
        request = load(FIXTURES / "contracts/request_roster.json")
        self.assertEqual(query["preimage"], query_preimage("people.list", request))
        self.assertEqual(query["preimage"], query_preimage("people.list", {**request, "cursor": "different"}))
        self.assertNotEqual(query["sha256"], digest(query_preimage("people.list", {**request, "limit": "10"})))
        request = load(FIXTURES / "contracts/request_assignees.json")
        permuted = copy.deepcopy(request)
        permuted["people"]["assignees"].reverse()
        self.assertEqual(normalize_request("item.people.update", request), normalize_request("item.people.update", permuted))
        self.assertNotEqual(digest({"id": "é"}), digest({"id": "e\u0301"}))
        omitted = normalize_request("item.people.update", {k: v for k, v in request.items() if k != "people"})
        self.assertNotIn("people", omitted)

    def test_cursor_mac_vectors_tampering_and_snapshot_bindings(self):
        witness = load(ROOT / self.manifest["computed_witness"])
        config = load(FIXTURES / "contracts/cursor_config_test_only.json")
        secret = bytes.fromhex(config["secret_hex"])
        for row in witness["cursor_vectors"]:
            self.assertEqual(token_for(row["payload"], secret), row["token"])
            self.validator("contracts/schemas/people/cursor.schema.json").validate(row["payload"])
            modified = {**row["payload"], "source_hash": "f" * 64}
            self.assertNotEqual(token_for(modified, secret), row["token"])
            issued = datetime.fromisoformat(row["payload"]["issued_at_utc"].replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(row["payload"]["expires_at_utc"].replace("Z", "+00:00"))
            self.assertEqual(expiry - issued, timedelta(seconds=900))
            self.assertEqual(issued.tzinfo, UTC)
            self.assertNotEqual(token_for({**row["payload"], "key_generation": "2"}, secret), row["token"])
        bad = load(FIXTURES / "contracts/cursor_protected.json")
        bad["route"] = "schedule.show"
        self.assertFalse(self.validator("contracts/schemas/people/cursor.schema.json").is_valid(bad))
        bad = load(FIXTURES / "contracts/cursor_trusted_local.json")
        bad["account_id"] = "injected"
        self.assertFalse(self.validator("contracts/schemas/people/cursor.schema.json").is_valid(bad))

    def test_fresh_noop_retains_prior_association_identity(self):
        computed = load(ROOT / self.manifest["computed_witness"])
        vectors = {row["id"]: row for row in computed["vectors"]}
        prior = vectors["existing_managed_row_id"]
        request = load(FIXTURES / "contracts/request_participants.json")
        noop = load(FIXTURES / "contracts/response_noop.json")
        self.assertNotEqual(prior["preimage"]["command_id"], request["command_id"])
        self.assertEqual(vectors["new_managed_row_id"]["preimage"]["command_id"], request["command_id"])
        self.assertEqual(noop["command_id"], request["command_id"])
        self.assertEqual(noop["effect"], "item_people_noop")
        self.assertEqual(noop["current_version"], noop["target_version"])
        self.assertFalse(noop["truth_changed"])
        self.assertEqual(prior["preimage"]["request_path"], "/people/participants/0")
        retained_id = "item_subject_role_" + digest(prior["preimage"])
        self.assertEqual(noop["associations"][0], {
            "item_subject_role_id": retained_id,
            "subject_id": request["people"]["participants"][0],
            "role": "participant",
            "status": "active",
        })
        self.assertNotEqual(retained_id, "item_subject_role_" + vectors["new_managed_row_id"]["sha256"])

    def test_success_receipt_equality_and_limits(self):
        computed = load(ROOT / self.manifest["computed_witness"])
        hashes = {v["id"]: v["sha256"] for v in computed["vectors"]}
        for name in ("response_updated", "response_noop", "response_replay", "response_dry_run"):
            value = load(FIXTURES / "contracts" / (name + ".json"))
            self.assertEqual(value["command_receipt_id"], value["receipt"]["command_receipt_id"])
            self.assertFalse(value["work_changed"])
            self.assertEqual(value["receipt"]["semantic_facts_hash"], hashes["update_semantic_facts"])
            if value["effect"] == "item_people_noop":
                self.assertEqual(value["associations"][0]["item_subject_role_id"], "item_subject_role_" + hashes["existing_managed_row_id"])
            else:
                # Changed success, its replay, and changed dry-run use replacement-path IDs.
                self.assertEqual(value["associations"][0]["item_subject_role_id"], "item_subject_role_" + hashes["new_managed_row_id"])
            changed = value["receipt"]["effect"] == "item_people_updated"
            self.assertEqual(int(value["current_version"]), int(value["target_version"]) + int(changed))
            self.assertEqual(value["truth_changed"], changed)
        mismatched = load(FIXTURES / "contracts/response_noop.json")
        mismatched["effect"] = "item_people_updated"
        self.assertFalse(self.validator("contracts/schemas/people/responses.schema.json#/$defs/item.people.update").is_valid(mismatched))
        for bad_id in ("", "x\n", "\ud800"):
            self.assertFalse(self.validator("contracts/schemas/people/types.schema.json#/$defs/id").is_valid(bad_id))
        limits = self.contract["limits"]
        self.assertEqual(
            (limits["total_role_rows_per_item_version"], limits["page_limit_max"], limits["page_limit_default"]), (100, 100, 25)
        )
        self.assertEqual(limits["sqlite_vm_steps"], limits["authorized_core_vm_steps"] + limits["optional_vm_steps"])
        self.assertTrue(limits["strictest_adapter_budget_wins"])


if __name__ == "__main__":
    unittest.main()
