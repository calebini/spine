# Scheduled Agent Autonomy

Status: Design exploration; non-normative; not an implementation commitment  
Last updated: 2026-09-04
Scope: How scheduled Spine truth might initiate bounded agent reasoning, tool use, useful advisories, and later governed actions

## Purpose

Spine can already express when an event or task occurs, when a notification opportunity becomes eligible, which durable work exists, and whether delivery was attempted. The open design question is how a scheduled trigger can enlist an LLM-backed agent to discover and produce useful information that was not fully prescribed when the schedule was authored.

The motivating example is a reminder for a golf trip this weekend. Two days before the trip, an agent notices that weather is relevant, checks a forecast, and sends an advisory such as:

> Hot and sunny conditions are expected. Pack shorts, sunscreen, and extra water.

The desired behavior is more autonomous than a hard-coded weather workflow. The user may want the agent to inspect the event context and decide that weather, traffic, course rules, an early departure, missing equipment, or nothing at all is the most useful response.

This note preserves the broader design discussion while it remains fluid. `specs/contextual-advisories.md` now owns the narrower normative draft for the first cross-system experiment. This note does not define accepted schema, command, migration, runtime, approval, or compatibility behavior beyond that draft.

## Central Distinction: Discretion Versus Authority

The working principle is:

> An agent may autonomously decide what to investigate, but it may not autonomously expand what it is authorized to do.

A durable policy need not prescribe the agent's exact plan, tool sequence, queries, or prose. It does need to bound the agent's authority. The explicit facts may include:

- the objective or responsibility delegated to the agent;
- the scheduled trigger and usefulness deadline;
- the context the agent may inspect;
- the capability families and tools it may use;
- read-only, proposal, or external-write authority;
- time, tool-call, token, and cost budgets;
- whether contacting another person is allowed;
- which outcomes require governance-authority approval;
- when the agent should notify, ask for clarification, or remain silent;
- the required result/evidence shape; and
- fallback behavior when research, inference, or delivery fails.

Within that envelope, the agent can construct a plan at runtime and decide what is materially useful.

## Working Vocabulary

The following terms are placeholders for discussion, not accepted ontology names.

### Agent mandate

A durable authority envelope describing an objective, accessible context, capability profile, budgets, approval rules, usefulness threshold, and allowed outcomes. A mandate authorizes a class of agent planning rather than one pre-authored tool sequence.

### Fixed recipe

A narrow form of mandate that prescribes a known operation, such as fetching weather and producing a packing advisory. Fixed recipes are predictable and useful for conformance tests, but they should not define the ceiling of agent autonomy.

### Agent run

One runtime invocation caused by an accepted temporal trigger or planning sweep. The run records the exact source facts, mandate version, context snapshot, chosen plan, approval evidence, tool/model attempts, result, and terminal outcome.

### Action evidence

Structured findings, sources, tool results, hashes, timestamps, confidence, and rationale produced during a run. Evidence is not automatically canonical item truth.

### Outcome

The terminal product of a run. Candidate outcomes include an advisory, no action, clarification request, candidate action, or downstream notification work.

## Autonomy Spectrum

The design should support more than one level of autonomy without confusing their authority.

### Level 1: Fixed recipe

Example: "Check the forecast two days before this trip and generate a packing advisory."

The operation and expected output are known in advance. This is the easiest form to validate deterministically around fake tools and model responses.

### Level 2: Bounded research and advice

Example: "Two days before this event, help me prepare. Research anything materially useful using approved read-only tools."

The agent chooses its own investigation plan. Weather is one possible discovery, not a required step. The allowed result may be an advisory, no action, or a clarification request.

This level currently appears closest to the intended product behavior.

### Level 3: Proposal authority

Example: "Prepare for this event and propose any coordination changes that would materially help."

The agent may produce candidate actions such as leaving earlier, rescheduling, contacting a participant, or adding a task. It cannot execute those proposals merely because it generated them.

