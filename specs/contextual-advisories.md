# Spine Scheduled Contextual Advisories

Status: Draft v0.2.0; selective manual synthesis; cross-system design target; not implemented
Scope: One scheduled Spine trigger causing one governed, bounded, read-only agent run and at most one ordinary derivative notification
Created: 2026-08-18
Updated: 2026-09-12

## 1. Purpose

Spine can determine when an event or task occurs, when notification work is eligible,
whether its source facts remain current, and whether delivery was attempted. This
specification defines the first cross-system boundary for using that deterministic
schedule to request bounded LLM initiative.

The motivating scenario is deliberately ordinary:

> Two days before a golf trip, help the user prepare. The agent may discover that the
> weather is relevant, retrieve a forecast through an approved read-only tool, and
> produce a useful packing advisory.

The schedule does not prescribe weather, a tool sequence, or final prose. It delegates
a bounded objective. The agent may instead discover another materially useful fact,
request clarification, or return `no_action`.

The first implementation experiment MUST answer this question:

> Can one scheduled Spine fact safely create an opportunity for an LLM to exercise
> bounded initiative, produce useful evidence-backed information, and create exactly
> one trustworthy notification without giving the LLM authority to mutate Spine or
> deliver directly?

This document specifies the role boundaries, minimum envelopes, lifecycle, freshness,
and proof obligations needed to run that experiment. It does not define a general
agent platform.

## 2. Naming and Authority Invariant

Normative cross-system contracts MUST name roles and protocols, not repositories,
packages, deployments, or product brands.

The governing role is `governance_authority`. A component may implement that role
under any repository, service, package, or product name without changing Spine's
contract. No external implementation name participates in an identifier preimage,
enum, schema property, command name, receipt, persisted authority fact, or error code.

The same rule applies to `agent_runtime`, `tool_provider`, `scheduler_runtime`, and
`delivery_adapter`. Configuration may bind a role to a concrete deployment, but the
binding is operational metadata rather than canonical coordination truth.

## 3. Foundational Invariants

1. **Deterministic shell, discretionary center.** Spine deterministically decides when
   advisory work is eligible. The agent may choose what to investigate only inside an
   accepted capability grant.
2. **A trigger is not authority.** Schedule eligibility does not authorize model use,
   tool use, canonical mutation, third-party contact, purchase, or delivery.
3. **Discretion cannot expand authority.** Tool output, retrieved content, prompts,
   and model conclusions cannot widen the accepted capabilities, budget, targets, or
   allowed outcomes.
4. **Source truth remains granular.** Items, versions, occurrences, advisory policies,
   opportunities, work, governance decisions, runs, outcomes, notification work, and
   delivery attempts retain separate identities and lifecycle evidence.
5. **Model output is not schedule identity.** Stochastic text, inferred plans, tool
   selection, and model-provider output never participate in deterministic schedule,
   opportunity, or source-work identity.
6. **Every run is snapshot-bound.** A run binds to exact item, item-version,
   occurrence, policy-version, context-snapshot, capability-request, and usefulness-
   deadline facts.
7. **Freshness is checked more than once.** Current source truth is checked before
   dispatch and again before accepting an outcome or materializing derivative work.
   Delivery continues to use ordinary attempt-start freshness.
8. **The agent cannot send.** An advisory or clarification becomes normal Spine
   notification work. Only the existing attempt-gated delivery path may contact a
   destination.
9. **The agent cannot mutate Spine.** A read-only run may return an advisory,
   `no_action`, or a clarification request. Any future canonical mutation is a
   separately governed candidate action outside Version 1.
10. **Silence is valid.** A successful run may return `no_action`; scheduled autonomy
    does not imply mandatory notification.
11. **No hidden reasoning contract.** The system persists structured inputs, tool-call
    evidence, concise findings, decisions, and outcomes. It MUST NOT require or treat
    private chain-of-thought as evidence.
