# Internal operations: RF0 baseline and first RF1 extraction

Date: 2026-11-11. SPINE-099 RF0/RF1 is complete at the final checkpoint below.
Earlier sections retain incremental evidence; RF2/RF3 conformance and recurring-family
activation are not claimed. The final response-sizing increment is committed as
`9e50c1c`; the operator subsequently selected RF2 under SPINE-100. Its separate
[evidence record](internal-operations-rf2.md) does not amend the RF1 baseline.

## Authority and baseline

The operator ratified [internal application operations](../../specs/internal-application-operations.md)
and requested a design commit before RF0/RF1. Ratification is `01d5fc9`
(`01d5fc9859f158f9e612da23f3a368f4467946fc`), following the clean SPINE-098
buildability/preservation review. No new product decision or public behavior was
introduced by ratification. RF2/RF3 and recurring R2/R3 remain separately gated.

The baseline is that commit **plus the existing uncommitted R2 admission/read
continuation and unrelated AGENTS.md edits**, not the commit alone. The
[source checkpoint](../../tests/fixtures/internal_operations/rf0_source_checkpoint.json)
records pre-extraction hashes, the worktree at capture, and hashes of the seven
pre-existing runtime/test/note/AGENTS files that must remain byte-identical.
Its worktree list explicitly includes the newly added RF0 characterization tests;
those are not represented as pre-existing R2 work. The R2 additions to backlog and
implementation history are also retained alongside the new RF tracking.

Before any extraction, the ordinary schedule, single-occurrence binding and R2
command/page/restoration/admission selection passed **82 tests**. Two additional
characterization tests then passed all **29 fixed-input cases** against the original
helpers: 23 route results/errors and six binding revision/source/history cases.
The [fixed-input witness](../../tests/fixtures/internal_operations/rf0_shared_helpers.json)
contains the exact inputs and results, including canonical hashes, prior evidence
fallbacks, messages and validation precedence. It is test evidence, not a new wire
contract, and was not regenerated to fit the extraction.

## Implemented increment

| Existing owner/callers | Shared owner now | Preserved distinction |
| --- | --- | --- |
| Command route helper; ordinary schedule, single binding, R2 configuration/create/adoption/restoration | `services.schedule_delivery.resolve_delivery` | Explicit ledger and configured defaults, not a command context; no writes, receipts, authority inference or sends. Family admission/replay ordering is unchanged. |
| Five existing scalar command checks | `core.request_values` | Same bodies, error codes/messages and call order. This is not a codec framework or a new request/admission layer. |
| Subject/group existence and delivery-target lookup | `ledger.catalog_reads` | Keyed existence does not imply active membership, ownership authority or disclosure permission. |
| Binding revision value and occurrence/prior source facts | `core.temporal_bindings` | Same caller-supplied IDs, preimages, exact history pins and current timezone-provider behavior; no new ID or clock sampling. |
| Selected binding provenance persistence | `ledger.provenance.persist_binding_provenance` | Equal content is retained; replacement supersedes then inserts within the caller's transaction. No child commit or receipt. |
| Current-item hydration | `ledger.item_reads.hydrated_item` | Current hydration remains distinct from historical hydration; anchor lookup/errors are unchanged. |
| Occurrence decoration/next-fact and profile application ID aliases | Existing `core.occurrence_details` / `core.hashing` | Services use their actual lower owner instead of importing a command alias. |

Ordinary command wrappers/aliases point downward to these owners. R2 services call
the owners directly at the same sites in their existing transaction/validation
sequence. Restoration still maps an unavailable route to its existing family error;
configuration/create/adoption still compare the same route snapshots, excluding
`delivery_state` only where they already did so. Nothing refreshes pinned profile
revisions, changes generation seeds, broadens copying, or adds work reconciliation.

The service package previously eagerly imported the scheduler, which imports command
dispatch. A normal command-to-service import therefore exposed a cycle. Only the two
existing scheduler exports are now lazy; their public import names and object
identities are preserved. The scheduler remains the explicitly retained invocation
adapter, not a dependency of importing the shared route operation.

## Verification and dependency ratchet

- Twelve moved helper ASTs match the baseline exactly apart from function names.
  The complete route body also matches after explicit dependency and ledger/default
  input remapping. Hydration adds only a static type cast, not runtime validation.
