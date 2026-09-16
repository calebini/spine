# Spine Backlog

Last updated: 2026-09-16

This is the single work queue for Spine development. The
[implementation plan](IMPLEMENTATION_PLAN.md) explains roadmap direction and delivery
history; [specs](../specs/README.md) and [contracts](../contracts/) remain authoritative
for behavior. An entry here does not accept a draft contract or authorize deployment.

## How to use this backlog

Focus on concrete items the operator brings to the backlog. Do not prescribe or
start gap analyses, general evidence reviews, or qualification campaigns unless the
operator requests them. Existing roadmap-derived entries are retained as candidates,
not selected work or automatic priorities. Dependencies and relevant verification
requirements still apply when a concrete task is selected.

- **Ready:** the stated task is bounded and can begin; this can be a preparation or
  design task without implying its eventual runtime feature is ready.
- **Needs decision:** scope or contract choices must be settled before implementation.
- **In progress:** record the responsible person or agent and current evidence here.
- **Blocked:** record the unmet dependency or external condition and how to clear it.
- **Done:** acceptance criteria are met and completion evidence is linked.
- **Deferred:** retained for later; no work or review is scheduled until the operator
  explicitly reactivates it.
- **Closed — withdrawn:** removed from planned work by the operator; does not claim
  implementation or verification was completed.

Keep each task's status in its entry, not in duplicate roadmap checklists. Keep IDs
stable when reordering. Split near-term initiatives into independently verifiable
outcomes; leave later horizons coarse. Before promoting a horizon, define its scope,
dependencies, acceptance criteria, and required decisions. When finishing a task,
record evidence and move it to Completed. Update affected orientation and contract
status labels in the same change. Routine task updates do not change spec authority.

## Next work

### SPINE-015 — Read authorized activities independently of unavailable linked resources

**Status:** In progress — selected by the operator on 2026-09-15. The supporting
draft, compatibility assessment, proposed test matrix and Kinflow handoff exist;
the approved ten-file bounded audit's one major and two minor findings have been
manually patched in Draft v0.2 and the Kinflow handoff, checkpointed at `354ed7e`.
Focused recheck 002 passed on 2026-09-16 against checkpoint `354ed7e`, with no findings.
The operator ratified the read design and authorized machine-contract codification
on 2026-09-16. That contract-only step is complete; implementation remains pending.
**Dependencies:** Existing trusted web
permissions, canonical recurrence/agenda and temporal-binding contracts. Read-design
ratification is complete; review the codified machine contract before runtime work.
This concrete item is independent of the withdrawn
SPINE-001–003 review tasks.

**Observed failure (operator report, not reproduced against staging):** A recurring
Science class has web ownership under `stage-whatsapp-group`. “Drive Callan to Science
class” follows one occurrence through an active `follow_source` binding, has Caleb
assigned, and has no web-access ownership. `schedule.show` of the authorized class
returns `resource_unavailable` because `bound_items` traverses the linked task.
Kinflow isolates the failed detail read and shows an explicitly incomplete calendar,
but the generic denial cannot safely identify the cause. Local code inspection
confirms this traversal also applies to `item.occurrences` and scoped agenda reads.

**Outcome:** Authorized event facts and canonical occurrences remain readable
independently of inaccessible followers. Related reads remain separately authorized;
public structured availability distinguishes usable activity facts from optional
context without revealing hidden resources or guessing temporal facts.

**Non-goals:** Runtime implementation, deployment, staging data changes, repairing
ownership, granting access from assignment, weakening cross-resource writes, client
recurrence calculation, or family-facing copy in Spine. Atomic provisioning of
intended ownership at task creation is a separate companion requirement; this item
must also handle legitimate access differences after correct creation.

**Acceptance:** The proposed IR-01–IR-16 matrix in the supporting spec covers:
authorized events with unowned or inaccessible followers; normally visible authorized
relations; disclosure-safe empty/incomplete context; generic direct denial; unavailable
task time without a fabricated deadline; epoch/version/pagination races; unchanged
cross-resource write protection; and Kinflow rendering from public canonical facts.
Before runtime delivery, review the codified schemas/registry/version and
consumer migration changes, and implement these behavioral oracles. Documentation
alone does not close the feature.

