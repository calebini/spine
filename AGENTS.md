# Spine Agent Instructions

Spine follows the Cortext1 component scaffold standard.

## Current Maturity

Spine is in seed-spec phase. Prefer concept, schema, and boundary clarification before runtime code.

Create implementation directories only when there is executable behavior to place there. The initial authoritative surface is:

- `README.md` for orientation
- `specs/` for normative design and compatibility promises
- `specs/decisions/` for accepted architecture decisions

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
