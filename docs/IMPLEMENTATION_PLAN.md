# Spine Implementation Plan

Role: Roadmap rationale and delivery history; current task status lives in [BACKLOG.md](BACKLOG.md)
Last updated: 2026-10-24 (Slice 2 directory/standalone foundation; timezone work separate)

This is a non-normative delivery plan. The specifications and machine-readable contracts remain authoritative.

Timezone incident planning (2026-10-22): SPINE-062 records the operator's
2026c-to-2026e resolution failure. The operator selected
[automatic per-zone byte-identity admission](../specs/decisions/0006-evidence-bound-timezone-compatibility.md):
retain a trusted authored-release zone reference and admit matching actual bytes
from any runtime release without a release-pair allowlist or per-upgrade approval.
Reference Paris/Chicago TZif bytes match across the incident releases; deployed
provider verification and runtime acceptance remain outstanding. The specification
now covers baseline trust/retention, canonical pin preservation and diagnostics.
Codify storage/ingestion and the machine schema before runtime work, and select
mainline versus a separate 0.6.0/schema-15 backport. This does not replace the people
delivery sequence or activate the deferred resilience roadmap.

The operator-requested bounded consistency audit completed on 2026-10-22 using
stable Whetstone 0.1.0/checkpoint `6e19fe3` and the explicitly approved seven-file
Codex payload. It returned `pass_with_minor_clarification`, with zero blockers or
majors and one responsibility-matrix wording issue, now corrected. The
[audit record](TZDB_COMPATIBILITY_AUDIT.md) preserves findings, disposition and
input hashes; no convergence or runtime acceptance is claimed.

