# R4 recurring-task release integration

Status: complete locally; package increment committed as `46da61f`,
migration-core as `62fe2ef`, CLI/worker activation as `d69a4ae` (2026-11-14).
Authority: [SPINE-095](../BACKLOG.md#spine-095--r4-recurring-task-activation-and-release-verification)
and the [R4 plan](../IMPLEMENTATION_PLAN.md#r4--public-activation-and-release-verification-spine-095).
R3 is committed as `c90f27d`. The unrelated agent-instructions and R2 restoration
edits remain outside this work.

## Offline package first

The [sync script](../../scripts/sync_recurring_task_contracts.py) copies the
ratified descriptor, closure manifest, and all 30 declared schemas byte-for-byte.
Nested schema paths are preserved to avoid basename collisions. Its `--check`
mode detects missing, modified and extra packaged JSON files. It rejects source
hash drift, duplicate paths/identities and incomplete transitive references.
No fixture, source contract, web bundle or runtime declaration is rewritten.

The [loader](../../src/spine/commands/recurring_task_package.py) checks the
compiled SHA-256 of the pin manifest, every asset, closure identity, transitive
references, command schema membership and exact existing runtime prerequisites.
Reads are size-bounded; all resolution is offline, with no source-directory or
network fallback and no cache that can conceal resource loss after a prior load.
Loading resources does not register or activate commands. The source descriptor
correctly still says `runtime_implemented=false` at this intermediate checkpoint.

Package pins SHA-256:
`ee9dd3d44fd4b3504e75da27cdfa255f7ac8dbbcaec7e076b88e8f7ba9504842`.

## Verification boundary

[Package tests](../../tests/test_recurring_task_package.py) cover source parity,
every required missing/corrupt asset, existing prerequisite loss, offline schema
validation, resource loss following success, sync parity, and the unchanged public
registry/schema boundary. The reusable
[wheel check](../../scripts/verify_recurring_task_wheel.py) requires an isolated,
non-editable virtual-environment installation and reports package-only scope.
It loaded 33 resources / 30 schemas / seven command entries outside the checkout;
`pip check` passed. Build and runtime environments were disposable and no
ledger, worker or delivery adapter was opened. This is not the full pinned
Tickerd/worker/public-CLI release qualification required by R4.

Final focused verification: **63 tests in 25.689 seconds, OK** (package,
recurring commands, machine fixtures, implemented declarations, architecture
boundaries and agent documentation). Repository Ruff, loader Mypy, compilation,
401 local documentation link paths, synchronization and diff hygiene pass.
The final locally built test wheel SHA-256 is
`bfa2886bc90875044296fdce7f0e5e7061dba883cebe6dd1e724e8ed6010f093`;
this is a disposable verification artifact, not a published release.

## Migration and preflight core

Packaging was committed as `46da61f`. The next increment supplies
`install_recurring_task_storage` through the existing ordered migration
dispatcher. The guarded disposable-candidate helper delegates to that same core,
not a second DDL implementation. It owns one exclusive transaction, validates
schema 19 before/inside it, rebuilds ownership-state constraints without changing
row values, installs the pinned DDL, performs deep migration verification, records
version 20, and checks the final expected-object manifest before commit. Every
failure rolls back DDL, data and the schema version, restores FK enforcement,
and does not arm recurring write tracking.

The [schema manifest generator](../../scripts/sync_recurring_task_schema_manifest.py)
overlays the pinned migration delta on the complete predecessor manifest, including
the replaced ownership table. Normal `verify_runtime_schema(expected_version=20)`
now checks that exact table/index/trigger inventory using the established bounded
preflight implementation. It ignores noncolliding extra objects and reports the
ordinary missing-object and definition-drift diagnostics. Deep integrity/domain
checks occur only in the explicit migration, not routine preflight.

[Release migration tests](../../tests/test_recurring_task_release_migration.py)
cover ordered dispatch, empty/no-enrollment installation, exact populated-history
and configured-ownership preservation, idempotency, all eight injected rollback
stages, final manifest failure, unknown ownership dependents, ambient-transaction
refusal, writer exclusion, and metadata-only verification. Public/default runtime
and migration admission still require schema 19; this is release substrate,
not a schema-20 production activation.

The migration increment's focused selection ran **87 tests in 27.193 seconds,
OK**, covering new migration/preflight cases, predecessor migrations, existing
ownership and recurring storage, package validation and boundary/documentation
checks. Repository Ruff, two-module Mypy, compilation, schema/resource sync,
403 local document paths and diff hygiene pass. The isolated, non-editable wheel
check also ran the explicit migration core and verified schema 20, without
creating any enrolled rule. The disposable verification wheel SHA-256 is
`f0651e06c1d54a167373062de6a65c25c445054faa6c42e35ede1a47928910d1`.
Full serial discovery: **1,717 tests in 510.142 seconds, OK (one skipped)**.

## Public CLI and worker activation

Runtime 0.12.0/schema 20 activates the seven exact local commands, preserving
the source-only wire corpus as representation evidence rather than claiming that
its finite witnesses prove runtime acceptance. The compiled registry binds all
family/dependency versions. CLI input is bounded and duplicate-key rejecting;
schema/key failures cannot trigger source/network fallback. Public admission
rejects HTTP transport metadata; frozen HTTP registries are unchanged.

Fresh initialization, ordered migration, reconnect tracking, routine metadata
preflight and explicit deep verification use schema 20. Deep verification pins
a read snapshot for source proofs. Historical schema-19 manifests and four
pre-extraction byte witnesses remain exact; witness fixtures run on their original
schema rather than being regenerated to accept new DDL. Existing predecessor
migration fixtures explicitly omit schema-20 installation. Current enrichment
uses the compiled current schema instead of its old literal-19 guard, without
widening disclosure or introducing a second supported writer baseline.

The canonical worker loads the recurring package during admission and constructs
the scheduler only with explicit active actor and protected ledger-bound cursor
configuration. No-rule workers preserve ordinary startup. Missing/invalid
configuration with enrolled rules fails DOWN before processor construction; if
rules appear later, an unconfigured reconciler refuses the cycle rather than
silently skipping them. Named route defaults can be supplied explicitly.

The reviewed `spine.trusted-web-provisioning.v3` bridge is packaged under a separate
ownership closure, with compiled prerequisites and per-resource hash checks.
Existing local plan/apply commands accept it; there is no new bootstrap command
or HTTP exposure. Public preview and explicit local-to-configured promotion are
tested. The v1/v2 shapes remain frozen and do not silently promote local state.

The non-editable wheel was exercised outside the checkout with Tickerd built from
exact source `ffe613c65ea3d6fc70a1dc3603c32068f06350df`: four Saturday pickups,
four reminder work rows, exact replay, independent assignment readback, then a
second rule with four pickups generated by the public worker alone. Explicit
deep verification and `pip check` passed. Future-only fake-sender execution created
no send log and performed no real send. The wheel SHA-256 is
`5688146619f61254024841e72a30bdbf730cf3a3ef57540373f40ae2d6fa2a81`.
See [activation canary](../../scripts/verify_recurring_task_activation.py),
[public tests](../../tests/test_recurring_task_public.py), and
[ownership package tests](../../tests/test_ownership_package.py).

Full serial discovery passed **1,724 tests in 590.414 seconds, OK (one skipped)**.
Final focused verification passed 39 tests, including the no-rule/shared-facet-key
test added after discovery and the final explicit ownership prerequisite gate.
Repository Ruff, six-module focused Mypy, compilation, exact synchronization of
both contract bundles and the schema manifest, documentation links and diff
hygiene pass. Full-suite evidence and final focused evidence are distinct; R4's
complete named lifecycle acceptance reconciliation remains the next increment.

## Complete lifecycle and release qualification

The activation checkpoint is committed as `d69a4ae`. The qualification increment
does not change the seven public command shapes or lifecycle semantics. It adds
an executable [obligation inventory](../../tests/recurring_task_release_obligations.py),
a [runner](../../scripts/verify_recurring_task_release.py), and a retained
[runtime result](recurring-related-task-r4-runtime-evidence.json). Every RRT-01–18
row names actual test methods. Resolution refuses missing/ambiguous witnesses;
failed or skipped evidence cannot close the runner. The inventory regression test
also checks that the retained result matches the current named selection.

**All 18 obligations passed together: 93 distinct tests, 63.756 seconds, zero
skips**, running against the non-editable wheel outside the checkout. Only test
code and fixture inputs came from the repository; `spine` and its child modules
came from the isolated installed package, with no source-runtime path fallback.
This includes fresh/populated migration, all injected rollback stages, immutable
history/FKs, old-writer refusal, replay, proof/lineage rejection, commit-clock
cutoffs, native ownership without grants, policy continuity, cancellation,
restoration/suppression and separate-connection races, adoption, retirement,
attempt freshness/protection, idle zero-write/fairness, cursor expiry and
invalidation, query indexes, disclosure/people/route checks and whole-unit budgets.
The JSON contains exact per-obligation test IDs, rather than treating wire
fixtures or file names as runtime proof.

The [installed public CLI canary](../../scripts/verify_recurring_task_activation.py)
now exercises the complete science-class lifecycle. Four Saturday classes at
11:30 produce four unique 13:00 pickups with four reminders at 12:50; a second
rule independently produces four tasks through the actual worker. The canary
then proves same-task following after a class moves, replacement work at the
successor time, cancellation on exclusion, exactly one linked restoration,
suppression, completion without reopening, overlapping-customization decisions
and explicit resolution. Separate rules exercise all three retirement
dispositions, checking task and binding outcomes, with profile-backed and zero
reminder cases alongside custom reminders.

One synthetic Tickerd cycle invokes the normal adapter, rendering and durable
attempt-backed processor with a **file-only fake sender**. It proves one send
record, no duplicate on repeated processing, public attempt readback and history
preservation after source cancellation. No real destination or live service is
contacted. Final explicit deep verification succeeds. Synthetic cycle time is a
test input to the normal Tickerd protocol, not a runtime clock override.

The descriptor's 18 runtime statuses now say `runtime_verified` and the packaged
descriptor/pin are synchronized, with compiled pin
`6daa92da0ef83f9e6ef934d02ff894c088a01c7fe0aec4b6244a0bc7e83993bc`.
The **wire fixture manifest and schema closure remain source-only** intentionally:
their finite computed examples are representation evidence, not the executable
release matrix. No HTTP registration or authorization widening accompanies this.

Reproduce the named runtime selection from the checkout:

```bash
PYTHONPATH=src .venv/bin/python -m scripts.verify_recurring_task_release \
  --report /absolute/disposable/rrt-runtime-evidence.json
```

For the installed-wheel selection, preload the installed `spine` with isolated
Python and add only the repository root for the test/fixture modules (never
`src`). For the public lifecycle, use the installed wheel's Python with `-I`,
the absolute canary-script path, and a working directory outside the checkout.
Both require the exact supported Tickerd runtime. The script creates and removes
its own disposable ledger and private cursor file; no existing ledger is used.

## Final verification results

- Full serial discovery: **1,727 tests in 620.482 seconds, OK (one skipped)**.
  The skipped revision-readback wheel test lacked local build tooling in the
  test interpreter; it was rerun with `SPINE_WHEEL_BUILD_PYTHON` pointing at the
  prepared disposable build interpreter: **one test in 8.990 seconds, OK**.
- Final source contract/inventory/operator-documentation/package selection:
  **39 tests, OK** (after the evidence and fixture-builder message reconciliation).
  The full discovery above preceded those final evidence/message-only adjustments;
  no runtime semantics changed after discovery.
- All 18 named runtime groups: **93 tests in 63.756 seconds, OK, no skips**,
  against the isolated installed wheel. The retained JSON has exact test IDs.
- Installed public CLI and actual worker science-class lifecycle: pass, including
  the file-only fake attempt and final explicit deep verification.
- Repository Ruff, compilation, changed-loader Mypy (`--follow-imports=silent
  --disable-error-code=import-untyped`), 487 local documentation paths and diff
  hygiene pass. The import-only exception is for unavailable jsonschema stubs;
  it does not disable checks of the loader's typed implementation. A broader
  ad-hoc strict check also found existing untyped enrichment-adapter methods;
  they were not changed or suppressed as part of this release.
- All 80 computed source-only artifacts regenerate exactly; recurring/ownership
  resource synchronization and the complete schema-20 manifest checks pass.
- Non-editable wheel closure/migration-core check and `pip check` pass. All **197
  installed Python modules** are byte-identical to their source counterparts.

Final verification wheel SHA-256:
`f9ecd66b38eba63d0e2369b7167517d1021b3217d0c987a0fe11de3d9c4f483a`.
The exact Tickerd source is `ffe613c65ea3d6fc70a1dc3603c32068f06350df`, version
0.2.0, capability `tickerd.runtime-capabilities.v1`, descriptor SHA-256
`215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b`.
No floating/sibling-source substitution was used for installed-wheel verification.

R1–R4 implementation/release-verification work is complete locally. This does
not assert live qualification or deployment. No push, live migration, real-send
test or release publication was performed. The preexisting `AGENTS.md` and R2
restoration-note edits remain untouched and outside the qualification increment.