### Level 4: Delegated execution authority

Example: "Prepare for this event and take approved actions within a defined budget and policy."

External writes, purchases, bookings, messages to third parties, or canonical Spine mutations cross a stronger boundary. They require explicit capability and approval policy, durable pre-write attempts, freshness checks, and auditable outcomes.

## Two Complementary Trigger Models

### Contextual reminder

A particular notification trigger delegates contextualization to an agent before final delivery. At eligibility time, the agent receives the reminder, item or occurrence snapshot, and mandate. It may enrich the eventual notification, request clarification, or decide that no message is warranted.

This model directly supports the golf-trip example.

### Notification-template activation hypothesis

For reminder-linked advisories, the current preferred design is to make the
notification template the explicit activation locus without turning that template
into an agent program. A template may eventually carry an optional immutable reference
to a versioned contextual-advisory definition and a bounded fallback posture. It must
not embed executable code, a provider-specific prompt, an unrestricted tool plan, or a
model-selected schedule.

Conceptually:

    item or recurrence occurrence
                |
    notification profile snapshot
                |
    notification template and trigger
                |
    deterministic opportunity
                |
    optional advisory request
                |
    governed external agent execution
                |
    accepted advisory or deterministic fallback
                |
    ordinary notification work and delivery attempts

This separation assigns distinct responsibilities:

- The notification template states **when** contextualization is requested, **which
  immutable advisory definition** applies, and **what fallback posture** is allowed.
- The advisory definition states the objective, context scope, allowed capabilities,
  budgets, evidence shape, usefulness deadline, and permitted outcomes. It may give an
  agent discretion to decide what is useful without prescribing weather, traffic, or
  another fixed lookup.
- Spine expands the temporal trigger deterministically, binds it to exact item,
  occurrence, profile-revision, template, advisory-definition, and destination facts,
  and retains lifecycle and provenance evidence.
- The governance authority controls capability and boundary crossing. An external
  agent runtime chooses and invokes allowed read-only tools and synthesizes the result.
- Accepted advisory prose returns through ordinary Spine notification work. The agent
  runtime does not deliver directly.

Ordinary notification templates remain valid and useful without an advisory reference.
An advisory outage, timeout, stale result, denial, or invalid result should normally
fall back to the template's deterministic reminder rather than erase it. A successful
no_action outcome may suppress derivative advisory prose only when the accepted
advisory definition explicitly permits silence; the later contract must distinguish
that intentional outcome from execution failure.

Context should be gathered close enough to delivery to satisfy declared freshness and
usefulness deadlines rather than being rendered when a distant notification
opportunity is first expanded. Recurring items create independently source-bound
advisory work per applicable occurrence. Replay must reuse accepted evidence and must
not invoke the model or tools again.

Reusable packs may eventually distribute owner-neutral advisory definitions and
notification-template activation references. Installation must snapshot or resolve
their exact immutable versions through supported contracts. The pack remains a
declarative artifact: it does not execute, contain operator item data, choose concrete
credentials, or become the advisory runtime.

This hypothesis is specific to contextual reminders. Proactive planning sweeps remain
a separate trigger model and must not be smuggled into notification-template semantics.
The exact schema, policy family, work kind, installer behavior, and compatibility
declarations remain decisions for the next normative specification pass.

### Proactive planning sweep

A scheduled agent session examines an upcoming horizon rather than one preselected reminder. For example:

> Review the next seven days and tell me anything I should know or prepare for.

The agent queries a bounded Spine agenda and selects which events or tasks merit attention. It might identify adverse weather, a passport requirement, a dependency risk, an event without a location, a long drive, or a scheduling conflict even when the individual items have no dedicated automation policy.

This model more fully realizes the idea of Spine as a planning fabric. It also introduces greater utility-ranking, noise, privacy, budget, and explanation pressure.

The two models may share mandate, run, evidence, approval, and delivery machinery.

