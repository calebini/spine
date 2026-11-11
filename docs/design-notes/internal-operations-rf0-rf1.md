# Internal operations: RF0 baseline and first RF1 extraction

Date: 2026-11-11. SPINE-099 remains in progress; this is an implementation
checkpoint, not whole-RF1 conformance or recurring-family activation.

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
Whetstone run is involved. The runtime increment is left uncommitted.
