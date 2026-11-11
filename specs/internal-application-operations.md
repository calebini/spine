# Spine Internal Application Operations

Status: Draft v0.1 — internal refactoring contract; not ratified or implemented
Date: 2026-11-11
Scope: Shared scheduling, binding and notification operations; complete item changes,
transaction-local state and synchronous change propagation

## 1. Authority and preservation boundary

This leaf develops the internal application boundary delegated by
[architecture](architecture.md). [Storage and atomicity](STORAGE_ATOMICITY_SPEC.md)
remains the Spine-wide persistence owner. Feature specifications retain authority
over domain behavior, validation order, identities, permissions, budgets, effects
and public contracts. If an extraction cannot preserve those requirements, stop and
amend the owning contract separately; this draft is not permission to reinterpret it.
The requirements below describe the proposed target, not current conformance.

The selected scope is the shared operations used by ordinary schedule authoring,
single-occurrence related tasks and the internal recurring-task engine. It includes
their mutation-state ownership and the propagation seam needed before recurring R3.
The [schedule](schedule-operations.md), [binding](relative-temporal-bindings.md),
[recurring lifecycle](recurring-related-tasks.md) and
[recurring command](recurring-related-task-commands.md) owners retain their distinct
semantics; this leaf is not a replacement feature specification.
It does not require restructuring every command family. The
[assessment](../docs/design-notes/internal-architecture-assessment-2026-11-11.md)
provides rationale; [backlog](../docs/BACKLOG.md) and
[implementation plan](../docs/IMPLEMENTATION_PLAN.md) own sequencing and evidence.

This refactor MUST preserve:

- Public command identifiers, request/response schemas and versions, normalization,
  validation/error precedence, effect ordering, cursor and historical replay behavior.
- Canonical preimages, identity derivation, immutable decoding, item versions,
  supporting facts, owner/access facts, audit/receipt content and attempt evidence.
- Trusted-local authority, protected-web admission and release fences, disclosure
  rules, policy-specific continuity, lifecycle vetoes and source identity proofs.
- Existing command-specific reconciliation choices, bounds, dry-run behavior and
  explicit no-op receipts; idle automatic planning remains non-durable.

No new public contract family, command, agent workflow, persistent table, migration,
service process, permission grant or recurring-family activation is introduced.
Internal type names below are design names, not a public Python API or wire format.
Existing runtime and source-only feature activation states remain unchanged.

## 2. Ownership and dependency direction

```text
CLI / HTTP / worker invocation adapter
  -> command-family admission, replay and response adapter
     -> application operations (services)
        -> domain rules (core) + persistence (ledger)
           -> owned LedgerConnection transaction

delivery processor -> attempt admission -> committed evidence -> external adapter
```

| Owner | Responsibility and permitted dependencies |
| --- | --- |
| `core` | Deterministic domain rules and explicit timezone capability; no command, service, ledger, web or vendor-adapter dependencies. |
| `ledger` | SQL, immutable decoding, constraints, mutation-scoped invariants, allocation and transaction state; may depend on `core`, not command or HTTP implementations. |
| `services` | Provider-independent application composition over `core`, `ledger` and explicit narrow capabilities; no command-handler or private command-helper imports. |
| `commands` | Exact family/version syntax, semantic admission sequence, replay identity, receipt and response/error projection; delegates reusable work to operations. |
| CLI / HTTP / worker adapters | Runtime admission, explicit caller authority, transport limits and release rules; invoke supported families/operations without manufacturing domain truth. |

Concrete SQLite persistence stays in `ledger`; no repository-interface framework,
ORM or database-to-adapter relocation is required. Transport code may supply an
admitted capability through a neutral internal type; shared operations MUST NOT
import an HTTP implementation to obtain it. This does not require moving all existing
permission/read machinery in the first extraction.

The scheduler's command-dispatch bridge may remain an explicitly identified invocation
adapter, preserving its command IDs and receipt semantics. It MUST NOT become a
way for extracted business operations to call back into commands. Temporary forwarding
aliases may point from commands to a lower owner, never the reverse. The implementation
inventory MUST name each retained dependency exception, its caller and removal gate;
no wildcard exemption or blanket claim of whole-repository conformance is permitted.

## 3. Explicit invocation inputs

An operation receives an owned transaction/session and typed inputs, not the full CLI
request, mutable reconciliation page or a bag of optional hooks.