## Candidate End-to-End Flow

The current hypothesis is:

```text
event, task, or bounded agenda horizon
                 |
        accepted temporal trigger
                 |
        durable agent mandate
                 |
       agent opportunity or work
                 |
      freshness and approval gate
                 |
            agent runtime
        /         |          \
 context read   tool calls   LLM reasoning
        \         |          /
        structured run evidence
                 |
       utility and outcome gate
          /       |         \
     no action  advisory  candidate action
                 |
      derivative notification work
                 |
    existing attempt-gated delivery path
```

Temporal expansion should remain deterministic and should not itself invoke a model or tool. A virtual opportunity alone should not authorize external action.

## Illustrative Mandate

This example demonstrates the intended degree of freedom. It is not a proposed public request schema.

```json
{
  "trigger": {
    "kind": "target_offset",
    "offset_seconds": "-172800"
  },
  "mandate": {
    "objective": "Help me prepare for this event",
    "autonomy": "research_and_advise",
    "context_scope": [
      "item",
      "occurrence",
      "location",
      "participants",
      "related_items",
      "personal_preferences"
    ],
    "capability_profile": "read_only_personal_assistant.v1",
    "notify_when": "materially_useful",
    "allowed_outcomes": [
      "advisory",
      "no_action",
      "request_clarification"
    ],
    "limits": {
      "max_tool_calls": "6",
      "max_runtime_seconds": "60"
    }
  }
}
```

The mandate does not say to check weather. At runtime, the agent might check weather, traffic, course information, relevant packing needs, or nothing. A read-only mandate cannot silently reschedule the trip, contact the course, make a purchase, or widen its own capabilities.

## Candidate Component Boundaries

These are working boundaries to validate, not accepted assignments.

### Spine

Spine may own:

- the temporal trigger and its binding to canonical item or occurrence truth;
- durable mandate identity and version references;
- eligible agent work or candidate-action pressure;
- item, occurrence, location, relationship, and lifecycle freshness checks;
- action-run coordination facts and outcome references;
- derivative-work provenance;
- command receipts, audit facts, and side-effect-attempt linkage;
- cancellation or reconciliation after source truth changes; and
- readback of trigger, run, outcome, delivery, and attempt state.

Spine should not make stochastic model output part of schedule, occurrence, or policy identity. Agent conclusions do not become canonical item truth without a separate accepted mutation.

### tickerd

tickerd continues to own daemon cadence, singleton/runtime mechanics, bounded processing, health, readiness, and reconciliation-loop execution. It should not own mandate semantics, agent reasoning, canonical results, or approval policy.

### Governance authority

The governance authority governs capability and boundary crossing. It may decide that a run is allowed, needs evidence, requires approval, or is blocked. Proposal and execution authority should not be inferred from the fact that a trigger became eligible. Public contracts name this role rather than its implementing repository or product.

### Agent runtime

The agent runtime plans, chooses tools within the accepted capability envelope, synthesizes results, and returns structured outcomes. It should not silently expand its mandate, bypass attempt accounting, or deliver directly around Spine's work pipeline.

### Memory

A separate memory component may own durable personal preferences and learned context. Spine may retain stable references or execution-time snapshots needed for replay and audit without becoming the general personal-memory authority.

### Tools and adapters

Tools provide read or write capabilities such as weather, traffic, maps, web research, calendars, messaging, or commerce. Tool and model calls that cross external boundaries need durable attempt and result evidence appropriate to their risk.

## Existing Spine Foundations

Current Spine behavior already provides useful substrate:

- deterministic local and UTC scheduling;
- recurrence and occurrence provenance;
- bounded notification opportunities;
- durable work materialization and derivative-work provenance fields;
- eligible, in-progress, retry, succeeded, failed, and cancelled work transitions;
- tickerd-backed bounded execution;
- candidate actions bound to item versions;
- freshness checks before work or candidate-action execution;
- `side_effect_attempts` as the single generic external-attempt ledger;
- delivery targets and a guarded notification processor; and
- an architectural governance-authority boundary.

