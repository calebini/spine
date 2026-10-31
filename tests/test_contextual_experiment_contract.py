"""Installed schema and independent byte-vector checks; no sibling imports."""

import hashlib
import json
import unittest
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


class ContractTests(unittest.TestCase):
    def test_packaged_schema_and_shared_byte_vector(self):
        root = Path(__file__).parents[1] / "contracts/contextual_notification"
        packaged = files("spine.contracts").joinpath("contextual_notification/local-v1.schema.json").read_bytes()
        self.assertEqual(packaged, (root / "local-v1.schema.json").read_bytes())
        schema = json.loads(packaged)
        Draft202012Validator.check_schema(schema)
        request = (root / "request.json").read_bytes()
        vector = json.loads((root / "vector.json").read_bytes())
        self.assertEqual(hashlib.sha256(request).hexdigest(), vector["request_sha256"])
        validator = Draft202012Validator(schema["$defs"]["request"])
        value = json.loads(request)
        validator.validate(value)
        value["allowed_tools"] = ["shell"]
        with self.assertRaises(ValidationError):
            validator.validate(value)
        value = json.loads(request)
        value["limits"]["model_calls"] = True
        with self.assertRaises(ValidationError):
            validator.validate(value)
