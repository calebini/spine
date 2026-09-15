# Cross-System Execution Architecture

Architecture ID: `cortext.cross-system-execution`  
Document version: `0.1.0-draft.1`  
Status: Proposed shared architecture; not ratified, implemented, or adopted by other components  
Created: 2026-09-15  
Canonical source repository: `https://github.com/calebini/spine`  
Canonical source path: `specs/cross-system-execution.md`

## 1. Purpose and authority

This is the shared design reference for coordination, governed execution, and result
consumption. It is hosted in Spine for convenience; hosting grants Spine no authority
over another component's native policy, execution state, or evidence lifecycle.
After explicit adoption, it governs the participating components' integration
boundaries, not their internal implementation or all uses of those components.

The architecture separates five questions:

1. Why is work requested, and what source facts does it concern?
2. Is the requested execution permitted, under which constraints?
3. How is the authorized job performed and its activity recorded?
4. Does the produced evidence satisfy the authorized result contract?
5. Is a particular use of accepted evidence still permitted and relevant?

This draft consolidates the boundaries in [Decision 0003](decisions/0003-role-based-governance-boundary.md),
[Decision 0005](decisions/0005-profile-scoped-advisory-execution.md), and the
[contextual-advisory profile](contextual-advisories.md). It does not supersede their
requirements, change their status, or advertise the profile as implemented.
Normative terms below describe the proposed agreement, conditional on adoption.

Authority is divided by subject:

- This document owns shared role boundaries and integration invariants.
- Component specifications own native artifacts, state transitions and interfaces.
- A versioned use-case profile owns its supported inputs, outcomes and consumption rules.
- Concrete cross-system contracts own field mappings, protocol versions and verification.

A profile may narrow shared permissions; it MUST NOT weaken a shared invariant.
Existing component/profile requirements remain binding. If a proposed mapping conflicts
with them, the affected integration MUST remain unsupported until the conflict is
explicitly resolved in the owning specifications. A reference here does not silently
override a requirement, accept a draft, or force an upgrade in another repository.

## 2. Versioning and downstream references

The architecture ID is stable across revisions and independent of its hosting path.
The document version is separate from package versions, use-case profile versions,
machine protocols, schema versions and runtime capability declarations.

An exact design reference records:

| Fact | Meaning |
| --- | --- |
| Architecture ID | `cortext.cross-system-execution` |
| Document version | Exact value, initially `0.1.0-draft.1`; no `latest` or version range |
| Source locator | Repository, repository-relative path and full Git commit containing the cited document |
| Relationship | Design reference or explicitly adopted architecture; neither asserts runtime conformance |
| Coverage | Participating role(s), profile(s), and any unresolved integration decisions |

These are documentation reference facts, not a new wire schema or registry. A local
relative link is a navigation convenience, not a replacement for the committed source
locator. Before the first commit, consumers may inspect this draft but cannot claim an
exact checkpoint reference. Record the containing commit in downstream documents after
it exists; the source need not embed its own commit or a consumer's hash.

Once a version is checkpointed for cross-repository reference, its content MUST NOT
be revised under that same version. Further draft checkpoints increment the draft
revision (`0.1.0-draft.2`, etc.); earlier content remains retrievable through Git.
Working edits before the first checkpoint are not separately published revisions.
The first accepted baseline is `1.0.0`, after explicit review and adoption decisions.
For accepted versions: corrections without changed obligations increment patch;
compatible additions increment minor; changed authority, weakened/strengthened existing
obligations or other incompatible interpretation changes increment major. None of
these increments automatically updates consumers.

Each participating project records adoption in its own authoritative design or
compatibility document. Updating this source does not imply downstream adoption;
record the new exact reference only after reviewing the change and any affected mappings.
Different document revisions are not automatically runtime-incompatible, but their
shared boundaries must be reconciled before claiming integration support.

There is one maintained source, not independently editable copies in each project.
If an offline copy is necessary, it is a labelled, unmodified copy of an exact source
revision, not a competing authority. Relocation preserves the architecture ID and
historical references and provides an explicit successor locator.