Important current limitations include:

- the canonical `work_kind` currently permits only `notification_reminder`;
- candidate-action kinds do not yet include an explicit agent invocation or agent proposal vocabulary;
- notification policies describe delivery scheduling, not general agent mandates;
- no durable agent-run/result artifact is defined;
- no general agent processor binding exists in the Spine worker;
- governance-authority integration remains deferred;
- first-class locations exist in the ontology and ledger but are not fully available through the public scheduling command surface; and
- operator readback does not expose agent planning, tool, result, approval, and derivative-delivery phases.

These limitations suggest that a real implementation will probably require a schema migration and cross-component contracts. That conclusion is provisional until the model is sharpened.

## Candidate Durable Artifacts

The design may need some or all of the following. Names and table boundaries are deliberately unsettled.

### Mandate or automation-policy artifact

Possible facts include objective, context scope, capability profile, autonomy level, approval policy, budgets, usefulness threshold, output contract, downstream delivery posture, version, and status.

### Agent-action work

Possible facts include item/version, occurrence/provenance, trigger opportunity, mandate version, eligibility and expiry, input snapshot hash, approval requirement, status, and reconciliation reason.

### Agent run

Possible facts include run identity, source work, selected plan, capability decision, model/tool policy, input hash, status, timestamps, result hash/reference, failure classification, and correlation identity.

### Evidence or result artifact

Possible facts include structured result contract, source timestamps, citations or provider references, confidence, validity window, content hash, storage reference, and retention classification.

### Derivative notification work

Successful advisories may create ordinary notification work whose source is the agent-action work or run. Existing delivery targets, stale checks, idempotency, attempts, and outcomes should remain authoritative. The agent runner should not send directly.

## Preliminary Safety and Granularity Invariants

These invariants are candidates for later normative treatment:

- Schedule and trigger expansion remains deterministic and model-free.
- A trigger does not itself grant tool, mutation, contact, purchase, or send authority.
- Every agent run binds to immutable source item, occurrence, mandate, and context-snapshot facts.
- Source changes can stale, cancel, or require revalidation of unstarted runs and derivative work.
- Agent-created plans and prose are runtime evidence, not hidden canonical coordination truth.
- Tool selection may be autonomous only within an accepted capability profile.
- Tool output and external content are untrusted data, not instructions that may expand authority.
- Model and tool attempts are correlated, bounded, and durably evidenced.
- A run may return `no_action`; useful autonomy must not imply mandatory notification.
- External writes and canonical Spine mutations require separately governed candidate actions or commands.
- Generated advisories enter the normal notification work and delivery path rather than bypassing it.
- Replay and retry cannot duplicate agent runs, external calls, candidate actions, or notification delivery.
- Model nondeterminism must not participate in schedule, occurrence, mandate, opportunity, or work identity.
- Operators can distinguish authored, triggered, awaiting approval, running, succeeded/failed, notification-materialized, delivery-attempted, and delivered states.

## Candidate First Vertical Slice

A useful first slice could prove general bounded autonomy through one narrow scenario without hard-coding weather as the architecture:

- one `contextual_reminder` or `scheduled_agent_run` trigger;
- events with local-instant starts;
- a required canonical primary location;
- a general `research_and_advise` mandate;
- a bounded read-only capability profile;
- runtime tool choice by the agent;
- structured `advisory`, `no_action`, and `request_clarification` outcomes;
- one derivative notification through the existing delivery path;
- fake weather, research, model, approval, and delivery adapters in tests;
- freshness, cancellation, replay, retry, timeout, and no-send coverage; and
- the golf-weather behavior as a conformance scenario rather than a hard-coded recipe.

The slice would exclude arbitrary tool installation, purchases, bookings, third-party contact, autonomous item mutation, multi-agent delegation, open-ended loops, and unrestricted external writes.

