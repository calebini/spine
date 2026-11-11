# Internal architecture assessment: shared operations before more integration

Date: 2026-11-11. **Assessment and proposal, not an accepted architecture change.**

Baseline: `e540a91` plus the preserved, uncommitted R2 admission/read continuation.
The unrelated `AGENTS.md` edit is also preserved. Normal release declarations are
0.11.2/schema 19; recurring-task storage/commands are internal candidate work, not
an activated public family. This report must not be read as deployment advice.

## Executive verdict

**Recommend broader internal restructuring of the application-operation layer,
delivered through targeted extractions. Do not replace the ledger architecture.**

The problem is larger than a few private imports, but substantially smaller than
a redesign of Spine. The domain model, immutable version/history discipline,
canonical identities, SQLite transaction boundary, source proofs and persisted
delivery-attempt gate are useful foundations. Recurring tasks mostly compose
existing entities rather than introducing a competing task model. Retain these.

The weak point is the contract *between internal writers*. Shared operations live
partly inside command handlers, partly in ledger callbacks, partly in feature
hooks and partly in transport wrappers. A new use case must know too much about
the ordering and bookkeeping of several existing features. Passing tests show
that particular callers perform that choreography correctly; they do not make
the choreography a reusable, enforced interface.

Three changes deserve priority before adding more recurring-task behavior:

1. Give shared scheduling, binding and notification operations an explicit home
   below command/transport adapters, with typed inputs and results.
2. Make a complete item change and its required supporting-data/notification
   consequences a single application responsibility. Preserve the different
   semantics of ordinary update, reschedule, role-only edit and generation restore.
3. Encapsulate transaction-local mutation state and rollback obligations, keeping
   the current transaction/finalizer protections rather than replacing them.

This assessment does **not** reproduce a new live corruption, unauthorized read
or duplicate-send defect. It identifies observed structural coupling, one concrete
class of duplicated planning rules, and credible omission/drift mechanisms. Their
severity is integration and maintenance risk, not an assertion of a broken release.
R3's absent all-writer/attempt integration is already planned, unpublished work;
it is not mislabeled here as a regression in the released feature set.

## Scope, method and limits

Read the repository instructions, current backlog/roadmap and their relevant
delivery evidence first. Followed actual imports and representative functions
across CLI, HTTP, worker, commands, services, domain codecs and persistence.
Read-only AST diagnostics examined **162 Python modules**, including local imports:

- 27 `services -> commands` import statements; 25 statically resolved calls from
  services to private command helpers. These counts are navigation aids, not a
  quality score or proof that every edge is wrong.
- `commands/core.py`: 9,606 lines; `commands/temporal_bindings.py`: 1,452;
  `services/recurring_task_children.py`: 796. Size alone is not a finding; the
  cross-responsibility call paths below are the evidence.
- Re-executed the read-only AST portion of the closed item-writer inventory:
  **27 producer-function entries match**, and literal item-version SQL insertion
  occurs only in `ledger/items.py`. Registered allocators remain `item_create`
  and `item_version_from_draft`. This is not a general Python alias/dynamic-SQL
  proof, nor proof of all propagation obligations.
- Found no `core` imports of commands/services/ledger/web/adapters in that scan.
  Core does depend on the timezone resolver; it is not wholly isolated from
  environment-backed timezone data.

Source links and line references below describe this working snapshot. Retained
test files were inspected, not rerun here. The prior R2 run's 1,402 tests/one skip
is historical regression evidence, not fresh verification of this assessment or
proof of architectural completeness. No application commands, runtime tests,
ledgers, migrations, providers or external reviewers were invoked. Only this
report and minimal backlog/plan tracking are edited. No normative contract changed.

## Current dependency and execution picture

Arrows mean calls/dependencies, not network boundaries. All of this remains one
Python component and one canonical ledger.

```text
CLI ------------------> commands.core.handle / family executors
HTTP --> web admission ---> commands.core / private handlers + feature hooks
            |                 |                ^
            |                 v                |
            +----------> services --------------+
                           |      scheduling calls handle for durable commands
                           |      recurring services call private command helpers
                           v
                     ledger operations <---- domain codecs/algorithms (core)
                           |
                LedgerConnection + SQL constraints + touched-state finalizers
                           |
                         SQLite

Tickerd --> Spine adapter --> scheduling / eligible work / processor
                                           |
                                  attempt + rendering persistence
                                           | commit, then external call
                                      delivery adapter
```

### Representative paths actually traced

