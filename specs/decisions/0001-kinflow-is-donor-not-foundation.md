# Decision 0001: Kinflow Is Donor, Not Foundation

Status: Accepted  
Date: 2026-05-31

## Decision

Spine will be a fresh Cortext1 component and schema/domain epoch.

Kinflow 1.0 is a donor/reference, not the foundation. Spine must not be implemented as a search-and-replace refactor of Kinflow.

## Rationale

Kinflow contains durable machinery and hard-won discipline, but its root ontology is too narrow for Spine.

Kinflow began as a deterministic family scheduler. Spine needs to become a general coordination ledger and planning fabric that supports events, tasks, projects, trips, locations, relationships, projections, audit/replay, and future automation pressure over one shared core.

## Salvage From Kinflow

Spine should preserve these lessons:

- deterministic lifecycle posture
- reason-code discipline
- audit and replay model
- idempotency receipts
- `delivery_attempts` as the canonical adapter-result/send ledger
- migration verification culture
- contract and version pinning discipline
- fail-closed adapter boundaries
- tickerd extraction pattern
- deterministic tests around replay and version conflict handling

## Do Not Carry Forward

Spine should not inherit:

- `Event` as the root concept
- family-specific naming in the core
- `participants_json` or `audience_json` identity blobs
- blurred `person_id`, `target_id`, and delivery target identity
- event-only reminder semantics
- destination override fields spread across event, reminder, and attempt records
- daemon kernel code now superseded by tickerd
- tightly coupled family scheduler assumptions

## Consequences

Spine starts spec-first around a shared coordination core.

Family scheduling becomes a profile over the core, not the core ontology.

Task management is treated as a first-class near-term profile, not a later service glued onto event scheduling.

Kinflow code and specs may be consulted for patterns, tests, migration posture, and adapter lessons, but schema names and lifecycle shapes must be re-justified in Spine terms.
