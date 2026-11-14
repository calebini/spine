# R3 initial increment — coalesced invalidation and queue CAS

Status: initial R3 increment committed as `ffb9690`; acknowledgement/guard
continuation implemented and verified, uncommitted
(2026-11-14). R3 not closed. Current status belongs to [SPINE-094](../BACKLOG.md#spine-094--r3-recurring-task-all-writer-safety-and-automatic-scheduling).

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
  increment is committed as `ffb9690`; no push, deployment, public activation or send occurred.

## Still required for R3 closure

Intent/enrollment queue production; complete semantic page planning, freshness
revalidation and automatic-sweep/continuation routing; end-to-end automatic
catch-up and repeated idle/blocked zero-write cycles. The continuations below add
attempt admission and bounded read-only discovery, but the dirty queue and
discovery alone are not evidence of automatic generation. Public activation
stays in R4.

## Continuation — page acknowledgement and direct-binding guards

Selected explicitly after checkpointing `ffb9690`; no runtime/schema declaration,
public activation, migration path or deployment changes.

### Proven queue coverage

The page captures the dirty generation and its certified assignment prefix in
the same command transaction as source truth. The application acknowledgement
helper advances only a contiguous non-blocked assignment prefix. A continuation
that skipped an earlier blocked assignment cannot clear it. Unreserved, still-
future source candidates preceding the source cursor also prevent clearance:
the cursor alone is not proof of their disposition. Already-due candidates are
not future generation work. Pending adoption/retirement intents prevent a final
clear. A new invalidation in the page's own transaction is deliberately retained;
a subsequent clean proof page can discharge it. Generation CAS remains the final
write boundary, preserving concurrent invalidation and delete/reinsert safety.

Acknowledgement runs inside the final response-sizing trial. Trimming a whole
unit restores both its SQL and page state, including any tentative acknowledgement.
Dry run, receipt failure and outer rollback also restore queue/progress/catalog
state. A successful coverage-only acknowledgement is `rule_page_applied` with the
normal progress/root/catalog update and command audit/receipt. It does not change
tasks, assignments, binding revisions, policies, work, attempts or access facts.
The existing related-item audit trigger still advances the binding catalog once;
it is neither suppressed nor bypassed. Once discharged, retained/idle observations
do not update progress. Explicit commands still retain their required receipts;
automatic no-op suppression is separate scheduler work.

### Assignment-aware ordinary binding admission

The shared application guard is called by `schedule.binding.reconcile`, which is
also the ordinary automatic binding sweep's command path. The candidate gate
keeps existing schema-19 behavior unchanged. An indexed generation lookup leaves
unrelated v1 bindings untouched, including on the private candidate schema.

For generated bindings it requires the latest generation. Existing legal explicit
cancel/detach resolutions remain available and rely on canonical terminal or
retired-binding truth plus atomic invalidation; manual cancellation does not
fabricate source-cancellation evidence or permit restoration. Automatic legacy
maintenance is allowed only for an exactly current governed assignment: current
task/binding/source witness, active scheduled source/open task, unchanged owner
identity/revision, permitted root retirement disposition, no applicable pending
adoption, and bounded positive source membership proof. `keep_following` retirement
retains maintenance. Stale, decision-required, source-cancel/exclusion, archived,
cleanup-pending or otherwise incompatible branches fail before mutation with the
existing `semantic_conflict` / `temporal_binding_id`, directing the caller to rule
reconciliation. Recurring reconciliation remains the owner of moves, positive
cancellation causes, assignment state, intent outcomes and restoration lineage;
the old command cannot reproduce those incompletely. Compatible replay still
precedes fresh guard checks.

### Verification and preservation

- **21 new focused tests pass**: full/partial acknowledgement, blocked assignment
  and source prefixes, stale continuation, self-invalidation, exact write/audit
  boundary, preview/receipt rollback and response-byte trimming; generated current,
  stale, archived, source-cancelled, excluded, pending-adoption/cleanup and retained-
  following cases; explicit manual detach/cancel; replay; exact target witness;
  ordinary v1 move/materialization on the private candidate ledger.
- The candidate direct-binding harness pins only its imported schema-version
  constant to candidate 20. It does not bypass contracts or mutation logic and
  does not change the installed schema-19 declaration.
- Historical no-op tests now distinguish one coverage-only acknowledgement from
  the subsequent unchanged idle page; duplicate/task/reminder/history assertions
  remain. The initial R3 invalidation differential explicitly isolates the later
  acknowledgement feature. A separate live all-table comparison proves exactly
  the allowed acknowledgement write set and independently recomputes receipt and
  audit hashes. Original frozen fixture bytes remain unchanged.
- Changed-file Ruff and the three selected application modules pass Mypy. The
  legacy binding command has existing typing debt: baseline and current each
  report 34 diagnostics under identical isolated Mypy options; no new diagnostic
  is introduced. No broad typing cleanup is included.
- Full regression: **1,630 tests in 476.271 seconds, OK (one skipped)**. The
  32-test documentation/declaration/web-sync/transaction/boundary selection passes
  separately, as do 391 local file links and diff hygiene. Unrelated operator
  edits and the original frozen fixtures retain their pre-work hashes. This
  continuation is committed as `8349a63`; no push, deployment, public activation or send.

## Continuation — automatic discovery and final attempt admission

Selected after `8349a63`. Internal candidate only; installed runtime/schema and
public capability declarations are unchanged. No live ledgers or real sends.

### Final attempt boundary

`ledger.recurring_task_attempts.assert_attempt_current` runs from the shared
`create_started_attempt` insertion path. Candidate work starts acquire a writer
transaction before the final proof; an existing rendered/command transaction is
joined rather than committed early. A caller disabling transaction management
without an active transaction is refused. Work-to-generation resolution uses the
unique task index; unrelated work retains existing behavior.

Admission requires the latest generation, exactly witnessed task/binding, active
source and task, correct active relation, unchanged owner identity/revision,
governed non-veto state, permitted root disposition and no applicable pending
adoption. Source item version/recurrence must match the current witness, and fresh
bounded positive membership plus exclusion/cancellation checks run in that same
snapshot. Proof exhaustion refuses, never cancels. Pending cancel/detach blocks;
keep-following retirement and new-assignment-only configuration edits do not
invalidate otherwise current children. Observed explicitly detached children
return to ordinary work freshness instead of depending on the former source.

This gate only admits a new attempt. It neither cancels protected work nor rewrites
attempts, and does not prevent recording an already admitted attempt's outcome.
Rendered replay remains non-sending. Shared adoption selection moved into a
read-only ledger helper; service callers retain the same exact selection rules.

### Read-only automatic discovery (not dispatch)

`services.recurring_task_planning` owns no durable cursor or progress. The caller
supplies an in-memory root keyset position, advanced even for unresolved or dense
roots. The root budget bounds rows *visited*, not just rows surviving an eligibility
filter. Maintenance selection is independent of source enumeration and survives
a source-proof budget failure. Clean roots do not scan assignment history merely
because completed tasks exist. Active roots still examine the moving generation
horizon, including positive-offset source times before evaluation when the child
is not yet due. Reserved slots, inactive occurrences and overdue children do not
become fresh generation candidates. Retired roots never generate new children.

Manual pages and discovery reuse `SourceWindow` for the same bounded source
expansion and enrollment filtering. Discovery never invokes reconciliation,
command receipts, progress writes, queue acknowledgements or rollback previews.
Tests enable SQLite `query_only`, compare all-table dumps and `total_changes`.
Fingerprints describe snapshot/discovery evidence, not dispatch authority.

**Remaining R3:** complete semantic page planning for changed/retained/blocked
units and transaction-local revalidation before dispatch; enrollment/intent queue
production; continuation routing and integration into the scheduling/Tickerd
path. In particular a persistent dirty marker must not repeatedly trigger a
no-op or blocked command. No automatic mutation dispatch or R3 closure is claimed
by this discovery increment. Public activation stays in R4.

### Verification

Focused discovery/attempt/page/binding/frozen-witness selection: **72 tests pass**
in 40.380 seconds. Includes writer-lock exclusion between proof and INSERT,
source-change-before-attempt, protected retry/outcome preservation, pending
adoption/cleanup, detached independence, superseded generations, owner mismatch,
rendered admission/replay, read-only idle ticks, bounded/fair lanes and rollover.
Seven changed runtime modules pass Mypy; changed-file Ruff and diff hygiene pass.
Full regression: **1,662 tests in 492.392 seconds, OK (one skipped)**. All 32 new
tests are included. The 26-test documentation/declaration/web-sync/internal-boundary
selection also passes, as do 391 local links. Original frozen fixtures and both
unrelated operator edits retain their pre-work SHA-256 values. This continuation
is uncommitted; no push, deployment, public activation or real send occurred.
