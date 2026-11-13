# R2 intent and lifecycle continuation

Date: 2026-11-12. Implementation evidence for SPINE-093, not a normative contract
or a complete R2 conformance claim.

## Boundary and checkpoint

The preceding admission/read increment is committed as `002d24a`. That commit
excluded the pre-existing `AGENTS.md` and restoration-note edits; both remain
preserved. No push occurred. The operator then selected continued manual
reconciliation and lifecycle work under the approved R2 plan.

This continuation changes internal services only. The source-only command family,
normal runtime/schema declarations, public registry, worker and web surfaces are
unchanged. All execution uses disposable ledgers; no live migration, delivery,
deployment, RF3/R3 work or public activation is included.

## Corrected cases

- A source cancellation performed during upcoming-open adoption records the
  assignment's terminal skip in that page, rather than leaving the finite intent
  without an outcome until an extra reconcile.
- Restoration selected from a source-cancelled predecessor retains that
  predecessor's adopted configuration and actual choices. A pending newer
  template is not implicitly applied to the restored task. The skip and restored
  assignment witness are committed in the same bounded unit.
- An immutable non-conflict outcome is final for that intent. In particular, an
  overdue skip cannot repeatedly intercept later source following when another
  assignment keeps the intent pending. Conflicts remain eligible for resolution.
- Generation and existing-assignment coverage use their own page results.
  An existing-task conflict does not falsely mark a completed generation scan
  as blocked. Pending conflicts remain visible in intent coverage on subsequent
  pages, even when the conflicting assignment is not on that page.
- Adoption and retirement coverage are reported independently, including
  `keep_following` retirement with a preserved adoption intent. Intent processed
  counts intersect the existing-assignment lane with each immutable high water;
  newly generated assignments do not inflate adoption counts.

Completion still uses the existing bounded missing-outcome/conflict proof. This
increment does not replace it with a row count, mutate prior outcomes, or declare
unresolved conflicts complete. Receipt replay preserves the original result and
does not add rows.

## Verification

`tests/test_recurring_task_intent_lifecycle.py` adds seven actual internal-command
regressions covering the cases above, finite pagination, generation above an
adoption high water, and byte-identical stored-result replay (apart from the
required replay flag). The first five tests reproduced failures before the
service changes. Focused verification with the existing reconciliation and
frozen shared-runtime witnesses passes **38 tests**, 18.470 seconds. Final full
regression: **1,477 tests, OK (one skipped)**, 393.779 seconds. The known non-fatal
read-budget callback and expected timezone-substitution diagnostics appeared.
Focused Ruff, two-module typing, frozen web copies, 244 unique local documentation
targets and diff hygiene pass. Public activation files have no diff. Preserved
`AGENTS.md` and restoration-note SHA-256 values are unchanged. This continuation
is uncommitted; no push or external review occurred.

## Remaining R2 exit work

R2 remains in progress. These cases do not close the broader lifecycle matrix:

- Conflict-resolution sequences involving cancellation, restoration, retirement,
  changed ownership or unavailable disclosure/route evidence still need exact
  durable-state and finality proofs. A missing outcome must not be mistaken for
  completion, nor may a blocked cleanup be recorded as successful retention.
- Broader adoption/retirement/suppression races, combined budgets and rollback
  boundaries, plus the remaining customization/source-continuity adversaries.
- Provable calendar-day reminder lead support and accurate finite-source
  exhaustion reporting, without unbounded historical expansion.

The existing [admission/read evidence](recurring-related-task-r2-admission-reads.md)
and [page-boundary evidence](recurring-related-task-r2-page-closure.md) retain their
earlier proofs and outstanding obligations. No RRT family is marked fully closed
by this increment. RF3/R3 and public activation require their own gates.

## Blocked intent resolution continuation — 2026-11-12

The preceding increment was committed as `d61571e` after operator authorization,
excluding the unrelated `AGENTS.md` and restoration-note edits. No push occurred.
The following work remains uncommitted and continues R2 only.

### Closed paths

- A failed route/disclosure child operation first rolls back its entire unit,
  then records only the blocked assignment state and immutable intent conflict.
  No partial task/policy/work mutation survives. This fallback itself consumes
  a mutation unit, participates in response-byte rollback, and retains the actual
  family policy mapping. Repeating unchanged blocked evidence does not append
  duplicate states/outcomes.
