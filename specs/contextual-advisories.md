# Spine Scheduled Contextual Advisories

Status: Draft v0.3.4; consumption authority and staged freshness clarified; not implemented
Scope: One notification-template activation requesting at most one governed, bounded, read-only agent run, with one notification delivery path for accepted enrichment or ordinary fallback
Created: 2026-08-18
Updated: 2026-09-15

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

The proposed [Cross-System Execution Architecture](cross-system-execution.md)
(`cortext.cross-system-execution`, `0.1.0-draft.1`) describes the reusable role
boundaries. This is a design reference, not adoption or implementation compatibility;
all advisory requirements in this document remain binding for this profile.
Use the shared document's exact-source reference rules when checkpointing downstream
designs. General execution extensibility does not admit additional advisory modes.

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
   submission, at dispatch, and again before consuming a governance-accepted outcome
   or materializing derivative work. Governance alone accepts or rejects evidence;
   Spine's freshness checks determine local consumption eligibility, not native acceptance.
   Delivery continues to use ordinary attempt-start freshness.
8. **The agent cannot send.** An advisory or clarification becomes normal Spine
   notification work. Only the existing attempt-gated delivery path may contact a
   destination.
9. **The agent cannot mutate Spine.** A read-only run may return an advisory,
   `no_action`, or a clarification request. Any future canonical mutation is a
   separately governed candidate action outside Version 1.
10. **Silence requires explicit permission.** A successful run may return `no_action`.
    By default that means no advisory enrichment, not cancellation of the underlying
    reminder. Suppressing the reminder additionally requires explicit, snapshot-bound
    operator permission for silence and an accepted, fresh `no_action` outcome.
11. **No hidden reasoning contract.** The system persists structured inputs, tool-call
    evidence, concise findings, decisions, and outcomes. It MUST NOT require or treat
    private chain-of-thought as evidence.
12. **Replay does not repeat intelligence.** An accepted outcome can be replayed and
    read back without invoking the model or tools again.
13. **No competing governance model.** Spine's advisory policy is temporal and
    coordinative intent, not a second governed-intent, policy, dispatch, approval, or
    evidence-acceptance authority. Cross-system adapters bind Spine facts to the
    governance authority's native versioned artifacts and return verifiable references.

### 3.1 Profile boundary and preservation

[Decision 0005](decisions/0005-profile-scoped-advisory-execution.md) defines the proposed
architectural protection boundary for this draft. The requirements in this document
remain binding for `read_only_contextual_advisory.v1`; no generic interface may bypass
its event, location, notification, outcome, privacy, authority, or lifecycle checks.
Their scope is this capability, not an implicit universal execution model.

Activation, coordination ownership/scope/source dependencies, execution requests,
native runs/evidence, and result consumption are distinct responsibilities even when
bound to one event. Future task research, multi-item planning, and approval-bearing
workflows require separate versioned contracts; they are not additional modes of this
profile. Existing required fields do not become optional, and this amendment adds no
new supported input, output, status, or command.

## 4. Version 1 Experimental Profile

Version 1 supports exactly one narrow profile:

- `capability_profile=read_only_contextual_advisory.v1`;
- one active event with a resolvable `local_instant` start;
- optionally one selected actionable occurrence of a recurring event;
- one canonical primary location suitable for an approved information lookup;
- one target-relative notification template before the event, explicitly referencing
  one immutable advisory definition;
- one plain-language objective supplied by the user or operator;
- an allowlisted set of read-only tools;
- bounded model calls, tool calls, elapsed runtime, and usefulness deadline;
- terminal outcomes `advisory`, `no_action`, and `request_clarification`;
- a single notification delivery path selecting accepted enrichment, ordinary fallback,
  or explicitly permitted silence; and
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
silently weakening the experimental profile. Rejection of activation authoring does
not itself cancel an existing ordinary reminder.

### 4.1 Notification-template activation

