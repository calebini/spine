# R2 admission, historical reads and budget verification

Date: 2026-11-11. Internal candidate only; **R2 remains in progress**.

Continuation: 2026-11-12, after RF2 checkpoint `07e097d`; explicitly selected
admission/read completion only. Earlier evidence below is retained at its original
checkpoint, not relabelled as current verification.

The operator requested committing the verified restoration increment and
continuing R2. It was committed as `e540a91`, excluding the unrelated `AGENTS.md`
edit. This follow-up is uncommitted; it does not activate a release.

## Runtime changes

- Explicit authoring references are resolved after compatible replay and before
  cursor/expected-version/semantic checks. The bounded helper uses keyed existence
  lookups for actor, catalog/item owners, source/root/assignment membership,
  locations, archetype/profile roots and exact revision membership, assignees,
  default scope owners, recipients and delivery targets. Missing rows report the
  narrow input path instead of being hidden by stale expected facts.
- Existence is not authority or semantic validity. Retirement, compatibility,
  ownership changes, ambiguous defaults and actual route/disclosure eligibility
  stay with their owning validators after freshness. Rendering selections retain
  their delegated disclosure-failure contract. Optimistic expected facts and
  target generation/task identities remain comparisons, not arbitrary lookups.
  Read filters are queries and are not turned into authoring references.
- Syntax errors use the declared top-level field order and then lexical nested
  paths, including the actual missing/extra field. Depth no longer outranks a
  lexically earlier failure. Discriminated unions retain the intended branch's
  genuine constant failures rather than discarding every constant error.
- Invalid surrogate strings/keys participate in those ordered syntax errors and
  produce closed `invalid_request` failures, not leaked canonicalization codes.
  Valid strings are not normalized or rewritten. A surrogate in the configured
  cursor key ID is an environment/configuration failure, not a caller error.
- Nonrecurring or wrong-type source items now fail semantically at
  `source.item_id`, rather than looking like a missing runtime environment.
  Available source version/revision freshness checks retain their precedence.
- Paged reads size the complete success envelope using the same base projection
  as execution, with an exact 1048576-byte cap. The former fixed 8192-byte
  reservation could underfill a terminal page. Reads now stop only between full
  rows, include the actual continuation and cutoff flag, and derive the next key
  from the last retained row. Single-row overflow still fails without truncation.

No request/response schema, ID preimage, cursor signing domain, contract version,
public dispatch, schema object, migration or write authority was changed.

## Actual tests

Thirteen new tests cover:

1. Deterministic nested syntax and constant/extra-field ordering.
2. Closed invalid-Unicode errors, including an invalid object key and simultaneous
   earlier syntax failure; invalid cursor configuration.
3. Real ordinary event/task items that are not valid recurring event sources.
4. Missing owner, assignee, location and archetype references before staleness.
5. Missing suppression assignment before stale root/assignment facts.
6. Explicit profile/archetype revision membership and recipient/target/default
   lookup precedence.
7. Actor/root reference, authenticated-cursor and expected-fact phase ordering.
   Lexically malformed cursor syntax intentionally still precedes all lookups.
8. Assignment read membership before authenticated cursor validation, no repairs.
9. Exact historical reconcile replay after source changes, retirement and cursor
   expiry: no clock sample, no refreshed receipt/cursor and no writes. Invalid
   syntax and incompatible command-ID reuse still fail at their owning phases.
10. Cross-ledger/missing or invalid key context without mutation.
11. Actual large task-adoption history tuned above the old row-only cutoff but
    below the complete envelope cap, followed by real extra history requiring
    exact two-page continuation. No synthetic oversized projection or truncated
    payload replaces the real transactions. Read snapshots remain unchanged.
12. A canonical public following/COUNT-copy split that requires lineage proof:
    a too-small hop budget fails closed, while sufficient bounds refresh existing
    assignments without cancelling or creating duplicate tasks.
13. Actual mid-page proof exhaustion after a binding unit has already written:
    the whole outer page rolls back. Measurement only observes the existing
    budget during a dry run; it does not bypass or raise the execution limit.

The new regressions reproduced the prior ordering/Unicode/source failures before
their narrow patches. The focused complete-tree command/page/restoration/bootstrap
selection passes **80 tests**, 51.973 seconds. Three touched admission/runtime
modules pass focused strict typing; Ruff and diff hygiene pass. Full regression
passes **1,402 tests, OK (one skipped)**, 367.386 seconds. Known non-fatal
timezone-substitution diagnostics appeared. Frozen web copies and 364 local
documentation link targets pass. The unrelated `AGENTS.md` SHA-256 is unchanged;
package/version, schema and public command registry files have no diff.

