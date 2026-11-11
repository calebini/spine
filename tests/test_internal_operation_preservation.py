"""RF0 fixed-input witnesses, captured before the first RF1 extraction.

Only disposable ledgers are used. These fixtures pin results, not a public contract.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from functools import partial
from pathlib import Path
from unittest.mock import patch

from spine.commands import core, handle, temporal_bindings
from spine.core.canonical_json import canonical_json_bytes
from spine.core.errors import SpineValidationError
from tests import test_schedule_create_command as schedule_tests

FIXTURE = Path(__file__).parent / "fixtures/internal_operations/rf0_shared_helpers.json"


def observed(call):
    try:
        return {"result": call()}
    except SpineValidationError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}


class InternalOperationPreservationTests(unittest.TestCase):
    def test_delivery_routes_preserve_exact_results_and_error_precedence(self):
        cases = json.loads(FIXTURE.read_text())["delivery"]
        for case in cases:
            with self.subTest(case=case["name"]):
                helper = schedule_tests.ScheduleCreateCommandTests()
                helper.setUp()
                try:
                    for command, request in case.get("setup", []):
                        response = handle(command, request, helper.context)
                        self.assertTrue(response["ok"], response)
                    context = replace(helper.context, delivery_target_defaults=case["defaults"])
                    before = "\n".join(helper.connection.iterdump())
                    result = observed(partial(core._schedule_resolve_delivery, case["request"], context))
                    self.assertEqual(canonical_json_bytes(result), canonical_json_bytes(case["expected"]))
                    self.assertEqual("\n".join(helper.connection.iterdump()), before)
                finally:
                    helper.tearDown()

    def test_binding_facts_preserve_canonical_revision_and_history_bytes(self):
        cases = json.loads(FIXTURE.read_text())["binding"]
        for case in cases:
            with self.subTest(case=case["name"]), patch(
                "spine.core.schedule.system_timezone_database_version", return_value="2026c"
            ):
                operation = getattr(temporal_bindings, case["operation"])
                result = observed(partial(operation, **case["arguments"]))
                self.assertEqual(canonical_json_bytes(result), canonical_json_bytes(case["expected"]))
