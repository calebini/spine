# Spine Implementation Plan

Status: Planning guide  
Scope: Practical build sequence for moving Spine from seed specs to executable behavior

This document is a working implementation plan, not a normative spec. If it conflicts with `specs/`, the specs win. Update this plan as implementation teaches us better sequencing.

## Goal

Build Spine in small executable slices while preserving its core doctrine:

- Spine is the canonical coordination ledger.
- External tools are projections or side-effect targets.
- Determinism, audit, replay, and version binding come before adapters.
- Runtime directories appear only when behavior exists.

## Production Replacement Charter

Near-term production goal: replace the current Kinflow production service with Spine for the existing concierge-agent scheduling/message-runner path.

Current production baseline:

- Kinflow is in production.
- The only production adapter is OpenClaw.
- OpenClaw serves as the message runner between the concierge agent and schedule/reminder delivery.
- The replacement target is not a broad adapter platform yet; it is the narrow path needed to decommission Kinflow safely.

Priority implications:

- Spine should prioritize notification/reminder work, OpenClaw delivery, Tickerd foreground runtime, durable side-effect attempts, and operator verification.
- Google Calendar, Foreman/Threshold, dashboards, and broad projection work are lower priority until the Kinflow replacement path is viable.
- Kinflow remains a donor/reference for OpenClaw adapter semantics, delivery attempt discipline, operational probes, and rollout/rollback posture.
- Spine must not clone Kinflow's event-root ontology, but it should deliberately salvage the production mechanics needed for this replacement.

## Current Ground

Already in place:

- Orientation in `README.md`.
- Normative specs in `specs/`.
- A converged MVP ontology in `specs/ontology.md`.
- Accepted spec versioning and freeze policy in `specs/SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md`.
- Python package scaffold under `src/spine/`.
- Deterministic canonical JSON and hash primitives.
- SQLite schema/bootstrap helpers for the canonical local ledger.
- Atomic event/task v1 creation workflows with audit rows and current reads.
- Versioned lifecycle mutation workflows for event cancellation, task completion, task cancellation, and shell archiving.
- Supporting-set and relationship workflows for locations, item subject roles, inert notification policies, stored MVP relations, derived relation aliases, and copy-forward into new versions.
- Durable side-effect pressure ledgers for work instances, candidate actions, side-effect attempts, and external projections.
- Work outcome lifecycle services for start, success, failure, cancellation, and retry scheduling.
- Provider-agnostic internal services for item commands, reminder work generation, work eligibility, projection planning, and pre-write attempt gates.
- Initial Tickerd work adapter, active processor outcome handling, and bounded observe-only runtime command.

Not yet in place:

- Public contracts or vendor adapters.
- A packaged tickerd dependency declaration; local integration currently runs against the sibling tickerd repo while packaging is settled.

## Build Strategy

Implement inside-out:

1. Pure deterministic primitives.
2. Local persistence and validation.
3. Versioned coordination item workflows.
4. Supporting tables and relationships.
5. Work, attempts, and projection ledgers.
6. Tickerd work observation/processing boundary.
7. OpenClaw notification delivery path for the Kinflow replacement milestone.
8. Foreman/Threshold approval boundary and broader vendor adapters.

Avoid starting with adapters, dashboards, or automation. Those should consume Spine truth only after Spine can create, version, validate, and audit its own canonical records.

## Stage 1: Runtime Scaffold

Purpose: create the smallest executable Python shape that can host tested behavior.

Steps:

- Add `pyproject.toml` with package metadata, Python version, pytest config, and minimal tooling.
- Add `src/spine/__init__.py`.
- Add `tests/` with a first smoke test.
- Add package subdirectories only as needed for first behavior:
  - `src/spine/core/` for deterministic pure logic.
  - `src/spine/models/` for typed records and validation shapes.
  - `src/spine/ledger/` when the first canonical local persistence boundary exists.
- Keep `services/` and `protocols/` absent until orchestration or public importable interfaces exist.

Initial modules:

- `src/spine/core/canonical_json.py`
- `src/spine/core/hashing.py`
- `src/spine/core/errors.py`
- `src/spine/models/enums.py`

Tests:

- package imports
- canonical JSON smoke tests
- hash output shape tests

Exit criteria:

- `pytest` runs.
- No empty architecture beyond the directories needed by real code.
- README still accurately describes repo shape.

## Stage 2: Deterministic Core Primitives

Purpose: implement the rules that everything else depends on before touching storage.

Steps:

