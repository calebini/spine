"""Synthetic counting-capable Impetus consumer. Captures facts, never sends."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from importlib.resources import files

from jsonschema import Draft202012Validator, ValidationError

from spine.adapters.contextual_experiment import digest, dump, require
from spine.adapters.contextual_live import LiveCaptureStore, compact, decode
from spine.services.contextual_experiment import INTERFACE, OBJECTIVE, Experiment, instant, utc

VERSION = "impetus.openai.v1"
CONTRACT = "spine.contextual-notification-live-capture.v1"
OWNER = "5ff3c0c4530fe07e81cc9067eddadd967a90acc4"
SCHEMA_SHA256 = "bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b"
PROMPT = "helpful-personable-openai.v1"
COUNT = "openai.responses.input_tokens.v1"
GENERATION = "openai.responses.v1"
_raw_schema = files("spine.contracts").joinpath("contextual_notification/openai-v1.schema.json").read_bytes()
require(hashlib.sha256(_raw_schema).hexdigest() == SCHEMA_SHA256, "live_schema_pin")
SCHEMA = json.loads(_raw_schema)


def cost(config, inputs, outputs):
    return (inputs * config["input_nanodollars_per_million"] + outputs * config["output_nanodollars_per_million"] + 999999) // 1000000


def configuration_binding(text):
    require(isinstance(text, str) and len(text.encode()) <= 65536, "configuration_size")
    config = decode(text)
    required = {
        "model", "max_output_tokens", "input_token_upper_bound", "input_nanodollars_per_million",
        "output_nanodollars_per_million", "qualification_reference", "token_counting",
    }
    require(type(config) is dict and required <= config.keys()
            and config.keys() <= required | {"model_binding", "reasoning_effort"}, "configuration_fields")
    for key, maximum in (
        ("max_output_tokens", 2000), ("input_token_upper_bound", 2000000),
        ("input_nanodollars_per_million", 1000000000000), ("output_nanodollars_per_million", 1000000000000),
    ):
        require(type(config[key]) is int and 1 <= config[key] <= maximum, "configuration_bound")
    model = config["model"]
    binding = config.get("model_binding", "dated_snapshot")
    require(isinstance(model, str) and (
        binding == "dated_snapshot" and re.fullmatch(r"[a-zA-Z0-9.-]+-\d{4}-\d{2}-\d{2}", model)
        or binding == "documented_alias" and model == "gpt-6-luna"
    ), "model_binding")
    require("reasoning_effort" not in config or config["reasoning_effort"] in
            ("none", "low", "medium", "high", "xhigh", "max"), "reasoning_effort")
    reference = config["qualification_reference"]
    require(isinstance(reference, str) and 0 < len(reference.encode()) <= 512, "qualification_reference")
    counting = config["token_counting"]
    require(type(counting) is dict and set(counting) == {"charge_bound_nanodollars"}, "counting_required")
    amount = counting["charge_bound_nanodollars"]
    require(type(amount) is int and 1 <= amount <= 20000000, "count_reserve")
    generation = cost(config, config["input_token_upper_bound"], config["max_output_tokens"])
    require(generation + amount <= 20000000, "run_reserve")
    encoding = compact(config)
    return dict(
        capture_contract=CONTRACT, wire_version=VERSION, schema_sha256=SCHEMA_SHA256, owner_checkpoint=OWNER,
        configuration_encoding=encoding.decode(), configuration_revision=GENERATION + ":" + hashlib.sha256(encoding).hexdigest(),
        prompt_revision=PROMPT, counting_required=True, authorized_nanodollars=generation + amount,
        generation_reserve=generation, count_reserve=amount,
    )


class LiveExperiment(Experiment):
    """Separate format-2 profile; inherits only source freshness/fingerprint helpers."""

    capture_contract = CONTRACT

    def __init__(self, source, store, launcher, config, *, clock=None):
        require(isinstance(store, LiveCaptureStore), "live_store_required")
        require(store.namespace == source.namespace, "capture_namespace")
        keys = {"synthetic_only", "opted_in_item_ids", "permit_ordinary_text", "facet_fields", "definition_revision",
                "disclosure_revision", "lead_seconds", "allowed_tools"}
        require(type(config) is dict and keys <= config.keys() <= keys | {"provider_configuration_json"}, "profile_config_fields")
        self.source, self.store, self.client = source, store, launcher
        self.config = decode(dump(config))
        require(self.config["synthetic_only"] is True and self.config["allowed_tools"] == [], "synthetic_context_only")
        require(type(self.config["lead_seconds"]) is int and 1 <= self.config["lead_seconds"] <= 300, "lead_seconds")
        self.clock = clock or (lambda: datetime.now(UTC))

    def _observed_at_utc(self):
        # Completion and cutoff comparisons must retain the clock's fractions.
        return self.clock().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _configuration_binding(self, text):
        binding = configuration_binding(text)
        binding["capture_contract"] = self.capture_contract
        return binding

    @classmethod
    def validate_binding(cls, binding):
        expected = configuration_binding(binding["configuration_encoding"])
        expected["capture_contract"] = cls.capture_contract
        for name in ("source_config_sha256", "disclosure_sha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", binding[name]), "stored_fingerprint")
            expected[name] = binding[name]
        require(dump(binding) == dump(expected), "stored_binding")
        return decode(binding["configuration_encoding"])

    def export(self, work_instance_id, now_utc=None):
        existing = self.store.for_work(work_instance_id)
        if existing:
            self.validate_binding(existing[1]["binding"])
            return existing
        require("provider_configuration_json" in self.config, "export_configuration_required")
        binding = self._configuration_binding(self.config["provider_configuration_json"])
        snapshot = self.source.snapshot(work_instance_id, self.config)
        binding["source_config_sha256"] = snapshot["config_hash"]
        binding["disclosure_sha256"] = digest({name: self.config[name] for name in (
            "synthetic_only", "opted_in_item_ids", "permit_ordinary_text", "facet_fields", "disclosure_revision"
        )})
        opportunity = snapshot["opportunity"]
        existing = self.store.get(opportunity)
        if existing:
            self.validate_binding(existing["binding"])
            return opportunity, existing
        now_utc = now_utc or utc(self.clock())
        context = snapshot["context"]
        eligible = instant(context["notification"]["eligible_at_utc"])
        require(eligible - timedelta(seconds=self.config["lead_seconds"]) <= instant(now_utc)
                < eligible - timedelta(seconds=1), "outside_export_window")
        seconds = (instant(context["event"]["starts_at_utc"]) - eligible).total_seconds()
        require(seconds.is_integer(), "relative_time")
        context["notification"]["seconds_before_event"] = int(seconds)
        work_id = "experiment:" + digest(
            {"version": "spine.experiment-work.v1", "ledger": self.source.namespace, "opportunity": opportunity}
        )
        request = dict(
            interface=INTERFACE, version=VERSION, work_id=work_id,
            source_refs=dict(
                ledger_instance_id=self.source.namespace, item_id=snapshot["item_id"], item_version=snapshot["item_version"],
                notification_opportunity_id=opportunity, notification_policy_id=snapshot["policy"],
                rendering_definition_revision="sha256:" + snapshot["rendering_hash"],
                experiment_definition_revision=self.config["definition_revision"], disclosure_revision=self.config["disclosure_revision"],
            ),
            captured_at_utc=now_utc, context=context, objective=OBJECTIVE, allowed_tools=[],
            limits=dict(model_calls=1, tool_calls=0, elapsed_seconds=20, addendum_utf8_bytes=512),
            selection_cutoff_utc=utc(eligible), request_expires_at_utc=utc(eligible),
        )
        Draft202012Validator(SCHEMA["$defs"]["request"]).validate(request)
        for text, maximum in (
            (context["event"]["title"], 1024), (context["event"]["timezone"], 128),
            (context["notification"]["ordinary_text"], 8192), (OBJECTIVE, 2048),
            (context["archetype"], 256), (work_id, 256),
        ):
            require(0 < len(text.encode()) <= maximum, "request_string_bytes")
        for key, value in request["source_refs"].items():
            if key != "item_version":
                require(0 < len(value.encode()) <= 256, "source_reference_bytes")
        require(len(context["facets"]) <= 16, "facet_limit")
        for facet in context["facets"]:
            require(0 < len(facet["schema_revision"].encode()) <= 256, "facet_reference_bytes")
        raw = dump(request) + b"\n"
        require(len(raw) <= 65536, "request_size")
        exported = self.store.put(opportunity, work_instance_id, raw, self.fingerprint(snapshot), binding)
        return opportunity, exported

    def run(self, opportunity, now_utc=None):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        self.validate_binding(exported["binding"])
        request = decode(exported["request"])
        require(request["version"] == exported["binding"]["wire_version"], "stored_version")
        if exported["launched"]:
            return self.readback(opportunity, now_utc)
        now_utc = now_utc or utc(self.clock())
        if self.freshness(exported) != "current" or instant(now_utc) >= instant(request["selection_cutoff_utc"]) - timedelta(seconds=1):
            return self.capture(opportunity, None, now_utc, "not_invoked")
        self.client.prepare(exported["binding"])
        if self.store.mark_launched(opportunity):
            response = self.client.exchange("invoke", exported["request"])
            return self.capture(opportunity, response, self._observed_at_utc(), "invoke")
        return self.readback(opportunity, now_utc)

    def readback(self, opportunity, now_utc=None):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        self.validate_binding(exported["binding"])
        request = decode(exported["request"])
        read = dict(interface=INTERFACE, version=exported["binding"]["wire_version"], ledger_instance_id=self.source.namespace,
                    work_id=request["work_id"], request_sha256=hashlib.sha256(exported["request"]).hexdigest())
        response = self.client.exchange("read", dump(read))
        return self.capture(opportunity, response, now_utc or self._observed_at_utc(), "read")

    def capture(self, opportunity, response, now_utc, channel):
        exported = self.store.get(opportunity)
        require(exported is not None, "export_absent")
        self.validate_binding(exported["binding"])
        request = decode(exported["request"])
        identity = dict(ledger_instance_id=self.source.namespace, work_id=request["work_id"],
                        request_sha256=hashlib.sha256(exported["request"]).hexdigest())
        execution, disposition, validation_reason = None, None, None
        reason = "unresolved"
        try:
            Draft202012Validator(SCHEMA["$defs"]["response"]).validate(response)
            require(all(response[k] == v for k, v in identity.items()), "response_binding")
            disposition = response["disposition"]
            allowed = {"new", "existing", "rejected", "conflict", "unresolved"} if channel == "invoke" else {
                "found", "absent", "conflict", "unavailable"
            }
            require(disposition in allowed, "response_disposition")
            candidate = response["execution"]
            if disposition in ("new", "existing", "found"):
                require(candidate is not None, "missing_execution")
                self.validate_execution(candidate, request, exported["binding"])
                execution, reason = candidate, candidate["status"]
            else:
                require(candidate is None, "unexpected_execution")
                reason = disposition
        except (ValidationError, ValueError, TypeError, KeyError, OverflowError):
            # Unvalidated payloads do not enter capture as execution/accounting.
            # Their bounded digest and classification remain available for review.
            reason = "unresolved" if response is None else "invalid_response"
            validation_reason = "schema_or_consumer_semantics"
        completed = None if execution is None else execution["completed_at_utc"]
        timely = completed is not None and instant(completed) <= instant(request["selection_cutoff_utc"])
        fresh = self.freshness(exported)
        usable = bool(execution and execution["status"] == "succeeded" and timely and
                      instant(completed) <= instant(now_utc) <= instant(request["selection_cutoff_utc"]) and fresh == "current")
        try:
            response_digest = None if response is None else digest(response)
        except (ValueError, TypeError, OverflowError):
            response_digest = None
        record = dict(
            contract=self.capture_contract, **identity, opportunity_id=opportunity, observed_at_utc=now_utc,
            ordinary_text=request["context"]["notification"]["ordinary_text"], ordinary_text_kind="nominal_preview",
            execution=execution, reason=reason, source=fresh, result_completed_by_cutoff=bool(timely),
            usable_for_hypothetical_selection=usable, selected=False, sent=False, exchange=channel, disposition=disposition,
            validation_reason=validation_reason, response_sha256=response_digest,
            binding=exported["binding"], source_fingerprint=exported["fingerprint"],
        )
        self.store.capture(opportunity, record)
        return record

    @classmethod
    def validate_execution(cls, execution, request, binding):
        config = cls.validate_binding(binding)
        require(execution["configuration_revision"] == binding["configuration_revision"] and
                execution["provider_configuration"] == config and execution["prompt_revision"] == PROMPT, "execution_pins")
        require(execution["interface_version"] == VERSION and
                execution["authorized_nanodollars"] == binding["authorized_nanodollars"], "execution_admission")
        start = instant(execution["started_at_utc"])
        require(execution["live_day"] == utc(start)[:10], "live_day")
        end = None if execution["completed_at_utc"] is None else instant(execution["completed_at_utc"])
        require(end is None or end >= start, "execution_time")
        require((end is None) == (execution["status"] in ("admitted", "running")), "terminal_time")
        calls = execution["calls"]
        require([c["ordinal"] for c in calls] == list(range(1, len(calls) + 1)) and
                [c["operation"] for c in calls] == [COUNT, GENERATION][:len(calls)], "call_sequence")
        previous = start
        for call in calls:
            entered = instant(call["possible_entry_at_utc"])
            require(entered >= previous and (end is None or entered <= end), "call_time")
            previous = entered
            require(re.fullmatch(r"[0-9a-f]{64}", call.get("request_sha256", "")), "call_digest")
            if call["certainty"] == "complete":
                previous = instant(call["completed_at_utc"])
                require(previous >= entered and (end is None or previous <= end), "completion_time")
            else:
                require("completed_at_utc" not in call, "uncertain_completion")
            if call["operation"] == COUNT:
                require(call["usage"] is None and call["tokens"] is None and
                        call["reserve"]["amount"] == binding["count_reserve"], "count_accounting")
                require(re.fullmatch(r"[0-9a-f]{64}", call.get("generation_request_sha256", "")), "generation_digest")
                if call["certainty"] == "complete":
                    require(type(call.get("counted_input_tokens")) is int, "missing_count")
            else:
                count = calls[0]
                require(count["certainty"] == "complete" and call.get("count_call_ordinal") == 1 and
                        call["request_sha256"] == count["generation_request_sha256"], "count_binding")
                require(count["counted_input_tokens"] <= config["input_token_upper_bound"] and
                        (instant(count["completed_at_utc"]) - instant(count["possible_entry_at_utc"])).total_seconds() <= 5,
                        "generation_after_invalid_count")
                usage, tokens = call["usage"], call["tokens"]
                if usage is None:
                    require(tokens is None and call["reserve"]["amount"] == binding["generation_reserve"], "unknown_usage")
                else:
                    require(tokens is not None and tokens["total_tokens"] == tokens["input_tokens"] + tokens["output_tokens"], "tokens")
                    require(all(tokens[key] <= 4000000 for key in ("input_tokens", "output_tokens", "total_tokens")), "token_bound")
                    require(tokens["reasoning_tokens"] is None or tokens["reasoning_tokens"] <= tokens["output_tokens"], "reasoning")
                    require(usage["amount"] == cost(config, tokens["input_tokens"], tokens["output_tokens"]), "usage_cost")
                    require(call["reserve"]["amount"] == max(0, binding["generation_reserve"] - usage["amount"]), "residual_reserve")
                if call["certainty"] == "uncertain":
                    require(usage is None, "uncertain_usage")
        for observation in execution["observations"]:
            ordinal = observation["call_ordinal"]
            require(1 <= ordinal <= len(calls) and calls[ordinal - 1]["operation"] == GENERATION, "observation_reference")
            observed = instant(observation["observed_at_utc"])
            generation = calls[ordinal - 1]
            require(end is not None and instant(generation.get("completed_at_utc", generation["possible_entry_at_utc"]))
                    <= observed <= end, "observation_time")
        if execution["status"] != "succeeded":
            require(execution["result"] is None, "failure_as_proposal")
            return
        require(end is not None and len(calls) == 2 and all(c["certainty"] == "complete" for c in calls), "incomplete_success")
        require(execution["reason"] is None and not execution["observations"], "success_with_failure")
        require((end - start).total_seconds() < request["limits"]["elapsed_seconds"] and
                end < instant(request["selection_cutoff_utc"]) - timedelta(seconds=1), "success_deadline")
        count, generation = calls
        require((instant(count["completed_at_utc"]) - instant(count["possible_entry_at_utc"])).total_seconds() <= 5,
                "count_deadline")
        tokens = generation["tokens"]
        require(generation["usage"] is not None and tokens is not None and
                tokens["input_tokens"] == count["counted_input_tokens"] <= config["input_token_upper_bound"] and
                tokens["output_tokens"] <= config["max_output_tokens"] and
                generation["usage"]["amount"] <= binding["generation_reserve"], "success_usage")
        require(generation.get("provider_model") == config["model"] and
                isinstance(generation.get("provider_response_id"), str) and
                0 < len(generation["provider_response_id"]) <= 256, "provider_identity")
        result = execution["result"]
        require(result is not None and 0 < len(result["review_note"].encode()) <= 512, "result")
        if result["kind"] == "addendum":
            require(result["basis"] == "provided_context" and result["sources"] == [] and
                    0 < len(result["text"].encode()) <= request["limits"]["addendum_utf8_bytes"], "context_only_result")