The selected planning task is
[SPINE-061](BACKLOG.md#spine-061--implement-people-and-responsibility), following
the completed source-contract task SPINE-060 and
the [people and responsibility contract](../specs/people-and-responsibility.md).
Build on existing subject-role storage, not facets or a second people registry.
Keep participation, task assignment, resource access and notification routing
independent. Scoped directory/association-disclosure policies D-01/D-02 were approved
on 2026-10-16. The logical draft passed bounded consistency review and the operator
ratified logical v1.0.0. Source-only machine candidates now cover standalone commands,
explicit scheduling/read successors, a dedicated role-only work-continuity proof,
exact cursor/error/budget rules and offline fixtures. The operator accepted the
A/B/C machine reviews and verified corrections on 2026-10-20 as sufficient for
implementation planning, not a fresh independent whole-bundle audit or runtime
qualification. All PR-01–16 runtime obligations remain pending. Existing self-only web
projections and facet-only equality are preserved; neither is silently broadened.
This planning step makes no runtime, frontend, pack, migration, commit/push or
deployment changes.

### People delivery sequence

The operator requested this implementation plan on 2026-10-20. The first slice's
concrete owner mapping and acceptance boundary are below. Reuse current subject-role
storage, version writers and finalizers; do not introduce a new people registry.
This is a delivery plan, not completed runtime evidence or an instruction to start
runtime work, expose a partial capability, migrate or deploy.

1. **Local role transactions and history.** Map all version writers and shared
   finalizers, then plan the standalone role replacement/read core and atomic
   scheduling integration together with identity, no-op/replay/dry-run, unmanaged
   copy-forward and rollback tests (PR-01–04, PR-13). Include scoped reference
   admission from PR-05, rather than adding it after the write path.
2. **Permissioned discovery and read projections.** Plan roster and labels,
   historical associations, authorized filters, snapshot-bound authenticated
   cursors and bounded indexed queries (PR-05–08, PR-12). Permission and source
   concurrency evidence from PR-16 belongs with these owners.
3. **Work continuity and writer parity.** Exercise role-only policy bijection
   across all work states, mixed edits, recurring/relative-source freshness and
   every version writer/finalizer (PR-09–11, PR-13, PR-16). Do not silently reuse
   the facet-only equality proof for people changes.
4. **Public successors, packaging and complete qualification.** Wire the explicit
   CLI/protected HTTP successors, installed schema/registry closure and frozen
   compatibility gates (PR-14–16), carrying forward every prior runtime obligation.
   Advertise no partial family; runtime evidence and activation are distinct from
   source contract review. No migration, deployment or operator-ledger work is
   authorized by this outline.

### People Slice 1 — local role transactions and history

**Goal:** implement the internal foundation for explicit event participant/task
assignee replacement and exact-version readback. Changed writes produce one
immutable successor; no-ops preserve existing identities; replay reuses receipt
facts. Assignment/attendance must not grant access or change notification routing.
Keep new public selectors unadvertised until the complete family qualifies.

#### Existing owner map

The following are inspected reuse points, not assertions that they already satisfy
the new people contract:

| Concern | Existing owner | Planned use / compatibility constraint |
| --- | --- | --- |
| Physical role facts | `src/spine/ledger/schema.sql`, `item_subject_roles` | Reuse exact item/version/subject/role uniqueness, active/inactive status and existing subject index. No table, column, schema number or migration is allocated. |
| Role reads and replacement | `src/spine/ledger/supporting.py`: `current_subject_roles`, `copy_forward_supporting_sets`, `replace_item_subject_roles` | Exact-version reads and selected-kind replacement; preserve every other role and all old-version rows. Explicit IDs must replace random helper defaults on new command-owned rows. |
| Item successor/CAS | `src/spine/ledger/items.py`: `create_item_version_from_draft`, `create_next_item_version`, `_insert_item_version` | Reuse current-version comparison, supporting-set copy, detail preservation, audit and pointer update in one transaction. Avoid allocating a version before detecting a no-op. |
| Input bundle | `src/spine/ledger/item_drafts.py` | Use existing role replacement operands; no new parallel item writer. |
| Command transaction | `src/spine/commands/core.py`: `handle`, `_dispatch_atomic`; `src/spine/ledger/transactions.py`: `LedgerConnection._commit_checked` | Receipt, audit, role facts and item pointer commit or roll back together; retain existing finalizer ownership and dry-run failure marking. |
| Receipt replay | `src/spine/commands/receipts.py`: `command_receipt`, `insert_command_receipt`, `get_command_receipt` | Validate canonical request identity and original stored result; perform the specified fresh/replay permissions separately. No reconstruction from mutable current labels. |
| Existing task/scheduling callers | `src/spine/commands/core.py`: task create/update and schedule create/update handlers | Existing task role replacement can replace both assignee and owner. Preserve that legacy contract; the new people path replaces only participant for events or assignee for tasks. Add scheduling v4 through explicit successor dispatch, not by loosening released request schemas. |
| Writer/finalizer coverage | `src/spine/ledger/facet_writer_inventory.v1.json`, `rendering_writer_inventory.v1.json`; `src/spine/ledger/items.py` | Use existing producer lists as starting inventories and reconcile actual allocation call sites. These inventories are not a completed people proof. Include create, update, completion, cancellation, archive and facet-triggered versions. |
| Unchanged work and policy meaning | `src/spine/ledger/facet_continuity.py`; notification/rendering support | Retain the facet proof's role equality. People-only continuity needs its own edge classification/proof before new writes are publicly usable; do not widen a shared equality allowlist. |
| Admission/disclosure | `src/spine/web/permissions.py`, existing identity/membership owners and reviewed people companion resolver names | Reuse existing resource ownership/grants and membership sources, while implementing the distinct roster/reference/association/label rules. Existing generic permissions alone are not proof of the new rules. |

#### Internal implementation order

1. **S1a — normalized managed sets and exact-version reader.** Implement focused
   pure normalization/equality/identity helpers plus bounded ledger projections.
   Use a small people-specific module only where the existing owner would otherwise
   mix new and legacy rules. Normalize subject IDs without coercion, distinguish
   omitted versus explicit empty replacement, reject duplicate/ambiguous/ineligible
   fresh references as specified, and compare complete managed tuples including
   inactive rows. Preserve historical IDs and unmanaged roles. Derive new row IDs
   from the reviewed canonical command/path preimages; no-op reads retain prior IDs.
   These are private components and tests, not callable new public contracts.
2. **S1b — transactional role mutation and continuity prerequisite.** Reuse the
   existing item-version draft, CAS writer, supporting-set copy and finalizers.
   Add the narrow role-only proof/reconciliation seam needed to prevent unrelated
   policy/work cancellation; implement its full work-state matrix in Slice 3.
   If that proof is not available, keep new mutation entry points private rather
   than shipping a knowingly unsafe temporary path. Inject errors after role,
   policy/audit and receipt writes to prove outer rollback. No new proof table.
3. **S1c — local handlers and scheduling successor integration.** Implement
   `item.people.show`/`item.people.update` handlers and the people portions of
   schedule create/update v4 behind the unadvertised candidate boundary. Use the
   same shared core for standalone/composite operations, with one transaction and
   one version for a composite. Owner-scope admission is part of the write, not
   deferred post-validation. Show's current-label disclosure shares the Slice 2
   resolver; do not claim full standalone read acceptance before it exists.
4. **S1d — parity evidence and checkpoint.** Exercise actual disposable-ledger
   handlers through the same transaction path as public commands, retaining the
   unadvertised boundary. Extend the actual writer inventory and regression tests;
   record which PR obligations have runtime evidence versus remaining dependencies.
   Do not turn passing internal tests into compiled capability/package activation.

S1a is the first executable sub-slice. It has a bounded code surface, no write
exposure, and acceptance tests independent of HTTP or deployment. The operator
subsequently authorized it on 2026-10-20; the checkpoint below records actual
implementation, not merely a queued background task.

#### Slice 1 acceptance tests

- Event participants and task assignees: omit/preserve, replace, clear, multiple
  subjects, inactive rows, person/agent/accountless subjects, wrong item type,
  terminal writes, duplicates and invalid/missing IDs. Preserve an existing
  opposite role, owner, watcher and recipient; do not infer related-item roles.
- Changed update: one CAS successor with deterministic IDs, one audit and receipt;
  complete old version remains readable. An equal current set produces no version
  or audit, retains the prior association IDs, and records a fresh command receipt.
- Compatible replay after later edits returns original versions/rows/effect and
  writes nothing. Conflicting command reuse, stale versions and malformed retained
  evidence refuse without partial effects. Fresh/replay permission tests use their
  distinct contract rules, including membership changes and preserved references.
- Dry-run uses the real admission/transaction path but persists nothing on success
  or failure. Check the required true-only failure marker and canonical preview IDs.
- Composite scheduling: create people atomically; people-only update requires no
  materialization; mixed ordinary dimensions commit once; presentation-only edits
  remain exclusive. Preserve old local task-role and frozen schedule versions.
- Rollback/finalization: inject failures after each affected write boundary, and
  show no orphan version/role/policy, changed pointer, audit or receipt. Observe
  declared finalizer and allocator ownership rather than bypassing it in tests.
- Continuity boundary: unchanged routing/access/facet facts, no new attempts/sends,
  correct pending-work preservation only under a proven role-only edge. Full lease,
  started/retry/terminal/recurring/source-race acceptance is explicitly still Slice 3.

Add proposed `tests/test_people_core.py` and `tests/test_people_commands.py` only
when their implementation exists. Extend existing `tests/test_ledger_item_workflows.py`,
`test_schedule_create_command.py`, `test_schedule_operations_command.py`,
`test_agent_command_contract_mvp.py`, `test_facet_writers.py`, and
`test_ledger_transactions.py` where the existing owner is exercised. The offline
`test_people_and_responsibility_contracts.py` remains a contract witness, never a
substitute for these runtime tests. Use synthetic temporary ledgers only.

#### Completion and release gates for the whole initiative

| Gate | Required evidence | Not established by Slice 1 |
| --- | --- | --- |
| Foundation | S1a–d tests; PR-01–04 and the implemented portions of PR-05/13/16 | Full protected disclosure, cost bounds and complete writer/work races |
| Read/discovery | Slice 2: PR-05–08/12 and related PR-16 races | Installed public successor parity |
| Work continuity | Slice 3: PR-09–11/13/16, including mixed edge histories and follow-source invalidation | Deployment or permission to send |
| Complete family | Slice 4: PR-14–16 plus every earlier pending obligation; installed CLI/HTTP and frozen-bundle checks | Operator-ledger migration, staging/release/push approval |

For code implementation, run focused new tests and affected owner regressions,
then strict typing/lint and the repository's full regression/synchronization/
installed-package checks in proportion to the resulting public surface. Record
actual commands and failures; no full-suite result is claimed by this planning pass.
Do not select a release/schema number from the plan. Real query-plan evidence may
identify an index need in Slice 2; that requires a separately specified migration
and manifest, never startup DDL. No product decision is currently missing; surface
an actual contract conflict if discovered instead of silently choosing semantics.

**S1a implementation checkpoint (2026-10-20):** private helpers are implemented in
`src/spine/core/people.py` and `src/spine/ledger/people.py`, tested by
`tests/test_people_core.py` and `tests/test_people_ledger.py`. The reader is one
statement over exact item/version roles; its projection has no labels or permission
decision and remains a private primitive requiring admitted callers and an outer
request budget. It returns the historical association IDs and selected/current
versions separately; all-role overflow refuses rather than truncating or repairing.
Pure admission selection identifies additions/reactivations but does not assert
subject eligibility or authorization. The shared repository guidance keeps the
semantic core independent from the ledger adapter; legacy helpers are untouched.

Verification: 17 new tests pass; with existing item workflows, transaction and
selected people/schedule/continuity/independent-read contracts, 112 tests pass in
3.925 seconds. Focused Ruff, diff hygiene and strict mypy on the two new modules
pass. Broad core/ledger typing has the same 36 errors in ten unchanged files with
or without these modules; it is not reported clean. No full suite, query-cost,
concurrent permission, write rollback, installed-package or public CLI/HTTP
qualification is claimed. Runtime/package declarations remain unchanged and all
whole-feature PR-01–16 obligations stay pending.

**Handoff:** The operator authorized the local S1a checkpoint on 2026-10-20,
including the plan/acceptance notes. All 112 selected tests passed again in
3.980 seconds; focused Ruff, new-module strict typing and diff hygiene passed.
The unrelated pre-existing agent guidance remains outside this checkpoint. Next
is S1b transactional/continuity implementation, explicitly authorized below.
No separate background implementation job is running or required to preserve these
files. No external review, migration, ledger installation, push or deployment
occurred. This document is the shared durable plan; temporary thread progress does
not create a second authority.

**S1b implementation in progress (2026-10-21):** The operator explicitly
authorized this slice, including repeated confirmation to begin; no additional
start approval is required. `ledger/people_authoring.py` now contains a private
role-only successor primitive using the existing CAS draft writer inside an
already-owned outer command transaction. It validates lifecycle/version/patch,
delegates fresh-addition admission through a mandatory caller callback, detects
no-op before allocation, preserves unmanaged roles, and verifies deterministic
replacement rows. Its separate role-edge check reuses strict unchanged-fact and
policy-bijection comparison without relaxing facet-only role equality; it adds
facet snapshot and policy-presentation meaning checks. The allocator inventory
and existing empty/eight-facet producer regression now include this path.

This is not a new public command or complete S1b acceptance. Canonical command
receipt/replay and protected admission handlers, the worker/scheduler per-edge
classification and complete continuity state/race matrix remain unfinished.
Tests exercise real outer rollback, including a receipt inserted by a test caller;
that does not claim a production people receipt handler or public dry-run path.
Existing public capabilities, version/schema declarations and frozen contracts
are unchanged. No commit, push, migration, deployment or operator-ledger access
is authorized by this implementation step. Spine Packs work is paused separately;
there is no hidden background implementation job.

**S1b first-increment verification:** 12 new authoring tests and affected existing
people, item/transaction, schedule/continuity contracts, facet writer inventory
and rendering-storage regressions pass together: **185 tests, 29.548 seconds**.
Focused Ruff and strict mypy on the new source module pass. This is selected
regression evidence, not the full suite or whole-feature/public qualification.

**S1b completion work (2026-10-23):** The operator confirmed production is stable
and requested resuming the people sequence. The private writer now has additional
outer-rollback coverage for deferred foreign keys, finalizer failure, capacity
overflow and a lost-version race. It still delegates fresh-reference admission to
its caller; command receipts/replay and public dry-run envelopes belong to S1c.

The shared policy resolver used by worker freshness and scheduler reconciliation
now rechecks declared people edges using existing version-bound audit facts,
deterministic managed IDs, exact historical policies and a complete policy bijection.
Mixed facet/presentation edges use their own proof: facets retain role/presentation
equality; presentation-only edits retain role/facet equality. Existing indexed audit
IDs/receipt facts select those owners; no proof table or durable cache is added.
Ancestry is bounded at 100 item-version edges, including skipped-version gaps;
invalid/over-capacity evidence fails closed without work cancellation or rebinding.
Ordinary legacy edits retain their existing reconciliation path. Exact-version
policy capture replaces an incorrect implicit use of the current policy set when
reconstructing historical proofs. Existing facet-only equality remains strict.

Runtime tests cover scheduler no-op planning, unchanged work/attempt rows, mixed
role/facet/presentation history, intermediate drift, no-op IDs, start/retry/terminal
retention, independently stale routes, follow-source invalidation, and the ancestry
boundary. The initial full-suite run exposed an unnecessary facet-content read on
revoked-rendering fallback; classification was corrected to avoid content reads
on legacy paths, and that existing disclosure regression passes again.

**Current verification:** 247 selected tests passed before the final read-order
correction; afterward 39 focused people/lineage/revocation checks pass. Focused
Ruff, strict typing of the new module and diff hygiene pass. The corrected full-suite
rerun passes: **1,102 tests, one skipped, 166.853 seconds**, including all 24 private
authoring/continuity tests. Checking both modified shared modules reports one pre-existing typing
error on the unchanged `_rendering_pending` access in notifications.py; no unrelated
typing cleanup or all-module typing pass is claimed.

This finishes the verified private S1b prerequisite, not the
complete public feature or full work-state/concurrency qualification. S1c next owns
actual handlers, fresh/replay admission, receipts/dry-run and atomic scheduling v4
integration; Slice 2 owns directory/label disclosure; Slice 3 retains the full
state/race matrix. PR-01–16 are not globally closed. Public selectors, package
capabilities, runtime/schema versions and frozen wire schemas remain unchanged.
No operator ledger, new migration, real delivery, external audit, push or deployment.
The operator selected checkpointing this completed step before S1c. Keep the separate
pre-existing `AGENTS.md` amendment outside the cohesive S1b commit.

**S1c private local implementation (2026-10-23):** The operator authorized the
next leg from checkpoint `c80faaf`. `commands/people_candidate.py` now executes
trusted-local `item.people.show` and `item.people.update` using the actual outer
command transaction. Readback binds exact historical associations to current local
catalog labels without storing labels in receipts. Standalone changed/no-op receipts
use the reviewed canonical semantic preimage, preserve prior IDs on no-op, and
validate immutable original result/audit evidence on replay before fresh version or
reference eligibility checks. Malformed retained evidence refuses without repair.
Dry-run performs real writes and the same touched-state finalizers, then rolls the
outer transaction back; it never commits or reserves preview identities. Ordinary
commit still owns deferred SQLite FK enforcement.

The private `PeopleAuthoring` hook joins scheduling v4 to existing create/update
handlers and rendering hooks. People and ordinary schedule dimensions commit one
version/audit/receipt, not a second people command. Replacement touches only the
item-type-managed role; omitted people copy forward, explicit equal replacement in
an otherwise changed composite uses replacement paths, and whole-command no-op
retains prior IDs. People-only updates require no materialization, do not reconcile
work, and verify the separate role-only edge. The shared freshness resolver selects
those v4 edges from exact indexed receipt evidence. Mixed presentation histories
retain their strict distinct proof. Old selectors and task-role authoring are
unchanged.

**Scope limits:** This is an unadvertised trusted-local candidate, not an admitted
web implementation. It refuses transport metadata rather than allowing protected
callers to select local authority. Active-ID admission runs inside the write under
the existing trusted-local full-ledger policy; no item ownership is adopted or
changed. Protected owner-scoped admission, initiating-account/receipt disclosure,
access-release fences and the shared current-label disclosure resolver remain
Slice 2/protected-successor dependencies, not passing claims. Roster discovery and
pagination, full PR work/race matrices and installed/public activation remain gated.
No schema, package version, compiled declaration or frozen wire contract changes.

**Verification:** 26 new real-ledger handler/composite tests pass, including canonical
vector agreement, fresh/no-op/replay distinctions, current labels/exact history,
malformed receipts/audits, fail-closed private admission, preview/finalizer rollback,
one-version mixed edits, replacement/copy identity, existing role writers, selected
rendering retention and actual worker freshness across mixed exclusive edges. The
existing empty/eight-facet writer matrix includes these handlers. The selected
regression run passes 193 tests; the subsequent defensive receipt-type check is
covered by the rerun of all 26 handler tests. Focused Ruff, strict mypy on the three
people modules and diff hygiene pass. The full suite passes: **1,128 tests, one
skipped, 178.820 seconds**. The final defensive receipt-type correction is also
covered by the 26-test focused rerun. This is the verified private local S1c
increment; protected admission/read acceptance remains explicitly pending.
S1d must reconcile remaining PR obligations rather than claim whole-family closure.
No audit, commit, push, operator ledger, send, migration or deployment.

**S1c checkpoint and S1d (2026-10-23):** At the operator's request, S1c was
committed as `d050ca3`, excluding the pre-existing `AGENTS.md` edit. S1d then ran
the actual writer/handler parity work, not a new external review. The existing
25-producer inventory remains authoritative and now links the people evidence;
there is no new allocator or parallel people inventory. A runtime observer exercises
each producer and validates complete role copies/replacements, old-version row
immutability and successful transaction completion. Selected legacy cases carry
active/inactive fixtures for all five roles to avoid empty-set proofs.

That work reproduced a missed S1c identity rule: omitted roles used legacy
`prior-id-vN` IDs instead of the reviewed command-derived copy path. An explicit
private draft operand now opts the new people/scheduling-v4 paths into canonical
copy IDs. Legacy writers keep their default identities; neither old rows nor
no-op IDs are rewritten. Missing/unsupported owning command identity refuses
before allocation. The logical spec's inaccurate "existing" wording was clarified
without changing hash domains, paths, schemas or compatibility. Exact regressions
cover standalone unmanaged-role copies, v4 omission and legacy-default preservation.

The [runtime evidence map](PEOPLE_RUNTIME_EVIDENCE.md) separates local evidence
from remaining PR-01–16 dependencies. S1d additionally verifies that real adopted
ownership, access state, membership, delivery routes, work and attempts do not
change when people change, and that active agents/accountless people can be
selected without account provisioning. No whole PR obligation, protected runtime
or complete Slice 1 acceptance is claimed. Protected owner-scope admission and
replay/label permissions remain explicit Slice 2 dependencies; full work/race
and installed/public parity remain Slices 3/4.

S1d's selected regression run passes **198 tests, 41.860 seconds**. Focused Ruff,
strict typing of the six touched runtime owners and all 214 local link targets in
the affected specifications/tracking/evidence documents pass. Full regression:
**1,133 tests, one skipped, 186.307 seconds; passed**. The private S1d increment is
verified; it does not close every Slice 1 acceptance item or any whole-family PR
obligation. On 2026-10-24 the operator authorized its focused checkpoint. All 31
people command/writer-parity tests, focused Ruff, strict typing of six runtime
owners and staged diff hygiene were rechecked. Keep the separate `AGENTS.md` edit
outside the commit. Public activation, push and deployment remain unauthorized.
Next planned delivery is Slice 2; this checkpoint does not start it.

### People Slice 2 — private directory and protected standalone increment

The operator authorized starting Slice 2 on 2026-10-24 from `e7c1a41`. Its first
executable increment shares scoped roster/fresh-reference admission and current-label
disclosure between local/protected paths, with a separate authenticated people cursor
codec matching reviewed vectors. The private protected standalone service reuses
current identity/item ownership/grant predicates and the same canonical mutation body;
it does not route protected callers through trusted-local admission. Current item
permission exposes role IDs/history, while self/shared-roster authority separately
controls names. Missing authority yields closed nondisclosure; missing FK/capacity does
not. Fresh owner eligibility is inside the write, and receipt replay checks initiating
identity/current disclosure rather than fresh edit/reference permission.

Real local/protected roster paging binds query/source/identity/access, ledger instance,
key generation and relevant future membership transitions. Read-only assembly and fresh
release share one bounded budget and write no durable evidence/cache. Failed protected
write release rolls back version, roles, audit, receipt and private attribution link.
Existing schema/indexes suffice for this increment; no migration or new persistence.

This is **partial Slice 2**, not its acceptance or public activation. The remaining
cohesive read-integration increment must wire the shared resolver into protected
scheduling-v4 authoring and independent reads: optional people sections, authorized
person filters before temporal expansion, source/authority proof integration and
successor agenda/occurrence/section cursor streams. Carry forward optional core-reserve
degradation, dense/hidden bounded query evidence and actual race matrices. Preserve
frozen independent reads and self-only `subject_roles`. Full continuity/installed
qualification remain Slices 3/4. The [runtime evidence map](PEOPLE_RUNTIME_EVIDENCE.md)
separates current partial tests from whole PR obligations. No external audit, public
selector, package/schema version, commit/push, live ledger or deployment is authorized.

The preceding bounded delivery is
[SPINE-058](BACKLOG.md#spine-058--deliver-trusted-local-facet-revision-readback):
an exact revision-addressed catalog read to unblock historical-pin planning in
Spine Packs. SPINE-055–057 delivered and pushed the draft, contracts,
fixtures and manually verified review clarification through `3968dfd`. The review
had no blockers or majors; its corrected minor has not been re-audited. This plan
did not itself authorize runtime work. The operator subsequently ratified the
contract and authorized implementation after planning checkpoint `d8dbc24` on
2026-10-15. Runtime 0.10.0 adds only the trusted-local read; schema 19 and web
exposure remain unchanged. The implementation is committed/pushed as `8f3c50b`;
exact-pin consumer adoption and deployment remain separately authorized gates.
Executable evidence is recorded in SPINE-058. This does not block the independent
Spine Packs FR-3/4 work or silently make people a prerequisite for flight packs.

The selected post-release correction is
[SPINE-054](BACKLOG.md#spine-054--repair-successor-notification-profile-listing).
An exact-source public-CLI reproduction at `01ebce7` confirmed that the shared
legacy projection rejects v2 profiles before the successor list can project them.
Runtime 0.9.1 separates projection from unchanged snapshot-bound page selection.
Schema 19, contract selectors and stored hashes remain unchanged. Spine Packs
qualification must use a separately approved repaired commit, not relabel the
original 0.9.0 baseline; deployment and pack adoption remain separate decisions.

Use [the backlog](BACKLOG.md) to select work, record dependencies, and track completion.
The status labels, audit reports, and checklists below are retained delivery snapshots;
they are not a second live task queue. Update this document when initiative scope or
sequencing rationale changes, and update the backlog for task progress. Future horizons
stay coarse until promoted into bounded work with acceptance criteria.

The backlog retains deferred resilience work in SPINE-004–007 and SPINE-010,
facet design/review history in SPINE-008–009, and later horizons in SPINE-011–014.
Facet delivery follows SPINE-027–029 after the clean integration recheck. The operator
authorized Slices A, B and C on 2026-09-27. Runtime 0.8.0 / schema 17 builds the eleven
permission-enforced facet HTTP commands on the trusted-local storage/command foundation.
A dedicated additive registry leaves the existing v1 command and v2 read families
unchanged. Concrete verification and delivery status are recorded under SPINE-029.
The broad web/staging review tasks SPINE-001–003 were withdrawn at the operator's
request; no general gap analysis is scheduled.
SPINE-015 separately tracks independent authorized activity reads when linked resources
are unavailable, including the ratified versioned read projection and Kinflow migration.
The operator accepted the read design on 2026-09-16. Machine-contract codification
and its manual validation fixes are checkpointed and pushed through `4d16670`;
focused machine-contract audit 002 passed with no findings on 2026-09-17. The v2
registry, schemas, cursor rules and fixtures remain separate from unchanged v1
runtime assets. Spine 0.6.0 now implements the complete v2 backend registry with
HTTP/package admission and behavioral tests. Exact release commit `ad1db8e` is pushed
and has passed operator-reported clean-room backend validation. Kinflow adoption and
deployment remain separate gates. Static contract checks alone do not establish
access-control or concurrent-read correctness; concrete backend evidence is recorded
in SPINE-015.

Current context correction (2026-09-13): the operator is already testing the connected
[Kinflow frontend](../../kinflow-web-ui/README.md) against staged Spine on `cortext1`.
Kinflow records browser/API staging checks in its
[integration guide](../../kinflow-web-ui/docs/staging-integration.md). Statements below
about a forthcoming GUI or first staging deployment describe the earlier delivery
plan. SPINE-001–003 are closed as withdrawn. Focus on concrete operator-supplied
backlog items; only perform a gap analysis when explicitly requested.

Resilience priority correction (2026-09-13): the operator is satisfied with containment
and resilience following the event-emission fixes and has deferred SPINE-004–007 and
SPINE-010. The historical resilience-first sequencing below no longer schedules work
or makes those initiatives blanket prerequisites for facets or advisories. Preserve
their feature-specific contract and verification requirements.

## Planned Delivery: Trusted-Local Facet Revision Readback (SPINE-058)

Spine Packs FR-2 needs to resolve historical revision pins without guessing roots
from desired keys or current catalog pointers. One indexed lookup is a smaller,
more coherent addition than a client probing protocol or changes to several closed
binding/rendering projections. The [readback leaf](../specs/facet-schema-revision-readback.md),
[machine companion](../contracts/facet-schema-revision-readback.v1.json) and
[fixture manifest](../contracts/facet-schema-revision-readback-fixture-manifest.json)
own behavior. Existing facet logical/storage and command/preflight owners retain
authority. Current progress and completion evidence belong only in SPINE-058.

The operator authorized this as one cohesive runtime slice on 2026-10-15, with
three internal gates rather than separate environment deployments:

1. **Contract acceptance:** Ratify draft v0.1.1 and its source-only machine contract
   without treating offline models as runtime proof. No additional routine audit
   is planned for the recommendation-aligned minor correction; new substantive
   ambiguity must still be surfaced.
2. **Implementation and proof:** Add trusted-local CLI dispatch, bounded read-only
   snapshot resolution, exact compiled prerequisite declarations and deliberate
   installed schema closure. Preserve original stored decoding and hashes, apply
   the specified deterministic error order, and add real disposable-ledger tests
   for all RR-01–11 obligations. Include concurrent catalog changes, failure/limit
   injection, no-write assertions and installed-package command verification.
   Do not advertise a partially verified capability.
3. **Release and consumer handoff:** Complete operator examples, version declarations,
   focused then full regression checks, contract-sync/package checks and RR evidence.
   After separately authorized commit/push, provide the exact implemented release pin
   to Spine Packs. Its adoption refreshes its inventory/schema closure and qualifies
   FR-2 planning against old cross-root pins; that is separate work, not accomplished
   by Spine's release tests. Deployment also remains separately authorized.

No database migration, index/layout change, HTTP/MCP route, new permission model,
batch/history enumeration or root probing is part of this delivery. Existing web
registries, packaged web bytes, facet commands and binding/rendering wire shapes
must remain unchanged; local packaging changes must not leak into the frozen web
closure. Do not choose a runtime version from this roadmap or claim a schema bump:
the inspected baseline is 0.9.1/schema 19 and the additive release number is assigned
with implementation (now 0.10.0, schema 19 unchanged). No Spine Packs changes, live
ledgers or notification sends are authorized by this plan.

**2026-10-15 implementation checkpoint:** The shared local command/registry and
dedicated installed schema closure now implement the accepted lookup. The facet
web adapter validates its frozen reviewed command set independently of additive
local commands; its routes, wire bytes and pins remain unchanged. Runtime/schema
declarations and operator examples align with the release. Executable RR mappings
and verification results are in SPINE-058. The implementation is included in the
authorized checkpoint; push and consumer adoption remain separate. The next handoff
must name the exact release commit, not a moving HEAD pin.

## Planned Delivery: Facet-Aware Notification Rendering (SPINE-051–053)

SPINE-042 closed the final machine-contract minor with a clean bounded consistency
recheck. SPINE-043 drafted the [integration amendment](../specs/notification-rendering-integration.md);
SPINE-048 closed its buildability recheck with no findings. SPINE-049 ratified the
design and codified source-only successor authoring/evidence/cursor schemas and computed
fixtures. SPINE-050's focused machine-contract recheck returned
`pass_with_minor_clarification`, no blockers/majors, with boundaries preserved.
The fixture-only residual was corrected and locally verified in `da128c5`, following
the main contract checkpoint `78fc71a`. The corrected bytes have not been externally
re-audited; this is not a clean post-patch audit or convergence claim. Existing
ordinary output, policy-specific work identity and source-only activation fences are
preserved. Schema-18 location protection is already delivered locally; broader
protected-location sharing, new web family exposure and pack adoption remain separate.
No further routine audit is scheduled for that fixture-only correction. Concrete
contract or product ambiguities discovered during implementation must still be surfaced.

SPINE-037 repairs the initial machine-contract review findings. Location-label rendering
also requires the newly explicit facet-reference freeze in facet storage Section 7.1:
the existing FK protects deletion, while schema 17's canonical-field trigger only
checks `item_locations`. Implement the versioned trigger/manifest migration and FS-14
proof before enabling this rendering path. This is not a facet layout redesign or an
already implemented guarantee at that checkpoint; existing canonical location values
are preserved at cutover without fabricating earlier labels. SPINE-038 subsequently
implements this prerequisite in runtime 0.8.3/schema 18, without activating the
rendering-definition family or changing the existing public facet contracts.

The ratified [rendering-definition spec](../specs/notification-rendering-definitions.md)
separates reusable presentation configuration from facet schemas and reminder timing.
Spine would own resolution, disclosure, rendering and attempt evidence; packs would
distribute definitions and profile references through public commands. Start with
explicit scalar and location-label detail suffixes and exact schema/definition revisions, preserving the
ordinary renderer for unselected reminders and eligible fallback. This is independent
of LLM advisory execution. The operator agreed reusable scoped disclosure with per-policy
evidence, narrow location-label lookup and retirement preserving existing pinned use.
The focused bounded recheck passed, and SPINE-035 ratifies the logical design and adds
initial source-only catalog/disclosure schemas, selection/evidence fragments and
reference fixtures. SPINE-049–050 subsequently closed the integration design and
machine-contract work for implementation planning. SPINE-051–053 subsequently closed
the executable local release in 0.9.0/schema 19, with evidence linked below. Pack-format
and installer adoption follow Spine's contract rather than
inventing renderer semantics. Historical evidence remains in SPINE-035 and SPINE-050.

### Delivery authority and release boundary

The [logical rendering spec](../specs/notification-rendering-definitions.md),
[integration leaf](../specs/notification-rendering-integration.md),
[storage/atomicity owner](../specs/STORAGE_ATOMICITY_SPEC.md),
[integration matrix](../contracts/notification-rendering-integration.v1.json),
[successor registry](../contracts/notification-rendering-integration-contract-registry.v1.json)
and [fixture manifest](../contracts/notification-rendering-integration-fixture-manifest.json)
own behavior. Existing profiles, notifications, permissions and facet-continuity
contracts retain their authority. This plan allocates implementation and proof; it
does not change schemas, assign a release/schema number or mark any capability implemented.

The planning update did not authorize runtime work or deployment. The operator
subsequently authorized Slice A implementation on 2026-10-05; deployment remains gated.
[SPINE-051–053](BACKLOG.md#rendering-delivery--implementation-sequence) are three
cohesive internal checkpoints for **one end-to-end release**. Add tests with each
slice, not only at the end. Keep successor command registration, compiled capability
advertising, production migration activation and deployment gated until all three
slices and all required RI families pass. Internal test harnesses may exercise the
candidate migration and handlers without exposing partially supported live contracts.
No service cutover or environment patch is required between these checkpoints.

### Slice A — Persistence and authoring (SPINE-051)

Build the complete storage and authoring foundation against schema 18 or a separately
verified successor; do not select a schema number from this roadmap.

- Implement the Section 5 relational tables, immutable canonical payloads/reference
  projections, FKs, unique indexes, guards, hashes and catalog generation. Extend the
  existing rendering table for its v1/v2 branches; do not create a second attempt ledger.
- Add a candidate atomic migration and equivalent fresh initialization. Backfill
  explicit ordinary presentations for active, disabled and historical policies;
  preserve existing IDs, receipts, v1 profile hashes and rendering bytes. Add expected
  schema objects and explicit deep verification without introducing startup scans.
- Cover every item-version/policy producer with an explicit writer inventory and
  shared finalization. Copy from exact predecessor policy IDs, including shared-intent
  and multi-copy-forward cases; reject missing, forked or inconsistent support rows.
  Establish the common current-descendant resolver for worker/scheduler use in Slice B.
- Implement rendering-definition and disclosure catalog commands, immutable revisions,
  retirement/revocation, bounded show/list, exact/unique-match selection, permission
  resolvers and authenticated cursor/config handling. Preserve owner/role boundaries,
  the protected-location denial and trusted-local exact-location approval rules.
- Implement profile v2, schedule create/update v3 and direct authoring v2 through
  shared services: profile pins, complete-plan composition, presentation-only edits,
  origin provenance and application evidence. Honor replay, no-op, dry-run, transaction
  rollback, v1 historical decoding and the old-request lossy-replacement/revise guards.
- Preserve fresh trusted-local ordinary-only creation followed by explicit owner
  adoption and presentation editing. Never infer ownership or introduce a scheduler hold.

**Exit evidence:** Real disposable-ledger tests for catalog and authoring transactions,
permission/cursor bounds, writer coverage, history preservation, migration interruption
and failed-write rollback. Exercise the fixed profile-list limits, shared failure
envelopes, dry-run markers and original composition evidence. Candidate storage and
all writers must agree before proceeding; public activation remains off.

**2026-10-05 internal checkpoint:** Candidate relational storage and atomic migration,
historical ordinary backfill, metadata-only object-manifest checks, exact-policy
supporting-row finalization, catalog/permission/cursor handlers and shared successor
authoring are implemented. Real disposable-ledger tests cover catalog and authoring
replay/no-op/dry-run, owner adoption, exact/ambiguous grants, protected-location denial,
work-preserving presentation edits, all inventoried item/policy writers, shared-intent
lineage, migration interruptions and unchanged populated v1 profile/attempt evidence.
See [SPINE-051 evidence](BACKLOG.md#spine-051--rendering-persistence-and-authoring-foundation)
for test mappings and the local wheel-build limitation. This is not public activation
or full RI-family closure. Committed as `653e135` on 2026-10-06 before beginning B.

### Slice B — Delivery integration (SPINE-052)

Wire the foundation into the existing scheduler/worker attempt path, not a new pipeline.

- Share exact-policy/current-descendant resolution across scheduler and worker.
  Presentation/facet-only edits retain eligible, leased and retry work identities,
  leases, retries and provider keys; absent work stays absent and independently stale
  work still follows its existing rules. Preserve started/terminal history.
- Implement deterministic scalar and permitted location-label suffixes over the
  unchanged ordinary renderer, using pinned schema/definition decoders and current
  facet values. Revalidate item owner, grant, route and access at the attempt fence.
- Keep unselected reminders byte-identical v1. Selected-but-omitted detail remains
  v2 evidence with ordinary wording; revocation, empty selections and suffix overflow
  must not leak values or source references. Corruption and evidence-size failures
  fail closed before adapter invocation, not through an invented fallback.
- Persist one final rendering with its existing side-effect attempt atomically.
  Same-attempt replay uses stored bytes; a new retry may use current facts while
  retaining the provider idempotency key. No second send identity or advisory execution.
- Exercise edit/revoke/ownership/route races and recurring/follow-source items.
  Prove the setup interleaving rules both with verified operational exclusion and
  without it: materialization=none is command-local, and ordinary delivery can begin
  between separately committed create/adopt/edit steps without exclusion.

**Exit evidence:** Real-ledger work-state and race tests, injected commit/adapter-boundary
failures, immutable replay evidence and provider-key assertions. Use deterministic
test adapters, not real recipients. Ordinary bytes and delivery identity remain
unchanged; activation and deployment remain off.

**2026-10-06 internal checkpoint:** Delivery integration is implemented over the
existing attempt ledger and shared exact-policy resolver. Selected reminders append
deterministic scalar/permitted-location labels, with omission privacy and immutable
v2 evidence; ordinary reminders retain their v1 bytes and envelope. The attempt-start
transaction rechecks current facts and commits rendering plus attempt atomically.
Same-attempt replay uses stored bytes; fresh retries preserve the provider key.
Real disposable-ledger proofs include shared-intent policy distinctions, recurring and
follow-source targets, work-state preservation, prepared-edit/revocation/ownership/route
races, two-connection SQLite writer contention, commit faults, byte limits and the
already-due/grace/setup interleavings. See
[SPINE-052 evidence](BACKLOG.md#spine-052--integrate-facet-details-into-notification-attempts)
for executable mappings and verification results. No live
ledger, service, public contract activation or release version changed. Slice C is
the next separately authorized checkpoint; do not deploy A/B alone.

### Slice C — Readback, operator handoff and release verification (SPINE-053)

- Complete full schedule-show v2 and successor response/receipt projections with
  preserved selection, scope-chain, revision-hash, overlay and policy-origin evidence.
  Distinguish persisted v1/v2 attempts; preserve old summary/redaction behavior without
  adding fields to frozen compact or web contracts.
- Finish CLI discovery/help and generic operator guidance with progressive disclosure:
  definition/grant setup, ownership adoption, exact presentation edits, optional
  explicit materialization and evidence readback. Explain retirement versus revocation,
  ordinary fallback versus failure, and the operational exclusion needed for strict
  details-before-delivery ordering. No automatic service control or assumed chat consent.
- Re-run populated/fresh migration, all-writer, concurrency, rollback/restore, old-worker
  refusal and ordinary rendering regressions as a single release candidate. Check
  non-editable package resources, exact registry/schema pins, bounded preflight and
  current web-contract nonactivation. Run focused checks first, then the appropriate
  full suite; record any skipped or blocked proof explicitly.
- Only after end-to-end evidence passes, enable the coherent local command families,
  integration capability and matching migration/runtime manifest together. Do not
  advertise support earlier. Broader HTTP registry exposure needs its own versioned
  contract and approval; this slice does not silently extend the current web registry.
- Prepare a separately approved staging handoff: preserve/verify the ledger backup,
  stop all writers for migration, provision protected cursor configuration deliberately,
  verify startup/readback and use controlled canaries. Rollback pairs the pre-migration
  backup with matching code and preserves the newer ledger; it is not a down migration.

**Exit evidence:** All RI families linked to executable passing tests, honest release
capability declarations, complete package/CLI readback, and actionable operator and
rollback instructions. Deployment and any real send remain separate authorizations.

**Implemented 2026-10-06 (release checkpoint; not pushed/deployed):** Runtime 0.9.0/schema 19
activates the local successor authoring/catalog/readback families as one release.
Full suite: 1,017 tests passed; focused final contracts/readback: 41 passed. The installed
non-editable wheel passed fresh/populated migration, exact resource/registry pins,
actual predecessor worker refusal and paired-backup verification using the pinned
Tickerd package. Compact and current web contracts remain unchanged. See
[SPINE-053](BACKLOG.md#spine-053--complete-rendering-readback-and-release-verification)
for the RI-01–14 evidence map, artifact hash and
[operator handoff](NOTIFICATION_RENDERING_GUIDE.md). Next action requires a separate
push/deployment decision; do not expose successor payloads through frozen HTTP routes.

### Required proof allocation

The table preserves the introduction/allocation plan. Slice C has now rerun these
families together and recorded test names/results under SPINE-053. Static schemas,
vector regeneration and audit reports still do not count as executed stateful proof.

| Family | Introduce proof | Required release evidence |
| --- | --- | --- |
| RI-01 | A/B | Historical migration and unselected ordinary bytes/hashes/provider envelope unchanged |
| RI-02 | A | Profile/presentation hashes, exact/unique selection, decoder guards and historical replay |
| RI-03 | A/B | Authoring rollback plus operational-exclusion and automatic-scheduler interleavings |
| RI-04 | A | Changed/no-op/dry-run/replay presentation edits preserve work and reject lossy old requests |
| RI-05 | A/B | Shared-intent exact ancestry, repeated copy-forward and conflict on ambiguity/forks |
| RI-06 | B | Eligible, leased, retry, started, terminal, stale and absent work-state matrix |
| RI-07 | B | Attempt versus edit/revoke/owner/route races; no private values on omission |
| RI-08 | B | Atomic attempt/evidence commit, suffix overflow and corruption fail-closed behavior |
| RI-09 | B | Same-attempt stored replay, fresh retry evidence and stable provider identity |
| RI-10 | A/B | Role/grant checks at authoring and attempt time, protected-location denial |
| RI-11 | A | Signed cursor/context/epoch/time fences, bounded indexed reads and no durable read writes |
| RI-12 | A/C | Fresh/populated migration, interruption, verified backup restore and old-worker refusal |
| RI-13 | A | Exhaustive producer inventory and finalization detects missing/mismatched support rows |
| RI-14 | C | Complete v1/v2 readback, safe old projections, coherent packaging and activation |

No unresolved product decision is currently identified. If implementation exposes a
missing normative rule, stop that affected path and seek a targeted specification
decision rather than inventing policy. These slices do not restart deferred resilience,
retention or general qualification campaigns, introduce authentication, expand protected
location visibility, install packs, change the GUI, or implement contextual advisories.

## Delivered Fix: Schedule-Show CLI Notification Profile Include (SPINE-031)

Runtime 0.8.2 accepts `notification_profile` in `schedule.show --include`, including
mixed detail sets, and lists it in CLI help and validation errors. This repairs an
adapter omission against the existing `spine.schedule-show.v1` contract; schema 17,
handler behavior, and public contract versions are unchanged. CLI-entry-point tests
cover every contract include, JSON-input parity, and unknown/duplicate rejection.
Local verification and deployment status are recorded in SPINE-031 in the backlog.

## Delivered Fix: OpenClaw Retry Delivery Idempotency (SPINE-026)

The operator reported successful WhatsApp delivery followed by a CLI timeout and
duplicate messages on subsequent retries. Spine 0.6.1 separates the existing
per-attempt ledger key from a provider key derived solely from the work-instance ID.
Distinct attempts and rendering evidence remain durable, while the gateway receives
`openclaw-delivery:{work_instance_id}` on every retry. The outbound v2 envelope hashes
both keys and the exact attempt-time rendering. Schema 15, ledger uniqueness,
timeout values and retry timing are unchanged.

Real-ledger tests model a delivered-but-timed-out call, reconstruct a retry from
durable work in a fresh process, and prove two ledger attempts with one visible
delivery through an idempotent gateway double. Old-envelope replay remains
fail-closed. SPINE-026 records exact verification and limitations. The real gateway's
key retention, restart persistence and handling of changed retry prose still require
separate runtime evidence; no deployment or service restart is part of this repair.

## Planned Delivery: Versioned Archetype Facets (SPINE-027–029)

The 2026-09-26 integration recheck passed with no findings and preserved boundaries.
Its approved model was gpt-5.6-sol. The reviewed sources are checkpointed through
`4060e89`; the physical storage design is accepted v1.0 and the reviewed logical
integration draft was v0.7. This closes that focused contract review, not runtime verification or
a convergence declaration. The [backlog](BACKLOG.md#facet-delivery--implementation-sequence)
owns live task status; this section defines implementation order and release fences.

The subsequent operator-selected diagnostic found a dry-run wire-contract conflict
and an all-writer activation-proof gap. The manual v0.8 amendment defines previews and
the storage leaf's Section 5.1 gate without changing the accepted physical layout.
Local contract checks are not a new Whetstone verdict or SQLite enforcement proof.

Authoritative inputs are [the logical facet contract](../specs/archetype-facets.md),
[its storage leaf](../specs/archetype-facet-storage.md),
[Decision 0004](../specs/decisions/0004-versioned-item-facets.md),
[Spine-wide atomicity](../specs/STORAGE_ATOMICITY_SPEC.md), and the
[integration companion](../contracts/archetype-facet-integration.v1.json),
[command registry](../contracts/archetype-facet-contract-registry.v1.json) and
[fixture manifest](../contracts/archetype-facet-fixture-manifest.json).
These own behavior; the delivery plan does not invent missing policy or override them.

### Slice A — Persistence and all-writer foundation (SPINE-027)

**Implemented, 2026-09-27:** one cohesive internal slice covering
the canonical storage substrate and every existing item-version producer. Do not split
the migration from its writer support, or deploy a database that existing commands
can leave without facet markers. Public facet commands stay unregistered in this slice.

Runtime 0.6.2 assigns schema 16 and supplies the atomic predecessor migration,
canonical codecs, eight-table layout, shared precommit enforcement and
[closed writer inventory](../src/spine/ledger/facet_writer_inventory.v1.json).
The [implementation handoff](FACET_STORAGE_IMPLEMENTATION.md) maps each FS family
to real SQLite tests and explicitly retained Slice B/C gates. No live migration,
deployment, public facet command or web registry activation occurred. The numbered
scope below is retained as the delivered Slice A checklist, not a second queue.

1. Implement pure definition/value normalization, compatibility checks, pinned decoder
   selection and canonical hashes against the published vectors. Keep I/O out of core;
   unknown decoder selectors and corrupt/noncanonical persisted bytes fail closed.
2. Codify all eight specified tables, constraints, triggers, FK parent keys and indexes;
   extend the existing catalog audit resource kinds without losing historical rows.
   Produce matching fresh-schema SQL, migration, schema-object fingerprints and package
   data through existing mechanisms. Allocate the next available schema number against
   the actual implementation base; schema 15 is the inspected baseline, not a reserved
   next-number promise. Do not add dynamic DDL per operator schema.
3. Add transaction-owned ledger primitives for immutable definitions/bindings, complete
   snapshots, historical reference protection and current-only typed projections.
   Helpers never commit, invent audit/receipt identities, or repair canonical rows on read.
   Stored definitions/values remain authority; typed rows are derived.
4. Wire empty-marker creation and exact snapshot/reference copy-forward into **every**
   version producer: item/lifecycle, schedule, recurrence, notifications/profile
   application and temporal-binding reconciliation. Publish the closed machine-readable
   producer/call-site/finalizer/test inventory required by storage Section 5.1 and prove
   coverage. Gate allocation and outer commit through the shared transaction-owned
   touched-version finalizer, including negative bypass/missing-marker tests. Complete
   this gate before releasing the migration, even with public facet commands disabled.
   Retain original authoring evidence; enforce archetype-change guards;
   update only the changed item's current typed rows in the same outer transaction.
5. Backfill explicit empty snapshots for every existing historical item version; leave
   existing items, audit, receipts, work and attempts semantically unchanged. Prove
   rollback on injected failures and rejection of old runtimes against the new schema.
   Verify backup/restore on disposable ledgers; no live deployment or automatic downgrade.
6. Extend explicit deep verification to canonical/projection parity. Keep routine
   preflight object/contract-bounded and all read paths free of repair or durable traces.
   Prove indexed candidate-rooted queries and operation budgets against unrelated data.

**Exit evidence:** real SQLite tests for FS-01–05, storage/reference portions of FS-06,
transaction/concurrency portions of FS-07–09, and FS-10–11. Publish a concrete mapping
from every FS family to tests or a named follow-on gate; do not label permission,
public replay or notification acceptance complete based on helper tests. Include
multiple existing command paths against seeded nonempty facets, historical decoding
after catalog retirement, deferred-FK/commit failures, current-index parity, and
missing/drifted-object admission failures. Pure oracles supplement these tests.

### Slice B — Public commands and notification continuity (SPINE-028)

**Implementation checkpoint, 2026-09-27:** runtime 0.7.0 adds all eleven shared-handler/
trusted-local commands, six-write atomic preview/replay behavior, authenticated bounded
pagination and stable-intent notification continuity. The
[operator guide](FACET_COMMANDS.md) covers exact contract pins, private cursor configuration,
schema upgrade/removal, and the explicit boundary against automatic web exposure.

Public SQLite tests exercise a reference-rich flight lifecycle, explicit schema upgrade,
historical decoding, eight-entry retention, same-value reference revalidation and atomic
failure. Notification tests cover successive facet versions, queued/in-progress/retry/
terminal rows, recurring provenance, follow-source staleness, and attempt/render replay
without permission to send again. Two-connection tests cover source-release races and
concurrent scheduling writes; the large unrelated-ledger fixture exercises the public
owner-rooted indexed query. No live ledger, service or web route was changed. Final
verification and completion status are recorded under SPINE-028 in the backlog.

The following scope is retained as the Slice B delivery checklist.

Build on Slice A to implement all eleven reserved facet commands through shared
handlers and the trusted-local CLI. Enforce exact request/response pins, produced-row
identities, stale-version checks, one outer transaction, audit counts and same-ID
replay. Fresh sets require the concrete item type in both pinned compatibility sets,
even for same-value no-ops; retained/removal/replay paths keep their specified exemptions.

Cover all six writes' applicable dry-run changed/no-op/replay/failure paths, including
zero durable deltas, no sends, bounded previews, later-commit identity equality and
`reconciliation_performed=false` in preview despite required equivalence validation.
The invocation flag remains outside facet request JSON; see logical Section 10.2.1.

Integrate facet-only edits with ordinary notification continuity before exposing
`item.facets.update`. Resolve the current policy by stable item/intent, not a one-hop
copy predecessor. Verify semantic equality atomically and preserve existing work,
leases, attempts and rendering evidence without expansion, cancellation or sending.
Respect downstream follow_source staleness and reconcile it only through its existing
path. Cover multiple successive edits, recurring work, queued/leased/retry/terminal
states, independent stale work, concurrent lease/attempt start and lost-response replay.

Implement bounded local show/list/query and the authenticated facet cursor contract,
including protected key/context provisioning, clone/restore invalidation and no
durable cursor store. Use the single-request budget for evaluation and release checks;
first-page source races fail without internal retries and continuations fail stale.

Complete CLI effect/replay portions of FS-07–09, FS-12 and the trusted-local FS-13
flight proof: register, bind, create item, attach, inspect, query, replace, retire/remove.
The create/attach pair remains two atomic commands and a failed attach leaves the item.
Activate only fully tested runtime contract families and command registry entries;
ship operator documentation and packaged contracts together. No automatic web route
registration, schedule projection extension or pack-v2 activation follows from CLI support.

### Slice C — Permission-enforced reads and web admission (SPINE-029)

**Implementation checkpoint, 2026-09-27:** runtime 0.8.0 / schema 17 adds the
`spine.trusted-web-facets.v1` family with a dedicated eleven-command registry,
closed request/response/error/discovery schemas and packaged digest pins. The
canonical handlers remain shared; a protected adapter owns transaction, permission,
receipt-attribution and release fences. Offline schema 17 extends catalog grant
storage, with v2 local provisioning alongside unchanged v1. No new authentication,
shared-location resolver, schedule projection or Kinflow UI behavior is claimed.

The [admission leaf](../specs/facet-web-admission.md) records the exact transport and
migration decisions; the [consumer/operator handoff](FACET_WEB_API.md) covers
configuration, permissions, retries and upgrade boundaries. Verification exercises
all six write replay mappings, admin demotion, retained-read/lost-edit, hidden
references, complete access proofs, grant time boundaries, release races and rollback.
The task's test counts and final status remain in SPINE-029 rather than this history.

Implement the reviewed catalog resolver/grant extension and item/reference authority
on the same handlers, including all six receipt-disclosure replay mappings. Prove
current initiating identity/read checks, safe foreign-ID failures, read-retained/
write-revoked replay, hidden nested references and release-time revocation with real
ledger state. Do not reuse fresh write authority as a replay prerequisite or expose
facet values through receipt replay.

Complete protected pagination with configured context/key, bounded candidate/access
proofs and fresh release fences: tampering, expiry, key/generation rotation, gained/lost
visibility, grant transitions and source races. Reuse existing independent-read
machinery only where semantics match; preserve the distinct facet cursor pin/bytes.
The permission-enforced subset permits scalar/self-subject references, not implicit
shared locations; the reference-rich flight demonstration remains trusted-local.

Before activation, codify and test the exact versioned web registry/admission mapping
and package/capability declarations required by the owning web contract. No mutation
of a frozen registry or invented permission mapping. If that codification reveals an
unsettled API/product choice, surface it rather than treating this plan as authority.
Finish permission portions of FS-06–09 plus adversarial cursor/replay/revocation tests.
Kinflow UI integration is a separate consumer task, not an implied Spine deliverable.

### Verification, handoff and release discipline

- Run focused tests during each slice, then the relevant full suite, configured strict
  core/ledger type checks, lint, contract-package parity, clean initialization/upgrade
  tests and diff/link hygiene. Record actual versions, counts and any skips/limitations.
- Retain tests proving existing non-facet scheduling, reads and worker behavior; no
  full integrity/quick/FK scan is introduced at routine startup. Feature-local bounds
  and failure injection are required, not a restart of the deferred resilience campaign.
- These are implementation checkpoints, not three mandatory staging deployments.
  Prefer one cohesive deployable release after its selected public surface is proven.
  A foundation-only checkpoint must not advertise facet support. Deploy only with a
  consistent backup, writer-stop/migration procedure, matching runtime and explicit
  post-commit rollback/restore warning as required by the storage leaf.
- No blanket audit sweep is planned. A genuine contract conflict discovered while
  building goes back to its owning spec for a targeted decision/correction.
- Recipes, observations/advisories, occurrence-level facets, richer types, field ACLs,
  atomic create-with-facets, generalized location sharing and retention remain outside
  this delivery. No pack installation or UI changes are implied.

## Planned Fat Slice: Independent Authorized Activity Reads (SPINE-015)

This is one cohesive Spine backend delivery, followed by a separately coordinated
deployment and Kinflow adoption. The steps below are an implementation order, not
six environment deployments. Live task status and completion evidence remain in
[SPINE-015](BACKLOG.md#spine-015--read-authorized-activities-independently-of-unavailable-linked-resources).
This planning update does not begin implementation or authorize staging changes.

Delivery checkpoint (2026-09-18, subsequent operator authorization): internal
foundation and the next assembly slice are implemented. Pinned validation,
normalization, read-only bounded contexts, authorized candidates/core/time, all eleven
detail sections, all four agenda summaries, and canonical occurrence/resolved/unplaced
agenda assembly are locally tested. Collection assembly prepares the full bounded
authorized set; public pagination is still pending. Separate optional permissions and
budgets preserve root admission and distinguish null/empty from unavailable context.

Actual query plans justified schema 15's index-only migration for endpoint-pair
relations/bindings, policy-rooted work and creation receipts. Fresh initialization,
manifest and upgrade tests are included; candidate grant discovery now explicitly
uses existing grantee indexes. Real canonical occurrence keys also exposed and fixed
the unadvertised projection/cursor schema's incorrect 256-character key limit, without
changing any canonical identity or v1 pin. See SPINE-015 for exact test evidence.

The foundation and assembly checkpoints were subsequently pushed, and SPINE-025
repaired their contract synchronization/source-only typing gates; the operator
reported clean Python 3.12 cloud validation. That evidence does not activate v2.

Delivery checkpoint (2026-09-19, subsequent operator authorization): internal fresh
release fences and authorized source hashing are now implemented. The shared read
path closes assembly before opening a fresh read-only snapshot, rechecks selected
identity/authorization (including denied prerequisites and timed transitions), and
reassembles relevant authorized source facts before releasing an internal result.
One bounded request budget spans both transactions with separate optional reserves.
Public hashes follow the exact authorized-only snapshot preimage; optional section
summaries retain their projected row evidence. First-read and retained private-proof
races use the specified generic access/version failures. No wire cursors or public
HTTP responses are implemented by this checkpoint.

Actual transition-query plans use existing grantee, membership, owner and operation
indexes; no new migration was necessary. The selected-subject fence compares the
full canonical subject row because subjects have no numeric revision column. The
cursor's numeric `subject_revision` needs an explicit implementation at cursor
integration; no synthetic value or public capability was introduced here.

Verification: focused **95 tests/160 subtests**; full unittest **590 tests** and
pytest **590 tests/572 subtests**, without skips. Both mypy 1.20.2 and 2.3.0 pass
source-only and editable strict core/ledger runs (37 files, no incremental cache).
Ruff, compileall, contract synchronization and diff hygiene pass. The additional
local offline wheel attempt could not run because `setuptools.build_meta` is absent;
no new installed-wheel or cloud acceptance is claimed. SPINE-015 records exact
commands, durations, query-plan evidence and the environment limitation.

Remaining order at that checkpoint: cursor codec/identity encoding and actual section/combined-stream
pagination; complete HTTP/package/capability integration and behavioral gates;
operator/Kinflow handoff and separate consumer acceptance/deployment. All new objects
remain internal and unpaged; v2 routes and capability advertisement remain inactive.
The operator subsequently authorized a local commit of this release-fence slice;
no push, deployment or staging change is included in that authorization.

Delivery checkpoint (2026-09-19, subsequent operator authorization): implemented
internal v2 cursor codec, selected-identity encoding and actual section, occurrence
and combined resolved/unplaced agenda pagination from `629c7a4`. Tokens match the
computed HMAC vector, use closed stream-specific keys, and preserve the original
query/snapshot/issuance/expiry. Paging and response validation run before the fresh
release fence under the shared request budget. Every continuation reassembles and
reauthorizes; a bounded service-local volatile proof store retains only private
evidence, never responses. Proof loss fails closed with `access_changed`; live
families are neither evicted for admission nor renewed by child pages.

The positive-decimal `subject_revision` is now a pinned content fingerprint of the
selected subject's six canonical fields, supporting equality only. The full row
remains in the private fence; persisted account-subject binding revision maps
directly to its distinct v2 field. Contract/vector pins and the consumer handoff
document this encoding and bounded proof retention. Actual identity lookup plans
use existing primary-key indexes, and pagination adds no SQL scans or migrations;
schema 15 is unchanged. See SPINE-015 for exact verification and environment limits.

Verification: new paging suite **31 tests / 36 subtests**; combined focused suites
**126 tests / 196 subtests**; full unittest **621 tests** and full pytest **621 tests /
608 subtests**, without skips. Mypy 1.20.2 and 2.3.0 each pass source-only and
editable-install strict core/ledger checks (37 files). Ruff, compilation, contract
synchronization, 71 local documentation links and diff hygiene pass. A fresh offline
wheel attempt on a temporary source copy still cannot import `setuptools.build_meta`;
no wheel/installed-wheel or cloud acceptance is claimed for this slice.

Remaining order at that checkpoint: HTTP integration, package admission, complete capability activation
and backend behavioral gates; final operator/Kinflow handoff and separate consumer
acceptance/deployment. All paging remains internal; no public v2 route, packaged
asset or capability declaration was activated, and no commit/push/deployment is
included in this slice.

Delivery checkpoint (2026-09-19, subsequent operator authorization): completed
HTTP/package/capability integration from clean `141d995`. Runtime **0.6.0** implements
all four v2 routes in the existing backend. The new read service admits the exact
packaged manifest, complete transitive pins, runtime declarations and route registry.
Selected capability discovery has its own fresh identity fence. All read routes use
the authorized pager; actual HTTP serialization and byte limits run before fresh
release checks. V1 pins, routes, command semantics and writes remain unchanged.
Schema **15** is unchanged; actual discovery identity query plans use existing
primary-key indexes, with no new item traversal or migration.

The fixture manifest now maps IR-01–IR-15 backend evidence to executable tests.
All eleven sections, canonical occurrence and resolved/unplaced agenda facts,
transport boundaries, cursor/source/access races and no durable read effects have
local backend coverage. IR-16 and the consumer portion of IR-15 remain pending.
Operator documentation and the Kinflow handoff now describe supported versions,
public examples, failure/cache behavior and deployment/rollback boundaries.

Verification: combined focused suite **190 tests / 269 subtests**; full unittest
**650 tests**; full pytest **650 tests / 652 subtests**, no skips. Mypy 1.20.2 and
2.3.0 each pass all 37 core/ledger files in source-only and editable-install strict
checks. Ruff, synchronization, compilation, 125 local file links and diff hygiene
pass. Temporary build tooling resolved the prior environment blocker: a fresh
0.6.0 wheel contains 97 byte-matching web JSON assets; its isolated installation
passes all 26 HTTP tests, synthetic schema-15 initialization/deep verification and
system-info checks. SPINE-015 records commands, versions, wheel digest and exact
results. This is local package/HTTP evidence, not a cloud or deployment result.

The completed slice was committed and pushed as
`ad1db8e1a4c7aa9a525612324d08824802a86351`. Operator-reported clean-room validation
of that exact commit passed the complete focused suite (**190 tests / 269 subtests**),
all **26** installed-wheel HTTP tests, package parity for all **97** web JSON assets,
synthetic schema-15 migration/deep verification, strict source-only and
editable-install mypy 1.20.2, Ruff, compilation, synchronization, documentation and
diff checks. Full cloud discovery remained **650 tests**: **617 passed + 33
Tickerd-dependent skips**, plus **652 passing subtests**. Tickerd absence also blocked
an unpatched successful `system.info`, and the cloud proxy prevented provisioning
mypy 2.3.0; both paths passed locally and no actionable Spine failure was found.

Next steps are separately authorized deployment/canaries and Kinflow integration
acceptance. Backend validation does not complete IR-16 or the consumer portion of
IR-15, and no deployment, staging change or consumer implementation is claimed here.

### Authority and delivery boundary

Build against [independent activity reads](../specs/independent-activity-reads.md),
its [machine-contract companion](../specs/independent-activity-read-contracts.md),
the [read registry](../contracts/spine.trusted-web-read-registry.v1.json),
[projection rules](../contracts/trusted-web-read-projection.v1.json),
[normalization and budgets](../contracts/trusted-web-read-normalization.v1.json),
[cursor protocol](../contracts/trusted-web-read-cursor.v2.json),
[schema pins](../contracts/trusted-web-read-schema-pins.v1.json), and
[fixture manifest](../contracts/independent-activity-read-fixture-manifest.json).
These artifacts, not this plan, define wire behavior and exact limits.

The deliverable is the complete initial read registry: two POST command routes for
`schedule.show` and `item.occurrences`, `POST /api/v2/agenda`, and selected-identity
`GET /api/v2/read-capabilities`. An accessible event must remain readable when an
unowned or inaccessible downstream task follows it. An accessible follow-source
task still requires its own authorized, current temporal-source proof; otherwise
its time is unavailable, not guessed from a stored deadline.

Preserve v1 API/registry/pins and complete-or-deny behavior, direct CLI behavior,
all write authorization/replay rules, canonical recurrence identity, workers and
delivery semantics. No v2 writes, identity/authentication redesign, ownership repair,
task-creation ownership provisioning, facets, advisory execution, or deferred
resilience campaign belongs in this slice. No new service is needed: extend the
existing `spine.web` backend. No canonical data migration is assumed.

### Implementation order

1. **Establish bounded selection and shared read infrastructure.** Use the existing
   `src/spine/web/service.py`, `permissions.py`, `contracts.py`, and `http.py` as
   integration seams, keeping new projected reads separate from v1 graph admission.
   Inspect query/index support for authorized candidates, temporal dependencies,
   section evidence and indexed creation-receipt selection. Record either a supported
   no-migration conclusion or the concrete required query/index migration with its
   normal manifest and migration tests; do not assume a full hidden-graph scan is
   acceptable. Implement exact normalization, mandatory calendar-format validation,
   shared read context, consistent source snapshots, and separate core/optional
   budgets from the machine artifacts. Reuse canonical engines without invoking
   receipt-bearing mutation commands or introducing read-time repair.
2. **Implement authorized core and temporal projections.** Build root admission and
   closed field allowlists shared by all three reads. Reuse canonical recurrence
   expansion, overlays, timezone resolution and temporal-binding freshness rules;
   do not re-derive occurrence IDs. Traverse only required authorized time sources,
   not downstream followers. Implement available/not_scheduled/unavailable time,
   event-start/task-due placement rules and generic direct denial. Cover the reported
   Science-class/following-task case with real local domain fixtures immediately.
3. **Complete sections and agenda assembly.** Implement all eleven detail sections
   and the four agenda section states using their field-to-authority predicates.
   Authorize before selection, counting and pagination. Keep absent and undisclosable
   singleton evidence equally null; empty authorized summary buckets remain non-null.
   Do not release raw receipt/rendering/provider payloads. Add canonical resolved
   agenda entries followed by unplaced authorized cores under the combined limit;
   temporal coverage and pagination remain distinct. Optional context failures may
   degrade only that context, never mask failed root admission or release checks.
4. **Finish freshness fences and continuation before enabling routes.** Revalidate
   identity selection, account-subject binding revision, authorization epochs and
   timed grant/membership activation or expiry in a fresh release snapshot. Fence
   relevant source versions on first and later pages. Implement the separate v2
   HMAC cursor codec and computed vectors, fixed original expiry, section/stream
   binding, query normalization and authorized source hashes. Hidden follower
   mutations alone must not invalidate independent event facts. Use deterministic
   clock and assembly hooks to test races; do not rely on timing sleeps. Keep these
   fences in the shared read path so no route can omit them.
5. **Integrate HTTP, package and activate the complete contract family.** Retain
   selected-identity admission, Origin/CSRF protection, request bounds, no-store
   responses and generic errors. Wire all four routes, validate responses, package
   the exact new registry/transitive schemas/artifacts and add runtime declarations
   with pin parity checks. Missing/mismatched required assets must fail closed.
   Advertise v2 only when the complete initial registry and behavioral gates pass;
   no partial-capability advertisement or silent fallback. Keep the v1 codec and
   command registry unchanged and do not expose these projections as CLI v1 output.
6. **Verify, document and hand off one releasable backend.** Run the acceptance
   gates below. Update affected contract/spec implementation-status declarations,
   host-neutral operator/API documentation, README orientation and the existing
   [Kinflow handoff](INDEPENDENT_READS_KINFLOW_HANDOFF.md) to match actual behavior.
   Provide exact supported versions, example public responses, failure/cache rules,
   migration assessment and deployment/rollback instructions. Do not mark Kinflow
   adoption or staging verification complete based on backend tests.

### Runtime acceptance and evidence

- Map IR-01–IR-15 to executable backend/HTTP tests with real canonical item,
  recurrence, ownership, permission and binding fixtures; IR-16 is the consumer
  integration gate, supported by backend fixtures but verified in Kinflow.
- Exercise independent event/occurrence/agenda success, legitimate visible related
  items, generic direct denial, and indistinguishable missing versus hidden context.
  Include hidden-graph growth, protected nested evidence and cursor/hash inspection;
  no hidden-dependent count, capacity result or existence explanation may leak.
- Prove stale/unavailable own-source time never releases an old due date; cover
  resolved-empty recurrence, unscheduled tasks, unplaced cores, DST/all-day/UTC,
  overrides/exclusions and terminal lifecycle against canonical engine output.
- Exercise first-page and continuation races, grants appearing/disappearing through
  time without epoch writes, version guards, identity switches, cursor tampering,
  cross-route/section replay, fixed expiry and combined agenda limits. Hidden-only
  follower changes must leave independent snapshots valid absent a global epoch change.
- Trace/read-check success and failure paths to prove no durable domain writes,
  receipts, provenance regeneration, work creation or sends. Test budget boundaries
  and optional degradation without consuming core reserve. Preserve existing v1,
  CLI and cross-resource write denials, including writes attempted after a v2 read.
- Extend `tests/test_independent_activity_read_contracts.py` and add dedicated
  runtime/HTTP tests without replacing existing expectations in
  `tests/test_trusted_web_runtime.py` and `tests/test_trusted_web_contracts.py`.
  Run focused tests first, then the full project suite with its required local
  dependencies, lint/diff hygiene and installed-package contract checks. Record exact
  commands/results and any genuine environment limitations in SPINE-015.

### Release and consumer sequence

Backend completion means implemented contracts, passing runtime gates, packaged pins,
and an actionable handoff—not a deployed capability. On separately approved deployment,
preserve the ledger and existing worker, follow any demonstrated migration requirement,
and verify service health plus v1 and v2 canaries. Use controlled mixed-access fixtures;
do not repair ownership or send real reminders as a test shortcut.

Kinflow then adopts the exact advertised capability, canonical occurrences and
structured time/section states. Verify IR-16 late-response/identity-switch handling
and IR-15 mixed-client/rollback behavior in that repository. Capability loss clears
v2 caches/cursors and retains explicit unsupported/legacy failure behavior; it must
not turn into a fabricated empty calendar. Record backend delivery, staging validation
and consumer adoption as separate evidence so SPINE-015 closes only when its agreed
end-to-end acceptance is met.

## Delivered Sustaining Slice: Canonical Owner-Scope Discovery

Schema 11 implements the contract in `specs/owner-scope-discovery.md` as a bounded read-only `owner_scope.list`
projection so agents can discover active system, subject, and subject-group owner
scopes before creating archetypes, notification profiles, and bindings. The slice
removes routine table knowledge from owner selection while retaining existing
per-owner catalog list commands. It requires closed schemas, fixtures, cursor and
generation tests, indexed bounded selection, runtime registry parity, and a no-write
proof before advertisement.

## Delivered Slice: Deterministic Notification Rendering

The schema-9 runtime now turns admitted ordinary reminder work into deterministic,
concise `en-CA` prose at attempt start. Rendering uses the proposed attempt time plus
current canonical title, target, item type, pinned target timezone, occurrence or
follow-source binding evidence, and primary location. Relative phrases cover the
six-hour window; longer horizons use calendar wording such as `at 2 PM tomorrow`.

Each rendering is immutable evidence linked one-to-one with its side-effect attempt.
The rendering and `attempt_status=started` row commit atomically, the OpenClaw request
envelope binds rendering identity/content hash/exact body, compatible replay cannot
authorize another transport call, retries receive new attempt-time evidence, and
`schedule.show` nests stored evidence under the corresponding attempt. The public
schema, schema-object manifest, computed vector, failure oracles, migration, runtime
capability declarations, and operator documentation ship with the implementation.

## Delivered Sustaining Slice: Scheduler Planning and Durable No-Op Suppression

The Tickerd-driven horizon cycle now performs bounded read-only Spine planning before
dispatching receipt-bearing provenance or notification-work operations. Active policy
presence alone no longer causes materialization. A plan dispatches only when it can
create missing actionable work, repair recurrence provenance needed by the evaluated
horizon, or reconcile stale cancellable work with `status=eligible`, zero attempts,
and no side-effect-attempt evidence.

Past exhausted one-shot and bounded policies, already-materialized opportunities, and
recurrence horizons with no qualifying occurrence now produce zero ledger growth.
`deliver_within` remains eligible through its exact grace interval; disabled-policy
work remains discoverable for reconciliation; existing retry, in-progress, and
terminal work remains protected history. The dispatch limit counts actionable plans
rather than raw active-policy rows, preventing exhausted items from starving later
work. Explicit `notification_work.materialize` retains its receipt-bearing
zero-selected, all-retained, changed, collision, and replay semantics.

Behavioral proof covers exhausted and future one-shots, exact late grace, local-time
target-relative expansion, equivalent-work suppression, explicit no-op receipts,
policy-edit and policy-disable reconciliation, exhausted and active recurrence,
repeat-cycle provenance suppression, and dispatch-limit fairness. The complete suite
passes without a schema migration or public command change.

## Delivered Fat Slice: Atomic Schedule Creation

The audited `spine.schedule-create.v2` contract is implemented as one environment-sized delivery. The operator-facing `schedule.create` command creates an event or task, its local-instant anchor, optional archetype and notification-profile application, optional inherited recurrence, complete initial reminder-policy set, optional occurrence provenance, and optional bounded notification work in one transaction and returns one replay-safe composite receipt.

The delivery includes:

- transport-neutral command registration plus the `spine-command ... schedule create` CLI alias;
- normalized `CommandContext.delivery_target_defaults` resolution without route creation or approval;
- exact timezone-version pinning, fail-closed initial local-time resolution, and internal UTC horizon normalization;
- direct reuse of canonical recurrence, notification, provenance, opportunity, and work engines without public subcommand chaining;
- one version-`1` item, one composite audit, and one composite command receipt with full rollback on any child failure;
- compatible replay from stored result evidence, deterministic dry run, and post-commit receipt/evidence verification;
- behavioral coverage for event/task, recurrence, policy-only/materialized branches, routes, DST, replay, semantic uniqueness, injected rollback, and the no-send boundary; and
- runtime command/version declarations plus agent/operator documentation aligned with the executable surface.

Behavioral proof covers non-recurring events, recurring tasks, policy-only and bounded branches, named and explicit routes, recurrence provenance, response-schema conformance, replay without current-environment re-resolution, dry-run identity equivalence, DST ambiguity rejection, task-role semantic uniqueness, injected failure after each write phase, and the no-send boundary.

This original slice required no schema migration because schema 7 already owned every canonical row required by schedule creation. Schema 8 was later added for explicit relative temporal bindings.

## Delivered P0: Canonical Schedule Verification

The `spine.schedule-show.v1` read model is implemented as the operator verification boundary over the current schema. It returns current item and schedule facts, concrete timezone-version and UTC-resolution evidence, recurrence, current notification policies and intent IDs, bounded work and attempt detail, route snapshots, relations and temporal bindings when requested, complete status counts, and separate authored/opportunity/work/delivery lifecycle dimensions. The direct CLI `--item-id` and `--include` form maps to the same transport-neutral command request.

The related documentation audit treats `notification_policies.policy_id` and the public `notification_policy_id` alias as distinct intentional surfaces, replaces item-specific operator SQL with `schedule.show`, and documents `timezone_database_version.kind=system_current` as a one-time pin to a concrete version. Omission remains invalid and compatible replay retains the original resolved version.

## Delivered Operator Layer: Compact Receipts and Countdown Builder

The `spine.schedule-compact.v1` CLI projection provides audit-complete, chat-sized success output for `schedule.create` and `schedule.show` while retaining full JSON as the default. It carries item/command/receipt identity, scheduled time and pinned timezone data, policy and intent IDs, bounded work identity, route source/target references, and separate authoring, expansion, materialization, attempt, and outcome states.

The read-only `schedule.build` command implements `spine.schedule-countdown-builder.v1`. It compiles an explicit reference instant plus relative event delay and reminder cadence into a normal, fully pinned `schedule.create` request. Its first tested profile—event in two hours, remind every 30 minutes until start—resolves the route and timezone version, bounds four work opportunities, performs no write, and feeds the existing atomic authoring path unchanged.

## Delivered Fat Slice: Operational Schedule Lifecycle

`specs/schedule-operations.md` defines the implemented contract family for daily schedule operation after creation:

- `agenda.show` provides one bounded cross-item local-time agenda with recurrence expansion and snapshot-bound pagination;
- `schedule.update` atomically changes whole-item schedule truth, whole-series recurrence, reminder policies, and delivery routing while reconciling obsolete never-started work and optionally materializing a replacement horizon; and
- `schedule.cancel` performs a type-neutral terminal transition and cancels all never-started notification work without rewriting started or terminal evidence.

The implementation is one environment-sized service-layer slice over the canonical scheduling engines rather than public subcommand chaining. It declares the complete version family, exposes all three commands through transport-neutral dispatch and the generic CLI, writes deterministic receipts and audits, preserves immutable canonical detail, supports dry run and replay, and has behavioral coverage for agenda selection/cursors, recurrence replacement, reminder replacement, reconciliation, bounded materialization, cancellation, and no-send behavior. This slice itself required no migration.

## Delivered Fat Slice: Relative Temporal Bindings and Atomic Related Tasks

`specs/relative-temporal-bindings.md` is implemented as one schema-8 family. `schedule.related_task.create` atomically creates a normal task, concrete due anchor, stored `part_of` relation, explicit `snapshot|follow_source` binding and immutable first revision, optional reminders, optional bounded work, one audit, and one receipt. A selected recurring source also creates or refreshes bounded `consumer=temporal_binding` occurrence provenance in that transaction.

`schedule.binding.list` provides bounded state-ordered discovery with generation-bound cursors. `schedule.binding.reconcile` resolves one follow-source binding at a time, creating an ordinary next task version when derived due time changes, refreshing only binding evidence for source-only changes, applying terminal/detach/decision outcomes, and reconciling notification work without sending. Tickerd's horizon cycle invokes only automatically eligible branches.

Safety is independent of sweep cadence: direct due replacement is rejected while a follow binding governs the task, agenda/readback expose stale or decision state without erasing the task, and work processing checks binding freshness before a side-effect attempt can start. Structural schemas and initial fixtures live in `contracts/relative-temporal-binding-fixture-manifest.json`; runtime coverage includes atomic rollback, replay, dry run, selected occurrences, source movement, source-only refresh, snapshot divergence, cursor invalidation, scheduler terminal handling, agenda actionability, and stale-delivery rejection.

## Delivered Additive Slice: Primary Schedule Location

`specs/schedule-primary-location.md` activates the existing canonical `locations` and
version-scoped `item_locations` model across the high-level scheduling surfaces without
adding another location authority or a schema migration. `schedule.create` and
`schedule.update` accept closed inline-create/reference forms; `schedule.show` and
`agenda.show` expose an explicitly requested clean view; `schedule.build` passes the
public authoring value through; and compact create/show receipts preserve the complete
bound view when present.

The implementation derives deterministic location and item-location identities,
copies retained primary roles across item versions, preserves immutable historical
rows on replace/clear, validates references inside the transaction, and snapshots
replay evidence. Location timezone remains descriptive and cannot alter schedule time,
location-only mutation does not stale recurrence provenance or reminder work, and
authoring still performs no send. Structural fixtures plus behavioral tests cover
inline/reference creation, dry run, replay after metadata refresh, read projections,
no-op/copy-forward behavior, replace/clear, missing references, rollback, work
retention, and runtime capability declarations.

## Delivery Goal

Ship one environment-sized implementation that supports the complete path from a structured recurrence or notification command to deterministic virtual results, canonical relational state, durable notification work, Tickerd processing, and a recorded adapter attempt.

The delivery is intentionally broad because recurrence identity, occurrence provenance, notification scheduling, reconciliation, and work authorization are one connected system. Internal gates isolate faults; they are not separate deployment units.

## Authority Map

- `specs/recurrence.md`: recurrence normalization, identity, expansion, mutation, lineage, and occurrence provenance.
- `specs/notifications.md`: notification schedules, opportunities, late handling, materialization, and reconciliation.
- `specs/notification-rendering.md`: deterministic attempt-time prose, immutable evidence, and adapter-envelope binding.
- `specs/operational-resilience.md`: draft cross-cutting resource bounds, failure containment, recovery, dependency admission, and sustained-operation proof.
- `specs/ontology.md`: relational authority and lifecycle invariants.
- `specs/agent-command-contract.md`: public command and receipt behavior.
- `specs/schedule-show.md`: canonical aggregate schedule and delivery-lifecycle readback.
- `specs/schedule-operator-tools.md`: relative countdown compilation and compact operator projection.
- `specs/schedule-operations.md`: implemented cross-item agenda and atomic schedule update/cancel reconciliation lifecycle.
- `specs/schedule-primary-location.md`: implemented primary-location authoring, mutation, builder, readback, and compact-projection extension.
- `specs/relative-temporal-bindings.md`: implemented atomic related-task creation, binding persistence/state, bounded discovery, reconciliation, and attempt freshness.
- `contracts/schemas/recurrence-*.schema.json` and `contracts/schemas/notification-*.schema.json`: public machine shapes.
- `contracts/vector-manifest.json`: computed identity and behavior evidence.

## Delivered Surface

### Deterministic scheduling engine

- Canonical `local_date`, `local_instant`, and `instant_utc` schedule facts.
- `DAILY`, `WEEKLY`, `MONTHLY`, and `YEARLY` frequencies.
- Positive intervals, count and inclusive-until bounds, selector defaults, weekday/month/month-day/set-position selectors, and week starts.
- Invalid-calendar-date omission, pinned timezone facts, nonexistent-local omission, and earliest-instant ambiguous-time resolution.
- Rdates, exdates, detail/lifecycle overrides, moved occurrences, duplicate collapse, deterministic ordering, diagnostics, density limits, bounded ranges, and revision-bound cursors.
- Exact original-schedule and expressed-time range behavior, including occurrences moved into the requested expressed range.

### Canonical persistence and migration

- Schema version 8, retaining schema-7 recurrence and notification authority while adding explicit temporal-binding headers, immutable revisions, and a cursor-invalidation catalog generation.
- Occurrence provenance snapshots, slot uniqueness, supersession, and unresolved-range reports.
- Stable notification-intent identities, immutable policy versions, structured schedule rows, boundaries, selectors, and occurrence target selectors.
- Opportunity-bound work snapshots and fail-closed work/attempt constraints.
- One transactional migration bundle with clean-prior-schema, structural, constraint, rollback, and scheduling-data preflight coverage.
- One active scheduling authority after migration.

### Commands and mutations

- Structured recurrence authoring on event-start and task-due anchors.
- `item.occurrences` with bounded pagination and diagnostics.
- `recurrence.instance.add`, `.remove`, and `.override`.
- `recurrence.series.edit` with `one`, `this_and_following`, and `whole_series` scopes.
- `occurrence_provenance.regenerate` with closed effects and report behavior.
- `reminder.create`, `.edit`, and `.disable` for structured notification policies.
- `notification.opportunities` and `notification_work.materialize`.
- `schedule.show` with bounded policy, work, route, receipt, and attempt evidence.
- `schedule.related_task.create`, `schedule.binding.list`, and `schedule.binding.reconcile`, plus relation/binding schedule readback and agenda actionability.
- Deterministic replay, stale-version checks, dry runs, receipts, and atomic item/supporting-set writes.

### Notification and delivery path

- Once, explicit-offset, fixed-elapsed repeat-window, and local-calendar notification schedules.
- Item, each-occurrence, and selected-occurrence application scopes.
- Stable intent, schedule, slot, opportunity, cursor, and work identity.
- Explicit late handling and deterministic opportunity diagnostics.
- Duplicate-safe materialization and unstarted-work reconciliation after policy, target, routing, recurrence, occurrence, or lifecycle changes.
- Tickerd horizon reconciliation, observe-only execution, active bounded execution, and fake OpenClaw evidence.
- `side_effect_attempts` as the sole adapter-attempt ledger.

### Contract evidence

- Full Draft 2020-12 validation for all schemas, manifests, and contract fixtures.
- Computed recurrence and notification vectors generated through the executable normalizers and expanders.
- Published canonical inputs, normalized output, preimage JSON, digests, and expansion results for the two primary scenarios:
  - every three days at 08:00 local;
  - every hour during the six hours before an event.

## Final Acceptance Evidence

The fat slice passed the following consolidation and proof campaign:

1. Keep normative specs, README, operator guide, and this plan aligned with the executable surface.
2. Remove dead prototype helpers and obsolete golden artifacts so only the canonical command family is discoverable.
3. Run strict type checks and focused style checks over every changed scheduling module.
4. Run the complete test suite with the sibling Tickerd source available so integration tests execute rather than skip.
5. Run the official schema/fixture validator and computed-vector corpus independently.
6. Rehearse migration from a clean schema-version-6 ledger, migration preflight rejection, injected rollback, and post-migration verification.
7. Run a bounded canary sequence: seed, observe-only, active with fake OpenClaw, inspect work and `side_effect_attempts`.
8. Review the diff for one-authority behavior, accidental direct-send paths, secret material, and unrelated user changes.

## Acceptance Campaign

The environment handoff should support one concentrated user test campaign:

1. Author every three days at 08:00 in an IANA timezone, cross a DST boundary, and verify stable pagination and identity.
2. Exercise weekly selected weekdays, monthly last-day, yearly selectors, local dates, and fixed UTC schedules.
3. Add, remove, move, and lifecycle-override occurrences; inspect immutable revisions and lineage.
4. Apply one, following, and whole-series edits, including a count-bounded split.
5. Author every hour during the six hours before an event, inspect six opportunities, materialize, and replay an overlapping range without duplicate work.
6. Author every-day-at-08:00-local notification cadence and verify wall-clock behavior through DST.
7. Target every occurrence and one selected occurrence; verify current provenance is required before work is authorized.
8. Edit recurrence, reschedule a target, change routing, disable a policy, and end the parent lifecycle; verify unstarted-work reconciliation and immutable started history.
9. Process materialized work through Tickerd and fake OpenClaw; inspect success, retryable failure, permanent failure, idempotency, and attempt evidence.
10. Consider a real OpenClaw canary only as a separate explicitly approved operation after all fake-path evidence is clean.

## Exit Criteria

The fat slice is ready for one environment patch only when all of the following are true:

- Every accepted recurrence and notification schedule surface is implemented across core logic, persistence, services, commands, responses, and tests.
- Equivalent commands on fresh ledgers produce byte-identical identities, hashes, order, cursors, effects, and receipts.
- Recurrence-bound work and side effects fail closed without active current occurrence provenance.
- Notification cadence and delivery retry remain observably distinct.
- Every adapter attempt is recorded in `side_effect_attempts` before the external boundary.
- The complete tests, strict type checks, focused style checks, official schema validation, computed vectors, migration rehearsals, and fake canary pass.
- The operator guide provides exact inspection, migration, rollback, and bounded canary instructions.
- No external send or deployment has occurred during implementation verification.

## Internal Gates

| Gate | Proof | State |
|---|---|---|
| Engine | Pure recurrence and notification normalization/expansion tests and computed vectors | Passed |
| Ledger | Schema-8 constraints, v6-to-v8 migration, preflight, and rollback tests | Passed |
| Commands | Authoring, reads, mutation, replay, cursor, and provenance tests | Passed |
| Notifications | Opportunity, materialization, reconciliation, and recurrence-binding tests | Passed |
| Delivery | Tickerd observe-only and active fake OpenClaw with durable attempts | Passed |
| Handoff | Full no-skip suite, documentation, migration rehearsal, and bounded fake canary | Passed |

## Deferred Beyond This Delivery

- governance-authority approval integration.
- Calendar and vendor adapters beyond the OpenClaw path.
- General daemon ownership in Spine; Tickerd remains the runtime owner.
- Conversational parsing as canonical truth; ingest must persist explicit structured facts.
- Dashboards and broad external projections.
- Release freeze-manifest promotion.

## Next Initiative: Operational Resilience and Boundedness

Historical initiative, now deferred by operator direction (2026-09-13). The heading
is retained for existing links; consult the backlog for current scheduling.

`specs/operational-resilience.md` is the draft authority for the next sustaining
initiative. It converts the storage-growth incident and the broader runtime sweep into
one cross-cutting contract without moving notification semantics into Tickerd or
granting automatic deletion authority over the ledger.

The planned delivery order is:

1. **Containment:** wire process-enforced Tickerd event-file limits at every Spine sink;
   retain host rotation/quota as defense in depth; expose storage pressure; validate
   retry configuration; implement `spine.tickerd-compatibility.v1` against Tickerd
   `0.2.0`, capability `tickerd.runtime-capabilities.v1`, and audited revision
   `ffe613c65ea3d6fc70a1dc3603c32068f06350df`; report that exact dependency; and add a transitional
   fail-closed dry-run size ceiling.
2. **Recovery:** isolate poison-item reconciliation failures; add bounded backoff,
   circuit breaking, and retry exhaustion; define in-progress lease recovery and
   ambiguous external outcomes through an accepted decision, ontology amendment,
   migration, readback, and operator workflow.
3. **Scalability:** replace full-fetch and count/offset automatic discovery with fair
   keyset traversal; make notification materialization continuation-complete; bound
   agenda/readback computation; and enforce request, text, collection, and expansion
   budgets at the core boundary.
4. **Qualification:** run the required idle/backlog/provider-outage/crash/tzdb/WAL/disk-
   pressure/large-ledger scenarios before declaring conformance.

This initiative does not subsume the future ledger-storage lifecycle below. It adds
budgets, alarms, stop conditions, and classification; archival or compaction still
requires its own explicit authority and recovery proof.

Runtime `0.2.0` completes the Tickerd compatibility portion of containment: exact
package/capability admission, `system.info.v2`, bounded worker event sinks, pre-cycle
storage pressure stops, and a process-local durability latch. Retry-budget validation,
the transitional dry-run ceiling, broader storage readback, and the recovery/scalability
items remain future slices.

### Future Horizon: Bounded Ledger Storage Lifecycle

Spine's ledger is canonical, append-oriented coordination evidence, so its storage
lifecycle must not be treated as ordinary log rotation. The recent scheduler no-op
suppression removes accidental idle growth; the remaining legitimate growth should be
measured in staging before retention or archival policy is designed. This horizon item
does not authorize automatic deletion, compaction, or archival.

The future work should proceed in this order:

1. Establish a post-fix storage baseline and a supported storage readback that reports
   database, WAL, table, index, and major evidence-family growth without requiring raw
   SQL from operators.
2. Classify every durable fact family as permanent canonical truth, replay/audit
   evidence, reconstructable derived data, archive-eligible evidence after semantic
   closure, or prohibited ephemeral telemetry.
3. Resolve the idempotency boundary before pruning command receipts: either preserve
   indefinite replay evidence or define a finite replay window backed by a compact,
   durable replay fingerprint or tombstone contract.
4. Specify explicit archival and compaction operations with immutable manifests,
   content hashes, verification, restore/readback behavior, and fail-closed handling.
   Delivery attempts and other safety evidence remain durable unless a normative
   retention rule proves otherwise.
5. Add disk budgets, growth alarms, and operator stop conditions. Spine must never
   automatically delete canonical evidence merely because a storage threshold is
   crossed.

Backups protect recovery but do not reduce the active ledger. WAL checkpointing only
controls the WAL sidecar, and `VACUUM` only reclaims pages after an independently
authorized retention operation. Rotating whole database files is not an acceptable
substitute because it would fragment Spine's canonical authority.

### Future Horizon: Archetype Facets and Workflow Recipes

Specification work started 2026-09-07: `specs/decisions/0004-versioned-item-facets.md`
and `specs/archetype-facets.md` define the proposed first facet slice. Decision 0004's
logical architecture was ratified on 2026-09-24; the companion facet specification
remains a draft and implementation is not authorized. The v0.2 bounded recheck passed; draft
machine schemas, structural fixtures and pure identity/type vectors were added on
2026-09-09. The first machine-contract audit identified replay-response alignment
and test-dependency scope issues; both were manually patched on 2026-09-12, with a
focused recheck subsequently passing with preserved boundary. Its only clarification
concerned wording in the recheck notes, not a source-contract mismatch. The hybrid
physical design in [archetype-facet-storage.md](../specs/archetype-facet-storage.md)
was accepted as v1.0 on 2026-09-25 after a bounded buildability audit and its manual
minor patch. The 2026-09-26 v0.6 logical amendment specifies permission resolver mappings,
authenticated cursor/source-snapshot semantics and exact notification continuity,
with `contracts/archetype-facet-integration.v1.json` and test-only oracles. Its targeted
v0.7 corrections passed the focused buildability recheck on 2026-09-26 with zero findings
and preserved boundaries. Implementation is sequenced above as SPINE-027–029;
remaining executable gates include exact DDL/object manifests,
migration fixtures and persisted/concurrent proofs of those contracts. In particular,
attempt-start policy resolution must survive multiple copy-forwards by stable intent;
source-event edits retain existing downstream follow_source invalidation. Shared
location references remain unavailable in the permission-enforced web subset until
their family owns a disclosure rule; the flight proof remains trusted-local. Static fixtures do not prove runtime
behavior. Workflow recipes and external observations remain separate future work;
current pack and web registries are unchanged.

Spine's current archetypes are intentionally thin, owner-scoped semantic identities.
Their future value should grow primarily through separately versioned capabilities
that bind to them, rather than through rigid event subclasses or an expanding set of
archetype-specific core tables. The facet delivery plan does not depend on the deferred
Operational Resilience and Boundedness campaign and does not authorize implementation.

The intended boundary is:

- Spine owns a generic, versioned facet substrate and the canonical facet values
  attached to immutable item versions.
- Reusable packs may define owner-neutral facet schemas and workflow recipes, but pack
  artifacts do not contain an operator's item data and do not execute at runtime.
- Domain-specific facts such as airline, flight number, provider, or opponent remain
  typed facet values unless a concept becomes broadly useful enough to promote into
  Spine's generic coordination model.
- External, volatile facts such as a live flight gate, delay, weather forecast, or
  vendor status remain provenance-bearing observations and must not silently overwrite
  canonical scheduled facts.
- Workflow recipes remain declarative authoring conveniences outside Spine. A
  deterministic runner or agent may expand an explicitly selected recipe through
  Spine's public commands; Spine owns the resulting items, relationships, temporal
  bindings, policies, and receipts.
- A future owner-scoped activation preference may record which exact recipe version is
  suggested, automatic, or disabled for an archetype, without moving recipe execution
  into Spine.

The architectural progression is retained below; steps 1–2 now have the accepted
design and reviewed machine-contract foundation described above. Their runtime proof
belongs to SPINE-027–029; steps 4–5 remain separate future work:

1. Accept an architecture decision defining the core-versus-facet promotion rule,
   schema ownership, immutable schema versioning, provenance, query/index requirements,
   and the boundary between canonical facts and external observations.
2. Specify a generic facet registry, versioned item-facet persistence, command
   authoring and mutation surfaces, deterministic validation, and complete readback.
   Arbitrary unregistered attribute bags and direct database writes remain prohibited.
3. Prove the substrate narrowly with `flight_details.v1`, covering airline, flight
   number, and typed origin/destination references while retaining departure, arrival,
   time-zone, lifecycle, and primary-location authority in Spine's generic model.
4. Specify external observation provenance and expiry before adding live terminal,
   gate, delay, or status enrichment.
5. Specify pack-distributed workflow recipes, deterministic plan/apply/verify behavior,
   owner-scoped activation preferences, and explicit authorization before allowing
   recipe-driven authoring.

Starter packs may anticipate these future references in design notes, but released
pack contracts must not claim facet or recipe capabilities until the corresponding
Spine contracts, migrations, commands, readback, and compatibility declarations exist.

### Future Horizon: Notification-Activated Contextual Advisories

The first contextual-advisory product path should enrich an explicitly selected
notification rather than create an independent, hidden scheduling system. The operator
selected notification-template activation and ordinary fallback on 2026-09-12, while
the advisory definition, governance decision, model/tool execution, and accepted
evidence remain separate versioned artifacts with distinct owners. This horizon does
not authorize implementation and does not expand the current notification-profile
contracts.

The intended boundary is:

- A notification template may optionally reference an immutable contextual-advisory
  definition and declare deterministic fallback behavior. It defines trigger timing,
  not executable logic, prompts, credentials, providers, or a runtime-selected plan.
- Spine remains the temporal and coordination authority. It owns deterministic
  opportunity and work identity, exact item or occurrence provenance, source and
  deadline freshness, derivative notification lineage, and delivery readback.
- A separate advisory definition bounds the objective, visible context, capability
  profile, tool/model/runtime budgets, evidence requirements, usefulness deadline,
  allowed outcomes, and whether intentional silence is permitted.
- The governance authority grants or denies capability. An external agent runtime may
  decide what to investigate only within that grant and cannot mutate Spine or deliver
  directly.
- Ordinary deterministic reminder rendering remains the reliable default. Advisory
  outage, timeout, denial, invalid evidence, or stale evidence normally falls back to
  the base reminder and must never be misreported as a successful no_action outcome.
- Accepted no_action also falls back by default; suppression requires explicit bound
  silence permission. Accepted content, fallback, and suppression share one persisted
  selection for one notification delivery identity. Late enrichment cannot create a
  second notification. Materialization failure after selection requires explicit
  recovery, not an automatic branch switch or another model run.
- Context is acquired near delivery under explicit freshness bounds. Temporal
  expansion remains model-free, and recurrence produces separately bound advisory work
  for each applicable occurrence.
- Reusable packs may eventually distribute owner-neutral advisory definitions and
  template activation references, but pack artifacts remain declarative and have no
  runtime or operator data.
- Proactive planning sweeps are a separate trigger model. They may reuse mandate, run,
  evidence, and governance machinery, but they must not inherit authority merely from
  notification-template support.

The delivery sequence should be:

Shared architecture drafting (SPINE-020) follows the protection and native-handoff
investigation. [Cross-System Execution Architecture](../specs/cross-system-execution.md)
is the proposed versioned source for the Impetus HLD and later component mappings.
Component specs reference an exact document version and committed source, without
copying authority or claiming automatic adoption. The initial draft does not select
a runner backend or close the native execution and advisory machine-contract gaps.

Before the advisory machine-contract step, apply the narrowly scoped architectural
protection amendment in [Decision 0005](../specs/decisions/0005-profile-scoped-advisory-execution.md)
and compare it against the [preservation checklist](design-notes/advisory-protection-preservation-checklist.md).
This is the selected specification-only task SPINE-017, not selection of the broader
SPINE-011 horizon or general workflow implementation. Native field correlation,
run/attempt/retry and budget ownership, and freshness handoff must be settled before
the advisory contracts are finalized. Future people/responsibility or facet context
uses its own authoritative contracts when consumed; those implementations and general
workflow support do not become blanket prerequisites for basic event enrichment.
A later bounded audit should examine explicit preservation objectives and the three
extension cases without claiming implementation readiness or restarting deferred
resilience/storage campaigns. Current status and completion evidence live in the backlog.

1. Publish and operationally prove the Version 1 pack format using only archetypes,
   notification profiles, and owner-scoped default bindings.
2. Audit the reconciled notification-template activation/fallback direction in
   specs/contextual-advisories.md and settle the remaining definition/activation schema,
   work-kind, evidence-ownership, context-minimization, budget, and operator-surface details.
3. Specify immutable advisory definitions, notification-template references,
   deterministic fallback and silence semantics, per-occurrence identity, freshness,
   replay, reconciliation, and complete readback.
4. Define and audit cross-system capability, governance, submission, execution-result,
   and evidence-acceptance contracts before creating runtime adapters.
5. Implement one bounded read-only vertical slice: a location-bearing event, one
   target-relative template activation, bounded agent-selected research, and zero or
   one accepted advisory routed through ordinary notification delivery. Use the golf
   preparation scenario as a conformance example, not a hard-coded weather workflow.
6. Only after the Spine and advisory-runtime capabilities exist, introduce a new pack
   manifest version that may independently carry facet schemas, advisory definitions,
   and template activation references. Version 1 packs and installations remain valid.

The companion non-normative exploration is
docs/design-notes/scheduled-agent-autonomy.md. The existing
specs/contextual-advisories.md draft now records this selected direction. Machine
contracts, timing/selection race fixtures, native mapping, and implementation remain
future work; the prior selective-synthesis audit did not cover this subsequent change.

## Next Delivery: Trusted Multi-Operator Web API

First delivery: multiple trusted operators, initially two, selecting their identity
honestly in the web interface. Existing WhatsApp agent operation remains unchanged;
new protected chat admission or account-attribution integration is not a gate for this slice.
`specs/accounts-and-chat-attribution.md` owns accounts and attribution;
`specs/identity-and-access.md` owns authentication/delegation architecture;
`specs/permissions.md` owns resource permissions, group roles, and access modes.

Use `access_mode=multi_user` and `identity_mode=trusted_identity`. Accounts bind to
distinct subjects; owners, roles and grants govern the selected identity's operations.
No automatic full-scope grant for both operators and no impersonation protection claim.
Restrict deployment to trusted devices/operators. Unknown identities never fall back
to an operator. Single-operator full scope remains a separate optional access mode.

`specs/permission-enforcement-and-web-admission.md` preserves the broader normative draft:
physical ownership/role/grant revisions, an exhaustive current-command disposition,
verified web sessions, access epochs, bounded queries, receipt linkage and delivery
authorization. Section 1 separates the immediate trusted slice from the preserved
deferred protected path; it declares no runtime or schema support.

`specs/trusted-multi-operator-web-api.md` now drafts that first service slice: honest
per-request identity context, local plan/apply provisioning, thirteen allowlisted
scheduling/catalog-use commands, scoped agenda and unscheduled-item reads, permission
checks, atomic owner/attribution evidence, replay and bounded service operation.
It preserves current task-completion behavior rather than claiming that completion
automatically cancels all queued work.

### Audit Status

- Web API draft committed in `63aee41`; manual corrections committed in `a0f9da1`.
- `trusted-multi-operator-web-api-contract-audit-001`: `pass_with_minor_clarification`,
  boundary preserved; one terminology clarification and one stale schema reference.
- `trusted-multi-operator-web-api-contract-audit-002`: focused recheck `pass`, boundary
  preserved, zero findings. The corrections use canonical `access_epoch` /
  `expected_access_epoch` and align the schedule-create reference to schema 12.
- Reports are retained under `whetstone_runs/` in each run's `change_audit/` directory.
  This is bounded logical consistency evidence, not full convergence, runtime verification
  or qualification of every future permission/authentication feature.

No additional broad spec draft or routine audit loop is scheduled now. Resolve concrete
gaps exposed by codification with narrow updates to the existing authorities; escalate
material product/boundary decisions instead of inventing them in schemas or runtime code.

### 1. Codify the Contracts — Initial Bundle Added

The first bundle is indexed in [TRUSTED_WEB_CONTRACTS.md](TRUSTED_WEB_CONTRACTS.md):
closed registry, pinned inner schema dependencies, HTTP/provisioning/evidence schemas,
plan/ID vectors and positive/negative fixtures. The dedicated static suite checks these
artifacts; runtime tests now accompany the `WEB-01`–`WEB-15` scenario mapping. Schema 13
and signed-wire vectors are implemented. Catalog nested-result authorization remains
an executable resolver concern, not a claim made by the broad canonical response schema.

Add machine-readable artifacts to this repository; this does not mean external publication
or deployment. Cover:

- HTTP request/response and error envelopes, identity selection, operator/context reads,
  scoped agenda/item projections and cursor encoding/normalization.
- Local `web_access.plan` / `web_access.apply` provisioning, normalized plan hashes,
  explicit operation paths, registered row-ID roles, effects and failure shapes.
- Minimal account/access persistence and receipt-attribution linkage, including the
  shared access epoch and atomic ownership/evidence requirements; align the ontology
  and migration design without adopting the entire deferred authentication model.
- The closed thirteen-command web registry with pinned inner request/response versions,
  required contracts, resource/effect resolvers and projection rules. Do not change the
  canonical inner CLI families or advertise unimplemented web capabilities.
- Positive/negative/replay/concurrency fixture scenarios mapped to `WEB-01`–`WEB-15` in
  the web spec. Define expected state/evidence as well as wire shapes; schema validation
  alone is not proof of permission or transaction behavior.

Exit gate: artifacts validate, registry/fixture coverage is checked, and no unresolved
logical decision prevents the backend from being implemented. Runtime-dependent oracles
remain explicitly pending until exercised in the next stages.

### 2. Cohesive Backend Slice — Implemented

Spine 0.4.0 adds the optional `spine-web` entry point, local plan/apply provisioning,
schema-13 access heads/history and owner indexes, complete-or-deny resolvers, shared
outer transactions, exact runtime pins, signed cursors, bounded private HTTP admission,
and no-write reads. Existing local CLI and worker remain full-scope. See
`docs/TRUSTED_WEB_OPERATIONS.md` for provisioning and paired rollback.

The original delivery scope below remains the checklist:

Build the minimal migrations, account/subject selection and permission state, local
provisioning commands, bounded HTTP service, scoped reads and allowlisted scheduling/
catalog-use handlers. Reuse shared transaction-owned command services, not CLI subprocesses
or separately committing composites. Commit owner/attribution facts with canonical effects
and receipts; preserve replay, current versions and all existing scheduling capabilities.

Include readiness, request-integrity checks, capacity limits and bounded diagnostics.
Use established HTTP framework mechanisms without adding authentication/session machinery.
Keep the browser GUI as a separate follow-on deliverable; the backend must be testable
with an API client and fixtures without a completed GUI. These are internal implementation
gates, not a requirement to deploy many small intermediate slices.

### 3. Verification — Local Checks Added; Deployment Gates Remain

The runtime suite exercises all thirteen commands, canonical scheduling results,
private/group rights, route approval invalidation, same-ID concurrent creates, local
writer contention, stale revisions/cursors, failure rollback, immutable access history,
1,000 idle reads, and a ledger with 100,000 unrelated receipts. Budgets remain fixed;
overflow returns capacity rather than false completeness. No external transport was
invoked. Full regression verification remains required for each release.

Still perform the network/TLS and two-device staging acceptance below. Actual browser
identity-switch/discard behavior belongs to the forthcoming GUI, not these backend tests.


Execute the `WEB-01`–`WEB-15` oracles, focused contract/runtime tests and the appropriate
full regression suite. Explicitly cover two distinct selected subjects; member/admin/owner
and private/group boundaries; denied nested/history disclosure; default profiles and custom
reminders; recurrence/location; task completion versus work reconciliation; and unchanged
local CLI/worker behavior. Test identity-switch correlation using a client harness; reserve
actual browser cache/late-response UX verification for GUI acceptance.

Exercise same-ID retries after ambiguous outcomes, atomic rollback, foreign-ID disclosure,
access-epoch changes, stale cursors and simultaneous CLI/web/worker activity. Benchmark
production-sized fixtures, qualify the proposed SQL/time/response ceilings and ratify any
adjustments explicitly. Prove bounded preflight and absence of read/idle receipt or log floods.
Passing static fixtures alone does not meet this gate.

### 4. Restricted Staging Deployment and Evaluation

After separate deployment approval, back up the ledger and provisioning evidence, migrate
with schema-compatible rollback/restore instructions, and explicitly provision both operators
and their intended scopes. Do not infer ownership or adopt every historical item automatically.
Verify allowed/disallowed reachability, readiness, permission-aware readbacks, canonical
schedule canaries and continued local worker operation; observe resource use and retry behavior.
Use controlled fixtures or separately approved sends, not unsolicited delivery canaries.
Update generic operator guidance and report residual limitations. Browser UI design/build
and its visible unverified-identity warning remain a separate tracked follow-on, required
before calling the operator-facing web experience complete.

### Boundaries Preserved Throughout

Unsupported commands or unresolved ownership must fail, not imply full access.
Owner-only item transfer and admin/owner-approved member route use are ratified policy;
their full administration UI and future delivery-security machinery need not ship first.

Defer verified web sign-in, automated/WhatsApp-code recovery, executor tokens and
protected agent admission. Manual host-side account/binding repair is enough recovery
now. Retain the stronger specs for later qualification; do not make authentication-method
selection a blocker for the trusted web interface. The bounded logical audit is complete;
contract codification and executable verification remain delivery gates.

Keep the CLI as a direct trusted-local full-scope path for now. The web backend does
not shell out to it; both reuse command/services code. Mixed CLI/web/worker operation
needs concurrency and replay verification. Moving CLI behind a service is a separate
future enforcement choice, not a prerequisite for facets or accounts.
Existing trusted-local worker delivery continues without claiming per-user mandate
enforcement. Stronger audience/derivation decisions gate those deferred protected features.

Protected executor and OpenClaw qualification drafts remain future work. Preserve the
provisional inspection note without requiring new instrumentation or token machinery
for current trusted-local staging. No deployment or external audit is authorized
merely by this roadmap entry.