The notification template owns timing and optionally references a separate immutable,
versioned advisory definition. The definition owns the bounded objective, context scope,
requested capability profile, budgets, allowed outcomes, usefulness deadline rules,
and explicit silence permission. A template does not contain executable agent logic,
credentials, a provider-specific plan, or an independent advisory schedule. A template
without an advisory reference retains its ordinary reminder behavior.

Applying a profile MUST snapshot the template, advisory-definition revision, fallback
behavior, and silence permission into the item-bound policy. Later edits to reusable
definitions or profiles MUST NOT silently change that snapshot. The item-bound advisory
policy in Section 6 expresses this activation binding, not a competing schedule.

One activated notification opportunity has one logical delivery identity shared by
the accepted-advisory/clarification branch and the ordinary-reminder fallback branch.
References to derivative notification work below describe the accepted-content branch;
they do not authorize an additional notification alongside the base reminder. Advisory
work, acceptance evidence, selected content, notification work, and delivery attempts
remain separately observable facts. Other templates retain their own opportunities;
this rule does not collapse an event's independent reminders into one.

This is a draft extension, not a change to currently implemented notification/profile
request shapes or published pack contracts. Exact activation schemas and snapshot
mapping MUST be defined and audited before runtime support or compatibility is claimed.

### 4.2 Configurable investigation limits

Version 1 starts with a small, bounded investigation, not one universal budget for
every enrichment activity. Authorized operators MUST be able to configure model-call,
tool-call, elapsed-runtime, and cost ceilings, plus research timing and a firm
content-selection deadline, per immutable advisory-definition revision. Different
definitions may carry different limits within the supported capability profile.
Configurability does not permit unlimited execution, new capabilities, or extension
of the ordinary reminder's late-handling window.

Any supplied defaults MUST resolve to concrete, finite limits when the definition is
authored. Profile application snapshots those resolved limits into the item-bound
policy; subsequent configuration edits cannot silently change existing bindings,
submissions, or replay behavior. The governance authority may narrow requested limits
under Section 7.2; an operator-configured budget is not a grant to spend it, and the
agent cannot increase its limits during execution.

Research cannot hold delivery open past the bound selection cutoff. If no usable
accepted result exists by that cutoff, Section 8.1 selects the ordinary reminder when
independently eligible, subject to the existing materialization-recovery gate. Neither
the cutoff nor a longer configured runtime may override ordinary eligibility, late
handling, or a previously committed branch. Initial numeric defaults, permitted
ranges, and exact cutoff derivation remain machine-contract design work, not values
implicitly ratified by choosing a small configurable starting policy.

## 5. Role Boundaries

### 5.1 Spine: coordination and scheduling authority

Spine owns:

- the event, item version, temporal anchor, recurrence occurrence, and location facts;
- the item-bound contextual-advisory activation policy, immutable definition reference,
  and notification-owned trigger;
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
- exact notification policy/intent, template, and notification-opportunity binding;
- immutable advisory-definition identity and revision, plus profile revision when used;
- plain-language objective;
- requested capability profile;
- allowed outcome kinds;
- tool, model, runtime, and cost limits;
- usefulness deadline;
- context-scope declaration;
- derivative delivery target and rendering profile;
- ordinary-reminder fallback behavior and explicit silence permission (default false);
- status and lineage; and
- authoring command, timestamp, and normalization version.

This policy expresses requested behavior. It is not an authorization grant.
Its requested behavior is snapshot-bound; the delivery target is inherited from the
activated notification, and the agent cannot select or substitute it.

### 6.2 Advisory opportunity and work

Deterministic notification expansion supplies the exact source anchor or occurrence
and trigger instant for the bound advisory opportunity. Materialization produces
durable advisory work before any governance request or model invocation; it does not
create a second independently scheduled reminder.

The logical work binds at least:

- advisory opportunity and policy version;
- activated notification opportunity, template, advisory-definition revision, and
  shared logical delivery identity;
- source item, item version, anchor, and optional occurrence provenance;
- context-snapshot hash;
- eligibility instant, usefulness deadline, and expiry instant;
- bounded content-selection cutoff and the bound fallback/silence policy;
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