- [Preservation tests](../../tests/test_internal_operation_preservation.py) compare
  canonical result/error bytes to the captured baseline and assert route resolution
  writes nothing to the disposable ledger.
- [Boundary tests](../../tests/test_internal_operation_boundaries.py) exercise actual
  ordinary schedule, single binding and six-task recurring generation through the
  same route operation, with no delivery attempts. They verify forwarding identity,
  absence of command/commit/dispatch dependencies in extracted modules, and fresh
  interpreter import isolation, including the scheduler export identities.
- The [dependency inventory](../../tests/fixtures/internal_operations/rf1_dependency_inventory.json)
  records named lexical callers, imports/calls and counts, before and after. No
  wildcard module exemption is used. Any new module, caller, target or duplicate
  call fails the ratchet; removals require explicitly shrinking the inventory.
  Across services, command imports fall from 52 to 48 and call sites from 128 to
  109. This is a dependency count, not a claim of system-wide decoupling.
- Focused after-extraction schedule/binding/R2 tests passed 84 tests including the
  two baseline witnesses. Eight RF0/RF1 tests passed, as did the combined 12-test
  Tickerd compatibility/RF selection in the correct environment. Seven touched
  shared-boundary modules pass strict typing; focused Ruff and diff hygiene pass.
- Full regression passes **1,410 tests, OK (one skipped)** in 375.428 seconds,
  using Spine's installed pinned Tickerd v1 package. The run emitted a non-failing
  capacity-limit trace diagnostic and timezone-substitution diagnostics; no test
  assertion failed. The final 20-test documentation/declaration/frozen-web/boundary
  selection, 381 local link targets, strict typing, Ruff and diff hygiene also pass.

The first broad verification command used the historical sibling Tickerd source
override. That checkout now advertises v2, incompatible with Spine's pinned v1,
so that run was stopped and is **not** passing evidence. Spine's own virtual
environment contains the required `tickerd.runtime-capabilities.v1` package. Use:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

The initial focused characterization did not exercise Tickerd; the corrected full
run establishes overall regression compatibility for this checkpoint. No provider
pin or acceptance test was relaxed, and no dependency installation was needed.

## Remaining RF1 and next checkpoint

RF0's inventory and selected characterization are established. **RF1 is not done.**
Continue extracting the shared policy normalization, successor materialization and
work-reconciliation operations used by ordinary update, single binding and recurring
create/adoption/restoration. Also remove the remaining R2 reverse calls to timed
target resolution, receipt reads, recurring runtime failure/time/cursor helpers, and
recurring catalog/projection helpers. The inventory identifies every retained caller.
Do not move an entire command handler behind a new name or add child dispatch.

Untouched people/read permission helpers are named exceptions with separate cleanup
gates; scheduler dispatch is the accepted invocation-adapter exception. Neither is
an excuse for new business-operation dependencies. RF1 closure still requires no
R2 service calls into command internals and the remaining IO-01/02/06/08 evidence.
RF2 complete mutation/state ownership and RF3 propagation are not implemented here.
Original R2 functional gates and R4-only public activation remain intact.

No public command/contract, package version, ledger schema/migration, frozen web
artifact, permission model, operator guide or delivery behavior changes. All test
ledgers are disposable. No operator ledger, external send, deployment, push or new
Whetstone run is involved. The first runtime increment was subsequently committed
as `02bfb03`, excluding the pre-existing R2/AGENTS changes and their tracking hunks.

## RF1 continuation: policy preparation and work classification

The operator requested committing the first increment and continuing RF1.
`services.schedule_policies` now owns create/update/disable preparation and route
copying, with ordinary command aliases and direct recurring callers. It preserves
the existing `_UNSET` identity for copy-forward, explicit empty replacement, key and
intent binding, sorted normalization, duplicate detection, and exact ID/preimage
derivation. It performs no writes, admission, dispatch or new default resolution.

`ledger.schedule_work.reconcile_work_plan` owns the existing SQL-backed read-only
classification, including policy-specific lineage resolution, reason precedence,
attempt evidence and eligible/unattempted cancellation candidates. It does not cancel
or materialize anything itself. Owning callers retain their existing mutation and
transaction ordering. This does not yet extract successor materialization.

