# Spine

Spine is the canonical coordination ledger and planning fabric for a personal Cortext1 agent environment.

It records coordination truth locally and deterministically. Calendars, maps, messengers, dashboards, and local agents are projections: they can mirror, enrich, notify, render, or execute side effects, but they do not own intent, state, history, decisions, or replayable truth.

## Product Promise

Spine owns coordination truth. Adapters make it visible, actionable, or enriched elsewhere.

## Current Status

Seed-spec phase with an initial runtime scaffold, deterministic core primitives, a SQLite local ledger schema foundation, atomic event/task v1 creation workflows, versioned lifecycle mutation workflows, first supporting-set/relationship workflows, durable side-effect pressure ledgers, work outcome lifecycle services, provider-agnostic internal services, a Tickerd work adapter boundary with observe-only and explicit active processor outcome handling, generic attempt-backed side-effect processing, and an OpenClaw-style notification outbound specialization with fake-sender coverage. This repository intentionally starts with orientation and normative specs before adding broader runtime behavior.

Authoritative starting points:

- `specs/overview.md` defines purpose, doctrine, and non-goals.
- `specs/architecture.md` defines component boundaries and runtime relationships.
- `specs/ontology.md` sketches the first durable ontology and data model.
- `specs/agent-command-contract.md` defines the MVP agent command core and CLI contract.
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
- `docs/AGENT_OPERATOR_GUIDE.md`: agent-facing contract for operating current Spine runtime surfaces safely
- `docs/OPENCLAW_DEPLOYMENT_RUNBOOK.md`: operational rollout notes for the first OpenClaw replacement path
- `contracts/`: machine-readable command fixture manifest and shared response schema
- `deploy/`: deployment templates for systemd and environment files
- `src/spine/`: initial Python package scaffold
- `src/spine/ledger/`: canonical local persistence boundary
- `src/spine/services/`: provider-agnostic orchestration over ledger workflows
- `src/spine/adapters/`: external runtime and side-effect boundaries, starting with Tickerd work execution, generic side-effect attempt processing, and OpenClaw-style notification delivery
- `tests/`: executable expectations

Implementation, contracts, migrations, and tests should be added only when their behavior is ready to be made concrete.

## Local Runtime Smoke

Install Spine locally during development so runtime entry points do not depend on manual `PYTHONPATH=src` wiring:

```bash
python3 -m pip install -e ".[dev,test]"
```

With Tickerd installed, or with `TICKERD_SRC` pointing at a local Tickerd `src` directory, Spine can run a bounded observe-only Tickerd pass over a local SQLite ledger:

```bash
spine-seed-demo /tmp/spine-demo.sqlite
# For an already-created ledger, seed the demo only when absent:
spine-seed-demo --if-absent /tmp/spine-demo.sqlite
PYTHONPATH="$TICKERD_SRC" spine-tickerd-observe /tmp/spine-demo.sqlite
PYTHONPATH="$TICKERD_SRC" spine-tickerd-runner \
  --db /tmp/spine-demo.sqlite \
  --state-dir /tmp/spine-state \
  --max-cycles 1
PYTHONPATH="$TICKERD_SRC" spine-worker \
  --db /tmp/spine-worker.sqlite \
  --state-dir /tmp/spine-worker-state \
  --initialize-schema \
  --mode observe_only \
  --bindings openclaw \
  --openclaw-sender fake \
  --max-cycles 1
PYTHONPATH="$TICKERD_SRC" spine-openclaw-smoke \
  --db /tmp/spine-openclaw-smoke.sqlite \
  --state-dir /tmp/spine-openclaw-state \
  --seed-demo \
  --max-cycles 1
```

The seed command creates one subject, one task, one notification policy, and one eligible generated work instance. The observe command emits JSONL records to stdout. The foreground runner and worker write lock, owner, health, and event files under the state directory. Neither command performs vendor writes in the default `observe_only` mode. The OpenClaw smoke runs Tickerd in active mode with a file-backed fake sender and writes fake outbound evidence to `openclaw_sends.jsonl` under the state directory.

The OpenClaw smoke is fake by default. A real OpenClaw gateway send requires an explicit operator opt-in:

```bash
PYTHONPATH="$TICKERD_SRC" spine-openclaw-smoke \
  --db /tmp/spine-openclaw-gateway.sqlite \
  --state-dir /tmp/spine-openclaw-gateway-state \
  --seed-demo \
  --sender gateway \
  --allow-real-send \
  --max-cycles 1
```

The gateway sender calls `openclaw gateway call send --params ... --json`. It reads `SPINE_OPENCLAW_GATEWAY_URL`, `SPINE_OPENCLAW_GATEWAY_TOKEN`, `SPINE_OPENCLAW_GATEWAY_PASSWORD`, and `SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS`, with Kinflow gateway env names accepted as migration fallback.

## Ledger Migrations

Spine keeps `schema.sql` as the latest fresh-ledger bootstrap and stores numbered SQLite migrations under `src/spine/ledger/migrations/` for existing ledgers. Before running a durable local ledger through Tickerd or an adapter, apply and verify migrations:

```bash
spine-ledger-migrate \
  --db ~/.spine/ledger.sqlite \
  --initialize-if-empty
```

For an already-initialized ledger, omit `--initialize-if-empty`. To run verification without applying migrations:

```bash
spine-ledger-migrate \
  --db ~/.spine/ledger.sqlite \
  --verify-only
```

Verification checks the recorded schema version, required tables and indexes, SQLite foreign-key and integrity checks, and Spine's full ledger invariant sweep.

## Local Verification

CI runs the unittest suite, Ruff, and strict mypy over the mature `src/spine/core` and `src/spine/ledger` surfaces. Run the same checks locally with:

```bash
python3 -m unittest discover -s tests
ruff check src/spine/core src/spine/ledger
mypy --strict src/spine/core src/spine/ledger
```