- Cancel/detach retirement records an ownership-blocked cleanup as a conflict,
  never successful retention. It remains pending until actual terminal or
  independent-state evidence resolves it. Keep-following retirement remains
  distinct from a preserved adoption intent's success or failure.
- Exact source-cancelled state resolves a prior adoption conflict without
  overwriting the original conflict row. Restoration carries forward the intent
  reference. Resolution uses primary-key predecessor reads through the current
  state's immutable same-intent lineage; every read consumes proof budget.
  Later restoration/following cannot reopen an already-final skip simply because
  the latest operational reason changed. Evidence from another intent is not
  accepted. No new state shape, table, migration or history rewrite is introduced.
- Overdue resolution of a prior conflict now appends the actual governed skip
  witness, rather than leaving the earlier decision-required reason unchanged.
- An actual six-child profile-adoption recovery exposed colliding profile-policy
  link IDs. The recurring composition supplies its per-application identity seed
  through the existing profile persistence owner. The optional parameter defaults
  to the existing derivation for ordinary callers; real outer-command attribution
  is unchanged. No public request or response shape changes.

### Added verification

Nine additional tests extend the lifecycle file to sixteen cases. They exercise
real route drift/recovery, unchanged blocked no-ops, controlled disclosure-owner
rejection/recovery, preview and audit/receipt-fault rollback, mutation and byte
boundaries, ownership-conflicted retirement followed by explicit task completion,
source cancellation resolving a prior conflict, multi-conflict restoration and
overdue/move sequences, and a two-connection adoption-versus-retirement race.
The race admits one winner, gives the loser a stale-version result, preserves
the winning command's replay without writes, and checks foreign keys and finite
intent/generation counts. The history proof also has a low-budget failure check.

Focused lifecycle/reconcile/shared-runtime/frozen-child verification passes
**48 tests**, 26.746 seconds, followed by the passing low-budget proof regression.
Full regression: **1,486 tests, OK (one skipped)**, 394.880 seconds. Four touched
service modules pass typing; focused Ruff, frozen web copies, 244 local link
targets and diff hygiene pass. The known non-fatal read-budget callback and
expected timezone-substitution diagnostics appeared. The earlier frozen baselines
were not regenerated to accommodate these changes. Public activation files have
no diff; the unrelated `AGENTS.md` and restoration-note hashes remain unchanged.

### Still open

This closes the selected blocked-outcome/finality cases, not every R2 exit gate.
Broader reminder-lead/calendar-day support and finite-source exhaustion, remaining
customization/source-continuity and combined-budget matrices, and additional
cross-connection interleavings remain tracked R2 work. RF3/R3, public activation,
live ledgers, migration, sending and deployment remain outside this continuation.

## Finite-source exhaustion continuation — 2026-11-12

The blocked-intent increment was committed as `0f2aeec`, preserving both unrelated
edits. No push occurred. The following continuation is internal R2 work and remains
uncommitted.

### Scope

- Completed manual pages can now distinguish `source_exhausted` from `waiting`.
  The proof uses the evaluation instant, not the horizon's end: an empty current
  window is not evidence that a sparse or future source has ended.
- The core helper reuses pre-exclusion candidate arithmetic, including COUNT,
  inclusive UNTIL, exclusive segment bounds, segment-start clipping, omitted
  invalid calendar dates and nonexistent local times. It does not enumerate all
  historical occurrences. Local evaluations use the pinned source timezone.
- Active future rdates or moved occurrences prevent an exhaustion claim, including
  moves beyond the generation horizon. Unknown/unbounded futures remain waiting;
  exclusions do not prematurely consume COUNT. This is a conservative proof, not
  an exhaustive search for the next surviving occurrence.
- Calendar preparation and child inspections consume the existing proof budget.
  Incomplete lanes, blocked pages and retired rules preserve their prior precedence.
  Repeated exhausted observations do not write progress or audit rows. Explicit
  commands retain their ordinary command receipts; no automatic loop is added.

### Verification

Ten new tests cover count/until boundary equality, segment clipping, invalid month
days, leap-day yearly gaps, DST omissions, pinned local-time conversion, bounded
arithmetic for old rules, future additions/moves, actual manual source-following,
read-only proof budget failure and repeated exhausted no-op reconciliation.
The initial eight tests plus existing reconciliation/lifecycle and frozen witnesses
passed **56 tests**, 28.620 seconds. The final ten-test file passes, as do focused
Ruff and three-module typing. Full regression passes **1,496 tests, OK (one skipped)**,
420.159 seconds. The known non-fatal web read-budget callback and expected timezone
substitution diagnostics appeared. All 244 unique local documentation targets and
diff hygiene pass.
Frozen web copies and public activation files are unchanged; preserved unrelated
edit hashes match the preceding checkpoint. No frozen witness was regenerated.

