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