12. **Replay does not repeat intelligence.** An accepted outcome can be replayed and
    read back without invoking the model or tools again.
13. **No competing governance model.** Spine's advisory policy is temporal and
    coordinative intent, not a second governed-intent, policy, dispatch, approval, or
    evidence-acceptance authority. Cross-system adapters bind Spine facts to the
    governance authority's native versioned artifacts and return verifiable references.

## 4. Version 1 Experimental Profile

Version 1 supports exactly one narrow profile:

- `capability_profile=read_only_contextual_advisory.v1`;
- one active event with a resolvable `local_instant` start;
- optionally one selected actionable occurrence of a recurring event;
- one canonical primary location suitable for an approved information lookup;
- one target-relative advisory trigger before the event;
- one plain-language objective supplied by the user or operator;
- an allowlisted set of read-only tools;
- bounded model calls, tool calls, elapsed runtime, and usefulness deadline;
- terminal outcomes `advisory`, `no_action`, and `request_clarification`;
- zero or one derivative notification work instance; and
- existing Spine delivery-target and attempt-ledger behavior.

The default conformance scenario uses this objective:

> Help me prepare for this event. Use approved read-only tools when they could produce
> materially useful, timely information. Do not contact anyone or change anything.

The objective MUST NOT require or mention a weather lookup. Weather discovery is one
test of agent initiative, not a hard-coded workflow contract.

Version 1 excludes:

- canonical Spine writes requested or performed by the agent;
- messages, purchases, bookings, reservations, or other external writes;
- contact with participants or third parties;
- unrestricted web or tool access;
- credential acquisition by the agent;
- arbitrary tool installation;
- multi-agent delegation;
- child workflow graphs;
- open-ended loops or background continuation;
- proactive multi-item planning sweeps;
- automatic policy learning;
- agent-authored recurrence or notification schedules; and
- more than one derivative notification per advisory opportunity.

Version 1 authoring and submission validation MUST enforce the event-only scope and
required canonical primary location above. Generic item or snapshot types MUST NOT
implicitly admit tasks or waive that location prerequisite. If required location facts
cannot be disclosed under the context scope, the request fails closed rather than
silently weakening the experimental profile.

## 5. Role Boundaries

### 5.1 Spine: coordination and scheduling authority

Spine owns:

- the event, item version, temporal anchor, recurrence occurrence, and location facts;
- the contextual-advisory policy and its trigger;
- deterministic opportunity expansion and durable advisory work;
- the exact context snapshot or immutable references needed to reproduce it;
- source and deadline freshness;
- submission references and `acceptance_reference` facts;
- derivative notification intent and work provenance;
- delivery-target selection and delivery lifecycle readback; and
- reconciliation, audit, command receipts, and replay facts.

Spine MUST NOT evaluate governance policy, plan the investigation, invoke an LLM,
select tools for the agent, accept its own execution evidence on behalf of another
authority, or let the agent bypass normal notification delivery.

Spine alone persists changes to its advisory policy, opportunity, work, and derivative
notification facts through validated Spine-owned operations. External roles produce
the authoritative native decisions, authorizations, and execution evidence that may
cause those changes; they do not acquire direct ledger-mutation authority. Any later
transition table MUST distinguish the producer of the causal evidence from the sole
Spine persistence authority. A governance adapter translates and verifies references;
it is not an additional authority over either system's native lifecycle.

### 5.2 `scheduler_runtime`: cadence authority

The scheduler runtime owns wake-up cadence, singleton/process behavior, bounded polling,
and processor invocation. It may discover eligible Spine advisory work and initiate the
submission protocol. It does not own policy semantics, governance decisions, agent
reasoning, or canonical outcomes.

### 5.3 `governance_authority`: authorization and evidence-acceptance authority

The governance authority owns:

- conversion or binding of a Spine submission to a governed intent;
- policy evaluation for the requested capability profile;
- allowance, denial, expiry, and any required approval;
- the exact capability grant and execution budget;
- dispatch authorization;
- acceptance or rejection of returned execution evidence; and
- replayable decision and acceptance receipts.

