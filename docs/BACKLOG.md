# Spine Backlog

Last updated: 2026-11-10

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

## Selected feature design

### SPINE-075 — Specify recurring-source per-occurrence related tasks

**Status:** Done — first design draft written (2026-11-07), machine-codified and
ratified under SPINE-091 (2026-11-09); not implemented. D-01–05 are approved.
The bounded consistency
review is complete under SPINE-076; SPINE-077's three additional lenses reported
one operability minor, now amended locally under SPINE-078 without an external
recheck. Detailed technical companions are now drafted under SPINE-079; their
SPINE-080 buildability review reported three majors, now amended locally under
SPINE-081 and passed the scoped SPINE-082 recheck before machine codification. No product
decision is reopened by recording or correcting those contract seams.
**Request:** A recurring class should generate one independently completable
pickup task per occurrence, due 90 elapsed minutes after the expressed class
start, following moves, with one reminder ten minutes before its own due time.
The operator approved automatic cancellation of still-open governed tasks on
confirmed source exclusion/cancellation. Preserve completed tasks, manual
cancellation/detach and attempted/delivered evidence.
**Approved reinstatement (2026-11-07):** D-01 selects automatic restoration without
confirmation when the same occurrence is proved restored and the latest pickup
was cancelled solely because of its source. Create one linked successor task
generation under the same assignment, preserving the cancelled task and all prior
work/attempt history. Active-rule, identity, manual-suppression, configuration and
generation/catch-up checks still apply; repeated scans cannot create another
successor. This is a specification amendment only.
**Approved generation policy (2026-11-07):** D-02 selects upcoming occurrences
from enrollment by default, an optional explicit starting occurrence, and a
configurable eight-week rolling horizon. Persist the chosen start/horizon; do
not reset enrollment on each scan or drop existing tasks outside the window.
Already-started-class and downtime catch-up are governed by D-03 below. This
changes no runtime.
**Approved catch-up (2026-11-07):** D-03 permits bounded missing-task creation
while the derived due is strictly future, including after the class starts.
Past reminders obey their existing late policy; no forced late send or new
overdue-task backfill. Existing overdue tasks remain unchanged. The same cutoff
applies to restoration successors, with current-time revalidation before commit.
**Approved configuration edits (2026-11-07):** D-04 requires an explicit scope:
normally upcoming open governed tasks plus future generation, with a newly-
generated-only alternative. Bounded adoption preserves individual exceptions,
terminal/overdue/detached tasks and attempted history; requested/applied revisions
and conflicts remain visible. Reusable-profile edits do not implicitly adopt a
new revision. This adds a draft update surface, not a registered runtime command.
**Approved retirement (2026-11-07):** D-05 requires explicit keep-following,
detach or cancel-outstanding-open disposition. All stop new assignments and
restoration successors. Keep-following preserves existing bindings/reminders;
detach keeps concrete due values independently; cancellation includes overdue
governed open tasks. Cleanup is bounded and preserves terminal/manual exceptions
and attempted history. No source event is changed.
**Design:** [Recurring related tasks](../specs/recurring-related-tasks.md) owns
series-rule enrollment, durable per-occurrence assignments/selector reservations,
explicit lineage continuity, bounded generation and lifecycle reconciliation.
It reuses ordinary nonrecurring tasks, `part_of`, selected-occurrence bindings,
notification policies/work and the existing scheduler. Minimal draft delegations
in the existing command, architecture, ontology, binding and notification owners
do not change implemented command lists, selectors, routes or v1 behavior.
**Open product decisions:** None among the selected D-01–05. SPINE-079 specifies
proposed storage, lineage, command and limit/clock rules; technical review and
machine schemas/computed fixtures remain pending. Draft family names are not
runtime declarations and no schema number is reserved.
**Verification:** Local consistency review tightened assignment-aware direct/sweep
reconciliation, positive novelty proof after source edits, and the per-rule scope
of duplicate prevention. The existing documentation, scaffold and implemented-
contract declaration suite passes **12 tests (0.352 seconds, final checkpoint check)**. All **378 local
Markdown link targets in ten changed documents** resolve; `git diff --check`
passes. The pre-existing `AGENTS.md` change is byte-for-byte preserved. No runtime,
machine-schema/fixture, migration or ledger changes; no external audit, commit or
push is part of this specification step.
**Checkpoint authorization (2026-11-07):** The operator requested a local
checkpoint of the draft with D-01–05 and its supporting specification/index/
tracking amendments. Exclude the pre-existing `AGENTS.md` edit. This does not
authorize a push, external review, ratification or implementation.
**Next:** Review the detailed technical companions, then codify machine contracts/
fixtures and write the implementation plan before runtime work. This is
selected feature design, not a restart of deferred resilience initiatives.

### SPINE-076 — Bounded review of recurring-related-task design

**Status:** Done — the authorized single reviewer-only pass returned **pass**,
boundary preserved, with zero blockers, majors, minors or nits. No source edits.
**Scope:** One reviewer-only consistency audit of SPINE-075 at checkpoint
`d9a8397fbf0bb82294ca2bdf47c014a72cd0949d`; preserve D-01–05 and existing owner
boundaries. Check source-slot continuity, cancellation/restoration, enrollment/
catch-up, scoped edits/retirement, bounded page/replay behavior and reminder safety.
Do not confuse deferred machine codification with a whole-bundle readiness review.
**Package:** [Audit notes](../whetstone_runs/recurring-related-tasks-contract-audit-001/audit-notes.md)
enumerate fourteen complete specification inputs; the
[prepared manifest](../whetstone_runs/recurring-related-tasks-contract-audit-001/prepared-inputs.json)
binds their hashes, notes and complete rendered built-in-context prompt. Source
payload is 694,706 bytes; rendered prompt is 709,654 UTF-8 bytes. No runtime code,
ledger, credentials or environment configuration is included.
**Runtime/destination:** Stable Whetstone `0.1.0` checkpoint
`6e19fe3e72dedda50a372781a43c08e5d7e7480a`; Codex Reviewer `gpt-6.1-sol`, explicit
medium reasoning, installed CLI `0.166.0-alpha.6`. This records the current CLI,
not the older version in retained people audits. No development-channel fallback.
**Guard:** The [launcher](../whetstone_runs/recurring-related-tasks-contract-audit-001/run-review.py)
verifies checkpoint, source/notes/prompt hashes and runtime/client versions locally.
Execution refuses until actual exact-payload approval is recorded in
[execution status](../whetstone_runs/recurring-related-tasks-contract-audit-001/execution-status.json).
The operator subsequently approved the exact prepared package in this thread;
the [authorization](../whetstone_runs/recurring-related-tasks-contract-audit-001/authorization.md)
records the payload/model boundary. No source-spec mutation, Editor, convergence,
ratification, implementation, commit or push is authorized by this audit.
**Local verification:** The guarded launcher passes `--verify-only` with fourteen
sources and the exact complete prompt; it reports `verified_not_sent`. Stable
selection and installed client version are checked without a reviewer/model call.
**Outcome:** The persisted
[report](../whetstone_runs/recurring-related-tasks-contract-audit-001/change_audit/change_audit_report.md)
contains no findings. The actual manifest/brief match the approved fourteen-source
package and complete prompt hash, and all source hashes are unchanged. The
[execution summary](../whetstone_runs/recurring-related-tasks-contract-audit-001/execution-summary.md)
records the supported runtime/model, checks and limits. No Editor, automatic
retry/correction loop or convergence claim; no source/runtime/ledger mutations,
ratification, implementation, commit or push.
**Next:** Report the bounded consistency pass. Technical storage/lineage/wire
closure, machine schemas/computed fixtures and ratification remain separate
operator-directed work before the implementation plan and runtime implementation.

### SPINE-077 — Structural, determinism and operability design evaluations

**Status:** Done — all three approved reviewer-only passes completed on unchanged
inputs. Structural integrity and determinism pass with zero findings; operability
passes with one minor clarification. Zero blockers/majors; all boundaries preserved.
**Scope:** Independent `structural_integrity`, `determinism` and `operability`
`audit-change` passes against the same fourteen-specification checkpoint
`d9a8397fbf0bb82294ca2bdf47c014a72cd0949d`. Preserve D-01–05, source recurrence
authority, ordinary tasks, per-rule assignment/generation identity and existing
notification/ownership boundaries. No edits or finding feedback between passes.
**Package:** [Shared audit notes](../whetstone_runs/recurring-related-tasks-design-evaluations-001/audit-notes.md)
list the exact fourteen full specifications and lens-specific questions. The
[prepared manifest](../whetstone_runs/recurring-related-tasks-design-evaluations-001/prepared-inputs.json)
binds unchanged source/notes bytes and all three complete prompts. Each pass
contains 694,706 source bytes; complete prompts total 2,131,221 UTF-8 bytes across
three separate calls. No prior feedback/report, runtime code, ledger or private
configuration is added to the transmitted package.
**Execution:** Stable Whetstone `0.1.0` checkpoint
`6e19fe3e72dedda50a372781a43c08e5d7e7480a`, external Codex `gpt-6.1-sol`, medium
reasoning, CLI `0.166.0-alpha.6`. One pass per profile, isolated output directories,
1200-second subprocess timeout each; no Editor, Phase 1/convergence, automatic
correction/new review loop, source mutation, ratification, runtime implementation,
commit or push. Detailed mechanical contracts remain deferred; real semantic
gaps are in scope under each selected lens.
**Guard:** The [launcher](../whetstone_runs/recurring-related-tasks-design-evaluations-001/run-review.py)
verifies the checkpoint, all sources/notes, each complete prompt, runtime and client
versions without sending. Execution requires actual approval recorded in
[execution status](../whetstone_runs/recurring-related-tasks-design-evaluations-001/execution-status.json),
one explicit profile and an unused profile output directory. Source/destination
drift requires renewed explanation/approval, not fallback.
**Verification:** The guarded launcher passes local `--verify-only` for all three
profiles and fourteen unchanged sources, reporting `verified_not_sent`. Diff
hygiene passes; no source specification or pre-existing guidance edit changed.
**Authorization:** The operator approved all fourteen specifications, shared notes,
each built-in reviewer/profile context and generated copies for all three passes;
the [authorization record](../whetstone_runs/recurring-related-tasks-design-evaluations-001/authorization.md)
binds the exact scope/model/prompt hashes.
**Outcome:** The [execution summary](../whetstone_runs/recurring-related-tasks-design-evaluations-001/execution-summary.md)
links each persisted report/feedback. Actual manifests and complete rendered
prompts match the approved package; all fourteen source hashes remain unchanged.
No Editor, source corrections, ratification or convergence claim.
**Reported minor:** Operability `OP-001` identifies no supported way to record
an individual restoration veto after source-only task cancellation: the binding
is retired and the task cannot be freshly cancelled again. The recommended
technical clarification is a replay-safe assignment-level suppression action,
explicit concurrent-successor precedence and visible veto readback, preserving
the terminal predecessor. This exercises an approved safeguard, not new policy.
**Subsequent action:** The operator authorized the narrow local specification patch
recorded under SPINE-078. Original reports/feedback and their counts are unchanged;
the amendment has not received an external recheck.

### SPINE-078 — Specify the individual restoration-suppression action

