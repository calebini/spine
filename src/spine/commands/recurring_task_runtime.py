"""Internal R2 schema admission, syntax normalization and protected cursors.

Explicitly supplied source contracts are a development boundary, not installed
public capability declarations. Public packaging/registration remains R4.
"""

from __future__ import annotations

import copy
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from spine.core.canonical_json import canonical_json_bytes
from spine.core.recurring_task_runtime import (
    CURSOR as CURSOR,
)
from spine.core.recurring_task_runtime import (
    PREFIX as PREFIX,
)
from spine.core.recurring_task_runtime import (
    _b64 as _b64,
)
from spine.core.recurring_task_runtime import (
    _unb64 as _unb64,
)
from spine.core.recurring_task_runtime import (
    cursor_config as cursor_config,
)
from spine.core.recurring_task_runtime import (
    cursor_payload as cursor_payload,
)
from spine.core.recurring_task_runtime import (
    fail as fail,
)
from spine.core.recurring_task_runtime import (
    instant as instant,
)
from spine.core.recurring_task_runtime import (
    sign_cursor as sign_cursor,
)
from spine.core.recurring_task_runtime import (
    verify_cursor as verify_cursor,
)
from spine.core.recurring_task_runtime import (
    wire as wire,
)
from spine.core.recurring_tasks import CONTRACT
from spine.core.rendering_definitions import normalize_selection

RESPONSE = "spine.recurring-related-tasks-response.v1"
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


def unicode_errors(value: Any, path: tuple[str, ...] = ()) -> list[Any]:
    """Include the canonical string domain in ordinary ordered syntax failures."""
    errors = []
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            errors.append(ValidationError("invalid Unicode string", validator="utf8", path=path))
    elif isinstance(value, dict):
        for key, child in value.items():
            # Do not place a surrogate key in the failure envelope itself.
            if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
                errors.append(ValidationError("invalid Unicode object key", validator="utf8", path=path))
            else:
                errors.extend(unicode_errors(child, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(unicode_errors(child, (*path, str(index))))
    return errors


FORMATS = FormatChecker()


def _datetime(value: Any) -> bool:
    return not isinstance(value, str) or instant(value).tzinfo is not None


FORMATS.checks("date-time", raises=(ValueError, TypeError))(_datetime)


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
            if candidates:
                schema = candidates[0]
            else:
                # An unknown view has no selected branch. Validate common
                # requirements and supplied known fields before ordering errors;
                # do not let the discriminator bypass an earlier root-ID error
                # or invent required fields from an unrelated view.
                branches = schema["oneOf"]
                properties = {key: prop for branch in branches for key, prop in branch["properties"].items()}
                properties["view"] = {"enum": [branch["properties"]["view"]["const"] for branch in branches]}
                required = set.intersection(*(set(branch["required"]) for branch in branches))
                schema = {"type": "object", "properties": properties, "required": sorted(required), "additionalProperties": False}
        if definition is not None:
            schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": uri + "#/$defs/" + definition}
        errors = list(Draft202012Validator(schema, registry=self.registry, format_checker=FORMATS).iter_errors(value))
        errors.extend(unicode_errors(value))
        if not errors:
            return
        if output:
            fail("environment_failure", "response_contract")

        def leaves(error: Any) -> list[Any]:
            if error.context:
                children = error.context
                if error.validator in {"oneOf", "anyOf"} and isinstance(error.instance, dict):
                    for discriminator in ("mode", "kind", "owner_kind", "view", "purpose", "resolution", "revision_resolution"):
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
        def error_path(error: Any) -> list[Any]:
            path = list(error.absolute_path)
            if error.validator == "additionalProperties" and isinstance(error.instance, dict):
                extra = sorted(set(error.instance) - set(error.schema.get("properties", {})))
                if extra:
                    path.append(extra[0])
            if error.validator == "required":
                missing = sorted(
                    set(error.validator_value) - set(error.instance),
                    key=lambda key: (FIELDS.index(key) if not path and key in FIELDS else len(FIELDS), key),
                )
                if missing:
                    path.append(missing[0])
            return path

        def ordering(error: Any) -> tuple[int, tuple[str, ...], bool]:
            path = error_path(error)
            top = FIELDS.index(path[0]) if path and path[0] in FIELDS else len(FIELDS)
            return (top, tuple(str(p) for p in path), error.validator != "additionalProperties")

        error = min(errors, key=ordering)
        path = error_path(error)
        if (
            path[:2] == ["configuration", "task_owner"]
            and isinstance(value["configuration"]["task_owner"], dict)
            and value["configuration"]["task_owner"].get("owner_kind") == "system"
        ):
            fail("invalid_request", "configuration.task_owner.owner_kind")
        if error.validator == "additionalProperties" and isinstance(error.instance, dict):
            fail("unsupported_field", ".".join(map(str, path)))
        fail("invalid_request", ".".join(map(str, path)) or "request")

    def request(self, command: str, request: Any) -> dict[str, Any]:
        entry = self.descriptor["commands"].get(command)
        if entry is None:
            fail("unsupported_command", "command")
        if isinstance(request, dict) and request.get("contract_version") != CONTRACT:
            fail("unsupported_contract_version", "contract_version")
        self.validate(entry["request_schema"].rsplit("/", 1)[1].removesuffix(".schema.json"), request)
        result: dict[str, Any] = copy.deepcopy(request)
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