- Implement canonical JSON encoding from `specs/ontology.md`.
- Implement SHA-256 lowercase hex hashing over canonical UTF-8 JSON bytes.
- Implement hash payload builders for:
  - `coordination_item_versions.intent_hash`
  - `coordination_item_versions.normalized_fields_hash`
  - `audit_log.payload_hash`
- Add enum definitions for MVP values:
  - item types
  - item shell status
  - event status
  - task status
  - temporal anchor kinds
  - relation types and statuses
  - attempt/projection/work statuses when their slices arrive
- Add structured validation errors with stable machine-readable codes.

Tests:

- object keys sort deterministically
- optional absent fields are omitted
- invalid surrogate code points are rejected
- numbers in hashed payloads are rejected
- string escaping follows the MVP rule
- hashes are stable across equivalent object insertion order
- enum validation rejects unknown values

Exit criteria:

- Deterministic hash behavior is fully covered by tests.
- No database or adapter code is required to test these primitives.

## Stage 3: SQLite Schema Foundation

Purpose: create the first durable local ledger substrate.

Recommended boundary:

- Use SQLite first.
- Put SQLite under `src/spine/ledger/`, not `src/spine/adapters/`.
- Treat `ledger/` as Spine's canonical local persistence boundary.
- Reserve `adapters/` for external projections and side-effect systems.
- Keep schema creation deterministic and local.
- Do not introduce a migration framework until there is more than one schema version to manage.

Tables for first schema:

- `subjects`
- `temporal_anchors`
- `coordination_items`
- `coordination_item_versions`
- `event_details`
- `task_details`
- `audit_log`

Steps:

- Add `src/spine/ledger/schema.sql` for schema version 1.
- Add `src/spine/ledger/sqlite.py` with connection/bootstrap helpers.
- Add a connection/bootstrap helper that can initialize an empty SQLite database.
- Enable foreign keys on every connection.
- Add schema introspection tests so table and constraint drift is visible.
- Represent timestamps as explicit stored values; do not generate hidden "now" values inside validators.

Validation to enforce in this stage:

- required fields
- enum values
- unique IDs
- item version contiguity starting at 1
- `coordination_items.current_version` equals the current item version
- event/task detail row legality
- minimal temporal anchor shape rules

Tests:

- initialize empty database
- insert a subject
- insert valid temporal anchors
- reject invalid temporal anchors
- reject event versions without event details
- reject task versions without task details
- reject event versions with task details
- reject non-contiguous versions

Exit criteria:

- A fresh local SQLite database can be initialized and inspected.
- The schema can support a valid event v1 and task v1 bundle.
- Invalid bootstrap bundles leave no partial canonical rows.

## Stage 4: Atomic Item Creation Workflows

Purpose: make the first real Spine behavior: create canonical coordination truth.

Workflows:

- `create_event_v1`
- `create_task_v1`
- optionally `create_project_v1` and `create_collection_v1` if they are cheap after the shared core exists

Inputs:

- caller-supplied or generated IDs
- created timestamp
- creating subject
- title and optional summary/source ref
- type-specific detail inputs
- optional initial supporting sets deferred until Stage 5

Steps:

- Add transaction wrapper for canonical writes.
- Build item shell plus version row atomically.
- Compute and persist `intent_hash` and `normalized_fields_hash`.
- Insert required detail row for event/task.
- Insert at least one audit row for creation.
- Reject stale or malformed inputs before commit.
- Make item creation idempotency explicit only if needed; do not invent adapter-style idempotency yet.

Tests:

- create event v1 with instant UTC start.
- create all-day event v1 with local date anchor.
- create task v1 with no due anchor.
- create task v1 with due local date.
- reject all-day event with instant start.
- reject timed event with date/window anchor.
- reject done task without completion metadata if implemented in initial status path.
- verify audit row is written.
- verify hashes match expected canonical payloads.

Exit criteria:

- A user-facing script or test fixture can create event and task records deterministically.
- Current item reads return the v1 canonical facts without inference.

## Stage 5: Version Mutation and Current Reads

Purpose: make Spine capable of changing canonical truth without mutating history.

Steps:

- Add current item read model.
- Add `create_next_item_version` helper.
- Enforce stale target rejection: mutation must target current version.
- Copy forward unchanged version-scoped supporting rows once Stage 6 exists.
- Implement event status transition:
  - `scheduled -> cancelled`
  - reject `cancelled -> scheduled`
- Implement task status transitions:
  - `open -> done`
  - `open -> cancelled`
  - reject transitions out of `done` and `cancelled`
- Keep shell archive separate from event/task lifecycle.

Tests:

- create v2 from current v1.
- reject v3 when v2 is missing.
- reject mutation against stale v1 after v2 exists.
- event cancellation creates a new version and preserves v1.
- task completion creates a new version and records completion fields.
- archive updates item shell and writes audit without mutating item versions.

