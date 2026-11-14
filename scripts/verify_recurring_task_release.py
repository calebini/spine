"""Run all 18 RRT witness groups together and write their actual test outcomes.

Run from the repository: PYTHONPATH=src .venv/bin/python -m
scripts.verify_recurring_task_release --report /absolute/disposable/report.json
This supplements, never replaces, full discovery and installed-wheel canaries.
"""

import argparse
import json
import time
import unittest
from pathlib import Path

from tests.recurring_task_release_obligations import resolved_obligations


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = set()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.add(test.id())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    groups = resolved_obligations()
    unique = {test.id(): test for tests in groups.values() for test in tests}
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(
        unittest.TestSuite(unique[key] for key in sorted(unique)))
    evidence = {key: {"status": "pass" if all(t.id() in result.passed for t in tests) else "not_passed",
                      "tests": [t.id() for t in tests]} for key, tests in groups.items()}
    ok = result.wasSuccessful() and not result.skipped and all(row["status"] == "pass" for row in evidence.values())
    args.report.write_text(json.dumps({"ok": ok, "scope": "named-RRT-runtime-witnesses",
                                     "tests_run": result.testsRun, "elapsed_seconds": round(time.monotonic() - started, 3),
                                     "skipped": len(result.skipped),
                                     "obligations": evidence}, indent=2) + "\n")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