Follow the [spec versioning policy](SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md): no
new freeze manifest, reciprocal hash gates, runtime checks, or package declarations
are introduced by this draft. A later release-critical machine contract must carry
its own version, validation, tests and implemented-capability declaration.

## 3. Roles and responsibilities

Public integration terms identify roles, not project brands. An explicit deployment
binding selects implementations and trust relationships; discovery or matching a
product name does not establish trust.

| Role | Owns | Does not own |
| --- | --- | --- |
| Coordination authority | Canonical source facts, activation, permitted context disclosure, source freshness, and coordination-side consumption | Research planning, governance decisions, native evidence acceptance |
| `governance_authority` | Policy decisions, effective grants, dispatch authorization, approval validity, acceptance/rejection of native evidence | Canonical schedule changes, research synthesis, notification delivery |
| `agent_runtime` | Authorized job execution, model/tool interaction, live limit enforcement, run and call records, produced outcomes | Self-granted authority, accepting its own evidence, direct advisory delivery or ledger mutation |
| `tool_provider` | A declared capability's concrete operation and returned evidence | Permission to perform additional operations or judge overall job success |
| `scheduler_runtime` | Cadence, process/singleton mechanics and processor invocation | Business eligibility, policy truth, evidence acceptance or result-consumption permission |
| Result consumer / effect executor | The separately authorized use or effect, with its own validation and attempt boundary | Treating accepted evidence as an unrestricted command |

Informative component mapping: Spine serves the coordination role and advisory
consumption; Threshold is the governance candidate (the inspected checkout is still
named `foreman`); Impetus is the planned execution component; Tickerd supplies runtime
cadence where needed. This mapping is not a deployed compatibility claim. Product
names MUST NOT be inserted into role-neutral wire fields, enums or identity preimages
merely to identify the current implementation. Native artifact identities remain native.

Impetus is a distinct logical component. That does not require a daemon, network
service, workflow engine or database per role. A bounded subprocess/package is an
initial deployment option, not a selected runtime. Shared deployment MUST NOT erase
the authority or credential boundaries above.

## 4. End-to-end interaction

```text
Coordination authority
  -- immutable request + permitted source snapshot --> Governance authority
Governance authority
  -- authorized invocation + effective limits -------> Execution runtime
Execution runtime <---- granted operations/evidence ---> Tool providers
Execution runtime
  -- produced outcome + execution evidence ----------> Governance authority
Governance authority
  -- verifiable acceptance/rejection references -----> Result consumer
Result consumer
  -- independent freshness/permission/attempt checks -> Authorized use or effect
```

This is an authority/evidence flow, not a prescribed transport or queue topology.
Polling, responses or callbacks must implement the same correlation and permission
rules. A callback reference supplies routing/correlation, not ambient authorization.

The producer records or resolves an immutable request before submission. Governance
binds it to native intent/decision artifacts and may allow, narrow, deny or require
approval according to the selected profile. Execution starts only with a verifiable,
applicable authorization. An intake success or eligible schedule is not that authorization.

Execution returns produced evidence, not accepted truth. Governance checks it against
the authorized contract, then the consumer independently checks whether the specific
use is permitted and current. Where no new result is usable, the profile determines
the outcome; ordinary-reminder fallback is an advisory rule, not a universal execution rule.

## 5. Capabilities and adapter extensibility

Permission attaches to a versioned capability and its constrained operation, not to
a transport. “Retrieve a forecast for these coordinates and dates” is a capability;
“may use HTTP” is not a sufficient grant.

The execution component separates enforced execution controls from the replaceable
model/agent backend and capability adapters. It may support additional backend or
adapter implementations without exposing them to every job.

Before activation, a capability binding MUST specify its identity/version, operation
and input/output contract, allowed resource scope, effect characteristics, credential
scope, timeout/accounting behavior, and evidence expectations. The exact descriptor
schema belongs to the execution/native integration contracts, not this architecture.
The effective grant references admitted capabilities. Missing or unsupported bindings
MUST prevent that operation; the runtime MUST NOT substitute a broader tool or transport.

Adapters may eventually use MCP, HTTP APIs, SDK functions, bounded executables,
browser automation, or other explicitly specified interfaces. These are extension
possibilities, not enabled capabilities. Supporting MCP does not authorize every
discovered tool; allowing a CLI does not authorize arbitrary shell commands; supporting
HTTP does not authorize arbitrary destinations. Nested delegation and additional
execution surfaces require their own supported contracts.

