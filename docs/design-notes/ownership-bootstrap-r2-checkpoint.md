# Ownership bootstrap — internal R2 checkpoint

Date: 2026-11-10
Authority: [accepted bootstrap specification](../../specs/local-ownership-bootstrap.md)
Tracking: [SPINE-093](../BACKLOG.md#spine-093--r2-recurring-task-commands-and-manual-reconciliation)

## Checkpoint and scope

The operator ratified the reviewed machine package, committed separately as
`232944b`, then selected its implementation within R2. This increment replaces
the internal manual engine's unconfigured-ledger refusal. It does not complete
the recurring-task family, activate a public contract or include a deployment.
The operator subsequently requested committing this increment before continuing
the remaining R2 implementation. That checkpoint does not activate a release.

## Implemented boundary

- `ledger/ownership.py` validates the bounded row-or-absent state and existing
  immutable instance metadata without repair or full-ledger scans. A real owner
  creator initializes local state at epoch 1; a later creating transaction
  advances once. Existing configured ledger/realm/recovery facts are retained.
  Invalid identifiers, postures, integer domains and overflow fail closed.
- The existing outer command transaction owns the once marker. Its lifecycle and
  unit-savepoint snapshot now restore that marker with SQL and existing facet,
  presentation and recurring-task trackers. No independent bootstrap commit or
  receipt exists. The generated-child extension reserves the epoch immediately
  before the owner header/history, not in a second page-end increment.
- The unpublished candidate-20 installer folds in the ratified state rebuild:
  connection-local FK disable outside the migration transaction, explicit named
  column copy, parent replacement without child FK retargeting, and verbatim
  restoration of the three referencing triggers. Failures restore predecessor
  schema/data and FK enforcement. Candidate object/resource hashes are updated;
  current schema-19 manifests and published migration 13 are unchanged.
- Explicit migration verification includes FK/integrity, existing domain/facet/
  rendering invariants, instance/state and recurring-task deep checks. Routine
  candidate admission and ownership reads do not inherit those scans.
- V3 provisioning requires explicitly injected source contracts and a candidate
  connection. It is not loaded by ordinary CLI/HTTP paths. Plans bind the complete
  before-state, explicit realm, normalized operations and references; apply uses
  existing row-ID derivation/audit/receipt ownership, actor/replay precedence,
  expected epoch, one promotion/operation advance and eligible-operator/no-lockout
  checks. Configured no-op/replay at maximum epoch do not advance. V1/v2 configured
  behavior and frozen schema/preimage files are unchanged.

## Actual evidence

`tests/test_ownership_bootstrap.py` contains 16 real disposable-ledger tests:

| Contract gate | Internal evidence (not public release acceptance) |
| --- | --- |
| LOB-01 | Actual six-child R2 page from absent access state; one local epoch, six owner headers/history, no accounts/grants/attempts; compatible replay |
| LOB-02 | Outer/unit rollback and earlier-unit retention; first generation faults after task/state/owner/binding/policy/work/audit/receipt; actual dry-run and work-budget last-unit rollback |
| LOB-03 | Configured migration with real accounts/bindings preserves predecessor rows and triggers; page and repeated primitive calls consume one epoch |
| LOB-04 | Actual injected v3 promotion, exact replay after epoch change, incompatible replay, stale epoch/recovery witness, ledger mismatch, no-lockout, maximum-epoch no-op and changed-request refusal |
| LOB-05 | Candidate posture check behind explicit test schema admission refuses local state; legacy provisioning cannot promote it; no implicit v3 contract loading |
| LOB-06 | Two real R2 first-owner pages on separate connections: stale catalog loser re-reads/retries; two committed pages/epochs. Both deterministic owner/provisioning writer orders preserve state and freshness |
| LOB-07 | Configured and empty rebuilds, fault injection at eight migration boundaries, account FK preservation, trigger SQL preservation, FK restoration and candidate object fingerprints; existing R1 tests retain old-writer refusal |
| LOB-08 | Actual invalid stored IDs, missing instance metadata, overflow and SQL null guards; unsupported dependent object rejection; bounded routine trace. Existing R1 tests retain object-drift detection |

The old test asserting that absent state must fail has been replaced with the
ratified successful local/no-realm assertion, not removed. Existing configured
R2 and web provisioning tests remain regression coverage.

These tests do not close the descriptor's public-runtime obligations or the
family's wider R2/R3/R4 exit matrix. In particular, public CLI dispatch, installed
v3 contract loading, real service/worker operation against the successor schema,
all-writer scheduling and release packaging/activation remain deferred.

## Compatibility and verification limits

Public package/schema remain **0.11.2 / 19**. The candidate resource is covered by
the existing `*.candidate.sql` package-data rule. Existing pre-amendment disposable
candidate-20 files fail new fingerprint validation and must be deliberately
recreated; this is not an in-place reinterpretation of any published schema.
No operator ledger was opened or migrated, no accounts/permissions were inferred,
and no delivery adapter or real send was used.

Selected actual/bootstrap/frozen-contract run: **65 tests passed**. New modules
pass focused strict typing with missing third-party JSON Schema stubs excluded;
focused Ruff and frozen web-copy synchronization pass. Final full suite:
**1,370 tests, OK (one skipped)** in 328.648 seconds. The initial full run found
one version-selection error in the rendering writer-parity harness: it still used
the predecessor fingerprint verifier on candidate 20. That test now selects the
strict recurring-candidate verifier, which also validates inherited rendering
objects. The standalone case passes with the legacy `src:tests` import path; the
full rerun passes. No runtime verifier or contract was relaxed. A later type-only
connection cast received another **16-test actual-bootstrap run**, all passing.
The final complete-tree selection, including the strict parity case, passed all
**66 tests** after that type-only clarification.
The suite emitted existing non-fatal budget-trace/timezone diagnostics.
Broad strict typing still reports untouched annotation
sites in existing transaction/provisioning code; no unrelated cleanup is claimed.
An actual wheel build was not performed because local setuptools/build/wheel
tooling is absent; no network dependency installation was attempted. The SQL
resource's existing package-data inclusion rule was checked, not wheel-certified.