`InvocationContext` carries the canonical actor, exact command family/version and
outer command identity where applicable, explicit authority, clock access and shared
resource accounting. Authority is a closed choice: trusted-local invocation selected
by local composition, or admitted protected context with the existing account/subject,
scope and freshness evidence. An absent context MUST NOT mean trusted-local. A client
request boolean cannot select authority. This adds no token or authentication system.

`IdentityPlan` separates the outer command identity from item/policy/work identities,
generation-scoped child seeds and restoration predecessor references. It delegates
derivation to the existing feature owner. Moving a function or changing its name MUST
NOT alter a preimage, substitute an outer ID for a required generation-scoped seed,
introduce a synthetic child command ID,
or replace a history pin with the current catalog head. Existing injected clocks and
ID sources remain injectable; newly sampled values cannot replace stored replay facts.

Budgets are shared by the entire invocation/page, with typed counters for the owning
contract's proof steps, lineage hops, selected rows, mutations, work, output and time
where applicable. An extracted child MUST NOT reset its parent's allowance. Each
operation declares what it consumes and checks capacity before unbounded loading or
expansion; a caller-only check is insufficient if another caller can omit it. Existing
deadline/commit-cutoff resampling remains explicit rather than freezing all checks at
the initial clock sample. No new numeric limits or failure precedence are invented here.

## 4. Shared operations

Use separate typed intents for create, change and restore rather than one universal
mutation object with unrelated optional fields. Supporting-set changes distinguish
keep, replace and explicit clear; omission is normalized by the family adapter before
application. Only combinations allowed by the owning command are constructible.

| Operation | Input and result | Obligation |
| --- | --- | --- |
| Prepare notification plan | Actual or prospective item/owner, exact profile/custom policies, route, presentation/disclosure selections and identity plan -> immutable resolved policy/application/presentation plan | Resolve defaults only when the owning intent requires them; no incidental authoring or disclosure grant. |
| Resolve source / prepare binding change | Stored selector and proof, source/target versions, accepted offset and lifecycle intent -> source evidence and binding plan | Preserve recurrence and single-occurrence binding semantics; ambiguous or unavailable lineage is not repaired by guessing. |
| Prepare/apply item change | Typed create/change/restore intent, expected version or absence, supporting plans, owner/binding intent and work mode -> item/version identities, audit facts and mutation effects | Own the complete selected mutation in the supplied transaction, using the existing allocator. |
| Reconcile notification work | Explicit current or prospective target, policies, bounded work selection, work mode and optional materialization range -> created/cancelled/retained/protected evidence and charged use | Preserve existing freshness classifications and command-specific output projection; never send. |

Preparation is read-only and does not authorize a later write by itself. Plans carry
their expected versions and exact dependencies; any plan made before the owning write
transaction MUST be revalidated inside it before application. Extraction MUST preserve
the family's ordering of replay, reference checks, stale checks and semantic validation.
There is no new universal validation order across unrelated command contracts.

Prospective owner/item facts MUST be explicit when preparation precedes insertion.
Disclosure and people-selection checks use the actual intended owner, not a fabricated
temporary owner. Ownership initialization remains governed by
[local ownership bootstrap](local-ownership-bootstrap.md); no web realm or grants are
created as a side effect. A prospective view MUST NOT be presented as committed current
truth to ordinary read or delivery callers.

Work modes distinguish keeping the owning command's existing policy, stale-work-only
reconciliation and bounded materialization/reconciliation. They are internal explicit
choices, not new user switches. A generic item edit MUST NOT acquire eager work creation
merely because a composite schedule edit uses the same lower operation. Planning and
attempt-time eligibility remain distinct checks owned by [notifications](notifications.md).

Operations return structured domain results, not a whole public success envelope.
Family adapters keep exact errors, `field` paths, receipt fields and sort order. Shared
validation failures may be translated only through deliberate family mappings; unexpected
programming errors MUST NOT be silently converted into a successful no-op or a guessed
validation failure. Existing failure contracts remain authoritative.

## 5. Complete item-change ownership

For each migrated intent, the application owner MUST account for every applicable
obligation below, explicitly recording either its prepared action or that it is
unaffected. Callers MUST NOT finish the operation by remembering additional SQL or
editing connection trackers themselves.

1. Recheck expected current facts and authority at the owning transaction boundary.
2. Allocate canonical item/version/detail facts through the existing guarded ledger
   allocator; preserve its compare-and-swap and mutation audit ownership.
