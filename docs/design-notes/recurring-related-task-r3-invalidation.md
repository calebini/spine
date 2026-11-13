# R3 initial increment — coalesced invalidation and queue CAS

Status: initial R3 increment implemented and verified, uncommitted; R3 not closed
(2026-11-13). Current status belongs to [SPINE-094](../BACKLOG.md#spine-094--r3-recurring-task-all-writer-safety-and-automatic-scheduling).

## Authority and checkpoint

The operator requested committing RF3 and beginning R3. RF3 is committed as
`7e3983d`. The two unrelated changes in `AGENTS.md` and the R2 restoration evidence
were excluded and remain untouched. This increment implements part of
[storage §3.6 and §6](../../specs/recurring-related-task-storage.md) through the
accepted [application propagation boundary](../../specs/internal-application-operations.md).
It does not change public contracts, schema declarations, feature activation,
deployment or sending authorization.

## Implemented boundary

- `ledger/recurring_task_invalidation.py` owns the derived queue writes. Source
  lookup uses `related_task_rules_source_idx`; target, binding and relation lookup
  use generation UNIQUE indexes followed by the assignment PK/current-generation
  comparison. No child/history expansion or synchronous child mutation occurs.
- The existing application propagation owner passes exact item, recurrence,
  ownership, binding, relation and policy evidence into that persistence boundary.
  Existing standalone item helpers and standalone policy insertion also invalidate;
  they do not gain an application-layer dependency. Ordinary schema-19 ledgers
  remain unaffected because the candidate capability gate is closed there.
- Source changes mark SOURCE; current-generation task/binding/relation changes
  mark TARGET. The INTENT flag primitive is available, but intent/enrollment
  command integration belongs to the next increment. Retired roots are not
  filtered out: retained following or cleanup may still need maintenance.
- `RecurringMutationState` owns catalog advancement and the root/reason set for
  the transaction. The catalog advances once per semantic transaction, including
  existing recurring command/page advancement. Repeated root/reason observation
  within that transaction adds no writes; additional reasons merge into the same
  dirty token. It also retains exact newly allocated item IDs before owner/policy
  extensions, avoiding dependent lookups before any generation exists. Later item
  edits are not exempted. Savepoint rollback restores SQL and both evidence sets.
- Dirty tokens use the monotonic catalog generation, not `1` after an absent-row
  insert. Delete/reinsert therefore cannot recreate an older token and allow an
  old page to clear newer work. Source/target invalidation resets assignment
  continuation to zero and retains previously pending reason flags.
- Acknowledgement is an internal CAS primitive, not proof of completed work.
  A matching generation can advance assignment coverage or delete a completed
  row; stale generations and non-advancing coverage write nothing. A page cannot
  acknowledge an invalidation produced in its own transaction. The subsequent
  reconciliation/scheduler integration must supply the proof and use this CAS.

## Deliberate R3 behavior change and preservation

Ordinary source/generated-task mutations now invalidate recurring read cursors
and expected catalog facts in the same transaction. An old snapshot must fail
with `stale_version` at `expected.catalog_generation`; a caller rereads before a
fresh mutation. Compatible command replay still returns its prior receipt before
freshness checks and makes no new queue/audit/receipt writes.

The original RF2 and R2 immediate-parent witness files remain byte-identical.
Their historical producer tests explicitly isolate pre-R3 invalidation behavior;
a separate live R3 differential executes the same complete lifecycle with and
without the new invalidation boundary. It compares all domain tables and public
responses exactly except catalog fields, derived queue rows and catalog-bound
receipt/audit digest fields. Those changed digests are independently recomputed
from their actual semantic/request/result preimages. Audit identities, counts,
actions, actors and every other audit column remain equal. No golden was recaptured.
The separate `r3_catalog_body_amendment.json` pins exactly the one changed
`advance_catalog` AST body against the prior R2 amendment; the complete prior
body fixtures remain unchanged and all other function-body hashes stay frozen.

Happy-path test helpers reread current rule state after independent task edits.
Explicit stale/admission/concurrency tests still submit their own expected facts;
new tests prove the old snapshot is rejected rather than implicitly repaired.

## Verification

- Thirteen new tests pass: source/recurrence coalescing; two-root fan-out without
  child creation; generated-task edits and stale admission; compatible replay;
  public preview rollback; standalone item writes; binding retirement; merged
  flags/continuation reset; old-page CAS and delete/reinsert ABA; nested/outer
  rollback; invalidation-failure atomicity; unrelated writers/read-only idle;
  deterministic two-connection interleaving; indexed EXPLAIN plans and transaction
  guards. (Several tests cover more than one listed obligation.)
- Both historical lifecycle witnesses and the live R3 differential pass. The
  previously stale independent-reminder adoption case passes after explicit
  readback. Six selected modules pass typing; changed-file Ruff passes.
- The 68-test lifecycle/edge selection initially exposed one real regression:
  redundant new-child lookup work exceeded the existing 100,000-instruction guard
  for a delayed rdate after three source revisions. The obsolete first full run
  was stopped rather than treated as a result. Initial binding/relation IDs and
  new item/owner allocations now avoid impossible dependency queries; no limit or
  expected result changed. The exact bounded case plus all new invalidation and
  transaction-state tests pass (25 tests). A fresh full run follows the correction.
- The first completed full run reported 1,609 tests with two errors, two failures
  and one skip. Residuals were two shared-helper consumers missing the new readback
  alias, one remaining happy-path adoption request using the old catalog, and the
  frozen body inventory requiring the explicit single-function R3 amendment above.
  All 23 targeted residual/invalidation tests pass after those narrow corrections;
  a fresh full run follows below. No runtime limits or domain expectations were changed.
- Final full regression: **1,609 tests in 474.773 seconds, OK (one skipped)**.
  The complete 68-test lifecycle/edge selection passes, as do 32 documentation,
  declaration, web-sync, dependency and transaction-state tests. Six selected
  modules pass typing; changed-file Ruff, 393 local links and diff hygiene pass.
  Both unrelated file hashes and original frozen fixtures are unchanged. This
  increment is uncommitted; no push, deployment, public activation or send occurred.

## Still required for R3 closure

Intent/enrollment queue production; proven page acknowledgement; complete writer
and direct-binding assignment-aware admission coverage; fresh source/owner/intent
proof inside every actual send-attempt transaction; protected work-state/race
tests; fair bounded automatic planning, horizon rollover and catch-up; repeated
idle/blocked zero-write cycles. The dirty queue alone does not make stale sends
safe and is not evidence of automatic generation. Public activation stays in R4.
