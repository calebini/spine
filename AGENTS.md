# Spine Agent Instructions

Spine follows the Cortext1 component scaffold standard.

## Current Maturity

Spine is an implemented alpha with a staged backend on `cortext1`. The sibling
`kinflow-web-ui` repository provides a connected read-only frontend under operator
testing. Do not assume the frontend or staging deployment is missing or requires
a general qualification review. Draft features still require concept, schema, and boundary clarification
before runtime code.

Create implementation directories only when there is executable behavior to place there. The authoritative surface is:

- `README.md` for orientation
- `specs/` for normative design and compatibility promises
- `specs/decisions/` for accepted architecture decisions
- `contracts/` for machine-readable public agreements

## Work Tracking

Use `docs/BACKLOG.md` for ordered work, dependencies, task status, and completion
evidence. Use `docs/IMPLEMENTATION_PLAN.md` for roadmap rationale and delivery history.
Update the backlog when taking, blocking, completing, or withdrawing a tracked task.
Focus on concrete items the operator brings. Do not prescribe or start gap analyses,
general evidence reviews, or qualification campaigns unless explicitly requested.
Retained roadmap candidates are not selected work or automatic priorities. Appropriate
verification remains part of a selected concrete change. Backlog entries do not override
specifications or turn draft features into accepted runtime contracts.

Resilience, containment, recovery/scalability qualification, and the related storage
lifecycle backlog items SPINE-004–007 and SPINE-010 are deferred by operator direction.
Do not restart them or impose them as blanket prerequisites for other work without
an explicit request. Preserve implemented safeguards and task-specific verification.

## Doctrine

Spine is the canonical coordination ledger and planning fabric.

Calendars, maps, messengers, dashboards, and local agents are projections. External tools may mirror, enrich, notify, render, or execute side effects, but they are not the authority for coordination truth.

## Donor Rule

Kinflow 1.0 is a donor, not the foundation.

Salvage durable machinery and discipline from Kinflow:

- deterministic lifecycle posture
- reason-code discipline
- audit and replay model
- idempotency receipts
- the single durable attempt-ledger pattern behind Kinflow's `delivery_attempts`
- migration verification culture
- contract and version pinning discipline
- fail-closed adapter boundaries
- tickerd extraction pattern
- deterministic tests around replay and version conflicts

Do not carry forward Kinflow's event-root ontology, family-specific core naming, JSON identity blobs, event-only reminders, or daemon-kernel ownership.

## Component Boundaries

Spine owns:

- coordination items and versions
- source-of-truth state
- relationships, blockers, and dependencies
- time and location semantics
- notification and work eligibility
- audit/replay facts
- candidate actions and projection truth

Spine does not own:

- daemon heartbeat or singleton runtime semantics, which belong to tickerd
- safety approval gates, which belong to Foreman/Threshold
- vendor-side state, which belongs to adapters as projections
- external side effects without a persisted attempt record

Spine's canonical generic adapter-result/send ledger is `side_effect_attempts`.

## Verification Expectations

For spec-only changes, review affected spec files for internal consistency and ensure the README still points at the authoritative documents.

When runtime code, contracts, migrations, or public behavior are added, introduce matching tests and version declarations before treating the behavior as stable.