The context snapshot is a minimized, versioned input envelope. Its default disclosure
scope is limited to the relevant event's title, time, canonical primary location, and
the minimum identity, lifecycle, occurrence, and provenance facts needed to bind and
verify that event. Free-text details are not included by default; only explicitly
permitted relevant details may be disclosed. The supported envelope may include:

- item identity, type, title, details, and current lifecycle state;
- exact local time, UTC instant, timezone, and timezone-database version;
- selected recurrence occurrence and provenance when applicable;
- canonical primary location facts;
- explicitly permitted related-item summaries; and
- exact snapshot time and content hash.

Unrelated events, household history, and sensitive notes MUST NOT enter the default
snapshot. Related-item summaries and additional details require explicit scoped
permission; a relationship or shared owner alone does not grant disclosure. Medical
appointments require explicit operator opt-in to external enrichment before any
event context crosses the enrichment boundary. Ordinary scheduling, an archetype
assignment, or an ordinary notification-profile binding alone is not that opt-in.
Opt-in still permits only the declared minimized context; it does not automatically
release all notes or related records. Without it, enrichment is unavailable and the
independently eligible ordinary reminder remains governed by Section 8.1.

It MUST exclude delivery credentials, unrelated personal data, hidden adapter state,
and mutable references whose resolved contents cannot later be identified. A context
scope permits disclosure; it does not grant tool or mutation authority.

Snapshot capture time is observation evidence, not a source-freshness input. Once
submitted, the exact snapshot contents and their integrity hash MUST be retained or
immutably resolvable for replay. The future hash preimage MUST explicitly exclude the
hash field itself and declare its canonicalization version; it may include the original
capture time, but a later capture time MUST NOT invalidate unchanged source facts.
A closed snapshot schema alone does not enforce this policy. Exact permission facts,
medical-sensitivity designation, field selection, redaction, and enforcement rules in
Section 15 remain required before implementation; no automatic classifier or reserved
archetype taxonomy is introduced by this privacy default.

## 7. Cross-System Envelope Family

The envelopes below are advisory-specific views. Their required event/notification
correlation must remain exact, but MUST NOT be promoted into mandatory fabricated
source facts for unrelated future native executions. Reuse native contracts through
an explicit mapping rather than a second generalized governance schema in Spine.
The mapping must keep submission, logical run, execution attempt, accepted evidence,
and notification-consumption identities distinct; notification retry or explicit
materialization recovery cannot become permission to redispatch intelligence.

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
- activated notification opportunity and advisory-definition revision identities;
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
Version 1 implements only preauthorized `allowed` and terminal `blocked`; interactive
approval is outside Version 1. A returned `approval_required` MUST stop the logical
advisory work without dispatch, model/tool invocation, or automatic retry. Spine MUST
preserve that native classification and expose a reason-coded, terminal unsupported-
approval result distinct from `blocked`. Later native approval MUST NOT silently resume
that stopped Version 1 work. Supporting such resumption requires a separately specified
approval lifecycle; this contract does not implement one.
This stops enrichment, not an independently eligible ordinary reminder. The ordinary
fallback follows Section 8.1 without treating the governance result as acceptance.

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

Spine may select accepted advisory or clarification content only from an accepted outcome whose
submission and source facts are still fresh. Governance acceptance is necessary but is
not itself proof of Spine freshness or delivery. The projected classification MUST be
verifiable against the native acceptance artifact and MUST NOT become a second
evidence lifecycle maintained by Spine.

Before consuming an accepted reference, Spine MUST verify its binding to the stored
submission, native authorization, run, evidence, and outcome; verify that the outcome
is successful and belongs to the effective allowed set; and apply its own freshness
gate. A missing, unverifiable, or contradictory binding, including an out-of-set
outcome marked accepted by the producer, MUST create no advisory-derived notification.
Spine records a reason-coded local consumption failure without changing the native
acceptance decision or inventing a second evidence-acceptance lifecycle. This failure
and its evidence references MUST be visible in operator readback.
Ordinary fallback may still be selected under Section 8.1 from its own valid reminder
policy. It MUST NOT inherit invalid advisory evidence or be labeled accepted advice.

