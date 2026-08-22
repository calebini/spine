# Spine Architecture

Status: Draft v0.2.0
Scope: Component boundaries, module posture, and runtime relationships

## 1. Architectural Doctrine

Spine stores coordination truth.

Tickerd keeps time.

The governance authority governs boundary crossing.

Adapters touch the outside world.

Local agents and dashboards consume Spine truth or propose candidate actions; they do not replace Spine as the ledger.

## 2. Boundary Summary

Spine owns:

- coordination item identity
- item versions and current pointers
- item lifecycle validity
- item relationships and dependency status
- subject, group, and participation references
- first-class location records
- time models and temporal anchors
- notification policy and work eligibility
- deterministic notification-opportunity expansion and work materialization
- generated work instances
- candidate actions
- external projection records
- side-effect attempts
- audit log and replay facts

Spine does not own:

- runtime tick loop mechanics
- process singleton ownership
- approval policy evaluation
- vendor APIs
- external rendering state
- side effects without a persisted attempt row

## 3. Shared Core With Profiles

Spine SHOULD use one shared coordination core with profile-specific detail tables.

It MUST NOT split event scheduling and task management into unrelated services joined by glue. They share subjects, time, locations, dependencies, notifications, work generation, audit, projections, and daemon processing.

It also MUST NOT collapse task and event semantics into a single overloaded lifecycle.

Recommended shape:

- `coordination_items` for shared identity and state
- `coordination_item_versions` for versioned canonical facts
- `event_details` for event-specific facts
- `task_details` for task-specific facts
- `coordination_item_relations` for graph structure
- shared supporting tables for subjects, time, locations, policies, work, projections, attempts, and audit

## 4. Runtime Relationship to tickerd

tickerd owns:

- heartbeat
- runtime cycle
- `active`, `observe_only`, and `suspended` modes
- health/readiness reporting
- singleton ownership
- cadence and overrun behavior
- reconciliation loop
- bounded work item processing

Spine owns:

- what exists
- what is due
- what is blocked
- what is true
- which work instances are eligible
- which candidate actions exist
- which state transitions are valid
- how canonical notification schedules produce bounded opportunities and durable work

The Spine tickerd adapter SHOULD map eligible Spine work instances to tickerd work items.

In `observe_only` mode, the adapter MUST inspect or report eligible work without external side effects.

In `active` mode, the adapter MAY process eligible work through an explicit processor. The adapter MUST start the work before invoking the processor and MUST persist the processor outcome as Spine work lifecycle state. Any external write MUST pass through Spine side-effect attempt accounting and any required governance-authority approval.

## 5. Relationship to the Governance Authority

`specs/decisions/0003-role-based-governance-boundary.md` proposes that Spine name this relationship by protocol role rather than by repository, package, deployment, or product brand. Concrete component bindings belong to operational configuration.

Spine creates coordination pressure:

- an item becomes actionable
- a projection is stale
- a reminder is due
- a dependency puts an event at risk
- a user decision is needed
- an automation candidate exists

The governance authority constrains boundary crossing:

- allowed
- requires approval
- blocked
- needs evidence

Spine SHOULD persist candidate actions before asking any external approval or execution system to act.

## 6. Adapter and Projection Boundary

Adapters are replaceable projections or side-effect executors.

Examples:

- Google Calendar mirrors selected event views.
- Google Maps geocodes, enriches, or renders locations.
- WhatsApp and Discord deliver reminders.
- Local agents act on approved candidate actions.
- Dashboards render current Spine truth.

Adapters MUST NOT own canonical item state.

Adapters MUST write outcomes back as projection records, side-effect attempts, audit records, or explicit domain transitions.

Projection drift MUST be recoverable by replaying or reconciling from Spine truth.

## 7. Notification Scheduling Boundary

`specs/notifications.md` owns the canonical notification-scheduling semantics. A notification policy may express one notification, explicit target-relative offsets, or a bounded repeat window. Spine expands that intent into virtual notification opportunities and materializes selected actionable opportunities as durable `work_instances` rows.

Calendar notification cadence may reuse the frequency, selector, timezone-version, invalid-date, and DST-resolution semantics of `specs/recurrence.md`, but it does not create a recurrence set or store recurrence on a notification trigger anchor. Recurring-item notification policies bind to canonical item occurrences through current occurrence provenance before work is created.

Tickerd may initiate bounded materialization and process eligible work. It does not own notification schedule interpretation. Repeated notification opportunities are separate work instances; adapter retries remain attempts or retry state for one work instance. No policy or opportunity may invoke an adapter directly.