The four [policy witnesses](../../tests/fixtures/internal_operations/rf1_policy_witness.json)
were computed from the committed `02bfb03` function definitions, not from rewritten
expectations. Fixed create, carry-forward, empty clear and disable results include
complete normalized facts/preimages. Existing boundary tests now cover both new
owners, and the dependency inventory shrinks only removed calls.

Verification: 67 focused schedule-update, single-binding successor, recurring page/
restoration and policy-lineage tests pass; nine operation tests pass; both new
owners pass strict typing and focused Ruff/diff hygiene pass. Full regression passes
1,410 tests (one skipped), 364.845 seconds. The policy witness added after full-suite
collection passes separately within the final 23-test documentation/declaration/
frozen-web/operation selection. All 382 local links resolve. The same non-failing
capacity trace and timezone-substitution diagnostics appeared. Five moved helper
bodies match the baseline after name/local/type-only normalization.
Existing R2/AGENTS files remain byte-identical. This continuation is
now committed as `f9fd18a`. RF1 remained open for materialization, timed binding-source resolution,
and the named recurring runtime/catalog/receipt/read dependencies; no RF2/RF3 or
functional R2/R3 resumption is implied.

## RF1 continuation: successor materialization and timed bindings

The operator requested committing the policy/classification increment and continuing.
`services.schedule_materialization.materialize_successor` now composes the existing
successor work operation. `core.notification_targets` owns deterministic target,
range, offset and initial-time calculations. `ledger.schedule_work` owns the exact
existence/evidence SQL lookups. `core.temporal_bindings` now also owns item-source
and target-time resolution. Existing command aliases point downward; recurring
child/reconcile services call these owners directly and have no remaining import of
command-core or temporal-binding command modules.

No generation identity, producer label, opportunity ordering, policy limit, prospective
item-version hydration, provenance fact, work creation flag or transaction ownership
changes. In particular, existing producer `schedule.update` and `manage_transaction=False`
remain untouched; naming cleanup is not permission to change historical evidence.
No external send, child receipt, commit, or additional automatic materialization.

Verification so far: 77 selected ordinary/binding/recurring and boundary tests pass;
four shared modules pass strict typing. The exact dependency ratchet is reduced,
not broadened. Two new tests in [shared materialization](../../tests/test_shared_materialization.py)
prove no-op mode touches no ledger, repeated execution creates no duplicate work,
and caller rollback restores the complete database. A local differential experiment
executed the committed `f9fd18a` materializer and the extracted operation on the same
disposable ledger: complete result tuples, repeat results and in-transaction SQL
dumps matched exactly, and both outer rollbacks restored the baseline. Full regression
passes **1,413 tests, OK (one skipped)** in 369.823 seconds using installed Tickerd v1.
The final 25-test documentation/declaration/frozen-web/operation selection, strict
typing, focused Ruff, diff hygiene and 383 link targets pass. The known non-failing
capacity trace and timezone-substitution diagnostics appeared. This continuation
was committed as `25ebada`, with existing R2/AGENTS edits
preserved. Remaining RF1 work was the named recurring runtime/catalog/receipt/read
dependencies; RF1 closure and RF2/RF3 are not claimed.

## RF1 continuation: recurring primitives, receipts and catalog reads

The operator requested continued RF1 after `25ebada`. The new owners are:

- `core.recurring_task_runtime`: the existing recurring-family failure/time helpers,
  cursor constants, canonical encoding, signing, configuration checks and verification.
  A narrow `CursorValidator` protocol keeps the existing schema-validation call at
  the same point without importing command admission. No new authentication or
  generic codec framework is introduced.
- `ledger.receipts`: exact keyed receipt lookup and historical row decoding. Receipt
  construction/insertion and family replay decisions remain at their existing owners;
  command imports forward to the same lower read implementation.
- `ledger.recurring_task_catalog`: existing catalog-generation reads/advancement,
  keyed lookup, source snapshots and stored rule/intent projections. These preserve
  historical pins, null/omitted fields, counter strings and validation errors. The
  catalog update still joins the caller transaction without making a receipt or commit.

Recurring services use these owners directly. Their sole remaining command dependency
is `_reconcile` calling `commands.recurring_tasks.success_response` to budget the exact
complete response bytes. The command must retain response ownership; replacing this
last call needs an explicit narrow projection/size capability with parity evidence,
not moving a handler or duplicating its response formula. **RF1 remains open.**

### Preservation of the dirty R2 baseline