3. Carry forward or replace supporting sets, including time/location, subject roles,
   facets and exact revisions, policies, profile applications and presentations.
4. Apply explicit owner, relation and binding changes and their existing histories,
   epochs and indexes; preserve source-proof and generation lineage requirements.
5. Perform only the selected command's required work reconciliation/materialization,
   then register its exact mutation effects and required synchronous consequences.
6. Return complete evidence to the outer adapter for audit/receipt completion and
   finalization; failure anywhere rolls back the complete unit.

This is an obligation list, not a replacement SQL statement order. The current allocator
may write supporting extensions before the current-pointer CAS. Preserve that safe
ordering with an explicit prospective successor view; do not move materialization to
a second transaction to make a current-only helper convenient. A closed, owned internal
assembly may adapt the allocator's existing extension hooks, but migrated callers MUST
NOT supply arbitrary callbacks that can omit required supporting work.

In particular:

- Keep every unselected subject role, including the opposite participant/assignee role;
  an explicit empty selection clears only its named role.
- Preserve empty and populated facet snapshots, non-queryable references, immutable
  location/reference facts and historical definition decoding.
- Keep profile/application/presentation links aligned with the exact successor policy.
  Shared historical intents do not make one policy's change invalidate all policies.
- Restoration follows the recurring feature's actual predecessor choices and new
  generation identities, not ordinary create against the latest defaults. Manual
  customization, terminal veto, detach, suppression and source-only cancellation
  provenance remain significant; no generic restore policy supersedes them.
- Do not rewrite leased/attempted/delivered evidence to make a successor appear clean.
  Work protections and attempt-start freshness remain governed by their feature owners.

## 6. Transaction and in-memory state

One outer command/page invocation owns commit, rollback and the command receipt.
Shared operations join it: no independent writer, nested commit, implicit-commit
script, synthetic subcommand receipt or external adapter call. The existing standalone
ledger helpers may retain their local transaction behavior outside composition; when
composed, their contexts MUST be absorbed by the outer `LedgerConnection` owner.

Audit cardinality and payloads remain family-specific. Audit facts may be produced by
the allocator or an existing owning helper, but the complete audit/receipt set MUST be
present before commit validation requires it. Current continuity decoders that read
receipt/audit evidence retain their historical formats and validation. They belong
below wire adapters and MUST NOT be replaced by a new durable witness in this refactor.

`TransactionMutationState` owns the closed set of connection-local obligations:
ownership-epoch consumption, touched recurring rows, pending rendering/policy state,
rendering versions/catalog/profiles/attempts, and facet allocation/version/root/item/
binding/definition state. Feature enablement and allocation guards stay connection
configuration, not caller-mutable page fields. One explicit registration point per
component defines checkpoint, restore, reset and finalization coverage. This is not
a dynamic plugin registry. Preserve finalizer dependencies and existing order, including
recurring checks before rendering checks before facet checks when enabled.

`PageState` owns accepted result/work/mapping accumulators, root/runtime working copies,
owner/change flags, mutation counts, continuation position and retained unit checkpoints.
It is not passed wholesale to child operations. On a bounded unit rollback, restore
both SQL and the corresponding transaction/page checkpoint without erasing earlier
accepted units. Nested checkpoints close in LIFO order. A failed trial may be represented
by a domain result only where the owning reconciliation contract permits that result.

Proof work already spent, elapsed time and other consumption the feature defines as
non-refundable MUST NOT be restored with rolled-back mutation/output counters. Tests
must distinguish these categories, including retry within the same bounded page.
No budget is made refundable merely because it resides in a checkpointed object.

If SQLite interruption has already aborted the outer transaction, do not resume a
partial page or replace the original failure with a missing-savepoint error. Abort
the invocation, clear its pending state and preserve the owning failure classification.
Successful commit, failed finalization, rollback and connection reuse MUST all leave
no stale obligations for the next invocation. Required finalization cannot be bypassed
through raw commit, outermost savepoint release or an unregistered version producer.

Attempt admission remains a separate short transaction that persists immutable attempt
and rendering evidence before external sending. It MUST NOT be folded into scheduling
composition. Retrying a prior attempt preserves its exact rendering/evidence; a new
attempt still performs the existing current-state and disclosure checks.

## 7. Synchronous mutation effects and propagation