It MUST NOT become the schedule authority, rewrite the Spine context snapshot, infer
that delivery occurred, or silently grant capabilities that Spine did not request.
Its native intent, policy, authorization, dispatch, attempt, receipt, and evidence
artifacts remain canonical within that authority. Spine MUST NOT recreate those
artifacts under cosmetically neutral names.

### 5.4 `agent_runtime`: reasoning and execution authority

The agent runtime owns runtime planning, allowed tool selection, synthesis, and the
structured outcome. It operates only under a valid dispatch authorization. It MUST NOT
expand its grant, mutate Spine, contact a recipient, choose an unapproved destination,
or represent an outcome as accepted or delivered.

### 5.5 `tool_provider`: capability implementation

A tool provider implements one granted read-only capability and returns structured,
timestamped evidence. Tool content is untrusted input. The provider does not interpret
the overall objective or authorize subsequent actions.

### 5.6 `delivery_adapter`: external notification execution

The delivery adapter consumes eligible derivative notification work through Spine's
ordinary attempt gate. It does not receive the agent's capability grant and cannot
turn an advisory run into another class of action.

The deterministic ordinary-reminder renderer in `specs/notification-rendering.md` is
not an agent runtime and does not consume advisory outcomes. It remains the reliable
non-model rendering path when an advisory is unavailable, rejected, stale, or absent.

## 6. Durable Spine Facts

The first implementation is expected to require a later ledger schema version. Exact
tables and identifier preimages remain open until the cross-system envelopes have been
audited, but the logical facts are:

### 6.1 Contextual-advisory policy

A version-scoped policy minimally records:

- stable advisory intent identity and immutable policy-row identity;
- source item and item version;
- trigger schedule or notification-opportunity binding;
- plain-language objective;
- requested capability profile;
- allowed outcome kinds;
- tool, model, runtime, and cost limits;
- usefulness deadline;
- context-scope declaration;
- derivative delivery target and rendering profile;
- status and lineage; and
- authoring command, timestamp, and normalization version.

This policy expresses requested behavior. It is not an authorization grant.

### 6.2 Advisory opportunity and work

Deterministic expansion produces an advisory opportunity for an exact source anchor or
occurrence and trigger instant. Materialization produces durable advisory work before
any governance request or model invocation.

The logical work binds at least:

- advisory opportunity and policy version;
- source item, item version, anchor, and optional occurrence provenance;
- context-snapshot hash;
- eligibility instant, usefulness deadline, and expiry instant;
- requested capability profile and limits; and
- current submission, `acceptance_reference`, and derivative-work references when present.

An eligible opportunity alone MUST NOT invoke the model or tools.

Discovery MUST resolve existing work for the same source opportunity and immutable
policy version before creating fresh work. Re-observing unchanged source facts MUST
return the existing identities, including after work has reached a terminal state.
Snapshot construction time and stochastic output MUST NOT create a new source-work
identity. Exact lookup keys, first-creation rules, uniqueness enforcement, and identity
preimages remain machine-contract prerequisites, not closed by this logical rule.

### 6.3 Context snapshot

The context snapshot is a minimized, versioned input envelope. Version 1 may include:

- item identity, type, title, details, and current lifecycle state;
- exact local time, UTC instant, timezone, and timezone-database version;
- selected recurrence occurrence and provenance when applicable;
- canonical primary location facts;
- explicitly permitted related-item summaries; and
- exact snapshot time and content hash.

It MUST exclude delivery credentials, unrelated personal data, hidden adapter state,
and mutable references whose resolved contents cannot later be identified. A context
scope permits disclosure; it does not grant tool or mutation authority.