**Specification evidence:** [Independent activity reads](../specs/independent-activity-reads.md)
defines read boundaries, completeness, availability, consistency, compatibility,
and proposed contract tests. [Kinflow handoff](INDEPENDENT_READS_KINFLOW_HANDOFF.md)
defines consumer migration and rendering behavior. Local Markdown link and consistency
checks cover this specification delivery; no staging verification is claimed.

**Audit evidence and next step:**
`whetstone_runs/independent-activity-reads-contract-audit-001/audit-notes.md` lists
the ten-file reviewer inventory and focused consistency questions. The approved review
returned `needs_revision` on 2026-09-15 (0 blockers, 1 major, 2 minors, 0 nits).
Findings: scope singular expected-version guards to direct reads versus multi-item
agenda; distinguish selected account-subject identity binding revisions from temporal
binding revisions; clarify the v2 authoring-receipt projection's source/include semantics
without silently adding a v1 include option. Cited passages were checked locally.
Recommended manual choices: direct-read singular guards, agenda snapshot/cursor fencing;
explicit identity-binding terminology; independently specified v2 receipt evidence.
The operator-approved manual patch was completed on 2026-09-15 in Draft v0.2 and the
Kinflow handoff. Direct reads accept singular expected item/recurrence guards; agenda
rejects them and uses candidate-snapshot/cursor fences. V2 explicitly distinguishes
`account_subject_binding_revision` from `temporal_binding_revision_id`. The requested
v2 authoring-receipt singleton projects authorized creation evidence; absent and
undisclosable evidence both yield null, without adding v1 includes or creating receipts.
IR-11/12/14 now include matching future behavioral oracles. Seven documentation and
two implemented-declaration tests passed; `git diff --check` passed. No v1 schema,
runtime, canonical spec, or other-repository edits. The subsequent focused re-audit
passed; it does not ratify the complete contract or authorize runtime work.

Report, feedback, brief and manifest are retained under that root's `change_audit/`.
Invocation/manifest pin Sol, bundled CLI `0.154.0-alpha.6.2`, consistency and launcher
medium reasoning. Returned model-authored reviewer metadata says `gpt-5`, inconsistent
with the invocation/manifest; it is not independent model attestation. All ten raw
input hashes remained unchanged and all normalized manifest hashes matched.
`boundary_preserved=false` is the findings-based major verdict, not independent proof
of a runtime leak; no staging verification or convergence claim. No source specs,
runtime, shared defaults, commits or pushes changed during this audit.

Follow review with targeted clarification/ratification, then machine schemas,
registry/cursor and field-authority mappings plus IR-01–IR-16 fixtures before runtime.
The focused recheck inventory and questions are in
`whetstone_runs/independent-activity-reads-contract-audit-002/audit-notes.md`.
It used Sol and bundled CLI `0.154.0-alpha.6.2`, consistency profile and launcher
medium reasoning. Report: `pass`, zero blocker/major/minor/nit findings,
`boundary_preserved=true`, next action `none`. The three prior findings were not
raised again; empty feedback provides no per-finding explanation or exhaustive
coverage proof. All seven raw input hashes remained unchanged and normalized
manifest hashes matched; source specs matched checkpoint `354ed7e` before review.
Report, feedback, manifest and brief are under that root's `change_audit/`.
No source edits, Editor, runtime changes, commit or push occurred during recheck.
Nine documentation/declaration checks passed before checkpointing. Next selected
step remains contract ratification/codification, not a claim of runtime conformance.
Local pickup inspection reconfirmed the read-side `bound_items` calls and existing
connected-item checks; no runtime or source-spec change was made for preparation.

