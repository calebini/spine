# SPINE-062 two-line patch validation

Date: 2026-10-22. Local synthetic validation; no production deployment or ledger access.

| Line | Branch | Base | Runtime | Ledger schema |
| --- | --- | --- | --- | --- |
| Mainline | `fix/spine-062-mainline` | `ca9ea72eec1fdf87e6aed7dad7cf16c5bd4212bc` | `0.10.1` | 19, unchanged |
| Production maintenance | `fix/spine-062-prod-0.6.0` | `a28bdf0e20cdb671e4a3862572d85c952f354056` | `0.6.0+tzdb.1` | 15, unchanged |

The operator confirmed the production source revision. The maintenance patch applies
only timezone-resolution integrations, shared new resolver/provisioning/schema files,
tests, version declarations and documentation. It does not include mainline's later
capabilities or migrations. Shared resolver, provisioning, catalog and regression
files were compared byte-for-byte between branches. The original main worktree's
unrelated people-authoring edits were excluded by using isolated worktrees.

## Results

| Check | Mainline | Production maintenance |
| --- | --- | --- |
| Full repository suite | 1117 passed; 1840 subtests passed | 689 passed; 652 subtests passed |
| Isolated installed wheel: timezone regressions and version smoke | 42 passed | 42 passed |
| New shared modules: strict mypy | Pass | Pass |
| Core/ledger plus new modules: strict mypy | Same 36 baseline errors in 10 unrelated files | Pass, 39 files |
| Ruff on changed runtime files and new regression corpus | Pass | Pass |
| Diff hygiene, schema parity, fixture digests, unchanged migration files | Pass | Pass |

Full suites used `python -m pytest -o addopts='' -q`. Mainline's existing installed
revision-readback wheel test ran with `SPINE_WHEEL_BUILD_PYTHON` pointing at a prepared
build interpreter; it did not skip. The 36 mainline mypy errors were reproduced on
an untouched `ca9ea72` source export, and the error lines matched exactly. No attempt
was made to repair unrelated rendering typing in this incident patch.

The 39 timezone cases cover:

- Exact releases and automatic matching across forward, reverse, unseen and suffixed
  runtime labels; an unchanged zone beyond the incident's Paris/Chicago pair.
- Changed Winnipeg/Dublin data, modified complete files, missing baselines, unknown
  authored references, malformed JSON, duplicate/conflicting identities, unsupported
  evidence methods, invalid digests/counts and truncated TZif/footer data.
- Historical offsets/folds, current DST gaps/folds and distant-future footer rules;
  earliest-UTC fold choice and COUNT seeking across omitted gaps.
- Warm global ZoneInfo caches, live version changes, metadata/provider precedence,
  and replacement during capture. Exact verified bytes are used for resolution and
  recurrence gap parsing.
- Immutable capture refusal for relabeling a newer provider or replacing an original
  build. Read paths do not enroll or alter catalog evidence.
- Real subprocess CLI agenda reads across one-off and recurring schedules, unchanged
  complete responses and ledger dumps, original authored pins and nonzero failure
  exit when required evidence is removed.
- Notification opportunity equality, temporal-binding conversions, rendering hashes,
  and the worker's OpenClaw processor with fake transport. The test verifies matching
  durable attempt/rendering evidence exists before the fake sender is called.
- Structured substitution diagnostics, repetition suppression, and clean JSON stdout.

## Installed packages

Both wheels were built with setuptools 84.2.1, with no dependency resolution during
build. Separate virtual environments without system site packages installed each
wheel and test dependencies offline. Python 3.14.6, pytest 9.1.1 and jsonschema 4.26.0
were used. Each run asserted `spine.__file__` was inside that isolated environment,
reported the exact runtime/schema, invoked the installed baseline-tool entry point,
and ran the copied compatibility tests outside the source checkout. Runtime module
loading did not use an editable Spine install. No real transport was invoked.

| Artifact | SHA-256 |
| --- | --- |
| `spine_ledger-0.10.1-py3-none-any.whl` | `c9fa744eddd76f1bf9bc0255df0f533809b66e3cae12d42dea66d32a038c23ba` |
| `spine_ledger-0.6.0+tzdb.1-py3-none-any.whl` | `56d765e5f2d35f0c01adf7d5e01667a68ebbb72c58cecd7bc251b877e7a661d9` |

Artifacts/logs are retained locally under `/private/tmp/spine062-wheels/`,
`/private/tmp/spine062-installed/` and `/private/tmp/spine062-*.log`. Rebuilding may
change ZIP timestamps and therefore the whole-wheel digest. These are the packages
actually exercised; subsequent edits only add validation/tracking documentation.

## Remaining production acceptance