Snapshot capture time is observation evidence, not a source-freshness input. Once
submitted, the exact snapshot contents and their integrity hash MUST be retained or
immutably resolvable for replay. The future hash preimage MUST explicitly exclude the
hash field itself and declare its canonicalization version; it may include the original
capture time, but a later capture time MUST NOT invalidate unchanged source facts.
A closed snapshot schema alone does not settle minimization or sensitive-data policy;
the disclosure and redaction decisions in Section 15 remain required.

## 7. Cross-System Envelope Family

The initial boundary uses role-neutral Spine envelopes and semantic requirements for
the other roles. Machine-readable schemas, fixtures, and a mapping to the selected
governance authority's native contracts MUST be added before implementation or
compatibility declaration.

The names in this section are Spine-facing interoperability views. They are not
alternate canonical intent, dispatch, receipt, or evidence types. When the configured
governance authority already has a native versioned artifact for one of these facts,
the adapter MUST preserve that artifact's identity and return a verifiable reference;
it MUST NOT synthesize a competing hash, lifecycle, or acceptance status in Spine.

Spine-facing projections may normalize their own declared fields, but MUST preserve
native artifact identities and native canonical bytes, hashes, and verification rules.
Normalizing a projection MUST NOT rewrite native evidence or become an alternate
acceptance decision. The future mapping and fixtures MUST show which fields are
Spine-owned projections and which remain opaque native authority facts.

### 7.1 `spine.contextual-advisory-submission.v1`

Spine submits one immutable request containing:

- `submission_id` and idempotency key;
- advisory work, opportunity, and policy identities;
- source item/version and optional occurrence-provenance identities;
- context snapshot or immutable snapshot reference plus hash;
- objective and requested capability profile;
- requested limits and allowed outcome kinds;
- eligible, usefulness-deadline, and expiry timestamps;
- protocol versions; and
- a callback/correlation reference that conveys no ambient authority.

It MUST NOT contain model-provider credentials, tool credentials, delivery credentials,
or a concrete governance implementation name.

Before crossing this boundary, Spine MUST atomically persist or resolve the submission
identity, idempotency key, exact canonical request bytes, and their declared protocol
and canonicalization versions for the advisory work. Repeated submission MUST reuse
those persisted facts rather than rebuild the request with a new snapshot time. A
same-key request with different canonical bytes is a reason-coded replay mismatch:
it leaves the original submission unchanged and MUST NOT cross the governance boundary.

### 7.2 `spine.contextual-advisory-governance-binding.v1`

The governance adapter returns a signed or otherwise verifiable Spine-facing binding
receipt containing:

- submission identity and native governed-intent reference;
- native decision and dispatch-authorization references when present;
- projected classification `allowed|approval_required|blocked`;
- reason code;
- requested capability profile and the accepted profile or explicit subset;
- exact tool, model, runtime, cost, and expiry constraints;
- native policy, registry, evaluator, and protocol versions; and
- decision timestamp and replay facts.

The projected classification is readback and routing information. It MUST NOT replace
the native decision, make evidence policy-visible, or authorize dispatch by itself.
Version 1 may implement only preauthorized `allowed` and terminal `blocked`; it MUST
fail closed rather than pretending to support a native approval lifecycle.

An accepted grant MUST be no broader than the submitted request: permitted model and
tool references and allowed outcome kinds are subsets of those requested; numeric
ceilings may only decrease; expiry may only shorten; and the cost currency or
accounting unit MUST remain identical. Accepted expiry MUST NOT exceed submission
expiry or the usefulness deadline. Exact reference equality, numeric encoding, and
set normalization belong in the machine contracts and their fixtures before
implementation. The binding MUST expose the effective constraints and allowed outcome
set, directly or through verifiable native references. Spine MUST reject a missing,
unverifiable, or widened grant for dispatch; that validation does not make Spine the
governance policy evaluator.

### 7.3 Governed invocation requirements

The governance authority's native authorized invocation presented to the agent runtime
must bind:

- governed intent, Spine submission, native dispatch, and logical run identities;
- exact native dispatch-authorization reference and expiry;
- objective and minimized context snapshot;
- allowed capabilities and tool descriptors;
- hard budgets and deadline;
- required output contract; and
- correlation facts for tool and model attempts.