**Machine-contract delivery (2026-09-16):** Read design ratified as v1. The
[companion](../specs/independent-activity-read-contracts.md) and separate
`spine.trusted-web-read-registry.v1` codify two v2 command projections, agenda,
capability discovery, explicit temporal/section unions, field-authority mappings,
route-specific guards, authorized-only summaries and creation-receipt selection.
Eleven JSON schemas, independent schema/artifact pins, fixed-expiry cursor protocol,
five computed normalization vectors, one MAC vector and 53 schema fixtures are
provided. The IR-01–IR-16 behavioral matrix remains explicitly `runtime_pending`.
Offline semantic tests do not certify privacy, domain expansion, races or deployment.
No v1 contract/pin, runtime module, installed registry or packaged capability changed.
Verification: 73 tests and 202 subtests passed across the new offline contracts,
existing trusted-web contracts/runtime, implemented declarations, agent documentation,
and recurrence/schedule-operation/temporal-binding fixtures. Ruff, Markdown file-target
checks and `git diff --check` passed. These are local checks, not staging or a new audit.
Next step: bounded machine-contract audit, then separately authorized implementation
and Kinflow migration. No audit, commit or push was performed in this delivery.

## Roadmap candidates — not selected work

These retained entries require operator selection. They do not schedule a gap analysis.

### SPINE-008 — Close the focused facet machine-contract recheck

**Status:** Ready. **Dependencies:** None for the focused contract review.

**Acceptance:** Recheck the manually patched replay-response alignment and
test-dependency scope findings against the current facet bundle; retain the result and
resolve any resulting concrete findings. Update the facet draft's recheck status
without representing static fixtures as runtime proof. This task does not start an
additional broad audit campaign or authorize facet implementation.

