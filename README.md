# Spine

Spine is the canonical coordination ledger and planning fabric for a personal Cortext1 agent environment.

It records coordination truth locally and deterministically. Calendars, maps, messengers, dashboards, and local agents are projections: they can mirror, enrich, notify, render, or execute side effects, but they do not own intent, state, history, decisions, or replayable truth.

## Product Promise

Spine owns coordination truth. Adapters make it visible, actionable, or enriched elsewhere.

## Current Status

Seed-spec phase with an initial runtime scaffold, deterministic core primitives, a SQLite local ledger schema foundation, atomic event/task v1 creation workflows, versioned lifecycle mutation workflows, first supporting-set/relationship workflows, durable side-effect pressure ledgers, work outcome lifecycle services, provider-agnostic internal services, and a Tickerd work adapter boundary with observe-only and explicit active processor outcome handling. This repository intentionally starts with orientation and normative specs before adding broader runtime behavior.

Authoritative starting points:

- `specs/overview.md` defines purpose, doctrine, and non-goals.
- `specs/architecture.md` defines component boundaries and runtime relationships.
- `specs/ontology.md` sketches the first durable ontology and data model.
- `specs/decisions/0001-kinflow-is-donor-not-foundation.md` records the Kinflow relationship.

## First Product Profiles

Spine should support a shared coordination core with profiles layered over it:

- family scheduling
- task management
- trips, projects, and collections
- reminders and generated work instances
- first-class locations
- item relationships and dependencies
- deterministic projection and adapter ledgers

Events and tasks share a common spine, but neither is forced into the other's lifecycle. The core owns common identity, versioning, relationships, subjects, time, locations, work eligibility, audit, and side-effect accounting. Type-specific tables own event and task details.

## Relationship to Nearby Components

Kinflow 1.0 is a donor. Its deterministic lifecycle posture, audit/replay habits, reason-code discipline, idempotency model, and adapter-result ledger lessons should inform Spine. Its event-root and family-specific ontology should not become Spine's foundation.

tickerd owns daemon heartbeat and bounded runtime execution. Spine adapts eligible work into tickerd work items.

Foreman/Threshold owns approval and boundary crossing policy. Spine may generate candidate actions; Foreman/Threshold decides whether those actions are allowed, require approval, or are blocked.

Adapters touch external systems and persist outcomes back into Spine. Projection failures damage projections, not canonical truth.

## Repository Shape

This repository follows the Cortext1 component scaffold standard incrementally:

- `README.md`: orientation
- `specs/`: normative design and compatibility promises
- `specs/decisions/`: accepted decisions
- `docs/IMPLEMENTATION_PLAN.md`: non-normative build sequence for moving from specs to executable behavior
- `src/spine/`: initial Python package scaffold
- `src/spine/ledger/`: canonical local persistence boundary
- `src/spine/services/`: provider-agnostic orchestration over ledger workflows
- `src/spine/adapters/`: external runtime and side-effect boundaries, starting with Tickerd work observation
- `tests/`: executable expectations

Implementation, contracts, migrations, and tests should be added only when their behavior is ready to be made concrete.

## Local Runtime Smoke

With the sibling Tickerd checkout available, Spine can run a bounded observe-only Tickerd pass over a local SQLite ledger:

```bash
PYTHONPATH=src python3 -m spine.runtime.seed_demo /tmp/spine-demo.sqlite
PYTHONPATH=src:../tickerd/src python3 -m spine.runtime.tickerd_observe /tmp/spine-demo.sqlite
PYTHONPATH=src:../tickerd/src python3 -m spine.runtime.tickerd_runner \
  --db /tmp/spine-demo.sqlite \
  --state-dir /tmp/spine-state \
  --max-cycles 1
```

The seed command creates one subject, one task, one notification policy, and one eligible generated work instance. The observe command emits JSONL records to stdout. The foreground runner writes lock, owner, health, and event files under the state directory. Neither command performs vendor writes in the default `observe_only` mode.