### Remaining boundary

This does not close R2. Provable calendar-day reminder lead support, remaining
customization/source-continuity and combined-budget matrices, and additional
cross-connection interleavings remain tracked work. No RF3/R3, public activation,
schema migration, live ledger access, notification send or deployment is included.

## Calendar-day reminder leads — 2026-11-12

The finite-source increment was committed as `e87c9d6`, excluding the unrelated
edits. The operator then selected calendar-day reminder leads and remaining R2
work. This continuation is internal, uncommitted and does not activate R3/R4.

### Proof and persistence boundary

Calendar-day once/offsets/bounded-repeat templates now admit when their earliest
source-relative reminder has a bounded proof. Create/update supply the current
recurrence time facts; elapsed-only validation retains its previous arithmetic
and does not read timezone data. No wire, configuration hash, stored shape,
schema version or ordinary notification-resolution semantics change.

For a task instant `T`, its source instant `S`, and a calendar reminder `R`:

```
T = S + task_offset
R - T = days*86400 + reminder_clock - task_clock
        + task_utc_offset - reminder_utc_offset
```

The proof ranges `task_clock` over `0..86399`, including possible moved-source
times and midnight-crossing task offsets. Offset extrema come from the exact
version-verified TZif bytes, including every historical type and both POSIX-footer
offsets. No recurrence history or future year range is enumerated, no contemporary
sampling substitutes for future rules, and only byte-derived parsing is cached.
Provider version/evidence checks still run. Existing capture size/type limits bound
the work; unavailable evidence fails closed.

The result is a **conservative upper bound**, not a promise of the smallest horizon
for a particular series. Short horizons without this proof are rejected, not
silently widened. A calendar label in another zone still uses the task's local
date, exactly as the existing notification resolver does. Gap omission and
earliest-fold resolution remain owned by that resolver.

Same-zone calendar repeat boundaries can be ordered by their shared-date local
labels; elapsed boundaries retain their exact ordering. Mixed-zone/mixed-basis
windows require disjoint proven UTC-offset intervals. An unprovable window or
absolute reminder is rejected under the existing configuration-conflict contract.
The existing R2 strict start-before-stop admission is preserved.

Before a new assignment is created, reconciliation rechecks the lead under its
current source time facts. An insufficient proof yields `configuration_invalid`
without a partial child. Existing-task following, cancellation and restoration do
not depend on a rolling generation horizon and are not blocked by that check.
This is a manual R2 boundary, not an implementation of the deferred all-writer
invalidation/automatic-worker path.

### Verification and preservation

Fourteen new tests cover bound equality and one-second rejection; positive and
negative task offsets; same-zone and mixed repeat windows; earliest mixed offset
selection; absolute/unavailable-evidence rejection; actual resolver comparisons
across DST, date-line jumps and future footer dates; omitted gaps/earliest folds;
synthetic footer-only offsets; and unchanged elapsed-only behavior.
An unsupported/missing exact source-time context produces a structured
configuration conflict rather than a timezone lookup/runtime exception.

Disposable command tests exercise create/update no-write rejection, stored replay
without reproof, real calendar work/no-duplicate reconciliation, a local recurring
source across DST, upcoming-open adoption, source cancellation and fresh-generation
restoration with prior task history preserved. A projection-seam injection checks
changed-source timezone rejection before child writes; this is not represented as
full source-writer integration evidence.

The initial eleven tests plus existing admission/read, frozen-child and shared
runtime tests pass **56 tests**, 36.146 seconds. The final fourteen-test calendar
file passes separately, 2.644 seconds. Existing timezone compatibility pytest checks
pass **39 tests**, 2.13 seconds;
five-module typing, focused Ruff and frozen web copies pass. Final full regression:
**1,510 tests, OK (one skipped)**, 406.749 seconds. Known non-fatal web read-budget
callback and expected timezone-substitution diagnostics appeared. All 245 unique
local documentation targets and diff hygiene pass. The earlier full run was
stopped deliberately before adding the final source-basis guard; this reported
result is the fresh complete run against the final code.