**Sources:** [Facet draft and machine-contract status](../specs/archetype-facets.md),
[facet roadmap](IMPLEMENTATION_PLAN.md#future-horizon-archetype-facets-and-workflow-recipes).

### SPINE-009 — Settle facet implementation gates

**Status:** Needs decision. **Dependencies:** SPINE-008 and the facet-specific
contract gates below. The deferred resilience campaign is not a blanket prerequisite.

**Acceptance:** Resolve Decision 0004, migration/index design, permission resolver
mappings, authenticated cursor semantics, and exact notification-work freshness on
facet-only item edits. Add the required contracts and behavioral oracles, then create
bounded implementation tasks for the flight-details proof. Keep workflow recipes and
external observations separate; do not advertise runtime facets from draft schemas.

**Sources:** [Facet gates](../specs/archetype-facets.md),
[Decision 0004](../specs/decisions/0004-versioned-item-facets.md).

## Later horizons

These entries preserve roadmap intent. Their acceptance criteria describe the next
planning outcome; each needs decomposition before executable work is selected.

### SPINE-011 — Prepare notification-activated contextual advisories

The narrow protection-amendment drafting task is completed separately as SPINE-017.
Its proposed decision and manual checklist do not close this horizon's remaining
native mapping, machine-contract, or implementation decisions.

**Status:** Needs decision. **Dependencies:** Confirm the roadmap's Version 1 pack
publication/proof prerequisite with its owning component before the advisory delivery
slice. The deferred resilience campaign is not a blanket prerequisite; the advisory
contract's own bounds and acceptance requirements still apply.

**Acceptance:** Review the current activation/fallback direction and settle immutable
definitions, privacy/context bounds, configurable budgets, silence permission,
selection/recovery races, evidence ownership, and cross-system contracts. Define
timing/race/replay fixtures and a bounded read-only proof routed through ordinary
notification delivery. Split contract and runtime work only after those choices are
settled; record the external pack dependency rather than assuming it is complete.

**Sources:** [Current advisory draft](../specs/contextual-advisories.md),
[autonomy exploration](design-notes/scheduled-agent-autonomy.md),
[advisory roadmap](IMPLEMENTATION_PLAN.md#future-horizon-notification-activated-contextual-advisories).

### SPINE-012 — Define workflow recipes and external observations

**Status:** Needs decision. **Dependencies:** SPINE-009 for canonical facet integration;
explicit external runner and pack ownership.

**Acceptance:** Separate volatile provenance/expiry-bearing observations from canonical
facets; define declarative recipe versions, deterministic plan/apply/verify behavior,
owner activation preferences, and authorization boundaries. Produce separate bounded
tasks for observations and recipes before implementation.

**Source:** [Facets and recipes horizon](IMPLEMENTATION_PLAN.md#future-horizon-archetype-facets-and-workflow-recipes).

### SPINE-013 — Select the next protected identity and admission slice

**Status:** Needs decision. **Dependencies:** A selected product need and enforcement
scope beyond the trusted web delivery.

**Acceptance:** Choose and bound the next protected feature, such as verified web
sign-in, recovery, protected executor/chat admission, or delivery mandates. Reconcile
its preserved draft, cross-component ownership, and qualification oracles before
creating implementation tasks. These features do not gate the current trusted GUI.

**Sources:** [Identity architecture](../specs/identity-and-access.md),
[enforcement draft](../specs/permission-enforcement-and-web-admission.md),
[OpenClaw admission](../specs/openclaw-admission.md).

### SPINE-014 — Triage the remaining deferred roadmap ideas

**Status:** Needs decision. **Dependencies:** An explicit selected use case.

**Acceptance:** When calendar/vendor projections, broader dashboards, governance
integration, or freeze-manifest promotion become a priority, create a bounded task
with component ownership, dependencies, and acceptance evidence. Preserve Tickerd's
runtime ownership and structured canonical ingest; those boundaries are not features
to implement in Spine.

**Source:** [Deferred roadmap](IMPLEMENTATION_PLAN.md#deferred-beyond-this-delivery).

## Deferred resilience, containment, and storage work

Deferred on 2026-09-13 at the operator's request. The operator is satisfied with the
resilience and containment achieved when the event-emission issues were fixed.
SPINE-004–007 and the related storage-lifecycle horizon SPINE-010 are retained for
later, with no assessment, implementation, or qualification work scheduled. Reactivate
only on explicit operator request. This changes work priority, not implemented safety
behavior or the verification required for a separately selected concrete change.

### SPINE-004 — Reconcile and finish the remaining containment slice

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** Operator selection of a concrete containment
task; any gap assessment requires an explicit request. Resolve relevant draft
requirements before implementing uncovered behavior.

**Acceptance if reactivated:** Map current code and tests to the resilience containment requirements,
credit already implemented Tickerd admission, event bounds, storage stops, and durability
latching, and identify exact remaining work. Confirm the status of retry-budget
validation, the transitional dry-run ceiling, and storage readback; define bounded
implementation tasks and their failure oracles. Close those tasks with matching tests
and declarations before marking this item done.

**Sources:** [Resilience spec](../specs/operational-resilience.md),
[compatibility](../specs/compatibility.md),
[resilience roadmap](IMPLEMENTATION_PLAN.md#next-initiative-operational-resilience-and-boundedness).

### SPINE-005 — Specify and implement bounded failure recovery

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 for delivery ordering;
accepted recovery semantics before runtime work.

**Acceptance if reactivated:** Settle poison-item isolation, bounded backoff/circuit breaking and
retry exhaustion, in-progress lease recovery, and ambiguous external outcomes. Add
the required decision, ontology/migration changes, readback, and operator workflow;
split implementation into bounded tasks with crash/replay/failure tests. Preserve
durable attempt evidence and prove recovery does not silently duplicate effects.

**Source:** [Resilience spec](../specs/operational-resilience.md).

### SPINE-006 — Deliver bounded traversal and continuation

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 and SPINE-005 for delivery
ordering; settle traversal and budget contracts before runtime work.

**Acceptance if reactivated:** Specify and implement fair keyset traversal for automatic discovery,
continuation-complete notification materialization, bounded agenda/readback, and core
request/text/collection/expansion budgets. Split by executable boundary and retain
large-ledger, continuation, fairness, and overflow evidence.

**Source:** [Resilience spec](../specs/operational-resilience.md).

### SPINE-007 — Qualify operational resilience

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004–006.

**Acceptance if reactivated:** Run the required idle, persistent backlog, provider outage, crash,
timezone-data, WAL, disk-pressure, and large-ledger campaigns against exact release
versions. Record bounded resource behavior, recovery outcomes, and remaining gaps;
claim conformance only for requirements exercised by retained evidence.

**Source:** [Resilience qualification requirements](../specs/operational-resilience.md).

### SPINE-010 — Establish the ledger storage lifecycle

**Status:** Deferred (2026-09-13, operator direction). **Dependencies if reactivated:** SPINE-004 storage readback; post-fix
staging growth evidence before choosing retention behavior.

**Acceptance if reactivated:** Establish a measured growth baseline; classify durable fact families;
settle replay retention; specify verified archival/compaction, manifests, restore,
budgets, and stop conditions. Create bounded delivery tasks. Storage pressure alone
never authorizes deletion of canonical evidence.

**Source:** [Storage lifecycle horizon](IMPLEMENTATION_PLAN.md#future-horizon-bounded-ledger-storage-lifecycle).

## Completed

### SPINE-024 — Seed the Impetus HLD from the shared architecture

**Status:** Done (2026-09-15; proposed HLD drafting, not audited or implemented).
**Dependencies:** Shared checkpoint `082dc7f`, SPINE-019–023.
**Outcome:** Wrote `../impetus/specs/architecture.md`, `0.1.0-draft.1`, directly
in the operator-selected repository. It references shared architecture
`cortext.cross-system-execution` at exact Spine commit
`082dc7fbed4895d93314d0d331ea3874c74dc640`. It defines execution/controller/backend/
capability boundaries, native evidence and governance ownership, limits and uncertain
call recovery, source-freshness and advisory preservation, and future-profile boundaries.
Provider/backend, transport, native mappings, storage and numeric budgets remain open.

**Handoff:** Updated Impetus overview and README and added the HLD to its existing
scaffold verifier's required files. Preserved the otherwise uncommitted seed scaffold;
no runtime folders or machine-contract placeholders were created. The Impetus project
thread can refine/review the HLD and select the bounded first-slice choices before
machine contracts. No automatic adoption or runtime compatibility is claimed.

**Verification:** Impetus `python3 scripts/verify_repo.py` passed (structure/local
links/template checks only). New/edited Impetus files have no trailing whitespace;
all five pinned Spine source paths exist at the stated local commit. Remote availability
was not tested or implied. Spine `git diff --check` passed. No nested audit, external
execution, deployment, commit or push; Spine source specifications were unchanged.

### SPINE-023 — Focused re-audit of advisory authority/freshness clarifications

**Status:** Done (2026-09-15, reviewer-only focused recheck).
**Dependencies:** SPINE-021 findings and SPINE-022 manual patch.
**Outcome:** `cross-system-execution-contract-audit-003` returned `pass`, zero
blocker/major/minor/nit findings, `boundary_preserved=true`, next action `none`.
The two prior findings were not raised again; the manual patch addresses their
specific passages. Empty feedback supplies no per-finding closure explanation or
exhaustive coverage proof. This is bounded consistency evidence, not convergence,
cross-repo adoption or runtime-readiness certification.

**Evidence:** Local ignored artifacts under
`whetstone_runs/cross-system-execution-contract-audit-003/change_audit/` include
the report, feedback, manifest and brief. Explicit invocation and manifest pin
`gpt-5.6-sol`, bundled CLI `0.154.0-alpha.6.2`, profile `consistency`; launcher
reasoning remains `medium`. Returned model metadata also identifies Sol this time.
All four raw hashes remained unchanged and all four normalized manifest hashes
matched; `git diff --check` passed. No source spec edits, Editor, additional model
calls, shared-default changes, commit or push were performed.

### SPINE-022 — Clarify advisory consumption and staged freshness checks

**Status:** Done (2026-09-15, manual specification patch; subsequent re-audit passed in SPINE-023).
**Dependencies:** Operator-approved findings from SPINE-021 retry 002.
**Outcome:** [Contextual advisories](../specs/contextual-advisories.md) Draft v0.3.4
reserves native evidence acceptance for governance; Spine refuses local consumption
when stale. Initial stale work creates/sends no submission; a later failed dispatch
recheck preserves the immutable submission/native references and blocks execution.
Replay resolves that preserved state without new execution or snapshot replacement,
including an incomplete native handoff. Lifecycle, failure distinctions and future
fixture obligations align with those rules; exact native mappings remain deferred.

**Verification:** 7 agent-documentation tests and 2 implemented-contract-declaration
tests passed; `git diff --check` passed. Acceptance-reference §7.5, fallback/branch
selection §8.1, explicit recovery §8.2 and idempotency/attempt accounting §10 remained
byte-identical to their pre-patch contents. README still routes to the authoritative
spec index. Only the advisory source spec and this tracker were edited for this task;
earlier uncommitted work was preserved. No runtime, machine-contract, other-repository,
editor workflow, nested audit, commit or push changes.

### SPINE-021 — Bounded audit of the shared execution architecture

**Status:** Done (2026-09-15, reviewer-only audit; findings patched in SPINE-022 and rechecked in SPINE-023).
**Dependencies:** SPINE-020 draft; no downstream adoption or runtime implementation implied.

**Outcome:** Retry 002 completed with `needs_revision`: 0 blockers, 2 majors,
0 minors, 0 nits. Both findings are in `specs/contextual-advisories.md`:
`fb_acceptance_consumption_terms` separates governance evidence acceptance from
Spine consumption/freshness checks (§3 invariant 7 and §9);
`fb_freshness_submission_sequence` separates initial pre-submission refusal from
post-submission dispatch prevention, preserving immutable submission/replay evidence (§§8–9).
The cited passages were checked locally. No source-spec patch was made.

**Evidence:** `whetstone_runs/cross-system-execution-contract-audit-002/change_audit/`
contains the report, feedback, brief and manifest (local ignored artifacts).
Invocation and manifest pin `gpt-5.6-sol`, bundled CLI `0.154.0-alpha.6.2`,
consistency profile and launcher reasoning `medium`. The feedback's model-authored
reviewer metadata incorrectly says `gpt-5`; it is inconsistent with the explicit
invocation/manifest and is not independent model attestation.

**Verification and limits:** All ten raw input hashes remained unchanged and all ten
normalized manifest hashes matched. `git diff --check` passed. Report
`boundary_preserved=false` follows the major-finding verdict; this is not an
independent preservation/coverage test or a convergence claim. No Editor, native
repository source expansion, shared default change, commit or push occurred.
Attempt 001 is retained separately as `audit_failed`: CLI `0.142.0` was rejected
before semantic review. No installation upgrade was needed for retry 002.

### SPINE-020 — Draft the versioned shared execution architecture

**Status:** Done (2026-09-15, Codex; proposed specification drafting only).
**Dependencies:** SPINE-017–019 protection and native-handoff findings.

**Outcome:** Added [Cross-System Execution Architecture](../specs/cross-system-execution.md),
ID `cortext.cross-system-execution`, document version `0.1.0-draft.1`. It separates
coordination, governance, execution, capabilities and result consumption, with explicit
budget/evidence/freshness and retry boundaries. Downstream exact references identify
the version, source repository/path and containing Git commit; design reference,
adoption and runtime conformance remain distinct. Checkpointed revisions are immutable;
further drafts increment the draft revision. No freeze manifest or hash gate was added.

**Preservation:** Added links in orientation, architecture and advisory specs and
recorded the Impetus handoff sequence in the roadmap. Original architecture/advisory
body lines remain verbatim and in order; only declared status/date headers changed.
The full advisory profile remains authoritative for its required behavior. No other
repository, runtime, machine schema, registry, package version or migration changed.
The separate native-handoff report from SPINE-019 is included in the same checkpoint.

**Verification:** Seven agent-documentation tests and two implemented-contract
declaration tests passed; 87 local links resolved, whitespace and diff checks passed.
These checks do not establish semantic preservation or cross-system conformance.
At drafting completion the shared document was not yet audited; see SPINE-021–023
for the subsequent audit, patch and passing focused recheck. It remains proposed,
not ratified. Other components have not
adopted it; exact downstream checkpoint references can be made after its commit exists.
The Impetus HLD, native contracts, backend selection and runtime work remain separate.

### SPINE-019 — Investigate native advisory execution handoff

**Status:** Done (2026-09-15, Codex; operator-selected investigation).
**Dependencies:** Protection amendment and bounded review, SPINE-017–018.

**Outcome:** The [native handoff investigation](design-notes/advisory-native-handoff-investigation.md)
maps Spine's first advisory profile to native drafts, actual code and focused tests.
Intent admission, pinned policy, evidence persistence, approvals and replay are real;
the current dispatch path records local success without research execution. Native
scoped authorization, a bounded runner, advisory evidence validation and Spine freshness
handoff still need contract/runtime work. A field-only adapter cannot close that gap.
The note recommends a bounded native execution extension paired with the Spine bridge,
not completion of a general workflow platform. Runner and transport choices remain open.

**Evidence:** Spine base `560ecc4`, native base `8afa61f`; 55 focused native tests
passed using temporary databases, covering runtime API, evidence, replay, arbitration
and intake. All 19 report links and diff hygiene passed. Native pre-existing dirty
files remained untouched. No normative specifications, runtime code, deployments,
provider calls, or audits changed. This is not native full-spec or live integration
qualification; see the report's evidence boundary and declared Tickerd-version mismatch.

### SPINE-018 — Bounded review of the advisory protection amendment

**Status:** Done — reviewer-only audit completed on 2026-09-14 (Codex); the operator-
authorized minor wording clarification was applied on 2026-09-15.
**Dependencies:** SPINE-017 draft and explicit approval of the eleven-file inventory.

**Outcome:** `pass_with_minor_clarification`: zero blockers, zero majors, one minor,
zero nits. Finding `fb_0001` identifies the ambiguous architecture §9.1 phrase
“general workflow support does not.” Recommendation: explicitly say that general
workflow support remains outside this slice and is not a prerequisite for advisory v1.
No source specs were patched during the audit; no Editor, convergence, or
implementation run occurred.

**Manual follow-up:** Addressed `fb_0001` in architecture §9.1 using the recommended
wording, consistent with Decision 0005 and contextual advisories §15. This is a
specification-only clarification, not new workflow capability. The original audit
artifacts remain unchanged and describe the pre-patch inputs; no re-audit is claimed.
Verification: all seven agent-documentation tests and `git diff --check` passed;
README links still point to the authoritative spec index and architecture document.

**Evidence:** Local ignored run `whetstone_runs/advisory-protection-contract-audit-001/`:
`change_audit/change_audit_feedback.json`, `change_audit/change_audit_report.json`,
and `input-verification.md`. All eleven inputs retained their pre-run hashes and
match the manifest; all three baseline copies match git objects at `706b499`.
Feedback and report bind to the generated audit brief hash. The approved review
compared the baseline with candidate `6077bf3`, using P-01–P-20 and E-01–E-06.

**Limit:** Whetstone reports `boundary_preserved=true`, derived from severity counts,
not independent objective assessments. The report does not establish complete
checklist coverage, semantic equivalence, convergence, decision ratification, or
advisory implementation readiness. Its objective-assessment enhancement remains
unimplemented. Further manual changes or review runs require operator authorization.

### SPINE-017 — Draft the advisory architectural protection amendment

**Status:** Done (2026-09-13, Codex; specification drafting only, selected by the operator).
**Dependencies:** Existing advisory draft and the completed three-case extensibility
analysis; no outstanding product decision blocked this narrow amendment.

**Outcome:** Added proposed [Decision 0005](../specs/decisions/0005-profile-scoped-advisory-execution.md),
additive advisory/architecture/ontology clarifications, and the baseline-bound
[preservation checklist](design-notes/advisory-protection-preservation-checklist.md).
The amendment separates advisory-specific requirements from future execution scope,
dependencies, native run/evidence, and result-consumption boundaries. It adds no
general automation support and leaves the broader SPINE-011 horizon unselected.

**Preservation evidence:** Against baseline `706b499665add9e15a041f2c26dd20c2446f5139`,
all original body lines of the three amended specs remain verbatim and in order;
only the advisory status line changes. P-01–P-20 record manual obligation correspondence
and E-01–E-06 identify future review objectives. No runtime, machine schema, migration,
fixture, package version, registry, native governance spec, or deferred initiative was
changed. Local link and diff-hygiene checks passed. Relevant unittest suites passed:
agent documentation (7), implemented contract declarations (2), and notification
rendering fixtures (3). HEAD and index stayed unchanged.

**Limit:** Manual comparison and tests are not independent semantic preservation proof.
Decision ratification and a later approved bounded reviewer audit remain separate;
no audit was run and no advisory implementation-readiness claim is made.

### SPINE-000 — Establish work tracking and reconcile orientation

**Status:** Done (2026-09-13). **Dependencies:** None.

**Outcome and evidence:** Added this ordered backlog with stable IDs, statuses,
dependencies, and acceptance criteria. Linked it from the
[README](../README.md), [agent instructions](../AGENTS.md), and
[implementation plan](IMPLEMENTATION_PLAN.md); separated live task status from roadmap
snapshots. Reconciled the seed-spec label, README schema boundary, and specs index's
web implementation label against [package metadata](../pyproject.toml),
[ledger identity](../specs/ledger-instance-identity.md), and
[web implementation status](../specs/trusted-multi-operator-web-api.md).
Documentation links and diff whitespace were checked; runtime behavior is unchanged.

Earlier delivered slices remain in the implementation plan's delivery history;
they are not recreated as retrospective tasks here.

## Closed — withdrawn

### SPINE-001 — Reconcile existing web staging evidence and remaining gaps

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request. This assistant-created evidence
review was not tied to a confirmed defect. The frontend and staging deployment already
exist; no gap analysis is requested. No qualification or verification completion is
claimed. SPINE-015 separately tracks the reported linked-resource read failure.

### SPINE-002 — Close evidenced gaps in the existing staging setup

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request with SPINE-001. No specific remaining
staging work had been established for this placeholder. This closure neither schedules
new staging checks nor claims all possible deployment checks have passed.

### SPINE-003 — Reconcile existing Kinflow frontend coverage and follow-ons

**Status:** Closed — withdrawn (2026-09-13). **Dependencies:** None; no follow-up required.

**Closure:** Withdrawn at the operator's request. Kinflow's connected frontend is
already under operator testing; no general frontend gap analysis is requested.
Future work will follow concrete operator-supplied items, not this broad review.

## Completed — cloud validation repair

### SPINE-016 — Reconcile clean cloud validation findings

**Status:** Done (2026-09-13, Codex). **Dependencies:** None.

**Scope:** Restore the five packaged archetype-facet schema copies through the
existing synchronization script and enforce its check in CI; repair strict core/ledger
typing without semantic changes; correct the trusted-web test helper import for both
pytest and documented unittest discovery. Keep unrelated specification work intact.

**Confirmed locally:** The sync check reports exactly five missing copies; strict
mypy reports 26 errors in notification rendering and ledger transactions; pytest
collection fails on the top-level `test_schedule_create_command` import.

**Acceptance:** Complete documented unittest discovery, pytest, repository-wide Ruff,
strict core/ledger mypy, compileall with bytecode outside the repository, and the
packaged-contract sync check. Preserve pre-existing local work; no deployment, real
ledger access, runtime internet changes, commits, or pushes.

**Outcome and evidence:** Regenerated only the five missing packaged schemas with
[sync_web_contracts.py](../scripts/sync_web_contracts.py); added its `--check` invocation
to [CI](../.github/workflows/ci.yml). Corrected renderer non-returning validation and
timezone annotations, and matched the SQLite context-manager type signature; executable
logic and public contract versions are unchanged. The web test now imports its helper
through the existing `tests` package. Added renderer rejection cases and isolated
in-memory transaction commit/rollback/exception tests.

Verified with the existing virtual environment (Python 3.14.6, mypy 2.3.0, Ruff 0.16.2,
pytest 9.1.1): `python -m unittest discover -s tests` ran 492 tests in 20.474s, OK;
`pytest -q` completed successfully with 492 passing test result markers;
`ruff check .` passed; `mypy --strict src/spine/core src/spine/ledger` reported no
issues in 35 source files; `python -m compileall -q src tests examples` passed with
`PYTHONPYCACHEPREFIX` in a cleaned temporary directory and repository bytecode unchanged;
`python scripts/sync_web_contracts.py --check` and `git diff --check` passed. Unittest
remains the documented and CI validation path. CI's Python 3.12 job was not run remotely.

The final preservation check confirms HEAD/index unchanged, all ten other pre-existing
modified/untracked files byte-for-byte intact, and the entire prior backlog preserved
before this separately appended entry. No out-of-scope work was performed.