The backend may choose useful actions and sequence research within the grant. Every
model/tool call crosses enforced controls outside model-authored text. Retrieved
content, prompts, tool descriptions and model output cannot widen authority. Credentials
are supplied through configured execution boundaries, not entrusted to generated plans.
The design must state the actual isolation/enforcement mechanism before claiming
containment; instructions alone are not an enforcement boundary.

## 6. Policy, budgets, validation and evidence

The requester supplies desired scope and finite limits. Governance owns the effective
grant and may narrow, not expand, those requests. The runtime checks permission and
remaining limits before calls and enforces deadlines during execution where supported.
It records actual usage, including violations; it MUST NOT discard or clamp observed
usage to make a run appear compliant. Post-execution rejection alone is not budget enforcement.

Each capability's accounting contract must define reservations or other pre-call bounds,
unknown/delayed usage, concurrency, cancellation, provider/SDK retries and exhaustion.
If the required hard bound cannot be enforced, the capability is unsupported under
that grant. Read-only business behavior can still disclose information or incur cost.

Validation has three separate owners:

- The runtime validates inputs and produces structurally valid outcomes, call records
  and usage evidence. Provider failures remain failures, not fabricated success.
- Governance independently checks authorization binding, admissible outcome types,
  usage/authority constraints and native evidence integrity before accepting evidence.
  It may reuse validators but MUST NOT trust the producer's “validated” claim as acceptance.
- The consumer validates its own source freshness, applicability, disclosure and
  effect eligibility. Native acceptance does not establish those facts for it.

Governance owns the acceptance decision and native evidence lifecycle. The runtime
owns production and accurate execution records; the exact record stores, references
and retention responsibilities must be assigned by the concrete contract. Projections
MUST preserve canonical native identity and verification bytes, not create a parallel
acceptance ledger. Hash agreement proves integrity relative to trusted material, not
the identity or authority of an otherwise untrusted sender.

## 7. Identity, retry and lifecycle separation

Keep activation/request, source ownership, permission scope, source dependencies,
native intent/authorization, logical run, concrete attempts, produced evidence,
acceptance, and consumption/effect identities distinguishable. This is not a demand
for one table or service per concept; exact mappings and identity preimages belong
to the component contracts.

An owning item is not the complete permission scope or dependency set. The shared
execution interface MUST NOT force future profiles to invent events or notifications.
Conversely, this architecture changes no current item/version foreign keys or required
advisory bindings. Scope-wide, empty-scope or multi-source work remains unsupported
until separately specified.

Each concrete operation has one authoritative retry decision path. Governance owns
dispatch retry permission; its designated dispatch scheduler schedules attempts within
that permission. The runtime executes and accounts for model/tool retries only within
the authorized per-call and aggregate limits. A bridge or SDK MUST NOT introduce an
unaccounted retry loop. The exact logical-run relationship to dispatch attempts,
attempt-start persistence and uncertain-call recovery must be defined before implementation.

Transport replay resolves the original request/dispatch or reports a conflict; it
does not grant fresh execution. Consumption or delivery retry MUST NOT redispatch
intelligence. Persisted attempt-before-effect requirements remain owned by the relevant
effect boundary, including Spine's existing `side_effect_attempts` gate. Deterministic
IDs do not establish exactly-once external effects or exactly-once billable model calls.

Source-item lifetime, execution lifetime, authorization expiry, information validity,
selection cutoff and delivery deadline are separate facts. A future durable workflow
may need its own external coordinator and lifetime; it cannot extend a current
authorization or reopen a terminal advisory branch by implication.

## 8. Freshness and result consumption

The source authority answers whether a request's referenced facts remain current;
governance and the runtime honor the profile's required freshness handoff before
dispatch. Consumers check again before applying results, and effect executors apply
their own attempt-start validation. A successful check is not an indefinite lock on
the source or permission to reuse the result for another request.