## 8. Lifecycle

One successful advisory follows this sequence:

1. An operator activates an immutable advisory definition on a notification template,
   snapshot-bound to the exact item, notification policy, and trigger.
2. Spine deterministically expands the notification opportunity and materializes its
   bound advisory work without invoking a model.
3. The scheduler runtime selects eligible work.
4. Spine verifies source, policy, occurrence, deadline, and context freshness.
5. The submission is recorded before it crosses the governance boundary.
6. The governance authority binds the submission to its native governed intent and
   returns a replayable decision reference.
7. If allowed, it creates native dispatch authorization and dispatches one bounded
   invocation to the agent runtime only after the current Spine freshness recheck
   in Section 9 succeeds; the check before submission is not sufficient.
8. The runtime may call only granted read-only tools and submits one terminal result as
   produced evidence.
9. The governance authority accepts or rejects that evidence through its native
   lifecycle and returns a verifiable `acceptance_reference`.
10. Spine rechecks source and deadline freshness.
11. Spine atomically selects at most one delivery branch under Section 8.1. Accepted
    `advisory` or `request_clarification` content binds the notification work to the
    accepted outcome, never to a second competing delivery identity. Both kinds use
    the advisory policy's derivative delivery target and rendering profile, with the
    same freshness and attempt gates. Clarification
    content is the accepted question rather than the advisory headline/body/findings;
    it cannot select a new recipient or bypass acceptance. `no_action` creates no
    advisory content; it selects ordinary fallback unless silence is explicitly allowed.
12. The existing notification processor separately attempts delivery and records the
    result in `side_effect_attempts`.

Authoring, opportunity expansion, advisory-work materialization, governance decision,
agent execution, outcome acceptance, derivative-work materialization, delivery
attempt, and delivery outcome remain separately observable facts.

### 8.1 Content selection and ordinary fallback

Spine MUST resolve one content-selection decision for the activated notification
opportunity. Selection is conditional on current ordinary reminder eligibility;
neither accepted advice nor fallback can override source freshness, cancellation,
route validity, late handling, or runtime safety gates.

| Enrichment result before the bounded selection cutoff | Notification behavior |
|---|---|
| Accepted, fresh `advisory` | Select accepted advisory content. |
| Accepted, fresh `request_clarification` | Select the accepted question through the same policy-bound delivery target/profile. |
| Accepted, fresh `no_action`, silence not explicitly allowed | Select the ordinary reminder. |
| Accepted, fresh `no_action`, silence explicitly allowed in the bound policy and compatible with the accepted grant | Record intentional suppression; authorize no delivery. |
| Denial, unsupported approval, timeout, unavailable runtime/tool, invalid/rejected evidence, stale enrichment, or no usable result by cutoff | Select the ordinary reminder if it remains eligible. |
| Ordinary reminder no longer eligible | Do not deliver either branch; preserve the reasons and ordinary reconciliation behavior. |

Fallback uses the existing deterministic ordinary-reminder renderer and attempt path.
It does not require governance acceptance of an advisory, invoke an LLM, copy rejected
content, or convert an enrichment failure into successful `no_action`. Lack of explicit
silence permission means false. Permission alone cannot suppress a reminder: suppression
requires a valid accepted `no_action` before content selection is committed.

Content selection MUST be persisted and concurrency-safe before any delivery attempt
starts. Only the selected branch may authorize work for the shared delivery identity;
materialization MUST reuse existing identities and cannot leave two competing eligible
work rows. Committed fallback or suppression cannot be replaced by late enrichment.
Selected accepted content MUST pass advisory-freshness checks again at attempt start.
If that content becomes unusable before any delivery attempt has started, Spine MUST
select ordinary fallback on the same logical delivery identity when the ordinary
reminder is still eligible. This is a one-way, reason-coded change from accepted content
to fallback, not permission to create another reminder or retry failed materialization.
It MUST be serialized against attempt start and preserve the earlier selection evidence.
If notification materialization previously failed, the explicit recovery gate in
Section 8.2 still applies before any work is made deliverable.