The original RF1 baselines and prior admission amendment are unchanged. A separate
[two-body calendar amendment](../../tests/fixtures/internal_operations/r2_calendar_lead_body_amendment.json)
hash-pins only create/update's intentional source-context plumbing on top of the
prior amendment. The guard still requires one complete accepted body set and
preserves all unrelated hashes. No public registry, packaged contract, package
version or migration is changed; both unrelated working-tree hashes are preserved.

R2 remains open for remaining customization/source-continuity, combined-budget
and cross-connection proof matrices. No push, external audit, live ledger access,
send, deployment, RF3/R3 or public activation occurred.

## Customization, delayed continuity and exact budgets — 2026-11-12

Calendar-lead work was committed as `09a2c8e`, excluding both unrelated edits.
The operator selected the remaining R2 customization, continuity, budget and
concurrency cases. This continuation is internal and uncommitted.

### Corrections proved by regressions

- A fresh generation now preserves the predecessor's actual `completion_state`
  and optional defer anchor, alongside the already-preserved title, summary,
  source reference and priority. The defer fact gets a deterministic new anchor
  ID, not a reused row ID; explicit clears remain clear. Completed/cancelled
  status and completion actor/time are not copied into the new open task.
  No task-template configuration or wire field was added.
- Implicit recurrence segment copies now name their immediate predecessor as
  `lineage_parent_segment_id`. Previously the second and subsequent copies kept
  an older ancestor, so authentic public `recurrence.instance.add` commands could
  produce a path that correctly failed the strict R2 continuity verifier. The
  correction is prospective; explicit segment authoring is unchanged and no
  historical source row is rewritten or heuristically repaired.
- A first reconciliation delayed beyond an rdate's creation proves its historical
  `new_rdate` birth and then a separate current `carry_forward` chain. Both use
  the existing closed proof shapes. Its birth selector is reserved to the same
  assignment, while current generation/state pin current proof. Every copy must
  still validate; incomplete lineage rolls back the birth proof with the whole
  failed unit, without cancelling other tasks or granting new-slot authority.
- `lineage_hops` now limits each path's depth, as the accepted command contract
  requires. Rechecking a path or proving another task does not consume another
  task's hop allowance. Every traversal still consumes the shared `proof_steps`
  budget, including failed and rolled-back units; no work is refunded. The page
  checkpoint tests continue to prove this non-refund boundary.

### Evidence and preservation

Nine new cases in [R2 edge tests](../../tests/test_recurring_task_r2_edges.py)
cover actual individual details/clears, delayed additions across three public
source mutations, missing copy evidence, low proof/hop rollback, exact three-hop
acceptance versus two-hop rejection, exact proof-step acceptance versus one step
under, and physical first-generation writer races. Distinct command IDs produce
one winner and one stale loser; identical command IDs produce one creation and
one compatible replay. Both leave exactly one reservation/generation per slot.
The public recurrence commands operate only on disposable test ledgers; the
recurring-task command family remains internal.

The original RF2 full-lifecycle fixture remains byte-identical. Its original
results are still reproduced using its historical source-segment producer.
A separate [immediate-parent witness amendment](../../tests/fixtures/internal_operations/r2_immediate_parent_witness_amendment.json)
pins only the second source edit and its downstream identity differences. Create
and first move are unchanged; effect, changed flag and full response byte counts
are unchanged in every amended case. A complete current lifecycle must match the
amended set, not an arbitrary mixture of old/new hashes.

Focused edge/page/witness verification: **24 tests, OK**, 8.304 seconds; the final
source/restoration/reconciliation/preservation selection passes **72 tests**,
31.952 seconds. Both new physical writer races also pass five repetitions each
(10 tests, 4.504 seconds). Focused Ruff, six-module typing, frozen web-contract
synchronization, all 247 local documentation targets and diff hygiene pass. Full-suite
verification initially ran **1,520 tests** (423.038 seconds) with one failure,
one error and one skipped: the older one-hop test still encoded page-cumulative
depth, and its instrumentation still passed the removed consumable-hop argument.
The former now proves one-hop preview acceptance across six assignments, then
actual two-hop rejection/whole-page rollback and exact two-hop acceptance after
another public source edit. The instrumentation retains its mid-page exhaustion
and rollback assertion. The complete admission/read file passes **22 tests**,
28.335 seconds. The fresh complete regression passes **1,520 tests, OK (one
skipped)**, 403.331 seconds. The known non-fatal web read-budget callback and
expected timezone-substitution diagnostics appeared. This closes the selected
edge cases, not whole-R2 exit: the consolidated R2 obligation map and remaining
individual-offset/disclosure/reference-invalidation assessment are not replaced
by these tests. Both unrelated edit hashes and the original frozen fixtures are
preserved. No new public registry, contract/schema/package version, normal
migration, RF3/R3 integration, live access, send, deployment or push is included.

