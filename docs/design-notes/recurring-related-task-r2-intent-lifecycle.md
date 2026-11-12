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