## Remaining R2 work

Do not infer whole-family conformance from these selected cases. Continue intent
selection/coverage and wider adoption races, remaining source continuity/novelty
and lifecycle/effect/reason cases, individual detail/offset/disclosure/reference
invalidation coverage, broader provable calendar-day reminder lead support, and
the remaining manual-engine proof/budget matrix. Admission/read completion below
does not claim every combined lifecycle limit or per-proof hop boundary is closed.

No R3 automatic scheduling/all-writer activation or R4 publication is included.
No push, live ledger, deployment, adapter invocation, send or external audit was
performed. Existing work, storage and attempt safeguards remain in place.

## Admission/read completion — 2026-11-12

The preserved continuation was resumed after RF2, without broadening into RF3/R3.
Nine additional tests extend the original thirteen:

1. Multiple absent top-level fields follow command order, not alphabetical order.
   Unknown `show.view` does not bypass an earlier missing/malformed rule or
   assignment ID or invent required fields from an unselected view.
2. Every reconcile limit rejects zero, one-above-maximum, leading-zero and numeric
   input before row lookup; every maximum normalizes successfully. Read limits
   exercise the same syntax boundary. These are admission tests, not claims that
   every maximum-size lifecycle page has been executed.
3. Candidate/transport/dependency admission precedes syntax, refuses an existing
   outer transaction and rejects non-local transport metadata. Unsupported command
   and contract errors retain their next phases.
4. All five rule/source/catalog expected facts, assignment version, generation and
   task identity fail in exact order before suppression semantics. Every failure
   leaves the disposable ledger unchanged.
5. All five published cursor purposes reject signed noncanonical JSON, duplicate
   keys, unknown fields, incorrect lifetimes, datetime overflow, another ledger's
   token under the same key, and retired key IDs. Exact expiry equality and changed
   catalog generations are stale, not invalid. Published positive vectors remain
   byte-for-byte unchanged.
6. Trusted-local list filters distinguish active/retired/all and treat absent owner
   or source matches as empty queries. Terminal reads need no signing key and do
   not reconstruct configuration bodies in summaries.
7. Actual cancel/restore history paginates assignments, generations and states one
   row at a time, matches complete reads exactly, preserves order, terminates, and
   rejects changed limits. Assignment/proof IDs cannot cross root membership.
8. After ordinary task completion and a source revision, reads expose current
   observed versions/status and `needs_reconcile`, while immutable witness version,
   proof, snapshot and state history stay unchanged. Reads never repair them.
9. Rule/assignment/proof and single-row state reads pass at their exact complete
   envelope size and fail one byte below it without truncation or writes. These
   boundary tests inject a smaller internal cap; the original large-history test
   continues to exercise the actual 1,048,576-byte cap.

The new tests reproduced the missing-field precedence defect and unhandled cursor
datetime overflow before their narrow runtime corrections. Unknown-view admission
now validates the schema-derived common requirements and supplied known fields
before selecting the earliest failure. No wire schema, canonicalization, signing
domain, version, permission, identity derivation or persisted representation changed.

Verification: focused R2 baseline **69 tests passed**; expanded selection **76
passed** (56.833 seconds), followed by both additional admission/expected-order
tests passing. Touched Ruff and frozen web-copy synchronization pass. Four modules
pass focused strict typing with only the already-unavailable third-party
`jsonschema` stubs excluded (`--disable-error-code=import-untyped`).

The first full run executed 1,470 tests (one skipped) and found one stale RF1
exact-body assertion: it intentionally froze the two functions now changed by
this authorized functional continuation. The original RF1 fixture remains
byte-identical. A separate [two-body amendment](../../tests/fixtures/internal_operations/r2_admission_read_body_amendment.json)
pins that original fixture's SHA-256 and the exact replacement bodies; the guard
still requires one complete baseline/amendment, never arbitrary per-function
mixing. No other body is exempted or rebaselined. The corrected guard and focused
boundary/contract/declaration selection pass **41 tests** (5.203 seconds).
Final full regression rerun: **1,470 tests, OK (one skipped)**, 377.265 seconds.
Known non-fatal read-budget and timezone-substitution diagnostics appeared. The
selected admission/read slice is complete; the broader R2 exit is not. Local
tracking links, diff hygiene and frozen public/schema/migration surface checks
pass. All original RF1/RF2 frozen witnesses remain byte-identical.

`AGENTS.md` and the preserved restoration note retain their pre-resumption SHA-256
values. No commit, push, deployment, live ledger or external call is part of this
continuation. The admission/read slice is separate from remaining R2 manual-engine
exit evidence and does not authorize RF3/R3 or public activation.