## Individual-offset and reference continuation — 2026-11-13

The operator selected the remaining manual R2 cases and acceptance mapping.
All prior uncommitted work is preserved, including the unrelated `AGENTS.md` and
restoration-note edits. This continuation makes no public activation or schema
change and does not introduce a public individual-offset editing command.

Two related defects were reproduced with canonical lower-owner binding/item
fixtures. Source following calculated the correct individually customized due
time but wrote the rule's original offset into the next binding revision. The
child change operation now preserves the actual prior offset unless three-way
adoption explicitly changes that managed field. Separately, generation validation
required every restoration's offset to equal its adopted rule configuration.
It now compares a restored generation to the predecessor's immutable
source-cancellation assignment/binding witness. First-generation validation still
requires the rule offset. No mutable latest pointer or historical rewrite is
used. A deliberately wrong restoration binding still fails the entire page,
leaving the ledger byte-for-byte unchanged.

[Preservation tests](../../tests/test_recurring_task_r2_preservation.py) cover:

- An individual offset surviving refresh, source move, cancellation and linked
  restoration; explicit offset adoption on ordinary siblings; non-overlapping
  adoption preserving the exception; overlapping offset adoption failing without
  changing the customized task; deep decoding of historical generations.
- Exact existing disclosure reuse without new grants, revoked disclosure and
  inactive delivery-route rejection without partial successors or ordinary
  rendering substitution. Existing referenced-route immutability rejects changing
  the destination under an existing approval; restoration then still uses the
  original destination. This is preservation of the existing route contract,
  not a new route-snapshot mechanism.
- Inactive individual participants and inactive non-queryable facet subject
  references preventing restoration without losing predecessor history.
  Existing facet retirement, primary-location identity and immutable facet-value
  copy tests remain in the restoration suite. Locations have no invented
  active/inactive lifecycle.
- Started-source/future-task catch-up, exact due equality, negative-offset
  past-due exclusion, inclusive selected enrollment across source copying,
  group-owned generated tasks with a distinct assignee and notification
  recipient, and manual cancellation/detachment staying consumed after source
  disappearance/return. Whole-event cancellation cancels its open pickups without
  inventing a terminal-event reopen operation; clearing an occurrence lifecycle
  cancellation restores only its linked task. Ordinary-state fixtures prove manual observation, not
  the deferred automatic all-writer invalidation boundary.

### Consolidated manual R2 acceptance map

This map supersedes earlier checkpoint lists of outstanding **manual R2** work.
It does not ratify public activation or close cross-slice RRT obligations. The
machine descriptor remains `pending_runtime_verification` for final R4 replay;
R3's automatic writer/attempt/scheduler evidence remains separate.

