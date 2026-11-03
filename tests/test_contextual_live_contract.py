"""Independent wire vectors, corrected owner closure and installed resource pins."""

import copy
import hashlib
import json
import os
import unittest
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from spine.adapters.contextual_experiment import dump
from spine.adapters.contextual_live import LiveLauncher, compact
from spine.services.contextual_live import (
    GENERATION,
    OWNER,
    SCHEMA,
    SCHEMA_SHA256,
    LiveExperiment,
    configuration_binding,
)


class LiveContractTests(unittest.TestCase):
    def resource(self, name):
        return files("spine.contracts").joinpath("contextual_notification/" + name).read_bytes()

    def test_complete_packaged_closure_and_independent_vector(self):
        root = Path(__file__).parents[1] / "contracts/contextual_notification"
        pins = json.loads(self.resource("live-pins.v1.json"))
        self.assertEqual(pins["owner_checkpoint"], OWNER)
        self.assertEqual(pins["files"]["openai-v1.schema.json"], SCHEMA_SHA256)
        self.assertEqual(self.resource("live-pins.v1.json"), (root / "live-pins.v1.json").read_bytes())
        for name, expected in pins["files"].items():
            with self.subTest(name=name):
                raw = self.resource(name)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                self.assertEqual(raw, (root / name).read_bytes())
        Draft202012Validator.check_schema(SCHEMA)
        for kind, name in (("request", "live-request.json"), ("read", "live-read.json"), ("response", "live-late-response.json")):
            Draft202012Validator(SCHEMA["$defs"][kind]).validate(json.loads(self.resource(name)))
        vector = json.loads(self.resource("live-vector.json"))
        for kind, name in (("request", "live-request.json"), ("read", "live-read.json"), ("response", "live-late-response.json")):
            self.assertEqual(hashlib.sha256(self.resource(name)).hexdigest(), vector[kind + "_sha256"])
        response = json.loads(self.resource("live-late-response.json"))
        self.assertEqual(response["request_sha256"], vector["request_sha256"])
        binding = configuration_binding(self.resource("live-configuration.json").decode())
        binding.update(source_config_sha256=vector["source_config_sha256"], disclosure_sha256=vector["disclosure_sha256"])
        self.assertEqual(binding["configuration_revision"], vector["configuration_revision"])
        LiveExperiment.validate_execution(response["execution"], json.loads(self.resource("live-request.json")), binding)

    def test_independent_request_bytes_and_configuration_key_order(self):
        config = json.loads(self.resource("live-configuration.json"))
        binding = configuration_binding(json.dumps(config))
        self.assertEqual(binding["configuration_encoding"].encode(), compact(config))
        self.assertNotEqual(binding["configuration_revision"], GENERATION + ":" + hashlib.sha256(dump(config)).hexdigest())
        for mutate in (lambda c: c.pop("token_counting"), lambda c: c.update(api_key="forbidden"),
                       lambda c: c["token_counting"].update(charge_bound_nanodollars=True)):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(ValueError):
                configuration_binding(json.dumps(changed))
        with self.assertRaises(ValueError):
            configuration_binding('{"model":1,"model":2}')
        for option in ("--enable-live", "--provider-config", "--provider-config=synthetic-config.json"):
            with self.assertRaisesRegex(ValueError, "base_command_has_live_options"):
                LiveLauncher(["fixture-worker", option])

    def test_corrected_schema_rejects_invalid_generation_observation_references(self):
        response = json.loads(self.resource("live-late-response.json"))
        validator = Draft202012Validator(SCHEMA["$defs"]["response"])
        cases = []
        for ordinal in (0, 1, 3, True):
            changed = copy.deepcopy(response)
            changed["execution"]["observations"][0]["call_ordinal"] = ordinal
            cases.append(changed)
        for calls in ([], [response["execution"]["calls"][0]]):
            changed = copy.deepcopy(response)
            changed["execution"]["calls"] = calls
            cases.append(changed)
        for changed in cases:
            with self.subTest(execution=changed["execution"]):
                self.assertFalse(validator.is_valid(changed))

    def test_source_owner_schema_copy_when_checkout_available(self):
        owner = Path(os.environ.get("IMPETUS_SRC", Path(__file__).resolve().parents[2] / "impetus/src")).parent
        path = owner / "contracts/schemas/contextual-notification-openai-v1.schema.json"
        if not path.exists():
            self.skipTest("Independent Impetus checkout required for owner resource parity")
        self.assertEqual(self.resource("openai-v1.schema.json"), path.read_bytes())
