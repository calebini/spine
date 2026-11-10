# Recurring related tasks: R1 checkpoint

Date: 2026-11-10. Non-normative implementation evidence for SPINE-092.

## Boundary

The ratification and delivery plan were committed as `5ed85be`. This checkpoint
implements the internal persistence and source-identity substrate, not the public
recurring-task command family. The accepted specifications remain authoritative.

Normal initialization, migration, package version and implemented declarations
remain at the existing `0.11.2` / schema `19` baseline. The source descriptor still
has `runtime_implemented=false` and `ledger_schema_version=null`. No new command
is registered, no scheduler dispatch is added and no existing item is enrolled.

`spine.ledger.recurring_task_migration.install_candidate` is an explicit developer
test entry point requiring `disposable_test_ledger=True` and an idle ledger
connection. It installs the next free ordered migration, candidate **20**, only on
disposable schema-19 ledgers. The candidate marker makes ordinary schema-19
writers refuse that ledger; it is not a supported deployment path. Reopened test
connections explicitly call `attach_candidate` to arm transaction finalization.
R4 must integrate normal initialization/migration, connection arming, manifests,
package/contract declarations and public registration together.

## Implemented substrate

- All 15 physical tables, 27 history/header triggers and 11 explicit indexes:
  the nine normative access indexes, the pending-adoption unique index, and a
  source-lineage copy lookup index on the existing recurrence ledger.
- Deferred same-root/current-pointer FKs; unique owner/key, assignment sequence,
  selector reservations, child identities and generation predecessors; canonical
  immutable payloads, contiguous revisions and monotone restoration vetoes.
- Eight new identity derivations, configuration/state hashes, immutable decoding
  and delegation to the existing command, recurrence and notification algorithms.
  All **110** published identity/preimage vectors are exercised by runtime helpers.
- No helper commits. The existing outer transaction validates touched rows and
  either commits the complete reference graph or rolls it back. Unchanged
  schema-19 connections do not arm these hooks.
- Atomic additive migration with metadata fingerprints, explicit migration-time
  integrity/FK checks, interruption rollback and preservation of old table bytes.
  Candidate routine verification reads schema metadata only.
- Bounded row/component/hop accounting for pinned source membership and stored
  one-to-one lineage; daily/weekly/monthly/yearly recognition, COUNT subtraction,
  complete union contributors, original versus expressed time, and conservative
  added-date novelty. Missing/changed/ambiguous evidence is not guessed identity.

## Verification and ownership

`tests/test_recurring_task_storage.py` proves actual fresh/populated SQLite
migration, rollback at four stages, version refusal, metadata drift, FK/unique/
counter/preimage rejection, historical decoding, exact initial binding/ownership
witnesses, intent/outcome/progress/catalog/queue persistence and indexed keysets.
Separate connections exercise reservation/CAS contention and physical predecessor
uniqueness. The latter explicitly isolates the SQL constraint with FKs enabled;
it is **not** end-to-end restoration admission evidence, which remains R2/R3 work.

`tests/test_recurring_task_sources.py` exercises actual existing public source and
related-task producers, stored selectors/children/lineage, old-seed recognition
without occurrence expansion from seed, correct fresh copy evidence, COUNT split
arithmetic, unions, move/exclusion identity, positive added dates, alias rejection
and finite-budget failure. Correct COUNT-copy facts are newly authored synthetic
facts using the registered normalizer/ID/persistence helpers, not repairs to
existing history or a claim that the current generic producer emits those facts.

These introduce real RRT-01/04/05/18 foundation evidence. They do not close all
18 end-to-end runtime obligations or change source-only fixture status. Mutation,
restoration, authorization, idempotency/audit receipts, invalidation, delivery
admission, scheduler fairness and public exposure still belong to R2–R4.

Verification results:

- Full regression run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`
  — **1,305 tests passed, one skipped**. Final R1 witness/decoder/query-plan
  assertions were then covered by the final targeted run below.
- Final selected regression run: **105 tests passed**, including **25** new R1
  tests, all 24 source-only family contract tests and the existing command,
  recurrence, binding, documentation and implemented-declaration regressions.
- Focused Ruff: passed. Strict mypy on the four new core/ledger modules with
  `--follow-imports=silent`: passed. Changed documentation targets and
  `git diff --check`: passed.
- The full run emitted non-fatal Python 3.14 resource/read-budget callback
  diagnostics and expected timezone-substitution diagnostics; unittest returned
  success. No unrelated warning cleanup was included.

R1 implementation and tracking changes were committed as `bc96a1d` after operator
approval. No push was performed. The R1 producer findings below describe that
checkpoint; the [R2 follow-up](recurring-related-task-r2-foundation.md) records
prospective fixes separately, without rewriting those historical findings.

## Delegated producer seams retained for R2

The actual public `recurrence.instance.add` path copies a segment while retaining
`source_revision_id="initial"`. Its parent pointer and copied child lineage exist,
but it does not supply the predecessor revision required by the ratified copied-
segment predicate. R1 returns `source_continuity_unresolved` for that copy proof.
Exact-selector identity is a separate valid path and remains usable; this is not
a claim that every added date invalidates existing assignments.

The generic `derive_recurrence_lineage` matcher also compares child semantics
exactly. A valid COUNT split changes `start_bound` and remaining count, so that
matcher alone does not emit its unchanged-stream copy correspondence. R1 can
verify correctly authored stored evidence, including the count subtraction, but
does not invent the missing producer fact.

Before relying on these mappings in the R2 engine, select a narrow, forward-only
producer follow-up: correct newly produced ancestry and explicitly established
COUNT-copy lineage, with actual public-command regression tests. Do not rewrite
old revisions, relabel old lineage, accept equal ordinals/nearby times as identity,
or broaden retarget authority. A generic original-time shift without an
authoritative per-occurrence retarget fact remains unresolved by design.

No live ledger, operator environment, real recipient, notification adapter or
external reviewer was used in this checkpoint. AGENTS.md was preserved unchanged.