| Obligation | Executed manual-engine evidence | Later boundary not claimed |
| --- | --- | --- |
| RRT-03 — transaction/replay | [Command tests](../../tests/test_recurring_task_commands.py): authoring faults, preview and replay before fresh checks. [Reconciliation](../../tests/test_recurring_task_reconcile.py): all child-stage rollback, full receipt sizing and replay. [Restoration](../../tests/test_recurring_task_restoration.py): task/owner/binding/policy/work/audit/receipt fault matrix. | Installed public adapters and scheduler invocation. |
| RRT-04/05 foundation — source identity | [Source tests](../../tests/test_recurring_task_sources.py): actual selector membership, union, COUNT split/copy, retarget rejection and missing lineage. [Edges](../../tests/test_recurring_task_r2_edges.py): delayed positive rdate birth/copy, incomplete-history rollback and path depth. | Every automatic source writer/attempt seam. |
| RRT-06 — enrollment/discovery | Preservation tests: upcoming and selected enrollment, started-source catch-up and negative offsets. Reconciliation: moved-source and paged candidates. Edges: delayed additions. [Horizon tests](../../tests/test_recurring_task_horizon.py): COUNT/UNTIL/segment exhaustion, sparse sources and future moves/additions. | Continuous automatic scheduling. |
| RRT-07 — strict future | Reconciliation: initial, restoration and adoption equality-at-commit rollback. Command tests: backward clock and preview sampling. Preservation: enrollment equality and past-due exclusion. | Worker attempt-start race. |
| RRT-08 — child/owner identity | Reconciliation: deterministic generations, exact owner history/access epoch before policies, realm-independent bootstrap and no duplicate tasks. Preservation: group ownership remains distinct from assignee/recipient and creates no grants. | Public activation/package verification. |
| RRT-09 — policies/intents | Reconciliation: multiple distinct policy tokens and explicit adoption. Restoration: modified family/independent reminders, disabled reminders, retained profile pins and repeated successors. [Calendar leads](../../tests/test_recurring_task_calendar_leads.py): DST-aware admission, actual work, adoption and restoration. | Automatic work dispatch/attempt safety. |
| RRT-10 — cancellation/restoration | Reconciliation: source exclusion, linked successor, suppression and both physical interleavings. Restoration/preservation: actual custom facts, offset history, manual cancel/detach vetoes and no partial invalid successor. | Automatic invalidation from every ordinary writer. |
| RRT-11 — adoption | Reconciliation: D=B, overlaps, empty clears and new-only. [Intent lifecycle](../../tests/test_recurring_task_intent_lifecycle.py): immutable high-water outcomes, final skips, conflict recovery, cancellation/restoration and adoption/retirement race. Preservation: offset branches. | Immediate release/blocking at attempt admission. |
| RRT-12 — retirement | Reconciliation: all three dispositions and overdue/out-of-horizon maintenance. Intent lifecycle: ownership-blocked cleanup, retained following/adoption coverage and physical retirement race. | Source/attempt interleavings under automatic scheduling. |
| RRT-15 — reads/cursors | [Admission/read tests](../../tests/test_recurring_task_admission_reads.py): actual history pagination, exact envelopes, precedence, signed/noncanonical/expired/rebound/cross-ledger cursors and read-only observed-versus-historical truth. [Storage](../../tests/test_recurring_task_storage.py): indexed seek plans. | Installed-wheel registry/transport exposure. |
| RRT-16 — references/authority | Admission/read: reference and ownership errors before stale facts. Intent lifecycle: route/disclosure and ownership conflict persistence. Preservation/restoration: real grants, revoked approval, inactive subject/route/facet references and independent group ownership. | Protected transport/public admission and all-writer invalidation. |
| RRT-17 — bounds | Reconciliation: combined candidate/assignment/mutation/work/byte limits, complete reminder units and one-unit overflow. Admission/read: exact read bounds and mid-page proof exhaustion. Edges: exact shared proof steps and independent hop depth. [Page state](../../tests/test_recurring_page_state.py): SQL/Python rollback, no refunded proof work and no partial finalizers. | Scheduler fairness and attempt budgets. |
| RRT-18 foundation — concurrency | Edges: physical first-generation races for same/different command IDs. Reconciliation: physical successor/suppression interleavings. Intent lifecycle: adoption/retirement race. Storage: predecessor uniqueness/CAS and immutable history. | Automatic writer/worker races. |

RRT-02 (installed activation), RRT-13 (attempt admission), and the scheduler
portion of RRT-14 remain deliberately outside R2. Manual idle/no-progress
observations are tested, but do not establish scheduler fairness or delivery
safety. RF3 extraction and R3 integration are not started by this continuation.

### Final verification and checkpoint

The affected storage/restoration/reconciliation/intent/page/witness selection
passes **102 tests**, 47.889 seconds. The final preservation file passes
**15 tests**, 10.416 seconds. Full regression using the installed pinned Tickerd
and `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover
-s tests` passes **1,533 tests, OK (one skipped)**, 401.367 seconds. Two final
whole-event/occurrence cancellation tests were added after that suite's discovery;
they are included in the passing final 15-test run, not the 1,533 count. Runtime
code was unchanged during that full run. The known ignored HashTrieMap
read-budget callback and expected timezone-substitution diagnostics appeared.

Focused Ruff, seven-module mypy, frozen web-contract synchronization, 269 local
documentation targets and diff hygiene pass. Both unrelated file hashes and the
four original frozen witness hashes remain unchanged. The previous explicit
immediate-parent amendment is retained; this continuation changes no baseline.

The manual R2 exit is complete. This is an internal implementation checkpoint,
not whole-family conformance or release readiness. The changes remain uncommitted;
no push, public activation, live ledger, external send, deployment, normal migration
or RF3/R3 work occurred. The next gate is separately selected RF3 propagation
before the R3 all-writer/automatic scheduling slice, followed by R4 activation
and its complete installed-package replay.
