# Spine Overview

Status: Draft v0.3.0
Scope: Canonical coordination ledger and planning fabric
Created: 2026-05-31

## 1. Purpose

Spine provides a deterministic source of truth for personal coordination.

It records what should be true about plans, obligations, relationships, work, state transitions, projections, decisions, and side effects. External tools may render, enrich, deliver, or execute from that truth, but they must not become canonical authorities.

## 2. Source-of-Truth Doctrine

Spine is the canonical coordination ledger and planning fabric.

Spine MUST own:

- coordination intent
- item state and item history
- item versions
- item relationships
- subject and group references
- time semantics
- location semantics
- notification and work eligibility
- deterministic notification schedule expansion and durable reminder materialization
- atomic high-level creation of one scheduled event or task with its initial reminder policies and optional bounded work
- atomic high-level update and cancellation of scheduled events or tasks with mandatory stale-work reconciliation
- projection state
- adapter attempt outcomes
- audit and replay facts
- candidate action records, when automation pressure exists

External systems MUST be treated as projections or side-effect targets.

External systems MUST NOT be the authority for canonical item state, notification policy, location truth, dependency truth, or lifecycle history.

## 3. Product Shape

Spine is not merely an event scheduler. It is a general coordination core with type-specific profiles.

The initial expected profiles are:

- family scheduling
- task management
- project, trip, and collection planning

The shared core MUST support common concepts across profiles:

- subjects and subject groups
- coordination items
- versioned item facts
- first-class time models
- first-class locations
- explicit item archetype classification
- item relationships and dependencies
- participants, assignees, watchers, and notification recipients
- reusable, owner-scoped notification profile definitions and snapshot applications
- generated work instances
- projection records
- side-effect attempts
- audit records

## 4. Core Ontology

The root concept is `coordination_item`.

A coordination item represents a durable unit of coordination truth. The item may be an event, task, project, collection, deadline, routine, reminder, availability block, or another future type.

The core item record owns identity and lifecycle state that is common across item types. Type-specific detail tables own fields that do not generalize cleanly.

Events MUST NOT be modeled as the root concept.

Tasks MUST NOT be forced into event semantics.

Events MUST NOT be forced into task semantics.

## 5. Candidate Item Types

The initial ontology should anticipate:

- `event`
- `task`
- `project`
- `collection`
- `deadline`
- `routine`
- `reminder`
- `availability_block`

Only `event`, `task`, `project`, and `collection` need to be treated as near-term implementation targets.

## 6. Non-Goals

Spine does not own:

- daemon heartbeat, singleton locks, runtime modes, or daemon-cycle cadence semantics
- third-party calendar, map, messenger, or dashboard state
- approval policy for unsafe or boundary-crossing actions
- vendor-specific contact identity as canonical subject identity
- a global multi-service scheduler
- opaque planning or reasoning as hidden state

## 7. Determinism Requirements

Spine MUST prefer explicit persisted facts over hidden inference.

Archetype selection and notification-profile default resolution MUST be explicit,
bounded, and receipt-bearing when they affect a write. Spine MUST NOT classify free
text or traverse undeclared group membership to choose reminder behavior during
canonical command handling. `specs/notification-profiles.md` owns that draft
capability boundary.

Historical UTC trigger and attempt timestamps MUST NOT be recomputed on read or replay.

Every external write MUST be represented by a persisted side-effect attempt with enough evidence to support retry, audit, and replay.

State transitions MUST be reason-coded once a reason-code catalog exists.

Adapter failures MUST NOT mutate canonical coordination truth unless the domain transition itself is explicitly represented and valid.

Routine operation MUST remain bounded under repetition, backlog, accumulated history,
partial failure, and storage pressure. `specs/operational-resilience.md` owns the
cross-cutting resource, containment, recovery, and qualification requirements. Those
requirements do not authorize deletion of canonical evidence or transfer coordination
authority to Tickerd, an adapter, or a host supervisor.

Exact runtime admission against Tickerd and the translation from Spine-owned storage
facts into Tickerd's generic safety-stop protocol are governed by
`specs/compatibility.md`. That compatibility boundary does not make Tickerd
authoritative for coordination truth, work eligibility, or storage thresholds.

High-level authoring convenience MUST compose canonical item, recurrence, notification, work, audit, and receipt models without becoming a second authority. A composite command either commits its complete requested canonical bundle or none of it, and it MUST remain separate from external delivery.

Cross-item agenda views MUST remain bounded read models over canonical current truth. They MUST NOT introduce a second schedule store or silently paginate across changed source facts.
