# Spine Architecture

Status: Draft v0.1.0  
Scope: Component boundaries, module posture, and runtime relationships

## 1. Architectural Doctrine

Spine stores coordination truth.

Tickerd keeps time.

Foreman/Threshold governs boundary crossing.

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

The Spine tickerd adapter SHOULD map eligible Spine work instances to tickerd work items.

In `observe_only` mode, the adapter MUST inspect or report eligible work without external side effects.

In `active` mode, the adapter MAY process eligible work, but any external write MUST pass through Spine side-effect attempt accounting and any required Foreman/Threshold approval.

## 5. Relationship to Foreman/Threshold

Foreman may later be branded conceptually as Threshold. Spine MUST NOT assume a repository or package rename.

Spine creates coordination pressure:

- an item becomes actionable
- a projection is stale
- a reminder is due
- a dependency puts an event at risk
- a user decision is needed
- an automation candidate exists

Foreman/Threshold constrains boundary crossing:

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

## 7. Suggested Future Package Boundaries

Implementation directories should be added when behavior exists:

- `src/spine/core/` for pure domain rules and deterministic state transitions
- `src/spine/models/` for storage-facing records or typed data shapes
- `src/spine/services/` for orchestration that stays provider-agnostic
- `src/spine/adapters/` for database, tickerd, and vendor integration boundaries
- `src/spine/protocols/` for stable public interfaces

Core code MUST NOT depend on adapters.