**Status:** Done — operator-authorized bounded specification amendment for
SPINE-077 operability `OP-001` applied and locally verified; not externally
rechecked. No runtime or machine-schema changes.
**Change:** [Recurring related tasks Section 8.3](../specs/recurring-related-tasks.md#83-individual-restoration-suppression-after-source-cancellation)
defines a supported assignment-level veto after source-only cancellation, even
when the task is terminal and the binding retired. Add a provisional command,
persistent evidence/readback and required fixture cases. Suppression-first blocks
restoration; restoration-first makes the stale veto fail without implicitly
cancelling a successor. Preserve D-01–05, other assignments and all terminal/
attempted history. Exact field/enum/preimage codification remains pending.
**Verification:** Existing documentation/scaffold/implemented-contract declaration
checks pass **12 tests (0.359 seconds)**. All **393 local Markdown link targets
in ten documents**, new-leaf section anchors and diff hygiene pass. The
[local follow-up](../whetstone_runs/recurring-related-tasks-design-evaluations-001/minor-patch-followup.md)
records the patch; original audit reports/feedback/counts and reviewed source
hashes are preserved. This is not runtime suppression/race test evidence.
**Boundary:** No audit rerun, source report rewrite, ratification, implementation,
ledger access, migration, delivery, commit or push is authorized by this patch.
**Checkpoint authorization (2026-11-08):** The operator subsequently requested a
local commit of the amended leaf and supporting review/patch tracking. Exclude
the pre-existing `AGENTS.md` edit. Generated Whetstone run artifacts remain local
under the repository's existing ignore rule; the recorded verdicts and local
patch status are retained here. No push or additional review is authorized.
**Next:** Report the applied clarification before separately directed checkpoint,
technical contract closure or a focused external recheck.

### SPINE-079 — Close recurring-task storage, identity and command contracts

**Status:** Done — detailed human-readable technical drafts written and locally
verified (2026-11-08), not ratified. Subsequent SPINE-080 review requires three
major boundary/dependency corrections; this entry is not review acceptance. Preserve approved
D-01–05 and the individual restoration veto. No runtime, machine schemas/fixtures,
migration, external review, commit, push or deployment is included.
**Scope:** Focused physical-storage/identity and command companions beneath the
logical recurring-related-task leaf: canonical configuration and source proofs,
constraints and indexes, bounded progress, edit/retirement intent, all-writer
freshness, replay, clock/cursor rules and verification oracles. Existing source
recurrence and ordinary child identities retain their owning contracts.
**Artifacts:** [Storage/identity/lineage](../specs/recurring-related-task-storage.md)
specifies a relational header/history layout with canonical immutable payloads,
per-rule slot reservations, linked task generations, source-only cancellation and
suppression evidence, bounded edit/retirement intents, indexed invalidation and
migration/rollback. [Commands](../specs/recurring-related-task-commands.md) specifies
the seven proposed local operations, exact configuration/read branches, complete-unit
budgets, commit-time future-due checks, closed effects/reasons/errors, replay and
purpose/ledger-bound HMAC continuation. The logical owner delegates minimally;
the Spine-wide storage owner, command authority and indexes retain their roles.
**Support boundary:** Exact selectors and validated one-to-one carry-forward proof
can retain a task. Arbitrary changed recurrence topology without authoritative
mapping remains decision-required; no ordinal/nearest-time pairing, inferred
novelty or client-authored mapping is introduced. Pending edits/retirement gate
obsolete work; no-op clocks/empty rolling horizons do not write progress.
**Preservation:** The pre-existing `AGENTS.md` amendment is unrelated and remains
untouched. Environment-specific release/deployment considerations stay outside
these specifications. Ambiguous source continuity is not inferred from timestamps
or occurrence ordinals.
**Verification:** Documentation/scaffold/implemented-contract declaration suite:
**12 tests pass**. All **413 local Markdown targets in nine changed documents**,
new-leaf anchors, untracked-leaf whitespace,
`git diff --check` and the unchanged AGENTS SHA-256 are checked. This is prose
verification, not runtime/migration/race or machine-fixture evidence.
**Next:** Separately authorize a bounded buildability review of this technical
closure, then machine-contract/fixture codification and the implementation plan.
**Checkpoint authorization (2026-11-08):** The operator requested committing the
detailed specification closure, excluding the unrelated `AGENTS.md` amendment,
then staging a reviewer-only bounded buildability package. Staging does not
authorize transmitting its new payload, launching a reviewer or pushing commits.

### SPINE-080 — Bounded buildability review of recurring-task technical closure

**Status:** Done — approved single reviewer pass completed (2026-11-08):
**needs_revision**, **boundary_preserved=false**, **0 blockers / 3 majors /
0 minors / 0 nits**. Review execution is complete; technical acceptance is not.
The operator requested staging after the SPINE-079 local
checkpoint `0a33da39d69da874b13b60273a019e09b03e42b0`; no push is authorized.
**Package:** [Audit notes](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/audit-notes.md)
enumerate **18 complete specifications**, comprising the logical/storage/command
drafts and their preserved owners. The
[prepared manifest](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/prepared-inputs.json)
binds all source bytes, notes, pinned adapter and complete built-in buildability
prompt. Source bytes: **878,001**; rendered prompt: **893,073 characters /
893,501 UTF-8 bytes**. No runtime, machine schemas or old review reports are inputs.
**Reviewer:** One `audit-change` pass, real built-in `buildability`, stable Whetstone
`0.1.0` checkpoint `6e19fe3e72dedda50a372781a43c08e5d7e7480a`, Codex CLI
`0.166.0-alpha.6`, `gpt-6.1-sol`, explicit medium reasoning, 1200-second timeout.
**Focus:** Physical keys/history, source proof/novelty, stable child generation,
command/projection closure, adoption/retirement progress, bounded pages/cursors,
clock/replay/races, all-writer attempt freshness, migration and no idle writes.
Preserve D-01–05 and the suppression action; no scope expansion or heuristic mapping.
**Guard:** [Launcher](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/run-review.py)
defaults to local verification. Execution requires actual approval bound to the
manifest/notes hashes in the
[status record](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/execution-status.json),
then normal tool permission for nested CLI state. It refuses changed source,
checkpoint/runtime/adapter/prompt/CLI or an existing attempt. The
[authorization record](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/authorization.md)
records the actual operator approval and its exact manifest/notes hashes. Audit
artifacts remain local under the existing ignore rule.
**Boundary:** Reviewer-only; no source edits, Editor, convergence loop, ratification,
runtime implementation, ledger access, migration, delivery, deployment or push.
Subsequent machine schemas/computed fixtures are explicitly not delivered by this
review. Its result is not whole-feature runtime acceptance or convergence.
**Outcome:** The [persisted report](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/change_audit/change_audit_report.md)
and [execution summary](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/execution-summary.md)
record all three in-scope majors: BF-001 missing normative selector-table/key/
producer dependency; BF-002 unspecified distinct per-reminder intent creation
discriminator; BF-003 child owner domain/atomic ownership evidence inconsistent
with definition-rendering admission. The boundary flag describes the proposed
ownership contract, not an audit process violation or confirmed runtime defect.
**Integrity:** Process exit 0; all 18 source hashes, notes, complete prompt and
runtime/CLI/adapter remain unchanged. No source correction or further audit was
performed. Original report/feedback bytes are preserved; local run artifacts
remain ignored. The unrelated `AGENTS.md` amendment is unchanged.
**Next:** SPINE-081 records the subsequently authorized local manual amendment;
a focused external recheck still precedes machine schemas/computed fixtures.
Original finding counts/verdict are unchanged. No automatic patch/review loop.

### SPINE-081 — Bounded amendment for recurring-task buildability findings

**Status:** Done — operator-authorized manual specification patch applied and
locally verified (2026-11-08) for SPINE-080 BF-001–003; the subsequent focused
SPINE-082 recheck passed with zero findings and boundary preserved.
No runtime, schema/DDL, machine-fixture generation, new audit, commit, push or deployment.
**Assessment:** Agree with all three as normative gaps, not confirmed runtime
defects. Existing recurrence selector storage and per-policy authoring-token
machinery already exist; document/reuse them. Restrict generated item ownership
to subject/group, explicitly establish existing owner/header history atomically,
and preserve ordinary local create/rendering behavior outside this new family.
**Preservation:** Keep D-01–05, immutable identities/history, original audit reports,
and the pre-existing `AGENTS.md`/audit-tracking changes. No implicit ownership
transfer, creator entitlement, access grant or disclosure approval.
**Changes:** Recurrence/ontology/binding owners now identify existing selector
storage, exact FK and insert-versus-reuse validation. Notification/create/profile
owners register the already-implemented policy-key creation-token convention;
the new family closes generation-specific reminder mapping without rewriting
old IDs. Logical/storage/command drafts restrict child owners to subject/group,
create the existing owner/header history before presentation/work, record real
actor/receipt evidence and access-epoch change, and exclude ownership transfer.
Permissions/rendering owners preserve current ordinary local creation and grants.
**Evidence:** [Manual follow-up](../whetstone_runs/recurring-related-task-technical-buildability-audit-001/manual-patch-followup.md)
distinguishes verified gaps from runtime claims and preserves original reports.
Existing doc/declaration, create/profile and selected-binding checks pass
**39 tests**; pure no-ledger identity checks and static DDL dependency checks pass.
Local links/new anchors, diff hygiene and unchanged AGENTS bytes are verified.
This is not new-family runtime or migration test evidence.
**Next:** SPINE-082 records the separate clean focused recheck; machine schemas/
computed fixtures are the next separately selected step. No ratification or
change to the original audit's three-major/false-boundary report is claimed.
**Checkpoint/recheck request (2026-11-08):** The operator requested a local commit
of the bounded patch and related audit tracking, then a focused buildability
recheck. Exclude the unrelated `AGENTS.md` amendment. Prepare a new exact payload
and approval record; the earlier 18-file approval does not approve changed source
bytes or an additional reviewer request. No push is authorized.

### SPINE-082 — Focused buildability recheck of BF-001–003

**Status:** Done — approved focused pass completed (2026-11-08): **pass**,
**boundary_preserved=true**, **0 blockers / 0 majors / 0 minors / 0 nits**.
SPINE-081 patch checkpoint:
`d1631670eff8b718b5a6cff2c839885f884bb2b8`. No push is authorized.
**Package:** [Audit notes](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/audit-notes.md)
list **13 inputs: 12 complete specifications plus original BF-001–003 feedback**.
The [prepared manifest](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/prepared-inputs.json)
binds their ordered paths, bytes/hashes, notes, adapter and full built-in prompt.
Inputs: **609,337 bytes**; prompt: **623,658 characters / 624,065 UTF-8 bytes**.
Prior feedback is historical evidence, not normative authority or a file to rewrite.
**Focus:** Exact selector authority/producer/reuse; distinct reminder tokens and
real outer attribution; explicit subject/group child ownership/header/history/
epoch before disclosure/work. Recheck the three findings and patch-introduced
regressions only; preserve D-01–05, ordinary create behavior and frozen identities.
**Execution:** One reviewer-only `audit-change`, built-in `buildability`, stable
Whetstone `0.1.0` checkpoint `6e19fe3e72dedda50a372781a43c08e5d7e7480a`,
Codex CLI `0.166.0-alpha.6`, `gpt-6.1-sol`, explicit medium reasoning and
1200-second timeout. No Editor, convergence, automatic retry or source mutation.
**Guard:** The [launcher](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/run-review.py)
defaults to local verification and refuses source/checkpoint/runtime/adapter/CLI/
prompt drift, missing approval hashes or an existing attempt. The
[authorization](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/authorization.md)
and [status](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/execution-status.json)
record the actual operator approval and manifest/notes hashes. Original run artifacts are unchanged; new artifacts
remain local under the existing ignore rule. The unrelated AGENTS edit is excluded.
**Outcome:** The [persisted report](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/change_audit/change_audit_report.md)
and [execution summary](../whetstone_runs/recurring-related-task-technical-buildability-audit-002/execution-summary.md)
show empty feedback and no remaining findings within the BF-001–003/patch-regression
scope. No per-ID reviewer narrative was supplied; do not invent broader endorsement.
Process exit 0; all approved inputs, notes, prompt, runtime/adapter/CLI and AGENTS
bytes unchanged. Original audit-001 verdict/counts/reports are preserved.
**Next:** Separately select machine schemas/computed fixtures, then their review
and implementation plan. This scoped result is not convergence, ratification,
whole-feature runtime acceptance or permission to implement/deploy. No runtime,
ledger/migration, send, deployment, commit or push occurred during review.

### SPINE-083 — Codify recurring-task machine contracts and computed fixtures

**Status:** Done — source-only machine codification (2026-11-08) after the clean
SPINE-082 recheck. SPINE-084–090 records correction/review through clean residual
rechecks; SPINE-091 ratifies the source family (2026-11-09). Source-only schemas, capability/dependency manifest, computed
wire/identity/cursor/model fixtures and offline contract tests are present.
No runtime registration, handler/worker behavior or DDL/migration is implemented
by source codification. Later reviews/checkpoints are recorded in their own entries.
**Authority:** Preserve the reviewed logical/storage/command leaves and D-01–05.
Record mechanical wire-name/representation closure explicitly where prose used
descriptive tuples; do not invent product policy or treat offline model evidence
as runtime concurrency, transaction, migration or delivery proof.
**Preservation:** Keep existing AGENTS and review-tracking changes; do not alter
frozen schemas, installed HTTP registries/pins or packaged runtime declarations.
**Artifacts:** [Machine companion](../specs/recurring-related-task-machine-contract.md),
[capability/dependency manifest](../contracts/recurring-related-tasks.v1.json),
[fixture manifest](../contracts/recurring-related-task-fixture-manifest.json),
[21 source-only schemas](../contracts/schemas/recurring-related-tasks/), and
[offline contract tests](../tests/test_recurring_related_task_contracts.py).
The explicit offline closure binds 29 resources, including eight existing delegated
schemas. No frozen schema or runtime registry is changed. The corpus contains
70 wire fixtures (59 valid, 11 intentionally invalid), 85 canonical preimage/hash/ID
vectors, five purpose-specific cursor/HMAC vectors and 39 finite decision witnesses.
Mutually exclusive evidence branches are labelled as alternatives, not a single
ledger snapshot. Eighteen actual runtime proof obligations remain explicitly pending.
**Verification:** The new 14-test module plus existing documentation, declarations,
schedule-create, profile-command and relative-binding regressions pass **53 tests**.
The deterministic stdout-only builder's `--check` verifies all 76 generated
artifacts; focused Ruff and `git diff --check` pass. Existing AGENTS.md bytes are
unchanged; all **414 local Markdown targets** in seven affected documents resolve. Offline
examples do not prove SQL, migration, locking, scheduler or delivery races.
**Next:** Review this machine corpus before ratification and the selected runtime
implementation plan. No external review, commit or push was performed in this step.
**Checkpoint/review preparation (2026-11-08):** The operator requested a local
commit of the cohesive machine corpus and supporting review/codification tracking,
then preparation of a reviewer-only bounded machine-contract review. Exclude the
unrelated `AGENTS.md` edit. External transmission requires separate exact-payload
approval; no push, runtime implementation or migration is authorized.
**Checkpoint:** `9e8260d59b5a4b4949c48d9425979c9492889c12` —
`Define recurring-task machine contracts and computed fixtures`. The final selected
suite passed 53 tests before commit. No push; AGENTS.md was excluded.

### SPINE-084 — Bounded consistency review of recurring-task machine corpus

**Status:** Done — all three approved reviewer-only assessments completed
(2026-11-08), each `needs_revision` and `boundary_preserved=false`. Combined:
**0 blockers / 4 majors / 6 minors / 0 nits**, ten distinct in-scope findings.
Assessment completion does not close the findings, ratify the corpus or authorize implementation.
The original approved attempt remains `audit_failed` at client
`turn/start`: **1,402,443 characters** exceeded the **1,048,576-character** cap.
No semantic verdict exists for the oversized attempt; the valid replacement
assessments are recorded below. Its failure was setup recovery, not source feedback.
**Scope:** One reviewer-only `audit-change` of SPINE-083's source-only machine
codification: schema/spec/delegated-resource consistency, closed wire projections,
canonical preimages/digests, policy tokens/ownership, evidence equality, effects/
errors/replay/previews, bounded cursors and honest offline/runtime proof boundaries.
Preserve D-01–05 and BF-001–003 closure. No redesign, Editor, convergence, source
mutation, implementation, migration, ledger access, send or deployment.
**Checkpoint:** `9e8260d59b5a4b4949c48d9425979c9492889c12`.
**Original failed package:** [Audit notes](../whetstone_runs/recurring-related-task-machine-contract-audit-001/audit-notes.md)
enumerate **121 inputs**: four complete feature leaves, three machine manifests,
29 complete schema resources, 70 wire fixtures, four computed/evidence/model
corpora, the builder and offline tests, complete storage-atomicity context and
eight exact named-section authority extracts. The
[prepared manifest](../whetstone_runs/recurring-related-task-machine-contract-audit-001/prepared-inputs.json)
binds ordered input bytes/hashes, original context-source hashes/ranges, notes,
launcher, adapter and full built-in prompt. Omitted authority sections are outside
this audit; excerpts are exact text, not summaries. Inputs **1,357,788 bytes**;
prompt **1,402,443 characters / 1,402,845 UTF-8 bytes**. No AGENTS.md, ledger,
environment configuration or live credentials are included.
**Execution pins:** Stable Whetstone `0.1.0`, checkpoint
`6e19fe3e72dedda50a372781a43c08e5d7e7480a`; Codex Reviewer `gpt-6.1-sol`, explicit
medium reasoning, installed CLI `0.167.0-alpha.3.2`, built-in `consistency`,
1200-second timeout. CLI version differs from prior audit-002 and is recorded
explicitly; no model/runtime fallback.
**Guard:** [Launcher](../whetstone_runs/recurring-related-task-machine-contract-audit-001/run-review.py)
defaults to local verification; checks checkpoint, source/copy/section/prompt/
runtime/CLI/adapter/launcher hashes; refuses absent exact approval or an existing
attempt. [Authorization](../whetstone_runs/recurring-related-task-machine-contract-audit-001/authorization.md)
and [execution status](../whetstone_runs/recurring-related-task-machine-contract-audit-001/execution-status.json)
record the operator's explicit 121-input/notes/context/copies approval and exact
manifest/notes hashes. Run artifacts remain local under the existing ignore rule.
**Local verification:** `--verify-only` returns `verified_not_sent` for all 121
inputs and the exact rendered prompt. This is payload verification, not a model
review or readiness verdict. The original review roots remain unchanged.
**Attempt evidence:** The original
[report](../whetstone_runs/recurring-related-task-machine-contract-audit-001/change_audit/change_audit_report.json)
and [concise execution summary](../whetstone_runs/recurring-related-task-machine-contract-audit-001/execution-summary.md)
record `input_too_large`. Nested CLI exited 1; Whetstone/guard exited 0 while
persisting the failure. No feedback file exists. Zero report counts do not mean
a clean audit. Post-attempt hashes/runtime/CLI checks pass; all 121 inputs,
source specs/contracts and AGENTS bytes are unchanged. No automatic retry occurred.
**Replacement preparation:** The operator requested staging smaller overlapping
packages, not sending them. The [approval packet](../whetstone_runs/recurring-related-task-machine-split-review-001/README.md)
and [coverage map](../whetstone_runs/recurring-related-task-machine-split-review-001/review-map.json)
account for all 121 original exact inputs with no hidden additions or omissions:

- [A: storage/identity](../whetstone_runs/recurring-related-task-machine-audit-002-storage-identity/audit-notes.md)
  — 27 inputs, full prompt **908,478 characters / 908,675 UTF-8 bytes**, headroom 140,098 characters.
- [B: authoring/lifecycle](../whetstone_runs/recurring-related-task-machine-audit-003-authoring-lifecycle/audit-notes.md)
  — 96 inputs, full prompt **856,114 characters / 856,376 UTF-8 bytes**, headroom 192,462 characters.
- [C: reads/integration](../whetstone_runs/recurring-related-task-machine-audit-004-reads-integration/audit-notes.md)
  — 64 inputs, full prompt **916,046 characters / 916,306 UTF-8 bytes**, headroom 132,530 characters.

Every guarded launcher passes local `--verify-only`, enforcing complete source/
context/schema/prompt/runtime hashes and a **950,000-character** staging ceiling.
The 18 original failed-run files and all machine/source/AGENTS bytes remain unchanged.
Each replacement now has independent authorization/status recording the operator's
fresh approval of all three exact inventories, respective notes, built-in reviewer/
consistency-profile context and generated copies. Old approval was not inherited.
Source-only runtime/ledger boundaries and execution pins remain unchanged; all
pre-send guards pass. No review was launched during the earlier preparation.
**Results:** [A report](../whetstone_runs/recurring-related-task-machine-audit-002-storage-identity/change_audit/change_audit_report.md)
records 2 majors / 1 minor; [B report](../whetstone_runs/recurring-related-task-machine-audit-003-authoring-lifecycle/change_audit/change_audit_report.md)
1 major / 3 minors; [C report](../whetstone_runs/recurring-related-task-machine-audit-004-reads-integration/change_audit/change_audit_report.md)
1 major / 2 minors. The [reconciled summary](../whetstone_runs/recurring-related-task-machine-split-review-001/review-summary.md)
retains all ten findings and the manual next-step recommendation. Majors concern
recurrence-key encoding, independently verifiable source/lineage proof inputs,
the missing D=B adoption branch, and cursor rejection/error-ordering oracles.
Minors concern composed reminder witnesses, blocked-unit/page wording, assignee
deduplication, failure fields, read watermarks and blocked-child policy mappings.
**Integrity:** All three guarded processes exited 0 with valid feedback/reports;
actual manifests match approved ordered paths/hashes and client identity. The
entire 121-input union, frozen coverage map, 18 oversized-attempt files and AGENTS
bytes remain unchanged. No specification/contract/fixture/test/runtime patch,
Editor, automatic retry, ledger access, migration, send, deployment, commit or push.
**Follow-up:** The operator authorized bounded manual corrections under SPINE-085;
its local verification does not revise these original external verdicts.
**Next:** Stage fresh exact-hash rechecks of the corrected corpus when selected.
Preserve D-01–05 and all
existing ownership/identity/notification boundaries. No clean corpus-closure,
ratification, convergence or runtime-implementation claim is made.

### SPINE-085 — Correct recurring-task machine-review findings

**Status:** Done locally (2026-11-08) — all ten agreed A/B/C findings patched with
focused offline regression evidence. Not externally rechecked or ratified.
**Scope:** Source-only specs/schemas, deterministic computed fixtures and offline
oracles for occurrence-key bytes, positive source/lineage evidence, composed
multi-policy identities, three-way adoption, blocked-unit/page wording, raw versus
normalized assignee sets, exact failure fields, cursor rejection/precedence and
cross-surface catalog/policy mappings. Preserve D-01–05 and existing frozen owners.
**Boundary:** No runtime handler/worker/DDL/migration or registration changes,
live ledger, sends, new external audit, ratification, commit, push or deployment.
Keep all original review reports/manifests and pre-existing AGENTS/tracking edits.
Changed source will intentionally stale the old exact-payload guards; do not
rewrite their inventory or claim an external recheck.
**Changes:** Preserve recurrence's encoded occurrence key rather than substituting
a digest; regenerate dependent identities. Retain twelve normalized source
snapshots and nine bounded source-proof cases with independently checked hashes,
copy/COUNT/union/retarget/novelty evidence. Retain profile-plus-custom composition,
distinct intent tokens and replacement/copy-forward preimages. Correct D=B
adoption preservation, successful blocked selection versus failed-page wording,
raw duplicate-assignee normalization, exact failure fields, read watermarks and
blocked-task policy mappings. Add 29 cursor outcome cases, including invalid and
stale contexts and precedence over later expected-fact errors. The independent
source checker is explicitly limited to the finite WEEKLY fixture shapes and
64 candidate steps, not a runtime resolver. The standalone stdout-only builder
also has a direct-entrypoint regression.
**Verification:** **79 tests passed**: 62 selected machine/scaffold/documentation/
declaration/scheduling/profile/binding regressions and 17 existing recurrence/
occurrence/frozen-contract tests. All **80 generated artifacts** reproduce exactly
(72 wire fixtures, six computed/evidence/model corpora and two manifests); the
offline schema closure contains 30 resources. Focused Ruff, formatting and
`git diff --check` pass. Pre-existing AGENTS.md bytes and all 18 inventoried
oversized-attempt artifacts remain unchanged; original A/B/C reports are retained.
No runtime `src/`, installed/frozen schema, migration or registration changed.
**Next:** A focused fresh-payload external recheck is the next review gate when
authorized. Old payload approvals and their source hashes are not reused. This
local correction is not whole-corpus closure or implementation authorization.
**Checkpoint:** `183724882a6084932cfa2a520f710cbd1466aa5f` —
`Correct recurring-task machine contracts and regression evidence`. All 79 selected
tests and exact regeneration passed again before commit. The unrelated AGENTS.md
change was excluded; no push occurred. Focused recheck preparation is SPINE-086.

### SPINE-086 — Stage focused recurring-task machine-correction rechecks

**Status:** Done — preparation only (2026-11-08); all four packages verify locally
as `verified_not_sent`. Fresh exact-payload external approval remains pending.
**Scope:** Reviewer-only `audit-change`, built-in `consistency`, against correction
checkpoint `1837248`. The [approval packet](../whetstone_runs/recurring-related-task-machine-rechecks-001/README.md)
and [finding map](../whetstone_runs/recurring-related-task-machine-rechecks-001/review-map.json)
assign all ten prior findings exactly once, with overlapping complete schema/code/
authority context. This is focused finding coverage, not a repeat of every original
121-input review file or a whole-feature convergence run.

- [A: identity/composition](../whetstone_runs/recurring-related-task-machine-audit-005-identity-composition-recheck/audit-notes.md)
  — **32 inputs**, 943,477 full prompt characters; A/F-001 and A/F-003.
- [B: source proofs](../whetstone_runs/recurring-related-task-machine-audit-006-source-proof-recheck/audit-notes.md)
  — **26 inputs**, 850,516 characters; A/F-002.
- [C: authoring](../whetstone_runs/recurring-related-task-machine-audit-007-authoring-recheck/audit-notes.md)
  — **93 inputs**, 781,200 characters; B/FB-001–004.
- [D: reads/cursors](../whetstone_runs/recurring-related-task-machine-audit-008-read-cursor-recheck/audit-notes.md)
  — **68 inputs**, 908,100 characters; C/fb_001–003.

**Guards:** Each ordered payload, notes, exact source-hashed named-section context,
schema-reference closure, checkpoint, shared finding map, prior artifact hashes,
launcher/adapter/runtime/CLI and complete built-in prompt is bound and locally
verified. Prompt ceiling remains 950,000 characters below the observed 1,048,576
client cap; no unmeasured trimming or fallback. Explicit staged pins: stable
Whetstone 0.1.0 / `6e19fe3e72dedda50a372781a43c08e5d7e7480a`, Codex CLI
0.167.0-alpha.3.2, `gpt-6.1-sol`, medium reasoning, 1200 seconds. Exact inventories
are in each `prepared-inputs.json`; no AGENTS/environment/ledger/credentials.
**Authorization:** All four status files explicitly deny external-send approval;
no reviewer launched and no `change_audit` output exists. Old A/B/C approvals are
not inherited. Normal execution access is still required after affirmative new
approval. No Editor, source change, implementation, migration, send or deployment
is part of preparation. New artifacts remain local under the existing ignore rule;
these tracking additions follow the selected commit and are not yet committed.
**Next:** Obtain exact A/B/C/D payload approval, then execute and monitor each
bounded assessment separately and reconcile all findings/shared seams. No clean
machine-corpus closure, ratification or runtime implementation is claimed.
**Approval follow-up:** The operator explicitly approved the four exact packages,
notes, built-in context and generated copies. Fresh authorization records bind
each unchanged manifest/notes hash; execution is tracked separately below.

### SPINE-087 — Execute focused recurring-task machine-correction rechecks

**Status:** Done — all four explicitly approved reviewer-only assessments
completed (2026-11-08). Combined **0 blockers / 1 major / 1 minor / 0 nits**;
the machine corpus still needs correction and is not ratified.
**Scope:** Only SPINE-086's exact 32/26/93/68-input packages against `1837248`,
stable Whetstone, built-in consistency, GPT-6.1 Sol at medium reasoning. Verify
each payload, runtime, destination and full prompt before launch. Preserve source
bytes and all old review evidence; record persisted results independently of
process exit codes. No automatic retry, source patch, Editor, implementation,
ledger access, migration, send, deployment, commit or push.
**Results:** [Terminal reconciliation](../whetstone_runs/recurring-related-task-machine-rechecks-001/review-summary.md).
A passes with no findings; B returns needs-revision, boundary false, one major;
C passes with minor clarification, boundary true, one minor; D passes with no
findings. B/F-001 leaves original A/F-002 incomplete: successor fixture segment
ancestry still says `initial` rather than the producing/copying predecessor,
and hash checks do not independently reject that relationship. C/FB-001 leaves
original B/FB-004 incomplete: two authoring configuration failure fixtures still
name reconcile, and tests omit command from their code/field comparison.
**Verification:** All four processes exited 0 with valid reports/feedback, not
merely empty failure counts. Actual submitted manifests exactly match approved
ordered paths/hashes, notes and reviewer identity. All four post-review guards
pass; 44 inventoried prior artifacts and AGENTS bytes remain unchanged. There
were no source patches between reviews. Local authorization/status and tracking
changes are uncommitted; no push, runtime work or automatic retry occurred.
**Next:** Seek authorization for the two narrow source-only corrections and
regression tests, then freshly stage the affected rechecks. Original approval
does not authorize changed payloads or implementation. No whole-corpus closure
or convergence claim is made.

### SPINE-088 — Correct the two focused machine-recheck residuals

**Status:** Done — both SPINE-087 residuals patched locally (2026-11-08) with
independent regressions; the SPINE-090 focused rechecks passed (2026-11-09).
Not ratified or implemented.
**Scope:** Correct successor fixture segment ancestry without changing runtime
normalizers, regenerate affected identities/evidence, reject self-consistently
hashed invalid ancestry, and align authoring failure examples with matching
command/code/field branches. Preserve existing historical ancestry and all
working-tree changes; old review artifacts and approvals remain immutable.
**Boundary:** No runtime behavior, migrations, ledger access, new external audit,
ratification, commit, push or deployment.
**Changes:** Fixture construction explicitly supplies the producing/copying
predecessor revision for successor segments, including matching preview inputs
used for deterministic copy IDs. This is scoped to newly constructed fixture
facts, not a historical-row rewrite or runtime-normalizer change. Independent
snapshot checking now separates identity/hash verification from ancestry; the
new regression constructs successors with valid hashes but `initial` or an
unrelated stable source revision, proves their mathematical identities valid,
then rejects their ancestry. Regenerated seven affected artifacts, including
proof/lineage identities and suppression references. The two authoring failures
now model update of immutable `configuration.task_owner` and unavailable
`configuration.notification_plan` disclosure; independent tests assert all 13
command/code/field triples. Reconcile per-assignment decision-required semantics
remain unchanged. The machine companion is draft.3 with explicit oracle scope.
**Verification:** **80 selected tests passed**, including 24 source-only machine
tests and existing scheduling/profile/binding/recurrence regressions. All **80
generated artifacts** reproduce exactly; focused Ruff, formatting and
`git diff --check` pass. Original source owner specifications, public schemas,
runtime `src/`, old audit inputs/reports, all 44 inventoried prior artifacts and
AGENTS bytes are unchanged. Pre-existing tracking changes remain intact. No new
audit, ledger access, runtime work, commit or push occurred.
**Next:** Checkpoint and freshly stage focused rechecks of the affected proof and
failure branches when requested. The old source-bound guards are intentionally
stale after correction; do not refresh their frozen hashes or reuse old approval.
Local verification does not establish external closure or implementation readiness.
**Checkpoint:** `d5744bad53fa820eb9e6c132df427bf601871a78` —
`Correct recurring-task fixture ancestry and failure attribution` (2026-11-09).
All 80 selected tests, exact 80-artifact regeneration, focused Ruff and diff
hygiene passed again before commit. AGENTS.md was excluded; no push occurred.
Fresh focused recheck preparation follows under SPINE-089.

### SPINE-089 — Stage the two residual machine-contract rechecks

**Status:** Done — preparation only (2026-11-09). Both guarded launchers return
`verified_not_sent`; fresh exact-payload external approval remains pending.
**Scope:** Reviewer-only `audit-change`, built-in `consistency`, against corrected
checkpoint `d5744ba`, preserving the earlier clean A/D reports rather than rerunning
all four scopes. The [approval packet](../whetstone_runs/recurring-related-task-machine-residual-rechecks-001/README.md)
and [finding map](../whetstone_runs/recurring-related-task-machine-residual-rechecks-001/review-map.json)
bind the two residuals and all overlap/context explicitly:

- [B: successor ancestry](../whetstone_runs/recurring-related-task-machine-audit-009-source-ancestry-recheck/audit-notes.md)
  — **26 inputs**, **854,569** full prompt characters, B/F-001 from audit-006.
- [C: failure attribution](../whetstone_runs/recurring-related-task-machine-audit-010-failure-attribution-recheck/audit-notes.md)
  — **46 inputs**, **659,414** characters, C/FB-001 from audit-007.

**Verification:** Ordered input/notes/source-context/schema-reference hashes,
committed checkpoint, two-finding coverage, prior artifact preservation, launcher,
adapter/runtime/CLI and complete built-in prompts all verify locally. Complete
included schemas are transitively closed (11 and 17 documents); authority excerpts
are exact source-hashed named sections, never summaries. Both prompts are under
the 950,000-character staging ceiling and observed 1,048,576-character client cap.
**Pins:** Stable Whetstone 0.1.0 / `6e19fe3e72dedda50a372781a43c08e5d7e7480a`,
Codex CLI 0.167.0-alpha.3.2, `gpt-6.1-sol`, explicit medium reasoning and 1200 seconds.
Exact inventories and full prompt hashes are in each `prepared-inputs.json`.
**Authorization/boundary:** Both status files deny external-send approval; no
reviewer launched and no `change_audit` output exists. Old approvals and frozen
review inputs are not rewritten or reused. No Editor, source mutation, runtime
work, migration, ledger access, notification send, deployment, ratification or
convergence is part of staging. AGENTS.md remains unchanged and uncommitted;
only new preparation tracking follows the selected commit. No push occurred.
**Next:** Obtain approval of both exact payloads, notes, built-in consistency
context and generated copies, then run and monitor each independently through its
normal permission mechanism. Reconcile results with retained clean A/D evidence;
neither local staging nor an individual pass establishes whole-corpus closure.
**Approval follow-up:** The operator explicitly approved both exact packages,
notes, built-in review context and generated copies using GPT-6.1 Sol at medium
reasoning. Fresh package authorization records bind the unchanged manifest and
notes hashes; execution is recorded separately below.

### SPINE-090 — Execute the two residual machine-contract rechecks

**Status:** Done (2026-11-09) — both approved reviewer-only assessments completed
with `pass`, preserved boundaries and **0 blockers / 0 majors / 0 minors / 0 nits**.
**Scope:** SPINE-089's 26-input successor-ancestry and 46-input failure-attribution
packages at `d5744ba`, stable Whetstone, built-in consistency, GPT-6.1 Sol at medium
reasoning. Preserve all source bytes, old review evidence and working-tree edits.
No source patch, Editor, runtime work, migration, ledger access, notification send,
deployment, commit, push or automatic retry.
**Results:** [Terminal reconciliation](../whetstone_runs/recurring-related-task-machine-residual-rechecks-001/review-summary.md).
Audit-009 source ancestry and audit-010 failure attribution have empty structured
feedback arrays. The two residuals receive no remaining or introduced findings;
retained clean A/D evidence and unchanged composition/cursor/read fixtures are
reconciled without claiming a new full-corpus review.
**Verification:** Both processes exited 0 and produced valid reports; submitted
ordered paths/hashes, notes and configured reviewer pins match approval. All
post-review guards pass; 88 prior artifacts and AGENTS bytes remain unchanged.
**Metadata caveat:** Audit-010's generated reviewer.model says `gpt-6`; its approved
launcher/actual manifest and inspected pinned adapter request `gpt-6.1-sol` with
medium reasoning. Raw feedback is preserved. Generated self-description is not
runtime attestation; ephemeral CLI mode retains no independent session record.
No fallback is present in the inspected launch path. This caveat is recorded
separately from semantic findings and is not silently rewritten.
**Boundary:** No source edit, Editor, runtime work, ledger access, migration,
notification send, deployment, commit, push or retry occurred. Tracking and local
execution artifacts remain uncommitted. No convergence or automatic ratification.
**Next:** Seek explicit ratification, then prepare the implementation plan and its
pending runtime verification obligations. No reported in-scope machine findings
remain outstanding in the reviewed chain; passing offline review is not runtime proof.

### SPINE-091 — Ratify recurring-task contracts and prepare delivery plan

**Status:** Done (2026-11-09) — operator-authorized source contract ratification
and four-slice implementation plan complete; runtime implementation not started.
**Scope:** Accept the reviewed logical/storage/command/machine family as v1.0.0,
align source manifest/schema annotation/fixture status labels, preserve all wire
shapes and identity bytes, and allocate all 18 runtime obligations to substantial
implementation checkpoints. Preserve existing AGENTS/tracking changes and raw
audit evidence, including the generated model-label caveat.
**Boundary:** Runtime declarations, command/web registries, package/schema
versions and migration files remain unchanged. No ledger access, external review,
notification send, commit, push or deployment.
**Changes:** All four feature leaves accepted v1.0.0; descriptor and source-only
fixture/closure statuses ratified, five schema title annotations aligned and
closure hashes regenerated. Existing source-only boundary tests now require
ratified status while retaining unimplemented/undeclared/unregistered guards.
README/spec index and current backlog status reflect acceptance, not delivery.
The existing implementation plan now defines four substantial checkpoints for
one complete feature, R1–R4 below, with every RRT-01–18 obligation mapped once
to concrete real-test evidence and a final activation gate. Product D-01–05,
trusted-local exposure and all wire/normalization/identity/limit semantics are unchanged.
**Verification:** **80 selected tests passed**; all **80 deterministic artifacts**
reproduce; focused Ruff/formatting, local Markdown targets/added anchors and
`git diff --check` pass. Mechanical comparison confirms the 20 family schema
validation semantics and descriptor/fixture content are unchanged except status/
title metadata; closure resource paths are identical and all hashes current.
All 18 runtime obligations remain pending. Runtime/package/migration declarations,
AGENTS bytes, raw reviews and 88 inventoried prior audit artifacts are preserved.
No runtime work, external audit, commit or push occurred.
**Checkpoint:** Ratification and plan committed as `5ed85be`; AGENTS.md excluded.
The operator then authorized SPINE-092/R1. No push was requested.
**Next:** Follow SPINE-092's implementation evidence; retain the source-only
activation boundary until R4, rather than treating ratification as runtime support.

### SPINE-092 — R1: recurring-task persistence and source identity

**Status:** Done, internal checkpoint (2026-11-10) — operator authorized R1 after
ratification/plan commit `5ed85be`. R1 committed as `bc96a1d`; no push.
**Scope:** Exact physical records/constraints/indexes and ordered migration,
canonical decoders/identities, authentic bounded source proof and lineage.
Existing items/selectors/owners/bindings/notification tables retain authority;
no automatic enrollment or public command activation. Choose the next free
migration number during implementation, not in this plan.
**Acceptance:** Actual fresh/populated synthetic migration, rollback/FK/unique/
history rejection, reservation/predecessor races, source identity/COUNT/union/
retarget/novelty fail-closed cases and indexed access plans. Introduce RRT-01/04/
05/18 evidence; detailed work and exit gate are in the
[delivery plan](IMPLEMENTATION_PLAN.md#r1--persistence-and-source-identity-foundation-spine-092).
**Evidence:** Candidate migration 20 implements 15 tables, 27 guards and 11 explicit
indexes without changing normal schema-19 initialization/migration. New canonical
helpers exercise all 110 published vectors. Actual SQLite graph/rollback/drift,
reservation/CAS and physical predecessor races, indexed plans and actual source
membership/COUNT/union/move/exclusion/novelty tests pass. See the
[R1 checkpoint](design-notes/recurring-related-task-r1-checkpoint.md) for exact
test ownership, activation limits and the delegated producer seams; no historical
source facts were repaired. RRT-01/04/05/18 receive foundation evidence only.
**Verification:** Full regression run **1,305 passed / one skipped**; final selected
run **105 passed**, including **25 R1 tests**; focused Ruff, strict mypy on the four
new modules, documentation targets and `git diff --check` pass. See checkpoint
notes for the final-run sequence and non-fatal diagnostics.
**Next:** R1 committed as `bc96a1d`; continue the operator-selected R2 work below.
No public command, automatic generation, delivery or deployment is authorized.

### SPINE-093 — R2: recurring-task commands and manual reconciliation

**Status:** In progress (2026-11-10) — operator authorized R1 checkpoint and R2,
including the narrow prospective producer fixes. R1 committed as `bc96a1d`.
**Scope:** All seven internal command handlers, configuration/enrollment,
read/history/cursors, atomic ordinary task/owner/binding/policy/work creation,
move/cancel/restore/suppress, both adoption scopes and all retirement dispositions.
No partial public family registration or automatic invocation before later gates.
**Acceptance:** Real outer transactions/replay/rollback and no child commits;
strict-future commit and whole-unit budgets; distinct reminder identities and
immutable ownership without grants; lifecycle/adoption/retirement and cursor
positive/negative/race tests. Primary RRT-03/06/07/08/09/10/11/12/15/16/17 proof.
See [R2](IMPLEMENTATION_PLAN.md#r2--command-engine-and-manual-reconciliation-spine-093).
**Progress:** First internal increment implements forward-only copied-segment
ancestry, positive following/COUNT-copy lineage and the exposed COUNT authoring
projection/counting fix. Actual public-command tests consume the new evidence;
retained offline fixtures still reproduce without rewriting history. Internal
create/update/retire/show/list handlers, immutable profile/archetype/route snapshots,
receipt replay, dry-run rollback and purpose-separated cursor/read projections are
implemented behind explicit source-contract injection. No public dispatch changed.
See [R2 foundation](design-notes/recurring-related-task-r2-foundation.md).
**Verification so far:** Full regression run **1,322 passed / one skipped**;
final focused run **88 passed**, including 17 new foundation tests. Focused Ruff,
changed pure-module mypy, documentation targets and diff hygiene pass. R2 changes
were committed as `250b4fa`; no push, live migration, deployment or external audit.
**Continued progress:** The subsequent increment executes internal manual
reconcile/suppression and real ordinary child/owner/binding/profile/policy/work
composition. Selected source move/exclusion/restoration, terminal veto, three-way
adoption, intent conflict resolution and retirement cases now have real transaction
tests. Whole-unit work boundaries restore SQLite and Python finalizer state together.
See [manual-engine evidence and precise exit gaps](design-notes/recurring-related-task-r2-manual-engine.md).
**Latest verification:** Full suite **1,344 tests, OK (one skipped)**; selected
R1/R2/contracts/transactions **91 tests, OK**; overlapping writer parity/lifecycle
selection **73 tests, OK**. All 80 offline artifacts reproduce. Focused Ruff,
nine-file strict typing, compilation, documentation links and diff hygiene pass.
New writer inventories have actual empty/eight-facet and people/rendering parity
coverage. No normal schema/package/public activation changed.
**Remaining:** Exact byte-driven continuation and combined-budget accounting,
complete restoration/custom-policy and managed-set matrices, intent/coverage and
error-precedence closure, replay evidence and physical concurrency tests. The local
ownership epoch/bootstrap direction was selected by the operator: define
realm-independent trusted-local initialization, not implicit web provisioning.
The [bootstrap leaf](../specs/local-ownership-bootstrap.md) is ratified as design
v1.0.0 on 2026-11-10 following the clean review below. The operator selected
machine/migration definition, not runtime activation, for the next increment.
The manual-engine/draft increment is committed as `313a79e` (no push).
Its [bounded bootstrap consistency audit](../whetstone_runs/local-ownership-bootstrap-contract-audit-001/audit-notes.md)
completed against that checkpoint: seven exact specifications plus notes and
built-in context, configured GPT-6.1 Sol/medium through pinned stable Whetstone.
The operator explicitly approved that exact package on 2026-11-10; all
payload/runtime pins were verified before and after launch. The persisted
[report](../whetstone_runs/local-ownership-bootstrap-contract-audit-001/change_audit/change_audit_report.md)
is **pass**, boundary preserved, zero blockers/majors/minors/nits. This is one
bounded consistency assessment, not convergence; the subsequent explicit operator
ratification is separate from that verdict.
The [candidate machine package](../contracts/local-ownership-bootstrap.v1.json)
and [fixture manifest](../contracts/local-ownership-bootstrap-fixture-manifest.json)
define the closed state union, v3 explicit promotion, failure mapping, migration
blueprint and offline witnesses. Package review and actual implementation evidence
remain pending; no package/schema/runtime registry or public dispatch changed.
**Bootstrap definition verification:** 47 selected contract tests pass, including
eight new tests for 28 fixtures, 13 finite transition witnesses, canonical
plan/apply digests, exact row-ID reuse, offline schema closure and non-activation.
Focused Ruff, frozen web-copy synchronization, new local links and diff hygiene
pass. No runtime code or ledger was changed; SQL/race/migration obligations remain
explicitly pending, not satisfied by those offline tests.
R2 is **not complete**; selected passing tests do not close an
entire RRT obligation or authorize R3/R4.
**Next:** Operator authorized the remaining R2 implementation on 2026-11-10.
Review the new bootstrap machine/migration package before its implementation,
then continue the manual reconciliation/lifecycle engine against these tested
foundations. Preserve immutable history and the R4-only public activation boundary.

### SPINE-094 — R3: recurring-task all-writer safety and automatic scheduling

**Status:** Blocked by SPINE-093; planned, not started or separately authorized.
**Scope:** All existing source/target/relation/binding/owner/policy writers,
atomic invalidation/catalog/dirty-CAS integration, per-attempt current-truth
admission and fair bounded read-only scheduler planning. Preserve ordinary v1
bindings/tasks, attempted history and Tickerd ownership/safety boundaries.
**Acceptance:** RRT-13/14 plus final RRT-04/05/07/10/11/12/16/17/18 evidence:
explicit writer/reconcile/attempt interleavings, suppression/restoration and
pending-intent races, protected-work matrix, rollover/catch-up, dense-root fairness
and repeated idle zero-write cycles. No real sends. See
[R3](IMPLEMENTATION_PLAN.md#r3--all-writer-safety-and-automatic-scheduling-spine-094).
**Next:** Finish R2 and obtain the selected checkpoint's implementation kickoff.

### SPINE-095 — R4: recurring-task activation and release verification

**Status:** Blocked by SPINE-094; planned, not started or separately authorized.
**Scope:** Exact packaged closure, trusted-local public commands and dependencies,
implemented declarations, coherent migration/package metadata and generic operator
documentation. No web allowlist, authentication redesign or deployment procedure.
**Acceptance:** RRT-02 and all 18 obligations rerun with named real test evidence;
non-editable installed-wheel public CLI science-class scenario, exact pinned
dependencies, fresh/populated synthetic migrations, fake worker/attempts, full
documented suite and applicable lint/typing/compilation/sync/regeneration checks.
Change source-only assertions to implemented-behavior tests, not removed gates.
See [R4](IMPLEMENTATION_PLAN.md#r4--public-activation-and-release-verification-spine-095).
**Next:** Finish R3, verify the complete release and only then advertise the family.
Any live deployment or real-send test requires a separate operator request.

## Post-release corrective work

### SPINE-065 — Materialize follow-source reminders against successor time

**Status:** Done locally (2026-10-28) — the narrow runtime fix is implemented and
verified as 0.11.2/schema 19, selected for the operator-authorized local checkpoint
below; not deployed.
The earlier SPINE-064 delivery remains test-only; its acceptance module and the
existing `AGENTS.md` edit are preserved without changes. Reproduced the reported
missing replacement on `233656c` before editing. Runtime 0.11.2 retains schema 19
and all public contract selectors/pins. Push and deployment remain separate.
**Problem:** A bounded `schedule.binding.reconcile` moves a follow-source task and
cancels old work, but computes the `item_relative` materialization window from the
old due time. Moving the source by a day can therefore produce no replacement
reminder. [Relative bindings §7.6](../specs/relative-temporal-bindings.md#76-notification-work-reconciliation)
requires bounded materialization against successor truth.
**Baseline checkout:** Inspected main checkpoint `233656c` (runtime 0.11.1/schema
19). The [acceptance module](../tests/test_coordination_acceptance.py) was uncommitted
at the original handoff and is absent from that baseline commit. The new authorized
checkpoint includes its unchanged bytes with the fix, so a fresh checkout can run
the reproducer. Preserve the unrelated `AGENTS.md` edit; do not reset or stage it.
**Reproduce from repository root:**

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_coordination_acceptance.CoordinationAcceptanceTests.test_rescheduling_changes_followers_but_preserves_snapshots_and_delivery_history -v
```

The scenario creates an event at 2026-08-22 14:00 UTC, a follow-source task due one
hour earlier, and a snapshot task. It records one fake event delivery, moves the
event to the next day, and reconciles the follower with bounded `item_relative`
materialization. Event replacement reminders exist; snapshot work and prior
delivery evidence remain unchanged. The follower moves to 2026-08-23 13:00 UTC,
but the assertion expects its replacement work at 12:30 UTC and receives `[]`.
**Implementation starting point:**
`src/spine/commands/temporal_bindings.py:handle_binding_reconcile` normalizes
materialization using `_scheduled_for_target(target_current)` before the stale
branch derives `target_from_source(...)`. `_versioned_reconcile` then uses that
already-normalized window against successor policies. The same old-time
calculation is present in pre-integration main `75a4b95`; UTC reproduction does
not depend on the timezone compatibility change.
**Repair boundary:** Resolve the materialization window against the time belonging
to the selected reconciliation outcome. Preserve current/no-op, explicit detach,
terminal/unresolved, and snapshot semantics; keep command replay, atomic rollback,
policy lineage, and attempted-work history intact. Do not weaken the new assertion,
skip the scenario, widen its range to hide the defect, or introduce unconditional
extra materialization. Add focused coverage for affected branches, including dry
run/replay and relative versus explicit ranges where the fix changes resolution.
**Acceptance:** All five new stories pass, alongside the existing relative-binding
tests and complete documented unittest suite. Run full pytest with the existing
`PYTHONPATH=src:tests` workaround, Ruff, strict core/ledger mypy, and applicable
compilation/contract checks. Record exact results and any unrelated failures.
Use only disposable ledgers and fake delivery. No real sends, deployment, real
ledger access, unrelated refactoring, commit, or push is authorized by this handoff.
**Baseline evidence:** SPINE-064 records full-suite results: one failure in each
runner, both this regression; four other acceptance stories pass. No new test
dependency, running daemon, external service, or network access is required.
**Implementation (2026-10-28):** The stale-follow branch derives its target once
before materialization normalization; current/manual detach and other outcomes
retain their existing target basis. This also makes `local_range` use the resulting
timezone and pin. The corrected range exposed a second same-path defect: the
version writer copies policies before invoking the canonical extension, but updates
the current pointer afterward. Loading "current" policies in that extension chose
predecessor IDs, and the unchanged work-policy trigger correctly rejected successor
work. An exact-version ledger reader now supplies copied successor policies without
moving the pointer early or weakening constraints. Existing policy lineage,
transaction finalizers, work classifications and attempted history remain intact.
The unchanged acceptance story passes; 14 new regressions in
[successor materialization tests](../tests/test_binding_successor_materialization.py)
cover earlier/later moves, relative/local ranges, timezone changes, current repair/
no-op, equal-time refresh, dry run, replay, rollback, detach, snapshot refusal,
terminal targets and unresolved selected occurrences. The 27-test selected
acceptance/relative/new-regression run passes (3 subtests, 18.34 seconds); the final
14-test module passes independently (1.528 seconds).
**Verification:** Full documented unittest discovery passes **1,201 tests, one
skipped (289.244 seconds)**. Full pytest passes **1,239 tests and 1,892 subtests,
one skipped, one warning (292.53 seconds)**. All five existing acceptance stories
now pass without modifying their test file. The skip is the existing revision-
readback build harness without repository-local setuptools. The repeated warning
is the previously recorded synthetic serialization-deadline trace exception, not
a failed assertion; it remains outside this repair.

A fresh noneditable 0.11.2 wheel passes **72 installed binding/acceptance/timezone
tests and three subtests (28.80 seconds)** outside the checkout, plus the public
people verifier: eight HTTP routes, CLI, replay/history/dry-run, cursor paging,
frozen interfaces and deep disposable verification. `pip check` passes. The wheel
SHA-256 is `a70e8312f7389cc79d5121548a8d23f37100a279636df8f4d21e90f1a7a42aab`;
temporary artifacts are under `/tmp/spine-0112-hotfix.boz20i/`, not published or
durable external release storage. These checks use synthetic ledgers, TZif fixtures
and fake delivery only, not staging data or a provider-qualification claim.

Repository-wide Ruff, compilation (`src tests examples scripts`), all four package
sync checks, 277 local documentation link targets and diff hygiene pass. The final
documentation/declaration/scaffold check passes 12 tests (0.285 seconds). Strict
mypy is **not clean**: exact pre-fix `233656c` has the same 36 core/ledger errors in
10 files (52 checked), 37 focused temporal-binding errors, and one focused ledger-
notification `_rendering_pending` attribute error. Same-interpreter comparisons
match after line-shift normalization; neither addition introduces a diagnostic.
Unrelated typing/timeout repairs and the pre-existing bounded-terminal validation
discrepancy are not folded into this change. Legal `mode=none` branch controls pass.

No source schema, migration, machine contract, compiled family pin, Tickerd pin or
timezone-baseline policy changes. Existing receipts remain immutable: replaying an
older zero-work receipt does not repair it; fresh bounded current-state reconciliation
with a new command ID can repair eligible missing work. See the
[operator workflow](AGENT_OPERATOR_GUIDE.md#atomic-related-tasks-and-temporal-bindings).
The existing `AGENTS.md` and acceptance-module bytes are unchanged, and earlier
tracking is preserved. At verification, no staging/production ledger, external
send, Whetstone run, Git staging, commit, push or deployment had occurred.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python \
  -m pytest -o addopts='' -p no:cacheprovider -q tests
```

**Checkpoint authorization (2026-10-28):** The operator requested the focused
0.11.2 commit. Include the runtime repair, unchanged coordination acceptance
module that exposed it, fourteen new regression cases, version assertions,
installed verifier and operator/backlog/plan documentation. Exclude `AGENTS.md`.
Final selected binding/acceptance/version verification passes 32 tests and three
subtests (17.92 seconds). This authorizes a local checkpoint only, not a push or
deployment.

### SPINE-062 — Preserve timezone resolution across compatible tzdb upgrades

**Status:** Done locally — combined runtime 0.11.1/schema 19 is verified for the
operator-authorized merge of the timezone branch into people-enabled main on
2026-10-25. No deployment or push is authorized. The independent
runtime fix was implemented and locally verified on 2026-10-22; production
acceptance is separate.
Operator authorized both runtime patches on 2026-10-22.
Mainline 0.10.1 retains schema 19; maintenance 0.6.0+tzdb.1 retains schema 15 and is
based on confirmed production commit `a28bdf0e20cdb671e4a3862572d85c952f354056`.
The shared resolver and closed baseline catalog implement automatic full-TZif byte
identity against the original trusted authored version/zone reference, with coherent
provider capture, immutable provisioning and substitution diagnostics. Pins, receipts,
identities and ledger schemas are preserved. Full suites pass (mainline: 1117 tests; maintenance: 689 tests); each isolated wheel
passes 42 focused checks. See [validation evidence](TZDB_COMPATIBILITY_VALIDATION.md).
See [runtime contract](../specs/timezone-compatibility.md) and
[operator setup](TZDB_COMPATIBILITY_OPERATIONS.md).
**Integration correction (2026-10-25):** Commit `160547d` was pushed on
`fix/spine-062-mainline`, but not merged into the people release `83d1a96`.
Their common ancestor `ca9ea72` contains the specification only. Do not deploy
`83d1a96` as a replacement for an environment depending on the runtime fix.
Merge onto main checkpoint `75a4b95`, retain people v4/protected filters and all
existing packaged family pins, add cross-feature regressions and installed-wheel
verification, and preserve the unrelated `AGENTS.md` amendment. No production
backport changes, new schema, operator ledgers, real sends or external audit.
**Combined verification:** Full pytest passes **1,220 tests and 1,889 subtests,
one skipped, one warning (259.82 seconds)**. Pytest is required here: the 39
timezone cases are function-based and do not run under unittest discovery.
The selected timezone/people group passes 107 tests/14 subtests; four new cross-feature
HTTP regressions pass. A fresh noneditable 0.11.1 wheel passes the installed people
verifier (all eight HTTP routes and public CLI) and 43 installed timezone/integration
cases; `pip check` passes. Focused Ruff, strict typing of eight owners, all four
contract sync checks, 344 local link targets and diff hygiene pass. The skip is
the existing revision-readback build harness without setuptools. The warning is
an unraisable deadline-guard exception in a passing synthetic serialization-timeout
test; it reproduces in the merged focused case but not the exported pre-merge
31-test module. That guard/test are unchanged by the merge; no warning suppression
or broader timeout refactor is included. See the
[combined evidence](TZDB_COMPATIBILITY_VALIDATION.md#combined-peopletimezone-integration--2026-10-25).
The source companion's first-implementation version and all frozen package pins
remain unchanged; only the combined application version advances. Preserve both
timezone baseline and people cursor configuration at the separately authorized
rollout. The existing `AGENTS.md` amendment and concurrently created, unrelated
`tests/test_coordination_acceptance.py` are excluded from the local merge. The
recorded full-suite collection predates that unrelated test's appearance.
**Remaining operational acceptance:** Provision authenticated original Ubuntu
fingerprints and verify both route agendas on a disposable production backup.
The external agenda wrapper location remains unknown. No production changes made.
This task does not activate the deferred resilience roadmap.

### SPINE-061 — Implement people and responsibility

**Status:** Done locally — complete runtime 0.11.0 family verified on schema 19
(2026-10-24); Slice 4 is selected for the operator-authorized local checkpoint
below and remains undeployed. Private Slice 1 through S1d committed (`e7c1a41`), followed
by the scoped directory/standalone foundation at `c937661` and Slice 2 integration
at `1e5abf9`. Slice 3's private work-state/race increment is locally verified
(2026-10-24) and committed at `17b3d3e`. Slice 4's cohesive public successor/package
implementation closes the bounded PR-01–16 runtime map below; no published release,
deployment or consumer adoption is claimed.
The operator accepted the completed A/B/C
reviews and verified corrections as sufficient to close the machine-contract
review prerequisite and move into implementation planning. This is a bounded
acceptance of the review evidence, not an independent whole-bundle re-audit,
convergence, runtime acceptance or permission for migration/deployment. No runtime
edits were started under that planning step. The operator subsequently explicitly
authorized S1a implementation; its evidence and limits are below. The earlier 2026-10-17 implementation
request and the subsequently imposed review hold remain recorded below.
**Baseline:** Source-only machine checkpoint `9ef74c5b10511b1d226dcddf6cbf80a64c288bdc`
(`Codify people and responsibility contracts`), committed locally; not pushed.
All 202 contract-focused tests and checkpoint diff hygiene passed again.
**Intended scope:** Implement the accepted participation/assignment, scoped directory,
successor authoring/read and role-only continuity contracts with PR-01–16 executable
evidence; preserve current interfaces and independent ownership/routing semantics.
No partial capability activation, operator-ledger access, send or deployment.
**Review preparation:** Operator requested the bounded review on 2026-10-17.
Staged [people-and-responsibility-machine-contract-audit-001
notes](../whetstone_runs/people-and-responsibility-machine-contract-audit-001/audit-notes.md)
against exact checkpoint `9ef74c5`, with 121 inventoried source files, built-in
consistency profile and proposed Codex `gpt-6.1-sol` reviewer. Includes all new
schemas, their manifest-declared closure, fixtures/models/test and necessary
logical/compatibility authorities. No source edit or reviewer invocation occurred.
**Review execution:** The operator explicitly approved the 121 listed sources,
notes, built-in reviewer/consistency-profile context and generated audit copies.
All hashes match checkpoint `9ef74c5`; one reviewer-only audit-change was attempted.
**Review outcome:** `audit_failed` before substantive review: nested client
`turn/start` rejected 1,501,016 characters against its 1,048,576-character input
limit (`input_too_large`, code -32602). No semantic feedback was produced and
boundary preservation was not assessed. All 121 sources and notes remained
unchanged. See the retained [execution summary](../whetstone_runs/people-and-responsibility-machine-contract-audit-001/execution-summary.md)
and original change_audit failure artifacts. No Editor, source correction, automatic
retry or runtime implementation occurred.
**Runtime prerequisite:** The operator-selected Whetstone stable installation is
available on 2026-10-17: checkpoint `6e19fe3e72dedda50a372781a43c08e5d7e7480a`,
reported version `0.1.0`. Spine verified stable resolution and the bounded-audit
CLI through `whetstone --channel stable`; actual machine paths remain outside Git.
This satisfies the earlier setup deferral, not the machine-contract review itself.
**Split review preparation:** Part A is staged locally in
`whetstone_runs/people-authoring-machine-audit-001/`: 69 unchanged source files plus
review notes, exact hash inventory and the selected stable runtime's complete prompt
preview. The prompt is 814,306 characters (814,379 UTF-8 bytes), below the prior
1,048,576-character limit with approximately 22% headroom. Scope is authoring,
replay/no-op and role-only continuity; its 25-schema closure and 25 mutation fixtures
are explicit. Model is `gpt-6.1-sol`, medium reasoning as set by the pinned adapter;
the machine-local guarded Codex launcher reports `0.163.0-alpha.10.2`.
**Part A follow-up (2026-10-17):** The authorized first review completed with no
blockers, one major and two minors (`needs_revision`). The local failure schema
now permits the required optional true-only dry-run marker; the pure continuity
witness preserves unmanaged roles; and the logical spec defines the complete v4
changed-dimension order. All 44 selected people/scheduling/continuity contract
tests pass. These remain source-only contracts and pure-model evidence, not
transactional runtime acceptance. The operator requested a full Part A recheck,
not a findings-only recheck. Its new package under
`whetstone_runs/people-authoring-machine-audit-002/` contains 71 sources plus
notes; the rendered prompt is 817,901 characters / 817,974 UTF-8 bytes.

The full Part A recheck completed `pass_with_minor_clarification`, boundary
preserved, zero blockers/majors and two minors. Both are patched locally: include
the inherited exclusive `policy_presentations` branch in the complete v4 order;
bind the continuity witness to one explicit replacement role, preserving the
opposite role even on clear. All 45 selected contract tests, focused lint and diff
checks pass. The two minor patches have no separate external recheck; the operator
requested proceeding to B. Reports and the initial local-access failure remain
unchanged as evidence.

**Part B preparation:** `whetstone_runs/people-read-machine-audit-001/` stages the
full discovery/disclosure/reads/cursors and protected-transport boundary: 86 inputs,
37-schema dependency closure, 25 wire fixtures plus notes. The rendered prompt is
964,877 characters / 964,922 UTF-8 bytes, below the known 1,048,576-character limit.
The large agent-command source is included as exact source-hashed named sections;
omitted write-family/registry-table sections are explicit, not silently reviewed.
Shared sources include the local A corrections. No B verdict is recorded yet.
The execution permission layer blocked launch pending explicit approval of the
exact 86-input package plus notes and its external Codex destination. No reviewer
was launched; staging remains intact. The operator subsequently explicitly
approved the exact manifest-bound 86 inputs plus hash-bound notes for external
Codex `gpt-6.1-sol` at medium reasoning. Pre-launch verification matched all input,
notes and preview hashes, stable checkpoint and CLI version. The reviewer-only
audit completed through the normal execution permission mechanism:
`needs_revision`, boundary not preserved, zero blockers, one major, zero minors.
The [report](../whetstone_runs/people-read-machine-audit-001/change_audit/change_audit_report.md)
identifies a confirmed contract mismatch: the people optional-section union omits
inherited `scope`/`coverage` fields and permits incompatible unavailable reasons.
All three inherited envelope states fail that schema, while the existing 16 people
contract tests pass; inherited-envelope regression coverage is missing. Sources
remain unchanged by this review. See the retained
[execution summary](../whetstone_runs/people-read-machine-audit-001/execution-summary.md).

**Part B correction:** Applied locally with operator approval. The people-section
union now requires `scope=authorized_only` in every branch, complete coverage for
available projections, and incomplete coverage with `context_unavailable` for
unavailable projections. Not-requested sections have no payload/coverage/reason.
Schedule/agenda fixtures are aligned; two manifest-declared section-state fixtures
and three regressions cover inherited-envelope parity, closed states, and nested
schedule/agenda/unplaced results. New regressions failed before the correction.
All 48 selected people/scheduling/facet-continuity tests plus 15 independent-read
contract tests, focused Ruff and diff hygiene pass. Existing A corrections remain
intact. The original B report is unchanged: this is a verified local patch, not a
new external pass. See the
[patch follow-up](../whetstone_runs/people-read-machine-audit-001/patch-followup.md).
No runtime code, schema migration, audit launch, commit or push.

**Checkpoint (2026-10-18):** A/B source corrections, fixtures/tests and tracking are
committed as `7260cbb90255d130883e5fa5fb10f0589510c775`
(`Align people contracts with authoring and read invariants`). All 63 selected
offline tests, focused Ruff and diff hygiene passed again. No push. The separate
pre-existing `AGENTS.md` stable-launcher amendment remains uncommitted and preserved.

**Part C preparation:** Staged the focused integration review in
`whetstone_runs/people-integration-machine-audit-001/` at that checkpoint. The
[notes](../whetstone_runs/people-integration-machine-audit-001/audit-notes.md) and
SHA-256-bound inventory enumerate 68 inputs: 36 complete schema documents/dependency
closure, 17 selected wire fixtures, exact source-hashed replay/protected-web section
context, logical authorities, witnesses/tests and the prior finding/follow-up evidence.
The rendered prompt is 762,773 characters / 762,814 UTF-8 bytes. Scope is written/read
role projections, current/history, replay/disclosure and mutation/cursor consistency,
including the two corrected A minors and B's corrected optional-section envelope.
This is not a full A/B re-audit. Stable checkpoint `6e19fe3`, Codex CLI
`0.163.0-alpha.10.2`, `gpt-6.1-sol`, medium reasoning and consistency profile are pinned.
The operator explicitly approved those 68 inputs, notes, consistency context and
generated copies on 2026-10-18. All payload/section-source hashes, prompt preview,
source checkpoint, stable runtime and CLI version matched. The reviewer-only audit
completed through the normal execution permission mechanism:
`pass_with_minor_clarification`, boundary preserved, zero blockers/majors, one minor.
The [report](../whetstone_runs/people-integration-machine-audit-001/change_audit/change_audit_report.md)
identifies a confirmed offline no-op identity mismatch: the positive no-op fixture
and shared success assertion require a row ID derived from the current command,
instead of retaining the prior persisted association ID at the unchanged version.
The narrow correction is a distinct prior-command vector/ID for no-op and separate
identity assertions for no-op versus changed success/replay. No source patch was
made; prior corrected A/B findings were not re-raised. See the
[execution summary](../whetstone_runs/people-integration-machine-audit-001/execution-summary.md).

**Part C correction (2026-10-19):** Applied locally with operator approval. Added
`existing_managed_row_id` with a distinct prior command and exact canonical bytes/
digest; the no-op fixture retains that association ID. The shared receipt check now
separates no-op retention from changed/replayed/preview replacement derivation.
A dedicated regression failed against the old fixture, then passed after correction.
All 64 selected people/scheduling/facet-continuity/independent-read contract tests,
focused Ruff and diff hygiene pass. See the
[patch follow-up](../whetstone_runs/people-integration-machine-audit-001/patch-followup.md).
Logical/schema/runtime semantics and original review artifacts remain unchanged.
This is local verification, not a new external review or implementation acceptance.
No runtime edit, migration, reviewer invocation, commit or push.

**Checkpoint authorization (2026-10-20):** The operator authorized a local commit
of the narrow no-op fixture/vector/test correction and its tracking evidence.
All 64 selected contract tests, focused Ruff and diff hygiene were rechecked
before staging. The unrelated stable-launcher `AGENTS.md` amendment is excluded;
no push or machine-review gate closure is authorized by this checkpoint.

**Review acceptance (2026-10-20):** After discussing the limits of the evidence,
the operator accepted proceeding into implementation planning. Correction checkpoint
`3399327` contains the no-op identity fixture/vector/test and tracking record.
A/B/C are behavioral partitions, not automatic whole-bundle closure or convergence;
the review prerequisite is now explicitly accepted by the operator. All PR-01–16
runtime obligations remain pending. No further audit, runtime edit, migration,
deployment or push is started by this acceptance.

**Implementation plan (2026-10-20):** The operator requested the concrete plan.
The existing implementation-plan document now maps storage, selected-role copy/
replacement, CAS version writer, transaction/receipt ownership, legacy task-role
compatibility, scheduling successors, permission owners and distinct people-only
continuity. It sequences private foundation, transactions/proof, local handlers/
scheduling and parity evidence, followed by reads/disclosure, full continuity,
public/installed qualification. S1a (normalization/identity plus bounded exact-version
reader) is the recommended first executable sub-slice. No migration is allocated;
every PR-01–16 runtime obligation remains pending. No runtime job has been started.

**S1a foundation implementation (2026-10-20):** Explicitly authorized by the
operator. `core/people.py` now implements closed role-patch normalization with
omit/create/clear distinctions, Unicode-scalar opaque IDs and array bounds,
complete active/inactive managed-set comparison/hash, fresh-add/reactivation
selection (not permission approval), and existing command-derived replacement IDs.
`ledger/people.py` adds one-statement bounded exact-version/current readback with
separate current version, sorted managed associations and an over-limit sentinel
counting all role kinds. It does not look up labels, change facts, resolve access,
or activate any public surface. New tests cover Unicode/duplicates/limits,
inactive and opposite-role semantics, the reviewed ID vector, read-only historical
identity, terminal/unscheduled items, safe failures and exact/over-limit snapshots.

**Verification:** 17 new tests and the related ledger/transaction plus reviewed
contract suites pass together: **112 tests, 3.925 seconds**. Focused Ruff and
`git diff --check` pass. Strict mypy passes both new source files. The broader
core/ledger mypy command reports 36 errors in ten unchanged files; excluding the
two new modules yields the same 36 errors (49 existing versus 51 total files).
No unrelated typing cleanup or full-repository passing claim is included. Public
registries, package/version declarations, frozen schemas and legacy helpers are
unchanged. All PR-01–16 whole-feature runtime obligations remain pending; this
is only private foundation evidence, not implemented public people commands.

**S1a checkpoint authorization (2026-10-20):** The operator requested a local
checkpoint of the private foundation, its tests and the review-acceptance/planning
records. All 112 selected tests pass again (3.980 seconds), with focused Ruff,
strict typing for the two new modules and diff hygiene clean. The separate
pre-existing `AGENTS.md` launcher guidance is excluded. This checkpoint does not
authorize a push, public activation, migration or the next implementation slice.

**S1b started (2026-10-21):** The operator authorized transactional implementation;
this is now actual source work, not a queued job. A private outer-transaction-only
role writer uses the existing CAS allocator, deterministic managed rows, no-op
detection and mandatory fresh-addition admission callback. A separate role-only
proof preserves strict facet equality and checks unchanged facets, policy meaning,
immediate policy bijection and presentations. The writer inventory and existing
empty/eight-facet producer tests include the new path. No public commands are wired.
Disposable-ledger tests exercise replacement/history, unmanaged-role retention,
ineligible retained references, lifecycle/stale refusal and rollback after policy,
audit and test-caller receipt writes. Repeated event role edits preserve stored
facets, eligible reminder work and attempt history. Full worker/scheduler edge
classification, command receipt/replay/admission integration and the remaining
continuity matrix are not yet complete. Changes remain local and uncommitted.

**S1b first-increment checks:** 185 selected tests pass (29.548 seconds), including
12 new private authoring tests and existing writer/rendering-storage regressions.
Focused Ruff and strict typing of the new module pass. No full-suite or public
acceptance claim is made.

**S1b resumed (2026-10-23):** Operator confirmed production is stable and selected
continuing people implementation. Finish the private transactional/continuity seam
and verify before checkpointing; keep timezone compatibility separate. No public
activation or deployment. Existing working-tree changes are preserved.

**S1b verification checkpoint (2026-10-23):** The private transaction/continuity
prerequisite is implemented and verified. The shared worker/
scheduler policy resolver now validates people-only edges and mixed facet/presentation
edges under distinct unchanged-fact proofs, with exact historical policy capture,
deterministic IDs, policy bijection and a 100-version ancestry bound. Unsafe/skipped
people edges or capacity failure refuse without cancellation or work/attempt rewrites.
Existing ordinary mutations keep their owning reconciliation rules. The tests now
include actual outer rollback/finalization, scheduler no-op/read-only behavior,
intermediate-history drift, mixed proofs, work states, route staleness and follow-source
freshness. No durable proof table/cache or schema change was introduced.
247 selected tests passed before a full-suite regression revealed needless facet
reads on revoked-rendering fallback. That classification read was removed; all 39
focused people/lineage/revocation tests pass, as do Ruff, new-module strict mypy
and diff hygiene. The corrected full suite passes: **1,102 tests, one skipped,
166.853 seconds**. The shared-module typing check has
one unchanged pre-existing `_rendering_pending` diagnostic; it is not hidden as a pass.
The original 12 authoring tests plus 12 added transaction/continuity checks are
included in that full run. Public command wiring, actual people receipt/replay/admission and dry-run handlers
remain S1c work; full protected disclosure and race matrices remain later slices.

**S1b checkpoint:** The operator selected finishing/checkpointing S1b before S1c.
Checkpoint the eight cohesive implementation/test/tracking files; preserve the
separate pre-existing `AGENTS.md` edit. No push or public activation.

**S1c started (2026-10-23):** The operator selected private local handlers,
canonical receipt/replay/dry-run integration and atomic scheduling-v4 people
authoring. Reuse the S1a/b shared normalization, writer and continuity proof; do
not expose a partial public family. Directory pagination, protected transport and
complete release/race evidence remain later slices. Preserve the existing
`AGENTS.md` edit. No audit, commit, push, migration or deployment is authorized.

**S1c local result:** The private candidate now supplies standalone show/update,
canonical changed/no-op/replay receipts, deterministic previews with real transaction
rollback and existing finalizers, and atomic scheduling-v4 people integration.
Mixed composites produce one version; selected-role replacement preserves unmanaged
roles and old interfaces. People-only v4 edges use indexed receipt evidence and
the distinct role proof, without cancellation/materialization. Current local labels
are read, never stored in receipts. Protected contexts cannot enter this local path;
owner-scoped protected admission, replay disclosure and shared label/release checks
are explicitly pending rather than bypassed. Public family/registries and schema
are unchanged. 26 new handler tests, 193 selected regressions, focused Ruff, strict
typing of the three people modules and diff hygiene pass. The full suite passes:
**1,128 tests, one skipped, 178.820 seconds**. The final defensive receipt-type
check also passes the focused 26-test rerun. This verifies the private local
increment, not protected admission or whole-family acceptance. The changes were
uncommitted at that verification; the authorized checkpoint is recorded below.
The separate pre-existing `AGENTS.md` change is preserved.

**S1c checkpoint / S1d started (2026-10-23):** Operator authorized committing S1c
and proceeding with S1d. Checkpoint `d050ca3` contains only the twelve cohesive
implementation/test/tracking files; the existing `AGENTS.md` edit remains outside
it. Rechecked 26 handler tests, focused Ruff and staged scope; no push. S1d now
reconciles actual role-copy/replacement identities, version producers, transaction
parity and per-PR remaining dependencies on disposable ledgers. Keep all successor
capability and package activation gated. No new external review or deployment.

**S1d current result:** A real-allocator observer exercises all 25 existing version
producers, checking complete role copy/replacement, immutable old rows and actual
transactions/finalizers. The same inventory now links those people-specific tests.
This exposed a canonical copy-ID mismatch in S1c; the exact regression failed
against the checkpoint, then passed with an explicit people-successor copy operand.
Legacy callers retain their copy IDs. No old data, schema or frozen contract changed;
one inaccurate "existing" word in the logical spec is clarified. New tests also
check all unmanaged roles, active agents/accountless people and nonempty adopted
ownership/routing/work preservation. See the
[PR-01–16 evidence map](PEOPLE_RUNTIME_EVIDENCE.md) for precise partial evidence
versus pending admission, disclosure, filtering/cursors, work/race and installed
public gates. **198 selected tests pass (41.860 seconds)**, as do focused Ruff,
strict typing of six runtime owners, 214 local link targets and diff hygiene.
The full suite passes: **1,133 tests, one skipped, 186.307 seconds**. This closes the private S1d
evidence increment, not protected admission, every Slice 1 acceptance item or
whole-family PR qualification. The pre-existing `AGENTS.md` edit is untouched.

**S1d checkpoint authorization (2026-10-24):** Operator requested the focused
commit. Rechecked all 31 people command/writer-parity tests, focused Ruff, strict
typing of six runtime owners and staged diff hygiene. Exclude the separate
`AGENTS.md` edit; no push or next-slice implementation is authorized by this request.

**Next:** Slice 2 scoped
discovery/admission/label/filter/cursor work under the selected sequence.
Keep capability/package activation gated on complete
applicable runtime evidence. No external review, push, migration, operator-ledger
access or deployment occurred.

**Slice 2 started (2026-10-24):** Operator explicitly authorized implementation
from S1d checkpoint `e7c1a41`. Build shared roster/reference/label authority and
bounded cursor-backed discovery, then integrate protected people projections and
person filtering with the existing independent-read owners. Preserve D-01/D-02,
legacy self-only views, private candidate gates and all existing worktree changes.
No public activation, audit, commit, push, migration, operator ledger or deployment
is authorized by this request. Verification uses disposable ledgers only.

**Slice 2 private foundation result (2026-10-24):** Shared scoped roster/reference
and current-label authority, local/protected `pc1` roster paging, and protected
standalone show/update/replay now execute on disposable ledgers. Item grants do not
grant roster/fresh-reference access; existing references can be retained/removed.
Historical role IDs and current directory labels remain separate. Protected reads
are query-only and use fresh source/authority/identity release fences; failed write
release rolls back version/role/audit/receipt/attribution-link facts. Cursor vectors,
canonical encoding, key generation, future membership transitions without epoch bumps,
resource limits and hidden-label noninterference are tested. No persistence/schema
change or public/packaged activation. The existing transaction inventory records the
new private protected outer entrypoint; no new allocator or parallel role registry.

**Verification:** 126 selected people tests passed (16.361 seconds); the full run
passed **1,167 tests, one skipped (202.126 seconds)**. After the last two added
key-rotation/actor tests and defensive refinements, the final focused run passes
**69 tests (29.042 seconds)**. Focused Ruff, strict typing of six runtime owners,
local documentation link targets and diff hygiene pass. This is partial runtime
evidence, not completion of Slice 2 or whole PR-05–08/12/16 acceptance. The unrelated
`AGENTS.md` edit is unchanged; no commit/push/audit/live ledger/deployment.

**Next within Slice 2:** Protected scheduling-v4 fresh/replay admission and the
independent-read integration: optional people sections, authorized person filtering
before temporal expansion, successor read cursors/source/authority proofs, optional
core-reserve degradation and complete cost/race matrices. Keep frozen/self-only
surfaces unchanged. [Evidence and remaining gates](PEOPLE_RUNTIME_EVIDENCE.md).

**Checkpoint / integration authorization (2026-10-24):** Operator authorized
committing this private directory/standalone increment and proceeding with remaining
Slice 2 integration. Exclude the pre-existing `AGENTS.md` edit. Recheck the focused
69-test group, lint and staged diff hygiene before checkpointing. Continue protected
scheduling admission and the independent-read integration without public activation,
external review, push, migration, deployment or operator-ledger access.

**Checkpoint result:** `c937661` contains the thirteen cohesive directory/standalone
implementation, test, inventory and tracking files. The focused 69 tests pass again
(28.962 seconds), with lint and staged diff hygiene; the pre-existing `AGENTS.md`
change is excluded. No push. Remaining Slice 2 integration began from this checkpoint.

**Slice 2 integration result:** Private protected scheduling-v4 now reuses the real
people/rendering hooks, version allocator, route/catalog/reference permission owners,
normal creation ownership/history and atomic receipt attribution. Event participants
and task assignees create, preserve, replace and clear in the composite transaction;
equal replacements keep original IDs. Owner scope is explicit on creation, and
fresh references use that scope, never model-authored identity or unrelated groups.
The exact prospective create owner is admitted internally and persisted after the
item exists but before presentation selection, so approved definition rendering can
compose without an unowned intermediate commit or implicit disclosure grant.

Private schedule/agenda/occurrence successors reuse existing temporal, optional
evidence and ordering owners. People labels are a separate complete optional section;
frozen self-only `subject_roles` is unchanged. Current active role predicates run
after item authority and before temporal expansion. Nonmatching/hidden person IDs
do not trigger identity lookup, nonmatching agenda roots do not enter source facts,
and unavailable-time matching tasks remain unplaced. Stateless `pc1` pages cover
existing section/occurrence and resolved/unplaced streams, with fresh identity,
authority/source/assembly fences and one request-global SQL/time/byte/resource budget.
Only the new private family selects the bounded candidate/projection seams; released
read defaults and public registries/assets are unchanged. No schema/migration.

**Integration verification:** 206 cross-feature tests passed (79.066 seconds), then
the full regression run passed **1,203 tests, one skipped (211.483 seconds)**. The
final focused run, including the subsequently added future label-roster membership
transition case, passed **35 tests (13.822 seconds)**. Focused lint/diff hygiene and
strict typing of six people owners pass. A structural check of both new orchestration modules passes
with untyped definitions/calls/globals allowed; broader strict web/rendering typing
is not clean and is not claimed. See [current evidence](PEOPLE_RUNTIME_EVIDENCE.md).
No whole-family PR qualification or public activation is inferred from these checks.
The integration remains uncommitted; checkpoint `c937661` is not pushed and the
pre-existing `AGENTS.md` edit remains preserved. Next planned slice: full work-state,
lease/mixed-lineage and temporal-source race coverage, retaining remaining read
cost/concurrency matrices and installed/public activation gates explicitly.

**Slice 2 checkpoint authorization (2026-10-24):** Operator requested this focused
commit followed by Slice 3. The final people read/scheduling/protected/contract
group passes **71 tests (17.328 seconds)**; focused Ruff and diff hygiene pass.
Exclude the preserved `AGENTS.md` change. No push or public activation. Slice 3
will exercise the shared work-state, lease/mixed-lineage and temporal-source
freshness contracts on disposable ledgers, preserving the remaining Slice 4 gates.

**Slice 3 started (2026-10-24):** Checkpoint `1e5abf9` includes fourteen cohesive
Slice 2 integration/test/tracking files; the unrelated `AGENTS.md` edit remains
excluded and nothing was pushed. Implement and verify PR-09–11/13/16 work-state,
mixed-edge, recurring/relative-source and writer/lease/attempt race cases through
the existing owners. Preserve exact work/attempt evidence under valid people-only
edges; independently stale or invalid continuity must fail closed, not silently
cancel/resend. No public family activation, new persistence, Whetstone, operator
ledger, send, migration, deployment, further commit or push is authorized.

**Slice 3 result:** Twenty-four new real-ledger regressions exercise exact
eligible/selected/in-progress/retry/started/terminal/absent work, same-intent
ordinary/definition siblings and disabled policy bijection, unchanged attempt
payload/history/provider identity, actual two-connection version/attempt/roster
writer exclusion, stale retries, and prepared-versus-started rendering fences.
Recurring provenance, actual recurrence replacement, item/selected-occurrence
follow-source invalidation and explicit unchanged-time refresh are covered;
snapshot bindings remain non-governing. Exact people-family permission races
cover external grant revoke, timed grant expiry/activation without epoch writes,
and initiating replay after edit/roster loss but not after read revocation.
No runtime defect was confirmed: the existing owners satisfy these exercised
contracts, so no production logic, persistence, schema or package change is made.

**Slice 3 verification:** The affected owner group passes **168 tests (30.921
seconds)**. Full discovery passes **1,224 tests, one skipped (221.161 seconds)**;
the final **86-test** group, including the four permission-race tests added after
full discovery began, passes in **29.380 seconds**. Focused Ruff, strict typing of
six unchanged people runtime owners, 223 local link targets and diff hygiene pass.
See the [per-PR evidence map](PEOPLE_RUNTIME_EVIDENCE.md). At verification the Slice 3
tests/tracking were uncommitted and `AGENTS.md` remained preserved. No push, audit, migration,
operator ledger, send or deployment. Slice 4 retains installed CLI/HTTP/frozen
qualification and every remaining cost/concurrency/complete-family gate before
activation; none is waived by this private verification.

**Slice 3 checkpoint authorization (2026-10-24):** Operator requested the focused
commit. All 24 new regressions pass again (7.442 seconds), with focused Ruff and
diff hygiene. Include only the three new test modules and their backlog/plan/
evidence updates; exclude the pre-existing `AGENTS.md` change. No push, Slice 4
implementation, public activation, migration or deployment is authorized here.

**Slice 4 started (2026-10-24):** Operator explicitly selected the cohesive final
implementation slice: remaining bounded/privacy/access evidence, exact local and
protected HTTP successors, complete installed schema/registry closure, public
CLI/HTTP parity, frozen compatibility and operator documentation. Preserve all
existing command versions, self-only read contracts and the `AGENTS.md` edit.
Implementation may declare the complete verified runtime family, but not advertise
partial capability or infer staging/Packs/UI adoption. No push, Whetstone, live
ledger, migration, external send, deployment or further commit is authorized.

**Slice 4 result (2026-10-24):** Runtime 0.11.0 activates the complete reviewed
family: three standalone local people commands, additive schedule create/update
v4, and exactly eight protected HTTP v3 operations. The independently pinned
39-asset package contains all 36 schema documents; missing/tampered assets or
required declarations fail closed without source fallback. The frozen web,
rendering and revision-readback bundles are unchanged. Schema 19, physical storage,
Tickerd requirements, existing command versions, compact receipts and self-only
read projections are preserved. `jsonschema` is now a declared base dependency
because local public commands validate the installed contracts.

The remaining capacity/privacy tests verify exact role/candidate/roster sentinels,
indexed owner/group/grant/role probes, shared snapshot budgets and filtering before
expansion/pagination. Adding 3,000 hidden roots and 3,000 unrelated grants leaves
the dense authorized response/cursor and measured 44,800 VM-step cost unchanged.
Transport coverage verifies all routes, selected identity, permission failures,
decoded inner-result parity, deadlines and serialization rollback. A real
noneditable installed wheel passes public CLI/HTTP, history/no-op/replay/dry-run,
roster/occurrence pagination, frozen interfaces and deep disposable verification.

**Slice 4 verification:** Final full discovery passes **1,263 tests, one skipped
(260.364 seconds)**. The skip is the pre-existing revision-readback wheel harness
without local setuptools; it is not represented as executed. The separate prepared
installed-wheel verification returns `PASS` with eight HTTP routes, 36 packaged
schemas and zero real sends; `pip check` passes. The final selected public/contract/
documentation group passes **67 tests (39.635 seconds)**. Focused Ruff, strict
typing of six people owners, all four package sync checks, 371 local documentation
link targets and diff hygiene pass. The final documentation/declaration/scaffold
check passes 12 tests (0.252 seconds).
The preceding full run had only two stale 0.10.0 version assertions; both were
corrected to 0.11.0 before the final full run. Exact hashes, commands and acceptance
limits are in [runtime evidence](PEOPLE_RUNTIME_EVIDENCE.md#slice-4--public-transport-package-and-bounded-read-completion).

[Operator instructions](PEOPLE_COMMANDS.md) are linked progressively from the
quickstart/guide. A separate protected people cursor file enables roster paging
and the whole v3 web family (`SPINE_PEOPLE_CURSOR_CONFIG` locally;
`--people-cursor-config` for web). Bad/missing web configuration disables v3, not
valid older families. This is not stronger authentication, a new grant, or routing.
The unrelated `AGENTS.md` edit is preserved. No Whetstone run, operator ledger,
migration, external send, commit, push or deployment occurred. The next operational
step is an explicitly authorized focused checkpoint, followed by a separately
authorized rollout and consumer adoption; no retained roadmap item is selected.

**Slice 4 checkpoint authorization (2026-10-24):** The operator requested the
focused local implementation commit after reviewing the Specification chat's
completion report. Include the cohesive 0.11.0 runtime, packaged contracts,
tests and operator/delivery records. Preserve the unrelated `AGENTS.md` change.
This authorization includes neither pushing nor deployment or consumer adoption.

### SPINE-060 — Ratify and codify people and responsibility

**Status:** Done — logical v1.0.0 ratified; source-only machine candidate v0.1.0
and offline evidence codified/verified, 2026-10-16. Machine review and all runtime
obligations remain pending; no implementation or exposure is claimed.
**Scope:** Accept logical v1.0.0; define closed standalone and successor authoring/read
schemas, planned registry, permission/error/cursor/budget and role-only continuity
rules, offline fixtures and tests. Preserve existing runtime and packaged web pins.
**Boundary:** No runtime, DDL/migration, live ledger, frontend/Packs, nested review,
commit, push or deployment. Machine codification requires its own review before
runtime activation. Approved D-01/D-02 are not reopened by technical encodings.
**Delivered:** [Accepted logical leaf](../specs/people-and-responsibility.md),
[planned registry](../contracts/people-and-responsibility.v1.json),
[fixture manifest](../contracts/people-and-responsibility-fixture-manifest.json),
12 closed source-only schemas and explicit 24-schema dependency closure. Covers
three standalone commands, additive scheduling v4 candidates and protected people/
independent-read successors; current selectors, web registries, compiled declarations,
physical schema and packaged contracts remain unchanged. Exact request/effect/replay,
permission/disclosure, identity, error, cursor, budget, proof and indexed-query
requirements are codified. Role-only continuity is separate from facet-only equality;
source-event edits retain existing follow_source invalidation semantics.
**Evidence:** 49 positive/negative wire fixtures; 44 declared pure-model cases;
four exact canonical preimage/hash vectors and two deterministic test-only cursor
MAC vectors. The 12 new offline tests and all 202 contract-focused tests passed;
Ruff, four contract synchronization checks, local links and diff hygiene passed.
No runtime, existing schema, packaged bundle or dependency change; no live ledger,
nested review, commit, push or deployment. Fixture/model evidence is explicitly not
transaction, authorization, query-plan, installed-transport or worker proof.
**Next:** Checkpoint and obtain approval for a bounded machine-contract review.
After that gate, plan/implement PR-01–16 with exact runtime declarations and executable
public CLI/HTTP, writer/finalizer, query/concurrency and work-state evidence. No
additional product decision is currently identified; D-01/D-02 remain unchanged.

### SPINE-059 — Draft people and responsibility contracts

**Status:** Done — first specification draft and consistency amendments verified
2026-10-16; product policies D-01/D-02 subsequently approved the same day and bounded
review passed. Ratification/codification is separately tracked by SPINE-060;
implementation remains pending.
**Baseline:** `8f3c50b6fd1b4aa534e50925b7417a7a80d19122`, runtime 0.10.0/schema 19.
**Scope:** One [logical leaf](../specs/people-and-responsibility.md) over existing
subjects, memberships and versioned subject roles. Specify participation versus
assignment, preserve access ownership and routing, outline scoped discovery,
authoring/read/filter successors, role-only work continuity and acceptance fixtures.
**Boundary:** No runtime/SQL/schema/package changes, machine-contract publication,
ratification, Whetstone execution, deployment, UI or Spine Packs edits. The operator
subsequently authorized a local checkpoint and bounded-audit preparation, not a push
or nested review.
Do not treat a subject role as a grant, recipient or account; do not relax existing
web checks or facet-only continuity to implement this feature implicitly.
**Product decisions:** D-01 approved current group-roster discovery for all active
member/admin/owner roles, with independent item-create/edit checks and fresh reference
eligibility restricted to the item's owner scope. Cross-scope assignment remains
deferred, including private tasks assigned to another shared-group member. D-02
approved item-read disclosure of association IDs/roles/statuses, with separate current
authority for directory labels and no private-record access. Both were confirmed on
2026-10-16; neither changes current runtime permissions. No additional
family/beneficiary/driver taxonomy is selected.
**Delivered:** Draft v0.1.1 defines the four independent dimensions; series-level
event participants and task assignees; replacement/history semantics; unscheduled
assignment; operator-approved roster/association disclosure policies;
standalone/composite/read successors; and a separate role-only continuity proof. It explicitly preserves
current self-only HTTP rules and facet-only equality. Ten acceptance families and
the physical/cursor/error/package codification gates remain explicit; no machine
artifacts or runtime readiness is claimed.
**Verification:** Reviewed existing role schema, task authoring, web reference and
projection restrictions, access policy and facet continuity. All 10 changed/new
files are Markdown; 283 local link targets, authority/status/tracking assertions
and `git diff --check` passed. No runtime tests run for this documentation-only
draft; no nested review, implementation or deployment occurred.
**Checkpoint:** `d12c16fa1dfad137390eebdeb3a54b73819021b7` (local; not pushed).
**Review preparation:** Staged [people-and-responsibility-contract-audit-001
notes](../whetstone_runs/people-and-responsibility-contract-audit-001/audit-notes.md)
with exactly 16 committed specification inputs, built-in consistency profile and
proposed Codex `gpt-6.1-sol` reviewer. Local hash inventory binds the checkpoint;
the operator subsequently approved sending the 16 specifications. The execution
safety check blocked launch because approval did not explicitly include notes,
built-in reviewer/profile context and generated audit copies. No reviewer started
or package was sent on that attempt. The operator then explicitly approved notes,
built-in reviewer/consistency context and generated copies alongside those sources;
one reviewer-only audit completed under that complete authorization.
**Review outcome:** Codex `gpt-6.1-sol`, built-in consistency profile: `pass`,
`boundary_preserved=true`, no blockers, majors, minors or nits. Inspected the
[report](../whetstone_runs/people-and-responsibility-contract-audit-001/change_audit/change_audit_report.md)
and feedback; verified the manifest's exact 16-file inventory/model/profile and
unchanged source/notes hashes after the run. No Editor, source correction, runtime
change, ratification or convergence claim. No product decision pressure returned.
**Next:** Operator authorized ratification and machine codification under SPINE-060.
Implementation remains a later gate; no additional review is prescribed by this
logical bounded result.

### SPINE-058 — Deliver trusted-local facet revision readback

**Status:** Done — operator-authorized ratification and local implementation verified
2026-10-15 after planning checkpoint `d8dbc24`. Leaf contract ratified as v1.0.0;
runtime 0.10.0/schema 19 implements RR-01–11. Committed and pushed as `8f3c50b`;
deployment is not verified by this task. Consumer adoption remains separate.
**Dependency:** SPINE-055–057 draft/contracts/fixtures and minor clarification are
pushed through `3968dfd2beeb08411468494b7cb465471bbc52fd`. The bounded review found
no blockers or majors; its single minor was manually corrected and verified, not
re-audited. Ratification accepts that corrected v0.1.1 design without changing its
wire shape or trusted-local boundary.
**Authority:** [Readback leaf](../specs/facet-schema-revision-readback.md), its
[machine companion](../contracts/facet-schema-revision-readback.v1.json) and
[fixture manifest](../contracts/facet-schema-revision-readback-fixture-manifest.json).
This task allocates implementation/proof; it does not change those contracts.
**Scope:** One cohesive additive trusted-local release of
`facet_schema.revision.show`, resolving an exact revision ID to its actual root and
complete immutable definition using existing storage.
**Sequence:**

1. Explicitly ratify the reviewed logical/machine contract, preserving pending
   runtime obligations and unimplemented status until executable proof exists.
2. On implementation authorization, add bounded snapshot lookup, public CLI dispatch,
   read-only compiled registry/prerequisite declarations and deliberate installed
   local schema dependency closure. Reuse stored versioned decoding and existing
   indexes. Add runtime tests alongside the command, not as a later project.
3. Complete RR-01–11, operator documentation and additive release declarations;
   record exact evidence before advertising the capability. Commit/push, deployment
   and Spine Packs adoption each require their own authorization.

**Acceptance/proof:** Map every RR-01–11 obligation to executable evidence:

- Public CLI current/historical/retired reads and the A2/B2/B1 cross-root witness
  preserve exact root identity, definition/hash/ordinal (RR-01–03).
- Missing versus corrupt/unsupported-history failures, combined-input precedence
  and dry-run markers match the closed contract (RR-04–06).
- Success/failure are mutation-free; indexed bounded lookup fails closed at all
  specified byte/resource/SQL/time/lock limits; concurrent publish/retire yields one
  coherent snapshot (RR-07–09).
- Existing commands, binding/rendering shapes and frozen web surfaces remain
  unchanged; an installed non-editable package exposes the intended local contracts
  with exact compiled prerequisite parity (RR-10–11).

Run focused command/contract/storage/preflight/package regressions first, then the
appropriate full repository suite, contract-sync and diff hygiene checks. Use only
disposable ledgers and test adapters; no operator-ledger or delivery activity.
**Boundary:** No HTTP/MCP exposure, new authorization model, batch/history enumeration,
root probing, database migration, schema/index changes, facet-value authoring,
notification behavior changes or Spine Packs edits. Do not revive deferred work.
**Handoff:** Supply Spine Packs the exact implemented release commit/runtime/schema,
selector/request/result/failure contract and schema closure, with RR evidence and
the A2/B2/B1 example. Packs must explicitly adopt that pin and qualify FR-2 planning;
neither this plan nor Spine's tests qualify its installer.
**Delivered:** Runtime 0.10.0/schema 19 adds the trusted-local command, bounded
snapshot lookup, stored versioned decoder/parity checks, exact error precedence,
read-only compiled registration and an eight-resource installed local contract
closure. No migration or existing wire shape changed. The full-suite run exposed
an existing coupling between the complete local command set and the frozen facet
HTTP set; the adapter now checks the reviewed eleven-command resolver set instead.
The new command remains denied at both HTTP paths and direct protected-service entry.
Frozen web bytes/pins remain unchanged. Operator guides include progressive-disclosure
examples and the stop-versus-not-found distinction.
**Executable evidence:** All following names are methods of
[`FacetSchemaRevisionReadbackTests`](../tests/test_facet_schema_revision_readback.py)
unless noted; fixtures/models remain offline examples, not substituted runtime proof.

| Obligation | Evidence |
| --- | --- |
| RR-01–03 | `test_public_cli_cross_root_history_retirement_and_zero_writes`: two roots, both advanced, real B1 binding and rendering pin, exact historical/current/retired output, frozen root-addressed show parity |
| RR-04/06 | `test_cli_combined_error_precedence_missing_opaque_and_dry_run`: all twelve combined-error vectors in both member orders, exact opaque IDs, invalid Unicode/types and dry-run envelope |
| RR-05 | `test_corrupt_historical_evidence_fails_closed_without_repair`: real damaged disposable definitions/hash/version markers/root links/current pointers and missing/drifted field projections |
| RR-07 | Public-CLI table snapshots plus `direct` no-write harness; `test_indexed_point_reads_no_deep_checks_no_reference_dereference` additionally denies SQL writes with an authorizer |
| RR-08 | `test_capacity_byte_sql_time_resource_and_lock_limits`, indexed EXPLAIN plans and LIMIT 33 check; oversized persisted definitions/field counts fail in the stored decoder |
| RR-09 | `test_concurrent_publish_retire_uses_one_snapshot_and_next_read_observes_change`: independent public-CLI writer connections interleaved with the selected read |
| RR-10 | Existing facet/rendering/web regressions plus `FacetWebTests.test_http_closed_routes_and_configuration`; unchanged web/schema/migration bytes and contract-sync checks |
| RR-11 | `test_installed_wheel_public_cli_and_exact_local_schema_closure` builds offline, installs non-editably into an isolated venv, verifies every package pin/dependency and invokes the installed CLI outside the source tree; `test_admission_registry_and_no_cursor_configuration` proves exact required-contract failure and cursor independence |

**Verification:** 119 focused tests, 68 targeted web regressions and three frozen-web
contract tests passed. Final full discovery: 1,041 tests passed in 167.858s after
the HTTP-set separation and contract-harness correction. Ruff, all four contract-
sync checks, schema manifest, compileall, packaged registry parity, 277 local Markdown
link targets and diff hygiene pass. The default venv lacks setuptools; the wheel test uses an
existing local prepared build interpreter through `SPINE_WHEEL_BUILD_PYTHON`, with
network access disabled for build/install. Runtime isolation does not borrow source
imports or the build environment's dependencies.
**Next:** Exact-release handoff supplied; downstream adoption and staging verification
belong to their separately authorized tasks. No automatic deployment, Packs adoption, further
Whetstone pass or convergence claim.

### SPINE-057 — Clarify revision-readback request error precedence

**Status:** Done — targeted manual draft-contract/model patch verified 2026-10-15;
committed and pushed as `3968dfd`; not ratified, implemented or re-audited.
**Source:** SPINE-056 audit `fb_001` (minor); pass_with_minor_clarification with
boundary preserved, no blocker or major finding.
**Scope:** Specify extra-before-missing shape validation and deterministic field
ordering, retain selector-before-ID validation, and add offline expected code/field/
exit vectors for combined malformed requests. Keep executable enforcement pending
under RR-06 and preserve all source-only/runtime/HTTP boundaries.
**Boundary:** No runtime implementation, old wire/schema change, migration, audit
rerun, ratification, push, deployment, send or changes to Spine Packs.
**Delivered:** Leaf draft v0.1.1 Section 5 defines extra-before-missing precedence,
case-sensitive Unicode code-point field order, key-existence presence, and selector-
before-ID validation. Machine contract/request-schema commentary mirror the rule.
The fixture manifest indexes 12 expected code/field/exit vectors; two added offline
tests verify the rule, reversed member ordering and the frozen failure envelope.
Executable enforcement remains a pending RR-06 gate; this is not runtime proof.
**Verification:** 47 focused contract tests passed, plus Ruff, all three contract
sync checks, schema-object manifest and diff hygiene checks. Runtime source and
frozen web bundles/pins are unchanged. Prior audit artifacts remain historical;
the patched bytes have not been reviewed by a second nested Reviewer.

### SPINE-056 — Bounded facet revision readback contract review

**Status:** Done — exact-package send approved and one reviewer-only pass completed
2026-10-15; pass_with_minor_clarification, boundary preserved.
**Baseline:** SPINE-055 committed as `a110ea2ae7601cbf0fe6084fa4b0e34fb5135a03`.
**Mode:** One reviewer-only Whetstone `audit-change`, built-in consistency profile,
planned GPT-6.1 Sol Reviewer; no Editor, source edits or convergence claim.
**Scope:** [Audit notes](../whetstone_runs/facet-schema-revision-readback-contract-audit-001/audit-notes.md)
list exactly 43 source files plus the notes, built-in reviewer/profile context and
generated audit copies. Local-only prepared-inputs.json pins byte lengths/hashes;
it is not a reviewer input. Check identity/history, deterministic errors, immutable
decoding, resource/transaction bounds, trusted-local-only exposure, frozen web
packaging, fixture/model limits and the historical-pin consumer handoff.
**Preparation evidence:** 45 focused contract tests, three contract sync checks and
diff hygiene passed. Every selected source matches the baseline; inventory size is
474,287 bytes excluding notes/context. Current CLI help and reviewer version checked.
**Boundary:** Only the approved nested Reviewer pass; no ratification, runtime proof, implementation,
extra payload, ledger/send, automatic rerun, source patch, commit, push or deployment.
**Outcome:** GPT-6.1 Sol / built-in consistency; 0 blockers, 0 major, 1 minor,
0 nits. `fb_001` asks for deterministic shape-validation precedence when multiple
required fields are missing, multiple extras exist, or missing/extra fields coexist,
plus offline expected-outcome vectors and retained RR-06 runtime enforcement.
**Evidence:** [Report](../whetstone_runs/facet-schema-revision-readback-contract-audit-001/change_audit/change_audit_report.md)
and [feedback](../whetstone_runs/facet-schema-revision-readback-contract-audit-001/change_audit/change_audit_feedback.json).
Post-run hashes confirm all 43 sources and approved notes unchanged; the actual
audit manifest exactly matches the approved input inventory. The notes' preparation-
time pending status is superseded by local authorization.md without changing notes bytes.
**Next:** The separately authorized manual patch is recorded under SPINE-057.
This audit itself ran no Editor or source patch; the corrected bytes have not been
re-audited. No convergence is claimed.

### SPINE-055 — Specify trusted-local facet revision readback

**Status:** Done — draft spec, source-only contracts and offline fixtures verified
2026-10-13; included in the authorized 2026-10-14 specification checkpoint.
Pushed through `3968dfd`; not ratified or implemented.
**Baseline:** `57cda1c2d5589360ee8efe7155fd20b503034c2a`, runtime 0.9.1/schema 19.
**Finding:** Current root lists cannot map an arbitrary historical revision pin to
its root; old show requires that unknown root. Static source and ten offline schema
checks confirmed the gap, not an implementation violation. Root probing cannot
distinguish a missing revision from a wrong root/revision pair by error code/field.
**Scope:** Draft `facet_schema.revision.show` with source-only closed contracts,
immutable current/historical/retired readback, bounds/failures, computed fixtures and
offline oracles. Keep the logical/storage owners and existing registries unchanged.
**Boundary:** No runtime dispatch/declaration, HTTP exposure, storage migration,
operator ledger, send, Whetstone run, push or changes to Spine Packs.
**Delivered:** [Readback leaf](../specs/facet-schema-revision-readback.md), separate
draft command/fixture manifests, three closed request/success/failure schemas,
18 structural fixtures, six synthetic historical-state witnesses and eight offline
contract/model tests. The A2/B2/B1 witness resolves B1 to actual root B without
following current pointers or desired keys. Current/retired success and corruption/
not-found distinctions preserve immutable hashes. Web generators explicitly exclude
these source-only schemas; existing bundles, pins and registries are unchanged.
**Verification:** 45 focused contract tests passed. Ruff, all three contract-sync
checks, schema-object manifest check, 243 local Markdown link targets and
`git diff --check` passed. These are offline contract/model checks, not runtime
qualification. RR-01–11 executable acceptance obligations remain pending.
**Next gate:** Bounded contract review, then explicit ratification/implementation
and exact-baseline consumer adoption; not an authorization to start those steps.

### SPINE-054 — Repair successor notification-profile listing

**Status:** Done — implemented and locally verified 2026-10-10; included in this
authorized corrective release checkpoint, not pushed or deployed.
**Baseline:** `01ebce7b0c5fb9234e0eab55daca96b01c5cb6a7`, runtime 0.9.0/schema 19.
**Evidence:** Exact-source public CLI reproduction on a disposable ledger confirmed
ordinary v2 create/show success but v2 list failure whenever a selected page contains
a v2 revision. Empty/v1-only pages, filtering and cursor invalidation still work.
**Scope:** Separate catalog page selection from version-specific profile projection;
preserve the legacy guard, snapshot/cursor semantics, historical hashes and read-only
behavior. Prepare runtime 0.9.1 with unchanged schema and public contract families.
**Acceptance:** Public CLI regressions for ordinary/definition-pinned v2, mixed catalogs,
pagination, v1-to-v2 histories, owner/status filters, cursor invalidation and schema
validation; focused and full suites plus packaging/manifest hygiene checks.
**Boundary:** No live ledger, migration change, notification send, deployment
or push. Spine Packs must separately approve and pin the repaired release.
**Delivered:** The shared catalog helper takes an internal projection callback with
the original legacy guard as its default. The v2 list handler supplies the exact
successor projection and no longer reloads every page entry. Selection, ordering,
snapshot hashes and cursor validation are unchanged; no stored facts are rewritten.
`tests/test_profile_v2_listing.py` provides six public-CLI regressions on disposable
ledgers. V2-list cases failed against the original handler and pass after repair;
legacy rejection, historical hashes and read-only ledger snapshots are retained.
**Verification:** Focused suite: 116 tests passed. Full unittest discovery: 1,023
tests passed (162.610s). Ruff, compileall, contract sync, schema manifest and diff
hygiene checks passed. A non-editable 0.9.1 wheel installed in the disposable test
runtime passed all six listing regressions and the release script, including mixed
v1/v2 public-CLI pagination, exact resource pins, migration and paired-backup checks,
and old-worker refusal. `pip check` passed. Wheel SHA-256:
`2be842511413a87a614a49d1b917498cc1323fcab9cc78b3d9ebd80dc1cecdfc`.
Temporary logs/artifacts are under `/private/tmp/spine-profile-v2-wheel.kJF3vy` and
`/private/tmp/spine-profile-v2-{focused,full}.log`; not published release assets.
**Next handoff:** Push this checkpoint when authorized; Spine Packs must approve
its exact repaired commit instead of qualifying `01ebce7` unchanged.

## Rendering delivery — implementation sequence

The operator approved implementation planning and then SPINE-051 implementation on
2026-10-05, then committed that checkpoint and authorized SPINE-052 on 2026-10-06.
SPINE-051 and SPINE-052 were committed as internal checkpoints (`653e135`, `b729346`).
SPINE-053 completes the cohesive local release in runtime 0.9.0/schema 19 and is
included in this release checkpoint. There was no intermediate staging deployment.
Specs/contracts retain authority. RI-01–RI-14 local release evidence is recorded below;
deployment, real sends, new HTTP exposure and pack adoption remain separate.
The [implementation plan](IMPLEMENTATION_PLAN.md#planned-delivery-facet-aware-notification-rendering-spine-051053)
owns sequencing rationale and the proof allocation. Do not activate successor command
families, the integration capability or production migration until all three slices
and end-to-end verification are complete. New HTTP exposure and pack adoption stay separate.

### SPINE-051 — Rendering persistence and authoring foundation

**Status:** Implemented — internal candidate checkpoint, 2026-10-05; committed as
`653e135` on 2026-10-06. Public activation remains off.
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
Checkpoint committed as `653e135` after 104 focused tests, Ruff and diff checks.
No push, deployment or live-ledger change was performed.

### SPINE-052 — Integrate facet details into notification attempts

**Status:** Implemented — verified internal candidate checkpoint, 2026-10-06.
Public activation remains gated.
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
**Evidence:** `tests/test_rendering_delivery.py` executes real disposable-ledger
authoring, scheduler/worker and attempt paths. The candidate renderer builds ordered
typed-scalar/approved-location-label suffixes over the unchanged v1 base. Selected
omissions stay v2; inactive disclosure and unapproved location cases avoid private
source lookups. Exact immutable definition/schema/presentation pins and bounded
canonical evidence are checked at insertion and by the SQL-tracked commit finalizer.
The existing attempt's `BEGIN IMMEDIATE` fence rechecks current item, policy, facet,
ownership, disclosure and route facts; same-attempt replay loads stored bytes, while
a new retry retains its provider identity and may render current values.

| Proof allocation | Executed evidence |
| --- | --- |
| RI-01/05 | Frozen unselected v1 body/hash/envelope comparison; shared-intent siblings with distinct presentations after facet copy-forward; existing ancestry and profile regressions rerun |
| RI-03 | Already-due within-grace ordinary start before adoption/edit; exclusion through explicit materialization; failed edit preserves separately committed item/adoption; expired opportunities receive no new grace; started ordinary history is retained |
| RI-06 | Complete queued, in-progress, retry, started and terminal work rows unchanged across facet/presentation edits; selected Tickerd work survives an intervening edit; absent work stays absent; independently stale/cancelled work is not rescued |
| RI-07 | Facet/revoke/ownership/route edits between preparation and commit fail before send; fresh attempts use current facts; real two-connection SQLite writer contention serializes revocation behind the attempt commit |
| RI-08 | Rendering insert and commit-finalizer interruption roll back both rows and invoke no adapter; corrupt supporting facts/raw evidence and byte-cap failures fail closed; scalar limits, missing/schema-mismatched facets and suffix overflow omit without private evidence |
| RI-09 | Started replay after edits/revocation/clock advance reuses immutable bytes; gateway timeout followed by new retry creates two attempt/rendering records but one simulated provider delivery under the unchanged provider key |
| RI-10 delivery portion | Only explicitly approved location labels appear, never addresses/other metadata; unapproved locations are not looked up; existing protected-location/role tests rerun |

Recurring work uses the current series facet snapshot and the occurrence's target;
follow-source tasks use their own facets and reject a stale source binding. No real
recipient or external gateway was contacted. The fixtures' source-only obligation labels remain
historical; this table records actual execution rather than asserting complete
RI-01–RI-14 release qualification. Readback, restore/old-worker and installed-wheel
release proofs remain assigned to C.
**Verification:** Final consolidated full unittest discovery passed 960 tests;
217 focused tests passed, including all 58 delivery-module tests (inherited authoring
regressions included). Ruff, compileall, both web-contract sync checks, 152 local
documentation link targets and diff hygiene passed. Runtime 0.8.3/schema 18, public
registry and current web contracts are unchanged; candidate support is not advertised.
No push or deployment. Installed-wheel verification remains a C release gate.

### SPINE-053 — Complete rendering readback and release verification

**Status:** Done — implemented and locally verified 2026-10-06 after SPINE-052 commit
`b729346`; included in this release checkpoint, not pushed or deployed.
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

**Delivered:** Exact `spine.schedule-show.v2` projections preserve stored v1/v2 attempt
renderings and expose current presentation/application pins; v1 full projections
reject unrepresentable successor evidence instead of mislabelling it. Frozen compact
and independent web summaries omit facet values and do not load rendering evidence.
The local dispatch/registry, schema-19 migration and manifest, runtime 0.9.0 capability
declarations, CLI help/configuration, packaged local schemas/pins and progressive
[operator guide](NOTIFICATION_RENDERING_GUIDE.md) activate together. Current HTTP
schemas/registries and their packaged bytes are unchanged. Web dependency validation
keeps exact frozen prerequisites and checks the full local runtime union.

**Release proof mapping:**

| Families | Executable evidence |
| --- | --- |
| RI-01/02/03/04/05 | `test_rendering_authoring_foundation`, `test_rendering_successor_authoring`, `test_rendering_storage_integrity`, plus the ordinary-byte/shared-intent/setup interleaving tests in `test_rendering_delivery` recorded under SPINE-052 |
| RI-06/07/08/09 | `test_rendering_delivery`: work-state matrix, actual two-connection writer contention, preparation/commit interruptions, immutable started replay, fresh retry and simulated provider deduplication |
| RI-10/11 | `test_rendering_permissions`: authoring roles/grants, protected-location denial, cursor/context/expiry/rotation and indexed bounded reads; `test_rendering_delivery` verifies attempt-time scope/label-only release |
| RI-12/13 | Existing storage finalizer/all-writer proofs rerun; `test_rendering_release.test_populated_migration_faults_and_backup_restore` checks five failure stages, populated migration, metadata parity and backup; `scripts/verify_rendering_wheel.py` checks the actual predecessor wheel/worker refusal and paired backup verification |
| RI-14 | Seven `RenderingReleaseTests`: stored v1/v2 attempts after edits/revocation, v1/v2 profile readback against schemas, public CLI/compact/dry-run, frozen web summaries with no rendering reads, and bounded metadata-only preflight; installed-wheel resource pin/registry validation |

**Verification:** Focused final contracts/readback: 41 tests passed. Full
`.venv/bin/python -m unittest discover -s tests -q`: 1,017 tests passed (163.140s).
Ruff, compileall, schema-manifest checks, all three contract sync checks, local links
and `git diff --check` passed. No skipped release proof or blocked dependency remains.
Non-editable 0.9.0 and predecessor 0.8.3 wheels were installed in separate disposable
virtual environments, outside the checkout without `PYTHONPATH`. Exact Tickerd source
`ffe613c65ea3d6fc70a1dc3603c32068f06350df` produced its required 0.2.0 descriptor
`215f9aa6b54e6c0e6186796a55d78e1c5a270adc9b3ccefb433df5a3bb87b58b`.
The installed wheel verifies all 35 pinned local resources, fresh initialization,
populated migration, preserved policies/receipts, bounded `system.info`, unchanged web
registries, predecessor worker DOWN/not-ready/nonzero with one diagnostic and zero
processing, and old-runtime deep verification of the independent backup. `pip check`
passed. Candidate wheel SHA-256:
`3e9fc688c8d08d5300e5ee97d99b67815c705e578a42ce70de64614e694cb5de`.
Build/validation files under `/private/tmp/spine-rendering-wheel.wXcluz` are temporary
local artifacts, not a published release. No live ledger, service or real adapter was used.

**Next handoff:** Use this coherent release checkpoint to select an exact deployment
revision after a separately authorized push. Follow the guide's all-writer shutdown, verified backup, schema-19 migration,
protected pagination configuration and paired-code/backup rollback steps. Any staging
or real-send canary remains separately authorized.

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

The separately selected direct experiment is documented by completed SPINE-066 and
[its rough design](../specs/contextual-notification-experiment.md). It explores useful
or personable additions without governance and does not implement or ratify this
governed horizon. The existing advisory profile's requirements remain unchanged.

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

### SPINE-074 — Implement opt-in enriched reminder delivery offline

**Status:** Done locally — implemented and qualified offline, selected for the
operator-authorized local checkpoint (2026-11-06, Codex); not activated.
Operator-selected end-to-end implementation, treating useful
enrichment as the chosen capability. The [contract](../specs/notification-enrichment-delivery.md)
and [operations](NOTIFICATION_ENRICHMENT_DELIVERY.md) supersede SPINE-073's larger
capture-pilot architecture for this slice. Its standalone registry, format-3 and
seven-day purge are not prerequisites. Preserve that proposal as historical design.
**Implemented:** Exact owned timed/non-recurring event/work enrollment, whole-context
approval digest (including prose and derived reminder offset), read-only existing
source, explicitly initialized profile-marked format-2 capture store and existing
mandatory-count independent Impetus execution. Persist one immutable content choice
and private composed envelope, recheck consent/source/evidence at the canonical
attempt gate, and send at most one logical reminder with a validated suffix.
No-addition, unavailable/failed/uncertain/stale/late research, overlong composition,
revoked consent or unavailable private evidence use ordinary delivery. No late
upgrade or repeat research. Normal delivery retries keep the gateway key; actual
provider duplicate suppression remains gateway-owned.
**Evidence model:** New closed config/choice/outbound/evidence shapes and byte pins
match source/package resources. Additive `spine.openclaw.outbound.v3` separates the
ordinary rendering hash from composed-body hash. Ordinary canonical rendering rows
remain honest; private `delivery_evidence` recomputes the canonical attempt hash and
reports its actual status/provider reference. Unused prepared evidence after ordinary
fallback is not an attempted enriched message. Captures retain selected=false/sent=false.
No canonical migration, new registered CLI/HTTP capability, release or Tickerd pin;
optional library/worker injection is disabled by default.
**Unchanged owner boundary:** Verified independent Impetus HEAD
`5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, complete corrected schema SHA-256
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`, interface
`contextual-notification-experiment` / `impetus.openai.v1`. Mandatory count ordinal
1, generation ordinal 2, zero tools; original insertion-order configuration encoding,
20-second and 512-byte bounds and all existing execution/usage/reference checks remain.
**Offline verification:** Python 3.14.6; disposable ledgers/stores, fake clocks,
independent mocked Impetus subprocess and fake notification senders only. Source
export/research leave canonical source unchanged and create zero send attempts;
fake delivery asserts the ordinary rendering and canonical started attempt exist
before its sender runs. Eighteen new tests cover addendum/no-addition/count failure,
late/first-late observation, ordinary choice blocking research, consent/source drift,
transaction-gate races, private-store/receipt loss, credential/config-free restart
readback, no late second message, stable retry keys, exact disclosure, oversized
composition, read-only/profile boundaries, immutable evidence and contract parity.
Final focused capture/delivery/reminder/worker regressions: **140 passed, 59 subtests
(27.41 seconds; 27.623 seconds wall)**. Full documented unittest: **1,257 tests,
no skips (292.102 seconds; 292.714 wall)**.
Full pytest: **1,296 passed, 1,933 subtests, no skips, one known warning
(293.85 seconds; 294.355 wall)**. Final exact-context preview refinement
and stronger config-free readback fixture were followed by the focused rerun above,
**18 targeted tests (5.63 seconds; 5.963 wall)** and installed checks below.
**Installed qualification:** Succeeded offline with existing sibling Threshold
setuptools, without downloading/installing dependencies. Built own wheel from an
isolated source copy, installed only that wheel into a fresh noneditable runtime,
exposed existing validation dependencies without their editable path hooks, and
ran from external copied tests under `python -I`. Asserted Spine module/resource
origins inside the installed prefix, all installed source/resource bytes matching
the reviewed copy, and checkout source absent from import paths. **56 tests,
no skips (17.681 seconds; build/install/test 20.319 wall)**, followed by **18 final
installed tests (5.268 seconds; 5.519 wall)** with the strengthened readback fixture.
Wheel SHA-256: `1734a3a6211accbc21a971512d5970cc0f51194886a0314582f0acda5148faf5`.
Artifacts/logs are disposable local scratch, not a published release or real-trial record.
**Repository checks:** Repository-wide Ruff, compilation of src/tests/examples/scripts,
all five contract sync checks plus two documentation build tests (0.597 seconds
combined), 360 local documentation link targets and tracked/untracked diff hygiene
pass. Final compilation took 0.203 seconds; repository-wide Ruff took 0.072 seconds
and passed again after final edits. Strict configured core/ledger
mypy remains **36 pre-existing errors in 10 files (52 checked; 1.100 seconds)**;
all ten files are byte-identical to HEAD. The known synthetic serialization-deadline
`capacity_exceeded` ignored trace also recurred in full unittest; it is not a new
failed assertion or part of this change. No typing/timeout repair is included.
The build harness and connected tests were enabled with existing tooling and the
independent sibling, so these checks have no missing-setuptools or missing-owner skip.
**Development corrections, separate from repository issues:** Initial new-test
fixtures used a float where delivery requires a datetime; corrected before passing
runs. An unclosed scratch-store initializer was fixed; warning-free targeted reruns
pass. The initial focused command named a nonexistent test file and ran no tests;
the corrected/final 140-test commands above pass. A scratch preservation script
initially assumed every source fixture was packaged; corrected to compare the
actual packaged closure. No test weakening or pre-existing issue repair is included.
**Commands** (from repository root; `$RUN` is disposable validation scratch):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests \
  IMPETUS_SRC="$PWD/../impetus/src" \
  SPINE_WHEEL_BUILD_PYTHON="$PWD/../threshold/.venv/bin/python" \
  .venv/bin/python -m unittest discover -s tests
# Same environment for pytest; existing provider credential variables removed.
.venv/bin/python -m pytest -o addopts='' -p no:cacheprovider -q tests
.venv/bin/python -m pytest -o addopts='' -p no:cacheprovider -q \
  tests/test_enrichment_delivery.py tests/test_contextual_live.py \
  tests/test_contextual_live_contract.py tests/test_contextual_experiment.py \
  tests/test_contextual_experiment_contract.py tests/test_rendering_delivery.py \
  tests/test_openclaw_adapter.py tests/test_openclaw_gateway_sender.py \
  tests/test_side_effects_adapter.py tests/test_worker.py
.venv/bin/ruff check . --no-cache
.venv/bin/mypy --cache-dir "$RUN/mypy-cache"
PYTHONPYCACHEPREFIX="$RUN/pycache" .venv/bin/python -m compileall -q src tests examples scripts
# Each script run with --check: sync_web_contracts.py, sync_facet_web_contracts.py,
# sync_rendering_contracts.py, sync_revision_readback_contracts.py, sync_people_contracts.py.
node --test docs/site/build-pages.test.mjs
# Isolated source copy at $RUN/wheel-final/wheel-source; no checkout editable install:
../threshold/.venv/bin/python -m pip --isolated wheel --no-index --no-deps \
  --no-build-isolation --no-cache-dir --disable-pip-version-check \
  --wheel-dir "$RUN/wheel-final/wheels" "$RUN/wheel-final/wheel-source"
# Fresh venv --without-pip, own wheel only: existing pip --python <runtime/python>
# install --no-index --no-deps; runtime python -I runs 56 copied contextual/enrichment
# tests, then the 18 final enrichment tests; all independent worker providers mocked.
git diff --check
```

**Preservation/remaining boundary:** The initial AGENTS.md guidance edit is unchanged;
SPINE-073 design/tracking is retained with explicit supersession labels. Existing
Impetus tracked/untracked files are byte-identical; no Impetus edit. At completion
of validation, HEAD/index were unchanged, with no staging/commit/push/cleanup.
The operator subsequently authorized this bounded local checkpoint, including the
supporting superseded SPINE-073 design/history and excluding AGENTS.md guidance.
Source/package bytes still match the qualified wheel; reuse the completed checks
and verify the staged diff/hygiene without repeating unchanged runtime tests.
No real ledger, credential, provider,
network, actual notification, feature activation or deployment was accessed.
Next: agree the actual reminder/owner,
exact disclosure, continuous private state/retention, provider account/configuration
and one-message authorization before a real invocation/send. No additional usefulness
pilot or broad deferred resilience campaign is required by this slice.

### SPINE-073 — Design one real-reminder capture pilot

**Subsequent selection:** SPINE-074 supersedes this architecture for the implemented
enriched-delivery slice. The draft and evidence below remain historical; registry,
format-3 and seven-day purge proposals are not selected implementation requirements.

**Status:** Done — draft design delivered (2026-11-06, Codex), selected on
2026-11-05 after checkpoint `726b14a`; not ratified, implemented or activated.
Define one explicitly opted-in non-sensitive event/reminder
on an existing ledger, minimized reviewed disclosure, opportunity/store continuity,
retention and credential-free capture/readback. Ordinary delivery stays independent;
generated output remains selected=false/sent=false.
**Scope:** Draft specification and review/implementation plan only. Inspect source,
contracts and owner documentation, not real ledger contents. Preserve AGENTS.md
and Impetus edits. No runtime/schema implementation, actual pilot enrollment,
credential access, provider call, notification, deployment, dependency installation,
external handoff/review, commit or push is authorized.
**Acceptance:** Explicit first-pilot eligibility, consent/egress and ordinary-prose
rules, stable identity and launch-once state transitions, source/freshness and
normal-delivery independence, retention/access assumptions, existing-wire assessment,
offline acceptance oracles and prerequisites for a separately authorized real trial.
**Delivery and decisions:** [Draft specification](../specs/contextual-notification-real-capture-pilot.md)
and [operator/implementation plan with prepared owner handoff](CONTEXTUAL_NOTIFICATION_REAL_CAPTURE_PILOT.md).
One owned non-sensitive non-recurring timed event, one exact materialized
opportunity and local exact-byte consent. Default empty facets; optional at most
four approved primitive fields from one revision, including model-visible facet
revision IDs. Refuse primary-location/detail-bearing ordinary prose rather than
leaking excluded fields through rendering. Use a separate read-only source adapter,
persistent enrollment registry/authoritative one-way launch marker and proposed
format-3 private content; preserve synthetic formats 1/2 and work-ID derivation.
Separate content freshness, ordinary eligibility and retained execution: normal
delivery may proceed/write its own attempts without pilot writes or generated text.
Readback is credential-free and payload display requires retained-review consent.
Propose seven days for source-bearing content copies, then owner-agreed retirement
with longer-lived continuity/accounting metadata and no released unknown liability.
These are proposed choices for review; actual source/actor/provider/payload approval
and the future closed machine contracts are not supplied by this design.
**Owner boundary:** The complete existing wire appears reusable. Real-data scope,
retention/closeout and surviving owner accounting need explicit Impetus confirmation
even if its schema/version do not change. The plan contains the exact bounded owner
questions; nothing has been sent and no owner agreement is claimed. This corrects
the earlier suggestion that a handoff would only be needed for a wire change.
No general deferred resilience/storage campaign is selected.
**Design verification:** Complete corrected owner schema, Spine source copy and
package resource match SHA-256
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`, owner HEAD
`5ff3c0c4530fe07e81cc9067eddadd967a90acc4`. A wholly fictional existing-wire request
with a non-synthetic-prefixed namespace and primitive facet context passes the
complete Draft 2020-12 request schema plus independent owner semantic validation
(0.076s); this establishes shape compatibility only, not authority or real-data
qualification. Prepared 16 explicitly unexecuted implementation oracles covering
consent, prose/fields, identity, continuity, concurrency/crash prefixes, count/late
facts, microsecond timing, source/revocation drift, credential-free readback,
ordinary delivery, retention and format compatibility. Reviewed state transitions
have no path from closed/unresolved work back to provider entry.
Documentation packaging passes both existing tests (114.284ms runner, 0.270s wall),
local file links and diff whitespace pass. Runtime/full regression/installed-wheel
checks were not rerun for this design-only change; no executable or machine
contract bytes changed. Exact fictional assessment and preservation evidence are
retained in external scratch storage, not runtime/source-data artifacts in Git.
**Preservation and next action:** Seven Markdown files are new/updated, with
README/spec index and the existing synthetic contract pointing at the separate
draft. AGENTS.md, source/tests/contracts/resources, HEAD/index and the entire
Impetus checkout including its pre-existing edits are unchanged. No real ledger,
credential, provider, notification, dependency acquisition, staging, commit, push,
deployment or external review/handoff was accessed/performed. Next review the
Spine choices and take the prepared scope/retention questions to Impetus, then
separately select machine-contract/vector codification and offline implementation.
Real enrollment/preview/disclosure and any invocation remain separately authorized.

### SPINE-072 — Preserve live capture observation precision

**Status:** Done locally (2026-11-05, Codex), selected for the operator-authorized
checkpoint below; operator-selected fix for the
SPINE-071 same-second capture issue. Preserve subsecond precision for live
invoke/readback clock observations; do not change deterministic formatting,
original request bytes, launch-once semantics, historical trial records or
cutoff/freshness requirements. Add offline same-second and cutoff-edge
regressions with fake clocks/providers and disposable ledgers only.
**Scope:** Narrow Spine consumer correction, specifications/operations and
recorded verification. Preserve all existing edits and Impetus. No credentials,
network, paid trial, real source ledger, notification, dependency acquisition,
commit, push, deployment or feature activation.
**Implementation and compatibility:** The live service has a private observation
formatter that normalizes the injected/default datetime to UTC without dropping
fractions. Only post-invoke and implicit readback observations use it; explicit
caller-supplied strings retain their exact precision. The existing completion,
cutoff and freshness comparisons are unchanged, with no tolerance added. Whole-
second observations retain their old encoding. The deterministic formatter,
export/prelaunch formatting, original bytes, format-2 storage, schema/resources,
wire/capture v1 declarations, canonical schema 19 and package 0.11.2 are unchanged.
No migration, re-export or rewriting of historical captures is required.
**Regression evidence:** Both new test methods fail against the old consumer
(five failures in 1.057s / 1.239s wall). Fake provider completion at `.278Z` and
observation at `.278123Z` then pass on original invoke and reopened credential-free
readback after the correction. Tests preserve source data, request bytes and the
launch marker, with no selected/sent capture or repeated generation. Boundary
subtests check one microsecond before completion, exact completion, one microsecond
before cutoff, exact cutoff and one microsecond after cutoff. Explicit coarse
caller observations remain conservative rather than being reinterpreted.
**Verification:** Full documented unittest completes 1,239 tests in 284.561s
(285.336s wall): 1,238 passed and one environment-related wheel check skipped.
The harness had resolved the prepared builder's Python symlink to its base
interpreter, losing the existing setuptools environment. The single skipped
revision-readback wheel/CLI/schema check then passes independently with the
unresolved prepared-venv interpreter path (3.562s / 3.773s wall); no coverage
remains blocked. No dependency installation was needed. The existing ignored
serialization-deadline trace exception appears in its passing timeout test.
Focused live/deterministic/reminder pytest passes 99 tests
and 85 subtests (20.26s / 20.551s wall). Isolated installed-wheel capture/contracts
pass all 38 tests with no skips (12.393s / 12.565s wall), including both new methods.
Repository Ruff passes (0.318s), compilation of `src tests examples scripts` passes
with external bytecode (0.774s), docs packaging passes both tests (0.344s wall),
and all five contract sync checks pass (web 0.126s, facet-web 0.158s, rendering
0.088s, revision-readback 0.068s, people 0.104s). All 311 affected local documentation
file targets resolve. Full pytest was not repeated: the documented full unittest
run plus the focused pytest and installed capture checks exercise this correction.
**Known issues:** Strict configured core/ledger mypy still reports the same
36 pre-existing errors in ten files, 52 checked (1.381s wall). All ten diagnostic
owners are byte-identical to HEAD; no repair or suppression is included. The
previous synthetic deadline-trace warning is outside this correction.
**Installed package:** Built the own noneditable 0.11.2 wheel offline with the
existing prepared Threshold setuptools environment (1.322s); installed only that
wheel into a fresh venv with `--no-index --no-deps` (1.026s). Existing validation
dependencies are exposed through a plain dependency-directory `.pth`; editable
loader files are not loaded. `python -I` asserts installed-prefix modules/resources,
with checkout `src` absent, then runs unchanged copied tests from the external
test directory against the independent mocked Impetus subprocess. Package code/
resources are byte-compared with the reviewed source. Wheel SHA-256:
`66ddf099d4972faa3520c898dd35ed612040f7254c1aed239772ae4665260c37`.
Initial scratch preparation incorrectly expected a LICENSE file, leaving the
first scratch build without `src`; another harness pass lacked a source resource
comparison mirror (one installed-test error). Both were external harness setup
errors, corrected only in scratch storage. Final build and all 38 installed checks
pass; failed logs are retained separately and no repository build fix was needed.
**Commands and preservation:** All tests used disposable stores, fake clocks/
providers and a credential-stripped environment with `PYTHONDONTWRITEBYTECODE=1`,
`TMPDIR="$RUN/tmp"`, `PYTHONPATH=src:tests` and `IMPETUS_SRC="$PWD/../impetus/src"`.
`RUN` is fresh external scratch storage holding exact command/exit/duration logs,
reviewed source/test hashes, wheel, isolated runtime and preservation manifests.
The focused command is listed in the operations note; it now includes the two
new test methods. The full run originally saw the resolved base interpreter;
the single-check rerun below uses the corrected builder setting, preserving its
venv path:

```sh
.venv/bin/python -m unittest discover -s tests -v
SPINE_WHEEL_BUILD_PYTHON="$PWD/../threshold/.venv/bin/python" \
.venv/bin/python -m unittest \
  tests.test_facet_schema_revision_readback.FacetSchemaRevisionReadbackTests.test_installed_wheel_public_cli_and_exact_local_schema_closure -v
.venv/bin/ruff check . --no-cache
.venv/bin/mypy --strict --no-incremental --cache-dir "$RUN/mypy-cache" src/spine/core src/spine/ledger
for family in web facet_web rendering revision_readback people; do
  .venv/bin/python "scripts/sync_${family}_contracts.py" --check
done
PYTHONPYCACHEPREFIX="$RUN/bytecode" .venv/bin/python -m compileall -q src tests examples scripts
node --test docs/site/build-pages.test.mjs
../threshold/.venv/bin/python -m pip --isolated wheel --no-index --no-deps \
  --no-build-isolation --no-cache-dir --disable-pip-version-check \
  -w "$RUN/wheels-reviewed" "$RUN/wheel-source-reviewed"
.venv/bin/python -m venv --without-pip "$RUN/runtime"
.venv/bin/python -m pip --isolated --python "$RUN/runtime/bin/python" install \
  --no-index --no-deps --no-cache-dir --disable-pip-version-check \
  "$RUN/wheels-reviewed/spine_ledger-0.11.2-py3-none-any.whl"
"$RUN/runtime/bin/python" -I "$RUN/installed-checks/qualify.py"
git diff --check
```

Only the live consumer and its existing test module change executable bytes.
Pre-existing documentation edits are preserved with scoped follow-up updates.
AGENTS.md, the entire Impetus checkout and all retained SPINE-071 trial-evidence
bytes remain unchanged. No original trial read/recovery/invocation was performed,
and no credentials or live provider were accessed. At fix verification, the index
and HEAD remained unchanged and no commit or push had been made.

**Checkpoint authorization (2026-11-05):** The operator requested the local
checkpoint after completed validation. Include the SPINE-072 precision correction,
two offline regressions and supporting specification; SPINE-070 preparation and
SPINE-071 trial review; and their directly supporting README, operations, delivery
history and backlog evidence. All executable/test bytes match the validated
snapshot, so reuse completed regression/installed-wheel evidence and perform
staged scope/content/whitespace checks. Exclude the unrelated AGENTS.md guidance,
preserve all retained external trial/scratch artifacts, and leave Impetus unchanged.
This authorizes only the focused local commit, not a push, deployment, further
provider invocation, notification or feature activation.

### SPINE-071 — Run one synthetic provider capture through Spine

**Status:** Done locally with the observation-precision limitation below
(2026-11-04, Codex). The operator's “OK proceed” after
the completed SPINE-070 plan authorizes its one original synthetic invocation:
one count, at most one generation, zero tools/retries/notifications, retained
credential-free readback. Candidate revision and USD 0.004584 local admission
remain exactly as reviewed; the counting allowance is not a verified fee or
guaranteed upstream billing cap. No second opportunity follows uncertain work.
**Preflight:** Current official model/pricing pages were opened on 2026-11-04;
published Standard short-input base rates remain USD 0.10 input / USD 0.50
output per million, below configured conservative USD 0.40 / USD 0.60. The
counting guide does not establish a fee. Prior owner trial supplies historical
access evidence; current account access/final charges are not inferred from it.
The documented worker-owned credential file passes metadata-only ownership/
permissions checks; the worker alone may read its contents on original entry.
Exact reviewed recipe and all owner/source/package schema pins match. Runtime,
tests, contracts and both checkpoints are unchanged; existing edits are preserved.
**Scope:** Execute the [single-trial plan](CONTEXTUAL_NOTIFICATION_SINGLE_TRIAL_PLAN.md),
retain original bytes/bindings/marker, classify the actual result, read it without
credentials, verify unchanged source and zero notification attempts. No source
repair, Impetus edits, dependency acquisition, commit, push or deployment.
**Outcome:** [Trial review](CONTEXTUAL_NOTIFICATION_SINGLE_TRIAL_REVIEW.md).
One actual count and one generation succeeded with no_addition in **4.422s**
(**4.935s** including fresh preparation, invocation and immediate readback).
Count and generation input tokens match at **244**; output **92**, total **336**,
including **48** reasoning tokens within output. At configured conservative rates,
generation usage is **USD 0.0001528**; remaining generation reserve **USD 0.0034312**
plus unknown counting contingency **USD 0.001** retains the original **USD 0.004584**
admission. Computed usage is not an invoice. One owner run and the launch marker
remain retained; no counting, generation or notification was repeated.
**Newly observed limitation:** Invoke capture and immediate readback both observed
`2026-11-03T23:58:39Z`, while owner completion was `23:58:39.278Z`. Spine's
seconds-only observation formatter conservatively made usability=false. An actual
credential-free read at `23:58:56Z`, before cutoff `2026-11-04T00:00:34Z`, retained
the same execution and correctly made usability=true. All three original records
remain selected=false/sent=false. This is a same-second timestamp precision issue
in the checkpointed code, distinct from provider failure, stale source and the
previously recorded mypy/deadline-test issues. No source fix was made.
**Post-run verification:** Passed complete request/read/response schema and
consumer semantic checks, both stores' exact request bytes/digest, immutable
bindings/marker, one run/two operations, count/body ordinal and digest linkage,
config/prompt/model identity, token arithmetic, usage/reserve conservation, unchanged
canonical-source logical dump and zero `side_effect_attempts` (0.194s wall).
An additional independent credential-free CLI read matched the execution and
left owner state unchanged. The later Spine readback took 0.206s wall and did
not reopen provider configuration or credentials. Original request SHA-256:
`105081cf36f52503d679756d12b1bc4a330f4260e8873f67e252d4b9074c3980`.
Exact recipe, single-entry wrapper, authorization/prelaunch manifests, source/
sidecar/worker stores, all capture JSON, independent readback and verification
report are preserved together outside both checkouts. The wrapper refuses any
new invocation when its trial directory exists; reruns can only read.
**Commands:** The reviewed plan's `prepare`, `invoke` and `read` operations were
orchestrated once by the external single-entry wrapper using the existing Spine
interpreter and actual independent Impetus CLI. The original invocation received
ordinary sandbox network approval; only Impetus opened its existing credential
file. Later reads used the plan's `env -i ... trial_driver.py read` command and
an independent `python -m impetus --state <trial>/worker read` with the stored
`read.json`, no credential/live/configuration flags. No secret or resolved locator
was printed or retained in capture/report evidence.
Documentation packaging passed both tests (107.861ms runner); 311 local
documentation file targets, exact recipe parity, diff hygiene and final
preservation checks passed. The external single-entry wrapper passed Ruff before
execution. All six changed files are documentation; AGENTS.md and all Impetus
files remain byte-identical to the pre-trial snapshots, with HEAD unchanged and
the index empty.
**Qualification limit and next action:** The authorized one-case trial is
complete; general immediate-capture qualification retains the precision issue.
This proves neither live addendum usefulness, live failure/restart behavior,
real-reminder disclosure, final billing nor generated delivery. Next consider a
separately selected observation-precision fix with an offline same-second
completion regression; no additional paid trial is needed to reproduce it.
Executable bytes are unchanged, so full regression/wheel suites were not repeated;
SPINE-069 retains that evidence. No commit, push, deployment, dependency acquisition,
real-ledger access or notification occurred. Prior documentation and AGENTS.md
edits are preserved; Impetus checkout is unchanged.

### SPINE-070 — Prepare one synthetic real-provider capture trial

**Status:** Done locally (2026-11-04, Codex), offline preparation only. The
operator selected this concrete preparation following the SPINE-069 checkpoint
`1f7947d`; at preparation completion provider execution and account/tariff
qualification awaited separate resolution and authorization. The later selected
single trial is recorded separately in SPINE-071 above.
**Scope:** Review the carried-forward Impetus candidate, exact synthetic export,
fresh store/namespace layout, launcher and credential-free readback recipe,
admission arithmetic, acceptance criteria and remaining account/tariff assumptions.
Use existing tooling, disposable synthetic stores and mocked transports only.
Preserve AGENTS.md and all Impetus edits. No source/contract changes, credential
access, network, dependency acquisition, notification, commit or deployment.
**Acceptance:** A concrete reviewable trial plan with checked offline recipes,
exact pins and exposure, explicit limits and the separate authorization needed
before a single count plus at most one generation. Preparation completion does
not claim that the live trial or account qualification succeeded.
**Delivery:** [Single-trial plan](CONTEXTUAL_NOTIFICATION_SINGLE_TRIAL_PLAN.md)
includes the exact synthetic review request/digest, non-secret candidate bytes
and insertion-order revision, all pins, local admission arithmetic, checked
preparation/invocation/readback recipe, fresh store/namespace layout, evidence and
acceptance criteria, and the precise separate execution authorization. Operations
and delivery history link it. Source specifications/contracts remain unchanged.
**Candidate and limitations:** Carry forward the exact Impetus checkpoint
candidate `examples/openai-gpt-6-luna.candidate.json`, raw SHA-256
`6e93379ed73a5dafccafdd7286e6aed126203eb01ee466c1b6ffa051bdaba2be`;
configuration revision
`openai.responses.v1:88ad7139cd591f01ceb017b46b491525554aa377be257aa2c64434dd6cdb8e12`.
One count plus at most one generation, gpt-6-luna/low, 8,192 input/512 output
tokens, zero tools/retries. Generation reserves 3,584,000 nanodollars plus an
unknown counting contingency of 1,000,000: **USD 0.004584 local admission**.
This is conditional accounting, not a guaranteed upstream billing cap. The
owner's locally edited prior-trial notes are dated evidence, not new verification
of account access/terms, current prices or counting charges. No network refresh
or private prior-trial store inspection was performed. The mutable alias and
counting allowance remain explicit operator decisions before execution.

**Offline verification:**

| Check | Result | Duration |
| --- | --- | --- |
| Unmodified preparation recipe, clean environment | Fresh synthetic ledger/format-2 export/independent worker initialization; marker remains zero; zero attempts | 0.470s |
| Final reviewed recipe: context addendum | Mocked invoke, actual owner CLI readback, repeated Spine run reads only | 0.602s |
| Final reviewed recipe: no_addition | Same retained two-call execution across read/replay | 0.568s |
| Final reviewed recipe: late generation | Failed/unusable; schema-valid observation references generation ordinal 2 | 0.517s |
| Final reviewed recipe: lost response | Missing invoke execution recovered by readback; repeated run reads only | 0.508s |
| Complete live contract/resource/vector suite | All 4 test methods passed; no skips | 0.032s / 0.194s wall |
| Documentation packaging | Both tests passed; no skips | 112.068ms runner |
| Extracted recipe AST/Ruff, 248 local documentation file targets and diff hygiene | Passed | Routine checks |

The four recipe rehearsals use fake clocks, the existing independent mocked
Impetus subprocess fixture and disposable stores. Parent and fixture socket
creation are forbidden. An explicit fake locator is never opened; the fixture
uses its fixed fake key. Read/replay uses the unmodified independent owner CLI
with an allowlisted environment and no credentials/live/configuration flags.
Each rehearsal retains three captures and exactly two operation records; source
dump checks and zero notification attempts pass. Guarded parent reads prove that
read/replay never open the provider configuration file. An additional owner-only
offline projection check uses a fake key and forbidden transport to construct
the review count/generation bodies, confirming exact input projection, matching
configuration revision and 4,584,000-nanodollar reservation with zero provider I/O.
Body byte counts/digests and the exact request are recorded in the plan. External
temporary evidence retains the extracted final recipe, request/bindings/stores,
projection bytes and rehearsal outcome JSON; none is staged as runtime state.

**Commands:** Recipe preparation uses the plan's clean-environment command.
Rehearsal extracts its Python block and substitutes only fake clocks, the existing
`tests/fixtures/contextual_live_worker.py` command and simulated lost stdout;
read/replay then switches to the actual sibling `python -m impetus` CLI.

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests \
  IMPETUS_SRC="$PWD/../impetus/src" .venv/bin/python \
  -m unittest tests.test_contextual_live_contract -v
.venv/bin/ruff check --no-cache "$EVIDENCE/trial_driver-reviewed.py"
node --test docs/site/build-pages.test.mjs
git diff --check
```

**Preservation and next action at preparation completion:** All runtime, tests, contracts, package resources
and pre-existing AGENTS.md bytes remain unchanged. Impetus HEAD and all its
pre-existing local edits are preserved. No staging/commit or provider execution.
Full regressions and installed-wheel qualification were not repeated for these
documentation-only changes: SPINE-069 records the validated identical executable
snapshot, including 1,237 final unittest cases and 36 installed-wheel capture
checks. Its 36 pre-existing mypy errors and deadline warning remain documented;
this preparation claims no repair. Final live stores have not been created; the
expired review specimen must never be invoked. Next resolve account/charge/data
assumptions, obtain the stated single-trial authorization, then prepare one new
time-sensitive original export and invoke/read it without retries or sends.

### SPINE-069 — Implement offline live-profile synthetic capture

**Status:** Done locally (2026-11-03, Codex), reviewed offline implementation;
selected for the operator-authorized local checkpoint below. SPINE-068's design
is adopted for this slice; provider execution and deployment remain separate.
**Scope and decisions:** Separate live-profile service/launcher and fresh format-2
sidecar with exact request bytes, source/disclosure/config fingerprints, complete
owner schema pin, insertion-order configuration encoding/revision and prompt pin.
Count is mandatory, generation is one, tools are zero. Marker commit precedes
invocation; lost responses, restart and absent/unavailable reads never re-invoke.
Credential-free/config-file-free readback uses the original stored bindings.
Expected configuration drift makes the proposal unusable without erasing the
original execution. All captures are selected=false/sent=false. Sidecar triggers
preserve original exports/markers and append-only captures. Source/store namespace
must match. Format 1, deterministic work, ordinary reminders and canonical schema
19/release 0.11.2 remain unchanged. No registered public command is added.
**Delivery:** [Implemented contract](../specs/contextual-notification-live-capture.md),
[Spine decision 0007](../specs/decisions/0007-offline-live-capture-profile.md),
[operations](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md), exact source/package schema
closure, independent request/read/late-response byte vectors, and independent
mock-worker subprocess tests. The earlier handoff is retained as design history
with an explicit owner-correction/adoption update.
**Adopted owner inputs:** Impetus checkpoint
`5ff3c0c4530fe07e81cc9067eddadd967a90acc4`, interface
`contextual-notification-experiment`, unchanged wire version `impetus.openai.v1`.
The complete corrected schema is byte-identical to that commit, SHA-256
`bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b`.
Installed resource/fixture closure is pinned by
`contracts/contextual_notification/live-pins.v1.json`. Spine requires counting;
the complete owner schema still supports non-counting work for other consumers.

**Verification** (test-runner duration followed by wall time where available):

| Check | Result | Duration |
| --- | --- | --- |
| Full Spine pytest | 1,275 passed; 1,928 subtests passed; one known skip and warning | 287.41s / 288.020s |
| Final reviewed full unittest | 1,237 passed; no skips | 286.347s / 287.006s |
| Focused live/deterministic/reminder regression | 97 passed; 80 subtests passed | 20.55s / 20.820s |
| Reviewed installed-wheel capture/contracts | All 36 passed, no skips, outside checkout | 11.320s / 11.474s |
| Independent Impetus suite | All 57 passed, no skips | 2.800s / 2.987s |
| Repository Ruff / compilation / documentation packaging | Passed; two packaging tests | 0.318s / 0.713s / 0.401s wall |
| Five package contract sync checks | All passed: web, facet-web, rendering, revision-readback, people | 0.147 / 0.269 / 0.123 / 0.094 / 0.130s wall |
| Configured strict core/ledger mypy | 36 pre-existing errors in 10 unchanged files, 52 checked | 1.384s wall |

Connected proofs cover context-only addendum/no-addition, uncertain count,
over-limit count, count/generation mismatch, unknown generation usage, schema-valid
late generation at ordinal 2 and retained readback, negative observation references,
malformed execution/configuration/prompt/model/token/reserve facts, lost response,
actual worker death during count, after completed count and during generation,
readback without credentials/config file/live flags, config/source drift and late
capture. Source dumps remain unchanged during capture and notification attempts
remain zero. Fake clocks/transport and disposable ledgers/stores were used throughout.

**Check limits and pre-existing issues:** Pytest's one skip is the existing
revision-readback wheel harness because Spine's interpreter lacks setuptools.
That check passes in final unittest using the existing prepared Threshold build
interpreter. The existing synthetic serialization-deadline trace exception appears
as one pytest warning and a unittest ignored exception; it is not a failed assertion.
Strict mypy remains red with the documented 36 diagnostics; all 10 files are
byte-identical to HEAD. No typing repair or suppression is included. Initial
implementation tests exposed and fixed a new timedelta comparison error. Full pytest
preceded final command-option/namespace guard review; the full unittest and installed
capture checks validate the final reviewed code snapshot, including those guards.

**Installed package:** An offline scratch source copy built a noneditable 0.11.2
wheel with existing setuptools 80.9.0 (1.303s); only that wheel was installed with
`--no-index --no-deps` into a fresh venv (0.898s). Existing validation dependencies
were exposed through a plain dependency-directory `.pth`, without downloading or
installing dependencies. `python -I` asserted module/resource paths under the fresh
runtime prefix with checkout `src` absent, then ran unchanged copied tests against
the independent Impetus source worker. Wheel SHA-256:
`ee752914fc195f26dea6488201b7db4a4506d825f02943b5954f583cfd922d9f`.
This qualifies the capture boundary with existing dependencies, not a whole-release
or independent Impetus installed-wheel qualification.

**Commands:** All test commands used `PYTHONDONTWRITEBYTECODE=1`, disposable
`TMPDIR`, `IMPETUS_SRC="$PWD/../impetus/src"` and, for Spine tests,
`PYTHONPATH=src:tests`. Exact command/exit/duration logs, wheel and reviewed byte
manifests are retained in external temporary validation storage; no runtime state
or host-specific scratch path is added to the repository.

```sh
.venv/bin/python -m pytest -o addopts='' -p no:cacheprovider -q -ra tests
SPINE_WHEEL_BUILD_PYTHON="$PWD/../threshold/.venv/bin/python" \
  .venv/bin/python -m unittest discover -s tests -v
# Focused command is listed in CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE.md.
.venv/bin/ruff check . --no-cache
.venv/bin/mypy --strict --no-incremental --cache-dir "$RUN/mypy-cache" src/spine/core src/spine/ledger
for family in web facet_web rendering revision_readback people; do
  PYTHONPATH=src .venv/bin/python "scripts/sync_${family}_contracts.py" --check
done
PYTHONPYCACHEPREFIX="$RUN/bytecode" .venv/bin/python -m compileall -q src tests examples scripts
node --test docs/site/build-pages.test.mjs
# From the Impetus checkout, using the existing Spine interpreter:
(
  cd ../impetus
  PYTHONPATH=src ../spine/.venv/bin/python -m unittest discover -s tests
)
# RUN is the selected external scratch directory; source/tests were copied there:
../threshold/.venv/bin/python -m pip --isolated wheel --no-index --no-deps \
  --no-build-isolation --no-cache-dir --disable-pip-version-check -w "$RUN/wheels-reviewed" "$RUN/wheel-source"
.venv/bin/python -m venv --without-pip "$RUN/runtime-reviewed"
.venv/bin/python -m pip --isolated --python "$RUN/runtime-reviewed/bin/python" install \
  --no-index --no-deps --no-cache-dir --disable-pip-version-check "$RUN/wheels-reviewed/spine_ledger-0.11.2-py3-none-any.whl"
env -u PYTHONPATH -u PYTHONHOME "$RUN/runtime-reviewed/bin/python" -I "$RUN/installed-checks/qualify.py"
git diff --check
```

**Preservation and remaining action:** Pre-existing AGENTS.md guidance and all
pre-existing runtime/test/contract/example bytes, including deterministic profile
and package declarations, are unchanged. The selected design documents are promoted
with their historical handoff/backlog evidence retained. All Impetus files, its
existing local edits and checkpoint remain unchanged. At implementation verification,
nothing had been staged or committed.
A separately authorized single synthetic real-provider trial still needs its exact
request, qualified non-secret model/rate/counting configuration, admitted exposure,
source cutoff, fresh stores/namespace and explicit trusted launcher opt-in. Credentials
remain worker-owned outside the checkout/captures. No real provider/credential access,
network request, user-ledger write, notification, deployment or dependency acquisition
occurred. Real reminders and generated delivery remain separate work.

**Checkpoint authorization (2026-11-03):** The operator selected the focused local
SPINE-069 checkpoint after completed validation. Include the implementation,
corrected schema/resource closure, synthetic vectors, connected tests, supporting
SPINE-068 design history, decision, operations and recorded evidence. Exclude and
preserve `AGENTS.md`; leave Impetus untouched. The current tree matches the validated
snapshot apart from this checkpoint note, so reuse completed regression/wheel
evidence and perform staged scope/content/whitespace checks. This authorizes a
local commit only; no push, deployment, provider call, notification or activation.

### SPINE-068 — Define Spine adoption of the live Impetus capture profile

**Status:** Done locally (2026-11-02, Codex), proposed consumer contract and owner
handoff only. Runtime adoption and bilateral compatibility are not claimed.
**Selected scope:** Following SPINE-067 checkpoint `c0a7b13`, define the first live
consumer as a fresh synthetic ledger, count plus one generation, zero tools and
non-sending capture. Specify durable execution pins, a separate new sidecar format,
exact-byte identity/readback, source freshness, deadlines and honest USD usage and
reserves. Existing deterministic opportunities cannot become replacement live work.
**Delivery:** [Consumer proposal](../specs/contextual-notification-live-capture.md)
and [owner/implementation handoff](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE_HANDOFF.md),
linked from orientation, spec index, compatibility and delivery rationale. No runtime,
machine-schema copy, public registry or package-version declaration changes.
**Owner finding:** At Impetus `eba6578`, the inspected live schema is identical to
the committed file, SHA-256
`5de8e9de0a4052e91091e3f641215daae1dae8b087cc51adfc02865cf76b6b57`.
A fake-transport/fake-clock reproduction produces a failed/deadline execution with
late generation at ordinal 2 after count ordinal 1; the owner's schema rejects its
late observation because that field is fixed to 1. An in-memory range-only control
validates the same envelope. Impetus must correct the owner schema and add invoke/
readback coverage, then provide an exact corrected checkpoint/hash before Spine
declares adoption. No owner files were changed or compatibility inferred by proxy.
**Verification:** Offline reproduction passed its mismatch/control assertions in
0.013 seconds, with one fake count and one fake generation, zero real requests and
a disposable worker store. New/changed documentation file links and the exact
owner schema pin were checked; internal review distinguishes the proposal from
implemented deterministic contracts and separates count from generation/usage.
Byte comparisons preserve all runtime, tests, contracts, examples, `pyproject.toml`,
the pre-existing `AGENTS.md` edit and the entire Impetus working tree. Diff whitespace
checks pass. Full behavioral suites were not rerun for this documentation-only
task; SPINE-067's earlier regression/wheel evidence remains historical evidence
for its implemented boundary, not validation of a live consumer.
**Next concrete action:** Impetus-owned late-observation schema correction and
regression, followed by selection of its exact pin and the scoped offline Spine
implementation in the handoff. A real trial, real-reminder opt-in/disclosure,
commit, push, deployment and feature activation remain separate actions. No
provider calls, notifications, credential access or user-ledger writes occurred.

### SPINE-067 — Connect synthetic Spine export to deterministic Impetus capture

**Status:** Done locally (2026-10-29, Codex), synthetic connected proof.
**Scope:** Adopt the smallest local schema/byte binding with Impetus; export a real
synthetic event, explicitly permitted context and ordinary preview; invoke an
independent worker once and retain non-sending capture/readback. Preserve the
pre-existing AGENTS.md and design edits, existing schema/runtime pins and reminders.
**Delivery:** [Contract](../specs/contextual-notification-capture.md),
[operations/demo](CONTEXTUAL_NOTIFICATION_CAPTURE.md), independent process/contract
fixtures and source/capture tests. Separate owner stores; no live provider, source
ledger migration, real-send path or staging change.
**Verification:** 74 scoped pytest cases and 49 subtests pass, including 12 connected
capture tests, one standalone shared-contract test and existing ordinary-rendering,
scheduling and delivery regressions. The independent Impetus suite passes 20 cases
with schema validation enabled. Ruff on all new Python modules passes; both working
trees pass diff whitespace checks; Impetus's scaffold verifier passes. A real demo
in a disposable local directory created a source event and captured a context-only
proposal with selected/sent false. Source export/capture tests assert
no canonical ledger writes or side-effect attempts. Wheel qualification was attempted
but the local environment lacks the setuptools build backend; installed-wheel behavior
is not claimed. Full Spine regression, live providers, real data, staging, release,
commit and push were outside this task. SPINE-066 remains design-only history.

**Regression follow-up (2026-10-31):** Completed operator-authorized validation
of the local synthetic capture boundary on Spine `b376d97` plus the pre-existing
local slice. Independent Impetus `eba6578` was available; its pre-existing
documentation edits were preserved. Python 3.14.6, pytest 9.1.1, Ruff 0.16.2,
mypy 2.3.0 and jsonschema 4.26.0. No implementation, test or contract changes.

**Results** (wall durations unless a runner duration is stated):

| Check | Outcome | Duration |
| --- | --- | --- |
| Full Spine pytest | 1,252 passed; 1,897 subtests passed; one skip; one existing warning | 306.58s runner / 307.289s wall |
| Full documented unittest discovery | All 1,214 tests passed; no skips | 303.069s runner / 303.912s wall |
| Installed capture/contract boundary | All 13 unchanged tests passed; no skips | 5.415s runner / 5.590s wall |
| Independent Impetus unittest, including mocked provider tests | All 55 passed; no skips | 4.006s runner / 4.327s wall |
| Repository-wide Ruff | Passed | 0.347s |
| Strict core/ledger mypy | Failed: 36 existing errors in 10 files, 52 files checked | 2.925s |
| Same mypy command against exported committed HEAD | Same 36 diagnostics, exactly equal | 1.262s |
| Contract sync: web / facet-web / rendering / revision-readback / people | All five passed | 0.129 / 0.197 / 0.099 / 0.074 / 0.109s |
| Shared contextual schema/request/vector byte parity | All copies identical, including independent Impetus | 0.002s |
| Compile src/tests/examples/scripts | Passed; bytecode outside checkout | 0.761s |
| Documentation packaging tests | Both passed; no skips | 0.547s |
| Impetus scaffold verifier | Passed (structure only) | 0.094s |

The full suites include all 12 connected capture tests and the standalone
schema/vector test; no Impetus-dependent test was skipped. Pytest's sole skip was
`test_installed_wheel_public_cli_and_exact_local_schema_closure`: Spine's own
interpreter lacks setuptools. It passed in full unittest with
`SPINE_WHEEL_BUILD_PYTHON` set to the existing prepared Threshold interpreter.

**Pre-existing issues:** Strict mypy remains red. All 10 diagnostic files are
byte-identical to HEAD and a separate committed-source export produced exactly
the same 36 diagnostic lines. Pytest repeated the already-recorded
`PytestUnraisableExceptionWarning` in
`IndependentReadPageTests.test_page_serialization_is_inside_the_shared_deadline`
(`WebError: capacity_exceeded` from the synthetic deadline trace). Neither is a
new capture regression; neither was fixed or suppressed. Unittest emitted the
same existing deadline-trace exception. No failed Spine test assertions were observed.

**Installed-wheel qualification succeeded for this boundary.** An offline scratch
copy built `spine_ledger-0.11.2-py3-none-any.whl` using the existing sibling
Threshold setuptools 80.9.0 backend (1.724s); installation of only this wheel into
a fresh venv used `--no-index --no-deps` (1.013s). Existing validation dependencies
were exposed by a plain dependency-directory `.pth`, without downloading or
installing dependencies. From outside the checkout, `python -I` asserted that
Spine, all three capture modules and the packaged schema resolve under the fresh
runtime prefix, with checkout `src` absent, then ran the 13 unchanged tests against
the independent deterministic worker. Wheel SHA-256:
`d9426e71097a255b0badf5ffdaac5fd5876fd734495f5d38357eaf77de604d6a`.
This is local capture-boundary qualification, not a whole-package release claim.
The first scratch harness run had 12 passes and one missing-fixture error
(5.447s wall): the source-layout JSON copy used by a parity assertion was absent.
Copying only that JSON fixture into scratch resolved it; source/tests were unchanged.
The initial error and successful rerun logs are both retained.

**Commands and local evidence:** Logs, exact argv, durations, wheel, copied tests,
qualification bootstrap and before/after byte manifests were retained outside the
checkout as temporary local evidence, not published release storage. Session-specific
scratch locations are omitted from this checkpoint. The `run.py` wrapper writes stdout/stderr and JSON
exit/duration records, sets `PYTHONDONTWRITEBYTECODE=1`, and puts `TMPDIR` under
that directory. The equivalent check commands from the Spine root were:

```sh
RUN=/path/to/disposable-validation-workspace
export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$RUN/tmp"
export IMPETUS_SRC="$PWD/../impetus/src"
PYTHONPATH=src:tests .venv/bin/python -m pytest -o addopts='' -p no:cacheprovider -q -ra tests
PYTHONPATH=src:tests SPINE_WHEEL_BUILD_PYTHON="$PWD/../threshold/.venv/bin/python" \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check . --no-cache
.venv/bin/mypy --strict --no-incremental --cache-dir "$RUN/mypy-cache" src/spine/core src/spine/ledger
for family in web facet_web rendering revision_readback people; do
  PYTHONPATH=src .venv/bin/python "scripts/sync_${family}_contracts.py" --check
done
PYTHONPYCACHEPREFIX="$RUN/bytecode" .venv/bin/python -m compileall -q src tests examples scripts
node --test docs/site/build-pages.test.mjs
# Run the sibling checks from its checkout:
(
  cd ../impetus
  PYTHONPATH=src ../spine/.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
  ../spine/.venv/bin/python scripts/verify_repo.py
)
# Build from the scratch source copy, then install only the resulting Spine wheel:
../threshold/.venv/bin/python -m pip --isolated wheel --no-index --no-deps \
  --no-build-isolation --no-cache-dir --disable-pip-version-check -w "$RUN/wheels" "$RUN/wheel-source"
.venv/bin/python -m venv --without-pip "$RUN/runtime"
.venv/bin/python -m pip --isolated --python "$RUN/runtime/bin/python" install \
  --no-index --no-deps --no-cache-dir --disable-pip-version-check "$RUN/wheels/spine_ledger-0.11.2-py3-none-any.whl"
env -u PYTHONPATH -u PYTHONHOME "$RUN/runtime/bin/python" -I "$RUN/installed-checks/qualify.py"
git diff --check
```

Final byte comparison: only `docs/BACKLOG.md` changed during validation; all
pre-existing Spine and Impetus edits retained. Final `git diff --check` passes.
All tests used disposable ledgers and deterministic/fake or mocked providers. No network/dependency acquisition, real
provider calls, notifications, user-ledger writes, staging/production access,
feature activation, external review, commit, push or deployment occurred.

**Local checkpoint selection (2026-10-31):** The operator approved a bounded local
commit of SPINE-067, directly supporting design/operations documentation, fixtures
and this validation evidence. All mixed-file hunks were inspected. The unrelated
`AGENTS.md` guidance and the independent Impetus working tree are excluded and
preserved. Validation code/contracts match the checked snapshot; only documentation
was adjusted to omit session-specific scratch locations and record this selection.
Existing typing/deadline issues remain separate work. No push, deployment, live
provider, notification or feature activation is authorized by this checkpoint.


### SPINE-066 — Draft a direct advisory experiment and Impetus handoff

**Status:** Done (2026-10-29, Codex), rough design and examples only.
**Selected scope:** The operator requested a small Spine-owned design and Impetus
handoff, then selected a broader experiment across frequent opted-in event reminders.
Archetype, permitted facets, ordinary reminder text and relative timing inform a
useful or personable addition. No addition is valid and tools are optional. The
first milestone captures proposals for review without changing delivered content.
**Delivery:** [Versioned rough design](../specs/contextual-notification-experiment.md),
[Impetus owner handoff](CONTEXTUAL_NOTIFICATION_EXPERIMENT_HANDOFF.md), and concrete
[request](../examples/contextual-notification-experiment.request.json)/
[result](../examples/contextual-notification-experiment.result.json) examples.
The flight example demonstrates a context-only personable line, not a mandatory
travel workflow or provider capability. The design covers original-byte binding,
claim/readback, no automatic research retries, cutoff/fallback, source freshness,
capture evaluation and later one-notification selection/delivery. README, spec
index, compatibility notes and roadmap rationale link the proposed boundary.
**Owner boundary:** No governance service in this experiment; the existing governed
advisory profile and Impetus Light-first decision remain separate. Experimental-mode
adoption, exact schemas, disclosure/storage mappings, process/provider/tool limits
and timing configuration remain explicit owner decisions before runtime. Existing
source specifications, runtime, ledger schema and sibling repositories are unchanged.
**Verification:** Both JSON examples parse and their work/version binding, raw-byte
SHA-256, call/output limits, relative event/notification timing and execution/cutoff
ordering agree. All 10 local links in the new design/handoff resolve, including
anchors; `git diff --check` passes. Manually reviewed the proposal against the
existing source/disclosure, fallback, replay and attempt-ownership requirements.
These checks validate design/example consistency, not runtime conformance. No runtime
tests, external audit, provider calls, real sends, staging changes, commit or push
were performed. The pre-existing `AGENTS.md` edit is preserved.

### SPINE-064 — Add coordination-level acceptance stories

**Status:** Done — test-only delivery (2026-10-25). The operator selected a separate
implementation handoff for the exposed defect, tracked as SPINE-065. At the
test-only delivery, four stories passed and one intentionally remained a failing
regression, without a skip or expected-failure marker. The subsequent SPINE-065
runtime repair makes all five pass without editing this module; the original
failure evidence below is retained rather than relabeled as a green baseline.
**Scope:** Public-command stories for fresh-process plan handoff, coherent
rescheduling, independent people/access/delivery, lost-response replay, and honest
delivery history. Disposable SQLite ledgers, explicit clocks, and fake transport;
no external services, daemon, real ledger, or new dependency. Preserve concurrent
timezone integration and all existing staged work. Generated sequence testing and
the deferred resilience qualification campaign are outside this slice.
**Acceptance:** Independent expected outcomes across the composed capabilities;
standalone unittest/pytest execution, full regression runs, Ruff verification,
and an actionable defect handoff. Operator decision keeps runtime repair separate.
**Evidence:** [Acceptance module](../tests/test_coordination_acceptance.py) runs
without importing other test classes. It uses real CLI subprocesses for handoff
and replay, public commands for authoring, protected people reads for access,
and a second SQLite connection to verify committed evidence before fake transport.
**Defect found:** Move an event from 2026-08-22 14:00 UTC to the next day, then
reconcile its follow-source task with bounded `item_relative` materialization.
The task moves to 2026-08-23 13:00 UTC and its old reminder is cancelled, but the
expected replacement at 12:30 UTC is absent. In
`src/spine/commands/temporal_bindings.py`, `handle_binding_reconcile` normalizes the
materialization window against the old target before deriving the successor time.
The same calculation exists in committed pre-integration HEAD. Section 7.6 of
[relative bindings](../specs/relative-temporal-bindings.md#76-notification-work-reconciliation)
requires bounded materialization against successor truth. No runtime repair made.
**Verification:** With `PYTHONDONTWRITEBYTECODE=1`, documented unittest discovery
ran **1,187 tests in 284.972s: one failure, one skip**. Full pytest with
`PYTHONPATH=src:tests .venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider`
reported **1,224 passed, one failed, one skipped, 1,889 subtests passed in 287.60s**.
Both fail only the new rescheduling story. Pytest also reports one existing
deadline-test unraisable-exception warning; pytest-only timezone tests account
for the discovery-count difference. The other four new stories passed standalone
pytest in 12.06s. Repository-wide Ruff and diff checks pass. The unrelated pytest
import-path limitation remains unchanged. The concurrent timezone integration was
committed as `233656c` during validation; this task performed no staging or commit.

### SPINE-063 — Remove duplicate test discovery from imported test classes

**Status:** Done locally (2026-10-25), operator-selected cleanup.
**Change:** Replaced six direct test-class imports in five rendering test modules
with module imports and qualified references. Preserved every test body, fixture,
and inherited variant; no runtime, contract, or test-selection policy changes.
**Verification:** Compared discovery before/after by defining class source file,
class name, and method name: 1,263 executions became 1,178, preserving all 1,178
distinct cases exactly once. Removed 44 delivery, 21 foundation, 14 successor, and
6 schedule-operation repetitions. Python 3.14.6: documented
`.venv/bin/python -m unittest discover -s tests` passed **1,178 tests in 253.027s,
one skipped**. With `PYTHONPATH=src:tests`, `.venv/bin/python -m pytest -o addopts='' -q
-p no:cacheprovider` passed **1,177 tests and 1,889 subtests, one skipped, in
254.35s**. Both used `PYTHONDONTWRITEBYTECODE=1`; the existing skip requires a
prepared wheel-build interpreter. Repository-wide Ruff and `git diff --check`
passed. Pre-existing local `AGENTS.md` changes were preserved byte-for-byte.
**Separate harness limitation:** Without the explicit test import path, pytest
has five collection errors in the people authoring, commands, cursors, directory,
and public CLI modules due to top-level test-module imports. Reproduced the same
errors with unmodified HEAD test files; left this separate repair out of scope.

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
