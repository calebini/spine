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

The first increment is verified and committed as `7423052`. It changes neither the preserved
dirty R2 continuation nor the remaining RF2 exit requirements below.

## Recurring-page continuation

The operator selected page-state ownership after checkpoint `7423052`.
`services.recurring_task_page_state.PageState` now owns results/work/mappings,
working root/runtime facts, owner/change flags, mutation counts, continuation/lane
position and the retained SQL/Python checkpoint stack. The previous loose state
fields and independent snapshot loops are removed from reconciliation and its
existing child/adoption consumers.

`PageCheckpoint` deep-copies rollbackable working facts. Results are append-only:
their checkpoint stores the prior length, avoiding repeated copies of accepted
output prefixes. Restore preserves root/runtime/position and top-level accumulator
references, so the command's cutoff/audit view observes the same rollback.
`PageUnit` pairs that snapshot with the existing ledger-owned savepoint, without
another writer, commit or receipt. Units register immediately after entry, before
any child operation or decision-recovery reference lookup. Closure checks identity
and LIFO order; successful invocation releases the stack, exceptional invocation
unwinds it, and response-size rejection rolls back only the final suffix unit.

Final response projection is also a paired SQL/Python trial. A rejected trial restores
all page state, not just the change flag. Earlier accepted units stay intact; spent
proof and hop work is not refunded. Existing per-source hop-reset policy is unchanged.
The shared `ProofBudget`, execution clock/deadline, request/context/capabilities and
per-trial oversized-work rejection signal remain outside rollbackable state.

**Focused evidence:** the same 51 real command/page/restoration/admission/response
tests pass before (49.818 seconds) and after (49.047 seconds). Four complete
RF1 response/page/replay/ledger witnesses remain byte-identical; no fixture was
regenerated. Twelve new page tests cover suffix restoration, stable references,
deep copies, LIFO/foreign-unit rejection, failed entry, final projection trials,
recoverable/unexpected failures, failure in a recovery-path lookup, work/mutation
limits, individually oversized work, non-refundable proof/hops and SQLite write
interruption. Together with twelve RF1 boundary/body tests they pass (24 total).
Strict typing of the page state/reconciliation boundaries and focused Ruff pass.
The isolated HEAD-plus-page snapshot without dirty R2 edits passes **61 tests**,
26.330 seconds. Documentation/declaration/preservation checks pass **24 tests**,
4.002 seconds. Five untouched pre-existing file hashes match, and all 444 selected
local links and 40 heading fragments resolve. Full regression passes **1,447 tests,
OK (one skipped)** in 373.476 seconds, using installed pinned Tickerd v1. The known
non-failing capacity-limit and timezone diagnostics appeared. Final lint and diff
hygiene pass. This page-state continuation is verified and uncommitted.

Full item-change composition remains the next RF2 increment. Existing whole-Page
child signatures have not yet been replaced by closed prepared operations and
narrow results; they remain a named RF2 obligation, not a newly approved interface.

## Remaining RF2 work (not claimed complete)

1. Introduce closed prepared create/change/restore operations with typed results;
   stop passing the whole mutable page to child operations.
   Preserve the allocator's SQL order/prospective successor view, authority rechecks,
   explicit owner/binding changes, policies/applications/presentations, facets/roles,
   selected work behavior and evidence returned to the command owner.
2. Close IO-03–06/08 across that composition: faults after every owned stage,
   zero/eight facets, opposite roles and clears, shared-intent independent policies,
   customized restoration and terminal/suppression vetoes, exact budget accounting,
   protected replay/admission and full regression. This first increment only
   establishes the transaction/page-state portion of those gates.

RF3 propagation and functional recurring R2/R3 resumption need their existing
separate authorization/exit gates. No new policy decision is required for the
transaction-state extraction.
