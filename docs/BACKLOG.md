# Spine Backlog

Last updated: 2026-09-15

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

**Status:** Needs decision — supporting draft, compatibility assessment, proposed
test matrix, and Kinflow handoff prepared on 2026-09-13; contract ratification and
subsequent implementation remain pending. **Dependencies:** Existing trusted web
permissions, canonical recurrence/agenda and temporal-binding contracts; acceptance
of the new versioned read projection and disclosure rules before machine-contract
codification or runtime work. This concrete item is independent of the withdrawn
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
Before runtime delivery, ratify the draft, codify exact schemas/registry/version and
consumer migration changes, and implement these behavioral oracles. Documentation
alone does not close the feature.

**Specification evidence:** [Independent activity reads](../specs/independent-activity-reads.md)
defines read boundaries, completeness, availability, consistency, compatibility,
and proposed contract tests. [Kinflow handoff](INDEPENDENT_READS_KINFLOW_HANDOFF.md)
defines consumer migration and rendering behavior. Local Markdown link and consistency
checks cover this specification delivery; no staging verification is claimed.

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