Once any delivery attempt starts, the selected branch is frozen: neither late enrichment
nor later staleness can authorize an alternate-branch send, including after a failed or
uncertain attempt. Late evidence remains auditable but cannot reverse suppression,
reopen completed work, or create a follow-up advisory notification. Lost responses,
retries, and concurrent fallback/outcome processing MUST resolve the persisted branch
and existing attempt evidence.

This prevents a second notification caused by competing branches; it does not claim
exactly-once external transport delivery. Ordinary delivery retries and uncertain-send
handling remain governed by the existing attempt ledger.

Activation timing MUST leave a bounded opportunity for research near delivery and a
deterministic selection cutoff. No fallback may be sent before the original reminder
is eligible or after its late-handling window closes. Enrichment MUST NOT wait
indefinitely or extend that window. Exact timing fields, cutoff derivation, tie rules,
storage transaction boundaries, and race fixtures remain required machine-contract
work in Section 15; none may permit an alternate branch after delivery attempt start.

### 8.2 Materialization failure and explicit recovery

If derivative notification validation or persistence fails after governance acceptance,
Spine MUST retain the acceptance reference and a reason-coded local materialization
failure, with no partially committed derivative intent/work bundle and no delivery
attempt or delivery claim caused by that failed materialization. Reconciliation MUST
first distinguish an absent bundle from an already committed bundle, returning the
existing identities in the latter case. Neither case authorizes rerunning intelligence.
Version 1 MUST NOT automatically retry failed notification materialization for a
committed selection. Recovery requires an explicit authorized operator command and
reuses the same selected content and logical advisory work, retaining the accepted
outcome when the selected branch used it; it MUST NOT rerun the LLM/tools, request
fresh dispatch, or
create a new advisory opportunity to evade idempotency. Before creating missing work,
recovery MUST repeat current source and applicable deadline/late-handling checks and,
for accepted content, the acceptance-consumption and advisory-freshness checks. If
accepted content has become unusable and no attempt has started, the explicit recovery
operation may select only independently eligible ordinary fallback under Section 8.1;
it may not dispatch new research or revive stale advisory content.
Recovery cannot extend a deadline or override stale evidence.
If derivative work already exists, recovery returns its existing identities rather
than creating or resending a notification. Delivery retries remain governed by the
ordinary notification work/attempt lifecycle, not this recovery path.

Enrichment failure selecting ordinary fallback is a normal first content-selection
path, not a materialization retry. Conversely, failure to persist notification work
after selecting accepted content MUST NOT trigger an automatic fallback switch.
If even the selection/transaction outcome is uncertain, reconcile durable evidence
before recovery; uncertainty does not authorize a parallel fallback send. The accepted
advice remains evidence even if it is no longer eligible for recovery.

The exact recovery command, request/receipt contract, concurrency rules, and legal
transitions remain implementation prerequisites under Section 15. The lifecycle must
permit that explicit recovery while preventing scheduler-driven retries; merely naming
materialization failure terminal forever would not satisfy this decision.
Failure to materialize selected fallback likewise requires explicit operator recovery
and reason-coded readback; no advisory acceptance reference is fabricated for fallback.

## 9. Freshness, Cancellation, and Time

The context snapshot is fresh only while all bound source facts remain current and the
usefulness deadline has not passed. At minimum, freshness compares:

- item identity and current version;
- item lifecycle state;
- advisory policy identity and active status;
- notification policy, template snapshot, advisory-definition revision, and committed
  selection when present;
- temporal-anchor identity and resolved instant;
- recurrence revision, occurrence selector/key, and active provenance when applicable;
- canonical location version when location entered the snapshot; and
- context-snapshot hash and protocol version.