## Questions and Decision Pressure

The following discussion should happen before a normative specification or implementation plan is accepted.

### Trigger and discovery

- Is agent contextualization explicitly attached to individual reminders, inherited from an item profile, selected by a user-wide preference, or all three?
- Can an agent create an ephemeral run for a reminder that did not explicitly opt in?
- Does a proactive sweep use a recurring Spine item, a dedicated planning policy, or another component's schedule?
- How are duplicate discoveries suppressed across a contextual reminder and a planning sweep?

### Usefulness and silence

- Who defines `materially_useful`, and how is that decision explained?
- Should an agent prefer silence when confidence, novelty, or actionability is low?
- Does a suppressed notification remain visible as a `no_action` run?
- What feedback facts capture useful, noisy, late, incorrect, or unwanted advice?

### Context and memory

- Which item, location, relationship, participant, preference, and prior-run facts may enter the context snapshot?
- Which component owns personal preferences and learned behavior?
- How are sensitive facts minimized, retained, and redacted?
- Must every context source be pinned or hash-referenced for later explanation?

### Capabilities and approval

- What is the smallest useful capability-profile vocabulary?
- Are read-only public-data calls preauthorized, or does every external call pass the governance authority?
- Does model inference itself require a budget or approval decision distinct from tool calls?
- How does an agent promote an advisory into a proposed canonical or external action?
- Which decision evidence must Spine persist versus reference?

### Execution and attempts

- Is one candidate action also the execution run, or are pressure, approval, run, and attempts separate artifacts?
- Are weather retrieval, web research, LLM inference, and final delivery separate `side_effect_attempts`?
- Where do structured tool results and generated advisory content live?
- How are retries handled when some tool calls succeeded but synthesis or delivery failed?
- What is the idempotency boundary for a runtime-selected plan?

### Timing and fallback

- Does agent research begin exactly when the notification would have fired, or earlier so a delivery deadline can be met?
- What happens if research exceeds its deadline?
- Is there a static fallback reminder when the agent run fails or returns no result?
- How is forecast or traffic freshness represented when evidence can expire before delivery?

### Location and recurrence

- Is a canonical location mandatory for location-dependent mandates, or may an agent ask for clarification?
- How do moved, excluded, cancelled, or overridden recurrence occurrences affect an in-flight run?
- Can one result apply to several occurrences, or must every occurrence have independent evidence?

### Operator surface

- Should mandates be authored through lower-level commands before joining `schedule.create` and `schedule.update`?
- What should `schedule.show` and cross-item operational readback expose?
- How does an operator cancel, retry, approve, reject, or inspect a run without raw SQL?
- Which compact receipt facts are required for chat-based operators?

## Promotion Path

This note should remain exploratory while major questions are open. A reasonable promotion sequence is:

1. Continue discussion here and record alternatives, examples, and rejected approaches.
2. Decide component ownership, authority boundaries, trigger models, and the first autonomy level.
3. Write an accepted architecture decision for the mandate/run/evidence/outcome model.
4. Draft normative ontology, command, lifecycle, and safety specifications.
5. Define schema migration requirements and machine-readable contracts.
6. Add fake-tool, fake-model, fake-approval, and fake-delivery fixtures and computed evidence.
7. Audit the contract family for buildability and cross-component boundary integrity.
8. Implement one bounded vertical slice only after the contracts converge.

## Non-Decisions

Nothing in this note currently commits Spine to:

- the term `agent mandate` or any example field name;
- embedding mandates inside notification policies;
- creating a specific table or schema version;
- a particular model provider or agent framework;
- a specific weather, web, maps, memory, messaging, or approval adapter;
- allowing LLMs to mutate canonical truth;
- running an LLM for every reminder;
- treating model output as deterministic;
- adopting proactive planning sweeps;
- any particular approval or preauthorization policy; or
- the illustrative first vertical slice.

These are candidate directions preserved for further discussion.