Exit criteria:

- History is immutable.
- Current pointers move atomically.
- Basic lifecycle transitions are reasoned about as versioned truth.

## Stage 6: Supporting Sets and Relationships

Purpose: add the first richer coordination graph around items.

Tables:

- `locations`
- `item_locations`
- `item_subject_roles`
- `notification_policies`
- `coordination_item_relations`
- optionally `subject_groups` and `subject_memberships` if household modeling becomes immediately useful

Steps:

- Add first-class locations.
- Enforce immutable canonical location fields once referenced.
- Add item roles for participant, assignee, watcher, owner, recipient.
- Add notification policies as inert durable intent.
- Add relation rows with MVP stored relation types:
  - `depends_on`
  - `part_of`
- Add derived query helpers for:
  - `blocks`
  - `contains`
- Reject reserved relation types until a later accepted revision promotes them.
- Materialize complete supporting sets per item version.

Tests:

- create event with primary location.
- reject duplicate location role for same item version.
- create task with assignee.
- create active `depends_on` relation.
- derive inverse `blocks` relation in query helper.
- reject stored `blocks` relation.
- reject active duplicate relation.
- copy forward supporting sets into v2.
- verify no read-time fallback fills missing supporting rows.

Exit criteria:

- Spine can represent a family scheduling/task-management core item with participants, locations, notification intent, and dependencies.

## Stage 7: Work, Candidate Actions, Attempts, and Projections

Purpose: introduce durable side-effect pressure without executing real external side effects.

Tables:

- `work_instances`
- `candidate_actions`
- `side_effect_attempts`
- `external_projections`

Steps:

- Implement generated work rows for notification reminders.
- Enforce work version binding.
- Enforce derivative work provenance.
- Implement candidate action rows for:
  - `deliver_notification`
  - `sync_projection`
  - `request_user_decision`
- Implement side-effect attempt rows with pre-write durability semantics.
- Implement request payload/request hash computation.
- Implement projection records and staleness guards.
- Do not call tickerd, Foreman, or vendor APIs yet.

Tests:

- generate notification reminder work from a policy.
- reject reminder delivery pressure without a work row.
- reject work processing when item current version differs from work item version.
- create candidate action bound to item version.
- reject candidate action execution when stale.
- create `side_effect_attempts` row with durable request hash before simulated write.
- reject attempt with ambiguous origin linkage.
- reject projection write from stale source version.

Exit criteria:

- Spine can safely represent external pressure and attempted side effects without performing external writes.
- The single canonical attempt ledger exists.

## Stage 8: Internal Services

Purpose: introduce provider-agnostic orchestration only after storage rules are trustworthy.

Potential services:

- item command service
- reminder generation service
- work eligibility service
- projection planning service
- audit/replay inspection service

Rules:

- Services may orchestrate transactions.
- Services must not bypass core validators.
- Services must not depend on vendor adapters.
- Services must keep all external writes behind `side_effect_attempts`.

Exit criteria:

- Common workflows can be called through stable internal APIs instead of direct table manipulation.

## Stage 9: Tickerd Work Boundary

Purpose: let Spine consume Tickerd as the reusable runtime kernel without letting Tickerd own Spine truth.

Scope:

- Add a Spine-owned Tickerd adapter under `src/spine/adapters/`.
- Keep Tickerd as an optional runtime dependency until packaging is settled.
- Map eligible Spine `work_instances` into deterministic Tickerd `WorkItem` payloads.
- Respect Tickerd `observe_only`, `active`, and `suspended` mode semantics.
- In `observe_only`, validate/report eligible work without creating attempts or external writes.
- In `active`, reject stale work before any external work and delegate processing only through an explicit handler.
- Persist explicit active processor outcomes through Spine work lifecycle services.
- Do not integrate Foreman/Threshold in this stage.
- Do not call vendor APIs in this stage.

Tests:

- payload mapping is deterministic and JSON-friendly.
- eligible work maps to Tickerd work items when Tickerd is importable.
- observe-only processing blocks side effects.
- active mode without a configured processor blocks rather than inventing external behavior.
- Tickerd's reusable conformance smoke can run against the Spine adapter when the sibling Tickerd package is on `PYTHONPATH`.
- a bounded `python -m spine.runtime.tickerd_observe` command emits Tickerd JSONL records for eligible work.

Exit criteria:

- tickerd can observe eligible Spine work.
- the adapter can be wired into a Tickerd kernel without direct ledger ownership.
- a local user can run a finite observe-only pass against a Spine SQLite ledger.
- Spine remains the ledger of coordination truth, not the daemon owner.

