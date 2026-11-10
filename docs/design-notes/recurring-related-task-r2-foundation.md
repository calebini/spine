# Recurring related tasks: R2 foundation

Date: 2026-11-10. Non-normative progress evidence for SPINE-093.
**R2 remains in progress.** This is not a complete manual engine or release.

## Checkpoint and authorization

The operator authorized committing R1 and beginning R2, including the previously
identified prospective recurrence-producer fixes. R1 is committed as `bc96a1d`;
AGENTS.md was excluded and preserved unchanged. No push was requested.

R2 changes remain uncommitted. Normal schema/package declarations remain
`19` / `0.11.2`; the new family remains source-only and unregistered. Internal
tests use explicit candidate-20 disposable ledgers and injected source schemas.
No web route, daemon invocation, deployed ledger or delivery adapter is added.

## Prospective source fixes

Default successor segment construction now sets `source_revision_id` to its actual
predecessor revision instead of inheriting `initial`. Explicit normalized inputs
retain their input semantics, including deliberately invalid inputs used by the
independent frozen ancestry tests. Already persisted rows are not rewritten.

Canonical recurrence mutation paths explicitly enable positive stream-copy
lineage. Beyond the old exact-byte match, a following rule may qualify only with
an actual parent segment, unchanged seed/phase/selectors and exact remaining
COUNT arithmetic. Changed streams and non-unique matches remain unproved. The
default lineage helper retains its historical construction behavior for offline
evidence builders; this does not relabel their stored artifacts.

The public following-split test also exposed an existing writer defect:
`_following_rule_copy` passed persisted row identifiers/status into the rule
authoring normalizer. It now projects only authoring fields and uses the existing
count kernel with the authored timezone context, rather than expanding prior
occurrences from the seed. Actual public add and following-split commands now
produce evidence accepted by R1. Old initial rows retain their original bytes.

## Implemented internal foundation

`spine.commands.recurring_tasks.execute` currently implements exactly:

- `schedule.related_task_rule.create`
- `schedule.related_task_rule.update`
- `schedule.related_task_rule.retire`
- `schedule.related_task_rule.show`
- `schedule.related_task_rule.list`

It is not connected to public dispatch. Reconcile and assignment suppression
are explicitly unsupported at this intermediate internal checkpoint; no stub
success or simulated task mutation is returned for them.

The foundation provides closed source-schema validation and explicit defaults,
raw-cap-before-dedup assignee validation, immutable task-owner selection, pinned
archetype/profile snapshots, concrete route resolution, requested-versus-resolved
configuration, serialized adoption/retirement intents and no-op handling. No
rule authoring command creates tasks, owner headers, policies, work or grants.
Elapsed reminder lead/horizon checks are implemented; broader provable calendar-
day lead support still needs review before claiming complete R2 coverage.

Rendering resolution has a private prospective-owner scope argument for reusable
rule configuration. It accepts no fabricated future item ID and is excluded from
protected-adapter permission contexts. Actual generation must first persist the
real owner and revalidate the presentation; that generation path is still pending.
Missing disclosure fails without owner/grant/application residue.

One outer transaction owns writes, audit and receipt. Compatible replay precedes
fresh actor/source/catalog/clock resolution, verifies retained semantic/result and
audit evidence, and returns the original result even after retirement. Fresh dry
run validates the would-be graph then rolls it back. Fresh writes check canonical
entry/commit clocks and reject a backward clock. Future-due mutation checks remain
part of the pending reconciliation engine, not this authoring checkpoint.

Read handlers cover rule summaries and single rule/assignment/proof plus bounded
assignment/generation/state pages. Stored witness versions are separated from
observed ordinary source/task truth. Reads perform no repair or durable write.
Cursors use the existing protected key facility with this family's exact domain,
purpose, normalized query, ledger identity, generation and fixed one-hour lifetime;
they never reuse the facet token encoding. All five published cursor vectors
match the new codec. No test key is provisioned as runtime configuration.

## Verification ownership

`tests/test_recurring_task_commands.py` contains 17 actual internal-handler tests:
transaction rollback at audit/receipt, fresh preview and compatible replay,
normalized equivalent inputs, immutable snapshots, zero authoring fan-out,
five read/history views plus rule read, cursor corruption/query/purpose/expiry/
catalog/key failures, syntax/reference/stale precedence, disclosure refusal and
backward-clock rollback. All valid source wire requests normalize idempotently;
that syntax evidence does not mean reconcile/suppression execute.
The positive disclosure test also proves reuse of an actual provisioned approval
without creating a future item/owner. Pending adoption authoring is retained on
equal requests and explicitly superseded by cancel-retirement without fan-out.

`tests/test_recurring_task_sources.py` adds an actual public unchanged-COUNT split
and changes the R1 producer-gap regression to assert the corrected prospective
ancestry and successful continuity. The source-only contract suite still checks
the unchanged deterministic artifact bundle and deliberately malformed ancestry.

Verification: full regression run **1,322 passed / one skipped**. Final targeted
checks after the last normalization/scope assertions: **88 passed**, including the
17 foundation tests. Focused Ruff, strict mypy for the changed pure recurrence
module, local Markdown targets and `git diff --check` pass. The full run emitted
non-fatal read-budget callback and expected timezone-substitution diagnostics;
no unrelated cleanup was included. No external audit ran.

## Remaining R2 work

Implement manual bounded two-lane reconciliation and suppression, complete-unit
source/proof/mutation/work/response budgets, ordinary task/owner/history/binding/
policy/work creation, generation-scoped identities and real outer attribution.
Then source move/exclusion/cancellation, linked restoration/vetoes, three-way
adoption, high-water conflicts and all retirement dispositions, including existing
assignments outside the horizon. Add strict-future commit cutoffs, failure
injection at every child stage, page/replay/cursor and actual locking races.
Complete the global error-precedence and bounded-input/read matrices as well;
the selected foundation cases are not exhaustive conformance evidence.

Do not count the SQL-only predecessor constraint test or the offline branch
oracles as end-to-end restoration proof. Do not activate public commands or
automatic scheduling until the later R3/R4 gates are satisfied.
