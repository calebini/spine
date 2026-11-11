# Recurring related tasks: R2 manual-engine increment

Date: 2026-11-10. Non-normative implementation evidence for SPINE-093.
**R2 remains in progress; this is not a release or complete conformance claim.**

## Checkpoint

The operator requested committing the verified foundation and continuing R2.
The foundation is committed as `250b4fa`; no push was requested. The operator
requested checkpointing this subsequent increment before staging the bootstrap
draft review. The pre-existing `AGENTS.md` change is excluded.

Normal schema/package declarations remain `19` / `0.11.2`. All seven handlers
are internal, require an explicitly enabled disposable candidate-20 ledger and
injected source contracts, and remain absent from public/worker/web dispatch.
No existing/operator ledger, deployment, adapter send or external audit was used.

## Implemented paths

Manual reconciliation composes actual ordinary tasks, selected-occurrence
follow-source bindings, `part_of` relations, explicit owner headers/history,
profile applications, presentations, policies and work in one owning transaction.
Task identities are generation-seeded, while owner/application/audit/receipt
attribution retains the real outer command. Owner creation precedes actual-item
disclosure validation. The access epoch advances once per creating page; no
creator entitlement, membership, grant or disclosure authorization is inferred.

The selected cases exercise source moves, positive exclusion evidence, source-only
cancellation, linked successor restoration, permanent assignment suppression and
completion vetoes. A fresh explicit reconcile does not duplicate existing tasks
or reminder intents. Compatible replay and previews retain the foundation rules;
the committing clock rejects a page whose proposed new due has elapsed.

Three-way managed-field comparison evaluates D=B first. Tests cover preserved
individual wording, changed priority, overlap conflicts and explicit correction,
new-only edits, complete reminder-set additions with retained old intents, and
all retirement dispositions outside the new-generation horizon. Intent outcomes
are immutable; completion uses missing-outcome and retained-conflict evidence.

Existing assignments have a separate sequence lane. Source selection is bounded,
uses original selector ordering, merges moved overrides and seeks catch-up starts.
Positive membership/lineage remains in the R1 proof owner; ambiguous topology does
not authorize a new child. Continuations bind post-page generations and preserve
the first evaluation/expiry. Progress is written with semantic work, not merely
for a later observation time.

Whole-unit work/mutation boundaries use an inner savepoint **inside** the owning
command. `LedgerConnection.command_unit` restores Python finalizer trackers with
SQLite rollback. It cannot commit, run outside an outer command or nest. An
oversized indivisible unit still fails and rolls back the page. Recurrence kernels
have optional work-charge callbacks; existing callers retain their default path.

## Verification ownership

`tests/test_recurring_task_reconcile.py` adds actual internal-handler tests for
creation/ownership/epoch, replay/no duplicates, stage-by-stage rollback, preview,
commit cutoff equality, source move, exclusion/restoration, suppression, source
pages, distinct profile policies/work, three-way adoption and conflict resolution,
new-only edits, all retirement dispositions, reminder-set adoption, completion,
capacity rollback and a one-work-row page with tracker-safe rollback.

All test ledgers are disposable. Source changes use ordinary version allocation
and actual recurrence normalizers/persistence, not caller cancellation certificates
or mutations of stored historical selectors. Offline contract artifacts and review
evidence remain unchanged. This does not replace the remaining R2 proof matrix.

Final verification for this increment:

- Full regression: **1,344 tests, OK (one skipped)**, 325.604 seconds.
- Direct R1/R2/contracts/transaction selection: **91 tests, OK**; overlapping
  writer/people/rendering/lifecycle selection: **73 tests, OK**.
- All **80** deterministic source-only artifacts reproduce unchanged.
- Focused Ruff, compilation, seven local Markdown target sets and diff hygiene pass.
- Strict mypy passes for the internal command engine, five new service modules,
  two changed pure recurrence modules and source-proof module (nine files).
  Extending that check to the existing transaction/profile modules exposes four
  pre-existing errors on unchanged lines (bare dict/add-return callbacks and an
  untyped historical decoder); no broad typing cleanup was included.

The first full run found two missing writer-inventory registrations. The fix adds
the actual child create/change allocation call sites and policy writer, then runs
them in the shared empty/eight-facet and people/rendering parity harnesses. The
rendering harness verifies additive candidate-20 objects rather than attempting
its predecessor migration backwards. Caps were not raised to pass these tests.
The final full run above passes. Existing non-fatal Python read-budget callback
and expected timezone substitution diagnostics remain visible.

## Remaining exit work

This is the historical manual-engine checkpoint. Ownership bootstrap has since
been implemented and committed as `3836bd9`; see the
[bootstrap evidence](ownership-bootstrap-r2-checkpoint.md). The
[2026-11-11 page/lifecycle follow-up](recurring-related-task-r2-page-closure.md)
implements full-envelope byte-driven continuation and records the current,
narrower exit list. The original checkpoint's remaining list follows for history.

- Finish exact between-unit **response-byte** continuation and all combined
  proof/hop/candidate budgets. The current hard byte cap safely rolls back an
  oversized page; that is not yet complete byte-driven pagination.
- Finish the full restoration customization/independent-policy matrix, complete
  managed-set clearing/replacement cases and source continuity/novelty adversaries.
- Complete intent selection/coverage projections and the exhaustive closed
  effect/reason/error-precedence matrix, including referenced-row/cursor ordering.
- Prove strict-future restoration/adoption edges and real separate-connection
  reconciliation/suppression/adoption races, not just storage uniqueness tests.
- Resolve the ordinary local ownership/bootstrap seam: generation currently
  fails closed when `ledger_access_state` is absent rather than fabricating an
  identity realm. Tests explicitly provision a synthetic access realm. No new
  account/realm policy or implicit web provisioning is authorized by this code.
  The operator subsequently selected realm-independent bootstrap; the
  [new draft](../../specs/local-ownership-bootstrap.md) records that direction,
  reuses the existing epoch and leaves ratification/machine closure pending.
- Complete historical replay evidence and all read/budget adversaries, then rerun
  the complete R2 exit matrix. Broader provable calendar-day reminder lead support
  from the foundation also remains open.

No RRT obligation is marked wholly closed from this increment. R3 all-writer,
attempt-start and automatic scheduling work, and R4 public activation, remain
separate gates. Do not deploy or advertise this internal family.
