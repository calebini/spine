# Spine Backlog

Last updated: 2026-10-05

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

## Rendering delivery — implementation sequence

The operator approved implementation planning and then SPINE-051 implementation on
2026-10-05. SPINE-051 has an implemented internal checkpoint; later slices remain unstarted. These three internal checkpoints
deliver one cohesive backend release; there is no intermediate staging deployment.
Specs/contracts retain authority. Slice A has executable evidence below; complete
RI-01–RI-14 release qualification remains pending the delivery/readback slices.
The [implementation plan](IMPLEMENTATION_PLAN.md#planned-delivery-facet-aware-notification-rendering-spine-051053)
owns sequencing rationale and the proof allocation. Do not activate successor command
families, the integration capability or production migration until all three slices
and end-to-end verification are complete. New HTTP exposure and pack adoption stay separate.

### SPINE-051 — Rendering persistence and authoring foundation

**Status:** Implemented — internal candidate checkpoint, 2026-10-05; public activation remains off.
**Dependencies:** SPINE-038 schema-18 location protection; SPINE-049 ratified design;
SPINE-050 bounded review and locally verified fixture correction (`da128c5`).
**Scope:** Integration Sections 2–5, 7–9 and 11: candidate migration/fresh schema,
canonical storage/reference indexes/guards, historical ordinary backfill, all-policy-
writer inventory/finalization, shared exact-descendant resolver, definition/disclosure
catalog commands and permission/cursor rules, profile/schedule/direct-reminder
successor authoring, and original application evidence. Preserve replay/no-op/dry-run,
old decoders and old-request loss guards. Fresh local creation stays ordinary-only;
selected detail requires explicit ownership adoption and a later presentation edit.
**Acceptance:** Implement disposable-ledger proofs for RI-02/04/11/13 and the A portions
of RI-01/03/05/10/12. Demonstrate all writers copy valid supporting facts, atomic
rollback includes materialization/audit/receipts, read paths meet declared bounds,
and candidate migrations preserve history and fail without partial activation.
Test exact/ambiguous grants, role denials, profile duplicate semantics and all corrected
wire limits/evidence. Record concrete test mappings; unexecuted RI cases stay pending.
**Boundary:** No live ledger, deployment, adapter sends or public activation. Candidate
migrations/handlers are exercised internally. Do not add an owner input, implicit
adoption, scheduler hold, broader protected-location rights or schema number in this plan.
**Handoff:** Slice B receives working storage, authoring, writer/ancestry services and
their tests, not merely schema files. Actual schema/version assignment is coordinated
with final release activation, after checking the then-current migration baseline.
**Evidence:** Candidate DDL, an atomic schema-18 installer, compiled object-fingerprint
manifest and writer inventory; immutable catalog/profile/presentation decoding;
transaction-owned finalization over allocator- and SQL-tracked writes; private shared
profile/schedule/direct-reminder authoring hooks and catalog/admission/cursor handlers.
`tests/test_rendering_authoring_foundation.py` exercises catalog replay/no-op/dry-run,
computed v2 hash oracles, cursor/query bounds, missing support and interrupted migration.
`tests/test_rendering_successor_authoring.py` exercises profile pins, v1 loss guards,
ordinary creation → explicit adoption → presentation edit, exact/ambiguous disclosure,
application provenance, direct v2 edits, work preservation and rollback (RI-02/04 and
authoring portions of RI-03/05). `tests/test_rendering_permissions.py` covers roles,
spoofed actors, private catalog visibility, protected-location denial, cursor identity,
expiry and key rotation (authoring RI-10/11). `tests/test_rendering_storage_integrity.py`
executes all existing producer paths and shared-intent copy chains, validates manifests,
checks the fresh read-release fence, and preserves populated v1 profile/attempt bytes
(RI-13 and A portions of RI-01/05/12). Delivery races, operational exclusion, complete
restore/old-worker release checks and readback/activation remain assigned to B/C.
**Packaging note:** Candidate DDL is outside numbered migrations; package-data patterns
include it and both inventories. Local wheel building could not run because the
available Python environments lack `setuptools`; installed-wheel qualification remains
a release-checkpoint requirement, not a claim of completed packaging verification.
**Verification:** Full unittest discovery passed 894 tests; a subsequently added
candidate-storage run of the eight existing profile regressions also passed. Focused
candidate tests, Ruff, compileall, changed-document local links and diff hygiene pass.
No commit, push, deployment or live-ledger change was performed.

### SPINE-052 — Integrate facet details into notification attempts

**Status:** Ready — SPINE-051 internal checkpoint implemented; not started.
**Dependencies:** Complete candidate persistence/authoring and shared ancestry services.
**Scope:** Integration Sections 4/6 and attempt-time Section 7 rules: scheduler/worker
current-policy resolution, unchanged work/lease/retry/provider identity, deterministic
scalar/location-label suffixes, current facet/disclosure/access checks, ordinary fallback
and omission privacy, one immutable v2 rendering committed with its existing attempt.
Exercise recurring/follow-source and shared-intent cases, stored replay versus a fresh
retry, and edit/revoke/ownership/route races. Preserve v1 ordinary bytes and no-idle-write
behavior. Evidence corruption/size errors fail before adapter invocation.
**Acceptance:** Execute RI-06/07/08/09, complete delivery portions of RI-01/03/05/10,
and preserve Slice A regressions. Cover queued, leased, retry, started, terminal,
independently stale and absent work; prove presentation-only edits neither materialize
nor resend. Prove strict setup with verified operational exclusion and the possible
ordinary send between setup steps without it. Use deterministic adapters and fault
injection, no real recipients. Map evidence to each required oracle.
**Boundary:** No new send ledger, new provider identity, automatic service controls,
grace extension, advisory runtime or public activation.
**Handoff:** Slice C receives the tested authoring-to-attempt flow, including fallback,
replay, concurrency and failure-path evidence; readback/release gates remain outstanding.

### SPINE-053 — Complete rendering readback and release verification

**Status:** Blocked — depends on SPINE-051 and SPINE-052; not started.
**Dependencies:** End-to-end candidate storage, authoring and delivery behavior.
**Scope:** Schedule-show v2 and successor response/receipt projections; exact historical
v1/v2 decoding; safe old summary/redaction behavior; CLI discovery/help; generic operator
guidance with progressive disclosure; complete release proof and activation packaging.
Keep current compact/web families unchanged. Document explicit ownership/adoption,
definition/disclosure/presentation setup, retirement versus revocation, fallback versus
failure, and strict setup's external materializer-exclusion requirement.
**Acceptance:** Execute RI-14 and release RI-12 checks, rerun every RI-01–RI-14 family
together with focused/full regression suites, and record tests, results and any skipped
or blocked proof. Verify fresh/populated migration, all-writer coverage, concurrency,
paired backup/code rollback, old-worker refusal, exact capability/schema pins, bounded
preflight and installed package resources. Only then activate matching local command
families, integration capability and migration/runtime manifest as one coherent release.
**Boundary:** Planning/implementation completion does not authorize deployment, external
sends or new HTTP registry exposure. No fields added to frozen web schemas; a broader
web contract and pack installer support require separate work and approval.
**Handoff:** A version-pinned staging deployment prompt with backup, all-writer shutdown,
deliberate protected cursor configuration, health/readback checks, controlled canaries,
and restore instructions that retain the newer ledger. No live execution in this task.

## Rendering design and review history

### SPINE-050 — Review rendering integration successor machine contracts

**Status:** Done — bounded review and manual fixture correction complete (2026-10-05).
Corrected bytes locally verified and committed; not re-audited.
**Dependencies:** SPINE-049 ratification and source-only contract codification.
**Scope:** One reviewer-only Whetstone audit-change with the built-in consistency
profile and GPT-6.1 Sol. Review successor schema/spec agreement, version/decoder
boundaries, computed evidence, cursor/config semantics, fixture coverage and exclusion
from runtime/web activation. Existing dependencies are read-only comparison context.
**Package:** [Audit notes](../whetstone_runs/notification-rendering-integration-machine-contract-audit-001/audit-notes.md)
enumerate 103 source/context files plus the notes. Local prepared-inputs.json pins the
current uncommitted source bytes and HEAD; no commit is implied by staging.
**Acceptance:** Verify exact model/profile/inventory, review findings and boundary
verdict, and prove source hashes unchanged. Known RI runtime obligations remain pending.
**Evidence:** One consistency audit with GPT-6.1 Sol returned `needs_revision`:
0 blocker, 3 major, 2 minor; `boundary_preserved=false` because the successor
application/readback projection drops required existing selection/composition evidence.
Other findings: profile-list request/response caps disagree (500 versus 100),
schedule-create failure schemas disagree, schedule-update dry-run marker is too broad,
and overflow-vector candidate inputs are disconnected from its omission decision.
[Report](../whetstone_runs/notification-rendering-integration-machine-contract-audit-001/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/notification-rendering-integration-machine-contract-audit-001/change_audit/change_audit_feedback.json).
At audit completion all 103 source hashes and approved notes remained unchanged;
manifest inventory, model/profile and report-to-brief hash verified. The original
audit artifacts remain immutable evidence of the pre-patch package.
**Manual correction:** Accepted all five findings. Restored the 500-entry profile-list
response cap, required application scope-chain/revision-hash/overlay evidence (also
embedded in readback), reused the shared schedule-create failure schema, restricted
schedule-update dry_run to optional true, and derived overflow suffix/outcomes from
explicit normalized candidate selections before stripping private values/sources.
Added default-profile overlay/readback, permission-denied and limit-101 fixtures;
tests cover 100/101/500/501 page limits, missing evidence, all shared failure codes,
success dry-run markers, and overflow versus fitting suffixes/preserved omissions.
Section 11 states the preserved evidence and wire domains; no product scope change.
**Verification:** 183 contract tests and 1,139 subtests passed; Ruff, web-contract
sync --check, 154 local Markdown links and git diff --check passed. All 20 existing
schema dependency/comparison files in the audited package remain byte-identical.
Runtime source, schema activation and pending RI-01–RI-14 obligations are unchanged.
**Checkpoint:** `78fc71a` commits the ratified successor contracts, fixtures and five
manual corrections. Rechecked 183 tests/1,139 subtests, Ruff, web sync and diff hygiene.
**Recheck package:** [Audit-002 notes](../whetstone_runs/notification-rendering-integration-machine-contract-audit-002/audit-notes.md)
enumerate 62 files plus notes, built-in consistency context and generated copies for
GPT-6.1 Sol. Scope: closure of the five findings and directly introduced regressions;
selected fixture family and its schema dependencies, not a new full-package audit.
Local preparation metadata pins the committed inputs. The operator explicitly
approved the 62-file package, notes, built-in context and generated copies on 2026-10-05.
**Recheck outcome:** Audit-002 returned `pass_with_minor_clarification`, zero
blockers/majors, one minor, `boundary_preserved=true`. Prior audit-001 findings
were not reissued; the sole new finding is an inadmissible overlay fixture revision:
the suppressed and day-before templates have identical ordinary scheduling semantics,
contrary to the preserved duplicate-policy prohibition. Give the suppressed template
distinct timing, recompute its hashes/fixtures, and assert semantic uniqueness.
[Recheck report](../whetstone_runs/notification-rendering-integration-machine-contract-audit-002/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/notification-rendering-integration-machine-contract-audit-002/change_audit/change_audit_feedback.json).
Verified exact 62-file inventory, source/notes hashes unchanged, GPT-6.1 Sol/consistency,
and report-to-brief binding. No Editor or automatic correction/rerun.
**Minor correction:** The operator authorized the fixture-only fix. The suppressed
template now uses elapsed offset -172800 (48 hours), distinct from day_before's
-86400 (24 hours). Regenerated the selected revision, application/readback pins and
computed vectors. A focused regression strips rendering/derived fields, validates
ordinary profile semantics through the existing normalizer, checks distinct timings,
and proves deliberately duplicated timing fails even with different template keys.
**Verification:** 22 focused tests/149 subtests and 184 broader contract tests/1,139
subtests passed; exact fixture regeneration, Ruff, web-contract sync --check and
git diff --check passed. Source specs, schemas and runtime are unchanged. Prior audit
artifacts and existing tracking changes were preserved. The fixture correction and
audit closeout are committed in `da128c5`; no new audit or push was performed.
**Next:** SPINE-051–053 allocate implementation and remaining stateful proofs. No
further routine audit is scheduled for the fixture-only residual. Runtime work remains
separately authorized; no convergence or post-patch external-review claim.
**Boundary:** The operator approved the exact 103-file package for the completed
review and subsequently authorized targeted manual fixes and checkpoint. No runtime
implementation, SQL migration, Editor/convergence, push or deployment.

### SPINE-049 — Ratify rendering integration and codify successors

**Status:** Done — ratified and source-only successor contracts codified on 2026-10-04.
**Dependencies:** SPINE-048 clean bounded buildability recheck; logical rendering family.
**Scope:** Ratify the reviewed integration design; add source-only successor wire,
cursor/config schemas, registry and computed reference fixtures with contract tests.
Preserve all deployed contracts, historical decoders and pending runtime obligations.
**Acceptance:** Closed schema validation, independently recomputed hashes/cursor vectors,
negative fixtures, source-only packaging/activation guards, links and diff hygiene.
No runtime feature implementation, SQL migration, Whetstone run, commit or push.

**Outcome:** Integration v1.0 accepted after SPINE-048; logical and persistence owners
unchanged. Added 18 successor schemas, an exact source-only registry and fixture
manifest, 44 positive/negative wire examples, 34 computed canonical-hash vectors,
two signed cursor vectors, and an independently checked overflow example. V1
historical profile decoding and ordinary rendering remain explicit. Closed the direct
reminder edit wrapper, profile application/readback projection, cursor config domains,
standard failures and dry-run markers without changing any deployed schema or command.
All 14 RI stateful families remain pending, not counted as executed reference proofs.

**Verification:** 180 contract/regression tests and 1,123 subtests passed. Exact fixture
regeneration, independent canonical hashes/HMACs, negative wire cases, reference cursor
fences, historical decoding, nested attempt evidence and nonactivation checks pass.
Ruff, packaged-web synchronization, 226 local Markdown targets and diff hygiene pass.
Only test/reference machinery and the build-time exclusion list changed outside
specification/contract/tracking artifacts. Existing SPINE-048 closeout edits preserved.

**Next:** Bounded review of this successor machine-contract package, then separately
authorized authoring/worker/readback implementation with migration and concurrency
oracles. No product decision remains open in this codification; runtime activation,
web exposure and deployment remain unperformed and separately controlled.

### SPINE-048 — Rendering setup ordering recheck

**Status:** Done — reviewer-only recheck passed on 2026-10-04; zero findings,
boundary preserved. Bounded evidence only; not ratification or runtime qualification.
**Dependencies:** SPINE-047 correction committed at `59f3a1e`.
**Scope:** One reviewer-only buildability audit with GPT-6.1 Sol, focused on audit-002
R1-01: command-local materialization, operational exclusion, failure/resumption and
interleaving oracles. No new scheduler behavior or reopening unrelated closed findings.
**Package:** [Exact seven-file scope and notes](../whetstone_runs/notification-rendering-integration-contract-audit-003/audit-notes.md).
**Acceptance:** Inspect verdict and preservation, verify hashes/model/profile, record
closure or remaining findings. No source edits or runtime changes authorized.
**Evidence:** [Report](../whetstone_runs/notification-rendering-integration-contract-audit-003/change_audit/change_audit_report.json)
and [feedback](../whetstone_runs/notification-rendering-integration-contract-audit-003/change_audit/change_audit_feedback.json).
Verified exact seven-file inventory, GPT-6.1 Sol/buildability, source/notes hashes and
report/brief binding; all sources unchanged. Audit-002's delivery-ordering residual
has no remaining finding in this focused recheck. No Editor, commit or push.
**Next:** Operator ratification of the integration draft, then successor wire/cursor
schemas and computed fixtures before runtime implementation; no further audit started.

### SPINE-047 — Qualify staged rendering setup ordering

**Status:** Done — manual spec-only correction on 2026-10-04; focused recheck passed
under SPINE-048. Ratification remains separate.
**Dependencies:** SPINE-046 residual R1-01.
**Scope:** Command-local materialization semantics, explicit operational exclusion
for strict setup ordering, and scheduler-interleaving verification obligations.
No new hold state, scheduler behavior, ownership mechanism or runtime implementation.
**Acceptance:** Align draft/matrix/source-only tests; focused checks, links and diff hygiene.
**Result:** Draft v0.3 states that materialization=none is command-local, not a hold.
Strict ordering requires verified exclusion of concurrent/in-flight materialization
from before creation through presentation commit (through designated materialization
when controlling readiness explicitly). No automatic service control or grace extension;
failed setup requires an operator choice before exclusion is released. RI-03 now
requires stateful interleaving oracles with and without exclusion, explicitly pending.
**Verification:** 31 focused tests and 335 subtests, Ruff, package sync, 146 local link
targets and diff hygiene passed. Existing SPINE-046 audit evidence retained. No runtime
code, deployment operations, reviewer invocation, commit or push.

### SPINE-046 — Rendering integration focused recheck

**Status:** Done — reviewer-only recheck completed on 2026-10-04; `needs_revision`
(0 blockers, 1 major, 0 minors); design boundary preservation reported false.
**Dependencies:** SPINE-045 corrections committed at `053ec93`.
**Scope:** One reviewer-only Whetstone buildability recheck with GPT-6.1 Sol of
R1-01–R1-03 and their immediate consequences, including staged setup versus automatic
materialization. No source editing or new ownership/permission mechanism.
**Package:** [Exact 16-file scope and audit notes](../whetstone_runs/notification-rendering-integration-contract-audit-002/audit-notes.md).
**Acceptance:** Inspect findings and boundary verdict, verify manifest/source hashes,
and record closed/residual findings. No implementation, ratification,
Editor/convergence run, commit, push or deployment.
**Evidence:** [Report](../whetstone_runs/notification-rendering-integration-contract-audit-002/change_audit/change_audit_report.json)
and [findings](../whetstone_runs/notification-rendering-integration-contract-audit-002/change_audit/change_audit_feedback.json).
Exact 16-file scope, source/notes hashes, report brief hash and GPT-6.1 Sol/buildability
verified. Reviewer confirms the ownership path, revision guard and required-status
corrections; one directly introduced delivery-ordering claim remains unsound.
**Follow-up:** Section 3.3/matrix/RI-03/tests manually qualified under SPINE-047.
The audit verdict remains evidence about the pre-patch draft; SPINE-048 subsequently
passed its focused recheck of the residual correction.

### SPINE-045 — Rendering integration audit corrections

**Status:** Done — targeted manual draft correction on 2026-10-04; not re-audited.
**Dependencies:** SPINE-044 findings R1-01–R1-03.
**Scope:** Explicit staged trusted-local creation/adoption/presentation flow; reject
fresh v1 profile revision against a v2 current revision; required-status cursor rules.
Update the draft, source-only matrix and consistency tests; preserve runtime behavior.
**Acceptance:** Focused tests, authority/link consistency and diff hygiene. No runtime
implementation, schema activation, Whetstone invocation, commit or push.
**Result:** Draft v0.2 and its matrix define ordinary-only fresh local creation followed
by explicit adoption/presentation editing, with separately committed steps and no
inferred ownership. Fresh v1 profile revise rejects v2 current revisions (including
all-ordinary/no-op) after replay/reference/freshness checks; required list status is
bound verbatim into cursors. RI-02/03/11 carry the future behavioral proof obligations.
**Verification:** 30 focused tests and 335 subtests passed; Ruff, affected local links,
web-contract sync and diff hygiene passed. Tests prove source-only consistency, not
the unimplemented runtime behaviors. Ratification and bounded recheck remain pending.

### SPINE-044 — Rendering integration buildability audit

**Status:** Done — reviewer-only audit completed on 2026-10-04; `needs_revision`
(0 blockers, 2 majors, 1 minor); design boundary preservation reported false.
**Dependencies:** SPINE-043 draft checkpoint `2dc3f05`; prior machine-contract
findings are closed within SPINE-042's narrower review scope.
**Scope:** One reviewer-only Whetstone `audit-change`, built-in buildability profile,
`gpt-6.1-sol`. Assess storage/migration, authoring/version boundaries, policy-specific
work continuity, attempt evidence, permissions and bounded catalog cursors before
ratification. Distinguish missing semantics from explicitly pending wire codification.
**Package:** [Audit notes and exact 30-file scope](../whetstone_runs/notification-rendering-integration-contract-audit-001/audit-notes.md)
include the draft/matrix, owning specifications, relevant schema fragments, draft test
and three historical SQL files as read-only layout evidence. No source mutation authorized.
**Acceptance:** Inspect the report, severity/decision and preservation outcomes;
verify input hashes and requested model. No source edits, runtime/migration execution,
Editor/convergence workflow, commit, push or deployment.
**Evidence:** [Report](../whetstone_runs/notification-rendering-integration-contract-audit-001/change_audit/change_audit_report.json)
and [findings](../whetstone_runs/notification-rendering-integration-contract-audit-001/change_audit/change_audit_feedback.json).
Exact 30-file manifest, source hashes, notes hash and GPT-6.1 Sol/buildability verified.
**Follow-up:** R1-01–R1-03 manually addressed under SPINE-045; no recheck yet.
The original verdict remains evidence about the pre-patch draft. Ratification
remains pending. Boundary verdict describes draft gaps, not an audit scope violation.

### SPINE-043 — Rendering integration amendment

**Status:** Done — draft amendment and source-only integration matrix authored on
2026-10-04; not ratified or implemented. Subsequent audit and correction are tracked
under SPINE-044/045.
**Dependencies:** Accepted rendering logical design, SPINE-042 clean machine-contract
recheck and implemented schema-18 facet-location freeze.
**Scope:** Draft persistence/migration, versioned authoring and evidence integration,
policy-specific work continuity, permission/release mappings and bounded catalog
cursors; align delegated authorities and source-only machine tracking.
**Acceptance:** Concrete integration contracts and verification obligations, preserved
ordinary behavior and working-tree changes, explicit remaining decisions/gates,
local link/contract checks and diff hygiene. No runtime code, migration execution,
Whetstone run, commit, push or deployment.
**Result:** [Rendering integration draft](../specs/notification-rendering-integration.md)
defines the hybrid table/constraint/index layout, historical ordinary backfill,
versioned profile/schedule/direct-reminder and rendering envelopes, presentation-only
edit branch, exact policy ancestry, one final rendering per attempt, permission
mapping and signed bounded catalog cursors. The companion
`contracts/notification-rendering-integration.v1.json` maps all existing integration
gates and RI-01–RI-14 acceptance obligations. No stateful fixture is claimed executed.
Minimal authority/delegation/index/plan amendments retain the accepted logical owner
and current source-only status. Existing SPINE-042 working-tree evidence is preserved.
**Verification:** 27 focused tests and 333 subtests passed; new checks cover draft
status, gate coverage, version/table/obligation consistency and absence of runtime/
packaged activation. Ruff, source-only web-contract synchronization, 237 local Markdown
links across the changed documents (before this result entry) and diff hygiene passed.
**Open decisions:** None required for the retained first-slice scope. Protected
shared-location authority, broader cross-owner release, web family activation and
pack adoption remain separate scope choices, not implicitly authorized by this draft.
**Next:** Review/ratify the amendment; codify complete successor wire/cursor schemas
and computed fixtures, then bounded buildability review before runtime work. No
schema number or release version is reserved and no implementation gate is waived.

### SPINE-042 — Focused rendering list-limit recheck

**Status:** Done — approved focused recheck completed cleanly on 2026-10-04.
**Dependencies:** SPINE-040 minor finding and SPINE-041 correction, committed as
`18146e6` after 21 tests / 333 subtests passed.
**Scope:** One reviewer-only `audit-change`, consistency profile, `gpt-6.1-sol`.
Check strict canonical limit rejection in all four request/response properties,
JSON Schema regex portability, valid 1–100 strings and preserved echo/count semantics.
**Package:** [Audit notes and exact 13-file scope](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-003/audit-notes.md).
**Acceptance:** Inspect the bounded finding-closure/verdict and preservation result;
verify unchanged input hashes and requested model. No source edits, Editor,
convergence claim, runtime implementation, commit or push as part of this review.
Broader closed findings are not reopened.
**Result:** [Report](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-003/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-003/change_audit/change_audit_feedback.json):
`pass`, `boundary_preserved=true`; zero blockers, majors, minors or nits. The remaining
list-limit clarification is closed for this bounded contract scope. Requested
`gpt-6.1-sol` confirmed in manifest and feedback; built-in consistency profile.
All 13 source hashes match the staged baseline and audit manifest; approved notes
match the manifest. No source edits, Editor, runtime changes, commit or push ran.
This is bounded consistency evidence, not convergence or rendering implementation
readiness; remaining integration contracts are not waived.

### SPINE-041 — Reject noncanonical rendering list limits

**Status:** Done — operator-authorized targeted patch verified on 2026-10-04.
**Scope:** Tighten the four rendering definition/disclosure list request/response
limit patterns and add request/response newline-rejection tests. Preserve canonical
1–100 values, required response echoes and the separate record-count oracle.
**Dependencies:** SPINE-040's single minor finding.
No runtime activation, migration, audit rerun, commit or push.
**Result:** Replaced the four `$` terminators with strict end-of-input assertions.
Both request and response validators reject LF, CRLF and other whitespace/suffixes;
all canonical decimal strings 1–100 remain accepted. Echo and record-count rules
are unchanged. The new regression test reproduced the trailing-LF failure before
the schema correction. Focused rendering/notification/packaging checks passed:
**21 tests, 333 subtests**; Ruff, web-contract synchronization and diff hygiene passed.
Source-only status and existing backlog changes are preserved. This is a locally
verified manual correction, not a new Whetstone verdict.

### SPINE-040 — Focused rendering machine-contract recheck

**Status:** Done — approved reviewer-only recheck completed on 2026-10-04;
one minor clarification remains for a separately authorized manual patch.
**Dependencies:** SPINE-036 findings, SPINE-037 manual patch, and SPINE-039's clean
location amendment review; checkpoint `866081c` includes the schema-18 prerequisite.
**Scope:** One reviewer-only `audit-change`, built-in consistency profile,
`gpt-6.1-sol`. Recheck dry-run response encoding, accepted list-limit echo and
facet-location source immutability, plus source-only activation preservation.
**Package:** [Exact 35-file inventory and audit notes](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-002/audit-notes.md).
Prior findings and the clean location-spec report are context, not a replacement
for this machine-contract recheck. Storage implementation certification is excluded.
**Acceptance:** Classify each prior finding, inspect the bounded report/severities
and boundary result, verify unchanged inputs and report any remaining decisions.
No Editor, source patch, runtime change, convergence claim, commit or push.

**Result:** [Report](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-002/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-002/change_audit/change_audit_feedback.json):
`pass_with_minor_clarification`, `boundary_preserved=true`; zero blockers/majors,
one minor, zero nits. Requested `gpt-6.1-sol` confirmed in manifest and feedback.
Prior dry-run and facet-location findings are closed at the contract level. The
list-limit finding is partially closed: required echoes and record-count semantics
are correct, but all four request/response limit regexes accept a trailing LF.
Local read-only JSON Schema probes reproduced acceptance of `"20\n"` in all four
properties. Recommended patch: strict end-of-input matching and LF/CRLF negative
cases; no product decision needed. No source patch was performed.
All 35 input hashes match the prepared baseline and run manifest; approved notes
match the run manifest. This closes the bounded review, not rendering integration
contracts or runtime implementation. No Editor, commit, push or deployment ran.

### SPINE-039 — Bounded facet-location freeze specification audit

**Status:** Done — approved reviewer-only audit completed on 2026-10-04.
**Scope:** One reviewer-only Whetstone `audit-change`, built-in consistency profile,
`gpt-6.1-sol`. Review the storage/ontology freeze amendment, historical cutover,
concurrency, migration/rollback and preservation of existing facet/rendering behavior.
**Package:** [Audit notes](../whetstone_runs/facet-location-freeze-contract-audit-001/audit-notes.md)
name seven specifications plus the notes and generated copies. No runtime source or
tests are sent; this is not implementation certification, an Editor workflow or a
convergence run. Existing uncommitted implementation and contract work stay intact.
**Acceptance:** Inspect the report, classify findings/decisions, verify unchanged input
hashes and report the bounded verdict and preservation status. No automatic patches,
runtime changes, commit, push or deployment.
**Result:** [Report](../whetstone_runs/facet-location-freeze-contract-audit-001/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/facet-location-freeze-contract-audit-001/change_audit/change_audit_feedback.json):
`pass`, `boundary_preserved=true`; zero blockers, majors, minors or nits. Reviewer
`gpt-6.1-sol` confirmed in manifest and feedback; built-in consistency profile.
No in-scope findings or product decisions were returned. All seven source hashes and
the approved notes hash match the prepared baseline and final audit manifest; source
bytes stayed unchanged. This is bounded specification evidence, not convergence,
runtime certification or deployment approval. Existing uncommitted implementation
and rendering contracts remain intact; no Editor, patch, commit or push ran.

### SPINE-038 — Enforce facet-referenced location immutability

**Status:** Done — implemented and locally verified; checkpointed with runtime 0.8.3,
not deployed. The operator requested this checkpoint on 2026-10-04 after the clean
SPINE-039 specification audit; rendering contracts remain source-only.
**Scope:** Schema-18 forward trigger migration, exact schema-object manifests,
fresh initialization, historical/non-queryable reference protection, migration
rollback and concurrency tests. Preserve existing data and rendering contract work.
No deployment, commit, push or activation of facet-aware rendering.
**Result:** Runtime 0.8.3/schema 18. Migration 0018 changes only the existing location
canonical-field trigger plus schema activation; all historical SQL migrations are
unchanged. The schema-17 manifest is retained, the current manifest changes exactly
one object fingerprint, and the writer inventory now pins schema 18. Schema-17
activation verification is explicitly versioned so older migration chains still work.
The existing reference index serves both historical and non-queryable facet protection.
Metadata updates remain permitted; corrections require new location/item versions.
No location/catalog tables, public command contracts, work rows or attempt bodies change.
**Verification:** FS-14 has six executable tests / eleven subtests for all canonical
fields, metadata, historical removal/correction, failed attachment rollback, populated
cutover/backup restore, interrupted DDL/activation, schema drift, indexed lookup and both
two-connection writer orders. Full pytest: **776 passed, 1104 subtests passed** with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -o addopts='' -q`.
Ruff, strict mypy (43 source files), compileall, source-only contract synchronization,
212 local links across eleven documents and diff hygiene passed.
Installed non-editable wheel smoke outside the checkout passed fresh schema-18
initialization, real schema-17-to-18 migration, deep verification, packaged migration/
manifest presence and exclusion of the source-only rendering family. Wheel SHA-256:
`43b81445d157b1331ea955a7f08df8c5175fd5204831af92ad8b786219259f74`.
**Environment notes:** Initial worker verification using `../tickerd/src` correctly
failed closed because that checkout is now 0.3.0/capability v2. Final verification uses
the already installed compatible Tickerd 0.2.0/capability v1, with no compatibility
relaxation. The local venv lacked setuptools for a non-isolated wheel build; ordinary
isolated build-dependency provisioning succeeded without changing runtime dependencies.
**Handoff:** Preserve the existing uncommitted rendering contracts. Deployment requires
all writers stopped, a consistent verified backup, migration, then the new runtime.
Rollback restores the pre-migration backup with matching code; preserve any newer data
before restoration. No live ledger or service was touched; no audit rerun, commit or push.

### SPINE-037 — Align rendering contracts and facet-location immutability

**Status:** Done — operator-authorized targeted manual contract patch; not re-audited.
**Dependencies:** SPINE-036 findings and the implemented facet reference storage.
**Scope:** Shared dry-run response convention, accepted list-limit echo, and canonical
location freeze for all persisted facet references, including historical/non-queryable
fields. Check existing storage rules before extending them; preserve source-only
activation fences. No runtime implementation, migration, audit rerun, commit or push.
**Acceptance:** Consistent normative owners, matching schemas/fixtures and negative
tests; explicit future runtime proof for the additional location freeze.
**Result:** All success/failure response schemas accept only an optional true dry-run
marker, including reads; normal/replay/no-op fixtures omit it. Both list responses
require the accepted decimal-string limit. Added five preview fixtures (28 total),
all-command marker/limit tests and the separate record-count semantic oracle.
Storage inspection confirmed the existing immutable historical reference rows/FKs
protect deletion, while `locations_referenced_canonical_fields_update` checks only
`item_locations`. The ontology and facet-storage Section 7.1 now specify a freeze for
all persisted facet references, using the existing location-reference index. The
required forward migration/manifest update and FS-14 race/history/cutover proof remain
unimplemented; the stateful fixture is expressly not runtime evidence. No historical
label recovery, synthetic location association or new location lifecycle is implied.
**Verification:** Focused rendering contracts: 12 tests / 115 subtests passed. Two
non-overlapping regression selections covering rendering/notification/facet contracts,
facet storage/migration, supporting sets, declarations and packaging passed 101 tests
and 456 subtests in total. Ruff, source-only package synchronization, 158 local links
across seven affected documents and `git diff --check` passed. Runtime `src/` and the
index remain unchanged; prior working-tree edits and original audit artifacts preserved.
**Next:** A focused reviewer recheck would need an updated scope including the
facet-storage amendment; the previous audit verdict is not superseded by local tests.

### SPINE-036 — Bounded rendering-definition machine-contract review

**Status:** Done — operator-approved reviewer-only audit completed with `gpt-6.1-sol`.
Verdict `needs_revision`, `boundary_preserved=false`: zero blockers, two majors,
one minor and zero nits. This completes the review, not the findings or feature.
**Dependencies:** SPINE-035 initial codification in the current uncommitted worktree.
**Scope:** One reviewer-only `audit-change`, built-in consistency profile,
`gpt-6.1-sol` (operator-selected upgrade), app CLI 0.160.0. Review nine reserved commands, six schemas,
selection/evidence fragments, identities and receipt semantics, disclosure isolation,
23 fixtures/reference oracles and source-only packaging fences. Preserve the ratified
design and distinguish known remaining integration gates from new contradictions.
**Evidence:** [Audit notes and exact 43-file scope](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-001/audit-notes.md).
Source byte/hash inventory is local-only in the same run root; verify unchanged inputs
before launch. Review is against working-tree bytes, not the earlier HEAD checkpoint.
**Acceptance:** Inspect one completed report, classify findings and product decisions,
verify unchanged source bytes and report boundary preservation. No Editor, convergence
claim, source edits, runtime, commit or push. Approval of prior design audits does not
authorize sending this newly codified family.
**Result:** [Audit report](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-001/change_audit/change_audit_report.md)
and [structured feedback](../whetstone_runs/notification-rendering-definitions-machine-contract-audit-001/change_audit/change_audit_feedback.json).
Major findings: response shapes require/allow `dry_run=false` and cannot represent
dry-run read successes; facet-only location references assume immutability beyond the
ontology's stated `item_locations` freeze predicate. Minor: both list-response shapes
omit the accepted-limit echo. The reviewer confirms source-only packaging/activation
and the distinction between reference tests and unexecuted stateful obligations remain
preserved; the overall boundary verdict is false because of the identified contract
contradictions, not an observed runtime change.
**Verification:** The report and feedback both name the requested model. All 43 input
hashes match the prepared baseline and Whetstone manifest; the approved notes hash
also matches. No source specification, schema, fixture, test or build input changed
during review. No Editor or implementation ran.
**Follow-up:** Operator authorized SPINE-037 to patch the findings and inspect existing
facet storage. The selected amendment extends the location freeze to persisted facet
references; it introduces no location catalog or revision model. The audit verdict
above remains historical evidence, not a claim that the patch has been re-audited.

### SPINE-035 — Ratify rendering definitions and codify initial machine contracts

**Status:** Done — logical design ratified v1.0 and initial source-only machine
contracts/fixtures codified on 2026-10-03 following the clean SPINE-034 focused recheck.
**Scope:** Ratify the reviewed logical design; define source-only catalog/disclosure
command schemas, selection/evidence shapes, version registry and conformance fixtures.
Preserve existing authoring schemas, runtime declarations, ordinary rendering and work
identity. Physical storage, migration and final authoring/worker integration remain
explicit implementation gates, not silently invented in a schema-only step.
**Acceptance:** Closed schema fixtures and computed reference vectors pass; negative
fixtures cover disclosure isolation and preservation boundaries; existing contract and
documentation checks remain green. No runtime code, database migration, audit, commit
or push is included in this task.
**Delivered:** [Logical contract, Section 13](../specs/notification-rendering-definitions.md#13-initial-machine-contract-family),
[reserved registry](../contracts/notification-rendering-definition-contract-registry.v1.json),
six closed schemas, and [23 fixture files](../contracts/notification-rendering-definition-fixture-manifest.json).
Nine reserved catalog/disclosure commands do not enter the implemented registry.
Selection/evidence fragments are explicitly not fields accepted by current envelopes.
Reference coverage includes 16 rendering cases, 14 disclosure cases and nine canonical
preimage/digest vectors. Twelve stateful acceptance scenarios remain unexecuted runtime
obligations, not claimed implementation evidence.
The existing shared command-context dry-run and replay rules are preserved. A narrow
build-script exclusion prevents these six future schemas from entering the current web
wheel; packaging regressions cover accidental activation. The older notification family
test excludes this separate family without changing its expected existing schema set.
**Verification:** Contract/documentation regression suite passed 167 tests and 807
subtests; new negative cases cover revoked detail evidence, closed shapes, field limits,
wrong versions, invalid dates and omission privacy. Ruff, offline web-contract parity,
local Markdown links and diff hygiene pass. Existing `src/`, current contract schemas,
runtime version and ledger schema are unchanged. The pre-existing SPINE-034 completion
record in this working tree is preserved.
**Next gate:** Review the newly codified machine contracts, then close the explicitly
listed physical-storage/migration, enclosing authoring/evidence, policy-specific work
continuity, permission-resolver and authenticated-cursor integration contracts before
runtime work. No new product decision is required by this codification; no approval of
future web exposure or pack installation is inferred.

### SPINE-032 — Draft opt-in facet-aware notification rendering definitions

**Status:** Done — specification drafted and manually corrected after its first
bounded audit on 2026-10-03; not ratified, codified or implemented at that checkpoint. This completion
covers the requested design pass only, not feature delivery. The focused recheck is
now clean under SPINE-034; broader implementation contracts remain open.
**Evidence:** [Rendering definitions](../specs/notification-rendering-definitions.md)
owns proposed catalog/policy selection, scalar detail composition, exact schema
matching, attempt-time freshness, immutable evidence, fallback and pack boundaries.
Targeted delegation updates preserve current renderer/profile/facet contracts.
**Verification:** Seven agent-documentation tests, three current rendering-fixture
tests and two implemented-contract declaration tests pass. All 23 new/added local
Markdown link targets resolve; diff hygiene passes. These verify the draft's
integration/preservation, not executable behavior of the proposed extension.
**Operator directions incorporated:** Reusable scoped disclosure recorded per policy;
scalar detail plus existing location-reference labels; retirement blocks fresh use
without suppressing pinned existing reminders. Draft v0.1.2 records these directions;
exact authorization matching, location scope, permission and lifecycle mechanisms
remain reviewable design proposals, not a ratified machine contract.
**Follow-up:** SPINE-034 completed the focused recheck without findings; SPINE-035
subsequently records ratification and initial machine contracts/fixtures. Its remaining
integration gates precede implementation.
No runtime, schema, pack, web exposure or deployed-agent changes are authorized by
this entry. Deferred resilience initiatives are not reopened.

### SPINE-033 — Bounded audit of rendering definitions and scoped disclosure

**Status:** Done — bounded review completed 2026-10-03 with `needs_revision`:
zero blockers, one major, two minors; `boundary_preserved=false`. This closes the
review task, not the findings or the feature's implementation gates. No convergence claim.
**Dependencies:** SPINE-032 amended draft and operator-approved product directions.
**Scope:** Definition/profile/policy boundary, reusable destination-scoped disclosure,
single-hop existing location labels, retirement versus revocation, attempt freshness,
failure separation and preservation of current reminder behavior. Review the draft's
technical choices; do not assume the product discussion ratified them.
**Evidence:** [Audit notes and exact proposed send scope](../whetstone_runs/notification-rendering-definitions-contract-audit-001/audit-notes.md).
Local preparation verifies ten unique source paths, exact invocation/allowlist parity,
resolved added links and diff hygiene. The Whetstone CLI help was inspected; no live
reviewer was invoked during staging. The authorized live audit subsequently completed.
The shell-path Codex CLI 0.142.0 was rejected before semantic review because the selected
model requires a newer client. The failed output is preserved; the same approved bytes
and model were reviewed using already-installed app CLI 0.160.0 in an isolated recovery
root. No CLI upgrade or model substitution occurred.
**Result:** [Completed report](../whetstone_runs/notification-rendering-definitions-contract-audit-001/retry-cli-0160/change_audit/change_audit_report.md)
and [structured findings](../whetstone_runs/notification-rendering-definitions-contract-audit-001/retry-cli-0160/change_audit/change_audit_feedback.json).
The major is ambiguous authorization classification for custom additions inside a
profile-backed application. Minors concern unnecessary reapproval after timing-only
profile revisions and a pre-existing architecture reference to v1 instead of the
implemented v2 schedule contracts.
**Manual correction:** Authorized 2026-10-03; draft v0.1.2 now classifies templates
and replacements as profile-scoped, custom additions/direct reminders as direct-policy
scoped, and suppressed entries as producing no policy. Approval binds to the stable
profile root and disclosure facts, not its behavioral revision; exact profile revision
remains provenance. New verification oracles cover origin isolation and timing-only
approval reuse. Architecture v0.2.5 corrects the implemented v2 baseline without
changing current contracts. Local verification: 12 documentation/rendering-fixture/
implemented-declaration tests pass, all 23 added local links resolve and diff hygiene
passes. This patch step did not run a reviewer or change runtime; the subsequent
checkpoint is `48be7d4` and its reviewer recheck is recorded under SPINE-034.
At review completion, all ten specification hashes and the approved notes hash matched
the completed manifest; no source specification changed during that review. The manual
patch deliberately follows it and does not rewrite the preserved audit evidence.
**Acceptance:** One bounded reviewer-only report inspected, findings classified and
remaining decision/implementation gates stated; manual source changes only with
operator authorization. No Editor, Phase 1/2, machine contracts or runtime work.

### SPINE-034 — Focused rendering-definition manual-patch recheck

**Status:** Done — exact send scope approved and focused consistency recheck completed
2026-10-03 against checkpoint `48be7d4` using `gpt-5.6-sol` and app CLI 0.160.0.
Verdict `pass`, `boundary_preserved=true`; zero blockers, majors, minors or nits.
**Dependencies:** SPINE-033 completed feedback and the committed v0.1.2 manual fixes.
**Scope:** Custom-addition versus profile-derived disclosure scope, timing-only profile
revision approval reuse, and the corrected implemented v2 schedule baseline. No runtime
or broader specification rewrite. Four specifications plus prior feedback and the notes
form the exact proposed send scope.
**Evidence:** [Recheck notes](../whetstone_runs/notification-rendering-definitions-contract-audit-002/audit-notes.md).
**Result:** [Recheck report](../whetstone_runs/notification-rendering-definitions-contract-audit-002/change_audit/change_audit_report.md)
and [structured feedback](../whetstone_runs/notification-rendering-definitions-contract-audit-002/change_audit/change_audit_feedback.json).
The reviewer returned an empty feedback array on the explicitly scoped three-finding
closure/regression recheck. The five input hashes and approved notes hash match the
manifest; all four source specs remain byte-identical to the checkpoint. No source
mutation, Editor, implementation, further commit or push occurred during this review.
This is bounded consistency evidence, not convergence or implementation readiness.
Existing audit artifacts
remain local/ignored under the repository convention; the checkpoint contains the
specification and documentation changes, not generated reviewer payloads.
**Acceptance:** Inspect one completed report, account for closure of all three findings,
verify unchanged source hashes, and record residuals without claiming convergence or
implementation readiness. Any source patch requires separate operator direction.

## Recently completed backend work

### SPINE-031 — Accept notification-profile readback through CLI include flags

**Status:** Done — local implementation and verification, 2026-09-30; deployment pending.
Runtime 0.8.2 repairs `schedule.show --include notification_profile` preflight, help,
and validation text to match the existing handler and `spine.schedule-show.v1`
response contract. Schema 17 and public contract versions are unchanged.
**Evidence:** [CLI regression tests](../tests/test_schedule_show_command.py) reproduced
the rejection before the fix and now cover every contract include, the reported mixed
invocation, JSON-input response parity, help/error text, and unknown/empty/duplicate
rejection before opening the ledger. Focused tests: 10 tests + 17 subtests pass.
Full CI test command: 757 unittest tests pass. CI Ruff and strict mypy checks,
Ruff on changed tests, packaged web-contract parity, and diff hygiene pass.
No deployment or production data changes were performed.

### SPINE-030 — Restore policy-specific notification continuity

**Status:** Done — local implementation and verification, 2026-09-27; deployment pending.
Preserved schema-15 policies can share an intent while retaining distinct policy IDs.
The facet implementation incorrectly required intent uniqueness during reconciliation,
attempt-start validation, and facet continuity. Runtime 0.8.1 now resolves exact policy
ancestry across repeated copy-forwards and keys target snapshots by resolved policy;
the owning specifications and packaged integration contract/pins are aligned. Schema 17
is unchanged. The synthetic schema-15 fixture reproduces the failure before the patch
and verifies preservation through migration, reconciliation, facet edits, and fake sends.
**Evidence:** 755 tests + 961 subtests pass; installed-wheel focused run passes 84 tests
+ 182 subtests (one repository-only generator test deselected and verified separately).
Ruff, strict mypy, compileall, contract parity, and diff hygiene pass. See the
[hotfix report](NOTIFICATION_POLICY_LINEAGE_HOTFIX.md) for environment, artifact hashes,
and the remaining disposable-staging-backup deployment gate. No staging mutation,
deployment, commit, or push was performed.

### SPINE-015 — Read authorized activities independently of unavailable linked resources

**Completion checkpoint:** Spine 0.6.0 HTTP/package/capability integration is committed
and pushed at `ad1db8e1a4c7aa9a525612324d08824802a86351`. That exact commit passed
operator-reported clean-room backend validation. Kinflow has since added and exercised
the opt-in v2 client and calendar integration against staging. Manual usability
acceptance and promotion of that preview to the default connected view remain separate
Kinflow work and do not keep this backend item open.

**Status:** Done — backend delivery closed 2026-09-24. Initiative selected on
2026-09-15; specification and
machine-contract phases complete. Both focused rechecks passed without findings;
the manual machine-contract fixes and preceding checkpoints are pushed through
`4d16670`. Runtime delivery planning completed on 2026-09-18; the operator then
authorized the first implementation slice. Shared read-contract validation,
normalization, bounded read-only context, authorized selection and core/time
assembly are implemented and locally tested. The subsequent internal slice adds all
eleven detail-section projections, four agenda summaries, canonical occurrence and
resolved/unplaced agenda assembly, plus an index-only schema-15 migration. The
internal release-fence and authorized source-hashing slice is committed at
`629c7a4`; cursor/identity encoding and pagination at `141d995`. The subsequent
HTTP/package slice completes all four v2 routes, packaged admission and capability
advertisement in runtime 0.6.0. It is committed, pushed and clean-room validated as
recorded below. Schema 15 and v1 behavior remain unchanged. The backend defect and
delivery scope are closed. Any defect found during later Kinflow manual acceptance may
create a new bounded backend item; it does not leave SPINE-015 provisionally open.
**Dependencies:** Existing trusted web permissions, canonical recurrence/agenda and
temporal-binding engines, and the accepted read/machine contracts. No further broad
specification pass is scheduled. Query/index migration assessment and behavioral
verification are implementation tasks, not already satisfied by static fixtures.
This concrete item is independent of the withdrawn SPINE-001–003 review tasks and
the deferred resilience initiatives.

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

**Runtime delivery scope:** One cohesive backend slice implementing the complete
independent-read registry: v2 schedule detail, occurrences, agenda and capability
discovery. Shared authorized projection, own-time freshness, bounded queries,
source/release fences, cursor codec, packaged contract admission, runtime tests and
operator/consumer documentation ship together. See the
[delivery sequence](IMPLEMENTATION_PLAN.md#planned-fat-slice-independent-authorized-activity-reads-spine-015).
Deployment and Kinflow adoption follow separately with explicit evidence and approval;
this planning change performs neither.

**Non-goals:** Repairing ownership, granting access from assignment, weakening
cross-resource writes, changing v1/CLI semantics, v2 writes, client recurrence
calculation, family-facing copy in Spine, new authentication, facets, advisory
execution or reopening deferred resilience work. Atomic provisioning of intended
ownership at task creation is a separate companion requirement; this item must
also handle legitimate access differences after correct creation.

**Acceptance:** The accepted IR-01–IR-16 matrix in the supporting spec covers:
authorized events with unowned or inaccessible followers; normally visible authorized
relations; disclosure-safe empty/incomplete context; generic direct denial; unavailable
task time without a fabricated deadline; epoch/version/pagination races; unchanged
cross-resource write protection; and Kinflow rendering from public canonical facts.
The machine-contract review and IR-01–IR-15 backend behavioral gates are complete,
including exact packaged pins and registry, query/index migration assessment,
unchanged v1/CLI and write regression tests, and no durable read effects. IR-16 and
the consumer side of IR-15 require separate Kinflow integration evidence.
Documentation alone does not close the feature.

**Delivery checkpoints (in order):**

1. Shared bounded authorized selection, projection and own-time resolution — internal
   implementation complete.
2. All detail sections and resolved/unplaced agenda assembly — internal implementation
   complete.
3. Authorization/source fences, authorized source hashes, v2 cursor codec/identity
   encoding and actual first/next-page pagination — internal implementation complete,
   including retained private-proof revalidation.
4. Complete HTTP/packaging/capability integration and behavioral regression suite —
   implemented and locally verified in 0.6.0.
5. Host-neutral operator documentation and precise Kinflow release handoff — updated
   for 0.6.0, with consumer acceptance explicitly pending.
6. Kinflow adopted the contracts and exercised an opt-in v2 calendar against staging.
   Manual usability acceptance, remaining migration cases and default-view promotion
   are separately tracked consumer work. Backend completion does not claim consumer
   migration completion.

**Internal release-fence/source-hash checkpoint (2026-09-19):** Added
`web/read_release.py`, `read_authorization.py`, and `read_proof.py`. The internal
`read_authorized` path assembles in one read-only transaction, closes it, and opens
a fresh read-only transaction for mandatory identity/authorization/source checks.
A single outer clock/SQL/byte budget spans both; optional evidence and its rechecks
retain the optional SQL reserve. Unavailable sections discard their partial proof
and authorization fragments. Revalidation failure never silently downgrades an
already assembled result. These are unpaged internal objects, not HTTP responses.

Private checks include selected account/selection, account and account-subject
binding revisions, operator/subject state, ledger/realm/recovery/access epochs,
owner/catalog/route permissions, checked grants, active memberships, previously
denied necessary sources, and discovered candidate membership. Prospective grant
activation/expiry and membership activation bound validity without requiring an
epoch write; the deadline is also checked after fresh proof work. Subjects have no
numeric revision column: this slice fences the full canonical selected-subject row,
without inventing or exposing a cursor `subject_revision`. Its numeric wire mapping
must be implemented explicitly with cursor integration.

Public source digests use the exact `spine.trusted-web-read-snapshot.v1` preimage,
with unique `(kind,id)`-sorted records hashing closed authorized candidate cores,
canonical recurrence sets, required authorized temporal source cores/binding
revisions, and only requested projected section rows. Agenda summaries hash their
underlying authorized rows, not only counts; off-range candidates remain covered.
Unsupported/protected canonical proof references make time unavailable and never
enter the public digest as a substitute for authorization. Independent hidden
follower mutations leave the event proof unchanged. Canonical occurrence identities
and all v1/write/replay/worker/delivery behavior are reused unchanged.

Fresh direct source changes return `version_changed`; agenda or retained private
proof changes return `access_changed`. Root admission still precedes version guards;
invalid selected identity retains `identity_unavailable`. The internal retained-proof
path preserves the original authorization evaluation time and deadline. It is not a
wire cursor implementation and rejects cursor transport fields.

**Query/index evidence:** Actual `EXPLAIN QUERY PLAN` inspection on SQLite **3.53.2**
shows `SEARCH g USING INDEX access_grants_subject` for grantee/status/resource-kind
candidate transition scans, and `SEARCH g USING INDEX access_grants_group` with the
additional resource-ID equality for dependency probes. Correlated owner and operation
checks use `sqlite_autoindex_item_access_owners_1` and covering
`sqlite_autoindex_access_grant_operations_1`. Membership transition checks use
`subject_memberships_subject_status_idx`, with primary/covering group and adoption
lookups. The focused tests assert both grantee paths and the membership path. These
added paths need no index or schema migration; schema 15 remains unchanged.

**Verification:** Python **3.14.6**, pytest **9.1.1**, Ruff **0.16.2**. Test commands
used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src` and the existing local
Tickerd checkout; no dependency installation or Tickerd qualification was performed.

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_release.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_contracts.py tests/test_web_contract_sync.py --tb=short
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m pytest -o addopts='' -q
```

Results: focused **95 tests and 160 subtests passed in 13.33s**; full unittest
**590 tests in 34.325s, OK**; full pytest **590 passed, 572 subtests passed in
34.77s**, with no skips. The 31 new release tests cover real-ledger identity/source
races, selected-occurrence proof hashes, timed grants/memberships, protected proof
references, requested section evidence, first-read agenda/off-range candidates,
retained-proof checks, optional-budget isolation, no durable read effects, and
indexed query plans. Hooks and clocks are deterministic; no timing sleeps are used.

All four strict commands passed **37 source files** with incremental caching disabled
(configured target Python 3.12):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-release-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-read-release-120-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-release-230-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-read-release-230-editable src/spine/core src/spine/ledger
```

The first pair uses mypy **1.20.2**, the second **2.3.0**; `--python-executable`
selects discovery without an installed Spine distribution. `.venv/bin/ruff check .`,
`git diff --check`, and
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check`
passed. `PYTHONPYCACHEPREFIX=/tmp/spine-read-release-compile-cache .venv/bin/python -m compileall -q src tests examples`
passed with bytecode outside the repository.

**Environment limitation:** An additional offline wheel smoke attempt used
`.venv/bin/python -m pip wheel --no-deps --no-build-isolation --no-index <temporary-source> --wheel-dir <temporary-dist>`
on a temporary copy. It exited **2**, `BackendUnavailable: Cannot import
'setuptools.build_meta'`: the local environment lacks the build backend. No wheel was
produced and the subsequent installed-wheel checks did not run. This is not a claim
of fresh cloud/package acceptance for this slice; the synchronization gate remains
passing with deferred v2 assets excluded.

**Next implementation at that checkpoint:** v2 cursor codec/computed vectors, identity encoding,
fixed-expiry transport continuation, and section/combined-stream pagination using
these fences. Then complete HTTP/package/capability activation and its behavioral
gates, followed by separate Kinflow acceptance and deployment authorization. No v2
route, packaged capability or runtime declaration was activated. The operator
subsequently authorized a local commit of this slice; no push, staging migration,
deployment, or real-ledger access is included in that authorization.

**Internal cursor/pagination checkpoint (2026-09-19):** Implemented from clean
`629c7a450e4f63d11edd1953b777cf51eb8f776f`. Added `web/read_cursor.py` and
`web/read_pages.py`, with trusted paging callbacks inside the existing shared
release path. Page projection, signing, schema validation and response-size checks
precede the fresh release fence and share its original request deadline and SQL
budget. Invalid selected identity is admitted before cursor decoding. Every page
reassembles authorized data and rechecks retained private authority/source proof;
there is no public route or cached-response shortcut.

The independent HMAC-SHA256 codec computes the exact published wire vector. It
rejects wrong versions/signatures, padding, noncanonical base64url/JSON, duplicate
keys, unknown fields, invalid calendars, oversized tokens, wrong stream/root/query,
and changed identity. MAC verification precedes JSON parsing. All child pages retain
original issuance, expiry, authorization evaluation time and transition deadline.
Expiry is checked again after fresh proof work, including at the exact boundary.

`subject_revision` now has a pinned, tested positive-decimal content-fingerprint
encoding for the selected subject's six canonical fields. It is an equality token,
not a chronological counter. Private fences still compare the full subject row.
The account-subject binding maps directly from persisted `binding_revision` and
remains distinct from canonical temporal-binding revisions. The cursor artifact,
computed vectors, schema pins, contract companion and consumer handoff document
these rules; no v1 pin or runtime capability declaration changed.

Private proofs remain only in service-local memory, bounded to at most **128
families / 8 MiB serialized proof bytes** (configurable downward). They expire at
the original deadline; continuation never renews retention. Missing proof returns
`access_changed`, a full store returns `capacity_exceeded`, and an existing family
cannot be overwritten with different private evidence. Only closed projected
responses escape the pager; private checks, grant references and full assemblies
never enter tokens. No ledger/session/cache tables or durable read effects exist.

Detail collections page independently, with common-family enforcement across
supplied section cursors and first-page behavior for other included collections.
Occurrence pages retain the canonical engine's ordering and identities for both
range bases. Agenda pages emit resolved entries followed by item-ID-ordered
unplaced cores under one limit; whole-query temporal coverage is retained even
on a resolved-only page. Empty/exhausted results have no continuation.

**Query/index evidence:** Paging adds no SQL selection or OFFSET scans; it pages
the existing bounded authorized assembly. Actual SQLite **3.53.2** plans for the
selected-identity reads are `SEARCH subjects USING INDEX sqlite_autoindex_subjects_1
(subject_id=?)` and `SEARCH web_operators USING INDEX sqlite_autoindex_web_operators_1
(account_id=?)`. New tests assert those plans; prior grantee/membership/endpoint
plan tests also pass. No migration is necessary; ledger schema remains **15**.

**Verification:** New suite **31 tests / 36 subtests passed in 14.90s**. Combined
focused suites **126 tests / 196 subtests passed in 28.20s**. Tests cover all 13
closed cursor shapes, computed vectors, malformed signed payloads, fixed expiry,
identity switches, real-ledger section/occurrence/agenda continuation, mixed section
families, lost/bounded proofs, off-page source changes, timed grant and membership
transitions without epoch changes, hidden followers, denied/stale temporal sources,
DST exclusions/overrides, terminal lifecycle, optional failure, shared deadlines,
and byte-identical ledger dumps before/after successful paging.

Focused commands used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src`:

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_pages.py --tb=short
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_pages.py tests/test_independent_activity_read_release.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_contracts.py tests/test_web_contract_sync.py --tb=short
```

Full unittest **621 tests in 47.980s, OK**; full pytest **621 passed / 608 subtests
passed in 48.48s**, without skips. Commands used the same bytecode/PYTHONPATH
environment above and the existing sibling Tickerd checkout; no Tickerd installation
or separate qualification was performed:

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m pytest -o addopts='' -q
```

Python **3.14.6**, pytest **9.1.1**, Ruff **0.16.2**. All four strict checks passed
**37 source files**, with target Python 3.12 and incremental caching disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-pages-mypy-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-read-pages-mypy-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-pages-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-read-pages-120-editable src/spine/core src/spine/ledger
```

The first pair uses mypy **2.3.0**, the second **1.20.2**. Metadata discovery under
`/opt/homebrew/bin/python3` confirms Spine is absent for source-only checks. Ruff,
contract synchronization, compilation and diff hygiene pass:

```sh
.venv/bin/ruff check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check
PYTHONPYCACHEPREFIX=/tmp/spine-read-pages-compile .venv/bin/python -m compileall -q src tests examples
git diff --check
```

All **71** local file links in the four changed documentation/specification files
resolve. The synchronization gate still excludes deferred v2 assets. A fresh
offline wheel attempt copied packaging inputs/source to a temporary directory and
ran `.venv/bin/python -m pip wheel --no-deps --no-build-isolation --no-index
<temporary-source> --wheel-dir <temporary-dist>`. Pip exited **2** with
`BackendUnavailable: Cannot import 'setuptools.build_meta'`; no wheel was produced
and installed-wheel checks could not run. Both local Python environments lack
setuptools. Temporary build inputs were removed; no dependency installation or
network access was attempted. This is an environment limitation, not fresh
packaging or cloud acceptance for this slice.

**Next implementation at that checkpoint:** Complete the four-route HTTP integration, packaged contract
admission and runtime capability declarations with the behavioral/compatibility
gates. Then finalize operator documentation and Kinflow release handoff, followed
by separately authorized deployment and consumer acceptance. Internal paged-read
tests are not HTTP or Kinflow acceptance. No commit, push, deployment, staging
change, v2 activation, real-ledger access or Whetstone audit occurred in this slice.

**HTTP/package/capability checkpoint (2026-09-19):** Runtime **0.6.0**, schema
**15**, completes the four-route independent-read registry in the existing backend.
`web/read_service.py` loads the exact packaged v2 manifest and transitive assets;
startup checks runtime declarations and complete route registration. Selected
capability discovery uses read-only identity admission and a fresh release fence.
All three read routes use the existing authorized pager/source fences. Actual HTTP
JSON serialization and byte limits run before the fresh fence, under the shared
budget. Existing Host/Origin/identity/body limits, bounded concurrency and no-store
responses remain; v2 errors have closed generic envelopes without private details.
V1 routes, command registry, pins, write authorization, CLI, replay, worker and
delivery behavior are preserved.

The complete v2 package family adds **18 assets** (11 schemas and seven registry/
artifact files), with six implemented runtime contract declarations. Source and
package status/pins match. The fixture manifest maps IR-01–IR-15 backend evidence
to executable real-ledger tests; IR-16 and the consumer portion of IR-15 remain
pending. Operator documentation and the Kinflow handoff cover exact versions,
public response examples, temporal/section availability, generic failures, cache
invalidation, process-local cursor continuity, migration and rollback boundaries.
No staged deployment or frontend adoption is claimed.

New HTTP tests exercise the reported recurring Science event with an inaccessible
occurrence-bound follower; independent detail/occurrence/agenda reads; visible
cross-owner grants; denied/stale temporal sources; optional-context isolation;
generic root denials; all eleven sections; recurrence exceptions/DST and terminal
series; resolved/unplaced pages; cursor/access/source races; actual-wire byte limits;
closed receipt projections; hostile transport inputs; capacity rejection; unchanged
write denials; and no durable effects. Package tests reject every missing/corrupt
required asset and incomplete runtime declarations.

**Query/migration assessment:** This integration reuses existing bounded read and
pager queries. Actual `EXPLAIN QUERY PLAN` on a synthetic schema-15 ledger for the
two selected-identity lookups used by discovery returns:

```text
SELECT * FROM subjects WHERE subject_id=?
SEARCH subjects USING INDEX sqlite_autoindex_subjects_1 (subject_id=?)
SELECT * FROM web_operators WHERE account_id=?
SEARCH web_operators USING INDEX sqlite_autoindex_web_operators_1 (account_id=?)
```

Discovery does not traverse item graphs. No additional index or migration is needed;
the earlier schema-15 migration and its existing migration tests remain authoritative.

**Verification:** Focused tests ran before full regression. Python **3.14.6**,
pytest **9.1.1**, Ruff **0.16.2**; synthetic ledgers only. With
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src`:

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_trusted_web_runtime.py tests/test_trusted_web_contracts.py tests/test_independent_activity_read_pages.py tests/test_web_contract_sync.py --tb=short
# Pre-edit baseline: 70 passed, 70 subtests passed (25.23s).
.venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_http.py tests/test_independent_activity_read_pages.py tests/test_independent_activity_read_release.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_contracts.py tests/test_trusted_web_runtime.py tests/test_trusted_web_contracts.py tests/test_web_contract_sync.py --tb=short
# Completed focused suite: 190 passed, 269 subtests passed (59.39s).
.venv/bin/python -m unittest discover -s tests
# 650 tests, OK (68.250s).
.venv/bin/python -m pytest -o addopts='' -q
# 650 passed, 652 subtests passed (69.03s).
```

No skips; sibling Tickerd is available locally. Both mypy **2.3.0** and **1.20.2**
pass all **37 files**, source-only and editable-install, with strict rules, Python
3.12 target and incremental caching disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-http-mypy-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-read-http-mypy-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-read-http-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-read-http-120-editable src/spine/core src/spine/ledger
```

The source-only interpreter has neither a `spine-ledger` installed distribution nor
an importable `spine` module. Ruff, synchronization, compilation and diff hygiene
pass; all **125 local file links** in the eight changed Markdown files resolve:

```sh
.venv/bin/ruff check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check
PYTHONPYCACHEPREFIX=/tmp/spine-read-http-compile .venv/bin/python -m compileall -q src tests examples
git diff --check
```

**Fresh packaging evidence:** The previous missing-backend environment limitation
was resolved for this check by downloading setuptools **84.0.0**, wheel **0.48.0**
and packaging **26.3** to `/tmp/spine-http-build-tools`, then installing them only
under `/tmp/spine-http-build-backend`. Existing environments and repository files
were not changed by dependency installation. Network access was limited to obtaining
these build tools; the build/install and runtime checks were offline.

```sh
.venv/bin/python -m pip download --disable-pip-version-check --no-cache-dir --index-url https://pypi.org/simple --only-binary=:all: --no-deps --dest /tmp/spine-http-build-tools setuptools wheel packaging
.venv/bin/python -m pip install --disable-pip-version-check --no-index --find-links /tmp/spine-http-build-tools --target /tmp/spine-http-build-backend setuptools wheel packaging
# Build a temporary copy of src, pyproject.toml, README.md and LICENSE:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/spine-http-build-backend .venv/bin/python -m pip wheel --disable-pip-version-check --no-cache-dir --no-deps --no-build-isolation --no-index <temporary-source> --wheel-dir <temporary-dist>
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --no-index --no-deps --target <temporary-installed> <wheel>
```

Built `spine_ledger-0.6.0-py3-none-any.whl` (490827 bytes; SHA-256
`0147974bb9881b50c6013ef578175440e041cc632c490c717b2abe47f7932676`).
All **97 packaged web JSON files** match source bytes, including archetype-facet
schemas and the complete new family. With isolated `python -I`, the temporary
installation prepended to `sys.path`, and assertions that both imported code and
package metadata identify that wheel as 0.6.0, all **26 HTTP tests** pass (19.076s).
The repository supplies test fixtures, not the imported runtime. Installed migration
CLI checks `--initialize-if-empty` and `--verify-only` on a temporary synthetic ledger
pass at schema 15: integrity/invariants OK, zero foreign-key errors, 80 tables and
70 indexes. Installed `system info` reports 0.6.0/schema 15, all six v2 declarations,
compatible Tickerd 0.2.0 and timezone release 2026c-rearguard. Temporary build,
installation and ledger directories were removed.

**Operator-reported clean-room validation (2026-09-19):** Exact commit
`ad1db8e1a4c7aa9a525612324d08824802a86351` passed the available Python 3.12 cloud
backend gates with an unchanged checkout. The focused suite passed **190 tests and
269 subtests**; the isolated installed wheel passed all **26 HTTP tests**; all **97**
packaged web JSON assets matched source bytes, including the **18** v2 assets; and
synthetic schema-15 initialization and deep verification passed. Full discovery
remained **650 tests**: **617 passed + 33 Tickerd-dependent skips**, with **652
passing subtests**. Strict source-only and editable-install mypy 1.20.2, Ruff,
compilation, synchronization, documentation construction, migration regressions
and diff hygiene passed. The cloud-built 0.6.0 wheel had SHA-256
`8baf2dd4c6dee857635218eef21d823ae6ff7925aa7aa79c3218c3eaa0f0f4ee`.

Tickerd was unavailable in that environment, accounting for the 33 skips and
preventing an unpatched successful `system.info`; mypy 2.3.0 could not be provisioned
because the package proxy returned HTTP 403. These are environment limitations, not
actionable Spine failures; both paths passed locally. No cloud deployment, real-ledger
access, Kinflow acceptance or source modification occurred.

**Remaining work:** No backend implementation or validation blocker remains for this
release. Separately authorize and verify deployment/canaries, then Kinflow adoption,
IR-16 and the consumer side of IR-15. SPINE-015 remains in progress until those
end-to-end gates are complete.

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

**Checkpoint and audit preparation (2026-09-16):** Committed the contract-only
codification as `f9a301b` (`Codify independent activity read contracts`); pre-commit
verification again passed 73 tests and 202 subtests. Staged reviewer-only bounded
`audit-change` at `whetstone_runs/independent-activity-read-machine-contract-audit-001/`.
Its `audit-notes.md` enumerates the exact 39-file approval inventory (including notes),
review boundaries and goals. `preparation.json` records the source checkpoint/hashes
and supported invocation: Sol, consistency profile, bundled CLI, 900-second timeout.
The included 14 fixture files are a declared representative subset, not all 53.
Five existing authority documents are supplied as one verbatim excerpt artifact
with checkpoint, line-range and hash provenance, rather than sending their unrelated
sections. All eleven new schemas and new rule/vector/pin artifacts remain in scope.
Source files matched the committed checkpoint. Preparation did not invoke a reviewer,
Editor, source rewrite, convergence workflow or push.

**Machine-contract audit 001 (2026-09-16):** The operator approved the exact 39-file
inventory, built-in consistency profile and generated copies. Reviewer-only
`audit-change` completed with Sol, bundled CLI `0.154.0-alpha.6.2`, 900-second timeout.
Verdict `needs_revision`: 0 blockers, 3 majors, 0 minors/nits; all findings in scope.
`boundary_preserved=false` is the report's contract-gap assessment, not a finding
of an implemented runtime leak. Findings: available agenda summaries incorrectly
allow null instead of zero buckets; impossible local Gregorian date-times pass
machine validation; end-only available events and defer-only agenda tasks pass
required-primary-anchor validation. Read-only counterexamples reproduced each gap
against the checked-in schemas/static oracles. Sources were not patched.
All 38 raw source hashes stayed unchanged; all 39 normalized input hashes matched
the manifest, including notes. The manifest confirms the exact approved inventory,
Sol and consistency; no convergence or exhaustive coverage is claimed. Report and
feedback are under the run root's `change_audit/`. Next step: targeted manual schema/
semantic-oracle fixes with negative fixtures, updated new-contract pins, then focused
recheck. Runtime implementation remains pending. No Editor, commit or push was run.

**Manual audit patch (2026-09-16):** Addressed all three audit-001 findings without
runtime or v1 changes. Available agenda summary values are now non-null objects;
location and creation-receipt singletons retain valid null absence. Shared local
date-times use mandatory `spine-local-date-time` format assertion, with a specified
Gregorian/leap-year/clock domain and an executable offline checker. The test checker
also explicitly asserts the existing UTC `date-time` format without relying on an
optional validator dependency. Calendar checks cover requests, response range and
occurrence facts, and cursor ordering facts. Available event cores/occurrences require
`event_start`; agenda requires its matching primary anchor, including `task_due` for
tasks. Defer-only task detail and unavailable/unscheduled states remain valid.
Added 15 positive/negative fixtures (68 total) and semantic regression checks; refreshed
only the new v2 shared-schema pin. This is a manual contract patch, not a clean audit
verdict or runtime conformance result. Focused re-audit remains pending.
Verification: 77 tests and 266 subtests passed across new contract checks and the
existing web/runtime/domain fixture suites. Ruff, companion Markdown links and
`git diff --check` passed. No new audit, commit or push was performed.

**Focused machine-contract recheck staged (2026-09-17):** At operator request,
prepared `whetstone_runs/independent-activity-read-machine-contract-audit-002/` for
reviewer-only Sol/consistency verification of the three audit-001 fixes and directly
introduced regressions. Notes enumerate 32 exact outgoing inputs, including prior
feedback, affected schemas, parent/companion authority, test/pin/manifest evidence,
all 15 new fixtures and one unchanged baseline response. The approved manual patch
remains uncommitted; preparation records its actual source hashes against base
`f9a301b`, not a clean-checkpoint claim. Local preflight: 15 focused tests and 144
subtests passed; diff hygiene passed; bundled CLI `0.154.0-alpha.6.2` verified.
At preparation, outgoing approval was pending; no nested reviewer, source patch,
commit or push was run during preparation.

**Focused machine-contract recheck completed (2026-09-17):** After explicit
approval of the exact inventory, ran reviewer-only `audit-change` with
`gpt-5.6-sol`, built-in consistency profile and bundled CLI `0.155.0-alpha.2.6`.
Audit-002 returned `pass`, `boundary_preserved=true`, with zero blockers, majors,
minors or nits. The three prior findings were not raised again; no further action
was recommended within the focused scope. Report:
`whetstone_runs/independent-activity-read-machine-contract-audit-002/change_audit/change_audit_report.json`.
All 31 source files remained byte-identical to preparation, and all 32 manifest
input hashes matched, including the approved notes. Local focused verification
again passed 15 tests and 144 subtests. Review assessed the supplied contract,
schemas and oracle evidence, not runtime implementation or unsupplied fixtures;
it is not a convergence or deployment claim. No Editor, source patch, commit or
push was performed. The manual fixes remain ready to checkpoint before runtime
implementation.

**Runtime planning checkpoint (2026-09-18):** Updated this live task and the existing
implementation plan against the ratified read spec, machine companion, registry,
projection/normalization/cursor/pin artifacts, IR matrix and Kinflow handoff. The plan
keeps one backend delivery, with explicit verification and later deployment/consumer
gates; it does not add a new normative contract. No runtime, schema or fixture changes,
staging action, commit or push were performed by this planning update.
Verification: agent-documentation and independent-read contract suites passed
22 tests and 223 subtests; both planning documents' local links/heading anchors
and `git diff --check` passed. README still points to the authoritative read spec
and companion and correctly labels runtime implementation as pending.

**First runtime foundation slice (2026-09-18):** Added internal
`src/spine/web/read_contracts.py`, `read_context.py` and `read_projection.py`.
They load an explicitly supplied offline pinned bundle, assert Gregorian formats,
match normalization vectors, open dedicated read-only SQLite assembly snapshots,
enforce separate core/optional budgets, select owner/grant-authorized candidates,
and assemble closed current core/time projections. Source time is authorized before
follow-binding resolution; stale or denied source facts expose only unavailable time.
Snapshot-mode tasks retain independently readable time. This is not a public response
boundary: fresh release authorization/source fences are intentionally still required.

**Query/index assessment for this slice:** Existing owner/grantee indexes support
candidate admission; detail primary keys, unique seed-anchor lookup and the recurrence
revision index support rooted recurrence-header selection. Factored the canonical
recurrence header loader to traverse only the requested item's indexed detail history
instead of scanning all recurrence sets. Canonical revision precedence is unchanged,
including after item-version edits; both new projection and existing canonical loads
use that shared reader. `EXPLAIN QUERY PLAN` and old/new selection comparisons cover
the lookup. No DDL, schema version or migration is needed for these primitives.
Optional-section and complete agenda/source-fence query paths still need their own
task-local query assessment as they are implemented; this is not a whole-slice
no-migration claim.

**Boundary:** No v1 permission, route, registry or schema-pin changes; no v2 routes or
implemented-version declarations; no new packaged contract advertisement. Tests use
the checked-in source bundle explicitly. No live data repair, deployment, commit or
push. Existing uncommitted planning updates are preserved.

**Second internal assembly slice (2026-09-18):** Added `read_sections.py` and
`read_assembly.py`. All eleven fixed detail states and all four agenda singleton
states now assemble authorized rows before sorting/counting. Available null/empty,
not-requested, and generic incomplete optional failures remain distinct. Collection
assembly retains the whole bounded authorized set for later pagination; it does not
issue cursors or pretend a truncated set is exhausted. Agenda summaries retain their
underlying authorized rows for subsequent source hashing. Optional permission traversal
uses a separate resource reserve and does not consume root admission capacity.

Relations probe authorized endpoint pairs, including mixed owners with explicit read
grants; opaque relation metadata is fail-closed. Bindings expose current revision
headers only after both endpoints and the relation are disclosable. Profiles require
catalog/pinned-revision/application authority. Policies, historical work and attempts
share recipient/route/catalog predicates; only attempt evidence counts toward attempt
status. Approved current targets, self subject roles, proven item-local inline places
(including replacements), and authorized creation receipts use closed allowlists.
Undefined shared-place/foreign-subject authority and unknown protected receipt
references yield null/empty authorized subsets, not inventories of hidden resources.
No provider, rendering, raw receipt, source provenance or owner payload is returned.

Canonical occurrence expansion and overlays reuse the existing engine and decorator;
IDs/keys remain byte-for-byte canonical. Agenda reuses canonical recurrence ranges,
anchor resolution and ordering, without the v1 helper's binding hydration. It prepares
resolved entries first and separately ordered unplaced cores with whole-candidate
coverage; no last-known deadline is used. Non-temporal filters precede expansion.
Read-only ledger snapshots remain the only execution context; reads create no receipts,
work, provenance, repairs or other durable effects.

**Query/index evidence:** Actual `EXPLAIN QUERY PLAN` showed an all-status relation
scan and broader target/route probes for bindings/work. Schema 15 adds four indexes:
`independent_read_relation_endpoints_idx`, `independent_read_binding_endpoints_idx`,
`independent_read_work_policy_idx`, and `independent_read_creation_receipt_idx`.
Fresh initialization, normal migration, version declaration and the generated DDL
manifest are updated. A schema-14 upgrade test preserves every domain/evidence row
and ledger identity. Actual optional and agenda/recurrence SQL plans are regression
checked. Agenda inspection also exposed SQLite selecting the resource-kind grant
index; candidate discovery now uses explicit subject/group grantee probes through
existing indexes. Canonical recurrence child reads remain revision-indexed.

**Unadvertised contract correction:** Real engine occurrence keys exceed the generic
256-character resource-ID limit. Added a dedicated opaque key type to the projection
and matching cursor ordering slots, and updated only the v2 schema pins. Canonical
identities are neither shortened nor re-derived; response/cursor byte ceilings remain.
V1 pins, registry, HTTP routes, CLI/write authorization, replay and delivery semantics
are unchanged. This checkout requires schema 15 locally; no staging database was
migrated, and no push, deployment or public capability activation was performed.
The operator subsequently authorized a local commit of this completed internal slice.

**Next implementation:** Add fresh source/authorization release fences and authorized
snapshot hashing, then integrate the v2 cursor protocol and combined stream/section
pagination. Full HTTP/package/capability activation and IR-01–IR-16 HTTP/Kinflow
acceptance remain subsequent work. Internal assembly tests do not close those gates.

**Second-slice verification:** The new assembly suite adds 26 real-ledger tests for
mixed ownership, hidden graph growth, the recurring-event/unowned selected-occurrence
follower, protected catalog/route/receipt evidence, all section states, independent
optional failures/budgets, stale/denied source time, resolved/unplaced candidates,
recurrence exceptions, canonical identities, DST, date/windows, terminal/archive
lifecycle, read-only behavior, actual query plans, and index-only migration. Combined
assembly/foundation/contracts/migration/identity command:
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_foundation.py tests/test_independent_activity_read_contracts.py tests/test_ledger_migrations.py tests/test_ledger_identity.py`
passed **80 tests and 158 subtests**. The final full command
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q` passed
**552 tests and 567 subtests**. `.venv/bin/ruff check .`, `git diff --check`, and
changed-document local-link checks passed. No implementation blocker remains for
this internal slice; public release authorization and HTTP/Kinflow acceptance are
explicitly not claimed.

**Foundation verification:** `tests/test_independent_activity_read_foundation.py`
adds 19 tests covering exact vectors and calendar rejection, pin failure, budget
separation, read-only snapshots, root-first guards, the unowned-follower regression,
stale/denied source time, snapshot independence, unscheduled/defer-only tasks, grant
time boundaries, canonical recurrence lookup parity/query plans, DST/window projection,
v2 error mapping and non-advertisement. Full command
`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q` passed
526 tests and 567 subtests. `.venv/bin/ruff check .`, `git diff --check`, and planning
document link/heading checks passed. No new Whetstone run or staging claim.

## Facet delivery — implementation sequence

The operator selected delivery planning on 2026-09-26 after the clean integration
recheck and authorized SPINE-027 implementation on 2026-09-27. Slice A is complete;
SPINE-028 then SPINE-029 are the follow-ons. Design/review history remains below under
SPINE-008–009; live delivery status belongs to these entries.

### SPINE-027 — Implement facet persistence and all-writer foundation

**Status:** Done — internal persistence Slice A implemented and verified on 2026-09-27;
runtime 0.6.2 / ledger schema 16. The diagnostic's dry-run and all-writer activation findings
received a targeted amendment, local verification and a bounded buildability recheck
on 2026-09-26: pass, zero findings, boundary preserved. This delivers storage,
migration and all-writer proof only; public facet commands and web activation remain deferred.
**Dependencies:** SPINE-008 review complete, Decision 0004 ratified, storage v1.0
accepted, integration v0.7 focused recheck passed with zero findings. No unresolved
product decision is currently identified for this internal persistence slice.
The operator subsequently requested the feature-specific diagnostic sweep recorded
below; its concrete findings are manually addressed in logical v0.8 and storage
Section 5.1. This does not negate the
completed focused recheck or reopen deferred system-wide reviews.

**Scope:** Pure canonical validators/decoders; all eight accepted tables and exact
constraints/indexes/triggers; fresh-schema and migration/object-manifest parity;
historical empty-marker backfill; transaction-owned catalog/snapshot/reference/index
primitives; every existing item-version producer's marker/copy-forward participation;
explicit deep verification and fixture-only backup/restore proof. Choose the next
available schema number at implementation. No public facet command or web activation.

**Acceptance:** Persisted FS-01–05, storage portions of FS-06–09, FS-10–11; existing
commands preserve seeded nonempty facets and original evidence; atomic failure leaves
shell/support/index/audit/receipt facts coherent; immutable history remains decodable;
candidate-rooted query plans and budgets hold with unrelated history. Routine preflight
remains bounded. Publish the closed producer/call-site/finalizer/test inventory and
prove shared transaction-final enforcement, including negative bypass/missing-marker
tests, before activating the new schema even with public facet commands disabled.
Record a per-FS test/remaining-gate map, not a blanket completion claim.
The migration and all-version-writer support must ship together; no live DB changes.

**Completion evidence:** [storage implementation handoff and per-FS map](FACET_STORAGE_IMPLEMENTATION.md)
and [closed producer inventory](../src/spine/ledger/facet_writer_inventory.v1.json).
The eight-table schema/migration, pinned codecs, historical references/current typed
projections and shared transaction finalizer are implemented. Every inventoried
producer executes against both empty and eight-entry persisted snapshots. Missing
marker/finalizer/touch, stale projection and unregistered/early-commit paths roll back;
CLI and web mutations share the outer boundary through audit and receipt persistence.
Migration tests preserve predecessor rows/identities and extra audit objects, cover
all four item types/history, and prove rollback plus consistent backup restore.
Candidate-rooted text/integer probes stay bounded with 100000 unrelated items and
10000 unrelated versions. No public facet contract, CLI command or web route is enabled.

**Verification:** full suite `PYTHONPATH=src:../tickerd/src .venv/bin/pytest -o addopts='' -q --tb=short`
passed **701 tests and 930 subtests**; Ruff, compileall, focused strict typing on the
four new/extended facet transaction modules, 68 local document links and diff hygiene
passed. Repository-wide mypy is not clean outside those focused modules. Wheel-build
verification could not run because this venv lacks `setuptools.build_meta`; package
assets are explicitly declared but installed-wheel verification is not claimed.
No live DB mutation, Whetstone run, commit, push or deployment. Prior audit-tracking
working-tree edits were preserved.

### SPINE-028 — Implement facet commands and notification continuity

**Status:** Done — implemented and verified 2026-09-27; not committed or deployed.
SPINE-027 storage dependency is complete; its uncommitted implementation is preserved.
**Scope:** All eleven reserved commands through shared handlers/trusted-local CLI;
exact validation, identity, changed/no-op/replay and transaction semantics; bounded
reads and configured authenticated cursors; stable-intent notification lookup and
facet-only verified retention; operator docs, matching package/registry declarations.

**Acceptance:** Public-command FS-07–09 and FS-12–13, including real work/attempt races,
multiple facet copy-forwards, recurring/follow_source behavior, no duplicate sends,
and the trusted-local flight lifecycle. Verify first-page/continuation source races,
no durable read evidence and concrete item-type rejection. Do not expose item updates
before work-continuity proof, and do not add HTTP routes or frozen schedule fields.

**Completion evidence:** Runtime 0.7.0 / schema 16 implements all eleven commands,
six-write changed/no-op/replay/rollback previews, exact schema pins and explicit upgrades,
historical readback, owner-rooted indexed equality queries, and private-config signed
cursors with shared deadline/VM/resource bounds. The packaged writer inventory includes
the explicit facet producer. Facet-only equivalence is checked before commit; policy
resolution uses stable item/intent across successive copies while checking original
policy meaning. Existing work, attempts and rendering evidence are not rewritten.

`tests/test_facet_commands.py` proves the public flight/reference lifecycle, explicit
schema adoption, all six preview/replay branches, eight-entry retention, concrete-type
rejection, fresh no-op reference validation, atomic rollback, queued/in-progress/retry/
terminal work retention, recurring provenance, follow-source behavior and rendering/
attempt replay safety. `tests/test_facet_runtime_reads.py` proves real two-connection
source races and write contention, cursor/key/generation/expiry failures, candidate and
shared-budget failure without partial pages or durable evidence, protected CLI config,
and no whole-ledger preview copy. The large-ledger plan test now exercises the public
query against 100000 unrelated items and 10000 unrelated historical versions.

Verification: full pytest **721 tests and 941 subtests passed**; subsequent focused
command/integration/package-sync checks, including the added malformed-enum regression,
**32 tests and 158 subtests passed**. Ruff, compileall, strict focused mypy on all four
new runtime modules, packaged-schema synchronization, relative file-link checks and
`git diff --check` passed. Installed-wheel verification remains unavailable because
this venv lacks setuptools; the declared package assets and generated copies were
checked, but no installed-wheel result is claimed. See [operator handoff](FACET_COMMANDS.md).
No live database, Whetstone job, commit, push or deployment. No web route activation;
permission-sensitive resolver/disclosure proofs remain SPINE-029, not claimed here.

### SPINE-029 — Integrate permission-enforced facets and web admission

**Status:** Done — implemented and locally verified 2026-09-27; checkpointed with
the SPINE-029 implementation commit by operator request. Not deployed.
SPINE-028 is checkpointed in `335c973`; the working tree was clean at start.
**Scope:** Existing permission model's reviewed catalog extension, item/nested-reference
resolvers, six-write receipt-disclosure replay matrix, bounded protected cursors and
release fences. Codify/test exact web registry/admission/package declarations before
enabling routes; surface any unresolved interface decision in its owning spec.

**Acceptance:** Persisted permission portions of FS-06–09 and adversarial identity,
revocation, hidden-reference, replay, grant-transition and cursor-race tests. Retained
read access permits compatible receipt replay without fresh write rights; lost read
denies without leakage. No implicit shared-location resolver; reference-rich flight
authoring stays trusted-local. Existing web contracts/behavior remain unchanged unless
an explicit successor is required and codified. Kinflow adoption is separate work.

**Completion evidence:** Runtime **0.8.0 / ledger schema 17** adds all eleven
permission-enforced facet routes in the separate `spine.trusted-web-facets.v1`
family and exact `spine.trusted-web-facet-registry.v1` registry. Existing v1 command
and v2 independent-read registries, schemas and schedule projections are unchanged.
The [admission leaf](../specs/facet-web-admission.md), closed envelopes/discovery/error
schemas, wire fixtures, compiled resolver mappings and generated package digest pins
were codified before activation. The shared canonical handlers retain domain/audit/
idempotency semantics; the adapter owns protected receipt attribution and release checks.

Schema 17 extends only the existing grant vocabulary with `facet_schema`, retaining
root owner revision 1 and catalog.read/use semantics. Local provisioning `.v2`
coexists with frozen `.v1`; neither is a web endpoint. The pinned predecessor
manifest is byte-identical to the committed schema-16 manifest. Real upgrade tests
preserve grant revisions/operations, facet definitions, all unrelated rows, custom
indexes/triggers and FK mode; injected post-DDL failure restores schema/data atomically.

`tests/test_facet_web.py` covers all six writes' changed/no-op replay branches,
new-session replay, admin demotion and retired catalogs, current-read/lost-edit,
lost-read/foreign/local receipts, hidden references, inherited pinned-definition
readback, foreign catalog/item grants, system-mutation denial, complete access-proof
overflow, grant starts/expiry/revocation, fresh release/source races, cursor expiry/
key/generation/selection/ledger binding, actor/Origin/route boundaries and zero durable
read/replay effects. Proof/release share one VM/time/resource budget. Protected
references remain scalar/self-subject only; reference-rich flight authoring remains local.

Verification: **741 tests + 952 subtests passed** in the full pytest suite;
subsequent focused facet admission/contract/migration checks **19 passed** after the
final shared-budget refactor. Ruff, compileall, generated-contract/package parity,
changed Markdown file links and `git diff --check` passed. Configured strict mypy
and source-discovery strict mypy both passed **42 core/ledger files** (Python 3.14.6,
mypy 2.3.0, target 3.12). This included a behavior-neutral `policies`/`policy` variable
distinction fixing the prior facet-continuity branch's type inference.
Installed-wheel verification is still unavailable because this venv lacks setuptools;
source/package asset parity is verified, not an installed wheel.

[Consumer/operator handoff](FACET_WEB_API.md) covers migration/rollback, exact paths,
grants, retry and private cursor provisioning. No live ledger changes, Whetstone run,
commit, push, deployment, Kinflow UI changes or new authentication guarantees.

**Shared delivery guidance:** [Facet implementation sequence](IMPLEMENTATION_PLAN.md#planned-delivery-versioned-archetype-facets-spine-027029).
The owning [logical contract](../specs/archetype-facets.md),
[storage leaf and FS families](../specs/archetype-facet-storage.md), and
[integration companion](../contracts/archetype-facet-integration.v1.json) remain
authority for all three tasks. These checkpoints do not require separate staging
deployments or reopen deferred resilience, recipes, observations or pack-v2 work.

### SPINE-008 — Close the focused facet machine-contract recheck

**Status:** Done (2026-09-12; status records reconciled 2026-09-24).
**Dependencies:** None for the focused contract review.

**Outcome:** The focused reviewer-only recheck returned
`pass_with_minor_clarification` with `boundary_preserved=true`, zero blockers or
majors and one minor clarification confined to wording in the audit notes. Schema
creation correctly has one changed replay branch; the other five writes have changed
and no-op replay branches. The source schemas, fixture manifest, fixtures and focused
assertions were aligned, so no source-contract patch or additional model call was
required. This closes the recheck gate without claiming runtime conformance,
implementation readiness or convergence.

**Acceptance:** Recheck the manually patched replay-response alignment and
test-dependency scope findings against the current facet bundle; retain the result and
resolve any resulting concrete findings. Update the facet draft's recheck status
without representing static fixtures as runtime proof. This task does not start an
additional broad audit campaign or authorize facet implementation.

**Sources:** [Facet draft and machine-contract status](../specs/archetype-facets.md),
[facet roadmap](IMPLEMENTATION_PLAN.md#future-horizon-archetype-facets-and-workflow-recipes).

### SPINE-009 — Settle facet implementation gates

**Status:** Done (2026-09-27) — Decision 0004 logical architecture ratified 2026-09-24;
physical storage design accepted as v1.0 on 2026-09-25; permission/cursor/work contracts
codified and focused-recheck passed 2026-09-26. Contract review is closed; remaining
executable delivery gates were mapped to and completed through SPINE-027–029. The
subsequent operator-selected diagnostic reported one blocker and one major; the v0.8
manual amendment addresses
both with local spec/contract verification; the subsequent bounded buildability
recheck passed with zero findings and boundary preserved on 2026-09-26. SPINE-027
closed persistence, migration and all-writer proof; SPINE-028 closed commands, cursors
and notification continuity; SPINE-029 closed persisted authorization and web admission,
including the executable flight-details proof. This closes the gate tracker without
expanding the accepted facet boundary or claiming deployment.
**Dependencies:** SPINE-008 is complete. The deferred resilience campaign is not a
blanket prerequisite.

**Selected contract-closure pass (2026-09-26):** Completed specification/codification: specify the remaining
permission resolver, authenticated cursor and facet-only notification-work contracts;
align machine artifacts and test-only oracles. Preserve the uncommitted physical
ratification, accepted storage layout and current runtime/route advertisements. No
runtime implementation, new audit, commit or push is selected by this pass.

**Ratified boundary:** Spine owns a generic registry of immutable facet-schema
revisions, explicit archetype bindings and canonical versioned item-facet values.
Facets remain descriptive and cannot override core coordination semantics. The accepted
physical layout combines relational identity/history and references, canonical JSON
definitions/values and derived current-only typed indexes. Neither ratification
authorizes runtime implementation.

**Acceptance:** Decision 0004, physical storage and focused integration review are
resolved; delivery planning is complete. Close the remaining DDL/object-manifest,
migration, all-writer, persisted authorization, cursor concurrency and attempt-start
gates through SPINE-027–029 and record the executable flight-details proof. Keep
workflow recipes and external observations separate; do not advertise runtime facets
from draft schemas or static fixtures.

**Sources:** [Facet gates](../specs/archetype-facets.md),
[Accepted physical storage](../specs/archetype-facet-storage.md),
[Decision 0004](../specs/decisions/0004-versioned-item-facets.md).

**Physical-storage specification checkpoint (2026-09-24):** Added
[archetype-facet-storage.md](../specs/archetype-facet-storage.md) as the draft physical
leaf beneath the logical facet specification. Compared relational, JSON, EAV and
hybrid layouts; selected canonical definition/value JSON with relational history and
references plus current-only typed query rows. Defined table/constraint inventories,
all-version snapshot markers/copy-forward, historical decoding, atomic audit/receipt
and index maintenance, migration/rollback, bounded query plans, concurrency and FS-01–13
future verification oracles. The previously absent
[STORAGE_ATOMICITY_SPEC.md](../specs/STORAGE_ATOMICITY_SPEC.md) is a small Spine-wide
authority/delegation consolidation, not a new transaction model or resilience campaign.

**Initial decisions raised (resolved by the confirmation below):** Location reference activity lacks a current location-status
model; system query-owner semantics do not map to current item-access ownership;
logical Section 9's retained draft product-choice list needs explicit disposition.
Permission resolvers, authenticated cursors, notification-work freshness, physical
design review and executable migration/behavioral fixtures remain implementation gates.
No runtime/schema/machine-contract change, Whetstone run, commit, push or deployment
was performed. Existing SPINE-015 closure, facet recheck reconciliation and Decision
0004 ratification edits were preserved.

**Specification verification:** Focused facet structural/pure-vector and agent-documentation
checks (`PYTHONPATH=src:../tickerd/src .venv/bin/python -m pytest -o addopts='' -q
tests/test_archetype_facet_contract_fixtures.py tests/test_agent_documentation.py`)
passed 25 tests and 170 subtests. Checked all 62 local Markdown links/anchors across
the two new specifications and three amended documents; none were broken.
`git diff --check` passed. These checks do not prove the future FS storage fixtures.
The implementation-plan and Decision 0004 files remained byte-identical to their
pre-task uncommitted contents; the SPINE-015 closure and recheck status edits remain.

**Operator scope confirmation (2026-09-24):** Resolved all three questions above.
Locations require existence and applicable read permission, not a new retirement
lifecycle; active/inactive lifecycle checks remain specific to subject references.
Item-facet query owner is subject/subject_group only, independently of schema catalog
ownership (which still supports system). Confirmed scalar-only fields, same-owner
bindings, optional item/series-level facets and separate item creation/attachment.
Updated the logical/storage drafts and Decision 0004 consistently; physical storage
remains draft and the engineering gates remain open. Aligned the draft query and
reference-state schemas, example/vector expectations and structural tests, retaining
offline packaged schema parity without adding handlers or advertised capabilities.
No database-schema or runtime-code changes, Whetstone run, commit or push.

**Confirmation verification:** Facet contract, agent documentation, trusted-web contract
and implemented-declaration suites passed 42 tests and 207 subtests. Focused Ruff,
offline contract-copy parity, local documentation links and diff hygiene passed.
These are structural/consistency checks, not facet runtime or storage conformance proof.

**Storage audit preparation (2026-09-25):** Prepared
[archetype-facet-storage-contract-audit-001](../whetstone_runs/archetype-facet-storage-contract-audit-001/audit-notes.md)
as a single reviewer-only `audit-change` using the built-in buildability profile.
The exact outgoing inventory is the notes plus twenty source/reference/evidence files.
Objectives cover relational feasibility, immutable decoding/copy-forward, atomicity,
migration/rollback, indexed bounded queries and preservation of confirmed scope.
Awaiting explicit transmission approval; no reviewer call, source-spec change or
implementation occurred during preparation. Existing deferred engineering gates remain.

**Storage audit outcome (2026-09-25, supersedes preparation's pending approval):**
The operator explicitly approved the notes, all twenty sources, built-in buildability
profile and generated copies for `gpt-5.6-sol`. Completed one reviewer-only
`audit-change` using Codex CLI `0.155.0-alpha.16.3`: `pass_with_minor_clarification`,
`boundary_preserved=true`, zero blockers/majors and one minor. Finding
`fb_query_response_owner_scope` is verified: item.facets.query requests use itemOwner,
but responses still use broader owner and therefore admit impossible system-owner
results. Recommended next action is a manual response-schema correction plus a
negative contract fixture (and packaged-copy parity); it has not been applied.
All twenty sources and the approved notes were unchanged after review; manifest
input hashes match. No Editor, convergence claim, source patch, implementation,
commit or push. Physical ratification and the other facet engineering gates remain open.
Evidence: [report](../whetstone_runs/archetype-facet-storage-contract-audit-001/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/archetype-facet-storage-contract-audit-001/change_audit/change_audit_feedback.json).

**Storage audit minor manually patched (2026-09-25):** Corrected
`fb_query_response_owner_scope`: the query response now uses itemOwner, matching its
request and normative subject/group-only item ownership. Added the registered negative
`invalid_query_response_system_owner.json` fixture and extended owner-scope assertions
to cover both requests and responses while preserving system-owned schema catalogs.
Synced the packaged response schema. Focused facet/web contract and implemented-version
declaration checks passed 35 tests and 129 subtests; Ruff, package-copy parity and
`git diff --check` passed. No runtime/database changes, new audit, commit or push.
The original audit artifacts remain unchanged; local regression verification is not
a new reviewer verdict or closure of the remaining facet engineering gates.

**Physical design ratified (2026-09-25):** The operator accepted the hybrid storage
leaf as v1.0 after the bounded buildability audit and manual minor patch. Aligned the
logical owner's delegation, Decision 0004, specification index and implementation
roadmap. The original dated checkpoints above retain their historical status. The
Spine-wide persistence parent remains a draft authority consolidation; this acceptance
does not ratify it wholesale. Exact DDL/manifests/migration oracles, permission resolver
mappings, authenticated cursor/source-snapshot rules, facet-only work freshness and
all item-version writer proofs remain engineering gates. No runtime, schema-version,
advertised capability, new audit, commit or push is included in this ratification.

Ratification verification: focused facet/web contracts, implemented-version declarations
and agent-documentation tests passed (42 tests, 208 subtests). All 81 local Markdown
links/anchors across the six edited files resolved; `git diff --check` passed. These
are specification/structural checks, not proof of the unimplemented storage runtime.

**Integration contracts codified (2026-09-26):** Logical spec v0.6 closes the three
remaining contract definitions without changing accepted physical layout or advertising
runtime capabilities. Added `archetype-facet-integration.v1.json`, a closed cursor
payload schema, permission/cryptographic/work decision vectors and a retained-work
receipt fixture. Updated registry, fixture manifest, packaged schema copies and the
permission/notification/command owners. Cursor reads use bounded complete snapshots,
separately provisioned per-ledger signing configuration and no durable cache/receipts.
Schema publication does not migrate item values or work. Facet-only item edits verify
notification semantic continuity transactionally, preserving work and attempt evidence.

Implementation findings captured, not patched in runtime: current attempt-start policy
lookup uses only one copy-forward hop; it must resolve stable intent across successive
facet edits and retain all semantic checks. Existing follow_source source-version
invalidation is preserved: editing a source event can stale dependent bindings until
their ordinary reconciliation. No recursive task mutation is added. Existing-location
sharing authority is not defined for the permission-enforced web subset, so that path
remains fail-closed; reference-rich flight authoring is available to the trusted-local
slice. Broader reference sharing is separate product scope, not an invented permission.

Next: bounded review of this amendment, then executable migration/manifests and the
implementation plan/test matrix. Static oracles are not persisted behavior evidence;
SPINE-009 remains in progress until the remaining delivery gates are handled. No runtime
implementation, Whetstone run, commit or push was performed in this pass.

Contract-closure verification: focused facet integration/wire fixtures, trusted-web
contracts, implemented-version declarations and agent-documentation checks passed
50 tests and 255 subtests. Ruff on both facet test modules, packaged-schema parity,
all 94 local Markdown links/anchors across the nine changed documents, and
`git diff --check` passed. The 2026-09-25 uncommitted ratification edits were preserved.

**Checkpoint and bounded-audit preparation (2026-09-26):** Committed the cohesive
ratification/integration amendment as `28c7f1c` after repeating the 50-test/255-subtest
verification, Ruff, packaged-schema parity and diff checks. No push. Prepared
[archetype-facet-integration-contract-audit-001](../whetstone_runs/archetype-facet-integration-contract-audit-001/audit-notes.md)
as one reviewer-only audit-change using the built-in buildability profile and proposed
Codex model gpt-5.6-sol. The notes name thirty exact source inputs, focused reviewer
questions and preservation boundaries. Awaiting explicit authorization for those inputs,
the notes, built-in profile context and generated copies; no nested reviewer invoked.

**Integration amendment bounded audit completed (2026-09-26):** The operator explicitly
approved the thirty-file inventory, notes, built-in buildability profile and generated
copies for gpt-5.6-sol. Ran one reviewer-only audit-change with that requested model
(recorded in audit_manifest.json), Codex CLI 0.155.0-alpha.16.4, timeout 600 seconds.
Result: needs_revision, boundary_preserved=false, zero blockers, two majors, one minor.
Verified the findings against the supplied source: concrete item-type eligibility on
fresh set is implicit rather than closed; replay authority is not mapped per write
command; first-page source-change/release failure lacks an exact outcome. The authority
finding accounts for the boundary flag; no physical-layout redesign was requested.

Recommended next action is a targeted manual spec/companion/fixture patch, then focused
recheck; no patch was applied by this audit. All thirty sources and notes remained
byte-identical to the launch hashes; source files match commit 28c7f1c. Manifest input
hashes and audit-brief hash were verified. Feedback's model self-label says gpt-5; the
executed CLI selection and audit manifest record the approved gpt-5.6-sol. No Editor,
convergence claim, runtime change, commit or push. Evidence:
[report](../whetstone_runs/archetype-facet-integration-contract-audit-001/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/archetype-facet-integration-contract-audit-001/change_audit/change_audit_feedback.json).

**Targeted integration manual patch (2026-09-26):** Addressed all three verified
findings in logical spec v0.7, the existing integration companion and pure vectors.
`fb_item_type_compatibility` now requires concrete item type in both pinned revision
sets for every fresh set, including same-value no-ops; incompatibility is wrong_item_type
at item_id. Remove, retained copy-forward and compatible replay remain exempt.
`fb_replay_authority_matrix` now maps all six writes to current receipt read authority,
same initiating account/subject and explicit nested disclosure checks, without renewed
write/admin/use rights. Original create has only changed replay; the other five cover
changed and no-op receipts. Foreign identity, revoked read and release-time revocation
have closed safe outcomes. `fb_first_page_release_race` now permits one snapshot build
and no internal retry: source-only first-page races are environment_failure locally /
access_changed on web; continuation races remain stale_cursor. Neither returns partial
results/cursors or writes durable evidence; authority and capacity checks take precedence.

Added the incompatible-item failure fixture and manifest entry, plus decision vectors
and test-only oracles for all three closures. Focused facet, trusted-web, implemented
declaration and agent-documentation checks passed **53 tests and 354 subtests**. These
are machine-contract checks, not persisted authorization, concurrency or delivery proof.
Ruff, packaged web-contract parity, **87** local Markdown file links and diff hygiene
also passed.
The ratified physical storage design, notification-continuity rules, runtime files,
implemented registries and prior audit artifacts remain unchanged. The pre-existing
backlog audit record is preserved. No runtime implementation, new Whetstone run,
commit or push; the prior audit verdict remains historical, not upgraded to a pass.

**Integration focused recheck prepared (2026-09-26):** Staged
[archetype-facet-integration-contract-audit-002](../whetstone_runs/archetype-facet-integration-contract-audit-002/audit-notes.md)
against checkpoint 4060e89, including manual patch 2256a90 and the create-only-changed
replay clarification. One reviewer-only audit-change is proposed with buildability
and Codex gpt-5.6-sol. The exact twenty-one-file inventory narrows review to the prior
three findings and directly introduced regressions; no runtime sources or physical
storage redesign are included. Awaiting explicit authorization for those inputs,
notes, built-in profile and generated copies. No nested reviewer has been invoked.

**Integration focused recheck completed (2026-09-26):** The operator approved the
exact twenty-one files, notes, built-in buildability profile and generated copies.
Ran one reviewer-only audit-change using Codex gpt-5.6-sol, timeout 600 seconds.
The app update relocated the bundled executable to Resources/codex-cli/bin/codex;
recorded CLI version 0.158.0-alpha.2.1. Both manifest and feedback identify the
approved model. Result: **pass**, **boundary_preserved=true**, zero blockers,
majors, minors or nits. No residual or patch-induced issue was reported for the
concrete item-type, six-write replay-authority or first-page race closures. Feedback
contains no separate per-finding narrative; closure is the bounded pass against the
explicit recheck questions, not additional individual reviewer attestations.

Verified all twenty-one inputs and notes remained byte-identical to launch hashes,
the exact manifest inventory and normalized hashes, and report/feedback brief hashes.
No source specification, contract, fixture or runtime changes; no Editor, convergence
claim, commit or push. This closes the focused integration review gate, not the
remaining runtime/persistence/authorization/concurrency acceptance tests. Evidence:
[report](../whetstone_runs/archetype-facet-integration-contract-audit-002/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/archetype-facet-integration-contract-audit-002/change_audit/change_audit_feedback.json).

**Implementation planning checkpoint (2026-09-26):** Updated the existing delivery
plan and opened SPINE-027–029 with concrete scope, dependencies, release fences and
FS-family acceptance. Next is the cohesive persistence/all-writer slice; command/work
and protected web integration follow. Removed the stale roadmap statement making
facets subordinate to the deferred resilience campaign. Preserved prior audit evidence
and the distinction between a clean review and unimplemented runtime proofs. No source
spec/contract/runtime changes, migration, reviewer run, commit or push in this update.
Planning verification: agent-documentation and implemented-declaration tests passed
**9 tests and 79 subtests**; **117** local Markdown file/heading links and diff hygiene
passed. These checks verify documentation alignment, not facet implementation.

**Facet-family diagnostic sweep prepared (2026-09-26):** At explicit operator request,
staged [archetype-facets-diagnostic-sweep-001](../whetstone_runs/archetype-facets-diagnostic-sweep-001/sweep-notes.md)
against checkpoint ddbb96c. It will review structural integrity, determinism and
operability once each using Codex gpt-5.6-sol on the same logical-spec seed plus
accepted storage and explicit dependency/machine-contract references. This is a
reviewer-only diagnostic, not another targeted recheck, Editor workflow or convergence
run. Accepted product/architecture boundaries are fixed; concrete inconsistencies may
be reported for manual consideration. Deferred resilience and other horizons stay out.

Prepared an exact thirty-four-source inventory, five run-control/seed files, source
hashes and supported configuration. Local validation passed: source checkpoint/seed
parity, exact reference inventory, the three-profile scheduler, disabled convergence
and a fail-closed unused Editor executable. Advisory configured context is about
0.7 MB / 177000 estimated tokens per pass; not actual model usage. Awaiting explicit
approval of the listed files, built-in reviewer/profile/rubric context and generated
copies. No reviewer, runtime changes, source-spec edits, commit or push occurred.

**Facet-family diagnostic completed (2026-09-26):** The operator explicitly approved
the thirty-four sources, five controls/seed files, built-in reviewer/profile/rubric
context and generated copies. Three reviewer-only passes completed with Codex
gpt-5.6-sol: structural integrity zero findings; determinism one blocker
fb_dry_run_response_contract; operability one major fb_operability_r3_001; no minors
or nits. Aggregate advice is run_bounded_synthesis, not authorization for an Editor.

Verified the dry-run conflict with the inherited command contract and local read-only
schema probes: supplied success, replay and failure fixtures reject dry_run=true.
The all-writer finding concerns a closed inventory and activation/precommit proof;
the storage contract already requires checks on every writer and SPINE-027 already
requires call-site inventory/coverage. Tighten that gate without a global readiness
scan or a physical-layout redesign. Runtime enumeration remains implementation work.
Recommended next step: targeted manual contract/fixture amendment and explicit writer
activation acceptance, then focused verification. No source patch has been applied.

All 39 approved inputs remained byte-identical, and each round used the same seed.
No Editor, source mutation, implementation, commit or push. All three CLI headers and
invocation telemetry record gpt-5.6-sol; structural/operability feedback self-label
gpt-5, a retained metadata discrepancy. CLI-reported total usage: **411324 tokens**,
without a cost or input/output/cache breakdown. This is neither convergence nor
runtime proof. Evidence: [sweep report](../whetstone_runs/archetype-facets-diagnostic-sweep-001/rounds/profile_sweep_report.md)
and [manual assessment](../whetstone_runs/archetype-facets-diagnostic-sweep-001/manual-assessment.md).

**Facet diagnostic manual amendment (2026-09-26):** At operator direction, logical
v0.8 now defines all six writes' dry-run branches, deterministic would-be identities,
no durable writes/sends, handler-level response markers and item-update preview
reconciliation=false with equivalence validation still required. Response/failure
schemas, the integration companion, golden previews and negative fixtures agree.
Storage Section 5.1 now requires a closed implementation-produced writer inventory,
transaction-owned allocation/finalization and negative bypass/parity proofs before
new-schema activation. The physical v1.0 layout is unchanged. Synthetic gate vectors
are not the production inventory or proof of SQLite enforcement. SPINE-027/028 carry
the corresponding real-ledger acceptance work. Verification: the focused facet,
trusted-web, implemented-declaration and agent-documentation suite passed **57 tests
and 416 subtests**; Ruff on both changed test modules, packaged-contract sync check,
140 local Markdown links and `git diff --check` passed. No new audit, runtime code,
schema migration, commit or push occurred. Pre-existing diagnostic tracking was preserved.

**Facet diagnostic amendment bounded recheck staged (2026-09-26):** Prepared
[archetype-facet-diagnostic-amendment-audit-001](../whetstone_runs/archetype-facet-diagnostic-amendment-audit-001/audit-notes.md)
against `57ca486`. One reviewer-only audit-change with the buildability profile and
gpt-5.6-sol will target fb_dry_run_response_contract and fb_operability_r3_001 plus
amendment-induced regressions. Exact outgoing scope: thirty-two listed inputs,
the notes, built-in profile context and generated copies. Local staging verifies
file existence, unique inventory, JSON syntax, tracked-source/checkpoint parity,
hashes and supported CLI options. Input-manifest.json is local control data only.
Awaiting explicit outbound approval; no reviewer invoked, source specifications
changed, runtime work, commit or push. This does not reopen a diagnostic sweep or
make a convergence claim; SPINE-027 remains unstarted.

**Facet diagnostic amendment bounded recheck completed (2026-09-26):** Following
explicit approval of the thirty-two listed inputs, notes, built-in buildability
profile and generated copies, audit-change completed using gpt-5.6-sol. Verdict:
**pass**; **0 blockers, 0 majors, 0 minors, 0 nits**; **boundary_preserved=true**.
The focused scope covered both diagnostic finding closures and direct amendment
regressions. No residual finding was reported; the empty feedback artifact supplies
no separate per-finding closure narrative. Treat this as a clean bounded recheck,
not convergence or executable migration/finalizer/preview proof.

Verified all 33 approved raw input hashes unchanged, exact outgoing inventory,
Whetstone-normalized hashes, and manifest model/profile. Whetstone normalizes trailing
blank lines for its notes hash; the raw notes bytes were not modified. Source specs
and runtime remain unchanged. SPINE-027 is the next implementation target once
authorized; no Editor, commit, push or implementation occurred in this audit.
Evidence: [audit report](../whetstone_runs/archetype-facet-diagnostic-amendment-audit-001/change_audit/change_audit_report.md),
[feedback](../whetstone_runs/archetype-facet-diagnostic-amendment-audit-001/change_audit/change_audit_feedback.json)
and [manifest](../whetstone_runs/archetype-facet-diagnostic-amendment-audit-001/change_audit/audit_manifest.json).

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

### SPINE-026 — Keep OpenClaw delivery idempotency stable across retries

**Status:** Done (2026-09-22, Codex; implementation and local verification only).
Prepared runtime **0.6.1**, still schema **15**. No commit, push, deployment, service
restart, real gateway call or real-ledger change was performed.

**Root cause:** An OpenClaw send could reach WhatsApp before its CLI timed out.
Spine then retried with a different attempt-scoped key because `dedupe_key` was used
both for ledger uniqueness and gateway `idempotencyKey`. The timeout regression
reproduced two distinct visible deliveries under the old implementation.

**Repair:** Preserve attempt IDs and ledger keys (`openclaw:{work_instance_id}:N`).
The immutable outbound model now derives a separate provider key,
`openclaw-delivery:{work_instance_id}`, used only for gateway delivery idempotency.
The outbound v2 envelope includes both keys in request-hash evidence. Its closed
schema and generated package mirror are added. Existing attempt/rendering atomicity,
same-attempt replay suppression, freshness and result handling remain intact. Old v1
envelope replay fails closed without rewriting evidence or calling the gateway.
No migration is needed: existing work IDs derive the key and the existing request
hash covers it. The unique `(adapter_name, idempotency_key)` constraint, all ledger
code, timeout values and retry timing are unchanged.

**Regression evidence:** The gateway double remembers provider keys and returns the
original receipt after an initial delivery followed by a simulated CLI timeout.
The integration test records two attempts, two distinct ledger keys, and two valid
renderings/request hashes while observing one visible delivery. It reopens a persisted
synthetic ledger and reconstructs the second request in a fresh Python process.
It also verifies same-attempt replay does not call transport, ledger uniqueness still
rejects a duplicate attempt key, and the final work succeeds with attempt count two.
Additional cases cover different work with the same target/body, missing delivery
identity, old-envelope replay, and the canary's two-key preview.

**Files:** `src/spine/adapters/openclaw.py`; `tests/test_openclaw_adapter.py`,
`tests/test_openclaw_gateway_sender.py`, `tests/openclaw_helpers.py`,
`tests/test_seed_canary_runtime.py`; `contracts/schemas/openclaw-outbound-v2.schema.json`
and its `src/spine/contracts/web/schemas/` mirror; version declarations in
`src/spine/__init__.py`, `pyproject.toml` and `tests/test_stage1_scaffold.py`; README,
this backlog, implementation plan, OpenClaw deployment runbook, compatibility spec
and notification-rendering spec.

**Verification:** Python **3.14.6**, pytest **9.1.1**, mypy **2.3.0**, Ruff **0.16.2**.
Test commands used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src`:

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_openclaw_adapter.py tests/test_openclaw_gateway_sender.py tests/test_side_effects_adapter.py tests/test_worker.py tests/test_notification_rendering.py --tb=short
# Before repair: 42 passed, 23 subtests passed (1.02s).
.venv/bin/python -m pytest -o addopts='' -q tests/test_openclaw_adapter.py tests/test_openclaw_gateway_sender.py tests/test_side_effects_adapter.py tests/test_worker.py tests/test_notification_rendering.py tests/test_notification_rendering_contract_fixtures.py tests/test_seed_canary_runtime.py tests/test_web_contract_sync.py tests/test_stage1_scaffold.py --tb=short
# Completed focused verification: 65 passed, 27 subtests passed (2.01s).
.venv/bin/python -m unittest discover -s tests
# Final run: 656 tests, OK (70.488s).
.venv/bin/python -m pytest -o addopts='' -q
# 656 passed, 654 subtests passed (70.88s), no skips.
```

The first full unittest run had one failure in the pre-existing
`StorageSafetyTests.test_critical_pressure_maps_to_bounded_tickerd_stop`: live free
space was no longer under the test's one-byte threshold margin, returning `allow`.
That test passed immediately alone (**1 passed**, 0.16s), and both subsequent full
runs passed without changing the test or storage runtime. The initial failure is
retained as evidence of sensitivity to live filesystem measurements.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-openclaw-idempotency-mypy src/spine/core src/spine/ledger
# Success: no issues found in 37 source files.
.venv/bin/ruff check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check
PYTHONPYCACHEPREFIX=/tmp/spine-openclaw-idempotency-compile .venv/bin/python -m compileall -q src tests examples
git diff --check
# All passed; 97 local links in six changed Markdown files also resolve.
```

**Remaining limitation:** The real OpenClaw build's key scope, retention across the
entire retry horizon, restart persistence and treatment of changed retry prose need
separate runtime verification. Spine sends each attempt's exact persisted body;
the double models a gateway returning the earlier receipt for the repeated key.
This is not provider exactly-once qualification. Already-ambiguous deliveries sent
with pre-0.6.1 keys cannot be retroactively deduplicated by this change; deployment
and incident reconciliation remain separate actions.

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

## SPINE-015 cloud validation repair

### SPINE-025 — Reconcile deferred packaging and source-only strict typing

**Status:** Done (2026-09-19). Local verification and the subsequent operator-reported
Python 3.12 cloud validation passed. Synchronization repair preserved; bounded
shared-helper dependency repair passes source-only and editable-install strict
checking with both locally tested mypy versions, plus the full regression suites.
**Dependencies:** Existing SPINE-015 package-activation boundary; no new spec decision
or v2 activation. The operator subsequently supplied clean Python 3.12 cloud evidence;
public v2 activation, HTTP/Kinflow acceptance and deployment remain separate.

**Confirmed baseline:** Clean checkout `f575af5c059c6a9cdeed4de7319a713ea7a17760`.
The synchronization gate expected 17 deferred read-family mirrors. Both mypy 1.20.2
and 2.3.0 pass in the editable-install environment but fail with 308 diagnostics in
seven transitive modules when using an interpreter without an installed Spine package
for import discovery (the cloud reported 307 with its installed dependencies). The
ledger imports the command layer through both a pure ID helper and late temporal
binding/occurrence helpers. Moving only the ID helper did not resolve the gate; that
experiment was fully reverted before the handoff. The earlier core renderer repair
is separate from the service renderer errors in this report.

**Completed synchronization repair:** Exclude the source-only `trusted-web-read-*`
family until the already-planned HTTP/package/capability activation checkpoint;
retain the existing v1 registry and current schema synchronization. The checker still
rejects missing, changed, unexpected and prematurely packaged assets. Four focused
regressions include future non-read schemas, read-only check behavior and deferred
registry/schema rejection. No canonical or packaged JSON, runtime declarations,
dependency versions, or strict typing settings changed.

**Synchronization-stage verification (2026-09-18):** Python 3.14.6;
`python -m unittest discover -s tests` passed **556 tests in 29.217s**; `pytest -o addopts='' -q` passed **556 tests and 572 subtests
in 29.63s**. All test invocations used the existing `.venv` and disabled repository
bytecode writes. `ruff check .`, `python scripts/sync_web_contracts.py --check`, and
`git diff --check` passed. `python -m compileall -q src tests examples` passed with
bytecode redirected to a cleaned temporary directory; existing repository bytecode
was unchanged. At that checkpoint, these passes did not supersede the unresolved
source-only mypy failure; the completed typing repair follows below.

**Typing repair (2026-09-19):** Reproduced the source-only failure before editing
with the handoff's mypy 1.20.2 command: **308 errors in seven transitive modules,
35 explicitly checked files**. Moved the unchanged command-ID derivation to
`core/hashing.py`, six pure occurrence-detail/scheduled-fact helpers to
`core/occurrence_details.py`, and historical item/detail/anchor hydration to
`ledger/item_reads.py`. Notification profiles and temporal bindings now depend on
these shared lower-layer implementations rather than importing the command package.
The command module retains aliases for all nine moved private helpers, and both
public command-ID import paths remain available. An AST comparison against HEAD
confirmed that all ten extracted helper bodies are identical apart from renamed
shared-helper references. Canonical identities, SQL, validation errors, recurrence
and binding behavior are unchanged. No mypy configuration, tool pin, ignore,
import-skipping rule, contract, schema version, or activation declaration changed.
This repairs the strict core/ledger dependency boundary; it does not claim full
strict typing of the command/service/web modules outside that target.

Regression coverage adds a fixed command-ID preimage/public-export check, historical
hydration and stable-error checks, and extends the selected-occurrence binding test
with a fresh subprocess that rejects command-layer imports. The subprocess restores
only a synthetic fixture, checks foreign keys, resolves the binding under SQLite
query-only mode, compares canonical source/provenance evidence, and verifies no writes.
The pre-existing synchronization repair, its four tests, and the
[historical handoff](SPINE_015_CLOUD_TYPING_HANDOFF.md) remain byte-for-byte intact.

**Strict verification:** Python **3.14.6**, configured mypy target **3.12**;
mypy **1.20.2** and **2.3.0**. The alternate discovery interpreter
`/opt/homebrew/bin/python3` was verified to have no installed `spine-ledger`
distribution. All four commands below exited 0 with **“Success: no issues found
in 37 source files”**; incremental caching was disabled in every run:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-typing-repair-120-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/spine-mypy-1.20.2-validation-20260918 .venv/bin/python -m mypy --strict --no-incremental --cache-dir /tmp/spine-typing-repair-120-editable src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --python-executable /opt/homebrew/bin/python3 --cache-dir /tmp/spine-typing-repair-230-source src/spine/core src/spine/ledger
PYTHONDONTWRITEBYTECODE=1 .venv/bin/mypy --strict --no-incremental --cache-dir /tmp/spine-typing-repair-230-editable src/spine/core src/spine/ledger
```

**Regression verification:** pytest **9.1.1**, Ruff **0.16.2**. All test commands
used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../tickerd/src` with the existing
local environment; no Tickerd installation or qualification was performed.

```sh
.venv/bin/python -m pytest -o addopts='' -q tests/test_hashing.py tests/test_ledger_item_workflows.py tests/test_relative_temporal_bindings_command.py tests/test_recurrence_commands.py tests/test_agent_command_contract_mvp.py tests/test_command_response_fixtures.py tests/test_independent_activity_read_assembly.py tests/test_independent_activity_read_foundation.py tests/test_web_contract_sync.py
```

The focused selection passed **135 tests and 150 subtests in 10.22s**. After making
the child process explicitly select checkout source, the temporal-binding file
was rerun: `.venv/bin/python -m pytest -o addopts='' -q tests/test_relative_temporal_bindings_command.py`
passed **10 tests in 0.62s**.

Final full checks (all exited 0, no tests skipped):

- `.venv/bin/python -m unittest discover -s tests`: **559 tests in 30.141s, OK**.
- `.venv/bin/python -m pytest -o addopts='' -q`: **559 passed, 572 subtests passed
  in 30.65s**.
- `.venv/bin/ruff check .`: **All checks passed**.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/sync_web_contracts.py --check`:
  **passed**; deferred read-family packaging remains excluded.
- `PYTHONPYCACHEPREFIX=/tmp/spine-025-compile-cache .venv/bin/python -m compileall -q src tests examples`:
  **passed**, bytecode directed outside the repository.
- `git diff --check`: **passed**.

Final preservation checks confirmed the pre-existing sync script, sync tests and
handoff hashes unchanged, and all backlog content preceding SPINE-025 unchanged.
HEAD remains `f575af5c059c6a9cdeed4de7319a713ea7a17760`; the index remains empty.
There are no local validation blockers. This is not a fresh Linux/Python 3.12 cloud
run or completed SPINE-015 HTTP/Kinflow acceptance. Release fences, cursor integration
and HTTP/package/capability activation remain subsequent SPINE-015 work.

No commits, pushes, runtime internet enablement, deployment, real-ledger access,
Tickerd work or subsequent SPINE-015 feature implementation occurred.

**Operator-reported cloud follow-up (2026-09-19):** Both SPINE-025 failures are
resolved. Source-only mypy 1.20.2 passed all 37 files on Python 3.12 with Spine
uninstalled and strict rules unchanged. Contract synchronization and wheel inspection
passed, with deferred v2 assets excluded. The cloud run reported **526 passed + 33
Tickerd skips = 559 tests**, plus **572 passing subtests**; packaging, installed-wheel,
migration, lint, compilation and documentation checks passed and the checkout stayed
unchanged. No actionable Spine failures were reported. Unavailable Tickerd coverage
and inability to provision a second mypy version in cloud are environment limitations;
both mypy versions were already verified locally. This is supplied operator evidence,
not a cloud run performed by the implementation agent, and precedes the subsequent
SPINE-015 release-fence slice recorded above.