The earlier seven-file byte-preservation checkpoint is historical evidence, unchanged.
This extraction necessarily overlaps two of those files: `commands.recurring_task_runtime.py`
and `commands.recurring_tasks.py`. Their shared helpers become forwarding aliases;
their pre-existing syntax, admission, normalization, read, execute and response bodies
are unchanged. The [captured body witness](../../tests/fixtures/internal_operations/rf1_runtime_catalog_witness.json)
identifies the exact pre-extraction dirty-source hashes and checks all original
function/class bodies at either their original or extracted owners. It was captured
from the baseline, not regenerated from the result. Five other pre-existing files,
including AGENTS.md and the R2 reference module/test, remain byte-identical. Existing
R2 tracking additions remain separate from this work; nothing resumes R2 behavior.

### Verification

The pre-extraction command/admission/boundary selection passed 36 tests. The new
[runtime/catalog tests](../../tests/test_shared_recurring_runtime.py) cover fixed body
preservation, forwarding identity, fresh-process import isolation, published cursor
bytes, malformed/expired/stale cursors, invalid key configuration precedence, exact
receipt history, read-only catalog projection and rollback of catalog advancement.
The named dependency ratchet shrinks; no blanket exception is added. Strict typing
passes for the three new shared modules. The corrected focused selection passes
**91 tests**, 53.152 seconds; final documentation/declaration/frozen-web/operation
checks pass **30 tests**, 4.703 seconds. Ruff/diff hygiene and all 385 local
documentation targets pass. Full regression passes **1,418 tests, OK (one skipped)**
in 361.648 seconds with the installed pinned Tickerd v1. The previously known
non-failing capacity-limit trace and timezone-compatibility diagnostics appeared;
no test assertions failed. The operator subsequently requested checkpointing.
An initial expanded selection used a nonexistent test-module name; that
invocation is not passing evidence and has been replaced with the correct selection.

Commit preparation identified one pre-existing R2 edit inside a moved helper:
`cursor_config` rejects surrogate characters in the key generation. That change is
kept unstaged at its new core owner, not smuggled into the extraction commit. The
body witness now also captures the exact `25ebada` bodies. Its test requires one
complete captured baseline to match (committed or dirty), never an arbitrary mix.
The original R2 test still covers the additional cursor validation; the refactor's
cursor test covers the shared committed behavior. The two command files' original
R2 edits remain unstaged as well. No prior full-suite result is represented as a
clean-index run; commit-only verification is recorded separately.

The exact staged tree was exported to a disposable directory without stashing or
altering the working checkout. Its focused command/reconcile/restoration/lineage/
preservation selection passed **78 tests**, 28.937 seconds. The three mixed staged
files passed Ruff on their index contents; staged diff hygiene passed. The dirty
working tree separately passed the 11-test preservation/boundary selection after
the dual-baseline witness adjustment. No runtime behavior was changed during commit
preparation; the committed extraction retains the original committed helper bodies.

No public schema/registry/version changes, ledger migration, external send or deployment.
RF2/RF3 and recurring-family activation remain separate gates. No push requested.

## Next slice: response-sizing capability

Selected and implemented in the following continuation. The remaining RF1 edge was `_reconcile` importing and
calling `commands.recurring_tasks.success_response` during output-budget trials.

1. Capture exact complete envelope bytes and page decisions before changing the
   seam, including changed/no-op and ordinary/dry-run responses. Preserve both the
   committed and pre-existing R2 dirty states rather than silently absorbing the latter.
2. Keep `success_response`, audit/receipt identity projection and final response
   assembly in the command adapter. Supply a required, typed, narrow sizing
   capability to the reconciliation operation; no optional default authority,
   full-handler callback, duplicated envelope formula or public contract change.
3. Invoke it at the same trial point using current accepted result/audit facts.
   Preserve exact canonical byte accounting, cursor contents, unit rollback,
   non-refundable budgets, error precedence and caller transaction ownership.
4. Test exact-at-limit/over-limit output, continuation without duplicates or missing
   tasks, dry-run rollback, replay and final command-envelope agreement. Remove the
   last counted recurring command import/call only after preservation passes.

Run focused and full regression, frozen-contract/declaration checks, typing, lint
and diff hygiene. Assess IO-01/02/06/08 before recording RF1 closure. This brief does
not start RF2 state/mutation ownership, RF3 propagation or functional recurring R2/R3.