| Path | Representative call chain and boundary |
| --- | --- |
| Trusted-local read | [CLI request/open/context](../../src/spine/commands/cli.py#L123) -> [handle/dispatch](../../src/spine/commands/core.py#L116) -> `_handle_schedule_show` (core:664) -> [schedule readback](../../src/spine/services/schedule_readback.py). The CLI opens the ledger; it is not a client of HTTP admission. |
| Protected independent read | [HTTP v2 read routes](../../src/spine/web/http.py#L247) -> [ReadService.execute](../../src/spine/web/read_service.py#L25) -> `ReadPager` -> [read_authorized](../../src/spine/web/read_release.py#L109) -> snapshot/assembly/projection -> fresh release fence. Optional linked data is not automatically authorized by access to the main item. |
| Ordinary mutation | `task.update` -> [common update](../../src/spine/commands/core.py#L2986) -> [create_item_version_from_draft](../../src/spine/ledger/items.py#L341) -> supporting copies/extension/current-pointer CAS/audit -> command receipt -> outer finalizers/commit. |
| Composite scheduling | [schedule.create](../../src/spine/commands/core.py#L1446) resolves time, location, profile/policies and builds a persistence callback. The item writer calls that extension; the bundle creates canonical dependents/work and a receipt in the owning transaction. Successor people/rendering paths inject hooks; [protected scheduling](../../src/spine/web/people_schedule_service.py#L108) also owns admission, owner insertion and release proof. |
| Existing follow-source reconciliation | [temporal binding extension](../../src/spine/commands/temporal_bindings.py#L925) appends binding evidence, classifies work, cancels eligible rows, materializes against the successor and records the receipt, inside `create_next_item_version`. |
| Internal recurring reconciliation | [recurring command execute](../../src/spine/commands/recurring_tasks.py#L521) -> [Page/reconcile](../../src/spine/services/recurring_task_reconcile.py#L109) -> source proof/lifecycle/adoption -> [children.create/change](../../src/spine/services/recurring_task_children.py#L88). Whole-unit savepoints retain or roll back SQL and Python state; page receipt/cursor fit determines the retained prefix. |
| Scheduled delivery | [runner preflight](../../src/spine/runtime/tickerd_runner.py#L48) -> Tickerd -> [Spine adapter](../../src/spine/adapters/tickerd.py#L87) -> work freshness -> [attempt-backed processor](../../src/spine/adapters/side_effects.py#L100) -> [prepare_work_attempt](../../src/spine/services/attempts.py#L32) -> durable attempt/rendering -> sender -> outcome. Rendering admission rechecks current truth under a writer transaction; the external send is after persistence. |

## Foundations that should remain

1. **One authority, useful domain separation.** Events and tasks, participation,
   access ownership, routes, recurrence and notifications are distinct facts.
   Archetype/facet definitions and values retain immutable revision identity.
   Recurring assignments create ordinary tasks, not a separate task subsystem.
   See [item drafts](../../src/spine/ledger/item_drafts.py),
   [facet snapshots](../../src/spine/ledger/facets.py), and
   [recurring historical decoding](../../src/spine/ledger/recurring_tasks.py#L540).
2. **Central allocation and actual atomicity.** The item-version writer checks
   target freshness, copies supporting data, updates the shell with a CAS and
   records an audit. [LedgerConnection](../../src/spine/ledger/transactions.py#L129)
   blocks unfinalized commits, absorbs nested helper contexts, rejects child
   commits/scripts and rolls back failed finalization. These are more than naming
   conventions. Preserve the checks and fault tests.
3. **Identity/replay and contract rigor.** Canonical JSON/hashing and persisted
   receipts are shared; [compiled command requirements](../../src/spine/commands/registry.py#L348)
   exact-match dependencies, with deliberately frozen web pins. Bounded
   [schema preflight](../../src/spine/ledger/preflight.py#L78) checks expected object
   identities/DDL without routine whole-ledger verification. Do not loosen these
   protections to make extraction easy.
4. **No send without evidence.** The attempt gate and immutable rendered attempt
   replay are sound boundaries. [Rendering delivery tests](../../tests/test_rendering_delivery.py#L419)
   cover real SQLite exclusion against revocation; replay suppression is explicit
   in `adapters/side_effects.py:113`. Keep rendering freshness separate from merely
   having produced a candidate message.
5. **Real, not cosmetic, access separation.** HTTP applies selected-identity
   permissions/replay links and fresh release checks. Trusted-local CLI authority
   is deliberately broader. `identity_basis=self_selected` is honest identification,
   not strong authentication. An internal refactor must not silently change that
   accepted trust model or expose trusted-local operations over HTTP.
6. **Useful pure logic already exists.** Recurrence normalization/expansion,
   canonical IDs, notification schedule normalization, rendering calculations and
   source identity proofs should be retained. Not every cross-domain operation
   belongs in a command handler, but it need not become a new service process.

## Complexity: what is intrinsic, chosen, and accidental?

| Category | Examples | Treatment |
| --- | --- | --- |
| Intrinsic to this behavior | DST and local/UTC distinction; occurrence identity versus moved time; independently completable child tasks; route versus owner; races between mutation and send | Preserve explicit domain facts; do not conceal them with generic blobs or a universal state flag. |
| Chosen guarantees | Immutable history, exact hash/replay bytes, source-only cancellation/restoration with a new generation, three-way adoption, protected attempted work, exact byte-bounded pages, permission-release fences | They have real cost. Keep them unless the operator explicitly changes product policy. Refactoring cannot promise to remove their state machines. |
| Accidental implementation cost | Calling private command helpers from services, repeatedly wiring copies and policy links, passing an entire mutable `Page` to child operations, manually enumerating transaction trackers, duplicate range calculations, loosely typed hooks, storage proof depending directly on wire-receipt structure | Reduce through owned shared operations and typed seams. These costs are not required by immutable history or auditability. |

## Prioritized findings

Priority means recommended sequencing, not a public defect severity. Each finding
separates the observation, failure mechanism and counterevidence.

### F1 — Shared application operations are trapped in command modules

**Priority: now. Type: observed boundary weakness; confidence: high.**

Evidence: [recurring children:239/248](../../src/spine/services/recurring_task_children.py#L239)
call `_schedule_resolve_delivery` and `_schedule_normalize_policies`; child
reconciliation at [548/565](../../src/spine/services/recurring_task_children.py#L525)
calls `_schedule_reconcile_work_plan` and `_schedule_materialize_successor`.
Binding revision construction is reached through
[commands.temporal_bindings:130](../../src/spine/services/recurring_task_children.py#L130).
[Configuration:53](../../src/spine/services/recurring_task_configuration.py#L53)
and [restoration:118](../../src/spine/services/recurring_task_restoration.py#L118)
repeat the route dependency. Commands import services back; reconciliation locally
imports command projection/receipt helpers at `recurring_task_reconcile.py:492/606`.

Consequence: changing schedule wire normalization, command context, failure mapping
or a helper's side effects can change recurring behavior without changing its
contract. Local imports avoid import-time failures but do not remove conceptual
cycles. A function move alone is insufficient for helpers that mix route lookup,
normalized domain inputs, persistence and command-specific identifiers.

Counterevidence: reuse avoids divergent copies; the actual canonical ledger/domain
algorithms are shared. Some dependencies are only placement:
`services/notification_profile_application.py:9` imports `command_derived_id` from
`commands.receipts`, which reexports `core.hashing` at receipts:11. Occurrence helper
aliases in `commands/core.py:104` already point at lower-level owners. These are
straightforward extractions, not justification for redesign.

Action: extract named binding, route, notification plan/materialization and read
operations under `services`; move pure transforms to `core`, persistence to
`ledger`. Keep temporary compatibility aliases for old internal callers while
migrating them. Explicitly separate operation inputs from command envelopes.
Verify ID/error/receipt parity for every migrated caller; no fresh runtime defect
is claimed solely from the dependency graph.

### F2 — Complete mutation obligations remain caller-managed

**Priority: now for the operation seam; before R3 for all-writer adoption.
Type: architectural omission risk, with a concrete prior repair; confidence: high.**

Evidence: [items:341](../../src/spine/ledger/items.py#L341) accepts arbitrary
prerequisite and canonical-extension callbacks. It centrally copies facets,
locations, roles, policies and profile facts, but does not itself own the whole
schedule mutation. [Supporting copy:121](../../src/spine/ledger/supporting.py#L121)
copies policies before profile application links. A replacement then has to
retarget those links: [core:9038–9071](../../src/spine/commands/core.py#L9038)
contains the narrow direct reminder-edit/disable repair from `e540a91`.

Representative paths: schedule update's `persist_bundle` (core:2650); binding
reconcile's extension (temporal_bindings:925); recurring child extension
([children:451](../../src/spine/services/recurring_task_children.py#L451)). Each
knows which binding/catalog/policy/work actions must accompany a version. Child
creation also inserts ownership header/history directly at children:174 before
presentation validation. Web creation has a separate owner hook.

Failure mechanism: a legitimate writer can allocate a structurally valid successor
and omit a semantic consequence, or perform required steps in the wrong order.
Examples are a copied application pointing at the replaced policy, missing catalog
invalidation, or materialization against predecessor rather than successor time.
Some become FK/finalizer errors and roll back; others manifest as stale readback,
unnecessarily blocked work or missed scheduling rather than malformed rows.

Counterevidence: the copy helper, allocation guard, constraints and real writer
parity tests already prevent many omissions. Ordinary `task.complete` deliberately
does not perform work reconciliation; current-state attempt checks prevent sending
for a completed task ([work:292](../../src/spine/ledger/work.py#L292)). That behavior
must not be "fixed" by globally materializing or cancelling work on every version.
Likewise, ordinary writers' lack of recurring dirty propagation is the pending R3
obligation, not proof that the published ordinary commands are defective.

Action: a shared prepared item/schedule change must explicitly own supported
effects and distinguish `no reconciliation`, `reconcile existing` and `materialize
within supplied bounds`. Keep the low-level allocator, but stop requiring each
new caller to construct its supporting-data callback chain. Add all-writer
participation checks for these effects before recurring activation.

### F3 — Transaction-local state is correct by enumeration, not encapsulation

**Priority: narrow hardening now. Type: maintenance risk; confidence: high.**

Evidence: [transactions:167](../../src/spine/ledger/transactions.py#L167) clears
feature trackers; [185](../../src/spine/ledger/transactions.py#L185) runs ordered
finalizers; [271](../../src/spine/ledger/transactions.py#L271) separately lists
the fields that must be copied/restored for a unit rollback. TEMP-trigger Python
callbacks are not rolled back by SQLite. Recurring
[Page.unit/rollback_unit](../../src/spine/services/recurring_task_reconcile.py#L154)
has a second explicit snapshot list for progress/work/result state. Policy removal
also reaches into `_rendering_pending` at
[notifications:301](../../src/spine/ledger/notifications.py#L301).

Failure mechanism: adding a tracker to initialization/finalization but not rollback
can leave a rolled-back unit represented in commit validation or consume an epoch
that SQL restored. Adding a Page accumulator without rollback participation can
leak IDs or counts from an abandoned suffix into a receipt. Manual context-manager
entry/exit for a retained prefix makes ownership harder to review.

Counterevidence: `command_unit` already solves the fundamental SQL/Python rollback
problem, including interrupted SQLite transactions. The finalizer is fail-closed.
[Transaction tests](../../tests/test_ledger_transactions.py#L55) and the new
[mid-page rollback test](../../tests/test_recurring_task_admission_reads.py#L283)
exercise it. No presently missing tracker was demonstrated by this assessment.

Action: keep `LedgerConnection`, but give transaction-local feature state a closed,
typed checkpoint/reset/finalize owner; give Page accumulators an explicit snapshot
type. A new state component must supply all lifecycle operations once. This is a
small in-process facility, not a dynamic plugin registry. Test every component's
success, unit rollback, outer rollback and failed finalization. Preserve finalizer
ordering and consumed proof-budget semantics; not every counter should roll back.

### F4 — Domain continuity is coupled to command receipts and audit encodings

**Priority: protect during extraction now; decoder cleanup later.
Type: deliberate evidence mechanism with an accidental coupling; confidence: high.**

Evidence: [people_authoring.verify_retained_version_edge:71](../../src/spine/ledger/people_authoring.py#L71)
classifies a facet/people/presentation-only edge from audit IDs/hashes and receipt
facts. [_schedule_edge:158](../../src/spine/ledger/people_authoring.py#L158) reads
`changed_dimensions`, the v4 contract and normalized result equality. Notification
policy resolution and work freshness consume this continuity evidence; rendering
tests cover mixed-intent descendants.

Consequence: changing an audit action, receipt shape or "internal" ID path during
refactoring can invalidate already-stored continuity and stop otherwise eligible
reminders. It also makes adding a new valid non-temporal writer require knowledge
of the evidence formats of older command families.

Counterevidence: using immutable evidence rather than similarity is intentional
and avoids treating an arbitrary same-time mutation as safe. The existing proof
checks hashes, exact version edges and bounded evidence; this is not merely string
matching. Removing this proof or replacing it with trusted changed-dimension flags
would weaken safety.

Action: preserve all historical decoders, audit bytes and identity derivations.
Expose a typed `ContinuityEvidence` read interface backed by the existing formats.
Do not create a new evidence table or reinterpret old history in the initial
refactor. A future durable format would be a separately reviewed contract change.

### F5 — Protected admission is real, but its internal seam is tangled

**Priority: explicit authority inputs in new shared operations now; broader web
extraction later. Type: architectural risk, not a proven access bypass; confidence: high.**

Evidence: [web/service.command:213](../../src/spine/web/service.py#L213) checks
account/actor, receipt ownership and reference permissions before invoking `handle`.
Successor [people_schedule_service:124–172](../../src/spine/web/people_schedule_service.py#L124)
instead calls private schedule handlers with people/rendering hooks. It supplies a
prospective owner before authoring and verifies successors before release. Command
rendering runtime imports `web.permissions`/`WebError`; people runtime imports
`web.read_contracts`. `CommandContext` holds `Any` hooks/configuration.

Failure mechanism: extracting the shared mutation without its admission hooks could
make protected and trusted-local execution accidentally indistinguishable, omit
owner-before-disclosure ordering, or authorize a replay solely because a domain
receipt exists. Conversely, forcing web permission machinery into all operations
would couple local scheduling to account/realm provisioning again.

Counterevidence: current protected wrappers check permissions inside transactions,
bind receipt links and recheck release; local execution intentionally has broader
authority. HTTP header/Origin/Host rules at
[http:106](../../src/spine/web/http.py#L106) are transport protections, not proof
of human identity. No authentication redesign follows from this assessment.

Action: new internal operation contexts must distinguish explicit trusted-local
authority from an admitted protected operation; never treat a missing permission
object as implicit full access in the new interface. Keep release/replay disclosure
checks at the protected boundary. Extract neutral errors, contracts and permission
interfaces away from HTTP modules incrementally without changing grants or trust.

### F6 — Duplicate planning rules and misleadingly composable bounds

**Priority: extract the shared rules used by R2 now; wider boundedness work remains
deferred. Type: observed duplication and integration risk; confidence: high.**

Evidence: [_schedule_recurrence_source_range/_schedule_policy_offsets](../../src/spine/commands/core.py#L6072)
and scheduler [_recurrence_source_range/_policy_offsets](../../src/spine/services/scheduling.py#L718)
repeat offset traversal, the two-day conservative margin and local-range conversion.
They already differ in malformed input handling (Sequence versus list and error
classification), though valid normalized policies should produce the same range.
Three stale-work consumers have distinct checks: command work classification
at core:6718, [ledger notification reasons](../../src/spine/ledger/notifications.py#L143),
and [attempt eligibility](../../src/spine/ledger/work.py#L270).

Recurring [reconcile_work:538](../../src/spine/services/recurring_task_children.py#L538)
pre-bounds work rows, then calls the command classifier, which reads all item work
at core:6729. This is bounded in the current transaction by the caller's precheck,
but the callee signature does not express that precondition. A future caller can
assume it is independently bounded. The scheduler correctly separates a read-only
plan from dispatch at [scheduling:118–137](../../src/spine/services/scheduling.py#L118).

Counterevidence: scheduler no-op suppression is deliberate and tested. Attempt
freshness must be stricter than plan-time classification; different projections and
error order are not necessarily duplicated *policy*. Do not replace them with a
single boolean predicate or change published reason precedence.

Action: extract shared normalized range/offset computation and typed freshness
facts; keep operation-specific decisions and reason ordering. Shared work operations
must take a bounded selection or an explicit budget, not rely on undocumented
pre-scans. Preserve no-op automatic planning versus receipt-bearing explicit calls.

Related but **not a new prerequisite**: [list_eligible_work:27](../../src/spine/services/work.py#L27)
fetches eligible candidates before applying the output limit, and old generic
[dry-run:137](../../src/spine/commands/core.py#L137) copies the ledger in memory.
These are visible size-dependent paths, not measured outages here. Keep them with
the already deferred resilience/scalability work; do not restart that initiative
under the name of this refactor or claim the refactor fixes it.

### F7 — Family codecs and error boundaries can hide internal defects

**Priority: touched seams now; wholesale validation consolidation later.
Type: risk and maintenance cost; confidence: high for code, medium for impact.**

Evidence: family runtimes separately validate schemas, select union errors, sign
cursors and decode replay; the current uncommitted
[recurring runtime](../../src/spine/commands/recurring_task_runtime.py#L128)
fixes its own syntax ordering and Unicode classification. In
[rendering_candidate:124](../../src/spine/commands/rendering_candidate.py#L124),
`KeyError`, `TypeError` and `ValueError` after handler entry map to `invalid_request`.
An implementation indexing mistake can therefore look like caller failure.
[People web execution:231](../../src/spine/web/people_schedule_service.py#L231)
distinguishes pre-admission input from later domain failure differently.

Counterevidence: separate families genuinely have different wire precedence,
cursor domains and compatibility promises; global normalization would be risky.
The exact compiled registry and offline schema closure are assets, not duplication
to delete. Error envelopes currently prevent private exception content leaking.

Action: introduce typed internal failure categories at extracted operations, with
explicit family/transport mapping; retain the existing public codes and order.
Unexpected internal faults need a distinguishable internal diagnostic path, not
new public detail leakage. Reuse generic offline-validator/codec machinery only
where tests establish semantic equivalence. No new error taxonomy on the wire is
proposed without separate approval.

### F8 — Tests enforce some boundaries strongly, but not the application boundary

**Priority: guardrails alongside the first refactor, not after it.
Type: observed coverage distinction; confidence: high.**

Evidence: [facet writer inventory](../../tests/test_facet_writers.py#L59) scans
allocation calls and SQL literal sites; [people writer parity](../../tests/test_people_writer_parity.py#L51)
exercises actual copy/replacement; transaction, rendering-delivery, scheduler and
physical-race tests cover real safeguards. Those inventories do not describe
every change-propagation obligation, and no general layer-dependency gate was
found in the inspected tests/configuration. The default strict mypy targets in
[pyproject.toml](../../pyproject.toml) cover `core` and `ledger`, not all new service
seams; focused runs supplement them, but `Any` remains common there.

Concrete example: [children.change(page: Any)](../../src/spine/services/recurring_task_children.py#L383)
mutates `page.work`, `page.runtime`, `page.changed` and `page.mutations` as well as
SQL. Its type does not declare which state must be checkpointed. R2's admission
tests also borrow setup/methods from other test classes
([admission tests:16](../../tests/test_recurring_task_admission_reads.py#L16));
useful reuse, but incidental changes to a donor test can affect unrelated cases.

Action: ratchet allowed imports and writer/effect participation; type only the new
operation boundaries and Page state first. Preserve integration/fault tests and
add transport parity plus exact stored-byte checks around moves. Gradually move
shared test setup into neutral builders, without weakening scenarios or counting
offline fixtures as runtime proof. No test-count target or blanket test rewrite.

## What can a normal writer actually bypass?

| Responsibility | Present protection | Residual / required treatment |
| --- | --- | --- |
| Item-version allocation and facet snapshots | Two registered allocators, TEMP tracking, commit authorizer/finalizer, closed caller inventory | Not generally bypassable through ordinary production writers; retain and extend rather than replace. Raw SQLite under an operator is outside this application trust boundary. |
| Supporting copies | Central copy-forward plus FK/definition checks | Intentional successor replacement still requires application/presentation link repair. Put that complete operation behind one owner. |
| Notification behavior after a mutation | Work freshness/attempt gate and explicit schedule/binding reconcile | A writer can omit reconciliation by design (e.g. task completion). Make the mode explicit; do not erase that public distinction. |
| Binding/catalog/recurring invalidation | Binding callers increment their catalog; recurring touched-row validation checks its own graph | No universal source/task/owner mutation consequence hook yet. R3 must cover normal writers, but should use an owned effect interface, not repeat bespoke plumbing. |
| Access epochs and disclosure ordering | Protected wrappers and the local ownership primitive; transaction marker | The operation that creates ownership must own epoch/header/history ordering. Do not leave this as optional caller SQL. |
| Commit/receipt consistency | Outer transactions, shared receipt rows and per-family replay verification | New internal operations must never emit child command receipts or commit independently. Preserve family-specific historical replay, including its release permissions. |

## Proposed smallest coherent target

Use the existing package and SQLite, not new processes. `services` becomes the
explicit application-operation owner; `commands` becomes wire adaptation and
version-specific command/replay policy over it. This is an incremental direction,
not a demand to move all 9,606 lines at once.

```text
CLI / HTTP admission / worker adapter
                 |
      command-family adapter or internal invocation adapter
       (wire validation, exact replay/error/response policy)
                 |
       application operations in services
       - prepared item/schedule change
       - binding and recurring reconciliation
       - notification plan / work reconciliation
                 |
         domain logic in core + persistence in ledger
                 |
      owned LedgerConnection transaction and typed mutation state
                 |
               SQLite

worker processor -> attempt admission operation -> commit evidence -> adapter send
HTTP retains authorization/release fences around applicable operations/results.
```

Allowed dependencies:

- `core`: canonical/domain logic and explicitly supplied timezone capability;
  no ledger, commands, services, web or vendor adapter imports.
- `ledger`: SQL, stored invariant validation, immutable decoding and transaction
  primitives; may use `core`, never command envelopes or HTTP implementations.
  Existing receipt-derived continuity is retained behind a decoder interface.
- `services`: orchestration over `core`/`ledger` and narrow capability interfaces;
  no import of command internals. Not every external capability needs an abstract
  repository class; concrete SQLite functions remain appropriate.
- `commands`: family/version validation, input conversion, replay/receipt and
  error/response projection over shared operations. They may use a neutral
  invocation service for transaction ownership rather than own duplicated wrappers.
- `web`/CLI/worker: identify/admit, select a supported operation, enforce transport
  budgets and release rules, then invoke it. They cannot manufacture authorization
  by accepting flags in model-authored JSON.
- External adapters implement delivery/research interfaces; composition roots wire
  them. Existing experiment utility imports from adapters are later cleanup, not
  a reason to redesign the advisory work during this pause.

### Explicit interfaces to introduce, not new public wire contracts

Names are illustrative and require implementation design review before acceptance.

| Interface | Explicit inputs | Explicit result / owner |
| --- | --- | --- |
| `InvocationContext` | actor, authority (`TrustedLocal` or admitted protected capability), command family/ID, sampled clock, deadline/budget, identity allocation plan | Stable context, not a bag of hooks or a raw request. Outer invocation owns replay and commit. |
| `prepare_item_change` / `apply_item_change` | expected item version, typed create/update/lifecycle intent, keep/replace/clear supporting sets, explicit owner plan, pinned profile/presentation plan, binding intent, reconciliation mode | Item/version IDs, audit facts and typed `MutationEffects`; complete supporting changes in the supplied transaction. No send, child receipt or child commit. |
| `prepare_notification_plan` | actual or prospective owner/item context, exact profile/template selections, custom policies, route, disclosure authority, identity plan | Immutable resolved policy/presentation plan; no incidental authoring during validation. Installing a profile never grants disclosure. |
| `reconcile_notification_work` | target snapshot, current policies, changed facts, bounded work selection/budget, optional materialization interval | Created/cancelled/retained/protected IDs, reasons and charged resource use. Preserve per-call public effect semantics. |
| `resolve_binding_source` / `prepare_binding_change` | stored selector/proof, current source facts, target/version, offset and accepted lifecycle intent | Source/binding evidence and planned change. No command-module import or guessed source identity. |
| `MutationEffects` + synchronous propagation | exact old/new versions and proven dimensions: time, lifecycle, people, facets, policies/presentation, owner, relation/binding, recurrence | Required catalog invalidations and existing continuity facts in the same transaction; R3 adds its already-specified coalesced dirty writes. No asynchronous generic event bus. |
| `TransactionMutationState` / `PageState` | closed feature state and explicit budget/result accumulators | Snapshot/restore/reset/finalize, with one registration point per state component and no private-field writes from callers. |

The identity plan must distinguish outer command identity from generation-scoped
child seeds and predecessor identity. Do not regenerate IDs under a new operation
name. A generation restore is not ordinary task create with the latest defaults:
it retains actual predecessor choices while creating new scoped identities.

Transaction ownership remains **one outer boundary per command/page**, including
audit, receipt and propagation. Lower operations join it; current-state/commit-cutoff
checks run before commit. Bounded whole-unit rollback remains real SQL rollback
plus Python checkpoint restoration. Plan-time proof budgets and mutation counters
must each retain their specified accounting behavior, not share one generic counter.

Historical replay remains owned by each contract adapter: exact normalization,
identity/evidence checks and old response bytes remain unchanged. Protected replay
still checks current release authority. Ordinary explicit no-ops keep their receipts;
automatic idle planning remains non-durable. Attempt admission is a separate
transaction before external sending; it is not folded into a long scheduling unit.

## Retain / now / later

**Retain as-is in semantics:** schema/history, canonical preimages, contract pins,
source lineage, policy-specific intent continuity, role/owner/route separation,
attempt evidence, trusted-local authority and protected release fences, bounded
preflight, Tickerd ownership, scheduler no-op suppression.

**Refactor now, if approved:** the scheduling/binding/notification operations used
by R2; narrow transaction state encapsulation; explicit item-change ownership and
identity/authority/budget inputs; ratcheted architectural tests. Apply them to both
existing scheduling/binding writers and recurring callers so the new interface is
not a parallel subsystem used only by R2.

**Before R3 integration:** inventory normal writers' mutation effects and establish
one synchronous propagation entrypoint. R3 still supplies the new recurring
invalidations, source/target races and attempt guards under its existing plan.

**Later:** remaining command-module decomposition, common contract-loader mechanics,
neutral permission/read modules, test fixture builders, experiment utility placement.
Keep the release-fenced read architecture. Do not make an all-module typing campaign,
new auth system, ORM, event bus, workflow engine, microservices or retention/scalability
qualification a prerequisite for completing recurring tasks.

## Proposed incremental execution plan

No slice below is authorized by writing this report. Dependencies and exit tests
are explicit so this initiative does not turn into an indefinite cleanup project.

### RF0 — Preserve baseline and accept the narrow internal design

After operator approval, checkpoint the already-verified R2 continuation separately
from this assessment; leave unrelated edits excluded. Inventory the exact helpers,
callers, error precedence and persisted preimages that the first extraction touches.
Define the operation/authority/identity/effect interfaces in the appropriate internal
architecture documentation, preserving current normative owners. If a proposed
change needs new public behavior, stop and seek approval instead of hiding it in
refactoring. Add characterization cases only where the touched behavior lacks them.

Exit: agreed narrow scope; exact baseline; no migration/public declaration changes.

### RF1 — Extract shared operations with behavioral parity

Depends on RF0. Move pure aliases to their existing lower owners; extract route
resolution, policy planning, binding revision construction and work classification/
materialization into named services. Migrate ordinary schedule, single-occurrence
binding and recurring callers together for each operation. Scheduler dispatch may
temporarily retain its public command invocation adapter, but business operations
must not call command handlers. That adapter preserves command IDs/receipts.

Verify exact IDs, receipts, stored policy/selector/binding facts, error precedence,
ordinary no-op behavior and protected work. Compare CLI/shared-handler and protected
web paths for touched operations with their intentional authority differences.
Add a no-new reverse-import/private-command-call rule, with a precise temporary
allowlist for untouched modules. Exit: no R2 service calls command internals.

### RF2 — Own item-change composition and mutation state

Depends on RF1. Introduce typed plans/results for the touched create/change/restore
operations. Encapsulate supporting policy/application/presentation updates, explicit
ownership initialization and binding changes. Replace callback choreography for
these callers with a closed prepared operation; keep the existing allocator and
SQL guardrails. Encapsulate transaction/Page snapshot state without changing its
commit or budget semantics. Preserve prospective-owner-before-disclosure ordering.

Verify failures after each task/owner/binding/policy/presentation/work/audit/receipt
stage; nested and outer rollback; interruption; empty/eight-facet copy; opposite
people-role preservation; shared-intent independent policies; manual customization,
terminal/source-only restore and historical replay. Compare exact persisted bytes
against RF0. Existing real tests are the starting suite, not rewritten or weakened.

Exit: a complete bounded task change requires no arbitrary command callback,
direct connection-tracker edit or whole mutable Page object at its public internal
boundary. Authority, identity, budget and reconciliation mode are explicit.

### RF3 — Establish change propagation before R3

Depends on RF2; may precede or accompany completion of remaining R2 tests after
the operator resumes that work. Create the closed writer/effect inventory for
item/recurrence/binding/relation/owner/policy changes, including direct legacy
commands. Put existing invalidations behind the synchronous application owner.
Keep current lifecycle/work-mode distinctions; do not add blanket work cancellation.
Provide the seam into which R3's ratified dirty/CAS and attempt safety will plug.

Verify all touched writers register consequences, no-op writes do not emit new
effects, rollback leaves no invalidations, access/binding epochs move exactly as
specified, and current-state delivery checks remain effective. A bypass test must
fail if a listed writer stops calling required propagation. R3 implementation and
activation remain separately gated by completion of R2, not completed by RF3.

### RF4 — Incremental cleanup after the recurring integration boundary is stable

Not a resume prerequisite. Decompose remaining handler groups, move neutral read/
permission/receipt mechanics out of transport modules, and consolidate equivalent
validator plumbing. Maintain exact family-specific codecs and frozen web pins.
Take one owner/caller group at a time. Stop when the selected risk is removed;
there is no requirement to make all functions use one framework.

### Verification and checkpoint/rollback policy

- Keep each extraction and its tests reviewable, with no opportunistic formatting,
  schema/data migration, version activation or product change in the same slice.
- Use disposable test ledgers only when implementation is approved. Run focused
  tests first, then the repository regression suite and relevant package/contract
  synchronization checks before each accepted checkpoint. A whole-suite count
  supplements, but cannot replace, the specific parity/fault assertions above.
- Executable gates: AST/import direction ratchet; closed allocator plus effect
  inventory; strict typing on new operation/state types; no command invocation or
  child commit inside shared operations; unchanged offline digests/fixtures;
  direct/protected/reconcile caller parity; historical replay and rollback tests.
- Preserve shared time/SQL/output/proof budgets across composition. No reset budget
  per child and no hidden whole-ledger work inside an extracted helper.
- Initially no durable layout changes means rollback can return to the preceding
  code checkpoint without rewriting ledger history. Keep old internal forwarding
  aliases only while needed for safe caller migration. Do not dual-execute writes.
- Any new durable state, ID derivation or wire/error change invalidates that simple
  rollback assumption and requires a separate proposal and operator approval.
- No Whetstone run or deployment is implied. If later requested, review the actual
  interface/preservation amendment, not a promise that smaller files are safer.

## Explicit recurring-task resume gates

R2 resumes only after operator approval and RF0–RF2 are complete, with:

1. Recurring services no longer depending on private command handlers/helpers;
   shared operations also exercised by ordinary schedule/binding callers.
2. One owned item-change composition for create/change/restore, explicit authority
   and identity inputs, and no lost policy/application/presentation/owner obligations.
3. Complete SQL/Python rollback participation for the touched state; exact receipt,
   identity and historical decoding parity; preserved page/resource bounds.
4. Focused cross-feature/fault tests and full regression evidence, with failures
   resolved rather than hidden behind a compatibility flag.
5. The existing R2 remaining-work list retained as functional work, not erased by
   the refactor. A new operator instruction resumes implementation.

R3 additionally needs RF3's effect interface/inventory and the original R2 exit.
Its all-writer, automatic planning and attempt-race obligations are still required.
R4 still alone activates the public recurring family. None of these gates demands
a new external system, frontend qualification campaign or maintenance fork.

## How much recurring work survives?

Most *behavioral substance* is reusable; a line-count percentage would be false
precision. Keep the source-proof/selector algorithms, schema/immutable decoders,
canonical configuration/ID logic, enrollment/generation/adoption state model,
rollback and race tests, cursor contracts and wire corpus. Preserve the current
uncommitted admission fixes rather than reimplementing them from prose.

The most change-prone areas are `recurring_task_children`, configuration's access
to command route normalization, Page-to-child mutable coupling, and command-owned
read/receipt helpers imported back into services. Rewire or restructure those;
do not discard the source identity work or re-provision the feature model.

## Decisions and uncertainty

**One immediate operator decision:** approve the scoped RF0–RF3 initiative and its
resume gates, or choose a smaller placement-only extraction with the remaining
caller-coordination risk explicitly accepted. Recommendation: approve the scoped
initiative. Simply renaming private helpers public does not solve F2/F3.

No product guarantee needs to be relaxed to follow this recommendation. Stronger
authentication, altered restoration policy, simplified history, global eager work
reconciliation and a new persistence model are not decisions needed now.

Uncertainties to resolve within approved implementation, not by guessing policy:

- Exact interface granularity: confirm with at least ordinary schedule update,
  single-occurrence follow binding and recurring restoration before freezing it.
  Avoid a universal mutation object with dozens of unrelated optional fields.
- Error precedence and historical identity differences limit how much codec/replay
  code can be unified. Characterize first; keep family strategies where required.
- No measured performance improvement, absence-of-bugs proof or full writer-safety
  proof is claimed by static inspection. The unit-state design's cost must be
  tested under existing bounded pages, not assumed better because it is typed.
- Whether a future durable continuity witness is worthwhile remains open; it is
  unnecessary for the first restructuring and cannot alter old evidence silently.
- The deferred size-dependent paths noted in F6 remain deferred. This report does
  not certify overall scalability, recovery or retention.

**Bottom line:** Spine does not need a new foundation. It needs a clearer internal
application boundary so a new feature can request a correct operation instead of
learning and repeating the ledger's entire supporting-data choreography.

## Assessment artifact verification

Local link/source-line validation checked 428 targets across this report, backlog
and implementation plan with no missing targets. Diff whitespace checks pass,
including this new untracked report. A SHA-256 comparison against the 1,474-file
starting snapshot found only the two intended tracking files changed and this
report added; no original file was removed. Runtime, tests, schemas, contracts,
specifications, existing R2 notes and `AGENTS.md` remain byte-identical to the
assessment start. No commit, push or runtime verification was performed in this task.