`specs/notification-rendering.md` defines the draft deterministic prose boundary for ordinary `notification_reminder` attempts. Rendering occurs only after existing freshness and late-handling gates grant attempt-start admission, uses the proposed attempt time plus current canonical item, target, occurrence/binding, and primary-location facts, and atomically persists immutable body evidence with the generic started attempt before external contact. It is a pure service/core concern with adapter-specific escaping at the edge; it does not make prose a scheduling fact or introduce a second attempt ledger. Contextual model-generated advisories remain a separate authority chain.

## 8. Composite Schedule Authoring Boundary

`specs/schedule-create.md` defines `schedule.create`, a provider-independent orchestration service over existing item, recurrence, notification, provenance, work, audit, and receipt authorities. It introduces no new canonical entity and MUST live in the service/command layer rather than core schedule normalization or an adapter.

`specs/schedule-show.md` defines the matching provider-independent read model. `schedule.show` aggregates current item and schedule truth with bounded policy, work, route, receipt, and side-effect-attempt evidence. It introduces no persistence and never treats its projection as a second authority. In particular, authoring commitment, virtual opportunity expansion, durable work materialization, delivery attempt, and delivery outcome remain separate observable lifecycle dimensions.

`specs/schedule-operator-tools.md` defines provider-independent operator compilation and projection conveniences. `schedule.build` resolves explicit input facts into a normal `schedule.create` request without consuming its command ID or writing ledger state. CLI `--compact` projects canonical schedule responses after command handling; it cannot replace, mutate, or become an alternate source for their full receipts and read models.

`specs/schedule-operations.md` defines the implemented provider-independent operational lifecycle layer. `agenda.show` is a computed cross-item read model, not an agenda entity or projection authority. `schedule.update` and `schedule.cancel` are composite services over existing item, recurrence, policy, provenance, work, audit, and receipt authorities. Their defining responsibility is atomic truth mutation plus mandatory stale-work reconciliation; they do not own recurrence math, notification cadence, delivery execution, or adapter state. The schema-8 runtime declares the complete version family and proves it with behavioral tests.

`specs/relative-temporal-bindings.md` defines the implemented cross-item derivation layer. `schedule.related_task.create` is an atomic convenience boundary over ordinary task, anchor, `part_of`, binding, policy, provenance, work, audit, and receipt authorities. `schedule.binding.list` and `schedule.binding.reconcile` provide bounded eventual follow-source repair without synchronous source-mutation fan-out. Concrete target anchors remain the schedule authority for ordinary reads; binding revisions explain and govern derivation. Attempt-start freshness blocks stale follow-source work independently of sweep cadence. Tickerd may run the bounded reconciliation loop, but it does not own binding state or temporal derivation.

One fresh success is one database transaction containing the complete new item bundle, initial policies, requested recurrence provenance and bounded work, one audit, and one command receipt. The orchestration service reuses internal deterministic domain and persistence functions; it MUST NOT chain public command handlers whose independent commits would expose partial state or synthetic subcommand receipts.

An explicit or named context-default delivery target resolves only to an existing canonical route. Transport context cannot approve, create, update, or send through that route. The governance authority retains approval authority, and adapters remain inaccessible until later durable work processing passes the ordinary side-effect-attempt gate.

## 9. Scheduled Contextual-Advisory Boundary

`specs/contextual-advisories.md` defines the draft cross-system boundary for one scheduled Spine trigger to request one governed, bounded, read-only agent run and create at most one ordinary derivative notification. Spine remains the coordination and schedule authority; the governance authority owns authorization and evidence acceptance; the agent runtime owns bounded reasoning and allowed tool use; the existing delivery path owns contact with a destination.

Cross-system contracts name these roles rather than their implementing components. Agent plans, tool choices, and generated prose are execution evidence, not canonical coordination truth. No model or tool is invoked during deterministic schedule expansion, and no agent outcome may bypass source-freshness checks or Spine's attempt-gated notification pipeline.

`specs/schedule-primary-location.md` defines the prerequisite public activation of the existing first-class location model on schedule create, update, readback, builder, agenda, and compact surfaces. It creates no location authority outside `locations` and `item_locations`, never lets location timezone alter schedule time, and does not make current notification work location-sensitive.

## 10. Suggested Future Package Boundaries

Implementation directories should be added when behavior exists:

- `src/spine/core/` for pure domain rules and deterministic state transitions
- `src/spine/models/` for storage-facing records or typed data shapes
- `src/spine/services/` for orchestration that stays provider-agnostic
- `src/spine/adapters/` for database, tickerd, and vendor integration boundaries
- `src/spine/protocols/` for stable public interfaces

Core code MUST NOT depend on adapters.
