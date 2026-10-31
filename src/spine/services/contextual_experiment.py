"""Opt-in synthetic event export and capture. Never selects or sends notifications."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from importlib.resources import files

from jsonschema import Draft202012Validator, ValidationError

from spine.adapters.contextual_experiment import digest, dump, require

INTERFACE = "contextual-notification-experiment"
VERSION = "impetus.local.v1"
OBJECTIVE = (
    "Make this reminder more helpful or more personable. Add a brief relevant line "
    "when worthwhile; avoid repetition, invented facts and inferred preferences. "
    "Use optional read-only tools only when useful. No addition is fine."
)
SCHEMA = json.loads(files("spine.contracts").joinpath("contextual_notification/local-v1.schema.json").read_text())


def instant(text):
    require(isinstance(text, str) and text.endswith("Z"), "utc")
    return datetime.fromisoformat(text[:-1] + "+00:00")


def utc(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Experiment:
    def __init__(self, source, store, client, config):
        self.source, self.store, self.client = source, store, client
        # Trusted operator config, not model-selected policy. Pin a value copy.
        self.config = json.loads(dump(config))
        require(self.config["synthetic_only"] is True, "synthetic_only")
        require(1 <= self.config["lead_seconds"] <= 300, "lead_seconds")
        require(set(self.config["allowed_tools"]) <= {"fixture.lookup.v1"}, "tools")

    def export(self, work_instance_id, now_utc):
        existing = self.store.for_work(work_instance_id)
        if existing:
            return existing  # resolve before recapture, even if source/config changed
        snapshot = self.source.snapshot(work_instance_id, self.config)
        opportunity = snapshot["opportunity"]
        existing = self.store.get(opportunity)
        if existing:
            return opportunity, existing
        context = snapshot["context"]
        eligible = instant(context["notification"]["eligible_at_utc"])
        now = instant(now_utc)
        require(eligible - timedelta(seconds=self.config["lead_seconds"]) <= now < eligible - timedelta(seconds=1), "outside_export_window")
        seconds = (instant(context["event"]["starts_at_utc"]) - eligible).total_seconds()
        require(seconds.is_integer(), "relative_time")
        context["notification"]["seconds_before_event"] = int(seconds)
        work_id = "experiment:" + digest(
            {"version": "spine.experiment-work.v1", "ledger": self.source.namespace, "opportunity": opportunity}
        )
        request = dict(
            interface=INTERFACE,
            version=VERSION,
            work_id=work_id,
            source_refs=dict(
                ledger_instance_id=self.source.namespace,
                item_id=snapshot["item_id"],
                item_version=snapshot["item_version"],
                notification_opportunity_id=opportunity,
                notification_policy_id=snapshot["policy"],
                rendering_definition_revision="sha256:" + snapshot["rendering_hash"],
                experiment_definition_revision=self.config["definition_revision"],
                disclosure_revision=self.config["disclosure_revision"],
            ),
            captured_at_utc=now_utc,
            context=context,
            objective=OBJECTIVE,
            allowed_tools=self.config["allowed_tools"],
            limits=dict(model_calls=2, tool_calls=1, elapsed_seconds=30, addendum_utf8_bytes=512),
            selection_cutoff_utc=utc(eligible),
            request_expires_at_utc=utc(eligible),
        )
        Draft202012Validator(SCHEMA["$defs"]["request"]).validate(request)
        # The exporter chooses these bytes once. The digest is over them, not a
        # reserialization by the adapter or worker. Retain before subprocess entry.
        raw = dump(request) + b"\n"
        require(len(raw) <= 65536, "request_size")
        # seconds_before_event was added to context above; fresh reads must match it.
        fingerprint = self.fingerprint(snapshot)
        return opportunity, self.store.put(opportunity, work_instance_id, raw, fingerprint)

    @staticmethod
    def fingerprint(snapshot):
        copy = json.loads(dump(snapshot))
        copy["context"]["notification"].pop("seconds_before_event", None)
        return digest(copy)

    def freshness(self, exported):
        try:
            snapshot = self.source.snapshot(exported["work_instance_id"], self.config)
            return "current" if self.fingerprint(snapshot) == exported["fingerprint"] else "stale"
        except Exception:
            # No source error is converted into proof of current truth.
            return "unavailable"

    def run(self, opportunity, now_utc):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        request = json.loads(exported["request"])
        current = self.freshness(exported)
        if not exported["launched"]:
            if current != "current" or instant(now_utc) >= instant(request["selection_cutoff_utc"]) - timedelta(seconds=1):
                return self.capture(opportunity, None, now_utc, "not_invoked")
            # One durable original send intent. Crash before spawn may lose this
            # opportunity, but never authorizes another invoke after restart.
            if self.store.mark_launched(opportunity):
                response = self.client.exchange("invoke", exported["request"])
                # Use actual response observation time; caller-supplied decision time
                # is only for deterministic capture/recovery tests.
                return self.capture(opportunity, response, utc(datetime.now(UTC)), "invoke")
        return self.readback(opportunity, now_utc)

    def readback(self, opportunity, now_utc):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        request = json.loads(exported["request"])
        read = dict(
            interface=INTERFACE,
            version=VERSION,
            ledger_instance_id=self.source.namespace,
            work_id=request["work_id"],
            request_sha256=hashlib.sha256(exported["request"]).hexdigest(),
        )
        return self.capture(opportunity, self.client.exchange("read", dump(read)), now_utc, "read")

    def capture(self, opportunity, response, now_utc, channel):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        request = json.loads(exported["request"])
        binding = {
            "ledger_instance_id": self.source.namespace,
            "work_id": request["work_id"],
            "request_sha256": hashlib.sha256(exported["request"]).hexdigest(),
        }
        execution = None
        reason = "unresolved"
        disposition = None
        try:
            Draft202012Validator(SCHEMA["$defs"]["response"]).validate(response)
            require(all(response[k] == v for k, v in binding.items()), "response_binding")
            disposition = response["disposition"]
            require(
                disposition
                in (
                    {"new", "existing", "rejected", "conflict", "unresolved"}
                    if channel == "invoke"
                    else {"found", "absent", "conflict", "unavailable"}
                ),
                "response_disposition",
            )
            execution = response["execution"]
            if disposition in ("new", "existing", "found"):
                require(execution is not None, "missing_execution")
                self.validate_execution(execution, request)
                reason = execution["status"]
            else:
                require(execution is None, "unexpected_execution")
                reason = disposition
        except (ValidationError, ValueError, TypeError, KeyError):
            execution = None
            reason = "unresolved" if response is None else "invalid_response"
        freshness = self.freshness(exported)
        cutoff = instant(request["selection_cutoff_utc"])
        timely = execution is not None and execution["completed_at_utc"] is not None and instant(execution["completed_at_utc"]) <= cutoff
        usable = bool(execution and execution["status"] == "succeeded" and timely and instant(now_utc) <= cutoff and freshness == "current")
        record = dict(
            contract="spine.contextual-notification-capture.v1",
            **binding,
            opportunity_id=opportunity,
            observed_at_utc=now_utc,
            ordinary_text=request["context"]["notification"]["ordinary_text"],
            ordinary_text_kind="nominal_preview",
            execution=execution,
            reason=reason,
            source=freshness,
            result_completed_by_cutoff=bool(timely),
            usable_for_hypothetical_selection=usable,
            selected=False,
            sent=False,
            exchange=channel,
            disposition=disposition,
        )
        self.store.capture(opportunity, record)
        return record

    @staticmethod
    def validate_execution(execution, request):
        require(execution["configuration_revision"].startswith("fixture-model.v1:"), "nonfixture_provider")
        require(execution["prompt_revision"] == "helpful-personable.v1", "prompt_revision")
        for name in ("started_at_utc", "completed_at_utc"):
            if execution[name] is not None:
                instant(execution[name])
        calls = execution["calls"]
        for call in calls:
            instant(call["possible_entry_at_utc"])
            if "completed_at_utc" in call:
                instant(call["completed_at_utc"])
        require([c["ordinal"] for c in calls] == list(range(1, len(calls) + 1)), "call_sequence")
        for operation, limit in (
            ("fixture.model.v1", request["limits"]["model_calls"]),
            ("fixture.lookup.v1", request["limits"]["tool_calls"]),
        ):
            require(sum(c["operation"] == operation for c in calls) <= limit, "call_limit")
        require(
            "fixture.lookup.v1" in request["allowed_tools"] or all(c["operation"] != "fixture.lookup.v1" for c in calls), "tool_permission"
        )
        if execution["status"] != "succeeded":
            require(execution["result"] is None, "failure_as_proposal")
            return
        require(calls and all(c["certainty"] == "complete" and c["usage"] is not None for c in calls), "incomplete_success")
        require(execution["completed_at_utc"] is not None, "missing_completion")
        result = execution["result"]
        require(result is not None, "missing_proposal")
        if result["kind"] == "addendum":
            require(len(result["text"].encode()) <= request["limits"]["addendum_utf8_bytes"], "addendum_bytes")
            if result["basis"] == "provided_context":
                require(result["sources"] == [], "context_sources")
            else:
                require(result["sources"], "missing_sources")
                for source in result["sources"]:
                    instant(source["retrieved_at_utc"])
                    require(source["reference"] == "fixture:preparation-checklist", "fixture_source")
                    ordinal = source["observation_ordinal"]
                    require(ordinal <= len(calls) and calls[ordinal - 1]["operation"] == "fixture.lookup.v1", "provenance")