The hash comparison verifies the persisted snapshot against its stored submission,
not against a newly constructed snapshot with a later observation time. Freshness
also compares current values of all bound source facts, including versions of any
disclosed related-item facts. A change in capture time alone is not staleness; a
changed bound source fact cannot be excused by reusing the stored integrity hash.

If the initial freshness check fails before submission is recorded or sent, Spine
cancels or supersedes the advisory work with a reason-coded stale classification and
MUST NOT create or send that submission.

If the dispatch freshness recheck fails after submission persistence or transmission
but before execution starts, Spine records the stale classification and cancels or
supersedes the advisory work. The immutable submission and any native references MUST
remain auditable; the native dispatch path MUST prevent execution on that stale
submission. It MUST NOT rewrite the snapshot or erase the submission to simulate
non-submission. Replay resolves the same submission and recorded stale/dispatch-blocked
disposition (or the pending native disposition if the handoff is incomplete); it MUST
NOT launch execution, refresh the snapshot, or acquire a new run through replay.

If source truth changes during execution, the run and its evidence remain auditable,
but Spine refuses consumption/materialization with a reason-coded stale classification.
This local refusal MUST NOT change governance's native evidence-acceptance decision.
If source truth changes after derivative work is created, ordinary notification
reconciliation and attempt-start freshness apply.

No component may claim that an in-flight model call was undone. Already completed tool
or model attempts remain historical evidence, while stale results lose authority to
produce new delivery work.

The dispatch gate applies even if a submission has already been persisted or sent.
The native dispatch path MUST obtain a current Spine freshness result before starting
execution; an earlier submission check alone is insufficient. If execution has already
started when a change is detected, the historical run remains evidence and the
outcome/derivative freshness gates prevent stale materialization. The exact native
handoff and race-handling fixtures remain prerequisites under Section 15.

Stale enrichment does not itself make the ordinary reminder stale. Fallback MUST be
evaluated independently against the ordinary reminder's current canonical source and
late-handling rules. It cannot resurrect an obsolete item version or cancelled
notification opportunity; ordinary reconciliation handles replacement work.

## 10. Idempotency and Attempt Accounting

- One source opportunity and policy version produce one logical advisory work identity.
- Repeated scheduler discovery returns the existing work.
- Repeated submission uses the same submission identity and byte-equivalent request.
- Repeated governance dispatch resolves the same logical run and MUST NOT create a
  second concurrently authoritative run.
- Tool and model executions are attempts of that run and require correlation and
  replay evidence; retries do not create a new source opportunity.
- One accepted outcome produces at most one derivative notification intent/work bundle.
- Accepted content and fallback compete for the same notification opportunity and
  logical delivery identity, not separate idempotency namespaces.
- Repeated outcome reconciliation returns the existing derivative identities.
- Delivery retries remain attempts for the same notification work and use Spine's
  existing `side_effect_attempts` rules.

Whether model and read-only tool attempts are mirrored in Spine's generic attempt
ledger or referenced from the governance authority remains an open persistence
decision. There MUST NOT be two competing authorities for the same attempt fact.

## 11. Failure and Outcome Semantics

The first contract family must distinguish at least:

- source stale before submission;
- source stale after submission but before dispatch, with the preserved submission
  and native dispatch-blocking disposition separately observable;
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
be reported as delivered until a delivery attempt succeeds. Version 1 preserves the
ordinary-reminder fallback under Section 8.1. Delivered fallback is an ordinary reminder
delivery, not successful advisory generation. A successful `no_action` normally falls
back too; only explicitly authorized intentional silence suppresses the base reminder.

## 12. Readback

A canonical operator read must expose, without raw SQL:

- advisory policy and trigger;
- notification template/snapshot and immutable advisory-definition revision;
- source item/version/occurrence and snapshot hash;
- advisory work lifecycle;
- submission identity;
- governance decision and `acceptance_reference` facts with reason codes;
- agent run status, outcome kind, usage summary, and evidence references;
- freshness classification;
- selected content branch or intentional suppression, selection time and reason,
  fallback eligibility, and any late outcome excluded from delivery;