`MutationEffects` contains exact affected identities and before/after versions or
revisions, plus the proven change categories needed by existing consumers: time,
lifecycle, people, facets, policies, presentations, ownership, relations/bindings and
recurrence. Item-version allocation alone is not evidence that all categories changed.
This internal record is not the public `changed_dimensions` enum or a durable event.
Public ordering, exclusive presentation-only branches and continuity proofs stay exact.

An explicit writer/effect inventory MUST cover the selected ordinary, direct low-level
and recurring writers. One application-owned propagation entrypoint coordinates the
required existing catalog invalidations, epochs, derived indexes and continuity facts
inside the same transaction; ledger primitives retain actual persistence ownership.
Existing trigger/finalizer-owned effects are accounted for, not duplicated. No-op/replay
paths add no new mutation consequences beyond their existing receipt rules.

The RF3 seam MUST be established before recurring R3 all-writer integration. R3 separately
adds the ratified recurring dirty/CAS, automatic planning and attempt-safety behavior;
the seam itself neither activates that behavior nor counts as R3 completion. Do not add
a generic event bus, after-commit repair queue, global eager reconciliation or fresh
history/ID format. Missed required propagation is an invariant failure, not something
the next daemon tick is expected to repair.

## 8. Incremental verification and exit gates

RF0 records the exact code/worktree baseline, owning contracts, helper/caller inventory,
and any intentional caller-specific differences before extraction. Pre-existing local
changes are preserved and separately identified, not silently folded into a refactor.
Characterization fills gaps in existing tests without rewriting expected behavior.

| Gate | Required executable evidence before accepting the corresponding implementation |
| --- | --- |
| IO-01 / RF1 | Ratcheted import/call checks: extracted operations have no command dependency, child command invocation or child commit. Explicit untouched exceptions cannot grow silently. |
| IO-02 / RF1 | Ordinary schedule, single-occurrence binding and recurring callers exercise the same extracted operations. Exact identities, canonical JSON, error precedence and family receipts match the baseline for fixed inputs, clock and ID source. |
| IO-03 / RF2 | Real transaction fault injection after item, owner, binding, policy/application/presentation, work, audit and receipt stages; nested rollback, finalizer failure and interruption leave no partial durable or Python state. |
| IO-04 / RF2 | Empty/eight-facet copy-forward, opposite-role preservation and empty clears, independent policies sharing an intent, manual-customized restoration and terminal/suppression vetoes retain existing semantics. |
| IO-05 / RF2 | Shared proof/hop/row/work/output/time budgets, whole-unit page rollback, continuation and commit-cutoff checks retain exact accounting; failed trials cannot refund consumed proof or strand accepted units. |
| IO-06 / RF1–2 | Protected admission and replay/release denial tests, prospective-owner/disclosure checks, trusted-local behavior and dry-run rollback; a missing capability never grants local authority. |
| IO-07 / RF3 | Closed writer/effect inventory plus bypass tests; required consequences occur once with the owning write, rollback leaves none, no-op adds none, current work/attempt freshness stays effective. |
| IO-08 / each checkpoint | Existing focused tests, full regression suite, contract/package synchronization and frozen artifacts pass; new operation/state boundaries are typed. No public activation, schema, identity or evidence drift. |

Use disposable ledgers and fake clocks/adapters when implementation is authorized.
Compare persisted and public evidence, not merely final dates or test counts. The
current suite remains the baseline; deleting parity tests or accepting changed golden
bytes is not a refactoring strategy. A replay fixture from before extraction MUST
remain usable after it, with the existing protected release checks.

RF1 extracts shared operations; RF2 establishes complete mutation and state ownership;
RF3 establishes propagation before R3. R2 resumption requires RF0–RF2 evidence and
explicit operator direction, while its original remaining functional tests still apply.
R3 also needs RF3 and the original R2 exit; R4 alone activates the recurring family.
This draft does not authorize any of those implementation steps or an external audit.

Unrelated module decomposition, shared codec frameworks, neutral read-module moves,
test-builder cleanup and advisory utility placement remain later, demand-driven work.
Deferred resilience/retention/scalability initiatives are not reopened. No new product
decision is proposed here. Concrete module/type granularity must be checked against
ordinary update, single-occurrence binding and recurring restoration before RF1/RF2
are accepted; any discovered behavioral conflict returns to the owning specification.
