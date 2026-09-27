# Notification policy lineage hotfix — Spine 0.8.1

Date: 2026-09-27. Local implementation/verification complete; not a deployment claim.
Base: `8e536b6d95d68aff7afd1dd704f798bc18309a1b` plus the uncommitted hotfix.
Ledger schema remains **17**; no data rewrite or new migration is introduced.

## Defect and correction

The facet implementation assumed `(item_id, notification_intent_id)` uniquely selected
a current policy. Preserved schema-15 policies can legitimately have a shared intent,
distinct schedules, and distinct policy IDs. Their work rows name the exact policy.
The uniqueness assumption failed planning and reconciliation, rejected otherwise valid
work at attempt start, and prevented facet edits. Repeated reconciliation failures then
triggered Tickerd's existing fatal threshold.

The correction follows each work row's specific policy ancestry. Current policy ID
matches and persisted `source_notification_policy_id` chains identify its unique
descendant. Intent narrows the search; it never chooses an arbitrary sibling. Reads
use policy primary keys, stop at the original policy version, and require decreasing
versions and the same item/intent. Resolver caches are command/snapshot-local. Missing
descendants remain stale; malformed or forked lineage fails closed.

The shared rule covers scheduler planning, explicit materialization, schedule-update
reconciliation, and attempt-start validation. Target snapshots are keyed by current
policy ID so siblings cannot overwrite one another. Facet equivalence proves that every
prior policy has exactly one unchanged successor, including shared-intent siblings.

Semantic schedule/route/target checks, provenance and lifecycle checks, attempt evidence,
leases, terminal history, scheduler no-op suppression, and Tickerd failure thresholds
are not relaxed. Newly authored multi-reminder schedules still receive distinct intents.

Normative owners: [archetype facets](../specs/archetype-facets.md),
[notifications](../specs/notifications.md), and the
[facet integration contract](../contracts/archetype-facet-integration.v1.json).
The public request/response shapes and contract family identifiers are unchanged;
the corrected integration artifact and its packaged digest pins ship together.

## Verification

- [Synthetic regression suite](../tests/test_notification_policy_lineage.py): **14 tests,
  9 subtests**. A real schema-15 layout with canonical shared-intent policies and work
  migrates through 16 to 17 without changing predecessor rows. Before the patch, four
  tests reproduced planning, explicit materialization, schedule update, and freshness
  failures. Afterward, idle planning makes no durable changes; sibling work remains
  distinct through three facet edits; malformed lineage is rejected; changed schedule
  or routing affects only the correct sibling; unrelated work remains processable.
- The worker test performs four successful deterministic reconciliations and a bounded
  observe-only runner pass beyond the fatal threshold. Two fake deliveries persist
  successful attempt records. Later facet edits preserve completed work and attempts.
- Full source suite: `.venv/bin/python -m pytest -ra` — **755 passed, 961 subtests passed**.
  Existing multi-reminder creation tests retain the explicit unique-intent assertion.
- Ruff, configured strict mypy (42 core/ledger files), compileall, `git diff --check`,
  and both contract synchronization scripts in `--check` mode pass.

### Installed-wheel check

Built in an isolated temporary build environment and installed non-editably into a
new runtime environment with web/test extras and Tickerd built from exact source
`ffe613c65ea3d6fc70a1dc3603c32068f06350df`. The sibling Tickerd checkout was not moved;
its newer checkout was not used as the runtime dependency.

Environment: macOS arm64, Python **3.14.6**, SQLite **3.53.2**, setuptools **84.0.0**.
This is not Linux/Python-3.12 cloud qualification.

- **84 tests + 182 subtests passed** against installed packages, with `PYTHONPATH`
  unset, pytest's source-path setting disabled, and all imported Spine/Tickerd module
  paths checked against the new environment's `site-packages`.
- One repository-only generator test initially failed because the disposable test
  directory intentionally omitted source scripts. It was excluded from installed-runtime
  coverage and passed in the source suite and separate generator parity checks.
- `pip check`, fresh-ledger initialization, explicit deep verification, and installed
  `spine-command system info` passed: runtime 0.8.1, schema 17, Tickerd compatible.
- All **243** packaged Spine source/resource files checked match the hotfix worktree.

Artifact SHA-256 values (for this local build, not reproducible-build guarantees):

| Wheel | SHA-256 |
| --- | --- |
| `spine_ledger-0.8.1-py3-none-any.whl` | `ebed69058abee23a523c35250a442f7a3bab928cd79142079664b8f68c53a711` |
| `tickerd-0.2.0-py3-none-any.whl` | `c755cc60a72700d5353a49394cca564dda6d8a75b8c4d6267b430d18d5271ddc` |

Temporary local artifacts and harness:
`/private/tmp/spine-hotfix-validation.sMBbZ6/`. These are not durable release storage.

## Remaining deployment gate

No staging ledger or backup was available to this local test run. Before restarting
the stopped staging worker, test the committed/pinned patched package against a
**disposable copy** of the preserved staging ledger. Confirm no planning failures,
inspect cancellation/retention classifications and overdue reminder grace windows,
and validate attempt eligibility with outbound delivery disabled or explicitly fake.
Do not treat integrity verification alone as a behavioral check.

A schema-17 ledger needs no additional migration for 0.8.1. Preserve a consistent backup
and install the matching runtime before restarting services. Do not lower Tickerd's
failure threshold, rewrite historical intents, or delete policies to mask this defect.
Rollback to a pre-facet runtime still requires its matching pre-migration database;
do not pair that binary with a schema-17 ledger.

No live database, real delivery channel, deployment, commit, or push was used during
this hotfix work.