- derivative notification policy/work identity when present; and
- delivery attempt/outcome separately.

Readback MUST also expose local acceptance-consumption failures and derivative
materialization failures, retaining any native acceptance reference. Every failed or
terminal advisory-work path MUST expose its latest relevant reason, transition time,
Spine persistence actor, causal evidence-producing role, and evidence/replay references
when present. Absence of a submission, run, or attempt MUST be represented as absence,
not fabricated success or execution evidence.

Readback MUST distinguish unsupported approval with no Version 1 resumption path from
materialization failure requiring explicit operator recovery. Any recovery request and
result MUST remain separately auditable and correlated to the original advisory work,
persisted selection, accepted outcome when present, and existing or newly materialized
notification work when present.

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
- accepted advisory content and ordinary fallback cannot create competing notification
  work for the same opportunity;
- `no_action` produces ordinary fallback by default; only accepted, fresh `no_action`
  with explicit silence permission authorizes suppression;
- `request_clarification` creates at most one;
- a source move before execution stales or cancels the work;
- a source move during execution prevents derivative materialization;
- a forbidden write, contact, or send capability is denied;
- timeout and failure remain evidence and produce no advisory content, while selecting
  ordinary fallback only if the base reminder remains eligible;
- the agent runtime cannot invoke the delivery adapter directly;
- accepted outcomes replay without rerunning the model or tools; and
- delivery remains separately attempt-gated.

Passing these tests proves protocol composition and safety behavior. It does not prove
that autonomous advice is useful.

The machine-contract fixture set MUST additionally prove:

- default snapshots exclude unpermitted details, unrelated events, household history,
  and sensitive notes; medical enrichment without explicit opt-in discloses no event
  context externally and does not cancel an independently eligible ordinary reminder;
- distinct advisory definitions can have distinct finite budgets; resolved defaults
  and limits remain unchanged in existing bindings and replays after configuration
  edits, and neither the agent nor a longer runtime may extend the selection cutoff
  or ordinary delivery window;
- an enum-valid but disallowed outcome is rejected, including when a native reference
  incorrectly claims acceptance, without advisory-derived work or a second acceptance
  ledger; independently eligible ordinary fallback remains available;
- a widened tool/model/outcome grant, raised budget, extended expiry, or changed cost
  unit cannot authorize dispatch;
- external decision/evidence producers cannot directly mutate Spine work state;
- unchanged source facts observed at a later time retain identities and freshness,
  while changed bound item, occurrence, location, or related-item facts fail freshness;
- same-key changed submission bytes never cross the governance boundary;
- initial freshness failure records stale work without creating or sending a submission;
- a source change after submission persistence or transmission but before execution
  blocks dispatch, preserves immutable submission/native references, and replays without
  model/tool execution, snapshot replacement or a new run, including an incomplete handoff;
- a source change during execution causes a reason-coded local consumption refusal
  without rewriting native evidence or its governance acceptance decision;
- materialization failure preserves acceptance evidence without partial derivative work,
  and retry/replay after an already committed bundle returns its existing identities;
- accepted clarification uses the same policy-bound target/profile and attempt gate as
  an advisory, with the accepted question as content and no recipient override;
- unsupported approval stops without dispatch or automatic retry, including upon
  repeated scheduler discovery or a later native approval observation;
- materialization failure is not automatically retried; explicit recovery rechecks
  acceptance/freshness, never reruns the model/tools, and cannot extend the deadline;
- explicit recovery cannot duplicate a committed notification bundle or resend work,
  including after lost responses or concurrent recovery requests;
- fallback and a concurrent or late accepted outcome cannot create two selected
  deliverable branches or deliveries; a committed fallback choice never becomes late advice;
- accepted content becoming stale before first attempt falls back on the same delivery
  identity when independently eligible, while any started/failed/uncertain attempt
  prevents alternate-branch sending; failed materialization still requires explicit recovery;
- intentional silence cannot be inferred from failure, timeout, missing results, or
  silence permission alone, and late `no_action` cannot reverse committed fallback;