The required output contract MUST bind the effective allowed outcome set from the
submitted request and accepted grant. Prompt text alone cannot change that set.

The invocation does not disclose approval internals or grant capabilities by textual
instruction alone. Its canonical schema, hash, idempotency, attempt, and retry rules
belong to the governance authority rather than this Spine specification.

### 7.4 Produced contextual-advisory evidence requirements

The runtime submits produced evidence with exactly one terminal outcome:

- `advisory`: concise headline/body, structured findings, evidence references,
  generation time, and information-validity time;
- `no_action`: a bounded reason code and optional concise explanation; or
- `request_clarification`: one concise question and reason code.

Every outcome also contains run and authorization identities, terminal status, model
and tool attempt references, actual usage, start/end times, and output-contract version.
Failure and timeout are execution terminal states, not `no_action` outcomes.

A successful outcome is admissible only when its kind is a member of the submitted
allowed outcome set and any narrower accepted grant/output contract. The governance
authority MUST reject evidence that violates this constraint, even if the kind is a
valid member of the overall three-value enum. A rejection preserves the relevant
native evidence and reason rather than relabeling the result as `no_action`. Failure
evidence MUST distinguish timeout, tool/model failure, invalid output, and authority
violations and bind the actual attempt/usage facts, including failures before any
model or tool call. Actual over-budget usage, if observed, remains recorded evidence
of a violation; it MUST NOT be clamped or discarded to make a run appear conforming.

The outcome MUST NOT contain a command to mutate Spine or an instruction to a delivery
adapter. It MUST NOT require chain-of-thought. Citations or provider references must
identify the evidence used without copying unrestricted source content.

The runtime's receipt and outcome are produced evidence, not accepted truth. Their
canonical evidence schema, integrity hash, lifecycle, and replay rules belong to the
governance authority. The eventual cross-system fixture MUST demonstrate exact binding
between the Spine submission, native dispatch authorization, native execution receipt,
and produced outcome evidence.

### 7.5 `spine.contextual-advisory-acceptance-reference.v1`

The governance adapter returns a Spine-facing `acceptance_reference` containing:

- Spine submission and native governed-intent, dispatch, run, evidence, and decision
  references;
- projected classification `accepted|rejected`;
- native acceptance reason code;
- native accepted outcome hash and evidence references;
- acceptance time; and
- native acceptance-registry, evaluator, and protocol versions.

Spine may materialize derivative notification work only from an accepted outcome whose
submission and source facts are still fresh. Governance acceptance is necessary but is
not itself proof of Spine freshness or delivery. The projected classification MUST be
verifiable against the native acceptance artifact and MUST NOT become a second
evidence lifecycle maintained by Spine.

Before consuming an accepted reference, Spine MUST verify its binding to the stored
submission, native authorization, run, evidence, and outcome; verify that the outcome
is successful and belongs to the effective allowed set; and apply its own freshness
gate. A missing, unverifiable, or contradictory binding, including an out-of-set
outcome marked accepted by the producer, MUST create no derivative notification.
Spine records a reason-coded local consumption failure without changing the native
acceptance decision or inventing a second evidence-acceptance lifecycle. This failure
and its evidence references MUST be visible in operator readback.

## 8. Lifecycle

One successful advisory follows this sequence:

1. An operator authors an advisory policy bound to an exact Spine item and trigger.
2. Spine deterministically expands and materializes one advisory work item.
3. The scheduler runtime selects eligible work.
4. Spine verifies source, policy, occurrence, deadline, and context freshness.
5. The submission is recorded before it crosses the governance boundary.
6. The governance authority binds the submission to its native governed intent and
   returns a replayable decision reference.
7. If allowed, it creates native dispatch authorization and dispatches one bounded
   invocation to the agent runtime.
8. The runtime may call only granted read-only tools and submits one terminal result as
   produced evidence.
