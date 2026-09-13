# Decision 0005: Profile-Scoped Advisory Execution

Status: Proposed — specification-only protection amendment; not a runtime capability
Date: 2026-09-13

## Context

The first [contextual-advisory profile](../contextual-advisories.md) enriches one
notification for a location-bearing event. Its deliberately narrow validation,
single-delivery, fallback, and recovery rules remain necessary. They must not become
universal requirements for every future request to external execution.

The [three-case assessment](../../docs/design-notes/advisory-extensibility-gap-analysis.md)
examined location-free task research, scope-wide planning, and an approval-bearing
booking workflow. It found extension risks, not authority to implement those cases.
In particular, existing work and candidate-action rows require an owning item/version;
a new trigger alone would not make them scope-owned workflow roots.

## Proposed decision

### 1. Profile requirements are binding, not universal

The event, primary location, notification activation, three allowed outcome kinds,
one logical delivery identity, and unsupported-approval termination requirements of
advisory v1 MUST remain enforced for that profile. Calling a field profile-specific
does not make it optional in an advisory request or permit a new outcome.

Future capabilities MUST use separately specified, versioned contracts with explicit
validation and authorization. They MUST NOT be implemented by relabeling a task as an
event, inventing a notification or delivery target, overloading advisory prose with
commands, or admitting arbitrary extension objects. Unknown profiles remain unsupported.
Existing published contract meanings and stored identities cannot change by implication.

### 2. Keep five responsibilities distinguishable

Designs MUST distinguish:

- **Activation:** the recorded reason work is requested, not permission to execute it.
- **Coordination binding:** any owning item, permitted execution scope, and exact
  source dependencies. These are distinct facts, even when all concern one event.
- **Execution request:** objective, minimized context, requested capabilities, limits,
  and correlation to native governance artifacts; a request is not a grant.
- **Execution and evidence:** native dispatch, run, attempts, and produced/accepted
  evidence, with their owning authorities and replay semantics preserved.
- **Result consumption:** the separately permitted use of accepted evidence, such as
  selecting reminder content. Acceptance alone grants neither mutation nor delivery.

These are conceptual responsibilities, not five new tables or mandatory services.
Advisory v1 instantiates them with its existing required notification/event bindings.
A common native execution interface MUST NOT require future callers to fabricate those
bindings solely to use it. Advisory-local schemas may and must retain those requirements.

### 3. Do not make one item's lifecycle the universal process lifecycle

Current item-bound work and candidate-action constraints remain unchanged. Future
scope-level or multi-source operations require an explicit ownership, bounded context,
authorization, completeness, and freshness contract before implementation. A genuine
planning task may be an owner where product semantics warrant it; a hidden dummy item
is not a substitute for specifying scope and dependencies. No choice of new storage
or generic source-reference schema is made here.

Coordination item state, a future external process lifetime, one bounded invocation,
authorization/evidence expiry, and notification selection/delivery deadlines MUST NOT
be collapsed into one status, identity, timeout, or retry counter. The advisory
fallback deadline does not define all future workflow lifetimes. Conversely, a future
workflow cannot extend an advisory deadline, resume its terminal unsupported-approval
path, or reopen its committed fallback/suppression/delivery branch.

### 4. Preserve native authority and effect ownership

Spine retains coordination truth and its validated persistence operations. Governance
retains native authorization, approval validity, dispatch and evidence acceptance.
Any future durable workflow waiting, step coordination, and callbacks belong to an
explicit external runtime/coordinator boundary, not hidden Spine reminder state.
Tickerd retains cadence and singleton mechanics; canonical Spine schedules and future
workflow timers must retain distinct ownership. No specific runtime is selected.

The first advisory native mapping MUST identify which authority owns logical runs,
model/tool attempts, budget accounting, and retry permission; references or projections
must not create competing native records. A governed dispatch attempt and a concrete
vendor-operation attempt may represent different facts. Any future write integration
MUST define their correlation, the effect executor, and a single authoritative retry
decision path for each effect before support is advertised. This does not remove
Spine's existing persisted-attempt-before-side-effect rule or claim exactly-once effects.

Facet values remain canonical typed facts, not workflow checkpoints, grants, executable
recipes, or automatically accepted external observations. Future people/context
extensions cannot infer access or disclosure permission from relationships alone.

## Preservation and acceptance boundary

This amendment changes no existing field cardinality, enum, identifier derivation,
database constraint, command registry, version advertisement, or runtime behavior.
It does not authorize generalized automation, a new repository, or a broader review
campaign. The deferred resilience/storage initiatives remain deferred; relevant
existing safety rules and concrete feature-specific verification still apply.

Review this proposal with the targeted advisory, architecture, and ontology additions
and the [preservation checklist](../../docs/design-notes/advisory-protection-preservation-checklist.md).
Check both preservation of advisory v1 and separation of the three future cases.
The checklist is manual comparison evidence, not independent audit or proof of semantic
equivalence. Ratification and the remaining exact native/machine contracts precede
runtime implementation; this decision does not settle them by implication.