- fallback respects cancellation, source freshness, routes, late handling, and runtime
  safety, and does not send before ordinary eligibility or extend its delivery window;
- materialization failure after accepted-content selection does not automatically
  switch to fallback or rerun intelligence;
- other templates retain independent reminders and templates without activation retain
  ordinary behavior;
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

Decision 0005 adds a preservation constraint on how these open details are resolved;
it does not close them. Before finalizing this profile's machine contracts, record
the advisory-specific versus native field mapping, run/attempt/retry and budget
ownership, and source-freshness handoff. Keep every required advisory binding and
the Section 8 selection/recovery rules intact. Exact interfaces for future triggers,
scope-wide work, new result consumers, and durable workflows remain outside this slice;
they are not prerequisites to implement the first bounded advisory.

The following decisions remain intentionally open before machine contracts and
implementation; selective clarification does not close them by implication:

1. exact schemas and authoring/application mapping for immutable advisory definitions,
   notification-template activation references, and item-bound policy snapshots;
2. whether advisory execution uses a new `work_kind` or a candidate-action artifact;
3. which component is authoritative for model/tool attempt records and their retention;
4. the exact adapter mapping from Spine submission/binding/`acceptance_reference` views
   to the selected governance authority's native intent, dispatch, receipt, and evidence
   contracts;
5. the exact context-permission, medical-sensitivity designation, field-selection,
   redaction, and enforcement contracts implementing the Section 6.3 privacy defaults;
6. initial numeric budgets, supported configuration ranges, accounting units, and
   usefulness-deadline defaults implementing the per-definition limits in Section 4.2;
7. the exact commands and readback projection used by operators;
8. the explicit derivative-materialization recovery command, request/receipt contract,
   concurrency rules, and legal transitions implementing Section 8;
9. exact identity preimages, first-creation and concurrent lookup rules, snapshot hash
   preimages, encodings, and projection-to-native verification rules; and
10. the dispatch freshness handoff and race-handling contract with the native authority;
11. bounded research timing, selection cutoff derivation and tie rules, and the
    transaction/uniqueness rules that serialize fallback, accepted content, suppression,
    materialization recovery, and delivery attempts for one notification identity; and
12. exact immutable silence-permission fields, content-selection readback, and accepted-
    content rendering contracts that remain separate from the ordinary renderer.

The operator ratified three Version 1 policy decisions on 2026-09-12: clarification
uses the advisory's derivative delivery target/profile; unsupported approval stops
without dispatch or automatic retry; and materialization failure requires explicit
operator recovery using accepted advice rather than rerunning intelligence. These
decisions are normative in Sections 7.2 and 8. They settle product behavior, not the
remaining machine contracts or implementation readiness. Pending technical decisions
do not grant additional authority to dispatch, deliver, or retry by inference.

The operator also ratified notification-template activation and ordinary-reminder
fallback on 2026-09-12. This replaces the standalone-trigger/no-fallback experimental
posture: enrichment failure preserves the base reminder when independently eligible;
accepted `no_action` suppresses it only with explicit permission; all branches share
one logical delivery identity. The selected product direction is no longer an open
policy-family choice, but its exact schemas and runtime integration remain open above.

On 2026-09-13 the operator ratified minimized event-only disclosure by default, explicit
permission for additional details, no default unrelated-event/household-history/
sensitive-note disclosure, and explicit opt-in for medical-appointment enrichment.
The operator also ratified small bounded investigations with configurable limits per
enrichment activity and a firm deadline that preserves independently eligible ordinary
fallback. These product policies are captured in Sections 4.2 and 6.3; they do not
select numeric budgets, create a sensitivity taxonomy, or close the remaining machine
contracts and enforcement details.

The primary-location prerequisite is satisfied by the implemented and audited
`spine.schedule-primary-location.v1` family; it is no longer an open advisory decision.

Until these decisions converge, there is no schema version, compatibility declaration,
or implementation commitment for contextual advisories.
