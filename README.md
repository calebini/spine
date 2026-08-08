# Spine

Spine is the canonical coordination ledger and planning fabric for a personal Cortext1 agent environment.

It records coordination truth locally and deterministically. Calendars, maps, messengers, dashboards, and local agents are projections: they can mirror, enrich, notify, render, or execute side effects, but they do not own intent, state, history, decisions, or replayable truth.

## Product Promise

Spine owns coordination truth. Adapters make it visible, actionable, or enriched elsewhere.

## Current Status

Seed-spec phase with an acceptance-verified canonical scheduling and notification fat slice. The runtime now implements structured recurrence across local-date, local-instant, and fixed-UTC bases; daily, weekly, monthly, and yearly frequencies; selectors, exceptions, overrides, series edits, bounded occurrence reads, lineage, and occurrence provenance. It also implements one-time, offset, fixed-elapsed, and local-calendar notification schedules; bounded opportunities; durable work materialization and reconciliation; Tickerd horizon repair; and fake OpenClaw delivery through `side_effect_attempts`. Schema version 7 is the single relational scheduling authority. Computed vectors, Draft 2020-12 fixture validation, migration/rollback tests, no-skip Tickerd integration tests, and a bounded fake-delivery canary are complete; production deployment and any real send remain separate operator actions.

Authoritative starting points:

- `specs/overview.md` defines purpose, doctrine, and non-goals.
- `specs/architecture.md` defines component boundaries and runtime relationships.
- `specs/ontology.md` sketches the first durable ontology and data model.
- `specs/recurrence.md` defines the canonical flexible recurrence-set model, deterministic identity and expansion, mutation, and occurrence-provenance boundaries.
- `contracts/schemas/recurrence-*.schema.json` and `contracts/recurrence-fixture-manifest.json` define the machine-readable recurrence contract family and initial fixtures.
- `specs/notifications.md` defines canonical notification schedules, opportunity expansion, durable work materialization, recurrence binding, and lifecycle reconciliation.
- `contracts/schemas/notification-*.schema.json` and `contracts/notification-fixture-manifest.json` define the machine-readable notification contract family and initial fixtures.
- `specs/agent-command-contract.md` defines the MVP agent command core and CLI contract.
- `docs/AGENT_QUICKSTART.md` gives a zero-context agent one executable, fake-only path through recurrence and recurring notifications.
- `specs/decisions/0001-kinflow-is-donor-not-foundation.md` records the Kinflow relationship.
- `specs/decisions/0002-first-class-delivery-targets.md` records the subject/group delivery target boundary.

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
- `docs/AGENT_QUICKSTART.md`: executable cold-start path for a new agent
- `docs/AGENT_OPERATOR_GUIDE.md`: agent-facing contract for operating current Spine runtime surfaces safely
- `docs/OPENCLAW_DEPLOYMENT_RUNBOOK.md`: operational rollout notes for the first OpenClaw replacement path
- `contracts/`: machine-readable command, recurrence, and notification agreements plus fixture manifests
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

The gateway sender calls `openclaw gateway call send --params ... --json`. It reads `SPINE_OPENCLAW_GATEWAY_URL`, `SPINE_OPENCLAW_GATEWAY_TOKEN`, `SPINE_OPENCLAW_GATEWAY_PASSWORD`, `SPINE_OPENCLAW_GATEWAY_TIMEOUT_MS`, and optional `SPINE_OPENCLAW_COMMAND_TIMEOUT_MS`. The gateway timeout is passed to OpenClaw; the command timeout wraps the local CLI process and defaults to gateway timeout plus 5000 ms of headroom.

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