Concrete protocols MUST specify the check/dispatch race, expiration and cancellation
semantics, and behavior when freshness is unknown. They MUST NOT claim an atomic
cross-system transaction merely because both systems persist receipts. If facts change
after execution starts, incurred calls remain real evidence; results may become unusable.
Cancellation is not proof that an external call never started or that no cost was incurred.

Information freshness is also distinct from source-version freshness: an unchanged
event does not make an old weather forecast current. Acceptance can remain historically
valid while later consumption is disallowed. The consumer records its own refusal
without rewriting native evidence or acceptance history.

## 9. First profile: notification-activated read-only advisory

The complete profile requirements remain in [contextual-advisories.md](contextual-advisories.md),
not replaced by this summary. The first slice preserves:

- One supported location-bearing event/occurrence and explicit notification-template
  activation, immutable context/definition binding, and finite configurable budgets.
- Minimized permitted context; additional detail and sensitive medical enrichment
  require the profile's explicit permissions. Ownership or relationships do not imply disclosure.
- Bounded runtime initiative inside approved research capabilities; no canonical
  mutation, direct messaging, child workflow or multi-agent delegation.
- Exactly the profile's allowed outcomes: `advisory`, `no_action`, or
  `request_clarification`, narrowed by the effective grant. Failure is not `no_action`.
- Unsupported approval stops enrichment without dispatch, automatic retry or later
  silent resumption. It does not prevent an independently eligible ordinary reminder.
- Ordinary fallback on unusable enrichment. Accepted `no_action` suppresses a reminder
  only under explicit silence permission. Clarification uses the same bound delivery path.
- One logical notification identity and serialized selection: late evidence cannot
  create a second delivery or reopen a committed branch. The existing pre-attempt stale
  content downgrade and attempt-start branch-freeze rules remain intact.
- Derivative-materialization failure requires the existing explicit recovery path,
  not research rerun or an automatic branch switch. Recovery preserves accepted evidence.

The golf preparation example tests useful discretionary research; it does not hardcode
weather as the universal objective. The first registered capabilities, providers and
budget values still need selection and contracts. A future task, planning sweep, or
approval-bearing action requires a separate profile; flexibility here does not enable it.

## 10. Adoption, remaining work and review

Current adoption state: this is the proposed shared source. Spine reference additions
are draft design links only. No Impetus or governance repository has adopted this
version through this change, and no runtime declares conformance.

The [native-handoff investigation](../docs/design-notes/advisory-native-handoff-investigation.md)
found reusable native intent/policy/evidence/replay machinery, but not a ready-to-use
bounded research executor or complete advisory authorization/acceptance interface.
The next component work must distinguish new behavior from reused implementation.

Before an implementation slice is supported, resolve:

1. Native authorization, invocation, logical-run/attempt and evidence acceptance
   contracts, including budgets, expiry, failure and retry ownership.
2. Execution component HLD, selected model backend and explicit first capabilities,
   adapter enforcement, credentials, accounting and output validation.
3. Spine's immutable submission mapping, native reference verification, freshness
   handoff, selection/recovery integration and operator readback.
4. The bounded transport and trust arrangement, interruption/replay protocol and
   dependency compatibility. A subprocess is an option, not an assumption of safety.
5. Matching versioned machine contracts and tests in owning projects, plus cross-system
   fixtures for denied/widened grants, exhaustion, duplicate and uncertain submission,
   stale sources, disallowed outcomes and late/fallback races.

Architectural review must check that each authority has one owner, adapters do not
expand grants, version references are reproducible, and all advisory protections are
preserved. Static examples and fake success receipts do not prove real execution;
later runtime tests must include both deterministic failure oracles and the authorized
bounded usefulness proof. An audit of this document cannot by itself certify those.

This draft introduces no public command, machine schema, migration, shared datastore,
general workflow engine, new authentication system or implemented capability. It does
not reactivate deferred resilience/storage work or make facets/people extensions blanket
prerequisites. Impetus may derive its HLD from this source after checkpointing; native
governance and Spine contracts remain in their owning repositories.

## Revision history

| Version | Status | Change |
| --- | --- | --- |
| `0.1.0-draft.1` | Proposed | Initial shared role boundaries, adapter extensibility, evidence/budget/freshness ownership, advisory preservation and downstream version references |
