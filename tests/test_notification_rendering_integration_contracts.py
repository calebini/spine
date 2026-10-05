"""Successor wire and computed reference proofs; no implementation/SQL conformance claim."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine import IMPLEMENTED_CONTRACT_VERSIONS
from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text
from spine.core.notification_profiles import normalize_profile_revision
from tests.rendering_integration_reference import build, normalized_v2_revision, reference_suffix

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/notification_rendering_integration"
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=ValueError)
def utc_date(value):
    if isinstance(value, str):
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return True


def load(path):
    return json.loads(path.read_text())


def sha(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def preimage(domain, **facts):
    return {"derivation_version": domain, "canonical_json_version": "spine.canonical-json.v1", **facts}


def instant(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def reference_cursor_accepts(case, token=None, *, now="2026-10-04T12:01:00Z", **changes):
    """Pure cryptographic/fence oracle only; no DB reads or permission resolution."""
    expected = copy.deepcopy(case)
    expected.update(changes)
    config = expected["config"]
    try:
        wire = token or case["token"]
        if len(wire.encode("ascii")) > 4096:
            return False
        prefix, key_id, encoded, tag = wire.split(".")
        if prefix != "nrc1" or key_id != config["key_id"]:
            return False

        def decode(part):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
                raise ValueError("noncanonical base64url")
            raw = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
            if base64.urlsafe_b64encode(raw).decode().rstrip("=") != part:
                raise ValueError("noncanonical base64url")
            return raw

        raw, mac = decode(encoded), decode(tag)
        message = b"spine.notification-rendering-cursor.v1\0" + key_id.encode() + b"\0" + raw
        wanted = hmac.digest(bytes.fromhex(config["secret_hex"]), message, "sha256")
        if not hmac.compare_digest(mac, wanted):
            return False
        payload = json.loads(raw)
        if canonical_json_bytes(payload) != raw:
            return False
        if payload != expected["payload"]:
            return False
        if payload["ledger_instance_id"] != config["ledger_instance_id"] or payload["key_generation"] != config["key_generation"]:
            return False
        for key in ("query", "context", "access"):
            if payload[key + "_hash"] != sha(preimage("spine.rendering-cursor-" + key + ".v1", **{key: expected[key]})):
                return False
        access = expected["access"]
        if payload["access_epoch"] != access["access_epoch"] or payload["access_valid_until_utc"] != access["valid_until_utc"]:
            return False
        issued, expires, current = map(instant, (payload["issued_at_utc"], payload["expires_at_utc"], now))
        if not issued <= current < expires <= issued + timedelta(seconds=900):
            return False
        if access["valid_until_utc"] is not None and expires > instant(access["valid_until_utc"]):
            return False
        if expected["context"]["mode"] == "trusted_local" and access != {"access_epoch": None, "valid_until_utc": None}:
            return False
        for field in ("catalog_generation", "access_epoch"):
            if payload[field] is not None and not 1 <= int(payload[field]) <= 2**63 - 1:
                return False
        return True
    except (ValueError, KeyError, TypeError, UnicodeError):
        return False


class RenderingIntegrationContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {p.name: load(p) for p in (ROOT / "contracts/schemas").glob("*.schema.json")}
        cls.resources = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in cls.schemas.values())
        cls.manifest = load(ROOT / "contracts/notification-rendering-integration-fixture-manifest.json")
        cls.registry = load(ROOT / cls.manifest["registry"])
        cls.vectors = load(ROOT / cls.manifest["computed_vectors"])

    def validator(self, name, fragment="#"):
        return Draft202012Validator({"$ref": self.schemas[name]["$id"] + fragment}, registry=self.resources, format_checker=FORMATS)

    def test_schemas_and_all_positive_negative_wire_fixtures(self):
        for path in self.registry["schemas"]:
            Draft202012Validator.check_schema(load(ROOT / path))
        for case in self.manifest["fixtures"]:
            with self.subTest(case=case["fixture_id"]):
                errors = list(self.validator(Path(case["schema"]).name, case["schema_ref"]).iter_errors(load(ROOT / case["fixture"])))
                self.assertEqual(not errors, case["valid"], [e.message for e in errors])

    def test_reference_fixture_regeneration_is_exact(self):
        for path, expected in build().items():
            with self.subTest(path=path):
                self.assertEqual(load(ROOT / path), expected)

    def test_catalog_and_show_success_dry_run_markers(self):
        for command in ("create", "revise", "show", "list"):
            response = load(FIXTURES / ("response_profile_" + command + ".json"))
            validator = self.validator("notification-profile-responses-v2.schema.json", "#/$defs/" + command)
            self.assertTrue(validator.is_valid({**response, "dry_run": True}))
            self.assertFalse(validator.is_valid({**response, "dry_run": False}))
        for fixture, schema in (
            ("response_schedule_show", "schedule-show-response-v2"),
            ("response_schedule_create", "schedule-create-response-v3"),
            ("response_presentation_edit", "schedule-update-response-v3"),
        ):
            response = load(FIXTURES / (fixture + ".json"))
            validator = self.validator(schema + ".schema.json")
            self.assertTrue(validator.is_valid({**response, "dry_run": True}))
            self.assertFalse(validator.is_valid({**response, "dry_run": False}))

    def test_profile_list_request_response_boundary_agreement(self):
        request = load(FIXTURES / "request_profile_list_101.json")
        response = load(FIXTURES / "response_profile_list.json")
        profile = response["entries"][0]
        for limit in (100, 101, 500, 501):
            with self.subTest(limit=limit):
                # Construct a page fixture with distinct stable root keys, not 101
                # copies of one record. Pagination/catalog fencing remains pending.
                entries = []
                for i in range(limit):
                    entry = copy.deepcopy(profile)
                    entry.update(notification_profile_id=f"profile-{i:03}", profile_key=f"profile_{i:03}")
                    entries.append(entry)
                page = {**response, "entries": entries, "count": str(limit)}
                self.assertEqual(
                    self.validator("notification-profile-commands-v2.schema.json", "#/$defs/profileList").is_valid(
                        {**request, "limit": str(limit)}
                    ),
                    limit <= 500,
                )
                self.assertEqual(
                    self.validator("notification-profile-responses-v2.schema.json", "#/$defs/list").is_valid(page), limit <= 500
                )

    def test_schedule_create_failures_match_shared_envelope(self):
        response = load(FIXTURES / "failure_schedule_create_permission_denied.json")
        shared = self.validator("notification-rendering-integration-failure.schema.json")
        create = self.validator("schedule-create-response-v3.schema.json")
        codes = self.schemas["notification-rendering-integration-failure.schema.json"]["properties"]["error"]["properties"]["code"]["enum"]
        for code in [*codes, "unknown_failure"]:
            for marker in ({}, {"dry_run": True}, {"dry_run": False}):
                candidate = {**response, **marker, "error": {**response["error"], "code": code}}
                self.assertEqual(create.is_valid(candidate), shared.is_valid(candidate))
        self.assertFalse(create.is_valid({**response, "command": "schedule.update"}))

    def test_application_and_readback_preserve_resolution_and_overlays(self):
        application = load(FIXTURES / "application_archetype_default_overlays.json")
        readback = load(FIXTURES / "readback_archetype_default_overlays.json")
        revision = load(FIXTURES / "response_profile_overlay_revision.json")["notification_profile"]["revision"]
        self.assertEqual(application, readback["application"])
        self.assertEqual(application["normalized_profile_revision_hash"], revision["normalized_revision_hash"])
        self.assertEqual(
            revision["normalized_revision_hash"], sha(preimage("spine.notification-profile-revision-hash.v2", revision=revision["content"]))
        )
        self.assertEqual(
            application["scope_chain"], [{"owner_kind": "subject", "owner_subject_id": "subject_owner"}, {"owner_kind": "system"}]
        )
        self.assertEqual(application["notification_profile_binding_id"], "binding-example")
        self.assertEqual(application["suppress_template_keys"], ["suppressed"])
        self.assertEqual(application["replacements"][0]["template_key"], "day_before")
        self.assertEqual(application["replacements"][0]["schedule"]["at"]["offset_seconds"], "-3600")
        self.assertEqual(application["custom_additions"][0]["policy_key"], "custom")
        self.assertEqual(
            {(p["policy_origin"], p["source_key"]) for p in application["policies"]},
            {("profile_replacement", "day_before"), ("custom_addition", "custom")},
        )
        validator = self.validator("notification-profile-application-v2.schema.json")
        for field in ("scope_chain", "normalized_profile_revision_hash", "suppress_template_keys", "replacements", "custom_additions"):
            bad = {k: v for k, v in application.items() if k != field}
            self.assertFalse(validator.is_valid(bad), field)
            self.assertFalse(
                self.validator("notification-profile-readback-v2.schema.json").is_valid({**readback, "application": bad}), field
            )
        self.assertFalse(validator.is_valid({**application, "scope_chain": []}))
        self.assertFalse(validator.is_valid({**application, "notification_profile_binding_id": None}))
        historical = load(FIXTURES / "response_profile_historical_v1.json")["notification_profile"]["revision"]
        # The v2 projection accepts the original v1 digest; it does not rehash it.
        self.assertTrue(validator.is_valid({**application, "normalized_profile_revision_hash": historical["normalized_revision_hash"]}))

    def test_overlay_revision_has_distinct_ordinary_policy_semantics(self):
        content = load(FIXTURES / "response_profile_overlay_revision.json")["notification_profile"]["revision"]["content"]
        # Rendering and derived hashes do not distinguish ordinary policies.
        ordinary = {
            "compatible_item_types": content["compatible_item_types"],
            "templates": [{k: t[k] for k in ("template_key", "schedule", "late_handling")} for t in content["templates"]],
        }
        normalized = normalize_profile_revision(ordinary)
        semantics = [canonical_json_text({k: t[k] for k in ("schedule", "late_handling")}) for t in normalized.templates]
        self.assertEqual(len(semantics), len(set(semantics)))
        self.assertEqual(
            {t["template_key"]: t["schedule"]["at"]["offset_seconds"] for t in normalized.templates},
            {"day_before": "-86400", "suppressed": "-172800"},
        )
        duplicate = copy.deepcopy(ordinary)
        duplicate["templates"][1]["schedule"] = copy.deepcopy(duplicate["templates"][0]["schedule"])
        duplicate["templates"][1]["late_handling"] = copy.deepcopy(duplicate["templates"][0]["late_handling"])
        with self.assertRaisesRegex(SpineValidationError, "duplicate"):
            normalize_profile_revision(duplicate)

    def test_every_preimage_canonical_bytes_and_digest(self):
        names = set()
        for vector in self.vectors["hashes"]:
            with self.subTest(case=vector["case_id"]):
                self.assertNotIn(vector["case_id"], names)
                names.add(vector["case_id"])
                self.assertEqual(canonical_json_text(vector["preimage"]), vector["canonical_json"])
                self.assertEqual(sha(vector["preimage"]), vector["sha256"])

    def test_profile_and_application_hashes_are_linked_to_wire_values(self):
        profile = load(FIXTURES / "response_profile_show.json")["notification_profile"]["revision"]
        for template in profile["content"]["templates"]:
            bare = {k: v for k, v in template.items() if k != "normalized_template_hash"}
            self.assertEqual(
                template["normalized_template_hash"], sha(preimage("spine.notification-profile-template-hash.v2", template=bare))
            )
        self.assertEqual(
            profile["normalized_revision_hash"], sha(preimage("spine.notification-profile-revision-hash.v2", revision=profile["content"]))
        )
        application = load(FIXTURES / "application_v2.json")
        entries = []
        for policy in application["policies"]:
            self.assertEqual(
                policy["presentation_hash"],
                sha(preimage("spine.notification-policy-presentation-hash.v1", presentation=policy["presentation"])),
            )
            entries.append({k: policy[k] for k in ("notification_policy_id", "presentation_hash")})
        self.assertEqual(entries, sorted(entries, key=lambda e: e["notification_policy_id"]))
        self.assertEqual(
            application["effective_presentation_set_hash"], sha(preimage("spine.notification-presentation-set-hash.v1", entries=entries))
        )
        empty = load(FIXTURES / "readback_no_profile.json")
        self.assertIsNone(empty["application"])
        self.assertFalse(empty["upgrade_available"] or empty["effective_policy_diverged"])
        self.assertIsNone(empty["pinned_notification_profile_revision_id"])
        self.assertIsNone(empty["current_notification_profile_revision_id"])

    def test_normalization_omission_and_semantic_address_uniqueness(self):
        omitted = load(FIXTURES / "request_profile_ordinary_omitted.json")["revision"]
        explicit = copy.deepcopy(omitted)
        explicit["templates"][0]["rendering"] = {"kind": "ordinary"}
        self.assertEqual(normalized_v2_revision(omitted), normalized_v2_revision(explicit))
        historical = load(FIXTURES / "response_profile_historical_v1.json")["notification_profile"]["revision"]
        content = historical["content"]
        self.assertEqual(historical["normalized_revision_hash"], sha({"contract_version": "spine.notification-profiles.v1", **content}))
        self.assertTrue(all("rendering" not in value for value in content["templates"]))
        request = load(FIXTURES / "request_schedule_create_ordinary.json")
        applications = request["notification_plan"]["rendering_applications"]
        addresses = [(a["source_kind"], a["source_key"]) for a in applications]
        self.assertEqual(addresses, sorted(set(addresses)))
        duplicate = copy.deepcopy(request)
        duplicate["notification_plan"]["rendering_applications"] *= 2
        self.assertTrue(self.validator("schedule-create-request-v3.schema.json").is_valid(duplicate))
        repeated = [(a["source_kind"], a["source_key"]) for a in duplicate["notification_plan"]["rendering_applications"]]
        self.assertNotEqual(len(repeated), len(set(repeated)))  # Semantic rejection, not JSON-Schema equality.

    def test_nested_attempt_evidence_and_fallback_preserve_base(self):
        ordinary = load(FIXTURES / "ordinary_v1.json")
        identities = set()
        for kind in ("included", "revoked", "empty_subset", "overflow"):
            with self.subTest(kind=kind):
                envelope = load(FIXTURES / ("rendering_" + kind + ".json"))
                base, details = envelope["base_rendering"], envelope["details"]
                self.assertEqual(base, load(FIXTURES / "ordinary_overflow_base_v1.json") if kind == "overflow" else ordinary)
                self.assertEqual(details["attempt_id"], base["attempt_id"])
                self.assertEqual(details["rendered_item_version"], base["rendered_item_version"])
                self.assertEqual(details["base_rendering_input_hash"], base["rendering_input_hash"])
                self.assertEqual(details["base_rendered_content_hash"], base["rendered_content_hash"])
                facts = {k: v for k, v in details.items() if k not in ("input_hash", "content_hash", "body_text")}
                self.assertEqual(details["input_hash"], sha({**facts, "canonical_json_version": "spine.canonical-json.v1"}))
                self.assertEqual(
                    details["content_hash"],
                    sha(
                        {
                            "contract_version": details["contract_version"],
                            "canonical_json_version": "spine.canonical-json.v1",
                            "body_text": details["body_text"],
                        }
                    ),
                )
                ih = sha(
                    preimage(
                        "spine.notification-rendering-input-hash.v2",
                        base_rendering_input_hash=base["rendering_input_hash"],
                        details_input_hash=details["input_hash"],
                    )
                )
                ch = sha(preimage("spine.notification-rendering-content-hash.v2", rendering_input_hash=ih, body_text=details["body_text"]))
                self.assertEqual(envelope["rendering_input_hash"], ih)
                self.assertEqual(envelope["rendered_content_hash"], ch)
                self.assertEqual(envelope["body_text"], details["body_text"])
                identity = "notification_rendering_" + sha(
                    preimage(
                        "spine.notification-rendering-id.v2",
                        attempt_id=base["attempt_id"],
                        rendering_input_hash=ih,
                        rendered_content_hash=ch,
                    )
                )
                self.assertEqual(envelope["notification_rendering_id"], identity)
                identities.add(identity)
                self.assertLessEqual(len(canonical_json_bytes(envelope)), 32768)
                self.assertLessEqual(len(canonical_json_bytes(details)), 16384)
                if kind != "included":
                    self.assertEqual(envelope["body_text"], base["body_text"])
                    self.assertTrue(all(set(v) == {"selection_key", "outcome"} for v in details["selections"]))
        self.assertEqual(len(identities), 4)
        overflow = self.vectors["overflow_reference"]
        candidates = overflow["candidate_selections"]
        suffix = "".join(f" · {s['label']}: {s['value']}" for s in candidates if s["outcome"] == "included")
        self.assertEqual(overflow["candidate_suffix"], suffix)
        self.assertTrue(all(0 < len(s["value"]) <= 120 and 0 < len(s["label"]) <= 40 for s in candidates))
        result = reference_suffix(overflow["base_body"], candidates)
        evidence = load(FIXTURES / "rendering_overflow.json")["details"]
        for field in ("selections", "outcome", "body_text"):
            self.assertEqual(result[field], evidence[field])
        self.assertEqual(overflow["outcome"], result["outcome"])
        self.assertEqual(evidence["selections"], [{"selection_key": s["selection_key"], "outcome": "suffix_overflow"} for s in candidates])
        short = [{**s, "value": "X"} for s in candidates]
        self.assertEqual(reference_suffix(overflow["base_body"], short)["outcome"], "details_included")
        omitted = {"selection_key": "optional", "outcome": "not_selected"}
        self.assertEqual(reference_suffix(overflow["base_body"], [*candidates, omitted])["selections"][-1], omitted)
        self.assertEqual(overflow["candidate_scalars"], len(overflow["base_body"] + overflow["candidate_suffix"]))
        self.assertGreater(overflow["candidate_scalars"], 1024)
        self.assertLessEqual(len(overflow["base_body"]), 1024)

    def test_cursor_mac_bytes_and_all_bound_facts(self):
        for case in self.vectors["cursors"]:
            with self.subTest(mode=case["case_id"]):
                signed = (
                    b"spine.notification-rendering-cursor.v1\0"
                    + case["config"]["key_id"].encode()
                    + b"\0"
                    + canonical_json_bytes(case["payload"])
                )
                self.assertEqual(signed.hex(), case["signed_bytes_hex"])
                self.assertEqual(hmac.digest(bytes.fromhex(case["config"]["secret_hex"]), signed, "sha256").hex(), case["mac_hex"])
                self.assertEqual(case["canonical_payload"], canonical_json_text(case["payload"]))
                self.assertTrue(reference_cursor_accepts(case))
                self.assertFalse(reference_cursor_accepts(case, now=case["payload"]["expires_at_utc"]))
                self.assertFalse(reference_cursor_accepts(case, now="2026-10-04T11:59:59Z"))
                for field, value in (("limit", "11"), ("status", "retired"), ("owner", {"owner_kind": "system"})):
                    self.assertFalse(reference_cursor_accepts(case, query={**case["query"], field: value}))
                for field in ("ledger_instance_id", "key_generation", "command", "catalog_generation", "last_id", "access_epoch"):
                    self.assertFalse(reference_cursor_accepts(case, payload={**case["payload"], field: "changed"}))
                self.assertFalse(reference_cursor_accepts(case, context={**case["context"], "audience": "another-context"}))
                self.assertFalse(reference_cursor_accepts(case, access={**case["access"], "access_epoch": "99"}))
                self.assertFalse(reference_cursor_accepts(case, config={**case["config"], "key_generation": "rotated"}))
                self.assertFalse(reference_cursor_accepts(case, config={**case["config"], "secret_hex": "ff" * 32}))
                self.assertFalse(reference_cursor_accepts(case, token=case["token"] + "="))
                damaged = case["token"][:-1] + ("A" if case["token"][-1] != "A" else "B")
                self.assertFalse(reference_cursor_accepts(case, token=damaged))

    def test_authoring_bounds_and_old_schemas_remain_closed(self):
        request = load(FIXTURES / "request_presentation_edit.json")
        validator = self.validator("schedule-update-request-v3.schema.json")
        for edits in ([], request["patch"]["policy_presentations"] * 33):
            bad = copy.deepcopy(request)
            bad["patch"]["policy_presentations"] = edits
            self.assertFalse(validator.is_valid(bad))
        bad = copy.deepcopy(request)
        bad["materialization"] = load(ROOT / "tests/fixtures/schedule_create/contracts/request_event_repeat_window_materialized.json")[
            "materialization"
        ]
        self.assertFalse(validator.is_valid(bad))
        bad = {**request, "contract_version": "spine.schedule-update.v2"}
        self.assertFalse(self.validator("schedule-update-request.schema.json").is_valid(bad))
        profile = load(FIXTURES / "request_profile_create.json")
        profile["contract_version"] = "spine.notification-profiles.v1"
        self.assertFalse(self.validator("notification-profile-commands.schema.json", "#/$defs/profileCreate").is_valid(profile))
        for field in ("key_id", "key_generation", "secret_hex"):
            config = load(FIXTURES / "cursor_config_test_only.json")
            for suffix in ("\n", "\r\n", " "):
                self.assertFalse(
                    self.validator("notification-rendering-cursor-config.schema.json").is_valid({**config, field: config[field] + suffix})
                )

    def test_registry_references_nonactivation_and_pending_stateful_proofs(self):
        self.assertEqual(self.registry["status"], "specified_not_implemented")
        self.assertFalse(self.registry["runtime_activation"])
        for entry in self.registry["commands"].values():
            self.assertNotIn(entry["contract_version"], IMPLEMENTED_CONTRACT_VERSIONS)
            for field in ("request_schema", "response_schema"):
                path, _, fragment = entry[field].partition("#")
                schema = load(ROOT / path)
                for part in fragment.strip("/").split("/") if fragment else []:
                    schema = schema[part]
                self.assertIsInstance(schema, dict)
        for path in self.registry["schemas"]:
            schema = load(ROOT / path)
            pending = [schema]
            resolver = self.resources.resolver(base_uri=schema["$id"])
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    if "$ref" in value:
                        self.assertIsInstance(resolver.lookup(value["$ref"]).contents, dict)
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
            self.assertFalse((ROOT / "src/spine/contracts/web/schemas" / Path(path).name).exists())
        obligations = load(ROOT / self.manifest["stateful_obligations"])
        self.assertFalse(obligations["runtime_verified"])
        self.assertEqual({v["family"] for v in obligations["families"]}, {f"RI-{n:02}" for n in range(1, 15)})
        self.assertTrue(all(v["status"] == "pending_runtime" for v in obligations["families"]))


if __name__ == "__main__":
    unittest.main()