SSH to the configured cortext1 address was unreachable from this environment. No
production backup or actual Ubuntu TZif files were inspected. Before deployment,
authenticate original 2026c Ubuntu build evidence, provision its catalog, and verify
both reported route agendas plus fake notification preparation on an approved
disposable production backup. Confirm diagnostics are visible in the actual CLI and
worker logging environments. Local macOS-compiled reference files are not proof of
the deployed Ubuntu fingerprints. The production Python/dependency environment also
needs its installed-package check; local Python 3.14 validation does not claim that.

The external daily-agenda wrapper's source remains unidentified, so its reported
exit-code masking has not been patched. See [operations](TZDB_COMPATIBILITY_OPERATIONS.md)
for setup, verification and rollback boundaries. The logical policy's earlier bounded
Whetstone audit is separate evidence; no new external runtime review was invoked.

## Combined people/timezone integration — 2026-10-25

The operator authorized merging `160547d808bd25dbcf20c5f25c888ba18984d8f8` into
people-enabled main `75a4b95bfe07a6976370dbbbb6c8cd9264595055`. The previous release
`83d1a96` contains the people implementation but not the timezone runtime fix;
the common ancestor `ca9ea72` contains only its specification. This combined
release is **0.11.1/schema 19**, not a redefinition of either earlier wheel.

Merge conflicts were limited to release versions, README prose and version test
assertions. All people declarations and the timezone declaration are retained.
Auto-merged callers preserve people v4 dispatch and selected/selected-ID filtering
while using the timezone-aware resolver. No timezone algorithm change, new schema,
or migration is introduced; the production maintenance branch is not modified.
People, frozen web, rendering and revision-readback contract bytes/pins remain
unchanged. All four synchronization checks pass.

The new `tests/test_timezone_people_integration.py` supplies four public HTTP
regressions: fresh v4 creation/replay and people-only update across a provider
upgrade; person-filtered agenda exclusion before expansion of an incompatible
nonmatching item; recurring occurrence identities and exact `pc1` continuation;
and fail-closed fresh creation when a baseline is absent or zone bytes changed.
These run against disposable ledgers and real synthetic TZif fixtures, not operator
data or authenticated production provider files.

The selected timezone/people/public CLI/HTTP/read/work/declaration group passes
**107 tests, 14 subtests (50.18 seconds)**. The four new integration regressions
pass independently (7.580 seconds). An installed-only copy of the timezone plus
new integration corpus passes **43 tests (8.82 seconds)** outside the checkout,
with the noneditable installed path asserted and no source runtime present.
Pytest reported one cache-permission warning from using `/dev/null` as configuration;
there was no test failure.

Full combined pytest passes **1,220 tests and 1,889 subtests, one skipped, one warning
(259.82 seconds)**. The existing revision-readback installed build harness skips
without setuptools in the repository interpreter; independent wheel execution above
is not skipped. The full run emits a `PytestUnraisableExceptionWarning` in the passing
synthetic serialization-deadline case: its unchanged trace guard raises
`capacity_exceeded` while an object/generator is being finalized. A focused merged
rerun passes with that warning; an exported pre-merge `75a4b95` copy passes the
31-test read-page module (36 subtests) without it. There is no failed assertion or
confirmed production behavior failure. The guard/test are unchanged, and this merge
does not suppress the warning or introduce a broader deadline refactor.

A fresh noneditable wheel has SHA-256
`c1e12f5e48066a8636c497e78f57794cc5b5825ca63f1557a4e45a40413c3afc`.
Its separate runtime installs the declared web dependencies and exact cached
Tickerd 0.2.0 artifact; `pip check` passes. The installed people verifier reports
`PASS`, version `0.11.1`, schema `19`, 36 packaged schemas, all eight public HTTP
routes, public CLI, history/no-op/replay/dry-run, `pc1` pagination, frozen interfaces
and deep disposable verification. The baseline CLI entrypoint also starts correctly.
The wheel and temporary verification directories are local artifacts, not a
published package or external durable evidence store.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m pytest -o addopts='' -q tests
env -u PYTHONPATH /tmp/spine-0111-merge.syQpCG/runtime/bin/python -I \
  /Users/Shared/Agent-Workspace/repos/personal/cortext1/spine/scripts/verify_people_wheel.py
```

Focused Ruff, strict mypy on the two timezone modules plus six people owners,
344 local documentation link targets and diff hygiene pass; no project-wide strict
typing claim is made. The unrelated
`AGENTS.md` amendment remains byte-identical and excluded. A concurrently created,
unrelated `tests/test_coordination_acceptance.py` is also left untouched/untracked;
it is not part of the recorded full-suite collection or this merge. This authorization is
for a local merge, not a push, staging/production deployment, provider enrollment,
operator ledger access, real external send or new Whetstone review. Preserve both
the timezone baseline environment and the separate people cursor configuration
when a later rollout is authorized.
