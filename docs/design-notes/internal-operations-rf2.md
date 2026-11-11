# RF2: transaction state and complete item-change ownership

Date: 2026-11-11. Selected by the operator after RF1 checkpoint `9e50c1c`.
Tracking: [SPINE-100](../BACKLOG.md#spine-100--rf2-complete-item-change-and-transactionpage-state-ownership).
Authority: [internal application operations §§5–6](../../specs/internal-application-operations.md).
This is implementation evidence, not a new feature contract or whole-RF2 closure.

## Baseline and preservation boundary

RF1 is committed separately, excluding the older R2 admission/read continuation
and unrelated `AGENTS.md` changes. Those files/hunks remain uncommitted and are
not resumed by RF2. The same 95 transaction/ownership/facet/recurring-storage/
reconciliation/restoration/response-witness tests pass before the extraction
(33.199 seconds) and after it (38.104 seconds).

No public registry, request/response schema, durable schema, version declaration,
identity preimage, receipt or audit format changes. No user ledger, send, migration,
external review, deployment or push. The source candidate remains internal; this
does not activate recurring-task commands or the scheduler.

## First increment: one transaction-state owner

`ledger.mutation_state.TransactionMutationState` owns four closed components:

| Component | Transaction-local obligations |
| --- | --- |
| Ownership | Whether this transaction has consumed its ownership epoch |
| Recurring | Exact touched table/key tuples |
| Rendering | Pending policy presentations, versions, catalog objects, profiles and attempts |
| Facets | Allocations, versions, roots, items, bindings and definitions |

The fixed component tuple supplies checkpoint, restore, reset and finalization
coverage. Declared fields provide their own snapshot coverage; adding a component
requires an explicit registration/test change. There is no dynamic plugin API.
Snapshots deep-copy nested pending presentation data. Restore keeps component and
top-level set/dict identities stable, so a retained state reference observes rollback.

`LedgerConnection` retains transaction ownership, savepoints, feature enablement,
the registered version-producer guard, commit authorization and SQLite operations.
SQL TEMP callbacks now update the typed state. Rendering persistence, ownership
bootstrap/provisioning, policy replacement and facet preview callers use the same
owner rather than parallel private connection fields. The facet command's existing
preview-proof ordering and family error mapping are intentionally unchanged.

Finalization remains recurring → rendering → facets. Feature-specific finalizers
and facet allocation/exact-proof checks remain the same. Rendering finalization can
still add facts consumed by the following facet proof. No finalizer commits itself.
Feature-disabled/raw SQLite read behavior remains supported by presentation lookup.

Every commit/rollback/context exit resets all obligations, including connections
without facet tracking enabled. An interrupt that already aborted SQLite clears
state rather than restoring a partial checkpoint; the original interruption escapes.
Ordinary unit rollback restores its checkpoint, retaining earlier accepted units.
Connection flags and producer guards are not reset or copied as page mutation data.

## Verification

- The 95-test before/after preservation selection passes. Existing complete
  response/page/replay/SQL-dump witnesses were not regenerated.
- Eleven new state-owner tests plus twelve RF1 dependency/body checks pass
  (23 total). Coverage includes all thirteen state fields, deep-copy independence,
  per-connection isolation, nested successful/failed units, epoch preservation,
  all transaction exits, deferred-FK commit failure, exact finalizer order,
  failure at each finalizer, missing facet proofs and real write-time interruption.
- An AST ratchet rejects use of the thirteen removed connection trackers,
  including dynamic `getattr`/`setattr`/`hasattr` paths, across runtime source.
- The two new/touched transaction boundary modules pass strict mypy;
  all touched runtime/tests pass focused Ruff and diff hygiene.
- The isolated HEAD-plus-RF2 snapshot, excluding the older R2 dirty continuation,
  passes **106 tests**, 36.451 seconds. The documentation/declaration/RF0–RF1
  preservation selection passes **24 tests**, 3.982 seconds. All 456 local link
  targets resolve; the five untouched pre-existing files retain their baseline hashes.
- Full regression passes **1,435 tests, OK (one skipped)** in 392.707 seconds,
  using installed pinned Tickerd v1. Known non-failing capacity-limit and timezone
  compatibility diagnostics appeared, as in the RF1 baseline. Thirty-six affected
  cross-document heading fragments and final diff hygiene also pass.

The first increment is verified and uncommitted. It changes neither the preserved
dirty R2 continuation nor the remaining RF2 exit requirements below.

## Remaining RF2 work (not claimed complete)

1. Encapsulate recurring `PageState` and retained unit checkpoints. Preserve LIFO
   closing, accepted earlier units, continuation/cutoff behavior and non-refundable
   proof/hop/time costs. Do not pass the whole mutable page to child operations.
2. Introduce closed prepared create/change/restore operations with typed results.
   Preserve the allocator's SQL order/prospective successor view, authority rechecks,
   explicit owner/binding changes, policies/applications/presentations, facets/roles,
   selected work behavior and evidence returned to the command owner.
3. Close IO-03–06/08 across that composition: faults after every owned stage,
   zero/eight facets, opposite roles and clears, shared-intent independent policies,
   customized restoration and terminal/suppression vetoes, exact budget accounting,
   protected replay/admission and full regression. This first increment only
   establishes the transaction-state portion of those gates.

RF3 propagation and functional recurring R2/R3 resumption need their existing
separate authorization/exit gates. No new policy decision is required for the
transaction-state extraction.
