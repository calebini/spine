# R2 page boundaries and lifecycle follow-up

Date: 2026-11-11. Internal candidate only; **R2 remains in progress**.

The operator requested committing the ownership-bootstrap increment and continuing
R2. Bootstrap was committed as `3836bd9`; the unrelated `AGENTS.md` edit was
excluded. The operator subsequently requested checkpointing this follow-up before
continuing R2. That checkpoint does not activate a release.

## Implemented in this increment

- Byte-driven continuation sizes the complete success envelope, including command,
  receipt and audit IDs, policy mappings and the authenticated continuation.
  Whole-unit savepoints remain under one outer transaction until the final response
  fits. Oversized suffixes roll back in reverse order, together with ownership
  markers, work, intent outcomes and Python finalizer state. Accepted units are not
  executed a second time; proof work already performed is not refunded. A page
  that cannot contain one complete result fails without writes.
- Final progress, intent completion, catalog advancement and cursor construction
  share a rollback scope. A tentative completed intent cannot survive a byte
  boundary that removes one of its outcomes. The final receipt uses the same
  envelope projection as the byte planner. Dry run retains its ordinary no-write
  semantics.
- The transaction helper permits explicitly opted-in nested unit scopes with
  unique depth-local savepoints. Ordinary implicit nesting remains rejected.
  Regression tests cover inner/outer ownership rollback and one-epoch behavior.
- Restoration retains the assignment's original managed baseline, separately from
  the customized fields copied into its successor. Previously a copied custom
  title became the baseline and could be overwritten by a later unrelated rule
  edit. The new test restores an individually titled task and subsequently adopts
  a priority-only rule change without losing that title.
- Generated/adopted archetypes retain the exact supplied selection-source and
  optional source reference. Three-way comparison includes those facts rather
  than manufacturing `explicit`. Primary-location comparison uses the owning
  authoring contract's `create` mode rather than an unsupported `inline` mode.

## Actual transaction evidence

New tests exercise:

1. Multi-page byte continuation, bounded full receipts, replay, no duplicate task
   generations, and no suffix owner/work/finalizer residue.
2. Byte boundaries during adoption, including dry run and pending high-water intent
   preservation after suffix rollback.
3. A result that fits by itself but whose full receipt cannot fit: page rollback.
4. Simultaneous candidate, assignment, mutation, work, proof/hop and byte limits,
   retaining both reminders of a two-policy task as one indivisible unit. This is
   a combined-case test, not exhaustive proof/hop boundary coverage.
5. Restoration baseline preservation across a later three-way adoption.
6. Exact due equality at restoration/adoption commit: no writes on stale
   evaluation; a fresh overdue adoption is skipped rather than authorized by an
   earlier evaluation.
7. Two physical connections racing to restore one assignment: one successor,
   one stale loser, and compatible winner replay.
8. Complete managed-set clearing (summary, source reference, priority, assignees,
   archetype, primary location and family reminders), preserving independently
   authored reminder intent/destination and immutable historical location rows.
9. Both suppression-first and restoration-first stale-request interleavings across
   two physical connections, with no suppression retargeting or duplicate child.
10. Explicit nested savepoint opt-in and ownership/finalizer rollback.

Final focused command/page/bootstrap selection: **60 tests, OK**, 23.138 seconds.
Four touched R2 modules pass focused strict typing; all touched runtime/tests pass
Ruff. Frozen web-contract copies remain synchronized; 362 local documentation
targets exist; `git diff --check` passes. Full regression: **1,380 tests, OK
(one skipped)**, 348.468 seconds, using `PYTHONPATH=src:tests`. The known non-fatal
read-budget finalization diagnostic and timezone-substitution diagnostics appeared;
no test failure was reported. The unrelated `AGENTS.md` change retains its
pre-existing SHA-256. The operator requested committing this verified continuation;
no push or activation is authorized by that checkpoint.

## Remaining R2 exit work

Subsequent restoration work is recorded in the
[restoration follow-up](recurring-related-task-r2-restoration.md); use its newer
evidence and remaining list rather than restarting the work below.

Do not infer whole-family conformance from this checkpoint. Still required:

- Full restoration customization and independent-policy matrix, including adopted
  location/archetype/facet/offset and individually changed reminder behavior.
- Complete proof/hop/source-candidate budget adversaries and one-unit cases, beyond
  the existing fail-closed and selected combined cases. Exhaustive effect/reason,
  reference/cursor/error-precedence, intent selection and coverage matrices.
- Historical replay evidence after later lifecycle/configuration changes, remaining
  read-budget adversaries, wider adoption races and source continuity/novelty cases.
- Broader provable calendar-day reminder lead support identified in the foundation,
  and the complete R2 exit matrix against the ratified corpus.

No public command registry, package/schema version, normal migration, live ledger,
automatic scheduler, delivery adapter or web-admission capability was changed.
R3 and R4 remain separate, unstarted gates; no deployment or push was performed.