9. The governance authority accepts or rejects that evidence through its native
   lifecycle and returns a verifiable `acceptance_reference`.
10. Spine rechecks source and deadline freshness.
11. An accepted `advisory` or `request_clarification` atomically creates at most one
    ordinary derivative notification intent/work bundle with provenance back to the
    accepted outcome. `no_action` creates none.
12. The existing notification processor separately attempts delivery and records the
    result in `side_effect_attempts`.

Authoring, opportunity expansion, advisory-work materialization, governance decision,
agent execution, outcome acceptance, derivative-work materialization, delivery
attempt, and delivery outcome remain separately observable facts.

If derivative notification validation or persistence fails after governance acceptance,
Spine MUST retain the acceptance reference and a reason-coded local materialization
failure, with no partially committed derivative intent/work bundle and no delivery
attempt or delivery claim caused by that failed materialization. Reconciliation MUST
first distinguish an absent bundle from an already committed bundle, returning the
existing identities in the latter case. Neither case authorizes rerunning intelligence.
Retry scheduling and recovery transitions remain explicit decisions in Section 15;
this failure-reporting requirement does not silently make failure terminal forever or
authorize automatic retries.

## 9. Freshness, Cancellation, and Time

The context snapshot is fresh only while all bound source facts remain current and the
usefulness deadline has not passed. At minimum, freshness compares:

- item identity and current version;
- item lifecycle state;
- advisory policy identity and active status;
- temporal-anchor identity and resolved instant;
- recurrence revision, occurrence selector/key, and active provenance when applicable;
- canonical location version when location entered the snapshot; and
- context-snapshot hash and protocol version.

The hash comparison verifies the persisted snapshot against its stored submission,
not against a newly constructed snapshot with a later observation time. Freshness
also compares current values of all bound source facts, including versions of any
disclosed related-item facts. A change in capture time alone is not staleness; a
changed bound source fact cannot be excused by reusing the stored integrity hash.

If freshness fails before dispatch, Spine cancels or supersedes the advisory work and
does not submit it. If source truth changes during execution, the run and its evidence
remain auditable, but Spine rejects the outcome for derivative materialization with a
reason-coded stale classification. If source truth changes after derivative work is
created, ordinary notification reconciliation and attempt-start freshness apply.

No component may claim that an in-flight model call was undone. Already completed tool
or model attempts remain historical evidence, while stale results lose authority to
produce new delivery work.

The dispatch gate applies even if a submission has already been persisted or sent.
The native dispatch path MUST obtain a current Spine freshness result before starting
execution; an earlier submission check alone is insufficient. If execution has already
started when a change is detected, the historical run remains evidence and the
outcome/derivative freshness gates prevent stale materialization. The exact native
handoff and race-handling fixtures remain prerequisites under Section 15.

## 10. Idempotency and Attempt Accounting

- One source opportunity and policy version produce one logical advisory work identity.
- Repeated scheduler discovery returns the existing work.
- Repeated submission uses the same submission identity and byte-equivalent request.
- Repeated governance dispatch resolves the same logical run and MUST NOT create a
  second concurrently authoritative run.
- Tool and model executions are attempts of that run and require correlation and
  replay evidence; retries do not create a new source opportunity.
- One accepted outcome produces at most one derivative notification intent/work bundle.
- Repeated outcome reconciliation returns the existing derivative identities.
- Delivery retries remain attempts for the same notification work and use Spine's
  existing `side_effect_attempts` rules.

Whether model and read-only tool attempts are mirrored in Spine's generic attempt
ledger or referenced from the governance authority remains an open persistence
decision. There MUST NOT be two competing authorities for the same attempt fact.

## 11. Failure and Outcome Semantics

The first contract family must distinguish at least:

- source stale before submission;
- submission replay mismatch;
- governance blocked;
- governance approval required but unsupported by the selected implementation;
- governance decision unavailable or expired;
- unauthorized capability or tool request;
- agent invocation timeout;
- tool unavailable or tool evidence invalid;
- model failure or invalid output;
- outcome outside the submitted or narrowed allowed set;
- unverifiable or contradictory governance/evidence references;
- successful `no_action`;
- successful `request_clarification`;
- accepted advisory stale before derivative materialization;
- accepted advisory or clarification unable to materialize derivative work;
- usefulness deadline exceeded;
- derivative notification already materialized; and
- later notification delivery failure.

An execution failure MUST NOT be reported as `no_action`. An accepted advisory MUST NOT
be reported as delivered until a delivery attempt succeeds. The experiment has no
static fallback reminder unless a later specification explicitly defines one.

## 12. Readback

A canonical operator read must expose, without raw SQL:

- advisory policy and trigger;
- source item/version/occurrence and snapshot hash;
- advisory work lifecycle;
- submission identity;
- governance decision and `acceptance_reference` facts with reason codes;
- agent run status, outcome kind, usage summary, and evidence references;
- freshness classification;
- derivative notification policy/work identity when present; and
- delivery attempt/outcome separately.

Readback MUST also expose local acceptance-consumption failures and derivative
materialization failures, retaining any native acceptance reference. Every failed or
terminal advisory-work path MUST expose its latest relevant reason, transition time,
Spine persistence actor, causal evidence-producing role, and evidence/replay references
when present. Absence of a submission, run, or attempt MUST be represented as absence,
not fabricated success or execution evidence.

Compact output may summarize these facts but cannot collapse `accepted`,
`notification_materialized`, `delivery_attempted`, and `delivered` into one status.

The same separation applies to acceptance-consumption and materialization failures.
Compact readback may omit large evidence bodies but MUST retain stable correlation
IDs, current advisory-work state, freshness, the relevant failure reason, and derivative
work and latest delivery-attempt facts when present.

The implementation-ready command family MUST provide logical policy authoring and
canonical policy/work readback through Spine-owned operations, not raw SQL. Authoring
must bind actor, command identity, target version, normalized requested policy, and
replay facts; readback must accept stable item/policy/work selectors. Exact public
names, request/response fields, bounded selection, and permission rules remain open
under Section 15; these logical requirements do not declare runtime commands.

## 13. Proof Strategy

The first slice has two different proof layers. They MUST NOT be conflated.
There are exactly two required layers: the deterministic conformance harness and the
real product experiment. Fake adapter, model, and tool integration fixtures are test
artifacts within the deterministic conformance harness; they are not a third proof
layer and cannot satisfy the real product experiment.

### 13.1 Deterministic conformance harness

Fake clock, governance, agent, tool, and delivery adapters prove:

- duplicate scheduler discovery creates one advisory work item;
- duplicate submission and dispatch do not create duplicate logical runs;
- an accepted advisory creates exactly one derivative notification work item;
- `no_action` creates none;
- `request_clarification` creates at most one;
- a source move before execution stales or cancels the work;
- a source move during execution prevents derivative materialization;
- a forbidden write, contact, or send capability is denied;
- timeout and failure remain evidence but create no advisory notification;
- the agent runtime cannot invoke the delivery adapter directly;
- accepted outcomes replay without rerunning the model or tools; and
- delivery remains separately attempt-gated.

Passing these tests proves protocol composition and safety behavior. It does not prove
that autonomous advice is useful.

The machine-contract fixture set MUST additionally prove:

- an enum-valid but disallowed outcome is rejected, including when a native reference
  incorrectly claims acceptance, without derivative work or a second acceptance ledger;
- a widened tool/model/outcome grant, raised budget, extended expiry, or changed cost
  unit cannot authorize dispatch;
- external decision/evidence producers cannot directly mutate Spine work state;
- unchanged source facts observed at a later time retain identities and freshness,
  while changed bound item, occurrence, location, or related-item facts fail freshness;
