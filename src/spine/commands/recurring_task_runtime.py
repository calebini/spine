"""Internal R2 schema admission, syntax normalization and protected cursors.

Explicitly supplied source contracts are a development boundary, not installed
public capability declarations. Public packaging/registration remains R4.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from spine.core.recurring_tasks import CANONICAL, CONTRACT, decode
from spine.core.rendering_definitions import normalize_selection

CURSOR = "spine.recurring-related-tasks.cursor.v1"
RESPONSE = "spine.recurring-related-tasks-response.v1"
PREFIX = "schedule.related_task_rule."
DEFAULTS = {
    "source_candidates": (256, 2048),
    "assignments": (32, 128),
    "mutations": (32, 128),
    "proof_steps": (10000, 50000),
    "lineage_hops": (64, 256),
    "work_rows": (128, 4096),
    "response_bytes": (262144, 1048576),
}
FIELDS = [
    "contract_version",
    "command_id",
    "actor_subject_id",
    "requested_at_utc",
    "owner",
    "rule_key",
    "source",
    "enrollment",
    "related_task_rule_id",
    "expected",
    "configuration",
    "adoption_scope",
    "disposition",
    "assignment_id",
    "target_generation_id",
    "target_task_item_id",
    "limits",
    "view",
    "proof_id",
    "source_item_id",
    "status",
    "limit",
    "cursor",
]


def fail(code: str, field: str, message: str = "recurring-task request could not complete") -> NoReturn:
    raise SpineValidationError(code + ":" + field, message)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def wire(value: datetime) -> str:
    if value.tzinfo is None:
        fail("environment_failure", "clock")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def _datetime(value: Any) -> bool:
    return not isinstance(value, str) or instant(value).tzinfo is not None


class RecurringTaskContracts:
    """Offline-only exact document registry, injected by internal callers."""

    def __init__(self, documents: dict[str, dict[str, Any]], descriptor: dict[str, Any]) -> None:
        self.documents, self.descriptor = copy.deepcopy(documents), copy.deepcopy(descriptor)
        self.registry = Registry().with_resources((v["$id"], Resource.from_contents(v)) for v in self.documents.values())
        self.base = "https://cortext.local/spine/contracts/schemas/recurring-related-tasks/"
        self.by_id = {v["$id"]: v for v in self.documents.values()}
        if descriptor.get("contract_version") != CONTRACT or len(self.by_id) != len(documents):
            fail("environment_failure", "contract_version")

    def validate(self, resource: str, value: Any, *, definition: str | None = None, output: bool = False) -> None:
        uri = self.base + resource + ".schema.json"
        schema = self.by_id.get(uri)
        if schema is None:
            fail("environment_failure", "contract_version")
        if resource == "show-request" and isinstance(value, dict):
            view = value.get("view", "rule")
            candidates = [branch for branch in schema["oneOf"] if branch["properties"]["view"]["const"] == view]
            if not candidates:
                fail("invalid_request", "view")
            schema = candidates[0]
        if definition is not None:
            schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": uri + "#/$defs/" + definition}
        errors = list(Draft202012Validator(schema, registry=self.registry, format_checker=FORMATS).iter_errors(value))
        if not errors:
            return
        if output:
            fail("environment_failure", "response_contract")

        def leaves(error):
            if error.context:
                children = error.context
                if error.validator in {"oneOf", "anyOf"} and isinstance(error.instance, dict):
                    for discriminator in ("mode", "kind", "owner_kind", "view", "purpose", "resolution"):
                        matching = [
                            index
                            for index, branch in enumerate(error.schema[error.validator])
                            if discriminator in branch.get("properties", {})
                            and branch["properties"][discriminator].get("const") == error.instance.get(discriminator)
                        ]
                        if len(matching) == 1:
                            children = [child for child in children if child.schema_path[0] == matching[0]]
                            break
                return [leaf for child in children for leaf in leaves(child)]
            return [error]

        # Select the intended discriminated branch, not unrelated union branches.
        errors = [leaf for error in errors for leaf in leaves(error)]
        errors = [e for e in errors if e.validator != "const"] or errors

        def ordering(error):
            path = list(error.absolute_path)
            top = FIELDS.index(path[0]) if path and path[0] in FIELDS else len(FIELDS)
            return (top, -len(path), tuple(str(p) for p in path), error.validator != "additionalProperties")

        error = min(errors, key=ordering)
        path = list(error.absolute_path)
        if (
            path[:2] == ["configuration", "task_owner"]
            and isinstance(value["configuration"]["task_owner"], dict)
            and value["configuration"]["task_owner"].get("owner_kind") == "system"
        ):
            fail("invalid_request", "configuration.task_owner.owner_kind")
        if error.validator == "additionalProperties" and isinstance(error.instance, dict):
            extra = sorted(set(error.instance) - set(error.schema.get("properties", {})))
            if extra:
                path.append(extra[0])
                fail("unsupported_field", ".".join(map(str, path)))
        if error.validator == "required":
            missing = sorted(set(error.validator_value) - set(error.instance))
            if missing:
                path.append(missing[0])
        fail("invalid_request", ".".join(map(str, path)) or "request")

    def request(self, command: str, request: Any) -> dict[str, Any]:
        entry = self.descriptor["commands"].get(command)
        if entry is None:
            fail("unsupported_command", "command")
        if isinstance(request, dict) and request.get("contract_version") != CONTRACT:
            fail("unsupported_contract_version", "contract_version")
        self.validate(entry["request_schema"].rsplit("/", 1)[1].removesuffix(".schema.json"), request)
        result = copy.deepcopy(request)
        canonical_json_bytes(result)
        if command.endswith("create"):
            result["configuration"].setdefault("generation_horizon_seconds", "4838400")
        if "configuration" in result:
            config = result["configuration"]
            config["task_template"]["people"]["assignees"] = sorted(set(config["task_template"]["people"]["assignees"]))
            plan = config["notification_plan"]
            if plan is not None:
                fields = [("custom_additions", "policy_key")]
                if plan["mode"] != "none":
                    fields.append(("replacements", "template_key"))
                for field, key in fields:
                    plan.setdefault(field, [])
                    plan[field].sort(key=lambda v: v[key])
                    for entry in plan[field]:
                        schedule = entry["schedule"]
                        if schedule["kind"] == "offsets":
                            unique = {canonical_json_bytes(v): v for v in schedule["at"]}
                            schedule["at"] = [unique[key] for key in sorted(unique)]
                if plan["mode"] != "none":
                    plan.setdefault("suppress_template_keys", [])
                    plan["suppress_template_keys"].sort()
                plan.setdefault("rendering_applications", [])
                for application in plan["rendering_applications"]:
                    application["selection"] = normalize_selection(application["selection"])
                plan["rendering_applications"].sort(key=lambda v: (v["source_kind"], v["source_key"]))
                if plan["mode"] == "archetype_default":
                    plan.setdefault("on_no_match", "fail")
        if command.endswith("reconcile"):
            result["limits"] = {key: result["limits"].get(key, str(bounds[0])) for key, bounds in DEFAULTS.items()}
        if command.endswith("list"):
            result.setdefault("status", "active")
            result.setdefault("limit", "50")
        if command.endswith("show"):
            result.setdefault("view", "rule")
            if result["view"] in {"assignments", "generations", "states"}:
                result.setdefault("limit", "50")
        return result

    def response(self, command: str, value: dict[str, Any]) -> None:
        entry = self.descriptor["commands"][command]
        resource = entry["response_schema" if value["ok"] else "failure_schema"].rsplit("/", 1)[1].removesuffix(".schema.json")
        self.validate(resource, value, output=True)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _b64(raw) != value:
        raise ValueError("noncanonical base64url")
    return raw


def cursor_config(config: Any, ledger_id: str) -> None:
    if (
        config is None
        or not isinstance(getattr(config, "secret", None), bytes)
        or len(config.secret) < 32
        or getattr(config, "ledger_id", None) != ledger_id
        or not isinstance(getattr(config, "generation", None), str)
        or not config.generation
    ):
        fail("environment_failure", "cursor_configuration")


def sign_cursor(config: Any, payload: dict[str, Any], contracts: RecurringTaskContracts) -> str:
    cursor_config(config, payload["query"]["ledger_instance_id"])
    contracts.validate("cursor", payload, output=True)
    raw = canonical_json_bytes(payload)
    tag = hmac.new(config.secret, CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()
    return _b64(raw) + "." + _b64(tag)


def verify_cursor(
    config: Any, token: str, query: dict[str, Any], purpose: str, now: str, catalog: str, contracts: RecurringTaskContracts
) -> dict[str, Any]:
    cursor_config(config, query["ledger_instance_id"])
    try:
        body, tag = token.split(".")
        raw, mac = _unb64(body), _unb64(tag)
        if not hmac.compare_digest(mac, hmac.new(config.secret, CURSOR.encode() + b"\0" + raw, hashlib.sha256).digest()):
            raise ValueError("signature")
        payload = decode(raw.decode("utf-8"))
        contracts.validate("cursor", payload)
        if payload["key_id"] != config.generation or payload["purpose"] != purpose or payload["query"] != query:
            raise ValueError("binding")
        if instant(payload["expires_at_utc"]) != instant(payload["issued_at_utc"]) + timedelta(seconds=3600):
            raise ValueError("lifetime")
    except (ValueError, UnicodeError, SpineValidationError, KeyError, TypeError) as exc:
        raise SpineValidationError("invalid_request:cursor", "invalid recurring-task cursor") from exc
    if payload["catalog_generation"] != catalog or instant(now) >= instant(payload["expires_at_utc"]):
        fail("stale_cursor", "cursor")
    return payload


def cursor_payload(config: Any, *, purpose: str, query: dict[str, Any], catalog: str, now: str, after: Any) -> dict[str, Any]:
    cursor_config(config, query["ledger_instance_id"])
    return {
        "cursor_version": CURSOR,
        "canonical_json_version": CANONICAL,
        "key_id": config.generation,
        "purpose": purpose,
        "query": query,
        "catalog_generation": catalog,
        "issued_at_utc": now,
        "expires_at_utc": wire(instant(now) + timedelta(seconds=3600)),
        "after": after,
    }
