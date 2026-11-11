# RF2: transaction state and complete item-change ownership

Date: 2026-11-11. Selected by the operator after RF1 checkpoint `9e50c1c`.
Tracking: [SPINE-100](../BACKLOG.md#spine-100--rf2-complete-item-change-and-transactionpage-state-ownership).
Authority: [internal application operations §§5–6](../../specs/internal-application-operations.md).
This is implementation evidence, not a new feature contract or public activation.

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
hygiene pass. This page-state continuation is committed as `07fc937`.

## Complete child composition continuation

Selected after checkpoint `07fc937`. The internal operation boundary now has
separate `CreateChild`, `ChangeChild` and `RestoreChild` inputs, a required
`ChildInvocation`, and typed created/changed/work evidence. It is not a new public
command or a universal mutation object. The exact recurring contract and outer
command identities remain fixed; generation-scoped identities retain their existing
preimages. Cancel and detach are mutually exclusive dispositions, not independently
combinable booleans. A terminal disposition cannot also request a move or adoption.

The admitted trusted-local composer explicitly selects authority. Child entrypoints
require both that authority and the existing owned `LedgerConnection` transaction;
missing authority, a raw connection or an invocation outside that transaction cannot
fall through to the allocator's standalone transaction convenience. This is internal
composition discipline, **not** new authentication or protection from a trusted local
process with direct ledger access. Protected transport remains denied at the existing
command admission boundary; no protected recurring entrypoint is introduced.

| Intent | Complete owned work | Deliberately unaffected / separately owned |
| --- | --- | --- |
| Create | Guarded task v1, due anchor, selected roles/location/archetype, owner/history/epoch, relation, binding/revision, exact policies/application/presentations, selected work and returned identities | No inherited facets or predecessor unless the explicit restore intent is used |
| Change | Existing allocator/CAS/audit, prospective successor supporting sets, selected named-role clears/adoption, binding freshness or retirement, bounded work classification/materialization | Owner/relation identity retained; unselected supporting fields copy forward; binding-only refresh does not manufacture an item version |
| Restore | New generation identity with actual predecessor configuration, exact facet entries and reference history, additional roles/locations, active family **and independent** policies, pinned application/presentation, new work | No current-default re-resolution; terminal/manual/detach/suppression and source-only eligibility remain the recurring feature's decisions |

The page application still owns source proof, selector reservation, assignment and
generation lineage and their cutoff/intent checks. Those feature-specific steps and
the complete child operation share the same retained SQL/Python unit, transaction
finalizers and outer receipt. There is no newly independent child transaction or
receipt. The allocator's private prerequisite/extension closures remain inside the
operation; callers cannot supply a callback that skips supporting work. Existing SQL
write ordering and the prospective successor view are preserved.

Children, restoration helpers and adoption helpers no longer accept a `Page`, CLI
request or command context. Route resolution receives only configured delivery
defaults; restoration preparation and intent completion receive the same shared
`ProofBudget`, never a replacement allowance. Work and mapping/audit evidence return
to the owning page, which alone folds it into checkpointed accumulators. Intent
helpers return whether they changed state instead of mutating page flags.

Work selection retains its `limit + 1` bounded query. Create also checks its complete
indivisible work result before returning. `ChildWorkOverflow` carries the existing
code/message but tells the page that this is an oversized child, not a removable
suffix that permits prefix success. Whole-page aggregate budgets, exact response
sizing, shared proof/hop consumption and commit-time clock checks remain unchanged.

### Composition verification

- The same 80 pre/post-refactor command, page, restoration, admission and response
  tests pass (53.644 and 53.496 seconds). The subsequent 102-test composition and
  dependency/body selection passes in 60.486 seconds.
- Twelve new child tests cover closed inputs, explicit authority/transaction
  failure, complete create/change/restore, no child receipt or replay re-entry,
  invalid intent combinations, real change-stage fault rollback, indivisible work
  capacity, empty assignee clear retaining a participant, protected started work,
  and non-queryable location references through move/cancel/restore. The added page
  regression proves child overflow cannot return a successful prefix or refund work.
- Seven new complete-envelope and ledger-dump witnesses were captured from the
  **committed pre-refactor `07fc937` source** with fixed clock/IDs. A second baseline
  run and the new implementation both match: create, move, cancel, restore, adoption
  with supporting-set clears, no-op and replay. The existing RF0/RF1 artifacts are
  untouched. See [lifecycle witness](../../tests/fixtures/internal_operations/rf2_child_composition_witness.json).
- The final 26-test child/page/witness selection passes (6.494 seconds), strict
  mypy passes six operation/page modules and focused Ruff passes. The isolated
  checkpoint-plus-refactor snapshot, excluding older R2 edits, passes **104 tests**
  (37.945 seconds), including transaction finalizers and unchanged body witnesses.
- The first full run (1,461 tests, 374.881 seconds) exposed exactly one stale
  internal producer inventory key: creation now allocates in `_create`, shared
  privately by create/restore. The exact entry in `facet_writer_inventory.v1.json`
  is updated; no allocator registration, table, DDL fingerprint or public contract
  changes. Both real facet/people writer matrices pass with discovery's test-root
  import path (four tests, 22.872 seconds), also in the isolated refactor-only
  snapshot (four tests, 23.623 seconds). No test expectation was weakened.
- Documentation, frozen declarations, RF0/RF1 preservation, shared-intent policy
  lineage and rendering permissions pass **36 tests**, 5.834 seconds. All 454
  selected local link targets and 40 heading fragments resolve; the five untouched
  pre-existing files retain their RF0 hashes. The older command/core R2 continuation
  is preserved separately and is not part of this implementation increment.
- The fresh complete regression run after the inventory correction passes
  **1,461 tests, OK (one skipped)** in 366.240 seconds, using installed pinned
  Tickerd v1. Only the established non-failing capacity-limit and timezone
  compatibility diagnostics appeared. Final diff hygiene passes. RF2 is complete
  for the selected migrated paths; the final composition increment is included in
  this operator-selected checkpoint.
  No functional R2 resumption is claimed.

### RF2 gate evidence map

| Gate | Evidence |
| --- | --- |
| IO-03 | Real create/restoration stage faults, new move-stage faults, prior transaction finalizer/interrupt tests and paired page-unit recovery tests |
| IO-04 | Real zero/eight-facet writer matrix, customized restoration, explicit opposite-role clear, non-queryable location references, terminal/suppression cases and shared-intent notification lineage tests |
| IO-05 | Existing bounded page/response/cutoff/concurrent restoration tests, paired checkpoint tests and the new typed child-overflow test; proof/hops are never refunded |
| IO-06 | Existing protected transport/replay/release and rendering permission tests, new explicit local-authority/owned-transaction rejection, retained dry-run ledger witness |
| IO-08 | Frozen RF0/RF1 and seven RF2 lifecycle witnesses, isolated refactor-only verification, strict typing/lint, unchanged public contracts and passing final full regression |

RF3 propagation and functional recurring R2/R3 resumption need their existing
separate authorization/exit gates. No new policy decision is required for this
internal composition refactor.