- same-key changed submission bytes never cross the governance boundary;
- a source change after submission but before execution is checked at dispatch;
- materialization failure preserves acceptance evidence without partial derivative work,
  and retry/replay after an already committed bundle returns its existing identities;
- failed attempts and over-budget usage remain observable without becoming `no_action`;
- projections preserve native artifact identities and verification bytes; and
- required location disclosure and event-only scope cannot be bypassed by generic types.

Canonical preimage, encoding, uniqueness, and concurrent replay vectors MUST be added
when those machine contracts are authored; this list is a proof obligation, not a
claim that executable fixtures already exist.

### 13.2 Real product experiment

The meaningful experiment uses:

- a real LLM invocation;
- at least one real approved read-only information source, initially weather;
- real Spine schedule, snapshot, freshness, idempotency, and derivative-work behavior;
- enough real governance enforcement to deny an unauthorized action;
- fake outbound delivery or an isolated non-sending capture adapter; and
- the general objective in Section 4, without telling the model to check weather.

The experiment records whether the agent:

- independently identifies a materially relevant investigation;
- chooses and uses an allowed tool appropriately;
- grounds its advisory in current evidence;
- remains within its authority and budgets;
- returns `no_action` when useful advice is not supported;
- produces concise advice a human considers better than the static reminder; and
- survives replay and source-staleness tests without duplicate or late delivery work.

Fake model output plus a fake information tool is an integration fixture within the
deterministic conformance harness, not the real product experiment.

## 14. Decision Outcomes

The experiment informs, but does not predetermine, the next architecture step:

- If bounded initiative is useful and the role boundaries remain clean, create the
  smallest agent-runtime component needed to own planning and tool execution.
- If useful behavior requires prescribed recipes, retain explicit automation policies
  and do not build a general runtime.
- If low-risk governance creates disproportionate ceremony, simplify the read-only
  capability profile rather than bypassing the authority boundary.
- If Spine must learn model plans, tool-selection heuristics, or provider concepts, the
  boundary is wrong and must be corrected before implementation.
- If outputs are noisy, generic, late, or weakly grounded, keep ordinary reminders as
  the product default and do not expand autonomy levels.

No new repository or long-running service is justified merely by writing this spec.
That decision follows the real product experiment.

## 15. Open Decisions Before Machine Contracts

The following decisions remain intentionally open before machine contracts and
implementation; selective clarification does not close them by implication:

1. whether the advisory trigger is a new policy family or a typed extension of current
   notification policy authoring;
2. whether advisory execution uses a new `work_kind` or a candidate-action artifact;
3. which component is authoritative for model/tool attempt records and their retention;
4. the exact adapter mapping from Spine submission/binding/`acceptance_reference` views
   to the selected governance authority's native intent, dispatch, receipt, and evidence
   contracts;
5. the exact context-snapshot minimization and sensitive-data rules;
6. the initial budgets and usefulness-deadline defaults;
7. whether `request_clarification` is rendered through the same delivery policy as an
   advisory;
8. the exact commands and readback projection used by operators;
9. unsupported-approval terminal/retry behavior for the selected Version 1 profile;
10. derivative-materialization recovery, retry scheduling, and legal recovery transitions;
11. exact identity preimages, first-creation and concurrent lookup rules, snapshot hash
    preimages, encodings, and projection-to-native verification rules; and
12. the dispatch freshness handoff and race-handling contract with the native authority.

For the three operator policy choices, the current proposals (not ratified defaults)
are: use the same derivative delivery target/profile for clarification and advisory;
stop unsupported approval requests without dispatch or automatic retry; and require
explicit operator recovery after derivative-materialization failure. A recovery choice
must define a usable command and legal transitions before implementation, not merely
name a terminal state. Pending decisions do not grant authority to dispatch, deliver,
or retry by inference.

The primary-location prerequisite is satisfied by the implemented and audited
`spine.schedule-primary-location.v1` family; it is no longer an open advisory decision.

Until these decisions converge, there is no schema version, compatibility declaration,
or implementation commitment for contextual advisories.