## Stage 10: OpenClaw Replacement Path

Purpose: make Spine capable of replacing Kinflow's production OpenClaw message-runner path.

Scope:

- Map Spine notification reminder work into an OpenClaw outbound message envelope.
- Persist `side_effect_attempts` before any OpenClaw send attempt.
- Normalize OpenClaw outcomes into Spine work outcomes and side-effect attempt terminal state.
- Preserve deterministic idempotency keys and request hashes.
- Add a bounded active runtime smoke that uses a fake OpenClaw send function.
- Add an operator-facing verification command comparable to Kinflow's production probes.
- Keep Foreman/Threshold out of this milestone unless a concrete production gate requires it.

Exit criteria:

- A seeded reminder can be processed through the Spine Tickerd active path into an OpenClaw-style send attempt with durable attempt evidence.
- Success, retryable failure, permanent failure, and adapter binding failure are represented without mutating canonical item truth.
- The path can run locally with a fake sender and can be switched to the real OpenClaw command behind an explicit operator choice.
- Kinflow's current production message-runner behavior has an equivalent Spine path ready for controlled canary use.

## Stage 11: Foreman/Threshold Boundary

Purpose: prepare the approval boundary after the OpenClaw replacement path exists.

Potential integration:

- persist candidate actions before approval checks
- pass approval evidence out to Foreman/Threshold
- persist approval result references where needed
- do not embed approval policy in Spine

Exit criteria:

- Foreman/Threshold can govern boundary crossing.
- Spine remains the ledger of coordination truth, not the policy gate or daemon owner.

## Stage 12: Broader Adapter Slice

Purpose: expand projection and adapter behavior after the OpenClaw replacement path is proven.

Recommended first adapter:

- a local/no-op adapter or file-backed test adapter before a real vendor.

Then choose one real projection:

- Google Calendar read/write projection for selected event views, or
- a notification delivery adapter after reminder work lifecycle is clearer.

Rules:

- Persist `side_effect_attempts` before any external write.
- Use idempotency keys.
- Record provider references and terminal outcomes.
- Treat vendor state as projection state.

Exit criteria:

- One adapter can perform a bounded side effect with full attempt accounting and replay evidence.

## Stage 13: Contracts and Freeze Manifest

Purpose: promote stable public surfaces only when they deserve compatibility promises.

Triggers:

- another component consumes a Spine artifact as authoritative
- runtime declares implemented spec version
- migrations or protocols become public contracts
- release review needs exact artifact identity

Steps:

- Add `contracts/` only for machine-readable public agreements.
- Add stable public protocols only when importable interfaces exist.
- Add contract tests for promoted contracts.
- Introduce a freeze manifest only when there is at least one release-critical public artifact to pin.
- Implement the lightweight freeze verifier from `specs/SPINE_SPEC_VERSIONING_AND_FREEZE_POLICY.md`.

Exit criteria:

- Canonical surfaces have version declarations, tests, and optional manifest pins.

## Stage 14: Product Profiles

Purpose: build real user-facing value on top of the ledger.

Early profiles:

- family scheduling
- task management
- trips, projects, and collections
- reminders and generated work
- first-class locations
- dependency and blocker views

Likely sequencing:

1. Family scheduling without external writes.
2. Task management with dependencies and due/defer anchors.
3. Reminder generation as durable work.
4. Projection dashboards.
5. External calendar and messenger adapters.

Exit criteria:

- Product workflows are projections over Spine truth, not substitutes for it.

## What Not To Do Yet

- Do not start with a daemon.
- Do not start with Google Calendar or messenger writes.
- Do not create a second adapter-result ledger.
- Do not add a full contract/freezing system before public contracts exist.
- Do not build a broad web app before the local ledger can create and version records.
- Do not make every planned future package directory before behavior exists.

## First Three Checkpoints

Checkpoint 1: package and deterministic primitives

- `pyproject.toml`
- `src/spine/core/canonical_json.py`
- `src/spine/core/hashing.py`
- tests for canonical JSON and hashes

Checkpoint 2: SQLite schema and bootstrap validation

- schema initialization
- subjects, anchors, items, versions, event/task details, audit
- tests for valid and invalid bootstrap bundles

Checkpoint 3: item command workflows

- create event v1
- create task v1
- current reads and audit verification

Checkpoint 4: version mutation workflows

- create next item version
- event/task status transitions
- stale target rejection

After these checkpoints, Spine has broken ground for real: it can persist canonical coordination truth, prove deterministic identity, and reject invalid state without relying on external systems.