## RF1 continuation: required response-sizing capability

The runtime/catalog extraction and next-slice brief were committed as `8e887a3`.
The operator then selected this final RF1 seam. `ResponseSizer` is a required,
keyword-only internal capability on `reconcile` and `_reconcile`, not an optional
fallback or a new public API. It accepts only result, effect, changed flag and an
immutable snapshot of the currently accepted audit IDs, returning a byte count.
The command adapter binds command ID, family, evaluation time and dry-run mode;
its pure measuring closure uses the unchanged `success_response` and canonical JSON
encoder. No response formula moved or was duplicated. Final response/receipt creation
remains in the command adapter. No ledger, full request, mutable page, command
dispatch, new clock sample or authority inference is supplied to the capability.

The call remains inside the same tentative finalization savepoint, after `finish`
and before the byte comparison. Suffix rollback, proof costs, audit accumulation,
IDs, cursor limits, error mapping and outer transaction ownership are unchanged.
The old exact body witness is retained: only the explicitly checked capability
keyword is normalized out of `execute` for comparison with the two captured
committed/dirty baselines. The preserved R2 admission/read continuation remains
separate; the current tree is not represented as a clean committed baseline.

### Preservation and exit evidence

Before editing runtime code, four real disposable-ledger scenarios were captured
twice with a fixed test-only ledger ID: changed generation, no-op, dry-run and
byte-limited multi-page generation. Their complete response-trial/final/replay byte
digests, exact lengths, assignment IDs and full ledger-dump digests were identical.
The [pre-change witness](../../tests/fixtures/internal_operations/rf1_response_sizing_witness.json)
is checked unchanged by [response-sizing tests](../../tests/test_recurring_response_sizing.py).

- **IO-01:** Every recurring-task service has zero command imports/calls; the final
  counted exception was removed and an explicit no-recurring-exceptions test was
  added. Unrelated named people/read and scheduler invocation exceptions remain;
  this is not a whole-repository decoupling claim.
- **IO-02:** The four pre-change witnesses match after extraction, including
  successive byte-rejection trials and replay. Earlier ordinary/single-binding/
  recurring shared-operation and fixed-ID witnesses remain. The sizing callback
  uses the same unchanged command envelope, with current (not stale captured) audits.
- **Applicable IO-06:** Missing capability fails before ledger access. The internal
  recurring entry still rejects web transport before replay; compatible trusted-local
  replay does not invoke the sizer. Existing prospective-owner/disclosure and dry-run
  tests remain. No recurring web admission or new authority path is introduced.
- **IO-08:** Focused dirty-baseline regression passes **97 tests**, 60.450 seconds;
  both actual command/service modules pass strict typing, and lint/diff hygiene pass.
  Final documentation/declaration/frozen-contract/operation checks pass **36 tests**,
  9.857 seconds, including the extended admission/replay guard. An isolated snapshot
  of `8e887a3` plus only this refactor (without the dirty R2 continuation) passes
  **84 focused tests**, 34.880 seconds, including the same byte/ledger witnesses.
  All 389 local documentation targets resolve. Full regression passes **1,424 tests,
  OK (one skipped)** in 384.057 seconds with installed pinned Tickerd v1. The known
  non-failing capacity-limit trace and timezone-compatibility diagnostics appeared.

New tests cover exact-at-limit and one-byte-under behavior for normal and dry-run
responses, immutable outer identity with fresh audit snapshots, Unicode byte counts,
missing-capability rejection, sizing failure rollback and connection reuse. The
exact-limit test accounts for the response publishing its requested limit (whose
decimal width changes envelope size); it finds the stable exact boundary. Initial
test-harness attempts used an enclosing writer, correctly rejected by admission,
and assumed the limit was absent from the response. Both assumptions were corrected
in tests only; no runtime contract or expected golden output was relaxed.

No public artifacts, schema/package versions, migrations, sends or deployment changed.
No commit or push requested for this continuation. RF0/RF1's selected extraction
exit is satisfied by the evidence above; SPINE-099 is complete. RF2 complete item-
change/state ownership is the next separately authorized slice; RF3 and functional
R2/R3 are not started by this work. This does not claim whole-repository decoupling
or complete conformance to the later portions of the internal-operations contract.
